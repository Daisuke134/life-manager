"""Uniform secret-free runtime event envelope and durable JSONL append."""

from __future__ import annotations

import errno
import fcntl
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from runtime.host.storage_failure import validate_storage_failure


REQUIRED_FIELDS = {
    "version", "event_id", "timestamp", "loop_id", "domain", "run_id", "phase",
    "status", "release_sha", "provider", "profile_alias", "effect_class",
    "effect_status", "blocker", "evidence_refs",
}
DIAGNOSTIC_FIELDS = {
    "product_loop_id", "job_id", "owner_id", "wake_id", "occurrence_id",
    "loaded_argv_sha256", "loaded_env_sha256", "exit_code", "failure_layer",
    "error_class", "retryable", "next_action", "provider_receipt_id",
    "official_readback_ref",
}
# Present only when the effect-identity persistence step actually ran
# (see lm_loop_run._persist_effect_identity); absent otherwise.
# ``error_detail`` is present only for a failing run that captured entrypoint
# stderr (see lm_loop_run._run_entrypoint's bounded tail capture).
OPTIONAL_FIELDS = {"effect_identity_status", "error_detail", "storage_failure"}
FIELDS = REQUIRED_FIELDS | DIAGNOSTIC_FIELDS | OPTIONAL_FIELDS
MAX_ERROR_DETAIL_CHARS = 4096
EFFECT_IDENTITY_STATUSES = {"not_written", "rejected", "persisted"}
DOMAINS = {"physical", "mental", "financial", "earn", "growth", "system"}
PHASES = {"plan", "execute", "reconcile", "verify", "report"}
STATUSES = {"running", "pass", "fail", "blocked"}
EFFECTS = {"none", "publish", "message", "money", "application", "trade", "account_mutation"}
EFFECT_STATUSES = {"not_applicable", "unknown", "planned", "started", "verified", "failed", "reconciled"}
FAILURE_LAYERS = {"clean", "admission", "entrypoint", "effect_readback", "runtime", "unknown"}
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
SAFE_REF = re.compile(r"[a-z][a-z0-9+.-]*://[A-Za-z0-9._:/-]{1,512}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SECRET = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~+/-]+|(?:token|secret|password|credential|api.?key|auth\.json)\s*[=:]|(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}|/" r"Users/)"
)
DEFAULT_MAX_BYTES = 16 * 1024 * 1024
HEALTH_CATCHUP_BYTES = 256 * 1024
HEALTH_PROJECTION_MAX_BYTES = 4 * 1024 * 1024
HEALTH_CLOCKS = ("last_attempt", "last_success", "last_effect", "last_receipt", "last_verified_effect")


def _health_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _health_cursor(fd: int, offset: int) -> dict:
    info = os.fstat(fd)
    return {
        "device": info.st_dev, "inode": info.st_ino, "offset": offset,
        "modified_ns": info.st_mtime_ns,
        "head": hashlib.sha256(os.pread(fd, min(offset, 128), 0)).hexdigest(),
        "tail": hashlib.sha256(os.pread(fd, min(offset, 128), max(0, offset - 128))).hexdigest(),
    }


def _empty_health_projection() -> dict:
    return {"version": 1, "reports": {}, "running": {}, "clocks": {}, "complete": True}


def _update_health_projection(value: dict, event: dict) -> None:
    if event["phase"] not in {"execute", "report"}:
        return
    loop_id, timestamp = event["loop_id"], event["timestamp"]
    clocks = value["clocks"].setdefault(loop_id, dict.fromkeys(HEALTH_CLOCKS))
    clocks["last_attempt"] = timestamp
    if event["phase"] == "report":
        value["reports"][loop_id] = event
        value["running"].pop(loop_id, None)
        if event["status"] == "pass":
            clocks["last_success"] = timestamp
    elif event["status"] == "running" and event.get("job_id") is not None:
        pid = event["run_id"].rsplit("-", 1)[-1]
        # A job has one admitted execution; restarted PIDs must not accumulate forever.
        value["running"][loop_id] = {pid: event}
    if event["effect_class"] != "none":
        if event["effect_status"] in {"started", "verified", "failed", "reconciled"}:
            clocks["last_effect"] = timestamp
        if event["phase"] == "report" and event["effect_status"] in {"verified", "reconciled"}:
            clocks["last_verified_effect"] = timestamp
    if event.get("provider_receipt_id") or event.get("official_readback_ref"):
        clocks["last_receipt"] = timestamp


def _project_health_lines(value: dict, lines: list[bytes]) -> None:
    for line in lines:
        if b'"phase"' not in line or (b'"report"' not in line and b'"execute"' not in line):
            continue
        try:
            event = validate_runtime_event(json.loads(line))
        except (ValueError, TypeError, UnicodeError):
            continue
        _update_health_projection(value, event)


def _load_health_projection(path: Path) -> dict | None:
    try:
        fd = os.open(path.with_suffix(".health.json"), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > HEALTH_PROJECTION_MAX_BYTES:
            raise ValueError("invalid health projection file")
        raw = os.read(fd, HEALTH_PROJECTION_MAX_BYTES + 1)
    finally:
        os.close(fd)
    value = json.loads(raw)
    digest = value.pop("digest")
    if (len(raw) > HEALTH_PROJECTION_MAX_BYTES or value.get("version") != 1
            or digest != hashlib.sha256(_health_bytes(value)).hexdigest()
            or type(value.get("complete")) is not bool):
        raise ValueError("invalid health projection")
    cursor = value["journal"]
    pending = value.get("backfill_next")
    if pending is not None and (not isinstance(pending, str) or Path(pending).name != pending
                                or not pending.startswith(f"{path.stem}-")
                                or not pending.endswith(f"{path.suffix}.gz")):
        raise ValueError("invalid health backfill cursor")
    if (any(type(cursor[key]) is not int or cursor[key] < 0
            for key in ("device", "inode", "offset", "modified_ns"))
            or any(not SHA256.fullmatch(cursor[key]) for key in ("head", "tail"))):
        raise ValueError("invalid health cursor")
    for loop_id, clocks in value["clocks"].items():
        if not SAFE_ID.fullmatch(loop_id) or set(clocks) != set(HEALTH_CLOCKS):
            raise ValueError("invalid health clocks")
        for timestamp in clocks.values():
            if timestamp is not None and datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("naive health clock")
    for loop_id, event in value["reports"].items():
        validate_runtime_event(event)
        if event["loop_id"] != loop_id or event["phase"] != "report" or loop_id not in value["clocks"]:
            raise ValueError("invalid projected report")
    for loop_id, events in value["running"].items():
        for pid, event in events.items():
            validate_runtime_event(event)
            if (event["loop_id"] != loop_id or event["phase"] != "execute"
                    or event["status"] != "running" or event.get("job_id") is None
                    or event["run_id"].rsplit("-", 1)[-1] != pid or loop_id not in value["clocks"]):
                raise ValueError("invalid projected running event")
    return value


def _backfill_health_archives(value: dict, path: Path, budget: int) -> bool:
    archives = sorted(path.parent.glob(f"{path.stem}-*{path.suffix}.gz"), reverse=True)
    if value.get("backfill_next"):
        archives = [archive for archive in archives if archive.name <= value["backfill_next"]]
    older, complete = [], True
    for archive in archives[:4]:
        try:
            with gzip.open(archive, "rb") as stream:
                archived = stream.read(budget + 1)
            if len(archived) > budget:
                break
            budget -= len(archived)
            if archived and not archived.endswith(b"\n"):
                complete = False
                archived = archived[:archived.rfind(b"\n") + 1]
            older.append(archived)
        except (OSError, EOFError, zlib.error):
            break
    if len(older) < len(archives):
        value["backfill_next"] = archives[len(older)].name
        complete = False
    else:
        value.pop("backfill_next", None)
    historical = _empty_health_projection()
    for archived in reversed(older):
        _project_health_lines(historical, archived.splitlines())
    current_loops = set(value["reports"]) | set(value["running"])
    for loop_id, clocks in historical["clocks"].items():
        current = value["clocks"].setdefault(loop_id, dict.fromkeys(HEALTH_CLOCKS))
        for name, timestamp in clocks.items():
            if current[name] is None:
                current[name] = timestamp
    for loop_id, event in historical["reports"].items():
        value["reports"].setdefault(loop_id, event)
    for loop_id, events in historical["running"].items():
        if loop_id not in current_loops:
            value["running"][loop_id] = events
    return complete


def _health_projection_locked(fd: int, path: Path, *, budget: int, backfill: bool = False) -> dict:
    size, corrupt = os.fstat(fd).st_size, False
    try:
        value = _load_health_projection(path)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        value, corrupt = None, True
    matched = False
    if value is not None and value["journal"]["offset"] <= size:
        cursor = _health_cursor(fd, value["journal"]["offset"])
        if value["journal"]["offset"] < size:
            cursor["modified_ns"] = value["journal"]["modified_ns"]
        matched = value["journal"] == cursor
    offset = value["journal"]["offset"] if matched else 0
    gap = corrupt or (value is not None and not matched) or size - offset > budget
    if not matched or gap:
        value = _empty_health_projection()
        offset = max(0, size - budget)
    data = os.pread(fd, min(budget, size - offset), offset)
    if offset and (not matched or gap):
        data = data.partition(b"\n")[2]
    end = size if not data or data.endswith(b"\n") else size - len(data.rsplit(b"\n", 1)[-1])
    if not matched and offset == 0:
        # Bootstrap is bounded; normal reads use only the cursor delta and never open archives.
        gap = not _backfill_health_archives(value, path, budget - len(data)) or gap
    _project_health_lines(value, data[:len(data) - (size - end)].splitlines())
    if matched and backfill and value.get("backfill_next"):
        gap = not _backfill_health_archives(value, path, budget - len(data)) or gap
    value["complete"] = value["complete"] and not gap
    value["journal"] = _health_cursor(fd, end)
    value["history_status"] = ("health_history_incomplete" if end != size else
                               "health_history_gap" if not value["complete"] else None)
    return value


def read_runtime_health_projection(path: Path) -> dict:
    """Read a verified cursor or a bounded journal delta; never modify runtime state."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return {**_empty_health_projection(), "history_status": "health_history_gap"}
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return {**_empty_health_projection(), "history_status": "health_history_gap"}
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return {**_empty_health_projection(), "history_status": "health_history_busy"}
        return _health_projection_locked(fd, path, budget=HEALTH_CATCHUP_BYTES)
    finally:
        os.close(fd)


def _write_health_projection(fd: int, path: Path, value: dict) -> None:
    value.pop("history_status", None)
    value["journal"] = _health_cursor(fd, os.fstat(fd).st_size)
    value["digest"] = hashlib.sha256(_health_bytes(value)).hexdigest()
    target = path.with_suffix(".health.json")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_health_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def redact_secrets(text: str) -> str:
    """Replace anything matching the event-wide SECRET pattern with a marker.

    Reused so any free-text diagnostic field (e.g. an entrypoint's stderr
    tail) is pre-cleaned before it ever reaches ``validate_runtime_event``,
    which otherwise rejects the whole event outright on a SECRET match --
    losing the diagnostic instead of just the secret-looking substring.
    """
    return SECRET.sub("[redacted]", text)


def _max_bytes() -> int:
    try:
        value = int(os.environ.get("LM_RUNTIME_EVENTS_MAX_BYTES", DEFAULT_MAX_BYTES))
    except ValueError:
        return DEFAULT_MAX_BYTES
    return value if value > 0 else DEFAULT_MAX_BYTES


def _next_archive(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = path.with_name(f"{path.stem}-{stamp}{path.suffix}.gz")
    suffix = 0
    while candidate.exists():
        suffix += 1
        candidate = path.with_name(f"{path.stem}-{stamp}.{suffix}{path.suffix}.gz")
    return candidate


def rotate_jsonl_locked(
    fd: int,
    path: Path,
    max_bytes: int | None = None,
    keep_archives: int | None = None,
    keep_tail_bytes: int = 0,
) -> None:
    """Archive an oversized locked JSONL to .gz; optionally carry its last whole lines
    (at most ``keep_tail_bytes``) into the fresh file for bounded-tail readers."""
    if keep_archives is not None and keep_archives < 0:
        raise ValueError("keep_archives must be non-negative")
    if os.fstat(fd).st_size <= (max_bytes or _max_bytes()):
        return
    archive = _next_archive(path)
    temporary = archive.with_name(f".{archive.name}.tmp.{os.getpid()}")
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        with os.fdopen(os.dup(fd), "rb") as source, temporary.open("xb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as target:
                shutil.copyfileobj(source, target)
            raw.flush()
            os.fsync(raw.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, archive)
        tail = b""
        if keep_tail_bytes > 0:
            size = os.fstat(fd).st_size
            os.lseek(fd, max(0, size - keep_tail_bytes), os.SEEK_SET)
            tail = os.read(fd, keep_tail_bytes)
            if size > keep_tail_bytes:
                tail = tail.partition(b"\n")[2]  # drop the partial first line
            tail = tail[:tail.rfind(b"\n") + 1]  # drop an unterminated last line
        os.ftruncate(fd, 0)
        if tail:
            os.lseek(fd, 0, os.SEEK_SET)  # non-O_APPEND fds would otherwise leave a hole
            _write_complete(fd, tail)
        os.fsync(fd)
        if keep_archives is not None:
            archives = sorted(path.parent.glob(f"{path.stem}-*{path.suffix}.gz"))
            expired_archives = archives[:-keep_archives] if keep_archives else archives
            for expired in expired_archives:
                expired.unlink()
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def validate_runtime_event(event: dict) -> dict:
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    missing, unknown = REQUIRED_FIELDS - set(event), set(event) - FIELDS
    if missing:
        raise ValueError(f"missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"unknown fields: {sorted(unknown)}")
    if SECRET.search(json.dumps(event, ensure_ascii=False, sort_keys=True)):
        raise ValueError("secret-like event value forbidden")
    if event["version"] != 1 or not re.fullmatch(r"[0-9a-f]{24,64}", event["event_id"]):
        raise ValueError("invalid version or event_id")
    try:
        datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("invalid timestamp") from exc
    for key in ("loop_id", "run_id", "provider"):
        if not isinstance(event[key], str) or not SAFE_ID.fullmatch(event[key]):
            raise ValueError(f"invalid {key}")
    alias = event["profile_alias"]
    if alias is not None and (not isinstance(alias, str) or not SAFE_ID.fullmatch(alias)):
        raise ValueError("invalid profile_alias")
    if event["domain"] not in DOMAINS or event["phase"] not in PHASES:
        raise ValueError("invalid domain or phase")
    if event["status"] not in STATUSES or event["effect_class"] not in EFFECTS:
        raise ValueError("invalid status or effect_class")
    if event["effect_status"] not in EFFECT_STATUSES:
        raise ValueError("invalid effect_status")
    blocker = event["blocker"]
    if blocker is not None and (not isinstance(blocker, str) or not SAFE_ID.fullmatch(blocker)):
        raise ValueError("invalid blocker")
    refs = event["evidence_refs"]
    if not isinstance(refs, list) or len(refs) > 32 or any(
        not isinstance(ref, str) or not SAFE_REF.fullmatch(ref) for ref in refs
    ):
        raise ValueError("invalid evidence_refs")
    diagnostic = set(event) & DIAGNOSTIC_FIELDS
    if diagnostic and diagnostic != DIAGNOSTIC_FIELDS:
        raise ValueError(f"missing diagnostic fields: {sorted(DIAGNOSTIC_FIELDS - diagnostic)}")
    if diagnostic:
        product_loop_id = event["product_loop_id"]
        if product_loop_id is not None and (
                not isinstance(product_loop_id, str) or not SAFE_ID.fullmatch(product_loop_id)):
            raise ValueError("invalid product_loop_id")
        for key in ("job_id", "owner_id", "wake_id", "occurrence_id", "next_action"):
            if not isinstance(event[key], str) or not SAFE_ID.fullmatch(event[key]):
                raise ValueError(f"invalid {key}")
        if not event["occurrence_id"].startswith(f'{event["job_id"]}:'):
            raise ValueError("invalid occurrence_id")
        for key in ("loaded_argv_sha256", "loaded_env_sha256"):
            value = event[key]
            if value is not None and (not isinstance(value, str) or not SHA256.fullmatch(value)):
                raise ValueError(f"invalid {key}")
        exit_code = event["exit_code"]
        if exit_code is not None and (
                isinstance(exit_code, bool) or not isinstance(exit_code, int)
                or exit_code < -255 or exit_code > 255):
            raise ValueError("invalid exit_code")
        if event["failure_layer"] not in FAILURE_LAYERS:
            raise ValueError("invalid failure_layer")
        for key in ("error_class", "provider_receipt_id"):
            value = event[key]
            if value is not None and (not isinstance(value, str) or not SAFE_ID.fullmatch(value)):
                raise ValueError(f"invalid {key}")
        if type(event["retryable"]) is not bool:
            raise ValueError("invalid retryable")
        readback = event["official_readback_ref"]
        if readback is not None and (
                not isinstance(readback, str) or not SAFE_REF.fullmatch(readback)):
            raise ValueError("invalid official_readback_ref")
    if "effect_identity_status" in event and event["effect_identity_status"] not in EFFECT_IDENTITY_STATUSES:
        raise ValueError("invalid effect_identity_status")
    if "error_detail" in event:
        detail = event["error_detail"]
        if not isinstance(detail, str) or not detail or len(detail) > MAX_ERROR_DETAIL_CHARS:
            raise ValueError("invalid error_detail")
    if "storage_failure" in event:
        failure = validate_storage_failure(event["storage_failure"])
        expected = f'lm-storage://{event.get("owner_id", event["loop_id"])}/{event["run_id"]}/{failure["operation"]}'
        if failure["proof_ref"] != expected:
            raise ValueError("foreign storage proof")
    return event


def build_runtime_event(*, loop_id: str, domain: str, run_id: str, release_sha: str,
                        provider: str, profile_alias: str | None, effect_class: str,
                        succeeded: bool, blocker: str | None,
                        deferred: bool = False,
                        evidence_scheme: str = "agent-runner",
                        claimed_occurrence_id: str | None = None,
                        effect_identity_ref: str | None = None,
                        product_loop_id: str | None = None,
                        job_id: str | None = None,
                        owner_id: str | None = None,
                        wake_id: str | None = None,
                        loaded_argv_sha256: str | None = None,
                        loaded_env_sha256: str | None = None,
                        exit_code: int | None = None,
                        failure_layer: str | None = None,
                        error_class: str | None = None,
                        retryable: bool | None = None,
                        next_action: str | None = None,
                        provider_receipt_id: str | None = None,
                        official_readback_ref: str | None = None,
                        effect_identity_status: str | None = None,
                        error_detail: str | None = None,
                        storage_failure: dict | None = None) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    if succeeded and deferred:
        raise ValueError("runtime event cannot be both succeeded and deferred")
    status = "blocked" if deferred else ("pass" if succeeded else "fail")
    material = f"{release_sha}:{loop_id}:{run_id}:report:{status}"
    if claimed_occurrence_id is not None:
        if (not isinstance(claimed_occurrence_id, str)
                or not SAFE_ID.fullmatch(claimed_occurrence_id)
                or not claimed_occurrence_id.startswith(f"{loop_id}:")):
            raise ValueError("invalid claimed occurrence")
        material += f":{claimed_occurrence_id}"
    effective_job_id = job_id or loop_id
    effective_owner_id = owner_id or loop_id
    effective_wake_id = wake_id or run_id
    effective_occurrence_id = claimed_occurrence_id or f"{effective_job_id}:{run_id}"
    effective_failure_layer = failure_layer or (
        "clean" if succeeded else ("admission" if deferred else "entrypoint")
    )
    effective_error_class = error_class if error_class is not None else blocker
    effective_retryable = retryable if retryable is not None else (
        deferred or (not succeeded and effect_class == "none")
    )
    effective_next_action = next_action or (
        "none" if succeeded else (
            "retry_after_eligibility" if deferred else (
                "reconcile_owner" if effect_class == "none" else "official_readback_required"
            )
        )
    )
    event = {
        "version": 1,
        "event_id": hashlib.sha256(material.encode()).hexdigest()[:24],
        "timestamp": timestamp,
        "loop_id": loop_id,
        "domain": domain,
        "run_id": run_id,
        "phase": "report",
        "status": status,
        "release_sha": release_sha,
        "provider": provider,
        "profile_alias": profile_alias,
        "effect_class": effect_class,
        "effect_status": (
            "not_applicable"
            if effect_class == "none" or blocker in {
                "host_admission_deferred:resource_capacity_busy",
                "host_admission_deferred:resource_fifo_wait",
                "host_admission_deferred:resource_admission_unavailable",
                "host_admission_deferred:resource_claim_identity_invalid",
                "host_admission_deferred:memory_headroom_unavailable",
                "host_admission_deferred:memory_headroom_low",
                "host_admission_deferred:disk_headroom_unavailable",
                "host_admission_deferred:disk_headroom_low",
            }
            else "unknown"
        ),
        "blocker": blocker,
        "evidence_refs": [f"{evidence_scheme}://{loop_id}/{run_id}/summary.json"],
        "product_loop_id": product_loop_id,
        "job_id": effective_job_id,
        "owner_id": effective_owner_id,
        "wake_id": effective_wake_id,
        "occurrence_id": effective_occurrence_id,
        "loaded_argv_sha256": loaded_argv_sha256,
        "loaded_env_sha256": loaded_env_sha256,
        "exit_code": 0 if succeeded and exit_code is None else exit_code,
        "failure_layer": effective_failure_layer,
        "error_class": effective_error_class,
        "retryable": effective_retryable,
        "next_action": effective_next_action,
        "provider_receipt_id": provider_receipt_id,
        "official_readback_ref": official_readback_ref,
    }
    if claimed_occurrence_id is not None and claimed_occurrence_id != f"{loop_id}:{run_id}":
        suffix = claimed_occurrence_id[len(loop_id) + 1:]
        event["evidence_refs"].append(f"lm-occurrence://{loop_id}/{suffix}/claim")
    if effect_identity_ref is not None:
        if not isinstance(effect_identity_ref, str) or not SAFE_REF.fullmatch(effect_identity_ref):
            raise ValueError("invalid effect identity reference")
        event["evidence_refs"].append(effect_identity_ref)
    if effect_identity_status is not None:
        event["effect_identity_status"] = effect_identity_status
    if error_detail is not None:
        redacted = redact_secrets(error_detail).strip()[:MAX_ERROR_DETAIL_CHARS]
        if redacted:
            event["error_detail"] = redacted
    if storage_failure is not None:
        event["storage_failure"] = storage_failure
    return validate_runtime_event(event)


def build_runtime_start_event(*, loop_id: str, domain: str, run_id: str,
                              release_sha: str, provider: str,
                              profile_alias: str | None, effect_class: str,
                              product_loop_id: str | None = None,
                              job_id: str | None = None,
                              owner_id: str | None = None,
                              wake_id: str | None = None,
                              occurrence_id: str | None = None,
                              loaded_argv_sha256: str | None = None,
                              loaded_env_sha256: str | None = None) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    material = f"{release_sha}:{loop_id}:{run_id}:execute:running"
    effective_job_id = job_id or loop_id
    effective_owner_id = owner_id or loop_id
    effective_wake_id = wake_id or run_id
    effective_occurrence_id = occurrence_id or f"{effective_job_id}:{run_id}"
    return validate_runtime_event({
        "version": 1,
        "event_id": hashlib.sha256(material.encode()).hexdigest()[:24],
        "timestamp": timestamp,
        "loop_id": loop_id,
        "domain": domain,
        "run_id": run_id,
        "phase": "execute",
        "status": "running",
        "release_sha": release_sha,
        "provider": provider,
        "profile_alias": profile_alias,
        "effect_class": effect_class,
        "effect_status": "not_applicable" if effect_class == "none" else "started",
        "blocker": None,
        "evidence_refs": [f"lm-loop://{loop_id}/{run_id}/summary.json"],
        "product_loop_id": product_loop_id,
        "job_id": effective_job_id,
        "owner_id": effective_owner_id,
        "wake_id": effective_wake_id,
        "occurrence_id": effective_occurrence_id,
        "loaded_argv_sha256": loaded_argv_sha256,
        "loaded_env_sha256": loaded_env_sha256,
        "exit_code": None,
        "failure_layer": "clean",
        "error_class": None,
        "retryable": False,
        "next_action": "monitor_running",
        "provider_receipt_id": None,
        "official_readback_ref": None,
    })


def build_install_event(*, loop_id: str, domain: str, release_sha: str,
                        provider: str, effect_class: str) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    material = f"{release_sha}:{loop_id}:install:plan:pass"
    return validate_runtime_event({
        "version": 1,
        "event_id": hashlib.sha256(material.encode()).hexdigest()[:24],
        "timestamp": timestamp,
        "loop_id": loop_id,
        "domain": domain,
        "run_id": "install",
        "phase": "plan",
        "status": "pass",
        "release_sha": release_sha,
        "provider": provider,
        "profile_alias": None,
        "effect_class": effect_class,
        "effect_status": "not_applicable" if effect_class == "none" else "unknown",
        "blocker": None,
        "evidence_refs": [f"lm-loop://{loop_id}/install/summary.json"],
    })


def _contains_event_id(fd: int, event_id: str) -> bool:
    """Parse only rows that can contain the requested event ID."""
    needle = event_id.encode()
    os.lseek(fd, 0, os.SEEK_SET)
    with os.fdopen(os.dup(fd), "rb") as reader:
        for line in reader:
            if needle not in line and b"\\u" not in line:
                continue
            try:
                existing = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(existing, dict) and existing.get("event_id") == event_id:
                return True
    return False


def _write_complete(fd: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise OSError(errno.EIO, "runtime journal write made no progress")
        remaining = remaining[written:]


def append_runtime_event(path: Path, event: dict) -> None:
    validate_runtime_event(event)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = (json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        if _contains_event_id(fd, event["event_id"]):
            os.fsync(fd)
            return
        projection = _health_projection_locked(fd, path, budget=2 * DEFAULT_MAX_BYTES, backfill=True)
        rotate_jsonl_locked(fd, path)
        size = os.fstat(fd).st_size
        try:
            if size:
                os.lseek(fd, -1, os.SEEK_END)
                if os.read(fd, 1) != b"\n":
                    _write_complete(fd, b"\n")
            _write_complete(fd, data)
        except OSError:
            # The existing writer lock excludes siblings; only this incomplete append is undone.
            os.ftruncate(fd, size)
            os.fsync(fd)
            raise
        # A complete record remains available if durability confirmation fails.
        os.fsync(fd)
        _update_health_projection(projection, event)
        try:
            _write_health_projection(fd, path, projection)
        except OSError:
            # The journal is authoritative; a missed cache update is bounded reader catch-up.
            pass
    finally:
        os.close(fd)
