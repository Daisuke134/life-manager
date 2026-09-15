from pathlib import Path
import importlib.util
from datetime import date
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
    assert module._discovery_turn_count(exhaustive=False, source=None, query=None) == 3
    assert module._discovery_turn_count(exhaustive=False, source=object(), query=None) == 1
