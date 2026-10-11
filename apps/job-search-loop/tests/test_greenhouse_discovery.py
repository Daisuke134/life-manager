import unittest
from pathlib import Path

from job_search_loop.greenhouse_discovery import candidate_jobs, live_board_jobs


class GreenhouseDiscoveryTests(unittest.TestCase):
    def test_daily_owner_discovers_greenhouse_before_shared_model_lane(self):
        script = (
            Path(__file__).resolve().parents[1] / "scripts/run-daily.sh"
        ).read_text(encoding="utf-8")

        self.assertNotIn("-m job_search_loop.greenhouse_discovery", script)
        self.assertIn("--active-provider all", script)

    def test_live_board_jobs_normalizes_only_official_https_rows(self):
        rows = live_board_jobs(
            "anthropic",
            "Anthropic",
            fetch_json=lambda _url: {
                "jobs": [
                    {
                        "title": "Solutions Architect, Japan",
                        "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/123",
                        "location": {"name": "Tokyo, Japan"},
                        "content": "Customer-facing AI role",
                        "first_published": "2026-08-24T00:00:00Z",
                    },
                    {
                        "title": "Unsafe",
                        "absolute_url": "http://example.com/jobs/1",
                        "location": {"name": "Tokyo"},
                    },
                ]
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ats"], "greenhouse")
        self.assertEqual(rows[0]["company"], "Anthropic")

    def test_candidate_jobs_requires_target_role_and_japan_or_remote(self):
        jobs = [
            {
                "ats": "greenhouse",
                "company": "Scale AI",
                "title": "Solutions Architect, Japan",
                "url": "https://job-boards.greenhouse.io/scaleai/jobs/123",
                "location": "Tokyo, Japan",
                "posted_at_ms": 2,
            },
            {
                "ats": "greenhouse",
                "company": "Scale AI",
                "title": "Office Manager",
                "url": "https://job-boards.greenhouse.io/scaleai/jobs/124",
                "location": "Tokyo, Japan",
                "posted_at_ms": 3,
            },
            {
                "ats": "greenhouse",
                "company": "Scale AI",
                "title": "AI Product Manager",
                "url": "https://job-boards.greenhouse.io/scaleai/jobs/125",
                "location": "San Francisco",
                "posted_at_ms": 4,
            },
            {
                "ats": "greenhouse",
                "company": "GitLab",
                "title": "Senior Professional Services Engineer - Japan",
                "url": "https://job-boards.greenhouse.io/gitlab/jobs/126",
                "location": "Remote, Japan",
                "posted_at_ms": 5,
            },
        ]

        rows = candidate_jobs(jobs, seen=set())

        self.assertEqual([row["url"] for row in rows], [jobs[0]["url"], jobs[3]["url"]])
        self.assertEqual(
            candidate_jobs(
                jobs,
                seen={jobs[0]["url"].casefold(), jobs[3]["url"].casefold()},
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
