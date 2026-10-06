"""Pre-effect CrowdWorks Paid observation failures stay retryable and fenced."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
OWNER = ROOT / "skills/earn/crowdworks/scripts/paid-owner"


def _fake_tree(tmp_path: Path, result: dict, kernel_rc: int = 1):
    fake_root = tmp_path / "repo"
    fake_owner = fake_root / "skills/earn/crowdworks/scripts/paid-owner"
    fake_owner.parent.mkdir(parents=True)
    shutil.copy2(OWNER, fake_owner)

    lock = fake_root / "skills/browser/scripts/run_with_file_lock.py"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        "import os, sys\n"
        "index = sys.argv.index('--') + 1\n"
        "os.execv(sys.argv[index], sys.argv[index:])\n",
        encoding="utf-8",
    )

    kernel = fake_root / "skills/_shared/marketplace-core/scripts/paid_kernel.py"
    kernel.parent.mkdir(parents=True)
    kernel.write_text(
        "import json, pathlib, sys\n"
        "output = pathlib.Path(sys.argv[sys.argv.index('--output') + 1])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        f"output.write_text({json.dumps(result)!r})\n"
        f"raise SystemExit({kernel_rc})\n",
        encoding="utf-8",
    )

    reconciler = fake_root / "skills/_shared/marketplace-core/scripts/reconcile_paid_no_effect.py"
    reconciler.write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path(os.environ['RECONCILE_ARGS']).write_text(' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    return fake_owner, fake_root


def _run(fake_owner: Path, state_root: Path, args_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(fake_owner)],
        env={
            **os.environ,
            "LIFE_MANAGER_PYTHON": sys.executable,
            "LIFE_MANAGER_LOCK_PYTHON": sys.executable,
            "LIFE_MANAGER_STATE_ROOT": str(state_root),
            "LIFE_MANAGER_OCCURRENCE_ID": "crowdworks-revenue-paid:run-1",
            "RECONCILE_ARGS": str(args_file),
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_inventory_observation_failure_is_retryable_without_provider_effect(tmp_path: Path):
    fake_owner, _ = _fake_tree(
        tmp_path,
        {
            "status": "failed",
            "effect": 0,
            "failed": 1,
            "pending": 0,
            "failed_step": "provider_inventory",
            "error_detail": "crowdworks_paid_browser_unavailable",
            "items": [],
        },
    )
    args_file = tmp_path / "reconcile.args"
    result = _run(fake_owner, tmp_path / "state", args_file)

    assert result.returncode == 75
    assert "--owner crowdworks-revenue-paid" in args_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(("error_detail", "pre_effect", "expected_returncode"), [
    ("crowdworks_paid_handoff_unavailable_price_minor", True, 75),
    ("crowdworks_paid_handoff_unavailable_contract_terms_sha256", True, 75),
    ("crowdworks_paid_handoff_unavailable_price_minor", False, 1),
    ("crowdworks_paid_handoff_unavailable_contract_terms_sha256", False, 1),
])
def test_field_specific_handoff_failures_are_retryable_only_with_pre_effect_proof(
        tmp_path: Path, error_detail: str, pre_effect: bool, expected_returncode: int):
    fake_owner, _ = _fake_tree(
        tmp_path,
        {
            "status": "ok",
            "effect": 0,
            "failed": 1,
            "pending": 0,
            "items": [{
                "work_id": "63942104",
                "status": "failed",
                "effect": 0,
                "failed": 1,
                "pre_effect": pre_effect,
                "error_detail": error_detail,
            }],
        },
    )
    args_file = tmp_path / "reconcile.args"
    result = _run(fake_owner, tmp_path / "state", args_file)

    assert result.returncode == expected_returncode
    if pre_effect:
        assert "--owner crowdworks-revenue-paid" in args_file.read_text(encoding="utf-8")


def test_item_failure_after_mutation_is_not_downgraded_to_retryable(tmp_path: Path):
    fake_owner, _ = _fake_tree(
        tmp_path,
        {
            "status": "ok",
            "effect": 0,
            "failed": 1,
            "pending": 0,
            "items": [{
                "work_id": "63570481",
                "status": "failed",
                "effect": 0,
                "failed": 1,
                "pre_effect": False,
                "error_detail": "crowdworks_paid_contract_timeout",
            }],
        },
    )
    result = _run(fake_owner, tmp_path / "state", tmp_path / "reconcile.args")

    assert result.returncode == 1


def test_item_observation_failure_uses_kernel_pre_effect_proof(tmp_path: Path):
    fake_owner, _ = _fake_tree(
        tmp_path,
        {
            "status": "ok",
            "effect": 0,
            "failed": 1,
            "pending": 0,
            "items": [{
                "work_id": "63570481",
                "status": "failed",
                "effect": 0,
                "failed": 1,
                "pre_effect": True,
                "error_detail": "crowdworks_paid_contract_timeout",
            }],
        },
    )
    result = _run(fake_owner, tmp_path / "state", tmp_path / "reconcile.args")

    assert result.returncode == 75
