import json
import os
import shutil
import subprocess
from pathlib import Path

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
    return loop_cleanup.reclaim_release_source(release, repo, can_reclaim=lambda: True, **kw)


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
    result = loop_cleanup.reclaim_release_source(release, repo, can_reclaim=lambda: next(answers))
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
