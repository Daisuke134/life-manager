"""Worktree proofs get a reserved slice at the start of discovery and resume from a cursor.

2026-10-26: every 60 s watchdog pass spent its whole discovery budget (17.5 s) on the inventory
scan, so the Git proofs placed after it never ran and no worktree was ever retired.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import disk_cleanup as MODULE  # noqa: E402


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


def _repo_with_three_worktrees(tmp_path: Path) -> tuple[Path, list[Path]]:
    home = tmp_path / "home"
    repo = home / "Projects" / "life-manager-main"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True)
    _git(repo, "config", "user.name", "Disk Cleanup Test")
    _git(repo, "config", "user.email", "disk-cleanup-test@example.invalid")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    _git(repo, "remote", "add", "origin", str(repo))
    _git(repo, "update-ref", "refs/remotes/origin/main", _git(repo, "rev-parse", "HEAD"))
    (repo / ".worktrees").mkdir()
    paths = []
    for name in ("a", "b", "c"):
        path = repo / ".worktrees" / name
        _git(repo, "worktree", "add", "--detach", str(path), "HEAD")
        paths.append(path)
    return home, paths


def _governor_with_fake_proofs(home: Path, monkeypatch, clock: list[float], cost: float):
    governor = MODULE.HostDiskGovernor(home=home, state_dir=home / "state",
                                       lsof=lambda _path: "confirmed-closed", usage=lambda: (0, 1))
    governor.clock = lambda: clock[0]
    seen: list[str] = []

    def fake_identity(path, **_kwargs):
        if Path(path).name not in {"a", "b", "c"}:
            return None  # the main checkout is a record too; the real proof rejects it for free
        seen.append(Path(path).name)
        clock[0] += cost
        return ("proof", Path(path).name)

    monkeypatch.setattr(governor, "_worktree_identity", fake_identity)
    return governor, seen


def test_worktree_proofs_run_first_inside_the_discovery_budget(tmp_path, monkeypatch):
    home, paths = _repo_with_three_worktrees(tmp_path)
    clock = [0.0]
    governor, seen = _governor_with_fake_proofs(home, monkeypatch, clock, cost=1.0)
    candidates = governor.discover_candidates(deadline=10.0)  # worktree slice = 4 s, three proofs cost 3 s
    zombies = [Path(item["path"]).name for item in candidates if item["owner"] == "zombie-worktree"]
    assert zombies == ["a", "b", "c"]
    assert seen == ["a", "b", "c"]


def test_cursor_resumes_where_the_slice_ran_out(tmp_path, monkeypatch):
    home, paths = _repo_with_three_worktrees(tmp_path)
    clock = [0.0]
    governor, seen = _governor_with_fake_proofs(home, monkeypatch, clock, cost=1.0)
    first = governor._worktree_candidates(deadline=1.0)  # one proof fits
    assert [Path(item["path"]).name for item in first] == ["a"]
    cursor = json.loads((home / "state" / "worktree-proof-cursor.json").read_text())
    assert cursor == {"Projects/life-manager-main": 2}  # records: main, a | b, c
    clock[0] = 0.0
    second = governor._worktree_candidates(deadline=1.0)
    assert [Path(item["path"]).name for item in second] == ["b"]
    clock[0] = 0.0
    third = governor._worktree_candidates(deadline=10.0)  # finishes the ring: c, then wraps to a, b
    assert [Path(item["path"]).name for item in third] == ["c", "a", "b"]
    assert json.loads((home / "state" / "worktree-proof-cursor.json").read_text()) == {"Projects/life-manager-main": 0}
