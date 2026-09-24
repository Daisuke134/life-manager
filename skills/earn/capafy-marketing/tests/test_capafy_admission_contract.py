import json
from pathlib import Path


def test_capafy_marketing_declares_finite_host_admission_contract():
    root = Path(__file__).resolve().parents[4]
    entry = json.loads((root / "config/loop-registry.json").read_text())["loops"][
        "capafy-ig-marketing-daily"
    ]

    assert entry["resource_class"] == "agent"
    assert entry["admission_class"] == "borrow"
    assert entry["priority"] == "support"


def test_capafy_goal_monitors_declare_rebindable_host_admission_contract():
    root = Path(__file__).resolve().parents[4]
    loops = json.loads((root / "config/loop-registry.json").read_text())["loops"]

    for loop_id in (
        "capafy-goal-monitor",
        "capafy-goal-monitor-daily-close",
        "capafy-goal-monitor-hourly",
    ):
        entry = loops[loop_id]
        assert entry["resource_class"] == "deterministic", loop_id
        assert entry["admission_class"] == "borrow", loop_id
        assert entry["priority"] == "support", loop_id
        assert entry["coalesce_queued_wakes"] is True, loop_id
        assert entry["coalesce_reserved_wakes"] is True, loop_id
