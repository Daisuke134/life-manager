from __future__ import annotations

import json
import subprocess
import sys
import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[4]
REGISTRY = ROOT / "config" / "loop-registry.json"
SCRIPT = ROOT / "skills" / "earn" / "gig" / "scripts" / "coconala_application_effect_reconcile.py"


def _load_wrapper():
    spec = importlib.util.spec_from_file_location("coconala_application_effect_reconcile_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_coconala_effect_fence_adapters_are_registered() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    loops = registry["loops"]

    apply_reconcile = loops["hf-gig-apply-direct"]["effect_reconcile"]
    assert apply_reconcile == {
        "argv": [
            "skills/earn/gig/scripts/coconala_application_effect_reconcile.py",
        ],
        "occurrence_flag": None,
        "resolve_flag": None,
        "timeout_seconds": 900,
    }

    storefront_reconcile = loops["hf-gig-storefront-direct"]["effect_reconcile"]
    assert storefront_reconcile == {
        "argv": [
            "skills/earn/gig/scripts/storefront_pre_effect_reconcile.py",
        ],
        "occurrence_flag": "--occurrence",
        "resolve_flag": None,
        "timeout_seconds": 900,
    }


def test_application_reconcile_leases_registered_identity_only_after_exact_target(
    tmp_path, monkeypatch, capsys
) -> None:
    wrapper = _load_wrapper()
    monkeypatch.setattr(
        wrapper.reconciler,
        "discover_single_target",
        lambda *, owner_id, intent_root: ("occ-1", "run-1", ["123", "456"])
    )
    calls = []

    class Completed:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return Completed()

    monkeypatch.setattr(wrapper.subprocess, "run", fake_run)
    assert wrapper.main(["--intent-root", str(tmp_path)]) == 0

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [
        "bash",
        str(ROOT / "skills" / "browser" / "with-browser.sh"),
        "coconala:kosuke",
        "--",
        sys.executable,
        str(ROOT / "skills" / "earn" / "gig" / "scripts" / "application_occurrence_reconcile.py"),
        "--owner-id",
        "hf-gig-apply-direct",
        "--occurrence-id",
        "occ-1",
        "--runtime-run-id",
        "run-1",
        "--intent-root",
        str(tmp_path),
        "--max-pages",
        "1000",
        "--request-id",
        "123",
        "--request-id",
        "456",
    ]
    assert kwargs["cwd"] == ROOT
    assert kwargs["env"]["BROWSER_WAIT_SECONDS"] == "0"
    assert kwargs["env"]["AI_ENSURE_PROVISION_BROWSER"] == "/dev/null"
    assert capsys.readouterr().out == ""


def test_application_reconcile_does_not_touch_browser_without_exact_target(
    tmp_path, monkeypatch, capsys
) -> None:
    wrapper = _load_wrapper()
    monkeypatch.setattr(
        wrapper.reconciler,
        "discover_single_target",
        lambda *, owner_id, intent_root: None,
    )

    def fail_run(*args, **kwargs):
        raise AssertionError("browser must not be invoked without an exact target")

    monkeypatch.setattr(wrapper.subprocess, "run", fail_run)
    assert wrapper.main(["--intent-root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "nothing_to_reconcile"


def _intent(root: Path, request_id: str, state: str, phase: str | None) -> None:
    value = {"request_id": request_id, "state": state, "version": 2}
    if phase is not None:
        value["effect_phase"] = phase
    (root / f"{request_id}.json").write_text(json.dumps(value), encoding="utf-8")


def test_settled_write_ahead_store_closes_unbound_fences(tmp_path, monkeypatch, capsys) -> None:
    wrapper = _load_wrapper()
    monkeypatch.setattr(wrapper.reconciler, "discover_single_target",
                        lambda *, owner_id, intent_root: None)
    _intent(tmp_path, "1", "confirmed", "irreversible_attempt_started")
    _intent(tmp_path, "2", "retired_absent", "irreversible_attempt_started")
    _intent(tmp_path, "3", "prepared", None)
    monkeypatch.setattr(wrapper, "_fenced_occurrences",
                        lambda owner_id: ["hf-gig-apply-direct:old-1"])
    proofs = []

    def resolver(owner_id, occurrence_id, *, settled_proof):
        proofs.append(settled_proof())
        return True

    monkeypatch.setattr(wrapper, "_resolve_settled", resolver)
    assert wrapper.main(["--intent-root", str(tmp_path)]) == 0

    assert proofs[0]["unresolved_irreversible"] == 0 and proofs[0]["scanned_intents"] == 3
    closure = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert closure["owner_id"] == "hf-gig-apply-direct"
    assert closure["occurrence_id"] == "hf-gig-apply-direct:old-1"
    assert closure["verified"] is True and closure["evidence_ref"].startswith("gig-intents://sha256/")


def test_unresolved_or_unreadable_intent_keeps_every_fence(tmp_path, monkeypatch, capsys) -> None:
    wrapper = _load_wrapper()
    monkeypatch.setattr(wrapper.reconciler, "discover_single_target",
                        lambda *, owner_id, intent_root: None)
    _intent(tmp_path, "1", "confirmed", "irreversible_attempt_started")
    _intent(tmp_path, "2", "prepared", "irreversible_attempt_started")
    (tmp_path / "3.json").write_text("{broken", encoding="utf-8")

    def never(*_args, **_kwargs):
        raise AssertionError("unsettled store must not read or release fences")

    monkeypatch.setattr(wrapper, "_fenced_occurrences", never)
    monkeypatch.setattr(wrapper, "_resolve_settled", never)
    assert wrapper.main(["--intent-root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "nothing_to_reconcile"
    assert result["unresolved_irreversible"] == 2
