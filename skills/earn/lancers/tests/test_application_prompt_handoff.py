from pathlib import Path
import importlib.util
from datetime import date, datetime, timedelta, timezone
import sys


def _load_application_loop():
    path = Path(__file__).resolve().parents[1] / "scripts" / "application_loop.py"
    spec = importlib.util.spec_from_file_location("lancers_application_loop_prompt_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bounded_live_meeting_handoff_does_not_conflict_with_human_deliverable_refusal():
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "application_loop.py"
    ).read_text(encoding="utf-8")

    assert "Zoom・電話・video meetingが明示的に必須でも拒否せず" in source
    assert "同期参加そのものが成果物ならmandatory_human_presence" in source
    assert "shared Telegram human-handoff" in source
    assert "必須ならhard_prohibitedにする" not in source
    assert "SKIP_CACHE_VERSION = 3" in source


def test_planner_prompt_forbids_tools_and_requires_complete_submit_fields():
    module = _load_application_loop()
    prompt = module.build_planner_prompt(
        [{
            "external_id": "123",
            "title": "業務自動化システム開発",
            "description": "確認済みの公開案件です。",
            "category": "system",
            "schema_version": 1,
            "record_type": "opportunity",
            "platform": "lancers",
            "url": "https://www.lancers.jp/work/detail/123",
            "budget_type": "fixed",
            "budget_min_minor": 10000,
            "budget_max_minor": 50000,
            "currency": "JPY",
            "buyer_external_id": "buyer-1",
            "observed_at": "2026-09-15T00:00:00Z",
        }],
        date(2026, 9, 15),
    )

    assert "ツールを使わず" in prompt
    assert "submit_requiredの場合" in prompt
    assert "proposal_text・price_jpy・deliver_dateをnullにしない" in prompt


def test_exhaustive_discovery_has_one_bounded_turn():
    module = _load_application_loop()

    assert module._discovery_turn_count(exhaustive=True, source=None, query=None) == 1
    assert module._discovery_turn_count(exhaustive=False, source=None, query=None) == 1
    assert module._discovery_turn_count(exhaustive=False, source=object(), query=None) == 1


def test_transient_pending_failure_does_not_abort_fresh_discovery(tmp_path, monkeypatch):
    module = _load_application_loop()
    pending = {
        "project_id": "5601059",
        "amount_minor": 88000,
        "delivery_due_on": "2026-09-24",
    }
    monkeypatch.setattr(module.application_tick, "read_pending_descriptor", lambda _path: pending)
    monkeypatch.setattr(
        module.application_tick.shared,
        "read_pending_descriptors",
        lambda _path: [pending],
    )
    monkeypatch.setattr(
        module,
        "_reconcile_pending",
        lambda *_args, **_kwargs: module.ApplicationLoopResult(
            False, error="account_unavailable", project_id="5601059"
        ),
    )
    discoveries = []

    def discoverer(**_kwargs):
        discoveries.append(True)
        return {"ok": True, "opportunities": [], "observed_count": 0, "already_decided_count": 0}

    result = module.run_loop(
        state_path=tmp_path / "application.json",
        evidence_root=tmp_path / "evidence",
        discoverer=discoverer,
        clock=lambda: datetime(2026, 9, 15, tzinfo=timezone.utc),
    )

    assert discoveries == [True]
    assert result["reason"] == "no_eligible_project"
    assert result["unresolved_project_id"] == "5601059"


def test_pending_descriptor_rotates_by_attempt(tmp_path, monkeypatch):
    module = _load_application_loop()
    descriptors = [
        {"project_id": "1", "amount_minor": 1, "delivery_due_on": "2026-09-16"},
        {"project_id": "2", "amount_minor": 1, "delivery_due_on": "2026-09-16"},
        {"project_id": "3", "amount_minor": 1, "delivery_due_on": "2026-09-16"},
    ]
    monkeypatch.setattr(module.application_tick.shared, "read_pending_descriptors", lambda _path: descriptors)

    state_path = tmp_path / "application.json"
    first = module._pending_descriptor_for_wake(
        state_path, datetime(2026, 9, 15, tzinfo=timezone.utc)
    )
    second = module._pending_descriptor_for_wake(
        state_path,
        datetime(2026, 9, 15, tzinfo=timezone.utc) + timedelta(seconds=60),
    )

    assert first["project_id"] != second["project_id"]


def test_pending_descriptor_visits_every_item_when_wakes_skip_clock_slots(tmp_path, monkeypatch):
    module = _load_application_loop()
    descriptors = [
        {"project_id": str(i), "amount_minor": 1, "delivery_due_on": "2026-09-16"}
        for i in range(1, 5)
    ]
    monkeypatch.setattr(module.application_tick.shared, "read_pending_descriptors", lambda _path: descriptors)
    state_path = tmp_path / "application.json"
    start = datetime(2026, 9, 15, tzinfo=timezone.utc)

    visited = [module._pending_descriptor_for_wake(
        state_path, start + timedelta(minutes=2 * i)
    )["project_id"] for i in range(4)]

    assert visited == ["1", "2", "3", "4"]
    assert module._pending_descriptor_for_wake(state_path, start + timedelta(minutes=8))["project_id"] == "1"
    assert (tmp_path / "application-pending-cursor.json").stat().st_mode & 0o777 == 0o600


def test_default_discovery_reads_one_rotating_query_per_wake(tmp_path, monkeypatch):
    module = _load_application_loop()
    calls = []

    def discover(**kwargs):
        calls.append(kwargs)
        return {"ok": False, "error": "no_normalized_opportunities", "opportunities": []}

    monkeypatch.setattr(module.status, "run_discovery", discover)

    result = module._run_default_discovery(
        datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc),
        20.0,
        tmp_path / "application.json",
    )

    assert result["ok"] is True
    assert len(calls) == 1
    assert calls[0]["query"] == module._discovery_query(
        datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    )
