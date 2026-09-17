import hashlib
import http.server
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from job_search_loop.ledger import Ledger
from job_search_loop.mercor_learning import (
    build_learning_candidate,
    decide_change,
    evaluate_source_claim,
)
from job_search_loop.mercor_learning_sources import build_source_observation, collect_sources


BASELINE = {
    "version": 1,
    "daily_target": 2,
    "auto_apply_threshold": 75,
    "compensation_floor_jpy": 5_500_000,
}
REPLAY_CASES = [
    {"case_id": "eligible-74", "score": 74, "hard_eligible": True},
    {"case_id": "eligible-82", "score": 82, "hard_eligible": True},
    {"case_id": "hard-reject-99", "score": 99, "hard_eligible": False},
]


class LearningPassTests(unittest.TestCase):
    def test_collect_sources_keeps_transport_metadata_out_of_candidate_builder(self):
        import job_search_loop.mercor_learning_sources as sources

        def fake_run(command, *, timeout=30):
            if command[0].endswith("crwl"):
                return 0, "Navigate to Explore; Submit Application; Resume Later", ""
            if command[0].endswith("gh"):
                return 0, json.dumps([{
                    "fullName": "example/mercor-jobs",
                    "url": "https://github.com/example/mercor-jobs",
                    "description": "listing index",
                }]), ""
            return 2, "", "no x tab"

        with patch.object(sources, "_run", side_effect=fake_run), patch.object(
            sources.Path, "is_file", return_value=False
        ):
            result = collect_sources(
                query="Mercor Japanese AI evaluator application",
                observed_at="2026-09-17T11:30:00Z",
            )
        self.assertEqual(result["source_count"], 3)
        self.assertEqual(result["income_receipts_promoted"], 0)

    def test_official_source_requires_expected_document_markers(self):
        import job_search_loop.mercor_learning_sources as sources

        def fake_run(command, *, timeout=30):
            if command[0].endswith("crwl"):
                return 0, "transport succeeded but document body is absent", ""
            return 2, "", "source unavailable"

        with patch.object(sources, "_run", side_effect=fake_run), patch.object(
            sources.Path, "is_file", return_value=False
        ):
            result = collect_sources(observed_at="2026-09-17T11:30:00Z")
        official = result["sources"][0]
        self.assertTrue(official["source_unavailable"])
        self.assertEqual(official["evidence_grade"], "unavailable")

    def test_learning_wake_collects_bounded_mercor_sources_before_strategy_run(self):
        script = (Path(__file__).resolve().parents[1] / "scripts" / "run-learning.sh").read_text()
        self.assertIn("mercor_learning_sources collect", script)
        self.assertIn("mercor-learning-sources.json", script)
        self.assertIn("--query", script)

    def test_source_observation_keeps_provenance_and_unavailable_surfaces_explicit(self):
        source = build_source_observation(
            source_url="https://talent.docs.mercor.com/how-to/apply",
            source_kind="official_guidance",
            observation="Mercor documents Job fit and Newest filters.",
            hypothesis="Reviewing page one through four keeps plausible roles in the queue.",
            target_stage="application",
            one_variable="listing_order",
            strategy_version="mercor-fit-evidence-v1",
            baseline_cohort={"resolved": 0},
            proposed_change={"listing_order": "page_one_to_four"},
            published_at=None,
            observed_at="2026-09-17T11:30:00Z",
            author="Mercor",
            claimed_outcome="No hiring or payout claim; guidance only.",
            evidence_grade="official",
            source_unavailable=False,
        )
        self.assertEqual(source["source_kind"], "official_guidance")
        self.assertIsNone(source["published_at"])
        self.assertEqual(source["author"], "Mercor")
        self.assertFalse(source["source_unavailable"])

        unavailable = build_source_observation(
            source_url="https://html.duckduckgo.com/html/?q=mercor",
            source_kind="first_person",
            observation="Search surface returned a bot challenge.",
            hypothesis="Search unavailable; retain the official guidance hypothesis.",
            target_stage="application",
            one_variable="listing_order",
            strategy_version="mercor-fit-evidence-v1",
            baseline_cohort={"resolved": 0},
            proposed_change={"listing_order": "page_one_to_four"},
            published_at=None,
            observed_at="2026-09-17T11:30:00Z",
            author="",
            claimed_outcome="",
            evidence_grade="unavailable",
            source_unavailable=True,
        )
        self.assertTrue(unavailable["source_unavailable"])
        self.assertEqual(unavailable["evidence_grade"], "unavailable")

    def test_external_claim_never_becomes_income_without_official_receipt(self):
        result = evaluate_source_claim({
            "source_kind": "marketing",
            "source_url": "https://example.com/post",
            "claimed_income_usd": 10000,
        })
        self.assertEqual(result["verified_income_usd"], 0)
        self.assertEqual(result["evidence_grade"], "hypothesis_only")

    def test_only_verified_official_receipt_contributes_income(self):
        result = evaluate_source_claim({
            "source_kind": "official_receipt",
            "claimed_income_usd": 125.50,
            "provider": "mercor",
            "receipt_status": "received",
            "verified": True,
            "provider_receipt_id": "earnings-1",
            "evidence_ref": "earnings-readback.json",
            "evidence_sha256": "a" * 64,
        })
        self.assertEqual(result["verified_income_usd"], 125.50)
        self.assertEqual(result["evidence_grade"], "official_receipt")

    def test_small_cohorts_are_insufficient_for_a_strategy_change(self):
        result = decide_change(
            before=[{"stage": "submitted"}],
            after=[{"stage": "offer"}],
        )
        self.assertEqual(result["decision"], "insufficient_evidence")

    def test_explicit_negative_outcomes_are_resolved_for_revert_decision(self):
        before = [{"stage": "rejected", "evidence_grade": "official", "evidence_ref": f"before-{i}"} for i in range(5)]
        after = [{"stage": "offer", "evidence_grade": "official", "evidence_ref": f"after-{i}"} for i in range(5)]
        result = decide_change(before=before, after=after)
        self.assertEqual(result["decision"], "keep")
        self.assertEqual(result["before_resolved"], 5)

    def test_learning_candidate_changes_one_strategy_variable(self):
        candidate = build_learning_candidate(
            source_url="https://talent.docs.mercor.com/how-to/apply",
            source_kind="official_guidance",
            observation="Mercor recommends the Job fit and Newest views.",
            hypothesis="Job-fit ordering will increase offer-stage conversion.",
            target_stage="offer",
            one_variable="listing_order",
            strategy_version="mercor-fit-evidence-v1",
            baseline_cohort={"resolved": 12, "strategy_version": "v0"},
            proposed_change={"listing_order": "job_fit_then_newest"},
        )
        self.assertEqual(candidate["one_variable"], "listing_order")
        self.assertEqual(list(candidate["proposed_change"]), ["listing_order"])
        with self.assertRaisesRegex(ValueError, "exactly one variable"):
            build_learning_candidate(
                source_url="https://talent.docs.mercor.com/how-to/apply",
                source_kind="official_guidance",
                observation="observation",
                hypothesis="hypothesis",
                target_stage="offer",
                one_variable="listing_order",
                strategy_version="v1",
                baseline_cohort={"resolved": 12},
                proposed_change={"listing_order": "job_fit", "copy": "short"},
            )

    def _module(self):
        try:
            from job_search_loop import learning
        except ImportError:
            self.fail("job_search_loop.learning is missing")
        return learning

    def _new_driver(self, root: Path):
        learning = self._module()
        ledger = Ledger(root / "ledger.sqlite3")
        driver = learning.LearningDriver(
            ledger,
            baseline_strategy=BASELINE,
            replay_cases=REPLAY_CASES,
        )
        return learning, ledger, driver

    def _seed_outcomes(
        self,
        ledger: Ledger,
        generation_id: str,
        *,
        prefix: str,
        positive: int,
        resolved: int = 10,
    ) -> None:
        for index in range(resolved):
            application_id = ledger.add_attributed_application(
                "Held-out Employer",
                "Applied AI Engineer",
                f"https://jobs.example.com/{prefix}-{index}",
                strategy_generation_id=generation_id,
                source="official_ats",
                query_family="held-out",
                rank_config={"threshold": 75},
                role_family="applied_ai",
                material_variant="engineering_en_v2",
                message_variant="none",
                model_route="codex",
                prompt_sha256="a" * 64,
                material_sha256="b" * 64,
            )
            disposition = "positive" if index < positive else "negative"
            ledger.record_funnel_outcome(
                application_id=application_id,
                funnel_stage="interview",
                disposition=disposition,
                evidence_source="gmail",
                evidence_sha256=hashlib.sha256(
                    f"{prefix}-{index}".encode("utf-8")
                ).hexdigest(),
                occurred_at=f"2026-07-{index + 1:02d}T00:00:00+00:00",
                observed_at="2026-07-30T00:00:00+00:00",
                observation_policy_version=(
                    "interview-window-v1" if disposition == "negative" else None
                ),
            )

    def test_first_pass_bootstraps_one_safe_candidate_and_replay_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            _, ledger, driver = self._new_driver(Path(directory))

            report = driver.run()
            status = driver.status()
            ledger.close()

            self.assertEqual(report["decision"], "inconclusive")
            self.assertEqual(report["reason"], "insufficient_resolved_applications")
            self.assertEqual(status["active_strategy"], BASELINE)
            self.assertEqual(status["candidate_strategy"]["auto_apply_threshold"], 80)
            self.assertEqual(status["changed_field"], "auto_apply_threshold")
            self.assertEqual(status["replay"]["violations"], 0)
            self.assertEqual(status["replay"]["case_count"], 3)
            self.assertRegex(status["replay"]["manifest_sha256"], r"^[a-f0-9]{64}$")

    def test_assignment_is_stable_and_reaches_both_experiment_arms(self):
        with tempfile.TemporaryDirectory() as directory:
            _, ledger, driver = self._new_driver(Path(directory))
            driver.run()

            first = driver.assign("application-key-7")
            second = driver.assign("application-key-7")
            assignments = [driver.assign(f"application-key-{index}") for index in range(64)]
            status = driver.status()
            ledger.close()

            self.assertEqual(first, second)
            self.assertEqual({row["arm"] for row in assignments}, {"baseline", "candidate"})
            valid_generations = {
                status["active_generation_id"],
                status["candidate_generation_id"],
            }
            self.assertTrue(
                all(row["strategy_generation_id"] in valid_generations for row in assignments)
            )

    def test_insufficient_snapshot_is_idempotent_and_keeps_experiment_open(self):
        with tempfile.TemporaryDirectory() as directory:
            _, ledger, driver = self._new_driver(Path(directory))

            first = driver.run()
            second = driver.run()
            decision_count = ledger.connection.execute(
                "SELECT COUNT(*) FROM learning_decisions"
            ).fetchone()[0]
            status = driver.status()
            ledger.close()

            self.assertEqual(second, first)
            self.assertEqual(decision_count, 1)
            self.assertIsNotNone(status["experiment_id"])
            self.assertEqual(status["active_generation_id"], first["baseline_generation_id"])

    def test_promote_atomically_advances_active_pointer_after_separated_intervals(self):
        with tempfile.TemporaryDirectory() as directory:
            _, ledger, driver = self._new_driver(Path(directory))
            initial = driver.run()
            self._seed_outcomes(
                ledger,
                initial["baseline_generation_id"],
                prefix="baseline-promote",
                positive=0,
            )
            self._seed_outcomes(
                ledger,
                initial["candidate_generation_id"],
                prefix="candidate-promote",
                positive=10,
            )

            promoted = driver.run()
            status = driver.status()
            decision = ledger.connection.execute(
                """
                SELECT active_before_generation_id, active_after_generation_id
                FROM learning_decisions
                WHERE decision_id = ?
                """,
                (promoted["decision_id"],),
            ).fetchone()
            ledger.close()

            self.assertEqual(promoted["decision"], "promote")
            self.assertEqual(
                status["active_generation_id"], initial["candidate_generation_id"]
            )
            self.assertIsNone(status["experiment_id"])
            self.assertEqual(
                tuple(decision),
                (
                    initial["baseline_generation_id"],
                    initial["candidate_generation_id"],
                ),
            )

    def test_resolved_overlapping_intervals_close_inconclusive_on_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            _, ledger, driver = self._new_driver(Path(directory))
            initial = driver.run()
            self._seed_outcomes(
                ledger,
                initial["baseline_generation_id"],
                prefix="baseline-overlap",
                positive=5,
            )
            self._seed_outcomes(
                ledger,
                initial["candidate_generation_id"],
                prefix="candidate-overlap",
                positive=6,
            )

            result = driver.run()
            status = driver.status()
            ledger.close()

            self.assertEqual(result["decision"], "inconclusive")
            self.assertEqual(result["reason"], "confidence_intervals_overlap")
            self.assertEqual(
                status["active_generation_id"], initial["baseline_generation_id"]
            )
            self.assertIsNone(status["experiment_id"])

    def test_closed_inconclusive_candidate_is_not_reopened_for_same_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            _, ledger, driver = self._new_driver(Path(directory))
            initial = driver.run()
            self._seed_outcomes(
                ledger,
                initial["baseline_generation_id"],
                prefix="baseline-next",
                positive=5,
            )
            self._seed_outcomes(
                ledger,
                initial["candidate_generation_id"],
                prefix="candidate-next",
                positive=6,
            )
            closed = driver.run()

            next_result = driver.run()
            status = driver.status()
            ledger.close()

            self.assertEqual(closed["reason"], "confidence_intervals_overlap")
            self.assertNotEqual(next_result["experiment_id"], closed["experiment_id"])
            self.assertEqual(status["candidate_strategy"]["auto_apply_threshold"], 85)
            self.assertEqual(
                next_result["reason"], "insufficient_resolved_applications"
            )

    def test_verified_safety_violation_rolls_back_before_sample_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            _, ledger, driver = self._new_driver(Path(directory))
            initial = driver.run()
            driver.record_candidate_execution(
                outcome="safety_violation",
                evidence_sha256="c" * 64,
                occurred_at="2026-07-30T01:00:00+00:00",
            )

            result = driver.run()
            status = driver.status()
            ledger.close()

            self.assertEqual(result["decision"], "rollback")
            self.assertEqual(result["reason"], "verified_safety_violation")
            self.assertEqual(
                status["active_generation_id"], initial["baseline_generation_id"]
            )
            self.assertIsNone(status["experiment_id"])

    def test_three_consecutive_candidate_failures_roll_back_and_success_resets_streak(self):
        with tempfile.TemporaryDirectory() as directory:
            _, ledger, driver = self._new_driver(Path(directory))
            first_experiment = driver.run()
            for index, outcome in enumerate(
                ("failure", "failure", "success", "failure", "failure")
            ):
                driver.record_candidate_execution(
                    outcome=outcome,
                    evidence_sha256=f"{index + 1:064x}",
                    occurred_at=f"2026-07-30T0{index}:00:00+00:00",
                )
            not_rolled_back = driver.run()
            self.assertEqual(not_rolled_back["decision"], "inconclusive")
            self.assertEqual(driver.status()["candidate_failure_streak"], 2)

            driver.record_candidate_execution(
                outcome="failure",
                evidence_sha256="f" * 64,
                occurred_at="2026-07-30T06:00:00+00:00",
            )
            rolled_back = driver.run()
            status = driver.status()
            ledger.close()

            self.assertEqual(rolled_back["decision"], "rollback")
            self.assertEqual(
                rolled_back["reason"], "three_consecutive_candidate_failures"
            )
            self.assertEqual(
                status["active_generation_id"],
                first_experiment["baseline_generation_id"],
            )
            self.assertIsNone(status["experiment_id"])

    def test_decision_and_execution_receipts_are_database_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            _, ledger, driver = self._new_driver(Path(directory))
            report = driver.run()
            driver.record_candidate_execution(
                outcome="success",
                evidence_sha256="d" * 64,
                occurred_at="2026-07-30T01:00:00+00:00",
            )
            event_id = ledger.connection.execute(
                "SELECT event_id FROM learning_execution_events"
            ).fetchone()[0]

            with self.assertRaises(sqlite3.IntegrityError):
                ledger.connection.execute(
                    "UPDATE learning_decisions SET decision='promote' WHERE decision_id=?",
                    (report["decision_id"],),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                ledger.connection.execute(
                    "DELETE FROM learning_execution_events WHERE event_id=?",
                    (event_id,),
                )
            ledger.close()

    def test_stale_active_pointer_fences_decision_instead_of_overwriting_race(self):
        with tempfile.TemporaryDirectory() as directory:
            _, ledger, driver = self._new_driver(Path(directory))
            initial = driver.run()
            driver.record_candidate_execution(
                outcome="failure",
                evidence_sha256="e" * 64,
                occurred_at="2026-07-30T01:00:00+00:00",
            )
            ledger.connection.execute(
                f"""
                CREATE TRIGGER simulate_learning_pointer_race
                BEFORE INSERT ON learning_decisions
                BEGIN
                    UPDATE strategy_learning_control
                    SET active_generation_id =
                        '{initial["candidate_generation_id"]}'
                    WHERE scope = 'default';
                END
                """
            )

            with self.assertRaisesRegex(RuntimeError, "changed during decision"):
                driver.run()
            control = ledger.connection.execute(
                """
                SELECT active_generation_id, experiment_id
                FROM strategy_learning_control
                WHERE scope = 'default'
                """
            ).fetchone()
            ledger.close()

            self.assertEqual(
                tuple(control),
                (
                    initial["baseline_generation_id"],
                    initial["experiment_id"],
                ),
            )

    def test_learning_report_delivery_is_content_addressed_and_at_most_once(self):
        learning = self._module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, ledger, driver = self._new_driver(root)
            report = driver.run()
            ledger.close()
            requests = []

            def requester(**kwargs):
                requests.append(kwargs)
                return {"ok": True, "result": {"message_id": "learning-901"}}

            first = learning.deliver_learning_report(
                report,
                database=root / "telegram.sqlite3",
                requester=requester,
            )
            second = learning.deliver_learning_report(
                report,
                database=root / "telegram.sqlite3",
                requester=requester,
            )

            self.assertEqual(first["status"], "sent")
            self.assertEqual(first["message_id"], "learning-901")
            self.assertEqual(second, first)
            self.assertEqual(len(requests), 1)
            self.assertNotIn("Held-out Employer", json.dumps(report))

    def test_resident_script_writes_private_receipt_and_reuses_telegram_ack(self):
        app_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class Handler(http.server.BaseHTTPRequestHandler):
                calls = 0

                def do_POST(self):
                    type(self).calls += 1
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        b'{"ok":true,"result":{"message_id":"learning-script-902"}}'
                    )

                def log_message(self, format, *args):
                    pass

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            env = {
                **os.environ,
                "HOME": str(root / "home"),
                "XDG_STATE_HOME": str(root / "state"),
                "JOB_SEARCH_STATE_ROOT": str(root / "job-state"),
                "JOB_SEARCH_PYTHON": sys.executable,
                "TELEGRAM_BOT_API_BASE_URL": (
                    f"http://127.0.0.1:{server.server_port}/bot"
                ),
                "TELEGRAM_BOT_TOKEN": "test-token",
                "JOB_SEARCH_TELEGRAM_CHAT_ID": "test-chat",
                "MERCOR_LEARNING_SOURCES_SKIP": "1",
            }

            first = subprocess.run(
                ["/bin/zsh", str(app_root / "scripts" / "run-learning.sh")],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            second = subprocess.run(
                ["/bin/zsh", str(app_root / "scripts" / "run-learning.sh")],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            reports = sorted(
                (root / "job-state" / "evidence").glob(
                    "learning-*/learning-decision.json"
                )
            )
            summaries = sorted(
                (root / "job-state" / "evidence").glob(
                    "learning-*/summary.json"
                )
            )
            self.assertEqual(len(reports), 2)
            self.assertEqual(len(summaries), 2)
            self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in reports))
            first_report = json.loads(reports[0].read_text(encoding="utf-8"))
            second_report = json.loads(reports[1].read_text(encoding="utf-8"))
            self.assertEqual(first_report["decision_id"], second_report["decision_id"])
            self.assertEqual(first_report["decision"], "inconclusive")
            self.assertTrue(
                all(
                    json.loads(path.read_text(encoding="utf-8"))["status"]
                    == "success"
                    for path in summaries
                )
            )
            self.assertEqual(Handler.calls, 1)


if __name__ == "__main__":
    unittest.main()
