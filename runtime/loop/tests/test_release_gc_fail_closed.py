"""Release GC must never treat an unreadable or foreign launchd inventory as "nothing is loaded".

2026-10-24: 116 launchd labels pointed at releases that release GC had deleted (EX_CONFIG).
With HOME pointing at an agent's private home, ~/Library/LaunchAgents resolved to an empty
directory, loaded_release_roots returned no protection and keep=1 deleted every other release.
"""
import plistlib
from pathlib import Path

import pytest

from runtime.loop import central_cleanup


def _release(root: Path, name: str) -> Path:
    path = root / name
    (path / "bin").mkdir(parents=True)
    (path / "bin" / "lm-loop-run").write_text("#!/bin/sh\n")
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


def test_memoized_resolution_matches_path_resolve(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "l").symlink_to(tmp_path / "a" / "b")
    (tmp_path / "a" / "b" / "up").symlink_to("../a")
    (tmp_path / "loop1").symlink_to(tmp_path / "loop2")
    (tmp_path / "loop2").symlink_to(tmp_path / "loop1")
    memo: dict = {}
    for raw in ("l/x", "l/up/b/../b/y", "a/./b/", "missing/../a", "loop1/z", "a/b"):
        path = str(tmp_path / raw)
        assert central_cleanup._resolve_memo(path, memo) == str(Path(path).resolve()), raw
