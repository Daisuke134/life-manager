from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "mobile-postiz-effect-reconcile.py"
SPEC = importlib.util.spec_from_file_location("mobile_postiz_effect_reconcile", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def identity() -> dict:
    return {
        "schema_version": 1,
        "kind": "life_manager_effect_identity",
        "runtime_run_id": "run-1",
        "occurrence_id": "life-manager-honne-ja:run-1",
        "loop_id": "life-manager-honne-ja",
        "job_id": "marketing-video-publication:job-1",
        "effect_key": "marketing:video:honne-ai:tiktok:creative:" + "a" * 64 + ":" + "b" * 64,
        "product_id": "honne-ai",
        "format_id": "reelclaw",
        "form": "relationship-confession",
        "locale": "ja",
        "platform": "tiktok",
        "creative_id": "creative",
        "slot": "2026-07-30T12:30:00.000Z",
        "integration_ref": "integration://postiz/tiktok/honne-ai-ja",
        "account_id": "@honnevideo",
        "video_sha256": "a" * 64,
        "caption_sha256": "b" * 64,
    }


def proof_for(value: dict) -> dict:
    return {
        "owner_id": value["loop_id"],
        "occurrence_id": value["occurrence_id"],
        "verified": True,
        "proof_kind": "postiz_official_readback",
        "provider_receipt_id": "postiz-provider-1",
        "identity": value,
        "provider_readback": {
            "provider": "postiz",
            "state": "PUBLISHED",
            "post_id": "postiz-provider-1",
            "account_id": value["account_id"],
            "integration_ref": value["integration_ref"],
            "content": {
                key: value[key]
                for key in ("video_sha256", "caption_sha256", "media_sha256", "pack_sha256", "media_order_sha256")
                if key in value
            },
        },
    }


def test_exact_provider_proof_is_ready_without_mutating_the_ledger():
    value = identity()
    result = MODULE.evaluate_proof(value, proof_for(value))
    assert result == {"status": "ready", "owner_id": value["loop_id"], "occurrence_id": value["occurrence_id"]}


def test_proof_must_match_every_effect_identity_field():
    value = identity()
    wrong_account = proof_for(value)
    wrong_account["identity"] = {**value, "account_id": "@wrong-account"}
    assert MODULE.evaluate_proof(value, wrong_account)["status"] == "inconclusive"

    wrong_hash = proof_for(value)
    wrong_hash["identity"] = {**value, "caption_sha256": "c" * 64}
    assert MODULE.evaluate_proof(value, wrong_hash)["status"] == "inconclusive"

    wrong_provider = proof_for(value)
    wrong_provider["provider_readback"] = {
        **wrong_provider["provider_readback"], "account_id": "@wrong-account",
    }
    assert MODULE.evaluate_proof(value, wrong_provider)["status"] == "inconclusive"

    missing_hashes = {**value, "effect_key": "marketing:anything", "video_sha256": None}
    missing_hashes.pop("caption_sha256")
    assert MODULE.evaluate_proof(
        missing_hashes, {**proof_for(value), "identity": missing_hashes},
    )["status"] == "inconclusive"


def test_missing_or_unverified_provider_receipt_stays_held():
    value = identity()
    missing = proof_for(value)
    del missing["provider_receipt_id"]
    assert MODULE.evaluate_proof(value, missing)["status"] == "inconclusive"

    unverified = proof_for(value)
    unverified["verified"] = False
    assert MODULE.evaluate_proof(value, unverified)["status"] == "inconclusive"

    missing_readback = proof_for(value)
    del missing_readback["provider_readback"]
    assert MODULE.evaluate_proof(value, missing_readback)["status"] == "inconclusive"


def test_only_a_released_unknown_row_is_ready_for_a_future_provider_executor():
    value = identity()
    proof = proof_for(value)

    result = MODULE.reconcile_proof(
        value, proof, state="released", effect_unknown=1,
    )
    assert result["status"] == "ready"
    held = MODULE.reconcile_proof(
        value, proof, state="claimed", effect_unknown=1,
    )
    assert held["status"] == "inconclusive"


def test_carousel_proof_requires_the_exact_ordered_media_hashes():
    value = identity()
    media = [f"{chr(97 + i)}" * 64 for i in range(6)]
    media_order = hashlib.sha256(
        json.dumps(media, ensure_ascii=False, separators=(",", ":")).encode(),
    ).hexdigest()
    value.update({
        "product_id": "anicca-ios",
        "platform": "instagram",
        "effect_key": "marketing:carousel:anicca-ios:creative:" + "d" * 64 + ":" + media_order + ":" + "f" * 64,
        "integration_ref": "integration://postiz/instagram/anicca-carousel",
        "account_id": "@anicca.carousel",
        "video_sha256": None,
        "caption_sha256": "f" * 64,
        "media_sha256": media,
        "pack_sha256": "d" * 64,
        "media_order_sha256": media_order,
    })
    proof = proof_for(value)
    assert MODULE.evaluate_proof(value, proof)["status"] == "ready"
    proof["provider_readback"]["content"].pop("media_sha256")
    assert MODULE.evaluate_proof(value, proof)["status"] == "inconclusive"
