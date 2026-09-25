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


def _hard_prohibited_snapshot(visible_text: str) -> dict:
    from application_snapshot import build_envelope

    return build_envelope({
        "pass_id": "planner-visible-evidence",
        "lease_fence": {"task": "planner-test", "token": "1" * 32, "generation": 1},
        "observed_at": "2026-09-20T00:00:00Z",
        "objective": {
            "target_applications": 1,
            "max_applications": 1,
            "required_search_source_ids": ["source"],
        },
        "search_sources": [{
            "source_id": "source",
            "url": "https://coconala.com/requests",
            "page_index": 1,
            "card_request_ids": ["5268696"],
            "has_next": False,
            "exhausted": True,
            "screenshot_sha256": "2" * 64,
            "dom_sha256": "3" * 64,
        }],
        "request_details": [{
            "request_id": "5268696",
            "canonical_url": "https://coconala.com/requests/5268696",
            "title": "音声ドラマの女性案内人役",
            "category": "ナレーション・ボイス制作",
            "visible_text": visible_text,
            "accepting_applications": True,
            "budget_min_jpy": None,
            "budget_max_jpy": 5000,
            "applicants_count": 31,
            "contracted_count": 0,
            "applicants": [],
            "observed_at": "2026-09-20T00:00:00Z",
        }],
        "already_applied_ids": [],
    })


def _hard_prohibited_decision() -> dict:
    return {
        "request_id": "5268696",
        "business_class": "hard_prohibited",
        "reason_codes": [
            "mandatory_human_presence",
            "案内人(ミサト役)に加えて、劇中に登場する「広報アナウンサー」および「自動電話対応アナウンサー」のセリフ(計3行)の兼任をお願いいたします。",
        ],
        "proposal_text": None,
        "price_jpy": None,
        "deliver_date": None,
        "work_frequency": None,
        "weekly_hours_min": None,
        "weekly_hours_max": None,
        "screening_answers": [],
    }


def test_hard_prohibited_evidence_allows_a_small_visible_role_qualifier_insertion():
    planner = load_planner()
    snapshot = _hard_prohibited_snapshot(
        "募集内容\nメインの案内人役(ミサト役)に加えて、劇中に登場する「広報アナウンサー」"
        "および「自動電話対応アナウンサー」のセリフ(計3行)の兼任をお願いいたします。"
    )

    errors = planner.validate_decisions(
        snapshot, {"decisions": [_hard_prohibited_decision()]}, require_complete=True,
    )

    assert "decision[0]_hard_prohibited_evidence_not_in_visible_text" not in errors


def test_hard_prohibited_evidence_still_rejects_unrelated_visible_text():
    planner = load_planner()
    snapshot = _hard_prohibited_snapshot("募集内容\n別の募集内容だけが表示されています。")

    errors = planner.validate_decisions(
        snapshot, {"decisions": [_hard_prohibited_decision()]}, require_complete=True,
    )

    assert "decision[0]_hard_prohibited_evidence_not_in_visible_text" in errors


def test_boundary_only_hard_prohibited_evidence_repair_uses_exact_page_text():
    planner = load_planner()
    snapshot = _hard_prohibited_snapshot(
        "募集内容\nCodexを前提としてレクチャー可能な方を希望しています。\n"
        "・画面共有をしながらレクチャー可能な方"
    )
    decision = {
        "request_id": "5268696",
        "business_class": "hard_prohibited",
        "reason_codes": [
            "mandatory_human_presence",
            "画面共有をしながらレクチャー可能な方を希望しています。",
        ],
        "proposal_text": None,
        "price_jpy": None,
        "deliver_date": None,
        "work_frequency": None,
        "weekly_hours_min": None,
        "weekly_hours_max": None,
        "screening_answers": [],
    }

    repaired, repairs = planner.repair_hard_prohibited_evidence(
        snapshot, {"decisions": [decision]}
    )

    assert repaired["decisions"][0]["business_class"] == "hard_prohibited"
    assert repaired["decisions"][0]["reason_codes"][1] == (
        "画面共有をしながらレクチャー可能な方"
    )
    assert repairs[0]["method"] == "visible_line_common_substring"
    assert planner.validate_decisions(snapshot, repaired, require_complete=True) == []


def test_boundary_only_repair_keeps_specific_model_line_over_a_shared_suffix():
    planner = load_planner()
    snapshot = _hard_prohibited_snapshot(
        "募集内容\nLive2D Cubism Editor 5.3を使用した、Live2Dモデルのリギングをお願いしたいです。"
    )
    decision = {
        "request_id": "5268696",
        "business_class": "hard_prohibited",
        "reason_codes": [
            "original_illustration_or_modelling",
            "Live2Dモデルのリギング（モデリング）をお願いしたいです。",
        ],
        "proposal_text": None,
        "price_jpy": None,
        "deliver_date": None,
        "work_frequency": None,
        "weekly_hours_min": None,
        "weekly_hours_max": None,
        "screening_answers": [],
    }

    repaired, repairs = planner.repair_hard_prohibited_evidence(
        snapshot, {"decisions": [decision]}
    )

    assert repaired["decisions"][0]["reason_codes"][1] == "Live2Dモデルのリギング"
    assert repairs[0]["method"] == "visible_line_common_substring"


def test_hard_prohibited_evidence_repair_rejects_a_paraphrase():
    planner = load_planner()
    snapshot = _hard_prohibited_snapshot("募集内容\n画面共有で説明できます")
    decision = {
        "request_id": "5268696",
        "business_class": "hard_prohibited",
        "reason_codes": [
            "mandatory_human_presence",
            "画面共有をしながらレクチャー可能な方を希望しています。",
        ],
        "proposal_text": None,
        "price_jpy": None,
        "deliver_date": None,
        "work_frequency": None,
        "weekly_hours_min": None,
        "weekly_hours_max": None,
        "screening_answers": [],
    }

    repaired, repairs = planner.repair_hard_prohibited_evidence(
        snapshot, {"decisions": [decision]}
    )

    assert repaired["decisions"][0]["reason_codes"][1] == decision["reason_codes"][1]
    assert repairs == []


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
    assert "PLANNER_CACHE_VERSION = 5" in source


def test_coconala_prompt_scopes_music_boundary_and_preserves_other_prohibitions():
    planner = load_planner()

    prompt = planner.planner_prompt({"request_details": []})

    assert "Coconala application lane" in prompt
    assert "music_or_audio_production" in prompt
    assert "generated or prompted music/audio" in prompt
    assert "music software, music research, or writing about music is not music_or_audio_production" in prompt
    assert "only when no other hard-prohibition class applies" in prompt
