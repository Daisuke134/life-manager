"""Fail-closed, provider-neutral Meta Loop promotion lifecycle.

Discovery and candidate scoring stay in :mod:`platform_enrollment`.  This
module owns the shared boundary after a candidate is promoted: it fences the
owner effect, asks an injected provider adapter for an owner/canary/settlement
receipt, rolls back unverified work, and persists every outcome privately.
No provider transport is imported here; adapters are the only code allowed to
perform provider effects.
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
_EVENT_FIELDS = frozenset({
    "schema_version", "event_key", "lifecycle_key", "provider", "candidate_id",
    "candidate_snapshot_key", "run_id", "observed_at", "phase", "status",
    "owner_id", "owner_receipt_ref", "canary_receipt_ref",
    "settlement_receipt_ref", "rollback_receipt_ref", "net_amount_minor",
    "currency", "reason", "error_class", "next_action",
})
_PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT = re.compile(r"^provider-receipt://[^/]+/[^/]+$")
_LIFECYCLE_KEY = re.compile(
    r"^meta-loop-lifecycle:v1:[a-z][a-z0-9_-]{1,31}:"
    r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}:[0-9a-f]{64}$"
)
_EVENT_KEY = re.compile(
    r"^meta-loop-lifecycle:v1:[a-z][a-z0-9_-]{1,31}:"
    r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}:[0-9a-f]{64}:[a-z_]+$"
)
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_GATE_NAMES = ("policy", "adapter", "funded_work", "canary", "unit_economics")
_PHASES = frozenset({"provision", "terminal", "rollback"})
_STATUSES = frozenset({
    "planned", "held", "failed", "settled", "rolled_back",
    "rollback_required", "effect_unknown",
})
_TERMINAL_STATUSES = frozenset(_STATUSES - {"planned"})
_MAX_LINE_BYTES = 64 * 1024


class MetaLoopLifecycleError(ValueError):
    """A lifecycle input or provider receipt is unsafe to use."""


class MetaLoopLifecycleStoreError(MetaLoopLifecycleError):
    """Lifecycle state is malformed, corrupt, or idempotency-conflicted."""


def _text(value: Any, reason: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise MetaLoopLifecycleError(reason)
    value = value.strip()
    if not value or len(value) > max_length or "\x00" in value:
        raise MetaLoopLifecycleError(reason)
    return value


def _timestamp(value: Any, reason: str) -> str:
    value = _text(value, reason)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MetaLoopLifecycleError(reason) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MetaLoopLifecycleError(reason)
    return value


def _provider(value: Any, reason: str = "provider_invalid") -> str:
    value = _text(value, reason, max_length=32)
    if _PROVIDER.fullmatch(value) is None:
        raise MetaLoopLifecycleError(reason)
    return value


def _candidate_id(value: Any) -> str:
    value = _text(value, "candidate_id_invalid", max_length=128)
    if _ID.fullmatch(value) is None:
        raise MetaLoopLifecycleError("candidate_id_invalid")
    return value


def _receipt(value: Any, reason: str, provider: str) -> str:
    value = _text(value, reason, max_length=512)
    if _RECEIPT.fullmatch(value) is None:
        raise MetaLoopLifecycleError(reason)
    observed_provider = value[len("provider-receipt://"):].split("/", 1)[0]
    if observed_provider != provider:
        raise MetaLoopLifecycleError("receipt_provider_mismatch")
    return value


def _candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        raise MetaLoopLifecycleError("candidate_invalid")
    provider = _provider(candidate.get("provider"))
    candidate_id = _candidate_id(candidate.get("candidate_id"))
    decision = _text(candidate.get("decision"), "decision_invalid", max_length=16)
    if decision not in {"hold", "promote"}:
        raise MetaLoopLifecycleError("decision_invalid")
    gates = candidate.get("gates")
    if not isinstance(gates, Mapping) or set(gates) != set(_GATE_NAMES):
        raise MetaLoopLifecycleError("gates_invalid")
    normalized_gates: dict[str, str] = {}
    for name in _GATE_NAMES:
        status = _text(gates.get(name), "gates_invalid", max_length=8)
        if status not in {"pass", "fail"}:
            raise MetaLoopLifecycleError("gates_invalid")
        normalized_gates[name] = status
    snapshot_key = _text(
        candidate.get("idempotency_key", candidate.get("candidate_snapshot_key")),
        "candidate_snapshot_key_invalid", max_length=256,
    )
    snapshot_prefix = f"marketplace-candidate:v1:{provider}:{candidate_id}:"
    if (
        not snapshot_key.startswith(snapshot_prefix)
        or _SHA256.fullmatch(snapshot_key[len(snapshot_prefix):]) is None
    ):
        raise MetaLoopLifecycleError("candidate_snapshot_key_invalid")
    next_action = _text(candidate.get("next_action"), "next_action_invalid", max_length=1024)
    return {
        "provider": provider,
        "candidate_id": candidate_id,
        "decision": decision,
        "gates": normalized_gates,
        "candidate_snapshot_key": snapshot_key,
        "next_action": next_action,
    }


def _is_promotable(candidate: Mapping[str, Any]) -> bool:
    return candidate["decision"] == "promote" and all(
        value == "pass" for value in candidate["gates"].values()
    )


def lifecycle_key(candidate: Mapping[str, Any]) -> str:
    """Return one idempotency identity for one provider/candidate snapshot."""

    value = _candidate(candidate)
    digest = hashlib.sha256(value["candidate_snapshot_key"].encode("utf-8")).hexdigest()
    return f"meta-loop-lifecycle:v1:{value['provider']}:{value['candidate_id']}:{digest}"


def _event_key(lifecycle: str, suffix: str) -> str:
    value = f"{lifecycle}:{suffix}"
    if _EVENT_KEY.fullmatch(value) is None:
        raise MetaLoopLifecycleError("event_key_invalid")
    return value


def _event(
    candidate: Mapping[str, Any],
    lifecycle: str,
    *,
    run_id: str,
    observed_at: str,
    phase: str,
    status: str,
    next_action: str,
    reason: str,
    owner_id: str | None = None,
    owner_receipt_ref: str | None = None,
    canary_receipt_ref: str | None = None,
    settlement_receipt_ref: str | None = None,
    rollback_receipt_ref: str | None = None,
    net_amount_minor: int | None = None,
    currency: str | None = None,
    error_class: str | None = None,
    suffix: str | None = None,
) -> dict[str, Any]:
    value = _candidate(candidate)
    if not isinstance(lifecycle, str) or _LIFECYCLE_KEY.fullmatch(lifecycle) is None:
        raise MetaLoopLifecycleError("lifecycle_key_invalid")
    run_id = _text(run_id, "run_id_invalid", max_length=128)
    if _RUN_ID.fullmatch(run_id) is None:
        raise MetaLoopLifecycleError("run_id_invalid")
    observed_at = _timestamp(observed_at, "observed_at_invalid")
    if phase not in _PHASES or status not in _STATUSES:
        raise MetaLoopLifecycleError("lifecycle_state_invalid")
    if suffix is None:
        suffix = status
    record = {
        "schema_version": SCHEMA_VERSION,
        "event_key": _event_key(lifecycle, suffix),
        "lifecycle_key": lifecycle,
        "provider": value["provider"],
        "candidate_id": value["candidate_id"],
        "candidate_snapshot_key": value["candidate_snapshot_key"],
        "run_id": run_id,
        "observed_at": observed_at,
        "phase": phase,
        "status": status,
        "owner_id": owner_id,
        "owner_receipt_ref": owner_receipt_ref,
        "canary_receipt_ref": canary_receipt_ref,
        "settlement_receipt_ref": settlement_receipt_ref,
        "rollback_receipt_ref": rollback_receipt_ref,
        "net_amount_minor": net_amount_minor,
        "currency": currency,
        "reason": _text(reason, "reason_invalid", max_length=256),
        "error_class": error_class,
        "next_action": _text(next_action, "next_action_invalid", max_length=256),
    }
    return record


def planned_event(
    candidate: Mapping[str, Any], lifecycle: str, *, run_id: str, observed_at: str,
) -> dict[str, Any]:
    """Build the pre-effect fence written before owner provisioning."""

    return _event(
        candidate, lifecycle, run_id=run_id, observed_at=observed_at,
        phase="provision", status="planned", next_action="provision_owner",
        reason="owner_provision_pending", suffix="planned",
    )


def _normalize_event(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != _EVENT_FIELDS:
        raise MetaLoopLifecycleStoreError("event_fields_invalid")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise MetaLoopLifecycleStoreError("event_schema_invalid")
    provider = _provider(raw.get("provider"), "provider_invalid")
    candidate_id = _candidate_id(raw.get("candidate_id"))
    lifecycle = _text(raw.get("lifecycle_key"), "lifecycle_key_invalid", max_length=256)
    if _LIFECYCLE_KEY.fullmatch(lifecycle) is None:
        raise MetaLoopLifecycleStoreError("lifecycle_key_invalid")
    event_key = _text(raw.get("event_key"), "event_key_invalid", max_length=300)
    if _EVENT_KEY.fullmatch(event_key) is None or not event_key.startswith(lifecycle + ":"):
        raise MetaLoopLifecycleStoreError("event_key_invalid")
    snapshot = _text(
        raw.get("candidate_snapshot_key"), "candidate_snapshot_key_invalid", max_length=256,
    )
    expected_prefix = f"marketplace-candidate:v1:{provider}:{candidate_id}:"
    if (
        not snapshot.startswith(expected_prefix)
        or _SHA256.fullmatch(snapshot[len(expected_prefix):]) is None
    ):
        raise MetaLoopLifecycleStoreError("candidate_snapshot_key_invalid")
    run_id = _text(raw.get("run_id"), "run_id_invalid", max_length=128)
    if _RUN_ID.fullmatch(run_id) is None:
        raise MetaLoopLifecycleStoreError("run_id_invalid")
    _timestamp(raw.get("observed_at"), "observed_at_invalid")
    phase = _text(raw.get("phase"), "lifecycle_state_invalid", max_length=16)
    status = _text(raw.get("status"), "lifecycle_state_invalid", max_length=32)
    if phase not in _PHASES or status not in _STATUSES:
        raise MetaLoopLifecycleStoreError("lifecycle_state_invalid")

    def optional_receipt(name: str) -> str | None:
        value = raw.get(name)
        if value is None:
            return None
        try:
            return _receipt(value, f"{name}_invalid", provider)
        except MetaLoopLifecycleError as error:
            raise MetaLoopLifecycleStoreError(str(error)) from error

    owner_id = raw.get("owner_id")
    if owner_id is not None:
        owner_id = _text(owner_id, "owner_id_invalid", max_length=256)
    owner_receipt_ref = optional_receipt("owner_receipt_ref")
    canary_receipt_ref = optional_receipt("canary_receipt_ref")
    settlement_receipt_ref = optional_receipt("settlement_receipt_ref")
    rollback_receipt_ref = optional_receipt("rollback_receipt_ref")
    net = raw.get("net_amount_minor")
    if net is not None and (type(net) is not int or net < 0):
        raise MetaLoopLifecycleStoreError("net_amount_invalid")
    currency = raw.get("currency")
    if currency is not None:
        currency = _text(currency, "currency_invalid", max_length=3)
        if _CURRENCY.fullmatch(currency) is None:
            raise MetaLoopLifecycleStoreError("currency_invalid")
    reason = _text(raw.get("reason"), "reason_invalid", max_length=256)
    error_class = raw.get("error_class")
    if error_class is not None:
        error_class = _text(error_class, "error_class_invalid", max_length=128)
    next_action = _text(raw.get("next_action"), "next_action_invalid", max_length=256)

    if status == "settled" and (
        phase != "terminal" or settlement_receipt_ref is None or net is None or net <= 0 or currency is None
    ):
        raise MetaLoopLifecycleStoreError("settlement_receipt_incomplete")
    if status == "rolled_back" and (phase != "rollback" or rollback_receipt_ref is None):
        raise MetaLoopLifecycleStoreError("rollback_receipt_incomplete")
    if status == "rollback_required" and (phase != "rollback" or owner_receipt_ref is None):
        raise MetaLoopLifecycleStoreError("rollback_required_receipt_incomplete")
    if status == "planned" and (phase != "provision" or any(
        value is not None for value in (
            owner_receipt_ref, canary_receipt_ref, settlement_receipt_ref, rollback_receipt_ref,
        )
    )):
        raise MetaLoopLifecycleStoreError("planned_event_invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "event_key": event_key,
        "lifecycle_key": lifecycle,
        "provider": provider,
        "candidate_id": candidate_id,
        "candidate_snapshot_key": snapshot,
        "run_id": run_id,
        "observed_at": _timestamp(raw.get("observed_at"), "observed_at_invalid"),
        "phase": phase,
        "status": status,
        "owner_id": owner_id,
        "owner_receipt_ref": owner_receipt_ref,
        "canary_receipt_ref": canary_receipt_ref,
        "settlement_receipt_ref": settlement_receipt_ref,
        "rollback_receipt_ref": rollback_receipt_ref,
        "net_amount_minor": net,
        "currency": currency,
        "reason": reason,
        "error_class": error_class,
        "next_action": next_action,
    }


def _canonical_bytes(record: Mapping[str, Any]) -> bytes:
    encoded = (
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if len(encoded) > _MAX_LINE_BYTES:
        raise MetaLoopLifecycleStoreError("event_line_too_large")
    return encoded


def _reject_symlink(path: Path, reason: str) -> None:
    if path.is_symlink():
        raise MetaLoopLifecycleStoreError(reason)


def _ensure_root(path: Path) -> None:
    _reject_symlink(path, "lifecycle_root_invalid")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _reject_symlink(path, "lifecycle_root_invalid")
    if not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise MetaLoopLifecycleStoreError("lifecycle_root_invalid")


def _open_private(path: Path, flags: int, mode: int = 0o600) -> int:
    _reject_symlink(path, "lifecycle_file_invalid")
    try:
        descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)
    except OSError as error:
        raise MetaLoopLifecycleStoreError("lifecycle_file_invalid") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise MetaLoopLifecycleStoreError("lifecycle_file_invalid")
        os.fchmod(descriptor, 0o600)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


class MetaLoopLifecycleStore:
    """Private append-only event store with lifecycle-key idempotency."""

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
            payload = os.read(descriptor, _MAX_LINE_BYTES * 256)
            extra = os.read(descriptor, 1)
        finally:
            os.close(descriptor)
        if extra or (payload and not payload.endswith(b"\n")):
            raise MetaLoopLifecycleStoreError("lifecycle_corrupt")
        if not payload:
            return []
        rows: list[dict[str, Any]] = []
        for line in payload.splitlines():
            try:
                raw = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise MetaLoopLifecycleStoreError("lifecycle_corrupt") from error
            try:
                rows.append(_normalize_event(raw))
            except MetaLoopLifecycleError as error:
                raise MetaLoopLifecycleStoreError("lifecycle_corrupt") from error
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
        parent = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)

    def record(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        record = _normalize_event(raw)
        lock = self._locked(exclusive=True)
        try:
            for existing in self._read_rows():
                if existing["event_key"] != record["event_key"]:
                    continue
                if existing != record:
                    raise MetaLoopLifecycleStoreError("event_key_conflict")
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

    def latest(self, lifecycle: str) -> dict[str, Any] | None:
        if not isinstance(lifecycle, str) or _LIFECYCLE_KEY.fullmatch(lifecycle) is None:
            raise MetaLoopLifecycleStoreError("lifecycle_key_invalid")
        rows = self.read_all()
        matches = [row for row in rows if row["lifecycle_key"] == lifecycle]
        return matches[-1] if matches else None


def _method(adapter: Any, name: str):
    value = getattr(adapter, name, None)
    if not callable(value):
        raise MetaLoopLifecycleError(f"adapter_{name}_missing")
    return value


def _owner_receipt(raw: Any, provider: str) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise MetaLoopLifecycleError("owner_receipt_invalid")
    if _text(raw.get("status"), "owner_receipt_invalid", max_length=32) != "provisioned":
        raise MetaLoopLifecycleError("owner_not_provisioned")
    owner_id = _text(raw.get("owner_id"), "owner_receipt_invalid", max_length=256)
    receipt = _receipt(raw.get("receipt_ref"), "owner_receipt_invalid", provider)
    _timestamp(raw.get("observed_at"), "owner_receipt_invalid")
    return {"owner_id": owner_id, "receipt_ref": receipt}


def _canary_receipt(raw: Any, provider: str) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise MetaLoopLifecycleError("canary_receipt_invalid")
    if _text(raw.get("status"), "canary_receipt_invalid", max_length=32) != "verified":
        raise MetaLoopLifecycleError("canary_not_verified")
    if raw.get("replay_zero") is not True:
        raise MetaLoopLifecycleError("replay_not_zero")
    receipt = _receipt(raw.get("receipt_ref"), "canary_receipt_invalid", provider)
    _timestamp(raw.get("observed_at"), "canary_receipt_invalid")
    return {"receipt_ref": receipt}


def _rollback_receipt(raw: Any, provider: str) -> str:
    if not isinstance(raw, Mapping):
        raise MetaLoopLifecycleError("rollback_receipt_invalid")
    if _text(raw.get("status"), "rollback_receipt_invalid", max_length=32) != "rolled_back":
        raise MetaLoopLifecycleError("rollback_not_verified")
    receipt = _receipt(raw.get("receipt_ref"), "rollback_receipt_invalid", provider)
    _timestamp(raw.get("observed_at"), "rollback_receipt_invalid")
    return receipt


def _settlement_receipt(raw: Any, provider: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise MetaLoopLifecycleError("settlement_receipt_invalid")
    if _text(raw.get("status"), "settlement_receipt_invalid", max_length=32) != "settled":
        raise MetaLoopLifecycleError("settlement_not_settled")
    receipt = _receipt(raw.get("receipt_ref"), "settlement_receipt_invalid", provider)
    net = raw.get("net_amount_minor")
    if type(net) is not int or net <= 0:
        raise MetaLoopLifecycleError("settlement_net_not_positive")
    currency = _text(raw.get("currency"), "settlement_receipt_invalid", max_length=3)
    if _CURRENCY.fullmatch(currency) is None:
        raise MetaLoopLifecycleError("settlement_currency_invalid")
    _timestamp(raw.get("observed_at"), "settlement_receipt_invalid")
    return {"receipt_ref": receipt, "net_amount_minor": net, "currency": currency}


def _save_terminal(
    store: Any,
    candidate: Mapping[str, Any],
    lifecycle: str,
    *,
    run_id: str,
    observed_at: str,
    status: str,
    phase: str,
    reason: str,
    next_action: str,
    owner_id: str | None = None,
    owner_receipt_ref: str | None = None,
    canary_receipt_ref: str | None = None,
    settlement_receipt_ref: str | None = None,
    rollback_receipt_ref: str | None = None,
    net_amount_minor: int | None = None,
    currency: str | None = None,
    error_class: str | None = None,
) -> dict[str, Any]:
    event = _event(
        candidate, lifecycle, run_id=run_id, observed_at=observed_at,
        phase=phase, status=status, reason=reason, next_action=next_action,
        owner_id=owner_id, owner_receipt_ref=owner_receipt_ref,
        canary_receipt_ref=canary_receipt_ref,
        settlement_receipt_ref=settlement_receipt_ref,
        rollback_receipt_ref=rollback_receipt_ref,
        net_amount_minor=net_amount_minor, currency=currency,
        error_class=error_class,
    )
    persistence = getattr(store, "record", None)
    if not callable(persistence):
        raise MetaLoopLifecycleError("lifecycle_store_invalid")
    result = persistence(event)
    return {
        "status": status, "lifecycle_key": lifecycle, "next_action": next_action,
        "record": result.get("record", event), "persistence": result,
    }


def _rollback(
    candidate: Mapping[str, Any], adapter: Any, store: Any, lifecycle: str, *,
    run_id: str, observed_at: str, owner: Mapping[str, str],
    canary_receipt_ref: str | None, reason: str, error_class: str | None = None,
    next_action_on_success: str = "hold_until_new_candidate_snapshot",
) -> dict[str, Any]:
    provider = candidate["provider"]
    try:
        raw = _method(adapter, "rollback_owner")(dict(candidate), dict(owner), reason)
        rollback_ref = _rollback_receipt(raw, provider)
    except Exception as error:
        return _save_terminal(
            store, candidate, lifecycle, run_id=run_id, observed_at=observed_at,
            status="rollback_required", phase="rollback", reason=reason,
            next_action="official_readback_then_rollback", owner_id=owner["owner_id"],
            owner_receipt_ref=owner["receipt_ref"], canary_receipt_ref=canary_receipt_ref,
            error_class=type(error).__name__,
        )
    return _save_terminal(
        store, candidate, lifecycle, run_id=run_id, observed_at=observed_at,
        status="rolled_back", phase="rollback", reason=reason,
        next_action=next_action_on_success, owner_id=owner["owner_id"],
        owner_receipt_ref=owner["receipt_ref"], canary_receipt_ref=canary_receipt_ref,
        rollback_receipt_ref=rollback_ref, error_class=error_class,
    )


def run_meta_loop_lifecycle(
    candidate: Mapping[str, Any], adapter: Any, store: Any, *,
    run_id: str, observed_at: str,
) -> dict[str, Any]:
    """Execute one fenced Meta Loop promotion lifecycle.

    A planned event is persisted before the first provider effect.  If a later
    wake sees that fence without a terminal receipt, it returns
    ``reconcile_required`` and never replays the owner effect.
    """

    value = _candidate(candidate)
    lifecycle = lifecycle_key(candidate)
    latest_reader = getattr(store, "latest", None)
    recorder = getattr(store, "record", None)
    if not callable(latest_reader) or not callable(recorder):
        raise MetaLoopLifecycleError("lifecycle_store_invalid")
    existing = latest_reader(lifecycle)
    if existing is not None:
        if existing["status"] in _TERMINAL_STATUSES:
            return {
                "status": "duplicate", "lifecycle_key": lifecycle, "record": existing,
                "next_action": existing["next_action"],
            }
        return {
            "status": "reconcile_required", "lifecycle_key": lifecycle,
            "record": existing, "next_action": "official_readback_before_retry",
        }

    if not _is_promotable(value):
        return _save_terminal(
            store, value, lifecycle, run_id=run_id, observed_at=observed_at,
            status="held", phase="terminal", reason="candidate_not_promotable",
            next_action=value["next_action"],
        )

    plan = recorder(planned_event(value, lifecycle, run_id=run_id, observed_at=observed_at))
    if plan.get("status") == "duplicate":
        existing = latest_reader(lifecycle)
        if existing is None:
            raise MetaLoopLifecycleError("lifecycle_plan_readback_missing")
        return {
            "status": "reconcile_required", "lifecycle_key": lifecycle,
            "record": existing, "next_action": "official_readback_before_retry",
        }

    provider = value["provider"]
    try:
        raw_owner = _method(adapter, "provision_owner")(dict(value))
        owner = _owner_receipt(raw_owner, provider)
    except Exception as error:
        return _save_terminal(
            store, value, lifecycle, run_id=run_id, observed_at=observed_at,
            status="effect_unknown", phase="terminal", reason="owner_provision_failed",
            next_action="official_readback_before_retry", error_class=type(error).__name__,
        )

    try:
        raw_canary = _method(adapter, "canary_readback")(dict(value), dict(owner))
        canary = _canary_receipt(raw_canary, provider)
    except Exception as error:
        return _rollback(
            value, adapter, store, lifecycle, run_id=run_id, observed_at=observed_at,
            owner=owner, canary_receipt_ref=None, reason="canary_unverified",
            error_class=type(error).__name__,
        )

    try:
        raw_settlement = _method(adapter, "settle")(dict(value), dict(owner), dict(canary))
        settlement = _settlement_receipt(raw_settlement, provider)
    except Exception as error:
        return _rollback(
            value, adapter, store, lifecycle, run_id=run_id, observed_at=observed_at,
            owner=owner, canary_receipt_ref=canary["receipt_ref"],
            reason="settlement_unverified", error_class=type(error).__name__,
            next_action_on_success="retry_after_provider_readback",
        )

    return _save_terminal(
        store, value, lifecycle, run_id=run_id, observed_at=observed_at,
        status="settled", phase="terminal", reason="lifecycle_complete",
        next_action="continue_quality_and_payout_readback", owner_id=owner["owner_id"],
        owner_receipt_ref=owner["receipt_ref"], canary_receipt_ref=canary["receipt_ref"],
        settlement_receipt_ref=settlement["receipt_ref"],
        net_amount_minor=settlement["net_amount_minor"], currency=settlement["currency"],
    )


__all__ = [
    "MetaLoopLifecycleError", "MetaLoopLifecycleStore", "MetaLoopLifecycleStoreError",
    "lifecycle_key", "planned_event", "run_meta_loop_lifecycle", "SCHEMA_VERSION",
]
