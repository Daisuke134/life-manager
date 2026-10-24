from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/crowdworks/scripts/telegram_report.py"


def load():
    spec = importlib.util.spec_from_file_location(
        "crowdworks_telegram_report_occurrence_test", PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_wake_summary_key_binds_runtime_occurrence(tmp_path, monkeypatch):
    module = load()
    status = tmp_path / "application-owner.json"
    status.write_text(json.dumps({"observed_at": "2026-09-19T00:00:00+00:00"}), encoding="utf-8")
    captured: list[str] = []
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "crowdworks-revenue-report:run-1")
    monkeypatch.setattr(module.summary, "summarise_apply_wake", lambda **_kwargs: "wake")
    monkeypatch.setattr(
        module.outbox,
        "enqueue",
        lambda _database, event_key, _message, _now: captured.append(event_key) or True,
    )

    assert module.enqueue_wake_summary(
        tmp_path / "outbox.sqlite3", status_path=status, ledger_path=tmp_path / "missing.jsonl",
        now="2026-09-19T00:01:00+00:00",
    ) == 1
    assert captured == ["crowdworks:wake:crowdworks-revenue-report:run-1:2026-09-19T00:00:00+00:00"]


def test_wake_summary_without_runtime_occurrence_keeps_legacy_key(tmp_path, monkeypatch):
    module = load()
    status = tmp_path / "application-owner.json"
    status.write_text(json.dumps({"observed_at": "2026-09-19T00:00:00+00:00"}), encoding="utf-8")
    captured: list[str] = []
    monkeypatch.delenv("LIFE_MANAGER_OCCURRENCE_ID", raising=False)
    monkeypatch.setattr(module.summary, "summarise_apply_wake", lambda **_kwargs: "wake")
    monkeypatch.setattr(
        module.outbox,
        "enqueue",
        lambda _database, event_key, _message, _now: captured.append(event_key) or True,
    )

    assert module.enqueue_wake_summary(
        tmp_path / "outbox.sqlite3", status_path=status, ledger_path=tmp_path / "missing.jsonl",
        now="2026-09-19T00:01:00+00:00",
    ) == 1
    assert captured == ["crowdworks:wake:2026-09-19T00:00:00+00:00"]


def test_run_reports_provider_rejection_as_not_ok(tmp_path, monkeypatch):
    module = load()
    monkeypatch.setattr(module, "enqueue_decisions", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(module, "enqueue_declines", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(module, "enqueue_wake_summary", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        module.delivery,
        "deliver_pending",
        lambda *_args, **_kwargs: SimpleNamespace(
            attempted=1, delivered=0, delivery_uncertain=0,
            pre_send_failed=0, provider_rejected=1,
        ),
    )

    result = module.run(database=tmp_path / "outbox.sqlite3", now="2026-10-09T05:30:00Z")

    assert result["ok"] is False
    assert result["provider_rejected"] == 1
    assert result["pre_send_failed"] == 0
    assert result["delivery_uncertain"] == 0


def test_report_uses_the_same_custom_environment_file_as_setup(tmp_path, monkeypatch):
    from skills._shared import telegram

    home = (tmp_path / "different-owner").resolve()
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    custom = home / "settings" / "notifications.env"
    custom.parent.mkdir(mode=0o700)
    custom.write_text("TELEGRAM_BOT_TOKEN=synthetic-private-token\n")
    custom.chmod(0o600)
    monkeypatch.setenv("LIFE_MANAGER_ENV_FILE", str(custom))
    monkeypatch.setenv("CROWDWORKS_REPORT_CHAT", "synthetic-owner-chat")
    module = load()
    from skills.earn.crowdworks.scripts.install_local import _report_missing

    assert _report_missing(home, {"LIFE_MANAGER_ENV_FILE": str(custom)}) == []
    sent = []
    monkeypatch.setattr(module.delivery, "_load", lambda *_args: telegram)
    monkeypatch.setattr(telegram.TelegramClient, "send_text",
                        lambda self, message: sent.append(message) or {"message_ids": [701]})
    for name in ("enqueue_decisions", "enqueue_declines", "enqueue_wake_summary"):
        monkeypatch.setattr(module, name, lambda *_args, **_kwargs: 0)
    database = home / "outbox.sqlite3"
    module.outbox.enqueue(database, "synthetic-report", "owner report", "2026-10-24T00:00:00Z")

    result = module.run(database=database, now="2026-10-24T00:01:00Z")

    assert result["ok"] is True
    assert result["delivered"] == 1
    assert result["pre_send_failed"] == result["delivery_uncertain"] == 0
    assert sent == ["owner report"]
    assert not (home / ".local/state/life-manager/.env").exists()
