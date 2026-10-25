"""Exact provider collection and lag-safe delivery recovery, offline transport."""
from datetime import datetime, timedelta, timezone
import importlib
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_digital_cycle_acceptance as fixtures
import test_owned_effect_recovery as recovery
from test_candidate_verification import NOW
from manager_core.digital_handoff import REPOSITORY, PUBLIC_BASE
from manager_core.owned_cycle import run_owned_cycle
from manager_core.reconcile import reconcile_owned


class PublicCollectorTests(unittest.TestCase):
    def provider_fixture(self, tmp):
        packet, git, journal, context = recovery.OwnedRecoveryTests().prepare(tmp)
        journal.reserve(packet, context, packet['baseline'], packet['candidate'], git.parent, NOW)
        sha = git.send(git.parent)
        evidence = git.evidence(sha)
        urls = {f'https://api.github.com/repos/{REPOSITORY}/commits/{sha}':
                json.dumps(evidence.receipt).encode()}
        for commit, bodies in [(sha, evidence.committed_bodies),
                               (git.parent, evidence.parent_bodies)]:
            for name, raw in bodies.items():
                urls[f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}/manager-support/{name}'] = raw
        def get(url):
            self.assertIn(url, urls, 'collector may only use expected fixed URLs')
            return urls[url]
        return packet, git, journal, sha, urls, get

    def test_delivery_verifies_bytes_but_timeout_or_old_version_stays_unknown(self):
        collector = importlib.import_module('manager_core.owned_public_collector')
        for state in ('current', 'old', 'timeout'):
            with self.subTest(state=state), TemporaryDirectory() as tmp:
                packet, git, journal, sha, urls, get = self.provider_fixture(tmp)
                at = datetime.now(timezone.utc) + timedelta(seconds=1)
                reconcile_owned(journal, packet['effect_key'], lambda _: git.evidence(sha), at)
                evidence = git.evidence(sha)
                bodies = evidence.parent_bodies if state == 'old' else evidence.committed_bodies
                for name, raw in bodies.items(): urls[PUBLIC_BASE + name] = raw
                def read(url):
                    if state == 'timeout': raise TimeoutError('fixture HTTP timeout')
                    return get(url)
                result = collector.collect_owned_delivery(packet['effect_key'], journal, at, get=read)
                expected = {'current': 'VERIFIED', 'old': 'PENDING', 'timeout': 'UNKNOWN'}[state]
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['receipt_ref'], sha)
                self.assertEqual(result['proof_level'], 'P0')
                journal.save_delivery(packet['effect_key'], result)
                self.assertEqual(journal.delivery_record(packet['effect_key'])['status'], expected)
                wrong = dict(result, receipt_ref='f' * 40)
                with self.assertRaises(ValueError): journal.save_delivery(packet['effect_key'], wrong)

    def test_occurrence_pagination_collects_saved_packet_and_all_immutable_bytes(self):
        collector = importlib.import_module('manager_core.owned_public_collector')
        with TemporaryDirectory() as tmp:
            packet, git, journal, sha, urls, get = self.provider_fixture(tmp)
            list_url = f'https://api.github.com/repos/{REPOSITORY}/commits?sha=gh-pages&per_page=100&page='
            urls[list_url + '1'] = json.dumps([{'sha': 'f' * 40, 'commit': {'message': 'unrelated'}}] * 100).encode()
            urls[list_url + '2'] = json.dumps([json.loads(urls[f'https://api.github.com/repos/{REPOSITORY}/commits/{sha}'])]).encode()
            at = datetime.now(timezone.utc) + timedelta(seconds=1)
            result = collector.collect_owned_occurrence(packet['effect_key'], journal, at, get=get)
            self.assertIsNotNone(result)
            self.assertEqual(result.receipt['sha'], sha)
            self.assertEqual(result.parent_commit, git.parent)
            self.assertEqual(len(result.committed_bodies), 7)
            # Transport injection is a fixture, not authenticated public proof.
            self.assertNotEqual(journal.record(packet['effect_key']).status, 'PRESENT')

    def test_wrong_parent_or_partial_immutable_body_never_closes_occurrence(self):
        collector = importlib.import_module('manager_core.owned_public_collector')
        for bad in ('parent', 'body', 'message', 'repository'):
            with self.subTest(bad=bad), TemporaryDirectory() as tmp:
                packet, git, journal, sha, urls, get = self.provider_fixture(tmp)
                receipt_url = f'https://api.github.com/repos/{REPOSITORY}/commits/{sha}'
                receipt = json.loads(urls[receipt_url])
                if bad == 'parent': receipt['parents'][0]['sha'] = 'f' * 40
                if bad == 'message': receipt['commit']['message'] += ' sibling'
                if bad == 'repository': receipt['html_url'] = f'https://github.com/other/repo/commit/{sha}'
                urls[receipt_url] = json.dumps(receipt).encode()
                urls[f'https://api.github.com/repos/{REPOSITORY}/commits?sha=gh-pages&per_page=100&page=1'] = json.dumps([receipt]).encode()
                if bad == 'body':
                    url = f'https://raw.githubusercontent.com/{REPOSITORY}/{sha}/manager-support/finance.html'
                    urls[url] = urls[url][:10]
                self.assertIsNone(collector.collect_owned_occurrence(packet['effect_key'], journal,
                    datetime.now(timezone.utc) + timedelta(seconds=1), get=get))
                self.assertNotEqual(journal.record(packet['effect_key']).status, 'PRESENT')

    def test_delivery_lag_or_missing_file_does_not_rollback(self):
        for failure in ('lag', 'missing', 'hash_only'):
            with self.subTest(failure=failure), TemporaryDirectory() as tmp:
                conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
                real_send = host.send
                def delayed(*args):
                    sha = real_send(*args)
                    if failure == 'lag':
                        for path in host.context.baseline_bundle.iterdir():
                            (host.served / path.name).write_bytes(path.read_bytes())
                    elif failure == 'missing': (host.served / 'finance.html').unlink()
                    else:
                        path = host.served / 'finance.html'
                        path.write_bytes(path.read_bytes() + b'\n')
                    return sha
                with patch.object(host, 'send', side_effect=delayed) as send, \
                        patch.object(host, 'rollback', wraps=host.rollback) as rollback:
                    first = run_owned_cycle(conf, store, host=host, now=NOW)
                    self.assertEqual(first['status'], 'UNKNOWN')
                    self.assertEqual(first.get('rollback_writes'), 0)
                    rollback.assert_not_called()
                    self.assertFalse(store.stopped())
                    # Readback resumes before cadence; it must not republish.
                    host._publish_fixture(git.git('rev-parse', 'HEAD'))
                    run_owned_cycle(conf, store, host=host, now=NOW)
                    self.assertEqual(send.call_count, 1)
                    self.assertEqual(store.journal.delivery_record(first['effect_key'])['status'], 'VERIFIED')

    def test_confirmed_regression_rolls_back_once_with_exact_target(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
            host.regress_served = True
            with patch.object(host, 'rollback', wraps=host.rollback) as rollback:
                self.assertEqual(run_owned_cycle(conf, store, host=host, now=NOW)['status'],
                                 'ROLLED_BACK_SANDBOX_REGRESSION')
                self.assertEqual(run_owned_cycle(conf, store, host=host, now=NOW)['status'], 'STOPPED_REGRESSION')
                self.assertEqual(rollback.call_count, 1)

    def test_sibling_target_advance_does_not_authorize_rollback(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
            host.regress_served = True
            real_send = host.send
            def moved_target(*args):
                sha = real_send(*args)
                (host.checkout / 'unrelated.html').write_text('another owner advanced target')
                git.git('add', 'unrelated.html'); git.git('commit', '-qm', 'independent target advance')
                return sha
            with patch.object(host, 'send', side_effect=moved_target), \
                    patch.object(host, 'rollback', wraps=host.rollback) as rollback:
                result = run_owned_cycle(conf, store, host=host, now=NOW)
                self.assertEqual(result['status'], 'UNKNOWN')
                self.assertEqual(result.get('rollback_writes'), 0)
                rollback.assert_not_called()
                self.assertEqual(git.git('rev-list', '--count', 'HEAD'), '3')
