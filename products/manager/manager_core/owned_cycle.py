"""E16 reference cycle; production ownership is intentionally not fabricated.

Only an exact offline local-Git sandbox adapter is implemented here. The real
publisher/collector retain their existing platform boundary. No scheduler is
installed, no remote is pushed, and sandbox evidence never becomes P1/P2.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime,timezone
import fcntl
import json
from pathlib import Path
import sqlite3
import subprocess
from .models.source import _aware
from .digital_handoff import (prepare_owned_change,PublisherContext,REPOSITORY,SOURCE_REF,WORKFLOW,
                              ALLOWED_PATHS,commit_message,admit_release,verify_readback,validate_intent,plan_release)
from .digital_environment import verify_bundle
from .outbox import OwnedEffectJournal
from .reconcile import reconcile_owned,reconcile_pending_owned,OwnedOccurrenceEvidence
from .owned_public_collector import DeliveryObservation


@dataclass(frozen=True)
class CycleConfig:
    owner_id: str
    interval_seconds: int
    def __post_init__(self):
        if type(self.owner_id) is not str or not self.owner_id.strip() or len(self.owner_id)>128:
            raise ValueError('host owner identity required')
        if type(self.interval_seconds) is not int or not 1<=self.interval_seconds<=86400:
            raise ValueError('bounded cadence required')


class CycleStore:
    """Single-host persistent storage; flock is held for the entire effect cycle.

    No lease-expiry takeover is used. This is not a distributed lock and requires
    a filesystem with reliable local flock semantics. Git CAS fences old sends.
    """
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.db=self.root/'cycle.sqlite'
        from .state_recovery import restore_requires_reconciliation
        self._restore_quarantined=restore_requires_reconciliation(self.root)
        if self._restore_quarantined:
            # Do not even run schema initialization against a stale snapshot.
            self.journal=None;self.learning=None
        else:
            with sqlite3.connect(self.db) as db:
                db.execute('CREATE TABLE IF NOT EXISTS schedule(owner TEXT PRIMARY KEY,slot INTEGER NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS control(id INTEGER PRIMARY KEY CHECK(id=1),stopped INTEGER NOT NULL)')
                db.execute('INSERT OR IGNORE INTO control VALUES(1,0)')
            self.journal=OwnedEffectJournal(self.db)
            from .learning import PolicyLearner
            self.learning=PolicyLearner(self.db)
    @contextmanager
    def owner_lock(self):
        with (self.root/'owner.lock').open('a+b') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:yield False;return
            try:yield True
            finally:fcntl.flock(lock,fcntl.LOCK_UN)
    def due(self,config,now):
        if self.restore_requires_reconciliation():raise PermissionError('restored state requires external reconciliation')
        slot=int(now.timestamp())//config.interval_seconds
        with sqlite3.connect(self.db,isolation_level=None) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT slot FROM schedule WHERE owner=?',(config.owner_id,)).fetchone()
            if row and row[0]>=slot:db.execute('COMMIT');return False
            db.execute('INSERT OR REPLACE INTO schedule VALUES(?,?)',(config.owner_id,slot));db.execute('COMMIT')
        return True  # one current slot, never a burst of missed historical effects
    def stopped(self):
        if self.restore_requires_reconciliation():return True
        with sqlite3.connect(self.db) as db:return bool(db.execute('SELECT stopped FROM control WHERE id=1').fetchone()[0])
    def stop(self):
        if self.restore_requires_reconciliation():raise PermissionError('restored state requires external reconciliation')
        with sqlite3.connect(self.db) as db:db.execute('UPDATE control SET stopped=1 WHERE id=1')
    def append(self,event):
        if self.restore_requires_reconciliation():raise PermissionError('restored state requires external reconciliation')
        self.learning.record_sandbox_technical(event)
    def cycle_count(self):
        if self.restore_requires_reconciliation():raise PermissionError('restored state requires external reconciliation')
        return len(self.learning.sandbox_technical_observations())
    def restore_requires_reconciliation(self):
        from .state_recovery import restore_requires_reconciliation
        return self._restore_quarantined or restore_requires_reconciliation(self.root)


class LocalGitCycleSandbox:
    """Explicit sandbox only: actual files/SQLite/local Git, no credentials/remotes.

    Served files are separate from the candidate and commit checkout. This
    simulates deployment independently but is not a live HTTP/provider readback.
    """
    def __init__(self,checkout,served,context,assessment,scope,source_audit):
        self.checkout=Path(checkout).resolve();self.served=Path(served).resolve()
        self.context=context;self.assessment=assessment;self.scope=scope;self.source_audit=source_audit
        self.regress_served=False
        if self.checkout==self.served or self.checkout in self.served.parents or self.served in self.checkout.parents:
            raise ValueError('independent served directory required')
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.checkout),*args],stderr=subprocess.DEVNULL).decode().strip()
    def assert_offline(self):
        if Path(self.git('rev-parse','--show-toplevel')).resolve()!=self.checkout or self.git('remote'):
            raise PermissionError('standalone local sandbox repository without remotes required')
        if self.git('status','--porcelain'):raise PermissionError('sandbox target must be clean')
    def manifest(self):return json.loads((self.checkout/'manager-support/manifest.json').read_text())
    def _bundle(self,commit):
        bodies={n.removeprefix('manager-support/'):subprocess.check_output(
            ['git','-C',str(self.checkout),'show',commit+':'+n]) for n in ALLOWED_PATHS}
        return json.loads(bodies['manifest.json']),bodies
    def _publish_fixture(self,commit,*,regress=False):
        manifest,bodies=self._bundle(commit);self.served.mkdir(parents=True,exist_ok=True)
        for name,body in bodies.items():(self.served/name).write_bytes(body)
        if regress:(self.served/'finance.html').write_bytes(b'fixture served regression')
        # Fixture-only deployment binding. It is never a public provider receipt.
        from .digital_handoff import digest
        (self.served/'.sandbox-deployment.json').write_text(json.dumps(
            dict(commit=commit,candidate_sha256=digest(manifest))))
    def _commit_cas(self,parent,message):
        self.git('add','--',*ALLOWED_PATHS)
        names=set(self.git('diff','--cached','--name-only').splitlines())
        if not names or not names<=set(ALLOWED_PATHS):raise PermissionError('exact scoped changes required')
        tree=self.git('write-tree');commit=self.git('commit-tree',tree,'-p',parent,'-m',message)
        self.git('update-ref','HEAD',commit,parent)
        return commit
    def stage(self,site,now):
        # Same guard and fresh audit as the original platform publisher, but the
        # sandbox never impersonates its real GitHub workflow environment.
        from scripts.phase06_release_guard import stage_release
        from scripts.phase06_kernel_release import fresh_audit
        fresh_audit(self.source_audit,now)
        return stage_release(Path(site),self.checkout,self.source_audit)
    def send(self,packet,parent,now):
        if self.git('rev-parse','HEAD')!=parent:raise PermissionError('target moved')
        verify_bundle(Path(self.context.candidate_bundle),packet['candidate'])
        self.stage(self.context.candidate_bundle,now)
        commit=self._commit_cas(parent,commit_message(packet));self._publish_fixture(commit,regress=self.regress_served)
        return commit
    def occurrence(self,key):
        # Look up the saved effect independently of the current candidate.
        # reconcile_owned validates the full message/source against its packet.
        message='Manager release: effect '+key+' source '
        commit=self.git('log','-1','--format=%H','--fixed-strings','--grep='+message)
        if not commit:return None
        parent=self.git('rev-parse',commit+'^');manifest,bodies=self._bundle(commit);old,oldb=self._bundle(parent)
        receipt={'sha':commit,'html_url':f'https://github.com/{REPOSITORY}/commit/{commit}',
                 'parents':[{'sha':parent}], 'commit':{'committer':{'date':self.git('show','-s','--format=%cI',commit)},
                 'message':self.git('show','-s','--format=%B',commit)},
                 'files':[{'filename':n,'status':'modified'} for n in self.git('diff-tree','--no-commit-id','--name-only','-r',commit).splitlines()]}
        return OwnedOccurrenceEvidence(receipt,manifest,bodies,parent,old,oldb)
    def assessment_source(self):return json.loads((self.context.candidate_bundle/'manifest.json').read_text())['source_commit']
    def readback(self,manifest):
        try:
            raw=(self.served/'manifest.json').read_bytes()
            if json.loads(raw)!=manifest:return False
            verify_readback(manifest,{n:(self.served/n).read_bytes() for n in manifest['files']})
            return True
        except (ValueError,OSError):return False
    def observe_delivery(self,packet,receipt_ref):
        from .digital_handoff import digest
        from .candidate_verification import _Safety
        ref=str(self.served)
        try:
            if self.git('rev-parse','HEAD')!=receipt_ref:
                return DeliveryObservation('UNKNOWN','TARGET_ADVANCED',ref)
            binding=json.loads((self.served/'.sandbox-deployment.json').read_text())
            if binding!=dict(commit=receipt_ref,candidate_sha256=digest(packet['candidate'])):
                return DeliveryObservation('PENDING','DEPLOYMENT_NOT_BOUND',ref)
            if json.loads((self.served/'manifest.json').read_bytes())!=packet['candidate']:
                return DeliveryObservation('PENDING','DIFFERENT_SERVED_VERSION',ref)
            bodies={name:(self.served/name).read_bytes() for name in packet['candidate']['files']}
            try:verify_readback(packet['candidate'],bodies)
            except ValueError:
                # Hash difference alone is UNKNOWN. A bound completed fixture
                # plus failure of the fixed HTML/CSP rubric is a regression.
                for body in bodies.values():
                    safety=_Safety();safety.feed(body.decode('utf-8'))
                    if not safety.safe or not safety.csp:
                        return DeliveryObservation('REGRESSION','BOUND_FIXED_HTML_RUBRIC_FAILURE',ref)
                return DeliveryObservation('UNKNOWN','HASH_MISMATCH_ONLY',ref)
            return DeliveryObservation('VERIFIED','EXACT_SERVED_CANDIDATE',ref)
        except (ValueError,OSError):
            return DeliveryObservation('UNKNOWN','DELIVERY_UNAVAILABLE',ref)
    def rollback(self,packet,now,*,expected_commit):
        # Compare the current immutable candidate before restoring exactly seven
        # old bytes. Any independent target change stops recovery.
        parent=self.git('rev-parse','HEAD')
        if parent!=expected_commit or self.manifest()!=packet['candidate']:
            raise PermissionError('rollback target moved')
        verify_bundle(Path(self.context.baseline_bundle),packet['baseline'])
        self.stage(self.context.baseline_bundle,now)
        commit=self._commit_cas(parent,'Sandbox bounded rollback '+packet['effect_key'])
        self._publish_fixture(commit)
        verify_bundle(self.checkout/'manager-support',packet['baseline'])
        return self.readback(packet['baseline'])


def _cycle_result(status,writes=0,**extra):
    return dict(status=status,writes=writes,deployed=False,proof_level='P0',
                human_outcome='NOT_MEASURED',causal_support=False,**extra)


def _observe_owned_delivery(state_store,host,record,now,*,writes=0,allow_rollback=True):
    packet=json.loads(record.packet_json)
    observation=host.observe_delivery(packet,record.receipt_ref)
    if type(observation) is not DeliveryObservation:
        observation=DeliveryObservation('UNKNOWN','UNTYPED_DELIVERY',str(host.served))
    state_store.journal.save_delivery(record.key,dict(status=observation.status,
        effect_key=record.key,receipt_ref=record.receipt_ref,
        candidate_sha256=packet['candidate_sha256'],observed_at=datetime.now(timezone.utc).isoformat(),
        proof_ref=observation.proof_ref,proof_level='P0',reason=observation.reason))
    base=dict(effect_key=record.key,receipt_ref=record.receipt_ref)
    if observation.status=='VERIFIED':
        return _cycle_result('VERIFIED_SANDBOX_TECHNICAL',writes,**base)
    if observation.status=='REGRESSION' and allow_rollback and not state_store.stopped():
        state_store.stop()
        try:recovered=host.rollback(packet,now,expected_commit=record.receipt_ref)
        except Exception:recovered=False
        return _cycle_result('ROLLED_BACK_SANDBOX_REGRESSION' if recovered else 'ROLLBACK_UNKNOWN',
                             writes,rollback_writes=1 if recovered else None,**base)
    return _cycle_result('UNKNOWN',writes,rollback_writes=0,reason=observation.reason,**base)


def _recover_owned_deliveries(state_store,host,now,*,allow_rollback=True):
    batch=state_store.journal.recovery_batch('delivery');blocking=None
    for record in batch:
        observed=_observe_owned_delivery(state_store,host,record,now,allow_rollback=allow_rollback)
        if observed['status']!='VERIFIED_SANDBOX_TECHNICAL':
            if observed['status'] in ('ROLLED_BACK_SANDBOX_REGRESSION','ROLLBACK_UNKNOWN'):
                blocking=observed;continue
            if state_store.stopped() and observed['status']=='UNKNOWN':continue
            if blocking is None:blocking=observed
    state_store.journal.complete_recovery_batch('delivery',batch)
    if blocking is not None:return blocking
    if not state_store.stopped() and state_store.journal.pending_deliveries(limit=1):
        return _cycle_result('UNKNOWN',rollback_writes=0,reason='UNSCANNED_DELIVERY_BATCH')
    return None


def _dispatch_owned_locked(state_store,host,packet,now):
    """Called only within the owner lock; checkpointable output is data only."""
    validate_intent(packet)
    key=packet['effect_key']
    def result(status,writes=0,**extra):
        return dict(status=status,writes=writes,effect_key=key,**extra)
    record=state_store.journal.record(key)
    if record is not None:
        return result(record.status,receipt_ref=record.receipt_ref)
    # Direct runtime callers must not bypass the current scope/assessment.
    prepared=prepare_owned_change(host.context,host.assessment,host.scope,now)
    if prepared.packet is None:return result('NO_ACTION',reason=prepared.reason)
    # Recompute immutable bindings at the ORIGINAL creation time. Fresh scope
    # checks must not renew its lease or require an identical dispatch clock.
    original=plan_release(prepared.packet['baseline'],prepared.packet['candidate'],
                          datetime.fromisoformat(packet['created_at']))
    if original!=packet:return result('NO_ACTION',reason='PREPARED_PACKET_CHANGED')
    context=PublisherContext(REPOSITORY,SOURCE_REF,WORKFLOW,packet['candidate']['source_commit'],'1')
    current=host.manifest();verify_bundle(host.checkout/'manager-support',current)
    try:
        admit_release(packet,context,current,packet['candidate'],now)
        record=state_store.journal.reserve(packet,context,current,packet['candidate'],host.git('rev-parse','HEAD'),now)
    except PermissionError:return result('NO_ACTION',reason='TARGET_MOVED_OR_NOT_ADMITTED')
    if not record.dispatch:return result(record.status,receipt_ref=record.receipt_ref)
    try:host.send(packet,record.expected_parent,now)
    except Exception:return result('UNKNOWN',None)
    return result('SUBMITTED',1)


def dispatch_owned_once(state_store,host,packet,now):
    """Fresh journal lookup, admission, reserve and send in one locked step.

    Never checkpoint a reserve's temporary dispatch flag separately from send.
    This public entry also preserves pending recovery, stop and scope gates.
    """
    _aware(now)
    if state_store.restore_requires_reconciliation():
        return dict(status='RESTORE_RECONCILIATION_REQUIRED',writes=0)
    if type(host) is not LocalGitCycleSandbox:
        return dict(status='DEPLOYMENT_HOST_REQUIRED',writes=0)
    with state_store.owner_lock() as acquired:
        if not acquired:return dict(status='OWNER_BUSY',writes=0)
        host.assert_offline()
        reconcile_pending_owned(state_store.journal,host.occurrence,datetime.now(timezone.utc))
        pending=bool(state_store.journal.pending_records(limit=1))
        delivery=_recover_owned_deliveries(state_store,host,now,allow_rollback=not pending)
        if pending:return dict(status='UNKNOWN',writes=0)
        if delivery is not None:return delivery
        if state_store.stopped():return dict(status='STOPPED_REGRESSION',writes=0)
        return _dispatch_owned_locked(state_store,host,packet,now)


def run_owned_cycle(config,state_store,*,host=None,now=None):
    now=now or datetime.now(timezone.utc);_aware(now)
    result=_cycle_result
    if state_store.restore_requires_reconciliation():
        return result('RESTORE_RECONCILIATION_REQUIRED')
    # There is no production host adapter until the real owner, persistent
    # volume and promotion path have been observed. A caller flag cannot mint it.
    if type(host) is not LocalGitCycleSandbox:return result('DEPLOYMENT_HOST_REQUIRED')
    with state_store.owner_lock() as acquired:
        if not acquired:return result('OWNER_BUSY')
        host.assert_offline()
        reconcile_pending_owned(state_store.journal,host.occurrence,datetime.now(timezone.utc))
        pending=bool(state_store.journal.pending_records(limit=1))
        delivery=_recover_owned_deliveries(state_store,host,now,allow_rollback=not pending)
        if pending:
            r=result('UNKNOWN',0,reason='PRIOR_OCCURRENCE_UNRESOLVED')
            state_store.append(r);return r
        if delivery is not None:state_store.append(delivery);return delivery
        if state_store.stopped():return result('STOPPED_REGRESSION')
        if not state_store.due(config,now):return result('NOT_DUE')
        prepared=prepare_owned_change(host.context,host.assessment,host.scope,now)
        if prepared.packet is None:
            r=result('NO_ACTION',reason=prepared.reason);state_store.append(r);return r
        packet=prepared.packet;key=packet['effect_key']
        dispatched=_dispatch_owned_locked(state_store,host,packet,now);writes=dispatched['writes']
        if dispatched['status'] in ('UNKNOWN','NO_ACTION'):
            r=result(dispatched['status'],writes,reason=dispatched.get('reason'))
            state_store.append(r);return r
        record=state_store.journal.record(key);packet=json.loads(record.packet_json)
        # Git fixture commit timestamps come from the actual Git clock, distinct
        # from the scheduling fixture clock. This is not a production timestamp.
        reconciled=reconcile_owned(state_store.journal,key,host.occurrence,datetime.now(timezone.utc))
        if reconciled.status!='PRESENT':r=result('UNKNOWN',writes)
        else:r=_observe_owned_delivery(state_store,host,state_store.journal.record(key),now,writes=writes)
        # Native endpoint only; no invented welfare score or scalar promotion.
        state_store.append(r);return r
