import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[4]
OWNER = ROOT / "skills/earn/crowdworks/scripts/paid-owner"


def test_paid_owner_does_not_recreate_hint_from_stale_inventory_output(tmp_path: Path) -> None:
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
        "output.write_text(json.dumps({'status':'failed','effect':0,'failed':1,'failed_step':'provider_inventory'}))\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    state_root = tmp_path / "state"
    hint = tmp_path / "entrypoint-result.json"
    environment = {
        **os.environ,
        "LIFE_MANAGER_PYTHON": sys.executable,
        "LIFE_MANAGER_LOCK_PYTHON": sys.executable,
        "LIFE_MANAGER_STATE_ROOT": str(state_root),
        "LIFE_MANAGER_RESULT_HINT_PATH": str(hint),
    }

    result = subprocess.run([str(fake_owner)], env=environment, text=True,
                            capture_output=True, check=False)

    assert result.returncode == 1
    assert not hint.exists()


def test_paid_owner_reconciles_exact_zero_effect_occurrence_after_kernel(tmp_path: Path) -> None:
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
        "output.write_text(json.dumps({'status':'ok','effect':0,'failed':0,'items':[]}))\n",
        encoding="utf-8",
    )
    reconciler = fake_root / "skills/earn/crowdworks/scripts/reconcile_paid_no_effect.py"
    reconciler.write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path(os.environ['RECONCILE_ARGS']).write_text(' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    state_root = tmp_path / "state"
    args_file = tmp_path / "reconcile.args"
    environment = {
        **os.environ,
        "LIFE_MANAGER_PYTHON": sys.executable,
        "LIFE_MANAGER_LOCK_PYTHON": sys.executable,
        "LIFE_MANAGER_STATE_ROOT": str(state_root),
        "LIFE_MANAGER_OCCURRENCE_ID": "crowdworks-revenue-paid:run-1",
        "RECONCILE_ARGS": str(args_file),
    }

    result = subprocess.run([str(fake_owner)], env=environment, text=True,
                            capture_output=True, check=False)

    assert result.returncode == 0
    args = args_file.read_text(encoding="utf-8")
    assert "--resolve" in args
    assert "--state-root " + str(state_root) in args
    assert "--occurrence crowdworks-revenue-paid:run-1" in args
