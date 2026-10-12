from __future__ import annotations

import inspect
import json
import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import job_search_loop.workday_search_loop as workday_search_loop
import job_search_loop.workday_qualification as workday_qualification
from job_search_loop.ledger import Ledger
from job_search_loop.workday_search_loop import (
    cached_source_fetcher,
    interleave_companies,
    qualified_queue_ids,
    rank_candidates,
    rotated_sources,
    rolling_submission_metrics,
    search_until_qualified,
    snapshot_candidates,
    company_submit_attempt_exposure,
    filter_submit_attempt_sources,
    qualify_with_wake_cursor,
    reject_stale_workday_rows,
    submit_attempt_hosts,
    validate_shortlist,
    unique_sources,
)
from job_search_loop.workday_qualification import POLICY_VERSION, qualify_one


class WorkdayQualificationTests(unittest.TestCase):
    def test_shortlist_prompt_includes_worldwide_locations_and_salary_target(self):
        prompt_source = inspect.getsource(workday_search_loop.main)

        self.assertIn("No location category outranks another", prompt_source)
        self.assertIn("onsite or hybrid roles worldwide", prompt_source)
        self.assertIn("remote roles worldwide", prompt_source)
        self.assertIn("USD 100,000 annual gross base target", prompt_source)
        self.assertNotIn("Tokyo onsite or hybrid", prompt_source)
        self.assertNotIn("United States roles in any location", prompt_source)
        self.assertNotIn("Japan employment first", prompt_source)
        self.assertNotIn(
            "Every row that explicitly supports employment from Japan must rank before any row tied to another country",
            prompt_source,
        )

        fit_source = inspect.getsource(workday_qualification.qualify_one)
        self.assertIn("USD 100,000 annual gross base", fit_source)
        self.assertIn("CEO or C-suite", fit_source)
        self.assertIn("Do not reject a role based on title alone", fit_source)

    def test_v7_requalifies_old_rejections_without_replaying_submit_intents(self):
        self.assertEqual(POLICY_VERSION, "workday-global-scope-v7")
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "ledger.sqlite3")

            def rejected(label: str, url: str) -> str:
                application_id = ledger.add_application("Example", label, url)
                ledger.record_workday_fit_decision(
                    application_id,
                    "rejected",
                    ("a" if label != "Already submitted" else "b") * 64,
                    policy_version="workday-global-scope-v6",
                )
                return application_id

            eligible = rejected(
                "Worldwide onsite",
                "https://example.wd1.myworkdayjobs.com/Careers/job/DE/Role_R1",
            )
            submitted = rejected(
                "Already submitted",
                "https://example.wd1.myworkdayjobs.com/Careers/job/FR/Role_R2",
            )
            ledger.connection.execute(
                """
                INSERT INTO submit_intents
                  (intent_id, application_id, fence, payload_hash, japan_day,
                   slot, status, created_at)
                VALUES (?, ?, 1, ?, '2026-10-12', 1, 'submit_unknown',
                        '2026-10-12T00:00:00+00:00')
                """,
                ("intent-worldwide", submitted, "c" * 64),
            )

            rows = ledger.superseded_workday_fit_rejections(POLICY_VERSION)
            ledger.close()

        self.assertEqual([row["application_id"] for row in rows], [eligible])

    def test_sponsorship_wording_alone_does_not_exclude_worldwide_roles(self):
        shortlist_source = inspect.getsource(workday_search_loop.main)
        fit_source = inspect.getsource(workday_qualification.qualify_one)

        self.assertIn("Sponsorship status alone is not a reason to reject any role", fit_source)
        self.assertIn("regardless of country", shortlist_source)
        self.assertIn("answer every work-authorization and sponsorship question truthfully", fit_source)
        self.assertNotIn(
            "eligible only with existing work authorization or explicit employer sponsorship",
            shortlist_source,
        )

    def test_candidate_windows_interleave_companies_instead_of_source_volume(self):
        rows = [
            {"company": "Rakuten", "url": f"r-{index}"}
            for index in range(4)
        ] + [
            {"company": "Salesforce", "url": "s-1"},
            {"company": "Razer", "url": "z-1"},
        ]
        self.assertEqual(
            [row["url"] for row in interleave_companies(rows)],
            ["r-0", "s-1", "z-1", "r-1", "r-2", "r-3"],
        )

    def test_qualification_uses_model_shortlist_before_ledger_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, oldest, memory = self._row(root)
            ledger = Ledger(ledger_path)
            preferred = ledger.add_application(
                "Preferred", "Current Scope", "https://preferred.wd1.myworkdayjobs.com/Careers/job/Japan/Role_R2"
            )
            ledger.transition(preferred, "qualified")
            ledger.transition(preferred, "materials_ready")
            ledger.close()
            preferred_url = "https://preferred.wd1.myworkdayjobs.com/Careers/job/Japan/Role_R2"
            fetched = []

            result = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                preferred_urls=(preferred_url,),
                fetch_description=lambda url: fetched.append(url) or "Current scope in Japan",
                run_model=lambda _prompt: {
                    "decision": "qualified",
                    "mandatory_evidence": ["Grounded experience matches"],
                    "unsupported_gaps": [],
                    "interview_thesis": "Credible interview case",
                    "location_feasibility": "Japan is feasible",
                    "compensation_thesis": "Unpublished and uncertain",
                    "compensation_uncertain": True,
                    "resume_variant": "business",
                },
            )

            self.assertEqual(result["application_id"], preferred)
            self.assertEqual(fetched, [preferred_url])
            self.assertNotEqual(result["application_id"], oldest)

    def test_submit_attempt_sources_match_workday_host_case_insensitively(self):
        sources = (
            {
                "company": "Rakuten Group, Inc.",
                "host": "RAKUTEN.WD1.MYWORKDAYJOBS.COM",
                "tenant": "rakuten",
                "site": "Careers",
            },
            {
                "company": "New Company",
                "host": "new.wd1.myworkdayjobs.com",
                "tenant": "new",
                "site": "Careers",
            },
        )
        self.assertEqual(
            filter_submit_attempt_sources(
                sources, {"rakuten.wd1.myworkdayjobs.com"}
            ),
            (sources[1],),
        )

    def test_submit_attempt_sources_return_empty_when_all_are_exposed(self):
        sources = (
            {
                "company": "Rakuten",
                "host": "rakuten.wd1.myworkdayjobs.com",
                "tenant": "rakuten",
                "site": "Careers",
            },
            {
                "company": "Salesforce",
                "host": "salesforce.wd1.myworkdayjobs.com",
                "tenant": "salesforce",
                "site": "Careers",
            },
        )
        self.assertEqual(
            filter_submit_attempt_sources(
                sources,
                {
                    "rakuten.wd1.myworkdayjobs.com",
                    "salesforce.wd1.myworkdayjobs.com",
                },
            ),
            (),
        )

    def test_company_submit_attempt_exposure_counts_submit_intents_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(path)
            for index, company in enumerate(("Rakuten", "Rakuten", "Razer")):
                application_id = ledger.add_application(
                    company,
                    f"Role {index}",
                    f"https://{company.lower()}.wd1.myworkdayjobs.com/job/{index}",
                )
                ledger.transition(application_id, "qualified")
                ledger.transition(application_id, "materials_ready")
                ledger.connection.execute(
                    "UPDATE applications SET current_state='submitted' WHERE id=?",
                    (application_id,),
                )
                ledger.connection.execute(
                    """
                    INSERT INTO submit_intents
                      (intent_id, application_id, fence, payload_hash, japan_day,
                       slot, status, created_at)
                    VALUES (?, ?, 1, ?, '2026-08-28', ?, 'submitted',
                            '2026-08-28T00:00:00+00:00')
                    """,
                    (
                        f"intent-{application_id}",
                        application_id,
                        "a" * 64,
                        index + 1,
                    ),
                )
            claimed_id = ledger.add_application(
                "Salesforce",
                "Claimed Role",
                "https://salesforce.wd1.myworkdayjobs.com/job/claimed",
            )
            unknown_id = ledger.add_application(
                "Nvidia",
                "Unknown Role",
                "https://nvidia.wd1.myworkdayjobs.com/job/unknown",
            )
            materials_id = ledger.add_application(
                "Zendesk",
                "Materials Role",
                "https://zendesk.wd1.myworkdayjobs.com/job/materials",
            )
            rejected_id = ledger.add_application(
                "Autodesk",
                "Rejected Role",
                "https://autodesk.wd1.myworkdayjobs.com/job/rejected",
            )
            for slot, (application_id, state, status) in enumerate(
                (
                    (claimed_id, "submit_claimed", "submit_claimed"),
                    (unknown_id, "submit_unknown", "submit_unknown"),
                    (materials_id, "materials_ready", "submit_claimed"),
                    (rejected_id, "rejected", "submit_unknown"),
                ),
                start=1,
            ):
                ledger.connection.execute(
                    "UPDATE applications SET current_state=? WHERE id=?",
                    (state, application_id),
                )
                ledger.connection.execute(
                    """
                    INSERT INTO submit_intents
                      (intent_id, application_id, fence, payload_hash, japan_day,
                       slot, status, created_at)
                    VALUES (?, ?, 1, ?, '2026-08-28', ?, ?, '2026-08-28T00:00:00+00:00')
                    """,
                    (
                        f"intent-{application_id}",
                        application_id,
                        "a" * 64,
                        slot,
                        status,
                    ),
                )
            ledger.connection.commit()
            ledger.close()
            self.assertEqual(
                company_submit_attempt_exposure(path),
                {
                    "Rakuten": 2,
                    "Razer": 1,
                    "Salesforce": 1,
                    "Nvidia": 1,
                },
            )
            self.assertEqual(
                submit_attempt_hosts(path),
                frozenset(
                    {
                        "rakuten.wd1.myworkdayjobs.com",
                        "razer.wd1.myworkdayjobs.com",
                        "salesforce.wd1.myworkdayjobs.com",
                        "nvidia.wd1.myworkdayjobs.com",
                        "zendesk.wd1.myworkdayjobs.com",
                        "autodesk.wd1.myworkdayjobs.com",
                    }
                ),
            )
    def test_transient_qualification_failure_retries_same_wake(self):
        attempts = 0

        def qualify():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("model at capacity")
            return {
                "status": "decided",
                "decision": "qualified",
                "application_id": "A",
            }

        result = search_until_qualified(
            discover=lambda: {"status": "queue_present", "discovered": []},
            qualify=qualify,
            max_candidates=3,
        )

        self.assertEqual(result["status"], "qualified")
        self.assertEqual(attempts, 2)

    def test_search_fills_multiple_distinct_qualified_rows_to_target(self):
        discoveries = []
        decisions = iter(
            (
                {"status": "decided", "decision": "qualified", "application_id": "A"},
                {"status": "decided", "decision": "qualified", "application_id": "B"},
                {"status": "decided", "decision": "qualified", "application_id": "B"},
                {"status": "decided", "decision": "qualified", "application_id": "C"},
            )
        )

        result = search_until_qualified(
            discover=lambda: discoveries.append(len(discoveries) + 1)
            or {"status": "discovered", "discovered": []},
            qualify=lambda: next(decisions),
            max_candidates=4,
            target_qualified=3,
        )

        self.assertEqual(len(discoveries), 4)
        self.assertEqual(result["status"], "qualified")
        self.assertEqual(result["qualified_application_ids"], ["A", "B", "C"])

    def test_main_stops_after_one_new_qualified_row_per_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path = root / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            ledger.close()

            candidate_memory = root / "candidate-memory.json"
            candidate_memory.write_text(
                json.dumps({"concepts": []}), encoding="utf-8"
            )
            sources = root / "sources.json"
            sources.write_text(json.dumps({"sources": []}), encoding="utf-8")
            output = root / "search-result.json"
            snapshot = root / "snapshot.json"
            decisions = iter(
                {
                    "status": "decided",
                    "decision": "qualified",
                    "application_id": f"application-{index}",
                }
                for index in range(3)
            )
            argv = [
                "workday_search_loop",
                "--ledger",
                str(ledger_path),
                "--candidate-memory",
                str(candidate_memory),
                "--sources",
                str(sources),
                "--runner",
                str(root / "agent-runner.py"),
                "--schema",
                str(root / "schema.json"),
                "--shortlist-schema",
                str(root / "shortlist-schema.json"),
                "--workdir",
                str(root / "workdir"),
                "--evidence-root",
                str(root / "evidence"),
                "--output",
                str(output),
                "--snapshot",
                str(snapshot),
                "--max-candidates",
                "3",
            ]

            with patch.object(
                workday_search_loop, "snapshot_candidates", return_value=[]
            ), patch.object(
                workday_search_loop, "reject_stale_workday_rows", return_value=[]
            ), patch.object(
                workday_search_loop, "qualified_queue_ids", return_value=()
            ), patch.object(
                workday_search_loop,
                "discover_one",
                return_value={"status": "discovered", "discovered": []},
            ), patch.object(
                workday_search_loop,
                "qualify_with_wake_cursor",
                side_effect=lambda *_args, **_kwargs: next(decisions),
            ), patch.object(
                workday_search_loop,
                "deliver_fit_decision",
                return_value={"message_id": "telegram-1", "status": "sent"},
            ), patch("sys.argv", argv):
                self.assertEqual(workday_search_loop.main(), 0)

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                result["qualified_application_ids"],
                ["application-0"],
            )
            self.assertEqual(result["status"], "qualified")
            self.assertEqual(len(result["discoveries"]), 1)
            self.assertEqual(len(result["decisions"]), 1)

    def test_main_preserves_existing_queue_and_qualifies_fresh_workday_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path = root / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            ledger.close()
            candidate_memory = root / "candidate-memory.json"
            candidate_memory.write_text(json.dumps({"concepts": []}), encoding="utf-8")
            sources = root / "sources.json"
            sources.write_text(json.dumps({"sources": []}), encoding="utf-8")
            output = root / "search-result.json"
            snapshot = root / "snapshot.json"
            base_args = ["workday_search_loop"]
            for flag, path in (
                ("--ledger", ledger_path),
                ("--candidate-memory", candidate_memory),
                ("--sources", sources),
                ("--runner", root / "agent-runner.py"),
                ("--schema", root / "schema.json"),
                ("--shortlist-schema", root / "shortlist-schema.json"),
                ("--workdir", root / "workdir"),
                ("--evidence-root", root / "evidence"),
                ("--output", output),
                ("--snapshot", snapshot),
            ):
                base_args.extend((flag, str(path)))

            fresh_url = "https://fresh.wd5.myworkdayjobs.com/Careers/job/Remote/New_R1"
            fresh_candidate = {
                "company": "NewCo",
                "title": "Business Analyst",
                "location": "Remote",
                "url": fresh_url,
            }
            with patch.object(
                workday_search_loop, "snapshot_candidates", return_value=[fresh_candidate]
            ), patch.object(
                workday_search_loop,
                "reject_stale_workday_rows",
                return_value=[],
            ), patch.object(
                workday_search_loop,
                "qualified_queue_ids",
                return_value=("existing-application",),
            ), patch.object(
                workday_search_loop,
                "discover_one",
                return_value={"status": "no_fresh_workday", "discovered": []},
            ) as discover, patch.object(
                workday_search_loop,
                "rank_candidates",
                return_value=(fresh_url,),
            ) as rank, patch.object(
                workday_search_loop,
                "qualify_with_wake_cursor",
                return_value={
                    "status": "decided",
                    "decision": "qualified",
                    "application_id": "new-application",
                },
            ) as qualify, patch.object(
                workday_search_loop,
                "deliver_fit_decision",
                return_value={"message_id": "fit-message", "status": "sent"},
            ), patch.object(
                workday_search_loop,
                "rolling_submission_metrics",
                return_value={"target": 48, "confirmed_count": 0, "deficit": 48},
            ), patch("sys.argv", base_args):
                self.assertEqual(workday_search_loop.main(), 0)

            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "qualified")
            self.assertEqual(
                result["queued_application_ids"],
                ["new-application", "existing-application"],
            )
            self.assertEqual(result["qualified_application_ids"], ["new-application"])
            self.assertEqual(result["shortlist"], [fresh_url])
            rank.assert_called_once()
            discover.assert_called_once()
            qualify.assert_called_once()

    def test_zero_rolling_target_does_not_discover_or_qualify(self):
        calls = []
        result = search_until_qualified(
            discover=lambda: calls.append("discover"),
            qualify=lambda: calls.append("qualify"),
            max_candidates=24,
            target_qualified=0,
        )

        self.assertEqual(result["status"], "deficit_satisfied")
        self.assertEqual(result["qualified_application_ids"], [])
        self.assertEqual(calls, [])

    def test_no_fresh_jobs_still_requalifies_superseded_fit_rows(self):
        discovery_calls = []
        fit_decisions = iter(
            [
                {
                    "status": "decided",
                    "decision": "qualified",
                    "application_id": "old-location-reject",
                },
                {"status": "no_pending_workday_fit"},
            ]
        )

        result = search_until_qualified(
            discover=lambda: discovery_calls.append("discover")
            or {"status": "no_fresh_workday", "discovered": []},
            qualify=lambda: next(fit_decisions),
            max_candidates=3,
            target_qualified=2,
        )

        self.assertEqual(result["status"], "sources_exhausted")
        self.assertEqual(result["qualified_application_ids"], ["old-location-reject"])
        self.assertEqual(len(result["decisions"]), 2)
        self.assertEqual(discovery_calls, ["discover"])

    def test_rolling_submission_metrics_uses_recent_confirmation_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
            ledger = Ledger(ledger_path)
            rows = (
                ("recent", now - timedelta(hours=1)),
                ("old", now - timedelta(hours=25)),
                ("future", now + timedelta(hours=1)),
            )
            for index, (label, received_at) in enumerate(rows):
                application_id = ledger.add_application(
                    label,
                    f"Role {label}",
                    f"https://{label}.wd1.myworkdayjobs.com/Careers/job/{index}",
                )
                intent_id = f"intent-{label}"
                ledger.connection.execute(
                    """
                    INSERT INTO submit_intents
                      (intent_id, application_id, fence, payload_hash, japan_day,
                       slot, status, created_at)
                    VALUES (?, ?, 1, ?, '2026-08-30', ?, 'submitted', ?)
                    """,
                    (
                        intent_id,
                        application_id,
                        "a" * 64,
                        index + 1,
                        (received_at - timedelta(minutes=1)).isoformat(),
                    ),
                )
                ledger.connection.execute(
                    """
                    INSERT INTO submission_confirmations
                      (message_id, thread_id, intent_id, evidence_sha256,
                       received_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"message-{label}",
                        f"thread-{label}",
                        intent_id,
                        "b" * 64,
                        received_at.isoformat(),
                        now.isoformat(),
                    ),
                )
            ledger.close()

            self.assertEqual(
                rolling_submission_metrics(ledger_path, now=now),
                {"target": 48, "confirmed_count": 1, "deficit": 47},
            )

    def test_qualified_queue_is_detected_before_snapshot_search(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "Example", "Role", "https://example.wd1.myworkdayjobs.com/Careers/job/R1"
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.record_workday_fit_decision(
                application_id, "qualified", "a" * 64, policy_version="test"
            )
            ledger.close()

            self.assertEqual(
                qualified_queue_ids(
                    ledger_path,
                    {"example.wd1.myworkdayjobs.com"},
                    policy_version="test",
                ),
                (application_id,),
            )

            self.assertEqual(
                qualified_queue_ids(
                    ledger_path,
                    {"example.wd1.myworkdayjobs.com"},
                    policy_version="new-policy",
                ),
                (),
            )

    def test_recovery_requested_row_does_not_block_fresh_qualification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path = root / "ledger.sqlite3"
            url = "https://cloudera.wd5.myworkdayjobs.com/External_Career/job/role"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application("Cloudera", "Applied AI Specialist", url)
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.record_workday_fit_decision(
                application_id, "qualified", "a" * 64, policy_version="test"
            )
            ledger.close()
            credentials = root / "credentials.json"
            credentials.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "credentials": [
                            {
                                "service": "workday:cloudera.wd5.myworkdayjobs.com",
                                "username": "candidate@example.com",
                                "email": "candidate@example.com",
                                "password": "Strong-Workday-Password-9!",
                                "account_status": "recovery_requested",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(credentials, 0o600)

            with patch.dict(
                os.environ,
                {"JOB_SEARCH_MACHINE_CREDENTIALS": str(credentials)},
            ):
                queued = qualified_queue_ids(
                    ledger_path,
                    {"cloudera.wd5.myworkdayjobs.com"},
                    policy_version="test",
                )

            self.assertEqual(queued, ())

    def test_retryable_not_submitted_row_is_queued_before_fresh_qualification(self):
        row = {
            "application_id": "retryable-application",
            "company": "Danaher",
            "title": "Business Account Manager",
            "canonical_url": "https://danaher.wd1.myworkdayjobs.com/job/role",
        }
        ledger = Mock()
        ledger.pending_materials_ready_applications.return_value = []
        ledger.retryable_applications.return_value = [row]
        ledger.workday_fit_qualified.return_value = True
        with patch.object(workday_search_loop, "Ledger", return_value=ledger):
            queued = qualified_queue_ids(
                Path("/ledger.sqlite3"),
                set(),
                policy_version="test",
            )

        self.assertEqual(queued, ("retryable-application",))

    def test_non_workday_retryable_cannot_abort_workday_queue(self):
        ledger = Mock()
        ledger.pending_materials_ready_applications.return_value = []
        ledger.retryable_applications.return_value = [
            {
                "application_id": "ashby-retry",
                "company": "Ashby Company",
                "title": "Role",
                "canonical_url": "https://jobs.ashbyhq.com/example/role",
            },
            {
                "application_id": "workday-retry",
                "company": "Danaher",
                "title": "Business Account Manager",
                "canonical_url": "https://danaher.wd1.myworkdayjobs.com/job/role",
            },
        ]
        ledger.workday_fit_qualified.return_value = True
        with patch.object(
            workday_search_loop, "Ledger", return_value=ledger
        ), patch.dict(
            os.environ, {"JOB_SEARCH_MACHINE_CREDENTIALS": ""}
        ):
            queued = qualified_queue_ids(
                Path("/ledger.sqlite3"), set(), policy_version="test"
            )

        self.assertEqual(queued, ("workday-retry",))

    def test_duplicate_registry_source_is_fetched_once(self):
        sources = (
            {"company": "A", "host": "a.wd1.myworkdayjobs.com", "tenant": "a", "site": "Careers", "search_text": "one"},
            {"company": "A", "host": "a.wd1.myworkdayjobs.com", "tenant": "a", "site": "Careers", "search_text": "two"},
        )
        self.assertEqual(len(unique_sources(sources)), 1)

    def test_complete_snapshot_is_ranked_in_chunks_then_finalists(self):
        candidates = [
            {"url": f"https://a.wd1.myworkdayjobs.com/Careers/job/{index}"}
            for index in range(50)
        ]
        calls = []
        candidate_id_calls = []

        def rank(chunk):
            calls.append([row["url"] for row in chunk])
            candidate_id_calls.append([row["candidate_id"] for row in chunk])
            return {"ranked_candidate_ids": [chunk[-1]["candidate_id"]]}

        result = rank_candidates(
            candidates=candidates,
            rank_chunk=rank,
            chunk_size=2,
        )

        self.assertEqual(len(calls), 26)
        self.assertEqual(len(calls[-1]), 25)
        self.assertEqual(result, (calls[-1][-1],))
        self.assertTrue(all(ids[0] == "c0" for ids in candidate_id_calls))

    def test_snapshot_skips_failed_source_and_keeps_other_company(self):
        with tempfile.TemporaryDirectory() as directory:
            sources = (
                {"company": "Broken", "host": "broken.wd1.myworkdayjobs.com", "site": "Careers"},
                {"company": "Good", "host": "good.wd1.myworkdayjobs.com", "site": "Careers"},
            )

            def fetch(source):
                if source["company"] == "Broken":
                    raise TimeoutError
                return [{"title": "Good Role", "locationsText": "Tokyo", "externalPath": "/job/Good_R1"}]

            rows = snapshot_candidates(
                ledger_path=Path(directory) / "ledger.sqlite3",
                sources=sources,
                fetch_jobs=fetch,
            )

            self.assertEqual([row["company"] for row in rows], ["Good"])

    def test_snapshot_requeues_unfinished_seen_rows_only(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)

            def add(label):
                application_id = ledger.add_application(
                    "Example",
                    label,
                    f"https://example.wd1.myworkdayjobs.com/Careers/job/{label}",
                )
                ledger.transition(application_id, "qualified")
                ledger.transition(application_id, "materials_ready")
                return application_id

            unfinished = add("Unfinished")
            held = add("Held")
            ledger.record_workday_fit_decision(
                held, "hold", "a" * 64, policy_version="test"
            )
            rejected = add("Rejected")
            ledger.record_workday_fit_decision(
                rejected, "rejected", "b" * 64, policy_version="test"
            )
            qualified = add("Qualified")
            ledger.record_workday_fit_decision(
                qualified, "qualified", "c" * 64, policy_version="test"
            )
            attempted = add("Attempted")
            ledger.connection.execute(
                """
                INSERT INTO submit_intents
                  (intent_id, application_id, fence, payload_hash, japan_day,
                   slot, status, created_at)
                VALUES (?, ?, 1, ?, '2026-08-30', 1, 'submit_claimed',
                        '2026-08-30T00:00:00+00:00')
                """,
                ("intent-attempted", attempted, "d" * 64),
            )
            ledger.close()

            source = {
                "company": "Example",
                "host": "example.wd1.myworkdayjobs.com",
                "site": "Careers",
            }
            rows = snapshot_candidates(
                ledger_path=ledger_path,
                sources=(source,),
                fetch_jobs=lambda _source: [
                    {
                        "title": label,
                        "locationsText": "Tokyo",
                        "externalPath": f"/job/{label}",
                    }
                    for label in ("Unfinished", "Held", "Rejected", "Qualified", "Attempted")
                ],
            )

            self.assertEqual(
                {row["title"] for row in rows},
                {"Unfinished", "Held"},
            )

    def test_snapshot_prefers_unfinished_rows_before_fresh_rows(self):
        source = {
            "company": "Example",
            "host": "example.wd1.myworkdayjobs.com",
            "site": "Careers",
        }
        jobs = [
            {"title": "Fresh", "locationsText": "Tokyo", "externalPath": "/job/Fresh"},
            {"title": "Unfinished", "locationsText": "Tokyo", "externalPath": "/job/Unfinished"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "Example",
                "Unfinished",
                "https://example.wd1.myworkdayjobs.com/Careers/job/Unfinished",
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.close()

            rows = snapshot_candidates(
                ledger_path=ledger_path,
                sources=(source,),
                fetch_jobs=lambda _source: jobs,
            )

        self.assertEqual([row["title"] for row in rows], ["Unfinished", "Fresh"])

        with tempfile.TemporaryDirectory() as directory:
            rows = snapshot_candidates(
                ledger_path=Path(directory) / "ledger.sqlite3",
                sources=(source,),
                fetch_jobs=lambda _source: jobs,
            )

        self.assertEqual([row["title"] for row in rows], ["Fresh", "Unfinished"])

    def test_snapshot_keeps_unfinished_first_then_interleaves_fresh_companies_to_400(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "Example",
                "Unfinished",
                "https://example.wd1.myworkdayjobs.com/Careers/job/Unfinished",
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.close()

            sources = (
                {
                    "company": "Example",
                    "host": "example.wd1.myworkdayjobs.com",
                    "site": "Careers",
                },
                {
                    "company": "Red Hat",
                    "host": "redhat.wd1.myworkdayjobs.com",
                    "site": "Careers",
                },
                {
                    "company": "Razer",
                    "host": "razer.wd1.myworkdayjobs.com",
                    "site": "Careers",
                },
            )
            jobs = {
                "example.wd1.myworkdayjobs.com": [
                    {"title": "Unfinished", "locationsText": "Tokyo", "externalPath": "/job/Unfinished"},
                    *[
                        {"title": f"Fresh Example {index}", "locationsText": "Tokyo", "externalPath": f"/job/Fresh_Example_{index}"}
                        for index in range(1, 201)
                    ],
                ],
                "redhat.wd1.myworkdayjobs.com": [
                    {"title": f"Fresh Red Hat {index}", "locationsText": "Tokyo", "externalPath": f"/job/Fresh_Red_Hat_{index}"}
                    for index in range(1, 201)
                ],
                "razer.wd1.myworkdayjobs.com": [
                    {"title": f"Fresh Razer {index}", "locationsText": "Tokyo", "externalPath": f"/job/Fresh_Razer_{index}"}
                    for index in range(1, 101)
                ],
            }
            rows = snapshot_candidates(
                ledger_path=ledger_path,
                sources=sources,
                fetch_jobs=lambda source: jobs[source["host"]],
            )

        self.assertEqual(len(rows), 400)
        self.assertEqual(
            [row["title"] for row in rows[:6]],
            [
                "Unfinished",
                "Fresh Example 1",
                "Fresh Red Hat 1",
                "Fresh Razer 1",
                "Fresh Example 2",
                "Fresh Red Hat 2",
            ],
        )

    def test_shortlist_drops_model_invented_url_and_keeps_official_rows(self):
        official = "https://a.wd1.myworkdayjobs.com/Careers/job/A"
        candidates = [{"candidate_id": "candidate-1", "url": official}]
        self.assertEqual(
            validate_shortlist(
                {"ranked_candidate_ids": ["invented", "candidate-1"]},
                candidates,
            ),
            (official,),
        )

    def test_shortlist_fails_closed_when_no_official_url_remains(self):
        with self.assertRaisesRegex(ValueError, "no official candidate ID"):
            validate_shortlist(
                {"ranked_candidate_ids": ["invented"]},
                [{"candidate_id": "candidate-1", "url": "https://a.wd1.myworkdayjobs.com/Careers/job/A"}],
            )

    def test_each_source_is_fetched_once_per_wake(self):
        calls = []
        source = {"company": "A", "host": "a.myworkdayjobs.com"}
        fetch = cached_source_fetcher(
            lambda row: calls.append(row["company"]) or [{"title": "Role"}]
        )

        self.assertEqual(fetch(source), [{"title": "Role"}])
        self.assertEqual(fetch(source), [{"title": "Role"}])
        self.assertEqual(calls, ["A"])

    def test_sources_rotate_across_companies_in_one_wake(self):
        sources = ({"company": "A"}, {"company": "B"}, {"company": "C"})
        self.assertEqual(
            [row["company"] for row in rotated_sources(sources, 1)],
            ["B", "C", "A"],
        )

    def test_same_wake_continues_after_reject_and_hold_until_qualified(self):
        decisions = iter(("rejected", "hold", "qualified"))
        discovered = []

        def discover():
            number = len(discovered) + 1
            discovered.append(number)
            return {"status": "discovered", "discovered": [{"id": number}]}

        def qualify():
            return {
                "status": "decided",
                "decision": next(decisions),
                "application_id": str(len(discovered)),
            }

        result = search_until_qualified(
            discover=discover,
            qualify=qualify,
            max_candidates=10,
        )

        self.assertEqual(discovered, [1, 2, 3])
        self.assertEqual(result["status"], "qualified")
        self.assertEqual([row["decision"] for row in result["decisions"]], [
            "rejected", "hold", "qualified"
        ])

    def test_daily_owner_searches_until_qualified_before_browser_lane(self):
        script = (
            Path(__file__).resolve().parents[1] / "scripts/run-daily.sh"
        ).read_text(encoding="utf-8")
        qualifier = "-m job_search_loop.workday_search_loop"
        browser = "-m job_search_loop.browser_agent.orchestrator"
        self.assertIn(qualifier, script)
        self.assertLess(script.index(qualifier), script.index(browser))
        self.assertNotIn("-m job_search_loop.workday_discovery", script)
        self.assertNotIn("-m job_search_loop.workday_qualification", script)

    def _row(self, root: Path) -> tuple[Path, str, Path]:
        ledger_path = root / "ledger.sqlite3"
        ledger = Ledger(ledger_path)
        application_id = ledger.add_application(
            "Example",
            "Principal Stretch Role",
            "https://example.wd5.myworkdayjobs.com/Site/job/Japan/Role_JR1",
        )
        ledger.transition(application_id, "qualified")
        ledger.transition(application_id, "materials_ready")
        ledger.close()
        memory = root / "candidate-memory.json"
        memory.write_text(json.dumps({"facts": [{"claim": "Grounded experience"}]}))
        return ledger_path, application_id, memory

    def test_fresh_snapshot_rejects_only_absent_pre_submit_workday_row(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            stale = ledger.add_application(
                "Example", "Expired", "https://example.wd1.myworkdayjobs.com/Careers/job/Japan/Expired_R1"
            )
            current = ledger.add_application(
                "Example", "Current", "https://example.wd1.myworkdayjobs.com/Careers/job/Japan/Current_R2"
            )
            for application_id in (stale, current):
                ledger.transition(application_id, "qualified")
                ledger.transition(application_id, "materials_ready")
            ledger.close()
            source = {
                "company": "Example", "host": "example.wd1.myworkdayjobs.com",
                "tenant": "example", "site": "Careers",
            }
            jobs = {
                json.dumps(source, sort_keys=True): [
                    {"title": "Current", "externalPath": "/job/Japan/Current_R2"}
                ]
            }
            receipt = reject_stale_workday_rows(ledger_path, jobs)
            ledger = Ledger(ledger_path)
            self.assertEqual(receipt[0]["application_id"], stale)
            self.assertEqual(receipt[0]["reason"], "official_listing_absent")
            self.assertEqual(ledger.current_state(stale), "rejected")
            self.assertEqual(ledger.current_state(current), "materials_ready")
            ledger.close()

    def test_failed_source_host_is_not_reconciled_as_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "Unavailable", "Live", "https://unavailable.wd1.myworkdayjobs.com/Careers/job/Japan/Live_R1"
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.close()
            source = {
                "company": "Unavailable", "host": "unavailable.wd1.myworkdayjobs.com",
                "tenant": "unavailable", "site": "Careers",
            }
            jobs_by_source = {}
            rows = snapshot_candidates(
                ledger_path=ledger_path,
                sources=(source,),
                fetch_jobs=lambda _source: (_ for _ in ()).throw(TimeoutError()),
            )
            receipt = reject_stale_workday_rows(ledger_path, jobs_by_source)
            ledger = Ledger(ledger_path)
            self.assertEqual(rows, [])
            self.assertEqual(receipt, ())
            self.assertEqual(ledger.current_state(application_id), "materials_ready")
            ledger.close()

    def test_source_site_is_part_of_stale_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "Example", "Site B Role", "https://example.wd1.myworkdayjobs.com/SiteB/job/Japan/Role_R1"
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.close()
            source_a = {
                "company": "Example", "host": "example.wd1.myworkdayjobs.com",
                "tenant": "example", "site": "SiteA",
            }
            jobs_by_source = {
                json.dumps(source_a, sort_keys=True): [
                    {"title": "Site A Role", "externalPath": "/job/Japan/Role_A1"}
                ]
            }
            receipt = reject_stale_workday_rows(ledger_path, jobs_by_source)
            ledger = Ledger(ledger_path)
            self.assertEqual(receipt, ())
            self.assertEqual(ledger.current_state(application_id), "materials_ready")
            ledger.close()

    def test_changed_workday_slug_and_location_with_same_requisition_stays_live(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "Example", "Old Role", "https://example.wd1.myworkdayjobs.com/Careers/job/Tokyo/Old_R1"
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.close()
            source = {
                "company": "Example", "host": "example.wd1.myworkdayjobs.com",
                "tenant": "example", "site": "Careers",
            }
            jobs_by_source = {
                json.dumps(source, sort_keys=True): [
                    {"title": "New Role", "externalPath": "/job/Osaka/New_Title_R1"}
                ]
            }
            receipt = reject_stale_workday_rows(ledger_path, jobs_by_source)
            ledger = Ledger(ledger_path)
            self.assertEqual(receipt, ())
            self.assertEqual(ledger.current_state(application_id), "materials_ready")
            ledger.close()

    def test_empty_successful_snapshot_does_not_reject_workday_row(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "Example", "Role", "https://example.wd1.myworkdayjobs.com/Careers/job/Japan/Role_R1"
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.close()
            source = {
                "company": "Example", "host": "example.wd1.myworkdayjobs.com",
                "tenant": "example", "site": "Careers",
            }
            jobs_by_source = {json.dumps(source, sort_keys=True): []}
            receipt = reject_stale_workday_rows(ledger_path, jobs_by_source)
            ledger = Ledger(ledger_path)
            self.assertEqual(receipt, ())
            self.assertEqual(ledger.current_state(application_id), "materials_ready")
            ledger.close()

    def test_http_failure_receipt_skips_row_and_next_live_row_qualifies_same_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, first, memory = self._row(root)
            ledger = Ledger(ledger_path)
            second = ledger.add_application(
                "Second", "Live", "https://second.wd1.myworkdayjobs.com/Careers/job/Japan/Live_R2"
            )
            ledger.transition(second, "qualified")
            ledger.transition(second, "materials_ready")
            ledger.close()
            code = "\tS22\n" + "c" * 200
            message = "  token=abc\n  " + "z" * 400
            body = io.BytesIO(json.dumps({"errorCode": code, "message": message}).encode())
            error = HTTPError(
                "https://example.invalid", 403, "Forbidden", {},
                body,
            )
            self.addCleanup(error.close)
            failure = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: (_ for _ in ()).throw(error),
                run_model=lambda _prompt: self.fail("model must not run for failed fetch"),
            )
            self.assertEqual(failure["application_id"], first)
            self.assertEqual(failure["http_status"], 403)
            self.assertEqual(failure["provider_error_code"][:3], "S22")
            self.assertEqual(len(failure["provider_error_code"]), 80)
            self.assertEqual(failure["provider_message"], "[redacted]")
            self.assertTrue(body.closed)
            success = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                excluded_application_ids=frozenset({first}),
                fetch_description=lambda _url: "Applied AI customer role in Tokyo",
                run_model=lambda _prompt: {
                    "decision": "qualified",
                    "mandatory_evidence": ["Grounded experience matches"],
                    "unsupported_gaps": [],
                    "interview_thesis": "Credible applied AI interview case",
                    "location_feasibility": "Tokyo onsite is feasible",
                    "compensation_thesis": "Unpublished and uncertain",
                    "compensation_uncertain": True,
                    "resume_variant": "business",
                },
            )
            self.assertEqual(success["application_id"], second)
            self.assertEqual(success["decision"], "qualified")

    def test_urlerror_failure_receipt_skips_row_and_next_live_row_qualifies_same_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, first, memory = self._row(root)
            ledger = Ledger(ledger_path)
            second = ledger.add_application(
                "Second", "Live", "https://second.wd1.myworkdayjobs.com/Careers/job/Japan/Live_R2"
            )
            ledger.transition(second, "qualified")
            ledger.transition(second, "materials_ready")
            ledger.close()
            failure = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: (_ for _ in ()).throw(
                    URLError("temporary network failure")
                ),
                run_model=lambda _prompt: self.fail("model must not run for failed fetch"),
            )
            self.assertEqual(failure["status"], "qualification_retryable_failure")
            self.assertEqual(failure["application_id"], first)
            self.assertEqual(failure["error"], "URLError")
            self.assertIsNone(failure["http_status"])
            self.assertIsNone(failure["provider_error_code"])
            self.assertIsNone(failure["provider_message"])
            success = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                excluded_application_ids=frozenset({first}),
                fetch_description=lambda _url: "Applied AI customer role in Tokyo",
                run_model=lambda _prompt: {
                    "decision": "qualified",
                    "mandatory_evidence": ["Grounded experience matches"],
                    "unsupported_gaps": [],
                    "interview_thesis": "Credible applied AI interview case",
                    "location_feasibility": "Tokyo onsite is feasible",
                    "compensation_thesis": "Unpublished and uncertain",
                    "compensation_uncertain": True,
                    "resume_variant": "business",
                },
            )
            self.assertEqual(success["application_id"], second)
            self.assertEqual(success["decision"], "qualified")

    def test_malformed_http_error_body_returns_receipt_and_closes_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, first, memory = self._row(root)
            body = io.BytesIO(b"{")
            error = HTTPError(
                "https://example.invalid", 403, "Forbidden", {}, body
            )
            self.addCleanup(error.close)

            failure = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: (_ for _ in ()).throw(error),
                run_model=lambda _prompt: self.fail("model must not run for failed fetch"),
            )

            self.assertEqual(failure["status"], "qualification_retryable_failure")
            self.assertEqual(failure["application_id"], first)
            self.assertEqual(failure["error"], "HTTPError")
            self.assertEqual(failure["http_status"], 403)
            self.assertIsNone(failure["provider_error_code"])
            self.assertIsNone(failure["provider_message"])
            self.assertTrue(body.closed)

    def test_unicode_http_error_body_returns_receipt_and_closes_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, first, memory = self._row(root)
            body = io.BytesIO(b"\xff")
            error = HTTPError(
                "https://example.invalid", 403, "Forbidden", {}, body
            )
            self.addCleanup(error.close)

            failure = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: (_ for _ in ()).throw(error),
                run_model=lambda _prompt: self.fail("model must not run for failed fetch"),
            )

            self.assertEqual(failure["status"], "qualification_retryable_failure")
            self.assertEqual(failure["application_id"], first)
            self.assertEqual(failure["error"], "HTTPError")
            self.assertEqual(failure["http_status"], 403)
            self.assertIsNone(failure["provider_error_code"])
            self.assertIsNone(failure["provider_message"])
            self.assertTrue(body.closed)

    def test_valueerror_failure_receipt_is_row_scoped_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, first, memory = self._row(root)
            failure = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: (_ for _ in ()).throw(
                    ValueError("  permission\n denied  ")
                ),
                run_model=lambda _prompt: self.fail("model must not run for failed fetch"),
            )
            self.assertEqual(failure["status"], "qualification_retryable_failure")
            self.assertEqual(failure["application_id"], first)
            self.assertEqual(failure["error"], "ValueError")
            self.assertIsNone(failure["http_status"])
            self.assertIsNone(failure["provider_error_code"])
            self.assertEqual(failure["provider_message"], "permission denied")

    def test_failure_receipt_identity_fields_are_compact_and_non_null(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path = root / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            company = "Company " * 100
            title = "Role " * 100
            url = "https://example.wd1.myworkdayjobs.com/Careers/job/" + "x" * 2100
            application_id = ledger.add_application(company, title, url)
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.close()
            memory = root / "candidate-memory.json"
            memory.write_text(json.dumps({"facts": [{"claim": "Grounded experience"}]}))

            failure = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: (_ for _ in ()).throw(
                    URLError("temporary network failure")
                ),
                run_model=lambda _prompt: self.fail("model must not run for failed fetch"),
            )

            self.assertIsNotNone(failure["company"])
            self.assertIsNotNone(failure["title"])
            self.assertIsNotNone(failure["canonical_url"])
            self.assertLessEqual(len(failure["company"]), 240)
            self.assertLessEqual(len(failure["title"]), 240)
            self.assertLessEqual(len(failure["canonical_url"]), 2048)

    def test_wake_cursor_passes_and_records_failed_ids_for_next_qualification(self):
        failed_ids: set[str] = set()
        observed: list[frozenset[str]] = []
        decisions = iter(
            (
                {
                    "status": "qualification_retryable_failure",
                    "application_id": "A",
                },
                {"status": "decided", "decision": "qualified", "application_id": "B"},
            )
        )

        def qualify(excluded_ids: frozenset[str]) -> dict[str, object]:
            observed.append(excluded_ids)
            return next(decisions)

        result = search_until_qualified(
            discover=lambda: {"status": "queue_present", "discovered": []},
            qualify=lambda: qualify_with_wake_cursor(qualify, failed_ids),
            max_candidates=2,
        )
        self.assertEqual(result["status"], "qualified")
        self.assertEqual(observed, [frozenset(), frozenset({"A"})])

    def test_rejected_model_decision_never_enters_browser_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, application_id, memory = self._row(root)

            result = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: "Requires unsupported principal scope",
                run_model=lambda _prompt: {
                    "decision": "rejected",
                    "mandatory_evidence": [],
                    "unsupported_gaps": ["Principal scope is unsupported"],
                    "interview_thesis": "No grounded interview case",
                    "location_feasibility": "Tokyo",
                    "compensation_thesis": "Unknown",
                    "compensation_uncertain": True,
                    "resume_variant": "business",
                },
            )

            ledger = Ledger(ledger_path)
            self.assertEqual(result["decision"], "rejected")
            self.assertFalse(ledger.workday_fit_qualified(application_id))
            self.assertEqual(ledger.current_state(application_id), "rejected")
            ledger.close()

    def test_qualified_model_decision_unlocks_only_that_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, application_id, memory = self._row(root)

            result = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: "Applied AI customer role in Tokyo",
                run_model=lambda _prompt: {
                    "decision": "qualified",
                    "mandatory_evidence": ["Grounded experience matches"],
                    "unsupported_gaps": [],
                    "interview_thesis": "Direct applied AI deployment evidence",
                    "location_feasibility": "Tokyo onsite is feasible",
                    "compensation_thesis": "Target is plausible but unpublished",
                    "compensation_uncertain": True,
                    "resume_variant": "business",
                },
            )

            ledger = Ledger(ledger_path)
            self.assertEqual(result["decision"], "qualified")
            self.assertTrue(ledger.workday_fit_qualified(application_id))
            self.assertEqual(ledger.current_state(application_id), "materials_ready")
            ledger.close()

    def test_old_rejection_is_re_evaluated_once_by_new_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, application_id, memory = self._row(root)
            ledger = Ledger(ledger_path)
            ledger.record_workday_fit_decision(
                application_id,
                "rejected",
                "a" * 64,
                policy_version="no-voluntary-skip-v5",
            )
            ledger.close()

            result = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: "Applied AI implementation role",
                run_model=lambda _prompt: {
                    "decision": "qualified",
                    "mandatory_evidence": ["Equivalent impact is grounded"],
                    "unsupported_gaps": ["Published years exceed tenure"],
                    "interview_thesis": "Credible interview case now",
                    "location_feasibility": "Tokyo",
                    "compensation_thesis": "Unpublished and uncertain",
                    "compensation_uncertain": True,
                    "resume_variant": "business",
                },
            )

            ledger = Ledger(ledger_path)
            self.assertEqual(result["decision"], "qualified")
            self.assertTrue(ledger.workday_fit_qualified(application_id))
            ledger.close()

    def test_old_qualified_is_re_evaluated_once_by_new_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, application_id, memory = self._row(root)
            ledger = Ledger(ledger_path)
            ledger.record_workday_fit_decision(
                application_id, "qualified", "a" * 64, policy_version="old-policy"
            )
            ledger.close()

            result = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: "Senior people-management role in Tokyo",
                run_model=lambda _prompt: {
                    "decision": "rejected",
                    "mandatory_evidence": ["Japan employment is feasible"],
                    "unsupported_gaps": ["Senior leadership scope is outside target"],
                    "interview_thesis": "Continue to an adequate non-senior role",
                    "location_feasibility": "Tokyo",
                    "compensation_thesis": "Unpublished",
                    "compensation_uncertain": True,
                    "resume_variant": "business",
                },
            )

            ledger = Ledger(ledger_path)
            self.assertEqual(result["decision"], "rejected")
            self.assertEqual(ledger.current_state(application_id), "rejected")
            self.assertFalse(ledger.workday_fit_qualified(application_id))
            ledger.close()

    def test_old_hold_from_unavailable_source_does_not_block_search(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path, application_id, memory = self._row(root)
            ledger = Ledger(ledger_path)
            ledger.record_workday_fit_decision(
                application_id, "hold", "a" * 64, policy_version="old-policy"
            )
            ledger.close()

            result = qualify_one(
                ledger_path=ledger_path,
                candidate_memory_path=memory,
                fetch_description=lambda _url: self.fail("must not fetch foreign source"),
                run_model=lambda _prompt: self.fail("must not run model"),
                allowed_hosts={"another.wd1.myworkdayjobs.com"},
            )

            self.assertEqual(result["status"], "no_pending_workday_fit")


if __name__ == "__main__":
    unittest.main()
