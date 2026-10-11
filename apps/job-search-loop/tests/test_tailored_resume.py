import importlib
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
