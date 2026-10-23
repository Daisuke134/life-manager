"""Guided installation uses owner input and the existing release/control plane."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
from types import SimpleNamespace
import urllib.request

import pytest
import websocket

from skills.earn.lancers.tests.test_storefront_offer_reads_catalog import _private_catalog, _private_product


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "skills/earn/lancers/scripts/install_local.py"
WRAPPER = ROOT / "skills/earn/lancers/install.sh"
PREFIX = "lancers-revenue-"
JOBS = {PREFIX + name for name in (
    "browser", "application", "storefront", "negotiate", "paid", "work-sync", "telegram-report")}


def _forbidden(*_args, **_kwargs):
    raise AssertionError("real provider/browser/login/host operation is forbidden")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "owner-home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    for key in ("CDP", "CLOAK_CDP_BASE_URL", "LIFE_MANAGER_BROWSER_GUARD",
                "LIFE_MANAGER_BROWSER_IDENTITY", "LIFE_MANAGER_BROWSER_LEASE_IDENTITY",
                "LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID", "AI_BROWSER_HOLDER_START",
                "LIFE_MANAGER_LOOP_ID", "LIFE_MANAGER_OCCURRENCE_ID", "LIFE_MANAGER_RELEASE_SHA",
                "AGENT_RUNNER_CONFIG", "LIFE_MANAGER_HOST_PROFILE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(websocket, "create_connection", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    return home


def _tree(root):
    return {str(path.relative_to(root)): (
        os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None,
        stat.S_IMODE(path.lstat().st_mode)) for path in root.rglob("*")}


def _installer():
    if not SCRIPT.is_file():
        pytest.fail("INSTALL contract is missing: the guided install_local.py entrypoint is not implemented")
    spec = importlib.util.spec_from_file_location("lancers_guided_install_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_codex_login_keeps_the_manual_sign_in_prompt_visible(tmp_path, isolated_home, capfd):
    executable = tmp_path / "fixture-codex"
    executable.write_text(
        f"#!{sys.executable}\nimport os,pathlib,sys\n"
        "marker=pathlib.Path(os.environ['CODEX_HOME'])/'signed-in'\n"
        "if sys.argv[1:] == ['login','status']: raise SystemExit(0 if marker.is_file() else 1)\n"
        "assert sys.argv[1:] == ['login']\n"
        "print('Sign in at https://example.invalid/fixture-login',file=sys.stderr,flush=True)\n"
        "marker.parent.mkdir(parents=True,exist_ok=True)\nmarker.write_text('fixture')\n")
    executable.chmod(0o700)
    auth_file = isolated_home / ".selected-codex/auth.json"
    configuration = tmp_path / "runner.json"
    configuration.write_text(json.dumps({"providers": {"codex": {
        "executable": str(executable), "account_profile_order": ["owner"],
        "profiles": {"owner": {"auth_file": str(auth_file)}}}}}))

    assert _installer()._codex_login({"agent_runner_config": str(configuration)}, {}) is True
    assert "https://example.invalid/fixture-login" in capfd.readouterr().err


def test_public_lancers_dispatch_forwards_plan_without_touching_home(tmp_path, isolated_home):
    repository = tmp_path / "dispatch-repository"
    target = repository / "skills/earn/lancers/install.sh"
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "install.sh", repository / "install.sh")
    target.write_text("#!/bin/bash\n[ \"$#\" = 1 ] && [ \"$1\" = plan ] || exit 91\n"
                      "printf '%s\\n' '{\"status\":\"plan\",\"product\":\"lancers\"}'\n")
    before = _tree(isolated_home)

    completed = subprocess.run(["bash", str(repository / "install.sh"), "lancers", "plan"],
                               env={**os.environ, "HOME": str(isolated_home)},
                               capture_output=True, text=True, timeout=10)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"status": "plan", "product": "lancers"}
    assert _tree(isolated_home) == before


def test_wrapper_prepares_common_runtime_then_uses_the_managed_python(tmp_path, isolated_home):
    repository = tmp_path / "wrapper-repository"
    wrapper = repository / "skills/earn/lancers/install.sh"
    wrapper.parent.mkdir(parents=True)
    if WRAPPER.is_file():
        shutil.copyfile(WRAPPER, wrapper)
    common = repository / "scripts/install-local.sh"
    common.parent.mkdir(parents=True)
    events = tmp_path / "wrapper-events"
    common.write_text(f'#!/bin/bash\n[ "$1" = prepare ] || exit 92\nprintf "prepare\\n" >> "{events}"\n')
    python = isolated_home / ".local/share/life-manager/venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text(f"#!{sys.executable}\nimport json,pathlib,sys\n"
                      f"p=pathlib.Path({str(events)!r})\n"
                      "assert p.read_text() == 'prepare\\n'\n"
                      "p.write_text(p.read_text()+'python\\n')\n"
                      "args=sys.argv[1:]\n"
                      "assert (pathlib.Path(args[0]).name == 'install_local.py' and args[1:] == ['install']) or "
                      "args == ['-m','skills.earn.lancers.scripts.install_local','install']\n"
                      "print(json.dumps({'status':'fixture','business_outcomes_verified':False}))\n")
    python.chmod(0o700)

    completed = subprocess.run(["bash", str(wrapper), "install"],
                               env={**os.environ, "LIFE_MANAGER_PYTHON": str(python)},
                               capture_output=True, text=True, timeout=10)

    assert completed.returncode == 0, completed.stderr
    assert events.read_text() == "prepare\npython\n"
    assert json.loads(completed.stdout)["business_outcomes_verified"] is False


@pytest.fixture
def installation(tmp_path, isolated_home, monkeypatch):
    from runtime.host import local_profile
    from runtime.loop import local_install
    from skills.earn.lancers.scripts import lancers_onboarding as onboarding
    from skills.earn.lancers.scripts import local_identity, storefront_offer

    home = isolated_home
    incoming = tmp_path / "different-owner-home/materials"
    product = _private_product(incoming, listing_external_id="")
    raw = json.loads(product.read_text())
    raw["portfolio"]["external_id"] = raw["software_portfolio"]["external_id"] = ""
    product.write_text(json.dumps(raw, ensure_ascii=False))
    candidate = incoming / "candidate.json"
    candidate.write_text(json.dumps({"version": 1, "candidate": {"name": "PRIVATE-CANDIDATE"},
        "facts": [{"id": "verified-work", "claim": "PRIVATE-FACT-CLAIM", "evidence": "本人が持つ作業記録"}]}))
    catalog = _private_catalog(incoming / "catalog")
    configuration = home / ".config/life-manager"
    configuration.mkdir(parents=True, mode=0o700)
    selected_codex = home / "selected-tools/codex"
    selected_codex.parent.mkdir(parents=True)
    selected_codex.write_text("#!/bin/sh\nexit 93\n")
    selected_codex.chmod(0o700)
    runner_config = configuration / "agent-runner.json"
    runner_config.write_text(json.dumps({"providers": {"codex": {
        "executable": str(selected_codex), "executable_fallbacks": [],
        "account_profile_order": ["owner"], "profiles": {"owner": {
            "automation_home": str(home / ".local/state/codex/owner"),
            "auth_file": str(home / ".codex-owner/auth.json")}}}}}))
    profile = {"schema_version": 1, "owner_home": str(home), "tenant_id": "fixture-owner",
        "source_checkout": str(ROOT), "runtime": {"python": sys.executable, "node": "/fixture/node"},
        "agent_runner_config": str(runner_config), "browser_registry": str(configuration / "browsers.toml"),
        "environment_file": str(home / ".local/state/life-manager/.env")}
    environment = {"HOME": str(home), "LIFE_MANAGER_RUNTIME_PYTHON": sys.executable,
        "LIFE_MANAGER_PYTHON": sys.executable, "AGENT_RUNNER_CONFIG": str(runner_config),
        "LIFE_MANAGER_HOST_PROFILE": str(configuration / "host.json"),
        "LIFE_MANAGER_ENV_FILE": profile["environment_file"], "LANCERS_REPORT_CHAT": "fixture-chat"}
    Path(profile["environment_file"]).parent.mkdir(parents=True)
    Path(profile["environment_file"]).write_text("TELEGRAM_BOT_TOKEN=fixture-not-a-secret\n")
    state = home / ".local/state/anicca/lancers"
    state.mkdir(parents=True)
    (state / "work-sync.json").write_text("{}")
    (state / "application.json").write_text("{}")
    private = home / ".config/anicca/lancers"
    private.mkdir(parents=True, mode=0o700)
    (private / "telegram.env").write_text("LANCERS_REPORT_CHAT=fixture-chat\n")
    release = tmp_path / "accepted-immutable"
    (release / "bin").mkdir(parents=True)
    (release / "bin/lm-loop").write_text("#!/bin/sh\nexit 94\n")
    manifest = {"sha": "a" * 40, "provenance": "ancestor-of-origin-main", "release_paths": "ALL",
                "runtime_python": sys.executable}
    (release / "RELEASE.json").write_text(json.dumps(manifest))
    assert local_identity.validate_profile(json.loads(candidate.read_text()))["candidate"]["name"] == "PRIVATE-CANDIDATE"
    validated, image, avatar = storefront_offer._product(product, catalog, creating=True)
    assert validated["listing_external_id"] == "" and image.parent == avatar.parent == incoming
    assert local_install.validate_release(release, profile) == manifest
    selector = home / "loops/current"
    selector.parent.mkdir()
    selector.symlink_to(tmp_path / "previous-immutable", target_is_directory=True)
    case = SimpleNamespace(home=home, product=product, candidate=candidate, catalog=catalog,
        private_product=private / "storefront-product.json",
        private_candidate=home / ".config/anicca/job-search/profile.json",
        private_catalog=private / "listing-catalog.json", release=release, profile=profile,
        environment=environment, events=[], applied=[], authenticated=True, fresh_ok=True,
        selector=selector, config=runner_config, onboarding=onboarding)
    snapshot = {"url": onboarding.MYPAGE, "ready": "complete", "login_form": False,
                "human_verification": False, "profile_links": ["https://www.lancers.jp/profile/other-seller"]}

    def cut(repo, env, **_kwargs):
        assert Path(repo) == ROOT and env["LIFE_MANAGER_RUNTIME_PYTHON"] == sys.executable
        case.events.append("release")
        return release

    validate = local_install.validate_release

    def validate_immutable(path, binding):
        assert Path(path) == release
        case.events.append("validate-release")
        return validate(path, binding)

    def apply(path, owners, env, **_kwargs):
        assert Path(path) == release and set(owners) <= JOBS and len(owners) == len(set(owners))
        assert env["LIFE_MANAGER_RUNTIME_PYTHON"] == sys.executable
        case.applied.extend(owners)
        case.events.extend("apply:" + owner for owner in owners)
        return [{"ok": True, "loop_id": owner, "changed": False, "readback": "exact_release_loaded"}
                for owner in owners]

    def run(command, **kwargs):
        command = [str(value) for value in command]
        if command[0] == str(selected_codex):
            assert command[1:] in (["login", "status"], ["login"])
            assert kwargs["env"]["CODEX_HOME"] == str(home / ".codex-owner"), "login must use the selected runtime auth profile"
            case.events.append("codex:" + " ".join(command[1:]))
            return subprocess.CompletedProcess(command, 0 if command[1:] == ["login"] or case.authenticated else 1,
                                               "PRIVATE-CODEX-DETAIL", "PRIVATE-CODEX-DETAIL")
        if any(Path(value).name == "with-browser.sh" for value in command):
            assert str(release / "skills/browser/with-browser.sh") in command
            assert "lancers:dais" in command and "observe" in command
            assert str(release / "skills/earn/lancers/scripts/lancers_onboarding.py") in command
            assert sys.executable in command
            assert PREFIX + "browser" in case.applied
            case.events.append("observe")
            result = onboarding.connect(home, snapshot) if case.fresh_ok else {
                "ok": False, "error": "setup_required", "missing": ["account_observation"]}
            return subprocess.CompletedProcess(command, 0 if case.fresh_ok else 78, json.dumps(result), "")
        raise AssertionError("unexpected external operation: " + " ".join(command))

    monkeypatch.setattr(local_profile, "load_host_profile", lambda **_kwargs: profile)
    monkeypatch.setattr(local_profile, "host_environment", lambda **_kwargs: dict(environment))
    monkeypatch.setattr(local_profile, "prepare_host", _forbidden)
    monkeypatch.setattr(local_install, "load_host_profile", lambda **_kwargs: profile)
    monkeypatch.setattr(local_install, "host_environment", lambda **_kwargs: dict(environment))
    monkeypatch.setattr(local_install, "prepare_host", _forbidden)
    monkeypatch.setattr(local_install, "cut_release", cut)
    monkeypatch.setattr(local_install, "validate_release", validate_immutable)
    monkeypatch.setattr(local_install, "apply_targets", apply)
    monkeypatch.setattr(onboarding, "observe", _forbidden)
    monkeypatch.setattr(subprocess, "run", run)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    case.snapshot = snapshot
    return case


def _call(case, capsys, *args):
    try:
        code = _installer().main(list(args))
    except SystemExit as error:
        code = error.code
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["business_outcomes_verified"] is False
    assert "PRIVATE" not in captured.out + captured.err and "other-seller" not in captured.out + captured.err
    assert os.readlink(case.selector).endswith("previous-immutable")
    return code, result


def _inputs(case):
    return ["--candidate-profile", str(case.candidate), "--product", str(case.product),
            "--catalog", str(case.catalog)]


def _jobs(result):
    rows = {row["loop_id"]: row for row in result["jobs"]}
    assert set(rows) == JOBS
    assert all(isinstance(row.get("state"), str) and isinstance(row.get("missing"), list)
               and isinstance(row.get("next_action"), str) for row in rows.values())
    return rows


def test_plan_reads_without_prepare_login_import_observe_or_apply(installation, capsys):
    case = installation
    before = _tree(case.home)
    _code, result = _call(case, capsys, "plan", *_inputs(case))
    assert case.events == case.applied == [] and _tree(case.home) == before
    _jobs(result)


def test_missing_inputs_hold_only_their_lanes(installation, capsys):
    case = installation
    _code, result = _call(case, capsys, "install")
    rows = _jobs(result)
    assert {PREFIX + name for name in ("browser", "work-sync", "telegram-report")} <= set(case.applied)
    assert not {PREFIX + name for name in ("application", "negotiate", "paid", "storefront")} & set(case.applied)
    assert "candidate_profile" in rows[PREFIX + "application"]["missing"]
    assert rows[PREFIX + "storefront"]["missing"]
    assert not case.private_product.exists() and not case.private_candidate.exists()


@pytest.mark.parametrize("kind", ["candidate", "product"])
def test_broken_input_is_not_replaced_by_an_author_template(installation, capsys, kind):
    case = installation
    getattr(case, kind).write_text('{"PRIVATE-BROKEN-INPUT":')
    _code, result = _call(case, capsys, "install", *_inputs(case))
    rows = _jobs(result)
    assert PREFIX + "work-sync" in case.applied and PREFIX + "telegram-report" in case.applied
    target = PREFIX + ("application" if kind == "candidate" else "storefront")
    assert target not in case.applied and rows[target]["missing"]
    assert not getattr(case, "private_" + kind).exists()


@pytest.mark.parametrize("fresh_ok", [True, False])
def test_kept_running_browser_still_gets_a_fresh_account_observation(installation, monkeypatch, capsys, fresh_ok):
    from runtime.loop import local_install

    case = installation
    case.fresh_ok = fresh_ok
    apply = local_install.apply_targets

    def keep_browser(path, owners, env):
        rows = apply(path, owners, env)
        if owners == [PREFIX + "browser"]:
            rows[0]["skipped"] = "loaded-running"
        return rows

    monkeypatch.setattr(local_install, "apply_targets", keep_browser)
    _code, result = _call(case, capsys, "install", *_inputs(case))
    rows = _jobs(result)
    assert "observe" in case.events
    assert rows[PREFIX + "browser"]["state"] == "waiting"
    for name in ("application", "storefront", "negotiate", "paid", "work-sync"):
        assert (PREFIX + name in case.applied) is fresh_ok
        assert ("account_observation" in rows[PREFIX + name]["missing"]) is not fresh_ok
    assert PREFIX + "telegram-report" in case.applied
    assert result["status"] == "waiting"


def test_non_object_product_is_held_without_stopping_independent_jobs(installation, capsys):
    case = installation
    case.product.write_text("[]")
    _code, result = _call(case, capsys, "install", *_inputs(case))
    rows = _jobs(result)
    assert PREFIX + "storefront" not in case.applied and rows[PREFIX + "storefront"]["missing"]
    assert PREFIX + "work-sync" in case.applied and PREFIX + "telegram-report" in case.applied
    assert not case.private_product.exists()


def test_other_home_input_imports_relative_assets_and_optional_catalog(installation, capsys):
    case = installation
    source = _tree(case.product.parent)
    config = case.config.read_bytes()
    _code, result = _call(case, capsys, "install", *_inputs(case))
    _jobs(result)
    assert set(case.applied) == JOBS
    product = json.loads(case.private_product.read_text())
    assert product["listing_external_id"] == "" and product["seller_profile"]["public_path"] == "/profile/other-seller"
    for key in ("image_path", "profile_avatar_path"):
        assert product[key] == str((case.product.parent / json.loads(case.product.read_text())[key]).resolve())
    assert json.loads(case.private_candidate.read_text()) == json.loads(case.candidate.read_text())
    assert json.loads(case.private_catalog.read_text()) == json.loads(case.catalog.read_text())
    for path in (case.private_candidate, case.private_product, case.private_catalog):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert _tree(case.product.parent) == source and case.config.read_bytes() == config
    assert case.events.index("validate-release") < case.events.index("apply:" + PREFIX + "browser") < case.events.index("observe")


def test_reimport_of_empty_ids_preserves_confirmed_private_ids(installation, capsys):
    case = installation
    _call(case, capsys, "install", *_inputs(case))
    product = json.loads(case.private_product.read_text())
    product["listing_external_id"] = "99001"
    product["portfolio"]["external_id"] = "88001"
    product["software_portfolio"]["external_id"] = "88002"
    case.private_product.write_text(json.dumps(product, ensure_ascii=False))
    before = case.private_product.read_bytes()
    _call(case, capsys, "install", *_inputs(case))
    assert case.private_product.read_bytes() == before
    assert json.loads(case.product.read_text())["listing_external_id"] == ""


@pytest.mark.parametrize("kind", ["candidate", "product"])
def test_different_existing_owner_input_is_preserved_and_lane_is_held(installation, capsys, kind):
    case = installation
    _call(case, capsys, "install", *_inputs(case))
    if kind == "product":
        saved = json.loads(case.private_product.read_text())
        saved["listing_external_id"] = "99001"
        case.private_product.write_text(json.dumps(saved, ensure_ascii=False))
    before = getattr(case, "private_" + kind).read_bytes()
    incoming = json.loads(getattr(case, kind).read_text())
    if kind == "candidate":
        incoming["facts"][0]["claim"] = "PRIVATE-DIFFERENT-OWNER"
    else:
        incoming["listing_external_id"] = "77001"
    getattr(case, kind).write_text(json.dumps(incoming, ensure_ascii=False))
    case.applied.clear()
    _code, result = _call(case, capsys, "install", *_inputs(case))
    rows = _jobs(result)
    target = PREFIX + ("application" if kind == "candidate" else "storefront")
    assert target not in case.applied and rows[target]["missing"]
    assert PREFIX + "work-sync" in case.applied and PREFIX + "telegram-report" in case.applied
    assert getattr(case, "private_" + kind).read_bytes() == before


def test_unconfirmed_codex_login_stops_before_browser_or_apply(installation, capsys):
    case = installation
    case.authenticated = False
    _code, result = _call(case, capsys, "install", *_inputs(case))
    assert [event for event in case.events if event.startswith("codex:")] == [
        "codex:login status", "codex:login", "codex:login status"]
    assert case.applied == [] and "observe" not in case.events
    assert result["status"] != "installed"


def test_fresh_observe_failure_is_not_overwritten_by_old_status_or_a_report_gate(installation, capsys):
    case = installation
    assert case.onboarding.connect(case.home, case.snapshot)["ok"] is True
    assert case.onboarding.ready(case.home)["ok"] is True
    case.fresh_ok = False
    _code, result = _call(case, capsys, "install", *_inputs(case))
    rows = _jobs(result)
    assert case.events.count("observe") == 1
    assert PREFIX + "telegram-report" in case.applied
    assert not {PREFIX + name for name in ("application", "negotiate", "paid", "storefront", "work-sync")} & set(case.applied)
    assert rows[PREFIX + "work-sync"]["missing"] and result["status"] != "installed"


@pytest.mark.parametrize("only", ["candidate", "product"])
def test_candidate_and_storefront_lanes_can_install_independently(installation, capsys, only):
    case = installation
    flag = "--candidate-profile" if only == "candidate" else "--product"
    _code, result = _call(case, capsys, "install", flag, str(getattr(case, only)))
    _jobs(result)
    candidate_jobs = {PREFIX + name for name in ("application", "negotiate", "paid")}
    assert (candidate_jobs <= set(case.applied)) is (only == "candidate")
    assert (PREFIX + "storefront" in case.applied) is (only == "product")
    assert PREFIX + "work-sync" in case.applied and PREFIX + "telegram-report" in case.applied
