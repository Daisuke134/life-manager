import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from job_search_loop.browser_agent.workday_account import MachineWorkdayCredentialStore
from job_search_loop.workday_account_mail import complete_account_mail
from job_search_loop.workday_credentials import ensure_credentials
from job_search_loop.workday_verification import (
    VerificationError,
    VerificationStore,
    VerificationTarget,
    extract_verification_target,
)


TENANT = "crowdstrike.wd5.myworkdayjobs.com"
JOB_URL = f"https://{TENANT}/crowdstrikecareers/job/role-1"
ACTIVATION_URL = f"https://{TENANT}/crowdstrikecareers/activate/secret-token-123"


class WorkdayVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.profile = self.root / "profile.json"
        self.credentials = self.root / "private" / "workday-accounts.json"
        self.database = self.root / "state" / "workday-verifications.sqlite3"
        self.profile.write_text(
            json.dumps(
                {
                    "version": 1,
                    "candidate": {
                        "name": "Candidate",
                        "application_email": "candidate@example.com",
                    },
                    "facts": [
                        {
                            "id": "fact-001",
                            "claim": "Verified",
                            "evidence": "Private",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        ensure_credentials(
            job_url=JOB_URL,
            profile_path=self.profile,
            store_path=self.credentials,
            password_factory=lambda: "Strong-Workday-Password-9!",
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def _extract(self, **overrides):
        values = {
            "message_id": "message-1",
            "subject": "Verify your candidate account",
            "sender": "CrowdStrike People Services <crowdstrike@myworkday.com>",
            "body": (
                "Click this link to confirm your email address and complete setup "
                f"for your candidate account <a href=\"{ACTIVATION_URL}\">Verify</a>"
            ),
            "credential_store": self.credentials,
        }
        values.update(overrides)
        return extract_verification_target(**values)

    def test_exact_known_tenant_activation_is_private_and_receipt_is_redacted(self):
        target = self._extract()
        self.assertEqual(target.tenant, TENANT)
        self.assertEqual(target.verification_url, ACTIVATION_URL)
        receipt = target.receipt("claimed")
        self.assertEqual(receipt["message_id"], "message-1")
        self.assertEqual(receipt["tenant"], TENANT)
        self.assertEqual(receipt["status"], "claimed")
        serialized = json.dumps(receipt)
        self.assertNotIn("secret-token-123", serialized)
        self.assertNotIn(ACTIVATION_URL, serialized)
        self.assertEqual(len(receipt["url_sha256"]), 64)

    def test_password_reset_completion_releases_recovery_queue_state(self):
        credentials = self.root / "machine-credentials.json"
        credentials.write_text(
            json.dumps(
                {
                    "version": 1,
                    "credentials": [
                        {
                            "service": f"workday:{TENANT}",
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
        reset_url = f"https://{TENANT}/crowdstrikecareers/passwordreset/token"
        target = VerificationTarget(
            "message-reset",
            TENANT,
            reset_url,
            "a" * 64,
            kind="password_reset",
        )
        password = SimpleNamespace(
            control_type="password",
            role="textbox",
            label="New Password",
            stable_id="id:password",
            tag="input",
        )
        verify = SimpleNamespace(
            control_type="password",
            role="textbox",
            label="Verify New Password",
            stable_id="id:verify",
            tag="input",
        )
        submit = SimpleNamespace(
            control_type="button",
            role="button",
            label="Reset Password",
            stable_id="automation:resetPassword",
            tag="button",
        )
        observation = SimpleNamespace(controls=(password, verify, submit))
        page = Mock(url=reset_url)
        page.goto = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.type_target = AsyncMock()
        page.evaluate = AsyncMock(return_value="password has been reset")

        async def finish_reset(_target):
            page.url = f"https://{TENANT}/crowdstrikecareers/login"

        page.click_target = AsyncMock(side_effect=finish_reset)
        session = Mock()
        session.attach = AsyncMock(return_value=Mock())
        session.page.return_value = page
        session.close_owned = AsyncMock()
        builder = Mock(build=AsyncMock(return_value=observation))
        with patch(
            "job_search_loop.workday_account_mail.extract_verification_target_from_gmail",
            return_value=target,
        ), patch(
            "job_search_loop.workday_account_mail.BrowserSession",
            return_value=session,
        ), patch(
            "job_search_loop.workday_account_mail.ObservationBuilder",
            return_value=builder,
        ):
            receipt = asyncio.run(
                complete_account_mail(
                    account="candidate@example.com",
                    thread_id="thread-reset",
                    message_id="message-reset",
                    credential_store=credentials,
                    database=self.database,
                    endpoint="http://localhost:9222",
                    gog="/gog",
                )
            )

        self.assertEqual(receipt["status"], "opened")
        self.assertEqual(
            MachineWorkdayCredentialStore(credentials).account_status(JOB_URL),
            "create_submitted",
        )

    def test_untrusted_sender_tenant_scheme_path_and_ambiguity_fail_closed(self):
        cases = [
            {"sender": "Attacker <x@example.com>"},
            {
                "body": (
                    "Verify https://evil.wd5.myworkdayjobs.com/site/"
                    "activate/secret-token-123"
                )
            },
            {
                "body": (
                    f"Verify http://{TENANT}/crowdstrikecareers/"
                    "activate/secret-token-123"
                )
            },
            {"body": f"Verify https://{TENANT}/crowdstrikecareers/jobs/role-1"},
            {
                "body": (
                    f"Verify {ACTIVATION_URL} and "
                    f"https://{TENANT}/crowdstrikecareers/activate/other-token"
                )
            },
        ]
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(VerificationError):
                    self._extract(**values)

    def test_navigation_fence_is_at_most_once_after_start_unknown_or_opened(self):
        target = self._extract()
        store = VerificationStore(self.database)
        try:
            first = store.claim(target)
            self.assertIsNotNone(first)
            store.mark_navigation_started(target.event_key, first)
            self.assertIsNone(store.claim(target))
            store.mark_unknown(target.event_key, first)
            self.assertEqual(store.status(target.event_key), "navigation_unknown")
            self.assertIsNone(store.claim(target))

            second_target = self._extract(
                message_id="message-2",
                body=(
                    f"Verify https://{TENANT}/crowdstrikecareers/"
                    "activate/second-token"
                ),
            )
            second = store.claim(second_target)
            store.mark_navigation_started(second_target.event_key, second)
            store.mark_opened(second_target.event_key, second)
            self.assertEqual(store.status(second_target.event_key), "opened")
            self.assertIsNone(store.claim(second_target))
        finally:
            store.close()
        self.assertEqual(self.database.stat().st_mode & 0o777, 0o600)

    def test_expired_pre_navigation_claim_is_reclaimed_with_a_new_fence(self):
        target = self._extract()
        store = VerificationStore(self.database)
        first_at = datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc)
        try:
            first = store.claim(target, now=first_at)
            self.assertIsNotNone(first)
            self.assertIsNone(
                store.claim(target, now=first_at + timedelta(seconds=899))
            )
            second = store.claim(
                target,
                now=first_at + timedelta(seconds=900),
            )
            self.assertIsNotNone(second)
            self.assertNotEqual(first, second)
            with self.assertRaises(VerificationError):
                store.mark_navigation_started(target.event_key, first)
            store.mark_navigation_started(target.event_key, second)
            self.assertIsNone(
                store.claim(target, now=first_at + timedelta(days=30))
            )
        finally:
            store.close()

    def test_legacy_claim_without_claimed_at_recovers_from_created_at(self):
        target = self._extract()
        self.database.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.database)
        connection.execute(
            """
            CREATE TABLE workday_verifications (
              event_key TEXT PRIMARY KEY,
              message_id TEXT NOT NULL,
              tenant TEXT NOT NULL,
              url_sha256 TEXT NOT NULL,
              status TEXT NOT NULL,
              fence TEXT,
              created_at TEXT NOT NULL,
              completed_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO workday_verifications
              (event_key,message_id,tenant,url_sha256,status,fence,created_at)
            VALUES (?, ?, ?, ?, 'claimed', 'legacy-fence', ?)
            """,
            (
                target.event_key,
                target.message_id,
                target.tenant,
                target.url_sha256,
                datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc).isoformat(),
            ),
        )
        connection.commit()
        connection.close()

        store = VerificationStore(self.database)
        try:
            reclaimed = store.claim(
                target,
                now=datetime(2026, 7, 29, 0, 15, tzinfo=timezone.utc),
            )
            self.assertIsNotNone(reclaimed)
            self.assertNotEqual(reclaimed, "legacy-fence")
        finally:
            store.close()

    def test_prompt_and_schema_require_verification_results(self):
        root = Path(__file__).parents[1]
        prompt = (root / "prompts" / "inbox-pass.md").read_text(encoding="utf-8")
        schema = json.loads(
            (root / "schemas" / "inbox-pass-result.v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("workday_verification", prompt)
        self.assertIn("mark_navigation_started", prompt)
        self.assertIn("verifications", schema["required"])
        self.assertIn("verifications", schema["properties"])
        self.assertIn("processed_thread_ids", schema["required"])
        self.assertIn("processed_message_ids", schema["required"])
        self.assertTrue(
            schema["properties"]["processed_thread_ids"]["uniqueItems"]
        )
        self.assertTrue(
            schema["properties"]["processed_message_ids"]["uniqueItems"]
        )
        self.assertIn("processed_thread_ids", prompt)
        self.assertIn("processed_message_ids", prompt)


if __name__ == "__main__":
    unittest.main()
