import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from job_search_loop.browser_agent import runtime
from job_search_loop.browser_agent.candidate_memory import CandidateMemoryView


class LiveJobObservationTests(unittest.TestCase):
    def test_model_reads_mandatory_requirements_without_private_contact_values(self):
        private = {'candidate.full_name': 'Fixture Person',
                   'candidate.application_email': 'fixture@example.test',
                   'candidate.phone': '+81 90 1234 5678',
                   'candidate.date_of_birth': '1995-04-03',
                   'candidate.mailing_address.address_line_1': '15 Fictional Street'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'memory.json'
            path.write_text(json.dumps({'schema_version': 1, 'concepts': [
                {'concept': k, 'value': v} for k, v in private.items()]}))
            observation = Mock(url='https://jobs.ashbyhq.com/fixture/job', title='Fixture role',
                visible_text='Mandatory: 10 years of experience. US residency required. No sponsorship.\n' + '\n'.join(private.values()) + '\nFIXTURE PERSON 04/03/1995',
                controls=(), validation_text=(), visible_challenges=(), content_sha256='abc')
            with patch.dict(os.environ, {'JOB_SEARCH_CANDIDATE_MEMORY': str(path)}):
                result = runtime._safe_observation(observation, None, 99)
        text = result.get('visible_text', '')
        self.assertIn('10 years of experience', text)
        self.assertIn('No sponsorship', text)
        self.assertNotIn('FIXTURE PERSON', text)
        self.assertNotIn('04/03/1995', text)
        for value in private.values():
            self.assertNotIn(value, text)

    def test_address_fact_stays_resolvable_but_is_not_a_model_claim(self):
        memory = CandidateMemoryView({'schema_version': 1, 'concepts': [
            {'concept': 'fact.profile.mailing_address', 'value': 'Official mailing address: 15 Fictional Street'},
            {'concept': 'fact.experience', 'value': 'Supported deployed AI workflows.'}]})
        self.assertEqual([fact['concept'] for fact in memory.grounding_facts()], ['fact.experience'])
        self.assertEqual(memory.get('fact.profile.mailing_address'), 'Official mailing address: 15 Fictional Street')
