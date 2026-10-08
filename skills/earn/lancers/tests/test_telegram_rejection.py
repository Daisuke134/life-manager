import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "telegram_report.py"


def _load_reporter():
    spec = importlib.util.spec_from_file_location("test_lancers_telegram_rejection", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_notifier_records_provider_rejection_as_attempted(monkeypatch):
    reporter = _load_reporter()

    class TelegramProviderRejected(Exception):
        error_code = 400

    class Client:
        def send_text(self, _message):
            raise TelegramProviderRejected("Bad Request")

    class Telegram:
        class TelegramClient:
            @staticmethod
            def from_env(**_kwargs):
                return Client()

    monkeypatch.setattr(reporter, "_load", lambda *_args: Telegram)

    result = reporter._default_notifier("Lancers report")

    assert result.attempted is True
    assert result.provider_rejected is True
    assert result.error_code == "provider_rejected:400"


def test_provider_rejection_reaches_shared_outbox_as_its_own_counter(tmp_path):
    reporter = _load_reporter()
    database = tmp_path / "telegram.sqlite3"
    reporter.outbox.enqueue(
        database,
        event_key="lancers:telegram:reject",
        message="Lancers report",
        created_at="2026-10-09T05:30:00Z",
        repeat_after_seconds=None,
    )
    notifier = lambda _message: reporter.SendResult(
        attempted=True, error_code="provider_rejected:400", provider_rejected=True
    )

    result = reporter.deliver_pending(database, notifier, "2026-10-09T05:30:00Z")
    item = reporter.outbox.list_items(database)[0]

    assert result.attempted == 1
    assert result.provider_rejected == 1
    assert result.pre_send_failed == 0
    assert result.delivery_uncertain == 0
    assert item.status == "pending"
    assert item.last_error_code == "provider_rejected:400"
