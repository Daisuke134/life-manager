"""A merged, clean worktree is redundant even when the repository tracks a `memory/` directory.

2026-10-26: every anicca-products worktree (41, ~18 GiB) survived the watchdog because the repo
tracks `memory/` and `.specify/memory/`, and the immutable-store probe treated any `memory`
directory as a runtime memory store. Tracked content is already on origin/main; untracked files
inside such a directory still block retirement through the status gate.
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


def _repo_with_merged_worktree(tmp_path: Path) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    repo = home / "Projects" / "life-manager-main"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True)
    _git(repo, "config", "user.name", "Disk Cleanup Test")
    _git(repo, "config", "user.email", "disk-cleanup-test@example.invalid")
    (repo / "memory").mkdir()
    (repo / "memory" / "constitution.md").write_text("tracked memory\n")
    (repo / "skills" / "state").mkdir(parents=True)
    (repo / "skills" / "state" / "ledger.jsonl").write_text('{"tracked": true}\n')
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    _git(repo, "remote", "add", "origin", str(repo))
    worktrees = repo / ".worktrees"
    worktrees.mkdir()
    done = worktrees / "done"
    _git(repo, "worktree", "add", "-b", "done", str(done), "HEAD")
    (done / "README.md").write_text("base\ndone\n")
    _git(done, "add", "README.md")
    _git(done, "commit", "-m", "done lane")
    head = _git(done, "rev-parse", "HEAD")
    _git(repo, "merge", "--ff-only", head)  # merged: head is an ancestor of main
    _git(repo, "update-ref", "refs/remotes/origin/main", _git(repo, "rev-parse", "HEAD"))
    stale = time.time() - 4 * 3600
    os.utime(done, (stale, stale))
    return home, repo, done


def _governor(home: Path) -> MODULE.HostDiskGovernor:
    return MODULE.HostDiskGovernor(home=home, state_dir=home / "state",
                                   lsof=lambda _path: "confirmed-closed", usage=lambda: (0, 1))


def test_tracked_memory_and_state_directories_do_not_protect_a_merged_worktree(tmp_path):
    home, _repo, done = _repo_with_merged_worktree(tmp_path)
    assert _governor(home)._worktree_identity(done) is not None


def test_untracked_file_inside_tracked_memory_directory_still_protects(tmp_path):
    home, _repo, done = _repo_with_merged_worktree(tmp_path)
    (done / "memory" / "scratch.md").write_text("not committed\n")
    assert _governor(home)._worktree_identity(done) is None


def test_untracked_memory_directory_still_protects(tmp_path):
    home, _repo, done = _repo_with_merged_worktree(tmp_path)
    (done / "runtime-memory" / "memory").mkdir(parents=True)
    assert _governor(home)._worktree_identity(done) is None


def test_ignored_build_output_directories_are_regenerable_but_ignored_secret_files_are_not():
    assert MODULE._only_regenerable_status(
        "!! apps/landing/.next/\n!! apps/landing/out/\n!! packages/ai-monk-index/dist/\n"
        "!! apps/landing/public/ai-monk-factory-download/\n!! apps/landing/node_modules\n")
    assert not MODULE._only_regenerable_status("!! apps/api/.env\n")
    assert not MODULE._only_regenerable_status("!! private/\n")
    assert not MODULE._only_regenerable_status("!! apps/landing/credentials/\n")
    assert not MODULE._only_regenerable_status("?? docs/new-note.md\n")


def test_ls_remote_runs_once_per_repository_per_pass(tmp_path, monkeypatch):
    home, _repo, done = _repo_with_merged_worktree(tmp_path)
    governor = _governor(home)
    calls = []
    real = MODULE._run_git

    def counting(path, *args, **kwargs):
        if args[:1] == ("ls-remote",):
            calls.append(args)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(MODULE, "_run_git", counting)
    assert governor._worktree_identity(done) is not None
    assert governor._worktree_identity(done) is not None
    assert len(calls) == 1


def test_a_stale_local_origin_main_is_fetched_instead_of_failing_the_proof(tmp_path):
    home, repo, done = _repo_with_merged_worktree(tmp_path)
    base = _git(repo, "rev-list", "--max-parents=0", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)  # local tracking ref lags the remote
    assert _governor(home)._worktree_identity(done) is not None
    assert _git(repo, "rev-parse", "refs/remotes/origin/main") == _git(repo, "rev-parse", "refs/heads/main")
