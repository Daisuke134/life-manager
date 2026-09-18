from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


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
