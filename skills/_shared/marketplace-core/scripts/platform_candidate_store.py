"""Durable, fail-closed state for Meta Loop platform candidates.

This module records only a validated candidate evaluation.  It does not
discover providers, register owners, or perform provider effects.
"""

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
_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "provider",
        "candidate_id",
        "observed_at",
        "source_url",
        "snapshot_sha256",
        "decision",
        "gates",
        "reasons",
        "evidence_refs",
        "next_action",
        "idempotency_key",
    }
)
_GATE_NAMES = ("policy", "adapter", "funded_work", "canary", "unit_economics")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
_CANDIDATE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_IDEMPOTENCY = re.compile(
    r"^marketplace-candidate:v1:[a-z][a-z0-9_-]{1,31}:"
    r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}:[0-9a-f]{64}$"
)
_MAX_LINE_BYTES = 64 * 1024


class CandidateStoreError(ValueError):
    """The candidate state is invalid, corrupt, or conflicts with history."""


def _text(value: Any, reason: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise CandidateStoreError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise CandidateStoreError(reason)
    return text


def _timestamp(value: Any) -> str:
    text = _text(value, "observed_at_invalid")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise CandidateStoreError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CandidateStoreError("observed_at_invalid")
    return text


def _string_list(value: Any, reason: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise CandidateStoreError(reason)
    if len(value) > 128:
        raise CandidateStoreError(reason)
    result: list[str] = []
    for item in value:
        result.append(_text(item, reason, max_length=1024))
    return result


def _normalize_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != _EVENT_FIELDS:
        raise CandidateStoreError("candidate_state_fields_invalid")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise CandidateStoreError("candidate_state_schema_invalid")

    provider = _text(raw.get("provider"), "provider_invalid", max_length=32)
    if _PROVIDER.fullmatch(provider) is None:
        raise CandidateStoreError("provider_invalid")
    candidate_id = _text(raw.get("candidate_id"), "candidate_id_invalid", max_length=128)
    if _CANDIDATE_ID.fullmatch(candidate_id) is None:
        raise CandidateStoreError("candidate_id_invalid")
    observed_at = _timestamp(raw.get("observed_at"))
    source_url = _text(raw.get("source_url"), "source_url_invalid", max_length=2048)
    if not source_url.startswith("https://"):
        raise CandidateStoreError("source_url_invalid")
    snapshot_sha256 = _text(raw.get("snapshot_sha256"), "snapshot_sha256_invalid", max_length=64)
    if _HASH.fullmatch(snapshot_sha256) is None:
        raise CandidateStoreError("snapshot_sha256_invalid")
    decision = _text(raw.get("decision"), "decision_invalid", max_length=16)
    if decision not in {"hold", "promote"}:
        raise CandidateStoreError("decision_invalid")

    gates = raw.get("gates")
    if not isinstance(gates, Mapping) or set(gates) != set(_GATE_NAMES):
        raise CandidateStoreError("gates_invalid")
    normalized_gates: dict[str, str] = {}
    for name in _GATE_NAMES:
        status = _text(gates.get(name), "gates_invalid", max_length=8)
        if status not in {"pass", "fail"}:
            raise CandidateStoreError("gates_invalid")
        normalized_gates[name] = status

    reasons = _string_list(raw.get("reasons"), "reasons_invalid", allow_empty=True)
    evidence_refs = _string_list(raw.get("evidence_refs"), "evidence_refs_invalid", allow_empty=True)
    next_action = _text(raw.get("next_action"), "next_action_invalid", max_length=1024)
    idempotency_key = _text(raw.get("idempotency_key"), "idempotency_key_invalid", max_length=256)
    expected_key = f"marketplace-candidate:v1:{provider}:{candidate_id}:{snapshot_sha256}"
    if _IDEMPOTENCY.fullmatch(idempotency_key) is None or idempotency_key != expected_key:
        raise CandidateStoreError("idempotency_key_invalid")

    return {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "candidate_id": candidate_id,
        "observed_at": observed_at,
        "source_url": source_url,
        "snapshot_sha256": snapshot_sha256,
        "decision": decision,
        "gates": normalized_gates,
        "reasons": reasons,
        "evidence_refs": evidence_refs,
        "next_action": next_action,
        "idempotency_key": idempotency_key,
    }


def _canonical_bytes(record: Mapping[str, Any]) -> bytes:
    data = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    encoded = (data + "\n").encode("utf-8")
    if len(encoded) > _MAX_LINE_BYTES:
        raise CandidateStoreError("candidate_state_line_too_large")
    return encoded


def _reject_symlink(path: Path, reason: str) -> None:
    if path.is_symlink():
        raise CandidateStoreError(reason)


def _ensure_root(path: Path) -> None:
    _reject_symlink(path, "candidate_state_root_invalid")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _reject_symlink(path, "candidate_state_root_invalid")
    if not path.is_dir():
        raise CandidateStoreError("candidate_state_root_invalid")
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise CandidateStoreError("candidate_state_root_permissions_invalid")


def _open_private(path: Path, flags: int, mode: int = 0o600) -> int:
    _reject_symlink(path, "candidate_state_file_invalid")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags | nofollow, mode)
    except OSError as error:
        raise CandidateStoreError("candidate_state_file_invalid") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise CandidateStoreError("candidate_state_file_invalid")
        os.fchmod(descriptor, 0o600)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


class CandidateStateStore:
    """An append-only private JSONL store for candidate evaluations."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser()
        self.events_path = self.root / "events.jsonl"
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
        if extra or len(payload) > _MAX_LINE_BYTES * 128:
            raise CandidateStoreError("candidate_state_corrupt")
        if not payload:
            return []
        if not payload.endswith(b"\n"):
            raise CandidateStoreError("candidate_state_corrupt")
        rows: list[dict[str, Any]] = []
        for line in payload.splitlines():
            if not line or len(line) + 1 > _MAX_LINE_BYTES:
                raise CandidateStoreError("candidate_state_corrupt")
            try:
                parsed = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise CandidateStoreError("candidate_state_corrupt") from error
            try:
                rows.append(_normalize_record(parsed))
            except CandidateStoreError as error:
                raise CandidateStoreError("candidate_state_corrupt") from error
        return rows

    def _append(self, record: Mapping[str, Any]) -> None:
        encoded = _canonical_bytes(record)
        descriptor = _open_private(self.events_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
        try:
            written = 0
            while written < len(encoded):
                written += os.write(descriptor, encoded[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        parent_descriptor = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)

    def record(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Append one candidate evaluation, or return a safe idempotent duplicate."""

        record = _normalize_record(raw)
        lock = self._locked(exclusive=True)
        try:
            rows = self._read_rows()
            for existing in rows:
                if existing["idempotency_key"] != record["idempotency_key"]:
                    continue
                if existing != record:
                    raise CandidateStoreError("candidate_idempotency_conflict")
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

    def latest(self, provider: str, candidate_id: str) -> dict[str, Any] | None:
        provider = _text(provider, "provider_invalid", max_length=32)
        if _PROVIDER.fullmatch(provider) is None:
            raise CandidateStoreError("provider_invalid")
        candidate_id = _text(candidate_id, "candidate_id_invalid", max_length=128)
        if _CANDIDATE_ID.fullmatch(candidate_id) is None:
            raise CandidateStoreError("candidate_id_invalid")
        rows = self.read_all()
        matches = [
            row for row in rows
            if row["provider"] == provider and row["candidate_id"] == candidate_id
        ]
        return matches[-1] if matches else None


__all__ = ["CandidateStateStore", "CandidateStoreError", "SCHEMA_VERSION"]
