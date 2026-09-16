from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_planner():
    path = Path(__file__).resolve().parents[1] / "scripts" / "application_planner.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("application_planner_focus_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prompt_prioritizes_async_strengths_and_rejects_operational_labor():
    planner = load_planner()

    prompt = planner.planner_prompt({"request_details": []})

    assert "software / landing_page / article / strategy" in prompt
    assert "outreach_or_account_operations" in prompt
    assert "mandatory_desktop_or_browser_operations" in prompt
    assert "定期購入・保守・運用のように毎月続くもの" not in prompt


def test_common_policy_never_uses_skills_as_admission_or_execution_authority():
    planner = load_planner()

    policy = planner.common_marketplace_feasibility_policy()
    prompt = planner.planner_prompt({"request_details": []})
    normalized = " ".join(policy.split())

    assert "never an application whitelist" in policy
    assert "Missing an exact Skill" in normalized
    assert "Compose or build the execution method after contract" in normalized
    assert "Submit is the default for every feasible job" in normalized
    assert "unverified payment" in normalized
    assert "never standalone skip reasons" in normalized
    assert "music" not in policy.casefold()
    assert "audio" not in policy.casefold()
    assert "music_or_audio_production" not in policy
    assert policy in prompt


def test_prompt_rejects_uncontrolled_numeric_results_but_allows_meeting_handoff():
    planner = load_planner()
    prompt = planner.planner_prompt({"request_details": []})

    assert "uncontrolled_numeric_outcome" in prompt
    assert "shared Telegram human-handoff contract" in prompt
    assert "Google Calendar" in prompt
    assert "Life Manager call the owner" in prompt
    assert "even when that step explicitly uses phone, live voice, or live video" in prompt
    assert "only when synchronous attendance" in prompt
    assert "unless the listing explicitly requires synchronous phone" not in prompt


def test_policy_change_invalidates_coconala_decision_caches():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "application_parent.py").read_text(
        encoding="utf-8"
    )
    assert "INELIGIBLE_CACHE_VERSION = 3" in source
    assert "PLANNER_CACHE_VERSION = 4" in source


def test_coconala_prompt_scopes_music_boundary_and_preserves_other_prohibitions():
    planner = load_planner()

    prompt = planner.planner_prompt({"request_details": []})

    assert "Coconala application lane" in prompt
    assert "music_or_audio_production" in prompt
    assert "generated or prompted music/audio" in prompt
    assert "music software, music research, or writing about music is not music_or_audio_production" in prompt
    assert "only when no other hard-prohibition class applies" in prompt
