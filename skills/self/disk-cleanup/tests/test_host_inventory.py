import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

import host_inventory  # noqa: E402
from host_inventory import collect_host_inventory  # noqa: E402


def fake_runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    if argv[0].endswith("/df"):
        return subprocess.CompletedProcess(
            argv,
            0,
            "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
            "/dev/test 100 40 60 40% /test\n",
            "",
        )
    if argv[0].endswith("/mount"):
        return subprocess.CompletedProcess(
            argv,
            0,
            "/dev/test on /test (apfs, local)\n",
            "",
        )
    return subprocess.CompletedProcess(argv, 0, "8\t%s\n" % argv[-1], "")


def test_df_uses_kilobyte_blocks_matching_byte_parser() -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return fake_runner(argv, timeout=timeout)

    host_inventory._mounts(run=runner)

    assert [argv for argv in calls if argv[0].endswith("/df")] == [["/bin/df", "-kP"]]


def test_fast_inventory_is_atomic_and_records_coverage_gaps(tmp_path: Path) -> None:
    (tmp_path / "Projects").mkdir()
    state = tmp_path / "state"

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=state,
        runner=fake_runner,
    )

    written = json.loads((state / "host-inventory.json").read_text())
    assert written["schema_version"] == "life-manager-host-inventory-v1"
    assert written["inventory_sha256"] == payload["inventory_sha256"]
    assert written["mode"] == "fast"
    assert written["coverage"]["mount_count"] == 1
    assert written["coverage"]["root_count"] >= 10
    assert written["coverage"]["gaps"]
    assert all(root["measurement"] == "metadata-only" for root in written["roots"])


def test_inventory_uses_mount_metadata_for_local_writable_classification(tmp_path: Path) -> None:
    def runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/df"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/root 100 40 60 40% /\n"
                "/dev/data 200 100 100 50% /System/Volumes/Data\n",
                "",
            )
        if argv[0].endswith("/mount"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "/dev/root on / (apfs, local, read-only)\n"
                "/dev/data on /System/Volumes/Data (apfs, local)\n",
                "",
            )
        return subprocess.CompletedProcess(argv, 0, "8\t%s\n" % argv[-1], "")

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        runner=runner,
    )

    mounts = {mount["mount"]: mount for mount in payload["mounts"]}
    assert mounts["/"]["local"] is True
    assert mounts["/"]["writable"] is False
    assert mounts["/System/Volumes/Data"]["local"] is True
    assert mounts["/System/Volumes/Data"]["writable"] is True
    assert payload["coverage"]["local_writable_mounts"] == ["/System/Volumes/Data"]
    assert payload["coverage"]["missing_local_writable_mounts"] == []


def test_inventory_reports_local_writable_mount_missing_from_df(tmp_path: Path) -> None:
    def runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/df"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/root 100 40 60 40% /\n",
                "",
            )
        if argv[0].endswith("/mount"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "/dev/root on / (apfs, local, read-only)\n"
                "/dev/data on /System/Volumes/Data (apfs, local)\n",
                "",
            )
        return subprocess.CompletedProcess(argv, 0, "8\t%s\n" % argv[-1], "")

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        runner=runner,
    )

    coverage = payload["coverage"]
    assert coverage["local_writable_mounts"] == ["/System/Volumes/Data"]
    assert coverage["local_writable_mount_count"] == 1
    assert coverage["missing_local_writable_mounts"] == ["/System/Volumes/Data"]


def test_inventory_fails_closed_when_df_device_mount_lacks_metadata(tmp_path: Path) -> None:
    def runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/df"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/root 100 40 60 40% /\n"
                "/dev/data 200 100 100 50% /System/Volumes/Data\n",
                "",
            )
        if argv[0].endswith("/mount"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "/dev/root on / (apfs, local, read-only)\n",
                "",
            )
        return subprocess.CompletedProcess(argv, 0, "8\t%s\n" % argv[-1], "")

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        runner=runner,
    )

    data_mount = next(mount for mount in payload["mounts"] if mount["mount"] == "/System/Volumes/Data")
    assert data_mount["local"] is None
    assert data_mount["writable"] is None
    assert data_mount["mount_options"] is None
    assert payload["coverage"]["local_writable_mounts"] is None
    assert payload["coverage"]["local_writable_mount_count"] is None
    assert payload["coverage"]["missing_local_writable_mounts"] is None
    assert "mount-metadata:missing:/System/Volumes/Data" in payload["coverage"]["gaps"]


def test_inventory_excludes_devfs_and_autofs_from_local_writable_mounts(tmp_path: Path) -> None:
    def runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/df"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/root 100 40 60 40% /\n"
                "devfs 20 4 16 20% /dev\n"
                "map 30 4 26 14% /auto/test-user\n",
                "",
            )
        if argv[0].endswith("/mount"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "/dev/root on / (apfs, local)\n"
                "devfs on /dev (devfs, local)\n"
                "map auto_home on /auto/test-user (autofs, automounted)\n",
                "",
            )
        return subprocess.CompletedProcess(argv, 0, "8\t%s\n" % argv[-1], "")

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        runner=runner,
    )

    assert payload["coverage"]["local_writable_mounts"] == ["/"]
    mounts = {mount["mount"]: mount for mount in payload["mounts"]}
    assert mounts["/dev"]["local"] is True
    assert mounts["/auto/test-user"]["local"] is False


def test_inventory_parses_mount_and_df_paths_with_spaces(tmp_path: Path) -> None:
    mount_path = "/Volumes/External on Data"

    def runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/df"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                f"/dev/external 200 100 100 50% {mount_path}\n",
                "",
            )
        if argv[0].endswith("/mount"):
            return subprocess.CompletedProcess(
                argv,
                0,
                f"/dev/external on {mount_path} (apfs, local, journaled)\n",
                "",
            )
        return subprocess.CompletedProcess(argv, 0, "8\t%s\n" % argv[-1], "")

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        runner=runner,
    )

    mount = payload["mounts"][0]
    assert mount["mount"] == mount_path
    assert mount["mount_options"] == ["apfs", "journaled", "local"]
    assert mount["local"] is True
    assert mount["writable"] is True
    assert payload["coverage"]["local_writable_mounts"] == [mount_path]


def test_inventory_fails_closed_when_mount_metadata_times_out(tmp_path: Path) -> None:
    def runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/df"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/root 100 40 60 40% /\n",
                "",
            )
        if argv[0].endswith("/mount"):
            raise subprocess.TimeoutExpired(argv, timeout)
        return subprocess.CompletedProcess(argv, 0, "8\t%s\n" % argv[-1], "")

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        runner=runner,
    )

    mount = payload["mounts"][0]
    assert mount["local"] is None
    assert mount["writable"] is None
    assert mount["mount_options"] is None
    assert payload["coverage"]["local_writable_mounts"] is None
    assert payload["coverage"]["local_writable_mount_count"] is None
    assert payload["coverage"]["missing_local_writable_mounts"] is None
    assert "mount-metadata:TimeoutExpired" in payload["coverage"]["gaps"]


def test_full_inventory_recomputes_mount_timeout_after_df_consumes_budget(tmp_path: Path) -> None:
    clock = [0.0]
    probe_timeouts: list[tuple[str, float]] = []

    def runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        probe_timeouts.append((argv[0], timeout))
        if argv[0].endswith("/df"):
            clock[0] += 2.0
            return subprocess.CompletedProcess(
                argv,
                0,
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/root 100 40 60 40% /\n",
                "",
            )
        if argv[0].endswith("/mount"):
            return subprocess.CompletedProcess(
                argv,
                0,
                "/dev/root on / (apfs, local, read-only)\n",
                "",
            )
        return subprocess.CompletedProcess(argv, 0, "8\t%s\n" % argv[-1], "")

    collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        full=True,
        budget_seconds=3.0,
        runner=runner,
        clock=lambda: clock[0],
    )

    mount_calls = [timeout for argv, timeout in probe_timeouts if argv.endswith("/mount")]
    assert mount_calls
    assert mount_calls[0] <= 1.0


def test_full_inventory_uses_bounded_du_only_for_allowlisted_families(tmp_path: Path) -> None:
    for directory in ("Projects", "anicca-project", "gig", ".openclaw", "Library"):
        (tmp_path / directory).mkdir()

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        full=True,
        runner=fake_runner,
    )

    measurements = {root["measurement"] for root in payload["roots"]}
    assert "bounded-du" in measurements
    assert all(root["measurement"] in {"bounded-du", "metadata-only"} for root in payload["roots"])


def test_full_inventory_is_preserved_separately_from_fast_inventory(tmp_path: Path) -> None:
    state = tmp_path / "state"

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=state,
        full=True,
        runner=fake_runner,
    )

    full_path = state / "host-inventory-full.json"
    assert full_path.is_file()
    written = json.loads(full_path.read_text())
    assert written["mode"] == "full"
    assert written["inventory_sha256"] == payload["inventory_sha256"]
    assert not (state / "host-inventory.json").exists()


def test_full_inventory_allows_slow_allowlisted_root_with_bounded_timeout(tmp_path: Path) -> None:
    (tmp_path / "Projects").mkdir()

    def timeout_sensitive_runner(
        argv: list[str], *, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/du") and timeout < 10:
            raise subprocess.TimeoutExpired(argv, timeout)
        return fake_runner(argv, timeout=timeout)

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        full=True,
        runner=timeout_sensitive_runner,
    )

    projects = next(root for root in payload["roots"] if root["path"] == str(tmp_path / "Projects"))
    assert projects["measurement"] == "bounded-du"
    assert f"size-timeout:{tmp_path / 'Projects'}" not in payload["coverage"]["gaps"]


def test_du_timeout_preserves_unknown_size_with_owner_attribution(tmp_path: Path) -> None:
    projects_path = tmp_path / "Projects"
    projects_path.mkdir()

    def timeout_runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/du") and argv[-1] == str(projects_path):
            raise subprocess.TimeoutExpired(argv, timeout)
        return fake_runner(argv, timeout=timeout)

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        full=True,
        runner=timeout_runner,
    )

    projects = next(root for root in payload["roots"] if root["path"] == str(projects_path))
    assert projects["measurement"] == "timeout"
    assert projects["size_bytes"] is None
    assert projects["owner_family"] == "repository-worktree"
    assert f"size-timeout:{projects_path}" in payload["coverage"]["gaps"]


def test_inventory_replace_failure_preserves_target_and_removes_temporaries(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    state.mkdir()
    target = state / "host-inventory.json"
    target.write_text('{"old":true}\n')
    orphan = state / ".host-inventory.orphan"
    orphan.write_text("orphan")
    os.utime(orphan, (1, 1))
    monkeypatch.setattr(host_inventory.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("replace failed")))

    with pytest.raises(OSError, match="replace failed"):
        collect_host_inventory(home=tmp_path, state_dir=state, runner=fake_runner)

    assert target.read_text() == '{"old":true}\n'
    assert list(state.glob(".host-inventory.*")) == []


def test_full_inventory_gives_homebrew_a_longer_bounded_probe(tmp_path: Path) -> None:
    du_calls: list[tuple[str, float]] = []

    def recording_runner(
        argv: list[str], *, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/du"):
            du_calls.append((argv[-1], timeout))
        return fake_runner(argv, timeout=timeout)

    collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        full=True,
        runner=recording_runner,
    )

    assert ("/opt/homebrew", 30) in du_calls


def test_full_inventory_enforces_global_probe_budget(tmp_path: Path) -> None:
    for directory in (
        "Projects",
        "Projects/life-manager-main",
        "anicca-project",
        "anicca",
        "anicca-docs-tools",
        "anicca-portfolio-self-improve",
        "anicca-rtdash",
        "life-manager-repo-v0-retire",
        ".codex-worktrees",
        "gig",
        ".openclaw",
        "Library",
    ):
        (tmp_path / directory).mkdir(parents=True)

    clock = [0.0]
    du_timeouts: list[float] = []

    def budget_runner(
        argv: list[str], *, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/du"):
            du_timeouts.append(timeout)
            clock[0] += timeout
            raise subprocess.TimeoutExpired(argv, timeout)
        return fake_runner(argv, timeout=timeout)

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        full=True,
        runner=budget_runner,
        clock=lambda: clock[0],
    )

    assert sum(du_timeouts) <= 90
    assert any(gap.startswith("size-budget-exhausted:") for gap in payload["coverage"]["gaps"])


def test_full_inventory_records_partial_du_size_on_permission_error(tmp_path: Path) -> None:
    (tmp_path / "Projects").mkdir()

    def partial_runner(
        argv: list[str], *, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("/du"):
            return subprocess.CompletedProcess(argv, 1, f"64\t{argv[-1]}\n", "Operation not permitted")
        return fake_runner(argv, timeout=timeout)

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        full=True,
        runner=partial_runner,
    )

    projects = next(root for root in payload["roots"] if root["path"] == str(tmp_path / "Projects"))
    assert projects["size_bytes"] == 64 * 1024
    assert projects["measurement"] == "bounded-du-partial"
    assert f"size-permission-partial:{tmp_path / 'Projects'}" in payload["coverage"]["gaps"]


def test_full_inventory_zero_budget_skips_mount_and_size_probes(tmp_path: Path) -> None:
    def no_probe_runner(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"probe must not run with zero budget: {argv}")

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        full=True,
        runner=no_probe_runner,
        budget_seconds=0,
    )

    assert payload["mounts"] == []
    assert "inventory-budget-exhausted" in payload["coverage"]["gaps"]


def test_inventory_classifies_permission_limited_root(tmp_path: Path, monkeypatch) -> None:
    protected = tmp_path / "Library"
    protected.mkdir()
    real_scandir = host_inventory.os.scandir

    def permission_scandir(path):
        if Path(path) == protected:
            raise PermissionError("operation not permitted")
        return real_scandir(path)

    monkeypatch.setattr(host_inventory.os, "scandir", permission_scandir)

    payload = collect_host_inventory(home=tmp_path, state_dir=tmp_path / "state")

    assert f"permission-limited:{protected}" in payload["coverage"]["gaps"]


def test_inventory_reports_required_owner_family_coverage(tmp_path: Path) -> None:
    payload = collect_host_inventory(home=tmp_path, state_dir=tmp_path / "state")

    coverage = payload["coverage"]
    assert coverage["required_owner_families"]
    assert set(coverage["missing_owner_families"]).issubset(
        set(coverage["required_owner_families"])
    )


def test_inventory_persists_permission_boundary_owner_receipts(tmp_path: Path, monkeypatch) -> None:
    tcc = tmp_path / "Library" / "Application Support" / "com.apple.TCC"
    trash = tmp_path / ".Trash"
    system_tmp = Path("/private/tmp")
    system_folders = Path("/private/var/folders")
    boundary_paths = {tcc, trash, system_tmp, system_folders}
    real_lstat = host_inventory.os.lstat
    real_scandir = host_inventory.os.scandir

    def fake_lstat(path):
        path = Path(path)
        if path == system_tmp:
            raise FileNotFoundError(path)
        if path == system_folders:
            return os.stat_result((stat.S_IFLNK | 0o755, 0, 0, 1, 0, 0, 0, 0, 0, 0))
        if path in boundary_paths:
            return os.stat_result((stat.S_IFDIR | 0o755, 0, 0, 1, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    class EmptyScan:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_scandir(path):
        path = Path(path)
        if path == trash:
            raise PermissionError(path)
        if path == tcc:
            return EmptyScan()
        return real_scandir(path)

    monkeypatch.setattr(host_inventory.os, "lstat", fake_lstat)
    monkeypatch.setattr(host_inventory.os, "scandir", fake_scandir)

    payload = collect_host_inventory(
        home=tmp_path,
        state_dir=tmp_path / "state",
        runner=fake_runner,
    )

    receipts = payload["permission_owner_receipts"]
    assert {
        (receipt["path"], receipt["owner_family"])
        for receipt in receipts
    } == {
        (str(tcc), "user-library"),
        (str(trash), "downloads-trash"),
        (str(system_tmp), "system-temp"),
        (str(system_folders), "system-temp"),
    }
    assert all(receipt["reclaim_eligible"] is False for receipt in receipts)
    classifications = {
        (receipt["path"], receipt["access"])
        for receipt in receipts
    }
    assert (str(tcc), "readable") in classifications
    assert (str(trash), "permission-error") in classifications
    assert (str(system_tmp), "missing") in classifications
    assert (str(system_folders), "symlink") in classifications
    assert all("children" not in receipt for receipt in receipts)

    persisted = json.loads((tmp_path / "state" / "host-inventory.json").read_text())
    assert persisted["permission_owner_receipts"] == receipts


def test_storage_growth_tracks_exact_owner_and_keeps_unknowns():
    previous = {"observed_at": "2026-10-09T00:00:00Z", "roots": [{"path": "/srv/lm/a", "size_bytes": 0}], "coverage": {"gaps": []}}
    current = {"observed_at": "2026-10-09T00:01:00Z", "roots": [{"path": "/srv/lm/a", "size_bytes": 100 * 1024**2}, {"path": "/srv/lm/new", "size_bytes": None}], "coverage": {"gaps": ["partial"]}}
    result = host_inventory.project_storage_growth(previous, current, {"/srv/lm/a": ["alpha"]})
    assert result["roots"][0]["delta_bytes"] == 100 * 1024**2
    assert result["roots"][0]["elapsed_seconds"] == 60
    assert result["roots"][0]["bytes_per_second"] == (100 * 1024**2) / 60
    assert result["roots"][0]["owner_id"] == "alpha"
    assert result["roots"][1]["bytes_per_second"] is None
    assert result["roots"][1]["owner_id"] is None
    bad = host_inventory.project_storage_growth(previous, {**current, "observed_at": "2026-10-08T00:00:00Z"}, {})
    assert bad["roots"][0]["bytes_per_second"] is None


def test_inventory_persists_growth_without_changing_cleanup_authority(tmp_path):
    state = tmp_path / "state"
    first = collect_host_inventory(home=tmp_path, state_dir=state, runner=fake_runner)
    assert first["storage_growth"]["non_additive"] is True
    assert first["storage_growth"]["roots"]
    written = json.loads((state / "host-inventory.json").read_text())
    assert written["storage_growth"] == first["storage_growth"]


def test_shared_storage_roots_are_observed_as_metadata(tmp_path):
    paths = {r["path"] for r in collect_host_inventory(home=tmp_path, state_dir=tmp_path / "state", runner=fake_runner)["roots"]}
    assert str(tmp_path / ".local/state/life-manager") in paths
    assert str(tmp_path / "loops/releases") in paths


@pytest.mark.parametrize("first_timeout", (False, True))
def test_full_inventory_advances_past_budget_to_session_root(tmp_path, monkeypatch, first_timeout):
    families = (("repository-worktree", "{home}/Projects"),
                ("agent-runtime", "{home}/loops"),
                ("agent-session", "{home}/.codex-acct2"))
    monkeypatch.setattr(host_inventory, "ROOT_FAMILIES", families)
    for _, template in families:
        Path(template.format(home=tmp_path)).mkdir()
    clock, calls = [0.0], []
    def runner(argv, *, timeout):
        if argv[0].endswith("/du"):
            calls.append(argv[-1])
            clock[0] += timeout
            if first_timeout and Path(argv[-1]).name == "Projects":
                raise subprocess.TimeoutExpired(argv, timeout)
        return fake_runner(argv, timeout=timeout)
    payloads = []
    for _ in range(3):
        clock[0] = 0.0
        payloads.append(collect_host_inventory(home=tmp_path,state_dir=tmp_path/"state",
            full=True,runner=runner,clock=lambda:clock[0],budget_seconds=1))
    expected = [str(Path(template.format(home=tmp_path))) for _,template in families]
    assert calls == expected
    first_again = next(r for r in payloads[1]["roots"] if r["path"] == expected[0])
    assert first_again["size_bytes"] is None
    if first_timeout:
        assert first_again["size_sample"] is None
    else:
        assert first_again["size_sample"]["size_bytes"] == 8192
    delta = next(r for r in payloads[1]["storage_growth"]["roots"] if r["path"] == expected[0])
    assert delta["delta_bytes"] is None


def test_growth_uses_last_real_sample_time_after_unmeasured_pass():
    path = "/srv/lm/large"
    previous = {"observed_at":"2026-10-09T00:09:00Z", "roots":[{"path":path,"size_bytes":None,
        "size_sample":{"size_bytes":100,"observed_at":"2026-10-09T00:00:00Z"}}]}
    current = {"observed_at":"2026-10-09T00:10:00Z", "roots":[{"path":path,"size_bytes":700,
        "size_sample":{"size_bytes":700,"observed_at":"2026-10-09T00:10:00Z"}}]}
    result = host_inventory.project_storage_growth(previous,current,{})["roots"][0]
    assert result["delta_bytes"] == 600
    assert result["elapsed_seconds"] == 600
    assert result["bytes_per_second"] == 1
