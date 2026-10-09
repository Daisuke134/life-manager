"""Owned, finite stdio drain. A parent exiting must not break detached writers."""
from dataclasses import asdict, dataclass
import base64
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import time


@dataclass
class RelayHandle:
    process: subprocess.Popen
    stdin_write_fd: int
    control_socket: socket.socket
    private_root: Path
    binding: dict
    process_start: str
    last: dict | None = None

    @property
    def pid(self):
        return self.process.pid


def _private_root(root):
    root = Path(root)
    if not root.is_absolute() or any(p.is_symlink() for p in [root, *root.parents]):
        raise ValueError("unsafe relay root")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("relay root must be private")
    return root


def _private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, separators=(",", ":"))
        handle.flush(); os.fsync(handle.fileno())


def start_stderr_relay(private_root, policy, binding):
    root = _private_root(private_root)
    if set(binding) != {"owner_id", "run_id", "occurrence_id", "release_sha"} or binding["owner_id"] != policy.owner_id:
        raise ValueError("foreign relay binding")
    context = root / "relay-context.json"
    _private_json(context, {"policy": asdict(policy), "binding": binding})
    reader, writer = os.pipe()
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    parent.setblocking(False)
    child.setblocking(False)
    env = {k: os.environ[k] for k in ("PATH", "LANG", "TMPDIR") if k in os.environ}
    process = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--relay",
             str(context), str(reader), str(child.fileno())],
            pass_fds=(reader, child.fileno()), start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        start = " ".join(subprocess.check_output(["ps", "-p", str(process.pid), "-o", "lstart="], text=True).split())
        if not start:
            raise RuntimeError("relay process identity unavailable")
        _private_json(root / ".stderr-relay.json", {"pid": process.pid,
            "process_start": start, "binding": binding, "role": "diagnostic_only"})
        return RelayHandle(process, writer, parent, root, dict(binding), start)
    except BaseException:
        os.close(writer); parent.close()
        if process is not None:
            process.wait(timeout=5)  # No producer was started; closing input gives EOF.
        raise
    finally:
        os.close(reader); child.close()


def read_relay_snapshot(handle):
    while True:
        try:
            data = handle.control_socket.recv(4096)
        except OSError:
            break
        try:
            value = json.loads(data)
            if value.get("binding") == handle.binding:
                handle.last = value
        except (ValueError, AttributeError):
            continue
    if handle.process.poll() is not None:
        try:
            path = handle.private_root / "relay-result.json"
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                value = json.loads(stream.read(4097))
            if value.get("binding") == handle.binding:
                handle.last = value
        except (OSError, ValueError, AttributeError):
            pass
    return handle.last


class _PrivateRotatingHandler(RotatingFileHandler):
    terminator = ""

    def _open(self):
        fd = os.open(self.baseFilename,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(fd); raise ValueError("unsafe relay output")
        return os.fdopen(fd, "a", encoding="latin-1")

    def handleError(self, record):
        raise sys.exc_info()[1]


def relay_stderr(read_fd, control_fd, private_root, policy, binding):
    os.umask(0o077)
    root = _private_root(private_root)
    control = socket.socket(fileno=control_fd)
    control.setblocking(False)
    handler = head = None
    error = None
    try:
        handler = _PrivateRotatingHandler(root / "stderr.log", maxBytes=policy["diagnostic_segment_bytes"],
            backupCount=policy["diagnostic_backup_count"], encoding="latin-1")
        handler.setFormatter(logging.Formatter("%(message)s"))
        head = os.open(root / "head.bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except (OSError, ValueError) as exc:
        error = getattr(exc, "errno", None) or "capture_unavailable"
    tail = b""
    written = dropped = head_written = 0

    def receipt(eof):
        return {"binding": binding, "pid": os.getpid(), "observed_at": time.time(),
            "written_bytes": written, "dropped_bytes": dropped,
            "tail_b64": base64.b64encode(tail).decode("ascii"),
            "storage_error": error, "eof": eof}

    def notify(value):
        packet = json.dumps(value, separators=(",", ":")).encode()
        if len(packet) <= 4096:
            try: control.send(packet)
            except OSError: pass  # Loss of the parent must never close the input drain.

    try:
        while True:
            chunk = os.read(read_fd, policy["chunk_bytes"])
            if not chunk:
                break
            written += len(chunk)
            tail = (tail + chunk)[-2048:]
            if error is None:
                try:
                    if head_written < policy["head_bytes"]:
                        first = chunk[:policy["head_bytes"] - head_written]
                        head_written += os.write(head, first)
                    handler.emit(logging.LogRecord("relay", logging.INFO, "", 0,
                        chunk.decode("latin-1"), (), None))
                    handler.flush()
                except (OSError, ValueError) as exc:
                    error = getattr(exc, "errno", None) or "capture_unavailable"
                    dropped += len(chunk)
            else:
                dropped += len(chunk)
            notify(receipt(False))
        final = receipt(True)
        try: _private_json(root / "relay-result.json", final)
        except OSError: pass
        notify(final)
        return final
    finally:
        if head is not None: os.close(head)
        if handler is not None: handler.close()
        control.close(); os.close(read_fd)


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "--relay":
        raise SystemExit(64)
    context_path = Path(sys.argv[2])
    with context_path.open() as stream:
        context = json.load(stream)
    relay_stderr(int(sys.argv[3]), int(sys.argv[4]), context_path.parent,
                 context["policy"], context["binding"])
