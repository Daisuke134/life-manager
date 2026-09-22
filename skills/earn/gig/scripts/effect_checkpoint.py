#!/usr/bin/env python3
"""Append a model-decided external effect to a durable project ledger."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from pathlib import Path


REQUIRED = ("effect_key", "target", "payload_sha256", "official_receipt_url",
            "exact_readback", "quality_status", "qualification_sources", "semantic_contract_sha256")

_NO_POST_MARKERS = (
    "no posted content", "no posted videos", "no posts", "without posted content",
    "投稿なし", "投稿がなく", "投稿がない", "コンテンツはありません", "まだ動画はありません",
)
_POST_PROOF_MARKERS = (
    "visible posted content", "visible posted video", "posted videos are visible",
    "投稿を確認", "投稿動画を確認", "投稿コンテンツを確認",
)


def _same_json(left: object, right: object) -> bool:
    encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return encode(left) == encode(right)


def prepare_checkpoint(value: object) -> object:
    """Copy equivalent verified fields into the flat durable-ledger contract."""
    if not isinstance(value, dict):
        return value
    prepared = dict(value)
    official = value.get("official_readback")
    official = official if isinstance(official, dict) else {}
    missing = object()
    aliases = {
        "payload_sha256": value["message_sha256"] if "message_sha256" in value else missing,
        "official_receipt_url": official["official_url"] if "official_url" in official else missing,
        "exact_readback": official["exact_readback"] if "exact_readback" in official else missing,
    }
    for field, alias in aliases.items():
        if field in value and alias is not missing and not _same_json(value[field], alias):
            raise ValueError(f"conflicting checkpoint field: {field}")
        if field not in prepared and alias is not missing:
            prepared[field] = alias
    return prepared


def bind_current_cycle(root: Path, value: object) -> object:
    """Bind a receipt to the active paid cycle without trusting model repetition."""
    if not isinstance(value, dict):
        return value
    intent_path = root / "delivery" / "paid-remote-intent.json"
    if intent_path.is_symlink() or not intent_path.is_file():
        return value
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    if not isinstance(intent, dict):
        raise ValueError("invalid paid intent")
    prepared = dict(value)
    cycle = {
        "feedback_sha256": intent.get("buyer_feedback_sha256") or intent.get("feedback_sha256"),
        "requirements_sha256": intent.get("requirements_sha256"),
        "semantic_contract_sha256": intent.get("semantic_contract_sha256"),
    }
    if prepared.get("classification_revision") is True:
        cycle.pop("semantic_contract_sha256")
    for field, expected in cycle.items():
        if expected is None:
            continue
        if field in prepared and not _same_json(prepared[field], expected):
            raise ValueError(f"conflicting checkpoint cycle field: {field}")
        prepared[field] = expected
    return prepared


def valid_checkpoint(value: object) -> bool:
    if not isinstance(value, dict) or any(key not in value for key in REQUIRED):
        return False
    text_keys = ("effect_key", "target", "payload_sha256", "official_receipt_url",
                 "semantic_contract_sha256")
    if any(not isinstance(value[key], str) or not value[key].strip() for key in text_keys):
        return False
    if any(len(value[key]) != 64 or any(char not in "0123456789abcdef" for char in value[key])
           for key in ("payload_sha256", "semantic_contract_sha256")):
        return False
    sources = value["qualification_sources"]
    return (
        value["exact_readback"] is True
        and isinstance(value["quality_status"], str)
        and value["quality_status"] in {"qualified", "qualification", "invalid"}
        and isinstance(sources, list)
        and all(isinstance(source, str) and source.strip() for source in sources)
    )


def _row_text(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True).lower()


def _recipient_handle(row: dict) -> str:
    outcome = row.get("business_outcome")
    candidates = [
        row.get("candidate_handle"),
        outcome.get("recipient_handle") if isinstance(outcome, dict) else None,
    ]
    key = str(row.get("effect_key") or "")
    if key.startswith("tiktok:dm:") or key.startswith("google-sheets:append-readback:"):
        candidates.append(key.rsplit(":", 1)[-1])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().lower().lstrip("@")
    return ""


def _has_positive_post_proof(row: dict) -> bool:
    text = _row_text(row)
    negated = (
        "no visible posted", "not visible posted", "could not be confirmed",
        "did not confirm", "unable to confirm", "確認できな", "確認されな", "投稿なし",
    )
    return (not any(marker in text for marker in negated)
            and any(marker in text for marker in _POST_PROOF_MARKERS))


def _reconcile_tiktok_recipient_counts_unlocked(ledger: Path) -> list[str]:
    if ledger.is_symlink() or not ledger.is_file():
        return []
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    effective: dict[str, dict] = {}
    empty_profile_handles: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("effect_key") or "")
        if key:
            effective[key] = row
        if row.get("quality_status") == "invalid":
            claims = row.get("claim_to_source_map")
            claims = claims if isinstance(claims, list) else []
            for claim in claims:
                claim_text = str(claim.get("claim") or "").lower() if isinstance(claim, dict) else ""
                if any(marker in claim_text for marker in _NO_POST_MARKERS):
                    claim_handles = set(re.findall(r"@([a-z0-9._]+)", claim_text))
                    empty_profile_handles.update(claim_handles)
                    if not claim_handles and _recipient_handle(row):
                        empty_profile_handles.add(_recipient_handle(row))
            text = _row_text(row)
            handle = _recipient_handle(row)
            mentioned = set(re.findall(r"@([a-z0-9._]+)", text))
            if (not claims and handle and mentioned == {handle}
                    and any(marker in text for marker in _NO_POST_MARKERS)):
                empty_profile_handles.add(handle)

    revisions: list[dict] = []
    counted_recipient_keys: dict[str, str] = {}
    paired_tiktok_handles = {
        _recipient_handle(row) for key, row in effective.items()
        if key.startswith("tiktok:dm:") and _recipient_handle(row)
    }
    for key, row in effective.items():
        if row.get("counts_toward_50") is not True:
            continue
        reason = ""
        handle = _recipient_handle(row)
        if ((key.startswith("google-sheets:append-readback:")
             or row.get("record_type") == "google_sheets_append")
                and handle in paired_tiktok_handles):
            reason = "Bookkeeping receipts support a recipient send but never count as another recipient."
        elif key.startswith("tiktok:dm:"):
            if row.get("quality_status") != "qualified":
                reason = "Only a fully qualified recipient DM can increment the campaign total."
            elif (handle in empty_profile_handles
                    and not _has_positive_post_proof(row)):
                reason = ("Earlier official profile evidence shows no posted content, and this DM row "
                          "does not contain newer positive posted-content proof.")
            elif handle and handle in counted_recipient_keys:
                reason = ("This recipient already has a counted TikTok DM receipt; a recipient can "
                          "increment the campaign total only once.")
            elif handle:
                counted_recipient_keys[handle] = key
        if not reason:
            continue
        revision = dict(row)
        revision.update({
            "classification_revision": True,
            "record_type": "classification_revision",
            "counts_toward_50": False,
            "revision_reason": reason,
        })
        if key.startswith("tiktok:dm:") and "Earlier official" in reason:
            revision["quality_status"] = "invalid"
        revisions.append(revision)

    if revisions:
        with ledger.open("a", encoding="utf-8") as handle:
            for revision in revisions:
                handle.write(json.dumps(revision, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return [str(row["effect_key"]) for row in revisions]


def reconcile_tiktok_recipient_counts(ledger: Path) -> list[str]:
    """Append deterministic, idempotent recipient-count revisions under a file lock."""
    lock = ledger.with_suffix(ledger.suffix + ".reconcile.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            return _reconcile_tiktok_recipient_counts_unlocked(ledger)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def tiktok_verified_unique_count(ledger: Path) -> int | None:
    """Return the audited baseline plus later effective unique counted recipients."""
    if ledger.is_symlink() or not ledger.is_file():
        return None
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    anchor_index, baseline = -1, None
    effective: dict[str, dict] = {}
    first_index: dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        campaign = (row.get("observed_state") or {}).get("campaign")
        audit = campaign.get("ledger_audit") if isinstance(campaign, dict) else None
        value = audit.get("verified_effective_total") if isinstance(audit, dict) else None
        key = str(row.get("effect_key") or "")
        if (baseline is None and key.startswith("tiktok:effective-ledger-audit:")
                and row.get("quality_status") == "invalid"
                and isinstance(value, int) and value >= 0):
            anchor_index, baseline = index, value
        if key:
            effective[key] = row
            first_index.setdefault(key, index)
    if baseline is None:
        return None
    sheet_handles = {
        _recipient_handle(row)
        for key, row in effective.items()
        if (first_index[key] > anchor_index
            and key.startswith("google-sheets:append-readback:")
            and row.get("exact_readback") is True and row.get("quality_status") == "qualified"
            and _recipient_handle(row))
    }
    handles = set()
    for key, row in effective.items():
        handle = _recipient_handle(row)
        if (first_index[key] > anchor_index and key.startswith("tiktok:dm:")
                and row.get("counts_toward_50") is True
                and row.get("quality_status") == "qualified"
                and handle in sheet_handles):
            handles.add(handle)
    return baseline + len(handles)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--effect-json", required=True, type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    source = args.effect_json.resolve()
    if root not in source.parents or source.is_symlink() or not source.is_file():
        raise SystemExit("effect JSON must be a regular project-owned file")
    unbound_value = prepare_checkpoint(json.loads(source.read_text(encoding="utf-8")))
    value = bind_current_cycle(root, unbound_value)
    if not valid_checkpoint(value):
        raise SystemExit("invalid effect checkpoint")
    ledger = root / "delivery" / "paid-remote-progress.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if ledger.is_file():
        existing = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    matches = [row for row in existing if row.get("effect_key") == value["effect_key"]]
    revision = value.get("classification_revision") is True
    if matches and not revision:
        if not (_same_json(matches[-1], value) or _same_json(matches[-1], unbound_value)):
            raise SystemExit("duplicate effect checkpoint differs from durable receipt")
        print(json.dumps({"status": "already_checkpointed", "effect_key": value["effect_key"]}))
        return 0
    if revision:
        value["record_type"] = "classification_revision"
        if matches and _same_json(matches[-1], value):
            print(json.dumps({"status": "already_checkpointed", "effect_key": value["effect_key"]}))
            return 0
        if not matches or not str(value.get("revision_reason") or "").strip():
            raise SystemExit("classification revision requires an existing effect and reason")
        prior = matches[-1]
        immutable = ("target", "payload_sha256", "official_receipt_url", "exact_readback",
                     "semantic_contract_sha256")
        if any(not _same_json(value.get(key), prior.get(key)) for key in immutable):
            raise SystemExit("classification revision cannot change effect identity")
    elif matches:
        raise SystemExit("duplicate effect checkpoint")
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    reconcile_tiktok_recipient_counts(ledger)
    print(json.dumps({"status": "classification_revised" if revision else "checkpointed",
                      "effect_key": value["effect_key"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
