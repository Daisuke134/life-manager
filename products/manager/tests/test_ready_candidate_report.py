import unittest
from scripts.ready_candidate_report import ready_candidates


class CandidateReportTests(unittest.TestCase):
    def test_ready_and_blocked(self):
        rows = [
            {"id": "A", "status": "done", "depends": []},
            {"id": "B", "status": "todo", "depends": ["A"]},
            {"id": "C", "status": "blocked", "depends": ["A"]},
            {"id": "D", "status": "todo", "depends": ["C"]},
            {"id": "E", "status": "todo", "depends": ["A"], "external": "approval"},
        ]
        self.assertEqual(ready_candidates(rows), ["B"])

    def test_skipped_is_not_a_completed_dependency(self):
        rows = [
            {"id": "A", "status": "skipped", "depends": []},
            {"id": "B", "status": "todo", "depends": ["A"]},
        ]
        self.assertEqual(ready_candidates(rows), [])
