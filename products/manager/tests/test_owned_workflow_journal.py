"""Workflow dispatch intents are durably fenced before the HTTP side effect."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import timedelta
import json
import sqlite3
import unittest

from manager_core.digital_handoff import (
    MAIN_SOURCE_REF, PublisherContext, REPOSITORY, WORKFLOW, prepare_owned_change,
)
from manager_core.owned_platform_host import (
    WorkflowDispatchResult,
    WorkflowRunObservation,
    create_owned_workflow_request,
    reconcile_reserved_owned_workflow,
    submit_reserved_owned_workflow,
)
from manager_core.outbox import OwnedEffectJournal
from test_candidate_verification import NOW


class OwnedWorkflowJournalTests(unittest.TestCase):
    def prepare(self, root):
        from test_digital_cycle_acceptance import CycleAcceptanceTests
        _, _, host, _ = CycleAcceptanceTests().prepare(root)
        prepared = prepare_owned_change(host.context, host.assessment, host.scope, NOW,
                                       source_ref=MAIN_SOURCE_REF)
        packet = prepared.packet
        context = PublisherContext(REPOSITORY, MAIN_SOURCE_REF, WORKFLOW,
                                  packet['candidate']['source_commit'], '12345')
        parent = host.git('rev-parse', 'HEAD')
        owner_id = 'fixture-owner'
        request = create_owned_workflow_request(packet, owner_id, parent)
        journal = OwnedEffectJournal(Path(root) / 'owner.sqlite')
        return host, packet, context, parent, owner_id, request, journal

    def test_main_effect_and_request_are_atomically_reserved_before_send(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            reserved = journal.reserve(packet, context, packet['baseline'], packet['candidate'],
                                       parent, NOW, workflow_request=request, owner_id=owner_id)
            self.assertTrue(reserved.dispatch)
            record = journal.workflow_dispatch_record(request.request_id)
            self.assertEqual(record.status, 'READY')
            self.assertEqual(record.effect_key, packet['effect_key'])
            self.assertEqual(journal.pending_workflow_dispatches(), (record,))
            with sqlite3.connect(journal.path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM owned_effects').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM owned_workflow_dispatches').fetchone()[0], 1)

    def test_main_effect_becomes_dispatched_only_after_workflow_claim(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent, NOW,
                            workflow_request=request, owner_id=owner_id)
            self.assertEqual(journal.record(packet['effect_key']).status, 'RESERVED')
            _, claimed = journal.claim_workflow_dispatch(
                request.request_id, now=NOW + timedelta(hours=1))
            self.assertTrue(claimed)
            self.assertEqual(journal.record(packet['effect_key']).status, 'DISPATCHING')

    def test_expired_ready_request_is_atomically_fenced_for_read_only_recovery(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent, NOW,
                            workflow_request=request, owner_id=owner_id)

            expired, claimed = journal.claim_workflow_dispatch(
                request.request_id, now=NOW + timedelta(hours=6))

            self.assertFalse(claimed)
            self.assertEqual(expired.status, 'EXPIRED')
            self.assertEqual(journal.record(packet['effect_key']).status, 'RESERVED')
            self.assertEqual(journal.pending_workflow_dispatches(), ())
            self.assertEqual(
                tuple(row.key for row in journal.pending_records(limit=10)),
                (packet['effect_key'],),
            )

    def test_main_effect_cannot_be_reserved_for_dispatch_without_request(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            with self.assertRaises(PermissionError):
                journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent, NOW)
            self.assertIsNone(journal.record(packet['effect_key']))
            self.assertEqual(journal.pending_workflow_dispatches(), ())

    def test_send_claim_is_one_shot_across_restart_and_unknown_is_reconciled(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent, NOW,
                            workflow_request=request, owner_id=owner_id)
            first, claimed = journal.claim_workflow_dispatch(
                request.request_id, now=NOW + timedelta(hours=1))
            self.assertTrue(claimed)
            self.assertEqual(first.status, 'SENDING')
            restarted = OwnedEffectJournal(journal.path)
            second, claimed_again = restarted.claim_workflow_dispatch(
                request.request_id, now=NOW + timedelta(hours=1))
            self.assertFalse(claimed_again)
            self.assertEqual(second.status, 'SENDING')

            unknown = WorkflowDispatchResult('UNKNOWN', request.request_id, None)
            restarted.save_workflow_dispatch_result(unknown)
            observation = WorkflowRunObservation('UNKNOWN', request.request_id)
            saved = restarted.save_workflow_run_observation(observation)
            self.assertEqual(saved.status, 'UNKNOWN')
            _, claimed_after_unknown = restarted.claim_workflow_dispatch(
                request.request_id, now=NOW + timedelta(hours=1))
            self.assertFalse(claimed_after_unknown)

    def test_run_readback_and_validated_occurrence_advance_without_resending(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent, NOW,
                            workflow_request=request, owner_id=owner_id)
            journal.claim_workflow_dispatch(
                request.request_id, now=NOW + timedelta(hours=1))
            journal.save_workflow_dispatch_result(
                WorkflowDispatchResult('ACCEPTED', request.request_id, 204))
            found = WorkflowRunObservation('FOUND', request.request_id, 12345,
                                           'completed', 'success',
                                           'https://github.com/Daisuke134/life-manager/actions/runs/12345', 1)
            saved = journal.save_workflow_run_observation(found)
            self.assertEqual(saved.status, 'RUN_FOUND')
            self.assertEqual(saved.conclusion, 'success')
            journal._present(packet['effect_key'], 'c' * 40)
            completed = journal.workflow_dispatch_record(request.request_id)
            self.assertEqual(completed.status, 'PRESENT')
            self.assertEqual(completed.provider_commit, 'c' * 40)
            self.assertEqual(journal.pending_workflow_dispatches(), ())

    def test_observed_duplicate_run_is_sticky_until_provider_occurrence_is_reconciled(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent, NOW,
                            workflow_request=request, owner_id=owner_id)
            journal.claim_workflow_dispatch(
                request.request_id, now=NOW + timedelta(hours=1))
            journal.save_workflow_dispatch_result(
                WorkflowDispatchResult('ACCEPTED', request.request_id, 204))
            duplicate = WorkflowRunObservation('DUPLICATE', request.request_id, matching_runs=2)
            journal.save_workflow_run_observation(duplicate)

            later_single = WorkflowRunObservation(
                'FOUND', request.request_id, 12345, 'completed', 'success',
                'https://github.com/Daisuke134/life-manager/actions/runs/12345', 1)
            record = journal.save_workflow_run_observation(later_single)
            self.assertEqual(record.status, 'RUN_DUPLICATE')

    def test_submission_returns_claim_race_readback_instead_of_stale_ready(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent, NOW,
                            workflow_request=request, owner_id=owner_id)
            real_claim = journal.claim_workflow_dispatch

            def concurrent_worker_won(request_id, *, now=None):
                claimed, did_claim = real_claim(request_id, now=now)
                self.assertTrue(did_claim)
                accepted = journal.save_workflow_dispatch_result(
                    WorkflowDispatchResult('ACCEPTED', request_id, 204))
                self.assertEqual(accepted.status, 'ACCEPTED')
                return accepted, False

            journal.claim_workflow_dispatch = concurrent_worker_won
            calls = []
            result = submit_reserved_owned_workflow(
                journal, request, token='fixture-token',
                now=NOW + timedelta(hours=1),
                post=lambda *args: calls.append(args) or 204)
            self.assertEqual(result.status, 'ACCEPTED')
            self.assertFalse(result.sent)
            self.assertEqual(calls, [])

    def test_existing_workflow_run_is_reconciled_before_dispatch(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent, NOW,
                            workflow_request=request, owner_id=owner_id)
            run = {
                'id': 12345,
                'status': 'in_progress',
                'conclusion': None,
                'head_sha': request.source_commit,
                'head_branch': 'main',
                'event': 'workflow_dispatch',
                'display_title': 'Manager owned request ' + request.request_id,
                'html_url': 'https://github.com/Daisuke134/life-manager/actions/runs/12345',
            }
            posts = []
            result = reconcile_reserved_owned_workflow(
                journal, request.request_id, token='fixture-token',
                now=NOW + timedelta(hours=1),
                get=lambda *args: (200, json.dumps({'workflow_runs': [run]}).encode()),
                post=lambda *args: posts.append(args) or 204)
            self.assertEqual(result.status, 'RUN_FOUND')
            self.assertEqual(result.run_status, 'in_progress')
            self.assertFalse(result.sent)
            self.assertEqual(posts, [])
            self.assertEqual(journal.record(packet['effect_key']).status, 'DISPATCHING')

    def test_ambiguous_dispatch_is_read_only_on_the_next_wake(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent, NOW,
                            workflow_request=request, owner_id=owner_id)
            posts = []
            gets = []

            def get(*args):
                gets.append(args)
                return 200, b'{"workflow_runs": []}'

            def post(*args):
                posts.append(args)
                raise TimeoutError('fixture response lost')

            first = reconcile_reserved_owned_workflow(
                journal, request.request_id, token='fixture-token', now=NOW + timedelta(hours=1),
                get=get, post=post)
            second = reconcile_reserved_owned_workflow(
                journal, request.request_id, token='fixture-token', now=NOW + timedelta(hours=1),
                get=get, post=post)
            self.assertEqual(first.status, 'UNKNOWN')
            self.assertTrue(first.sent)
            self.assertEqual(second.status, 'UNKNOWN')
            self.assertFalse(second.sent)
            self.assertEqual(len(posts), 1)
            self.assertEqual(len(gets), 3)

    def test_accepted_dispatch_is_correlated_to_the_exact_run(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent, NOW,
                            workflow_request=request, owner_id=owner_id)
            run = {
                'id': 98765,
                'status': 'queued',
                'conclusion': None,
                'head_sha': request.source_commit,
                'head_branch': 'main',
                'event': 'workflow_dispatch',
                'display_title': 'Manager owned request ' + request.request_id,
                'html_url': 'https://github.com/Daisuke134/life-manager/actions/runs/98765',
            }
            gets = []
            posts = []

            def get(*args):
                gets.append(args)
                raw = {'workflow_runs': []} if len(gets) == 1 else {'workflow_runs': [run]}
                return 200, json.dumps(raw).encode()

            result = reconcile_reserved_owned_workflow(
                journal, request.request_id, token='fixture-token', get=get,
                now=NOW + timedelta(hours=1),
                post=lambda *args: posts.append(args) or 204)
            self.assertEqual(result.status, 'RUN_FOUND')
            self.assertEqual(result.run_id, 98765)
            self.assertTrue(result.sent)
            self.assertEqual(len(posts), 1)
            self.assertEqual(len(gets), 2)

    def test_mismatched_owner_or_parent_leaves_no_dispatch_reservation(self):
        with TemporaryDirectory() as tmp:
            host, packet, context, parent, owner_id, request, journal = self.prepare(Path(tmp))
            for candidate_request, candidate_owner in (
                    (request, 'wrong-owner'),
                    (create_owned_workflow_request(packet, owner_id, 'f' * 40), owner_id)):
                with self.subTest(owner=candidate_owner, parent=candidate_request.expected_parent), \
                        self.assertRaises(PermissionError):
                    journal.reserve(packet, context, packet['baseline'], packet['candidate'], parent,
                                    NOW, workflow_request=candidate_request, owner_id=candidate_owner)
            self.assertIsNone(journal.record(packet['effect_key']))
            self.assertEqual(journal.pending_workflow_dispatches(), ())


if __name__ == '__main__':
    unittest.main()
