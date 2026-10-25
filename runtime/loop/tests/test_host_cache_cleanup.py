import gzip
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from runtime.loop import host_cache_cleanup as MODULE  # noqa: E402


def _landing_worktree(home: Path, name: str, *, real_node_modules: bool, cache: bool, age_seconds: int) -> Path:
    worktree = home / "Projects/anicca-products-worktrees" / name
    landing = worktree / "apps/landing"
    landing.mkdir(parents=True)
    (landing / "package.json").write_text('{"name":"landing","private":true}\n')
    (landing / "package-lock.json").write_text('{"name":"landing","lockfileVersion":3,"packages":{}}\n')
    stale = time.time() - age_seconds
    if real_node_modules:
        (landing / "node_modules/next").mkdir(parents=True)
        (landing / "node_modules/next/package.json").write_text('{"version":"14.2.5"}\n')
        os.utime(landing / "node_modules", (stale, stale))
    if cache:
        (landing / ".next/cache/webpack").mkdir(parents=True)
        (landing / ".next/cache/webpack/0.pack").write_bytes(b"x" * 1024)
        os.utime(landing / ".next/cache", (stale, stale))
    return worktree


def test_idle_worktree_gets_shared_node_modules_and_loses_next_cache(tmp_path, monkeypatch):
    home = tmp_path / "home"
    store = tmp_path / "store"
    monkeypatch.setenv("ANICCA_PRODUCTS_NODE_MODULES_STORE", str(store))
    idle = _landing_worktree(home, "idle-20261026", real_node_modules=True, cache=True, age_seconds=3 * 3600)
    busy = _landing_worktree(home, "busy-20261026", real_node_modules=True, cache=True, age_seconds=60)
    result = MODULE.landing_cache_cleanup(home)
    assert result == {"examined": 2, "shared": 1, "cache_removed": 1, "skipped_busy": 1, "errors": 0}
    link = idle / "apps/landing/node_modules"
    assert link.is_symlink()
    assert (link / "next/package.json").read_text().startswith('{"version":"14.2.5"')
    assert not (idle / "apps/landing/.next/cache").exists()
    # The busy worktree is untouched: real directory and cache still there.
    assert not (busy / "apps/landing/node_modules").is_symlink()
    assert (busy / "apps/landing/.next/cache").is_dir()


def test_second_worktree_on_the_same_lockfile_reuses_the_store(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("ANICCA_PRODUCTS_NODE_MODULES_STORE", str(tmp_path / "store"))
    first = _landing_worktree(home, "a-20261026", real_node_modules=True, cache=False, age_seconds=7200)
    second = _landing_worktree(home, "b-20261026", real_node_modules=True, cache=False, age_seconds=7200)
    MODULE.landing_cache_cleanup(home)
    assert os.readlink(first / "apps/landing/node_modules") == os.readlink(second / "apps/landing/node_modules")
    assert MODULE.landing_cache_cleanup(home)["examined"] == 0  # already shared, nothing to do


def test_rotate_large_logs_archives_and_truncates_in_place(tmp_path):
    home = tmp_path / "home"
    logs = home / ".tsbridge/logs"
    logs.mkdir(parents=True)
    big = logs / "tsbridge.out.log"
    big.write_bytes(b"line\n" * 4096)
    small = logs / "tsbridge.err.log"
    small.write_bytes(b"ok\n")
    with open(big, "ab") as writer:  # a live appender keeps its descriptor across the rotation
        result = MODULE.rotate_large_logs(home, threshold=1024, now=lambda: 1_700_000_000.0)
        writer.write(b"after\n")
        writer.flush()
    assert result["rotated"] == 1 and result["errors"] == 0 and result["bytes_freed"] == 4096 * 5
    archives = list(logs.glob("tsbridge.out.log.*.gz"))
    assert len(archives) == 1
    assert gzip.open(archives[0]).read().startswith(b"line\n")
    assert big.read_bytes() == b"after\n"
    assert small.read_bytes() == b"ok\n"


def test_rotate_keeps_only_the_newest_archives(tmp_path):
    home = tmp_path / "home"
    logs = home / ".tsbridge/logs"
    logs.mkdir(parents=True)
    log = logs / "tsbridge.out.log"
    stamps = iter([1_700_000_000.0 + i * 60 for i in range(5)])
    for _ in range(5):
        log.write_bytes(b"z" * 2048)
        MODULE.rotate_large_logs(home, threshold=1024, keep=3, now=lambda: next(stamps))
    assert len(list(logs.glob("tsbridge.out.log.*.gz"))) == 3
