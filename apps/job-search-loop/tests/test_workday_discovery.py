from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import job_search_loop.workday_source_discovery as workday_source_discovery
from job_search_loop.ledger import Ledger
from job_search_loop.workday_discovery import _fetch_jobs, discover_one
from job_search_loop.workday_source_discovery import merge_sources, validate_sources

TEST_SOURCES = tuple(
    {
        "company": company,
        "host": f"{tenant}.wd1.myworkdayjobs.com",
        "tenant": tenant,
        "site": "Careers",
        "search_text": "Japan",
    }
    for company, tenant in (
        ("NVIDIA", "nvidia"),
        ("Workday", "workday"),
        ("Salesforce", "salesforce"),
        ("Rakuten", "rakuten"),
    )
)


class WorkdayDiscoveryTests(unittest.TestCase):
    def test_portfolio_search_prefers_fresh_finalist_over_existing_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            existing = ledger.add_application(
                "Rakuten",
                "Existing Role",
                "https://rakuten.wd1.myworkdayjobs.com/RakutenInc/job/Existing_R1",
            )
            ledger.transition(existing, "qualified")
            ledger.transition(existing, "materials_ready")
            ledger.record_workday_fit_decision(
                existing, "qualified", "a" * 64, policy_version="test"
            )
            ledger.close()
            fresh_url = "https://salesforce.wd12.myworkdayjobs.com/External/job/Fresh_R2"
            result = discover_one(
                ledger_path=ledger_path,
                sources=(
                    {
                        "company": "Salesforce",
                        "host": "salesforce.wd12.myworkdayjobs.com",
                        "tenant": "salesforce",
                        "site": "External",
                    },
                ),
                fetch_jobs=lambda source: [
                    {
                        "title": "Fresh Role",
                        "locationsText": "Tokyo",
                        "externalPath": "/job/Fresh_R2",
                    }
                ],
                preferred_urls=(fresh_url,),
                prefer_fresh=True,
            )
            self.assertEqual(result["status"], "discovered")
            self.assertEqual(result["discovered"][0]["company"], "Salesforce")
            self.assertNotEqual(result["discovered"][0]["application_id"], existing)

    def test_source_maintenance_accumulates_new_boards_without_replacing_old(self):
        old = TEST_SOURCES[:1]
        new = TEST_SOURCES[1:3]
        merged = merge_sources(old, new)
        self.assertEqual([row["company"] for row in merged], ["Workday", "Salesforce", "NVIDIA"])

    def test_new_worldwide_query_replaces_old_query_for_same_workday_board(self):
        old = (dict(TEST_SOURCES[0], search_text="Tokyo AI"),)
        refreshed = (dict(TEST_SOURCES[0], search_text="customer implementation"),)

        merged = merge_sources(old, refreshed)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["search_text"], "customer implementation")

    def test_source_prompt_does_not_restrict_searches_to_japan(self):
        prompt_source = inspect.getsource(workday_source_discovery.main)

        self.assertIn("Remote, onsite, and hybrid roles ", prompt_source)
        self.assertIn("worldwide are all in scope", prompt_source)
        self.assertIn("no location-specific search terms", prompt_source)
        self.assertNotIn("Tokyo, Japan-remote", prompt_source)
        self.assertNotIn("Include Tokyo or Japan intent in every search_text", prompt_source)

    def test_unqualified_row_from_missing_source_does_not_block_current_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            old_id = ledger.add_application(
                "Old",
                "Old Role",
                "https://old.wd1.myworkdayjobs.com/Careers/job/Old_R0",
            )
            ledger.transition(old_id, "qualified")
            ledger.transition(old_id, "materials_ready")
            ledger.close()
            source = TEST_SOURCES[0]

            result = discover_one(
                ledger_path=ledger_path,
                sources=(source,),
                fetch_jobs=lambda _source: [
                    {"title": "Fresh", "locationsText": "Tokyo", "externalPath": "/job/Fresh_R1"}
                ],
            )

            self.assertEqual(result["status"], "discovered")
            self.assertEqual(result["discovered"][0]["title"], "Fresh")

    def test_model_shortlist_can_select_later_snapshot_job_first(self):
        with tempfile.TemporaryDirectory() as directory:
            source = TEST_SOURCES[0]
            first_url = f"https://{source['host']}/{source['site']}/job/Tokyo/First_R1"
            best_url = f"https://{source['host']}/{source['site']}/job/Tokyo/Best_R2"

            result = discover_one(
                ledger_path=Path(directory) / "ledger.sqlite3",
                sources=(source,),
                fetch_jobs=lambda _source: [
                    {"title": "First", "locationsText": "Tokyo", "externalPath": "/job/Tokyo/First_R1"},
                    {"title": "Best", "locationsText": "Tokyo", "externalPath": "/job/Tokyo/Best_R2"},
                ],
                preferred_urls=(best_url, first_url),
            )

            self.assertEqual(result["discovered"][0]["title"], "Best")

    def test_cxs_fetch_paginates_exact_source_search_text_until_official_total(self):
        payloads = [
            {"total": 41, "jobPostings": [
                {"title": f"Role {index}", "externalPath": f"/job/R{index}"}
                for index in range(20)
            ]},
            {"total": 41, "jobPostings": [
                {"title": f"Role {index}", "externalPath": f"/job/R{index}"}
                for index in range(20, 40)
            ]},
            {"total": 41, "jobPostings": [
                {"title": "Role 40", "externalPath": "/job/R40"}
            ]},
        ]
        requests = []

        class Response:
            def __init__(self, payload): self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *_args): return False

        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data))
            return Response(payloads[len(requests) - 1])

        source = {**TEST_SOURCES[0], "search_text": "Tokyo Japan AI"}
        with patch("job_search_loop.workday_discovery.urlopen", fake_urlopen), patch(
            "job_search_loop.workday_discovery.json.load",
            side_effect=lambda response: response.payload,
        ):
            rows = _fetch_jobs(source)

        self.assertEqual(len(rows), 41)
        self.assertEqual([request["offset"] for request in requests], [0, 20, 40])
        self.assertEqual(
            [request["searchText"] for request in requests],
            ["Tokyo Japan AI", "Tokyo Japan AI", "Tokyo Japan AI"],
        )

    def test_cxs_fetch_raises_when_page_ends_before_official_total(self):
        payloads = [
            {"total": 21, "jobPostings": [
                {"title": f"Role {index}", "externalPath": f"/job/R{index}"}
                for index in range(20)
            ]},
            {"total": 21, "jobPostings": []},
        ]
        requests = []

        class Response:
            def __init__(self, payload): self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *_args): return False

        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data))
            return Response(payloads[len(requests) - 1])

        with patch("job_search_loop.workday_discovery.urlopen", fake_urlopen), patch(
            "job_search_loop.workday_discovery.json.load",
            side_effect=lambda response: response.payload,
        ):
            with self.assertRaisesRegex(ValueError, "total"):
                _fetch_jobs(TEST_SOURCES[0])

        self.assertEqual([request["offset"] for request in requests], [0, 20])

    def test_cxs_fetch_rejects_page_with_invalid_posting_identity(self):
        payload = {
            "total": 2,
            "jobPostings": [
                {"title": "Valid Role", "externalPath": "/job/Valid_R1"},
                {},
            ],
        }

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False

        with patch("job_search_loop.workday_discovery.urlopen", lambda *_args, **_kwargs: Response()), patch(
            "job_search_loop.workday_discovery.json.load",
            return_value=payload,
        ):
            with self.assertRaisesRegex(ValueError, "posting"):
                _fetch_jobs(TEST_SOURCES[0])

    def test_model_sources_accept_arbitrary_company_and_reject_explicit_exclusion(self):
        sources = validate_sources(
            {"sources": [
                {
                    "company": "DifferentCo",
                    "host": "different.wd1.myworkdayjobs.com",
                    "tenant": "different",
                    "site": "Careers",
                    "search_text": "applied AI",
                },
                {
                    "company": "OpenAI",
                    "host": "openai.wd1.myworkdayjobs.com",
                    "tenant": "openai",
                    "site": "Careers",
                    "search_text": "applied AI",
                },
            ]},
            frozenset({"OpenAI"}),
        )

        self.assertEqual([row["company"] for row in sources], ["DifferentCo"])

    def test_discovery_uses_runtime_sources_not_fixed_companies(self):
        source = {
            "company": "DifferentCo",
            "host": "different.wd1.myworkdayjobs.com",
            "tenant": "different",
            "site": "Careers",
            "search_text": "applied AI",
        }
        seen = []
        with tempfile.TemporaryDirectory() as directory:
            def fake_fetch(candidate):
                seen.append(candidate["company"])
                return []

            discover_one(
                ledger_path=Path(directory) / "ledger.sqlite3",
                fetch_jobs=fake_fetch,
                sources=(source,),
            )

        self.assertEqual(seen, ["DifferentCo"])

    def test_discovery_does_not_use_title_keywords_as_fit_judgment(self):
        with tempfile.TemporaryDirectory() as directory:
            def fake_fetch(source):
                if source["company"] == "NVIDIA":
                    return [{
                        "title": "Office Administrator",
                        "locationsText": "Japan, Tokyo",
                        "externalPath": "/job/Japan-Tokyo/Office-Administrator_JR8",
                    }]
                return []

            result = discover_one(
                ledger_path=Path(directory) / "ledger.sqlite3",
                fetch_jobs=fake_fetch,
                sources=TEST_SOURCES,
            )

            self.assertEqual(result["status"], "discovered")
            self.assertEqual(result["discovered"][0]["title"], "Office Administrator")

    def test_discovers_unseen_official_rows_without_keyword_ranking(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"

            def fake_fetch(source):
                if source["company"] == "NVIDIA":
                    return [
                        {
                            "title": "Solution Architect - Agentic AI",
                            "locationsText": "Japan, Tokyo",
                            "externalPath": "/job/Japan-Tokyo/Solution-Architect---Agentic-AI_JR9",
                        },
                        {
                            "title": "Office Administrator",
                            "locationsText": "Japan, Tokyo",
                            "externalPath": "/job/Japan-Tokyo/Office-Administrator_JR8",
                        },
                    ]
                if source["company"] == "Workday":
                    return [
                        {
                            "title": "Technical Account Manager",
                            "locationsText": "Japan, Tokyo",
                            "externalPath": "/job/Japan-Tokyo/Technical-Account-Manager_JR7",
                        }
                    ]
                return []

            first = discover_one(ledger_path=ledger_path, fetch_jobs=fake_fetch, sources=TEST_SOURCES)
            self.assertEqual(first["status"], "discovered")
            self.assertEqual(first["discovered"][0]["title"], "Solution Architect - Agentic AI")

            ledger = Ledger(ledger_path)
            self.assertEqual(ledger.current_state(first["discovered"][0]["application_id"]), "materials_ready")
            ledger.transition(first["discovered"][0]["application_id"], "rejected")
            ledger.close()

            second = discover_one(ledger_path=ledger_path, fetch_jobs=fake_fetch, sources=TEST_SOURCES)
            self.assertEqual(second["status"], "discovered")
            self.assertEqual(second["discovered"][0]["title"], "Office Administrator")

    def test_existing_workday_queue_prevents_backlog_growth(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "NVIDIA",
                "Agent Engineer",
                f"https://{TEST_SOURCES[0]['host']}/{TEST_SOURCES[0]['site']}/job/Japan-Tokyo/Agent-Engineer_JR1",
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.close()

            result = discover_one(
                ledger_path=ledger_path,
                fetch_jobs=lambda _source: self.fail("provider must not run while queue exists"),
                sources=TEST_SOURCES,
            )

            self.assertEqual(result["status"], "queue_present")
            self.assertEqual(result["queued_application_ids"], [application_id])

    def test_hold_fit_decision_does_not_block_next_fresh_job(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            held_id = ledger.add_application(
                "Salesforce",
                "Stretch Role",
                "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site/job/Japan/Stretch_JR1",
            )
            ledger.transition(held_id, "qualified")
            ledger.transition(held_id, "materials_ready")
            ledger.record_workday_fit_decision(
                held_id, "hold", "a" * 64, policy_version="test"
            )
            ledger.close()

            def fake_fetch(source):
                if source["company"] == "Workday":
                    return [{
                        "title": "Technical Account Manager",
                        "locationsText": "Japan, Tokyo",
                        "externalPath": "/job/Japan-Tokyo/Technical-Account-Manager_JR2",
                    }]
                return []

            result = discover_one(ledger_path=ledger_path, fetch_jobs=fake_fetch, sources=TEST_SOURCES)

            self.assertEqual(result["status"], "discovered")
            self.assertEqual(result["discovered"][0]["title"], "Technical Account Manager")

    def test_one_source_failure_does_not_stop_other_tenants(self):
        with tempfile.TemporaryDirectory() as directory:
            def fake_fetch(source):
                if source["company"] == "NVIDIA":
                    raise TimeoutError("provider timeout")
                if source["company"] == "Workday":
                    return [
                        {
                            "title": "Senior Technical Account Manager",
                            "locationsText": "Japan, Tokyo",
                            "externalPath": "/job/Japan-Tokyo/Senior-Technical-Account-Manager_JR6",
                        }
                    ]
                return []

            result = discover_one(
                ledger_path=Path(directory) / "ledger.sqlite3", fetch_jobs=fake_fetch,
                sources=TEST_SOURCES,
            )
            self.assertEqual(result["status"], "discovered")
            self.assertEqual(result["errors"], ["nvidia:TimeoutError"])
            self.assertEqual(result["discovered"][0]["company"], "Workday")


if __name__ == "__main__":
    unittest.main()
