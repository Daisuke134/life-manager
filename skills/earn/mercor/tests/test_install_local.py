"""Synthetic owner setup never borrows the developer's accounts or live runtime."""
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
SCRIPT = ROOT / "skills/earn/mercor/scripts/install_local.py"
WRAPPER = ROOT / "skills/earn/mercor/install.sh"
JOBS = {"mercor-revenue-application", "mercor-revenue-reply", "mercor-revenue-paid"}


def _forbidden(*_args, **_kwargs):
    pytest.fail("real browser, provider, login, or host effects are forbidden")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "different-owner-home"
    home.mkdir(mode=0o700)
    for key in tuple(os.environ):
        if (key.startswith(("TELEGRAM_", "MERCOR_", "JOB_SEARCH_", "XDG_", "LIFE_MANAGER_BROWSER_"))
                or key in {"CDP", "CDP_PORT", "CLOAK_CDP_BASE_URL", "AGENT_RUNNER_CONFIG",
                           "LIFE_MANAGER_HOST_PROFILE", "LIFE_MANAGER_ENV_FILE", "CODEX_HOME",
                           "AI_BROWSER_HOLDER_START", "GIG_REPORT_CHAT"}):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LIFE_MANAGER_STATE_ROOT", str(tmp_path / "isolated-state"))
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(tmp_path / "isolated-admission"))
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
    assert SCRIPT.is_file(), "guided Mercor installer is missing"
    spec = importlib.util.spec_from_file_location("mercor_guided_installer_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rows(result):
    rows = {row["loop_id"]: row for row in result["jobs"]}
    assert set(rows) == JOBS
    assert all(isinstance(row["missing"], list) and row["next_action"] for row in rows.values())
    return rows


def test_empty_home_plan_has_no_writes_or_subprocesses(isolated_home, monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", _forbidden)
    before = _tree(isolated_home)
    assert _installer().main(["plan"]) == 0
    result = json.loads(capsys.readouterr().out)
    rows = _rows(result)
    assert result["status"] == "plan" and result["business_outcomes_verified"] is False
    assert _tree(isolated_home) == before
    assert all("host_profile" in row["missing"] for row in rows.values())
    assert "candidate_profile" in rows["mercor-revenue-application"]["missing"]
    assert "paid_account_binding" in rows["mercor-revenue-paid"]["missing"]


def test_root_dispatches_mercor_plan_without_preparing_the_host(tmp_path, isolated_home):
    repository = tmp_path / "wrapper-repository"
    repository.mkdir()
    shutil.copyfile(ROOT / "install.sh", repository / "install.sh")
    wrapper = repository / "skills/earn/mercor/install.sh"
    wrapper.parent.mkdir(parents=True)
    assert WRAPPER.is_file(), "guided Mercor shell wrapper is missing"
    shutil.copyfile(WRAPPER, wrapper)
    python = isolated_home / ".local/share/life-manager/venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text(f"#!{sys.executable}\nimport json,sys\n"
                      "assert sys.argv[2:] == ['plan','--profile','fixture.json']\n"
                      "print(json.dumps({'status':'plan'}))\n")
    python.chmod(0o700)
    before = _tree(isolated_home)
    result = subprocess.run(["bash", str(repository / "install.sh"), "mercor", "plan", "--profile", "fixture.json"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "plan"
    assert _tree(isolated_home) == before


@pytest.fixture
def installation(tmp_path, isolated_home, monkeypatch):
    from runtime.host import local_profile
    from runtime.loop import local_install

    home = isolated_home
    resume = tmp_path / "different-owner/materials/own-resume.pdf"
    resume.parent.mkdir(parents=True)
    resume.write_bytes(b"%PDF-1.7\nSYNTHETIC-PRIVATE-RESUME\n")
    source = _write(resume.parent / "profile.json", {
        "version": 1, "candidate": {"name": "PRIVATE-OWNER", "application_email": "another-owner@fixture.invalid",
            "target_role_families": ["Software engineering"], "location_preferences": ["Remote"],
            "compensation_floor_jpy": 7000000, "compensation_target_jpy": 9000000},
        "materials": {"resumes": {"engineering": str(resume)}},
        "facts": [{"id": "one", "claim": "PRIVATE-CLAIM", "evidence": "PRIVATE-EVIDENCE"}],
    })
    codex = home / "selected-tools/codex"
    codex.parent.mkdir()
    codex.write_text("#!/bin/sh\nexit 92\n")
    codex.chmod(0o700)
    auth = _write(home / ".codex/auth.json", {"synthetic": "PRIVATE-AUTH"})
    profile = local_profile.prepare_host(ROOT, home=home, python=Path(sys.executable),
                                         node=Path(sys.executable), codex=codex)
    release = tmp_path / "accepted-immutable"
    (release / "bin").mkdir(parents=True)
    (release / "bin/lm-loop").write_text("#!/bin/sh\nexit 93\n")
    _write(release / "RELEASE.json", {"sha": "a" * 40, "provenance": "ancestor-of-origin-main",
        "release_paths": "ALL", "runtime_python": sys.executable})
    telegram = home / ".config/anicca/job-search/telegram.env"
    telegram.parent.mkdir(parents=True, exist_ok=True)
    telegram.write_text("TELEGRAM_BOT_TOKEN=PRIVATE-TOKEN\nJOB_SEARCH_TELEGRAM_CHAT_ID=123456\n")
    telegram.chmod(0o600)
    gog = home / "selected-tools/gog"
    gog.write_text("#!/bin/sh\nexit 94\n")
    gog.chmod(0o700)
    monkeypatch.setenv("PATH", str(codex.parent) + os.pathsep + os.environ["PATH"])
    case = SimpleNamespace(home=home, source=source, resume=resume, codex=codex, auth=auth, gog=gog,
        spawn=subprocess.run,
        host=profile, release=release, telegram=telegram, events=[], applied=[], browser_skip=None,
        codex_ok=True, gmail_accounts=[{"email": "another-owner@fixture.invalid", "services": ["gmail"]}],
        observation={"status": "authenticated", "firebase_identity_matched": True},
        private=home / ".config/anicca/job-search/profile.json",
        state=home / ".local/state/anicca/job-search/mercor/application/resume-state.json")

    def cut(repo, environment):
        assert Path(repo) == ROOT
        case.events.append("release")
        return release

    def host_apply(path, owners, environment):
        assert path == release and owners == [local_install.MERCOR_BROWSER]
        case.events.append("browser")
        return [{"ok": True, "label": local_install.MERCOR_BROWSER["label"], "changed": False,
                 **({"skipped": case.browser_skip} if case.browser_skip else {"readback": "exact_release_loaded"})}]

    def apply(path, owners, environment):
        assert path == release and len(owners) == 1 and set(owners) <= JOBS
        case.applied += owners
        case.events += ["apply:" + owner for owner in owners]
        return [{"ok": True, "loop_id": owners[0], "changed": False, "readback": "exact_release_loaded"}]

    def run(command, **options):
        command = [str(part) for part in command]
        if command[0] == str(codex):
            assert command[1:] in (["login", "status"], ["login"])
            case.events.append("codex:" + " ".join(command[1:]))
            return subprocess.CompletedProcess(command, 0 if case.codex_ok else 1, "PRIVATE-AUTH", "")
        if command[0] == str(gog):
            assert command[1:] == ["auth", "list", "--json", "--no-input"]
            case.events.append("gmail")
            return subprocess.CompletedProcess(command, 0, json.dumps({"accounts": case.gmail_accounts}), "")
        assert command == [str(release / "skills/browser/with-browser.sh"), "mercor:dais", "--",
                           sys.executable, str(release / "skills/earn/mercor/scripts/install_local.py"), "observe"]
        assert "browser" in case.events
        env = options["env"]
        assert env["AI_ENSURE_BROWSER"] == env["AI_ENSURE_PROVISION_BROWSER"] == "/dev/null"
        assert env["AI_BROWSER_REGISTRY"] == profile["browser_registry"]
        case.events.append("observe")
        return subprocess.CompletedProcess(command, 0, json.dumps(case.observation), "PRIVATE-OBSERVATION")

    monkeypatch.setattr(local_install, "cut_release", cut)
    monkeypatch.setattr(local_install, "apply_host_owners", host_apply)
    monkeypatch.setattr(local_install, "apply_targets", apply)
    monkeypatch.setattr(subprocess, "run", run)
    return case


def _call(case, capsys, *arguments):
    code = _installer().main(list(arguments))
    output = capsys.readouterr()
    assert not any(value in output.out + output.err for value in (
        "PRIVATE", "another-owner@fixture.invalid", str(case.source), str(case.resume), "123456"))
    result = json.loads(output.out)
    assert result["business_outcomes_verified"] is False
    return code, result, _rows(result)


def test_profile_plan_does_not_import_or_check_live_accounts(installation, capsys):
    case = installation
    before = _tree(case.home)
    code, _result, rows = _call(case, capsys, "plan", "--profile", str(case.source))
    assert code == 0 and not case.events and _tree(case.home) == before
    assert "account_observation" in rows["mercor-revenue-application"]["missing"]


def test_real_profile_install_connects_the_runtime_resume_and_preserves_replay(installation, capsys):
    case = installation
    source = _tree(case.source.parent)
    code, result, rows = _call(case, capsys, "install", "--profile", str(case.source))
    assert code == 78 and result["status"] == "waiting"
    assert set(case.applied) == {"mercor-revenue-application", "mercor-revenue-reply"}
    assert rows["mercor-revenue-paid"]["missing"] == ["paid_account_binding"]
    selected = json.loads(case.state.read_text())["resume_file"]
    assert selected == str(case.home / ".local/share/anicca/job-search/materials/resumes/engineering.pdf")
    assert Path(selected).read_bytes() == case.resume.read_bytes()
    assert stat.S_IMODE(case.private.stat().st_mode) == stat.S_IMODE(case.state.stat().st_mode) == 0o600
    assert _tree(case.source.parent) == source
    fences = _write(case.state.parent / "unknown-effect.json", {"effect": "unknown", "receipt": None})
    before = (case.private.read_bytes(), case.state.read_bytes(), fences.read_bytes())
    _call(case, capsys, "install", "--profile", str(case.source))
    assert before == (case.private.read_bytes(), case.state.read_bytes(), fences.read_bytes())
    assert case.events.index("observe") < case.events.index("apply:mercor-revenue-application")


@pytest.mark.parametrize("kind", ["placeholder", "missing_fact", "conflict", "malformed", "symlink"])
def test_invalid_or_conflicting_profile_is_preserved_and_never_activated(installation, capsys, kind):
    case = installation
    value = json.loads(case.source.read_text())
    if kind == "placeholder":
        value["candidate"]["name"] = "REPLACE_ME"
        _write(case.source, value)
    elif kind == "missing_fact":
        value["facts"] = []
        _write(case.source, value)
    elif kind == "conflict":
        value["candidate"]["application_email"] = "incumbent@fixture.invalid"
        _write(case.private, value)
    elif kind == "malformed":
        _write(case.private, value).write_text('{"PRIVATE-BROKEN":')
    else:
        case.private.symlink_to(case.source)
    before = case.private.read_bytes() if case.private.exists() else None
    _code, _result, rows = _call(case, capsys, "install", "--profile", str(case.source))
    assert not case.applied and rows["mercor-revenue-application"]["missing"]
    assert (case.private.read_bytes() if case.private.exists() else None) == before


@pytest.mark.parametrize("kind", ["resume", "malformed", "unknown"])
def test_existing_resume_state_conflict_is_not_overwritten(installation, capsys, kind):
    case = installation
    expected = str(case.home / ".local/share/anicca/job-search/materials/resumes/engineering.pdf")
    _write(case.state, {"resume_file": "PRIVATE-FOREIGN-RESUME"} if kind == "resume" else {"unrecognized": True})
    if kind == "malformed":
        case.state.write_text('{"PRIVATE-BROKEN":')
    before = case.state.read_bytes()
    _code, _result, rows = _call(case, capsys, "install", "--profile", str(case.source))
    assert case.state.read_bytes() == before
    assert "mercor-revenue-application" not in case.applied
    assert "resume_state_conflict" in rows["mercor-revenue-application"]["missing"]


def test_missing_telegram_holds_only_reply(installation, capsys):
    case = installation
    case.telegram.unlink()
    _code, _result, rows = _call(case, capsys, "install", "--profile", str(case.source))
    assert set(case.applied) == {"mercor-revenue-application"}
    assert rows["mercor-revenue-reply"]["missing"] == ["telegram_notification"]


@pytest.mark.parametrize("assignment", ['JOB_SEARCH_TELEGRAM_CHAT_ID="123456"', "export JOB_SEARCH_TELEGRAM_CHAT_ID='123456'"])
def test_telegram_quotes_and_export_match_the_runtime_parser(installation, capsys, assignment):
    case = installation
    case.telegram.write_text("TELEGRAM_BOT_TOKEN=PRIVATE-TOKEN\n" + assignment + "\n")
    _call(case, capsys, "install", "--profile", str(case.source))
    assert "mercor-revenue-reply" in case.applied


def test_missing_resume_holds_application_without_blocking_ready_reply(installation, capsys):
    case = installation
    case.resume.unlink()
    _code, _result, rows = _call(case, capsys, "install", "--profile", str(case.source))
    assert set(case.applied) == {"mercor-revenue-reply"}
    assert rows["mercor-revenue-application"]["state"] == "setup_required"


def test_other_gmail_account_is_not_accepted_for_reply_or_recovery(installation, capsys):
    case = installation
    case.gmail_accounts = [{"email": "foreign@fixture.invalid", "services": ["gmail"]}]
    _code, _result, rows = _call(case, capsys, "install", "--profile", str(case.source))
    assert not case.applied
    assert "gmail_authorization" in rows["mercor-revenue-application"]["missing"]
    assert "gmail_authorization" in rows["mercor-revenue-reply"]["missing"]


@pytest.mark.parametrize("observation", [{"status": "authenticated", "firebase_identity_matched": False},
                                       {"status": "authenticated"}, {"status": "logged_out"}])
def test_unbound_session_never_activates_owners(installation, capsys, observation):
    case = installation
    case.observation = observation
    _code, _result, rows = _call(case, capsys, "install", "--profile", str(case.source))
    assert not case.applied
    assert all("account_observation" in row["missing"] for row in rows.values())


def test_existing_running_browser_is_preserved_while_ready_owners_are_applied(installation, capsys):
    case = installation
    case.browser_skip = "existing_owner"
    _call(case, capsys, "install", "--profile", str(case.source))
    assert "observe" in case.events
    assert set(case.applied) == {"mercor-revenue-application", "mercor-revenue-reply"}


def test_paid_default_operator_never_counts_as_persistent_account_binding(installation, monkeypatch, capsys):
    case = installation
    monkeypatch.setenv("MERCOR_OPERATOR_ID", "default")
    _code, _result, rows = _call(case, capsys, "install", "--profile", str(case.source))
    assert rows["mercor-revenue-paid"]["state"] == "setup_required"
    assert "paid_account_binding" in rows["mercor-revenue-paid"]["missing"]


@pytest.mark.parametrize("kind", ["auth_alias", "material", "manifest", "receipt"])
def test_existing_unknown_material_or_auth_binding_is_never_replaced(installation, capsys, kind):
    case = installation
    config = case.private.parent
    data = case.home / ".local/share/anicca/job-search/materials"
    if kind == "auth_alias":
        target = _write(case.home / "foreign-auth.json", {"foreign": "PRIVATE-FOREIGN-AUTH"})
        path = config / "codex-auth.json"
        path.symlink_to(target)
    elif kind == "material":
        path = data / "resumes/engineering.pdf"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"PRIVATE-FOREIGN-RESUME")
    else:
        path = data / "manifest.v1.json" if kind == "manifest" else config / "install.json"
        _write(path, {"unrecognized": "PRIVATE-STATE"})
    before = _tree(case.home)
    _code, _result, rows = _call(case, capsys, "install", "--profile", str(case.source))
    assert _tree(case.home) == before
    assert not case.applied
    assert rows["mercor-revenue-application"]["missing"]


def test_runtime_caller_reads_the_installed_resume_state(installation, tmp_path, capsys):
    case = installation
    _call(case, capsys, "install", "--profile", str(case.source))
    app = tmp_path / "caller-repository/apps/job-search-loop"
    scripts = app / "scripts"
    scripts.mkdir(parents=True)
    for name in ("run-mercor.sh", "runtime-paths.sh"):
        shutil.copyfile(ROOT / "apps/job-search-loop/scripts" / name, scripts / name)
    (scripts / "retain-evidence.sh").write_text("#!/bin/sh\nexit 0\n")
    (scripts / "retain-evidence.sh").chmod(0o700)
    for directory, name in (("prompts", "mercor-pass.md"), ("schemas", "mercor-pass-result.v1.schema.json")):
        (app / directory).mkdir()
        (app / directory / name).write_text("{}")
    observed = tmp_path / "runtime-resume-reference.json"
    python = tmp_path / "synthetic-runtime-python"
    python.write_text(f"#!{sys.executable}\nimport json,pathlib,sys\n"
        "if 'job_search_loop.mercor_pass' in sys.argv:\n"
        f" pathlib.Path({str(observed)!r}).write_text(json.dumps(sys.argv[sys.argv.index('--resume')+1]))\n"
        " sys.exit(69)\n")
    python.chmod(0o700)
    jq = tmp_path / "synthetic-jq"
    jq.write_text(f"#!{sys.executable}\nimport json,sys\nprint(json.load(open(sys.argv[-1]))['resume_file'])\n")
    jq.chmod(0o700)
    completed = case.spawn(["zsh", str(scripts / "run-mercor.sh")], capture_output=True, text=True, timeout=10,
        env={**os.environ, "JOB_SEARCH_PYTHON": str(python), "JOB_SEARCH_JQ": str(jq),
             "JOB_SEARCH_STATE_ROOT": str(case.home / ".local/state/anicca/job-search"),
             "MERCOR_APPLICATION_STATE_ROOT": str(case.state.parent)})
    assert completed.returncode == 69
    selected = Path(json.loads(observed.read_text()))
    assert selected == case.home / ".local/share/anicca/job-search/materials/resumes/engineering.pdf"
    assert selected.read_bytes() == case.resume.read_bytes()


@pytest.mark.parametrize("alias_for", ["input", "home"])
def test_standard_macos_parent_alias_preserves_the_same_owner(installation, monkeypatch, capsys, alias_for):
    case = installation
    if not Path("/tmp").is_symlink() or not case.home.is_relative_to("/private/tmp"):
        pytest.skip("macOS standard /tmp alias fixture")
    source = case.source
    if alias_for == "home":
        monkeypatch.setenv("HOME", str(Path("/") / case.home.relative_to("/private")))
    else:
        source = Path("/") / source.relative_to("/private")
    _call(case, capsys, "install", "--profile", str(source))
    assert set(case.applied) == {"mercor-revenue-application", "mercor-revenue-reply"}


def test_unknown_symlink_parent_is_still_rejected(installation, tmp_path, capsys):
    case = installation
    link = tmp_path / "linked-owner-input"
    link.symlink_to(case.source.parent)
    _code, _result, rows = _call(case, capsys, "install", "--profile", str(link / case.source.name))
    assert not case.applied and rows["mercor-revenue-application"]["missing"]
    assert not case.private.exists()


@pytest.mark.parametrize("failure", [None, "busy", "observation", "park", "missing_resume"])
def test_owned_observation_preserves_the_exact_lease_and_session_binding(installation, monkeypatch, capsys, failure):
    case = installation
    _call(case, capsys, "install", "--profile", str(case.source))
    if failure == "missing_resume":
        case.resume.unlink()
    installer = _installer()
    monkeypatch.setattr(installer, "_inherited_lease", lambda: True)
    commands = []

    def run(command, **options):
        commands.append(command)
        verb = command[2]
        if verb == "acquire":
            assert command[3:] == ["mercor-revenue-application", "https://work.mercor.com/explore"]
            return subprocess.CompletedProcess(command, 75 if failure == "busy" else 0, json.dumps({
                "ok": failure != "busy", "ws": "ws://localhost/fixture", "token": "own-fence", "generation": 2}), "")
        assert command[3] == "mercor-revenue-application"
        assert command[command.index("--token") + 1] == "own-fence"
        if verb == "park" and failure == "park":
            raise OSError("PRIVATE-PARK-FAILURE")
        return subprocess.CompletedProcess(command, 0, '{"ok":true}', "")

    async def prepare(ws):
        assert ws == "ws://localhost/fixture"

    async def observe(ws, *, expected_email):
        assert ws == "ws://localhost/fixture" and expected_email == "another-owner@fixture.invalid"
        if failure == "observation":
            raise RuntimeError("PRIVATE-OBSERVATION-FAILURE")
        return {"status": "authenticated", "firebase_identity_matched": True}

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(installer.mercor_page_ready, "prepare", prepare)
    monkeypatch.setattr(installer.mercor_auth_readback, "observe", observe)
    result = installer._observe_owned()
    assert result.get("status") == ("authenticated" if failure in {None, "missing_resume"} else None)
    verbs = [command[2] for command in commands]
    assert verbs == (["acquire"] if failure == "busy" else ["acquire", "park"] if failure == "observation"
                     else ["acquire", "commit-cookies", "park"])
    assert capsys.readouterr().out == ""
