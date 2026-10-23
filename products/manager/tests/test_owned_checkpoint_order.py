"""Pre-send private reservation barrier and recovery tests (P0 fixtures only)."""
import base64
from contextlib import ExitStack
from time import monotonic
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_candidate_verification import NOW
from test_owned_platform_host import github_environment, platform_fixture
from manager_core.digital_handoff import MAIN_REF, REPOSITORY, WORKFLOW, prepare_owned_change
from manager_core.owned_checkpoint import PrivateCheckpoint
from manager_core.owned_cycle import run_owned_cycle, CycleStore


class OwnedCheckpointOrderTests(unittest.TestCase):
    def test_shadow_initialization_follows_all_existing_cycle_gates(self):
        from manager_core.owned_platform_host import CatalogShadowSettings
        from manager_core import owned_provider_shadow as shadow
        from manager_core.digital_handoff import PublisherContext
        from manager_core.outbox import plan_owned_rollback
        from test_owned_platform_rollback import OwnedPlatformRollbackTests
        from scripts import phase06_kernel_release as release
        import manager_core.owned_public_collector as collector
        expected = {'owner_busy': 'OWNER_BUSY', 'rollback': 'UNKNOWN',
                    'occurrence': 'UNKNOWN', 'current_delivery': 'UNKNOWN',
                    'delivery': 'UNKNOWN', 'stop': 'STOPPED_REGRESSION',
                    'not_due': 'NOT_DUE', 'release_disabled': 'NO_ACTION'}
        for gate, status in expected.items():
            with self.subTest(gate=gate), TemporaryDirectory() as tmp, ExitStack() as stack:
                factories = []
                settings = CatalogShadowSettings(monotonic()+120,
                    client_factory=lambda: factories.append('factory'))
                conf, store, host, *_ = platform_fixture(Path(tmp), catalog_shadow=settings)
                current = None
                if gate in ('rollback', 'delivery', 'current_delivery'):
                    packet, parent, receipt, _ = OwnedPlatformRollbackTests()._install_candidate_commit(
                        host, store, stop=False)
                    evidence = dict(status='PENDING', effect_key=packet['effect_key'],
                        receipt_ref=receipt, candidate_sha256=packet['candidate_sha256'],
                        observed_at=NOW.isoformat(), proof_ref='https://example.test/',
                        proof_level='P0', reason='PAGES_DEPLOYMENT_LAG', human_outcome='NOT_MEASURED')
                    if gate == 'rollback':
                        rollback = plan_owned_rollback(packet, receipt, parent, NOW, controller_sha='b'*40)
                        store.journal.reserve_rollback(rollback, NOW)
                    elif gate == 'current_delivery':
                        verified = dict(evidence, status='VERIFIED', proof_level='P2', reason='EXACT_DEPLOYED_CANDIDATE')
                        store.journal.save_delivery(packet['effect_key'], verified)
                        current = dict(kind='candidate', effect_key=packet['effect_key'], receipt_ref=receipt,
                            evidence=dict(evidence, status='UNKNOWN', reason='PAGES_DEPLOYMENT_NOT_BOUND_SUCCESS'))
                    stack.enter_context(patch.object(collector, 'collect_owned_delivery', return_value=evidence))
                elif gate == 'occurrence':
                    packet = prepare_owned_change(host.context, host.assessment, host.scope, NOW,
                                                  schema='manager.digital-handoff.v2').packet
                    publisher = PublisherContext(REPOSITORY, MAIN_REF, WORKFLOW, 'b'*40,
                                                 '123', workflow_commit='b'*40)
                    store.journal.reserve(packet, publisher, packet['baseline'], packet['candidate'],
                                          host._git('rev-parse', 'HEAD'), NOW)
                elif gate == 'stop':
                    store.stop()
                elif gate == 'not_due':
                    self.assertTrue(store.due(conf, NOW))
                elif gate == 'owner_busy':
                    self.assertTrue(stack.enter_context(store.owner_lock()))
                env = github_environment(MANAGER_RELEASE_ENABLED='false') if gate == 'release_disabled' else github_environment()
                with patch.dict('os.environ', env, clear=True), \
                     patch.object(release, 'source_checkout_commit', return_value='b'*40), \
                     patch.object(collector, 'collect_owned_occurrence', return_value=None), \
                     patch.object(collector, 'collect_owned_rollback', return_value=None), \
                     patch.object(host, 'observe_current_delivery', return_value=current), \
                     patch.object(shadow, 'compare_prepared_catalog_shadow', wraps=shadow.compare_prepared_catalog_shadow) as compare, \
                     patch.object(shadow, 'CheckpointedProvider', side_effect=AssertionError('provider initialized')) as provider, \
                     patch.object(host, 'send_owned') as send, \
                     self.frozen_now(host):
                    result = run_owned_cycle(conf, store, host=host, now=NOW)
                self.assertEqual(result['status'], status)
                compare.assert_not_called()
                provider.assert_not_called()
                send.assert_not_called()
                self.assertEqual(factories, [])
                self.assertIsNone(host._catalog_shadow_result)

    def frozen_now(self, host):
        return patch.object(host, '_now', return_value=NOW)

    def local_cli_boundary(self, host, events, expected_parent):
        actual = host._run_cli

        def run(argv, *, input_data=None, timeout=None):
            if argv[:3] == ['git', '-C', str(host.checkout)] and 'fetch' in argv:
                (host.checkout / '.git' / 'FETCH_HEAD').write_text(
                    expected_parent + '\tbranch refs/heads/gh-pages\n')
                return ''
            if argv and argv[0] == 'git' and 'push' in argv:
                events.append('push')
                return ''
            if argv and argv[0] == 'gh':
                events.append('dispatch')
                return ''
            return actual(argv, input_data=input_data, timeout=timeout)

        return patch.object(host, '_run_cli', side_effect=run)

    def test_reservation_ack_precedes_original_admission_and_every_send(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, gateway, *_ = platform_fixture(Path(tmp))
            from scripts import phase06_kernel_release as release
            import manager_core.owned_public_collector as collector
            parent = host._git('rev-parse', 'HEAD')
            events = []
            save = host.checkpoint.save

            def acknowledged_save():
                events.append('checkpoint')
                return save()

            admit = release.admit_owned

            def admitted(*args, **kwargs):
                events.append('admit')
                row = store.journal.pending_records()[0]
                self.assertFalse(row.dispatch)
                raw = base64.b64decode(gateway.value['snapshot'])
                snap = Path(tmp) / 'remote-snapshot.sqlite'
                snap.write_bytes(raw)
                with sqlite3.connect(snap) as db:
                    saved = db.execute(
                        'SELECT key,expected_parent,status FROM owned_effects'
                    ).fetchone()
                self.assertEqual(saved, (row.key, parent, 'DISPATCHING'))
                self.assertEqual(gateway.value['revision'], 1)
                return admit(*args, **kwargs)

            with patch.dict('os.environ', github_environment(), clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                 patch.object(release, 'admit_owned', side_effect=admitted), \
                 patch.object(host.checkpoint, 'save', side_effect=acknowledged_save), \
                 self.local_cli_boundary(host, events, parent), \
                 patch.object(collector, 'collect_owned_occurrence', return_value=None), \
                 self.frozen_now(host):
                result = run_owned_cycle(conf, store, host=host, now=NOW)

            self.assertEqual(result['status'], 'UNKNOWN')
            self.assertEqual(result['writes'], 1)
            self.assertLess(events.index('checkpoint'), events.index('admit'))
            self.assertLess(events.index('admit'), events.index('push'))
            self.assertLess(events.index('push'), events.index('dispatch'))

    def test_checkpoint_failure_before_or_after_remote_write_never_admits_or_sends(self):
        for failure in ('before_write', 'lost_ack', 'cas_conflict', 'owner_conflict'):
            with self.subTest(failure=failure), TemporaryDirectory() as tmp:
                conf, store, host, gateway, *_ = platform_fixture(Path(tmp))
                from scripts import phase06_kernel_release as release
                events = []
                transport = gateway
                if failure == 'before_write':
                    def transport(payload):
                        if payload['operation'] == 'checkpoint':
                            raise OSError('private checkpoint unavailable')
                        return gateway(payload)
                    host.checkpoint.transport = transport
                elif failure == 'lost_ack':
                    gateway.lose_ack = True
                elif failure == 'cas_conflict':
                    def transport(payload):
                        if payload['operation'] == 'checkpoint':
                            gateway.value['revision'] += 1
                        return gateway(payload)
                    host.checkpoint.transport = transport
                else:
                    def transport(payload):
                        if payload['operation'] == 'checkpoint':
                            gateway.value['owner'] = 'other:owner'
                        return gateway(payload)
                    host.checkpoint.transport = transport
                parent = host._git('rev-parse', 'HEAD')
                with patch.dict('os.environ', github_environment(), clear=True), \
                     patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                     patch.object(release, 'admit_owned') as admit, \
                     self.local_cli_boundary(host, events, parent), \
                     self.frozen_now(host):
                    result = run_owned_cycle(conf, store, host=host, now=NOW)
                self.assertEqual(result['writes'], 0)
                self.assertEqual(result['status'], 'UNKNOWN')
                admit.assert_not_called()
                self.assertNotIn('push', events)
                self.assertNotIn('dispatch', events)
                record = store.journal.pending_records()[0]
                self.assertEqual(record.expected_parent, parent)
                self.assertFalse(record.dispatch)
                if failure == 'lost_ack':
                    self.assertEqual(gateway.value['revision'], 1)
                    self.assertEqual(record.status, 'DISPATCHING')

    def test_uncertain_reservation_restore_never_sends_same_saved_key(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, gateway, *_ = platform_fixture(Path(tmp))
            from scripts import phase06_kernel_release as release
            parent = host._git('rev-parse', 'HEAD')
            gateway.lose_ack = True
            first_sends = []
            with patch.dict('os.environ', github_environment(), clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                 patch.object(release, 'admit_owned') as admit, \
                 self.local_cli_boundary(host, first_sends, parent), \
                 self.frozen_now(host):
                first = run_owned_cycle(conf, store, host=host, now=NOW)
            self.assertEqual(first['writes'], 0)
            admit.assert_not_called()
            self.assertEqual(first_sends, [])
            old = store.journal.pending_records()[0]
            self.assertEqual(old.expected_parent, parent)
            gateway.value['owner'] = None  # test-only lease expiry; never a production reset
            checkpoint = PrivateCheckpoint(gateway, run_id='123', run_attempt='1')
            db_path = checkpoint.acquire(Path(tmp) / 'restored-private-scratch')
            restored = CycleStore(db_path.parent)
            from manager_core.owned_platform_host import GitHubActionsCycleHost
            resumed = GitHubActionsCycleHost(checkpoint, host.checkout, host.source_audit_path)
            import manager_core.owned_public_collector as collector
            events = []
            resumed_sends = []
            with patch.dict('os.environ', github_environment(), clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                 patch.object(release, 'admit_owned') as next_admit, \
                 patch.object(collector, 'collect_owned_occurrence', side_effect=lambda key, journal: events.append(key)), \
                 self.local_cli_boundary(resumed, resumed_sends, parent), \
                 self.frozen_now(resumed):
                second = run_owned_cycle(conf, restored, host=resumed, now=NOW)
            current = restored.journal.pending_records()[0]
            self.assertEqual(second['status'], 'UNKNOWN')
            self.assertEqual(events, [old.key])
            self.assertEqual(current.key, old.key)
            self.assertEqual(current.packet_json, old.packet_json)
            self.assertEqual(current.expected_parent, old.expected_parent)
            self.assertFalse(current.dispatch)
            admit.assert_not_called()
            next_admit.assert_not_called()
            self.assertEqual(resumed_sends, [])

    def test_sent_occurrence_with_lost_checkpoint_ack_restores_without_retry_or_rollback(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, gateway, *_prefix, pages = platform_fixture(Path(tmp))
            from scripts import phase06_kernel_release as release
            import manager_core.owned_public_collector as collector
            parent = host._git('rev-parse', 'HEAD')
            events = []
            actual_send = host.send_owned

            def sent_then_crashed(*args, **kwargs):
                actual_send(*args, **kwargs)
                events.append('crash_after_send')
                raise RuntimeError('simulated process loss before occurrence reconciliation')

            host.send_owned = sent_then_crashed
            with patch.dict('os.environ', github_environment(), clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                 self.local_cli_boundary(host, events, parent), \
                 self.frozen_now(host):
                first = run_owned_cycle(conf, store, host=host, now=NOW)

            self.assertEqual(first['status'], 'UNKNOWN')
            self.assertIn('push', events)
            self.assertIn('dispatch', events)
            self.assertLess(events.index('push'), events.index('dispatch'))
            self.assertEqual(events.count('push'), 1)
            self.assertEqual(events.count('dispatch'), 1)
            saved = store.journal.pending_records()[0]
            self.assertEqual(saved.status, 'DISPATCHING')
            self.assertEqual(saved.expected_parent, parent)
            self.assertFalse(saved.dispatch)
            sent_commit = host._git('rev-parse', 'HEAD')
            self.assertNotEqual(sent_commit, parent)

            # The caller's post-send checkpoint is written remotely but its
            # response is lost. The next owner must restore and reconcile the
            # original packet, with no candidate/send authority.
            gateway.lose_ack = True
            from manager_core.owned_checkpoint import CheckpointUnavailable
            with self.assertRaises(CheckpointUnavailable):
                host.checkpoint.save()
            self.assertEqual(gateway.value['revision'], 2)
            gateway.value['owner'] = None  # fixture lease expiry; never a production reset
            checkpoint = PrivateCheckpoint(gateway, run_id='123', run_attempt='1')
            db_path = checkpoint.acquire(Path(tmp) / 'restored-private-scratch')
            restored = CycleStore(db_path.parent)
            from manager_core.owned_platform_host import GitHubActionsCycleHost
            resumed = GitHubActionsCycleHost(checkpoint, host.checkout, host.source_audit_path)
            old = restored.journal.pending_records()[0]
            occurrence_keys = []
            delivery_keys = []
            resumed_events = []

            def saved_occurrence(key, journal):
                occurrence_keys.append(key)
                return pages.evidence(sent_commit)

            def lagging_delivery(key, journal):
                delivery_keys.append(key)
                record = journal.record(key)
                packet = json.loads(record.packet_json)
                return dict(status='PENDING', effect_key=key,
                            receipt_ref=record.receipt_ref,
                            candidate_sha256=packet['candidate_sha256'],
                            observed_at=NOW.isoformat(),
                            proof_ref='https://daisuke134.github.io/life-manager/manager-support/',
                            proof_level='P0', reason='PAGES_DEPLOYMENT_LAG',
                            human_outcome='NOT_MEASURED')

            with patch.dict('os.environ', github_environment(), clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                 patch.object(collector, 'collect_owned_occurrence', side_effect=saved_occurrence), \
                 patch.object(collector, 'collect_owned_delivery', side_effect=lagging_delivery), \
                 patch.object(resumed, 'observe_current_delivery', return_value=None), \
                 patch.object(resumed, 'prepare_candidate', wraps=resumed.prepare_candidate) as prepare, \
                 patch.object(release, 'admit_owned') as next_admit, \
                 self.local_cli_boundary(resumed, resumed_events, sent_commit), \
                 self.frozen_now(resumed):
                second = run_owned_cycle(conf, restored, host=resumed, now=NOW)

            reconciled = restored.journal.record(old.key)
            self.assertEqual(second['status'], 'UNKNOWN')
            self.assertEqual(second['writes'], 0)
            self.assertEqual(occurrence_keys, [old.key])
            self.assertEqual(delivery_keys, [old.key])
            self.assertEqual(reconciled.packet_json, old.packet_json)
            self.assertEqual(reconciled.expected_parent, parent)
            self.assertEqual(reconciled.status, 'PRESENT')
            self.assertEqual(reconciled.receipt_ref, sent_commit)
            self.assertFalse(reconciled.dispatch)
            self.assertEqual(restored.journal.delivery_record(old.key)['status'], 'PENDING')
            self.assertEqual(resumed_events, [])
            prepare.assert_not_called()
            next_admit.assert_not_called()
            self.assertEqual(restored.cycle_count(), 0)
            self.assertFalse(restored.stopped())
            self.assertEqual(resumed._git('rev-parse', 'HEAD'), sent_commit)

    def test_old_rows_are_reconciled_before_stop_due_scope_or_candidate_gates(self):
        scenarios = ('stopped', 'not_due', 'revoked_scope', 'absent_candidate')
        for scenario in scenarios:
            with self.subTest(scenario=scenario), TemporaryDirectory() as tmp:
                conf, store, host, *_ = platform_fixture(Path(tmp))
                from scripts import phase06_kernel_release as release
                import manager_core.owned_public_collector as collector
                packet = prepare_owned_change(host.context, host.assessment, host.scope, NOW,
                                              schema='manager.digital-handoff.v2').packet
                baseline = host.manifest()
                context = __import__('manager_core.digital_handoff', fromlist=['PublisherContext']).PublisherContext(
                    REPOSITORY, MAIN_REF, WORKFLOW, packet['candidate']['source_commit'],
                    '123', workflow_commit=packet['candidate']['source_commit'])
                parent = host._git('rev-parse', 'HEAD')
                store.journal.reserve(packet, context, baseline, packet['candidate'], parent, NOW)
                host.checkpoint.save()
                if scenario == 'stopped':
                    store.stop()
                elif scenario == 'not_due':
                    self.assertTrue(store.due(conf, NOW))
                elif scenario == 'revoked_scope':
                    host.scope = replace(host.scope, revoked=True)
                elif scenario == 'absent_candidate':
                    host.context = host.assessment = host.scope = None
                    host.source_audit_path = Path(tmp) / 'missing-source-audit.json'
                with patch.dict('os.environ', github_environment(), clear=True), \
                     patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                     patch.object(collector, 'collect_owned_occurrence', return_value=None) as occurrence, \
                     patch.object(host, 'prepare_candidate', wraps=host.prepare_candidate) as prepare, \
                     patch.object(release, 'admit_owned') as admit, \
                     self.frozen_now(host):
                    result = run_owned_cycle(conf, store, host=host, now=NOW)
                self.assertEqual(result['status'], 'UNKNOWN')
                occurrence.assert_called_once()
                self.assertEqual(occurrence.call_args.args[0], packet['effect_key'])
                prepare.assert_not_called()
                admit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
