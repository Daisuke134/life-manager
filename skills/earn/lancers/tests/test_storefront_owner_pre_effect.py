from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[4]
OWNER = ROOT / "skills/earn/lancers/scripts/storefront-owner"


def _run_owner(
    tmp_path: Path, result: dict[str, object], *, host_hint: bool = False, args: tuple[str, ...] = ()
) -> tuple[subprocess.CompletedProcess[str], Path]:
    fake_root = tmp_path / "release"
    fake_script = fake_root / "skills/earn/lancers/scripts/storefront_offer.py"
    fake_script.parent.mkdir(parents=True)
    fake_script.write_text("# fake storefront entrypoint\n", encoding="utf-8")
    owner = fake_script.with_name("storefront-owner")
    owner.write_text(OWNER.read_text(encoding="utf-8"), encoding="utf-8")
    owner.chmod(0o700)
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "assert pathlib.Path(sys.argv[1]).name == 'storefront_offer.py', 'unexpected production dispatch'\n"
        f"pathlib.Path({str(tmp_path / 'argv.json')!r}).write_text(json.dumps(sys.argv[1:]))\n"
        f"print(json.dumps({result!r}, separators=(',', ':')))\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o700)
    state_root = tmp_path / "state"
    hint = tmp_path / "entrypoint-result.json"
    if host_hint:
        # lm_loop_run.py writes this marker before spawning the owner.
        hint.write_text('{"status":"pre_effect_failure","effect":0}\n', encoding="utf-8")
        hint.chmod(0o600)
    env = {
        **os.environ,
        "LIFE_MANAGER_PYTHON": str(fake_python),
        "LIFE_MANAGER_STATE_ROOT": str(state_root),
        "LIFE_MANAGER_RESULT_HINT_PATH": str(hint),
    }
    return subprocess.run([str(owner), *args], env=env, text=True, capture_output=True), hint


def test_owner_does_not_supply_author_product_and_preserves_explicit_product(tmp_path):
    result = {"ok": False, "logged_in": False, "error": "setup_required"}
    for name, args in (("default", ()), ("explicit", ("--product", str(tmp_path / "private product.json")))):
        directory = tmp_path / name
        _run_owner(directory, result, args=args)
        argv = json.loads((directory / "argv.json").read_text())
        assert argv.count("--product") == (1 if args else 0)
        if args:
            assert argv[argv.index("--product") + 1] == args[1]


def test_storefront_owner_marks_only_account_preflight_failures(tmp_path: Path) -> None:
    failed, hint = _run_owner(
        tmp_path / "preflight", {"ok": False, "logged_in": False, "error": "account_unavailable"}
    )
    assert failed.returncode == 1
    assert json.loads(hint.read_text(encoding="utf-8")) == {
        "status": "pre_effect_failure",
        "effect": 0,
    }
    assert stat.S_IMODE(hint.stat().st_mode) == 0o600


def test_storefront_owner_does_not_mark_provider_effect_uncertainty(tmp_path: Path) -> None:
    failed, hint = _run_owner(
        tmp_path / "provider", {"ok": False, "logged_in": True, "error": "offer_unavailable"}
    )
    assert failed.returncode == 1
    assert not hint.exists()


def test_storefront_owner_clears_host_pre_effect_hint_before_provider_step(tmp_path: Path) -> None:
    uncertain, hint = _run_owner(
        tmp_path / "uncertain",
        {"ok": False, "logged_in": True, "error": "portfolio_submission_uncertain"},
        host_hint=True,
    )
    assert uncertain.returncode == 1
    assert not hint.exists()

    preflight, hint = _run_owner(
        tmp_path / "preflight",
        {"ok": False, "logged_in": False, "error": "account_unavailable"},
        host_hint=True,
    )
    assert preflight.returncode == 1
    assert json.loads(hint.read_text(encoding="utf-8")) == {
        "status": "pre_effect_failure",
        "effect": 0,
    }
    assert stat.S_IMODE(hint.stat().st_mode) == 0o600


def test_storefront_owner_keeps_host_hint_for_account_lock_busy(tmp_path: Path) -> None:
    busy, hint = _run_owner(
        tmp_path / "busy",
        {"ok": False, "logged_in": False, "error": "account_lock_busy"},
        host_hint=True,
    )
    assert busy.returncode == 1
    assert json.loads(hint.read_text(encoding="utf-8")) == {"status": "pre_effect_failure", "effect": 0}
    assert stat.S_IMODE(hint.stat().st_mode) == 0o600


def test_storefront_owner_keeps_host_hint_for_any_pre_login_failure(tmp_path: Path) -> None:
    # storefront_offer reaches a provider mutation only after logged_in=True.
    failed, hint = _run_owner(
        tmp_path / "pre-login",
        {"ok": False, "logged_in": False, "error": "offer_unavailable"},
        host_hint=True,
    )
    assert failed.returncode == 1
    assert json.loads(hint.read_text(encoding="utf-8")) == {"status": "pre_effect_failure", "effect": 0}
    assert stat.S_IMODE(hint.stat().st_mode) == 0o600


def test_storefront_owner_uses_explicit_owner_mode_and_keeps_uncertain_hint_absent(tmp_path):
    failed, hint = _run_owner(
        tmp_path, {"ok": False, "logged_in": None, "error": "creation_pending"}, host_hint=True)
    argv = json.loads((tmp_path / "argv.json").read_text())
    assert "--owner-run" in argv and "--apply" not in argv and "--create-package" not in argv
    assert argv[argv.index("--state-path") + 1] == str(tmp_path / "state/application.json")
    assert failed.returncode == 1 and not hint.exists()
