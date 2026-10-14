import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "scripts" / "daily_loop.sh").read_text()
AUTO = Path(__file__).resolve().parents[1]
CP1_ORDER = "Required CP1 tab order: 基本情報 → Agent ワークスペース → 価格設定 last."
CP1_STAY_ON_PRICING = "After entering 価格設定, do not switch tabs before PRICES_MATCH, save, and confirmation."
CP1_RESTORE_AFTER_SWITCH = "If you leave 価格設定, re-enter every plan price/cap/trial and daily quota, then rerun PRICES_MATCH."
CP1_REANCHOR_AFTER_CARD_CHANGE = "After each Add Plan or period change, re-read state and match the card by its visible Period label; never reuse a positional index."


def _pattern():
    m = re.search(r"grep -qE '(\^\([^']+\))'", SRC)
    assert m, "resume re-prepare condition not found"
    return re.compile(m.group(1))


def test_empty_update_draft_is_reprepared():
    # Hook Lab 8123079349 v1.0.4 (2026-09-29): no confirmed model, blank package.
    assert _pattern().search("MODEL_UNKNOWN no-confirmed-model-yet")


def test_mismatch_still_reprepared_and_other_unknowns_are_not():
    p = _pattern()
    assert p.search("MODEL_MISMATCH anthropic/claude-sonnet-4.6 deepseek/deepseek-v4.1-flash")
    assert not p.search("MODEL_UNKNOWN detail-fetch-failed:URLError")
    assert not p.search("MODEL_MATCH deepseek/deepseek-v4.1-flash")


def test_cp1_confirmed_draft_is_not_reprepared():
    # Re-preparing a draft whose CP1 is already confirmed resets that confirmation.
    assert not _pattern().search("MODEL_UNKNOWN cp1-confirmed-awaiting-cp2")


def test_same_agent_reprepare_prompt_completes_all_cp1_tabs_before_finish():
    match = re.search(
        r'if \[ -n "\$REUSE_PREPARE_ID" \]; then\n    PROMPT="\$PROMPT\n(.*?)"\n  else',
        SRC,
        re.DOTALL,
    )
    assert match, "same-agent re-prepare handoff prompt not found"
    prompt = match.group(1)

    for required in (
        "fresh version $F_VERSION",
        "all three CP1 tabs",
        "Basic Info / 基本情報",
        "Agent ワークスペース",
        "Pricing / 価格設定",
        "EDIT_URL_FILE",
        "CONFIG_PATH",
        "TARGET PRICING",
        "scripts/cp1_agent.py prices $F_LISTING",
        "PRICES_MATCH",
        "下書きを保存",
        "提出を確認",
        "latest_version.agent_version_id=$F_VERSION",
        "latest_version.is_confirmed_skills=true",
    ):
        assert required in prompt

    assert "Do only step 5b" not in prompt


def test_cp1_tab_order_is_consistent_across_every_instruction_surface():
    surfaces = {
        "CP1_AGENTIC.md": (AUTO / "CP1_AGENTIC.md").read_text(),
        "DAILY_LOOP.md": (AUTO / "DAILY_LOOP.md").read_text(),
        "PUBLISHING_RUNBOOK.md": (AUTO / "PUBLISHING_RUNBOOK.md").read_text(),
    }
    for name, text in surfaces.items():
        normalized = " ".join(text.split())
        for contract in (CP1_ORDER, CP1_STAY_ON_PRICING, CP1_RESTORE_AFTER_SWITCH, CP1_REANCHOR_AFTER_CARD_CHANGE):
            assert " ".join(contract.split()) in normalized, f"{name} missing CP1 contract: {contract}"

    # daily_loop.sh injects two distinct prompts: new-version re-prepare and
    # ordinary step 5b. Both must carry the same safe tab-order contract.
    normalized_src = " ".join(SRC.split())
    for contract in (CP1_ORDER, CP1_STAY_ON_PRICING, CP1_RESTORE_AFTER_SWITCH, CP1_REANCHOR_AFTER_CARD_CHANGE):
        assert normalized_src.count(" ".join(contract.split())) == 2, f"daily_loop.sh must include twice: {contract}"
