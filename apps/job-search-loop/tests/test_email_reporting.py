import hashlib
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from job_search_loop import application_reporting
from job_search_loop.email_reporting import send_email_once
from job_search_loop.ledger import Ledger
from job_search_loop.outbox import Outbox


class EmailReportingTests(unittest.TestCase):
    @staticmethod
    def _confirmed_application(ledger, root, company, received_at):
        application_id = ledger.add_application(
            company,
            "Agent Engineer",
            f"https://{company.casefold().replace(' ', '')}.wd1.myworkdayjobs.com/job/1",
        )
        ledger.transition(application_id, "qualified")
        ledger.transition(application_id, "materials_ready")
        resume = root / f"{company.casefold().replace(' ', '-')}-resume.pdf"
        resume.write_bytes(b"%PDF-1.4\nverified resume\n")
        snapshot = root / f"{company.casefold().replace(' ', '-')}-ats.json"
        snapshot.write_text(
            json.dumps(
                {
                    "version": 1,
                    "url": f"https://{company.casefold().replace(' ', '')}.wd1.myworkdayjobs.com/job/1",
                    "navigation_committed": True,
                    "frames": [
                        {
                            "url": f"https://{company.casefold().replace(' ', '')}.wd1.myworkdayjobs.com/job/1",
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
        intent_created_at = (
            datetime.fromisoformat(received_at) - timedelta(seconds=1)
        ).isoformat()
        with patch("job_search_loop.ledger._now", return_value=intent_created_at):
            intent = ledger.claim_submission(
                application_id,
                "2026-10-13",
                company,
                resume_path=resume,
                resume_sha256=hashlib.sha256(resume.read_bytes()).hexdigest(),
                ats_snapshot_path=snapshot,
                ats_snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            )
            ledger.complete_submission_verified(
                intent.intent_id,
                intent.fence,
                outcome="submit_unknown",
                evidence_sha256=hashlib.sha256(company.encode()).hexdigest(),
                evidence_class="no_authoritative_completion_ui",
            )
        receipt_id = f"receipt-{company.casefold().replace(' ', '-')}"
        ledger.reconcile_submission_confirmation(
            intent_id=intent.intent_id,
            message_id=receipt_id,
            thread_id=f"thread-{receipt_id}",
            evidence_sha256=hashlib.sha256(receipt_id.encode()).hexdigest(),
            received_at=received_at,
        )
        return application_id, receipt_id

    def test_email_receipt_notifications_skip_pre_activation_submissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger_path = root / "ledger.sqlite3"
            ledger = Ledger(ledger_path)
            old_id, _ = self._confirmed_application(
                ledger, root, "Old Company", "2026-10-12T23:59:59+00:00"
            )
            recent_id, recent_receipt = self._confirmed_application(
                ledger, root, "Recent Company", "2026-10-13T00:00:01+00:00"
            )
            ledger.close()
            calls = []

            result = application_reporting.deliver_reconciled_outcomes(
                ledger_path=ledger_path,
                outbox_path=root / "telegram.sqlite3",
                sender=None,
                email_sender=lambda **kwargs: calls.append(kwargs)
                or {"status": "sent", "message_id": "email-1"},
                email_outbox_path=root / "email.sqlite3",
                email_recipient="candidate@example.test",
                email_since="2026-10-13T00:00:00+00:00",
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["event_key"], f"application-submitted:{recent_id}:{recent_receipt}")
        self.assertEqual(calls[0]["recipient"], "candidate@example.test")
        self.assertIn("Recent Company", calls[0]["message"])
        self.assertNotIn("Old Company", calls[0]["message"])
        by_application = {row["application_id"]: row for row in result}
        self.assertEqual(by_application[old_id]["email_status"], "suppressed_before_activation")
        self.assertEqual(by_application[recent_id]["email_status"], "sent")

    def test_email_reporting_start_time_is_created_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "email-reporting-enabled.json"
            first_time = datetime(2026, 10, 13, tzinfo=timezone.utc)
            later_time = first_time + timedelta(days=1)

            first = application_reporting.ensure_email_reporting_since(path, now=first_time)
            replay = application_reporting.ensure_email_reporting_since(path, now=later_time)

            self.assertEqual(first, "2026-10-13T00:00:00+00:00")
            self.assertEqual(replay, first)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_daily_email_briefing_is_once_per_japan_day(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = Ledger(root / "ledger.sqlite3")
            ledger.close()
            summary = root / "summary.json"
            summary.write_text(json.dumps({"status": "success"}), encoding="utf-8")
            discovery = root / "discovery.json"
            discovery.write_text(
                json.dumps({"status": "no_work", "shortlist": []}), encoding="utf-8"
            )
            calls = []

            def runner(argv, **kwargs):
                calls.append((argv, kwargs))
                return subprocess.CompletedProcess(
                    argv, 0, json.dumps({"id": "daily-mail-1", "threadId": "thread-9"}), ""
                )

            def email_sender(**kwargs):
                return send_email_once(
                    **kwargs, executable="/usr/bin/gog", runner=runner
                )

            arguments = {
                "ledger_path": root / "ledger.sqlite3",
                "outbox_path": root / "telegram.sqlite3",
                "email_outbox_path": root / "email.sqlite3",
                "email_recipient": "candidate@example.test",
                "email_sender": email_sender,
                "sender": None,
                "japan_day": "2026-10-13",
                "runner_summary_path": summary,
                "discovery_path": discovery,
                "output_path": root / "wake.json",
            }
            first = application_reporting.deliver_wake_report(run_id="daily-one", **arguments)
            replay = application_reporting.deliver_wake_report(run_id="daily-two", **arguments)

            self.assertEqual(first["email_status"], "sent")
            self.assertEqual(first["email_message_id"], "daily-mail-1")
            self.assertEqual(replay["email_message_id"], "daily-mail-1")
            self.assertEqual(len(calls), 1)

    def test_gmail_ack_is_persisted_and_same_event_is_not_sent_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "reporting.sqlite3"
            calls = []
            message = "応募の送信が完了し、受領証拠を確認しました。"

            def runner(argv, **kwargs):
                calls.append((argv, kwargs))
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    json.dumps({"id": "gmail-message-123", "threadId": "gmail-thread-4"}),
                    "",
                )

            first = send_email_once(
                database=database,
                event_key="application-submitted:app-1:receipt-4",
                recipient="candidate@example.test",
                account="candidate@example.test",
                subject="[Job Hunting] Danaher — Business Account Manager",
                message=message,
                executable="/usr/bin/gog",
                runner=runner,
            )
            replay = send_email_once(
                database=database,
                event_key="application-submitted:app-1:receipt-4",
                recipient="candidate@example.test",
                account="candidate@example.test",
                subject="[Job Hunting] Danaher — Business Account Manager",
                message=message,
                executable="/usr/bin/gog",
                runner=runner,
            )

            self.assertEqual(first["status"], "sent")
            self.assertEqual(first["message_id"], "gmail-message-123")
            self.assertEqual(replay, first)
            self.assertEqual(len(calls), 1)
            argv, kwargs = calls[0]
            self.assertEqual(argv[:3], ["/usr/bin/gog", "gmail", "send"])
            self.assertIn("--no-input", argv)
            self.assertNotIn("--dry-run", argv)
            self.assertEqual(kwargs["input"], message)

            outbox = Outbox(database, channel="email")
            try:
                stored = outbox.status("application-submitted:app-1:receipt-4")
            finally:
                outbox.close()
            self.assertEqual(stored, {"status": "sent", "message_id": "gmail-message-123"})

    def test_gmail_timeout_fences_the_event_without_retrying(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "reporting.sqlite3"
            calls = []

            def runner(argv, **kwargs):
                calls.append(argv)
                raise subprocess.TimeoutExpired(argv, timeout=60)

            arguments = {
                "database": database,
                "event_key": "job-search-daily-email:2026-10-13",
                "recipient": "candidate@example.test",
                "account": "candidate@example.test",
                "subject": "[Job Hunting] Daily briefing",
                "message": "No new confirmed applications today.",
                "executable": "/usr/bin/gog",
                "runner": runner,
            }
            with self.assertRaises(RuntimeError):
                send_email_once(**arguments)

            replay = send_email_once(**arguments)

            self.assertEqual(replay["status"], "send_started")
            self.assertIsNone(replay["message_id"])
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
