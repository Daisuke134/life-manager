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
