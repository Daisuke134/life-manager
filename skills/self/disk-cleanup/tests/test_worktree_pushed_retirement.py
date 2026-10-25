"""A clean, fully pushed, stale worktree is redundant even when main re-edited its files.

2026-10-26: 70 registered worktrees (~9 GiB) sat under life-manager-main/.worktrees because every
PR lands as a squash and main then appends to the same files (BOARD, SSOT), so
``_content_in_main``'s merge attempt conflicted and the ancestry proof failed. Removing a checkout
whose every commit is already on its upstream loses nothing, so that is the third proof.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import disk_cleanup as MODULE  # noqa: E402


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


def _repo_with_pushed_branch(tmp_path: Path) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    repo = home / "Projects" / "life-manager-main"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True)
    _git(repo, "config", "user.name", "Disk Cleanup Test")
    _git(repo, "config", "user.email", "disk-cleanup-test@example.invalid")
    (repo / "BOARD.md").write_text("- base\n")
    _git(repo, "add", "BOARD.md")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "remote", "add", "origin", str(repo))
    worktrees = repo / ".worktrees"
    worktrees.mkdir()
    done = worktrees / "done"
    _git(repo, "worktree", "add", "-b", "done", str(done), base)
    (done / "BOARD.md").write_text("- base\n- done lane line\n")
    _git(done, "add", "BOARD.md")
    _git(done, "commit", "-m", "done lane")
    head = _git(done, "rev-parse", "HEAD")
    # "pushed": the upstream ref carries the same commit.
    _git(repo, "update-ref", "refs/remotes/origin/done", head)
    _git(done, "branch", "--set-upstream-to=origin/done")
    # main re-edits the same line region after the squash, so merge-tree conflicts.
    (repo / "BOARD.md").write_text("- base\n- squash of done lane\n- another agent's line\n")
    _git(repo, "add", "BOARD.md")
    _git(repo, "commit", "-m", "squash + append")
    main_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", main_head)
    stale = time.time() - MODULE.PUSHED_WORKTREE_MIN_AGE_SECONDS - 60
    os.utime(done, (stale, stale))
    return home, repo, done


def _governor(home: Path) -> MODULE.HostDiskGovernor:
    return MODULE.HostDiskGovernor(home=home, state_dir=home / "state",
                                   lsof=lambda _path: "confirmed-closed", usage=lambda: (0, 1))


def test_pushed_stale_worktree_is_redundant_even_when_main_conflicts(tmp_path: Path) -> None:
    home, repo, done = _repo_with_pushed_branch(tmp_path)
    assert not MODULE._content_in_main(repo, _git(done, "rev-parse", "HEAD"),
                                       _git(repo, "rev-parse", "refs/remotes/origin/main"))
    assert MODULE._pushed_and_stale(done)
    assert _governor(home)._worktree_identity(done) is not None


def test_an_unpushed_commit_keeps_the_worktree(tmp_path: Path) -> None:
    home, repo, done = _repo_with_pushed_branch(tmp_path)
    (done / "extra.txt").write_text("not on origin\n")
    _git(done, "add", "extra.txt")
    _git(done, "commit", "-m", "unpushed")
    stale = time.time() - MODULE.PUSHED_WORKTREE_MIN_AGE_SECONDS - 60
    os.utime(done, (stale, stale))
    assert not MODULE._pushed_and_stale(done)
    assert _governor(home)._worktree_identity(done) is None


def test_a_fresh_pushed_worktree_is_left_alone(tmp_path: Path) -> None:
    home, repo, done = _repo_with_pushed_branch(tmp_path)
    os.utime(done, None)  # touched just now: someone may still be working here
    assert not MODULE._pushed_and_stale(done)
    assert _governor(home)._worktree_identity(done) is None


def test_no_upstream_means_not_pushed(tmp_path: Path) -> None:
    home, repo, done = _repo_with_pushed_branch(tmp_path)
    _git(done, "branch", "--unset-upstream")
    assert not MODULE._pushed_and_stale(done)
