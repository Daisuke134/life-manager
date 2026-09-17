#!/usr/bin/env python3
"""Check one mobile publish fence against exact provider proof without mutating state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any


ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
OCCURRENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PROVIDER_RECEIPT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
IDENTITY_FIELDS = (
    "schema_version", "kind", "runtime_run_id", "occurrence_id", "loop_id", "job_id",
    "effect_key", "product_id", "format_id", "form", "locale", "platform", "creative_id",
    "slot", "integration_ref", "account_id", "video_sha256", "caption_sha256",
    "media_sha256", "pack_sha256", "media_order_sha256",
)


def _inconclusive(owner_id: str, occurrence_id: str, reason: str) -> dict[str, str]:
    return {"status": "inconclusive", "owner_id": owner_id,
            "occurrence_id": occurrence_id, "reason": reason}


def _valid_identity(value: Any, owner_id: str, occurrence_id: str) -> bool:
    if not isinstance(value, dict) or set(value) - set(IDENTITY_FIELDS):
        return False
    if value.get("schema_version") != 1 or value.get("kind") != "life_manager_effect_identity":
        return False
    if value.get("loop_id") != owner_id or value.get("occurrence_id") != occurrence_id:
        return False
    if (not OCCURRENCE.fullmatch(occurrence_id)
            or not ID.fullmatch(str(value.get("runtime_run_id", "")))
            or not ID.fullmatch(str(value.get("job_id", "")))
            or not isinstance(value.get("effect_key"), str)
            or not ID.fullmatch(str(value.get("product_id", "")))
            or not ID.fullmatch(str(value.get("format_id", "")))
            or not ID.fullmatch(str(value.get("form", "")))
            or not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", str(value.get("locale", "")))
            or value.get("platform") not in {"instagram", "tiktok", "youtube"}
            or not ID.fullmatch(str(value.get("creative_id", "")))
            or not isinstance(value.get("slot"), str) or not value["slot"].strip()
            or not re.fullmatch(r"integration://postiz/[a-z]+/[A-Za-z0-9._:-]{1,200}", str(value.get("integration_ref", "")), re.IGNORECASE)
            or not re.fullmatch(r"@[A-Za-z0-9._-]{1,127}", str(value.get("account_id", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("caption_sha256", "")))):
        return False
    for key in ("video_sha256", "caption_sha256", "pack_sha256", "media_order_sha256"):
        if value.get(key) is not None and not re.fullmatch(r"[0-9a-f]{64}", str(value[key])):
            return False
    media = value.get("media_sha256")
    if media is not None and (not isinstance(media, list)
                              or not media or any(not re.fullmatch(r"[0-9a-f]{64}", str(x)) for x in media)):
        return False
    integration_match = re.fullmatch(
        r"integration://postiz/([a-z]+)/[A-Za-z0-9._:-]{1,200}",
        str(value["integration_ref"]), re.IGNORECASE,
    )
    if integration_match is None or integration_match.group(1).lower() != value["platform"]:
        return False
    video_key = re.fullmatch(
        r"marketing:video:([^:]+):(instagram|tiktok|youtube):([^:]+):([0-9a-f]{64}):([0-9a-f]{64})(?::([0-9a-f]{64}))?",
        str(value.get("effect_key", "")),
    )
    carousel_key = re.fullmatch(
        r"marketing:carousel:([^:]+):([^:]+):([0-9a-f]{64}):([0-9a-f]{64}):([0-9a-f]{64})(?::([0-9a-f]{64}))?",
        str(value.get("effect_key", "")),
    )
    if video_key:
        if (value["product_id"] != video_key.group(1)
                or value["platform"] != video_key.group(2)
                or value["creative_id"] != video_key.group(3)
                or value.get("video_sha256") != video_key.group(4)
                or value.get("caption_sha256") != video_key.group(5)
                or (video_key.group(6) is not None
                    and video_key.group(6) != hashlib.sha256(value["slot"].encode()).hexdigest())):
            return False
    elif carousel_key:
        if (value["product_id"] != carousel_key.group(1)
                or value["creative_id"] != carousel_key.group(2)
                or value.get("video_sha256") is not None
                or not isinstance(media, list) or len(media) != 6
                or value.get("pack_sha256") != carousel_key.group(3)
                or value.get("media_order_sha256") != carousel_key.group(4)
                or hashlib.sha256(json.dumps(media, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest() != carousel_key.group(4)
                or value.get("caption_sha256") != carousel_key.group(5)
                or (carousel_key.group(6) is not None
                    and carousel_key.group(6) != hashlib.sha256(value["slot"].encode()).hexdigest())):
            return False
    else:
        return False
    return True


def read_identity(path: Path, owner_id: str, occurrence_id: str) -> dict[str, Any] | None:
    """Read one private identity row without following symlinks."""
    try:
        info = path.lstat()
        if (not info.is_file() or info.st_uid != os.getuid() or info.st_nlink != 1
                or info.st_mode & 0o777 != 0o600):
            return None
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                rows = [json.loads(line) for line in handle.read(1024 * 1024 + 1).splitlines()]
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    matches = [row for row in rows if _valid_identity(row, owner_id, occurrence_id)]
    return matches[-1] if matches else None


def evaluate_proof(identity: dict[str, Any], proof: dict[str, Any]) -> dict[str, str]:
    owner_id = str(identity.get("loop_id", ""))
    occurrence_id = str(identity.get("occurrence_id", ""))
    readback = proof.get("provider_readback") if isinstance(proof, dict) else None
    content = readback.get("content") if isinstance(readback, dict) else None
    required_content = {
        key: identity.get(key)
        for key in ("video_sha256", "caption_sha256", "media_sha256", "pack_sha256", "media_order_sha256")
        if key in identity
    }
    if (not _valid_identity(identity, owner_id, occurrence_id)
            or not isinstance(proof, dict)
            or proof.get("owner_id") != owner_id
            or proof.get("occurrence_id") != occurrence_id
            or proof.get("verified") is not True
            or proof.get("proof_kind") != "postiz_official_readback"
            or not PROVIDER_RECEIPT.fullmatch(str(proof.get("provider_receipt_id", "")))
            or proof.get("identity") != identity):
        return _inconclusive(owner_id, occurrence_id, "provider_proof_identity_mismatch")
    if (not isinstance(readback, dict)
            or readback.get("provider") != "postiz"
            or readback.get("state") != "PUBLISHED"
            or readback.get("post_id") != proof["provider_receipt_id"]
            or readback.get("account_id") != identity.get("account_id")
            or readback.get("integration_ref") != identity.get("integration_ref")
            or not isinstance(content, dict)
            or any(content.get(key) != value for key, value in required_content.items())):
        return _inconclusive(owner_id, occurrence_id, "provider_readback_not_exact")
    return {"status": "ready", "owner_id": owner_id, "occurrence_id": occurrence_id}


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


def reconcile_proof(
    identity: dict[str, Any], proof: dict[str, Any], *, state: str | None,
    effect_unknown: int | None,
) -> dict[str, str]:
    result = evaluate_proof(identity, proof)
    if result["status"] != "ready":
        return result
    if state != "released" or effect_unknown != 1:
        return _inconclusive(
            result["owner_id"], result["occurrence_id"],
            "claimed_or_already_resolved",
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--admission-db", type=Path, default=Path.home() / ".local/state/life-manager/host-admission/resources/admission-v2.sqlite3")
    args = parser.parse_args(argv)
    if not ID.fullmatch(args.owner_id) or not OCCURRENCE.fullmatch(args.occurrence_id):
        parser.error("owner and occurrence IDs are invalid")
    identity = read_identity(args.identity, args.owner_id, args.occurrence_id)
    if identity is None:
        result = _inconclusive(args.owner_id, args.occurrence_id, "identity_missing_or_invalid")
    else:
        try:
            proof = json.loads(args.proof.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            proof = {}
        state, effect_unknown = _admission_state(args.admission_db, args.owner_id, args.occurrence_id)
        result = reconcile_proof(
            identity, proof, state=state, effect_unknown=effect_unknown,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
