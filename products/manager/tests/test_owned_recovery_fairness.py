"""Read-only recovery must visit later records despite earlier UNKNOWN rows.

PRESENT rows below are synthetic selector fixtures, not provider proof.
"""
from datetime import datetime, timezone
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_digital_cycle_acceptance as fixtures
from test_candidate_verification import NOW
from manager_core.digital_handoff import PublisherContext, REPOSITORY, SOURCE_REF, WORKFLOW, plan_release
from manager_core.owned_cycle import run_owned_cycle, _recover_owned_deliveries
from manager_core.owned_public_collector import DeliveryObservation
from manager_core.reconcile import reconcile_pending_owned


class RecoveryFairnessTests(unittest.TestCase):
    def reserve_many(self, store, host, git, count):
        baseline = host.manifest()
        candidate = json.loads((host.context.candidate_bundle / 'manifest.json').read_text())
        keys = []
        for n in range(count):
            other = dict(candidate, source_commit=f'{n + 1:040x}')
            packet = plan_release(baseline, other, NOW)
            context = PublisherContext(REPOSITORY, SOURCE_REF, WORKFLOW, other['source_commit'], '1')
            store.journal.reserve(packet, context, baseline, other, git.parent, NOW)
            keys.append(packet['effect_key'])
        return sorted(keys)

    def test_unknown_first_batch_does_not_starve_later_occurrences(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
            keys = self.reserve_many(store, host, git, 102)
            seen = []
            def read(key):
                seen.append(key)
                return None
            for _ in range(2):
                reconcile_pending_owned(store.journal, read, datetime.now(timezone.utc))
            self.assertEqual(set(seen), set(keys))
            self.assertLessEqual(len(seen), 200)
            self.assertEqual(len(store.journal.pending_records()), 100)

    def test_unknown_deliveries_do_not_starve_tail_even_while_stopped(self):
        for stopped in (False, True):
            with self.subTest(stopped=stopped), TemporaryDirectory() as tmp:
                conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
                keys = self.reserve_many(store, host, git, 102)
                for key in keys: store.journal._present(key, 'd' * 40)
                if stopped: store.stop()
                seen = []
                def observe(packet, receipt):
                    key = packet['effect_key']; seen.append(key)
                    return DeliveryObservation('VERIFIED' if key in keys[-2:] else 'UNKNOWN',
                                               'SYNTHETIC_SELECTOR_FIXTURE', 'fixture-only')
                with patch.object(host, 'observe_delivery', side_effect=observe), \
                        patch.object(host, 'rollback', wraps=host.rollback) as rollback:
                    for _ in range(2): _recover_owned_deliveries(store, host, NOW)
                    rollback.assert_not_called()
                self.assertEqual(set(seen), set(keys))
                for key in keys[-2:]:
                    self.assertEqual(store.journal.delivery_record(key)['status'], 'VERIFIED')
                self.assertTrue(store.journal.pending_deliveries(limit=1))

    def test_unknown_occurrence_blocks_writes_but_not_other_delivery_reads(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
            keys = self.reserve_many(store, host, git, 2)
            store.journal._present(keys[1], 'd' * 40)
            observation = DeliveryObservation('VERIFIED', 'SYNTHETIC_SELECTOR_FIXTURE', 'fixture-only')
            with patch.object(host, 'observe_delivery', return_value=observation) as reader, \
                    patch.object(host, 'send', wraps=host.send) as send:
                result = run_owned_cycle(conf, store, host=host, now=NOW)
                self.assertEqual(result['status'], 'UNKNOWN')
                self.assertEqual(result['writes'], 0)
                send.assert_not_called()
                reader.assert_called_once()
            self.assertEqual(store.journal.delivery_record(keys[1])['status'], 'VERIFIED')
