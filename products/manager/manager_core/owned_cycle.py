"""E16 local reference cycle and bounded Railway-to-GitHub owner bridge.

`run_owned_cycle` remains limited to the no-remote local-Git sandbox. The
Railway bridge has a separate fixed-main request contract and delegates every
publication to the protected GitHub workflow; it does not push Git itself.
Neither path turns technical publication evidence into human-outcome evidence.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime,timezone
import fcntl
import json
import os
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


def run_owned_workflow_bridge_once(state_root,*,env=None,now=None,get=None,post=None,
                                   public_get=None,mount_check=os.path.ismount):
    """Run one bounded Railway cycle for the fixed main-source service bundle.

    It reconciles earlier effects first, builds a candidate only from this
    immutable main deployment, binds it to the exact current Pages parent, and
    reserves one request before dispatch. Publication is still owned by the
    protected GitHub workflow; this function never commits to Pages itself.
    """
    from tempfile import TemporaryDirectory
    from .digital_environment import build_site
    from .digital_handoff import (
        MAIN_SOURCE_REF, PublisherContext, REPOSITORY, WORKFLOW, plan_release,
    )
    from .owned_platform_host import (
        RuntimeConfigurationError, create_owned_workflow_request,
        read_github_ref_commit, read_railway_runtime_identity,
        reconcile_reserved_owned_workflow,
    )
    env=os.environ if env is None else env
    now=now or datetime.now(timezone.utc);_aware(now)
    try:
        identity=read_railway_runtime_identity(
            env,
            expected_project_id=env.get('MANAGER_EXPECTED_RAILWAY_PROJECT_ID'),
            expected_environment_id=env.get('MANAGER_EXPECTED_RAILWAY_ENVIRONMENT_ID'),
            expected_service_id=env.get('MANAGER_EXPECTED_RAILWAY_SERVICE_ID'),
            expected_volume_name=env.get('MANAGER_EXPECTED_RAILWAY_VOLUME_NAME'),
            source_root=Path(__file__).resolve().parents[1],
            state_root=state_root,
            mount_check=mount_check,
        )
    except (RuntimeConfigurationError, OSError, TypeError, ValueError):
        return _cycle_result('DEPLOYMENT_HOST_REQUIRED',reason='RAILWAY_OWNER_PREFLIGHT_FAILED')

    try:
        store=CycleStore(state_root)
    except (OSError, sqlite3.Error, ValueError):
        return _cycle_result('DEPLOYMENT_HOST_REQUIRED',reason='PERSISTENT_OWNER_STATE_UNAVAILABLE')
    if store.restore_requires_reconciliation():
        return _cycle_result('RESTORE_RECONCILIATION_REQUIRED')

    from scripts.phase06_kernel_release import (
        immutable_snapshot, live_snapshot, public_get as default_public_get,
    )
    from .owned_public_collector import collect_owned_delivery, collect_owned_occurrence
    from .reconcile import reconcile_owned, reconcile_pending_owned
    public_reader=public_get or default_public_get

    with store.owner_lock() as acquired:
        if not acquired:return _cycle_result('OWNER_BUSY')
        requests=store.journal.pending_workflow_dispatches(limit=2)
        if len(requests)>1:
            return _cycle_result('RECONCILIATION_REQUIRED',
                                 reason='MULTIPLE_PENDING_WORKFLOW_REQUESTS')

        def read_occurrence(key):
            return collect_owned_occurrence(key,store.journal,now,get=public_reader)

        if requests:
            request_record=requests[0]
            prior_deliveries=store.journal.pending_deliveries(limit=100)
            for prior_delivery in prior_deliveries:
                if prior_delivery.key==request_record.effect_key:
                    continue
                evidence=collect_owned_delivery(
                    prior_delivery.key,store.journal,now,get=public_reader)
                store.journal.save_delivery(prior_delivery.key,evidence)
                if evidence['status']!='VERIFIED':
                    return _cycle_result('DELIVERY_RECONCILIATION_REQUIRED',
                                         effect_key=prior_delivery.key,
                                         delivery_status=evidence['status'],
                                         reason='PRIOR_DELIVERY_NOT_VERIFIED')
            if (len(prior_deliveries)==100 and
                    store.journal.pending_deliveries(
                        limit=1,after_key=prior_deliveries[-1].key)):
                return _cycle_result('DELIVERY_RECONCILIATION_REQUIRED',
                                     reason='MORE_PRIOR_DELIVERIES_REMAIN')
            # An older intent without a workflow request may still represent an
            # external effect. Reconcile it before touching the newer request;
            # a missing public occurrence is UNKNOWN, never permission to pass it.
            prior_page=store.journal.pending_records(limit=100)
            prior_records=tuple(record for record in prior_page
                                if record.key!=request_record.effect_key)
            for prior in prior_records:
                occurrence=reconcile_owned(store.journal,prior.key,read_occurrence,now)
                if occurrence.status!='PRESENT':
                    return _cycle_result('RECONCILIATION_REQUIRED',
                                         effect_key=prior.key,
                                         reason='UNRESOLVED_PRIOR_OWNER_EFFECT')
                effect=store.journal.record(prior.key)
                evidence=collect_owned_delivery(
                    effect.key,store.journal,now,get=public_reader)
                store.journal.save_delivery(effect.key,evidence)
                if evidence['status']!='VERIFIED':
                    return _cycle_result('RECONCILIATION_REQUIRED',
                                         effect_key=effect.key,
                                         delivery_status=evidence['status'],
                                         reason='PRIOR_DELIVERY_NOT_VERIFIED')
            if (len(prior_page)==100 and
                    store.journal.pending_records(limit=1,after_key=prior_page[-1].key)):
                return _cycle_result('RECONCILIATION_REQUIRED',
                                     reason='MORE_PRIOR_OWNER_EFFECTS_REMAIN')
            if store.stopped() and request_record.status=='READY':
                return _cycle_result('STOPPED',request_id=request_record.request_id)
            if request_record.status!='READY':
                reconcile_owned(store.journal,request_record.effect_key,read_occurrence,now)
                effect=store.journal.record(request_record.effect_key)
                if effect is not None and effect.status=='PRESENT':
                    evidence=collect_owned_delivery(
                        effect.key,store.journal,now,get=public_reader)
                    store.journal.save_delivery(effect.key,evidence)
                    if evidence['status']=='VERIFIED':
                        return _cycle_result(
                            'VERIFIED_PUBLIC_ARTIFACT_ONLY',
                            effect_key=effect.key,receipt_ref=effect.receipt_ref,
                            delivery_status=evidence['status'],published=True,
                            proof_level=evidence['proof_level'])
                    return _cycle_result(
                        'DELIVERY_'+evidence['status'],effect_key=effect.key,
                        receipt_ref=effect.receipt_ref,delivery_status=evidence['status'],
                        reason=evidence['reason'],published=False)
            bridge=reconcile_reserved_owned_workflow(
                store.journal,request_record.request_id,
                token=env['MANAGER_WORKFLOW_DISPATCH_TOKEN'],get=get,post=post)
            return _cycle_result(
                bridge.status,
                request_id=bridge.request_id,
                sent=bridge.sent,
                workflow_run_id=bridge.run_id,
                workflow_run_status=bridge.run_status,
                dispatch_http_status=bridge.http_status,
                published=False,
            )

        pending=store.journal.pending_records(limit=100)
        if pending:
            reconcile_pending_owned(store.journal,read_occurrence,now)
            if store.journal.pending_records(limit=1):
                return _cycle_result('RECONCILIATION_REQUIRED',
                                     reason='UNRESOLVED_PRIOR_OWNER_EFFECT')

        delivery_batch=store.journal.recovery_batch('delivery')
        for record in delivery_batch:
            evidence=collect_owned_delivery(record.key,store.journal,now,get=public_reader)
            store.journal.save_delivery(record.key,evidence)
        store.journal.complete_recovery_batch('delivery',delivery_batch)
        if store.journal.pending_deliveries(limit=1):
            return _cycle_result('DELIVERY_RECONCILIATION_REQUIRED')
        if store.stopped():return _cycle_result('STOPPED')

        token=env['MANAGER_WORKFLOW_DISPATCH_TOKEN']
        main_head=read_github_ref_commit('main',token=token,get=get)
        if main_head.status!='FOUND':
            return _cycle_result('UNKNOWN',reason='MAIN_HEAD_UNAVAILABLE')
        if main_head.commit_sha!=identity.source_commit:
            return _cycle_result('SOURCE_NOT_CURRENT',reason='WORKER_SHA_DIFFERS_FROM_MAIN')
        config=CycleConfig(identity.owner_id,identity.interval_seconds)
        if not store.due(config,now):return _cycle_result('NOT_DUE')

        pages_head=read_github_ref_commit('gh-pages',token=token,get=get)
        if pages_head.status!='FOUND':
            return _cycle_result('UNKNOWN',reason='PAGES_HEAD_UNAVAILABLE')
        try:
            baseline,live_bodies=live_snapshot(get=public_reader)
            committed,parent_bodies=immutable_snapshot(pages_head.commit_sha,get=public_reader)
        except (OSError,ValueError,TypeError,KeyError) as exc:
            return _cycle_result('UNKNOWN',reason='PUBLIC_BASELINE_UNAVAILABLE',
                                 error_type=type(exc).__name__)
        if baseline!=committed:
            return _cycle_result('UNKNOWN',reason='PAGES_BRANCH_MANIFEST_NOT_SERVED_YET')
        branch_pages={name:parent_bodies[name] for name in baseline['files']}
        if live_bodies!=branch_pages:
            different=sorted(name for name in set(live_bodies)|set(branch_pages)
                             if live_bodies.get(name)!=branch_pages.get(name))
            return _cycle_result('UNKNOWN',reason='PAGES_BRANCH_BYTES_NOT_SERVED_YET',
                                 different_paths=different)

        catalog_path=Path(__file__).resolve().parents[1]/'public_goods/service/catalog.json'
        catalog=json.loads(catalog_path.read_text())
        try:
            with TemporaryDirectory(prefix='manager-owned-candidate-') as tmp:
                candidate=build_site(catalog,Path(tmp)/'site',identity.source_commit)
                packet=plan_release(baseline,candidate,now,source_ref=MAIN_SOURCE_REF)
        except (OSError,ValueError,TypeError,KeyError):
            return _cycle_result('NO_ACTION',reason='CANDIDATE_BUILD_OR_VALIDATION_FAILED')
        if packet['decision']=='NO_ACTION':
            return _cycle_result('NO_ACTION',reason='CANDIDATE_ALREADY_CURRENT')

        request=create_owned_workflow_request(
            packet,identity.owner_id,pages_head.commit_sha)
        # run_id is syntactic context for pure admission only. GitHub Actions
        # supplies and authenticates the actual workflow context at the receiver.
        context=PublisherContext(REPOSITORY,MAIN_SOURCE_REF,WORKFLOW,
                                identity.source_commit,'1')
        try:
            reserved=store.journal.reserve(
                packet,context,baseline,candidate,pages_head.commit_sha,now,
                workflow_request=request,owner_id=identity.owner_id)
        except (PermissionError,ValueError):
            return _cycle_result('RECONCILIATION_REQUIRED',reason='REQUEST_RESERVATION_REJECTED')
        if not reserved.dispatch:
            return _cycle_result(reserved.status,effect_key=reserved.key,
                                 reason='REQUEST_ALREADY_RESERVED')
        bridge=reconcile_reserved_owned_workflow(
            store.journal,request.request_id,token=token,get=get,post=post)
        return _cycle_result(
            bridge.status,request_id=bridge.request_id,sent=bridge.sent,
            workflow_run_id=bridge.run_id,workflow_run_status=bridge.run_status,
            dispatch_http_status=bridge.http_status,published=False,
        )


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
