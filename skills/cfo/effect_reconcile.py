#!/usr/bin/env python3
"""Reconcile one occurrence-bound current CFO Telegram result.

Read the current ``last-result-report.json`` or, when it has rotated away or
belongs to another occurrence, that occurrence's validated B7 readback archive.
Legacy ``last-delivered-snapshot.json`` evidence remains exclusive to the
separate one-time migration adapter.
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
EVENT_KEY = re.compile(r"^cfo-result:[A-Za-z0-9][A-Za-z0-9._:-]{0,1023}$")
PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
MAX_EVENT_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUTBOX_ROOT = ROOT / "apps/life-manager/investment-core"
if str(OUTBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(OUTBOX_ROOT))

from runtime.host.resource_admission import (  # noqa: E402
    resolve_pre_effect_occurrence,
    resolve_unknown_occurrence,
)
from telegram_outbox import list_items  # noqa: E402


def _fail(reason: str) -> ValueError:
    return ValueError(reason)


def _private_file(path: Path, *, max_bytes: int, label: str) -> bytes:
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


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_private_file(path, max_bytes=MAX_REPORT_BYTES, label=label))
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
    state = result.get("state")
    effect_unknown = result.get("effect_unknown")
    if not (
        (state in {"claimed", "released"} and effect_unknown == 1)
        or (state == "released" and effect_unknown == 0)
    ):
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
        raise _fail("reporting_date_invalid")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise _fail("reporting_date_invalid") from error
    return value


def _event_date(value: object) -> str:
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(_event_epoch(value), timezone.utc).astimezone(
        ZoneInfo("Asia/Tokyo")
    ).strftime("%Y-%m-%d")


def _read_runtime_pair(
    state_dir: Path,
    occurrence_id: str,
    reporting_date: str,
) -> dict[str, Any]:
    try:
        raw = _private_file(
            state_dir / "events.jsonl", max_bytes=MAX_EVENT_BYTES, label="runtime_events"
        )
    except ValueError as error:
        if str(error) in {"runtime_events_missing", "runtime_events_not_private"}:
            raise _fail("runtime_event_pair_missing") from error
        raise
    try:
        rows = [json.loads(line) for line in raw.splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _fail("runtime_event_invalid") from error
    if any(not isinstance(row, dict) for row in rows):
        raise _fail("runtime_event_invalid")
    run_id = occurrence_id[len(OWNER_ID) + 1 :]
    matching = [
        row for row in rows
        if row.get("occurrence_id") == occurrence_id
        and row.get("loop_id") == OWNER_ID
        and row.get("owner_id") == OWNER_ID
        and row.get("job_id") == OWNER_ID
        and row.get("run_id") == run_id
    ]
    if len(matching) != 2:
        raise _fail("runtime_event_pair_missing")
    starts = [
        row for row in matching
        if row.get("phase") == "execute"
        and row.get("status") == "running"
        and row.get("effect_status") == "started"
        and row.get("effect_class") == "message"
    ]
    terminals = [
        row for row in matching
        if row.get("phase") == "report"
        and row.get("effect_class") == "message"
        and (
            (row.get("status") == "pass" and row.get("exit_code") == 0)
            or (
                row.get("status") == "fail"
                and isinstance(row.get("exit_code"), int)
                and row.get("exit_code") != 0
                and row.get("effect_status") == "unknown"
            )
        )
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
        raise _fail("reporting_date_mismatch")
    if start.get("release_sha") != terminal.get("release_sha"):
        raise _fail("runtime_event_release_mismatch")
    return {
        "run_id": run_id,
        "start_timestamp": start["timestamp"],
        "terminal_timestamp": terminal["timestamp"],
        "terminal_status": terminal.get("status"),
        "terminal_exit_code": terminal.get("exit_code"),
        "terminal_effect_status": terminal.get("effect_status"),
        "terminal_event_id": terminal.get("event_id"),
        "release_sha": terminal.get("release_sha"),
    }


def _historical_b7_report(
    state_dir: Path, occurrence_id: str, *, missing_report_reason: str
) -> dict[str, Any]:
    if not OCCURRENCE.fullmatch(occurrence_id) or not occurrence_id.startswith(f"{OWNER_ID}:"):
        raise _fail("occurrence_invalid")
    snapshot_directory = state_dir / "b7-readbacks"
    try:
        directory_info = os.lstat(snapshot_directory)
    except FileNotFoundError as error:
        raise _fail(missing_report_reason) from error
    except OSError as error:
        raise _fail("b7_snapshot_directory_unreadable") from error
    if (stat.S_ISLNK(directory_info.st_mode) or not stat.S_ISDIR(directory_info.st_mode)
            or os.path.realpath(snapshot_directory) != str(snapshot_directory)):
        raise _fail("b7_snapshot_directory_invalid")
    snapshot_path = snapshot_directory / f"{occurrence_id}.json"
    if not os.path.lexists(snapshot_path):
        raise _fail(missing_report_reason)
    snapshot = _read_json(
        snapshot_path,
        label="b7_snapshot",
    )
    run_id = occurrence_id[len(OWNER_ID) + 1 :]
    period = snapshot.get("reportingPeriod")
    if (snapshot.get("schemaVersion") != 3 or snapshot.get("status") != "sent"
            or snapshot.get("ownerId") != OWNER_ID
            or snapshot.get("runId") != run_id
            or snapshot.get("occurrenceId") != occurrence_id
            or snapshot.get("channel") != "telegram"
            or not isinstance(period, dict)):
        raise _fail("b7_snapshot_identity_invalid")
    reporting_date = _reporting_date(period.get("reportingDate"))
    event_key = snapshot.get("eventKey")
    if not isinstance(event_key, str) or not EVENT_KEY.fullmatch(event_key):
        raise _fail("event_key_invalid")
    if not _event_key_date(event_key, reporting_date):
        raise _fail("reporting_date_mismatch")
    resolution_kind = snapshot.get("resolutionKind")
    if resolution_kind not in {"sent", "duplicate"}:
        raise _fail("resolution_kind_invalid")
    message_sha256 = snapshot.get("messageSha256")
    if not isinstance(message_sha256, str) or not SHA256.fullmatch(message_sha256):
        raise _fail("message_sha256_invalid")
    provider_message_id = snapshot.get("providerMessageId")
    if not isinstance(provider_message_id, str) or not PROVIDER_ID.fullmatch(provider_message_id):
        raise _fail("provider_message_id_invalid")
    _event_epoch(snapshot.get("sentAt"))
    release_sha = snapshot.get("releaseSha")
    if not isinstance(release_sha, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", release_sha):
        raise _fail("release_sha_invalid")
    return {
        "resolution_kind": resolution_kind,
        "status": "sent",
        "reporting_date": reporting_date,
        "event_key": event_key,
        "message_sha256": message_sha256,
        "provider_message_id": provider_message_id,
        "release_sha": release_sha,
        "report_source": "b7_occurrence_snapshot",
    }


def _current_report(state_dir: Path, occurrence_id: str) -> dict[str, Any]:
    try:
        report = _read_json(state_dir / "last-result-report.json", label="result_report")
    except ValueError as error:
        if str(error) != "result_report_missing":
            raise
        return _historical_b7_report(
            state_dir, occurrence_id, missing_report_reason="result_report_missing"
        )
    if report.get("occurrenceId") != occurrence_id:
        return _historical_b7_report(
            state_dir, occurrence_id, missing_report_reason="occurrence_mismatch"
        )
    if report.get("status") not in {"pending", "sent"}:
        raise _fail("result_report_not_sent")
    if report.get("channel") != "telegram":
        raise _fail("channel_not_telegram")
    resolution_kind = report.get("resolutionKind")
    if report.get("status") == "sent" and resolution_kind not in {"sent", "duplicate"}:
        raise _fail("resolution_kind_invalid")
    if report.get("status") == "pending" and resolution_kind is not None:
        raise _fail("resolution_kind_invalid")
    reporting_date = _reporting_date(report.get("reportingDate"))
    event_key = report.get("eventKey")
    if not isinstance(event_key, str) or not EVENT_KEY.fullmatch(event_key):
        raise _fail("event_key_invalid")
    if not _event_key_date(event_key, reporting_date):
        raise _fail("reporting_date_mismatch")
    message_sha256 = report.get("messageSha256")
    if not isinstance(message_sha256, str) or not SHA256.fullmatch(message_sha256):
        raise _fail("message_sha256_invalid")
    provider_message_id = report.get("providerMessageId")
    if provider_message_id is not None and (
        not isinstance(provider_message_id, str) or not PROVIDER_ID.fullmatch(provider_message_id)
    ):
        raise _fail("provider_message_id_invalid")
    return {
        "resolution_kind": resolution_kind,
        "status": report["status"],
        "reporting_date": reporting_date,
        "event_key": event_key,
        "message_sha256": message_sha256,
        "provider_message_id": provider_message_id,
        "report_source": "last_result_report",
    }


def _event_key_date(event_key: str, reporting_date: str) -> bool:
    return event_key.startswith("cfo-result:") and (
        event_key.endswith(f":{reporting_date}")
        or f":{reporting_date}:" in event_key
    )


def _outbox_proof(state_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    database = state_dir / "telegram-outbox.sqlite3"
    if not database.is_file() or database.is_symlink():
        raise _fail("telegram_outbox_missing")
    try:
        items = [item for item in list_items(database) if item.event_key == report["event_key"]]
    except (OSError, sqlite3.Error, ValueError) as error:
        raise _fail("telegram_outbox_read_failed") from error
    if len(items) != 1:
        raise _fail("telegram_outbox_event_not_unique")
    item = items[0]
    if not _event_key_date(item.event_key, report["reporting_date"]):
        raise _fail("reporting_date_mismatch")
    if item.status != "delivered" or not item.provider_message_id or not item.delivered_at:
        raise _fail("provider_receipt_not_delivered")
    if not isinstance(item.message_sha256, str) or not SHA256.fullmatch(item.message_sha256):
        raise _fail("message_sha256_missing")
    if item.message_sha256 != report["message_sha256"]:
        raise _fail("message_sha256_mismatch")
    expected_provider_id = report.get("provider_message_id")
    if expected_provider_id is not None and item.provider_message_id != expected_provider_id:
        raise _fail("provider_message_id_mismatch")
    for timestamp in (item.created_at, item.delivered_at):
        if timestamp is not None and _event_date(timestamp) != report["reporting_date"]:
            raise _fail("reporting_date_mismatch")
    return {
        "message_sha256": item.message_sha256,
        "provider_message_id": item.provider_message_id,
        "delivered_at": item.delivered_at,
    }


def _base_proof(report: dict[str, Any], runtime: dict[str, Any], outbox: dict[str, Any]) -> dict[str, Any]:
    event_key_digest = hashlib.sha256(report["event_key"].encode("utf-8")).hexdigest()
    evidence_digest = hashlib.sha256(json.dumps({
        "event_key_sha256": event_key_digest,
        "reporting_date": report["reporting_date"],
        "message_sha256": outbox["message_sha256"],
        "provider_message_id": outbox["provider_message_id"],
        "delivered_at": outbox["delivered_at"],
        "terminal_event_id": runtime["terminal_event_id"],
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "owner_id": OWNER_ID,
        "occurrence_id": report.get("occurrence_id"),
        "reporting_date": report["reporting_date"],
        "resolution_kind": report["resolution_kind"],
        "report_source": report.get("report_source"),
        "admission_state": report.get("admission_state"),
        "admission_effect_unknown": report.get("admission_effect_unknown"),
        "event_key_sha256": event_key_digest,
        "message_sha256": outbox["message_sha256"],
        "provider_message_id": outbox["provider_message_id"],
        "runtime_start_timestamp": runtime["start_timestamp"],
        "runtime_terminal_timestamp": runtime["terminal_timestamp"],
        "terminal_event_id": runtime["terminal_event_id"],
        "official_readback_ref": f"telegram-outbox://event/{event_key_digest}/{evidence_digest}",
    }


def build_proof(*, state_dir: Path, admission_db: Path, occurrence_id: str) -> dict[str, Any]:
    occurrence = _read_admission(admission_db, occurrence_id)
    report = _current_report(state_dir, occurrence_id)
    report["occurrence_id"] = occurrence_id
    report["admission_state"] = occurrence["state"]
    report["admission_effect_unknown"] = bool(occurrence["effect_unknown"])
    runtime = _read_runtime_pair(state_dir, occurrence_id, report["reporting_date"])
    if report.get("release_sha") not in {None, runtime["release_sha"]}:
        raise _fail("runtime_event_release_mismatch")
    outbox = _outbox_proof(state_dir, report)
    if report["status"] == "pending":
        if not (
            runtime["terminal_status"] == "fail"
            and runtime["terminal_exit_code"] != 0
            and runtime["terminal_effect_status"] == "unknown"
        ):
            raise _fail("pending_runtime_terminal_invalid")
        report["resolution_kind"] = "receipt_recovered"
    elif not (
        (runtime["terminal_status"] == "pass" and runtime["terminal_exit_code"] == 0)
        or (
            runtime["terminal_status"] == "fail"
            and runtime["terminal_exit_code"] != 0
            and runtime["terminal_effect_status"] == "unknown"
        )
    ):
        raise _fail("current_runtime_terminal_invalid")
    if report["resolution_kind"] == "duplicate":
        if _event_epoch(outbox["delivered_at"]) >= _event_epoch(runtime["start_timestamp"]):
            raise _fail("duplicate_delivery_after_runtime_start")
        proof = _base_proof(report, runtime, outbox)
        proof.update({
            "occurrence_state": occurrence["state"],
            "verified": True,
            "proof_type": "pre_effect",
            "evidence_ref": f"lm-event://{OWNER_ID}/{runtime['run_id']}/{runtime['terminal_event_id']}",
        })
        return proof
    delivered_epoch = _event_epoch(outbox["delivered_at"])
    if delivered_epoch < _event_epoch(runtime["start_timestamp"]):
        raise _fail("sent_delivery_before_runtime_start")
    if delivered_epoch > _event_epoch(runtime["terminal_timestamp"]):
        raise _fail("sent_delivery_after_runtime_terminal")
    proof = _base_proof(report, runtime, outbox)
    proof.update({
        "occurrence_state": occurrence["state"],
        "verified": True,
        "proof_type": "cfo_result_telegram_provider_receipt",
        "provider": "telegram",
        "provider_receipt_id": f"telegram:{outbox['provider_message_id']}",
    })
    return proof


def reconcile(
    *, state_dir: Path, admission_db: Path, occurrence_id: str, resolve: bool = False
) -> dict[str, Any]:
    proof = build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence_id)
    resolved = False
    if resolve:
        if proof["admission_effect_unknown"] is False:
            proof["resolution_state"] = "PROOF_READY_ALREADY_RELEASED"
            return proof
        if proof["resolution_kind"] == "duplicate":
            resolved = resolve_pre_effect_occurrence(
                OWNER_ID,
                occurrence_id,
                pre_effect_readback=lambda: proof,
                expected_state=proof["occurrence_state"],
            )
        else:
            resolved = resolve_unknown_occurrence(
                OWNER_ID,
                occurrence_id,
                official_readback=lambda: proof,
                expected_state=proof["occurrence_state"],
            )
    proof["resolution_state"] = "RESOLVED" if resolved else "PROOF_READY"
    return proof


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path("~/.local/state/life-manager/life-manager-cfo-hourly"))
    parser.add_argument("--admission-db", type=Path, default=Path("~/.local/state/life-manager/host-admission/resources/admission-v2.sqlite3"))
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reconcile(
            state_dir=args.state_dir.expanduser().resolve(),
            admission_db=args.admission_db.expanduser().resolve(),
            occurrence_id=str(args.occurrence_id),
            resolve=args.resolve,
        )
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
        print(json.dumps({
            "status": "inconclusive",
            "owner_id": OWNER_ID,
            "occurrence_id": str(args.occurrence_id),
            "reason": str(error) if isinstance(error, ValueError) else "reconcile_read_failed",
        }, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
