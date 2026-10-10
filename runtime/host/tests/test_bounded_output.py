import base64
import os
from pathlib import Path
import subprocess
import sys
import time
import errno
import socket
import threading

import pytest
from runtime.host.storage_policy import load_storage_policy
from runtime.host.bounded_output import start_stderr_relay, read_relay_snapshot
from runtime.host import bounded_output

ROOT = Path(__file__).resolve().parents[3]


def start(root):
    policy = load_storage_policy(ROOT / "config/storage-policy.json", "life-manager-disk-cleanup")
    binding = {"owner_id": policy.owner_id, "run_id": "run-1",
        "occurrence_id": "life-manager-disk-cleanup:run-1", "release_sha": "a" * 40}
    return start_stderr_relay(root, policy, binding)


def finish(handle):
    os.close(handle.stdin_write_fd)
    handle.process.wait(timeout=10)
    receipt = read_relay_snapshot(handle)
    handle.control_socket.close()
    return receipt


def test_binary_log_burst_is_bounded_and_keeps_head_tail(tmp_path):
    handle = start(tmp_path)
    chunk = bytes(range(256)) * 16
    for _ in range(8192):
        os.write(handle.stdin_write_fd, chunk)
    receipt = finish(handle)
    assert receipt["eof"] is True
    assert receipt["written_bytes"] == 32 * 1024**2
    assert base64.b64decode(receipt["tail_b64"]) == chunk[-2048:]
    retained = sum(p.stat().st_size for p in tmp_path.iterdir() if p.is_file())
    assert retained <= 2 * 1024**2 + 40 * 1024
    assert (tmp_path / "head.bin").read_bytes() == chunk * 8


def test_relay_drains_when_parent_control_channel_closes(tmp_path):
    handle = start(tmp_path)
    handle.control_socket.close()
    for _ in range(1024):
        os.write(handle.stdin_write_fd, b"x" * 4096)
    os.close(handle.stdin_write_fd)
    assert handle.process.wait(timeout=10) == 0


def test_detached_writer_survives_original_parent_exit(tmp_path):
    helper = tmp_path / "owner.py"
    helper.write_text(
        "import os,sys,time\n"
        f"sys.path.insert(0,{str(ROOT)!r})\n"
        "from runtime.host.bounded_output import start_stderr_relay\n"
        "from runtime.host.storage_policy import load_storage_policy\n"
        f"p=load_storage_policy({str(ROOT / 'config/storage-policy.json')!r},'life-manager-disk-cleanup')\n"
        "h=start_stderr_relay(sys.argv[1],p,{'owner_id':p.owner_id,'run_id':'run-1','occurrence_id':'life-manager-disk-cleanup:run-1','release_sha':'a'*40})\n"
        "pid=os.fork()\n"
        "if pid==0:\n"
        " os.setsid();time.sleep(0.3);os.write(h.stdin_write_fd,b'late-child');os.close(h.stdin_write_fd);open(sys.argv[2],'w').write('alive');os._exit(0)\n"
        "os.close(h.stdin_write_fd);h.control_socket.close();os._exit(0)\n")
    root = tmp_path / "relay"
    marker = tmp_path / "alive"
    subprocess.run([sys.executable, "-B", str(helper), str(root), str(marker)], check=True, timeout=5)
    deadline = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker.read_text() == "alive"


def test_relay_rejects_symlink_root(tmp_path):
    root = tmp_path / "foreign"
    root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        start(root)


def test_launchd_relay_startup_failure_is_finite_and_precedes_producer(tmp_path):
    logs = tmp_path / "logs"
    root = logs / "bounded"
    root.mkdir(mode=0o700, parents=True)
    (root / ".launchd-life-manager-disk-cleanup.lock").mkdir()
    marker = tmp_path / "producer-started"
    helper = (
        "import os,sys\nfrom pathlib import Path\n"
        "from runtime.host.bounded_output import bounded_launchd_output\n"
        "from runtime.host.storage_policy import load_storage_policy\n"
        f"policy=load_storage_policy({str(ROOT / 'config/storage-policy.json')!r},'life-manager-disk-cleanup')\n"
        "try:\n"
        f" with bounded_launchd_output({str(logs)!r},policy):\n"
        f"  Path({str(marker)!r}).touch()\n"
        "  os.write(1,b'x'*(8*1024*1024))\n"
        "except (OSError,ValueError): raise SystemExit(78)\n"
    )
    try:
        result = subprocess.run([sys.executable, "-B", "-c", helper],
            cwd=ROOT, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        pytest.fail("failed relay left a parent reader holding the producer pipe open")
    assert result.returncode == 78
    assert not marker.exists()


def test_sink_enospc_does_not_close_writer_pipe(tmp_path, monkeypatch):
    policy = load_storage_policy(ROOT / "config/storage-policy.json", "life-manager-disk-cleanup")
    binding = {"owner_id": policy.owner_id, "run_id": "run-1",
        "occurrence_id": "life-manager-disk-cleanup:run-1", "release_sha": "a" * 40}
    reader, writer = os.pipe()
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    result = []
    def failure(*_args):
        raise OSError(errno.ENOSPC, "fixture storage full")
    monkeypatch.setattr(bounded_output._PrivateRotatingHandler, "emit", failure)
    thread = threading.Thread(target=lambda: result.append(bounded_output.relay_stderr(
        reader, child.detach(), tmp_path, vars(policy), binding)))
    thread.start()
    try:
        for _ in range(1024):
            os.write(writer, b"x" * 4096)
    finally:
        os.close(writer)
    thread.join(10); parent.close()
    assert not thread.is_alive()
    assert result[0]["eof"] is True
    assert result[0]["storage_error"] == errno.ENOSPC
    assert result[0]["dropped_bytes"] == 4 * 1024**2
