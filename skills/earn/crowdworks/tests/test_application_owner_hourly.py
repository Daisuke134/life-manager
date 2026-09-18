from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


PATH = Path(__file__).resolve().parents[1] / "scripts" / "application_owner.py"


def load():
    spec = importlib.util.spec_from_file_location("crowdworks_application_owner_hourly_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_hourly_rate_uses_top_of_official_range():
    module = load()

    assert module._hourly_rate("仕事の概要 時間単価制 1,500円 〜 2,000円") == 2000
    assert module._hourly_rate("仕事の概要 固定報酬制 50,000円") is None


def test_status_binds_runtime_occurrence_for_later_effect_reconciliation():
    module = load()

    assert module._bind_runtime_occurrence(
        {"status": "proposal_form_changed", "effect_delta": 0},
        "crowdworks-revenue-application:run-1",
    ) == {
        "status": "proposal_form_changed",
        "effect_delta": 0,
        "occurrence_id": "crowdworks-revenue-application:run-1",
    }


def test_receipt_writer_persists_runtime_occurrence(tmp_path, monkeypatch):
    module = load()
    module.LEDGER = tmp_path / "application-receipts.jsonl"
    monkeypatch.setenv(
        "LIFE_MANAGER_OCCURRENCE_ID", "crowdworks-revenue-application:run-1"
    )

    module._append({"record_type": "application_receipt", "status": "verified"})

    receipt = json.loads(module.LEDGER.read_text(encoding="utf-8"))
    assert receipt["occurrence_id"] == "crowdworks-revenue-application:run-1"


def test_historical_receipt_writer_does_not_bind_current_runtime_occurrence(tmp_path, monkeypatch):
    module = load()
    module.LEDGER = tmp_path / "application-receipts.jsonl"
    monkeypatch.setenv(
        "LIFE_MANAGER_OCCURRENCE_ID", "crowdworks-revenue-application:run-1"
    )

    module._append(
        {"record_type": "application_receipt", "status": "verified"},
        bind_occurrence=False,
    )

    receipt = json.loads(module.LEDGER.read_text(encoding="utf-8"))
    assert "occurrence_id" not in receipt


def test_reconcile_import_uses_unbound_historical_writer(tmp_path, monkeypatch):
    module = load()
    module.STATE = tmp_path
    module.TRANSACTION = tmp_path / "application-transaction.json"
    module.LEDGER = tmp_path / "application-receipts.jsonl"
    module.TRANSACTION.write_text(
        '{"pending":{"one":{"project_id":"123"}}}\n', encoding="utf-8"
    )
    monkeypatch.setenv(
        "LIFE_MANAGER_OCCURRENCE_ID", "crowdworks-revenue-application:run-1"
    )
    monkeypatch.setattr(module.application, "find_proposal_id", lambda _page, _project: "456")

    class Outcome:
        application_verified = True

    def reconcile_existing_application(**kwargs):
        kwargs["ledger_writer"](
            {"record_type": "application_receipt", "status": "verified"}
        )
        return Outcome()

    monkeypatch.setattr(
        module.application, "reconcile_existing_application", reconcile_existing_application
    )

    assert module._reconcile(object()) == 1
    receipt = json.loads(module.LEDGER.read_text(encoding="utf-8"))
    assert "occurrence_id" not in receipt


def test_discovery_groups_follow_durable_cursor_not_wall_clock(tmp_path):
    module = load()
    module.STATE = tmp_path
    (tmp_path / "application-owner.json").write_text(
        '{"next_group_index":5}\n', encoding="utf-8"
    )

    early = module._groups(object())
    late = module._groups(object())

    assert early == module.JOB_GROUPS[5:10]
    assert late == early
