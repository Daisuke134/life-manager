#!/usr/bin/env python3
"""Read-only exact Telegram readback for one CFO message occurrence."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


OWNER_IDS = {"life-manager-cfo-hourly", "life-manager-financial-report"}
OCCURRENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
CHAT = re.compile(r"^-?[0-9]{3,32}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _inconclusive(owner_id: str, occurrence_id: str, reason: str) -> dict[str, Any]:
    return {"status": "inconclusive", "owner_id": owner_id,
            "occurrence_id": occurrence_id, "reason": reason}


def _valid_snapshot(snapshot: Any, owner_id: str, occurrence_id: str) -> bool:
    if not isinstance(snapshot, dict):
        return False
    delivery = snapshot.get("delivery")
    return (
        snapshot.get("schemaVersion") == 1
        and snapshot.get("status") == "delivered"
        and snapshot.get("occurrence_id") == occurrence_id
        and OCCURRENCE.fullmatch(occurrence_id) is not None
        and owner_id in OWNER_IDS
        and isinstance(delivery, dict)
        and delivery.get("delivery") == "delivered"
        and IDENTIFIER.fullmatch(str(delivery.get("provider_message_id", ""))) is not None
        and SHA256.fullmatch(str(snapshot.get("message_sha256", ""))) is not None
    )


def build_proof(
    snapshot: dict[str, Any], provider_readback: dict[str, Any], *,
    owner_id: str, occurrence_id: str, expected_chat_id: str,
) -> dict[str, Any]:
    if not _valid_snapshot(snapshot, owner_id, occurrence_id):
        return _inconclusive(owner_id, occurrence_id, "snapshot_identity_mismatch")
    if not isinstance(provider_readback, dict) or provider_readback.get("provider") != "telegram":
        return _inconclusive(owner_id, occurrence_id, "telegram_identity_mismatch")
    delivery = snapshot["delivery"]
    if (
        provider_readback.get("state") != "delivered"
        or provider_readback.get("chat_id") != expected_chat_id
        or not CHAT.fullmatch(expected_chat_id)
        or provider_readback.get("message_id") != delivery["provider_message_id"]
    ):
        return _inconclusive(owner_id, occurrence_id, "telegram_identity_mismatch")
    if provider_readback.get("body_sha256") != snapshot["message_sha256"]:
        return _inconclusive(owner_id, occurrence_id, "telegram_body_mismatch")
    message_id = str(delivery["provider_message_id"])
    return {
        "status": "ready",
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_kind": "telegram_official_readback",
        "provider_receipt_id": message_id,
        "official_readback_ref": f"telegram://{expected_chat_id}/messages/{message_id}",
        "provider_readback": provider_readback,
    }


def _read_private_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _admission_state(database: Path, owner_id: str, occurrence_id: str) -> tuple[str | None, int | None]:
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT state,effect_unknown FROM occurrences WHERE owner_id=? AND occurrence_id=?",
                (owner_id, occurrence_id),
            ).fetchone()
    except sqlite3.Error:
        return None, None
    return (row[0], int(row[1])) if row else (None, None)


def reconcile(
    *, snapshot: Path, proof: Path, admission_db: Path, owner_id: str,
    occurrence_id: str, expected_chat_id: str,
) -> dict[str, Any]:
    state, effect_unknown = _admission_state(admission_db, owner_id, occurrence_id)
    if state not in {"claimed", "released"} or effect_unknown != 1:
        return _inconclusive(owner_id, occurrence_id, "claimed_or_already_resolved")
    snapshot_value = _read_private_json(snapshot)
    proof_value = _read_private_json(proof)
    if snapshot_value is None or proof_value is None:
        return _inconclusive(owner_id, occurrence_id, "private_receipt_unavailable")
    return build_proof(snapshot_value, proof_value, owner_id=owner_id,
                       occurrence_id=occurrence_id, expected_chat_id=expected_chat_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--admission-db", type=Path,
                        default=Path.home() / ".local/state/life-manager/host-admission/resources/admission-v2.sqlite3")
    args = parser.parse_args(argv)
    if (args.owner_id not in OWNER_IDS or not OCCURRENCE.fullmatch(args.occurrence_id)
            or not CHAT.fullmatch(args.chat_id)):
        parser.error("owner, occurrence and chat IDs are invalid")
    result = reconcile(snapshot=args.snapshot, proof=args.proof,
                       admission_db=args.admission_db, owner_id=args.owner_id,
                       occurrence_id=args.occurrence_id, expected_chat_id=args.chat_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
