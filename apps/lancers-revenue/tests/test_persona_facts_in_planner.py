"""The planner cannot judge an attribute requirement without being told the attributes.

Measured 2026-09-07, after the discovery queries were re-aimed at build work: every posting was
still refused, and two of the refusals were wrong.

    【急募】C++でのWindowsアプリ不具合修正   mandatory_human_presence   -- correct, a live call
    ECサイトの在庫確認業務                    mandatory_attribute_fabrication on 「・年齢：」
    バイマ出品作業                            mandatory_attribute_fabrication on 「・20歳以上の方」

`・年齢：` is a form field, and the persona is 24, so both can be answered honestly. The class
definition was right; the planner had no attributes to check the requirement against, and defaulted
to refusing. Refusing costs a real application every time.

Run: python3 -m pytest apps/lancers-revenue/tests/test_persona_facts_in_planner.py
"""

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

LOOP = Path(__file__).resolve().parents[3] / "skills" / "earn" / "lancers" / "scripts" / "application_loop.py"


def _module():
    spec = importlib.util.spec_from_file_location("lancers_loop_persona", LOOP)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


loop = _module()


def test_the_planner_is_told_the_attributes_it_must_judge():
    for fragment in ("応募者の確認済み属性", "年齢", "居住地", "国籍"):
        assert fragment in loop.PLANNER_RULES


def test_a_form_field_asking_an_attribute_is_not_fabrication():
    """The instruction has to say this outright; the class name alone invites the wrong reading."""
    assert "属性を尋ねる入力欄の存在" in loop.PLANNER_RULES
    assert "拒否理由にしない" in loop.PLANNER_RULES


def test_fabrication_is_scoped_to_requirements_that_contradict_the_facts():
    assert "確認済み属性と矛盾する必須要件だけに使う" in loop.PLANNER_RULES


def test_the_age_is_computed_not_hardcoded():
    """A hardcoded age silently becomes a lie on a birthday."""
    profile = Path("~/.config/anicca/job-search/profile.json").expanduser()
    if not profile.exists():
        assert loop.PERSONA_FACTS["age"].isdigit()
        return
    born = date.fromisoformat(json.loads(profile.read_text(encoding="utf-8"))["candidate"]["date_of_birth"])
    today = date.today()
    expected = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    assert loop.PERSONA_FACTS["age"] == str(expected)


def test_only_what_a_posting_may_ask_is_exposed():
    """Age, residence and citizenship answer application questions. The name and history do not,
    and belong nowhere near a prompt that produces buyer-facing text."""
    assert set(loop.PERSONA_FACTS) == {"age", "base", "citizenship"}
    assert "Daisuke" not in loop.PLANNER_RULES
    assert "date_of_birth" not in loop.PLANNER_RULES


def test_a_missing_profile_does_not_break_the_lane():
    """The lane must still judge if the private SSOT is unreadable."""
    facts = loop._persona_facts()
    assert facts["age"] and facts["base"] and facts["citizenship"]


def test_live_calls_are_refused_only_when_they_are_the_deliverable():
    """Selection and kickoff use minimal HITL; synchronous work itself remains prohibited."""
    assert "mandatory_human_presence" in loop.HARD_PROHIBITION_CLASSES
    assert "同期参加そのものが成果物ならmandatory_human_presenceとしてhard_prohibitedにする" in loop.PLANNER_RULES
    assert "契約選考面談・kickoff・通常の進捗確認" in loop.PLANNER_RULES
