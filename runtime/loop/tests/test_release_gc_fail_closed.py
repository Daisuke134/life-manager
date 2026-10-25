"""Release GC must never treat an unreadable or foreign launchd inventory as "nothing is loaded".

2026-10-24: 116 launchd labels pointed at releases that release GC had deleted (EX_CONFIG).
With HOME pointing at an agent's private home, ~/Library/LaunchAgents resolved to an empty
directory, loaded_release_roots returned no protection and keep=1 deleted every other release.
"""
import json
import os
import plistlib
import stat
from pathlib import Path

import pytest

from runtime.loop import central_cleanup, loop_cleanup


def _release(root: Path, name: str) -> Path:
    path = root / name
    (path / "bin").mkdir(parents=True)
    (path / "bin" / "lm-loop-run").write_text("#!/bin/sh\n")
    (path / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
    return path


def _agent(agents: Path, label: str, release: Path) -> None:
    agents.mkdir(parents=True, exist_ok=True)
    with (agents / f"{label}.plist").open("wb") as handle:
        plistlib.dump({"Label": label, "ProgramArguments": [str(release / "bin" / "lm-loop-run"), label]}, handle)


def test_missing_or_empty_agents_dir_refuses_instead_of_protecting_nothing(tmp_path):
    releases = tmp_path / "releases"
    _release(releases, "20260101T000000-aaaaaaaa")
    with pytest.raises(OSError):
        central_cleanup.loaded_release_roots(tmp_path / "missing", releases)
    (tmp_path / "empty").mkdir()
    with pytest.raises(OSError):
        central_cleanup.loaded_release_roots(tmp_path / "empty", releases)


def test_unreadable_plist_refuses(tmp_path):
    releases = tmp_path / "releases"
    release = _release(releases, "20260101T000000-aaaaaaaa")
    agents = tmp_path / "agents"
    _agent(agents, "ai.anicca.one", release)
    (agents / "ai.anicca.broken.plist").write_bytes(f"<plist><string>{release}/bin/lm-loop-run".encode())
    (agents / "com.other.vendor.plist").write_bytes(b"not a plist")
    with pytest.raises(OSError):
        central_cleanup.loaded_release_roots(agents, releases)


def test_pinned_and_loaded_releases_survive_release_gc(tmp_path):
    releases = tmp_path / "releases"
    loaded = _release(releases, "20260101T000000-aaaaaaaa")
    pinned = _release(releases, "20260102T000000-bbbbbbbb")
    _release(releases, "20260103T000000-cccccccc")
    newest = _release(releases, "20260104T000000-dddddddd")
    (releases / ".pins").mkdir()
    (releases / ".pins" / pinned.name).write_text("")
    current = tmp_path / "current"
    current.symlink_to(newest)
    agents = tmp_path / "agents"
    _agent(agents, "ai.anicca.one", loaded)

    central_cleanup.release_gc(releases, current, agents, keep=0)

    assert loaded.is_dir() and pinned.is_dir() and newest.is_dir()


def test_default_agents_dir_ignores_a_foreign_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "agent-home"))
    monkeypatch.delenv("LIFE_MANAGER_LAUNCH_AGENTS_DIR", raising=False)
    assert central_cleanup.default_launch_agents_dir() == Path(
        __import__("pwd").getpwuid(__import__("os").getuid()).pw_dir) / "Library" / "LaunchAgents"


def test_release_named_only_by_working_directory_or_environment_is_loaded(tmp_path):
    """2026-10-25: 175 plists name their release in LIFE_MANAGER_REPO, not only in ProgramArguments."""
    releases = tmp_path / "releases"
    by_env = _release(releases, "20260101T000000-aaaaaaaa")
    by_cwd = _release(releases, "20260102T000000-bbbbbbbb")
    _release(releases, "20260103T000000-cccccccc")
    agents = tmp_path / "agents"
    agents.mkdir()
    with (agents / "ai.anicca.env.plist").open("wb") as handle:
        plistlib.dump({"Label": "ai.anicca.env", "ProgramArguments": ["/bin/sh", "-c", "true"],
                       "WorkingDirectory": str(by_cwd),
                       "EnvironmentVariables": {"LIFE_MANAGER_REPO": str(by_env), "COUNT": "3"}}, handle)

    assert central_cleanup.loaded_release_roots(agents, releases) == {by_env.resolve(), by_cwd.resolve()}


def test_every_release_removal_appends_a_receipt(tmp_path, monkeypatch):
    log = tmp_path / "state" / "release-gc.jsonl"
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_GC_LOG", str(log))
    releases = tmp_path / "releases"
    loaded = _release(releases, "20260101T000000-aaaaaaaa")
    stale = [_release(releases, "20260102T000000-bbbbbbbb"), _release(releases, "20260103T000000-cccccccc")]
    newest = _release(releases, "20260104T000000-dddddddd")
    current = tmp_path / "current"
    current.symlink_to(newest)
    agents = tmp_path / "agents"
    _agent(agents, "ai.anicca.one", loaded)

    result = central_cleanup.release_gc(releases, current, agents, keep=0)

    assert result["removed_releases"] == 2 and not any(path.exists() for path in stale)
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert sorted(record["path"] for record in records) == sorted(str(path) for path in stale)
    for record in records:
        assert set(record) == {"ts", "path", "pid", "ppid", "argv", "keep", "protected_count"}
        assert record["pid"] == os.getpid() and record["keep"] == 0
        assert record["protected_count"] == 2  # loaded + current
    assert stat.S_IMODE(log.stat().st_mode) == 0o600
    assert stat.S_IMODE(log.parent.stat().st_mode) == 0o700


def test_release_survives_when_its_receipt_cannot_be_written(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_GC_LOG", str(blocker / "release-gc.jsonl"))
    releases = tmp_path / "releases"
    stale = _release(releases, "20260101T000000-aaaaaaaa")
    current = tmp_path / "current"
    current.symlink_to(_release(releases, "20260102T000000-bbbbbbbb"))

    result = loop_cleanup.gc_releases(releases, current, keep=0, protected=set())

    assert stale.is_dir() and result["removed_releases"] == 0 and result["errors"] == 1
