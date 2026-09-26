from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[4]
PAID_OWNER = ROOT / "skills/earn/lancers/scripts/paid-owner"
NEGOTIATE_OWNER = ROOT / "skills/earn/lancers/scripts/negotiate-owner"


def _fake_python_writing(tmp_path: Path, target_flag: str, payload: str) -> Path:
    """A fake managed-Python that writes ``payload`` to the script's --output path.

    Mirrors the fake-python fixture in test_paid_owner_reconcile.py: matches on
    which kernel script is invoked (identified by the flag right before it in
    argv is irrelevant here -- we match the script path itself) and writes the
    JSON a real kernel would have written, then exits 1 so the owner script's
    own KERNEL_RC-inspection logic is exercised end to end.
    """
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        f"if any(a.endswith({target_flag!r}) for a in args):\n"
        "    output = pathlib.Path(args[args.index('--output') + 1])\n"
        "    output.parent.mkdir(parents=True, exist_ok=True)\n"
        f"    output.write_text({payload!r})\n"
        "    raise SystemExit(1)\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o700)
    return fake_python


def test_paid_owner_reports_browser_attach_busy_as_exit_75(tmp_path: Path) -> None:
    fake_python = _fake_python_writing(
        tmp_path, "paid_kernel.py",
        '{"status":"failed","effect":0,"failed":1,"failed_step":"provider_inventory",'
        '"error_detail":"lancers_paid_inventory_browser_attach_busy"}',
    )
    state_root = tmp_path / "state"
    state_root.mkdir()
    env = {**os.environ, "LIFE_MANAGER_PYTHON": str(fake_python),
           "LIFE_MANAGER_STATE_ROOT": str(state_root)}

    result = subprocess.run([str(PAID_OWNER)], env=env, text=True,
                            capture_output=True, check=False)

    assert result.returncode == 75


def test_paid_owner_keeps_exit_1_for_an_unrelated_failure(tmp_path: Path) -> None:
    fake_python = _fake_python_writing(
        tmp_path, "paid_kernel.py",
        '{"status":"failed","effect":0,"failed":1,"failed_step":"provider_inventory",'
        '"error_detail":"lancers_paid_inventory_account_unavailable"}',
    )
    state_root = tmp_path / "state"
    state_root.mkdir()
    env = {**os.environ, "LIFE_MANAGER_PYTHON": str(fake_python),
           "LIFE_MANAGER_STATE_ROOT": str(state_root)}

    result = subprocess.run([str(PAID_OWNER)], env=env, text=True,
                            capture_output=True, check=False)

    assert result.returncode == 1


def test_negotiate_owner_reports_browser_attach_busy_as_exit_75(tmp_path: Path) -> None:
    fake_python = _fake_python_writing(
        tmp_path, "reply_kernel.py",
        '{"status":"blocked","effect":0,"failed":0,"blocker":"browser_attach_busy",'
        '"error_detail":"browser_attach_lock_timeout"}',
    )
    # The fake python above always exits 1 for a matched script; reply_kernel's
    # real classify_observation_error path exits 0, so patch the fake to match.
    fake_python.write_text(
        fake_python.read_text(encoding="utf-8").replace(
            "raise SystemExit(1)\n", "raise SystemExit(0)\n", 1
        ),
        encoding="utf-8",
    )
    state_root = tmp_path / "state"
    state_root.mkdir()
    env = {**os.environ, "LIFE_MANAGER_PYTHON": str(fake_python),
           "LIFE_MANAGER_STATE_ROOT": str(state_root)}

    result = subprocess.run([str(NEGOTIATE_OWNER)], env=env, text=True,
                            capture_output=True, check=False)

    assert result.returncode == 75


def test_negotiate_owner_keeps_exit_0_for_a_real_success(tmp_path: Path) -> None:
    fake_python = _fake_python_writing(
        tmp_path, "reply_kernel.py",
        '{"status":"ok","effect":0,"failed":0,"items":[]}',
    )
    fake_python.write_text(
        fake_python.read_text(encoding="utf-8").replace(
            "raise SystemExit(1)\n", "raise SystemExit(0)\n", 1
        ),
        encoding="utf-8",
    )
    state_root = tmp_path / "state"
    state_root.mkdir()
    env = {**os.environ, "LIFE_MANAGER_PYTHON": str(fake_python),
           "LIFE_MANAGER_STATE_ROOT": str(state_root)}

    result = subprocess.run([str(NEGOTIATE_OWNER)], env=env, text=True,
                            capture_output=True, check=False)

    assert result.returncode == 0
