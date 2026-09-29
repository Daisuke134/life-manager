#!/usr/bin/env python3
"""Reconcile one cross-venue Telegram effect from its durable provider receipt.

This adapter never sends Telegram messages and never retries the report. It only
closes an exact host fence when the occurrence is bound to a daily receipt and
the matching outbox row is durably marked delivered with a provider message id.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any


OWNER_ID = "investment-cross-venue-report"
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.host.resource_admission import resolve_unknown_occurrence  # noqa: E402
from telegram_outbox import list_items  # noqa: E402


def _read_occurrence(database: Path, occurrence_id: str) -> dict[str, Any]:
    if not occurrence_id.startswith(f"{OWNER_ID}:"):
        raise ValueError("occurrence_owner_mismatch")
    if not database.is_file():
        raise ValueError("admission_database_missing")
    try:
        with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
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
    if (
        result.get("owner_id") != OWNER_ID
        or result.get("state") not in {"claimed", "released"}
        or result.get("effect_unknown") != 1
    ):
        raise ValueError("occurrence_not_effect_unknown")
    return result


def _daily_receipt(state_dir: Path, occurrence_id: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for path in sorted(state_dir.glob("cross-venue-*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("occurrence_id") == occurrence_id:
            value["_path"] = path
            matches.append(value)
    if len(matches) != 1:
        raise ValueError("daily_receipt_occurrence_not_unique")
    receipt = matches[0]
    if receipt.get("status") not in {
        "delivery_pending", "delivery_uncertain", "delivered"
    }:
        raise ValueError("daily_receipt_not_delivery_candidate")
    event_key = receipt.get("event_key")
    if not isinstance(event_key, str) or not event_key:
        raise ValueError("daily_receipt_event_key_missing")
    return receipt


def _outbox_proof(state_dir: Path, event_key: str, receipt: dict[str, Any]):
    database = state_dir / "telegram-outbox.sqlite3"
    rows = [item for item in list_items(database) if item.event_key == event_key]
    if len(rows) != 1:
        raise ValueError("telegram_outbox_event_not_unique")
    item = rows[0]
    if item.status != "delivered" or not item.provider_message_id:
        raise ValueError("provider_receipt_not_delivered")
    receipt_message_id = receipt.get("provider_message_id")
    if receipt_message_id is not None and str(receipt_message_id) != item.provider_message_id:
        raise ValueError("provider_message_id_mismatch")
    return item


def build_proof(*, state_dir: Path, admission_db: Path, occurrence_id: str) -> dict[str, Any]:
    occurrence = _read_occurrence(admission_db, occurrence_id)
    receipt = _daily_receipt(state_dir, occurrence_id)
    item = _outbox_proof(state_dir, receipt["event_key"], receipt)
    provider_id = item.provider_message_id
    assert provider_id is not None
    evidence = {
        "event_key": item.event_key,
        "message_sha256": item.message_sha256,
        "provider_message_id": provider_id,
        "delivered_at": item.delivered_at,
    }
    digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_type": "telegram_provider_receipt",
        "provider": "telegram",
        "provider_receipt_id": f"telegram:{provider_id}",
        "official_readback_ref": f"telegram-outbox://{item.event_key}/{digest}",
        "provider_message_id": provider_id,
        "event_key": item.event_key,
        "message_sha256": item.message_sha256,
        "occurrence_state": occurrence["state"],
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


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
    receipt = {
        "schema_version": 1,
        "receipt_type": "INVESTMENT_CROSS_VENUE_TELEGRAM_RECONCILIATION",
        **proof,
        "resolution_state": "RESOLVED" if resolved else "PROOF_READY",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    path = state_dir / "reconciliation" / (
        occurrence_id.replace(":", "-", 1) + "-telegram.json"
    )
    _atomic_json(path, receipt)
    return {**receipt, "receipt_path": str(path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("~/.local/state/life-manager/investment-cross-venue"),
    )
    parser.add_argument(
        "--admission-db",
        type=Path,
        default=Path("~/.local/state/life-manager/host-admission/resources/admission-v2.sqlite3"),
    )
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    result = reconcile(
        state_dir=args.state_dir.expanduser().resolve(),
        admission_db=args.admission_db.expanduser().resolve(),
        occurrence_id=args.occurrence_id,
        resolve=args.resolve,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
