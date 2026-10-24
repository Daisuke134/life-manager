import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capafy_improvement_ledger as M  # noqa: E402


def reconcile(imp, views, trials, paid, by_agent=None):
    src = lambda n: [{"exposure_count": n, "source_name": "search"}]
    return {
        "observed_at": "2026-10-23T04:14:11Z",
        "traffic_sources": {
            "impressions": {"account": {"last_7d": {"by_source": src(imp)}}, "by_agent": {}},
            "last_7d": {"totals": {"views": views, "trial_orders": trials, "paid_orders": paid}},
            "by_agent": by_agent or {},
        },
    }


def test_funnel_computes_stage_rates() -> None:
    f = M.funnel(reconcile(10000, 1000, 10, 2))
    assert f["impressions"] == 10000 and f["views"] == 1000
    assert f["view_rate"] == 0.1 and f["trial_rate"] == 0.01 and f["paid_rate"] == 0.002


def test_weakest_stage_is_the_lowest_conversion_after_a_floor_of_volume() -> None:
    # 0.4% of views become paid, far below the 10% impression->view rate.
    f = M.funnel(reconcile(10000, 1000, 10, 4))
    assert M.weakest_stage(f) == "views_to_paid"


def test_weakest_stage_is_views_when_exposure_barely_converts() -> None:
    f = M.funnel(reconcile(100000, 300, 3, 3))
    assert M.weakest_stage(f) == "impressions_to_views"


def test_zero_volume_never_divides_and_reports_no_signal() -> None:
    f = M.funnel(reconcile(0, 0, 0, 0))
    assert f["view_rate"] is None and M.weakest_stage(f) is None


def test_previous_change_is_kept_only_when_its_metric_improved() -> None:
    prev = {"metric": "view_rate", "baseline": 0.10, "action": "x"}
    assert M.evaluate_previous(prev, {"view_rate": 0.13})["verdict"] == "kept"
    assert M.evaluate_previous(prev, {"view_rate": 0.09})["verdict"] == "revert_candidate"
    assert M.evaluate_previous(prev, {"view_rate": None})["verdict"] == "inconclusive"
    assert M.evaluate_previous(None, {"view_rate": 0.1}) is None


def _agent(rows):
    return {"last_7d": {"by_source": [
        {"source_type": t, "source_name": n, "views": v, "trial_orders": tr, "paid_orders": p}
        for t, n, v, tr, p in rows]}}


def test_channels_split_internal_marketplace_from_outside_distribution() -> None:
    r = reconcile(10000, 1000, 10, 2, by_agent={
        "a": _agent([("internal", "search", 600, 1, 0), ("ct", "hooklab_x", 30, 0, 0)]),
        "b": _agent([("internal", "category", 100, 0, 0), ("direct", "direct", 200, 0, 2),
                     ("referrer", "google", 20, 0, 0)]),
    })
    r["traffic_sources"]["by_agent"] = r["traffic_sources"]["by_agent"]
    c = M.channels(r)
    assert c["internal"] == {"views": 700, "trials": 1, "paid": 0}
    assert c["outside"] == {"views": 250, "trials": 0, "paid": 2}
    assert c["outside_view_share"] == 250 / 950


def test_lever_targets_the_channel_that_converts_least_per_view() -> None:
    low_outside = {"internal": {"views": 900, "trials": 2, "paid": 1}, "outside": {"views": 50, "trials": 0, "paid": 0},
                   "outside_view_share": 50 / 950}
    assert M.lever(low_outside) == "outside_reach"
    healthy_outside = {"internal": {"views": 500, "trials": 0, "paid": 0}, "outside": {"views": 500, "trials": 2, "paid": 1},
                       "outside_view_share": 0.5}
    assert M.lever(healthy_outside) == "internal_conversion"


def test_channels_use_the_account_level_split_not_the_rotating_agent_subset() -> None:
    # reconcile queries only ~60 of 79 agents per hour (utc_hour_round_robin), so a by_agent sum
    # swings with whichever agents were omitted (2026-10-24: internal read 294 vs the true ~1,239).
    r = reconcile(10000, 1000, 10, 2, by_agent={"a": _agent([("internal", "search", 5, 0, 0)])})
    r["traffic_sources"]["last_7d"]["by_source"] = [
        {"source_type": "internal", "source_name": "search", "views": 700, "trial_orders": 1, "paid_orders": 0},
        {"source_type": "internal", "source_name": "ai_overview", "views": 100, "trial_orders": 0, "paid_orders": 0},
        {"source_type": "direct", "source_name": "direct", "views": 200, "trial_orders": 0, "paid_orders": 1},
    ]
    c = M.channels(r)
    assert c["internal"] == {"views": 800, "trials": 1, "paid": 0}
    assert c["outside"] == {"views": 200, "trials": 0, "paid": 1}
