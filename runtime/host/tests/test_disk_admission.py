from __future__ import annotations

import importlib.util
import base64
import hashlib
import io
import json
import os
import pwd
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from threading import Event
from types import SimpleNamespace
from pathlib import Path

import pytest


GUARD = Path(__file__).resolve().parents[1] / "disk_admission.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("disk_admission_test", GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("available", (0, None, 2 * 1024**3 - 1, 2 * 1024**3))
def test_capacity_check_defers_before_child_or_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys, available,
):
    guard = load_guard()
    probes, children = [], []
    monkeypatch.setattr(guard, "disk_free_bytes", lambda p: probes.append(p) or available)
    monkeypatch.setattr(guard.os, "execvpe", lambda program, args, env: children.append((program, args)))
    target = tmp_path / "future" / "releases"
    result = guard.main(["--check-free-space", str(target)])
    assert result == (0 if available == guard.RECOVERY_FLOOR_BYTES else 75)
    assert children == []
    assert probes == [tmp_path]
    assert not target.parent.exists()
    if result == 75:
        receipt = json.loads(capsys.readouterr().out.strip())
        assert receipt["status"] == "deferred"
        assert receipt["available_bytes"] == available
        assert receipt["required_bytes"] == guard.RECOVERY_FLOOR_BYTES
        assert receipt["effect"] == receipt["readback"] == 0


def _write_cleanup_recovery_signal(path: Path) -> None:
    path.write_text(json.dumps({
        "owner_id": "host-disk-recovery",
        "reason": "disk_headroom_low",
        "required_bytes": 2 * 1024**3,
        "next_action": "restore_capacity_and_install_shared_disk_gate",
    }) + "\n", encoding="utf-8")
    path.chmod(0o600)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs:
                        pytest.fail("unexpected network access"))
    home = tmp_path / "home"
    host_state = home / ".local/state/life-manager/state"
    producer_state = home / ".local/state/life-manager/producer"
    host_state.mkdir(parents=True)
    producer_state.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LIFE_MANAGER_HOST_STATE_DIR", str(host_state))
    monkeypatch.setenv("LIFE_MANAGER_PRODUCER_STATE_DIR", str(producer_state))
    healthy = 16 * 1024**3
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: SimpleNamespace(
        total=healthy, used=0, free=healthy,
    ))
    for key in (
        "GIG_DISK_HEADROOM_KIB", "GIG_HOST_STATE_DIR", "GIG_STATE_DIR",
        "OPENCLAW_STATE_DIR", "DISK_CONTROL_STATE_DIR",
        "LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP",
        "LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK",
    ):
        monkeypatch.delenv(key, raising=False)


def test_host_state_uses_os_owner_home_not_environment_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    home = tmp_path / "fresh-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("LIFE_MANAGER_HOST_STATE_DIR")
    monkeypatch.delenv("LIFE_MANAGER_PRODUCER_STATE_DIR")
    guard = load_guard()
    owner_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert guard._host_state_dir() == owner_home / ".local/state/life-manager/state"
    assert guard._state_dir() == home / ".local/state/life-manager"


def test_disk_free_bytes_measures_the_requested_receipt_volume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    path = tmp_path / "receipt-volume"
    calls = []
    guard = load_guard()
    monkeypatch.setattr(guard.shutil, "disk_usage", lambda actual: (
        calls.append(actual) or SimpleNamespace(total=100, used=40, free=60)
    ))

    assert guard.disk_free_bytes(path) == 60
    assert calls == [path]


@pytest.mark.parametrize("free_bytes", (0, 12 * 1024**3 - 1))
def test_regular_producer_defers_below_disk_floor(
    tmp_path, monkeypatch, capsys, free_bytes,
):
    guard = load_guard()
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", "line-sticker-factory-hourly")
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: free_bytes)
    calls = []
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: calls.append(args))

    assert guard.main(["/bin/true"]) == 75
    assert calls == []
    receipt = json.loads(capsys.readouterr().out.strip())
    assert receipt["status"] == "deferred"
    assert receipt["reason"] == "disk_floor_low"
    assert receipt["required_bytes"] == guard.PRODUCER_FLOOR_BYTES


@pytest.mark.parametrize("free_bytes", (12 * 1024**3, None))
def test_regular_producer_runs_at_floor_or_unknown_free_space(
    tmp_path, monkeypatch, free_bytes,
):
    guard = load_guard()
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", "line-sticker-factory-hourly")
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: free_bytes)
    calls = []
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: calls.append(args))

    assert guard.main(["/bin/true"]) == 0
    assert calls and calls[0][1] == ["/bin/true"]


@pytest.mark.parametrize("loop_id", ("life-manager-disk-cleanup", "lm-fence-reconciler", "browser-recycle-idle", "warmup-flip-daily"))
def test_control_plane_runs_below_disk_floor(monkeypatch, loop_id):
    guard = load_guard()
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", loop_id)
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: 0)
    calls = []
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: calls.append(args))

    assert guard.main(["/bin/true"]) == 0
    assert calls


@pytest.mark.parametrize("free_bytes", (None, -1, True, "unknown", "missing"))
def test_disk_free_bytes_returns_unavailable_for_invalid_measurements(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, free_bytes,
):
    guard = load_guard()
    if free_bytes is None:
        monkeypatch.setattr(guard.shutil, "disk_usage", lambda _path: (_ for _ in ()).throw(OSError()))
    elif free_bytes == "missing":
        monkeypatch.setattr(guard.shutil, "disk_usage", lambda _path: SimpleNamespace())
    else:
        monkeypatch.setattr(guard.shutil, "disk_usage", lambda _path: SimpleNamespace(
            total=100, used=40, free=free_bytes,
        ))

    assert guard.disk_free_bytes(tmp_path) is None


def test_cleanup_stop_signal_does_not_block_child(monkeypatch: pytest.MonkeyPatch):
    host_state = Path(os.environ["LIFE_MANAGER_HOST_STATE_DIR"])
    _write_cleanup_recovery_signal(host_state / "disk-writers.stop")
    guard = load_guard()
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", "life-manager-disk-cleanup")
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: 0)
    calls = []
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: calls.append(args))

    assert guard.main(["/bin/true"]) == 0
    assert calls and calls[0][1] == ["/bin/true"]


def test_cleanup_recovery_signal_does_not_defer_regular_producer(monkeypatch: pytest.MonkeyPatch):
    host_state = Path(os.environ["LIFE_MANAGER_HOST_STATE_DIR"])
    _write_cleanup_recovery_signal(host_state / "disk-writers.stop")
    guard = load_guard()
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", "job-search-daily")
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: 20 * 1024**3)
    calls = []
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: calls.append(args))

    assert guard.main(["/bin/true"]) == 0
    assert calls and calls[0][1] == ["/bin/true"]


def test_operator_stop_signal_still_blocks_child(monkeypatch: pytest.MonkeyPatch):
    host_state = Path(os.environ["LIFE_MANAGER_HOST_STATE_DIR"])
    host_state.joinpath("disk-writers.stop").write_text("owner=operator\n", encoding="utf-8")
    guard = load_guard()
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: 0)
    calls = []
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: calls.append(args))

    assert guard.main(["/bin/true"]) == 1
    assert calls == []
    receipt = json.loads(
        (Path(os.environ["LIFE_MANAGER_PRODUCER_STATE_DIR"])
         / "state/disk-headroom.json").read_text(encoding="utf-8")
    )
    assert receipt["reason"] == "disk_writers_stop"


def test_fresh_policy_directory_is_created_private(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    host_state = tmp_path / "missing"
    monkeypatch.setenv("LIFE_MANAGER_HOST_STATE_DIR", str(host_state))
    guard = load_guard()
    assert guard.disk_headroom_ok() is True
    assert host_state.stat().st_mode & 0o777 == 0o700


def test_fresh_producer_state_is_created_before_disk_measurement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    producer_state = tmp_path / "new" / "producer"
    monkeypatch.setenv("LIFE_MANAGER_PRODUCER_STATE_DIR", str(producer_state))
    guard = load_guard()
    assert guard.disk_headroom_ok() is True
    assert producer_state.stat().st_mode & 0o777 == 0o700


def test_symlink_policy_directory_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("LIFE_MANAGER_HOST_STATE_DIR", str(alias))
    guard = load_guard()
    assert guard.disk_headroom_ok() is False


def test_pressure_marker_is_advisory(monkeypatch: pytest.MonkeyPatch):
    host_state = Path(os.environ["LIFE_MANAGER_HOST_STATE_DIR"])
    host_state.joinpath("disk-pressure.block").write_text("blocked\n", encoding="utf-8")
    guard = load_guard()
    assert guard.disk_headroom_ok() is True


def test_cli_requires_child_command():
    guard = load_guard()
    assert guard.main([]) == 2

@pytest.mark.parametrize("available,required,expected", [(1024,1024,0),(1023,1024,75),(None,1024,75),(1024,0,2),(1024,-1,2)])
def test_measured_capacity_check(monkeypatch, tmp_path, capsys, available, required, expected):
    guard = load_guard()
    monkeypatch.setattr(guard, "disk_free_bytes", lambda p: available)
    assert guard.main(["--check-free-space", str(tmp_path), str(required)]) == expected
    if expected == 75:
        receipt = json.loads(capsys.readouterr().out)
        assert receipt["required_bytes"] == required
        assert receipt["effect"] == receipt["readback"] == 0


def _release_capacity_fixture(tmp_path: Path):
    guard = load_guard()
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True,
                              capture_output=True, text=True)

    git("init", "--quiet")
    git("config", "user.name", "disk-admission-test")
    git("config", "user.email", "disk-admission-test@example.invalid")
    (repo / "runtime").mkdir()
    (repo / "runtime" / "fixture.py").write_text("VALUE = 1\n")
    (repo / "README.md").write_text("fixture\n")
    git("add", "README.md", "runtime/fixture.py")
    git("commit", "--quiet", "-m", "fixture")
    sha = git("rev-parse", "HEAD").stdout.strip()
    git("update-ref", "refs/remotes/origin/main", sha)

    loops = tmp_path / "loops"
    donor = loops / "releases" / "seed"
    donor.mkdir(parents=True)
    (donor / "RELEASE.json").write_text(json.dumps({
        "sha": sha,
        "release_paths": "ALL",
        "provenance": "ancestor-of-origin-main",
        "runtime_python": str(Path(sys.executable).resolve()),
        "runtime_python_cache_tag": sys.implementation.cache_tag,
    }))
    donor.chmod(0o555)
    (loops / "current").symlink_to(donor, target_is_directory=True)
    return guard, repo, sha, loops


def test_release_capacity_uses_staging_budget_without_diagnostic_floor(tmp_path: Path):
    guard, repo, sha, loops = _release_capacity_fixture(tmp_path)

    required = guard.release_capacity_bytes(repo, sha, loops, "node", "npm")

    assert 64 * 1024**2 < required < 65 * 1024**2


def test_release_capacity_measurement_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys,
):
    guard = load_guard()
    monkeypatch.setattr(
        guard, "release_capacity",
        lambda *_args: (_ for _ in ()).throw(ValueError("fixture measurement failure")),
    )

    assert guard.main([
        "--release-capacity", str(tmp_path), "a" * 40, str(tmp_path), "node", "npm",
    ]) == 1
    assert capsys.readouterr().out == ""


def _fresh_capacity_fixture(tmp_path: Path, entries: dict):
    guard, repo, _sha, loops = _release_capacity_fixture(tmp_path)
    (loops / "current").unlink()
    for relative in ("", "runtime/agentmail"):
        directory = repo / relative
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "package.json").write_text('{"name":"fixture","version":"1.0.0"}')
        (directory / "package-lock.json").write_text(json.dumps({
            "lockfileVersion": 3, "packages": {"": {}, **entries},
        }))
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "locked packages"], check=True)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    return guard, repo, sha, loops


def _capacity_donor(repo: Path, loops: Path, relatives, name="prior"):
    donor = loops / "releases" / name
    donor.mkdir()
    (donor / "RELEASE.json").write_bytes(
        (loops / "releases/seed/RELEASE.json").read_bytes())
    for relative in relatives:
        directory = donor / relative
        directory.mkdir(parents=True, exist_ok=True)
        package = json.loads((repo / relative / "package.json").read_bytes())
        package["scripts"] = {"test": "old script alias"}
        (directory / "package.json").write_text(json.dumps(package))
        lock = (repo / relative / "package-lock.json").read_bytes()
        (directory / "package-lock.json").write_bytes(lock)
        key = hashlib.sha256(f"{name}:{relative}".encode()).hexdigest()
        bundle = loops / "dependency-bundles" / ("npm-" + key)
        (bundle / "node_modules").mkdir(parents=True)
        (bundle / "node_modules/.package-lock.json").write_bytes(lock)
        (bundle / ".complete").write_text(key + "\n")
        bundle.chmod(0o555)
        (directory / "node_modules").symlink_to(bundle / "node_modules")
    donor.chmod(0o555)
    return donor


def _locked_capacity_package():
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as stream:
        entry = tarfile.TarInfo("package/index.js")
        entry.size = 1024**2
        stream.addfile(entry, io.BytesIO(b"x" * entry.size))
    payload = archive.getvalue()
    package = {"version": "1.0.0", "resolved": "https://registry.npmjs.org/fixture/-/fixture-1.0.0.tgz",
               "integrity": "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode()}
    metadata = {"name": "fixture", "version": "1.0.0", "dist": {
        "tarball": package["resolved"], "integrity": package["integrity"],
        "unpackedSize": entry.size, "fileCount": 1,
    }}
    return package, metadata, payload


@pytest.mark.parametrize("empty", (False, True))
def test_release_capacity_bootstraps_without_current(monkeypatch, tmp_path, empty):
    package, metadata, _payload = _locked_capacity_package()
    entries = {} if empty else {"node_modules/fixture": package,
                               "node_modules/dev-only": {"dev": True}}
    guard, repo, sha, loops = _fresh_capacity_fixture(tmp_path, entries)
    requests = []
    def fetch(url, **_kwargs):
        requests.append(url)
        return io.BytesIO(json.dumps(metadata).encode())
    monkeypatch.setattr(urllib.request, "urlopen", fetch)
    required, install = guard.release_capacity(repo, sha, loops, "node", "npm")
    assert required > 64 * 1024**2
    if not empty:
        assert required >= 67 * 1024**2
    assert install is True
    assert requests == ([] if empty else ["https://registry.npmjs.org/fixture/1.0.0"])
    assert not (loops / "current").exists()
    assert not (loops / "dependency-bundles").exists()


def test_release_capacity_measures_locked_tar_only_when_metadata_lacks_sizes(monkeypatch, tmp_path):
    package, metadata, payload = _locked_capacity_package()
    metadata["dist"].pop("unpackedSize")
    metadata["dist"].pop("fileCount")
    guard, repo, sha, loops = _fresh_capacity_fixture(tmp_path, {"node_modules/fixture": package})
    requests = []
    class TarResponse(io.BytesIO):
        def read(self, size=-1):
            assert size >= 0, "tarball must be measured as a bounded stream"
            return super().read(size)
    def fetch(url, **_kwargs):
        requests.append(url)
        return TarResponse(payload) if url == package["resolved"] else io.BytesIO(json.dumps(metadata).encode())
    monkeypatch.setattr(urllib.request, "urlopen", fetch)
    required, install = guard.release_capacity(repo, sha, loops, "node", "npm")
    assert required > 66 * 1024**2
    assert install is True
    assert requests == ["https://registry.npmjs.org/fixture/1.0.0", package["resolved"]]
    assert not (loops / "dependency-bundles").exists()


@pytest.mark.parametrize("failure", ("http", "metadata", "integrity", "lock"))
def test_first_release_measurement_failure_remains_closed(monkeypatch, tmp_path, capsys, failure):
    package, metadata, payload = _locked_capacity_package()
    if failure == "lock":
        package.pop("resolved")
    if failure == "metadata":
        metadata["version"] = "2.0.0"
    if failure == "integrity":
        metadata["dist"].pop("unpackedSize")
        package["integrity"] = metadata["dist"]["integrity"] = "sha512-" + base64.b64encode(
            hashlib.sha512(b"different locked tarball").digest()).decode()
    entries = {"node_modules/fixture": package}
    if failure == "http":
        entries.update({f"node_modules/fixture-{index}": {
            **package, "resolved": package["resolved"].replace("/fixture/", f"/fixture-{index}/"),
        } for index in range(8)})
    guard, repo, sha, loops = _fresh_capacity_fixture(tmp_path, entries)
    requests = []
    first_request = Event()
    def fetch(url, **_kwargs):
        requests.append(url)
        if failure == "http":
            if len(requests) == 1:
                first_request.wait(0.1)
            elif len(requests) > 8:
                first_request.set()
            raise OSError("fixture registry unavailable")
        return io.BytesIO(payload if url.endswith(".tgz") else json.dumps(metadata).encode())
    monkeypatch.setattr(urllib.request, "urlopen", fetch)
    assert guard.main(["--release-capacity", str(repo), sha, str(loops), "node", "npm"]) == 1
    receipt = json.loads(capsys.readouterr().err)
    assert receipt["reason"] == "release_capacity_measurement_failed"
    assert receipt["effect"] == receipt["readback"] == 0
    if failure == "http":
        assert len(requests) <= 8


@pytest.mark.parametrize("invalid", ("dangling", "descriptor"))
def test_invalid_current_is_not_treated_as_first_install(tmp_path, capsys, invalid):
    package, _metadata, _payload = _locked_capacity_package()
    guard, repo, sha, loops = _fresh_capacity_fixture(tmp_path, {"node_modules/fixture": package})
    _capacity_donor(repo, loops, ("", "runtime/agentmail"))
    current = loops / "current"
    if invalid == "dangling":
        current.symlink_to(loops / "missing-release")
    else:
        current.mkdir()
        (current / "RELEASE.json").write_text("{}")
    assert guard.main(["--release-capacity", str(repo), sha, str(loops), "node", "npm"]) == 1
    assert json.loads(capsys.readouterr().err)["reason"] == "release_capacity_measurement_failed"


@pytest.mark.parametrize("layout", ("one", "split", "invalid_first", "python_alias"))
def test_release_capacity_without_current_reuses_each_root(monkeypatch, tmp_path, layout):
    guard, repo, sha, loops = _fresh_capacity_fixture(tmp_path, {})
    groups = (("",), ("runtime/agentmail",)) if layout == "split" else (("", "runtime/agentmail"),)
    for index, relatives in enumerate(groups):
        donor = _capacity_donor(repo, loops, relatives, f"prior-{index}")
    if layout == "invalid_first":
        invalid = _capacity_donor(repo, loops, ("", "runtime/agentmail"), "00-invalid")
        (invalid / "RELEASE.json").write_text("[]")
    if layout == "python_alias":
        link = tmp_path / "python-alias"
        link.symlink_to(Path(sys.executable).resolve())
        descriptor = json.loads((donor / "RELEASE.json").read_text())
        descriptor["runtime_python"] = str(link)
        (donor / "RELEASE.json").write_text(json.dumps(descriptor))
    fresh = []
    monkeypatch.setattr(guard, "_fresh_dependency_bytes", lambda manifests, _block: fresh.append(manifests) or 0)

    required, install = guard.release_capacity(repo, sha, loops, "node-next", "npm-next")

    assert fresh == [], "reusable historical bundles were charged as fresh installs"
    assert install is False
    assert 64 * 1024**2 < required < 65 * 1024**2
    assert not os.path.lexists(loops / "current")


@pytest.mark.parametrize("unusable", ("missing", "manifest", "lock", "incomplete"))
def test_release_capacity_without_current_measures_only_unreused_roots(monkeypatch, tmp_path, unusable):
    guard, repo, sha, loops = _fresh_capacity_fixture(tmp_path, {})
    donor = _capacity_donor(repo, loops, ("", "runtime/agentmail"))
    directory = donor / "runtime/agentmail"
    if unusable == "missing":
        (directory / "node_modules").unlink()
    elif unusable == "manifest":
        (directory / "package.json").write_text('{"name":"different","version":"1.0.0"}')
    elif unusable == "lock":
        with (directory / "package-lock.json").open("ab") as handle:
            handle.write(b"\n")
    else:
        bundle = (directory / "node_modules").resolve().parent
        bundle.chmod(0o755)
        (bundle / ".complete").unlink()
        bundle.chmod(0o555)
    fresh = []
    monkeypatch.setattr(guard, "_fresh_dependency_bytes", lambda manifests, _block: fresh.append(manifests) or 0)

    required, install = guard.release_capacity(repo, sha, loops, "node", "npm")

    expected = [("runtime/agentmail", [(repo / "runtime/agentmail" / name).read_bytes()
                                      for name in ("package.json", "package-lock.json")])]
    assert fresh == [expected], "fresh capacity must measure only the unmatched root"
    assert install is True, "an unmatched empty lock still needs npm ci admission"
    assert 64 * 1024**2 < required < 65 * 1024**2


@pytest.mark.parametrize("invalid", ("sparse", "provenance", "writable", "reclaimed", "python", "cache_tag", "ancestry"))
def test_release_capacity_without_current_does_not_reuse_invalid_donors(monkeypatch, tmp_path, invalid):
    guard, repo, sha, loops = _fresh_capacity_fixture(tmp_path, {})
    donor = _capacity_donor(repo, loops, ("", "runtime/agentmail"))
    if invalid == "writable":
        donor.chmod(0o755)
    elif invalid == "reclaimed":
        donor.chmod(0o755)
        (donor / "RECLAIMED-RELEASE.json").write_text("{}")
        donor.chmod(0o555)
    else:
        descriptor = json.loads((donor / "RELEASE.json").read_text())
        field, value = {
            "sparse": ("release_paths", ["runtime"]),
            "provenance": ("provenance", "candidate"),
            "python": ("runtime_python", "/fixture/different-python"),
            "cache_tag": ("runtime_python_cache_tag", "different-tag"),
            "ancestry": ("sha", "f" * 40),
        }[invalid]
        descriptor[field] = value
        (donor / "RELEASE.json").write_text(json.dumps(descriptor))
    fresh = []
    monkeypatch.setattr(guard, "_fresh_dependency_bytes", lambda manifests, _block: fresh.append(manifests) or 0)

    _required, install = guard.release_capacity(repo, sha, loops, "node", "npm")

    expected = [(relative, [(repo / relative / name).read_bytes()
                            for name in ("package.json", "package-lock.json")])
                for relative in ("", "runtime/agentmail")]
    assert fresh == [expected]
    assert install is True


def test_release_capacity_reuses_locked_bundle_for_script_and_toolchain_change(tmp_path: Path):
    import hashlib
    import platform
    guard, repo, seed_sha, loops = _release_capacity_fixture(tmp_path)
    donor = (loops / "current").resolve()
    old = json.dumps({"name": "fixture", "version": "1.0.0", "scripts": {"test": "old"}}).encode()
    lock = b'{"lockfileVersion":3}\n'
    donor.chmod(0o755)
    (donor / "package.json").write_bytes(old)
    (donor / "package-lock.json").write_bytes(lock)
    header = "\0".join(("command", "npm-ci --omit=dev --ignore-scripts", "os", platform.system(),
                          "arch", platform.machine(), "node", "node", "npm", "npm")) + "\0"
    key_data = header.encode()
    for label, payload in (("package-json", old), ("package-lock", lock)):
        key_data += label.encode() + b"\0" + (hashlib.sha256(payload).hexdigest() + "  -\n").encode()
    key = hashlib.sha256(key_data).hexdigest()
    bundle = loops / "dependency-bundles" / ("npm-" + key)
    (bundle / "node_modules").mkdir(parents=True)
    (bundle / "node_modules/.package-lock.json").write_bytes(lock)
    (bundle / ".complete").write_text(key + "\n")
    bundle.chmod(0o555)
    (donor / "node_modules").symlink_to(bundle / "node_modules")
    donor.chmod(0o555)
    (repo / "package-lock.json").write_bytes(lock)

    def commit_package(package):
        (repo / "package.json").write_text(json.dumps(package))
        subprocess.run(["git", "-C", str(repo), "add", "package.json", "package-lock.json"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "package"], check=True)
        sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", sha], check=True)
        return sha

    package = {"name": "fixture", "version": "1.0.0", "scripts": {"test": "new"}}
    sha = commit_package(package)
    try:
        required = guard.release_capacity_bytes(repo, sha, loops, "node-next", "npm-next")
        assert 64 * 1024**2 < required < guard.RECOVERY_FLOOR_BYTES
        assert list((loops / "dependency-bundles").iterdir()) == [bundle]
        assert (donor / "package.json").read_bytes() == old
        # A dependency change used to raise here and block every release on main (2026-10-16,
        # #8168 added one package). Budget a fresh install the size of the donor's tree instead.
        bundle.chmod(0o755)
        (bundle / "node_modules" / "big.bin").write_bytes(b"\0" * (8 * 1024**2))
        bundle.chmod(0o555)
        package["dependencies"] = {"changed": "1.0.0"}
        changed_sha = commit_package(package)
        changed = guard.release_capacity_bytes(repo, changed_sha, loops, "node", "npm")
        assert changed >= required + 8 * 1024**2
    finally:
        donor.chmod(0o755)
        bundle.chmod(0o755)


def test_release_capacity_accepts_a_donor_that_recorded_the_python_symlink(tmp_path: Path):
    # 2026-10-23: one release recorded runtime_python as the Homebrew opt/ symlink while the running
    # interpreter resolves to the Cellar path. The raw string compare then rejected that donor and
    # every later release cut failed with "donor is not a complete immutable runtime".
    import hashlib
    import platform
    guard, repo, _seed_sha, loops = _release_capacity_fixture(tmp_path)
    donor = (loops / "current").resolve()
    link = tmp_path / "python-link"
    link.symlink_to(Path(sys.executable).resolve())
    donor.chmod(0o755)
    descriptor = json.loads((donor / "RELEASE.json").read_text())
    descriptor["runtime_python"] = str(link)
    (donor / "RELEASE.json").write_text(json.dumps(descriptor))
    package = json.dumps({"name": "fixture", "version": "1.0.0"}).encode()
    lock = b'{"lockfileVersion":3}\n'
    (donor / "package.json").write_bytes(package)
    (donor / "package-lock.json").write_bytes(lock)
    header = "\0".join(("command", "npm-ci --omit=dev --ignore-scripts", "os", platform.system(),
                        "arch", platform.machine(), "node", "node", "npm", "npm")) + "\0"
    key_data = header.encode()
    for label, payload in (("package-json", package), ("package-lock", lock)):
        key_data += label.encode() + b"\0" + (hashlib.sha256(payload).hexdigest() + "  -\n").encode()
    key = hashlib.sha256(key_data).hexdigest()
    bundle = loops / "dependency-bundles" / ("npm-" + key)
    (bundle / "node_modules").mkdir(parents=True)
    (bundle / "node_modules/.package-lock.json").write_bytes(lock)
    (bundle / ".complete").write_text(key + "\n")
    bundle.chmod(0o555)
    (donor / "node_modules").symlink_to(bundle / "node_modules")
    donor.chmod(0o555)
    (repo / "package.json").write_bytes(package)
    (repo / "package-lock.json").write_bytes(lock)
    subprocess.run(["git", "-C", str(repo), "add", "package.json", "package-lock.json"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "package"], check=True)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", sha], check=True)
    try:
        assert guard.release_capacity_bytes(repo, sha, loops, "node", "npm") > 0
    finally:
        donor.chmod(0o755)
        bundle.chmod(0o755)


def test_revenue_producer_runs_down_to_the_lower_revenue_floor(tmp_path, monkeypatch):
    # Kubernetes evicts low-priority pods first; a flat 12 GiB floor stopped every revenue lane
    # at 11 GiB while background batches kept the same rights (2026-10-16).
    guard = load_guard()
    registry = tmp_path / "config" / "loop-registry.json"
    registry.parent.mkdir()
    registry.write_text(json.dumps({"loops": {
        "earner": {"admission_class": "revenue"}, "batch": {"admission_class": "borrow"}}}))
    monkeypatch.setenv("LIFE_MANAGER_REPO", str(tmp_path))
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: 11 * 1024**3)
    assert guard._producer_gate("earner") is None
    assert guard._producer_gate("batch")[0] == "disk_floor_low"
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: guard.REVENUE_FLOOR_BYTES - 1)
    assert guard._producer_gate("earner")[0] == "disk_floor_low"
    assert guard._floor_bytes("earner") == guard.REVENUE_FLOOR_BYTES
    monkeypatch.setenv("LIFE_MANAGER_PRODUCER_FLOOR_BYTES", str(1024**3))
    assert guard._floor_bytes("earner") == 1024**3


def test_revenue_deferral_receipt_reports_the_floor_it_used(tmp_path, monkeypatch, capsys):
    guard = load_guard()
    registry = tmp_path / "config" / "loop-registry.json"
    registry.parent.mkdir()
    registry.write_text(json.dumps({"loops": {"earner": {"admission_class": "revenue"}}}))
    monkeypatch.setenv("LIFE_MANAGER_REPO", str(tmp_path))
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", "earner")
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: 1)
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: None)
    assert guard.main(["/bin/true"]) == 75
    receipt = json.loads(capsys.readouterr().out.strip())
    assert receipt["required_bytes"] == guard.REVENUE_FLOOR_BYTES


def test_producer_floor_can_be_calibrated_for_isolated_hosts(monkeypatch):
    guard = load_guard()
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", "line-sticker-factory-hourly")
    monkeypatch.setenv("LIFE_MANAGER_PRODUCER_FLOOR_BYTES", "0")
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: 1)
    calls = []
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: calls.append(args))
    assert guard.main(["/bin/true"]) == 0
