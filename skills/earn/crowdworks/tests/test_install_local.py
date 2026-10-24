"""Owner setup stays private and admits each existing CrowdWorks owner separately."""
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


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "skills/earn/crowdworks/scripts/install_local.py"
WRAPPER = ROOT / "skills/earn/crowdworks/install.sh"
PREFIX = "crowdworks-revenue-"
JOBS = {PREFIX + name for name in ("browser", "application", "reply", "paid", "report")}


def _forbidden(*_args, **_kwargs):
    raise AssertionError("real provider, browser, login, or host mutation is forbidden")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "different-owner-home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    registry = tmp_path / "empty-browser-registry.toml"
    registry.write_text("")
    monkeypatch.setenv("AI_BROWSER_REGISTRY", str(registry))
    monkeypatch.setenv("LIFE_MANAGER_STATE_ROOT", str(tmp_path / "isolated-state"))
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(tmp_path / "isolated-admission"))
    for key in tuple(os.environ):
        if (key.startswith(("TELEGRAM_", "LIFE_MANAGER_BROWSER_")) or key in {
            "CDP", "CDP_PORT", "CLOAK_CDP_BASE_URL", "AI_BROWSER_GUARD", "AI_BROWSER_HOLDER_START",
            "AGENT_RUNNER_CONFIG", "LIFE_MANAGER_HOST_PROFILE", "LIFE_MANAGER_ENV_FILE",
            "LIFE_MANAGER_LOOP_ID", "LIFE_MANAGER_OCCURRENCE_ID", "CROWDWORKS_REPORT_CHAT", "GIG_REPORT_CHAT",
        }):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    return home


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False))
    path.chmod(0o600)
    return path


def _tree(root):
    return {str(path.relative_to(root)): (
        os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None,
        stat.S_IMODE(path.lstat().st_mode)) for path in root.rglob("*")}


def _installer():
    if not SCRIPT.is_file():
        pytest.fail("guided CrowdWorks installer is missing")
    spec = importlib.util.spec_from_file_location("crowdworks_guided_installer_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rows(result):
    rows = {row["loop_id"]: row for row in result["jobs"]}
    assert set(rows) == JOBS
    assert all(isinstance(row["missing"], list) and row["next_action"] for row in rows.values())
    return rows


def test_empty_home_plan_has_no_file_login_browser_or_apply_effects(isolated_home, monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", _forbidden)
    before = _tree(isolated_home)

    assert _installer().main(["plan"]) == 0

    result = json.loads(capsys.readouterr().out)
    rows = _rows(result)
    assert result["status"] == "plan" and result["business_outcomes_verified"] is False
    assert _tree(isolated_home) == before
    assert all("host_profile" in row["missing"] for row in rows.values())
    assert {"candidate_profile", "provider_profile", "account_observation"} <= set(
        rows[PREFIX + "application"]["missing"])


def test_wrapper_plan_forwards_inputs_without_common_prepare(tmp_path, isolated_home):
    repository = tmp_path / "wrapper-repository"
    wrapper = repository / "skills/earn/crowdworks/install.sh"
    wrapper.parent.mkdir(parents=True)
    assert WRAPPER.is_file(), "guided CrowdWorks shell wrapper is missing"
    shutil.copyfile(WRAPPER, wrapper)
    python = isolated_home / ".local/share/life-manager/venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text(f"#!{sys.executable}\nimport json,sys\n"
                      "assert sys.argv[2:] == ['plan','--provider-profile','fixture.json']\n"
                      "print(json.dumps({'status':'plan'}))\n")
    python.chmod(0o700)
    before = _tree(isolated_home)

    completed = subprocess.run(["bash", str(wrapper), "plan", "--provider-profile", "fixture.json"],
                               capture_output=True, text=True, timeout=10)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "plan"
    assert _tree(isolated_home) == before


def test_wrapper_prepares_common_runtime_before_managed_python(tmp_path, isolated_home):
    repository = tmp_path / "wrapper-repository"
    wrapper = repository / "skills/earn/crowdworks/install.sh"
    wrapper.parent.mkdir(parents=True)
    assert WRAPPER.is_file(), "guided CrowdWorks shell wrapper is missing"
    shutil.copyfile(WRAPPER, wrapper)
    events = tmp_path / "wrapper-events"
    common = repository / "scripts/install-local.sh"
    common.parent.mkdir(parents=True)
    common.write_text(f'#!/bin/bash\n[ "$1" = prepare ] || exit 91\nprintf "prepare\\n" >> "{events}"\n')
    python = isolated_home / ".local/share/life-manager/venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text(f"#!{sys.executable}\nimport json,pathlib,sys\n"
                      f"assert pathlib.Path({str(events)!r}).read_text() == 'prepare\\n'\n"
                      "assert sys.argv[2:] == ['install']\n"
                      "print(json.dumps({'business_outcomes_verified':False}))\n")
    python.chmod(0o700)

    completed = subprocess.run(["bash", str(wrapper)], capture_output=True, text=True, timeout=10)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["business_outcomes_verified"] is False


@pytest.fixture
def installation(tmp_path, isolated_home, monkeypatch):
    from runtime.host import local_profile
    from runtime.loop import local_install

    home = isolated_home
    inputs = tmp_path / "another-user/materials"
    candidate = _write(inputs / "candidate.json", {
        "version": 1, "candidate": {"name": "PRIVATE-CANDIDATE"},
        "facts": [{"id": "design", "claim": "PRIVATE-CLAIM", "evidence": "PRIVATE-EVIDENCE"}],
    })
    provider = _write(inputs / "provider.json", {
        "version": 1, "provider_employee_id": "5432107", "display_name": "本人PRIVATE",
        "occupation": "デザイナー", "occupation_detail": {"id": "14", "label": "グラフィックデザイナー"},
        "status": "available", "hours_limit": "11-20", "min_hourly_wage": 2000, "max_hourly_wage": 4000,
        "web_meeting": "available", "simple_introduction": "PRIVATE-SUMMARY", "introduction": "PRIVATE-INTRO",
        "job_categories": ["ロゴ作成"],
        "skills": [{"name": "Illustrator", "level": "3", "years": 3, "note": "PRIVATE-WORK"}],
    })
    codex = home / "selected-tools/codex"
    codex.parent.mkdir()
    codex.write_text("#!/bin/sh\nexit 92\n")
    codex.chmod(0o700)
    profile = local_profile.prepare_host(ROOT, home=home, python=Path(sys.executable),
                                         node=Path(sys.executable), codex=codex)
    Path(profile["environment_file"]).write_text("TELEGRAM_BOT_TOKEN=PRIVATE-TOKEN\n")
    _write(home / ".config/anicca/crowdworks/unused.json", {})
    (home / ".config/anicca/crowdworks/telegram.env").write_text("CROWDWORKS_REPORT_CHAT=PRIVATE-CHAT\n")
    release = tmp_path / "accepted-immutable"
    (release / "bin").mkdir(parents=True)
    (release / "bin/lm-loop").write_text("#!/bin/sh\nexit 93\n")
    _write(release / "RELEASE.json", {
        "sha": "a" * 40, "provenance": "ancestor-of-origin-main", "release_paths": "ALL",
        "runtime_python": sys.executable,
    })
    case = SimpleNamespace(home=home, candidate=candidate, provider=provider, release=release, profile=profile,
        private_candidate=home / ".config/anicca/job-search/profile.json",
        private_provider=home / ".config/anicca/crowdworks/public-profile.json",
        state=home / ".local/state/anicca/crowdworks", events=[], applied=[], fail_owner=None,
        skip_browser=None, codex_authenticated=True, codex_error=False,
        observation={"account_observed": True, "account_matches": True, "avatar_present": True})
    validate = local_install.validate_release

    def cut(repo, environment):
        assert Path(repo) == ROOT and environment["AI_BROWSER_REGISTRY"] == profile["browser_registry"]
        case.events.append("release")
        return release

    def validate_immutable(path, host):
        assert path == release and host == profile
        case.events.append("validate-release")
        return validate(path, host)

    def apply(path, owners, environment):
        assert path == release and len(owners) == 1 and set(owners) <= JOBS
        assert environment["LIFE_MANAGER_RUNTIME_PYTHON"] == sys.executable
        owner = owners[0]
        case.events.append("apply:" + owner)
        if owner == case.fail_owner:
            raise RuntimeError("PRIVATE-APPLY-FAILURE")
        case.applied.append(owner)
        row = {"ok": True, "loop_id": owner, "changed": False, "readback": "exact_release_loaded"}
        if owner == PREFIX + "browser" and case.skip_browser:
            row["skipped"] = case.skip_browser
        return [row]

    def run(command, **options):
        command = [str(part) for part in command]
        if command[0] == str(codex):
            if case.codex_error:
                raise OSError("PRIVATE-CODEX-EXECUTABLE-ERROR")
            assert command[1:] in (["login", "status"], ["login"])
            config = json.loads(Path(profile["agent_runner_config"]).read_text())["providers"]["codex"]
            selected = config["profiles"][config["account_profile_order"][0]]
            assert options["env"]["CODEX_HOME"] == str(Path(selected["auth_file"]).parent)
            case.events.append("codex:" + " ".join(command[1:]))
            return subprocess.CompletedProcess(command, 0 if case.codex_authenticated else 1,
                                               "PRIVATE-AUTH", "PRIVATE-AUTH")
        assert command == [str(release / "skills/browser/with-browser.sh"), "crowdworks:dais", "--",
                           sys.executable, str(release / "skills/earn/crowdworks/scripts/install_local.py"), "observe"]
        env = options["env"]
        assert env["AI_BROWSER_REGISTRY"] == profile["browser_registry"]
        assert env["AI_BROWSER_GUARD"] == str(release / "skills/browser/browser-guard.sh")
        assert env["LIFE_MANAGER_BROWSER_IDENTITY"] == "crowdworks:dais"
        assert env["LIFE_MANAGER_BROWSER_TARGET_OWNER"] == PREFIX + "browser"
        assert env["AI_ENSURE_PROVISION_BROWSER"] == env["AI_ENSURE_BROWSER"] == "/dev/null"
        assert env["CLOAK_BROWSER_LAUNCHD_LABEL"] == ""
        assert PREFIX + "browser" in case.applied
        case.events.append("observe")
        return subprocess.CompletedProcess(command, 0, json.dumps(case.observation), "PRIVATE-OBSERVATION")

    monkeypatch.setattr(local_install, "prepare_host", _forbidden)
    monkeypatch.setattr(local_install, "cut_release", cut)
    monkeypatch.setattr(local_install, "validate_release", validate_immutable)
    monkeypatch.setattr(local_install, "apply_targets", apply)
    monkeypatch.setattr(subprocess, "run", run)
    return case


def _call(case, capsys, *args):
    code = _installer().main(list(args))
    output = capsys.readouterr()
    assert not any(value in output.out + output.err for value in (
        "PRIVATE", "5432107", str(case.candidate), str(case.provider)))
    result = json.loads(output.out)
    assert result["business_outcomes_verified"] is False
    return code, result, _rows(result)


def _inputs(case):
    return ["--candidate-profile", str(case.candidate), "--provider-profile", str(case.provider)]


def test_plan_with_inputs_never_imports_or_observes(installation, capsys):
    case = installation
    before = _tree(case.home)
    code, result, rows = _call(case, capsys, "plan", *_inputs(case))
    assert code == 0 and result["status"] == "plan"
    assert case.events == case.applied == [] and _tree(case.home) == before
    assert "account_observation" in rows[PREFIX + "reply"]["missing"]


def test_import_replay_keeps_owner_values_private_and_applies_only_existing_owners(installation, capsys):
    case = installation
    source = _tree(case.provider.parent)
    code, result, rows = _call(case, capsys, "install", *_inputs(case))
    assert code == 0 and result["status"] == "installed"
    assert all(row["state"] == "installed" for row in rows.values())
    assert set(case.applied) == JOBS
    assert json.loads(case.private_candidate.read_text()) == json.loads(case.candidate.read_text())
    assert json.loads(case.private_provider.read_text()) == json.loads(case.provider.read_text())
    for path in (case.private_candidate, case.private_provider):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert _tree(case.provider.parent) == source
    saved = (case.private_candidate.read_bytes(), case.private_provider.read_bytes())
    _call(case, capsys, "install", *_inputs(case))
    assert saved == (case.private_candidate.read_bytes(), case.private_provider.read_bytes())
    assert case.events.index("validate-release") < case.events.index("apply:" + PREFIX + "browser") < case.events.index("observe")
    assert all(case.events.index("observe") < case.events.index("apply:" + PREFIX + name)
               for name in ("application", "reply", "paid", "report"))


def test_relative_avatar_is_kept_relative_to_its_source_directory(installation, capsys):
    case = installation
    avatar = case.provider.parent / "owner.png"
    avatar.write_bytes(b"owner-image-fixture")
    value = json.loads(case.provider.read_text()) | {"avatar_path": "owner.png"}
    _write(case.provider, value)
    case.observation["avatar_present"] = False
    _call(case, capsys, "install", *_inputs(case))
    assert json.loads(case.private_provider.read_text())["avatar_path"] == str(avatar.resolve())
    assert PREFIX + "application" in case.applied
    assert json.loads(case.provider.read_text())["avatar_path"] == "owner.png"


@pytest.mark.parametrize("missing", ["occupation", "skill_years"])
def test_application_requirements_do_not_block_reply_paid_or_report(installation, capsys, missing):
    case = installation
    value = json.loads(case.provider.read_text())
    if missing == "occupation":
        del value["occupation_detail"]
        key = "provider_profile.occupation_detail"
    else:
        value["skills"][0]["years"] = 4
        key = "provider_profile.skills"
    _write(case.provider, value)
    _code, _result, rows = _call(case, capsys, "install", *_inputs(case))
    assert PREFIX + "application" not in case.applied
    assert key in rows[PREFIX + "application"]["missing"]
    assert {PREFIX + name for name in ("browser", "reply", "paid", "report")} == set(case.applied)


@pytest.mark.parametrize("observation,key", [
    ({"account_observed": True, "account_matches": False, "avatar_present": True}, "provider_account_binding"),
    ({"account_observed": False, "account_matches": False, "avatar_present": None}, "account_observation"),
    ({"authenticated": True, "account_id": "5432107"}, "account_observation"),
])
def test_unobserved_or_wrong_session_never_admits_business_owners(installation, capsys, observation, key):
    case = installation
    case.observation = observation
    _code, _result, rows = _call(case, capsys, "install", *_inputs(case))
    assert set(case.applied) == {PREFIX + "browser", PREFIX + "report"}
    for name in ("application", "reply", "paid"):
        assert key in rows[PREFIX + name]["missing"]


@pytest.mark.parametrize("avatar,applies,key", [(False, False, "provider_profile.avatar_path"),
                                               (None, False, "profile_observation"), (True, True, None)])
def test_public_avatar_removes_only_the_local_image_requirement(installation, capsys, avatar, applies, key):
    case = installation
    case.observation["avatar_present"] = avatar
    _code, _result, rows = _call(case, capsys, "install", *_inputs(case))
    assert (PREFIX + "application" in case.applied) is applies
    if key:
        assert key in rows[PREFIX + "application"]["missing"]
    assert {PREFIX + "reply", PREFIX + "paid", PREFIX + "report"} <= set(case.applied)


def test_only_report_is_held_for_missing_notification(installation, capsys):
    case = installation
    (case.home / ".config/anicca/crowdworks/telegram.env").unlink()
    Path(case.profile["environment_file"]).write_text("")
    _code, _result, rows = _call(case, capsys, "install", *_inputs(case))
    assert set(case.applied) == JOBS - {PREFIX + "report"}
    assert rows[PREFIX + "report"]["missing"] == ["telegram_notification"]


@pytest.mark.parametrize("kind", ["candidate", "provider"])
@pytest.mark.parametrize("failure", ["conflict", "malformed", "symlink"])
def test_existing_private_input_is_never_overwritten(installation, capsys, kind, failure):
    case = installation
    source = getattr(case, kind)
    destination = getattr(case, "private_" + kind)
    value = json.loads(source.read_text())
    if failure == "conflict":
        if kind == "candidate":
            value["facts"][0]["claim"] = "PRIVATE-OTHER-OWNER"
        else:
            value["provider_employee_id"] = "7777777"
        _write(destination, value)
    elif failure == "malformed":
        _write(destination, value)
        destination.write_text('{"PRIVATE-BROKEN":')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(source)
    before = destination.read_bytes()
    _code, _result, rows = _call(case, capsys, "install", *_inputs(case))
    assert destination.read_bytes() == before
    assert destination.is_symlink() is (failure == "symlink")
    assert set(case.applied) == {PREFIX + "browser", PREFIX + "report"}
    assert rows[PREFIX + "reply"]["missing"]


@pytest.mark.parametrize("kind", ["candidate", "provider"])
@pytest.mark.parametrize("first", ["identical", "conflict", "malformed", "symlink"])
def test_concurrent_first_import_preserves_the_first_published_private_input(installation, monkeypatch, capsys, kind, first):
    case = installation
    installer = _installer()
    source = getattr(case, kind)
    destination = getattr(case, "private_" + kind)
    incumbent = json.loads(source.read_text())
    if first == "conflict":
        if kind == "candidate":
            incumbent["facts"][0]["claim"] = "PRIVATE-FIRST-OWNER"
        else:
            incumbent["provider_employee_id"] = "7777777"
    write_private = installer.onboarding._write_private
    first_state = {}

    def publish_first(path, value):
        assert not first_state, "only the requested import may invoke this writer"
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if first == "symlink":
            destination.symlink_to(source)
        else:
            write_private(destination, incumbent)
            if first == "malformed":
                destination.write_text('{"PRIVATE-BROKEN":')
        first_state.update(content=destination.read_bytes(), inode=destination.lstat().st_ino)
        write_private(path, value)

    monkeypatch.setattr(installer.onboarding, "_write_private", publish_first)
    value, missing = installer._import_input(kind + "_profile", source, destination, write=True)

    expected = [] if first == "identical" else [kind + "_profile" + ("_conflict" if first == "conflict" else "")]
    assert missing == expected
    assert (value is not None) is (first == "identical")
    assert destination.read_bytes() == first_state["content"]
    assert destination.lstat().st_ino == first_state["inode"]
    assert destination.is_symlink() is (first == "symlink")
    assert not list(destination.parent.glob("." + destination.name + ".*"))
    if first != "symlink":
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600
        assert stat.S_IMODE(destination.parent.stat().st_mode) == 0o700
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("kind", ["candidate", "provider"])
def test_malformed_explicit_input_does_not_copy_author_defaults(installation, capsys, kind):
    case = installation
    getattr(case, kind).write_text("[]")
    _call(case, capsys, "install", *_inputs(case))
    assert not getattr(case, "private_" + kind).exists()
    assert set(case.applied) == {PREFIX + "browser", PREFIX + "report"}


def test_running_browser_is_still_observed_and_preserved(installation, capsys):
    case = installation
    case.skip_browser = "loaded-running"
    code, result, rows = _call(case, capsys, "install", *_inputs(case))
    assert "observe" in case.events and set(case.applied) == JOBS
    assert code == 78 and result["status"] == "waiting"
    assert rows[PREFIX + "browser"]["state"] == "waiting"


def test_later_owner_failure_keeps_confirmed_results_and_independent_apply(installation, capsys):
    case = installation
    case.fail_owner = PREFIX + "reply"
    _code, _result, rows = _call(case, capsys, "install", *_inputs(case))
    assert rows[PREFIX + "application"]["state"] == "installed"
    assert rows[PREFIX + "reply"]["state"] == "setup_required"
    assert rows[PREFIX + "paid"]["state"] == rows[PREFIX + "report"]["state"] == "installed"
    assert set(case.applied) == JOBS - {PREFIX + "reply"}


def test_missing_inputs_admit_browser_and_report_only(installation, capsys):
    case = installation
    _call(case, capsys, "install")
    assert set(case.applied) == {PREFIX + "browser", PREFIX + "report"}
    assert not case.private_candidate.exists() and not case.private_provider.exists()


@pytest.mark.parametrize("failure", ["logged_out", "missing_executable"])
def test_unconfirmed_codex_auth_keeps_report_independent(installation, capsys, failure):
    case = installation
    case.codex_authenticated = False
    case.codex_error = failure == "missing_executable"
    _code, _result, rows = _call(case, capsys, "install", *_inputs(case))
    assert [event for event in case.events if event.startswith("codex:")] == (
        [] if case.codex_error else ["codex:login status", "codex:login", "codex:login status"])
    assert set(case.applied) == {PREFIX + "browser", PREFIX + "report"}
    assert rows[PREFIX + "paid"]["missing"] == ["codex_login"]


@pytest.mark.parametrize("kind", ["candidate", "provider"])
def test_explicit_symlink_input_is_not_imported(installation, capsys, kind):
    case = installation
    source = getattr(case, kind)
    link = source.with_name("linked-" + source.name)
    link.symlink_to(source)
    setattr(case, kind, link)
    before = source.read_bytes()
    _call(case, capsys, "install", *_inputs(case))
    assert source.read_bytes() == before
    assert not getattr(case, "private_" + kind).exists()
    assert set(case.applied) == {PREFIX + "browser", PREFIX + "report"}


def test_state_write_failure_holds_state_consumers_only(installation, monkeypatch, capsys):
    case = installation
    installer = _installer()

    def full_disk(**_kwargs):
        raise OSError("PRIVATE-DISK-DETAIL")

    monkeypatch.setattr(installer.tempfile, "TemporaryFile", full_disk)
    _code, _result, rows = _call(case, capsys, "install", *_inputs(case))
    assert case.applied == [PREFIX + "browser"]
    assert all("crowdworks_state" in rows[PREFIX + name]["missing"]
               for name in ("application", "reply", "paid", "report"))


@pytest.mark.parametrize("official_employee,matches", [("543210", False), ("5432107", True)])
def test_immutable_observation_uses_lease_and_connection_only(installation, monkeypatch, official_employee, matches):
    from skills.earn.crowdworks.tests.test_account_identity import Page, dashboard

    case = installation
    _write(case.private_candidate, json.loads(case.candidate.read_text()))
    avatar = case.provider.parent / "owner.png"
    avatar.write_bytes(b"owner-image-fixture")
    _write(case.private_provider, json.loads(case.provider.read_text()) | {"avatar_path": str(avatar)})
    installer = _installer()
    account = installer.crowdworks_profile._account_module()
    page = Page(dashboard(employee=official_employee))
    factory_calls = []

    def connect(endpoint):
        factory_calls.append(endpoint)
        return SimpleNamespace(contexts=[SimpleNamespace(new_page=lambda: page)])

    for name in ("_owner", "_reap", "_unlock", "_restore", "_dump", "_credentials", "_notify"):
        monkeypatch.setattr(account, name, _forbidden)
    monkeypatch.setattr(account, "_browser", connect)
    monkeypatch.setattr(installer.crowdworks_profile, "_account_module", lambda: account)
    monkeypatch.setattr(installer.crowdworks_profile, "run_apply", _forbidden)
    monkeypatch.setattr(installer.crowdworks_profile, "run_observe", _forbidden)
    endpoint = "http://127.0.0.1:9228"
    pid, token, uuid = os.getpid(), "fixture-holder-token", "fixture-browser-uuid"
    for key, value in {"LIFE_MANAGER_BROWSER_LEASE_IDENTITY": "crowdworks:dais",
        "LIFE_MANAGER_BROWSER_IDENTITY": "crowdworks:dais",
        "LIFE_MANAGER_BROWSER_TARGET_OWNER": PREFIX + "browser", "LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID": str(pid),
        "AI_BROWSER_HOLDER_START": token, "CDP": endpoint, "CLOAK_CDP_BASE_URL": endpoint,
        "LIFE_MANAGER_BROWSER_GUARD": str(ROOT / "skills/browser/browser-guard.sh")}.items():
        monkeypatch.setenv(key, value)
    holder = {"identity": "crowdworks:dais", "pid": pid, "holder_start": token,
              "host": socket.gethostname().split(".")[0], "port": 9228, "uuid": uuid}

    def guard(command, **options):
        assert command == [str(ROOT / "skills/browser/browser-guard.sh"), "status"]
        return subprocess.CompletedProcess(command, 0, json.dumps({"identities": [{
            "identity": "crowdworks:dais", "reachable": True, "endpoint": endpoint, "port": 9228,
            "uuid": uuid, "holder": json.dumps(holder)}]}), "")

    monkeypatch.setattr(subprocess, "run", guard)
    result = installer._observe_owned()
    assert result["account_observed"] is True
    assert result["account_matches"] is matches
    assert len(factory_calls) == 1 and page.closed is True
    assert "5432107" not in json.dumps(result)
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_LEASE_IDENTITY", "other:owner")
    assert installer._observe_owned()["account_observed"] is False
    assert len(factory_calls) == 1
