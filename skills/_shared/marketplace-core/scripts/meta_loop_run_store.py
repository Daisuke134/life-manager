"""Private, append-only wake summaries for the marketplace Meta Loop."""

from __future__ import annotations

from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping


SCHEMA_VERSION = 1
_PAYLOAD_FIELDS = frozenset({
    "schema_version", "run_id", "observed_at", "status", "sources", "inspected",
    "persisted", "duplicates", "promoted", "held", "source_errors", "next_actions",
})
_EVENT_FIELDS = _PAYLOAD_FIELDS | {"idempotency_key"}
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_:-]{1,127}$")
_STATUS = frozenset({"ok", "empty", "partial"})
_MAX_LINE_BYTES = 64 * 1024


class MetaLoopRunStoreError(ValueError):
    """A wake summary is malformed, corrupt, or conflicts with an existing wake."""


def _text(value: Any, reason: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise MetaLoopRunStoreError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise MetaLoopRunStoreError(reason)
    return text


def _timestamp(value: Any) -> str:
    text = _text(value, "observed_at_invalid")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise MetaLoopRunStoreError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MetaLoopRunStoreError("observed_at_invalid")
    return text


def _counter(value: Any, reason: str) -> int:
    if type(value) is not int or value < 0:
        raise MetaLoopRunStoreError(reason)
    return value


def _source_errors(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 128:
        raise MetaLoopRunStoreError("source_errors_invalid")
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) not in ({
            "source", "error_class", "next_action",
        }, {
            "source", "error_class", "error_code", "next_action",
        }):
            raise MetaLoopRunStoreError("source_errors_invalid")
        normalized = {
            "source": _text(item.get("source"), "source_errors_invalid", max_length=128),
            "error_class": _text(item.get("error_class"), "source_errors_invalid", max_length=128),
            "next_action": _text(item.get("next_action"), "source_errors_invalid", max_length=256),
        }
        if "error_code" in item:
            error_code = _text(item.get("error_code"), "source_errors_invalid", max_length=128)
            if _ERROR_CODE.fullmatch(error_code) is None:
                raise MetaLoopRunStoreError("source_errors_invalid")
            normalized["error_code"] = error_code
        result.append(normalized)
    return result


def _next_actions(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 128:
        raise MetaLoopRunStoreError("next_actions_invalid")
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"provider", "candidate_id", "decision", "next_action"}:
            raise MetaLoopRunStoreError("next_actions_invalid")
        result.append({
            "provider": _text(item.get("provider"), "next_actions_invalid", max_length=32),
            "candidate_id": _text(item.get("candidate_id"), "next_actions_invalid", max_length=128),
            "decision": _text(item.get("decision"), "next_actions_invalid", max_length=16),
            "next_action": _text(item.get("next_action"), "next_actions_invalid", max_length=256),
        })
    return result


def _canonical_bytes(record: Mapping[str, Any]) -> bytes:
    encoded = (
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if len(encoded) > _MAX_LINE_BYTES:
        raise MetaLoopRunStoreError("run_summary_line_too_large")
    return encoded


def _normalize(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != _PAYLOAD_FIELDS:
        raise MetaLoopRunStoreError("run_summary_fields_invalid")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise MetaLoopRunStoreError("run_summary_schema_invalid")
    run_id = _text(raw.get("run_id"), "run_id_invalid", max_length=128)
    if _RUN_ID.fullmatch(run_id) is None:
        raise MetaLoopRunStoreError("run_id_invalid")
    observed_at = _timestamp(raw.get("observed_at"))
    status = _text(raw.get("status"), "status_invalid", max_length=16)
    if status not in _STATUS:
        raise MetaLoopRunStoreError("status_invalid")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "observed_at": observed_at,
        "status": status,
        "sources": _counter(raw.get("sources"), "sources_invalid"),
        "inspected": _counter(raw.get("inspected"), "inspected_invalid"),
        "persisted": _counter(raw.get("persisted"), "persisted_invalid"),
        "duplicates": _counter(raw.get("duplicates"), "duplicates_invalid"),
        "promoted": _counter(raw.get("promoted"), "promoted_invalid"),
        "held": _counter(raw.get("held"), "held_invalid"),
        "source_errors": _source_errors(raw.get("source_errors")),
        "next_actions": _next_actions(raw.get("next_actions")),
    }
    if status == "empty" and normalized["inspected"] != 0:
        raise MetaLoopRunStoreError("empty_status_with_candidates")
    if status == "ok" and normalized["inspected"] == 0:
        raise MetaLoopRunStoreError("ok_status_without_candidates")
    if normalized["promoted"] + normalized["held"] != normalized["inspected"]:
        raise MetaLoopRunStoreError("decision_count_mismatch")
    if normalized["persisted"] + normalized["duplicates"] > normalized["inspected"]:
        raise MetaLoopRunStoreError("persistence_count_mismatch")
    digest = hashlib.sha256(_canonical_bytes(normalized)).hexdigest()
    return {**normalized, "idempotency_key": f"meta-loop-run:v1:{run_id}:{digest}"}


def _reject_symlink(path: Path, reason: str) -> None:
    if path.is_symlink():
        raise MetaLoopRunStoreError(reason)


def _ensure_root(path: Path) -> None:
    _reject_symlink(path, "run_summary_root_invalid")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _reject_symlink(path, "run_summary_root_invalid")
    if not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise MetaLoopRunStoreError("run_summary_root_invalid")


def _open_private(path: Path, flags: int, mode: int = 0o600) -> int:
    _reject_symlink(path, "run_summary_file_invalid")
    try:
        descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)
    except OSError as error:
        raise MetaLoopRunStoreError("run_summary_file_invalid") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise MetaLoopRunStoreError("run_summary_file_invalid")
        os.fchmod(descriptor, 0o600)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


class MetaLoopRunStore:
    """Append-only, idempotent storage for bounded Meta Loop wake summaries."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser()
        self.events_path = self.root / "runs.jsonl"
        self.lock_path = self.root / ".lock"

    def _locked(self, *, exclusive: bool):
        _ensure_root(self.root)
        descriptor = _open_private(self.lock_path, os.O_RDWR | os.O_CREAT)
        handle = os.fdopen(descriptor, "r+b", buffering=0)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        return handle

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        descriptor = _open_private(self.events_path, os.O_RDONLY)
        try:
            payload = os.read(descriptor, _MAX_LINE_BYTES * 128)
            extra = os.read(descriptor, 1)
        finally:
            os.close(descriptor)
        if extra or (payload and not payload.endswith(b"\n")):
            raise MetaLoopRunStoreError("run_summary_corrupt")
        if not payload:
            return []
        rows: list[dict[str, Any]] = []
        for line in payload.splitlines():
            try:
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise MetaLoopRunStoreError("run_summary_corrupt") from error
            if not isinstance(value, Mapping) or set(value) != _EVENT_FIELDS:
                raise MetaLoopRunStoreError("run_summary_corrupt")
            normalized = _normalize({key: value[key] for key in _PAYLOAD_FIELDS})
            if normalized["idempotency_key"] != value.get("idempotency_key"):
                raise MetaLoopRunStoreError("run_summary_corrupt")
            rows.append(normalized)
        return rows

    def _append(self, record: Mapping[str, Any]) -> None:
        encoded = _canonical_bytes(record)
        descriptor = _open_private(self.events_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        parent = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)

    def record(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        record = _normalize(raw)
        lock = self._locked(exclusive=True)
        try:
            for existing in self._read_rows():
                if existing["run_id"] != record["run_id"]:
                    continue
                if existing != record:
                    raise MetaLoopRunStoreError("run_id_conflict")
                return {"status": "duplicate", "record": existing}
            self._append(record)
            return {"status": "appended", "record": record}
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def read_all(self) -> list[dict[str, Any]]:
        lock = self._locked(exclusive=False)
        try:
            return self._read_rows()
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def latest(self, run_id: str) -> dict[str, Any] | None:
        run_id = _text(run_id, "run_id_invalid", max_length=128)
        if _RUN_ID.fullmatch(run_id) is None:
            raise MetaLoopRunStoreError("run_id_invalid")
        rows = self.read_all()
        matches = [row for row in rows if row["run_id"] == run_id]
        return matches[-1] if matches else None


__all__ = ["MetaLoopRunStore", "MetaLoopRunStoreError", "SCHEMA_VERSION"]
