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



def test_lancers_storefront_fence_uses_official_roster_readback() -> None:
    # A storefront wake that reached the browser never writes the pre-effect marker.
    reconcile = json.loads((ROOT / "config/loop-registry.json").read_text())[
        "loops"]["lancers-revenue-storefront"]["effect_reconcile"]
    assert reconcile == {
        "argv": ["skills/earn/lancers/scripts/storefront_effect_reconcile.py"],
        "occurrence_flag": "--occurrence", "resolve_flag": "--resolve", "timeout_seconds": 900,
    }
