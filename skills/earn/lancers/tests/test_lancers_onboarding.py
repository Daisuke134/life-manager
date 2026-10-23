"""Account setup uses isolated HOME, a fake guard, and owned fake-CDP targets."""
from __future__ import annotations

import importlib.util
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request

import pytest

from skills.earn.lancers.tests.identity_fixture import write_identity


ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "skills/earn/lancers/scripts/lancers_onboarding.py"
MYPAGE = "https://www.lancers.jp/mypage"
ENDPOINT = "http://127.0.0.1:19471"


def _load():
    assert SOURCE.is_file(), "Lancers account connection is not implemented"
    spec = importlib.util.spec_from_file_location("lancers_onboarding_tested", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for name in ("CDP", "CLOAK_CDP_BASE_URL", "LIFE_MANAGER_BROWSER_GUARD",
                 "LIFE_MANAGER_BROWSER_LEASE_IDENTITY", "LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID",
                 "AI_BROWSER_HOLDER_START", "CLOAK_BROWSER_CONTEXT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLOAK_TARGET_OWNERS_FILE", str(home / "targets.json"))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("real HTTP/browser access is forbidden")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    return home


def _snapshot(**updates):
    return {"url": MYPAGE, "ready": "complete", "login_form": False,
            "human_verification": False,
            "profile_links": ["https://www.lancers.jp/profile/other-seller"], **updates}


def _profile(home):
    return home / ".config/anicca/lancers/public-profile.json"


def _observation(home):
    return home / ".config/anicca/lancers/onboarding-observation.json"


def _lease(home, monkeypatch, *, row_updates=None, holder_updates=None, status_updates=None, other_rows=()):
    holder = {"identity": "lancers:dais", "pid": os.getpid(),
              "host": socket.gethostname().split(".")[0], "holder_start": "fixture-token",
              "port": 19471, "uuid": "fixture-browser-uuid", **(holder_updates or {})}
    row = {"identity": "lancers:dais", "reachable": True, "endpoint": ENDPOINT,
           "port": 19471, "uuid": "fixture-browser-uuid", "holder": json.dumps(holder),
           **(row_updates or {})}
    status = {"identities": [row, *other_rows], "collisions": {}, **(status_updates or {})}
    guard = home / "fake-guard"
    calls = home / "guard-calls.txt"
    guard.write_text(
        f"#!{sys.executable}\nimport pathlib, sys\n"
        "assert sys.argv[1:] == ['status'], 'only read-only status is allowed'\n"
        f"pathlib.Path({str(calls)!r}).write_text('status')\n"
        f"print({json.dumps(status)!r})\n", encoding="utf-8")
    guard.chmod(0o700)
    for name, value in {
        "CDP": ENDPOINT, "CLOAK_CDP_BASE_URL": ENDPOINT,
        "LIFE_MANAGER_BROWSER_GUARD": str(guard),
        "LIFE_MANAGER_BROWSER_LEASE_IDENTITY": "lancers:dais",
        "LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID": str(os.getpid()),
        "AI_BROWSER_HOLDER_START": "fixture-token",
    }.items():
        monkeypatch.setenv(name, value)
    return calls


def _browser(module, monkeypatch, *, snapshot=None, snapshots=None, failure=None):
    cdp = module._load_cdp()
    events = []
    samples = iter(snapshots) if snapshots is not None else None

    def call(method, params):
        if method == "Target.getTargets":
            return {"targetInfos": []}
        if method == "Target.createTarget":
            assert params == {"url": MYPAGE}
            events.append("open")
            if failure == "open":
                raise TimeoutError("PRIVATE-EXCEPTION")
            return {"targetId": "owned-fixture-tab"}
        assert method == "Target.closeTarget"
        assert params == {"targetId": "owned-fixture-tab"}
        events.append("close")
        if failure == "close":
            raise TimeoutError("PRIVATE-EXCEPTION")
        return {"success": True}

    def evaluate(target, _expression):
        assert target == "owned-fixture-tab"
        assert cdp.target_ownership.owns_target(target, "lancers-onboarding")
        events.append("evaluate")
        if failure == "evaluate":
            raise TimeoutError("PRIVATE-EXCEPTION")
        if samples is not None:
            return next(samples)
        return snapshot if snapshot is not None else _snapshot(body="PRIVATE-DOM", token="PRIVATE-TOKEN")

    monkeypatch.setattr(cdp, "_browser_call", call)
    monkeypatch.setattr(cdp, "evaluate", evaluate)
    monkeypatch.setattr(module, "_load_cdp", lambda: cdp)
    monkeypatch.setattr(module.time, "sleep", lambda *_: None)
    return cdp, events


def test_connects_observed_other_account_for_existing_identity_reader(isolated_home):
    module = _load()
    candidate, provider = write_identity(isolated_home)
    provider.unlink()

    result = module.connect(isolated_home, _snapshot(body="PRIVATE-DOM", extra="PRIVATE-TOKEN"))

    assert result == {"ok": True, "status": "account_connected"}
    assert module.ready(isolated_home) == result
    sys.path.insert(0, str(SOURCE.parent))
    from local_identity import load_identity
    assert load_identity(candidate, provider)["account_id"] == "other-seller"
    assert "PRIVATE-" not in _observation(isolated_home).read_text()
    assert "PRIVATE-" not in provider.read_text()
    assert "other-seller" not in json.dumps(result)
    for path in (provider, _observation(isolated_home)):
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("updates", [
    {"url": "https://www.lancers.jp.evil.example/mypage?secret=PRIVATE"},
    {"url": "https://www.lancers.jp@evil.example/mypage"},
    {"url": "http://www.lancers.jp/mypage"},
    {"url": "https://www.lancers.jp/profile/other-seller"},
    {"url": MYPAGE + "?secret=PRIVATE"},
    {"ready": "loading"}, {"login_form": True}, {"login_form": None},
    {"human_verification": True}, {"human_verification": None},
    {"profile_links": []}, {"profile_links": "other-seller"},
    {"profile_links": ["https://www.lancers.jp/profile/other-seller",
                       "https://www.lancers.jp/profile/someone-else"]},
    {"profile_links": ["https://evil.example/profile/other-seller?token=PRIVATE"]},
    {"profile_links": ["https://www.lancers.jp/profile/other-seller?token=PRIVATE"]},
    {"profile_links": ["https://www.lancers.jp/profile/../mypage"]},
])
def test_unconfirmed_or_ambiguous_snapshot_cannot_connect(isolated_home, updates):
    module = _load()
    snapshot = _snapshot(**updates)
    assert module.observed_account(snapshot) is None
    result = module.connect(isolated_home, snapshot)
    assert result["error"] == "setup_required"
    assert not _profile(isolated_home).exists()
    assert "PRIVATE" not in _observation(isolated_home).read_text()


def test_duplicate_links_to_same_summary_account_are_unambiguous(isolated_home):
    module = _load()
    snapshot = _snapshot(profile_links=["https://www.lancers.jp/profile/other-seller"] * 2)
    assert module.observed_account(snapshot) == "other-seller"


@pytest.mark.parametrize("account", ["other-seller", "seller~another", "別の利用者"])
def test_summary_profile_and_statistics_links_connect_one_account(isolated_home, account):
    module = _load()
    root = f"https://www.lancers.jp/profile/{account}"
    snapshot = _snapshot(profile_links=[root, root + "/feedback/0/win", root + "/proposal",
                                        root + "/feedback/0/feedback"])

    assert module.observed_account(snapshot) == account
    assert module.connect(isolated_home, snapshot) == {"ok": True, "status": "account_connected"}
    assert json.loads(_profile(isolated_home).read_text())["account_id"] == account
    assert module.ready(isolated_home) == {"ok": True, "status": "account_connected"}


def test_statistics_link_to_another_account_is_ambiguous(isolated_home):
    module = _load()
    snapshot = _snapshot(profile_links=["https://www.lancers.jp/profile/other-seller",
                                       "https://www.lancers.jp/profile/someone-else/proposal"])
    assert module.observed_account(snapshot) is None
    assert module.connect(isolated_home, snapshot)["error"] == "setup_required"
    assert not _profile(isolated_home).exists()


@pytest.mark.parametrize("previous", ["not-json", "[]", '{"account_id":null}',
                                     '{"account_id":""}', '{"account_id":"someone-else"}'])
def test_invalid_or_mismatching_existing_profile_is_not_overwritten(isolated_home, previous):
    module = _load()
    assert module.connect(isolated_home, _snapshot())["ok"] is True
    path = _profile(isolated_home)
    path.write_text(previous)
    result = module.connect(isolated_home, _snapshot())
    assert result["error"] == "setup_required"
    assert path.read_text() == previous
    assert module.ready(isolated_home)["error"] == "setup_required"


def test_same_account_preserves_existing_private_profile_keys(isolated_home):
    module = _load()
    path = _profile(isolated_home)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"account_id": "other-seller", "portfolio": ["private-existing-proof"]}))
    assert module.connect(isolated_home, _snapshot())["ok"] is True
    assert json.loads(path.read_text())["portfolio"] == ["private-existing-proof"]
    assert "private-existing-proof" not in json.dumps(module.ready(isolated_home))


@pytest.mark.parametrize("corruption", ["account", "binding", "binding_missing", "binding_malformed",
                                     "snapshot", "digest", "missing", "broken"])
def test_ready_requires_current_same_account_and_matching_digest(isolated_home, corruption):
    module = _load()
    assert module.ready(isolated_home)["error"] == "setup_required"
    assert not (isolated_home / ".config").exists()
    module.connect(isolated_home, _snapshot())
    profile = json.loads(_profile(isolated_home).read_text())
    latest = json.loads(_observation(isolated_home).read_text())
    if corruption == "account":
        profile["account_id"] = "someone-else"
    elif corruption == "binding":
        profile["account_binding"]["observation_sha256"] = "b" * 64
    elif corruption == "binding_missing":
        profile.pop("account_binding")
    elif corruption == "binding_malformed":
        profile["account_binding"] = []
    elif corruption == "snapshot":
        latest["snapshot"]["ready"] = "loading"
    elif corruption == "digest":
        latest["observation_sha256"] = "b" * 64
    elif corruption == "missing":
        _observation(isolated_home).unlink()
    else:
        _observation(isolated_home).write_text("[]")
    _profile(isolated_home).write_text(json.dumps(profile))
    if corruption not in {"missing", "broken"}:
        _observation(isolated_home).write_text(json.dumps(latest))
    assert module.ready(isolated_home)["error"] == "setup_required"


def test_ready_reads_each_binding_input_once_without_writing_or_exposing_account(isolated_home, monkeypatch):
    module = _load()
    module.connect(isolated_home, _snapshot())
    paths = {_profile(isolated_home), _observation(isolated_home)}
    previous = {path: path.read_bytes() for path in paths}
    reads = []
    original_read = Path.read_text

    def read(path, *args, **kwargs):
        assert path in paths, "ready read an unrelated private input"
        reads.append(path)
        return original_read(path, *args, **kwargs)

    def forbidden(*_args, **_kwargs):
        pytest.fail("ready must not write binding or invoke browser")

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(module, "_write_private", forbidden)
    monkeypatch.setattr(module, "_load_cdp", forbidden)
    monkeypatch.setattr(module.subprocess, "run", forbidden)

    assert module.ready(isolated_home) == {"ok": True, "status": "account_connected"}
    assert len(reads) == 2
    assert set(reads) == paths
    assert {path: path.read_bytes() for path in paths} == previous


def test_unleased_observe_invalidates_old_success_before_any_guard_or_cdp(isolated_home, monkeypatch):
    module = _load()
    module.connect(isolated_home, _snapshot())

    def forbidden(*_args, **_kwargs):
        pytest.fail("unleased observation must not reach guard or browser")

    monkeypatch.setattr(module.subprocess, "run", forbidden)
    monkeypatch.setattr(module, "_load_cdp", forbidden)
    result = module.observe(isolated_home)
    assert result["error"] == "setup_required"
    assert module.ready(isolated_home)["error"] == "setup_required"


@pytest.mark.parametrize("entrypoint", ["observe", "connect"])
def test_enospc_invalidation_cannot_leave_previous_connection_ready(isolated_home, monkeypatch, entrypoint):
    module = _load()
    profile = _profile(isolated_home)
    profile.parent.mkdir(parents=True)
    profile.write_text(json.dumps({"account_id": "other-seller", "portfolio": ["existing-private-proof"]}))
    assert module.connect(isolated_home, _snapshot())["status"] == "account_connected"
    previous = profile.read_bytes()
    callbacks = []

    def no_space(_path, _value):
        raise OSError(errno.ENOSPC, "PRIVATE-STORAGE-DETAIL")

    monkeypatch.setattr(module, "_write_private", no_space)
    monkeypatch.setattr(module, "_inherited_lease", lambda: callbacks.append("guard") or False)
    monkeypatch.setattr(module, "_load_cdp", lambda: callbacks.append("browser"))

    result = module.observe(isolated_home) if entrypoint == "observe" else module.connect(isolated_home, _snapshot())

    assert result == {"ok": False, "error": "setup_required", "missing": ["private_storage"]}
    assert profile.read_bytes() == previous
    assert callbacks == []
    assert module.ready(isolated_home) == {
        "ok": False, "error": "setup_required", "missing": ["account_observation"],
    }
    assert not _observation(isolated_home).exists()


@pytest.mark.parametrize("entrypoint", ["observe", "connect"])
def test_unlink_denial_stops_before_writing_or_browser(isolated_home, monkeypatch, entrypoint):
    module = _load()
    module.connect(isolated_home, _snapshot())
    previous_profile = _profile(isolated_home).read_bytes()
    previous_observation = _observation(isolated_home).read_bytes()
    original_unlink = Path.unlink
    callbacks = []

    def denied(path, *args, **kwargs):
        if path == _observation(isolated_home):
            raise PermissionError(errno.EACCES, "PRIVATE-STORAGE-DETAIL")
        return original_unlink(path, *args, **kwargs)

    def forbidden_write(_path, _value):
        callbacks.append("write")
        raise OSError(errno.ENOSPC, "PRIVATE-STORAGE-DETAIL")

    monkeypatch.setattr(Path, "unlink", denied)
    monkeypatch.setattr(module, "_write_private", forbidden_write)
    monkeypatch.setattr(module, "_inherited_lease", lambda: callbacks.append("guard") or False)
    monkeypatch.setattr(module, "_load_cdp", lambda: callbacks.append("browser"))

    result = module.observe(isolated_home) if entrypoint == "observe" else module.connect(isolated_home, _snapshot())

    assert result == {"ok": False, "error": "setup_required", "missing": ["private_storage"]}
    assert callbacks == []
    assert _profile(isolated_home).read_bytes() == previous_profile
    assert _observation(isolated_home).read_bytes() == previous_observation


@pytest.mark.parametrize("boundary", ["holder", "token", "host", "lease_uuid", "lease_port",
                                     "endpoint", "reachable", "identity", "collision", "malformed"])
def test_inherited_environment_requires_real_guard_holder_endpoint_join(isolated_home, monkeypatch, boundary):
    module = _load()
    holder, row, status = {}, {}, {}
    other_rows = []
    if boundary == "holder":
        holder["pid"] = os.getpid() + 1
    elif boundary == "token":
        holder["holder_start"] = "wrong-token"
    elif boundary == "host":
        holder["host"] = "other-host"
    elif boundary == "lease_uuid":
        holder["uuid"] = "different-browser"
    elif boundary == "lease_port":
        holder["port"] = 19472
    elif boundary == "endpoint":
        row["endpoint"] = "http://127.0.0.1:19472"
    elif boundary == "reachable":
        row["reachable"] = False
    elif boundary == "identity":
        row["identity"] = "coconala:kosuke"
    elif boundary == "collision":
        status["collisions"] = {"fixture-browser-uuid": ["lancers:dais", "other:identity"]}
        other_rows = [{"identity": "other:identity", "uuid": "fixture-browser-uuid",
                       "reachable": True, "endpoint": "http://127.0.0.1:19472", "port": 19472, "holder": ""}]
    else:
        row["holder"] = "not-json-PRIVATE"
    _lease(isolated_home, monkeypatch, row_updates=row, holder_updates=holder,
           status_updates=status, other_rows=other_rows)
    monkeypatch.setattr(module, "_load_cdp", lambda: pytest.fail("invalid lease must not connect to CDP"))
    assert module.observe(isolated_home)["error"] == "setup_required"
    assert not _profile(isolated_home).exists()


@pytest.mark.parametrize("shares_lancers_uuid", [False, True])
def test_guard_collision_is_scoped_to_lancers_browser_uuid(isolated_home, monkeypatch, shares_lancers_uuid):
    module = _load()
    uuid = "fixture-browser-uuid" if shares_lancers_uuid else "unrelated-browser-uuid"
    other_rows = [
        {"identity": "other:a", "uuid": uuid, "reachable": True,
         "endpoint": "http://127.0.0.1:19472", "port": 19472, "holder": ""},
        {"identity": "other:b", "uuid": uuid, "reachable": True,
         "endpoint": "http://127.0.0.1:19473", "port": 19473, "holder": ""},
    ]
    identities = ["lancers:dais", "other:a", "other:b"] if shares_lancers_uuid else ["other:a", "other:b"]
    _lease(isolated_home, monkeypatch, other_rows=other_rows,
           status_updates={"collisions": {uuid: identities}})
    cdp, events = _browser(module, monkeypatch)

    result = module.observe(isolated_home)

    if shares_lancers_uuid:
        assert result["error"] == "setup_required"
        assert not _profile(isolated_home).exists()
        assert events == []
    else:
        assert result == {"ok": True, "status": "account_connected"}
        assert events == ["open", "evaluate", "close"]
        assert cdp.target_ownership.targets_for_owner("lancers-onboarding") == set()


def test_observe_closes_only_owned_target_before_private_connection(isolated_home, monkeypatch):
    module = _load()
    calls = _lease(isolated_home, monkeypatch)
    cdp, events = _browser(module, monkeypatch)
    connect = module.connect

    def after_close(home, snapshot):
        assert events == ["open", "evaluate", "close"]
        assert cdp.target_ownership.targets_for_owner("lancers-onboarding") == set()
        return connect(home, snapshot)

    monkeypatch.setattr(module, "connect", after_close)
    result = module.observe(isolated_home)
    assert result == {"ok": True, "status": "account_connected"}
    assert calls.read_text() == "status"
    assert cdp.BASE == ENDPOINT
    assert module.ready(isolated_home) == result


def test_observe_waits_for_positive_account_dom_after_empty_complete(isolated_home, monkeypatch):
    module = _load()
    _lease(isolated_home, monkeypatch)
    cdp, events = _browser(module, monkeypatch, snapshots=[
        _snapshot(url="about:blank", profile_links=[]),
        _snapshot(profile_links=[]),
        _snapshot(),
    ])
    sleeps = []
    monkeypatch.setattr(module.time, "sleep", sleeps.append)

    result = module.observe(isolated_home)

    assert result == {"ok": True, "status": "account_connected"}
    assert events == ["open", "evaluate", "evaluate", "evaluate", "close"]
    assert sleeps == [0.5, 0.5]
    assert cdp.target_ownership.targets_for_owner("lancers-onboarding") == set()
    assert module.ready(isolated_home) == result


@pytest.mark.parametrize("snapshot", [
    _snapshot(profile_links=[]),
    _snapshot(login_form=True),
    _snapshot(human_verification=True),
    _snapshot(url="https://www.lancers.jp.evil.example/mypage"),
    _snapshot(profile_links=["https://www.lancers.jp/profile/other-seller",
                             "https://www.lancers.jp/profile/someone-else"]),
])
def test_observe_stops_at_existing_attempt_limit_without_positive_account(isolated_home, monkeypatch, snapshot):
    module = _load()
    _lease(isolated_home, monkeypatch)
    cdp, events = _browser(module, monkeypatch, snapshots=[snapshot] * 20)
    sleeps = []
    monkeypatch.setattr(module.time, "sleep", sleeps.append)

    result = module.observe(isolated_home)

    assert result["error"] == "setup_required"
    assert events == ["open"] + ["evaluate"] * 20 + ["close"]
    assert sleeps == [0.5] * 20
    assert cdp.target_ownership.targets_for_owner("lancers-onboarding") == set()
    assert not _profile(isolated_home).exists()


@pytest.mark.parametrize("failure", ["open", "evaluate", "close"])
def test_observation_or_cleanup_failure_cannot_leave_old_ready(isolated_home, monkeypatch, failure):
    module = _load()
    module.connect(isolated_home, _snapshot())
    previous = _profile(isolated_home).read_bytes()
    _lease(isolated_home, monkeypatch)
    cdp, events = _browser(module, monkeypatch, failure=failure)
    result = module.observe(isolated_home)
    assert result["error"] == "setup_required"
    assert "PRIVATE" not in json.dumps(result)
    assert _profile(isolated_home).read_bytes() == previous
    assert module.ready(isolated_home)["error"] == "setup_required"
    assert events == (["open"] if failure == "open" else ["open", "evaluate", "close"])
    if failure != "close":
        assert cdp.target_ownership.targets_for_owner("lancers-onboarding") == set()


@pytest.mark.parametrize("command", ["observe", "status"])
def test_cli_unconfigured_is_secret_free_setup_required(isolated_home, command):
    _load()
    completed = subprocess.run([sys.executable, str(SOURCE), command], capture_output=True,
                               text=True, env=os.environ, timeout=10)
    assert completed.returncode == 78
    assert json.loads(completed.stdout)["error"] == "setup_required"
    assert completed.stderr == ""


def test_status_cli_exposes_account_connected_without_account_or_private_fields(isolated_home):
    module = _load()
    module.connect(isolated_home, _snapshot())
    completed = subprocess.run([sys.executable, str(SOURCE), "status"], capture_output=True,
                               text=True, env=os.environ, timeout=10)
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {"ok": True, "status": "account_connected"}
    assert completed.stderr == ""


def test_import_does_not_read_private_input_or_invoke_browser(isolated_home, monkeypatch):
    original = Path.read_text

    def read(path, *args, **kwargs):
        assert not path.is_relative_to(isolated_home), "import read private input"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: pytest.fail("import invoked browser"))
    _load()
    assert list(isolated_home.iterdir()) == []


@pytest.mark.parametrize("summary_links,title,body,want", [
    (["https://www.lancers.jp/profile/other-seller"], "Mypage", "PRIVATE-DOM", "other-seller"),
    (["https://www.lancers.jp/profile/other-seller"] * 4 + [
        "https://www.lancers.jp/profile/other-seller/feedback/0/win",
        "https://www.lancers.jp/profile/other-seller/proposal",
        "https://www.lancers.jp/profile/other-seller/feedback/0/feedback",
    ] * 2, "Mypage", "PRIVATE-DOM", "other-seller"),
    ([], "Mypage", "PRIVATE-DOM", None),
    (["https://www.lancers.jp/profile/other-seller"], "Human Verification", "PRIVATE-DOM", None),
    (["https://www.lancers.jp/profile/other-seller"], "Mypage", "This site uses reCAPTCHA. PRIVATE-DOM", "other-seller"),
    (["https://www.lancers.jp/profile/other-seller"], "Mypage", "captcha PRIVATE-DOM", "other-seller"),
    (["https://www.lancers.jp/profile/other-seller"], "CAPTCHA verification", "PRIVATE-DOM", None),
    (["https://www.lancers.jp/profile/other-seller"], "Mypage", "Verify that you are human. PRIVATE-DOM", None),
    (["https://www.lancers.jp/profile/other-seller"], "Mypage", "ユーザーが人間であることを確認する PRIVATE-DOM", None),
])
def test_dom_snapshot_reads_summary_links_without_page_text(isolated_home, summary_links, title, body, want):
    module = _load()
    script = r'''
const vm = require('node:vm'), input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const document = {readyState:'complete', title:input.title,
  body:{innerText:input.body},
  querySelector: () => null,
  querySelectorAll: selector => selector === '.mypage.result-summary a[href*="/profile/"]'
    ? input.links.map(href => ({href})) : [{href:'https://www.lancers.jp/profile/someone-else'}],
};
const location = {origin:'https://www.lancers.jp', pathname:'/mypage', href:'https://www.lancers.jp/mypage?secret=PRIVATE'};
process.stdout.write(JSON.stringify(vm.runInNewContext(input.expression, {document, location, URL, JSON})));
'''
    completed = subprocess.run(["node", "-e", script], input=json.dumps({
        "expression": module.EXPRESSION, "links": summary_links, "title": title, "body": body}),
        capture_output=True, text=True, timeout=10, check=True)
    snapshot = json.loads(completed.stdout)
    assert module.observed_account(snapshot) == want
    if want is not None:
        assert module.connect(isolated_home, snapshot) == {"ok": True, "status": "account_connected"}
    assert "PRIVATE" not in completed.stdout
