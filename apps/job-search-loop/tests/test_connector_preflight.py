import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from job_search_loop.connector_preflight import ConnectorPreflightError, verify_connectors


class ConnectorPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.profile = self.root / "profile.json"
        self.outbox = self.root / "state" / "telegram.sqlite3"
        self.output = self.root / "state" / "connector-preflight.json"
        self.profile.write_text(
            json.dumps(
                {
                    "version": 1,
                    "candidate": {
                        "name": "Candidate",
                        "application_email": "candidate@example.test",
                    },
                    "facts": [{"id": "f1", "claim": "Fact", "evidence": "Evidence"}],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def gmail_ok(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, '{"messages":[]}', "")

    @staticmethod
    def telegram_ok(**kwargs):
        return {"status": "sent", "message_id": "setup-101"}

    def test_ready_requires_gmail_and_positive_telegram_ack(self):
        receipt = verify_connectors(
            profile_path=self.profile,
            outbox_path=self.outbox,
            output_path=self.output,
            gmail_runner=self.gmail_ok,
            telegram_sender=self.telegram_ok,
        )
        self.assertEqual(receipt["status"], "ready")
        self.assertEqual(receipt["telegram"]["message_id"], "setup-101")
        self.assertNotIn("candidate@example.test", json.dumps(receipt))
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.output.parent.stat().st_mode), 0o700)

    def test_gmail_only_is_ready_when_telegram_is_not_configured(self):
        receipt = verify_connectors(
            profile_path=self.profile,
            outbox_path=self.outbox,
            output_path=self.output,
            gmail_runner=self.gmail_ok,
            telegram_sender=None,
        )

        self.assertEqual(receipt["status"], "ready")
        self.assertEqual(receipt["gmail"]["status"], "ready")
        self.assertEqual(receipt["telegram"]["status"], "not_configured")
        self.assertNotIn("candidate@example.test", json.dumps(receipt))

    def test_gmail_failure_sends_no_telegram_and_writes_no_receipt(self):
        sent = []

        def gmail_failed(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 1, "", "failed")

        with self.assertRaisesRegex(ConnectorPreflightError, "Gmail"):
            verify_connectors(
                profile_path=self.profile,
                outbox_path=self.outbox,
                output_path=self.output,
                gmail_runner=gmail_failed,
                telegram_sender=lambda **kwargs: sent.append(kwargs),
            )
        self.assertEqual(sent, [])
        self.assertFalse(self.output.exists())

    def test_unavailable_optional_telegram_does_not_block_gmail_readiness(self):
        receipt = verify_connectors(
            profile_path=self.profile,
            outbox_path=self.outbox,
            output_path=self.output,
            gmail_runner=self.gmail_ok,
            telegram_sender=lambda **kwargs: {"status": "send_started", "message_id": None},
        )

        self.assertEqual(receipt["status"], "ready")
        self.assertEqual(receipt["telegram"]["status"], "unavailable")
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
