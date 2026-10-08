import importlib.util
import io
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _notify_with_response(tmp_path, monkeypatch, case, body, http_status=None):
    notification = load(f"test_effect_notification_{case}", "effect_notification.py")
    delivery = load(f"test_effect_delivery_{case}", "telegram_delivery.py")
    env_file = tmp_path / "telegram.env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=test-token\n", encoding="utf-8")
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return body

    def opener(request, timeout):
        calls.append((request, timeout))
        if http_status is not None:
            raise urllib.error.HTTPError(
                request.full_url, http_status, "gateway error", None, io.BytesIO(body)
            )
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", opener)
    arguments = dict(
        database=tmp_path / "outbox.sqlite3",
        event_key=f"cfo:subject:{case}",
        message="CFO report",
        observed_at="2026-10-09T04:00:00Z",
        chat_id="123",
        env_file=env_file,
        sender=lambda message: delivery.send_via_shared_client(
            message, chat_id="123", env_file=env_file
        ),
    )
    return (
        notification.notify_effect(**arguments),
        notification.notify_effect(**arguments),
        calls,
    )


def test_shared_effect_notification_delivers_once_and_replays_zero(tmp_path):
    notification = load("test_effect_notification", "effect_notification.py")
    calls = []

    def sender(message):
        calls.append(message)
        delivery = load("test_effect_delivery", "telegram_delivery.py")
        return delivery.SendResult(True, "provider-1", None)

    arguments = dict(
        database=tmp_path / "outbox.sqlite3",
        event_key="platform:lane:effect-1",
        message="Codex::: effect happened",
        observed_at="2026-09-07T05:00:00Z",
        chat_id="123",
        env_file=tmp_path / "telegram.env",
        sender=sender,
    )
    first = notification.notify_effect(**arguments)
    replay = notification.notify_effect(**arguments)

    assert first["delivery"] == "delivered"
    assert first["provider_message_id"] == "provider-1"
    assert replay["delivery"] == "delivered"
    assert replay["attempted"] == 0
    assert calls == ["Codex::: effect happened"]


def test_provider_ack_timestamp_is_after_claim_not_report_observation_time(tmp_path):
    notification = load("test_effect_notification_delivery_time", "effect_notification.py")
    outbox = load("test_effect_outbox_delivery_time", "telegram_outbox.py")
    delivery = load("test_effect_delivery_time", "telegram_delivery.py")
    database = tmp_path / "outbox.sqlite3"
    observed_at = "2026-09-07T05:00:00Z"

    result = notification.notify_effect(
        database=database,
        event_key="cfo:subject:telegram:2026-09-07:05",
        message="CFO report",
        observed_at=observed_at,
        chat_id="123",
        env_file=tmp_path / "telegram.env",
        sender=lambda _message: delivery.SendResult(True, "provider-ack-1", None),
    )

    item = outbox.list_items(database)[0]
    assert result["delivery"] == "delivered"
    assert item.claimed_at is not None
    assert item.delivered_at is not None
    parse_utc = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parse_utc(item.delivered_at) >= parse_utc(item.claimed_at)
    assert item.delivered_at != observed_at


def test_delivered_event_replays_receipt_when_generated_wording_drifts(tmp_path):
    notification = load("test_effect_notification_wording_drift", "effect_notification.py")
    calls = []

    def sender(message):
        calls.append(message)
        delivery = load("test_effect_delivery_wording_drift", "telegram_delivery.py")
        return delivery.SendResult(True, "provider-1", None)

    arguments = dict(
        database=tmp_path / "outbox.sqlite3",
        event_key="platform:lane:effect-1",
        observed_at="2026-09-07T05:00:00Z",
        chat_id="123",
        env_file=tmp_path / "telegram.env",
        sender=sender,
    )
    first = notification.notify_effect(message="Codex::: first wording", **arguments)
    replay = notification.notify_effect(message="Codex::: revised wording", **arguments)

    assert first["provider_message_id"] == "provider-1"
    assert replay == {
        "event_key": "platform:lane:effect-1",
        "delivery": "delivered",
        "provider_message_id": "provider-1",
        "attempted": 0,
        "delivered": 0,
        "delivery_uncertain": 0,
        "pre_send_failed": 0,
        "provider_rejected": 0,
    }
    assert calls == ["Codex::: first wording"]


def test_pre_send_failure_releases_the_same_sqlite_event_for_replay(tmp_path):
    notification = load("test_effect_notification_retry", "effect_notification.py")
    delivery = load("test_effect_delivery_retry", "telegram_delivery.py")
    calls = []

    def sender(message):
        calls.append(message)
        return delivery.SendResult(False, None, "not_started") if len(calls) == 1 \
            else delivery.SendResult(True, "provider-2", None)

    arguments = dict(
        database=tmp_path / "outbox.sqlite3",
        event_key="agent-economy:financial:stable",
        message="Codex::: stable financial transition",
        observed_at="2026-09-11T05:00:00Z",
        chat_id="123",
        env_file=tmp_path / "telegram.env",
        sender=sender,
    )
    first = notification.notify_effect(**arguments)
    replay = notification.notify_effect(**arguments)

    assert first["delivery"] == "pending"
    assert first["pre_send_failed"] == 1
    assert replay["delivery"] == "delivered"
    assert replay["provider_message_id"] == "provider-2"
    assert calls == [arguments["message"], arguments["message"]]


def test_non_json_first_chunk_response_is_fenced_not_replayed(tmp_path, monkeypatch):
    first, replay, calls = _notify_with_response(
        tmp_path, monkeypatch, "non_json_first_chunk", b"not-json"
    )

    assert first["delivery"] == "delivery_uncertain"
    assert first["attempted"] == 1
    assert first["delivery_uncertain"] == 1
    assert replay["attempted"] == 0
    assert len(calls) == 1


def test_non_json_http_error_after_first_chunk_is_fenced_not_replayed(tmp_path, monkeypatch):
    first, replay, calls = _notify_with_response(
        tmp_path,
        monkeypatch,
        "non_json_http_error",
        b"gateway error",
        http_status=502,
    )

    assert first["delivery"] == "delivery_uncertain"
    assert first["attempted"] == 1
    assert first["delivery_uncertain"] == 1
    assert replay["attempted"] == 0
    assert len(calls) == 1


def test_http_5xx_with_false_ok_is_delivery_uncertain_not_replayed(tmp_path, monkeypatch):
    first, replay, calls = _notify_with_response(
        tmp_path,
        monkeypatch,
        "http_5xx_false_ok",
        b'{"ok":false,"error_code":500,"description":"Internal Server Error"}',
        http_status=502,
    )

    assert first["delivery"] == "delivery_uncertain"
    assert first["attempted"] == 1
    assert first["delivery_uncertain"] == 1
    assert replay["attempted"] == 0
    assert len(calls) == 1


def test_explicit_http_rejection_is_provider_rejected_not_pre_send(tmp_path, monkeypatch):
    first, replay, calls = _notify_with_response(
        tmp_path,
        monkeypatch,
        "provider_rejection",
        b'{"ok":false,"error_code":400,"description":"Bad Request"}',
        http_status=400,
    )

    assert first["delivery"] == "pending"
    assert first["attempted"] == 1
    assert first["provider_rejected"] == 1
    assert first["pre_send_failed"] == 0
    assert first["delivery_uncertain"] == 0
    assert replay["attempted"] == 1
    assert replay["provider_rejected"] == 1
    assert len(calls) == 2


def test_known_provider_rejection_stops_current_outbox_drain(tmp_path):
    outbox = load("test_rejected_outbox", "telegram_outbox.py")
    delivery = load("test_rejected_delivery", "telegram_delivery.py")
    database = tmp_path / "outbox.sqlite3"
    outbox.enqueue(
        database,
        event_key="cfo:subject:provider-rejected-drain",
        message="CFO report",
        created_at="2026-10-09T05:00:00Z",
        repeat_after_seconds=None,
    )
    calls = []

    class Rejected:
        started = True
        provider_id = None
        error = "provider_rejected:400"
        provider_rejected = True

    def notifier(message):
        calls.append(message)
        return Rejected()

    outcome = delivery.deliver_pending(outbox, database, notifier, limit=5)
    item = outbox.list_items(database)[0]

    assert outcome.attempted == 1
    assert outcome.provider_rejected == 1
    assert outcome.pre_send_failed == 0
    assert outcome.delivery_uncertain == 0
    assert item.status == "pending"
    assert item.last_error_code == "provider_rejected:400"
    assert calls == ["CFO report"]


def test_missing_message_id_is_uncertain_not_a_provider_receipt(tmp_path, monkeypatch):
    first, replay, calls = _notify_with_response(
        tmp_path,
        monkeypatch,
        "missing_message_id",
        b'{"ok":true,"result":{"chat":{"id":123}}}',
    )

    assert first["delivery"] == "delivery_uncertain"
    assert first["provider_message_id"] is None
    assert first["delivery_uncertain"] == 1
    assert replay["attempted"] == 0
    assert len(calls) == 1


def test_shared_sender_never_stringifies_invalid_message_ids(monkeypatch):
    delivery = load("test_effect_delivery_invalid_message_id", "telegram_delivery.py")

    class FakeClient:
        message_id = None

        @classmethod
        def from_env(cls, **_kwargs):
            return cls()

        def send_text(self, _message):
            return {"status": "delivered", "message_ids": [self.message_id]}

    telegram = type("Telegram", (), {"TelegramClient": FakeClient})
    monkeypatch.setattr(delivery, "_load", lambda *_args: telegram)

    FakeClient.message_id = 123
    valid = delivery.send_via_shared_client("report", chat_id="123")
    assert valid.provider_id == "123"
    assert valid.error is None

    for message_id in (None, "None", "", True, 0, -1):
        FakeClient.message_id = message_id
        result = delivery.send_via_shared_client("report", chat_id="123")

        assert result.started is True
        assert result.provider_id is None
        assert result.error == "receipt_missing"
