#!/usr/bin/env python3
"""Reconcile one CFO Telegram effect from occurrence-bound local receipts.

The adapter never sends Telegram and never retries an outbox item.  A normal
invocation only reads the admission row, runtime event pair, private CFO
snapshot, and the shared Telegram outbox.  ``--resolve`` is the sole path that
passes an already verified provider receipt to the admission resolver.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
from typing import Any


OWNER_ID = "life-manager-cfo-hourly"
OCCURRENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EVENT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,1023}$")
MAX_EVENT_BYTES = 16 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUTBOX_ROOT = ROOT / "apps/life-manager/investment-core"
if str(OUTBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(OUTBOX_ROOT))

from runtime.host.resource_admission import resolve_unknown_occurrence  # noqa: E402
from telegram_outbox import list_items  # noqa: E402


def _fail(reason: str) -> ValueError:
    return ValueError(reason)


def _private_file(path: Path, *, max_bytes: int, label: str) -> bytes:
    """Read one owner-private regular file without following links."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise _fail(f"{label}_missing") from error
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > max_bytes
        ):
            raise _fail(f"{label}_not_private")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_json(path: Path, *, max_bytes: int, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_private_file(path, max_bytes=max_bytes, label=label))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _fail(f"{label}_invalid") from error
    if not isinstance(value, dict):
        raise _fail(f"{label}_invalid")
    return value


def _read_admission(database: Path, occurrence_id: str) -> dict[str, Any]:
    if not OCCURRENCE.fullmatch(occurrence_id):
        raise _fail("occurrence_invalid")
    if not occurrence_id.startswith(f"{OWNER_ID}:"):
        raise _fail("occurrence_owner_mismatch")
    if not database.is_file() or database.is_symlink():
        raise _fail("admission_database_missing")
    try:
        with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """SELECT occurrence_id,owner_id,state,effect_unknown
                   FROM occurrences WHERE occurrence_id=?""",
                (occurrence_id,),
            ).fetchone()
    except sqlite3.Error as error:
        raise _fail("admission_read_failed") from error
    if row is None:
        raise _fail("occurrence_missing")
    result = dict(row)
    if result.get("owner_id") != OWNER_ID:
        raise _fail("occurrence_owner_mismatch")
    if result.get("state") not in {"claimed", "released"} or result.get("effect_unknown") != 1:
        raise _fail("occurrence_not_effect_unknown")
    return result


def _event_epoch(value: object) -> float:
    if not isinstance(value, str):
        raise _fail("runtime_event_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise _fail("runtime_event_timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise _fail("runtime_event_timestamp_invalid")
    return parsed.timestamp()


def _reporting_date(value: object) -> str:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        raise _fail("snapshot_reporting_date_invalid")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise _fail("snapshot_reporting_date_invalid") from error
    return value


def _event_date(value: object) -> str:
    """Return the Asia/Tokyo reporting date for a runtime timestamp."""
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(_event_epoch(value), timezone.utc).astimezone(
        ZoneInfo("Asia/Tokyo")
    ).strftime("%Y-%m-%d")


def _read_runtime_pair(state_dir: Path, occurrence_id: str, reporting_date: str) -> dict[str, Any]:
    path = state_dir / "events.jsonl"
    try:
        raw = _private_file(path, max_bytes=MAX_EVENT_BYTES, label="runtime_events")
    except ValueError as error:
        if str(error) in {"runtime_events_missing", "runtime_events_not_private"}:
            raise _fail("runtime_event_pair_missing") from error
        raise
    rows: list[dict[str, Any]] = []
    try:
        for line in raw.splitlines():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise _fail("runtime_event_invalid")
            rows.append(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _fail("runtime_event_invalid") from error

    run_id = occurrence_id[len(OWNER_ID) + 1 :]
    matching = [
        row
        for row in rows
        if row.get("occurrence_id") == occurrence_id
        and row.get("loop_id") == OWNER_ID
        and row.get("owner_id") == OWNER_ID
        and row.get("job_id") == OWNER_ID
        and row.get("run_id") == run_id
    ]
    if len(matching) != 2:
        raise _fail("runtime_event_pair_missing")
    starts = [
        row
        for row in matching
        if row.get("phase") == "execute"
        and row.get("status") == "running"
        and row.get("effect_status") == "started"
        and row.get("effect_class") == "message"
    ]
    terminals = [
        row
        for row in matching
        if row.get("phase") == "report"
        and row.get("status") == "pass"
        and row.get("effect_class") == "message"
        and row.get("exit_code") == 0
    ]
    if len(starts) != 1 or len(terminals) != 1:
        raise _fail("runtime_event_pair_missing")
    start, terminal = starts[0], terminals[0]
    start_epoch = _event_epoch(start.get("timestamp"))
    terminal_epoch = _event_epoch(terminal.get("timestamp"))
    if start_epoch > terminal_epoch:
        raise _fail("runtime_event_pair_order_invalid")
    if _event_date(start.get("timestamp")) != reporting_date or _event_date(
        terminal.get("timestamp")
    ) != reporting_date:
        raise _fail("runtime_event_period_mismatch")
    if start.get("release_sha") != terminal.get("release_sha"):
        raise _fail("runtime_event_release_mismatch")
    return {
        "start_event_id": start.get("event_id"),
        "terminal_event_id": terminal.get("event_id"),
        "terminal_timestamp": terminal.get("timestamp"),
        "release_sha": terminal.get("release_sha"),
    }


def _snapshot_values(
    snapshot: dict[str, Any],
) -> tuple[str, str | None, str | None, str, str]:
    if snapshot.get("schemaVersion") != 1 or snapshot.get("status") != "delivered":
        raise _fail("snapshot_not_delivered")
    reporting_date = _reporting_date(
        snapshot.get("reportingDate", snapshot.get("reporting_date"))
    )
    delivery = snapshot.get("delivery")
    if not isinstance(delivery, dict) or delivery.get("delivery") != "delivered":
        raise _fail("snapshot_delivery_not_delivered")
    provider_id = delivery.get("provider_message_id")
    if provider_id is None or isinstance(provider_id, bool) or not str(provider_id).strip():
        raise _fail("snapshot_provider_receipt_missing")
    digest = snapshot.get("digest")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise _fail("snapshot_digest_missing")
    message_sha256 = snapshot.get("message_sha256", snapshot.get("messageSha256"))
    if message_sha256 is not None and (
        not isinstance(message_sha256, str) or not SHA256.fullmatch(message_sha256)
    ):
        raise _fail("snapshot_message_hash_invalid")
    event_key = snapshot.get("event_key", snapshot.get("eventKey"))
    if event_key is not None and (
        not isinstance(event_key, str) or not EVENT_KEY.fullmatch(event_key)
    ):
        raise _fail("snapshot_event_key_invalid")
    return reporting_date, event_key, message_sha256, str(provider_id), digest


def _event_key_date(event_key: str, reporting_date: str) -> bool:
    return event_key.startswith("cfo:") and (
        event_key.endswith(f":{reporting_date}")
        or f":{reporting_date}:" in event_key
    )


def _outbox_proof(
    state_dir: Path,
    *,
    reporting_date: str,
    snapshot_event_key: str | None,
    snapshot_message_sha256: str | None,
    provider_message_id: str,
) -> dict[str, Any]:
    database = state_dir / "telegram-outbox.sqlite3"
    if not database.is_file() or database.is_symlink():
        raise _fail("telegram_outbox_missing")
    try:
        items = list_items(database)
    except (OSError, sqlite3.Error, ValueError) as error:
        raise _fail("telegram_outbox_read_failed") from error
    if snapshot_event_key is not None:
        candidates = [item for item in items if item.event_key == snapshot_event_key]
    else:
        candidates = [
            item for item in items if item.provider_message_id == provider_message_id
        ]
    if len(candidates) != 1:
        raise _fail("telegram_outbox_event_not_unique")
    item = candidates[0]
    if not _event_key_date(item.event_key, reporting_date):
        raise _fail("telegram_outbox_period_mismatch")
    if item.status != "delivered" or not item.provider_message_id or not item.delivered_at:
        raise _fail("provider_receipt_not_delivered")
    if not isinstance(item.message_sha256, str) or not SHA256.fullmatch(item.message_sha256):
        raise _fail("message_sha256_missing")
    if snapshot_message_sha256 is not None and item.message_sha256 != snapshot_message_sha256:
        raise _fail("message_sha256_mismatch")
    if item.provider_message_id != provider_message_id:
        raise _fail("provider_message_id_mismatch")
    for timestamp in (item.created_at, item.delivered_at):
        if timestamp is not None and _event_date(timestamp) != reporting_date:
            raise _fail("telegram_outbox_period_mismatch")
    return {
        "event_key": item.event_key,
        "message_sha256": item.message_sha256,
        "provider_message_id": item.provider_message_id,
        "delivered_at": item.delivered_at,
    }


def build_proof(*, state_dir: Path, admission_db: Path, occurrence_id: str) -> dict[str, Any]:
    occurrence = _read_admission(admission_db, occurrence_id)
    snapshot = _read_json(
        state_dir / "last-delivered-snapshot.json",
        max_bytes=MAX_SNAPSHOT_BYTES,
        label="snapshot",
    )
    (
        reporting_date,
        snapshot_event_key,
        snapshot_message_sha256,
        provider_message_id,
        snapshot_digest,
    ) = _snapshot_values(snapshot)
    runtime = _read_runtime_pair(state_dir, occurrence_id, reporting_date)
    outbox = _outbox_proof(
        state_dir,
        reporting_date=reporting_date,
        snapshot_event_key=snapshot_event_key,
        snapshot_message_sha256=snapshot_message_sha256,
        provider_message_id=provider_message_id,
    )
    evidence = {
        "event_key": outbox["event_key"],
        "reporting_date": reporting_date,
        "message_sha256": outbox["message_sha256"],
        "provider_message_id": outbox["provider_message_id"],
        "delivered_at": outbox["delivered_at"],
        "snapshot_digest": snapshot_digest,
        "terminal_event_id": runtime["terminal_event_id"],
    }
    digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    event_key_digest = hashlib.sha256(outbox["event_key"].encode("utf-8")).hexdigest()
    return {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "occurrence_state": occurrence["state"],
        "verified": True,
        "proof_type": "cfo_telegram_provider_receipt",
        "provider": "telegram",
        "provider_receipt_id": f"telegram:{outbox['provider_message_id']}",
        "official_readback_ref": f"telegram-outbox://event/{event_key_digest}/{digest}",
        "event_key_sha256": event_key_digest,
        "reporting_date": reporting_date,
        "message_sha256": outbox["message_sha256"],
        "provider_message_id": outbox["provider_message_id"],
        "terminal_event_id": runtime["terminal_event_id"],
    }


def reconcile(
    *,
    state_dir: Path,
    admission_db: Path,
    occurrence_id: str,
    resolve: bool = False,
) -> dict[str, Any]:
    proof = build_proof(
        state_dir=state_dir,
        admission_db=admission_db,
        occurrence_id=occurrence_id,
    )
    resolved = False
    if resolve:
        resolved = resolve_unknown_occurrence(
            OWNER_ID,
            occurrence_id,
            official_readback=lambda: proof,
            expected_state=proof["occurrence_state"],
        )
    return {
        **proof,
        "resolution_state": "RESOLVED" if resolved else "PROOF_READY",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("~/.local/state/life-manager/life-manager-cfo-hourly"),
    )
    parser.add_argument(
        "--admission-db",
        type=Path,
        default=Path("~/.local/state/life-manager/host-admission/resources/admission-v2.sqlite3"),
    )
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    occurrence_id = str(args.occurrence_id)
    try:
        result = reconcile(
            state_dir=args.state_dir.expanduser().resolve(),
            admission_db=args.admission_db.expanduser().resolve(),
            occurrence_id=occurrence_id,
            resolve=args.resolve,
        )
    except ValueError as error:
        print(
            json.dumps(
                {
                    "status": "inconclusive",
                    "owner_id": OWNER_ID,
                    "occurrence_id": occurrence_id,
                    "reason": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    except (OSError, RuntimeError, sqlite3.Error):
        print(
            json.dumps(
                {
                    "status": "inconclusive",
                    "owner_id": OWNER_ID,
                    "occurrence_id": occurrence_id,
                    "reason": "reconcile_read_failed",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
