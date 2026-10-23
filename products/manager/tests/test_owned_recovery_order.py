"""Prior uncertain effects survive candidate changes, revocation and cadence."""
from dataclasses import replace
from datetime import timedelta
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_digital_cycle_acceptance as fixtures
from test_candidate_verification import NOW
from manager_core.candidate_verification import verify_candidate
from manager_core.digital_handoff import PublisherContext, REPOSITORY, SOURCE_REF, WORKFLOW, plan_release
from manager_core.owned_cycle import CycleStore, run_owned_cycle


class PriorRecoveryTests(unittest.TestCase):
    def uncertain_commit(self, tmp):
        config, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
        send = host.send
        def lose_response(*args):
            send(*args)
            raise OSError('response lost after external commit')
        with patch.object(host, 'send', side_effect=lose_response):
            self.assertEqual(run_owned_cycle(config, store, host=host, now=NOW)['status'], 'UNKNOWN')
        packet = plan_release(host.manifest(), host.manifest(), NOW)
        # The original intent is keyed by candidate identity, not its baseline.
        record = store.journal.record(packet['effect_key'])
        self.assertEqual(record.status, 'DISPATCHING')
        return config, store, host, git, record

    def assert_recovered(self, store, old, git):
        recovered = store.journal.record(old.key)
        self.assertEqual(recovered.status, 'PRESENT')
        self.assertEqual(recovered.receipt_ref, git.git('rev-parse', 'HEAD'))
        self.assertEqual(recovered.packet_json, old.packet_json)
        self.assertEqual(recovered.expected_parent, old.expected_parent)

    def change_candidate(self, host):
        path = host.context.candidate_bundle / 'manifest.json'
        manifest = json.loads(path.read_text())
        old_source = manifest['source_commit']
        manifest['source_commit'] = 'c' * 40
        for name in manifest['files']:
            page = host.context.candidate_bundle / name
            body = page.read_bytes().replace(old_source.encode(), b'c' * 40)
            page.write_bytes(body)
            manifest['files'][name] = sha256(body).hexdigest()
        path.write_text(json.dumps(manifest))
        host.assessment = verify_candidate(host.context.baseline_bundle,
                                          host.context.candidate_bundle, host.context.criteria)
        self.assertEqual(host.assessment.status, 'VERIFIED_TECHNICAL')

    def test_old_unknown_reconciles_before_changed_candidate(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git, old = self.uncertain_commit(tmp)
            self.change_candidate(host)
            # Recovery must use the saved packet's source, not this candidate.
            with patch.object(host, 'send', wraps=host.send) as send:
                run_owned_cycle(conf, CycleStore(store.root), host=host, now=NOW + timedelta(minutes=1))
                send.assert_not_called()
            self.assert_recovered(store, old, git)

    def test_expired_scope_does_not_hide_old_occurrence(self):
        for revoked in (False, True):
            with self.subTest(revoked=revoked), TemporaryDirectory() as tmp:
                conf, store, host, git, old = self.uncertain_commit(tmp)
                host.scope = replace(host.scope, expires_at=NOW, revoked=revoked)
                with patch.object(host, 'send', wraps=host.send) as send:
                    run_owned_cycle(conf, store, host=host, now=NOW + timedelta(minutes=1))
                    send.assert_not_called()
                self.assert_recovered(store, old, git)

    def test_not_due_or_stop_still_allows_read_only_reconcile(self):
        for stopped in (False, True):
            with self.subTest(stopped=stopped), TemporaryDirectory() as tmp:
                conf, store, host, git, old = self.uncertain_commit(tmp)
                if stopped:
                    store.stop()
                with patch.object(host, 'send', wraps=host.send) as send:
                    result = run_owned_cycle(conf, store, host=host, now=NOW)
                    send.assert_not_called()
                self.assertEqual(result['status'], 'STOPPED_REGRESSION' if stopped else 'NOT_DUE')
                self.assert_recovered(store, old, git)

    def test_unresolved_old_key_blocks_changed_candidate_without_dispatch(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
            old_manifest = host.manifest()
            candidate = json.loads((host.context.candidate_bundle / 'manifest.json').read_text())
            packet = plan_release(old_manifest, candidate, NOW)
            context = PublisherContext(REPOSITORY, SOURCE_REF, WORKFLOW, candidate['source_commit'], '1')
            old = store.journal.reserve(packet, context, old_manifest, candidate,
                                        git.git('rev-parse', 'HEAD'), NOW)
            self.change_candidate(host)
            with patch.object(host, 'send', wraps=host.send) as send:
                result = run_owned_cycle(conf, store, host=host, now=NOW)
                send.assert_not_called()
            self.assertEqual(result['status'], 'UNKNOWN')
            self.assertEqual(store.journal.record(old.key).packet_json, old.packet_json)
            self.assertEqual(store.journal.record(old.key).status, 'DISPATCHING')
            self.assertEqual(git.git('rev-list', '--count', 'HEAD'), '1')

    def test_pending_records_are_bounded_ordered_and_paginated(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
            baseline = host.manifest()
            candidate = json.loads((host.context.candidate_bundle / 'manifest.json').read_text())
            for n in range(102):
                other = dict(candidate, source_commit=f'{n + 1:040x}')
                packet = plan_release(baseline, other, NOW)
                context = PublisherContext(REPOSITORY, SOURCE_REF, WORKFLOW, other['source_commit'], '1')
                store.journal.reserve(packet, context, baseline, other, git.git('rev-parse', 'HEAD'), NOW)
            first = store.journal.pending_records()
            self.assertEqual(len(first), 100)
            self.assertEqual([r.key for r in first], sorted(r.key for r in first))
            remaining = store.journal.pending_records(after_key=first[-1].key)
            self.assertEqual(len(remaining), 2)
            self.assertEqual(len({r.key for r in first + remaining}), 102)
            self.assertTrue(all(not r.dispatch for r in first + remaining))
            for limit in (0, 101, True):
                with self.assertRaises(ValueError):
                    store.journal.pending_records(limit=limit)
