from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/mobile-postiz-provider-reconcile.py"


def load_module():
    spec = importlib.util.spec_from_file_location("mobile_postiz_provider_reconcile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def identity() -> dict:
    caption_hash = hashlib.sha256(b"caption").hexdigest()
    return {
        "schema_version": 1,
        "kind": "life_manager_effect_identity",
        "runtime_run_id": "run-1",
        "occurrence_id": "life-manager-honne-ja:run-1",
        "loop_id": "life-manager-honne-ja",
        "job_id": "marketing-video-publication:job-1",
        "effect_key": "marketing:video:honne-ai:tiktok:creative:" + "a" * 64 + ":" + caption_hash,
        "product_id": "honne-ai",
        "format_id": "reelclaw",
        "form": "relationship-confession",
        "locale": "ja",
        "platform": "tiktok",
        "creative_id": "creative",
        "slot": "2026-09-17T12:30:00.000Z",
        "integration_ref": "integration://postiz/tiktok/integration-1",
        "account_id": "@honnevideo",
        "video_sha256": "a" * 64,
        "caption_sha256": caption_hash,
    }


def write_identity(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    path.chmod(0o600)


def write_video_ledger(path: Path, *, provider_id: str = "post-1") -> None:
    path.write_text(json.dumps({
        "status": "published",
        "product_id": "honne-ai",
        "format_id": "reelclaw",
        "form": "relationship-confession",
        "locale": "ja",
        "slot": "2026-09-17T12:30:00.000Z",
        "creative_id": "creative",
        "platform": "tiktok",
        "video_sha256": "a" * 64,
        "caption_sha256": hashlib.sha256(b"caption").hexdigest(),
        "provider_id": provider_id,
        "provider_reconciled": True,
        "public_url": "https://www.tiktok.com/@honnevideo/video/123",
    }) + "\n", encoding="utf-8")
    path.chmod(0o600)


def provider_rows(*, account: str = "@honnevideo", integration: str = "integration-1") -> dict:
    return {
        "post": {
            "posts": [{
                "id": "post-1",
                "state": "PUBLISHED",
                "releaseURL": "https://www.tiktok.com/@honnevideo",
                "releaseId": "v_pub_file~v2-1.123",
                "integration": {"id": integration},
                "content": "caption",
                "settings": {
                    "__type": "tiktok",
                    "title": "caption",
                    "content_posting_method": "DIRECT_POST",
                },
            }],
        },
        "integrations": {"integrations": [{
            "id": integration,
            "identifier": "tiktok",
            "profile": account,
        }]},
    }


def test_build_proof_requires_official_post_and_integration_identity(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    sidecar = tmp_path / "identity.jsonl"
    ledger = tmp_path / "distribution.jsonl"
    write_identity(sidecar, identity())
    write_video_ledger(ledger)
    responses = provider_rows()

    def request_json(url: str, _api_key: str):
        return responses["integrations" if url.endswith("/integrations") else "post"]

    monkeypatch.setattr(module, "_request_json", request_json)
    value = module.read_identity(sidecar, "life-manager-honne-ja", "life-manager-honne-ja:run-1")
    proof = module.build_official_proof(value, ledger, "token")

    assert proof["owner_id"] == "life-manager-honne-ja"
    assert proof["occurrence_id"] == "life-manager-honne-ja:run-1"
    assert proof["verified"] is True
    assert proof["proof_kind"] == "postiz_official_readback"
    assert proof["provider_receipt_id"] == "post-1"
    assert proof["provider_readback"]["account_id"] == "@honnevideo"
    assert proof["provider_readback"]["integration_ref"] == value["integration_ref"]
    assert proof["provider_readback"]["content"]["video_sha256"] == "a" * 64


def test_apply_returns_the_fresh_exact_proof_only_after_resolver_accepts(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    sidecar = tmp_path / "identity.jsonl"
    ledger = tmp_path / "distribution.jsonl"
    write_identity(sidecar, identity())
    write_video_ledger(ledger)
    responses = provider_rows()
    monkeypatch.setattr(
        module, "_request_json",
        lambda url, _api_key: responses["integrations" if url.endswith("/integrations") else "post"],
    )
    resolved = []

    def resolver(**kwargs):
        proof = kwargs["official_readback"]()
        resolved.append(proof)
        return True

    monkeypatch.setattr(module, "resolve_unknown_occurrence", resolver)
    value = module.read_identity(sidecar, "life-manager-honne-ja", "life-manager-honne-ja:run-1")
    result = module.reconcile_provider_effect(
        value, ledger, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
        state="released", effect_unknown=1, api_key="token", apply=True,
    )

    assert result["status"] == "resolved"
    assert len(resolved) == 1
    assert resolved[0]["provider_receipt_id"] == "post-1"
    assert resolved[0]["provider_readback"]["account_id"] == "@honnevideo"


def test_same_platform_different_account_is_inconclusive_and_never_resolves(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    sidecar = tmp_path / "identity.jsonl"
    ledger = tmp_path / "distribution.jsonl"
    write_identity(sidecar, identity())
    write_video_ledger(ledger)
    responses = provider_rows(account="@other-account")
    calls = []

    def request_json(url: str, _api_key: str):
        calls.append(url)
        return responses["integrations" if url.endswith("/integrations") else "post"]

    monkeypatch.setattr(module, "_request_json", request_json)
    monkeypatch.setattr(module, "resolve_unknown_occurrence", lambda **_: (_ for _ in ()).throw(AssertionError("must not resolve")))
    value = module.read_identity(sidecar, "life-manager-honne-ja", "life-manager-honne-ja:run-1")
    result = module.reconcile_provider_effect(
        value, ledger, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
        state="released", effect_unknown=1, api_key="token", apply=True,
    )

    assert result["status"] == "inconclusive"
    assert result["reason"] == "provider_readback_not_exact"
    assert calls


def test_claimed_occurrence_stays_held_without_provider_request(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    sidecar = tmp_path / "identity.jsonl"
    ledger = tmp_path / "distribution.jsonl"
    write_identity(sidecar, identity())
    write_video_ledger(ledger)
    monkeypatch.setattr(module, "_request_json", lambda *_: (_ for _ in ()).throw(AssertionError("must not read provider")))
    value = module.read_identity(sidecar, "life-manager-honne-ja", "life-manager-honne-ja:run-1")

    result = module.reconcile_provider_effect(
        value, ledger, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
        state="claimed", effect_unknown=1, api_key="token", apply=True,
    )

    assert result == {
        "status": "inconclusive",
        "owner_id": "life-manager-honne-ja",
        "occurrence_id": "life-manager-honne-ja:run-1",
        "reason": "claimed_or_already_resolved",
    }


def test_receipt_from_a_different_slot_is_not_an_exact_effect_join(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    sidecar = tmp_path / "identity.jsonl"
    ledger = tmp_path / "distribution.jsonl"
    write_identity(sidecar, identity())
    write_video_ledger(ledger)
    row = json.loads(ledger.read_text(encoding="utf-8"))
    row["slot"] = "2026-09-17T14:30:00.000Z"
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    responses = provider_rows()
    monkeypatch.setattr(
        module, "_request_json",
        lambda url, _api_key: responses["integrations" if url.endswith("/integrations") else "post"],
    )
    value = module.read_identity(sidecar, "life-manager-honne-ja", "life-manager-honne-ja:run-1")

    result = module.reconcile_provider_effect(
        value, ledger, "life-manager-honne-ja", "life-manager-honne-ja:run-1",
        state="released", effect_unknown=1, api_key="token", apply=False,
    )

    assert result["status"] == "inconclusive"
    assert result["reason"] == "provider_readback_not_exact"
