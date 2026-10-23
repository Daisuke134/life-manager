"""Durable platform STOP and one-shot bounded rollback control contracts.

These are P0 SQLite and injected-gateway fixtures. They do not authenticate
GitHub, perform a provider write, or prove a live Pages rollback.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from test_candidate_verification import NOW
from test_owned_platform_host import github_environment, platform_fixture
from manager_core.digital_handoff import (ALLOWED_PATHS, MAIN_REF, REPOSITORY, WORKFLOW,
    SOURCE_REF, PublisherContext, commit_message, plan_release)
from manager_core.owned_checkpoint import PrivateCheckpoint
from manager_core.owned_cycle import CycleConfig, CycleStore, run_owned_cycle
from test_digital_handoff import manifest
from test_owned_checkpoint import MemoryGateway


class OwnedPlatformRollbackTests(unittest.TestCase):
    @staticmethod
    def _save_original_receipt(store, packet, candidate_sha, parent_sha):
        publisher=PublisherContext(REPOSITORY,MAIN_REF,WORKFLOW,
            packet['candidate']['source_commit'],'123',
            workflow_commit=packet['candidate']['source_commit'])
        store.journal.reserve(packet,publisher,packet['baseline'],packet['candidate'],
                              parent_sha,NOW)
        store.journal._present(packet['effect_key'],candidate_sha)

    @staticmethod
    def _copy_saved_v1_receipt(store, packet, source_journal):
        source=source_journal.record(packet['effect_key'])
        publisher=PublisherContext(REPOSITORY,SOURCE_REF,WORKFLOW,
            packet['candidate']['source_commit'],'12345')
        store.journal.reserve(packet,publisher,packet['baseline'],packet['candidate'],
                              source.expected_parent,NOW)
        store.journal._present(packet['effect_key'],source.receipt_ref)
        store.journal.save_delivery(packet['effect_key'],
                                    source_journal.delivery_record(packet['effect_key']))

    def _install_candidate_commit(self, host, store, *, stop=True):
        from manager_core.reconcile import OwnedOccurrenceEvidence

        packet=plan_release(
            json.loads((host.context.baseline_bundle/'manifest.json').read_text()),
            json.loads((host.context.candidate_bundle/'manifest.json').read_text()),
            NOW,schema='manager.digital-handoff.v2')
        parent=host._git('rev-parse','HEAD')
        for name in ALLOWED_PATHS:
            relative=name.removeprefix('manager-support/')
            (host.checkout/name).write_bytes((host.context.candidate_bundle/relative).read_bytes())
        host._git('add','--',*ALLOWED_PATHS)
        tree=host._git('write-tree')
        commit=host._git('commit-tree',tree,'-p',parent,'-m',commit_message(packet))
        host._git('update-ref','refs/heads/gh-pages',commit,parent)
        publisher=PublisherContext(REPOSITORY,MAIN_REF,WORKFLOW,
            packet['candidate']['source_commit'],'123',
            workflow_commit=packet['candidate']['source_commit'])
        store.journal.reserve(packet,publisher,packet['baseline'],packet['candidate'],parent,NOW)
        store.journal._present(packet['effect_key'],commit)
        if stop:store.stop()

        def bundle(ref):
            raw={name:host._run_cli_bytes(['git','-C',str(host.checkout),'show',f'{ref}:{name}'])
                 for name in ALLOWED_PATHS}
            return json.loads(raw['manager-support/manifest.json']),raw
        current,current_bytes=bundle(commit)
        old,old_bytes=bundle(parent)
        timestamp=host._git('show','-s','--format=%cI',commit)
        receipt={'sha':commit,'html_url':f'https://github.com/{REPOSITORY}/commit/{commit}',
                 'parents':[{'sha':parent}],
                 'commit':{'committer':{'date':timestamp},'message':host._git('show','-s','--format=%B',commit)},
                 'files':[{'filename':name,'status':'modified'} for name in
                          host._git('diff-tree','--no-commit-id','--name-only','-r',commit).splitlines()]}
        # Match immutable_snapshot/collect_owned_occurrence's canonical body
        # shape: repository-relative paths. The host converts at its Git edge.
        evidence=OwnedOccurrenceEvidence(
            receipt,current,{name.removeprefix('manager-support/'):raw
                            for name,raw in current_bytes.items()},
            parent,old,{name.removeprefix('manager-support/'):raw
                        for name,raw in old_bytes.items()})
        return packet,parent,commit,evidence

    def _platform_push_boundary(self, host, events, remote_sha):
        original=host._run_cli
        def run(argv, *, input_data=None, timeout=None):
            if argv[:3]==['git','-C',str(host.checkout)] and 'fetch' in argv:
                (host.checkout/'.git'/'FETCH_HEAD').write_text(remote_sha+'\tbranch refs/heads/gh-pages\n')
                return ''
            if argv and argv[0]=='git' and 'push' in argv:
                events.append(('push',host._git('rev-parse','HEAD')))
                return ''
            if argv and argv[0]=='gh':
                events.append(('dispatch',input_data))
                return ''
            return original(argv,input_data=input_data,timeout=timeout)
        return patch.object(host,'_run_cli',side_effect=run)

    def test_stop_survives_fresh_checkpoint_and_cycle_cannot_resume(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf, store, host, gateway, *_ = platform_fixture(root)
            store.stop()
            host.checkpoint.save()
            host.checkpoint.release()

            checkpoint = PrivateCheckpoint(gateway, run_id='123', run_attempt='1')
            db_path = checkpoint.acquire(root / 'fresh-private')
            restored = CycleStore(db_path.parent)
            from manager_core.owned_platform_host import GitHubActionsCycleHost
            resumed = GitHubActionsCycleHost(checkpoint, host.checkout, host.source_audit_path)

            from scripts import phase06_kernel_release as release
            with patch.dict('os.environ', github_environment(), clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                 patch.object(resumed, 'prepare_candidate', side_effect=AssertionError('STOP resumed')):
                result = run_owned_cycle(conf, restored, host=resumed, now=NOW)

            self.assertEqual(result['status'], 'STOPPED_REGRESSION')
            self.assertTrue(restored.stopped())
            self.assertEqual(restored.journal.pending_records(), ())

    def test_versioned_rollback_intent_is_acked_once_and_restore_has_no_send_bit(self):
        from manager_core.outbox import plan_owned_rollback, validate_owned_rollback

        baseline = manifest('a' * 40, 'old')
        candidate = manifest('b' * 40, 'new')
        original = plan_release(baseline, candidate, NOW, schema='manager.digital-handoff.v2')
        intent = plan_owned_rollback(original, 'd' * 40, 'c' * 40, NOW,
                                    controller_sha='b' * 40)
        self.assertEqual(intent['schema'], 'manager.digital-rollback.v1')
        self.assertEqual(intent['candidate_commit'], 'd' * 40)
        self.assertEqual(intent['parent_commit'], 'c' * 40)
        validate_owned_rollback(intent)
        with self.assertRaises(ValueError):
            validate_owned_rollback(dict(intent, candidate_commit='e' * 40))

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = CycleStore(root / 'seed')
            self._save_original_receipt(store,original,'d'*40,'c'*40)
            first = store.journal.reserve_rollback(intent, NOW)
            self.assertTrue(first.dispatch)
            gateway = MemoryGateway(store.db.read_bytes())
            checkpoint = PrivateCheckpoint(gateway, run_id='123', run_attempt='1')
            checkpoint.acquire(root / 'run')
            restored = CycleStore(root / 'run')
            row = restored.journal.rollback_record(intent['effect_key'])
            self.assertEqual(row.status, 'DISPATCHING')
            self.assertFalse(row.dispatch)
            replay = restored.journal.reserve_rollback(intent, NOW)
            self.assertFalse(replay.dispatch)
            self.assertEqual(replay.packet_json, row.packet_json)

    def test_checkpoint_validator_accepts_saved_rollback_and_rejects_corruption(self):
        from manager_core.outbox import plan_owned_rollback
        from manager_core.owned_checkpoint import _validate_database

        original = plan_release(manifest('a' * 40, 'old'), manifest('b' * 40, 'new'),
                                NOW, schema='manager.digital-handoff.v2')
        intent = plan_owned_rollback(original, 'd' * 40, 'c' * 40, NOW,
                                    controller_sha='b' * 40)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = CycleStore(root / 'state')
            self._save_original_receipt(store,original,'d'*40,'c'*40)
            store.journal.reserve_rollback(intent, NOW)
            _validate_database(store.db)
            with sqlite3.connect(store.db) as db:
                db.execute("UPDATE owned_rollbacks SET packet_json=? WHERE key=?",
                           (json.dumps(dict(intent, candidate_commit='e' * 40), sort_keys=True),
                            intent['effect_key']))
            with self.assertRaises(ValueError):
                _validate_database(store.db)

    def test_newest_unresolved_candidate_blocks_rollback_fallback(self):
        with TemporaryDirectory() as tmp:
            store=CycleStore(Path(tmp)/'state')
            baseline=manifest('a'*40,'old')
            first_candidate=manifest('b'*40,'first')
            first=plan_release(baseline,first_candidate,NOW,schema='manager.digital-handoff.v2')
            self._save_original_receipt(store,first,'d'*40,'c'*40)
            self.assertEqual(store.journal.latest_present_record().key,first['effect_key'])

            second_candidate=manifest('c'*40,'second')
            second=plan_release(first_candidate,second_candidate,NOW,schema='manager.digital-handoff.v2')
            publisher=PublisherContext(REPOSITORY,MAIN_REF,WORKFLOW,'c'*40,'123',workflow_commit='c'*40)
            store.journal.reserve(second,publisher,first_candidate,second_candidate,'d'*40,NOW)
            self.assertIsNone(store.journal.latest_present_record())

    def test_delivery_recovery_closes_only_exact_p2_rollback(self):
        from manager_core.outbox import plan_owned_rollback

        with TemporaryDirectory() as tmp:
            store=CycleStore(Path(tmp)/'state')
            original=plan_release(manifest('a'*40,'old'),manifest('b'*40,'candidate'),
                                  NOW,schema='manager.digital-handoff.v2')
            self._save_original_receipt(store,original,'d'*40,'c'*40)
            store.journal.save_delivery(original['effect_key'],{
                'status':'REGRESSION','effect_key':original['effect_key'],'receipt_ref':'d'*40,
                'candidate_sha256':original['candidate_sha256'],'observed_at':NOW.isoformat(),
                'proof_ref':'https://example.test/','proof_level':'P2',
                'reason':'BOUND_CURRENT_PAGE_CUE_FAILURE','human_outcome':'NOT_MEASURED'})
            rollback=plan_owned_rollback(original,'d'*40,'c'*40,NOW,controller_sha='b'*40)
            store.journal.reserve_rollback(rollback,NOW)
            store.journal._rollback_present(rollback['effect_key'],'e'*40)
            pending={'status':'PENDING','effect_key':rollback['effect_key'],'receipt_ref':'e'*40,
                'baseline_sha256':rollback['baseline_sha256'],'observed_at':NOW.isoformat(),
                'proof_ref':'https://example.test/','proof_level':'P0',
                'reason':'ROLLBACK_DEPLOYMENT_NOT_BOUND_SUCCESS','human_outcome':'NOT_MEASURED'}
            store.journal.save_rollback_delivery(rollback['effect_key'],pending)
            self.assertEqual([r.key for r in store.journal.pending_deliveries()],
                             [original['effect_key']])

            verified=dict(pending,status='VERIFIED',proof_level='P2',
                          reason='EXACT_DEPLOYED_PARENT_BASELINE')
            store.journal.save_rollback_delivery(rollback['effect_key'],verified)
            self.assertEqual(store.journal.pending_deliveries(),())

    def test_trusted_resume_clears_stop_only_after_recovery_and_checkpoints(self):
        from scripts import run_owned_digital_cycle as cli
        from scripts import phase06_kernel_release as release
        from manager_core.owned_platform_host import GitHubActionsCycleHost
        from manager_core.outbox import plan_owned_rollback

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,store,host,gateway,context,_,_,pages=platform_fixture(root)
            packet=plan_release(
                json.loads((context.baseline_bundle/'manifest.json').read_text()),
                json.loads((context.candidate_bundle/'manifest.json').read_text()),
                NOW,schema='manager.digital-handoff.v2')
            parent=host._git('rev-parse','HEAD')
            self._save_original_receipt(store,packet,'d'*40,parent)
            verified={'status':'VERIFIED','effect_key':packet['effect_key'],
                'receipt_ref':'d'*40,'candidate_sha256':packet['candidate_sha256'],
                'observed_at':NOW.isoformat(),'proof_ref':'https://example.test/',
                'proof_level':'P2','reason':'EXACT_DEPLOYED_CANDIDATE',
                'human_outcome':'NOT_MEASURED'}
            store.journal.save_delivery(packet['effect_key'],verified)
            rollback=plan_owned_rollback(packet,'d'*40,parent,NOW,controller_sha='b'*40)
            store.journal.reserve_rollback(rollback,NOW)
            store.journal._rollback_present(rollback['effect_key'],'e'*40)
            rollback_verified={'status':'VERIFIED','effect_key':rollback['effect_key'],
                'receipt_ref':'e'*40,'baseline_sha256':rollback['baseline_sha256'],
                'observed_at':NOW.isoformat(),'proof_ref':'https://example.test/',
                'proof_level':'P2','reason':'EXACT_DEPLOYED_PARENT_BASELINE',
                'human_outcome':'NOT_MEASURED'}
            store.journal.save_rollback_delivery(rollback['effect_key'],rollback_verified)
            store.stop()
            host.checkpoint.save()
            host.checkpoint.release()
            current={'kind':'rollback','effect_key':rollback['effect_key'],
                     'receipt_ref':'e'*40,'evidence':rollback_verified}
            context={'run_id':'123','attempt':'1','source_sha':'b'*40,
                     'runner_temp':root,'pages_root':pages.root}
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch.object(cli,'_check_main_context',return_value=context), \
                 patch.object(cli,'_private_fresh_root',return_value=root/'resume-private'), \
                 patch.object(cli,'PrivateCheckpoint',side_effect=lambda **kwargs:
                              PrivateCheckpoint(gateway,**kwargs)), \
                 patch.object(release,'source_checkout_commit',return_value='b'*40), \
                 patch.object(cli,'_recover_owned_deliveries',return_value=None), \
                 patch.object(GitHubActionsCycleHost,'observe_current_delivery',return_value=current):
                code,summary=cli.run_control('resume',root/'unused',pages.root)
            self.assertEqual(code,0,summary)
            self.assertEqual(summary['status'],'RESUMED_BY_OWNER')
            self.assertEqual(summary['authentication'],'GATEWAY_ACKNOWLEDGED')
            checkpoint=PrivateCheckpoint(gateway,run_id='123',run_attempt='1')
            db_path=checkpoint.acquire(root/'verify-resume')
            restored=CycleStore(db_path.parent)
            self.assertFalse(restored.stopped())

    def test_trusted_cli_stop_checkpoints_before_return_and_survives_restore(self):
        from scripts import run_owned_digital_cycle as cli
        from scripts import phase06_kernel_release as release

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,store,host,gateway,_,_,_,pages=platform_fixture(root)
            host.checkpoint.release()
            context={'run_id':'123','attempt':'1','source_sha':'b'*40,
                     'runner_temp':root,'pages_root':pages.root}
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch.object(cli,'_check_main_context',return_value=context), \
                 patch.object(cli,'_private_fresh_root',return_value=root/'stop-private'), \
                 patch.object(cli,'PrivateCheckpoint',side_effect=lambda **kwargs:
                              PrivateCheckpoint(gateway,**kwargs)), \
                 patch.object(release,'source_checkout_commit',return_value='b'*40):
                code,summary=cli.run_control('stop',root/'unused',pages.root)
            self.assertEqual(code,0)
            self.assertEqual(summary['status'],'STOPPED_BY_OWNER')
            self.assertEqual(summary['authentication'],'GATEWAY_ACKNOWLEDGED')
            checkpoint=PrivateCheckpoint(gateway,run_id='123',run_attempt='1')
            db_path=checkpoint.acquire(root/'verify-stop-control')
            restored=CycleStore(db_path.parent)
            self.assertTrue(restored.stopped())

    def test_later_current_regression_overrides_historical_p2_without_erasing_it(self):
        from scripts import run_owned_digital_cycle as cli
        from scripts import phase06_kernel_release as release
        from manager_core.owned_platform_host import GitHubActionsCycleHost

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            conf,store,host,gateway,_,_,_,pages=platform_fixture(root)
            packet,_,receipt,_=self._install_candidate_commit(host,store,stop=False)
            verified={'status':'VERIFIED','effect_key':packet['effect_key'],
                'receipt_ref':receipt,'candidate_sha256':packet['candidate_sha256'],
                'observed_at':NOW.isoformat(),
                'proof_ref':'https://daisuke134.github.io/life-manager/manager-support/',
                'proof_level':'P2','reason':'EXACT_DEPLOYED_CANDIDATE',
                'human_outcome':'NOT_MEASURED'}
            store.journal.save_delivery(packet['effect_key'],verified)
            current_regression={'kind':'candidate','effect_key':packet['effect_key'],
                'receipt_ref':receipt,'evidence':dict(verified,status='REGRESSION',
                    reason='BOUND_CURRENT_PAGE_CUE_FAILURE',observed_at=datetime.now(timezone.utc).isoformat())}

            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch.object(release,'source_checkout_commit',return_value='b'*40), \
                 patch.object(host,'observe_current_delivery',return_value=current_regression):
                first=run_owned_cycle(conf,store,host=host,now=NOW)
            self.assertEqual(first['status'],'STOPPED_REGRESSION')
            self.assertTrue(store.stopped())
            self.assertEqual(store.journal.delivery_record(packet['effect_key'])['status'],'VERIFIED')
            host.checkpoint.save();host.checkpoint.release()

            checkpoint=PrivateCheckpoint(gateway,run_id='123',run_attempt='1')
            db_path=checkpoint.acquire(root/'later-cycle-private')
            restored=CycleStore(db_path.parent)
            resumed=GitHubActionsCycleHost(checkpoint,host.checkout,host.source_audit_path)
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch.object(release,'source_checkout_commit',return_value='b'*40), \
                 patch.object(resumed,'observe_current_delivery',return_value=current_regression), \
                 patch.object(resumed,'prepare_candidate',side_effect=AssertionError('stopped cycle planned')) as prepare, \
                 patch.object(resumed,'send_owned',side_effect=AssertionError('stopped cycle sent')) as send:
                later=run_owned_cycle(conf,restored,host=resumed,now=NOW)
            self.assertEqual(later['status'],'STOPPED_REGRESSION')
            self.assertTrue(restored.stopped())
            self.assertEqual(restored.journal.delivery_record(packet['effect_key'])['status'],'VERIFIED')
            prepare.assert_not_called();send.assert_not_called()
            checkpoint.save();checkpoint.release()

            control_context={'run_id':'123','attempt':'1','source_sha':'b'*40,
                             'runner_temp':root,'pages_root':pages.root}
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch.object(cli,'_check_main_context',return_value=control_context), \
                 patch.object(cli,'_private_fresh_root',return_value=root/'resume-after-regression'), \
                 patch.object(cli,'PrivateCheckpoint',side_effect=lambda **kwargs:
                              PrivateCheckpoint(gateway,**kwargs)), \
                 patch.object(release,'source_checkout_commit',return_value='b'*40), \
                 patch.object(GitHubActionsCycleHost,'observe_current_delivery',return_value=current_regression):
                code,summary=cli.run_control('resume',root/'unused',pages.root)
            self.assertEqual(code,2)
            self.assertEqual(summary['status'],'UNKNOWN')

            checkpoint=PrivateCheckpoint(gateway,run_id='123',run_attempt='1')
            db_path=checkpoint.acquire(root/'verify-regression-stop')
            finally_restored=CycleStore(db_path.parent)
            self.assertTrue(finally_restored.stopped())
            self.assertEqual(finally_restored.journal.delivery_record(packet['effect_key'])['status'],'VERIFIED')

    def test_current_delivery_unknown_preserves_p2_without_stop_or_send(self):
        from scripts import phase06_kernel_release as release

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            conf,store,host,_,_,_,_,_=platform_fixture(root)
            packet,_,receipt,_=self._install_candidate_commit(host,store,stop=False)
            verified={'status':'VERIFIED','effect_key':packet['effect_key'],
                'receipt_ref':receipt,'candidate_sha256':packet['candidate_sha256'],
                'observed_at':NOW.isoformat(),'proof_ref':'https://example.test/',
                'proof_level':'P2','reason':'EXACT_DEPLOYED_CANDIDATE',
                'human_outcome':'NOT_MEASURED'}
            store.journal.save_delivery(packet['effect_key'],verified)
            current={'kind':'candidate','effect_key':packet['effect_key'],
                'receipt_ref':receipt,'evidence':dict(verified,status='UNKNOWN',proof_level='P0',
                    reason='PAGES_DEPLOYMENT_NOT_BOUND_SUCCESS')}
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch.object(release,'source_checkout_commit',return_value='b'*40), \
                 patch.object(host,'observe_current_delivery',return_value=current), \
                 patch.object(host,'prepare_candidate',side_effect=AssertionError('unknown health planned')) as prepare, \
                 patch.object(host,'send_owned',side_effect=AssertionError('unknown health sent')) as send:
                result=run_owned_cycle(conf,store,host=host,now=NOW)
            self.assertEqual(result['status'],'UNKNOWN')
            self.assertFalse(store.stopped())
            self.assertEqual(store.journal.delivery_record(packet['effect_key'])['status'],'VERIFIED')
            prepare.assert_not_called();send.assert_not_called()

    def test_current_v1_seed_allows_healthy_cycle_to_reach_not_due(self):
        from test_owned_public_collector import PublicCollectorTests
        from scripts import phase06_kernel_release as release

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            conf,store,host,_,_,_,_,_=platform_fixture(root/'platform')
            packet,source_journal,_,_,_,urls=PublicCollectorTests().prepare_v1_current_fixture(
                root/'v1-fixture')
            self._copy_saved_v1_receipt(store,packet,source_journal)
            self.assertTrue(store.due(conf,NOW))
            def get(url):
                self.assertIn(url,urls,'current v1 cycle used an unexpected public endpoint')
                return urls[url]
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch.object(release,'source_checkout_commit',return_value='b'*40), \
                 patch.object(release,'public_get',side_effect=get):
                result=run_owned_cycle(conf,store,host=host,now=NOW)
            self.assertEqual(result['status'],'NOT_DUE')
            self.assertFalse(store.stopped())
            self.assertEqual(store.journal.delivery_record(packet['effect_key'])['status'],'VERIFIED')

    def test_current_v1_seed_can_resume_only_after_fresh_verified_readback(self):
        from test_owned_public_collector import PublicCollectorTests
        from scripts import run_owned_digital_cycle as cli
        from scripts import phase06_kernel_release as release

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,store,host,gateway,_,_,_,pages=platform_fixture(root/'platform')
            packet,source_journal,_,_,_,urls=PublicCollectorTests().prepare_v1_current_fixture(
                root/'v1-fixture')
            self._copy_saved_v1_receipt(store,packet,source_journal)
            store.stop()
            host.checkpoint.save();host.checkpoint.release()
            context={'run_id':'123','attempt':'1','source_sha':'b'*40,
                     'runner_temp':root,'pages_root':pages.root}
            def get(url):
                self.assertIn(url,urls,'current v1 resume used an unexpected public endpoint')
                return urls[url]
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch.object(cli,'_check_main_context',return_value=context), \
                 patch.object(cli,'_private_fresh_root',return_value=root/'resume-v1-private'), \
                 patch.object(cli,'PrivateCheckpoint',side_effect=lambda **kwargs:
                              PrivateCheckpoint(gateway,**kwargs)), \
                 patch.object(release,'source_checkout_commit',return_value='b'*40), \
                 patch.object(release,'public_get',side_effect=get):
                code,summary=cli.run_control('resume',root/'unused',pages.root)
            self.assertEqual(code,0,summary)
            self.assertEqual(summary['status'],'RESUMED_BY_OWNER')
            checkpoint=PrivateCheckpoint(gateway,run_id='123',run_attempt='1')
            db_path=checkpoint.acquire(root/'verify-v1-resume')
            restored=CycleStore(db_path.parent)
            self.assertFalse(restored.stopped())
            self.assertEqual(restored.journal.delivery_record(packet['effect_key'])['status'],'VERIFIED')

    def test_resume_refuses_uncertain_occurrence_without_clearing_stop(self):
        from scripts import run_owned_digital_cycle as cli
        from scripts import phase06_kernel_release as release
        from manager_core.reconcile import reconcile_pending_owned

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,store,host,gateway,context,_,_,pages=platform_fixture(root)
            packet=plan_release(
                json.loads((context.baseline_bundle/'manifest.json').read_text()),
                json.loads((context.candidate_bundle/'manifest.json').read_text()),
                NOW,schema='manager.digital-handoff.v2')
            publisher=PublisherContext(REPOSITORY,MAIN_REF,WORKFLOW,'b'*40,'123',workflow_commit='b'*40)
            store.journal.reserve(packet,publisher,packet['baseline'],packet['candidate'],
                                  host._git('rev-parse','HEAD'),NOW)
            store.stop();host.checkpoint.save();host.checkpoint.release()
            control_context={'run_id':'123','attempt':'1','source_sha':'b'*40,
                             'runner_temp':root,'pages_root':pages.root}
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch.object(cli,'_check_main_context',return_value=control_context), \
                 patch.object(cli,'_private_fresh_root',return_value=root/'resume-private'), \
                 patch.object(cli,'PrivateCheckpoint',side_effect=lambda **kwargs:
                              PrivateCheckpoint(gateway,**kwargs)), \
                 patch.object(release,'source_checkout_commit',return_value='b'*40), \
                 patch('manager_core.reconcile.reconcile_pending_owned',return_value=None), \
                 patch.object(cli,'_recover_owned_deliveries',return_value=None):
                code,summary=cli.run_control('resume',root/'unused',pages.root)
            self.assertEqual(code,2)
            self.assertEqual(summary['status'],'UNKNOWN')
            checkpoint=PrivateCheckpoint(gateway,run_id='123',run_attempt='1')
            db_path=checkpoint.acquire(root/'verify-still-stopped')
            restored=CycleStore(db_path.parent)
            self.assertTrue(restored.stopped())

    def test_cli_control_rejects_caller_receipt_and_requires_workflow_dispatch(self):
        from scripts import run_owned_digital_cycle as cli

        with self.assertRaises(SystemExit):
            cli.main(['rollback', '--state-store', '/tmp/state', '--pages-checkout',
                      '/tmp/pages', '--receipt', 'a' * 40])

        with TemporaryDirectory() as tmp, \
             patch.dict('os.environ', github_environment(GITHUB_EVENT_NAME='schedule'), clear=True), \
             patch.object(cli, 'PrivateCheckpoint', side_effect=AssertionError('untrusted control acquired lease')):
            code, summary = cli.run_control('stop', Path(tmp) / 'state', Path(tmp) / 'pages')
        self.assertEqual(code, 2)
        self.assertEqual(summary['status'], 'UNKNOWN')
        self.assertEqual(summary['authentication'], 'NOT_PROVEN')
        self.assertFalse((Path(tmp) / 'state').exists())

    def test_explicit_rollback_acks_before_push_restores_parent_bytes_and_keeps_stop(self):
        from manager_core.owned_public_collector import OwnedRollbackEvidence
        import manager_core.owned_public_collector as collector

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,store,host,gateway,context,*_=platform_fixture(root)
            _,parent,candidate,evidence=self._install_candidate_commit(host,store)
            events=[]
            save=host.checkpoint.save
            def save_ack():
                events.append(('checkpoint',gateway.value['revision']+1))
                return save()
            def rollback_proof(key,journal,observed_at=None,**kwargs):
                commit=next(value for name,value in events if name=='push')
                return OwnedRollbackEvidence({'sha':commit}, {}, {}, candidate, {}, {})
            def delivery_proof(key,journal,observed_at=None,**kwargs):
                row=journal.rollback_record(key)
                packet=json.loads(row.packet_json)
                return {'status':'VERIFIED','effect_key':key,'receipt_ref':row.receipt_ref,
                    'baseline_sha256':packet['baseline_sha256'],'observed_at':datetime.now(timezone.utc).isoformat(),
                    'proof_ref':'https://daisuke134.github.io/life-manager/manager-support/',
                    'proof_level':'P2','reason':'EXACT_DEPLOYED_PARENT_BASELINE','human_outcome':'NOT_MEASURED'}
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch('scripts.phase06_kernel_release.source_checkout_commit',return_value='b'*40), \
                 patch.object(host,'_now',wraps=host._now), \
                 patch.object(host.checkpoint,'save',side_effect=save_ack), \
                 patch.object(collector,'collect_owned_occurrence',return_value=evidence), \
                 patch.object(collector,'collect_owned_rollback',side_effect=rollback_proof), \
                 patch.object(collector,'collect_owned_rollback_delivery',side_effect=delivery_proof), \
                 self._platform_push_boundary(host,events,candidate):
                result=host.rollback_latest_owned(store)

            self.assertEqual(result['status'],'ROLLBACK_SUBMITTED')
            self.assertEqual(result['rollback_delivery_status'],'VERIFIED')
            self.assertTrue(store.stopped())
            self.assertEqual([name for name,_ in events],['checkpoint','push','dispatch'])
            self.assertLess(events.index(('checkpoint',1)),events.index(next(row for row in events if row[0]=='push')))
            rollback_commit=next(value for name,value in events if name=='push')
            restored={name:host._git_blob(rollback_commit,name) for name in ALLOWED_PATHS}
            self.assertEqual(restored,{
                'manager-support/'+name:raw
                for name,raw in evidence.parent_bodies.items()})
            self.assertEqual(host._git_blob(rollback_commit,'manager-support/manifest.json'),
                             evidence.parent_bodies['manifest.json'])
            self.assertEqual((host.checkout/'unrelated.html').read_bytes(),b'preserve me')
            saved=store.journal.latest_rollback_record()
            self.assertEqual(saved.status,'PRESENT')
            self.assertEqual(saved.receipt_ref,rollback_commit)
            self.assertEqual(saved.delivery_status,'VERIFIED')

    def test_rollback_uses_real_relative_immutable_collector_output(self):
        import manager_core.owned_public_collector as collector
        from scripts import phase06_kernel_release as release

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,store,host,_,*_=platform_fixture(root)
            _,parent,candidate,_=self._install_candidate_commit(host,store)
            events=[]
            raw_reads=[]

            def receipt(sha):
                parent_sha=host._git('rev-parse',sha+'^')
                return {'sha':sha,
                    'html_url':f'https://github.com/{REPOSITORY}/commit/{sha}',
                    'parents':[{'sha':parent_sha}],
                    'commit':{'committer':{'date':host._git('show','-s','--format=%cI',sha)},
                              'message':host._git('show','-s','--format=%B',sha)},
                    'files':[{'filename':name,'status':'modified'} for name in
                        host._git('diff-tree','--no-commit-id','--name-only','-r',sha).splitlines()]}

            def get(url):
                prefix=f'https://api.github.com/repos/{REPOSITORY}/commits/'
                list_prefix=f'https://api.github.com/repos/{REPOSITORY}/commits?'
                if url.startswith(list_prefix):
                    rows=[]
                    current=host._git('rev-parse','HEAD')
                    for sha in dict.fromkeys((current,candidate)):
                        value=receipt(sha)
                        rows.append({'sha':sha,'commit':{'message':value['commit']['message']}})
                    return json.dumps(rows).encode()
                if url.startswith(prefix) and '?sha=' not in url:
                    return json.dumps(receipt(url.removeprefix(prefix))).encode()
                raw_prefix=f'https://raw.githubusercontent.com/{REPOSITORY}/'
                if url.startswith(raw_prefix):
                    raw_reads.append(url)
                    sha,path=url.removeprefix(raw_prefix).split('/',1)
                    return host._git_blob(sha,path)
                raise AssertionError(f'unexpected immutable collector URL: {url}')

            def pending_delivery(key,journal,observed_at=None,**kwargs):
                row=journal.rollback_record(key);packet=json.loads(row.packet_json)
                return {'status':'VERIFIED','effect_key':key,'receipt_ref':row.receipt_ref,
                    'baseline_sha256':packet['baseline_sha256'],
                    'observed_at':datetime.now(timezone.utc).isoformat(),
                    'proof_ref':'https://daisuke134.github.io/life-manager/manager-support/',
                    'proof_level':'P2','reason':'EXACT_DEPLOYED_PARENT_BASELINE',
                    'human_outcome':'NOT_MEASURED'}

            actual_rollback_read=collector.collect_owned_rollback
            rollback_results=[]
            clock_index=[0]
            clock_base=datetime.now(timezone.utc)
            def advancing_now():
                value=clock_base+timedelta(seconds=clock_index[0])
                clock_index[0]+=1
                return value
            def observe_rollback(*args,**kwargs):
                value=actual_rollback_read(*args,**kwargs)
                rollback_results.append(value)
                return value

            with patch.dict('os.environ',github_environment(
                    GIT_AUTHOR_DATE=(clock_base+timedelta(seconds=3)).isoformat(),
                    GIT_COMMITTER_DATE=(clock_base+timedelta(seconds=3)).isoformat()),clear=True), \
                 patch.object(release,'source_checkout_commit',return_value='b'*40), \
                 patch.object(release,'public_get',side_effect=get), \
                 patch.object(host,'_now',side_effect=advancing_now), \
                 patch.object(collector,'collect_owned_rollback',side_effect=observe_rollback), \
                 patch.object(collector,'collect_owned_rollback_delivery',
                              side_effect=pending_delivery), \
                 self._platform_push_boundary(host,events,candidate):
                result=host.rollback_latest_owned(store)

            self.assertEqual(len(rollback_results),1)
            self.assertIsNotNone(rollback_results[0])
            self.assertEqual(result['status'],'ROLLBACK_SUBMITTED',result)
            self.assertEqual([name for name,_ in events],['push','dispatch'])
            rollback_sha=result['receipt_ref']
            self.assertEqual(host._git('rev-parse',rollback_sha+'^'),candidate)
            self.assertEqual({name:host._git_blob(rollback_sha,name) for name in ALLOWED_PATHS},
                {name:host._git_blob(parent,name) for name in ALLOWED_PATHS})
            self.assertTrue({f'{candidate}/{name}' for name in ALLOWED_PATHS} <=
                            {url.removeprefix(
                                f'https://raw.githubusercontent.com/{REPOSITORY}/')
                             for url in raw_reads})

    def test_lost_pre_send_checkpoint_ack_has_zero_push_and_restore_reconcile_only(self):
        from manager_core.owned_checkpoint import CheckpointUnavailable
        import manager_core.owned_public_collector as collector

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,store,host,gateway,*_=platform_fixture(root)
            _,parent,candidate,evidence=self._install_candidate_commit(host,store)
            gateway.lose_ack=True
            events=[]
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch('scripts.phase06_kernel_release.source_checkout_commit',return_value='b'*40), \
                 patch.object(collector,'collect_owned_occurrence',return_value=evidence), \
                 self._platform_push_boundary(host,events,candidate):
                with self.assertRaises(CheckpointUnavailable):
                    host.rollback_latest_owned(store)
            self.assertEqual(events,[])
            self.assertEqual(gateway.value['revision'],1)
            pending=store.journal.pending_rollbacks()[0]
            self.assertEqual(pending.status,'DISPATCHING')
            self.assertFalse(pending.dispatch)

            # A fresh session sees the acknowledged (but lost) reservation and
            # may only reconcile it; it cannot re-enter the send path.
            gateway.value['owner']=None
            checkpoint=PrivateCheckpoint(gateway,run_id='123',run_attempt='1')
            db_path=checkpoint.acquire(root/'restored-private')
            restored=CycleStore(db_path.parent)
            from manager_core.owned_platform_host import GitHubActionsCycleHost
            resumed=GitHubActionsCycleHost(checkpoint,host.checkout,host.source_audit_path)
            with patch.object(collector,'collect_owned_rollback',return_value=None), \
                 patch.object(resumed,'send_owned_rollback',side_effect=AssertionError('replayed rollback')):
                result=resumed.reconcile_pending_rollbacks(restored)
            self.assertEqual(result['status'],'UNKNOWN')
            self.assertEqual(events,[])

    def test_sibling_target_advance_blocks_rollback_without_falling_back_to_candidate(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,store,host,_,*_=platform_fixture(root)
            _,parent,candidate,_=self._install_candidate_commit(host,store)
            (host.checkout/'unrelated.html').write_text('sibling owner advance')
            host._git('add','--','unrelated.html');host._git('commit','-qm','sibling advance')
            sibling=host._git('rev-parse','HEAD')
            events=[]
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch('scripts.phase06_kernel_release.source_checkout_commit',return_value='b'*40), \
                 self._platform_push_boundary(host,events,sibling):
                result=host.rollback_latest_owned(store)
            self.assertEqual(result['status'],'ROLLBACK_BLOCKED')
            self.assertEqual(result['reason'],'LATEST_RECEIPT_NOT_CURRENT')
            self.assertEqual(host._git('rev-parse','HEAD'),sibling)
            self.assertEqual(events,[])
            self.assertTrue(store.stopped())

    def test_deployment_lag_does_not_stop_but_exact_bound_rubric_failure_does(self):
        import manager_core.owned_public_collector as collector

        for status,reason,expected,stopped in (
            ('UNKNOWN','PAGES_DEPLOYMENT_NOT_BOUND_SUCCESS','UNKNOWN',False),
            ('REGRESSION','BOUND_CURRENT_PAGE_CUE_FAILURE','STOPPED_REGRESSION',True),
        ):
            with self.subTest(status=status),TemporaryDirectory() as tmp:
                _,store,host,_,*_=platform_fixture(Path(tmp))
                packet,_,receipt,_=self._install_candidate_commit(host,store,stop=False)
                observation={'status':status,'effect_key':packet['effect_key'],
                    'receipt_ref':receipt,'candidate_sha256':packet['candidate_sha256'],
                    'observed_at':NOW.isoformat(),
                    'proof_ref':'https://daisuke134.github.io/life-manager/manager-support/',
                    'proof_level':'P2' if status=='REGRESSION' else 'P0',
                    'reason':reason,'human_outcome':'NOT_MEASURED'}
                from scripts import phase06_kernel_release as release
                with patch.dict('os.environ',github_environment(),clear=True), \
                     patch.object(release,'source_checkout_commit',return_value='b'*40), \
                     patch.object(host,'observe_current_delivery',return_value=None), \
                     patch.object(collector,'collect_owned_delivery',return_value=observation):
                    result=run_owned_cycle(CycleConfig('platform-fixture-owner',60),store,
                                           host=host,now=NOW)
                self.assertEqual(result['status'],expected)
                self.assertEqual(store.stopped(),stopped)

    def test_crash_after_rollback_send_restores_as_reconcile_only(self):
        from manager_core.owned_public_collector import OwnedRollbackEvidence
        from manager_core.owned_checkpoint import PrivateCheckpoint
        import manager_core.owned_public_collector as collector

        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            _,store,host,gateway,*_=platform_fixture(root)
            _,parent,candidate,evidence=self._install_candidate_commit(host,store)
            events=[]
            actual=host._run_cli
            def after_dispatch(argv,*,input_data=None,timeout=None):
                if argv[:3]==['git','-C',str(host.checkout)] and 'fetch' in argv:
                    (host.checkout/'.git'/'FETCH_HEAD').write_text(candidate+'\tbranch refs/heads/gh-pages\n')
                    return ''
                if argv and argv[0]=='git' and 'push' in argv:
                    events.append(('push',host._git('rev-parse','HEAD')))
                    return ''
                if argv and argv[0]=='gh':
                    events.append(('dispatch',input_data))
                    raise RuntimeError('lost response after deployment dispatch')
                return actual(argv,input_data=input_data,timeout=timeout)
            with patch.dict('os.environ',github_environment(),clear=True), \
                 patch('scripts.phase06_kernel_release.source_checkout_commit',return_value='b'*40), \
                 patch.object(collector,'collect_owned_occurrence',return_value=evidence), \
                 patch.object(host,'_run_cli',side_effect=after_dispatch):
                with self.assertRaises(RuntimeError):
                    host.rollback_latest_owned(store)
            self.assertEqual([event[0] for event in events],['push','dispatch'])
            rollback_sha=events[0][1]
            row=store.journal.latest_rollback_record()
            self.assertEqual(row.status,'DISPATCHING')
            self.assertFalse(row.dispatch)
            self.assertEqual(gateway.value['revision'],1)

            gateway.value['owner']=None
            checkpoint=PrivateCheckpoint(gateway,run_id='123',run_attempt='1')
            db_path=checkpoint.acquire(root/'post-send-restore')
            restored=CycleStore(db_path.parent)
            from manager_core.owned_platform_host import GitHubActionsCycleHost
            resumed=GitHubActionsCycleHost(checkpoint,host.checkout,host.source_audit_path)
            def rollback_proof(key,journal,observed_at=None,**kwargs):
                return OwnedRollbackEvidence({'sha':rollback_sha},{},{},candidate,{}, {})
            def p2_pending(key,journal,observed_at=None,**kwargs):
                saved=journal.rollback_record(key);packet=json.loads(saved.packet_json)
                return {'status':'PENDING','effect_key':key,'receipt_ref':rollback_sha,
                    'baseline_sha256':packet['baseline_sha256'],'observed_at':datetime.now(timezone.utc).isoformat(),
                    'proof_ref':'https://daisuke134.github.io/life-manager/manager-support/',
                    'proof_level':'P0','reason':'ROLLBACK_DEPLOYMENT_NOT_BOUND_SUCCESS',
                    'human_outcome':'NOT_MEASURED'}
            with patch.object(collector,'collect_owned_rollback',side_effect=rollback_proof), \
                 patch.object(collector,'collect_owned_rollback_delivery',side_effect=p2_pending), \
                 patch.object(resumed,'send_owned_rollback',side_effect=AssertionError('rollback replay')):
                result=resumed.reconcile_pending_rollbacks(restored)
            self.assertEqual(result['status'],'ROLLBACK_RECONCILED')
            self.assertEqual(result['rollback_delivery_status'],'PENDING')
            row=restored.journal.latest_rollback_record()
            self.assertEqual(row.status,'PRESENT')
            self.assertEqual(row.receipt_ref,rollback_sha)
            self.assertEqual(row.delivery_status,'PENDING')
            self.assertTrue(restored.stopped())


if __name__ == '__main__':
    unittest.main()
