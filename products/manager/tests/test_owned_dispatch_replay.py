"""Engine checkpoints cannot carry a reusable owned-send permission."""
from datetime import timedelta
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_digital_cycle_acceptance as fixtures
from test_candidate_verification import NOW
from manager_core.digital_handoff import prepare_owned_change
from manager_core.owned_cycle import CycleStore, run_owned_cycle
from manager_core import owned_cycle


class DispatchReplayTests(unittest.TestCase):
    def prepare(self, tmp):
        config, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
        packet = prepare_owned_change(host.context, host.assessment, host.scope, NOW).packet
        return config, store, host, git, packet

    def test_valid_packet_can_be_dispatched_after_clock_advances(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git, packet = self.prepare(tmp)
            with patch.object(host, 'send', wraps=host.send) as send:
                result = owned_cycle.dispatch_owned_once(store, host, packet, NOW + timedelta(seconds=1))
                self.assertEqual(result['status'], 'SUBMITTED')
                self.assertEqual(result['writes'], 1)
                send.assert_called_once()

    def test_original_packet_lease_is_not_renewed_by_fresh_preparation(self):
        from dataclasses import replace
        with TemporaryDirectory() as tmp:
            conf, store, host, git, packet = self.prepare(tmp)
            host.scope = replace(host.scope, expires_at=NOW + timedelta(days=1))
            with patch.object(host, 'send', wraps=host.send) as send:
                result = owned_cycle.dispatch_owned_once(store, host, packet,
                                                        NOW + timedelta(hours=6, seconds=1))
                self.assertEqual(result['status'], 'NO_ACTION')
                send.assert_not_called()

    def test_replayed_step_result_cannot_reuse_dispatch_permission(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git, packet = self.prepare(tmp)
            with patch.object(host, 'send', wraps=host.send) as send:
                result = owned_cycle.dispatch_owned_once(store, host, packet, NOW)
                cached = json.loads(json.dumps(result))
                self.assertEqual(cached['writes'], 1)
                self.assertNotIn('dispatch', cached)
                again = owned_cycle.dispatch_owned_once(CycleStore(store.root), host, packet, NOW)
                self.assertEqual(again['writes'], 0)
                self.assertEqual(send.call_count, 1)
                self.assertEqual(git.git('rev-list', '--count', 'HEAD'), '2')

    def test_commit_then_engine_checkpoint_loss_does_not_resend(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git, packet = self.prepare(tmp)
            real_send = host.send
            def crash_after_commit(*args):
                real_send(*args)
                raise SystemExit('process died before engine checkpoint')
            with patch.object(host, 'send', side_effect=crash_after_commit) as send:
                with self.assertRaises(SystemExit):
                    owned_cycle.dispatch_owned_once(store, host, packet, NOW)
                result = owned_cycle.dispatch_owned_once(CycleStore(store.root), host, packet, NOW)
                self.assertEqual(result['status'], 'PRESENT')
                self.assertEqual(result['writes'], 0)
                self.assertEqual(send.call_count, 1)
            self.assertEqual(store.journal.record(packet['effect_key']).receipt_ref,
                             git.git('rev-parse', 'HEAD'))

    def test_engine_dedup_expiry_does_not_bypass_journal(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git, packet = self.prepare(tmp)
            # Fresh caller/no cached engine result, same durable effect journal.
            with patch.object(host, 'send', wraps=host.send) as send:
                owned_cycle.dispatch_owned_once(store, host, packet, NOW)
                for _ in range(3):
                    result = owned_cycle.dispatch_owned_once(CycleStore(store.root), host,
                                                              json.loads(json.dumps(packet)), NOW)
                    self.assertEqual(result['writes'], 0)
                self.assertEqual(send.call_count, 1)

    def test_slot_claim_crash_is_not_completed_effect(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git, packet = self.prepare(tmp)
            self.assertTrue(store.due(conf, NOW))  # process dies before reservation
            restarted = CycleStore(store.root)
            self.assertIsNone(restarted.journal.record(packet['effect_key']))
            self.assertEqual(run_owned_cycle(conf, restarted, host=host, now=NOW)['status'], 'NOT_DUE')
            later = run_owned_cycle(conf, restarted, host=host, now=NOW + timedelta(minutes=1))
            self.assertEqual(later['status'], 'VERIFIED_SANDBOX_TECHNICAL')
            self.assertEqual(later['writes'], 1)

    def test_direct_helper_preserves_scope_and_owner_lock(self):
        from dataclasses import replace
        with TemporaryDirectory() as tmp:
            conf, store, host, git, packet = self.prepare(tmp)
            with store.owner_lock(), patch.object(host, 'send', wraps=host.send) as send:
                result = owned_cycle.dispatch_owned_once(CycleStore(store.root), host, packet, NOW)
                self.assertEqual(result['status'], 'OWNER_BUSY')
                send.assert_not_called()
            host.scope = replace(host.scope, revoked=True)
            with patch.object(host, 'send', wraps=host.send) as send:
                result = owned_cycle.dispatch_owned_once(store, host, packet, NOW)
                self.assertEqual(result['status'], 'NO_ACTION')
                send.assert_not_called()
