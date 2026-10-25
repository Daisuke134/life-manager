"""K008: sqlite write-ahead effect reservation; NEVER retry an uncertain send.

The only supported adapter class is an explicitly offline fixture. One signed
grant may authorize multiple intent IDs, but a single SQLite transaction guards
the total reserved budget across them. Crash between DISPATCHING and send remains
uncertain and requires reconciliation, not retry.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3
from .authority import Grant, AuthorityVerifier


def _units(amount):
    try:
        d=Decimal(str(amount))
        q=d*1000000
        if not d.is_finite() or q!=q.to_integral_value() or not 0<=q<=10**15:
            raise ValueError("cost must be finite, positive-compatible and <=6 decimals")
        return int(q)
    except (InvalidOperation,TypeError):
        raise ValueError("invalid budget amount") from None


@dataclass(frozen=True)
class EffectRecord:
    key: str
    grant_id: str
    domain: str
    action: str
    target: str
    cost: float
    status: str
    receipt_ref: str | None = None
    dispatched_at: datetime | None = None


class DurableOutbox:
    def __init__(self,path: str | Path):
        self.path=str(path)
        with sqlite3.connect(self.path,timeout=15) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS effects (
                key TEXT PRIMARY KEY, grant_id TEXT NOT NULL, domain TEXT NOT NULL,
                action TEXT NOT NULL, target TEXT NOT NULL, cost_units INTEGER NOT NULL,
                status TEXT NOT NULL, receipt_ref TEXT, dispatched_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_effect_grant ON effects(grant_id)")

    @staticmethod
    def _as_record(row):
        if row is None: return None
        return EffectRecord(row[0],row[1],row[2],row[3],row[4],row[5]/1e6,
                            row[6],row[7],datetime.fromisoformat(row[8]))

    def record(self,key):
        with sqlite3.connect(self.path,timeout=15) as db:
            return self._as_record(db.execute(
                "SELECT key,grant_id,domain,action,target,cost_units,status,receipt_ref,dispatched_at FROM effects WHERE key=?",(key,)).fetchone())

    def execute(self,key: str,grant: Grant,signature: str,verifier: AuthorityVerifier,
                adapter,cost: float,at: datetime) -> EffectRecord:
        if not isinstance(key,str) or not key.strip() or len(key)>256:
            raise ValueError("nonempty stable intent key required")
        from .adapters.fixtures import OfflineFixtureAdapter
        # An arbitrary external caller must not bypass the fence by setting a flag.
        if type(adapter) is not OfflineFixtureAdapter or getattr(adapter,"offline_fixture",None) is not True:
            raise PermissionError("live effects are forbidden, even with a fixture grant")
        verifier.authorize(grant,signature,adapter.domain,adapter.action,adapter.target,cost,at)
        units=_units(cost)
        db=sqlite3.connect(self.path,timeout=15,isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT key,grant_id,domain,action,target,cost_units,status,receipt_ref,dispatched_at FROM effects WHERE key=?",(key,)).fetchone()
            if row is not None:
                if (row[1],row[2],row[3],row[4],row[5]) != (grant.grant_id,adapter.domain,adapter.action,adapter.target,units):
                    raise ValueError("idempotency key reused for a different effect")
                db.execute("COMMIT")
                return self._as_record(row)
            committed=db.execute("SELECT COALESCE(SUM(cost_units),0) FROM effects WHERE grant_id=?",(grant.grant_id,)).fetchone()[0]
            if committed + units > _units(grant.limit):
                raise PermissionError("cumulative grant budget exceeded")
            db.execute("""INSERT INTO effects
                (key,grant_id,domain,action,target,cost_units,status,receipt_ref,dispatched_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (key,grant.grant_id,adapter.domain,adapter.action,adapter.target,
                 units,"DISPATCHING",None,at.isoformat()))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction: db.execute("ROLLBACK")
            raise
        finally:
            db.close()
        try:
            receipt=adapter.send(key)
            if not isinstance(receipt,str) or not receipt:
                raise ValueError("empty fixture receipt")
        except Exception:
            self._set_status(key,"UNKNOWN",None)
        else:
            self._set_status(key,"SUBMITTED",receipt)
        return self.record(key)

    def _set_status(self,key,status,receipt_ref):
        if status not in {"UNKNOWN","SUBMITTED","PRESENT","ABSENT"}:
            raise ValueError("unsupported outbox state")
        with sqlite3.connect(self.path,timeout=15) as db:
            db.execute("UPDATE effects SET status=?,receipt_ref=? WHERE key=?",
                       (status,receipt_ref,key))


@dataclass(frozen=True)
class OwnedEffectRecord:
    key: str
    packet_json: str
    expected_parent: str
    status: str
    receipt_ref: str | None
    dispatch: bool = False


@dataclass(frozen=True)
class OwnedWorkflowDispatchRecord:
    request_id: str
    effect_key: str
    request_json: str
    status: str
    http_status: int | None
    run_id: int | None
    run_status: str | None
    conclusion: str | None
    provider_commit: str | None


class OwnedEffectJournal:
    """Durable owned-release reservation, not an executor or authority issuer.

    The host must call the original privileged admission and perform target Git
    CAS using expected_parent. Reservation is committed BEFORE that call. Any
    uncertain/crashed reservation is reconciled; it is never sent again here.
    Persistent owner storage is required; ephemeral CI is not deployment storage.
    """
    def __init__(self,path):
        self.path=str(path)
        with sqlite3.connect(self.path,timeout=15) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS owned_effects(
                key TEXT PRIMARY KEY,packet_json TEXT NOT NULL,expected_parent TEXT NOT NULL,
                status TEXT NOT NULL,receipt_ref TEXT)''')
            db.execute('''CREATE TABLE IF NOT EXISTS owned_deliveries(
                key TEXT PRIMARY KEY,status TEXT NOT NULL,evidence_json TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS owned_recovery_cursor(
                kind TEXT PRIMARY KEY CHECK(kind IN ('occurrence','delivery')),
                after_key TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS owned_workflow_dispatches(
                request_id TEXT PRIMARY KEY,effect_key TEXT NOT NULL UNIQUE,
                request_json TEXT NOT NULL,status TEXT NOT NULL,
                http_status INTEGER,run_id INTEGER,run_status TEXT,conclusion TEXT,
                provider_commit TEXT)''')
    def record(self,key):
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('SELECT key,packet_json,expected_parent,status,receipt_ref FROM owned_effects WHERE key=?',(key,)).fetchone()
        return OwnedEffectRecord(*row) if row else None
    def pending_records(self,limit=100,after_key=None):
        """Bounded saved intents; reading never restores dispatch permission."""
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('pending batch limit must be 1..100')
        if after_key is not None and (type(after_key) is not str or not after_key):
            raise ValueError('nonempty pagination key required')
        with sqlite3.connect(self.path,timeout=15) as db:
            rows=db.execute('''SELECT key,packet_json,expected_parent,status,receipt_ref
                FROM owned_effects WHERE status!='PRESENT' AND key>?
                ORDER BY key LIMIT ?''',(after_key or '',limit)).fetchall()
        return tuple(OwnedEffectRecord(*row) for row in rows)
    def delivery_record(self,key):
        import json
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('SELECT evidence_json FROM owned_deliveries WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None
    def pending_deliveries(self,limit=100,after_key=None):
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('delivery batch limit must be 1..100')
        if after_key is not None and (type(after_key) is not str or not after_key):
            raise ValueError('nonempty pagination key required')
        with sqlite3.connect(self.path,timeout=15) as db:
            rows=db.execute('''SELECT e.key,e.packet_json,e.expected_parent,e.status,e.receipt_ref
                FROM owned_effects e LEFT JOIN owned_deliveries d ON d.key=e.key
                WHERE e.status='PRESENT' AND (d.key IS NULL OR d.status!='VERIFIED')
                AND e.key>? ORDER BY e.key LIMIT ?''',(after_key or '',limit)).fetchall()
        return tuple(OwnedEffectRecord(*row) for row in rows)
    def recovery_batch(self,kind):
        if kind not in ('occurrence','delivery'):raise ValueError('unknown recovery kind')
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('SELECT after_key FROM owned_recovery_cursor WHERE kind=?',(kind,)).fetchone()
        read=self.pending_records if kind=='occurrence' else self.pending_deliveries
        records=read(after_key=row[0] if row else None)
        # Cycle over unresolved rows as well; never equate cursor with progress
        # on an external effect or allow writes while any row remains pending.
        return records or read()
    def complete_recovery_batch(self,kind,records):
        if kind not in ('occurrence','delivery'):raise ValueError('unknown recovery kind')
        if not records:return
        with sqlite3.connect(self.path,timeout=15) as db:
            db.execute('INSERT OR REPLACE INTO owned_recovery_cursor VALUES(?,?)',
                       (kind,records[-1].key))
    def save_delivery(self,key,evidence):
        import json
        from .models.source import _aware
        record=self.record(key)
        if (record is None or record.status!='PRESENT' or type(evidence) is not dict
                or evidence.get('effect_key')!=key or evidence.get('receipt_ref')!=record.receipt_ref
                or evidence.get('candidate_sha256')!=json.loads(record.packet_json)['candidate_sha256']
                or evidence.get('status') not in ('VERIFIED','PENDING','REGRESSION','UNKNOWN')):
            raise ValueError('delivery observation must bind exact saved occurrence')
        _aware(datetime.fromisoformat(evidence['observed_at']))
        serialized=json.dumps(evidence,sort_keys=True,allow_nan=False)
        with sqlite3.connect(self.path,timeout=15) as db:
            # Preserve historical verification; later live state is a different
            # observation, never retroactively erase the prior delivered fact.
            db.execute('''INSERT INTO owned_deliveries VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET status=excluded.status,evidence_json=excluded.evidence_json
                WHERE owned_deliveries.status!='VERIFIED' ''',(key,evidence['status'],serialized))
    @staticmethod
    def _workflow_record(row):
        return OwnedWorkflowDispatchRecord(*row) if row else None
    def workflow_dispatch_record(self,request_id):
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('''SELECT request_id,effect_key,request_json,status,http_status,
                run_id,run_status,conclusion,provider_commit
                FROM owned_workflow_dispatches WHERE request_id=?''',(request_id,)).fetchone()
        return self._workflow_record(row)
    def pending_workflow_dispatches(self,limit=100):
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('workflow recovery batch limit must be 1..100')
        with sqlite3.connect(self.path,timeout=15) as db:
            rows=db.execute('''SELECT request_id,effect_key,request_json,status,http_status,
                run_id,run_status,conclusion,provider_commit FROM owned_workflow_dispatches
                WHERE status!='PRESENT' AND status!='REJECTED' ORDER BY request_id LIMIT ?''',
                (limit,)).fetchall()
        return tuple(self._workflow_record(row) for row in rows)
    def claim_workflow_dispatch(self,request_id):
        with sqlite3.connect(self.path,timeout=15,isolation_level=None) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT request_id,effect_key,request_json,status,http_status,
                run_id,run_status,conclusion,provider_commit FROM owned_workflow_dispatches
                WHERE request_id=?''',(request_id,)).fetchone()
            if row is None:
                db.execute('ROLLBACK');raise ValueError('workflow request was not durably reserved')
            claimed=row[3]=='READY'
            if claimed:
                db.execute("UPDATE owned_workflow_dispatches SET status='SENDING' WHERE request_id=?",
                           (request_id,))
                effect = db.execute('''UPDATE owned_effects SET status='DISPATCHING'
                    WHERE key=? AND status='RESERVED' ''',(row[1],))
                if effect.rowcount != 1:
                    raise ValueError('workflow claim has no reserved owned effect')
                row=db.execute('''SELECT request_id,effect_key,request_json,status,http_status,
                    run_id,run_status,conclusion,provider_commit FROM owned_workflow_dispatches
                    WHERE request_id=?''',(request_id,)).fetchone()
            db.execute('COMMIT')
        return self._workflow_record(row),claimed
    def save_workflow_dispatch_result(self,result):
        from .owned_platform_host import WorkflowDispatchResult
        if (type(result) is not WorkflowDispatchResult or result.status not in
                ('ACCEPTED','UNKNOWN','REJECTED')):
            raise ValueError('typed workflow dispatch result required')
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('SELECT status FROM owned_workflow_dispatches WHERE request_id=?',
                           (result.request_id,)).fetchone()
            if row is None:
                raise ValueError('workflow dispatch result has no matching in-flight request')
            if row[0] == 'SENDING':
                db.execute('UPDATE owned_workflow_dispatches SET status=?,http_status=? WHERE request_id=?',
                           (result.status,result.http_status,result.request_id))
            elif row[0] in ('RUN_FOUND','RUN_DUPLICATE'):
                # A concurrent readback can prove that the run exists before
                # the POST response arrives. Keep the stronger run evidence.
                db.execute('UPDATE owned_workflow_dispatches SET http_status=? WHERE request_id=?',
                           (result.http_status,result.request_id))
            else:
                raise ValueError('workflow dispatch result has no matching in-flight request')
        return self.workflow_dispatch_record(result.request_id)
    def save_workflow_run_observation(self,observation):
        from .owned_platform_host import WorkflowRunObservation
        if (type(observation) is not WorkflowRunObservation or observation.status not in
                ('FOUND','UNKNOWN','DUPLICATE')):
            raise ValueError('typed workflow run observation required')
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('SELECT status FROM owned_workflow_dispatches WHERE request_id=?',
                           (observation.request_id,)).fetchone()
            if row is None or row[0] in ('REJECTED','PRESENT'):
                raise ValueError('workflow run observation has no reconcilable request')
            # A later paginated or transiently incomplete read must not erase
            # evidence that the same request created multiple workflow runs.
            next_status = ('RUN_DUPLICATE'
                           if row[0] == 'RUN_DUPLICATE' or observation.status == 'DUPLICATE'
                           else 'RUN_FOUND' if observation.status == 'FOUND' else row[0])
            effect = db.execute('''SELECT status FROM owned_effects WHERE key=(
                SELECT effect_key FROM owned_workflow_dispatches WHERE request_id=?)''',
                (observation.request_id,)).fetchone()
            if effect is None:
                raise ValueError('workflow run observation has no durable owned effect')
            if effect[0] == 'RESERVED' and observation.status in ('FOUND','DUPLICATE'):
                db.execute('''UPDATE owned_effects SET status='DISPATCHING' WHERE key=(
                    SELECT effect_key FROM owned_workflow_dispatches WHERE request_id=?)''',
                    (observation.request_id,))
            db.execute('''UPDATE owned_workflow_dispatches SET status=?,run_id=?,run_status=?,
                conclusion=? WHERE request_id=?''',
                (next_status,observation.run_id,observation.run_status,
                 observation.conclusion,observation.request_id))
        return self.workflow_dispatch_record(observation.request_id)
    def reserve(self,packet,context,current,candidate,expected_parent,now,*,revoked=False,
                workflow_request=None,owner_id=None):
        import re
        from .digital_handoff import validate_intent,canonical_bytes,admit_release,MAIN_SOURCE_REF
        validate_intent(packet)
        if type(expected_parent) is not str or not re.fullmatch('[0-9a-f]{40}',expected_parent):
            raise ValueError('immutable target parent required')
        serialized=canonical_bytes(packet).decode();key=packet['effect_key']
        # Pure admission is necessary but not authentication. Actual platform
        # identity/artifact checks remain in phase06_kernel_release.admit.
        admitted=admit_release(packet,context,current,candidate,now,revoked=revoked)
        request_json=None
        request_id=None
        if workflow_request is not None:
            from .owned_platform_host import validate_owned_workflow_request
            if packet['ref']!=MAIN_SOURCE_REF or not admitted['dispatch_deployment']:
                raise PermissionError('workflow request is limited to a new main-source release')
            bound=validate_owned_workflow_request(
                workflow_request,packet=packet,expected_owner_id=owner_id,
                current_parent=expected_parent)
            request_json=bound.to_json()
            request_id=bound.request_id
        elif packet['ref']==MAIN_SOURCE_REF and admitted['dispatch_deployment']:
            raise PermissionError('new main-source effects require a durable workflow request')
        with sqlite3.connect(self.path,timeout=15,isolation_level=None) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT key,packet_json,expected_parent,status,receipt_ref FROM owned_effects WHERE key=?',(key,)).fetchone()
            if row:
                if row[1]!=serialized or row[2]!=expected_parent:
                    raise ValueError('reserved effect binding changed; reconcile only')
                if request_json is not None:
                    workflow=db.execute('SELECT request_json FROM owned_workflow_dispatches WHERE effect_key=?',
                                        (key,)).fetchone()
                    if workflow is None or workflow[0]!=request_json:
                        raise ValueError('reserved workflow request binding changed; reconcile only')
                db.execute('COMMIT');return OwnedEffectRecord(*row)
            status=('RESERVED' if request_json is not None else 'DISPATCHING') \
                if admitted['dispatch_deployment'] else 'ALREADY_PRESENT_UNRECONCILED'
            db.execute('INSERT INTO owned_effects VALUES(?,?,?,?,NULL)',(key,serialized,expected_parent,status))
            if request_json is not None:
                db.execute('''INSERT INTO owned_workflow_dispatches(
                    request_id,effect_key,request_json,status,http_status,run_id,run_status,
                    conclusion,provider_commit) VALUES(?,?,?,'READY',NULL,NULL,NULL,NULL,NULL)''',
                    (request_id,key,request_json))
            db.execute('COMMIT')
        record=self.record(key)
        from dataclasses import replace
        return replace(record,dispatch=admitted['dispatch_deployment'])
    def _present(self,key,receipt_ref):
        # Called only after immutable occurrence validation by reconciler.
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('SELECT status,receipt_ref FROM owned_effects WHERE key=?',(key,)).fetchone()
            if row is None:raise ValueError('missing intent')
            if row[0]=='PRESENT' and row[1]!=receipt_ref:raise ValueError('conflicting occurrence')
            db.execute("UPDATE owned_effects SET status='PRESENT',receipt_ref=? WHERE key=?",(receipt_ref,key))
            dispatch=db.execute('SELECT provider_commit,status FROM owned_workflow_dispatches WHERE effect_key=?',
                                (key,)).fetchone()
            if dispatch:
                if dispatch[0] is not None and dispatch[0]!=receipt_ref:
                    raise ValueError('conflicting workflow provider occurrence')
                db.execute("UPDATE owned_workflow_dispatches SET status='PRESENT',provider_commit=? WHERE effect_key=?",
                           (receipt_ref,key))
