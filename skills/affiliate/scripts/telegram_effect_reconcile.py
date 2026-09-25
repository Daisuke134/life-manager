#!/usr/bin/env python3
"""Reconcile one Affiliate Telegram effect from an exact official readback.

The local Telegram sender returns a provider message id, but an id alone is not
an effect proof: a stale or cross-chat id can be accidentally bound to the
wrong report.  This adapter requires the official message body hash, chat,
sender and timestamp to match the exact outbox event before it can release a
fenced admission occurrence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


OWNER_ID = "affiliate-loop"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_READBACK_WINDOW_SECONDS = 15 * 60


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    result: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("row_not_object")
        result.append(value)
    return result


def _epoch(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError as error:
            raise ValueError("timestamp_invalid") from error
    raise ValueError("timestamp_invalid")


def _read_occurrence(database: Path, occurrence_id: str) -> dict[str, Any]:
    if not occurrence_id.startswith(f"{OWNER_ID}:"):
        raise ValueError("occurrence_owner_mismatch")
    if not database.is_file():
        raise ValueError("admission_database_missing")
    try:
        uri = f"{database.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """SELECT occurrence_id,owner_id,state,effect_unknown
                     FROM occurrences WHERE occurrence_id=?""",
                (occurrence_id,),
            ).fetchone()
    except sqlite3.Error as error:
        raise ValueError("admission_read_failed") from error
    if row is None:
        raise ValueError("occurrence_missing")
    result = dict(row)
    if (result.get("owner_id") != OWNER_ID
            or result.get("state") not in {"claimed", "released"}
            or result.get("effect_unknown") != 1):
        raise ValueError("occurrence_not_effect_unknown")
    return result


def _outbox_event(state_root: Path, telegram_event_uuid: str) -> dict[str, Any]:
    matches = [
        row for row in _rows(state_root / "telegram-outbox.jsonl")
        if row.get("event_uuid") == telegram_event_uuid
    ]
    if len(matches) != 1:
        raise ValueError("telegram_outbox_event_not_unique")
    event = matches[0]
    body = event.get("body")
    if not isinstance(body, str) or not body:
        raise ValueError("telegram_outbox_body_missing")
    if event.get("created_at") is None:
        raise ValueError("telegram_outbox_created_at_missing")
    event["body_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return event


def _sent_row(state_root: Path, telegram_event_uuid: str) -> dict[str, Any] | None:
    rows = [
        row for row in _rows(state_root / "telegram-sent.jsonl")
        if row.get("event_uuid") == telegram_event_uuid
    ]
    if len(rows) > 1:
        raise ValueError("telegram_sent_event_not_unique")
    return rows[0] if rows else None


def _readback_identity(readback: Mapping[str, Any]) -> dict[str, str]:
    if readback.get("verified") is not True:
        raise ValueError("official_readback_not_verified")
    if readback.get("provider") != "telegram":
        raise ValueError("official_readback_provider_mismatch")
    chat_id = readback.get("chat_id")
    message_id = readback.get("message_id")
    sender_id = readback.get("sender_id")
    date = readback.get("date")
    body_sha256 = readback.get("text_sha256")
    if not isinstance(chat_id, str) or not chat_id.strip():
        raise ValueError("official_chat_missing")
    if message_id is None or not str(message_id).strip():
        raise ValueError("official_message_id_missing")
    if sender_id is None or not str(sender_id).strip():
        raise ValueError("official_sender_missing")
    if not isinstance(date, str) or not date.strip():
        raise ValueError("official_date_missing")
    if not isinstance(body_sha256, str) or not _SHA256.fullmatch(body_sha256):
        raise ValueError("official_body_hash_invalid")
    _epoch(date)
    return {
        "chat_id": chat_id.strip(),
        "message_id": str(message_id).strip(),
        "sender_id": str(sender_id).strip(),
        "date": date,
        "body_sha256": body_sha256,
    }


def build_proof(*, state_root: Path, database: Path, occurrence_id: str,
                telegram_event_uuid: str,
                readback: Mapping[str, Any]) -> dict[str, Any]:
    """Build a provider proof without changing the admission ledger."""
    occurrence = _read_occurrence(database, occurrence_id)
    event = _outbox_event(state_root, telegram_event_uuid)
    identity = _readback_identity(readback)
    if identity["body_sha256"] != event["body_sha256"]:
        raise ValueError("body_hash_mismatch")
    if abs(_epoch(identity["date"]) - _epoch(event["created_at"])) > _READBACK_WINDOW_SECONDS:
        raise ValueError("readback_time_outside_window")
    sent = _sent_row(state_root, telegram_event_uuid)
    local_message_id = str(sent["message_id"]).strip() if sent and sent.get("message_id") is not None else None
    canonical_readback = json.dumps(dict(readback), sort_keys=True,
                                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "telegram_event_uuid": telegram_event_uuid,
        "verified": True,
        "proof_type": "official_telegram_body_readback",
        "provider_receipt_id": f"telegram:{identity['chat_id']}:{identity['message_id']}",
        "official_readback_ref": "telegram-readback://" + hashlib.sha256(canonical_readback).hexdigest(),
        "official_chat_id": identity["chat_id"],
        "official_message_id": identity["message_id"],
        "official_sender_id": identity["sender_id"],
        "official_date": identity["date"],
        "body_sha256": event["body_sha256"],
        "local_provider_message_id": local_message_id,
        "official_provider_message_id": identity["message_id"],
        "provider_message_id_mismatch": (
            local_message_id is not None and local_message_id != identity["message_id"]
        ),
        "occurrence_state": occurrence["state"],
    }


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def reconcile(*, state_root: Path, database: Path, occurrence_id: str,
              telegram_event_uuid: str, readback: Mapping[str, Any],
              resolve: bool = False) -> dict[str, Any]:
    proof = build_proof(
        state_root=state_root, database=database,
        occurrence_id=occurrence_id, telegram_event_uuid=telegram_event_uuid,
        readback=readback,
    )
    resolved = False
    if resolve:
        from runtime.host.resource_admission import resolve_unknown_occurrence

        resolved = resolve_unknown_occurrence(
            OWNER_ID, occurrence_id,
            official_readback=lambda: proof,
            expected_state=proof["occurrence_state"],
        )
    receipt = {
        "schema_version": 1,
        "receipt_type": "AFFILIATE_TELEGRAM_EFFECT_RECONCILIATION",
        **proof,
        "resolution_state": "RESOLVED" if resolved else "PROOF_READY",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = state_root / "reconciliation" / (
        occurrence_id.replace(":", "-", 1) + "-telegram.json"
    )
    _atomic_json(receipt_path, receipt)
    return {**receipt, "receipt_path": str(receipt_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=Path("~/.local/state/life-manager/affiliate"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--telegram-event", required=True)
    parser.add_argument("--readback", type=Path, required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    database = args.database.expanduser().resolve()
    readback = json.loads(args.readback.expanduser().read_text(encoding="utf-8"))
    if not isinstance(readback, dict):
        raise SystemExit("official readback must be a JSON object")
    result = reconcile(
        state_root=state_root, database=database,
        occurrence_id=args.occurrence, telegram_event_uuid=args.telegram_event,
        readback=readback, resolve=args.resolve,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["resolution_state"] in {"PROOF_READY", "RESOLVED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
