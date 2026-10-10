"""Owned, finite stdio drain. A parent exiting must not break detached writers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import contextmanager
import base64
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import selectors
import stat
import subprocess
import sys
import time
import shutil


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


def start_stderr_relay(private_root, policy, binding, *, stream_kind=None):
    root = _private_root(private_root)
    if set(binding) != {"owner_id", "run_id", "occurrence_id", "release_sha"} or binding["owner_id"] != policy.owner_id:
        raise ValueError("foreign relay binding")
    context = root / "relay-context.json"
    if stream_kind not in {None, "codex", "json"}:
        raise ValueError("invalid structured stream kind")
    _private_json(context, {"policy": asdict(policy), "binding": binding, "stream_kind": stream_kind})
    _private_json(root / ".lm-regenerable", {"role": "diagnostic_only", "binding": binding})
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


def prune_closed_diagnostics(evidence_root, policy, *, current_run, closed_probe=None, state_root=None):
    """Only relay-owned diagnostics; parent results, usage and journals remain."""
    result = {"removed": 0, "reclaimed_bytes": 0, "errors": 0, "preserved_bytes": 0}
    root = Path(evidence_root)
    if any(p.is_symlink() for p in [root, *root.parents]):
        return result
    if root.name == "agent-runner-evidence":
        capture_pattern = "*/*/attempt-*.capture/*"
    elif (state_root and root == Path(state_root).expanduser() / "evidence"
            and Path(current_run).parent == root):
        capture_pattern = "*/attempt-*.capture/*"
    else:
        return result
    allowed = {"relay-context.json", ".stderr-relay.json", ".lm-regenerable", "relay-result.json",
               "stderr.log", "head.bin", "semantic-stdout.json"}
    candidates = []
    deadline = time.monotonic() + 5
    for relay in root.glob(capture_pattern):
        if time.monotonic() >= deadline: break
        run = relay.parent.parent
        if not (run / "summary.json").is_file(): continue
        seal = run / "evidence-seal.json"
        if seal.exists() or seal.is_symlink(): continue
        try:
            if any(p.is_symlink() for p in [relay, relay.parent, run, run.parent]): continue
            info = relay.stat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077: continue
            files = list(relay.iterdir())
            if any(p.is_symlink() or not p.is_file() or
                   (p.name not in allowed and not re_log_backup(p.name)) for p in files): continue
            marker = relay / ".lm-regenerable"
            fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                meta = os.fstat(stream.fileno())
                if meta.st_uid != os.getuid() or meta.st_mode & 0o077 or meta.st_size > 4096 or meta.st_nlink != 1: continue
                value = json.loads(stream.read(4097))
            if value.get("role") != "diagnostic_only" or value["binding"]["owner_id"] != policy.owner_id: continue
            receipt = json.loads((relay / "relay-result.json").read_bytes()[:4097])
            if receipt.get("binding") != value["binding"]: continue
            size = sum(p.stat().st_size for p in files)
            candidates.append((info.st_mtime, relay, size))
        except (OSError, ValueError, KeyError, TypeError):
            result["errors"] += 1
    total = sum(size for _, _, size in candidates)
    cap = min(policy.owner_diagnostic_retained_bytes, policy.host_diagnostic_retained_bytes)
    for _, relay, size in sorted(candidates):
        if total <= cap or time.monotonic() >= deadline: break
        try:
            if closed_probe is None:
                check = subprocess.run(["lsof", "-nP", "+D", str(relay)], capture_output=True,
                    timeout=min(1, max(.1, deadline-time.monotonic())))
                closed = check.returncode == 1 and not check.stdout and not check.stderr
            else: closed = closed_probe(relay) is True
            if not closed:
                result["preserved_bytes"] += size
                continue
            shutil.rmtree(relay)
            result["removed"] += 1; result["reclaimed_bytes"] += size; total -= size
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
            result["errors"] += 1
    return result


def re_log_backup(name):
    return name.startswith("stderr.log.") and name.removeprefix("stderr.log.").isdigit()


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


@contextmanager
def bounded_launchd_output(log_root, policy):
    """Route the runner and inherited child stdio to owner-specific bounded logs."""
    root = _private_root(Path(log_root) / "bounded")
    segment = min(policy.diagnostic_segment_bytes,
        max(1, policy.owner_diagnostic_retained_bytes // (2 * (policy.diagnostic_backup_count + 1))))
    pipes = [os.pipe(), os.pipe()]
    ready_reader, ready_writer = os.pipe()
    saved = [os.dup(1), os.dup(2)]
    owned = {fd for pipe in pipes for fd in pipe} | {ready_reader, ready_writer, *saved}
    process = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--launchd-relay",
             str(root), policy.owner_id, str(segment),
             str(policy.diagnostic_backup_count), str(min(policy.chunk_bytes, segment)),
             *(str(reader) for reader, _ in pipes), str(ready_writer)],
            pass_fds=tuple(reader for reader, _ in pipes) + (ready_writer,), start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for fd in [*(reader for reader, _ in pipes), ready_writer]:
            os.close(fd); owned.remove(fd)
        with selectors.DefaultSelector() as ready:
            ready.register(ready_reader, selectors.EVENT_READ)
            if not ready.select(5) or os.read(ready_reader, 1) != b"G":
                raise ValueError("launchd relay initialization failed")
        os.close(ready_reader); owned.remove(ready_reader)
        sys.stdout.flush(); sys.stderr.flush()
        for target, (_, writer) in zip((1, 2), pipes):
            os.dup2(writer, target)
        yield
    finally:
        sys.stdout.flush(); sys.stderr.flush()
        for target, original in zip((1, 2), saved):
            os.dup2(original, target)
        for fd in owned: os.close(fd)
        if process is not None:
            try: process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass  # A detached writer still owns the pipe; keep its drain alive.


def _relay_launchd_output(root, owner, segment, backups, chunk_size, readers, ready_fd):
    root = _private_root(root)
    lock = os.open(root / f".launchd-{owner}.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    info = os.fstat(lock)
    if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(lock); raise ValueError("unsafe launchd log lock")
    with selectors.DefaultSelector() as selector:
        handlers = []
        try:
            for reader, stream in zip(readers, ("out", "err")):
                handler = _PrivateRotatingHandler(root / f"launchd-{owner}.{stream}.log",
                    maxBytes=segment, backupCount=backups, encoding="latin-1")
                handler.setFormatter(logging.Formatter("%(message)s"))
                handler.close()
                handlers.append(handler); selector.register(reader, selectors.EVENT_READ, handler)
            os.write(ready_fd, b"G"); os.close(ready_fd)
            while selector.get_map():
                for key, _ in selector.select():
                    chunk = os.read(key.fd, chunk_size)
                    if not chunk:
                        selector.unregister(key.fd); os.close(key.fd); continue
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    try:
                        handler = key.data
                        handler.emit(logging.LogRecord("launchd", logging.INFO, "", 0,
                            chunk.decode("latin-1"), (), None))
                    except (OSError, ValueError):
                        pass  # Sink failure must not break the producer's pipe.
                    finally:
                        try: key.data.close()  # Reopen after a concurrent writer's rotation.
                        except OSError: pass
                        fcntl.flock(lock, fcntl.LOCK_UN)
        finally:
            for handler in handlers: handler.close()
            os.close(lock)


class _SemanticStream:
    """Retain contract events before dropping raw diagnostic bytes."""
    def __init__(self, kind, limit):
        self.kind = kind
        self.limit = limit
        self.buffer = bytearray()
        self.skipping = False
        self.oversized = False
        self.usage = None
        self.tool_started = False
        self.wrapper = None
        self.errors = []

    def feed(self, chunk):
        if self.kind == "json":
            if not self.skipping:
                self.buffer.extend(chunk)
                if len(self.buffer) > self.limit:
                    self.oversized = True
                    self.buffer.clear(); self.skipping = True
            return
        for part in chunk.splitlines(keepends=True):
            ended = part.endswith(b"\n")
            if not self.skipping:
                self.buffer.extend(part)
                if len(self.buffer) > self.limit:
                    self.oversized |= bytes(self.buffer[:32]).lstrip().startswith((b"{", b"["))
                    self.buffer.clear(); self.skipping = True
            if ended:
                if not self.skipping:
                    self.consume(bytes(self.buffer))
                self.buffer.clear(); self.skipping = False

    def consume(self, data):
        try: value = json.loads(data)
        except (ValueError, UnicodeError): return
        if not isinstance(value, dict): return
        if self.kind == "codex":
            if value.get("type") == "turn.completed": self.usage = value
            kind = value.get("type")
            error = None
            if kind in {"turn.failed", "error"}:
                error = value.get("error") if isinstance(value.get("error"), dict) else value
            elif kind == "response.failed" and isinstance(value.get("response"), dict):
                error = value["response"].get("error")
            elif kind in {"item.started", "item.updated", "item.completed"}:
                item = value.get("item")
                if isinstance(item, dict) and item.get("type") == "error": error = item
            if isinstance(error, dict):
                keys = {"code", "error_code", "errorCode", "codex_error_info", "error_type",
                        "type", "status", "status_code", "statusCode", "http_status", "message"}
                compact = {k: (v[:1024] if isinstance(v, str) else v) for k, v in error.items()
                           if k in keys and type(v) in {str, int}}
                self.errors = (self.errors + [{"type": "error", "error": compact}])[-8:]
            if value.get("type") in {"item.started", "item.completed"}:
                item = value.get("item")
                if isinstance(item, dict) and item.get("type") not in {"agent_message", "error"}:
                    self.tool_started = True
        else:
            self.wrapper = value

    def text(self):
        if self.buffer and not self.skipping: self.consume(bytes(self.buffer))
        if self.kind == "codex":
            records = []
            if self.tool_started: records.append({"type": "item.started", "item": {"type": "command_execution"}})
            if self.usage is not None: records.append(self.usage)
            records.extend(self.errors)
            return "\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records)
        return json.dumps(self.wrapper, ensure_ascii=False, separators=(",", ":")) if self.wrapper is not None else ""


def relay_stderr(read_fd, control_fd, private_root, policy, binding, stream_kind=None):
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
    semantic = _SemanticStream(stream_kind, policy["structured_record_max_bytes"]) if stream_kind else None

    def receipt(eof):
        return {"binding": binding, "pid": os.getpid(), "observed_at": time.time(),
            "written_bytes": written, "dropped_bytes": dropped,
            "tail_b64": base64.b64encode(tail).decode("ascii"),
            "storage_error": error, "eof": eof,
            "result_oversized": semantic.oversized if semantic else False}

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
            if semantic is not None: semantic.feed(chunk)
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
        if semantic is not None:
            try:
                fd = os.open(root / "semantic-stdout.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(semantic.text()); stream.flush(); os.fsync(stream.fileno())
            except OSError as exc:
                final["storage_error"] = exc.errno
        try: _private_json(root / "relay-result.json", final)
        except OSError: pass
        notify(final)
        return final
    finally:
        if head is not None: os.close(head)
        if handler is not None: handler.close()
        control.close(); os.close(read_fd)


if __name__ == "__main__":
    if len(sys.argv) == 10 and sys.argv[1] == "--launchd-relay":
        _relay_launchd_output(Path(sys.argv[2]), sys.argv[3],
            *(int(value) for value in sys.argv[4:7]), [int(value) for value in sys.argv[7:9]], int(sys.argv[9]))
        raise SystemExit(0)
    if len(sys.argv) != 5 or sys.argv[1] != "--relay":
        raise SystemExit(64)
    context_path = Path(sys.argv[2])
    with context_path.open() as stream:
        context = json.load(stream)
    relay_stderr(int(sys.argv[3]), int(sys.argv[4]), context_path.parent,
                 context["policy"], context["binding"], context.get("stream_kind"))
