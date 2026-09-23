import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/_shared/marketplace-core/scripts/reconcile_paid_no_effect.py"


def load():
    spec = importlib.util.spec_from_file_location(
        "crowdworks_reconcile_paid_no_effect_test", PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def seed(tmp_path: Path, *, owner: str = "crowdworks-revenue-paid",
         occurrence: str = "crowdworks-revenue-paid:run-1",
         marker_status: str = "completed", marker_effect: int = 0,
         summary_occurrence: str | None = None, summary_effect: int = 0,
         item_effects: list[int] | None = None) -> Path:
    module = load()
    state_root = tmp_path / "crowdworks"
    marker = module.run_marker_path(state_root, occurrence)
    write_json(marker, {
        "version": 1,
        "occurrence_id": occurrence,
        "status": marker_status,
        "effect": marker_effect,
    })
    effects = item_effects if item_effects is not None else [0, 0]
    write_json(state_root / "paid-latest.json", {
        "status": "ok",
        "occurrence_id": summary_occurrence or occurrence,
        "effect": summary_effect,
        "failed": 0,
        "items": [{"work_id": str(i), "effect": effect, "failed": 0}
                  for i, effect in enumerate(effects)],
    })
    return state_root


def test_exact_paid_zero_effect_run_proves_pre_effect(tmp_path):
    module = load()
    occurrence = "crowdworks-revenue-paid:run-1"
    state_root = seed(tmp_path, occurrence=occurrence)

    proof = module.find_paid_no_effect_proof(state_root, "crowdworks-revenue-paid", occurrence)

    assert proof["verified"] is True
    assert proof["proof_type"] == "pre_effect"
    assert proof["occurrence_id"] == occurrence


def test_paid_no_effect_proof_rejects_mismatches_and_effectful_items(tmp_path):
    module = load()
    occurrence = "crowdworks-revenue-paid:run-2"

    state_root = seed(tmp_path, occurrence=occurrence,
                      summary_occurrence="crowdworks-revenue-paid:other")
    # The exact kernel marker is the authoritative no-dispatch proof; the
    # latest summary may already belong to a later wake.
    assert module.find_paid_no_effect_proof(
        state_root, "crowdworks-revenue-paid", occurrence)["verified"] is True

    state_root = seed(tmp_path, occurrence=occurrence, marker_effect=1)
    assert module.find_paid_no_effect_proof(
        state_root, "crowdworks-revenue-paid", occurrence) is None

    state_root = seed(tmp_path, occurrence=occurrence, marker_status="effect_started")
    assert module.find_paid_no_effect_proof(
        state_root, "crowdworks-revenue-paid", occurrence) is None


def test_reconcile_is_read_only_without_resolve(tmp_path, monkeypatch):
    module = load()
    occurrence = "crowdworks-revenue-paid:run-3"
    state_root = seed(tmp_path, occurrence=occurrence)
    monkeypatch.setattr(
        module,
        "resolve_pre_effect_occurrence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("resolve must be opt-in")
        ),
    )

    result = module.reconcile(state_root=state_root,
                              owner="crowdworks-revenue-paid",
                              occurrence=occurrence)

    assert result["resolved"] is False
    assert result["proof_type"] == "pre_effect"
