import importlib
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from job_search_loop.browser_agent.candidate_memory import CandidateMemoryView

try:
    tailoring = importlib.import_module('job_search_loop.tailored_resume')
except ModuleNotFoundError:
    tailoring = None


class TailoredResumeTests(unittest.TestCase):
    def memory(self):
        return CandidateMemoryView({'schema_version': 1, 'concepts': [
            {'concept': 'candidate.name', 'value': 'Fixture Candidate'},
            {'concept': 'candidate.application_email', 'value': 'fixture@example.test'},
            {'concept': 'fact.role', 'value': 'Built approved production systems at Example.'},
            {'concept': 'fact.project', 'value': 'Improved a verified workflow by 20%.'},
        ]})

    def test_tailoring_tool_exists(self):
        self.assertIsNotNone(tailoring, 'company-specific resume connection is missing')

    @unittest.skipIf(tailoring is None, 'tool is absent')
    def test_parent_symlink_cannot_redirect_a_private_resume(self):
        row = {'application_id': 'job-a', 'company': 'Example', 'title': 'Engineer', 'canonical_url': 'https://example.test/jobs/a'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'materials'
            outside = Path(directory) / 'outside'
            root.mkdir()
            outside.mkdir()
            (root / 'tailored').symlink_to(outside, target_is_directory=True)
            material = tailoring.compose(row, self.memory(), {'Experience': ['fact.role']})
            with self.assertRaisesRegex(ValueError, 'unsafe_resume_directory'):
                tailoring.store_artifact(root, row, material, b'%PDF-1.4 fixture')
            self.assertEqual(list(outside.iterdir()), [])

    @unittest.skipIf(tailoring is None, 'tool is absent')
    def test_only_existing_facts_can_enter_company_resume(self):
        row = {'application_id': 'job-a', 'company': 'Example <AI>', 'title': 'Engineer', 'canonical_url': 'https://example.test/jobs/a'}
        result = tailoring.compose(row, self.memory(), {'Experience': ['fact.role'], 'Projects': ['fact.project']})
        self.assertIn('Built approved production systems at Example.', result['html'])
        self.assertIn('Example &lt;AI&gt;', result['html'])
        self.assertEqual(result['fact_ids'], ['fact.role', 'fact.project'])
        with self.assertRaisesRegex(ValueError, 'unknown_fact_id'):
            tailoring.compose(row, self.memory(), {'Experience': ['fact.invented']})
        with self.assertRaisesRegex(ValueError, 'invalid_section'):
            tailoring.compose(row, self.memory(), {'Invented CEO role': ['fact.role']})

    @unittest.skipIf(tailoring is None, 'tool is absent')
    def test_artifact_is_bound_to_exact_job_and_hash(self):
        row = {'application_id': 'job-a', 'company': 'Example', 'title': 'Engineer', 'canonical_url': 'https://example.test/jobs/a'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            material = tailoring.compose(row, self.memory(), {'Experience': ['fact.role']})
            tailoring.store_artifact(root, row, material, b'%PDF-1.4 fixture')
            routed = tailoring.load_artifact(root, row, self.memory())
            self.assertEqual(routed['resume_variant'], 'company_tailored')
            self.assertTrue(Path(routed['resume_path']).is_file())
            self.assertIsNone(tailoring.load_artifact(root, {**row, 'application_id': 'job-b'}, self.memory()))
            with self.assertRaisesRegex(ValueError, 'target_binding_mismatch'):
                tailoring.load_artifact(root, {**row, 'company': 'Different'}, self.memory())
            Path(routed['resume_path']).write_bytes(b'changed PDF')
            with self.assertRaisesRegex(ValueError, 'resume_hash_mismatch'):
                tailoring.load_artifact(root, row, self.memory())


class CapturedResumeRoutingTests(unittest.TestCase):
    def test_english_form_cannot_change_the_captured_japanese_variant(self):
        from unittest.mock import Mock, patch
        from job_search_loop.browser_agent import runtime
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = {name: name + '.pdf' for name in ('engineering', 'technical_business', 'japanese')}
            for name, filename in values.items():
                (root / filename).write_bytes(('%PDF-1.4 ' + name).encode())
            (root / 'manifest.v1.json').write_text(json.dumps({'version': 1, 'resumes': values}))
            expected = hashlib.sha256((root / 'japanese.pdf').read_bytes()).hexdigest()
            ledger = Mock()
            ledger.strategy_assignment.return_value = {'capture_status': 'captured', 'material_variant': 'japanese',
                'material_sha256': expected, 'role_family': 'applied_ai'}
            memory = CandidateMemoryView({'schema_version': 1, 'concepts': []})
            row = {'application_id': 'fixture-id', 'company': 'Fixture', 'title': 'AI Engineer',
                'canonical_url': 'https://jobs.ashbyhq.com/fixture/job'}
            with patch.object(runtime, 'Ledger', return_value=ledger), patch.object(runtime, '_path_env', return_value=root), patch.object(runtime, '_materials_root', return_value=root), patch.object(runtime.CandidateMemoryView, 'load', return_value=memory):
                result = runtime._routed_resume(row, 'Application Name Email Resume Submit Application')
            self.assertEqual(result['resume_sha256'], expected)
            self.assertEqual(result['resume_variant'], 'japanese')
