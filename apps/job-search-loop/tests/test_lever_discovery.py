import unittest
from pathlib import Path

from job_search_loop.lever_discovery import candidate_jobs, live_site_jobs


class LeverDiscoveryTests(unittest.TestCase):
    def test_live_site_jobs_normalizes_only_official_https_rows(self):
        rows = live_site_jobs(
            "binance",
            "Binance",
            fetch_json=lambda _url: [
                {
                    "id": "one",
                    "text": "AI Solutions Engineer, Japan",
                    "hostedUrl": "https://jobs.lever.co/binance/one",
                    "categories": {"location": "Tokyo, Japan"},
                    "descriptionPlain": "Customer-facing AI role",
                    "createdAt": 123,
                },
                {
                    "id": "unsafe",
                    "text": "Unsafe",
                    "hostedUrl": "http://example.com/unsafe",
                    "categories": {"location": "Tokyo"},
                },
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ats"], "lever")
        self.assertEqual(rows[0]["company"], "Binance")

    def test_candidate_jobs_requires_target_role_and_japan_or_remote(self):
        jobs = [
            {
                "ats": "lever", "company": "Binance",
                "title": "AI Solutions Engineer, Japan",
                "url": "https://jobs.lever.co/binance/one",
                "location": "Tokyo, Japan", "posted_at_ms": 2,
            },
            {
                "ats": "lever", "company": "Binance",
                "title": "Office Manager", "url": "https://jobs.lever.co/binance/two",
                "location": "Tokyo, Japan", "posted_at_ms": 3,
            },
            {
                "ats": "lever", "company": "Arcadia",
                "title": "Applied AI Engineer", "url": "https://jobs.lever.co/arcadia/three",
                "location": "San Francisco", "posted_at_ms": 4,
            },
        ]

        rows = candidate_jobs(jobs, seen=set())

        self.assertEqual([row["url"] for row in rows], [jobs[0]["url"]])
        self.assertEqual(candidate_jobs(jobs, seen={jobs[0]["url"].casefold()}), [])

    def test_daily_workday_owner_does_not_search_lever(self):
        script = (Path(__file__).resolve().parents[1] / "scripts/run-daily.sh").read_text()
        self.assertNotIn("-m job_search_loop.lever_discovery", script)
        self.assertIn("--active-provider workday", script)


if __name__ == "__main__":
    unittest.main()
