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
printf '%s %s holder=%s\\n' "$1" "$2" "${{AI_BROWSER_HOLDER_PID:-none}}" >>"{tmp_path}/events"
''')
    guard.chmod(0o755)
    provisioner = browser / "ensure_provision_browser.sh"
    provisioner.write_text(f'''#!/usr/bin/env bash
printf 'provision %s holder=%s guard=%s\\n' "$1" "${{AI_BROWSER_HOLDER_PID:-none}}" "${{AI_BROWSER_GUARD##*/}}" >>"{tmp_path}/events"
[ "{acquire_rc}" = 0 ] || exit {acquire_rc}
printf 'http://127.0.0.1:41234\\n'
''')
    provisioner.chmod(0o755)
    python = tmp_path / "fake-browser-python"
    python.write_text(f'''#!/usr/bin/env bash
printf 'measure %s\\n' "${{WRITER_CDP_ENDPOINT:-missing}}" >>"{tmp_path}/events"
exit {measure_rc}
''')
    python.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "sleep").write_text(f"#!/bin/sh\nprintf 'wait\\n' >> '{tmp_path}/events'\n")
    (fake_bin / "sleep").chmod(0o755)
    (scripts / "writer-runtime-env.sh").write_text(f'''STATE_DIR="{tmp_path}/state"
LIFE_MANAGER_REPO="{tmp_path}"
WRITER_BROWSER_PYTHON="{python}"
export PATH="{tmp_path}/bin:$PATH"
''')
    (scripts / "money_sync.py").write_text(f'from pathlib import Path\np=Path({str(tmp_path / "events")!r})\np.write_text(p.read_text()+"sync\\n")\n')
    shutil.copy(WORKER, scripts / WORKER.name)
    return scripts / WORKER.name


def events(tmp_path, worker_pid):
    return (tmp_path / "events").read_text().replace(f"holder={worker_pid}", "holder=WORKER").splitlines()


def run(worker):
    process = subprocess.Popen(["bash", str(worker)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate(timeout=10)
    return process.pid, process.returncode, stderr


def test_worker_never_leases_dais_personal_chrome():
    source = WORKER.read_text()
    assert "interactive:dais" not in source
    assert 'BROWSER_IDENTITY="writer:anicca"' in source


def test_worker_holds_its_own_browser_lease_through_measurement(tmp_path):
    worker = fixture(tmp_path)
    pid, rc, stderr = run(worker)
    assert rc == 0, stderr
    assert events(tmp_path, pid) == [
        "provision writer:anicca holder=WORKER guard=browser-guard.sh",
        "measure http://127.0.0.1:41234", "sync", "release writer:anicca holder=WORKER",
    ]
    assert not (tmp_path / "state/.sales-measure.lock").exists()


def test_unavailable_browser_skips_without_waiting_or_releasing_a_foreign_lease(tmp_path):
    worker = fixture(tmp_path, acquire_rc=1)
    pid, rc, _stderr = run(worker)
    assert rc == 75
    assert events(tmp_path, pid) == ["provision writer:anicca holder=WORKER guard=browser-guard.sh"]
    assert not (tmp_path / "state/.sales-measure.lock").exists()


def test_failed_measurement_releases_exact_browser_lease(tmp_path):
    worker = fixture(tmp_path, measure_rc=23)
    pid, rc, _stderr = run(worker)
    assert rc == 23
    assert events(tmp_path, pid) == [
        "provision writer:anicca holder=WORKER guard=browser-guard.sh",
        "measure http://127.0.0.1:41234", "release writer:anicca holder=WORKER",
    ]
    assert not (tmp_path / "state/.sales-measure.lock").exists()
