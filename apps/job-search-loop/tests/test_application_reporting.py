import hashlib
import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_search_loop import telegram
from job_search_loop.ledger import Ledger
from job_search_loop.outbox import Outbox


class ApplicationReportingTests(unittest.TestCase):
    def test_terminal_report_suppresses_routine_inbox_message(self):
        reporting = importlib.import_module("job_search_loop.application_reporting")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requests = []

            def requester(**request):
                requests.append(request)
                return {"ok": True, "result": {"message_id": 701}}

            def sender(**kwargs):
                return __import__("job_search_loop.telegram", fromlist=["send_once"]).send_once(
                    **kwargs,
                    target="test-chat",
                    token="test-token",
                    requester=requester,
                )

            first = reporting.deliver_terminal_report(
                outbox_path=root / "outbox.sqlite3",
                run_id="inbox-test-1",
                outcome="no_work",
                reason="no_new_messages_or_preparation",
                output_path=root / "terminal.json",
                sender=sender,
            )
            replay = reporting.deliver_terminal_report(
                outbox_path=root / "outbox.sqlite3",
                run_id="inbox-test-1",
                outcome="no_work",
                reason="no_new_messages_or_preparation",
                output_path=root / "terminal.json",
                sender=sender,
            )
            unknown = reporting.deliver_terminal_report(
                outbox_path=root / "unknown.sqlite3",
                run_id="inbox-test-2",
                outcome="failed",
                reason="runner_failed",
                output_path=root / "unknown.json",
                sender=lambda **_: (_ for _ in ()).throw(RuntimeError("offline")),
            )

            self.assertEqual(first["delivery"], "suppressed")
            self.assertEqual(replay["event_key"], "job-search-inbox:inbox-test-1")
            self.assertEqual(len(requests), 0)
            self.assertEqual(unknown["delivery"], "suppressed")
            self.assertEqual(oct((root / "terminal.json").stat().st_mode & 0o777), "0o600")

    def test_application_progress_is_suppressed_before_submission(self):
        reporting = importlib.import_module("job_search_loop.application_reporting")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path = root / "ledger.sqlite3"
            outbox_path = root / "telegram.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "Dream AI",
                "Product Manager",
                "https://dream.wd1.myworkdayjobs.com/job/1",
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            evidence = "a" * 64
            ledger.record_workday_fit_decision(
                application_id,
                decision="qualified",
                evidence_sha256=evidence,
                policy_version="test-v1",
            )
            ledger.close()
            outbox = Outbox(outbox_path)
            fit_key = f"workday-fit:{application_id}:{evidence}"
            fit_message = (
                "[Job Hunting] 応募判断\n"
                "理由: Resume evidence matches the complete JD.\n"
                "給与: Published salary meets the floor."
            )
            outbox.enqueue(fit_key, fit_message)
            fence = outbox.claim(fit_key)
            outbox.mark_send_started(fit_key, fence)
            outbox.mark_sent(fit_key, fence, "fit-100")
            outbox.close()
            calls = []

            def sender(**kwargs):
                calls.append(kwargs)
                return {"status": "sent", "message_id": "progress-101"}

            receipt = reporting.deliver_application_progress(
                ledger_path=ledger_path,
                outbox_path=outbox_path,
                application_id=application_id,
                run_id="daily-1",
                sender=sender,
            )
            self.assertEqual(receipt["status"], "suppressed")
            self.assertIsNone(receipt["message_id"])
            self.assertEqual(calls, [])
            self.assertEqual(
                receipt["event_key"],
                f"workday-application-progress:{application_id}:daily-1",
            )

    def test_wake_report_prefers_semantic_failure_over_runner_success(self):
        reporting = importlib.import_module("job_search_loop.application_reporting")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path = root / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "NVIDIA",
                "AI Role",
                "https://nvidia.wd5.myworkdayjobs.com/job/JR-semantic",
            )
            ledger.close()
            discovery = root / "workday-discovery.json"
            discovery.write_text(
                json.dumps(
                    {
                        "status": "queue_present",
                        "queued_application_ids": [application_id],
                    }
                ),
                encoding="utf-8",
            )
            result = root / "result.json"
            result.write_text(
                json.dumps(
                    {
                        "status": "transport_failed",
                        "submitted": [],
                        "submit_unknown": [],
                        "blocked": ["NVIDIA — AI Role"],
                        "report_message_id": None,
                    }
                ),
                encoding="utf-8",
            )
            summary = root / "summary.json"
            summary.write_text(
                json.dumps({"status": "success", "result_path": str(result)}),
                encoding="utf-8",
            )
            (root / "semantic-validation.json").write_text(
                json.dumps(
                    {"status": "failed", "reason": "transport_failed_without_command_failure"}
                ),
                encoding="utf-8",
            )
            calls = []

            def sender(**kwargs):
                calls.append(kwargs)
                return {"status": "sent", "message_id": "902", "event_key": "key"}

            receipt = reporting.deliver_wake_report(
                ledger_path=ledger_path,
                outbox_path=root / "outbox.sqlite3",
                run_id="daily-semantic",
                japan_day="2026-08-24",
                runner_summary_path=summary,
                discovery_path=discovery,
                output_path=root / "wake-report.json",
                sender=sender,
            )

            self.assertEqual(receipt["outcome"], "failed")
            self.assertEqual(
                receipt["reason"],
                "transport_failed_without_command_failure",
            )
            self.assertIn("今回の処理を完了できませんでした", calls[0]["message"])
            self.assertNotIn("transport_failed_without_command_failure", calls[0]["message"])

    def test_blocked_queue_with_zero_receipts_is_not_reported_as_success(self):
        reporting = importlib.import_module("job_search_loop.application_reporting")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = Ledger(root / "ledger.sqlite3")
            application_id = ledger.add_application(
                "Example", "Marketing Manager", "https://example.wd1.myworkdayjobs.com/role"
            )
            ledger.close()
            discovery = root / "workday-discovery.json"
            discovery.write_text(
                json.dumps({"status": "queue_present", "queued_application_ids": [application_id]}),
                encoding="utf-8",
            )
            result_path = root / "result.json"
            result_path.write_text(
                json.dumps({
                    "status": "blocked_before_queue_complete",
                    "submitted": [],
                    "submit_unknown": [],
                    "blocked": [f"row-{n}" for n in range(7)],
                    "report_message_id": "report-1",
                }),
                encoding="utf-8",
            )
            summary = root / "summary.json"
            summary.write_text(
                json.dumps({"status": "success", "result_path": str(result_path)}),
                encoding="utf-8",
            )
            messages = []
            receipt = reporting.deliver_wake_report(
                ledger_path=root / "ledger.sqlite3",
                outbox_path=root / "outbox.sqlite3",
                run_id="daily-blocked-zero-submit",
                japan_day="2026-10-13",
                runner_summary_path=summary,
                discovery_path=discovery,
                output_path=root / "wake-report.json",
                sender=lambda **kwargs: messages.append(kwargs) or {
                    "status": "sent", "message_id": "wake-1", "event_key": "event-1"
                },
            )

        self.assertEqual(receipt["outcome"], "partial")
        self.assertEqual(receipt["reason"], "blocked_before_queue_complete")
        self.assertIn("応募完了: 0件", messages[0]["message"])
        self.assertIn("未完了/保留: 7件", messages[0]["message"])
        self.assertNotIn("今回の処理を完了しました", messages[0]["message"])

    def test_queue_complete_with_blocked_rows_is_not_reported_as_success(self):
        reporting = importlib.import_module("job_search_loop.application_reporting")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = Ledger(root / "ledger.sqlite3")
            application_id = ledger.add_application(
                "Example", "Marketing Manager", "https://example.wd1.myworkdayjobs.com/role"
            )
            ledger.close()
            discovery = root / "workday-discovery.json"
            discovery.write_text(
                json.dumps({"status": "queue_present", "queued_application_ids": [application_id]}),
                encoding="utf-8",
            )
            result_path = root / "result.json"
            result_path.write_text(
                json.dumps({
                    "status": "queue_complete",
                    "submitted": [],
                    "submit_unknown": [],
                    "blocked": [f"row-{n}" for n in range(4)],
                    "report_message_id": "report-1",
                }),
                encoding="utf-8",
            )
            summary = root / "summary.json"
            summary.write_text(
                json.dumps({"status": "success", "result_path": str(result_path)}),
                encoding="utf-8",
            )
            messages = []
            receipt = reporting.deliver_wake_report(
                ledger_path=root / "ledger.sqlite3",
                outbox_path=root / "outbox.sqlite3",
                run_id="daily-queue-complete-blocked",
                japan_day="2026-10-13",
                runner_summary_path=summary,
                discovery_path=discovery,
                output_path=root / "wake-report.json",
                sender=lambda **kwargs: messages.append(kwargs) or {
                    "status": "sent", "message_id": "wake-1", "event_key": "event-1"
                },
            )

        self.assertEqual(receipt["outcome"], "partial")
        self.assertEqual(receipt["reason"], "row_blocked")
        self.assertIn("応募完了: 0件", messages[0]["message"])
        self.assertIn("未完了/保留: 4件", messages[0]["message"])
        self.assertNotIn("今回の処理を完了しました", messages[0]["message"])

    def test_queue_complete_with_unknown_submission_reconciles_without_retry(self):
        reporting = importlib.import_module("job_search_loop.application_reporting")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = Ledger(root / "ledger.sqlite3")
            application_id = ledger.add_application(
                "Example", "Marketing Manager", "https://example.wd1.myworkdayjobs.com/role"
            )
            ledger.close()
            discovery = root / "workday-discovery.json"
            discovery.write_text(
                json.dumps({"status": "queue_present", "queued_application_ids": [application_id]}),
                encoding="utf-8",
            )
            result_path = root / "result.json"
            result_path.write_text(
                json.dumps({
                    "status": "queue_complete",
                    "submitted": [],
                    "submit_unknown": ["row-unknown"],
                    "blocked": [],
                    "report_message_id": "report-1",
                }),
                encoding="utf-8",
            )
            summary = root / "summary.json"
            summary.write_text(
                json.dumps({"status": "success", "result_path": str(result_path)}),
                encoding="utf-8",
            )
            messages = []
            receipt = reporting.deliver_wake_report(
                ledger_path=root / "ledger.sqlite3",
                outbox_path=root / "outbox.sqlite3",
                run_id="daily-queue-complete-unknown",
                japan_day="2026-10-13",
                runner_summary_path=summary,
                discovery_path=discovery,
                output_path=root / "wake-report.json",
                sender=lambda **kwargs: messages.append(kwargs) or {
                    "status": "sent", "message_id": "wake-1", "event_key": "event-1"
                },
            )

        self.assertEqual(receipt["outcome"], "partial")
        self.assertEqual(receipt["reason"], "submit_unknown")
        self.assertEqual(receipt["next_action"], "reconcile_submission_receipts")
        self.assertIn("送信結果不明: 1件", messages[0]["message"])
        self.assertNotIn("もう一度応募します", messages[0]["message"])

    def test_fit_decisions_are_suppressed_before_submission(self):
        reporting = importlib.import_module("job_search_loop.application_reporting")
        calls = []

        with tempfile.TemporaryDirectory() as directory:
            outbox = Path(directory) / "outbox.sqlite3"
            for status in ("rejected", "hold", "qualified"):
                with self.subTest(status=status):
                    application_id = f"application-{status}"
                    result = reporting.deliver_fit_decision(
                        decision={
                            "decision": status,
                            "application_id": application_id,
                            "evidence_sha256": "a" * 64,
                        },
                        outbox_path=outbox,
                        sender=lambda **kwargs: calls.append(kwargs),
                    )
                    self.assertEqual(result["status"], "suppressed")
                    self.assertIsNone(result["message_id"])
                    self.assertEqual(
                        result["event_key"],
                        f"workday-fit:{application_id}:{'a' * 64}",
                    )

        self.assertEqual(calls, [])

    def test_ineligible_outcome_is_suppressed_without_telegram(self):
        from job_search_loop.browser_agent.contracts import QueueRowReceiptV1
        from job_search_loop.browser_agent.outcome_reporting import send_hourly_outcomes

        calls = []
        with tempfile.TemporaryDirectory() as directory:
            result = send_hourly_outcomes(
                database=Path(directory) / "outbox.sqlite3",
                wake_id="wake-ineligible",
                receipts=(QueueRowReceiptV1("application-1", "Example", "Role", "ineligible"),),
                evidence_classes={},
                sender=lambda **kwargs: calls.append(kwargs),
            )

        self.assertEqual(result, {"status": "suppressed", "message_id": None})
        self.assertEqual(calls, [])

    def test_submitted_hourly_outcome_is_suppressed_without_telegram_setup(self):
        from job_search_loop.browser_agent.contracts import QueueRowReceiptV1
        from job_search_loop.browser_agent.outcome_reporting import send_hourly_outcomes

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            telegram_env = root / "telegram.env"
            telegram_env.write_text("", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "JOB_SEARCH_TELEGRAM_ENV": str(telegram_env),
                    "TELEGRAM_BOT_TOKEN": "",
                    "JOB_SEARCH_TELEGRAM_CHAT_ID": "",
                },
                clear=False,
            ):
                result = send_hourly_outcomes(
                    database=root / "outbox.sqlite3",
                    wake_id="wake-submitted-no-telegram",
                    receipts=(QueueRowReceiptV1("application-1", "Example", "Role", "submitted"),),
                    evidence_classes={"application-1": "authoritative_receipt_email"},
                )

        self.assertEqual(result, {"status": "suppressed", "message_id": None})
    def test_quota_failed_wake_reports_queued_company_role_and_next_action(self):
        reporting = importlib.import_module("job_search_loop.application_reporting")
        deliver = getattr(reporting, "deliver_wake_report", None)
        self.assertIsNotNone(deliver)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path = root / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "NVIDIA",
                "Senior AI Partner Manager",
                "https://nvidia.wd5.myworkdayjobs.com/job/JR-test",
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ledger.close()
            discovery = root / "workday-discovery.json"
            discovery.write_text(
                json.dumps(
                    {
                        "status": "queue_present",
                        "queued_application_ids": [application_id],
                    }
                ),
                encoding="utf-8",
            )
            attempts = root / "attempts.jsonl"
            attempts.write_text(
                json.dumps(
                    {"error_class": "transient_quota", "adapter_error": None}
                )
                + "\n",
                encoding="utf-8",
            )
            summary = root / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "attempts_path": str(attempts),
                    }
                ),
                encoding="utf-8",
            )
            calls = []

            def sender(**kwargs):
                calls.append(kwargs)
                return {
                    "status": "sent",
                    "message_id": "wake-901",
                    "event_key": "job-search-daily:test",
                }

            output = root / "wake-report.json"
            receipt = deliver(
                ledger_path=ledger_path,
                outbox_path=root / "telegram.sqlite3",
                run_id="daily-test",
                japan_day="2026-08-24",
                runner_summary_path=summary,
                discovery_path=discovery,
                output_path=output,
                sender=sender,
            )

            message = calls[0]["message"]
            self.assertTrue(message.startswith("[Job Hunting] 24時間レポート"))
            self.assertNotIn(":::", message)
            self.assertIn("会社: NVIDIA", message)
            self.assertIn("求人: Senior AI Partner Manager", message)
            self.assertIn("今回の処理を完了できませんでした", message)
            self.assertIn("応募完了: 0件", message)
            self.assertNotIn("transient_quota", message)
            self.assertIn("ユーザーの操作は必要ありません", message)
            self.assertEqual(receipt["message_id"], "wake-901")
            self.assertEqual(receipt, json.loads(output.read_text(encoding="utf-8")))
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_reconciled_receipt_sends_authoritative_submitted_correction_once(self):
        reporting = importlib.import_module("job_search_loop.application_reporting")
        deliver = reporting.deliver_reconciled_outcomes
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = Ledger(root / "ledger.sqlite3")
            application_id = ledger.add_application(
                "Dream AI", "Agent Engineer", "https://dream.wd1.myworkdayjobs.com/job/1"
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            resume = root / "resume.pdf"
            resume.write_bytes(b"%PDF-1.4\nresume\n")
            snapshot = root / "ats.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "url": "https://dream.wd1.myworkdayjobs.com/job/1",
                        "navigation_committed": True,
                        "frames": [
                            {
                                "url": "https://dream.wd1.myworkdayjobs.com/job/1",
                                "controls": [
                                    {"tag": "input", "type": "email"},
                                    {"tag": "input", "type": "file"},
                                    {"tag": "button", "type": "submit", "text": "Submit"},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            intent = ledger.claim_submission(
                application_id,
                "2026-08-23",
                "payload",
                resume_path=resume,
                resume_sha256=hashlib.sha256(resume.read_bytes()).hexdigest(),
                ats_snapshot_path=snapshot,
                ats_snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            )
            ledger.complete_submission_verified(
                intent.intent_id,
                intent.fence,
                outcome="submit_unknown",
                evidence_sha256="f" * 64,
                evidence_class="no_authoritative_completion_ui",
            )
            ledger.reconcile_submission_confirmation(
                intent_id=intent.intent_id,
                message_id="gmail-1",
                thread_id="thread-1",
                evidence_sha256="e" * 64,
                received_at="2099-01-01T00:00:00+00:00",
            )
            ledger.close()
            calls = []

            def fake_sender(**kwargs):
                calls.append(kwargs)
                return {"status": "sent", "message_id": "903"}

            result = deliver(
                ledger_path=root / "ledger.sqlite3",
                outbox_path=root / "telegram.sqlite3",
                sender=fake_sender,
            )

            self.assertEqual(result[0]["message_id"], "903")
            self.assertEqual(
                calls[0]["event_key"],
                f"application-submitted:{application_id}:gmail-1",
            )
            self.assertTrue(calls[0]["message"].startswith("[Job Hunting] 応募完了"))
            self.assertNotIn(":::", calls[0]["message"])
            self.assertIn("会社: Dream AI", calls[0]["message"])
            self.assertIn("求人: Agent Engineer", calls[0]["message"])
            self.assertIn("確認: authoritative_receipt_email", calls[0]["message"])

    def test_document_delivery_is_private_and_at_most_once(self):
        sender = getattr(telegram, "send_document_once", None)
        self.assertIsNotNone(sender)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "resume.pdf"
            source.write_bytes(b"%PDF-1.4\nresume\n")
            media_root = root / "allowed-media"
            database = root / "outbox.sqlite3"
            requests = []

            def requester(**kwargs):
                requests.append(kwargs)
                return {"ok": True, "result": {"message_id": 901}}

            first = sender(
                database=database,
                event_key="application-resume:abc",
                message="Resume used for Example — AI Engineer",
                document=source,
                media_root=media_root,
                requester=requester,
            )
            second = sender(
                database=database,
                event_key="application-resume:abc",
                message="Resume used for Example — AI Engineer",
                document=source,
                media_root=media_root,
                requester=requester,
            )

            self.assertEqual(first, {"status": "sent", "message_id": "901"})
            self.assertEqual(second, first)
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["method"], "sendDocument")
            self.assertEqual(requests[0]["document"], source.resolve())

    def test_submitted_resume_report_uses_ledger_company_role_and_url(self):
        try:
            reporting = importlib.import_module("job_search_loop.application_reporting")
        except ModuleNotFoundError:
            self.fail("job_search_loop.application_reporting is missing")
        deliver = getattr(reporting, "deliver_submitted_resumes", None)
        self.assertIsNotNone(deliver)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resume = root / "resume.pdf"
            resume.write_bytes(b"%PDF-1.4\nresume\n")
            resume_sha256 = hashlib.sha256(resume.read_bytes()).hexdigest()
            ledger_path = root / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            application_id = ledger.add_application(
                "Dream AI", "Agent Product Engineer", "https://jobs.example/dream"
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            ats_snapshot = root / "ats-snapshot.json"
            ats_snapshot.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "url": "https://jobs.example/dream",
                        "navigation_committed": True,
                        "frames": [
                            {
                                "url": "https://jobs.example/dream",
                                "controls": [
                                    {"tag": "input", "type": "email"},
                                    {"tag": "input", "type": "file"},
                                    {
                                        "tag": "button",
                                        "type": "submit",
                                        "text": "Submit Application",
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            ats_snapshot_sha256 = hashlib.sha256(
                ats_snapshot.read_bytes()
            ).hexdigest()
            intent = ledger.claim_submission(
                application_id,
                "2026-07-29",
                "payload",
                resume_path=resume,
                resume_sha256=resume_sha256,
                ats_snapshot_path=ats_snapshot,
                ats_snapshot_sha256=ats_snapshot_sha256,
            )
            ledger.complete_submission_verified(
                intent.intent_id,
                intent.fence,
                outcome="submitted",
                evidence_sha256="e" * 64,
                evidence_class="exact_completion_ui",
            )
            ledger.close()
            calls = []

            def fake_sender(**kwargs):
                calls.append(kwargs)
                return {"status": "sent", "message_id": "902"}

            result = deliver(
                ledger_path=ledger_path,
                outbox_path=root / "telegram.sqlite3",
                media_root=root / "media",
                sender=fake_sender,
            )

            self.assertEqual(len(result), 1)
            self.assertEqual(
                calls[0]["event_key"],
                f"application-resume:{application_id}:{resume_sha256}",
            )
            self.assertEqual(calls[0]["document"], resume.resolve())
            self.assertIn("Dream AI", calls[0]["message"])
            self.assertIn("Agent Product Engineer", calls[0]["message"])
            self.assertIn("https://jobs.example/dream", calls[0]["message"])
            self.assertEqual(result[0]["message_id"], "902")


if __name__ == "__main__":
    unittest.main()
