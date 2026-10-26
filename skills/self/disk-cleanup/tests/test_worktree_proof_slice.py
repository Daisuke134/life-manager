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


def _repo_with_three_worktrees(tmp_path: Path, repo_relative: str = "Projects/life-manager-main",
                               worktrees_relative: str = "Projects/life-manager-main/.worktrees",
                               names=("a", "b", "c")) -> tuple[Path, list[Path]]:
    home = tmp_path / "home"
    repo = home / repo_relative
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True)
    _git(repo, "config", "user.name", "Disk Cleanup Test")
    _git(repo, "config", "user.email", "disk-cleanup-test@example.invalid")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    _git(repo, "remote", "add", "origin", str(repo))
    _git(repo, "update-ref", "refs/remotes/origin/main", _git(repo, "rev-parse", "HEAD"))
    (home / worktrees_relative).mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        path = home / worktrees_relative / name
        _git(repo, "worktree", "add", "--detach", str(path), "HEAD")
        paths.append(path)
    return home, paths


def _governor_with_fake_proofs(home: Path, monkeypatch, clock: list[float], cost: float):
    governor = MODULE.HostDiskGovernor(home=home, state_dir=home / "state",
                                       lsof=lambda _path: "confirmed-closed", usage=lambda: (0, 1))
    governor.clock = lambda: clock[0]
    seen: list[str] = []

    def fake_identity(path, **_kwargs):
        if Path(path).name not in {"a", "b", "c", "x", "y", "z"}:
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
    # worktree slice = 8 s, split over the two registered repositories = 4 s each; three proofs cost 3 s
    candidates = governor.discover_candidates(deadline=20.0)
    zombies = [Path(item["path"]).name for item in candidates if item["owner"] == "zombie-worktree"]
    assert zombies == ["a", "b", "c"]
    assert seen == ["a", "b", "c"]


def test_cursor_resumes_where_the_slice_ran_out(tmp_path, monkeypatch):
    home, paths = _repo_with_three_worktrees(tmp_path)
    clock = [0.0]
    governor, seen = _governor_with_fake_proofs(home, monkeypatch, clock, cost=1.0)
    # share = 2 s: main (free), a (1 s); b would start with only 1 s left (< MIN_PROOF_SECONDS) and waits
    first = governor._worktree_candidates(deadline=4.0)
    assert [Path(item["path"]).name for item in first] == ["a"]
    cursor = json.loads((home / "state" / "worktree-proof-cursor.json").read_text())
    assert cursor == {"Projects/life-manager-main": 2}  # records: main, a | b, c
    clock[0] = 0.0
    second = governor._worktree_candidates(deadline=4.0)
    assert [Path(item["path"]).name for item in second] == ["b"]
    clock[0] = 0.0
    third = governor._worktree_candidates(deadline=10.0)  # finishes the ring: c, then wraps to a, b
    assert [Path(item["path"]).name for item in third] == ["c", "a", "b"]
    assert json.loads((home / "state" / "worktree-proof-cursor.json").read_text()) == {"Projects/life-manager-main": 0}


def test_each_repository_gets_an_even_share_of_the_slice(tmp_path, monkeypatch):
    home, _first = _repo_with_three_worktrees(tmp_path)
    _repo_with_three_worktrees(tmp_path, "Projects/anicca-products", "Projects/anicca-products-worktrees", ("x", "y", "z"))
    clock = [0.0]
    governor, seen = _governor_with_fake_proofs(home, monkeypatch, clock, cost=1.0)
    found = [Path(item["path"]).name for item in governor._worktree_candidates(deadline=4.0)]
    # 4 s split evenly: life-manager-main gets 2 s (a; b would not fit MIN_PROOF_SECONDS), then
    # anicca-products gets the remaining 3 s (x, y; z would not fit).
    assert found == ["a", "x", "y"]


def test_a_record_that_cannot_finish_before_the_deadline_is_not_marked_done(tmp_path, monkeypatch):
    home, _paths = _repo_with_three_worktrees(tmp_path)
    clock = [0.0]
    governor, seen = _governor_with_fake_proofs(home, monkeypatch, clock, cost=1.0)
    found = [Path(item["path"]).name for item in governor._worktree_candidates(deadline=6.0)]  # share 3 s
    assert found == ["a", "b"]  # c would start with 1 s left and be cut off; it waits for the next pass
    assert json.loads((home / "state" / "worktree-proof-cursor.json").read_text()) == {"Projects/life-manager-main": 3}
