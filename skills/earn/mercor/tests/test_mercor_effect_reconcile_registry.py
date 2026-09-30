from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_mercor_effect_owners_have_occurrence_bound_reconcilers() -> None:
    registry = json.loads((ROOT / "config/loop-registry.json").read_text())
    loops = registry["loops"]
    state_roots = {
        "mercor-revenue-application": "~/.local/state/anicca/job-search/mercor/application",
        "mercor-revenue-reply": "~/.local/state/anicca/job-search/mercor/reply",
    }
    for owner in ("mercor-revenue-application", "mercor-revenue-reply"):
        reconcile = loops[owner]["effect_reconcile"]
        assert reconcile == {
            "argv": [
                "skills/_shared/marketplace-core/scripts/reconcile_pre_effect_hint.py",
                "--state-root",
                state_roots[owner],
                "--owner",
                owner,
            ],
            "occurrence_flag": "--occurrence",
            "resolve_flag": "--resolve",
            "timeout_seconds": 900,
        }

    paid = loops["mercor-revenue-paid"]["effect_reconcile"]
    assert paid == {
        "argv": [
            "skills/_shared/marketplace-core/scripts/reconcile_paid_no_effect.py",
            "--state-root",
            "~/.local/state/anicca/job-search/mercor",
            "--owner",
            "mercor-revenue-paid",
        ],
        "occurrence_flag": "--occurrence",
        "resolve_flag": "--resolve",
    }
