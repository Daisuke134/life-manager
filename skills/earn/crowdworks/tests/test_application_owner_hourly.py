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


def test_application_owner_clears_host_pre_effect_hint(tmp_path, monkeypatch):
    module = load()
    hint = tmp_path / "entrypoint-result.json"
    hint.write_text('{"status":"pre_effect_failure","effect":0}\n', encoding="utf-8")
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))

    module._clear_pre_effect_hint()

    assert not hint.exists()


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


def test_applied_keeps_pending_projects_when_receipt_ledger_is_unreadable(tmp_path):
    module = load()
    module.LEDGER = tmp_path / "missing" / "application-receipts.jsonl"
    module.TRANSACTION = tmp_path / "application-transaction.json"
    module.TRANSACTION.write_text(
        '{"pending":{"one":{"project_id":"123"}}}\n', encoding="utf-8"
    )

    assert "123" in module._applied()


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


def _opportunity_snapshot():
    return {
        "ok": True,
        "platform": "crowdworks",
        "observed_at": "2026-09-30T10:00:00Z",
        "opportunities": [{
            "external_id": "123",
            "title": "業務自動化の案件",
            "description": "公開案件本文です。",
            "category": "システム開発",
            "url": "https://crowdworks.jp/public/jobs/123",
            "observed_at": "2026-09-30T10:00:00Z",
            "budget_type": "fixed",
            "currency": "JPY",
        }],
        "already_applied_ids": [],
    }


def test_live_crowdworks_observation_is_written_before_effect(tmp_path):
    module = load()
    evidence = tmp_path / "evidence"

    summary = module.record_crowdworks_live_observation(
        _opportunity_snapshot(),
        {"decisions": [{"request_id": "123", "business_class": "submit_required"}]},
        evidence_dir=evidence,
        pass_id="pass-1",
        store_root=tmp_path / "observations",
    )

    assert summary["eligible"] == 1
    assert (evidence / "opportunity-observation-summary.json").is_file()


def test_crowdworks_source_failure_is_explicit(tmp_path):
    module = load()
    evidence = tmp_path / "evidence"

    module.record_crowdworks_observation_source_failure(
        evidence, "pass-1", RuntimeError("browser unavailable")
    )

    payload = json.loads(
        (evidence / "opportunity-observation-summary.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "source_collect_failed"
    assert payload["next_action"] == "retry_crowdworks_public_snapshot_read_only"


def test_snapshot_builder_binds_platform_and_applied_ids():
    module = load()
    snapshot = module._crowdworks_snapshot(
        [{"external_id": "123", "title": "案件"}],
        {"456"},
        "2026-09-30T10:00:00Z",
    )

    assert snapshot == {
        "ok": True,
        "platform": "crowdworks",
        "observed_at": "2026-09-30T10:00:00Z",
        "opportunities": [{"external_id": "123", "title": "案件"}],
        "already_applied_ids": ["456"],
    }


def test_candidate_snapshot_contains_fetched_job_and_submit_decision(tmp_path):
    module = load()
    module.STATE = tmp_path
    module.LEDGER = tmp_path / "application-receipts.jsonl"
    module.TRANSACTION = tmp_path / "application-transaction.json"
    module._work_fit_verdict = lambda *_args: None
    module.account._wait = lambda _page: None

    class Locator:
        def __init__(self, body=False):
            self.body = body

        def evaluate_all(self, _script):
            return [{"href": "/public/jobs/123", "title": "業務自動化の案件"}]

        def inner_text(self):
            return (
                "システム開発の仕事の依頼 仕事の概要 固定報酬制 10,000円 "
                "仕事の詳細 公開案件本文です クライアント情報"
            )

    class Page:
        def locator(self, selector):
            return Locator(body=selector == "body")

        def goto(self, _url):
            return None

        def wait_for_timeout(self, _milliseconds):
            return None

    listings = [{
        "terms": ["業務自動化"],
        "tiers": [{"price_jpy": 10000, "scope": "自動化", "delivery_days": 7}],
    }]
    candidate, _listing, _tier, inspected = module._candidate(
        Page(), listings, ("development",), observed_at="2026-09-30T10:00:00Z"
    )

    assert candidate["external_id"] == "123"
    assert inspected["snapshot"]["opportunities"][0]["external_id"] == "123"
    assert inspected["decisions"] == [{
        "request_id": "123", "business_class": "submit_required",
    }]


def test_main_records_observation_before_crowdworks_application_effect(tmp_path, monkeypatch):
    module = load()
    module.STATE = tmp_path
    module.TRANSACTION = tmp_path / "application-transaction.json"
    module.LEDGER = tmp_path / "application-receipts.jsonl"
    events = []

    class Ensure:
        authenticated = True
        error = None
        status = "authenticated"

    class Page:
        def close(self):
            events.append("close")

    class Context:
        def new_page(self):
            return Page()

    class Browser:
        contexts = [Context()]

    class Tick:
        application_verified = True
        submitted = True
        error = None
        reason = "verified"

        def to_dict(self):
            return {"ok": True, "application_verified": True, "submitted": True}

    monkeypatch.setattr(module.account, "_owner", lambda: True)
    monkeypatch.setattr(module.account, "run_ensure", lambda **_kwargs: Ensure())
    monkeypatch.setattr(module.account, "_browser", lambda _url: Browser())
    monkeypatch.setattr(module.profile, "run_apply", lambda **_kwargs: {"ok": True})
    monkeypatch.setattr(module, "_reconcile", lambda _page: 0)
    monkeypatch.setattr(module, "_listings", lambda: [])
    monkeypatch.setattr(module, "_groups", lambda *_args: ())
    monkeypatch.setattr(
        module,
        "_candidate",
        lambda *_args, **_kwargs: (
            {"external_id": "123", "title": "案件"},
            {"value_prop": "自動化", "deliverables": [], "required_inputs": []},
            {"price_jpy": 1000, "delivery_days": 7, "scope": "自動化"},
            {"snapshot": _opportunity_snapshot(), "decisions": [{"request_id": "123", "business_class": "submit_required"}]},
        ),
    )
    monkeypatch.setattr(module, "record_crowdworks_live_observation", lambda *args, **kwargs: events.append("observe"))
    monkeypatch.setattr(module.application, "execute_application", lambda **_kwargs: (events.append("apply") or Tick()))
    monkeypatch.setattr(module, "_write_status", lambda _value: None)

    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(tmp_path / "hint.json"))
    assert module.main() == 0
    assert events[:2] == ["observe", "apply"]
