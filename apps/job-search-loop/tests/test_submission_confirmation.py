import hashlib
import json
import stat
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from job_search_loop.inbox import message_is_seen
from job_search_loop.ledger import Ledger
from job_search_loop.state import InvalidTransition
from job_search_loop.submission_confirmation import (
    _bounded_official_posting_loader,
    _confirmation_search_cursor_path,
    _confirmation_search_query_sha256,
    _gmail_confirmation_threads,
    _next_confirmation_page_token,
    _read_search_page_token,
    _write_search_page_token,
    main,
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

    def test_workday_tenant_receipt_uses_exact_official_brand_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, application_id, _ = self._unknown_submission(
                root,
                company="Northstar Group",
                title="Business Account Manager",
                url=(
                    "https://northstar.wd5.myworkdayjobs.com/External/job/"
                    "Business_Account_Manager"
                ),
            )
            ledger.close()
            received = datetime.now(timezone.utc) + timedelta(minutes=1)
            posting_readbacks = []
            payload = {
                "thread": {
                    "id": "gmail-workday-brand-thread",
                    "messages": [
                        {
                            "id": "gmail-workday-brand-message",
                            "threadId": "gmail-workday-brand-thread",
                            "internalDate": int(received.timestamp() * 1000),
                            "headers": {
                                "from": "Workday Notifications <notifications@myworkday.com>",
                                "to": "candidate@example.com",
                                "subject": "Workday application status update",
                            },
                            "body": (
                                "Northstar Analytics K.K. の Business Account Manager "
                                "の職務にご応募いただきありがとうございます。"
                            ),
                        }
                    ],
                }
            }
            thread = {
                "id": "gmail-workday-brand-thread",
                "from": "Workday Notifications <notifications@myworkday.com>",
                "subject": "Workday application status update",
                "snippet": "Northstar Analytics K.K. Business Account Manager",
            }

            def load_posting(candidate):
                posting_readbacks.append(candidate["company"])
                return {
                    "jobPostingInfo": {"title": "Business Account Manager"},
                    "hiringOrganization": {"name": "Northstar Analytics K.K."},
                }

            first = reconcile_confirmation_threads(
                ledger_path=root / "ledger.sqlite3",
                threads=[thread],
                thread_loader=lambda _thread_id: payload,
                seen_state=root / "inbox-seen.json",
                expected_recipient="candidate@example.com",
                official_posting_loader=load_posting,
            )

            self.assertEqual(posting_readbacks, ["Northstar Group"])
            self.assertEqual(
                first["reconciled"],
                [
                    {
                        "application_id": application_id,
                        "message_id": "gmail-workday-brand-message",
                        "thread_id": "gmail-workday-brand-thread",
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

    def test_unrelated_workday_mail_with_generic_subject_does_not_promote(self):
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
                    "id": "gmail-hpe-unrelated-thread",
                    "messages": [
                        {
                            "id": "gmail-hpe-unrelated-message",
                            "threadId": "gmail-hpe-unrelated-thread",
                            "internalDate": int(received.timestamp() * 1000),
                            "headers": {
                                "from": "Hewlett Packard Enterprise <hpe@myworkday.com>",
                                "to": "candidate@example.com",
                                "subject": "Workday application status update",
                            },
                            "body": (
                                "Thank you for your interest in "
                                "Hewlett Packard Enterprise."
                            ),
                        }
                    ],
                }
            }
            result = reconcile_confirmation_threads(
                ledger_path=root / "ledger.sqlite3",
                threads=[{
                    "id": "gmail-hpe-unrelated-thread",
                    "from": "Hewlett Packard Enterprise <hpe@myworkday.com>",
                    "subject": "Workday application status update",
                    "snippet": (
                        "Thank you for your interest in "
                        "Hewlett Packard Enterprise."
                    ),
                }],
                thread_loader=lambda _thread_id: payload,
                seen_state=root / "inbox-seen.json",
                expected_recipient="candidate@example.com",
            )

            self.assertEqual(result["reconciled"], [])
            reopened = Ledger(root / "ledger.sqlite3")
            self.assertEqual(
                reopened.connection.execute(
                    "SELECT current_state FROM applications WHERE id = ?",
                    (application_id,),
                ).fetchone()[0],
                "submit_unknown",
            )
            self.assertEqual(
                reopened.connection.execute(
                    "SELECT COUNT(*) FROM submission_confirmations"
                ).fetchone()[0],
                0,
            )
            reopened.close()

    def test_gmail_confirmation_search_includes_online_submission_phrase(self):
        first_page = Mock(stdout=json.dumps({
            "threads": [{"id": "gmail-page-one"}],
            "nextPageToken": "opaque-next-page",
        }))
        second_page = Mock(stdout=json.dumps({"threads": [{"id": "gmail-page-two"}]}))
        with patch(
            "job_search_loop.submission_confirmation.subprocess.run",
            side_effect=[first_page, second_page],
        ) as run:
            first_threads, next_page, fetched_page = _gmail_confirmation_threads(
                "candidate@example.com", "gog"
            )
            second_threads, final_page, fetched_backlog_page = _gmail_confirmation_threads(
                "candidate@example.com", "gog", page_token=next_page
            )

        self.assertEqual(first_threads, [{"id": "gmail-page-one"}])
        self.assertEqual(next_page, "opaque-next-page")
        self.assertIsNone(fetched_page)
        self.assertEqual(second_threads, [{"id": "gmail-page-two"}])
        self.assertIsNone(final_page)
        self.assertEqual(fetched_backlog_page, "opaque-next-page")

        first_args = run.call_args_list[0].args[0]
        first_query = first_args[-1]
        self.assertIn("--max", first_args)
        self.assertEqual(first_args[first_args.index("--max") + 1], "5")
        self.assertNotIn("--all", first_args)
        self.assertFalse(any(arg.startswith("--page=") for arg in first_args))
        second_args = run.call_args_list[1].args[0]
        self.assertIn("--page=opaque-next-page", second_args)
        query = first_query
        self.assertIn('"thank you for your online submission"', query)
        self.assertIn("from:myworkday.com", query)
        self.assertIn("from:myworkdayjobs.com", query)

    def test_expired_gmail_page_token_restarts_at_newest_page(self):
        second = Mock(stdout=json.dumps({
            "threads": [{"id": "gmail-page-one"}],
            "nextPageToken": "page-two",
        }))
        with patch(
            "job_search_loop.submission_confirmation.subprocess.run",
            side_effect=[subprocess.CalledProcessError(3, "gog"), second],
        ) as run:
            threads, next_page, fetched_page = _gmail_confirmation_threads(
                "candidate@example.com", "gog", page_token="expired-page"
            )

        self.assertEqual(threads, [{"id": "gmail-page-one"}])
        self.assertEqual(next_page, "page-two")
        self.assertIsNone(fetched_page)
        self.assertIn("--page=expired-page", run.call_args_list[0].args[0])
        self.assertNotIn("--page=expired-page", run.call_args_list[1].args[0])

    def test_search_page_token_is_private_and_bound_to_query(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "submission-confirmation-page.json"
            query_hash = "a" * 64

            _write_search_page_token(path, query_hash, "opaque-page-token")

            self.assertEqual(_read_search_page_token(path, query_hash), "opaque-page-token")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertIsNone(_read_search_page_token(path, "b" * 64))

            _write_search_page_token(path, query_hash, None)
            self.assertIsNone(_read_search_page_token(path, query_hash))

    def test_retryable_backlog_readback_failure_retains_effective_page(self):
        result = {
            "reconciled": [{"status": "reconciled", "message_id": "already-saved"}],
            "blocked": [
                {"status": "gmail_thread_readback_failed"},
                {"status": "official_posting_readback_unavailable"},
                {"status": "no_exact_uncertain_application"},
            ]
        }

        self.assertEqual(
            _next_confirmation_page_token(
                next_page_token="page-three",
                newest_next_page_token="page-two",
                fetched_page_token="page-two",
                result=result,
            ),
            "page-two",
        )

    def test_expired_backlog_token_failure_retries_newest_backlog_page(self):
        self.assertEqual(
            _next_confirmation_page_token(
                next_page_token="page-two",
                newest_next_page_token="page-two",
                fetched_page_token=None,
                result={"blocked": [{"status": "gmail_thread_readback_failed"}]},
            ),
            "page-two",
        )

    def test_terminal_ambiguous_match_does_not_stall_backlog_cursor(self):
        self.assertEqual(
            _next_confirmation_page_token(
                next_page_token="page-three",
                newest_next_page_token="page-two",
                fetched_page_token="page-two",
                result={"blocked": [{"status": "ambiguous_application_match"}]},
            ),
            "page-three",
        )

    def test_deterministic_readback_budget_deferral_advances_backlog_cursor(self):
        self.assertEqual(
            _next_confirmation_page_token(
                next_page_token="page-three",
                newest_next_page_token="page-two",
                fetched_page_token="page-two",
                result={
                    "blocked": [
                        {"status": "official_posting_readback_budget_exhausted"}
                    ]
                },
            ),
            "page-three",
        )

    def test_main_keeps_backlog_cursor_when_that_page_has_readback_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seen_path = root / "inbox-seen.json"
            cursor_path = _confirmation_search_cursor_path(seen_path)
            query_hash = _confirmation_search_query_sha256()
            _write_search_page_token(cursor_path, query_hash, "page-two")

            def search(_account, _gog, *, page_token=None):
                if page_token:
                    return ([{"id": "backlog-thread"}], "page-three", page_token)
                return ([{"id": "recent-thread"}], "page-two", None)

            page_results = [
                {"checked_threads": 1, "reconciled": [], "blocked": []},
                {
                    "checked_threads": 2,
                    "reconciled": [{"message_id": "already-confirmed"}],
                    "blocked": [
                        {
                            "thread_id": "unavailable-thread",
                            "status": "gmail_thread_readback_failed",
                        }
                    ],
                },
            ]

            with (
                patch("sys.argv", [
                    "submission_confirmation",
                    "reconcile",
                    "--account",
                    "candidate@example.com",
                    "--ledger",
                    str(root / "ledger.sqlite3"),
                    "--seen",
                    str(seen_path),
                    "--output",
                    str(root / "evidence.json"),
                ]),
                patch(
                    "job_search_loop.submission_confirmation._gmail_confirmation_threads",
                    side_effect=search,
                ),
                patch(
                    "job_search_loop.submission_confirmation.reconcile_confirmation_threads",
                    side_effect=page_results,
                ),
            ):
                main()

            self.assertEqual(
                _read_search_page_token(cursor_path, query_hash), "page-two"
            )
            evidence = json.loads((root / "evidence.json").read_text())
            self.assertEqual(
                evidence["reconciled"], [{"message_id": "already-confirmed"}]
            )
            self.assertEqual(
                evidence["blocked"][0]["status"], "gmail_thread_readback_failed"
            )

    def test_workday_posting_readbacks_are_bounded_and_cached(self):
        fetched = []

        def fetch(url, _sources):
            fetched.append(url)
            return {"url": url}

        load = _bounded_official_posting_loader(
            (), fetch, readback_limit=2
        )
        first = {"canonical_url": "https://one.wd5.myworkdayjobs.com/job/1"}
        second = {"canonical_url": "https://two.wd5.myworkdayjobs.com/job/2"}
        third = {"canonical_url": "https://three.wd5.myworkdayjobs.com/job/3"}

        self.assertEqual(load(first), {"url": first["canonical_url"]})
        self.assertEqual(load(first), {"url": first["canonical_url"]})
        self.assertEqual(load(second), {"url": second["canonical_url"]})
        with self.assertRaisesRegex(ValueError, "readback_budget_exhausted"):
            load(third)
        self.assertEqual(fetched, [first["canonical_url"], second["canonical_url"]])

    def test_posting_budget_exhaustion_leaves_fifth_receipt_for_next_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app_ids = []
            threads = []
            payloads = {}
            received = datetime.now(timezone.utc) + timedelta(minutes=1)
            for index in range(5):
                title = f"Role {index}"
                ledger, application_id, _ = self._unknown_submission(
                    root,
                    company=f"Parent Company {index}",
                    title=title,
                    url=(
                        "https://tenant"
                        f"{index}.wd5.myworkdayjobs.com/External/job/Role_{index}"
                    ),
                )
                ledger.close()
                app_ids.append(application_id)
                thread_id = f"workday-thread-{index}"
                threads.append(
                    {
                        "id": thread_id,
                        "from": "notifications@myworkdayjobs.com",
                        "subject": "Thank you for applying",
                    }
                )
                payloads[thread_id] = {
                    "thread": {
                        "messages": [
                            {
                                "id": f"workday-message-{index}",
                                "threadId": thread_id,
                                "internalDate": int(received.timestamp() * 1000),
                                "headers": {
                                    "from": "notifications@myworkdayjobs.com",
                                    "to": "candidate@example.com",
                                    "subject": "Thank you for applying",
                                },
                                "body": (
                                    f"Hiring Brand {index} の {title} の職務に"
                                    "ご応募いただきました"
                                ),
                            }
                        ]
                    }
                }

            def fetch_posting(url, _sources):
                index = next(i for i in range(5) if f"tenant{i}." in url)
                return {
                    "jobPostingInfo": {
                        "title": f"Role {index}",
                        "logoImage": {"alt": f"Hiring Brand {index} logo"},
                    },
                    "hiringOrganization": {"name": f"Hiring Brand {index}"},
                }

            seen_path = root / "inbox-seen.json"
            cursor_path = _confirmation_search_cursor_path(seen_path)
            query_hash = _confirmation_search_query_sha256()
            _write_search_page_token(cursor_path, query_hash, "page-two")

            def search(_account, _gog, *, page_token=None):
                if page_token is None:
                    return ([], "page-two", None)
                if page_token == "page-two":
                    return (threads, "page-three", page_token)
                if page_token == "page-three":
                    return ([], None, page_token)
                raise AssertionError(f"unexpected Gmail page token: {page_token}")

            argv = [
                "submission_confirmation",
                "reconcile",
                "--account",
                "candidate@example.com",
                "--ledger",
                str(root / "ledger.sqlite3"),
                "--seen",
                str(seen_path),
                "--output",
                str(root / "evidence.json"),
            ]

            def run_main():
                with (
                    patch("sys.argv", argv),
                    patch(
                        "job_search_loop.submission_confirmation._gmail_confirmation_threads",
                        side_effect=search,
                    ),
                    patch(
                        "job_search_loop.submission_confirmation._gmail_thread",
                        side_effect=lambda _account, thread_id, _gog: payloads[
                            thread_id
                        ],
                    ),
                    patch(
                        "job_search_loop.workday_qualification.fetch_official_posting",
                        side_effect=fetch_posting,
                    ),
                ):
                    main()
                return json.loads((root / "evidence.json").read_text())

            first_pass = run_main()
            self.assertEqual(
                [row["application_id"] for row in first_pass["reconciled"]],
                app_ids[:4],
            )
            self.assertEqual(
                first_pass["blocked"][0]["status"],
                "official_posting_readback_budget_exhausted",
            )
            self.assertEqual(
                _read_search_page_token(cursor_path, query_hash), "page-three"
            )
            for index in range(5):
                self.assertEqual(
                    message_is_seen(
                        seen_path,
                        message_id=f"workday-message-{index}",
                        thread_id=f"workday-thread-{index}",
                        received_epoch=received.timestamp(),
                    ),
                    index < 4,
                )

            run_main()  # Scan the end of the result set and wrap to page two.
            self.assertEqual(
                _read_search_page_token(cursor_path, query_hash), "page-two"
            )
            third_pass = run_main()
            self.assertEqual(
                [row["application_id"] for row in third_pass["reconciled"]],
                [app_ids[4]],
            )
            self.assertTrue(
                message_is_seen(
                    seen_path,
                    message_id="workday-message-4",
                    thread_id="workday-thread-4",
                    received_epoch=received.timestamp(),
                )
            )

            run_main()  # Wrap once more; the receipt must remain idempotent.
            replay = run_main()
            self.assertEqual(replay["reconciled"], [])
            ledger = Ledger(root / "ledger.sqlite3")
            self.assertEqual(
                ledger.connection.execute(
                    "SELECT COUNT(*) FROM submission_confirmations"
                ).fetchone()[0],
                5,
            )
            ledger.close()

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

    def test_thread_readback_timeout_does_not_block_later_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, application_id, _ = self._unknown_submission(root)
            ledger.close()
            received = datetime.now(timezone.utc) + timedelta(minutes=1)
            payload = {"thread": {"messages": [{
                "id": "gmail-after-timeout",
                "threadId": "thread-after-timeout",
                "internalDate": int(received.timestamp() * 1000),
                "headers": {
                    "from": "Dream AI <notifications@ashbyhq.com>",
                    "to": "candidate@example.com",
                    "subject": "Thank you for applying",
                },
                "body": (
                    "Thank you for applying to Agent Product Engineer "
                    "at Dream AI."
                ),
            }]}}

            def load_thread(thread_id):
                if thread_id == "thread-times-out":
                    raise subprocess.TimeoutExpired("gog", 15)
                return payload

            result = reconcile_confirmation_threads(
                ledger_path=root / "ledger.sqlite3",
                threads=[
                    {
                        "id": "thread-times-out",
                        "from": "Dream AI <notifications@ashbyhq.com>",
                        "subject": "Application received",
                    },
                    {
                        "id": "thread-after-timeout",
                        "from": "Dream AI <notifications@ashbyhq.com>",
                        "subject": "Thank you for applying",
                    },
                ],
                thread_loader=load_thread,
                seen_state=root / "inbox-seen.json",
                expected_recipient="candidate@example.com",
            )

            self.assertEqual(
                [row["application_id"] for row in result["reconciled"]],
                [application_id],
            )
            self.assertEqual(result["blocked"][0]["thread_id"], "thread-times-out")
            self.assertEqual(result["blocked"][0]["status"], "gmail_thread_readback_failed")

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
