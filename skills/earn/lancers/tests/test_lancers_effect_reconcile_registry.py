from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_lancers_effect_fences_use_exact_pre_effect_adapter() -> None:
    registry = json.loads((ROOT / "config/loop-registry.json").read_text())
    loops = registry["loops"]
    expected_owners = {
        "lancers-revenue-application",
        "lancers-revenue-negotiate",
        "lancers-revenue-storefront",
    }
    for owner in expected_owners:
        reconcile = loops[owner]["effect_reconcile"]
        assert reconcile["argv"] == [
            "skills/_shared/marketplace-core/scripts/reconcile_pre_effect_hint.py",
            "--state-root",
            "~/.local/state/anicca/lancers",
            "--owner",
            owner,
        ]
        assert reconcile["occurrence_flag"] == "--occurrence"
        assert reconcile["resolve_flag"] == "--resolve"
        assert reconcile["timeout_seconds"] == 900

