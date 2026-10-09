import json
import os
import shutil
import subprocess
import time
from pathlib import Path
import pytest

from runtime.loop import loop_cleanup


def fixture(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    for key, value in (("user.email", "test@example.invalid"), ("user.name", "Test")):
        subprocess.run(["git", "config", key, value], cwd=repo, check=True)
    files = {"bin/one.py": b"print('one')\n", "bin/two.py": b"print('two')\n",
             "memory/owner.md": b"keep memory", "state/data.jsonl": b"{}\n",
             "bin/credentials.py": b"keep credential", "bin/changed.py": b"original"}
    for name, data in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", sha], cwd=repo, check=True)
    release = tmp_path / "releases" / ("20260101T000000-" + sha[:8])
    release.mkdir(parents=True)
    for name, data in files.items():
        path = release / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (release / "bin/changed.py").write_bytes(b"unknown change")
    (release / "unknown.py").write_bytes(b"unknown")
    descriptor = json.dumps({"sha": sha, "release_paths": "ALL"}).encode()
    (release / "RELEASE.json").write_bytes(descriptor)
    return repo, release, descriptor


def reclaim(release, repo, **kw):
    return loop_cleanup.reclaim_release_source(release, repo, can_reclaim=lambda _: True, **kw)


def test_code_reclaim_preserves_data_and_invalidates_release(tmp_path):
    repo, release, descriptor = fixture(tmp_path)
    protected = [release / p for p in ("memory/owner.md", "state/data.jsonl", "bin/credentials.py", "bin/changed.py", "unknown.py")]
    before = {p: (p.stat().st_ino, p.read_bytes()) for p in protected}
    result = reclaim(release, repo)
    assert result["removed_files"] == 2
    assert not (release / "bin/one.py").exists()
    assert not (release / "RELEASE.json").exists()
    assert (release / "RECLAIMED-RELEASE.json").read_bytes() == descriptor
    assert not loop_cleanup._valid_release(release)
    assert {p: (p.stat().st_ino, p.read_bytes()) for p in protected} == before
    assert result["protected_deletions"] == 0


def test_file_budget_resumes_from_same_descriptor(tmp_path):
    repo, release, descriptor = fixture(tmp_path)
    first = reclaim(release, repo, max_files=1)
    assert first["removed_files"] == 1
    second = reclaim(release, repo, max_files=1)
    assert second["removed_files"] == 1
    assert (release / "RECLAIMED-RELEASE.json").read_bytes() == descriptor


def test_byte_or_time_budget_does_not_mark_or_delete(tmp_path):
    repo, release, _ = fixture(tmp_path)
    assert reclaim(release, repo, max_bytes=1)["removed_files"] == 0
    assert reclaim(release, repo, deadline=0)["removed_files"] == 0
    assert (release / "RELEASE.json").exists()


def test_final_reference_change_stops_before_effect(tmp_path):
    repo, release, _ = fixture(tmp_path)
    answers = iter((True, False))
    result = loop_cleanup.reclaim_release_source(release, repo, can_reclaim=lambda _: next(answers))
    assert result["removed_files"] == 0
    assert (release / "RELEASE.json").exists()
    assert (release / "bin/one.py").exists()


def test_symlink_parent_and_leaf_are_not_followed(tmp_path):
    repo, release, _ = fixture(tmp_path)
    outside = tmp_path / "outside"
    shutil.move(release / "bin", outside)
    (release / "bin").symlink_to(outside, target_is_directory=True)
    result = reclaim(release, repo)
    assert result["removed_files"] == 0
    assert (outside / "one.py").exists()
    (release / "bin").unlink()
    shutil.move(outside, release / "bin")
    (release / "bin/one.py").unlink()
    (release / "bin/one.py").symlink_to(release / "memory/owner.md")
    result = reclaim(release, repo)
    assert (release / "bin/one.py").is_symlink()
    assert (release / "memory/owner.md").read_bytes() == b"keep memory"


def test_replaced_parent_does_not_delete_new_memory_descendant(tmp_path):
    repo, release, _ = fixture(tmp_path)
    calls = 0
    def references(_owned_fds):
        nonlocal calls
        calls += 1
        if calls == 2:
            (release / "bin").rename(release / "memory" / "bin")
            (release / "bin").mkdir()
        return True
    result = loop_cleanup.reclaim_release_source(release, repo, can_reclaim=references)
    assert result["removed_files"] == 0
    assert (release / "memory/bin/one.py").exists()
    assert (release / "memory/bin/two.py").exists()
    assert (release / "RELEASE.json").exists()


def test_read_only_release_restores_directory_modes(tmp_path):
    repo, release, _ = fixture(tmp_path)
    for path in release.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    release.chmod(0o555)
    before = (release / "memory/owner.md").stat().st_ino
    try:
        result = reclaim(release, repo)
        assert result["removed_files"] == 2
        assert release.stat().st_mode & 0o777 == 0o555
        assert (release / "bin").stat().st_mode & 0o777 == 0o555
        assert (release / "memory/owner.md").stat().st_ino == before
    finally:
        for path in release.rglob("*"):
            if path.is_dir(): path.chmod(0o755)
        release.chmod(0o755)


@pytest.mark.parametrize("additional_reference", (None, "self_other_fd", "other_pid"))
def test_owner_reclaims_one_old_snapshot_and_keeps_rollback(tmp_path, monkeypatch, additional_reference):
    from runtime.loop import central_cleanup
    from runtime.loop import lm_loop
    repo, release, _ = fixture(tmp_path)
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=repo, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True, capture_output=True)
    rollback = release.with_name("20260102T000000-" + release.name.split("-")[1])
    shutil.copytree(release, rollback)
    current_root = release.with_name("20260103T000000-" + release.name.split("-")[1])
    shutil.copytree(release, current_root)
    os.utime(release, (1, 1)); os.utime(rollback, (2, 2)); os.utime(current_root, (3, 3))
    current = tmp_path / "current"
    current.symlink_to(current_root)
    monkeypatch.setenv("LIFE_MANAGER_SOURCE_REPO", str(repo))
    monkeypatch.setenv("LIFE_MANAGER_PROTECTED_RELEASES", str(tmp_path / "no-protected.json"))
    monkeypatch.setattr(central_cleanup, "loaded_release_roots", lambda *_: set())
    monkeypatch.setattr(central_cleanup, "open_release_roots", lambda *_: set())
    real_run = subprocess.run
    def run(command, **kw):
        if command[0] == "lsof":
            # Report actual open validation FDs, just as production lsof does.
            lines = ["p" + str(os.getpid())]
            resources = [release, release / "bin", release / "bin/one.py", release / "bin/two.py"]
            opened = []
            for p in Path("/dev/fd").iterdir():
                try:
                    fd = int(p.name)
                    info = os.fstat(fd)
                except (OSError, ValueError):
                    continue
                for resource in resources:
                    if resource.exists() and (info.st_dev, info.st_ino) == (resource.stat().st_dev, resource.stat().st_ino):
                        lines.extend(("f" + str(fd), "n" + str(resource)))
                        opened.append(fd)
            if opened and additional_reference:
                if additional_reference == "other_pid":
                    lines.append("p" + str(os.getpid() + 100000))
                    lines.append("f" + str(opened[0]))
                else:
                    lines.append("f999999")
                lines.append("n" + str(release / "unknown.py"))
            return subprocess.CompletedProcess(command, 0, "\n".join(lines), "")
        return real_run(command, **kw)
    monkeypatch.setattr(central_cleanup.subprocess, "run", run)
    real_lock = lm_loop._apply_lock
    attempts = 0
    def initially_busy(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("production apply is already owned")
        return real_lock(*args)
    monkeypatch.setattr(lm_loop, "_apply_lock", initially_busy)
    result = central_cleanup.reclaim_unreferenced_source(release.parent, current, tmp_path / "agents", 1)
    assert result["removed_files"] == (0 if additional_reference else 2)
    assert attempts >= 3
    assert (release / "RELEASE.json").exists() == bool(additional_reference)
    assert (rollback / "RELEASE.json").exists()
    assert (current_root / "RELEASE.json").exists()


def test_lifecycle_wait_deadline_keeps_lock_owned(tmp_path):
    from runtime.loop import central_cleanup, lm_loop
    current = tmp_path / "current"
    protocol = current.parent / ".admission-protocol.lock"
    with lm_loop._apply_lock(current, protocol):
        with pytest.raises(RuntimeError):
            with central_cleanup._source_reclaim_lock(current, time.monotonic()+.02):
                pytest.fail("owned protocol lock acquired")
    with pytest.raises(RuntimeError):
        with central_cleanup._source_reclaim_lock(current, 0):
            pytest.fail("expired deadline acquired locks")
