#!/usr/bin/env python3
"""Reconcile Postiz state to a unique native receipt and canonical identity row."""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE / "identity"))

from browser_adapter import unique_native_match  # noqa: E402
from intent_store import IntentStore  # noqa: E402
from publication_ledger import atomic_write, read_jsonl, validate_rows  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def identity_row(intent: dict, post: dict, native: dict, *, expected_handle: str,
                 observed_at: str) -> dict:
    integration = post.get("integration") or {}
    return {
        "schema_version": 1,
        "observed_at": observed_at,
        "postiz_post_id": str(post["id"]),
        "postiz_group_id": post.get("group"),
        "postiz_state": "PUBLISHED",
        "postiz_release_id": post.get("releaseId"),
        "postiz_release_url": post.get("releaseURL"),
        "publish_date": post.get("publishDate"),
        "creation_method": post.get("creationMethod") or "api",
        "integration_id": intent["integration_id"],
        "account_name": expected_handle,
        "account_id": intent["account_id"],
        "account_id_null_reason": None,
        "platform": integration.get("providerIdentifier") or intent["platform"],
        "content_sha256": intent["caption_sha256"],
        "publish_key": intent["publish_key"],
        "experiment_id": intent["experiment_id"],
        "experiment_id_null_reason": None,
        "creative_id": intent["creative_id"],
        "creative_sha256": intent["asset_sha256"],
        "creative_sha256_null_reason": None,
        "product_id": intent["product_id"],
        "product_id_null_reason": None,
        "hook_id": intent["hook_id"],
        "renderer_id": intent["renderer_id"],
        "attribution_token": intent["attribution_token"],
        "scheduled_at": intent["scheduled_at"],
        "provenance": ["marketing_publication_intent", "postiz_public_api", "native_readback"],
        "identity_status": "resolved",
        "native_post_id": native["native_post_id"],
        "native_post_url": native["native_post_url"],
        "resolution_method": "account_token_time_exact",
        "resolution_confidence": "deterministic",
        "candidate_count": 1,
    }


def append_identity(path: pathlib.Path, row: dict) -> bool:
    rows = read_jsonl(path)
    for existing in rows:
        if existing.get("postiz_post_id") == row["postiz_post_id"]:
            old = {key: value for key, value in existing.items() if key != "observed_at"}
            new = {key: value for key, value in row.items() if key != "observed_at"}
            require(old == new, "conflicting publication identity replay")
            return False
    native_key = (row["platform"], row["integration_id"], row["native_post_id"])
    require(not any((item.get("platform"), item.get("integration_id"),
                     item.get("native_post_id")) == native_key for item in rows),
            "duplicate native publication identity")
    updated = sorted(rows + [row], key=lambda item: (
        str(item.get("publish_date") or ""), str(item.get("postiz_post_id") or "")))
    validate_rows(updated)
    atomic_write(path, "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                               for item in updated))
    return True


def reconcile_postiz_result(*, store: IntentStore, publish_key: str, post: dict,
                            native_items: list[dict], expected_handle: str,
                            observed_at: str, ledger_path: pathlib.Path) -> dict:
    current = store.get(publish_key)
    intent = current["intent"]
    require(intent["native_handle"].casefold() == expected_handle.casefold(),
            "reconciled handle differs from immutable intent")
    integration = post.get("integration") or {}
    require(str(post.get("id") or "") == str(current.get("provider_post_id") or ""),
            "reconciled Postiz ID mismatch")
    require(str(integration.get("id") or "") == intent["integration_id"],
            "reconciled integration mismatch")
    require(str(integration.get("providerIdentifier") or "").casefold() ==
            intent["platform"].casefold(), "reconciled provider mismatch")
    state = post.get("state")
    if state == "ERROR":
        store.mark_provider_error(publish_key, post)
        return {"status": "provider_error", "identity_appended": False}
    store.reconcile_provider(publish_key, post)
    if state != "PUBLISHED":
        return {"status": "pending_provider", "identity_appended": False}
    native = unique_native_match(intent, native_items, expected_handle=expected_handle)
    if native is None:
        return {"status": "pending_native_receipt", "identity_appended": False}
    row = identity_row(intent, post, native, expected_handle=expected_handle,
                       observed_at=observed_at)
    appended = append_identity(pathlib.Path(ledger_path), row)
    store.record_reconciled_native(publish_key, native)
    return {"status": "published_native_verified", "identity_appended": appended,
            "postiz_post_id": row["postiz_post_id"],
            "native_post_id": row["native_post_id"],
            "native_post_url": row["native_post_url"]}
