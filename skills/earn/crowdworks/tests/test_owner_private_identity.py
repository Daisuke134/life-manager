"""Owner entrypoints validate the user's input before acquiring provider resources."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from skills.earn.crowdworks.tests.test_profile_private_identity import CANDIDATE, provider, write_json


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills/earn/crowdworks/scripts"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LIFE_MANAGER_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("AI_BROWSER_REGISTRY", str(tmp_path / "browsers.toml"))
    for key in ("CDP", "CDP_PORT", "CLOAK_CDP_BASE_URL", "LIFE_MANAGER_LOOP_ID",
                "LIFE_MANAGER_BROWSER_IDENTITY", "LIFE_MANAGER_BROWSER_TARGET_OWNER",
                "LIFE_MANAGER_BROWSER_LEASE_IDENTITY", "LIFE_MANAGER_OCCURRENCE_ID"):
        monkeypatch.delenv(key, raising=False)
    return home


def write_inputs(home):
    candidate = write_json(home / ".config/anicca/job-search/profile.json", CANDIDATE)
    profile = write_json(home / ".config/anicca/crowdworks/public-profile.json",
                         provider() | {"occupation_detail": {"id": "2", "label": "デザイナー"}})
    return candidate, profile


def copy_profile(fake_root):
    for relative in ("skills/earn/crowdworks/scripts/profile.py",
                     "apps/job-search-loop/job_search_loop/config.py"):
        target = fake_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def application(tmp_path, monkeypatch):
    name = "crowdworks_application_private_identity_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "application_owner.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    module.STATE = tmp_path / "application-state"
    module.STATE.mkdir()
    module.TRANSACTION = module.STATE / "application-transaction.json"
    module.LEDGER = module.STATE / "application-receipts.jsonl"
    module.TRANSACTION.write_bytes(b'{"pending":{"job-1":{"proposal":"keep"}}}')
    write_json(module.STATE / "application-owner.json", {"next_group_index": 5})
    return module


def test_application_missing_identity_stops_before_browser_and_preserves_pending(tmp_path, monkeypatch, capsys):
    module = application(tmp_path, monkeypatch)
    pending = module.TRANSACTION.read_bytes()
    calls = []
    monkeypatch.setattr(module.account, "_owner", lambda: calls.append("browser") or False)
    monkeypatch.setattr(module, "_clear_pre_effect_hint", lambda: calls.append("hint"))

    assert module.main() == 78

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "setup_required" and result["effect_delta"] == 0
    assert result["missing"] and result["next_group_index"] == 5
    assert calls == [] and module.TRANSACTION.read_bytes() == pending


@pytest.mark.parametrize("observed", ["87654321", None])
def test_application_account_mismatch_precedes_profile_and_discovery(tmp_path, monkeypatch, capsys, isolated_home, observed):
    write_inputs(isolated_home)
    module = application(tmp_path, monkeypatch)
    pending = module.TRANSACTION.read_bytes()
    calls = []
    monkeypatch.setattr(module.account, "_owner", lambda: True)
    monkeypatch.setattr(module.account, "run_ensure", lambda **_kwargs: SimpleNamespace(
        authenticated=True, account_id=observed))
    monkeypatch.setattr(module, "_clear_pre_effect_hint", lambda: None)
    monkeypatch.setattr(module.account, "_browser", lambda *_args: calls.append("browser"))

    assert module.main() == 78

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "setup_required" and result["effect_delta"] == 0
    assert calls == [] and module.TRANSACTION.read_bytes() == pending


def test_application_retains_profile_setup_reason_and_closes_its_page(tmp_path, monkeypatch, capsys, isolated_home):
    write_inputs(isolated_home)
    module = application(tmp_path, monkeypatch)
    closed = []
    page = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(module.account, "_owner", lambda: True)
    monkeypatch.setattr(module.account, "run_ensure", lambda **_kwargs: SimpleNamespace(
        authenticated=True, account_id="5432107"))
    monkeypatch.setattr(module, "_clear_pre_effect_hint", lambda: None)
    monkeypatch.setattr(module.account, "_browser", lambda *_args: SimpleNamespace(
        contexts=[SimpleNamespace(new_page=lambda: page)]))
    monkeypatch.setattr(module.profile, "run_apply", lambda **_kwargs: {
        "ok": False, "error": "setup_required", "missing": ["provider_profile.avatar_path"]})

    assert module.main() == 78
    assert json.loads(capsys.readouterr().out)["missing"] == ["provider_profile.avatar_path"]
    assert closed == [True]


def shell_tree(tmp_path, owner):
    fake_root = tmp_path / "repo"
    target = fake_root / "skills/earn/crowdworks/scripts" / owner
    target.parent.mkdir(parents=True)
    shutil.copy2(SCRIPTS / owner, target)
    copy_profile(fake_root)
    lock = fake_root / "skills/browser/scripts/run_with_file_lock.py"
    lock.parent.mkdir(parents=True)
    lock.write_text("import os,pathlib,sys\n"
                    "pathlib.Path(os.environ['LOCK_ARGS_FILE']).write_text('called')\n"
                    "i=sys.argv.index('--')+1\n"
                    "os.execv(sys.argv[i],sys.argv[i:])\n")
    if owner == "application-owner":
        kernel = target.with_name("application_owner.py")
    else:
        kind = "reply" if owner == "reply-owner" else "paid"
        kernel = fake_root / f"skills/_shared/marketplace-core/scripts/{kind}_kernel.py"
    kernel.parent.mkdir(parents=True, exist_ok=True)
    kernel.write_text("import json,os,pathlib,sys\n"
                      "pathlib.Path(os.environ['KERNEL_ARGS_FILE']).write_text(json.dumps(sys.argv[1:]))\n")
    return target


def run_shell(owner, tmp_path, args=()):
    return subprocess.run(["/bin/bash", str(owner), *map(str, args)], text=True, capture_output=True,
                          env={**os.environ, "LIFE_MANAGER_PYTHON": sys.executable,
                               "LIFE_MANAGER_LOCK_PYTHON": sys.executable,
                               "LOCK_ARGS_FILE": str(tmp_path / "lock.args"),
                               "KERNEL_ARGS_FILE": str(tmp_path / "kernel.args")})


@pytest.mark.parametrize("owner", ["application-owner", "reply-owner", "paid-owner"])
def test_owner_setup_failure_precedes_lock_and_kernel(tmp_path, owner):
    target = shell_tree(tmp_path, owner)
    result = run_shell(target, tmp_path)

    assert result.returncode == 78
    assert json.loads(result.stdout)["error"] == "setup_required"
    assert not (tmp_path / "lock.args").exists()
    assert not (tmp_path / "kernel.args").exists()


@pytest.mark.parametrize("owner", ["application-owner", "reply-owner", "paid-owner"])
def test_owner_uses_private_identity_for_kernel(tmp_path, isolated_home, owner):
    write_inputs(isolated_home)
    target = shell_tree(tmp_path, owner)
    result = run_shell(target, tmp_path)

    assert result.returncode == 0, result.stderr
    args = json.loads((tmp_path / "kernel.args").read_text())
    if owner == "paid-owner":
        assert args[args.index("--account-id") + 1] == "5432107"


@pytest.mark.parametrize("owner", ["reply-owner", "paid-owner"])
@pytest.mark.parametrize("equals", [False, True])
def test_owner_checks_explicit_profile_paths_instead_of_defaults(tmp_path, owner, equals):
    candidate = write_json(tmp_path / "custom-candidate.json", CANDIDATE)
    local = write_json(tmp_path / "custom-provider.json", provider())
    target = shell_tree(tmp_path, owner)
    args = ([f"--candidate-profile={candidate}", f"--provider-profile={local}"] if equals else
            ["--candidate-profile", candidate, "--provider-profile", local])
    result = run_shell(target, tmp_path, args)

    assert result.returncode == 0, result.stderr
    forwarded = json.loads((tmp_path / "kernel.args").read_text())
    assert all(str(arg) in forwarded for arg in args)
    if owner == "paid-owner":
        assert forwarded[forwarded.index("--account-id") + 1] == "5432107"


@pytest.mark.parametrize("script", ["reconcile_application_no_submit.py",
                                   "reconcile_reply_no_send.py",
                                   "reconcile_reply_accept_contract.py"])
def test_reconcile_setup_failure_preserves_admission_fence(tmp_path, monkeypatch, capsys, script):
    sys.path.insert(0, str(SCRIPTS))
    name = "crowdworks_private_" + script.removesuffix(".py")
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / script)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    state = tmp_path / "fenced-state"
    state.mkdir()
    database = tmp_path / "admission.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE fence (state TEXT, effect_unknown INTEGER)")
        db.execute("INSERT INTO fence VALUES ('claimed',1)")
    before = database.read_bytes()
    args = ["--state-root", str(state), "--resolve"]
    if script == "reconcile_reply_accept_contract.py":
        args += ["--occurrence", "crowdworks-revenue-reply:run-1", "--thread-id", "123"]
    else:
        args += ["--admission-db", str(database)]
        if script == "reconcile_reply_no_send.py":
            args += ["--all-fenced"]

    assert module.main(args) == 78
    assert json.loads(capsys.readouterr().out)["error"] == "setup_required"
    assert database.read_bytes() == before
    assert list(state.iterdir()) == []
