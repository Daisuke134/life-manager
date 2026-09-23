from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[4]
OWNER = ROOT / "skills/earn/lancers/scripts/paid-owner"


def test_lancers_paid_owner_reconciles_after_kernel_and_report(tmp_path: Path) -> None:
    fake_root = tmp_path / "repo"
    fake_owner = fake_root / "skills/earn/lancers/scripts/paid-owner"
    fake_owner.parent.mkdir(parents=True)
    shutil.copy2(OWNER, fake_owner)
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "if args and args[0].endswith('reconcile_paid_no_effect.py'):\n"
        "    pathlib.Path(os.environ['RECONCILE_ARGS']).write_text(' '.join(args[1:]))\n"
        "elif args and args[0].endswith('paid_kernel.py'):\n"
        "    output = pathlib.Path(args[args.index('--output') + 1])\n"
        "    output.parent.mkdir(parents=True, exist_ok=True)\n"
        "    output.write_text('{\\\"status\\\":\\\"ok\\\",\\\"effect\\\":0}')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o700)
    state_root = tmp_path / "state"
    state_root.mkdir()
    (state_root / "contracts.json").write_text(
        '{"source_complete":true}', encoding="utf-8"
    )
    args_file = tmp_path / "reconcile.args"
    env = {
        **os.environ,
        "LIFE_MANAGER_PYTHON": str(fake_python),
        "LIFE_MANAGER_STATE_ROOT": str(state_root),
        "LIFE_MANAGER_OCCURRENCE_ID": "lancers-revenue-paid:run-1",
        "RECONCILE_ARGS": str(args_file),
    }

    result = subprocess.run([str(fake_owner)], env=env, text=True,
                            capture_output=True, check=False)

    assert result.returncode == 0
    args = args_file.read_text(encoding="utf-8")
    assert "--resolve" in args
    assert "--owner lancers-revenue-paid" in args
    assert "--occurrence lancers-revenue-paid:run-1" in args
