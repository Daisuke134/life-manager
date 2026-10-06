import importlib.util
import hashlib
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


def shared_marker_path(state_root: Path, occurrence: str) -> Path:
    digest = hashlib.sha256(occurrence.encode()).hexdigest()
    return state_root / "shared-paid" / "runs" / f"{digest}.json"


def write_paid_marker(path: Path, occurrence: str, *, status: str = "completed",
                      effect: int = 0, version: int = 1) -> None:
    write_json(path, {
        "version": version,
        "occurrence_id": occurrence,
        "status": status,
        "effect": effect,
    })


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
    assert proof["evidence_ref"].startswith("lm-paid-run://")
    assert proof["evidence_ref"] in proof["evidence_refs"]


def test_pre_effect_marker_without_effect_field_proves_no_dispatch(tmp_path):
    module = load()
    occurrence = "crowdworks-revenue-paid:pre-effect-marker"
    state_root = seed(tmp_path, occurrence=occurrence)
    marker = module.run_marker_path(state_root, occurrence)
    write_json(marker, {
        "version": 1,
        "occurrence_id": occurrence,
        "status": "pre_effect",
    })

    proof = module.find_paid_no_effect_proof(state_root, "crowdworks-revenue-paid", occurrence)

    assert proof is not None
    assert proof["verified"] is True
    assert proof["proof_type"] == "pre_effect"


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


def test_resolve_retries_released_state_after_claimed_state(tmp_path, monkeypatch):
    module = load()
    occurrence = "crowdworks-revenue-paid:released-run"
    state_root = seed(tmp_path, occurrence=occurrence)
    states = []

    def resolve(_owner, _occurrence, *, pre_effect_readback, expected_state):
        states.append(expected_state)
        return expected_state == "released"

    monkeypatch.setattr(module, "resolve_pre_effect_occurrence", resolve)

    result = module.reconcile(
        state_root=state_root,
        owner="crowdworks-revenue-paid",
        occurrence=occurrence,
        resolve=True,
    )

    assert result["resolved"] is True
    assert states == ["claimed", "released"]


def test_exact_paid_zero_effect_run_supports_shared_paid_state_layout(tmp_path):
    module = load()
    owner = "mercor-revenue-paid"
    occurrence = f"{owner}:shared-run"
    state_root = tmp_path / "mercor"
    marker = state_root / "shared-paid" / "runs" / (
        hashlib.sha256(occurrence.encode()).hexdigest() + ".json"
    )
    write_json(marker, {
        "version": 1,
        "occurrence_id": occurrence,
        "status": "completed",
        "effect": 0,
    })

    proof = module.find_paid_no_effect_proof(state_root, owner, occurrence)

    assert proof["verified"] is True
    assert proof["occurrence_id"] == occurrence


def test_invalid_or_effectful_canonical_marker_blocks_shared_fallback(tmp_path):
    module = load()
    owner = "mercor-revenue-paid"
    canonical_markers = [
        ("effect_started", 0, 1),
        ("completed", 1, 1),
        ("completed", 0, 2),
    ]

    for index, (status, effect, version) in enumerate(canonical_markers):
        occurrence = f"{owner}:authoritative-{index}"
        state_root = tmp_path / str(index)
        write_paid_marker(shared_marker_path(state_root, occurrence), occurrence)
        write_paid_marker(
            module.run_marker_path(state_root, occurrence), occurrence,
            status=status, effect=effect, version=version,
        )

        assert module.find_paid_no_effect_proof(
            state_root, owner, occurrence) is None


def test_canonical_symlink_does_not_prove_no_effect(tmp_path):
    module = load()
    owner = "mercor-revenue-paid"
    occurrence = f"{owner}:canonical-symlink"
    state_root = tmp_path / "mercor"
    shared_marker = shared_marker_path(state_root, occurrence)
    write_paid_marker(shared_marker, occurrence)
    canonical_marker = module.run_marker_path(state_root, occurrence)
    canonical_marker.parent.mkdir(parents=True, exist_ok=True)
    canonical_marker.symlink_to(tmp_path / "missing-target.json")

    assert module.find_paid_no_effect_proof(
        state_root, owner, occurrence) is None


def test_shared_paid_fallback_is_mercor_only(tmp_path):
    module = load()
    occurrence = "crowdworks-revenue-paid:shared-only"
    state_root = tmp_path / "crowdworks"
    shared_marker = shared_marker_path(state_root, occurrence)
    write_paid_marker(shared_marker, occurrence)

    assert module.find_paid_no_effect_proof(
        state_root, "crowdworks-revenue-paid", occurrence) is None


def test_shared_paid_symlink_does_not_prove_no_effect(tmp_path):
    module = load()
    owner = "mercor-revenue-paid"
    occurrence = f"{owner}:shared-symlink"
    state_root = tmp_path / "mercor"
    target = tmp_path / "valid-marker.json"
    write_paid_marker(target, occurrence)
    shared_marker = shared_marker_path(state_root, occurrence)
    shared_marker.parent.mkdir(parents=True, exist_ok=True)
    shared_marker.symlink_to(target)

    assert module.find_paid_no_effect_proof(
        state_root, owner, occurrence) is None


def test_cli_reports_missing_occurrence_proof_as_structured_safety_stop(tmp_path,
                                                                        capsys):
    module = load()
    occurrence = "crowdworks-revenue-paid:missing-proof"

    result = module.main([
        "--state-root", str(tmp_path / "crowdworks"),
        "--owner", "crowdworks-revenue-paid",
        "--occurrence", occurrence,
    ])

    assert result == 75
    output = capsys.readouterr().out
    event = json.loads(output)
    assert event["error_class"] == "exact_paid_zero_effect_proof_unavailable"
    assert event["effect_status"] == "unknown"
    assert event["retryable"] is False
    assert event["next_action"] == "obtain_occurrence_bound_readback"
    assert event["resolved"] is False
