import errno
import hashlib
import json
import tempfile
import os
import signal
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

import disk_cleanup  # noqa: E402
from disk_cleanup import (  # noqa: E402
    GiB,
    HostDiskGovernor,
    classify_tier,
)

DEFAULT_BOOTSTRAP_HEALTH = disk_cleanup._default_bootstrap_health


@pytest.fixture(autouse=True)
def stub_bootstrap_health_for_governor_unit_tests(monkeypatch) -> None:
    monkeypatch.setattr(
        disk_cleanup,
        "_default_bootstrap_health",
        lambda _home, _state_dir: {"status": "not-applicable"},
    )


def test_tier_boundaries_use_bytes() -> None:
    assert classify_tier(20 * GiB) == "NORMAL"
    assert classify_tier(20 * GiB - 1) == "PREVENTIVE"
    assert classify_tier(11 * GiB) == "PREVENTIVE"
    assert classify_tier(11 * GiB - 1) == "PRESSURE"
    assert classify_tier(6 * GiB - 1) == "CRITICAL"
    assert classify_tier(3 * GiB - 1) == "ULTRA"


def test_closed_regenerable_artifact_is_reclaimed(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    candidate = tmp_path / "tmp" / "capafy-hf-npm.complete"
    candidate.mkdir(parents=True)
    (candidate / "payload").write_bytes(b"x" * 64)
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(candidate.parent))
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=state,
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor.sweep(
        [{"path": candidate, "class": "ephemeral", "owner": "temporary-run", "discovery": "allowlisted"}]
    )

    assert result["reclaimed"] > 0
    assert not candidate.exists()
    receipt = json.loads((state / "last-receipt.json").read_text())
    assert receipt["protected_deletions"] == 0
    assert receipt["cleanup_pid"] == os.getpid()
    assert receipt["reclaimed_candidates"] == [{
        "owner": "temporary-run", "path": str(candidate), "logical_bytes": 64,
    }]
    replay = governor.sweep([{
        "path": candidate, "class": "ephemeral", "owner": "temporary-run",
        "discovery": "allowlisted",
    }])
    assert replay["reclaimed_candidates"] == []
    assert replay["reclaimed_candidates_omitted"] == 0


def test_closed_package_download_caches_are_discovered_and_reclaimed(
    tmp_path: Path,
) -> None:
    relative_roots = {
        "homebrew-cache": "Library/Caches/Homebrew",
        "pip-cache": "Library/Caches/pip",
        "uv-cache": ".cache/uv",
        "bun-cache": "Library/Caches/bun",
        "burrito-cache": "Library/Caches/burrito_file_cache",
        "codex-runtime-cache": ".cache/codex-runtimes",
        "ffmpeg-cache": "Library/Caches/ffmpeg-static-nodejs",
        "npm-cache": ".npm/_cacache",
        "google-cache": "Library/Caches/Google",
    }
    paths = {}
    for owner, relative in relative_roots.items():
        path = tmp_path / relative
        path.mkdir(parents=True)
        (path / "artifact").write_bytes(b"regenerable package data")
        paths[owner] = path
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [
        item for item in governor.discover_candidates()
        if item.get("owner") in relative_roots
    ]
    result = governor.sweep(candidates)

    assert {item["owner"] for item in candidates} == set(relative_roots)
    assert all(not path.exists() for path in paths.values())
    assert result["reclaimed"] > 0
    assert result["errors"] == 0
    assert result["protected_deletions"] == 0
    assert len(result["reclaimed_candidates"]) == 8
    assert result["reclaimed_candidates_omitted"] == 1


@pytest.mark.parametrize("condition", ["closed", "open", "compiler", "changed"])
def test_darwin_clang_cache_reclaims_only_closed_generated_ast(
    tmp_path: Path, monkeypatch, request, condition: str,
) -> None:
    request.addfinalizer(lambda: shutil.rmtree(tmp_path, ignore_errors=True))
    home = tmp_path / "home"
    home.mkdir()
    cache = tmp_path / "C/clang/ModuleCache"
    modules = cache / "1J5J8FJPCELQN"
    modules.mkdir(parents=True)
    ast = b"\xcf\xfa\xed\xfe" + b"\0" * 8 + b"\x01\0\0\0" + b"\0" * 16 + b"__clangast\0"
    pcm = modules / "Foundation-3VW5DIPSHA0Z3.pcm"
    pcm.write_bytes(ast)
    retained = {
        modules / "Foundation.swiftmodule": b"compiled Swift module",
        modules / "modules.timestamp": b"metadata",
        modules / "unknown.pcm": b"unclassified original",
        modules / "shared.pcm": ast,
    }
    for path, content in retained.items():
        path.write_bytes(content)
    os.link(modules / "shared.pcm", tmp_path / "shared-original.pcm")
    (modules / "linked.pcm").symlink_to(pcm)
    monkeypatch.setattr(disk_cleanup, "_darwin_clang_cache", lambda _home: cache, raising=False)
    monkeypatch.setattr(disk_cleanup, "_clang_compiler_active", lambda: condition == "compiler", raising=False)

    def closed_probe(path):
        if path == pcm and condition == "changed":
            replacement = modules / "replacement.pcm"
            replacement.write_bytes(ast + b"new generation")
            replacement.replace(pcm)
        return "open" if path == pcm and condition == "open" else "confirmed-closed"

    governor = HostDiskGovernor(
        home=home, state_dir=home / "cleanup-state", lsof=closed_probe,
        usage=lambda: (0, 1),
    )
    candidates = [item for item in governor.discover_candidates()
                  if item.get("owner") == "clang-module-cache"]
    assert [item["path"] for item in candidates] == ([] if condition == "compiler" else [pcm])
    result = governor.sweep(candidates, write_receipt=False)
    assert pcm.exists() is (condition != "closed"), json.dumps(result)
    assert result["protected_deletions"] == 0
    assert all(path.read_bytes() == content for path, content in retained.items())
    assert modules.is_dir() and (modules / "linked.pcm").is_symlink()
    assert result["reclaimed"] > 0 if condition == "closed" else result["reclaimed"] == 0
    replay = governor.sweep([item for item in governor.discover_candidates()
                            if item.get("owner") == "clang-module-cache"], write_receipt=False)
    if condition == "closed":
        assert replay["reclaimed"] == 0


@pytest.mark.parametrize("git_marker_type", ["file", "directory"])
def test_temporary_worktree_candidate_is_preserved(
    tmp_path: Path, monkeypatch, git_marker_type: str
) -> None:
    temporary = tmp_path / "tmp"
    candidate = temporary / "cfo-active-worktree"
    candidate.mkdir(parents=True)
    git_marker = candidate / ".git"
    if git_marker_type == "file":
        git_marker.write_text("gitdir: /private/tmp/worktrees/active/.git/worktrees/active\n")
    else:
        git_marker.mkdir()
    progress = candidate / "progress.txt"
    progress.write_text("uncommitted work\n")
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = governor.discover_candidates()
    assert not any(Path(item["path"]).resolve() == candidate.resolve() for item in candidates)
    result = governor.sweep([{
        "path": candidate,
        "class": "ephemeral",
        "owner": "temporary-run",
        "discovery": "allowlisted",
    }])

    assert candidate.is_dir()
    assert progress.read_text() == "uncommitted work\n"
    assert result["preserved_reasons"] == {"unknown_artifact": 1}
    assert result["errors"] == 0
    assert result["protected_deletions"] == 0


def test_discover_stale_test_temporary_families_only(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    temporary = tmp_path / "T"
    home.mkdir()
    temporary.mkdir()
    additional_temporary = tmp_path / "additional-temp"
    additional_temporary.mkdir()
    old_paths = [
        temporary / "slide-pack-objects-9T7iWU",
        temporary / "slide-pack-image-cache-cta-QZWSuL",
        temporary / "slide-pack-workspace-mJXtWV",
        temporary / "slide-pack-fixture-bg-12345.png",
        temporary / f"pytest-of-{home.name}" / "pytest-42",
        additional_temporary / "slide-pack-workspace-WV9a0B",
        additional_temporary / f"pytest-of-{home.name}" / "pytest-44",
    ]
    for path in old_paths:
        if path.suffix == ".png":
            path.write_bytes(b"fixture")
        else:
            path.mkdir(parents=True)
            (path / "payload").write_bytes(b"temporary")
        os.utime(path, (1, 1))

    recent_paths = [
        temporary / "slide-pack-objects-recent1",
        temporary / f"pytest-of-{home.name}" / "pytest-43",
    ]
    for path in recent_paths:
        path.mkdir(parents=True)
    unknown = temporary / "cfo-old-run"
    unknown.mkdir()
    symlink = temporary / "slide-pack-objects-link01"
    symlink.symlink_to(old_paths[0], target_is_directory=True)

    monkeypatch.setattr(disk_cleanup, "_readonly_temp_root", lambda: temporary)
    monkeypatch.setattr(
        disk_cleanup,
        "_temporary_roots",
        lambda _primary: (temporary, additional_temporary),
    )
    governor = HostDiskGovernor(
        home=home,
        state_dir=home / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [
        item for item in governor.discover_candidates()
        if item.get("owner") == "temporary-run"
    ]

    assert {Path(item["path"]) for item in candidates} == set(old_paths)
    assert all(item["discovery"] == "allowlisted" for item in candidates)


@pytest.mark.parametrize("protected_filename", ["credentials.json", ".env.sh"])
def test_sweep_retires_only_registered_clean_merged_unleased_worktree(
    tmp_path: Path, monkeypatch, protected_filename: str,
) -> None:
    home = tmp_path / "home"
    repo = home / "Projects" / "life-manager-main"
    repo.mkdir(parents=True)

    def git(cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    subprocess.run(
        ["git", "init", "-b", "main", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    git(repo, "config", "user.name", "Disk Cleanup Test")
    git(repo, "config", "user.email", "disk-cleanup-test@example.invalid")
    (repo / "README.md").write_text("base\n")
    (repo / ".gitignore").write_text("ignored.bin\n")
    git(repo, "add", "README.md", ".gitignore")
    git(repo, "commit", "-m", "base")
    main_head = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/main", main_head)
    git(repo, "remote", "add", "origin", str(repo))

    worktrees = repo / ".worktrees"
    worktrees.mkdir()

    def add_detached(name: str) -> Path:
        path = worktrees / name
        git(repo, "worktree", "add", "--detach", str(path), main_head)
        return path

    safe = add_detached("zombie-safe")
    dirty = add_detached("dirty")
    (dirty / "README.md").write_text("uncommitted\n")
    untracked = add_detached("untracked")
    (untracked / "progress.txt").write_text("uncommitted\n")
    ignored = add_detached("ignored")
    (ignored / "ignored.bin").write_text("ignored progress\n")
    locked = add_detached("locked")
    git(repo, "worktree", "lock", "--reason", "active owner", str(locked))
    kept = add_detached("kept")
    (kept / ".anicca-keep").write_text("keep\n")
    unmerged = worktrees / "unmerged"
    git(repo, "worktree", "add", "-b", "unmerged", str(unmerged), main_head)
    (unmerged / "new-work.txt").write_text("unmerged work\n")
    git(unmerged, "add", "new-work.txt")
    git(unmerged, "commit", "-m", "unmerged work")
    leased = add_detached("leased")
    common = Path(git(repo, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = (repo / common).resolve()
    lease_path = common / "worktree-leases" / (
        hashlib.sha256(str(leased.resolve()).encode("utf-8")).hexdigest() + ".json"
    )
    lease_path.parent.mkdir(parents=True)
    lease_path.write_text("{}\n")

    protected_store = worktrees / "protected-store"
    git(repo, "worktree", "add", "-b", "protected-store", str(protected_store), main_head)
    (protected_store / "memory").mkdir()
    (protected_store / "memory" / "fact").write_text("keep")
    git(protected_store, "add", "memory/fact")
    git(protected_store, "commit", "-m", "protected store")
    protected_head = git(protected_store, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/main", protected_head)
    git(repo, "update-ref", "refs/heads/main", protected_head)
    credentials = worktrees / "credentials"
    git(repo, "worktree", "add", "-b", "credentials", str(credentials), main_head)
    (credentials / protected_filename).write_text("fixture credential must remain")
    git(credentials, "add", protected_filename)
    git(credentials, "commit", "-m", "fixture credentials")
    credential_head = git(credentials, "rev-parse", "HEAD")
    git(repo, "reset", "--hard", protected_head)
    git(repo, "merge", "--no-edit", "credentials")
    # Merge the two fixture branches as the authoritative local origin main.
    git(repo, "update-ref", "refs/remotes/origin/main", git(repo, "rev-parse", "HEAD"))

    governor = HostDiskGovernor(
        home=home,
        state_dir=home / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )
    candidates = [
        item for item in governor.discover_candidates()
        if item.get("owner") == "zombie-worktree"
    ]

    assert [Path(item["path"]) for item in candidates] == [safe]
    current_main = git(repo, "rev-parse", "refs/remotes/origin/main")
    git(repo, "update-ref", "refs/remotes/origin/main", main_head)
    assert governor._worktree_identity(safe) is None
    git(repo, "update-ref", "refs/remotes/origin/main", current_main)
    probe_calls = [0]
    def write_ignored_state_on_final_probe(_path):
        probe_calls[0] += 1
        if probe_calls[0] == 3:
            (safe / "state").mkdir()
            (safe / "state" / "events.jsonl").write_text("must remain")
        return "confirmed-closed"
    git(repo, "config", "core.excludesFile", str(repo / "fixture-ignore"))
    (repo / "fixture-ignore").write_text("state/\nfixture-ignore\n")
    governor.lsof = write_ignored_state_on_final_probe
    state_result = governor.sweep(candidates, write_receipt=False)
    assert safe.is_dir()
    assert (safe / "state" / "events.jsonl").read_text() == "must remain"
    (safe / "state" / "events.jsonl").unlink()
    (safe / "state").rmdir()
    clock = [0.0]
    governor.clock = lambda: clock[0]
    probe_calls[0] = 0
    def expire_on_final_probe(_path):
        probe_calls[0] += 1
        if probe_calls[0] == 3:
            clock[0] = 91.0
        return "confirmed-closed"
    governor.lsof = expire_on_final_probe
    expired = governor.sweep(candidates, write_receipt=False, deadline=90.0)
    assert safe.is_dir()
    assert expired["preserved_reasons"] == {"probe-budget-exhausted": 1}
    clock[0] = 0.0
    original_run = subprocess.run
    def timeout_remove(argv, **kwargs):
        if "worktree" in argv and "remove" in argv:
            assert 0 < kwargs["timeout"] <= 15
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return original_run(argv, **kwargs)
    governor.lsof = lambda _path: "confirmed-closed"
    with monkeypatch.context() as scoped:
        scoped.setattr(subprocess, "run", timeout_remove)
        timed_out = governor.sweep(candidates, write_receipt=False, deadline=90.0)
    assert safe.is_dir()
    assert timed_out["errors"] == 1
    assert timed_out["preserved_reasons"] == {"worktree_remove_timeout": 1}
    governor.lsof = lambda _path: "open"
    open_result = governor.sweep(candidates, write_receipt=False)
    assert safe.is_dir()
    assert open_result["preserved_reasons"] == {"open": 1}

    governor.lsof = lambda _path: "confirmed-closed"
    result = governor.sweep(candidates, write_receipt=False)

    assert not safe.exists()
    assert result["worktrees_retired"] == 1
    assert result["errors"] == 0
    assert result["protected_deletions"] == 0
    listing = git(repo, "worktree", "list", "--porcelain")
    assert str(safe) not in listing
    assert all(path.is_dir() for path in (dirty, untracked, ignored, locked, kept, unmerged, leased, protected_store, credentials))


@pytest.mark.parametrize("current_points_to_run", [True, False])
def test_stale_pytest_symlinks_are_unlinked_without_following_targets(tmp_path: Path, monkeypatch, current_points_to_run: bool) -> None:
    home = tmp_path / "home"
    home.mkdir()
    temporary = tmp_path / "T"
    run = temporary / f"pytest-of-{home.name}" / "pytest-42"
    run.mkdir(parents=True)
    outside = home / "memory"
    outside.mkdir()
    sentinel = outside / "fact"
    sentinel.write_text("must remain")
    large_file = outside / "large"
    large_file.write_bytes(b"x" * 4096)
    file_link = run / "file-link"
    file_link.symlink_to(large_file)
    link_bytes = file_link.lstat().st_size
    (run / "fixture-link").symlink_to(outside, target_is_directory=True)
    os.utime(run, (1, 1))
    other = run.parent / "pytest-43"
    other.mkdir()
    pointer = run.parent / "pytest-current"
    pointer.symlink_to(run.name if current_points_to_run else other.name, target_is_directory=True)
    monkeypatch.setattr(disk_cleanup, "_readonly_temp_root", lambda: temporary)
    monkeypatch.setattr(disk_cleanup, "_temporary_roots", lambda _primary: (temporary,))
    governor = HostDiskGovernor(home=home, state_dir=home / "state", lsof=lambda _path: "confirmed-closed", usage=lambda: (0, 1))
    candidates = [item for item in governor.discover_candidates() if item.get("owner") == "temporary-run"]
    result = governor.sweep(candidates, write_receipt=False)
    assert not run.exists()
    assert sentinel.read_text() == "must remain"
    assert large_file.stat().st_size == 4096
    assert result["reclaimed"] == link_bytes
    assert other.is_dir()
    assert pointer.is_symlink() is (not current_points_to_run)
    assert result["protected_deletions"] == 0


def test_stale_pytest_final_open_probe_is_fresh(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    temporary = tmp_path / "T"
    run = temporary / f"pytest-of-{home.name}" / "pytest-42"
    run.mkdir(parents=True)
    payload = run / "payload.bin"
    payload.write_bytes(b"active fixture")
    os.utime(run, (1, 1))
    monkeypatch.setattr(disk_cleanup, "_readonly_temp_root", lambda: temporary)
    monkeypatch.setattr(disk_cleanup, "_temporary_roots", lambda _primary: (temporary,))
    opened = [False]
    calls = []
    def snapshot():
        calls.append(opened[0])
        return frozenset({str(payload)}) if opened[0] else frozenset()
    cached_snapshot = disk_cleanup.lru_cache(maxsize=1)(snapshot)
    monkeypatch.setattr(disk_cleanup, "_open_paths", cached_snapshot)
    original_bytes = disk_cleanup._bytes
    handle = []
    def open_during_size_probe(path, **kwargs):
        handle.append(payload.open("rb"))
        opened[0] = True
        return original_bytes(path, **kwargs)
    monkeypatch.setattr(disk_cleanup, "_bytes", open_during_size_probe)
    governor = HostDiskGovernor(home=home, state_dir=home / "state", usage=lambda: (0, 1))
    candidates = [item for item in governor.discover_candidates() if item.get("owner") == "temporary-run"]
    try:
        result = governor.sweep(candidates, write_receipt=False)
        assert run.is_dir()
        assert result["preserved_reasons"] == {"open": 1}
        assert calls == [False, True]
    finally:
        for stream in handle: stream.close()
        cached_snapshot.cache_clear()


def test_core_simulator_assets_are_never_discovered_as_candidates(
    tmp_path: Path,
) -> None:
    simulator = tmp_path / "Library/Developer/CoreSimulator"
    device_data = simulator / "Devices/device/data"
    device_data.mkdir(parents=True)
    (device_data / "shipping-build.txt").write_text("preserve simulator data\n")
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = governor.discover_candidates()

    assert not any(
        Path(item["path"]).resolve() == simulator.resolve()
        or simulator.resolve() in Path(item["path"]).resolve().parents
        or Path(item["path"]).resolve() in simulator.resolve().parents
        for item in candidates
    )
    assert (device_data / "shipping-build.txt").read_text() == "preserve simulator data\n"


def test_open_or_protected_artifact_is_preserved(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    open_candidate = tmp_path / "tmp" / "capafy-hf-npm.open"
    open_candidate.mkdir(parents=True)
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(open_candidate.parent))
    protected = tmp_path / ".codex" / "logs.sqlite"
    protected.parent.mkdir()
    protected.write_bytes(b"x" * 64)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=state,
        lsof=lambda path: "open" if path == open_candidate else "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor.sweep(
        [
            {
                "path": open_candidate,
                "class": "ephemeral",
                "owner": "temporary-run",
                "discovery": "allowlisted",
            },
            {"path": protected, "class": "ephemeral", "owner": "unknown"},
        ]
    )

    assert result["reclaimed"] == 0
    assert open_candidate.exists()
    assert protected.exists()
    assert result["preserved"] == 2
    assert result["protected_deletions"] == 0


def test_protected_roots_never_enter_runtime_manifest(tmp_path: Path, monkeypatch) -> None:
    temporary = tmp_path / "tmp"
    disposable_candidate = temporary / "capafy-hf-npm.disposable"
    protected_candidates = []
    protected_paths = []
    for index, relative in enumerate(
        (
            ".claude/session.jsonl",
            ".codex/logs.sqlite",
            ".config/ai/config.json",
            ".openclaw/state/events.jsonl",
            ".openclaw/identity/device.json",
            ".openclaw/workspace/source.py",
            ".cloak/profile/Cookies",
            "anicca-rtdash/source.py",
            "anicca-monk-factory/source.py",
            "project/.git/config",
            "project/data.db",
            "project/credentials.json",
            "project/.env",
            "project/secret.key",
            "project/memory/fact",
            "project/publication-receipt.json",
        )
    ):
        candidate = temporary / f"capafy-hf-npm.protected-{index}"
        path = candidate / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("protected")
        protected_candidates.append(candidate)
        protected_paths.append(path)
    disposable_candidate.mkdir(parents=True)
    (disposable_candidate / "payload").write_text("regenerable")
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor.sweep(
        [
            *[
                {"path": candidate, "class": "ephemeral", "owner": "temporary-run", "discovery": "allowlisted"}
                for candidate in protected_candidates
            ],
            {"path": disposable_candidate, "class": "ephemeral", "owner": "temporary-run", "discovery": "allowlisted"},
        ]
    )

    assert all(candidate.exists() for candidate in protected_candidates)
    assert all(path.exists() for path in protected_paths)
    assert not disposable_candidate.exists()
    assert result["preserved_reasons"] == {"protected_descendant": len(protected_candidates)}
    assert result["reclaimed"] > 0
    assert result["protected_deletions"] == 0


def test_effect_recheck_preserves_new_protected_descendant(tmp_path: Path, monkeypatch) -> None:
    temporary = tmp_path / "tmp"
    candidate = temporary / "capafy-hf-npm.race"
    candidate.mkdir(parents=True)
    (candidate / "payload").write_text("regenerable")
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    real_bytes = disk_cleanup._bytes

    def inject_protected_descendant(path: Path, **kwargs) -> int | None:
        (path / ".env").write_text("credential")
        return real_bytes(path, **kwargs)

    monkeypatch.setattr(disk_cleanup, "_bytes", inject_protected_descendant)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor.sweep(
        [{"path": candidate, "class": "ephemeral", "owner": "temporary-run", "discovery": "allowlisted"}]
    )

    assert candidate.exists()
    assert (candidate / ".env").exists()
    assert result["preserved_reasons"] == {"protected_descendant": 1}


@pytest.mark.parametrize("max_age", [300, float("nan")])
def test_active_lease_preserves_artifact(tmp_path: Path, monkeypatch, max_age: float) -> None:
    temporary = tmp_path / "tmp"
    candidate = temporary / "capafy-hf-npm.lease-race"
    lease = temporary / "capafy-hf-npm.lease-race.lease"
    candidate.mkdir(parents=True)
    (candidate / "payload").write_text("in-flight")
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    real_bytes = disk_cleanup._bytes

    def start_lease(path: Path, **kwargs) -> int | None:
        lease.write_text("heartbeat")
        return real_bytes(path, **kwargs)

    monkeypatch.setattr(disk_cleanup, "_bytes", start_lease)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor.sweep(
        [{
            "path": candidate,
            "class": "ephemeral",
            "owner": "temporary-run",
            "discovery": "allowlisted",
            "lease": {"path": str(lease), "max_age_seconds": max_age},
        }]
    )

    assert candidate.exists()
    assert lease.exists()
    assert result["preserved_reasons"] == {"active_lease": 1}


def test_lease_probe_error_fails_closed(tmp_path: Path, monkeypatch) -> None:
    temporary = tmp_path / "tmp"
    candidate = temporary / "capafy-hf-npm.lease-probe-error"
    lease = temporary / "capafy-hf-npm.lease-probe-error.lease"
    candidate.mkdir(parents=True)
    (candidate / "payload").write_text("in-flight")
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    real_stat = Path.stat

    def deny_lease_probe(path: Path, *args, **kwargs):
        if path == lease:
            raise PermissionError("lease unreadable")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny_lease_probe)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: (_ for _ in ()).throw(AssertionError("lsof must not run after lease probe error")),
        usage=lambda: (0, 1),
    )

    result = governor.sweep(
        [{
            "path": candidate,
            "class": "ephemeral",
            "owner": "temporary-run",
            "discovery": "allowlisted",
            "lease": {"path": str(lease), "max_age_seconds": 300},
        }]
    )

    assert candidate.exists()
    assert result["preserved_reasons"] == {"active_lease": 1}


def test_expired_lease_open_path_is_preserved(tmp_path: Path, monkeypatch) -> None:
    temporary = tmp_path / "tmp"
    candidate = temporary / "capafy-hf-npm.open-race"
    lease = temporary / "expired.lease"
    candidate.mkdir(parents=True)
    (candidate / "payload").write_text("in-flight")
    lease.write_text("stale heartbeat")
    os.utime(lease, (1, 1))
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    probes = iter(("confirmed-closed", "open"))
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: next(probes),
        usage=lambda: (0, 1),
    )

    result = governor.sweep(
        [{
            "path": candidate,
            "class": "ephemeral",
            "owner": "temporary-run",
            "discovery": "allowlisted",
            "lease": {"path": str(lease), "max_age_seconds": 300},
        }]
    )

    assert candidate.exists()
    assert result["preserved_reasons"] == {"open": 1}


def test_unproved_candidate_is_preserved(tmp_path: Path) -> None:
    candidate = tmp_path / "important"
    candidate.write_bytes(b"do-not-delete")
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor.sweep([{"path": candidate, "class": "ephemeral", "owner": "operator"}])

    assert candidate.exists()
    assert result["preserved_reasons"] == {"unknown_artifact": 1}


def test_unknown_artifact_is_preserved_and_reported(tmp_path: Path, monkeypatch) -> None:
    temporary = tmp_path / "tmp"
    candidate = temporary / "cfo-unknown-class"
    candidate.mkdir(parents=True)
    (candidate / "payload").write_text("do-not-delete")
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))

    def unexpected_probe(_path: Path) -> str:
        raise AssertionError("unknown classes must be rejected before lsof")

    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=unexpected_probe,
        usage=lambda: (0, 1),
    )

    result = governor.sweep(
        [{"path": candidate, "class": "unknown", "owner": "temporary-run", "discovery": "allowlisted"}]
    )

    assert candidate.exists()
    assert result["reclaimed"] == 0
    assert result["preserved_reasons"] == {"unknown_class": 1}
    receipt = json.loads((tmp_path / "state" / "last-receipt.json").read_text())
    assert receipt["preserved_reasons"] == {"unknown_class": 1}
    assert receipt["protected_deletions"] == 0


def test_discovery_selects_only_codex_sparkle_installation_generations(tmp_path: Path) -> None:
    installation = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle/Installation"
    )
    generation = installation / "fBQSwumuD"
    generation.mkdir(parents=True)
    (generation / "ChatGPT.zip").write_bytes(b"x" * 32)
    launcher = installation.parent / "Launcher/QSYUe7BMl"
    launcher.mkdir(parents=True)
    (tmp_path / "Library/Caches/com.openai.codex/Cache.db").write_bytes(b"db")
    governor = HostDiskGovernor(home=tmp_path, state_dir=tmp_path / "state")

    candidates = governor.discover_candidates()

    assert [Path(item["path"]) for item in candidates if item["owner"] == "codex-app-updater"] == [generation]
    assert all(Path(item["path"]) != launcher for item in candidates)


def test_closed_codex_sparkle_installation_generation_is_reclaimed(tmp_path: Path) -> None:
    generation = (
        tmp_path
        / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle/Installation/fBQSwumuD"
    )
    source_like_payload = generation / "ChatGPT.app/Contents/Resources/main.js"
    source_like_payload.parent.mkdir(parents=True)
    source_like_payload.write_bytes(b"x" * 32)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [item for item in governor.discover_candidates() if item["owner"] == "codex-app-updater"]
    result = governor.sweep(candidates)

    assert result["reclaimed"] == 32
    assert not generation.exists()


def test_active_codex_sparkle_updater_keeps_installation_generation(
    tmp_path: Path, monkeypatch
) -> None:
    generation = (
        tmp_path
        / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle/Installation/fBQSwumuD"
    )
    generation.mkdir(parents=True)
    monkeypatch.setattr(disk_cleanup, "_sparkle_updater_active", lambda _root: True)
    governor = HostDiskGovernor(home=tmp_path, state_dir=tmp_path / "state")

    candidates = [item for item in governor.discover_candidates() if item["owner"] == "codex-app-updater"]

    assert candidates == []
    assert generation.exists()


@pytest.mark.parametrize(
    ("bundle_id", "application"),
    (
        ("com.openai.codex", "ChatGPT"),
        ("com.steipete.codexbar", "CodexBar"),
    ),
)
def test_stale_orphan_sparkle_updater_is_terminated_before_closed_generation_cleanup(
    tmp_path: Path, monkeypatch, bundle_id: str, application: str
) -> None:
    sparkle_root = (
        tmp_path / f"Library/Caches/{bundle_id}/org.sparkle-project.Sparkle"
    )
    generation = sparkle_root / "Installation/fBQSwumuD"
    generation.mkdir(parents=True)
    (generation / "ChatGPT.zip").write_bytes(b"x" * 32)
    (sparkle_root / "PersistentDownloads").mkdir()
    launcher = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(b"updater")
    updater_alive = True
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        assert argv[0] == "ps"
        command = f"{launcher} /Applications/{application}.app 0"
        if not updater_alive:
            stdout = ""
        else:
            stdout = (
                f"{os.getuid()} 4242 1 2-00:00:00 "
                f"Mon Sep 21 00:00:00 2026 {command}\n"
            )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    def fake_kill(pid: int, action: int) -> None:
        nonlocal updater_alive
        signals.append((pid, action))
        updater_alive = False

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", fake_kill)
    monkeypatch.setattr(
        disk_cleanup,
        "collect_host_inventory",
        lambda **_kwargs: {
            "coverage": {"mount_count": 1, "root_count": 1, "gaps": []},
        },
    )
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor.run_once()

    assert not generation.exists()
    assert signals == [(4242, signal.SIGTERM)]
    assert result["updater_recovery"] == {
        "already_exited": 0,
        "errors": 0,
        "observed": 1,
        "preserved": 0,
        "signaled": 1,
        "terminated": 1,
    }


def test_sparkle_recovery_does_not_signal_a_different_launcher_binary(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    generation = sparkle_root / "Installation/fBQSwumuD"
    generation.mkdir(parents=True)
    (generation / "ChatGPT.zip").write_bytes(b"x" * 32)
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    helper = sparkle_root / "Launcher/QSYUe7BMl/helper"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"helper")
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{helper} --inspect {updater}"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 "
            f"Mon Sep 21 00:00:00 2026 {command}\n"
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", lambda pid, action: signals.append((pid, action)))
    monkeypatch.setattr(
        disk_cleanup,
        "collect_host_inventory",
        lambda **_kwargs: {
            "coverage": {"mount_count": 1, "root_count": 1, "gaps": []},
        },
    )
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor.run_once()

    assert generation.exists()
    assert signals == []
    assert result["updater_recovery"]["observed"] == 0
    assert result["updater_recovery"]["errors"] == 1
    assert result["errors"] == 1


def test_stale_sparkle_updater_is_preserved_when_staged_path_is_a_symlink(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    external = tmp_path / "external-installation"
    external.mkdir()
    (sparkle_root / "Installation").parent.mkdir(parents=True)
    (sparkle_root / "Installation").symlink_to(external, target_is_directory=True)
    (sparkle_root / "PersistentDownloads").mkdir()
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    updater_alive = True
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{updater} /Applications/ChatGPT.app 0"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {command}\n"
            if updater_alive
            else ""
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    def fake_kill(pid: int, action: int) -> None:
        nonlocal updater_alive
        signals.append((pid, action))
        updater_alive = False

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", fake_kill)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert signals == []
    assert result == {
        "already_exited": 0,
        "errors": 1,
        "observed": 1,
        "preserved": 1,
        "signaled": 0,
        "terminated": 0,
    }


def test_stale_sparkle_updater_pid_reuse_is_preserved_before_signal(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    for name in ("Installation", "PersistentDownloads"):
        (sparkle_root / name).mkdir(parents=True)
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    ps_calls = 0
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        nonlocal ps_calls
        ps_calls += 1
        command = f"{updater} /Applications/ChatGPT.app 0"
        if "lstart=" in " ".join(argv):
            started = (
                "Mon Sep 21 00:00:00 2026"
                if ps_calls == 1
                else "Tue Sep 22 00:00:00 2026"
            )
            stdout = f"{os.getuid()} 4242 1 2-00:00:00 {started} {command}\n"
        else:
            stdout = f"{os.getuid()} 4242 1 2-00:00:00 {command}\n"
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", lambda pid, action: signals.append((pid, action)))
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert signals == []
    assert result["terminated"] == 0
    assert result["preserved"] == 1
    assert result["errors"] == 1


@pytest.mark.parametrize(
    "process_line",
    (
        "malformed {updater}",
        "{uid} nope 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {updater}",
        "{uid} 4242 1 unknown Mon Sep 21 00:00:00 2026 {updater}",
        "{uid} 4242 1 2-00:00:00 Nope Sep 21 00:00:00 2026 {updater}",
    ),
)
def test_malformed_relevant_sparkle_process_fails_closed_and_surfaces_error(
    tmp_path: Path, monkeypatch, process_line: str
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    generation = sparkle_root / "Installation/fBQSwumuD"
    generation.mkdir(parents=True)
    (generation / "ChatGPT.zip").write_bytes(b"x" * 32)
    (sparkle_root / "PersistentDownloads").mkdir()
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        stdout = process_line.format(uid=os.getuid(), updater=updater) + "\n"
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", lambda pid, action: signals.append((pid, action)))
    monkeypatch.setattr(
        disk_cleanup,
        "collect_host_inventory",
        lambda **_kwargs: {
            "coverage": {"mount_count": 1, "root_count": 1, "gaps": []},
        },
    )
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor.run_once()

    assert signals == []
    assert generation.exists()
    assert result["updater_recovery"]["errors"] == 1
    assert result["errors"] == 1


def test_sparkle_process_probe_stderr_fails_closed_and_surfaces_error(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    generation = sparkle_root / "Installation/fBQSwumuD"
    generation.mkdir(parents=True)
    (generation / "ChatGPT.zip").write_bytes(b"x" * 32)
    (sparkle_root / "PersistentDownloads").mkdir()
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    updater_alive = True
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{updater} /Applications/ChatGPT.app 0"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {command}\n"
            if updater_alive
            else ""
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "partial ps failure\n")

    def fake_kill(pid: int, action: int) -> None:
        nonlocal updater_alive
        signals.append((pid, action))
        updater_alive = False

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", fake_kill)
    monkeypatch.setattr(
        disk_cleanup,
        "collect_host_inventory",
        lambda **_kwargs: {
            "coverage": {"mount_count": 1, "root_count": 1, "gaps": []},
        },
    )
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor.run_once()

    assert signals == []
    assert generation.exists()
    assert result["updater_recovery"]["errors"] == 1
    assert result["errors"] == 1


@pytest.mark.parametrize(
    ("uid", "ppid", "elapsed"),
    (
        (os.getuid() + 1, 1, "2-00:00:00"),
        (os.getuid(), 4241, "2-00:00:00"),
        (os.getuid(), 1, "00:05:00"),
    ),
)
def test_sparkle_recovery_preserves_process_outside_signal_authority(
    tmp_path: Path,
    monkeypatch,
    uid: int,
    ppid: int,
    elapsed: str,
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    for name in ("Installation", "PersistentDownloads"):
        (sparkle_root / name).mkdir(parents=True)
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    updater_alive = True
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{updater} /Applications/ChatGPT.app 0"
        stdout = (
            f"{uid} 4242 {ppid} {elapsed} Mon Sep 21 00:00:00 2026 {command}\n"
            if updater_alive
            else ""
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    def fake_kill(pid: int, action: int) -> None:
        nonlocal updater_alive
        signals.append((pid, action))
        updater_alive = False

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", fake_kill)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert signals == []
    assert result["observed"] == 1
    assert result["preserved"] == 1
    assert result["errors"] == 0


def test_stale_sparkle_updater_is_preserved_when_a_staged_directory_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    (sparkle_root / "Installation").mkdir(parents=True)
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    updater_alive = True
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{updater} /Applications/ChatGPT.app 0"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {command}\n"
            if updater_alive
            else ""
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    def fake_kill(pid: int, action: int) -> None:
        nonlocal updater_alive
        signals.append((pid, action))
        updater_alive = False

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", fake_kill)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert signals == []
    assert result["preserved"] == 1
    assert result["errors"] == 1


def test_stale_sparkle_updater_is_preserved_when_bundle_ancestor_is_a_symlink(
    tmp_path: Path, monkeypatch
) -> None:
    real_bundle = tmp_path / "real-codex-cache"
    real_bundle.mkdir()
    bundle = tmp_path / "Library/Caches/com.openai.codex"
    bundle.parent.mkdir(parents=True)
    bundle.symlink_to(real_bundle, target_is_directory=True)
    sparkle_root = bundle / "org.sparkle-project.Sparkle"
    for name in ("Installation", "PersistentDownloads"):
        (sparkle_root / name).mkdir(parents=True)
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    updater_alive = True
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{updater.resolve()} /Applications/ChatGPT.app 0"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {command}\n"
            if updater_alive
            else ""
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    def fake_kill(pid: int, action: int) -> None:
        nonlocal updater_alive
        signals.append((pid, action))
        updater_alive = False

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", fake_kill)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert signals == []
    assert result["preserved"] == 1
    assert result["errors"] == 1


def test_stale_sparkle_updater_is_preserved_when_staged_inode_changes_after_probe(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    installation = sparkle_root / "Installation"
    for path in (installation, sparkle_root / "PersistentDownloads"):
        path.mkdir(parents=True)
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    updater_alive = True
    lsof_calls = 0
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{updater} /Applications/ChatGPT.app 0"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {command}\n"
            if updater_alive
            else ""
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    def fake_lsof(_path: Path) -> str:
        nonlocal lsof_calls
        lsof_calls += 1
        if lsof_calls == 2:
            installation.rmdir()
            installation.mkdir()
        return "confirmed-closed"

    def fake_kill(pid: int, action: int) -> None:
        nonlocal updater_alive
        signals.append((pid, action))
        updater_alive = False

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", fake_kill)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=fake_lsof,
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert signals == []
    assert result["preserved"] == 1
    assert result["errors"] == 1


def test_sparkle_generation_under_symlinked_bundle_is_not_discovered(
    tmp_path: Path, monkeypatch
) -> None:
    real_bundle = tmp_path / "real-codex-cache"
    generation = (
        real_bundle / "org.sparkle-project.Sparkle/Installation/fBQSwumuD"
    )
    generation.mkdir(parents=True)
    bundle = tmp_path / "Library/Caches/com.openai.codex"
    bundle.parent.mkdir(parents=True)
    bundle.symlink_to(real_bundle, target_is_directory=True)
    monkeypatch.setattr(disk_cleanup, "_sparkle_updater_active", lambda _root: False)
    governor = HostDiskGovernor(home=tmp_path, state_dir=tmp_path / "state")

    candidates = [
        item
        for item in governor.discover_candidates()
        if item["owner"] == "codex-app-updater"
    ]

    assert candidates == []
    assert generation.exists()


def test_sparkle_candidate_parent_replacement_after_probe_is_preserved(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    installation = sparkle_root / "Installation"
    generation = installation / "fBQSwumuD"
    generation.mkdir(parents=True)
    (generation / "internal.zip").write_bytes(b"x" * 32)
    external_installation = tmp_path / "external-installation"
    external_generation = external_installation / generation.name
    external_generation.mkdir(parents=True)
    (external_generation / "external.zip").write_bytes(b"x" * 64)
    original_installation = sparkle_root / "Installation-original"
    lsof_calls = 0

    def replace_parent_on_first_probe(_path: Path) -> str:
        nonlocal lsof_calls
        lsof_calls += 1
        if lsof_calls == 1:
            installation.rename(original_installation)
            installation.symlink_to(external_installation, target_is_directory=True)
        return "confirmed-closed"

    monkeypatch.setattr(disk_cleanup, "_sparkle_updater_active", lambda _root: False)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=replace_parent_on_first_probe,
        usage=lambda: (0, 1),
    )
    candidates = [
        item
        for item in governor.discover_candidates()
        if item["owner"] == "codex-app-updater"
    ]

    result = governor.sweep(candidates)

    assert (original_installation / generation.name).exists()
    assert external_generation.exists()
    assert result["reclaimed"] == 0
    assert result["preserved"] == 1
    assert result["errors"] == 1


def test_sparkle_updater_sigterm_timeout_is_preserved_as_error(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    for name in ("Installation", "PersistentDownloads"):
        (sparkle_root / name).mkdir(parents=True)
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{updater} /Applications/ChatGPT.app 0"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {command}\n"
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    ticks = iter((0.0, 6.0))
    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", lambda pid, action: signals.append((pid, action)))
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
        clock=lambda: next(ticks),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert signals == [(4242, signal.SIGTERM)]
    assert result["signaled"] == 1
    assert result["terminated"] == 0
    assert result["preserved"] == 1
    assert result["errors"] == 1


def test_sparkle_updater_process_lookup_error_is_read_back_as_already_exited(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    for name in ("Installation", "PersistentDownloads"):
        (sparkle_root / name).mkdir(parents=True)
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    ps_calls = 0

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        nonlocal ps_calls
        ps_calls += 1
        command = f"{updater} /Applications/ChatGPT.app 0"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {command}\n"
            if ps_calls <= 2
            else ""
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    def process_gone(_pid: int, _action: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", process_gone)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert result["signaled"] == 0
    assert result["terminated"] == 0
    assert result["already_exited"] == 1
    assert result["preserved"] == 0
    assert result["errors"] == 0


def test_sparkle_updater_process_lookup_error_with_same_process_is_preserved(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    for name in ("Installation", "PersistentDownloads"):
        (sparkle_root / name).mkdir(parents=True)
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{updater} /Applications/ChatGPT.app 0"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {command}\n"
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    def lookup_failed(_pid: int, _action: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", lookup_failed)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert result["signaled"] == 0
    assert result["terminated"] == 0
    assert result["already_exited"] == 0
    assert result["preserved"] == 1
    assert result["errors"] == 1


def test_missing_sparkle_root_is_no_work_without_process_probe(
    tmp_path: Path, monkeypatch
) -> None:
    process_probes = 0

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        nonlocal process_probes
        process_probes += 1
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )

    assert process_probes == 0
    assert result == {
        "already_exited": 0,
        "errors": 0,
        "observed": 0,
        "preserved": 0,
        "signaled": 0,
        "terminated": 0,
    }


@pytest.mark.parametrize("target", ("missing-cache", "com.openai.codex"))
def test_dangling_or_looped_sparkle_ancestor_is_preserved_as_error(
    tmp_path: Path, monkeypatch, target: str
) -> None:
    bundle = tmp_path / "Library/Caches/com.openai.codex"
    bundle.parent.mkdir(parents=True)
    bundle.symlink_to(target, target_is_directory=True)
    process_probes = 0

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        nonlocal process_probes
        process_probes += 1
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(
        bundle / "org.sparkle-project.Sparkle"
    )

    assert process_probes == 0
    assert result["preserved"] == 1
    assert result["errors"] == 1


def test_looped_sparkle_launcher_with_exact_process_is_preserved_without_crash(
    tmp_path: Path, monkeypatch
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    for name in ("Installation", "PersistentDownloads"):
        (sparkle_root / name).mkdir(parents=True)
    launcher = sparkle_root / "Launcher"
    launcher.symlink_to("Launcher", target_is_directory=True)
    updater = launcher / "QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{updater} /Applications/ChatGPT.app 0"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {command}\n"
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", lambda pid, action: signals.append((pid, action)))
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert signals == []
    assert result["observed"] == 1
    assert result["preserved"] == 1
    assert result["errors"] == 1


def test_symlinked_sparkle_root_is_preserved_as_error_without_process(
    tmp_path: Path, monkeypatch
) -> None:
    real_root = tmp_path / "real-sparkle"
    real_root.mkdir()
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    sparkle_root.parent.mkdir(parents=True)
    sparkle_root.symlink_to(real_root, target_is_directory=True)
    monkeypatch.setattr(
        disk_cleanup.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        usage=lambda: (0, 1),
    )

    result = governor._reconcile_stale_sparkle_updaters(sparkle_root)

    assert result["observed"] == 0
    assert result["preserved"] == 1
    assert result["errors"] == 1


@pytest.mark.parametrize(
    ("probe_state", "expected_errors"),
    (("open", 0), ("probe-error", 2)),
)
def test_sparkle_staging_probe_blocks_signal_and_propagates_errors(
    tmp_path: Path,
    monkeypatch,
    probe_state: str,
    expected_errors: int,
) -> None:
    sparkle_root = (
        tmp_path / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle"
    )
    generation = sparkle_root / "Installation/fBQSwumuD"
    generation.mkdir(parents=True)
    (sparkle_root / "PersistentDownloads").mkdir()
    updater = sparkle_root / "Launcher/QSYUe7BMl/Updater.app/Contents/MacOS/Updater"
    updater.parent.mkdir(parents=True)
    updater.write_bytes(b"updater")
    signals: list[tuple[int, int]] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        command = f"{updater} /Applications/ChatGPT.app 0"
        stdout = (
            f"{os.getuid()} 4242 1 2-00:00:00 Mon Sep 21 00:00:00 2026 {command}\n"
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(disk_cleanup.os, "kill", lambda pid, action: signals.append((pid, action)))
    monkeypatch.setattr(
        disk_cleanup,
        "collect_host_inventory",
        lambda **_kwargs: {
            "coverage": {"mount_count": 1, "root_count": 1, "gaps": []},
        },
    )
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: probe_state,
        usage=lambda: (0, 1),
    )

    result = governor.run_once()

    assert signals == []
    assert generation.exists()
    assert result["updater_recovery"]["preserved"] == 1
    assert result["updater_recovery"]["errors"] == expected_errors
    assert result["errors"] == expected_errors


def test_open_codex_sparkle_installation_generation_is_preserved(tmp_path: Path) -> None:
    generation = (
        tmp_path
        / "Library/Caches/com.openai.codex/org.sparkle-project.Sparkle/Installation/fBQSwumuD"
    )
    generation.mkdir(parents=True)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "open",
        usage=lambda: (0, 1),
    )

    candidates = [item for item in governor.discover_candidates() if item["owner"] == "codex-app-updater"]
    result = governor.sweep(candidates)

    assert generation.exists()
    assert result["preserved_reasons"] == {"open": 1}


def test_discovery_includes_exact_regenerable_model_and_runtime_caches(tmp_path: Path) -> None:
    for relative in (
        ".cache/codex-runtimes",
        ".cache/whisper",
        ".cache/life-manager/camofox-browser",
        "Library/Caches/camoufox",
        "Library/Caches/org.swift.swiftpm",
    ):
        (tmp_path / relative).mkdir(parents=True)
    governor = HostDiskGovernor(home=tmp_path, state_dir=tmp_path / "state")

    owners = {item["owner"]: Path(item["path"]) for item in governor.discover_candidates()}

    assert owners["codex-runtime-cache"] == tmp_path / ".cache/codex-runtimes"
    assert owners["whisper-model-cache"] == tmp_path / ".cache/whisper"
    assert owners["camofox-browser-cache"] == tmp_path / ".cache/life-manager/camofox-browser"
    assert owners["camoufox-sdk-cache"] == tmp_path / "Library/Caches/camoufox"
    assert owners["swiftpm-cache"] == tmp_path / "Library/Caches/org.swift.swiftpm"


def test_xcode_derived_data_is_exact_and_requires_closed_lsof(tmp_path: Path) -> None:
    derived_data = tmp_path / "Library/Developer/Xcode/DerivedData"
    generated_source = derived_data / "Anicca/Build/Intermediates.noindex/DerivedSources/Generated.swift"
    generated_source.parent.mkdir(parents=True)
    generated_source.write_bytes(b"generated build output")
    archive = tmp_path / "Library/Developer/Xcode/Archives"
    archive.mkdir(parents=True)
    (archive / "user.xcarchive").write_bytes(b"preserve")

    open_governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "open",
        usage=lambda: (0, 1),
    )
    candidates = [
        item for item in open_governor.discover_candidates()
        if item["owner"] == "xcode-derived-data-cache"
    ]

    assert [Path(item["path"]) for item in candidates] == [derived_data]
    open_result = open_governor.sweep(candidates)

    assert derived_data.exists()
    assert open_result["preserved_reasons"] == {"open": 1}

    closed_governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )
    closed_candidates = [
        item for item in closed_governor.discover_candidates()
        if item["owner"] == "xcode-derived-data-cache"
    ]
    closed_result = closed_governor.sweep(closed_candidates)

    assert not derived_data.exists()
    assert archive.exists()
    assert closed_result["errors"] == 0
    assert closed_result["protected_deletions"] == 0


def test_camoufox_sdk_cache_requires_closed_lsof_before_reclaim(tmp_path: Path) -> None:
    cache = tmp_path / "Library/Caches/camoufox"
    executable = cache / "Camoufox.app/Contents/MacOS/camoufox"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"browser-sdk")
    (cache / "GeoLite2-City.mmdb").write_bytes(b"database")
    (cache / "version.json").write_text("{}")

    open_governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "open",
        usage=lambda: (0, 1),
    )
    open_candidates = [
        item for item in open_governor.discover_candidates()
        if item["owner"] == "camoufox-sdk-cache"
    ]
    assert len(open_candidates) == 1
    open_result = open_governor.sweep(open_candidates)
    assert cache.exists()
    assert open_result["preserved_reasons"] == {"open": 1}

    closed_governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )
    closed_candidates = [
        item for item in closed_governor.discover_candidates()
        if item["owner"] == "camoufox-sdk-cache"
    ]
    closed_result = closed_governor.sweep(closed_candidates)
    assert not cache.exists()
    assert closed_result["errors"] == 0


def test_closed_camofox_fallback_cache_with_source_is_reclaimed(tmp_path: Path) -> None:
    cache = tmp_path / ".cache/life-manager/camofox-browser"
    source = cache / "pinned/source"
    source.mkdir(parents=True)
    (source / "server.js").write_bytes(b"x" * 32)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [item for item in governor.discover_candidates()
                  if item["owner"] == "camofox-browser-cache"]
    result = governor.sweep(candidates)

    assert not cache.exists()
    assert result["reclaimed"] == 32


def test_open_whisper_cache_is_preserved(tmp_path: Path) -> None:
    cache = tmp_path / ".cache/whisper"
    cache.mkdir(parents=True)
    (cache / "small.pt").write_bytes(b"x" * 32)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "open",
        usage=lambda: (0, 1),
    )

    candidates = [item for item in governor.discover_candidates()
                  if item["owner"] == "whisper-model-cache"]
    result = governor.sweep(candidates)

    assert cache.exists()
    assert result["preserved_reasons"] == {"open": 1}


def test_closed_exact_runtime_cache_with_source_named_dependency_is_reclaimed(tmp_path: Path) -> None:
    cache = tmp_path / ".cache/codex-runtimes"
    dependency = cache / "dependencies/source"
    dependency.mkdir(parents=True)
    (dependency / "payload.bin").write_bytes(b"x" * 32)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [item for item in governor.discover_candidates()
                  if item["owner"] == "codex-runtime-cache"]
    result = governor.sweep(candidates)

    assert not cache.exists()
    assert result["reclaimed"] == 32


def test_closed_browser_clone_with_source_named_dependency_is_reclaimed(
    tmp_path: Path, monkeypatch
) -> None:
    temporary = tmp_path / "T"
    temporary.mkdir()
    clone = (
        tmp_path / "X/com.google.Chrome.code_sign_clone/code_sign_clone.abc123"
    )
    clone.mkdir(parents=True)
    (clone / "runtime.js").write_bytes(b"x" * 32)
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [
        item for item in governor.discover_candidates() if item["owner"] == "browser"
    ]
    result = governor.sweep(candidates)

    assert not clone.exists()
    assert result["reclaimed"] == 32


def test_discover_and_sweep_allowlisted_tmp_cache_when_gettempdir_probe_fails(
    tmp_path: Path, monkeypatch
) -> None:
    with tempfile.TemporaryDirectory(prefix="lm-readonly-temp-probe-", dir="/tmp") as directory:
        temporary = Path(directory)
        candidate = temporary / "capafy-hf-npm.no-tempfile-probe"
        candidate.mkdir(parents=True)
        (candidate / "payload").write_bytes(b"x" * 64)
        os.utime(candidate, (1, 1))
        monkeypatch.setenv("TMPDIR", str(temporary))

        def no_writable_temporary_directory() -> str:
            raise FileNotFoundError("No usable temporary directory found")

        monkeypatch.setattr(
            disk_cleanup.tempfile, "gettempdir", no_writable_temporary_directory
        )
        governor = HostDiskGovernor(
            home=tmp_path,
            state_dir=tmp_path / "state",
            lsof=lambda _path: "confirmed-closed",
            usage=lambda: (0, 1),
        )

        candidates = [
            item for item in governor.discover_candidates()
            if item.get("owner") == "temporary-run"
        ]
        assert [Path(item["path"]).resolve() for item in candidates] == [candidate.resolve()]

        result = governor.sweep(candidates, write_receipt=False)

        assert not candidate.exists()
        assert result["reclaimed"] == 64


def test_discover_candidates_uses_darwin_user_temp_when_tmpdir_unset(
    tmp_path: Path, monkeypatch, request
) -> None:
    darwin_temp = tmp_path / "darwin-user" / "T"
    clone = (
        darwin_temp.parent
        / "X/com.google.Chrome.code_sign_clone/code_sign_clone.launchd"
    )
    open_clone = (
        darwin_temp.parent
        / "X/org.chromium.Chromium.code_sign_clone/code_sign_clone.open"
    )
    darwin_temp.mkdir(parents=True)
    clone.mkdir(parents=True)
    (clone / "runtime.js").write_bytes(b"x" * 32)
    open_clone.mkdir(parents=True)
    (open_clone / "runtime.js").write_bytes(b"y" * 16)
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.delenv("TMP", raising=False)
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.setattr(disk_cleanup.sys, "platform", "darwin")
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: "/tmp")
    disk_cleanup._browser_clone_roots.cache_clear()
    request.addfinalizer(disk_cleanup._browser_clone_roots.cache_clear)
    getconf_calls: list[list[str]] = []

    def fake_getconf(argv, **kwargs):
        getconf_calls.append(argv)
        assert kwargs.get("timeout")
        return subprocess.CompletedProcess(
            argv, 0, stdout=f"{darwin_temp}/\n", stderr=""
        )

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_getconf)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda path: "open" if path == open_clone else "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [
        item for item in governor.discover_candidates() if item["owner"] == "browser"
    ]
    result = governor.sweep(candidates)

    candidate_paths = [Path(item["path"]) for item in candidates]
    assert candidate_paths.count(clone) == 1
    assert candidate_paths.count(open_clone) == 1
    assert not clone.exists()
    assert open_clone.exists()
    assert result["reclaimed"] == 32
    assert result["preserved_reasons"] == {"open": 1}
    assert result["errors"] == 0
    assert result["protected_deletions"] == 0
    assert getconf_calls == [["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"]]


def test_browser_clone_probe_distinguishes_open_apfs_clone_from_closed_clone(
    tmp_path: Path, monkeypatch
) -> None:
    temporary = tmp_path / "T"
    temporary.mkdir()
    collection = tmp_path / "X/org.chromium.Chromium.code_sign_clone"
    open_clone = collection / "code_sign_clone.open"
    closed_clone = collection / "code_sign_clone.closed"
    open_clone.mkdir(parents=True)
    closed_clone.mkdir(parents=True)
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = f"n{open_clone}/Chromium.app.bundle/Contents/MacOS/Chromium\n"
        stderr = ""

    def record(argv, **_kwargs):
        calls.append(argv)
        return Result()

    monkeypatch.setattr(disk_cleanup.subprocess, "run", record)
    disk_cleanup._open_paths.cache_clear()

    assert disk_cleanup._default_lsof(open_clone) == "open"
    assert disk_cleanup._default_lsof(closed_clone) == "confirmed-closed"
    assert calls == [["/usr/sbin/lsof", "-nP", "-Fn"]]
    disk_cleanup._open_paths.cache_clear()


def test_release_probe_uses_one_global_lsof_instead_of_walking_the_tree(tmp_path: Path, monkeypatch) -> None:
    release = tmp_path / "loops/releases/20260828T010101-aaaaaaaa"
    release.mkdir(parents=True)
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = f"p123\nn{release}/bin/loop.sh\n"
        stderr = ""

    def record(argv, **_kwargs):
        calls.append(argv)
        return Result()

    monkeypatch.setattr(disk_cleanup.subprocess, "run", record)
    disk_cleanup._open_paths.cache_clear()

    assert disk_cleanup._default_lsof(release) == "open"
    assert calls == [["/usr/sbin/lsof", "-nP", "-Fn"]]
    disk_cleanup._open_paths.cache_clear()


def test_exact_cache_probe_uses_one_global_lsof_instead_of_walking_the_tree(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "Codex"
    cache.mkdir(parents=True)
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = f"p123\nn{cache}/Contents/cache.db\n"
        stderr = ""

    def record(argv, **_kwargs):
        calls.append(argv)
        return Result()

    monkeypatch.setattr(disk_cleanup.subprocess, "run", record)
    disk_cleanup._open_paths.cache_clear()

    assert disk_cleanup._default_lsof(cache) == "open"
    assert calls == [["/usr/sbin/lsof", "-nP", "-Fn"]]
    disk_cleanup._open_paths.cache_clear()


def test_exact_cache_probe_reports_closed_from_global_lsof_snapshot(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "Codex"
    cache.mkdir(parents=True)
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "p123\nn/tmp/other-process\n"
        stderr = ""

    def record(argv, **_kwargs):
        calls.append(argv)
        return Result()

    monkeypatch.setattr(disk_cleanup.subprocess, "run", record)
    disk_cleanup._open_paths.cache_clear()

    assert disk_cleanup._default_lsof(cache) == "confirmed-closed"
    assert calls == [["/usr/sbin/lsof", "-nP", "-Fn"]]
    disk_cleanup._open_paths.cache_clear()


def test_exact_cache_probe_fails_closed_when_global_lsof_reports_stderr(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "Codex"
    cache.mkdir(parents=True)
    calls: list[list[str]] = []

    class Result:
        returncode = 1
        stdout = ""
        stderr = "permission denied"

    def record(argv, **_kwargs):
        calls.append(argv)
        return Result()

    monkeypatch.setattr(disk_cleanup.subprocess, "run", record)
    disk_cleanup._open_paths.cache_clear()

    assert disk_cleanup._default_lsof(cache) == "probe-error"
    assert calls == [["/usr/sbin/lsof", "-nP", "-Fn"]]
    disk_cleanup._open_paths.cache_clear()


def test_release_retention_keeps_referenced_and_current_generation(tmp_path: Path) -> None:
    releases = tmp_path / "loops" / "releases"
    releases.mkdir(parents=True)
    names = [
        "20260828T010101-aaaaaaaa",  # oldest, unreferenced -> reclaimable
        "20260829T010101-bbbbbbbb",  # referenced by the protected list
        "20260830T010101-cccccccc",  # closed and unreferenced -> reclaimable
        "20260831T010101-dddddddd",
    ]
    for name in names:
        generation = releases / name
        generation.mkdir()
        (generation / "payload").write_bytes(b"x" * 16)
    (tmp_path / "loops" / "current").symlink_to(releases / names[3])
    protected = tmp_path / ".local/state/life-manager/protected-releases.json"
    protected.parent.mkdir(parents=True)
    protected.write_text(json.dumps([str(releases / names[1])]), encoding="utf-8")
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [item for item in governor.discover_candidates() if item["owner"] == "release-retention"]
    governor.sweep(candidates)

    assert not (releases / names[0]).exists()
    assert (releases / names[1]).exists()
    assert not (releases / names[2]).exists()
    assert (releases / names[3]).exists()


def test_read_only_release_export_is_still_reclaimable(tmp_path: Path) -> None:
    releases = tmp_path / "loops" / "releases"
    releases.mkdir(parents=True)
    stale = releases / "20260828T010101-aaaaaaaa"
    (stale / "bin").mkdir(parents=True)
    (stale / "bin" / "loop.sh").write_bytes(b"x" * 8)
    for name in ("20260830T010101-cccccccc", "20260831T010101-dddddddd"):
        (releases / name).mkdir()
    # cut-loop-release.sh exports releases chmod -R a-w
    for directory in (stale / "bin", stale):
        directory.chmod(0o555)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [item for item in governor.discover_candidates() if item["owner"] == "release-retention"]
    result = governor.sweep(candidates)

    assert not stale.exists()
    assert result["errors"] == 0


def test_release_retention_preserves_memory_and_state_jsonl_but_reclaims_plain_release(
    tmp_path: Path,
) -> None:
    releases = tmp_path / "loops" / "releases"
    releases.mkdir(parents=True)
    memory_release = releases / "20260828T010101-aaaaaaaa"
    state_release = releases / "20260829T010101-bbbbbbbb"
    dangling_memory_release = releases / "20260830T010101-cccccccc"
    dangling_state_release = releases / "20260831T010101-dddddddd"
    dependency_release = releases / "20260901T010101-eeeeeeee"
    plain_release = releases / "20260902T010101-ffffffff"
    current_release = releases / "20260903T010101-00000000"
    for index, path in enumerate((
        memory_release, state_release, dangling_memory_release, dangling_state_release,
        dependency_release, plain_release, current_release,
    )):
        path.mkdir()
        (path / "RELEASE.json").write_text(json.dumps({"sha": f"{index:040x}"}))
    (memory_release / "memory").mkdir()
    (memory_release / "memory" / "owner.md").write_text("private memory")
    state = state_release / "nested" / "state"
    state.mkdir(parents=True)
    (state / "events.jsonl").write_text("{}\n")
    (dangling_memory_release / "memory").symlink_to(
        tmp_path / "missing-memory", target_is_directory=True
    )
    dangling_state = dangling_state_release / "nested"
    dangling_state.mkdir()
    (dangling_state / "state").symlink_to(
        tmp_path / "missing-state", target_is_directory=True
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "owner.md").write_text("keep target")
    (dependency_release / "node_modules").symlink_to(outside)
    (plain_release / "bin").mkdir()
    (plain_release / "bin" / "loop.sh").write_text("#!/bin/sh\n")
    (plain_release / "memory").write_text("ordinary file")
    (tmp_path / "loops" / "current").symlink_to(current_release)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [item for item in governor.discover_candidates() if item["owner"] == "release-retention"]
    result = governor.sweep(candidates)

    assert memory_release.exists()
    assert state_release.exists()
    assert dangling_memory_release.exists()
    assert dangling_state_release.exists()
    assert not dependency_release.exists()
    assert not plain_release.exists()
    assert current_release.exists()
    assert (outside / "owner.md").exists()
    assert result["preserved_reasons"] == {"protected_descendant": 4}
    assert result["errors"] == 0


def test_release_named_only_by_a_launchd_plist_is_preserved(tmp_path: Path) -> None:
    releases = tmp_path / "loops" / "releases"
    releases.mkdir(parents=True)
    launched = "20260828T010101-aaaaaaaa"
    for name in (launched, "20260830T010101-cccccccc", "20260831T010101-dddddddd"):
        (releases / name).mkdir()
    agents = tmp_path / "Library/LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "ai.anicca.example.plist").write_text(
        f"<string>{releases / launched}/bin/loop.sh</string>", encoding="utf-8"
    )
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (0, 1),
    )

    candidates = [item for item in governor.discover_candidates() if item["owner"] == "release-retention"]
    governor.sweep(candidates)

    assert (releases / launched).exists()


def test_lsof_stderr_is_probe_error(monkeypatch) -> None:
    class Result:
        returncode = 1
        stdout = ""
        stderr = "permission denied"

    monkeypatch.setattr(disk_cleanup.subprocess, "run", lambda *args, **kwargs: Result())
    assert disk_cleanup._default_lsof(Path("/tmp/unknown")) == "probe-error"


def test_lsof_failure_fails_closed(tmp_path: Path, monkeypatch) -> None:
    temporary = tmp_path / "tmp"
    candidate = temporary / "capafy-hf-npm.lsof-error"
    candidate.mkdir(parents=True)
    (candidate / "payload").write_text("in-flight")
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "probe-error",
        usage=lambda: (0, 1),
    )

    result = governor.sweep(
        [{"path": candidate, "class": "ephemeral", "owner": "temporary-run", "discovery": "allowlisted"}]
    )

    assert candidate.exists()
    assert result["errors"] == 1
    assert result["preserved_reasons"] == {"probe-error": 1}


def test_cli_candidate_is_rejected(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "disk_cleanup.py"
    result = subprocess.run(
        [sys.executable, str(script), "--home", str(tmp_path), "--candidate", str(tmp_path / "important")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "--candidate is disabled" in result.stderr or "--candidate is disabled" in result.stdout


@pytest.mark.parametrize(
    "cleanup_result,capacity_status,expected_returncode",
    (
        ({"errors": 0, "protected_deletions": 0, "free_after": 2 * GiB - 1,
          "disk_writers_stop": {"status": "absent"}}, "unmet", 0),
        ({"errors": 0, "protected_deletions": 0}, "unknown", 1),
        ({"errors": 1, "protected_deletions": 0, "free_after": 12 * GiB,
          "disk_writers_stop": {"status": "absent"}}, "met", 1),
        ({"errors": 0, "protected_deletions": 1, "free_after": 12 * GiB,
          "disk_writers_stop": {"status": "absent"}}, "met", 1),
        ({"errors": 0, "protected_deletions": 0, "free_after": 2 * GiB,
          "disk_writers_stop": {"status": "absent"}}, "met", 0),
    ),
)
def test_cli_outcome_tracks_capacity_and_cleanup_errors(
    tmp_path: Path, monkeypatch, capsys, cleanup_result: dict,
    capacity_status: str, expected_returncode: int,
) -> None:
    class FakeGovernor:
        def __init__(self, **_kwargs) -> None:
            pass

        def acquire_lock(self) -> bool:
            return True

        def run_once(self) -> dict:
            return dict(cleanup_result)

        def release_lock(self) -> None:
            pass

    monkeypatch.setattr(disk_cleanup, "HostDiskGovernor", FakeGovernor)
    monkeypatch.setattr(
        disk_cleanup.sys,
        "argv",
        ["disk_cleanup.py", "--home", str(tmp_path), "--state-dir", str(tmp_path / "state")],
    )

    assert disk_cleanup.main() == expected_returncode
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is (expected_returncode == 0)
    assert output["capacity_recovery"] == {
        "status": capacity_status,
        "recovery_floor_bytes": 2 * GiB,
    }
    assert output.get("errors", 0) == cleanup_result.get("errors", 0)
    assert output.get("protected_deletions", 0) == cleanup_result.get("protected_deletions", 0)


def test_cli_reports_busy_lock_without_running_a_cleanup(tmp_path: Path, monkeypatch, capsys) -> None:
    class FakeGovernor:
        def __init__(self, **_kwargs) -> None:
            pass

        def acquire_lock(self) -> bool:
            return False

        def run_once(self) -> dict:
            raise AssertionError("busy owner must not run cleanup")

        def release_lock(self) -> None:
            raise AssertionError("busy owner has no lock to release")

    monkeypatch.setattr(disk_cleanup, "HostDiskGovernor", FakeGovernor)
    monkeypatch.setattr(
        disk_cleanup.sys,
        "argv",
        ["disk_cleanup.py", "--home", str(tmp_path), "--state-dir", str(tmp_path / "state")],
    )

    assert disk_cleanup.main() == 75
    output = json.loads(capsys.readouterr().out)
    assert output["reason"] == "cleanup_lock_busy"
    assert output["capacity_recovery"] == {
        "status": "unknown",
        "recovery_floor_bytes": 2 * GiB,
    }
    assert output["ok"] is False
    assert not (tmp_path / "state" / "last-receipt.json").exists()


def test_cli_busy_lock_preserves_managed_occurrence_identity(tmp_path: Path, monkeypatch, capsys) -> None:
    release = tmp_path / "release"
    release.mkdir()
    (release / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
    binding = {"owner_id": "life-manager-disk-cleanup", "run_id": "busy-1",
               "occurrence_id": "life-manager-disk-cleanup:busy-1", "release_sha": "a" * 40}
    monkeypatch.setattr(disk_cleanup, "REPOSITORY_ROOT", release)
    monkeypatch.setenv("LIFE_MANAGER_RUN_ID", binding["run_id"])
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", binding["occurrence_id"])
    state = tmp_path / "state"
    holder = HostDiskGovernor(home=tmp_path, state_dir=state)
    assert holder.acquire_lock()
    monkeypatch.setattr(disk_cleanup.sys, "argv", ["disk_cleanup.py", "--home", str(tmp_path), "--state-dir", str(state)])
    try:
        assert disk_cleanup.main() == 75
        output = json.loads(capsys.readouterr().out)
        assert output.get("identity") == binding
        assert output["reason"] == "cleanup_lock_busy"
        assert not (state / "last-receipt.json").exists()
    finally:
        holder.release_lock()


def test_lock_is_atomic(tmp_path: Path) -> None:
    first = HostDiskGovernor(home=tmp_path, state_dir=tmp_path / "state")
    second = HostDiskGovernor(home=tmp_path, state_dir=tmp_path / "state")
    assert first.acquire_lock()
    assert not second.acquire_lock()
    first.release_lock()
    assert first.acquire_lock()
    first.release_lock()


def test_lock_is_regular_persistent_mode0600_and_precreated_file_is_reused(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    lock_path = state / ".life-manager-disk-cleanup.lock"
    lock_path.write_bytes(b"")
    lock_path.chmod(0o600)
    governor = HostDiskGovernor(home=tmp_path, state_dir=state)

    assert governor.acquire_lock()
    assert lock_path.is_file()
    assert not lock_path.is_symlink()
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600
    governor.release_lock()
    assert lock_path.exists()
    assert governor.acquire_lock()
    governor.release_lock()


def test_precreated_regular_lock_never_mkdirs_lock_path_under_enospc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    lock_path = state / ".life-manager-disk-cleanup.lock"
    lock_path.write_bytes(b"")
    lock_path.chmod(0o600)
    reserve = state / ".receipt-reserve"
    reserve.write_bytes(b"reserve-sentinel")
    reserve.chmod(0o600)
    before = reserve.read_bytes()
    real_mkdir = Path.mkdir

    def fail_lock_mkdir(path: Path, *args, **kwargs):
        if path == lock_path:
            raise OSError(errno.ENOSPC, "legacy lock mkdir must not run")
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_lock_mkdir)
    first = HostDiskGovernor(home=tmp_path, state_dir=state)
    second = HostDiskGovernor(home=tmp_path, state_dir=state)
    assert first.acquire_lock()
    assert not second.acquire_lock()
    first.release_lock()
    assert first.acquire_lock()
    first.release_lock()
    assert reserve.read_bytes() == before


def test_lock_never_truncates_or_writes_and_preserves_receipt_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    lock_path = state / ".life-manager-disk-cleanup.lock"
    lock_path.write_bytes(b"")
    lock_path.chmod(0o600)
    reserve = state / ".receipt-reserve"
    reserve.write_bytes(b"reserve-sentinel")
    reserve.chmod(0o600)
    before = (reserve.read_bytes(), stat.S_IMODE(reserve.stat().st_mode))

    def fail_allocation(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, "lock allocation must not run")

    monkeypatch.setattr(disk_cleanup.os, "ftruncate", fail_allocation)
    monkeypatch.setattr(disk_cleanup.os, "write", fail_allocation)
    first = HostDiskGovernor(home=tmp_path, state_dir=state)
    second = HostDiskGovernor(home=tmp_path, state_dir=state)
    assert first.acquire_lock()
    assert not second.acquire_lock()
    first.release_lock()
    assert first.acquire_lock()
    first.release_lock()
    assert (reserve.read_bytes(), stat.S_IMODE(reserve.stat().st_mode)) == before


def test_lock_open_and_flock_errors_fail_closed_with_fd_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    reserve = state / ".receipt-reserve"
    reserve.write_bytes(b"reserve-sentinel")
    reserve.chmod(0o600)
    before = reserve.read_bytes()
    governor = HostDiskGovernor(home=tmp_path, state_dir=state)
    real_open = disk_cleanup.os.open

    monkeypatch.setattr(
        disk_cleanup.os,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(errno.EIO, "open failure")),
    )
    assert not governor.acquire_lock()
    assert governor._lock_fd is None
    assert reserve.read_bytes() == before

    opened: list[int] = []
    real_flock = disk_cleanup.fcntl.flock

    def capture_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def fail_flock(*_args, **_kwargs):
        raise OSError(errno.EIO, "flock failure")

    monkeypatch.setattr(disk_cleanup.os, "open", capture_open)
    monkeypatch.setattr(disk_cleanup.fcntl, "flock", fail_flock)
    assert not governor.acquire_lock()
    assert governor._lock_fd is None
    assert opened
    with pytest.raises(OSError):
        os.fstat(opened[-1])
    monkeypatch.setattr(disk_cleanup.fcntl, "flock", real_flock)
    assert reserve.read_bytes() == before


def test_new_lock_fchmod_failure_closes_fd_and_preserves_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    reserve = state / ".receipt-reserve"
    reserve.write_bytes(b"reserve-sentinel")
    reserve.chmod(0o600)
    before = reserve.read_bytes()
    opened: list[int] = []
    real_open = disk_cleanup.os.open

    def capture_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(disk_cleanup.os, "open", capture_open)
    monkeypatch.setattr(
        disk_cleanup.os,
        "fchmod",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(errno.ENOSPC, "fchmod full")),
    )
    governor = HostDiskGovernor(home=tmp_path, state_dir=state)
    assert not governor.acquire_lock()
    assert governor._lock_fd is None
    assert opened
    with pytest.raises(OSError):
        os.fstat(opened[-1])
    assert reserve.read_bytes() == before


def test_lock_path_unexpected_types_fail_closed_without_deletion(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    lock_path = state / ".life-manager-disk-cleanup.lock"
    for kind in ("directory", "symlink"):
        if kind == "directory":
            lock_path.mkdir()
        else:
            target = tmp_path / "lock-target"
            target.write_bytes(b"target")
            lock_path.symlink_to(target)
        governor = HostDiskGovernor(home=tmp_path, state_dir=state)
        assert not governor.acquire_lock()
        if kind == "directory":
            assert lock_path.is_dir()
            (lock_path / "ambiguous").write_text("keep")
            assert (lock_path / "ambiguous").exists()
            (lock_path / "ambiguous").unlink()
            lock_path.rmdir()
        else:
            assert lock_path.is_symlink()
            lock_path.unlink()


def test_legacy_directory_active_stale_invalid_and_extra_are_preserved(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    lock_path = state / ".life-manager-disk-cleanup.lock"

    for contents in (
        {"pid": str(os.getpid())},
        {"pid": "99999999"},
        {"pid": "not-a-pid"},
        {"pid": "99999999", "extra": "ambiguous"},
    ):
        lock_path.mkdir()
        for name, value in contents.items():
            (lock_path / name).write_text(value)
        governor = HostDiskGovernor(home=tmp_path, state_dir=state)
        assert not governor.acquire_lock()
        assert lock_path.is_dir()
        for child in lock_path.iterdir():
            child.unlink()
        lock_path.rmdir()


def test_launchd_is_five_minutes_and_single_owner() -> None:
    plist = Path(__file__).parents[1] / "launchd" / "ai.anicca.life-manager-disk-cleanup.plist"
    text = plist.read_text()
    assert "<integer>300</integer>" in text
    assert "disk_cleanup.py" in text


def test_legacy_hourly_trigger_delegates_to_the_same_host_guard() -> None:
    script = Path(__file__).parents[1] / "legacy-disk-janitor.sh"
    text = script.read_text()
    assert "EMERGENCY_GUARD_FULL_PASS=1" in text
    assert "disk_cleanup.py" in text


def test_run_once_records_inventory_summary(tmp_path: Path, monkeypatch) -> None:
    def fake_inventory(**_kwargs):
        return {"coverage": {"mount_count": 1, "root_count": 2, "gaps": ["size-deferred"]}}

    monkeypatch.setattr(disk_cleanup, "collect_host_inventory", fake_inventory)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (12 * GiB, 100 * GiB),
    )

    result = governor.run_once()

    assert result["inventory_mode"] == "full"
    assert (tmp_path / "state" / "host-inventory-full.at").exists()
    assert result["inventory_mounts"] == 1
    assert result["inventory_roots"] == 2
    assert result["inventory_gaps"] == 1
    receipt = json.loads((tmp_path / "state" / "last-receipt.json").read_text())
    assert receipt["inventory_roots"] == 2


def test_run_once_reports_unmet_below_shared_recovery_floor(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    state.mkdir()
    pressure = state / "disk-pressure.block"
    pressure.write_text("stale")
    monkeypatch.setattr(
        disk_cleanup,
        "collect_host_inventory",
        lambda **_kwargs: {"coverage": {"mount_count": 0, "root_count": 0, "gaps": []}},
    )
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=state,
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (2 * GiB - 1, 100 * GiB),
    )

    result = governor.run_once()

    assert not pressure.exists()
    expected_capacity = {"status": "unmet", "recovery_floor_bytes": 2 * GiB}
    assert result["capacity_recovery"] == expected_capacity
    assert result["ok"] is True
    receipt = json.loads((state / "last-receipt.json").read_text())
    assert receipt["capacity_recovery"] == expected_capacity


def _write_disk_writers_guard(path: Path, owner_id: str) -> None:
    path.write_text(json.dumps({
        "owner_id": owner_id,
        "reason": "disk_headroom_low",
        "required_bytes": 2 * GiB,
        "next_action": "restore_capacity_and_install_shared_disk_gate",
    }) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _run_disk_cleanup_once(tmp_path: Path, state: Path, monkeypatch, usage) -> dict:
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    monkeypatch.setattr(
        disk_cleanup,
        "collect_host_inventory",
        lambda **_kwargs: {"coverage": {"mount_count": 0, "root_count": 0, "gaps": []}},
    )
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=state,
        lsof=lambda _path: "confirmed-closed",
        usage=usage,
    )
    assert governor.acquire_lock()
    try:
        return governor.run_once()
    finally:
        governor.release_lock()


def test_run_once_clears_matching_disk_writers_guard_at_recovery_floor(
    tmp_path: Path, monkeypatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    guard = state / "disk-writers.stop"
    _write_disk_writers_guard(guard, "host-disk-recovery")
    result = _run_disk_cleanup_once(
        tmp_path, state, monkeypatch, lambda: (2 * GiB, 100 * GiB)
    )

    assert not guard.exists()
    assert result["free_after"] == 2 * GiB
    assert result["capacity_recovery"]["status"] == "met"
    assert result["disk_writers_stop"] == {"status": "cleared"}
    receipt = json.loads((state / "last-receipt.json").read_text())
    assert receipt["free_after"] == 2 * GiB
    assert receipt["ok"] is True
    assert receipt["disk_writers_stop"] == {"status": "cleared"}


def test_run_once_remeasures_after_inventory_and_preserves_guard_below_floor(
    tmp_path: Path, monkeypatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    guard = state / "disk-writers.stop"
    _write_disk_writers_guard(guard, "host-disk-recovery")
    free_samples = iter((2 * GiB, 2 * GiB, 2 * GiB, 2 * GiB - 1))
    result = _run_disk_cleanup_once(
        tmp_path, state, monkeypatch,
        lambda: (next(free_samples), 100 * GiB),
    )

    assert guard.exists()
    assert result["free_after"] == 2 * GiB - 1
    assert result["capacity_recovery"]["status"] == "unmet"
    assert result["ok"] is False
    assert result["disk_writers_stop"] == {
        "status": "preserved",
        "reason": "recovery_floor_not_met",
    }
    receipt = json.loads((state / "last-receipt.json").read_text())
    assert receipt["free_after"] == 2 * GiB - 1
    assert receipt["ok"] is False


@pytest.mark.parametrize(
    "replacement_mode",
    ("foreign_owner", "changed_identity"),
)
def test_run_once_preserves_foreign_or_replaced_disk_writers_guard(
    tmp_path: Path, monkeypatch, replacement_mode: str
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    guard = state / "disk-writers.stop"
    owner = "other-owner" if replacement_mode == "foreign_owner" else "host-disk-recovery"
    _write_disk_writers_guard(guard, owner)
    replacement = state / "replacement.json"
    _write_disk_writers_guard(replacement, "other-owner")
    if replacement_mode == "changed_identity":
        original_open = os.open
        swapped = False

        def replace_before_guard_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped and isinstance(path, (str, os.PathLike)) and Path(path) == guard:
                os.replace(replacement, guard)
                swapped = True
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(disk_cleanup.os, "open", replace_before_guard_open)
    result = _run_disk_cleanup_once(
        tmp_path, state, monkeypatch, lambda: (12 * GiB, 100 * GiB)
    )

    assert guard.exists()
    assert json.loads(guard.read_text())["owner_id"] == "other-owner"
    assert result["disk_writers_stop"]["status"] == "preserved"
    assert result["disk_writers_stop"]["reason"] == (
        "owner_mismatch" if replacement_mode == "foreign_owner" else "identity_changed"
    )


def test_watchdog_fast_inventory_survives_a_stale_budget_exhausted_full_marker(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LIFE_MANAGER_DISK_INVENTORY_FAST", "1")
    modes = []

    def inventory(**kwargs):
        modes.append(kwargs["full"])
        return {"coverage": {"mount_count": 1, "root_count": 1,
                             "gaps": ["size-budget-exhausted:/unknown"]}}

    monkeypatch.setattr(disk_cleanup, "collect_host_inventory", inventory)
    governor = HostDiskGovernor(home=tmp_path, state_dir=tmp_path / "state",
                                usage=lambda: (0, GiB))
    monkeypatch.setattr(governor, "discover_candidates", lambda **_kwargs: [])
    results = [governor.run_once(), governor.run_once()]

    assert modes == [False, False]
    assert [r["inventory_mode"] for r in results] == ["fast", "fast"]
    assert [r["inventory_gaps"] for r in results] == [1, 1]
    assert not governor.full_inventory_marker.exists()


def test_run_once_global_budget_preserves_candidate_and_does_not_advance_full_marker(
    tmp_path: Path, monkeypatch
) -> None:
    clock = [0.0]
    candidate = tmp_path / "tmp" / "capafy-hf-npm.budget"
    candidate.mkdir(parents=True)
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(candidate.parent))

    def discover_candidates(*, deadline=None) -> list[dict]:
        clock[0] = 105.0
        return [
            {
                "path": candidate,
                "class": "ephemeral",
                "owner": "temporary-run",
                "discovery": "allowlisted",
            }
        ]

    def fake_inventory(**kwargs):
        assert kwargs["budget_seconds"] == 0
        return {
            "coverage": {
                "mount_count": 1,
                "root_count": 1,
                "gaps": ["size-budget-exhausted:/tmp"],
            }
        }

    monkeypatch.setattr(disk_cleanup, "collect_host_inventory", fake_inventory)
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lambda _path: (_ for _ in ()).throw(AssertionError("lsof must not run after budget")),
        usage=lambda: (12 * GiB, 100 * GiB),
        clock=lambda: clock[0],
    )
    monkeypatch.setattr(governor, "discover_candidates", discover_candidates)

    result = governor.run_once()

    assert candidate.exists()
    assert result["preserved_reasons"] == {"probe-budget-exhausted": 1}
    assert not (tmp_path / "state" / "host-inventory-full.at").exists()


def test_run_once_rotates_candidate_start_after_budget_exhaustion(
    tmp_path: Path, monkeypatch
) -> None:
    state = tmp_path / "state"
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    candidates = []
    for index in range(4):
        path = temporary / f"capafy-hf-npm.budget-{index}"
        path.mkdir()
        (path / "payload").write_text("x")
        candidates.append({
            "path": path,
            "class": "ephemeral",
            "owner": "temporary-run",
            "discovery": "allowlisted",
        })

    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    monkeypatch.setattr(disk_cleanup, "GOVERNOR_BUDGET_SECONDS", 6)
    monkeypatch.setattr(disk_cleanup, "LSOF_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(disk_cleanup, "POST_SWEEP_RESERVE_SECONDS", 0)
    monkeypatch.setattr(
        disk_cleanup,
        "collect_host_inventory",
        lambda **_kwargs: {"coverage": {"mount_count": 0, "root_count": 0, "gaps": []}},
    )

    clock = [0.0]
    visited = []

    def consume_run_budget(path: Path) -> str:
        visited.append(path.name)
        clock[0] += 6
        return "confirmed-closed"

    rotations = []
    for _ in range(3):
        governor = HostDiskGovernor(
            home=tmp_path,
            state_dir=state,
            lsof=consume_run_budget,
            usage=lambda: (12 * GiB, 100 * GiB),
            clock=lambda: clock[0],
        )
        monkeypatch.setattr(governor, "discover_candidates", lambda **_kwargs: candidates)
        result = governor.run_once()
        assert result["preserved_reasons"] == {"probe-budget-exhausted": 4}
        rotations.append(result.get("candidate_rotation"))

    assert visited == [
        "capafy-hf-npm.budget-0",
        "capafy-hf-npm.budget-1",
        "capafy-hf-npm.budget-2",
    ]
    persisted_cursor = {"status": "persisted", "errors": []}
    assert rotations == [
        {
            "candidate_count": 4,
            "start_index": 0,
            "next_index": 1,
            "cursor_persistence": persisted_cursor,
        },
        {
            "candidate_count": 4,
            "start_index": 1,
            "next_index": 2,
            "cursor_persistence": persisted_cursor,
        },
        {
            "candidate_count": 4,
            "start_index": 2,
            "next_index": 3,
            "cursor_persistence": persisted_cursor,
        },
    ]


def _make_cursor_enospc_governor(tmp_path: Path, monkeypatch, free_bytes: int):
    state = tmp_path / "state"
    temporary = tmp_path / "tmp"
    candidate = temporary / "capafy-hf-npm.cursor-enospc"
    candidate.mkdir(parents=True)
    (candidate / "payload").write_text("keep")
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temporary))
    monkeypatch.setattr(
        disk_cleanup,
        "collect_host_inventory",
        lambda **_kwargs: {"coverage": {"mount_count": 0, "root_count": 0, "gaps": []}},
    )
    candidates = [{
        "path": candidate,
        "class": "ephemeral",
        "owner": "temporary-run",
        "discovery": "allowlisted",
    }]
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=state,
        lsof=lambda _path: "open",
        usage=lambda: (free_bytes, 100 * GiB),
    )
    monkeypatch.setattr(governor, "discover_candidates", lambda **_kwargs: candidates)
    sweep_calls = []
    real_sweep = governor.sweep

    def counted_sweep(*args, **kwargs):
        sweep_calls.append(1)
        return real_sweep(*args, **kwargs)

    monkeypatch.setattr(governor, "sweep", counted_sweep)
    assert governor.acquire_lock()
    return governor, state, candidate, sweep_calls


def test_cursor_mkstemp_enospc_keeps_sweeping_and_last_receipt_uses_reserve(
    tmp_path: Path, monkeypatch
) -> None:
    governor, state, candidate, sweep_calls = _make_cursor_enospc_governor(
        tmp_path, monkeypatch, free_bytes=2 * GiB - 1,
    )
    original_mkstemp = disk_cleanup.tempfile.mkstemp
    failures = {".candidate-cursor.json.": 2, ".last-receipt.json.": 1}

    def fail_cursor_and_terminal_once(*args, **kwargs):
        prefix = kwargs.get("prefix", "")
        if failures.get(prefix, 0):
            failures[prefix] -= 1
            raise OSError(errno.ENOSPC, "injected receipt tempfile exhaustion")
        return original_mkstemp(*args, **kwargs)

    monkeypatch.setattr(disk_cleanup.tempfile, "mkstemp", fail_cursor_and_terminal_once)
    try:
        result = governor.run_once()
    finally:
        governor.release_lock()

    assert sweep_calls == [1]
    assert candidate.exists()
    assert result["protected_deletions"] == 0
    assert result["ok"] is True
    cursor = result["candidate_rotation"]["cursor_persistence"]
    assert cursor["status"] == "failed"
    assert cursor["errors"][0] == {
        "stage": "before_sweep",
        "error_class": "OSError",
        "errno": errno.ENOSPC,
        "next_action": "continue_sweep_then_retry_once_after_recovery",
    }
    receipt = json.loads((state / "last-receipt.json").read_text())
    assert receipt["ok"] is True
    assert receipt["capacity_recovery"]["status"] == "unmet"
    assert governor._receipt_reserve_valid(state / ".receipt-reserve")


def test_cursor_atomic_enospc_retries_after_recovery_and_saves_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    governor, state, candidate, sweep_calls = _make_cursor_enospc_governor(
        tmp_path, monkeypatch, free_bytes=12 * GiB,
    )
    real_atomic_write = governor._atomic_receipt_write
    cursor_write_failed = False

    def fail_first_cursor_write(data: bytes, target: Path) -> None:
        nonlocal cursor_write_failed
        if target.name == "candidate-cursor.json" and not cursor_write_failed:
            cursor_write_failed = True
            raise disk_cleanup._ReceiptAtomicFailure(
                OSError(errno.ENOSPC, "injected candidate cursor exhaustion")
            )
        real_atomic_write(data, target)

    original_mkstemp = disk_cleanup.tempfile.mkstemp
    terminal_receipt_failure = 1

    def fail_terminal_receipt_once(*args, **kwargs):
        nonlocal terminal_receipt_failure
        if kwargs.get("prefix") == ".last-receipt.json." and terminal_receipt_failure:
            terminal_receipt_failure -= 1
            raise OSError(errno.ENOSPC, "injected last receipt tempfile exhaustion")
        return original_mkstemp(*args, **kwargs)

    monkeypatch.setattr(governor, "_atomic_receipt_write", fail_first_cursor_write)
    monkeypatch.setattr(disk_cleanup.tempfile, "mkstemp", fail_terminal_receipt_once)
    try:
        result = governor.run_once()
    finally:
        governor.release_lock()

    assert sweep_calls == [1]
    assert candidate.exists()
    assert result["protected_deletions"] == 0
    assert result["free_after"] == 12 * GiB
    assert result["capacity_recovery"]["status"] == "met"
    assert result["ok"] is True
    cursor = result["candidate_rotation"]["cursor_persistence"]
    assert cursor["status"] == "persisted_after_retry"
    assert cursor["errors"][0] == {
        "stage": "before_sweep",
        "error_class": "OSError",
        "errno": errno.ENOSPC,
        "next_action": "continue_sweep_then_retry_once_after_recovery",
    }
    assert json.loads((state / "last-receipt.json").read_text())["ok"] is True
    assert governor._receipt_reserve_valid(state / ".receipt-reserve")


def test_cursor_enospc_preserves_terminal_reserve_and_reports_postcommit_enospc(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    governor, state, candidate, sweep_calls = _make_cursor_enospc_governor(
        tmp_path, monkeypatch, free_bytes=12 * GiB,
    )
    reserve = state / ".receipt-reserve"
    governor._receipt_reserve()
    reserve_at_sweep = []
    counted_sweep = governor.sweep

    def record_reserve_then_sweep(*args, **kwargs):
        reserve_at_sweep.append(governor._receipt_reserve_valid(reserve))
        return counted_sweep(*args, **kwargs)

    monkeypatch.setattr(governor, "sweep", record_reserve_then_sweep)
    real_atomic_write = governor._atomic_receipt_write
    terminal_write_failed = False

    def fail_cursor_and_terminal_once(data: bytes, target: Path) -> None:
        nonlocal terminal_write_failed
        if target.name == "candidate-cursor.json":
            raise disk_cleanup._ReceiptAtomicFailure(
                OSError(errno.ENOSPC, "candidate cursor staging exhausted")
            )
        if target.name == "last-receipt.json" and not terminal_write_failed:
            terminal_write_failed = True
            raise disk_cleanup._ReceiptAtomicFailure(
                OSError(errno.ENOSPC, "terminal receipt staging exhausted")
            )
        real_atomic_write(data, target)

    real_receipt_reserve = governor._receipt_reserve

    def fail_postcommit_reserve_recreate(*, recreate: bool = False) -> None:
        if recreate:
            raise OSError(errno.ENOSPC, "receipt reserve recreation exhausted")
        real_receipt_reserve(recreate=recreate)

    monkeypatch.setattr(governor, "_atomic_receipt_write", fail_cursor_and_terminal_once)
    monkeypatch.setattr(governor, "_receipt_reserve", fail_postcommit_reserve_recreate)
    governor.release_lock()
    monkeypatch.setattr(disk_cleanup, "HostDiskGovernor", lambda **_kwargs: governor)
    monkeypatch.setattr(
        disk_cleanup.sys,
        "argv",
        ["disk_cleanup.py", "--home", str(tmp_path), "--state-dir", str(state)],
    )
    assert disk_cleanup.main() == 1
    result = json.loads(capsys.readouterr().out)

    assert sweep_calls == [1]
    assert reserve_at_sweep == [True]
    assert candidate.exists()
    assert result["protected_deletions"] == 0
    assert result["free_after"] == 12 * GiB
    assert result["capacity_recovery"]["status"] == "met"
    assert result["ok"] is False
    assert result["candidate_rotation"]["cursor_persistence"]["errors"][0] == {
        "stage": "before_sweep",
        "error_class": "OSError",
        "errno": errno.ENOSPC,
        "next_action": "continue_sweep_then_retry_once_after_recovery",
    }
    receipt = json.loads((state / "last-receipt.json").read_text())
    assert receipt["capacity_recovery"]["status"] == "met"
    assert receipt["ok"] is True
    assert result["receipt_persistence"] == {
        "status": "committed_reserve_missing",
        "stage": "reserve_recreate_after_commit",
        "error_class": "OSError",
        "errno": errno.ENOSPC,
        "next_action": "retry_on_next_run",
    }
    assert not reserve.exists()


def test_run_once_rechecks_budget_after_lsof_before_reclaim(tmp_path: Path, monkeypatch) -> None:
    clock = [0.0]
    candidate = tmp_path / "tmp" / "capafy-hf-npm.lsof-budget"
    candidate.mkdir(parents=True)
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(candidate.parent))

    def fake_inventory(**kwargs):
        assert kwargs["budget_seconds"] == 0
        return {"coverage": {"mount_count": 0, "root_count": 0, "gaps": ["size-budget-exhausted:/tmp"]}}

    monkeypatch.setattr(disk_cleanup, "collect_host_inventory", fake_inventory)

    def lsof(_path: Path) -> str:
        clock[0] = 106.0
        return "confirmed-closed"

    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        lsof=lsof,
        usage=lambda: (12 * GiB, 100 * GiB),
        clock=lambda: clock[0],
    )
    monkeypatch.setattr(
        governor,
        "discover_candidates",
        lambda **_kwargs: [
            {
                "path": candidate,
                "class": "ephemeral",
                "owner": "temporary-run",
                "discovery": "allowlisted",
            }
        ],
    )

    result = governor.run_once()

    assert candidate.exists()
    assert result["preserved_reasons"] == {"probe-budget-exhausted": 1}
    assert not (tmp_path / "state" / "host-inventory-full.at").exists()


@pytest.mark.parametrize("launchctl_status", (141, 153))
def test_gui_bootstrap_health_failure_is_observation_only(
    tmp_path: Path, monkeypatch, launchctl_status: int
) -> None:
    candidate = tmp_path / "tmp" / "capafy-hf-npm.health-failure"
    candidate.mkdir(parents=True)
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(candidate.parent))
    monkeypatch.setattr(disk_cleanup.sys, "platform", "darwin")

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        if argv[0] == "/usr/bin/dscl":
            stdout = f"UniqueID: {os.getuid()}\nNFSHomeDirectory: {tmp_path}\n"
            return subprocess.CompletedProcess(argv, 0, stdout, "")
        assert argv == [
            "/bin/launchctl",
            "print",
            f"gui/{os.getuid()}/ai.anicca.life-manager-disk-cleanup",
        ]
        return subprocess.CompletedProcess(argv, launchctl_status, "", "Reentrancy avoided")

    monkeypatch.setattr(disk_cleanup.subprocess, "run", fake_run)
    monkeypatch.setattr(
        disk_cleanup.os,
        "kill",
        lambda *_args: (_ for _ in ()).throw(AssertionError("cleanup must not signal app-server")),
    )
    monkeypatch.setattr(
        disk_cleanup,
        "collect_host_inventory",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("inventory must not run")),
    )

    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        bootstrap_health=lambda: DEFAULT_BOOTSTRAP_HEALTH(tmp_path, tmp_path / "state"),
        lsof=lambda _path: (_ for _ in ()).throw(AssertionError("lsof must not run")),
        usage=lambda: (12 * GiB, 100 * GiB),
    )
    monkeypatch.setattr(
        governor,
        "discover_candidates",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("discovery must not run")),
    )

    result = governor.run_once()

    assert result["reason"] == "gui-bootstrap-health-failure"
    assert result["evaluated"] == 0
    assert result["reclaimed"] == 0
    assert result["errors"] == 1
    assert result["protected_deletions"] == 0
    assert candidate.exists()
    receipt = json.loads((tmp_path / "state" / "last-receipt.json").read_text())
    assert receipt["reason"] == "gui-bootstrap-health-failure"
    assert receipt["health"]["error_code"] == f"launchctl-{launchctl_status}"
    assert receipt["health"]["domain"] == f"gui/{os.getuid()}"
    assert receipt["health"]["label"] == "ai.anicca.life-manager-disk-cleanup"
    assert receipt["evaluated"] == 0
    assert receipt["reclaimed"] == 0
    assert receipt["protected_deletions"] == 0
    assert receipt["session_recovery"] == {
        "authority": "gui-session-owner",
        "process_kill_authority": False,
        "required_readback": ["uid", "gui-domain", "canonical-label"],
        "stale_app_server_action": "observe-only",
    }
    assert not (tmp_path / "state" / "host-inventory-full.at").exists()


def test_canary_health_exception_preserves_without_process_action(
    tmp_path: Path, monkeypatch
) -> None:
    canary = tmp_path / "tmp" / "capafy-hf-npm.health-exception"
    canary.mkdir(parents=True)
    (canary / "payload").write_text("keep")
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(canary.parent))
    monkeypatch.setattr(
        disk_cleanup.os,
        "kill",
        lambda *_args: (_ for _ in ()).throw(AssertionError("cleanup must not signal app-server")),
    )

    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        bootstrap_health=lambda: (_ for _ in ()).throw(RuntimeError("bootstrap unavailable")),
        lsof=lambda _path: (_ for _ in ()).throw(AssertionError("lsof must not run")),
        usage=lambda: (12 * GiB, 100 * GiB),
    )

    result = governor.run_canary(canary)

    assert canary.exists()
    assert result["reason"] == "gui-bootstrap-health-failure"
    assert result["removed"] is False
    assert result["reclaimed"] == 0
    assert result["protected_deletions"] == 0
    receipt = json.loads((tmp_path / "state" / "canary-last-receipt.json").read_text())
    assert receipt["health"] == {
        "detail": "RuntimeError",
        "error_code": "health-check-exception",
        "status": "failure",
    }
    assert receipt["session_recovery"]["process_kill_authority"] is False
    assert receipt["session_recovery"]["stale_app_server_action"] == "observe-only"


def test_exact_canary_reclaims_one_regenerable_path_and_replay_is_noop(
    tmp_path: Path, monkeypatch
) -> None:
    temp_root = tmp_path / "tmp"
    canary = temp_root / "capafy-hf-npm.life-manager-canary"
    canary.mkdir(parents=True)
    (canary / "payload").write_bytes(b"canary" * 1024)
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(temp_root))

    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        bootstrap_health=lambda: {"status": "not-applicable"},
        lsof=lambda _path: "confirmed-closed",
        usage=lambda: (12 * GiB, 100 * GiB),
    )

    first = governor.run_canary(canary)
    replay = governor.run_canary(canary)

    assert first["canary_path"] == str(canary.resolve())
    assert first["removed"] is True
    assert first["before_bytes"] > 0
    assert first["after_bytes"] == 0
    assert first["reclaimed"] == first["before_bytes"]
    assert replay["reason"] == "canary-path-missing"
    assert replay["duplicate_effect"] == 0
    receipt = json.loads((tmp_path / "state" / "canary-last-receipt.json").read_text())
    assert receipt["canary_path"] == str(canary.resolve())
    assert receipt["initial"]["removed"] is True
    assert receipt["initial"]["reclaimed"] == first["before_bytes"]
    assert receipt["replay"]["duplicate_effect"] == 0


def test_exact_canary_rejects_path_outside_temp_root(tmp_path: Path) -> None:
    outside = tmp_path / "important"
    outside.write_text("preserve", encoding="utf-8")
    governor = HostDiskGovernor(
        home=tmp_path,
        state_dir=tmp_path / "state",
        bootstrap_health=lambda: {"status": "not-applicable"},
        lsof=lambda _path: (_ for _ in ()).throw(AssertionError("lsof must not run")),
        usage=lambda: (12 * GiB, 100 * GiB),
    )

    result = governor.run_canary(outside)

    assert result["reason"] == "canary-path-not-allowlisted"
    assert outside.exists()


@pytest.mark.parametrize("failure_stage", ["write", "fsync", "replace"])
def test_receipt_enospc_retries_atomic_commit_once_and_restores_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    target = state / "last-receipt.json"
    target.write_text('{"old":true}\n', encoding="utf-8")
    target.chmod(0o600)
    reserve = state / ".receipt-reserve"
    reserve.write_bytes(b"\0" * (1024 * 1024))
    reserve.chmod(0o600)

    replace_calls = 0
    write_failures = 0
    fsync_calls = 0
    real_replace = disk_cleanup.os.replace
    real_fdopen = disk_cleanup.os.fdopen
    real_fsync = disk_cleanup.os.fsync

    class WriteFailOnce:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.wrapped.__exit__(exc_type, exc, tb)

        def write(self, data):
            nonlocal write_failures
            if write_failures == 0:
                write_failures += 1
                raise OSError(errno.ENOSPC, "receipt write full")
            return self.wrapped.write(data)

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    def fdopen(fd, *args, **kwargs):
        wrapped = real_fdopen(fd, *args, **kwargs)
        return WriteFailOnce(wrapped) if failure_stage == "write" and write_failures == 0 else wrapped

    def fsync(fd):
        nonlocal fsync_calls
        fsync_calls += 1
        if failure_stage == "fsync" and fsync_calls == 1:
            raise OSError(errno.ENOSPC, "receipt fsync full")
        return real_fsync(fd)

    def replace(src, dst):
        nonlocal replace_calls
        if Path(dst).name == "last-receipt.json":
            replace_calls += 1
        if failure_stage == "replace" and replace_calls == 1:
            raise OSError(errno.ENOSPC, "receipt replace full")
        return real_replace(src, dst)

    monkeypatch.setattr(disk_cleanup.os, "fdopen", fdopen)
    monkeypatch.setattr(disk_cleanup.os, "fsync", fsync)
    monkeypatch.setattr(disk_cleanup.os, "replace", replace)

    governor = HostDiskGovernor(home=tmp_path, state_dir=state)
    governor._receipt({"value": "new"})

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["value"] == "new"
    if failure_stage == "replace":
        assert replace_calls == 2
    elif failure_stage == "fsync":
        assert fsync_calls >= 3
    else:
        assert write_failures == 1
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(state.glob(".last-receipt.json.*.tmp"))
    reserve_stat = reserve.stat()
    assert stat.S_ISREG(reserve_stat.st_mode)
    assert stat.S_IMODE(reserve_stat.st_mode) == 0o600
    assert reserve_stat.st_size == 1024 * 1024
    assert reserve_stat.st_blocks > 0


def test_receipt_other_errno_keeps_old_target_and_reserve_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    target = state / "last-receipt.json"
    old = b'{"old":true}\n'
    target.write_bytes(old)
    target.chmod(0o600)
    reserve = state / ".receipt-reserve"
    reserve.write_bytes(b"\0" * (1024 * 1024))
    reserve.chmod(0o600)
    replace_calls = 0
    real_replace = disk_cleanup.os.replace

    def replace(src, dst):
        nonlocal replace_calls
        replace_calls += 1
        raise OSError(errno.EIO, "receipt I/O failure")

    monkeypatch.setattr(disk_cleanup.os, "replace", replace)
    governor = HostDiskGovernor(home=tmp_path, state_dir=state)

    with pytest.raises(OSError) as caught:
        governor._receipt({"value": "new"})

    assert caught.value.errno == errno.EIO
    assert replace_calls == 1
    assert target.read_bytes() == old
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(state.glob(".last-receipt.json.*.tmp"))
    reserve_stat = reserve.stat()
    assert stat.S_ISREG(reserve_stat.st_mode)
    assert stat.S_IMODE(reserve_stat.st_mode) == 0o600
    assert reserve_stat.st_size == 1024 * 1024
    assert reserve_stat.st_blocks > 0


def _seed_receipt_reserve(state: Path) -> Path:
    reserve = state / ".receipt-reserve"
    reserve.write_bytes(b"\0" * (1024 * 1024))
    reserve.chmod(0o600)
    return reserve


def test_receipt_reserve_rebuilds_when_allocated_blocks_are_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    reserve = state / ".receipt-reserve"
    reserve.write_bytes(b"x" * (1024 * 1024))
    reserve.chmod(0o600)
    real_lstat = Path.lstat
    full = real_lstat(reserve)
    underallocated = SimpleNamespace(
        st_mode=full.st_mode,
        st_size=full.st_size,
        st_blocks=1,
    )
    lstat_calls = 1

    def report_underallocated_once(path: Path):
        nonlocal lstat_calls
        if path == reserve and lstat_calls:
            lstat_calls -= 1
            return underallocated
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", report_underallocated_once)

    HostDiskGovernor(home=tmp_path, state_dir=state)._receipt({"value": "new"})

    reserve_after = reserve.stat()
    assert reserve_after.st_blocks * 512 >= 1024 * 1024
    assert len(reserve.read_bytes()) == 1024 * 1024


@pytest.mark.parametrize("failure_stage", ["write", "flush", "fsync", "readback"])
def test_receipt_reserve_build_failure_has_no_partial_final_or_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    real_fdopen = disk_cleanup.os.fdopen
    real_fsync = disk_cleanup.os.fsync
    real_read_bytes = Path.read_bytes
    failures = 0

    class FailingStream:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.wrapped.__exit__(exc_type, exc, tb)

        def write(self, data):
            nonlocal failures
            if failure_stage == "write" and failures == 0:
                failures += 1
                raise OSError(errno.EIO, "reserve write failure")
            return self.wrapped.write(data)

        def flush(self):
            nonlocal failures
            if failure_stage == "flush" and failures == 0:
                failures += 1
                raise OSError(errno.EIO, "reserve flush failure")
            return self.wrapped.flush()

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    def fdopen(fd, *args, **kwargs):
        return FailingStream(real_fdopen(fd, *args, **kwargs))

    def fsync(fd):
        nonlocal failures
        if failure_stage == "fsync" and failures == 0:
            failures += 1
            raise OSError(errno.EIO, "reserve fsync failure")
        return real_fsync(fd)

    def read_bytes(path):
        nonlocal failures
        if failure_stage == "readback" and path.name.startswith(".receipt-reserve") and failures == 0:
            failures += 1
            raise OSError(errno.EIO, "reserve readback failure")
        return real_read_bytes(path)

    monkeypatch.setattr(disk_cleanup.os, "fdopen", fdopen)
    monkeypatch.setattr(disk_cleanup.os, "fsync", fsync)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    with pytest.raises(OSError):
        HostDiskGovernor(home=tmp_path, state_dir=state)._receipt({"value": "new"})

    assert not (state / ".receipt-reserve").exists()
    assert not list(state.glob(".receipt-reserve.*.tmp"))
    assert not list(state.glob(".last-receipt.json.*.tmp"))


def test_receipt_retry_reserve_recreate_fsync_failure_raises_after_commit_without_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    reserve = _seed_receipt_reserve(state)
    target = state / "last-receipt.json"
    target.write_text('{"old":true}\n', encoding="utf-8")
    target.chmod(0o600)
    real_replace = disk_cleanup.os.replace
    real_fdopen = disk_cleanup.os.fdopen
    real_fsync = disk_cleanup.os.fsync
    reserve_fd = None
    replace_calls = 0

    class TrackReserveStream:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.wrapped.__exit__(exc_type, exc, tb)

        def write(self, data):
            nonlocal reserve_fd
            result = self.wrapped.write(data)
            if len(data) >= 1024 * 1024:
                reserve_fd = self.wrapped.fileno()
            return result

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    def fdopen(fd, *args, **kwargs):
        return TrackReserveStream(real_fdopen(fd, *args, **kwargs))

    def fsync(fd):
        if reserve_fd is not None and fd == reserve_fd:
            raise OSError(errno.EIO, "reserve recreate fsync failure")
        return real_fsync(fd)

    def replace(src, dst):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 1:
            raise OSError(errno.ENOSPC, "first receipt commit full")
        return real_replace(src, dst)

    monkeypatch.setattr(disk_cleanup.os, "fdopen", fdopen)
    monkeypatch.setattr(disk_cleanup.os, "fsync", fsync)
    monkeypatch.setattr(disk_cleanup.os, "replace", replace)

    with pytest.raises(OSError):
        HostDiskGovernor(home=tmp_path, state_dir=state)._receipt({"value": "new"})

    assert replace_calls == 2
    assert json.loads(target.read_text(encoding="utf-8"))["value"] == "new"
    assert not reserve.exists()
    assert not list(state.glob(".receipt-reserve.*.tmp"))


def test_receipt_parent_dir_fsync_error_is_best_effort_and_does_not_consume_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    reserve = _seed_receipt_reserve(state)
    real_fsync = disk_cleanup.os.fsync
    dir_fsync_calls = 0

    def fsync(fd):
        nonlocal dir_fsync_calls
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            dir_fsync_calls += 1
            raise OSError(errno.EIO, "parent directory fsync failure")
        return real_fsync(fd)

    monkeypatch.setattr(disk_cleanup.os, "fsync", fsync)
    HostDiskGovernor(home=tmp_path, state_dir=state)._receipt({"value": "new"})

    assert dir_fsync_calls == 1
    assert json.loads((state / "last-receipt.json").read_text(encoding="utf-8"))["value"] == "new"
    assert reserve.exists()
    reserve_stat = reserve.stat()
    assert stat.S_IMODE(reserve_stat.st_mode) == 0o600
    assert reserve_stat.st_blocks * 512 >= 1024 * 1024


def test_receipt_second_enospc_has_one_retry_old_target_and_no_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    reserve = _seed_receipt_reserve(state)
    target = state / "last-receipt.json"
    old = b'{"old":true}\n'
    target.write_bytes(old)
    target.chmod(0o600)
    replace_calls = 0

    def replace(_src, _dst):
        nonlocal replace_calls
        replace_calls += 1
        raise OSError(errno.ENOSPC, "receipt full")

    monkeypatch.setattr(disk_cleanup.os, "replace", replace)
    with pytest.raises(OSError):
        HostDiskGovernor(home=tmp_path, state_dir=state)._receipt({"value": "new"})

    assert replace_calls == 2
    assert target.read_bytes() == old
    assert not reserve.exists()
    assert not list(state.glob(".last-receipt.json.*.tmp"))


def test_receipt_payload_over_64k_is_rejected_without_state_change(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    reserve = _seed_receipt_reserve(state)
    target = state / "last-receipt.json"
    old = b'{"old":true}\n'
    target.write_bytes(old)
    target.chmod(0o600)

    with pytest.raises(ValueError):
        HostDiskGovernor(home=tmp_path, state_dir=state)._receipt({"value": "x" * 70000})

    assert target.read_bytes() == old
    assert reserve.exists()
    assert stat.S_IMODE(reserve.stat().st_mode) == 0o600
    assert reserve.stat().st_blocks * 512 >= 1024 * 1024
    assert not list(state.glob(".last-receipt.json.*.tmp"))


def test_receipt_replace_fd_reuse_does_not_close_unrelated_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    _seed_receipt_reserve(state)
    real_replace = disk_cleanup.os.replace
    retained_fd: int | None = None

    def replace(src, dst):
        nonlocal retained_fd
        if Path(dst).name == "last-receipt.json":
            retained_fd = os.open(os.devnull, os.O_RDONLY)
        return real_replace(src, dst)

    monkeypatch.setattr(disk_cleanup.os, "replace", replace)
    HostDiskGovernor(home=tmp_path, state_dir=state)._receipt({"value": "new"})

    assert retained_fd is not None
    try:
        os.fstat(retained_fd)
    finally:
        os.close(retained_fd)


def test_receipt_carries_loaded_cleanup_identity(tmp_path, monkeypatch):
    root = tmp_path / "release"
    root.mkdir()
    (root / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
    monkeypatch.setattr(disk_cleanup, "REPOSITORY_ROOT", root)
    monkeypatch.setenv("LIFE_MANAGER_RUN_ID", "run-1")
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "life-manager-disk-cleanup:run-1")
    governor = HostDiskGovernor(home=tmp_path, state_dir=tmp_path / "state")
    payload = {"free_after": 600 * 1024**2, "errors": 0, "protected_deletions": 0}
    governor._receipt(payload)
    saved = json.loads((tmp_path / "state/last-receipt.json").read_text())
    assert saved["identity"] == {"owner_id": "life-manager-disk-cleanup", "run_id": "run-1", "occurrence_id": "life-manager-disk-cleanup:run-1", "release_sha": "a" * 40}
    assert payload["identity"] == saved["identity"]
    monkeypatch.delenv("LIFE_MANAGER_RUN_ID")
    monkeypatch.delenv("LIFE_MANAGER_OCCURRENCE_ID")
    governor._receipt({"free_after": 400*1024**2})
    assert json.loads((tmp_path / "state/last-receipt.json").read_text())["identity"] == saved["identity"]
    assert "identity" not in json.loads((tmp_path / "state/last-unbound-receipt.json").read_text())


def test_governor_reports_growth_and_preservation_reason_without_false_recovery(tmp_path, monkeypatch):
    governor = HostDiskGovernor(home=tmp_path, state_dir=tmp_path / "state", usage=lambda: (600*1024**2,100*GiB), lsof=lambda _p: "confirmed-closed")
    monkeypatch.setattr(governor, "discover_candidates", lambda **_kwargs: [])
    monkeypatch.setattr(disk_cleanup, "collect_host_inventory", lambda **_k: {"coverage": {"mount_count":1,"root_count":1,"gaps":[]},"storage_growth":{"roots":[{"path":"/srv/lm/unknown","delta_bytes":1048576,"attribution":"unattributed"}],"non_additive":True}})
    assert governor.acquire_lock()
    try: result = governor.run_once()
    finally: governor.release_lock()
    assert result["storage_growth"]["roots"][0]["delta_bytes"] == 1048576
    assert result["capacity_recovery"]["status"] == "unmet"
    assert result["storage_next_action"] == "inspect_unattributed_writer"
    assert result["protected_deletions"] == 0
