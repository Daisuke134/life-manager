from __future__ import annotations

import importlib.util
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
        "provider_receipt_id": "postiz-provider-1",
        "identity": value,
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


def test_missing_or_unverified_provider_receipt_stays_held():
    value = identity()
    missing = proof_for(value)
    del missing["provider_receipt_id"]
    assert MODULE.evaluate_proof(value, missing)["status"] == "inconclusive"

    unverified = proof_for(value)
    unverified["verified"] = False
    assert MODULE.evaluate_proof(value, unverified)["status"] == "inconclusive"


def test_only_a_released_unknown_row_can_be_cleared():
    value = identity()
    proof = proof_for(value)
    calls = []

    def resolver(owner_id, occurrence_id, *, official_readback):
        calls.append((owner_id, occurrence_id, official_readback()))
        return True

    result = MODULE.reconcile_proof(
        value, proof, state="released", effect_unknown=1,
        execute=True, resolver=resolver,
    )
    assert result["status"] == "reconciled"
    assert calls == [(value["loop_id"], value["occurrence_id"], proof)]

    calls.clear()
    held = MODULE.reconcile_proof(
        value, proof, state="claimed", effect_unknown=1,
        execute=True, resolver=resolver,
    )
    assert held["status"] == "inconclusive"
    assert calls == []
