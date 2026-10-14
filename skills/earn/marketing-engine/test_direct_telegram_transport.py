"""Marketing reporters must use the shared direct Bot API client."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATHS = (
    ROOT / "skills/earn/marketing-engine/report/owner_report_cli.py",
)


def load(path: Path):
    name = f"test_transport_{path.stem}_{path.parent.name}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class DirectTelegramTransportTest(unittest.TestCase):
    def local_credentials_file(self, directory: str) -> Path:
        credentials = Path(directory) / "credentials.json"
        credentials.write_text(json.dumps({"credentials": [
            {"service": "telegram-life-manager", "bot_token": "local-test-token", "chat_id": "local-test-chat"},
            {"service": "telegram-cloud-life-manager", "bot_token": "cloud-test-token", "chat_id": "cloud-test-chat"},
        ]}), encoding="utf-8")
        return credentials

    def test_every_reporter_uses_shared_client_and_receipt(self):
        for path in MODULE_PATHS:
            with self.subTest(path=path):
                module = load(path)
                with tempfile.TemporaryDirectory() as directory:
                    credentials = self.local_credentials_file(directory)
                    self.assertTrue(hasattr(module, "CREDENTIALS_FILE"))
                    with mock.patch.object(module, "CREDENTIALS_FILE", credentials):
                        self._assert_reporter_send(module)

    def _assert_reporter_send(self, module):
        client = mock.Mock()
        client.send_text.return_value = {
            "status": "delivered",
            "message_ids": [1234],
        }
        with mock.patch.object(
            module.TelegramClient, "from_env", return_value=client
        ) as factory, redirect_stdout(io.StringIO()) as stdout:
            self.assertTrue(module.send("truthful report"))
        factory.assert_called_once_with(environ={
            "TELEGRAM_BOT_TOKEN": "local-test-token",
            "TELEGRAM_CHAT_ID": "local-test-chat",
        })
        client.send_text.assert_called_once_with(
            "truthful report", chat_id="local-test-chat"
        )
        self.assertIn("1234", stdout.getvalue())

    def test_confirmed_send_failure_returns_false(self):
        module = load(MODULE_PATHS[0])
        with tempfile.TemporaryDirectory() as directory:
            credentials = self.local_credentials_file(directory)
            with mock.patch.object(module, "CREDENTIALS_FILE", credentials), mock.patch.object(
                module.TelegramClient,
                "from_env",
                side_effect=module.TelegramError("confirmed failure"),
            ), redirect_stderr(io.StringIO()) as stderr:
                self.assertFalse(module.send("truthful report"))
        self.assertIn("confirmed failure", stderr.getvalue())

    def test_no_reporter_invokes_openclaw_transport(self):
        forbidden = "openclaw" + " message"
        for path in MODULE_PATHS:
            with self.subTest(path=path):
                self.assertNotIn(forbidden, path.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
