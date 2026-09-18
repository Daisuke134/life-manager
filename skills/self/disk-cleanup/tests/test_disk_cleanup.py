import errno
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

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
    candidate = tmp_path / "tmp" / "cfo-complete"
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


def test_open_or_protected_artifact_is_preserved(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    open_candidate = tmp_path / "tmp" / "cfo-open"
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
    disposable_candidate = temporary / "cfo-disposable"
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
        candidate = temporary / f"cfo-protected-{index}"
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
    candidate = temporary / "cfo-race"
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
    candidate = temporary / "cfo-lease-race"
    lease = temporary / "cfo-lease-race.lease"
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
    candidate = temporary / "cfo-lease-probe-error"
    lease = temporary / "cfo-lease-probe-error.lease"
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
    candidate = temporary / "cfo-open-race"
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
    for relative in (".cache/codex-runtimes", ".cache/whisper", "Library/Caches/org.swift.swiftpm"):
        (tmp_path / relative).mkdir(parents=True)
    governor = HostDiskGovernor(home=tmp_path, state_dir=tmp_path / "state")

    owners = {item["owner"]: Path(item["path"]) for item in governor.discover_candidates()}

    assert owners["codex-runtime-cache"] == tmp_path / ".cache/codex-runtimes"
    assert owners["whisper-model-cache"] == tmp_path / ".cache/whisper"
    assert owners["swiftpm-cache"] == tmp_path / "Library/Caches/org.swift.swiftpm"


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
    candidate = temporary / "cfo-lsof-error"
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


def test_run_once_never_blocks_producers_even_below_eleven_gib(tmp_path: Path, monkeypatch) -> None:
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
        usage=lambda: (11 * GiB - 1, 100 * GiB),
    )

    governor.run_once()

    assert not pressure.exists()


def test_run_once_global_budget_preserves_candidate_and_does_not_advance_full_marker(
    tmp_path: Path, monkeypatch
) -> None:
    clock = [0.0]
    candidate = tmp_path / "tmp" / "cfo-budget"
    candidate.mkdir(parents=True)
    monkeypatch.setattr(disk_cleanup.tempfile, "gettempdir", lambda: str(candidate.parent))

    def discover_candidates() -> list[dict]:
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


def test_run_once_rechecks_budget_after_lsof_before_reclaim(tmp_path: Path, monkeypatch) -> None:
    clock = [0.0]
    candidate = tmp_path / "tmp" / "cfo-lsof-budget"
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
        lambda: [
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
    candidate = tmp_path / "tmp" / "cfo-health-failure"
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
        lambda: (_ for _ in ()).throw(AssertionError("discovery must not run")),
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
    canary = tmp_path / "tmp" / "cfo-health-exception"
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
    canary = temp_root / "cfo-life-manager-canary"
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


def test_receipt_reserve_rejects_sparse_file_with_nonzero_blocks(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    reserve = state / ".receipt-reserve"
    with reserve.open("wb") as stream:
        stream.truncate(1024 * 1024)
        stream.seek(0)
        stream.write(b"x")
    reserve.chmod(0o600)
    sparse_before = reserve.stat()
    assert sparse_before.st_blocks > 0
    assert sparse_before.st_blocks * 512 < 1024 * 1024

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
