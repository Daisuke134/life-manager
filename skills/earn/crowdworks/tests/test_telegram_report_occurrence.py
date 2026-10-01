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


def test_work_fit_blocker_notice_is_enqueued_once_per_contract_and_verdict(tmp_path, monkeypatch):
    module = load()
    root = tmp_path / "work-fit-blockers"
    root.mkdir()
    (root / "63570481.json").write_text(json.dumps({
        "work_id": "63570481", "title": "合成案件", "verdict": "refused:recruitment_or_selection_process"}), encoding="utf-8")
    (root / "bad.json").write_text("{", encoding="utf-8")
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(module.outbox, "enqueue",
                        lambda _db, key, message, _now: sent.append((key, message)) or True)

    assert module.enqueue_work_fit_blockers(tmp_path / "o.sqlite3", blockers_dir=root, now="2026-10-01T00:00:00+00:00") == 1
    key, message = sent[0]
    assert key == "crowdworks:paid-blocker:63570481:refused:recruitment_or_selection_process"
    assert "まだ行っていません" in message and "63570481" in message


def test_blocker_directory_matches_registry_state_root_and_paid_owner_state_path():
    root = Path(__file__).resolve().parents[4]
    registry = json.loads((root / "config/loop-registry.json").read_text(encoding="utf-8"))
    by_entry = {item["entrypoint"]: item for item in registry["loops"].values()
                if isinstance(item, dict) and "entrypoint" in item}
    paid = by_entry["skills/earn/crowdworks/scripts/paid-owner"]["state_root"]
    report = by_entry["skills/earn/crowdworks/scripts/report-owner"]["state_root"]
    assert paid == report
    assert '--state-path "$STATE_ROOT/paid"' in (root / "skills/earn/crowdworks/scripts/paid-owner").read_text(encoding="utf-8")
    module = load()
    assert str(module.PAID_BLOCKERS).endswith("/paid/work-fit-blockers")
    assert Path(paid).expanduser() == module.STATE


def test_blocker_directory_follows_state_root_env_and_defaults_without_it(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_STATE_ROOT", str(tmp_path))
    assert load().PAID_BLOCKERS == tmp_path / "paid" / "work-fit-blockers"
    monkeypatch.delenv("LIFE_MANAGER_STATE_ROOT")
    module = load()
    assert module.PAID_BLOCKERS == module.STATE / "paid" / "work-fit-blockers"
