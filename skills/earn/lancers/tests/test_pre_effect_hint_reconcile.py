from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "skills/_shared/marketplace-core/scripts/reconcile_pre_effect_hint.py"


def _load():
    spec = importlib.util.spec_from_file_location("reconcile_pre_effect_hint_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_marker_is_bound_to_owner_and_occurrence(tmp_path: Path) -> None:
    module = _load()
    owner = "lancers-revenue-application"
    occurrence = f"{owner}:run-1"
    marker = tmp_path / "loop-tmp" / owner / "run-1" / "entrypoint-result.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"status":"pre_effect_failure","effect":0}\n', encoding="utf-8")
    marker.chmod(0o600)

    proof = module.find_pre_effect_proof(tmp_path, owner, occurrence)
    assert proof == {
        "owner_id": owner,
        "occurrence_id": occurrence,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"lm-pre-effect://{owner}/run-1/entrypoint-result.json",
    }
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600
    assert module.find_pre_effect_proof(tmp_path, owner, f"{owner}:run-2") is None


def test_marker_with_effect_or_extra_shape_is_not_a_no_effect_proof(tmp_path: Path) -> None:
    module = _load()
    owner = "lancers-revenue-storefront"
    occurrence = f"{owner}:run-1"
    marker = tmp_path / "loop-tmp" / owner / "run-1" / "entrypoint-result.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        json.dumps({"status": "pre_effect_failure", "effect": 1}), encoding="utf-8"
    )
    marker.chmod(0o600)
    assert module.find_pre_effect_proof(tmp_path, owner, occurrence) is None


def test_reconcile_uses_resolver_only_after_exact_marker(tmp_path: Path) -> None:
    module = _load()
    owner = "lancers-revenue-negotiate"
    occurrence = f"{owner}:run-1"
    marker = tmp_path / "loop-tmp" / owner / "run-1" / "entrypoint-result.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"status":"pre_effect_failure","effect":0}', encoding="utf-8")
    marker.chmod(0o600)
    calls = []

    def resolver(owner_id, occurrence_id, *, pre_effect_readback, expected_state):
        calls.append((owner_id, occurrence_id, expected_state, pre_effect_readback()))
        return True

    result = module.reconcile(
        state_root=tmp_path,
        owner=owner,
        occurrence=occurrence,
        resolve=True,
        resolver=resolver,
    )
    assert result["resolved"] is True
    assert calls == [(owner, occurrence, "claimed", module.find_pre_effect_proof(tmp_path, owner, occurrence))]
