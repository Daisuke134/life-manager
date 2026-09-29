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
        lambda *, owner_id, intent_root: ("occ-1", "123")
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
        "--request-id",
        "123",
        "--intent-root",
        str(tmp_path),
        "--max-pages",
        "1000",
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
