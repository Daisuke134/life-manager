"""Provider-neutral, append-only human-gate contract.

Only an explicitly declared human act (interview, KYC, identity recording, or
approval) may create a gate.  The record carries the same owner/effect
namespace that will resume later, plus a stable notification event key.  It is
deliberately independent of any provider browser or Telegram sender.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
ACTION_KINDS = ("interview", "kyc", "identity_recording", "approval")
STATUSES = ("pending", "resolved", "expired", "rejected")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_REF = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]{1,1024}$", re.IGNORECASE)
_SECRET = re.compile(r"\b(?:password|cookie|api[_ -]?key|access[_ -]?token|secret)\b", re.IGNORECASE)
_FIELDS = (
    "schema_version", "record_type", "human_gate_id", "tenant_id", "owner_id",
    "product_loop_id", "job_id", "wake_id", "effect_key", "capability",
    "action_kind", "action", "action_sha256", "evidence_ref", "deadline",
    "status", "notification_event_id", "outbox_id", "answer_ref", "created_at",
    "updated_at",
)


class HumanGateError(ValueError):
    """The gate is malformed, unsafe, or conflicts with an existing identity."""


def _invalid(label: str) -> None:
    raise HumanGateError(f"human_gate_{label}")


def _exact_keys(value: Any, expected: Iterable[str]) -> None:
    if not isinstance(value, dict) or tuple(sorted(value)) != tuple(sorted(expected)):
        _invalid("shape")


def _text(value: Any, label: str, maximum: int = 128, *, secret_check: bool = False) -> str:
    if not isinstance(value, str):
        _invalid(label)
    text = value.strip()
    if not text or len(text) > maximum or "\x00" in text:
        _invalid(label)
    if secret_check and _SECRET.search(text):
        _invalid(label)
    return text


def _id(value: Any, label: str) -> str:
    text = _text(value, label, 128)
    if not _ID.fullmatch(text):
        _invalid(label)
    return text


def _hash(value: Any, label: str) -> str:
    text = _text(value, label, 64)
    if not _SHA256.fullmatch(text):
        _invalid(label)
    return text


def _ref(value: Any, label: str) -> str:
    text = _text(value, label, 1024, secret_check=True)
    if not _REF.fullmatch(text):
        _invalid(label)
    parsed = urlsplit(text)
    if not parsed.scheme or not parsed.netloc or parsed.username or parsed.password:
        _invalid(label)
    return text


def _instant(value: Any, label: str) -> str:
    text = _text(value, label, 40)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _invalid(label)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _invalid(label)
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _action_hash(action: str) -> str:
    return hashlib.sha256(action.encode("utf-8")).hexdigest()


def _identity_payload(value: dict[str, Any]) -> str:
    return "\n".join([
        value["tenant_id"], value["owner_id"], value["product_loop_id"], value["job_id"],
        value["wake_id"], value["effect_key"], value["capability"], value["action_kind"],
        value["action_sha256"], value["evidence_ref"],
    ])


def _expected_gate_id(value: dict[str, Any]) -> str:
    return "human-gate-" + hashlib.sha256(_identity_payload(value).encode("utf-8")).hexdigest()[:32]


def validate_human_gate(value: dict[str, Any]) -> dict[str, Any]:
    _exact_keys(value, _FIELDS)
    if value["schema_version"] != SCHEMA_VERSION or value["record_type"] != "human_gate":
        _invalid("version")
    human_gate_id = _id(value["human_gate_id"], "id")
    tenant_id = _id(value["tenant_id"], "tenant_id")
    owner_id = _id(value["owner_id"], "owner_id")
    product_loop_id = _id(value["product_loop_id"], "product_loop_id")
    job_id = _id(value["job_id"], "job_id")
    wake_id = _id(value["wake_id"], "wake_id")
    effect_key = _id(value["effect_key"], "effect_key")
    capability = _id(value["capability"], "capability")
    action_kind = _text(value["action_kind"], "action_kind", 32)
    if action_kind not in ACTION_KINDS:
        _invalid("action_kind")
    action = _text(value["action"], "action", 1000, secret_check=True)
    action_sha256 = _hash(value["action_sha256"], "action_sha256")
    if action_sha256 != _action_hash(action):
        _invalid("action_sha256")
    evidence_ref = _ref(value["evidence_ref"], "evidence_ref")
    deadline = _instant(value["deadline"], "deadline")
    status = _text(value["status"], "status", 16)
    if status not in STATUSES:
        _invalid("status")
    notification_event_id = _id(value["notification_event_id"], "notification_event_id")
    outbox_id = None if value["outbox_id"] is None else _id(value["outbox_id"], "outbox_id")
    answer_ref = None if value["answer_ref"] is None else _ref(value["answer_ref"], "answer_ref")
    created_at = _instant(value["created_at"], "created_at")
    updated_at = _instant(value["updated_at"], "updated_at")
    if datetime.fromisoformat(deadline.replace("Z", "+00:00")) <= datetime.fromisoformat(created_at.replace("Z", "+00:00")):
        _invalid("deadline")
    if datetime.fromisoformat(updated_at.replace("Z", "+00:00")) < datetime.fromisoformat(created_at.replace("Z", "+00:00")):
        _invalid("updated_at")
    canonical = {
        "schema_version": SCHEMA_VERSION, "record_type": "human_gate", "human_gate_id": human_gate_id,
        "tenant_id": tenant_id, "owner_id": owner_id, "product_loop_id": product_loop_id,
        "job_id": job_id, "wake_id": wake_id, "effect_key": effect_key, "capability": capability,
        "action_kind": action_kind, "action": action, "action_sha256": action_sha256,
        "evidence_ref": evidence_ref, "deadline": deadline, "status": status,
        "notification_event_id": notification_event_id, "outbox_id": outbox_id,
        "answer_ref": answer_ref, "created_at": created_at, "updated_at": updated_at,
    }
    if human_gate_id != _expected_gate_id(canonical):
        _invalid("identity")
    if notification_event_id != f"human-gate:{human_gate_id}":
        _invalid("notification_identity")
    if status == "pending" and answer_ref is not None:
        _invalid("pending_answer")
    return canonical


def build_human_gate(
    *, tenant_id: str, owner_id: str, product_loop_id: str, job_id: str, wake_id: str,
    effect_key: str, capability: str, action_kind: str, action: str, evidence_ref: str,
    deadline: str, created_at: str | None = None,
) -> dict[str, Any]:
    created = _instant(created_at or datetime.now(timezone.utc).isoformat(), "created_at")
    draft = {
        "schema_version": SCHEMA_VERSION, "record_type": "human_gate", "human_gate_id": "pending",
        "tenant_id": _id(tenant_id, "tenant_id"), "owner_id": _id(owner_id, "owner_id"),
        "product_loop_id": _id(product_loop_id, "product_loop_id"), "job_id": _id(job_id, "job_id"),
        "wake_id": _id(wake_id, "wake_id"), "effect_key": _id(effect_key, "effect_key"),
        "capability": _id(capability, "capability"), "action_kind": _text(action_kind, "action_kind", 32),
        "action": _text(action, "action", 1000, secret_check=True), "action_sha256": "",
        "evidence_ref": _ref(evidence_ref, "evidence_ref"), "deadline": _instant(deadline, "deadline"),
        "status": "pending", "notification_event_id": "pending", "outbox_id": None, "answer_ref": None,
        "created_at": created, "updated_at": created,
    }
    draft["action_sha256"] = _action_hash(draft["action"])
    draft["human_gate_id"] = _expected_gate_id(draft)
    draft["notification_event_id"] = f"human-gate:{draft['human_gate_id']}"
    return validate_human_gate(draft)


class HumanGateStore:
    """Append-only JSONL store with one current row per stable gate identity."""

    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        if self.path.exists():
            self.path.chmod(0o600)

    @contextmanager
    def _lock(self):
        lock_path = self.path.with_name(self.path.name + ".lock")
        lock_path.touch(mode=0o600, exist_ok=True)
        lock_path.chmod(0o600)
        with lock_path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(validate_human_gate(json.loads(line)))
            except (json.JSONDecodeError, HumanGateError) as error:
                raise HumanGateError("human_gate_state_invalid") from error
        return rows

    def _append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.path.chmod(0o600)

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        checked = validate_human_gate(record)
        with self._lock():
            existing = {row["human_gate_id"]: row for row in self._rows()}.get(checked["human_gate_id"])
            if existing is not None:
                if existing == checked:
                    return existing
                raise HumanGateError("human_gate_conflict")
            self._append(checked)
            return checked

    def pending(self) -> list[dict[str, Any]]:
        with self._lock():
            latest = {row["human_gate_id"]: row for row in self._rows()}
            return sorted((row for row in latest.values() if row["status"] == "pending"), key=lambda row: row["human_gate_id"])
