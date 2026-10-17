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
        "mercor-revenue-paid": "~/.local/state/anicca/job-search/mercor",
    }
    for owner, state_root in state_roots.items():
        assert loops[owner]["state_root"] == state_root
        reconcile = loops[owner]["effect_reconcile"]
        expected = {
            "argv": [
                "skills/earn/mercor/scripts/reconcile_fence_readback.py",
                "--state-root",
                state_root,
                "--owner",
                owner,
            ],
            "occurrence_flag": "--occurrence",
            "resolve_flag": "--resolve",
        }
        if owner != "mercor-revenue-paid":
            # Two bounded Gmail searches (30 s each) plus journal parsing.
            expected["timeout_seconds"] = 120
        assert reconcile == expected
