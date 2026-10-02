from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[4]
OWNER = ROOT / "skills/earn/lancers/scripts/application-owner"


def _run_owner(tmp_path: Path, result: dict[str, object]) -> tuple[subprocess.CompletedProcess[str], Path]:
    fake_root = tmp_path / "release"
    fake_script = fake_root / "skills/earn/lancers/scripts/application_loop.py"
    fake_script.parent.mkdir(parents=True)
    fake_script.write_text("# fake application entrypoint\n", encoding="utf-8")
    owner = fake_script.with_name("application-owner")
    owner.write_text(OWNER.read_text(encoding="utf-8"), encoding="utf-8")
    owner.chmod(0o700)
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        f"print(json.dumps({result!r}, separators=(',', ':')))\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o700)
    state_root = tmp_path / "state"
    hint = tmp_path / "entrypoint-result.json"
    env = {
        **os.environ,
        "LIFE_MANAGER_PYTHON": str(fake_python),
        "LIFE_MANAGER_STATE_ROOT": str(state_root),
        "LIFE_MANAGER_RESULT_HINT_PATH": str(hint),
    }
    return subprocess.run([str(owner)], env=env, text=True, capture_output=True), hint


def test_application_owner_marks_only_account_preflight_failures(tmp_path: Path) -> None:
    failed, hint = _run_owner(
        tmp_path / "preflight", {"ok": False, "platform": "lancers", "submitted": False, "error": "account_lock_busy"}
    )
    assert failed.returncode == 1
    assert json.loads(hint.read_text(encoding="utf-8")) == {
        "status": "pre_effect_failure",
        "effect": 0,
    }
    assert stat.S_IMODE(hint.stat().st_mode) == 0o600


def test_application_owner_marks_account_unavailable(tmp_path: Path) -> None:
    failed, hint = _run_owner(
        tmp_path / "unavailable", {"ok": False, "platform": "lancers", "submitted": False, "error": "account_unavailable"}
    )
    assert failed.returncode == 1
    assert json.loads(hint.read_text(encoding="utf-8")) == {
        "status": "pre_effect_failure",
        "effect": 0,
    }


def test_application_owner_does_not_mark_provider_effect_uncertainty(tmp_path: Path) -> None:
    failed, hint = _run_owner(
        tmp_path / "provider", {"ok": False, "platform": "lancers", "submitted": True, "error": "submission_uncertain"}
    )
    assert failed.returncode == 1
    assert not hint.exists()
