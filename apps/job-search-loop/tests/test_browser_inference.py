from __future__ import annotations

import unittest

from job_search_loop.browser_agent.candidate_memory import CandidateMemoryView
from job_search_loop.browser_agent.inference import StableInferencePolicy


class BrowserInferenceTests(unittest.TestCase):
    def test_anywhere_profile_preference_allows_relocation_without_granting_work_authorization(self):
        memory = CandidateMemoryView(
            {
                "schema_version": 1,
                "concepts": [
                    {
                        "concept": "candidate.location_preferences",
                        "value": ["Anywhere"],
                    },
                    {
                        "concept": "candidate.work_authorizations",
                        "value": [],
                    },
                ],
            }
        )

        policy = StableInferencePolicy(memory)
        relocation = policy.resolve(
            "mobility.relocation",
            target_location="New York",
        )
        authorization = policy.resolve(
            "work_authorization.authorized",
            country="United States",
        )

        self.assertTrue(relocation.value)
        self.assertEqual(relocation.provenance, ("candidate.location_preferences",))
        self.assertFalse(authorization.value)
