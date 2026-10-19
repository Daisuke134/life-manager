"""Experiment 1 (bid the buyer's budget lower bound) A/B contract."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evaluator = _load("experiment_evaluator")
parent = _load("application_parent")

EXP = "coconala-bid-budget-lower-bound-v1"
T0 = 1_790_000_000
DAY = 86_400
CONFIG = Path(__file__).resolve().parents[1] / "config" / "experiments.json"


def _spec() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))["queue"][0]


def _strategy(**experiment) -> dict:
    started = evaluator.start_ab({}, _spec(), now=T0)
    assert started["ok"], started
    started["experiment"].update(experiment)
    return started["strategy"]


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _applied(arm: str, count: int) -> list[dict]:
    return [
        {"requestId": f"{arm}{i}", "title": f"{arm}案件{i}", "ts": T0 + 60,
         "experiment_id": EXP, "experiment_arm": arm}
        for i in range(count)
    ]


def _sales(*sales: tuple[str, int, int]) -> tuple[dict, dict]:
    """(title, talkroom, net yen) -> (CFO readback, talkroom -> title map)."""
    records = [
        {"work_external_id": f"talkroom-{room}", "net_amount_minor": jpy,
         "occurred_at": _iso(T0 + 3 * DAY)}
        for _title, room, jpy in sales
    ]
    titles = {str(room): title for title, room, _jpy in sales}
    return {"receipt_map": {"complete": True, "records": records}}, titles


def _assess(strategy, applied, sales, *, now=T0 + 15 * DAY, attempts=()):
    readback, titles = sales
    return evaluator.assess_ab(
        strategy, applied_rows=applied, readback=readback, revenue_titles=titles,
        attempts=list(attempts), outcomes=[], now=now,
    )


def _status(result) -> str:
    return result["strategy"]["experiments"][-1]["status"]


def test_assign_arm_is_deterministic_and_balanced() -> None:
    arms = [evaluator.assign_arm(EXP, str(5_000_000 + i)) for i in range(1000)]
    assert arms == [evaluator.assign_arm(EXP, str(5_000_000 + i)) for i in range(1000)]
    assert set(arms) == {"A", "B"}
    assert 450 <= arms.count("B") <= 550


def test_keep_when_b_wins_contracts_and_yen_per_application() -> None:
    applied = _applied("A", 150) + _applied("B", 150)
    sales = _sales(("A案件0", 1, 5_000), ("B案件0", 2, 3_000), ("B案件1", 3, 3_000),
                   ("B案件2", 4, 3_000))
    result = _assess(_strategy(), applied, sales)
    assert _status(result) == "kept"
    assert result["strategy"]["adopted_bid_policy"] == "budget_lower_bound"
    assert result["events"][-1]["status"] == "kept"


def test_revert_when_a_leads_by_two_contracts() -> None:
    applied = _applied("A", 150) + _applied("B", 150)
    sales = _sales(("A案件0", 1, 5_000), ("A案件1", 2, 5_000), ("B案件0", 3, 3_000),
                   ("A案件2", 4, 5_000))
    result = _assess(_strategy(), applied, sales)
    assert _status(result) == "reverted"
    assert "adopted_bid_policy" not in result["strategy"]


def test_defer_until_samples_and_cohort_age() -> None:
    sales = _sales(("A案件0", 1, 5_000))
    young = _assess(_strategy(), _applied("A", 150) + _applied("B", 150), sales,
                    now=T0 + 13 * DAY)
    small = _assess(_strategy(), _applied("A", 149) + _applied("B", 150), sales)
    for result in (young, small):
        assert _status(result) == "active"
        assert result["events"] == []
    assert young["summary"]["reason"] == "cohort_too_young"
    assert small["summary"]["reason"] == "insufficient_applications"


def test_cap_reverts_to_a_without_decision() -> None:
    applied = _applied("A", 400) + _applied("B", 400)
    sales = _sales(("A案件0", 1, 5_000), ("B案件0", 2, 5_000))
    result = _assess(_strategy(), applied, sales)
    assert _status(result) == "reverted"
    assert result["events"][-1]["evaluation"]["reason"] == "sample_cap_without_decision"


def test_guardrail_reverts_on_b_send_failures_before_samples() -> None:
    attempts = [
        {"experiment_id": EXP, "experiment_arm": arm, "request_id": f"{arm}{i}",
         "outcome": "failed" if (arm == "B" and i < 6) or (arm == "A" and i < 1) else "confirmed"}
        for arm in ("A", "B") for i in range(20)
    ]
    result = _assess(_strategy(), _applied("A", 20) + _applied("B", 20),
                     _sales(), attempts=attempts)
    assert _status(result) == "reverted"
    assert result["events"][-1]["evaluation"]["reason"] == "guardrail_send_failure"


def test_unjoinable_receipts_are_unattributed_never_zero() -> None:
    sales = _sales(("どの応募とも一致しないサービス", 9, 7_000))
    result = _assess(_strategy(), _applied("A", 10) + _applied("B", 10), sales)
    assert result["summary"]["unattributed"] == {"count": 1, "jpy": 7_000}

    missing = evaluator.assess_ab(
        _strategy(), applied_rows=_applied("A", 150) + _applied("B", 150), readback=None,
        revenue_titles={}, attempts=[], outcomes=[], now=T0 + 15 * DAY,
    )
    assert missing["summary"]["unattributed"] is None
    assert missing["summary"]["arms"]["A"]["net_jpy"] is None
    assert missing["summary"]["reason"] == "revenue_readback_unavailable"
    assert _status(missing) == "active"

    readback, _titles = sales
    no_titles = _assess(_strategy(), _applied("A", 150) + _applied("B", 150), (readback, {}))
    assert no_titles["summary"]["unattributed"] is None
    assert no_titles["summary"]["reason"] == "revenue_readback_unavailable"


def test_overlapping_active_experiments_are_quarantined() -> None:
    strategy = _strategy()
    strategy["experiments"].append({"id": "other", "status": "active", "mode": "ab"})
    result = _assess(strategy, [], _sales())
    assert {row["status"] for row in result["strategy"]["experiments"]} == {"quarantined"}


def test_legacy_assess_does_not_quarantine_an_ab_experiment() -> None:
    result = evaluator.assess(_strategy(), None, now=T0 + DAY)
    assert _status(result) == "active"


def test_evaluate_auto_starts_next_queued_spec_once(tmp_path: Path) -> None:
    strategy_path = tmp_path / "strategy.json"
    strategy_path.write_text("{}", encoding="utf-8")
    kwargs = dict(
        strategy_path=strategy_path, funnel_path=tmp_path / "funnel.jsonl",
        events_path=tmp_path / "events.jsonl", applied_path=tmp_path / "applied.jsonl",
        readback_path=tmp_path / "readback.json", titles_path=tmp_path / "titles.json",
        attempts_path=tmp_path / "attempts.jsonl", outcomes_path=tmp_path / "outcomes.jsonl",
        experiments_path=CONFIG,
    )
    first = evaluator.evaluate_files(**kwargs, now=T0)
    second = evaluator.evaluate_files(**kwargs, now=T0 + DAY)
    experiments = json.loads(strategy_path.read_text(encoding="utf-8"))["experiments"]
    assert first["started"] == EXP and second["started"] is None
    assert [row["id"] for row in experiments] == [EXP]
    assert experiments[0]["source_url"].startswith("https://")
    assert experiments[0]["hypothesis"]


def test_b_price_stays_inside_buyer_range_official_bounds_and_cost_floor() -> None:
    detail = {"budget_min_jpy": 3_000, "budget_max_jpy": 10_000, "visible_text": ""}
    price = parent.commercial_offer_price(detail, planner_price_jpy=8_000, arm="B")
    assert price == 3_000
    official = dict(detail, visible_text="最低提案価格は5,000円です。提案額は9,000円まで")
    price = parent.commercial_offer_price(official, planner_price_jpy=8_000, arm="B")
    assert price == 5_000 and parent._price_within_official_bounds(price, official["visible_text"]) == price
    cheap = {"budget_min_jpy": 500, "budget_max_jpy": 3_000, "visible_text": ""}
    assert parent.commercial_offer_price(cheap, planner_price_jpy=2_400, arm="B") == parent.COST_FLOOR_JPY
    for unchanged in ({"budget_min_jpy": None, "budget_max_jpy": None},
                      {"budget_min_jpy": None, "budget_max_jpy": 10_000}):
        assert parent.commercial_offer_price(unchanged, planner_price_jpy=8_000, arm="B") == 8_000
    assert parent.commercial_offer_price(detail, planner_price_jpy=8_000, arm="A") == 8_000


direct = _load("application_direct")
gate = _load("b2_result_gate")
AB = {"id": EXP, "mode": "ab", "policy": "budget_lower_bound"}


def test_direct_apply_passes_ab_experiment_and_adopted_policy_but_not_legacy() -> None:
    ab = direct._official_open_scan_prep(
        {"active_strategy_experiment": AB, "adopted_bid_policy": "budget_lower_bound"})
    legacy = direct._official_open_scan_prep(
        {"active_strategy_experiment": {"id": "x", "mode": "isolated"}})
    assert ab["active_strategy_experiment"] == AB
    assert ab["adopted_bid_policy"] == "budget_lower_bound"
    assert legacy["active_strategy_experiment"] is None

    context = gate.build_context({
        "apply_skip_thresholds": {"min_budget_jpy": 0}, "max_apply_per_pass": 20,
        "active_strategy_experiment": AB, "adopted_bid_policy": "budget_lower_bound",
    }, Path("/nonexistent-applied.jsonl"))
    assert context["active_strategy_experiment"] == AB
    assert context["adopted_bid_policy"] == "budget_lower_bound"


def test_passprep_surfaces_ab_mode_policy_and_adopted_policy(tmp_path: Path) -> None:
    import subprocess

    gig = tmp_path / "gig"
    gig.mkdir()
    strategy = _strategy()
    strategy["adopted_bid_policy"] = "budget_lower_bound"
    (gig / "strategy.json").write_text(json.dumps(strategy), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS.parent / "passprep.py")],
        capture_output=True, text=True, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        check=True,
    )
    prep = json.loads(completed.stdout.strip().splitlines()[-1])
    assert prep["active_strategy_experiment"]["mode"] == "ab"
    assert prep["active_strategy_experiment"]["policy"] == "budget_lower_bound"
    assert prep["adopted_bid_policy"] == "budget_lower_bound"


def test_send_outcomes_feed_the_guardrail_ledger(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    decisions = [
        {"request_id": rid, "business_class": "submit_required", "price_jpy": 3_000,
         "experiment_id": EXP, "experiment_arm": arm}
        for rid, arm in (("1", "A"), ("2", "B"))
    ]
    (evidence / "application-decisions.json").write_text(
        json.dumps({"decisions": decisions}), encoding="utf-8")
    (evidence / "parent-commit.json").write_text(json.dumps({"results": [
        {"request_id": "1", "status": "confirmed"},
        {"request_id": "2", "status": "submission_failed:form_rejected"},
    ]}), encoding="utf-8")
    values = direct.summarize(evidence, 0)
    ledger = tmp_path / "experiment-attempts.jsonl"
    direct._record_experiment_attempts(ledger, "pass-1", values["report_results"])
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert [(row["request_id"], row["experiment_arm"], row["outcome"]) for row in rows] == [
        ("1", "A", "confirmed"), ("2", "B", "failed")]
