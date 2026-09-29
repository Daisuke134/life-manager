"""Private, replay-safe JSONL state for read-only marketplace observations."""

from __future__ import annotations

from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping


SCHEMA_VERSION = 1
_FIELDS = frozenset({
    "schema_version", "provider", "opportunity_id", "source_url", "title", "currency",
    "source_hash", "observed_at", "decision", "reasons", "evidence_refs", "next_action",
    "idempotency_key",
})
_HASH = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
_OPPORTUNITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,191}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_MAX_LINE_BYTES = 64 * 1024


class OpportunityObservationError(ValueError):
    """Observation input, state, or idempotency history is unsafe."""


def _text(value: Any, reason: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise OpportunityObservationError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise OpportunityObservationError(reason)
    return text


def _timestamp(value: Any) -> str:
    text = _text(value, "observed_at_invalid")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise OpportunityObservationError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OpportunityObservationError("observed_at_invalid")
    return text


def _string_list(value: Any, reason: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise OpportunityObservationError(reason)
    return [_text(item, reason, max_length=1024) for item in value]


def _normalize(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != _FIELDS:
        raise OpportunityObservationError("opportunity_state_fields_invalid")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise OpportunityObservationError("opportunity_state_schema_invalid")
    provider = _text(raw.get("provider"), "provider_invalid", max_length=32)
    if _PROVIDER.fullmatch(provider) is None:
        raise OpportunityObservationError("provider_invalid")
    opportunity_id = _text(raw.get("opportunity_id"), "opportunity_id_invalid", max_length=192)
    if _OPPORTUNITY.fullmatch(opportunity_id) is None:
        raise OpportunityObservationError("opportunity_id_invalid")
    source_url = _text(raw.get("source_url"), "source_url_invalid", max_length=2048)
    if not source_url.startswith("https://"):
        raise OpportunityObservationError("source_url_invalid")
    title = _text(raw.get("title"), "title_invalid", max_length=512)
    currency = _text(raw.get("currency"), "currency_invalid", max_length=3)
    if _CURRENCY.fullmatch(currency) is None:
        raise OpportunityObservationError("currency_invalid")
    source_hash = _text(raw.get("source_hash"), "source_hash_invalid", max_length=64)
    if _HASH.fullmatch(source_hash) is None:
        raise OpportunityObservationError("source_hash_invalid")
    observed_at = _timestamp(raw.get("observed_at"))
    decision = _text(raw.get("decision"), "decision_invalid", max_length=16)
    if decision not in {"eligible", "hold"}:
        raise OpportunityObservationError("decision_invalid")
    reasons = _string_list(raw.get("reasons"), "reasons_invalid")
    evidence_refs = _string_list(raw.get("evidence_refs"), "evidence_refs_invalid")
    next_action = _text(raw.get("next_action"), "next_action_invalid", max_length=1024)
    idempotency_key = _text(raw.get("idempotency_key"), "idempotency_key_invalid", max_length=512)
    expected = f"marketplace-opportunity:v1:{provider}:{opportunity_id}:{source_hash}"
    if idempotency_key != expected:
        raise OpportunityObservationError("idempotency_key_invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "opportunity_id": opportunity_id,
        "source_url": source_url,
        "title": title,
        "currency": currency,
        "source_hash": source_hash,
        "observed_at": observed_at,
        "decision": decision,
        "reasons": reasons,
        "evidence_refs": evidence_refs,
        "next_action": next_action,
        "idempotency_key": idempotency_key,
    }


def _canonical_bytes(record: Mapping[str, Any]) -> bytes:
    encoded = (
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if len(encoded) > _MAX_LINE_BYTES:
        raise OpportunityObservationError("opportunity_state_line_too_large")
    return encoded


def _ensure_root(path: Path) -> None:
    if path.is_symlink():
        raise OpportunityObservationError("opportunity_state_root_invalid")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise OpportunityObservationError("opportunity_state_root_invalid")
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise OpportunityObservationError("opportunity_state_root_permissions_invalid")


def _open_private(path: Path, flags: int, mode: int = 0o600) -> int:
    if path.is_symlink():
        raise OpportunityObservationError("opportunity_state_file_invalid")
    try:
        descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)
    except OSError as error:
        raise OpportunityObservationError("opportunity_state_file_invalid") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise OpportunityObservationError("opportunity_state_file_invalid")
        os.fchmod(descriptor, 0o600)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


class OpportunityObservationStore:
    """Append-only private observation state with exactly-once snapshot identity."""

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
        if extra or not payload or not payload.endswith(b"\n"):
            if not payload:
                return []
            raise OpportunityObservationError("opportunity_state_corrupt")
        rows: list[dict[str, Any]] = []
        for line in payload.splitlines():
            if not line or len(line) + 1 > _MAX_LINE_BYTES:
                raise OpportunityObservationError("opportunity_state_corrupt")
            try:
                parsed = json.loads(line.decode("utf-8"))
                rows.append(_normalize(parsed))
            except (UnicodeDecodeError, json.JSONDecodeError, OpportunityObservationError) as error:
                raise OpportunityObservationError("opportunity_state_corrupt") from error
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
        record = _normalize(raw)
        lock = self._locked(exclusive=True)
        try:
            for existing in self._read_rows():
                if existing["idempotency_key"] != record["idempotency_key"]:
                    continue
                if existing != record:
                    raise OpportunityObservationError("opportunity_idempotency_conflict")
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

    def latest(self, provider: str, opportunity_id: str) -> dict[str, Any] | None:
        provider = _text(provider, "provider_invalid", max_length=32)
        opportunity_id = _text(opportunity_id, "opportunity_id_invalid", max_length=192)
        rows = self.read_all()
        matches = [
            row for row in rows
            if row["provider"] == provider and row["opportunity_id"] == opportunity_id
        ]
        return matches[-1] if matches else None


__all__ = ["OpportunityObservationError", "OpportunityObservationStore", "SCHEMA_VERSION"]
