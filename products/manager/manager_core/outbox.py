"""K008: sqlite write-ahead effect reservation; NEVER retry an uncertain send.

The only supported adapter class is an explicitly offline fixture. One signed
grant may authorize multiple intent IDs, but a single SQLite transaction guards
the total reserved budget across them. Crash between DISPATCHING and send remains
uncertain and requires reconciliation, not retry.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from .authority import Grant, AuthorityVerifier


ROLLBACK_LEASE = timedelta(minutes=15)
ROLLBACK_SCHEMA = 'manager.digital-rollback.v1'


def _rollback_identity(original_packet, candidate_commit, parent_commit, controller_sha):
    from .digital_handoff import ALLOWED_PATHS, digest, validate_intent
    validate_intent(original_packet)
    if original_packet['schema'] != 'manager.digital-handoff.v2':
        raise ValueError('main-bound saved candidate required for rollback')
    if any(type(value) is not str or len(value) != 40 or
           any(char not in '0123456789abcdef' for char in value)
           for value in (candidate_commit, parent_commit, controller_sha)):
        raise ValueError('immutable candidate, parent and controller commits required')
    baseline = original_packet['baseline']
    candidate = original_packet['candidate']
    return {
        'schema': ROLLBACK_SCHEMA,
        'candidate_effect_key': original_packet['effect_key'],
        'candidate_commit': candidate_commit,
        'parent_commit': parent_commit,
        'controller_sha': controller_sha,
        'baseline': baseline,
        'baseline_sha256': original_packet['baseline_sha256'],
        'candidate': candidate,
        'candidate_sha256': original_packet['candidate_sha256'],
        'allowed_paths': list(ALLOWED_PATHS),
        'restored_source_sha': baseline['source_commit'],
        'max_changed_files': len(ALLOWED_PATHS),
        'money_budget': 0,
        'external_authority': 'TRUSTED_MAIN_OWNER_CONTROL',
        'effect_key': digest({
            'schema': ROLLBACK_SCHEMA,
            'candidate_effect_key': original_packet['effect_key'],
            'candidate_commit': candidate_commit,
            'parent_commit': parent_commit,
            'controller_sha': controller_sha,
            'baseline_sha256': original_packet['baseline_sha256'],
            'candidate_sha256': original_packet['candidate_sha256'],
            'allowed_paths': list(ALLOWED_PATHS),
        }),
    }


def plan_owned_rollback(original_packet, candidate_commit, parent_commit, created_at,
                        *, controller_sha):
    """Build a versioned restore intent for one exact saved main release."""
    from .models.source import _aware
    from .digital_handoff import canonical_bytes
    _aware(created_at)
    packet = _rollback_identity(original_packet, candidate_commit, parent_commit, controller_sha)
    packet.update(created_at=created_at.isoformat(),
                  expires_at=(created_at + ROLLBACK_LEASE).isoformat())
    packet['packet_sha256'] = hashlib.sha256(canonical_bytes(packet)).hexdigest()
    return packet


def validate_owned_rollback(packet):
    """Validate a durable rollback intent without treating it as send authority."""
    from .digital_handoff import canonical_bytes, _manifest, digest
    from .models.source import _aware
    if type(packet) is not dict:
        raise ValueError('typed rollback intent required')
    try:
        from .digital_handoff import ALLOWED_PATHS
        baseline = _manifest(packet['baseline'])
        candidate = _manifest(packet['candidate'])
        created = datetime.fromisoformat(packet['created_at'])
        expires = datetime.fromisoformat(packet['expires_at'])
        _aware(created); _aware(expires)
        required = {
            'schema', 'candidate_effect_key', 'candidate_commit', 'parent_commit', 'controller_sha',
            'baseline', 'baseline_sha256', 'candidate', 'candidate_sha256',
            'allowed_paths', 'restored_source_sha', 'max_changed_files',
            'money_budget', 'external_authority', 'effect_key', 'created_at',
            'expires_at', 'packet_sha256',
        }
        if set(packet) != required:
            raise ValueError('unknown rollback fields')
        hex40=lambda value: type(value) is str and len(value)==40 and all(
            char in '0123456789abcdef' for char in value)
        hex64=lambda value: type(value) is str and len(value)==64 and all(
            char in '0123456789abcdef' for char in value)
        if (not hex40(packet['candidate_commit']) or not hex40(packet['parent_commit']) or
                not hex40(packet['controller_sha']) or
                not hex64(packet['candidate_effect_key'])):
            raise ValueError('invalid immutable rollback SHA binding')
        # Reconstruct the original release identity from immutable packet fields.
        identity = {
            'schema': ROLLBACK_SCHEMA,
            'candidate_effect_key': packet['candidate_effect_key'],
            'candidate_commit': packet['candidate_commit'],
            'parent_commit': packet['parent_commit'],
            'controller_sha': packet['controller_sha'],
            'baseline_sha256': packet['baseline_sha256'],
            'candidate_sha256': packet['candidate_sha256'],
            'allowed_paths': list(ALLOWED_PATHS),
        }
        if (packet['schema'] != ROLLBACK_SCHEMA or
                packet['allowed_paths'] != list(ALLOWED_PATHS) or
                packet['max_changed_files'] != len(ALLOWED_PATHS) or
                type(packet['max_changed_files']) is not int or
                packet['money_budget'] != 0 or type(packet['money_budget']) is not int or
                packet['external_authority'] != 'TRUSTED_MAIN_OWNER_CONTROL' or
                packet['restored_source_sha'] != baseline['source_commit'] or
                packet['baseline_sha256'] != digest(baseline) or
                packet['candidate_sha256'] != digest(candidate) or
                expires - created != ROLLBACK_LEASE or not created < expires or
                packet['effect_key'] != digest(identity)):
            raise ValueError('rollback intent binding changed')
        unsigned = dict(packet); unsigned.pop('packet_sha256')
        if packet['packet_sha256'] != hashlib.sha256(canonical_bytes(unsigned)).hexdigest():
            raise ValueError('rollback packet digest changed')
    except (KeyError, TypeError, ValueError):
        raise ValueError('invalid owned rollback intent') from None
    return created


def owned_rollback_commit_message(packet):
    validate_owned_rollback(packet)
    return ('Manager bounded rollback: effect '+packet['effect_key']+
            ' candidate '+packet['candidate_commit']+
            ' release '+packet['candidate_effect_key'])


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
class OwnedRollbackRecord:
    key: str
    packet_json: str
    status: str
    receipt_ref: str | None
    delivery_status: str = 'UNKNOWN'
    delivery_json: str | None = None
    dispatch: bool = False


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
            db.execute('''CREATE TABLE IF NOT EXISTS owned_rollbacks(
                key TEXT PRIMARY KEY,packet_json TEXT NOT NULL,
                status TEXT NOT NULL,receipt_ref TEXT,
                delivery_status TEXT NOT NULL DEFAULT 'UNKNOWN',delivery_json TEXT)''')
            rollback_columns={row[1] for row in db.execute('PRAGMA table_info(owned_rollbacks)')}
            if 'delivery_status' not in rollback_columns:
                db.execute("ALTER TABLE owned_rollbacks ADD COLUMN delivery_status TEXT NOT NULL DEFAULT 'UNKNOWN'")
            if 'delivery_json' not in rollback_columns:
                db.execute('ALTER TABLE owned_rollbacks ADD COLUMN delivery_json TEXT')
            db.execute('CREATE INDEX IF NOT EXISTS idx_owned_effect_receipt ON owned_effects(receipt_ref,status)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_owned_rollback_receipt ON owned_rollbacks(receipt_ref,status)')
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
                AND e.key>? ORDER BY e.key''',(after_key or '',)).fetchall()
            rollback_rows=db.execute('''SELECT key,packet_json,receipt_ref,delivery_status,delivery_json
                FROM owned_rollbacks WHERE status='PRESENT' AND delivery_status='VERIFIED' ''').fetchall()
        # A candidate regression is closed only by the exact saved rollback
        # receipt plus P2 deployed-baseline proof. A hash mismatch, pending
        # deployment, or older/sibling rollback never suppresses recovery.
        compensated=set()
        for key,packet_json,receipt_ref,status,delivery_json in rollback_rows:
            try:
                packet=json.loads(packet_json);evidence=json.loads(delivery_json)
                validate_owned_rollback(packet)
                if (evidence.get('effect_key')==key and evidence.get('receipt_ref')==receipt_ref and
                        evidence.get('baseline_sha256')==packet['baseline_sha256'] and
                        evidence.get('status')=='VERIFIED' and evidence.get('proof_level')=='P2' and
                        evidence.get('human_outcome')=='NOT_MEASURED'):
                    compensated.add(packet['candidate_effect_key'])
            except (TypeError,ValueError,KeyError,json.JSONDecodeError):
                continue
        unresolved=(row for row in rows if row[0] not in compensated)
        return tuple(OwnedEffectRecord(*row) for _,row in zip(range(limit),unresolved))
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
    def reserve(self,packet,context,current,candidate,expected_parent,now,*,revoked=False):
        import re
        from .digital_handoff import validate_intent,canonical_bytes,admit_release
        validate_intent(packet)
        if type(expected_parent) is not str or not re.fullmatch('[0-9a-f]{40}',expected_parent):
            raise ValueError('immutable target parent required')
        serialized=canonical_bytes(packet).decode();key=packet['effect_key']
        # Pure admission is necessary but not authentication. Actual platform
        # identity/artifact checks remain in phase06_kernel_release.admit.
        admitted=admit_release(packet,context,current,candidate,now,revoked=revoked)
        with sqlite3.connect(self.path,timeout=15,isolation_level=None) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT key,packet_json,expected_parent,status,receipt_ref FROM owned_effects WHERE key=?',(key,)).fetchone()
            if row:
                if row[1]!=serialized or row[2]!=expected_parent:
                    raise ValueError('reserved effect binding changed; reconcile only')
                db.execute('COMMIT');return OwnedEffectRecord(*row)
            status='DISPATCHING' if admitted['dispatch_deployment'] else 'ALREADY_PRESENT_UNRECONCILED'
            db.execute('INSERT INTO owned_effects VALUES(?,?,?,?,NULL)',(key,serialized,expected_parent,status))
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

    def latest_present_record(self):
        """Return the newest saved row only if its occurrence is proven present."""
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('''SELECT key,packet_json,expected_parent,status,receipt_ref
                FROM owned_effects ORDER BY rowid DESC LIMIT 1''').fetchone()
        return OwnedEffectRecord(*row) if row and row[3]=='PRESENT' else None

    def has_owned_history(self):
        with sqlite3.connect(self.path,timeout=15) as db:
            return (db.execute('SELECT 1 FROM owned_effects LIMIT 1').fetchone() is not None or
                    db.execute('SELECT 1 FROM owned_rollbacks LIMIT 1').fetchone() is not None)

    def record_for_receipt(self,receipt_ref):
        """Resolve one current Pages SHA to its unique saved candidate receipt."""
        import re
        if type(receipt_ref) is not str or not re.fullmatch('[0-9a-f]{40}',receipt_ref):
            return None
        with sqlite3.connect(self.path,timeout=15) as db:
            rows=db.execute('''SELECT key,packet_json,expected_parent,status,receipt_ref
                FROM owned_effects WHERE receipt_ref=? AND status='PRESENT' LIMIT 2''',
                (receipt_ref,)).fetchall()
        if len(rows)!=1:return None
        from .digital_handoff import validate_intent
        row=rows[0];packet=json.loads(row[1]);validate_intent(packet)
        return OwnedEffectRecord(*row) if packet.get('schema') in (
            'manager.digital-handoff.v1','manager.digital-handoff.v2') else None

    def rollback_for_receipt(self,receipt_ref):
        """Resolve one current Pages SHA to its unique saved rollback receipt."""
        import re
        if type(receipt_ref) is not str or not re.fullmatch('[0-9a-f]{40}',receipt_ref):
            return None
        with sqlite3.connect(self.path,timeout=15) as db:
            rows=db.execute('''SELECT key,packet_json,status,receipt_ref,delivery_status,delivery_json
                FROM owned_rollbacks WHERE receipt_ref=? AND status='PRESENT' LIMIT 2''',
                (receipt_ref,)).fetchall()
        if len(rows)!=1:return None
        validate_owned_rollback(json.loads(rows[0][1]))
        return OwnedRollbackRecord(*rows[0])

    def rollback_record(self,key):
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('''SELECT key,packet_json,status,receipt_ref,delivery_status,delivery_json
                              FROM owned_rollbacks WHERE key=?''',
                           (key,)).fetchone()
        return OwnedRollbackRecord(*row) if row else None

    def latest_rollback_record(self):
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('''SELECT key,packet_json,status,receipt_ref,delivery_status,delivery_json
                FROM owned_rollbacks ORDER BY rowid DESC LIMIT 1''').fetchone()
        return OwnedRollbackRecord(*row) if row else None

    def pending_rollbacks(self,limit=100):
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('rollback batch limit must be 1..100')
        with sqlite3.connect(self.path,timeout=15) as db:
            rows=db.execute('''SELECT key,packet_json,status,receipt_ref,delivery_status,delivery_json
                FROM owned_rollbacks WHERE status!='PRESENT' OR delivery_status!='VERIFIED'
                ORDER BY rowid LIMIT ?''',(limit,)).fetchall()
        return tuple(OwnedRollbackRecord(*row) for row in rows)

    def reserve_rollback(self,packet,now):
        """Persist a rollback before checkpoint ACK; replay never regains dispatch."""
        from .digital_handoff import canonical_bytes
        created=validate_owned_rollback(packet)
        from .models.source import _aware
        _aware(now)
        if not created<=now<datetime.fromisoformat(packet['expires_at']):
            raise PermissionError('bounded rollback lease expired')
        original=self.record(packet['candidate_effect_key'])
        original_packet=(json.loads(original.packet_json) if original else None)
        if (original is None or original.status!='PRESENT' or
                original.receipt_ref!=packet['candidate_commit'] or
                original.expected_parent!=packet['parent_commit'] or
                original_packet['baseline']!=packet['baseline'] or
                original_packet['candidate']!=packet['candidate'] or
                original_packet['baseline_sha256']!=packet['baseline_sha256'] or
                original_packet['candidate_sha256']!=packet['candidate_sha256']):
            raise PermissionError('exact saved candidate receipt required for rollback')
        serialized=canonical_bytes(packet).decode();key=packet['effect_key']
        with sqlite3.connect(self.path,timeout=15,isolation_level=None) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT key,packet_json,status,receipt_ref,delivery_status,delivery_json
                FROM owned_rollbacks WHERE key=?''',
                           (key,)).fetchone()
            if row:
                if row[1]!=serialized:
                    raise ValueError('rollback effect binding changed; reconcile only')
                db.execute('COMMIT')
                return OwnedRollbackRecord(*row)
            db.execute('INSERT INTO owned_rollbacks(key,packet_json,status,receipt_ref,delivery_status,delivery_json) VALUES(?,?,?,NULL,\'UNKNOWN\',NULL)',
                       (key,serialized,'DISPATCHING'))
            db.execute('COMMIT')
        from dataclasses import replace
        return replace(self.rollback_record(key),dispatch=True)

    def _rollback_present(self,key,receipt_ref):
        import re
        if type(receipt_ref) is not str or not re.fullmatch('[0-9a-f]{40}',receipt_ref):
            raise ValueError('official rollback commit SHA required')
        with sqlite3.connect(self.path,timeout=15) as db:
            row=db.execute('SELECT status,receipt_ref FROM owned_rollbacks WHERE key=?',
                           (key,)).fetchone()
            if row is None:raise ValueError('missing rollback intent')
            if row[0] not in ('DISPATCHING','PRESENT'):
                raise ValueError('invalid rollback occurrence state')
            if row[0]=='PRESENT' and row[1]!=receipt_ref:
                raise ValueError('conflicting rollback occurrence')
            db.execute("UPDATE owned_rollbacks SET status='PRESENT',receipt_ref=? WHERE key=?",
                       (receipt_ref,key))

    def rollback_delivery_record(self,key):
        row=self.rollback_record(key)
        if row is None or row.delivery_json is None:return None
        import json
        return json.loads(row.delivery_json)

    def save_rollback_delivery(self,key,evidence):
        import json
        from .models.source import _aware
        row=self.rollback_record(key)
        if row is None or row.status!='PRESENT' or type(evidence) is not dict:
            raise ValueError('present saved rollback required')
        packet=json.loads(row.packet_json)
        if (evidence.get('effect_key')!=key or evidence.get('receipt_ref')!=row.receipt_ref or
                evidence.get('baseline_sha256')!=packet['baseline_sha256'] or
                evidence.get('status') not in ('VERIFIED','PENDING','UNKNOWN')):
            raise ValueError('rollback delivery must bind exact saved receipt')
        if (evidence.get('human_outcome')!='NOT_MEASURED' or
                (evidence['status']=='VERIFIED' and evidence.get('proof_level')!='P2') or
                (evidence['status']!='VERIFIED' and evidence.get('proof_level') not in ('P0','P2'))):
            raise ValueError('rollback delivery proof level or outcome changed')
        _aware(datetime.fromisoformat(evidence['observed_at']))
        serialized=json.dumps(evidence,sort_keys=True,allow_nan=False)
        with sqlite3.connect(self.path,timeout=15) as db:
            db.execute('''UPDATE owned_rollbacks SET delivery_status=?,delivery_json=? WHERE key=?
                AND delivery_status!='VERIFIED' ''',(evidence['status'],serialized,key))
