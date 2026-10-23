"""Regressions for independently collected immutable release occurrences."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from manager_core.digital_environment import PAGES
from manager_core.digital_handoff import REPOSITORY, PUBLIC_BASE, plan_release, commit_message

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)
PAGES_COMMIT = 'd' * 40
PARENT_COMMIT = 'e' * 40
ROOT = Path(__file__).resolve().parents[1]


def bundle(source, label):
    files = {name: (name + label).encode() for name in PAGES}
    manifest = {'schema': 'manager.public-service.v1', 'source_commit': source,
                'files': {name: sha256(raw).hexdigest() for name, raw in files.items()},
                'beneficiary_outcome': 'NOT_MEASURED', 'real_participants': 0,
                'clinical_claim': False, 'experiment_enabled': False}
    return manifest, {**files, 'manifest.json': (json.dumps(manifest, sort_keys=True) + '\n').encode()}


class EvidenceClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW + timedelta(hours=1)


class ImmutableOccurrenceTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('proof_occurrence', ROOT / 'scripts/phase06_kernel_release.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.before, self.parent_files = bundle('a' * 40, 'old')
        self.after, self.commit_files = bundle('b' * 40, 'new')

    def evidence(self, packet, *, older=False):
        receipt = {'sha': PAGES_COMMIT,
                   'html_url': f'https://github.com/{REPOSITORY}/commit/{PAGES_COMMIT}',
                   'commit': {'message': commit_message(packet), 'committer': {
                       'date': (NOW - timedelta(minutes=1) if older else NOW).isoformat()}},
                   'parents': [{'sha': PARENT_COMMIT}],
                   'files': [{'filename': 'manager-support/' + name, 'status': 'modified'}
                             for name in sorted(self.commit_files)]}
        urls = {f'https://api.github.com/repos/{REPOSITORY}/commits/{PAGES_COMMIT}': json.dumps(receipt).encode()}
        for commit, files in ((PAGES_COMMIT, self.commit_files), (PARENT_COMMIT, self.parent_files)):
            urls.update({f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}/manager-support/{name}': raw
                         for name, raw in files.items()})
        urls.update({PUBLIC_BASE + name: raw for name, raw in self.commit_files.items()})
        return receipt, urls

    def prove(self, packet, urls):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            intent = root / 'intent.json'
            intent.write_text(json.dumps(packet))
            with patch.object(self.module, 'public_get', side_effect=lambda url: urls[url]) as get, \
                 patch.object(self.module, 'datetime', EvidenceClock):
                result = self.module.prove(intent, PAGES_COMMIT, root, NOW)
                return result, {call.args[0] for call in get.call_args_list}

    def test_retry_new_intent_reconciles_earlier_same_effect_without_republishing(self):
        packet = plan_release(self.before, self.after, NOW)
        _, urls = self.evidence(packet, older=True)
        result, reads = self.prove(packet, urls)
        self.assertTrue(result['reconciled_existing_occurrence'])
        self.assertEqual(result['parent_pages_commit'], PARENT_COMMIT)
        self.assertEqual(result['baseline'], self.before)
        self.assertEqual(result['observation_baseline'], self.before)
        self.assertEqual(result['committed_at'], (NOW - timedelta(minutes=1)).isoformat())
        self.assertEqual(reads, set(urls))

    def test_no_action_observation_retains_original_transition_separately(self):
        packet = plan_release(self.after, self.after, NOW)
        _, urls = self.evidence(packet, older=True)
        result, reads = self.prove(packet, urls)
        self.assertEqual(result['baseline'], self.before)
        self.assertEqual(result['observation_baseline'], self.after)
        self.assertEqual(result['changed_pages'], sorted(PAGES))
        self.assertEqual(result['observation_changed_pages'], [])
        self.assertEqual(reads, set(urls))

    def test_live_bytes_cannot_repair_wrong_immutable_commit_bytes(self):
        packet = plan_release(self.before, self.after, NOW)
        _, urls = self.evidence(packet)
        urls[f'https://raw.githubusercontent.com/{REPOSITORY}/{PAGES_COMMIT}/manager-support/finance.html'] = b'wrong committed occurrence'
        with self.assertRaises(ValueError):
            self.prove(packet, urls)

    def test_receipt_file_list_must_equal_actual_parent_to_candidate_diff(self):
        packet = plan_release(self.before, self.after, NOW)
        receipt, urls = self.evidence(packet)
        receipt['files'] = [{'filename': 'manager-support/finance.html', 'status': 'modified'}]
        urls[f'https://api.github.com/repos/{REPOSITORY}/commits/{PAGES_COMMIT}'] = json.dumps(receipt).encode()
        with self.assertRaises(ValueError):
            self.prove(packet, urls)

    def test_unrelated_parent_is_not_the_proposed_baseline(self):
        packet = plan_release(self.before, self.after, NOW)
        _, urls = self.evidence(packet)
        _, unrelated = bundle('c' * 40, 'other')
        for name, raw in unrelated.items():
            urls[f'https://raw.githubusercontent.com/{REPOSITORY}/{PARENT_COMMIT}/manager-support/{name}'] = raw
        with self.assertRaises(ValueError):
            self.prove(packet, urls)

    def test_returned_commit_must_match_the_requested_immutable_sha(self):
        packet = plan_release(self.before, self.after, NOW)
        receipt, urls = self.evidence(packet)
        receipt['sha'] = 'f' * 40
        receipt['html_url'] = f'https://github.com/{REPOSITORY}/commit/' + 'f' * 40
        urls[f'https://api.github.com/repos/{REPOSITORY}/commits/{PAGES_COMMIT}'] = json.dumps(receipt).encode()
        with self.assertRaises(ValueError):
            self.prove(packet, urls)


if __name__ == '__main__':
    unittest.main()
