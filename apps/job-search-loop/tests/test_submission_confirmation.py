import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from job_search_loop.ledger import Ledger
from job_search_loop.state import InvalidTransition
from job_search_loop.submission_confirmation import (
    _gmail_confirmation_threads,
    reconcile_confirmation_threads,
)


class SubmissionConfirmationTests(unittest.TestCase):
    def _unknown_submission(
        self,
        root: Path,
        *,
        company: str = "Dream AI",
        title: str = "Agent Product Engineer",
        url: str = (
            "https://jobs.ashbyhq.com/dream/"
            "agent-product-engineer/application"
        ),
        outcome: str = "submit_unknown",
    ) -> tuple[Ledger, str, str]:
        ledger = Ledger(root / "ledger.sqlite3")
        application_id = ledger.add_application(
            company,
            title,
            url,
        )
        ledger.transition(application_id, "qualified")
        ledger.transition(application_id, "materials_ready")

        resume = root / "resume.pdf"
        resume.write_bytes(b"%PDF-1.4\nresume\n")
        resume_sha256 = hashlib.sha256(resume.read_bytes()).hexdigest()
        snapshot = root / "ats-snapshot.json"
        snapshot.write_text(
            json.dumps(
                {
                    "version": 1,
                    "url": url,
                    "navigation_committed": True,
                    "frames": [
                        {
                            "url": url,
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
        snapshot_sha256 = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        intent = ledger.claim_submission(
            application_id,
            "2026-07-29",
            "payload",
            resume_path=resume,
            resume_sha256=resume_sha256,
            ats_snapshot_path=snapshot,
            ats_snapshot_sha256=snapshot_sha256,
        )
        ledger.complete_submission_verified(
            intent.intent_id,
            intent.fence,
            outcome=outcome,
            evidence_sha256="e" * 64,
            evidence_class="rendered_validation_rejection" if outcome == "not_submitted" else "no_authoritative_completion_ui",
        )
        return ledger, application_id, intent.intent_id

    def test_late_confirmation_promotes_every_row_once_without_resubmit(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger, application_id, intent_id = self._unknown_submission(
                Path(directory)
            )
            received_at = (
                datetime.now(timezone.utc) + timedelta(minutes=1)
            ).isoformat()

            first = ledger.reconcile_submission_confirmation(
                intent_id=intent_id,
                message_id="gmail-message-1",
                thread_id="gmail-thread-1",
                evidence_sha256="a" * 64,
                received_at=received_at,
            )
            second = ledger.reconcile_submission_confirmation(
                intent_id=intent_id,
                message_id="gmail-message-1",
                thread_id="gmail-thread-1",
                evidence_sha256="a" * 64,
                received_at=received_at,
            )

            self.assertEqual(first, "reconciled")
            self.assertEqual(second, "duplicate")
            self.assertEqual(
                ledger.connection.execute(
                    "SELECT current_state FROM applications WHERE id = ?",
                    (application_id,),
                ).fetchone()[0],
                "submitted",
            )
            self.assertEqual(
                ledger.connection.execute(
                    "SELECT status FROM submit_intents WHERE intent_id = ?",
                    (intent_id,),
                ).fetchone()[0],
                "submitted",
            )
            self.assertEqual(
                ledger.connection.execute(
                    "SELECT status FROM submission_attempts WHERE intent_id = ?",
                    (intent_id,),
                ).fetchone()[0],
                "submitted",
            )
            self.assertEqual(
                ledger.connection.execute(
                    "SELECT status FROM daily_slots WHERE application_id = ?",
                    (application_id,),
                ).fetchone()[0],
                "submitted",
            )
            self.assertEqual(
                ledger.connection.execute(
                    "SELECT COUNT(*) FROM submission_confirmations"
                ).fetchone()[0],
                1,
            )
            transitions = ledger.connection.execute(
                """
                SELECT from_state, to_state
                FROM events
                WHERE application_id = ?
                ORDER BY created_at, rowid
                """,
                (application_id,),
            ).fetchall()
            self.assertEqual(
                [tuple(row) for row in transitions][-1],
                ("submit_unknown", "submitted"),
            )
            outcomes = ledger.funnel_outcomes(application_id)
            self.assertEqual(len(outcomes), 1)
            self.assertEqual(
                {
                    key: outcomes[0][key]
                    for key in (
                        "funnel_stage",
                        "disposition",
                        "evidence_source",
                        "evidence_sha256",
                        "occurred_at",
                        "observed_at",
                        "observation_policy_version",
                    )
                },
                {
                    "funnel_stage": "confirmed_application",
                    "disposition": "positive",
                    "evidence_source": "gmail",
                    "evidence_sha256": "a" * 64,
                    "occurred_at": received_at,
                    "observed_at": received_at,
                    "observation_policy_version": None,
                },
            )
            ledger.close()

    def test_hpe_online_submission_confirmation_reconciles_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, application_id, _ = self._unknown_submission(
                root,
                company="Hewlett Packard Enterprise",
                title="Service Engineer",
                url=(
                    "https://hpe.wd1.myworkdayjobs.com/External/job/"
                    "Service_Engineer"
                ),
            )
            ledger.close()
            received = datetime.now(timezone.utc) + timedelta(minutes=1)
            payload = {
                "thread": {
                    "id": "gmail-hpe-thread",
                    "messages": [
                        {
                            "id": "gmail-hpe-message",
                            "threadId": "gmail-hpe-thread",
                            "internalDate": int(received.timestamp() * 1000),
                            "headers": {
                                "from": "Hewlett Packard Enterprise <hpe@myworkday.com>",
                                "to": "candidate@example.com",
                                "subject": "Thank you for your online submission",
                            },
                            "body": (
                                "Hewlett Packard Enterprise has received your "
                                "application for Service Engineer."
                            ),
                        }
                    ],
                }
            }
            thread = {
                "id": "gmail-hpe-thread",
                "subject": "Thank you for your online submission",
                "snippet": "Hewlett Packard Enterprise Service Engineer",
            }

            first = reconcile_confirmation_threads(
                ledger_path=root / "ledger.sqlite3",
                threads=[thread],
                thread_loader=lambda _thread_id: payload,
                seen_state=root / "inbox-seen.json",
                expected_recipient="candidate@example.com",
            )

            self.assertEqual(
                first["reconciled"],
                [
                    {
                        "application_id": application_id,
                        "message_id": "gmail-hpe-message",
                        "thread_id": "gmail-hpe-thread",
                        "status": "reconciled",
                    }
                ],
            )
            reopened = Ledger(root / "ledger.sqlite3")
            self.assertEqual(
                reopened.connection.execute(
                    "SELECT current_state FROM applications WHERE id = ?",
                    (application_id,),
                ).fetchone()[0],
                "submitted",
            )
            self.assertEqual(
                reopened.connection.execute(
                    "SELECT COUNT(*) FROM submission_confirmations"
                ).fetchone()[0],
                1,
            )
            reopened.close()

            replay = reconcile_confirmation_threads(
                ledger_path=root / "ledger.sqlite3",
                threads=[thread],
                thread_loader=lambda _thread_id: payload,
                seen_state=root / "inbox-seen.json",
                expected_recipient="candidate@example.com",
            )

            self.assertEqual(replay["reconciled"], [])
            reopened = Ledger(root / "ledger.sqlite3")
            self.assertEqual(
                reopened.connection.execute(
                    "SELECT COUNT(*) FROM submission_confirmations"
                ).fetchone()[0],
                1,
            )
            reopened.close()

    def test_gmail_confirmation_search_includes_online_submission_phrase(self):
        completed = Mock(stdout=json.dumps({"threads": []}))
        with patch(
            "job_search_loop.submission_confirmation.subprocess.run",
            return_value=completed,
        ) as run:
            self.assertEqual(
                _gmail_confirmation_threads("candidate@example.com", "gog"), []
            )

        query = run.call_args.args[0][-1]
        self.assertIn('"thank you for your online submission"', query)

    def test_generic_transition_cannot_bypass_confirmation_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger, application_id, _ = self._unknown_submission(
                Path(directory)
            )

            with self.assertRaises(InvalidTransition):
                ledger.transition(application_id, "submitted")

            self.assertEqual(
                ledger.connection.execute(
                    "SELECT current_state FROM applications WHERE id = ?",
                    (application_id,),
                ).fetchone()[0],
                "submit_unknown",
            )
            self.assertEqual(
                ledger.connection.execute(
                    "SELECT COUNT(*) FROM submission_confirmations"
                ).fetchone()[0],
                0,
            )
            ledger.close()

    def test_exact_late_ashby_receipt_reconciles_and_marks_thread_seen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, application_id, _ = self._unknown_submission(root)
            ledger.close()
            received = datetime.now(timezone.utc) + timedelta(minutes=1)
            wrapped_subject = (
                '<<<EXTERNAL_UNTRUSTED_CONTENT id="subject-1">>>\n'
                "Source: google_api\n---\n"
                "Application received: Agent Product Engineer at Dream AI\n"
                '<<<END_EXTERNAL_UNTRUSTED_CONTENT id="subject-1">>>'
            )
            wrapped_body = (
                '<<<EXTERNAL_UNTRUSTED_CONTENT id="body-1">>>\n'
                "Source: google_api\n---\n"
                "Thank you for applying to Agent Product Engineer at Dream AI.\n"
                '<<<END_EXTERNAL_UNTRUSTED_CONTENT id="body-1">>>'
            )
            payload = {
                "thread": {
                    "id": "gmail-thread-2",
                    "messages": [
                        {
                            "id": "gmail-message-2",
                            "threadId": "gmail-thread-2",
                            "internalDate": int(received.timestamp() * 1000),
                            "headers": {
                                "from": "Dream AI Recruiting <notifications@ashbyhq.com>",
                                "subject": wrapped_subject,
                            },
                            "body": wrapped_body,
                        }
                    ],
                }
            }

            result = reconcile_confirmation_threads(
                ledger_path=root / "ledger.sqlite3",
                threads=[
                    {
                        "id": "gmail-thread-2",
                        "subject": "Application received",
                        "from": "notifications@ashbyhq.com",
                    }
                ],
                thread_loader=lambda thread_id: payload,
                seen_state=root / "inbox-seen.json",
            )

            self.assertEqual(
                result,
                {
                    "version": 1,
                    "checked_threads": 1,
                    "reconciled": [
                        {
                            "application_id": application_id,
                            "message_id": "gmail-message-2",
                            "thread_id": "gmail-thread-2",
                            "status": "reconciled",
                        }
                    ],
                    "blocked": [],
                },
            )
            reopened = Ledger(root / "ledger.sqlite3")
            self.assertEqual(
                reopened.connection.execute(
                    "SELECT current_state FROM applications WHERE id = ?",
                    (application_id,),
                ).fetchone()[0],
                "submitted",
            )
            reopened.close()
            self.assertEqual(
                json.loads(
                    (root / "inbox-seen.json").read_text(encoding="utf-8")
                ),
                {"version": 2, "message_ids": ["gmail-message-2"]},
            )

    def test_spoofed_sender_cannot_promote_or_acknowledge_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, application_id, _ = self._unknown_submission(root)
            ledger.close()
            received = datetime.now(timezone.utc) + timedelta(minutes=1)
            payload = {
                "thread": {
                    "id": "gmail-thread-spoof",
                    "messages": [
                        {
                            "id": "gmail-message-spoof",
                            "threadId": "gmail-thread-spoof",
                            "internalDate": int(received.timestamp() * 1000),
                            "headers": {
                                "from": (
                                    "Dream AI Recruiting "
                                    "<notifications@ashbyhq.com.evil.example>"
                                ),
                                "subject": (
                                    "Application received: "
                                    "Agent Product Engineer at Dream AI"
                                ),
                            },
                            "body": (
                                "Thank you for applying to "
                                "Agent Product Engineer at Dream AI."
                            ),
                        }
                    ],
                }
            }

            result = reconcile_confirmation_threads(
                ledger_path=root / "ledger.sqlite3",
                threads=[
                    {
                        "id": "gmail-thread-spoof",
                        "subject": "Application received",
                    }
                ],
                thread_loader=lambda thread_id: payload,
                seen_state=root / "inbox-seen.json",
            )

            self.assertEqual(result["reconciled"], [])
            self.assertEqual(
                result["blocked"][0]["status"],
                "no_exact_uncertain_application",
            )
            reopened = Ledger(root / "ledger.sqlite3")
            self.assertEqual(
                reopened.connection.execute(
                    "SELECT current_state FROM applications WHERE id = ?",
                    (application_id,),
                ).fetchone()[0],
                "submit_unknown",
            )
            reopened.close()
            self.assertFalse((root / "inbox-seen.json").exists())

    def test_unique_authoritative_receipt_without_role_promotes_one_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, application_id, _ = self._unknown_submission(root)
            ledger.close()
            received = datetime.now(timezone.utc) + timedelta(minutes=1)
            payload = {"thread": {"messages": [{
                "id": "gmail-roleless",
                "threadId": "thread-roleless",
                "internalDate": int(received.timestamp() * 1000),
                "headers": {
                    "from": "Dream AI <notifications@ashbyhq.com>",
                    "to": "candidate@example.com",
                    "subject": "Thank you for applying",
                },
                "body": "Dream AI has received your application.",
            }]}}

            result = reconcile_confirmation_threads(
                ledger_path=root / "ledger.sqlite3",
                threads=[{"id": "thread-roleless", "subject": "Thank you for applying"}],
                thread_loader=lambda _thread_id: payload,
                seen_state=root / "seen.json",
                expected_recipient="candidate@example.com",
            )

            self.assertEqual(result["reconciled"][0]["application_id"], application_id)

    def test_ambiguous_company_and_role_match_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, _, _ = self._unknown_submission(root)
            first.close()
            second, _, _ = self._unknown_submission(
                root,
                url=(
                    "https://jobs.ashbyhq.com/dream/"
                    "agent-product-engineer-2/application"
                ),
            )
            second.close()
            received = datetime.now(timezone.utc) + timedelta(minutes=1)
            payload = {
                "thread": {
                    "id": "gmail-thread-ambiguous",
                    "messages": [
                        {
                            "id": "gmail-message-ambiguous",
                            "threadId": "gmail-thread-ambiguous",
                            "internalDate": int(received.timestamp() * 1000),
                            "headers": {
                                "from": (
                                    "Dream AI Recruiting "
                                    "<notifications@ashbyhq.com>"
                                ),
                                "subject": (
                                    "Application received: "
                                    "Agent Product Engineer at Dream AI"
                                ),
                            },
                            "body": (
                                "Thank you for applying to "
                                "Agent Product Engineer at Dream AI."
                            ),
                        }
                    ],
                }
            }

            result = reconcile_confirmation_threads(
                ledger_path=root / "ledger.sqlite3",
                threads=[
                    {
                        "id": "gmail-thread-ambiguous",
                        "subject": "Application received",
                    }
                ],
                thread_loader=lambda thread_id: payload,
                seen_state=root / "inbox-seen.json",
            )

            self.assertEqual(result["reconciled"], [])
            self.assertEqual(
                result["blocked"][0]["status"],
                "ambiguous_application_match",
            )
            self.assertFalse((root / "inbox-seen.json").exists())

    def test_inbox_driver_reconciles_and_delivers_before_model_scan(self):
        script = (
            Path(__file__).parents[1] / "scripts" / "run-inbox.sh"
        ).read_text(encoding="utf-8")

        reconcile_at = script.index(
            "-m job_search_loop.submission_confirmation reconcile"
        )
        delivery_at = script.index(
            "-m job_search_loop.application_reporting deliver"
        )
        scan_at = script.index("-m job_search_loop.inbox scan")
        summary_at = script.index("-m job_search_loop.summary")

        self.assertLess(reconcile_at, delivery_at)
        self.assertLess(delivery_at, scan_at)
        self.assertLess(summary_at, scan_at)


if __name__ == "__main__":
    unittest.main()
