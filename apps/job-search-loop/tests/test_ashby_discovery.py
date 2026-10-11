import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_search_loop.ashby_discovery import discover_one


class AshbyDiscoveryTests(unittest.TestCase):
    def discover(self, root, live, *, excluded=(), max_jobs=4):
        cache = root / 'cache.json'
        cache.write_text(json.dumps({'jobs': [self.job('CachedCo', 'cached')]}))
        profile = root / 'profile.json'
        profile.write_text(json.dumps({'candidate': {'employer_exclusions': list(excluded)}}))
        materials = root / 'materials'
        materials.mkdir()
        (materials / 'resume.pdf').write_bytes(b'%PDF-1.4 fixture')
        (materials / 'manifest.v1.json').write_text(json.dumps({'version': 1, 'resumes': {
            name: 'resume.pdf' for name in ('engineering', 'technical_business', 'japanese')}}))
        prompt = root / 'prompt.md'
        prompt.write_text('Use grounded facts and the live posting.')
        with patch('job_search_loop.ashby_discovery._fresh_jobs', return_value=(live, ['board:HTTPError'], 1, ['board'])):
            return discover_one(cache_path=cache, ledger_path=root/'ledger.sqlite3', profile_path=profile,
                materials_root=materials, prompt_path=prompt, refresh_state=root/'cursor.json',
                board_batch=3, board_blocker_state=root/'blockers.json', max_jobs=max_jobs)

    @staticmethod
    def job(company, identity, location='Tokyo, Japan'):
        return {'ats': 'ashby', 'company': company, 'title': 'Solutions Engineer',
                'url': f'https://jobs.ashbyhq.com/{company}/{identity}', 'location': location,
                'description': 'Official current posting', 'isListed': True}

    def test_failed_live_board_never_admits_cached_posting(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.discover(Path(tmp), [])
        self.assertEqual(result['discovered'], [])

    def test_private_company_exclusion_applies_before_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.discover(Path(tmp), [self.job('Aaru', 'live')], excluded=('Aaru',))
        self.assertEqual(result['discovered'], [])

    def test_zero_budget_creates_no_application(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.discover(Path(tmp), [self.job('LiveCo', 'live')], max_jobs=0)
        self.assertEqual(result['discovered'], [])

    def test_fresh_us_posting_is_shortlisted_for_model_eligibility_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.discover(Path(tmp), [self.job('LiveCo', 'live', 'San Francisco')])
        self.assertEqual([row['company'] for row in result['discovered']], ['LiveCo'])


if __name__ == '__main__':
    unittest.main()
