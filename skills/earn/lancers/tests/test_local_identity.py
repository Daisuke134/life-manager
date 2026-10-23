from __future__ import annotations

import importlib.util
import io
import json
import os
from datetime import date
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from skills.earn.lancers.tests.identity_fixture import PROFILE, write_identity


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills/earn/lancers/scripts"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def empty_home(tmp_path, monkeypatch):
    home = tmp_path / "empty-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    assert not (home / ".config").exists()
    return home


@pytest.mark.parametrize("broken", [False, True])
def test_run_loop_requires_identity_before_any_external_callback(empty_home, tmp_path, broken):
    if broken:
        candidate, _ = write_identity(empty_home)
        candidate.write_text('{"version":1,"candidate":{"name":"private-marker"},"facts":[]}')
    module = _load("lancers_missing_identity_loop", "application_loop.py")
    calls = []

    def discover(**_kwargs):
        calls.append("discovery")
        return {"ok": True, "opportunities": []}

    def forbidden(*_args, **_kwargs):
        calls.append("external")
        raise AssertionError("external work is forbidden without setup")

    result = module.run_loop(state_path=tmp_path / "application.json",
                             evidence_root=tmp_path / "evidence", discoverer=discover,
                             planner=forbidden, safety_verifier=forbidden, submitter=forbidden)
    assert result.get("error") == "setup_required"
    assert result["ok"] is False
    assert "candidate_profile" in result["missing"]
    assert "private-marker" not in json.dumps(result)
    assert calls == []
    assert not (tmp_path / "evidence").exists()


@pytest.mark.parametrize("reconcile", [False, True])
def test_main_requires_identity_before_dispatch_and_notification(empty_home, tmp_path, monkeypatch, reconcile):
    module = _load("lancers_missing_identity_main", "application_loop.py")
    calls = []

    def dispatch(*_args, **_kwargs):
        calls.append("dispatch")
        return {"ok": True}

    def notify(_result):
        calls.append("notify")
        return SimpleNamespace(delivery_uncertain=False, pre_send_failed=False)

    monkeypatch.setattr(module, "run_loop", dispatch)
    monkeypatch.setattr(module, "run_reconcile_only", dispatch)
    monkeypatch.setattr(module, "_load", lambda *_: SimpleNamespace(notify_application_wake=notify))
    state = tmp_path / "application.json"
    state.write_text('{"pending":"preserve-me"}')
    output = io.StringIO()
    argv = ["--json", "--state-path", str(state)] + (["--reconcile-only"] if reconcile else [])
    assert module.main(argv, stdout=output) != 0
    assert json.loads(output.getvalue())["error"] == "setup_required"
    assert calls == []
    assert state.read_text() == '{"pending":"preserve-me"}'


def test_planner_and_safety_use_only_local_identity_with_optional_attributes_absent(empty_home):
    write_identity(empty_home)
    module = _load("lancers_other_identity_prompts", "application_loop.py")
    planner = module.build_planner_prompt([], date(2026, 10, 23))
    snapshot = json.loads(planner.split("\nSNAPSHOT:\n", 1)[1])
    safety = json.loads(module._safety_prompt({}, {}).split("\n", 1)[1])
    for proof in (snapshot["seller_proof"], safety["seller_proof"]):
        assert proof["account_id"] == "other-seller"
        assert proof["candidate"]["name"] == "別の利用者"
        assert proof["facts"] == PROFILE["facts"]
        for key in ("profile_version", "proof_version", "price_version"):
            assert len(proof[key]) == 64
        assert not {"catalog_product_id", "portfolio_id", "package_id", "public_software_proof"} & proof.keys()
    for author_value in ("24歳", "東京 (日本)", "日本語ネイティブ", "keiodaisuke", "Daisuke134", "monthly-sns-content-ops-v1"):
        assert author_value not in planner
        assert author_value not in json.dumps(safety, ensure_ascii=False)
    assert "未確認" in planner


def test_import_does_not_read_private_identity(empty_home, monkeypatch):
    reads = []
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path.is_relative_to(empty_home):
            reads.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    _load("lancers_identity_import_boundary", "application_loop.py")
    assert reads == []


def test_crowdworks_profile_cannot_supply_lancers_identity(empty_home, tmp_path):
    _, provider = write_identity(empty_home)
    crowdworks = empty_home / ".config/anicca/crowdworks/public-profile.json"
    crowdworks.parent.mkdir(parents=True)
    provider.rename(crowdworks)
    module = _load("lancers_no_crowdworks_identity", "application_loop.py")
    calls = []
    result = module.run_loop(state_path=tmp_path / "application.json",
                             discoverer=lambda **_: calls.append("discovery") or {"ok": True, "opportunities": []})
    assert result.get("error") == "setup_required"
    assert "provider_profile.account_id" in result["missing"]
    assert calls == []


@pytest.mark.parametrize("configured", [False, True])
def test_account_id_cli_validates_both_inputs_without_creating_them(empty_home, configured):
    if configured:
        write_identity(empty_home)
    result = subprocess.run([sys.executable, str(SCRIPTS / "local_identity.py"), "account-id"],
                            capture_output=True, text=True, env=os.environ)
    if configured:
        assert result.returncode == 0, result.stderr
        assert result.stdout == "other-seller\n"
    else:
        assert result.returncode == 78
        assert json.loads(result.stdout) == {"ok": False, "error": "setup_required", "missing": [
            "candidate_profile", "provider_profile.account_id"]}
        assert not (empty_home / ".config").exists()


def test_paid_answer_grounds_from_account_only_lancers_profile(empty_home, tmp_path, monkeypatch):
    write_identity(empty_home)
    module = _load("lancers_paid_local_grounding", "paid_adapter.py")
    contexts = []
    monkeypatch.setattr(module._REPLY_COMPOSER, "compose", lambda context, **_: contexts.append(context) or "本人の回答")
    adapter = module.LancersPaidAdapter(account_id="other-seller", inventory_reader=lambda: {},
                                        provider=object(), state_path=tmp_path / "application.json")
    assert adapter.provider_profile == empty_home / ".config/anicca/lancers/public-profile.json"
    assert adapter._compose_answer({"buyer_context": "仕様を説明してください"}) == "本人の回答"
    assert "業務自動化を実装できる" in json.dumps(contexts, ensure_ascii=False)


def _managed_python_stub(tmp_path):
    python = tmp_path / "managed-python"
    python.write_text(
        "#!/usr/bin/env python3\nimport json, os, pathlib, sys\n"
        "script = pathlib.Path(sys.argv[1])\n"
        "if script.name == 'local_identity.py':\n"
        f"    os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n"
        "assert script.name == 'paid_kernel.py', 'unexpected production dispatch'\n"
        "pathlib.Path(os.environ['PAID_ARGV']).write_text(json.dumps(sys.argv[1:]))\n"
        "raise SystemExit(1)\n"
    )
    python.chmod(0o700)
    return python


@pytest.mark.parametrize("configured", [False, True])
def test_paid_owner_uses_validated_local_account_before_kernel(empty_home, tmp_path, configured):
    if configured:
        write_identity(empty_home)
    python = _managed_python_stub(tmp_path)
    args = tmp_path / "paid-argv.json"
    result = subprocess.run([str(SCRIPTS / "paid-owner")], capture_output=True, text=True,
                            env={**os.environ, "LIFE_MANAGER_PYTHON": str(python),
                                 "LIFE_MANAGER_STATE_ROOT": str(tmp_path / "state"),
                                 "PAID_ARGV": str(args)})
    if configured:
        assert result.returncode == 1
        argv = json.loads(args.read_text())
        assert argv[argv.index("--account-id") + 1] == "other-seller"
        assert "keiodaisuke" not in argv
    else:
        assert result.returncode == 78
        assert json.loads(result.stdout)["error"] == "setup_required"
        assert not args.exists()
