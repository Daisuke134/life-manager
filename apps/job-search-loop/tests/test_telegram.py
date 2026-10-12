import inspect
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_search_loop import telegram


class TelegramReportTests(unittest.TestCase):
    def test_telegram_configuration_can_be_absent_without_exposing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "telegram.env"
            environment = {
                "JOB_SEARCH_TELEGRAM_ENV": str(env_file),
                "TELEGRAM_BOT_TOKEN": "",
                "JOB_SEARCH_TELEGRAM_CHAT_ID": "",
            }
            with patch.dict(os.environ, environment, clear=False):
                self.assertFalse(telegram.is_configured())
                env_file.write_text(
                    "TELEGRAM_BOT_TOKEN=test-token\nJOB_SEARCH_TELEGRAM_CHAT_ID=123\n",
                    encoding="utf-8",
                )
                self.assertTrue(telegram.is_configured())

    def test_uncertain_send_is_not_retried_through_direct_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "outbox.sqlite3"
            requests = []

            def requester(**request):
                requests.append(request)
                return {"ok": True, "result": {"message_id": 900}}

            outbox = telegram.Outbox(database)
            try:
                outbox.enqueue("uncertain", "already attempted")
                fence = outbox.claim("uncertain")
                outbox.mark_send_started("uncertain", fence)
            finally:
                outbox.close()

            result = telegram.send_once(
                database=database,
                event_key="uncertain",
                message="already attempted",
                target="test-chat",
                token="test-token",
                requester=requester,
            )

            self.assertEqual(result, {"status": "send_started", "message_id": None})
            self.assertEqual(requests, [])

    def test_transport_has_no_openclaw_or_subprocess_dependency(self):
        source = inspect.getsource(telegram)
        self.assertNotIn("openclaw", source.casefold())
        self.assertNotIn("subprocess", source)

    def test_same_text_with_changed_material_digest_sends_new_event_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requests = []
            def requester(**request):
                requests.append(request)
                return {"ok": True, "result": {"message_id": 800 + len(requests)}}
            database = root / "outbox.sqlite3"

            first = telegram.send_daily_report(
                database=database,
                japan_day="2026-08-06",
                message="same owner-facing report",
                material_digest="a" * 64,
                target="test-chat",
                token="test-token",
                requester=requester,
            )
            changed = telegram.send_daily_report(
                database=database,
                japan_day="2026-08-06",
                message="same owner-facing report",
                material_digest="b" * 64,
                target="test-chat",
                token="test-token",
                requester=requester,
            )
            replay = telegram.send_daily_report(
                database=database,
                japan_day="2026-08-06",
                message="same owner-facing report",
                material_digest="b" * 64,
                target="test-chat",
                token="test-token",
                requester=requester,
            )

            self.assertEqual(first["message_id"], "801")
            self.assertEqual(changed["message_id"], "802")
            self.assertEqual(replay, changed)
            self.assertNotEqual(first["event_key"], changed["event_key"])
            self.assertEqual(
                len(requests), 2
            )
            self.assertEqual(requests[0]["method"], "sendMessage")
            self.assertEqual(requests[0]["token"], "test-token")

    def test_daily_report_sends_one_content_addressed_correction(self):
        sender = getattr(telegram, "send_daily_report", None)
        self.assertIsNotNone(sender)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requests = []
            def requester(**request):
                requests.append(request)
                return {"ok": True, "result": {"message_id": 700 + len(requests)}}
            database = root / "outbox.sqlite3"

            first = sender(
                database=database,
                japan_day="2026-07-29",
                message="Discovery blocked; no applications.",
                target="test-chat",
                token="test-token",
                requester=requester,
            )
            correction = sender(
                database=database,
                japan_day="2026-07-29",
                message="Discovery recovered; best-fit role blocked on legal answers.",
                target="test-chat",
                token="test-token",
                requester=requester,
            )
            duplicate = sender(
                database=database,
                japan_day="2026-07-29",
                message="Discovery recovered; best-fit role blocked on legal answers.",
                target="test-chat",
                token="test-token",
                requester=requester,
            )

            self.assertEqual(first["message_id"], "701")
            self.assertEqual(correction["message_id"], "702")
            self.assertEqual(duplicate, correction)
            self.assertEqual(len(requests), 2)
            self.assertEqual(
                requests[1]["fields"]["text"],
                "Discovery recovered; best-fit role blocked on legal answers.",
            )
            self.assertIn(":correction:", correction["event_key"])


if __name__ == "__main__":
    unittest.main()
