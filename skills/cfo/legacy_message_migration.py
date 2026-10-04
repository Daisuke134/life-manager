#!/usr/bin/env python3
"""One-time read-only migration proof for the retired CFO Telegram producer.

This adapter is intentionally not registered in the normal fence reconciler.
It accepts only the exact retired release semantics and can resolve only a
pre-effect occurrence whose message was already delivered before that run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUTBOX_ROOT = ROOT / "apps/life-manager/investment-core"
if str(OUTBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(OUTBOX_ROOT))

from runtime.host.resource_admission import resolve_pre_effect_occurrence  # noqa: E402
from telegram_outbox import list_items  # noqa: E402
from effect_reconcile import (  # noqa: E402
    SHA256,
    _event_date,
    _event_epoch,
    _private_file,
    _read_admission,
    _read_runtime_pair,
    _reporting_date,
)


OWNER_ID = "life-manager-cfo-hourly"
LEGACY_RELEASE_SHA = "86e447303b9c4f03edaa90244b80c9d4d214ac65"
PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_private_file(path, max_bytes=4 * 1024 * 1024, label=label))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label}_invalid") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label}_invalid")
    return value


def _event_key_date(event_key: str, reporting_date: str) -> bool:
    return event_key.startswith("cfo:") and event_key.endswith(f":{reporting_date}")


def _legacy_snapshot(state_dir: Path) -> dict[str, str]:
    snapshot = _read_json(state_dir / "last-delivered-snapshot.json", "legacy_snapshot")
    if snapshot.get("schemaVersion") != 1 or snapshot.get("status") != "delivered":
        raise ValueError("legacy_snapshot_not_delivered")
    reporting_date = _reporting_date(snapshot.get("reportingDate"))
    delivery = snapshot.get("delivery")
    if not isinstance(delivery, dict) or delivery.get("delivery") != "delivered":
        raise ValueError("legacy_snapshot_delivery_not_delivered")
    provider_message_id = delivery.get("provider_message_id")
    if not isinstance(provider_message_id, str) or not PROVIDER_ID.fullmatch(provider_message_id):
        raise ValueError("legacy_provider_message_id_invalid")
    delivered_at = snapshot.get("deliveredAt")
    if not isinstance(delivered_at, str):
        raise ValueError("legacy_snapshot_delivery_time_missing")
    if _event_date(delivered_at) != reporting_date:
        raise ValueError("legacy_snapshot_period_mismatch")
    return {
        "reporting_date": reporting_date,
        "provider_message_id": provider_message_id,
        "delivered_at": delivered_at,
    }


def _legacy_outbox(state_dir: Path, snapshot: dict[str, str]) -> dict[str, str]:
    database = state_dir / "telegram-outbox.sqlite3"
    if not database.is_file() or database.is_symlink():
        raise ValueError("legacy_outbox_missing")
    try:
        candidates = [
            item for item in list_items(database)
            if item.provider_message_id == snapshot["provider_message_id"]
        ]
    except (OSError, sqlite3.Error, ValueError) as error:
        raise ValueError("legacy_outbox_read_failed") from error
    if len(candidates) != 1:
        raise ValueError("legacy_outbox_not_unique")
    item = candidates[0]
    if not _event_key_date(item.event_key, snapshot["reporting_date"]):
        raise ValueError("legacy_outbox_period_mismatch")
    if item.status != "delivered" or item.provider_message_id != snapshot["provider_message_id"]:
        raise ValueError("legacy_outbox_not_delivered")
    if not isinstance(item.message_sha256, str) or not SHA256.fullmatch(item.message_sha256):
        raise ValueError("legacy_message_sha256_missing")
    if not item.delivered_at:
        raise ValueError("legacy_outbox_delivery_time_missing")
    if _event_date(item.delivered_at) != snapshot["reporting_date"]:
        raise ValueError("legacy_outbox_period_mismatch")
    return {
        "event_key": item.event_key,
        "message_sha256": item.message_sha256,
        "provider_message_id": item.provider_message_id,
        "delivered_at": item.delivered_at,
    }


def build_proof(*, state_dir: Path, admission_db: Path, occurrence_id: str) -> dict[str, Any]:
    occurrence = _read_admission(admission_db, occurrence_id)
    snapshot = _legacy_snapshot(state_dir)
    runtime = _read_runtime_pair(state_dir, occurrence_id, snapshot["reporting_date"])
    if runtime["release_sha"] != LEGACY_RELEASE_SHA:
        raise ValueError("legacy_release_not_allowed")
    outbox = _legacy_outbox(state_dir, snapshot)
    if _event_epoch(snapshot["delivered_at"]) != _event_epoch(outbox["delivered_at"]):
        raise ValueError("legacy_delivery_timestamp_mismatch")
    if _event_epoch(snapshot["delivered_at"]) >= _event_epoch(runtime["start_timestamp"]):
        raise ValueError("legacy_delivery_after_runtime_start")
    event_key_digest = hashlib.sha256(outbox["event_key"].encode("utf-8")).hexdigest()
    evidence_digest = hashlib.sha256(json.dumps({
        "event_key_sha256": event_key_digest,
        "message_sha256": outbox["message_sha256"],
        "provider_message_id": outbox["provider_message_id"],
        "snapshot_delivered_at": snapshot["delivered_at"],
        "outbox_delivered_at": outbox["delivered_at"],
        "terminal_event_id": runtime["terminal_event_id"],
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "occurrence_state": occurrence["state"],
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"lm-event://{OWNER_ID}/{runtime['run_id']}/{runtime['terminal_event_id']}",
        "event_key_sha256": event_key_digest,
        "reporting_date": snapshot["reporting_date"],
        "message_sha256": outbox["message_sha256"],
        "provider_message_id": outbox["provider_message_id"],
        "official_readback_ref": f"telegram-outbox://legacy-event/{event_key_digest}/{evidence_digest}",
    }


def reconcile(*, state_dir: Path, admission_db: Path, occurrence_id: str, resolve: bool = False) -> dict[str, Any]:
    proof = build_proof(state_dir=state_dir, admission_db=admission_db, occurrence_id=occurrence_id)
    resolved = False
    if resolve:
        resolved = resolve_pre_effect_occurrence(
            OWNER_ID,
            occurrence_id,
            pre_effect_readback=lambda: proof,
            expected_state=proof["occurrence_state"],
        )
    return {**proof, "resolution_state": "RESOLVED" if resolved else "PROOF_READY"}


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
            "reason": str(error) if isinstance(error, ValueError) else "legacy_read_failed",
        }, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
