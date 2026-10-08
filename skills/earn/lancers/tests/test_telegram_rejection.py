import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "telegram_report.py"


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_reporter():
    return _load_script("test_lancers_telegram_rejection", SCRIPT)


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


def test_lane_report_returns_nonzero_and_provider_rejection_json(monkeypatch, tmp_path):
    lane_report = _load_script(
        "test_lancers_lane_report_rejection", SCRIPT.with_name("lane_report.py")
    )
    delivery = SimpleNamespace(
        attempted=1, delivered=0, delivery_uncertain=0,
        pre_send_failed=0, provider_rejected=1,
    )
    monkeypatch.setattr(lane_report, "read_snapshot", lambda _path: {"source_complete": True})
    monkeypatch.setattr(lane_report, "_load", lambda *_args: SimpleNamespace(
        notify_negotiate_wake=lambda _snapshot: delivery
    ))
    output = io.StringIO()
    monkeypatch.setattr(lane_report.sys, "stdout", output)

    status = lane_report.main(
        ["--lane", "negotiate", "--state-path", str(tmp_path / "snapshot.json")]
    )
    payload = json.loads(output.getvalue())

    assert status == 1
    assert payload["ok"] is False
    assert payload["provider_rejected"] == 1


def test_storefront_apply_emits_provider_rejection_and_nonzero(monkeypatch, tmp_path):
    storefront = _load_script(
        "test_lancers_storefront_rejection", SCRIPT.with_name("storefront_offer.py")
    )
    delivery = SimpleNamespace(
        attempted=1, delivered=0, delivery_uncertain=0,
        pre_send_failed=0, provider_rejected=1,
    )
    monkeypatch.setattr(
        storefront,
        "run",
        lambda *_args: {"ok": True, "action": "updated"},
    )
    monkeypatch.setattr(storefront, "_load", lambda *_args: SimpleNamespace(
        notify_storefront_wake=lambda _result: delivery
    ))
    output = io.StringIO()
    monkeypatch.setattr(storefront.sys, "stdout", output)

    status = storefront.main(
        ["--apply", "--product", str(tmp_path / "product.json"),
         "--state-path", str(tmp_path / "state.json")]
    )
    payload = json.loads(output.getvalue())

    assert status == 1
    assert payload["ok"] is False
    assert payload["telegram_delivery"]["provider_rejected"] == 1
