import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "scripts" / "daily_loop.sh").read_text()


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
