import json
from pathlib import Path


def test_capafy_marketing_declares_finite_host_admission_contract():
    root = Path(__file__).resolve().parents[4]
    entry = json.loads((root / "config/loop-registry.json").read_text())["loops"][
        "capafy-ig-marketing-daily"
    ]

    assert entry["resource_class"] == "agent"
    # Capafy's only marketing channel; as borrow it never got a slot once revenue
    # owners filled the host (no Reel since 2026-08-24).
    assert entry["admission_class"] == "revenue"
    assert entry["priority"] == "revenue"


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


def test_capafy_effectful_recurring_owners_declare_effect_and_coalescing_contract():
    root = Path(__file__).resolve().parents[4]
    loops = json.loads((root / "config/loop-registry.json").read_text())["loops"]
    expected = {
        "capafy-loop-daily": ("publish", "deterministic", "revenue", "revenue"),
        # Revenue readers / the IG account owner never got a slot as borrow once revenue
        # owners filled the host (2026-09-27, SSOT P-5 / 7-6e).
        "capafy-outcome-monitor": ("message", "deterministic", "revenue", "revenue"),
        "capafy-ig-account-manager": ("account_mutation", "agent", "revenue", "revenue"),
        "capafy-ig-marketing-daily": ("publish", "agent", "revenue", "revenue"),
    }

    for loop_id, contract in expected.items():
        entry = loops[loop_id]
        assert (
            entry["effect_class"],
            entry["resource_class"],
            entry["admission_class"],
            entry["priority"],
        ) == contract, loop_id
        assert entry["coalesce_queued_wakes"] is True, loop_id
        assert entry["coalesce_reserved_wakes"] is True, loop_id
