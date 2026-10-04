from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "skills/writer-agent/scripts/writer-sales-measure-worker.sh"


def fixture(tmp_path, acquire_rc=0, measure_rc=0):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "runtime/host").mkdir(parents=True)
    (tmp_path / "runtime/host/owned_directory_lock.py").symlink_to(ROOT / "runtime/host/owned_directory_lock.py")
    browser = tmp_path / "skills/browser"
    browser.mkdir(parents=True)
    guard = browser / "browser-guard.sh"
    guard.write_text(f'''#!/usr/bin/env bash
printf '%s %s\\n' "$1" "$2" >>"{tmp_path}/events"
if [ "$1" = acquire ]; then
  [ "{acquire_rc}" = 0 ] || exit {acquire_rc}
  printf 'http://[::1]:9222\\n'
fi
''')
    guard.chmod(0o755)
    python = tmp_path / "fake-browser-python"
    python.write_text(f'''#!/usr/bin/env bash
printf 'measure %s\\n' "${{WRITER_CDP_ENDPOINT:-missing}}" >>"{tmp_path}/events"
exit {measure_rc}
''')
    python.chmod(0o755)
    (scripts / "writer-runtime-env.sh").write_text(f'''STATE_DIR="{tmp_path}/state"
LIFE_MANAGER_REPO="{tmp_path}"
WRITER_BROWSER_PYTHON="{python}"
''')
    (scripts / "money_sync.py").write_text(f'from pathlib import Path\np=Path({str(tmp_path / "events")!r})\np.write_text(p.read_text()+"sync\\n")\n')
    shutil.copy(WORKER, scripts / WORKER.name)
    return scripts / WORKER.name


def test_worker_holds_registered_browser_lease_through_measurement(tmp_path):
    worker = fixture(tmp_path)
    result = subprocess.run(["bash", str(worker)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "events").read_text().splitlines() == [
        "acquire interactive:dais", "measure http://[::1]:9222", "sync", "release interactive:dais"
    ]
    assert not (tmp_path / "state/.sales-measure.lock").exists()


def test_busy_browser_skips_provider_and_releases_only_worker_lock(tmp_path):
    worker = fixture(tmp_path, acquire_rc=9)
    result = subprocess.run(["bash", str(worker)], capture_output=True, text=True)
    assert result.returncode == 75
    assert (tmp_path / "events").read_text().splitlines() == ["acquire interactive:dais"]
    assert not (tmp_path / "state/.sales-measure.lock").exists()


def test_failed_measurement_releases_exact_browser_lease(tmp_path):
    worker = fixture(tmp_path, measure_rc=23)
    result = subprocess.run(["bash", str(worker)], capture_output=True, text=True)
    assert result.returncode == 23
    assert (tmp_path / "events").read_text().splitlines() == [
        "acquire interactive:dais", "measure http://[::1]:9222", "release interactive:dais"
    ]
    assert not (tmp_path / "state/.sales-measure.lock").exists()
