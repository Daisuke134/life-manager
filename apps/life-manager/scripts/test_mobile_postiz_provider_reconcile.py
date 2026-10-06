from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("mobile-postiz-provider-reconcile.py")
SPEC = importlib.util.spec_from_file_location("mobile_postiz_provider_reconcile", MODULE_PATH)
reconcile = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reconcile)
import distribute


def test_product_scoped_flat_distribution_row_matches_without_product_field(tmp_path):
    identity = {
        "product_id": "ebook-ja",
        "format_id": "ebook-watercolor",
        "form": "ebook-reflection-reel",
        "locale": "ja",
        "creative_id": "baseline.ebook-ja.d1.s1",
        "platform": "instagram",
        "slot": "2026-10-06T22:00:00.000Z",
        "video_sha256": "a" * 64,
        "caption_sha256": "b" * 64,
        "account_id": "@obou.anicca",
        "integration_ref": "integration://postiz/instagram/cmooplxmu04tpmd0y4h3cpk33",
    }
    ledger = (
        tmp_path / "data" / "tenants" / "dais-local" / "marketing"
        / "video-publication" / "ebook-ja" / "distribution.jsonl"
    )
    ledger.parent.mkdir(parents=True)
    row = {
        "ts": "2026-10-06T22:00:20Z",
        "platform": "instagram",
        "status": "published",
        "creative_id": identity["creative_id"],
        "video_sha256": identity["video_sha256"],
        "caption_sha256": identity["caption_sha256"],
        "slot": identity["slot"],
        "format_id": identity["format_id"],
        "form": identity["form"],
        "locale": identity["locale"],
        "provider_id": "post-123",
        "public_url": "https://www.instagram.com/reel/abc123",
        "route": "postiz",
        "provider_reconciled": True,
    }
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    ledger.chmod(0o600)

    local = reconcile._local_receipt(identity, ledger)

    assert local is not None
    assert local[1] == "post-123"


def test_official_postiz_readback_recovers_post_missing_from_local_distribution_ledger(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    video_bytes = b"reconciled English/Japanese video bytes"
    video_sha = hashlib.sha256(video_bytes).hexdigest()
    caption = "A Japanese reflection.\n\nhttps://aniccaai.com/go/ej_abcdefghijklmnopqrst\n\n#内省"
    caption_sha = hashlib.sha256(caption.encode()).hexdigest()
    caption_object = data_dir / "objects" / "sha256" / caption_sha
    caption_object.parent.mkdir(parents=True)
    caption_object.write_text(caption, encoding="utf-8")
    caption_object.chmod(0o600)
    video_object = data_dir / "objects" / "sha256" / video_sha
    video_object.write_bytes(video_bytes)
    video_object.chmod(0o600)
    ledger = data_dir / "tenants" / "dais-local" / "marketing" / "video-publication" / "ebook-ja" / "distribution.jsonl"
    ledger.parent.mkdir(parents=True)

    slot = "2026-10-06T22:00:00.000Z"
    integration_id = "cmooplxmu04tpmd0y4h3cpk33"
    provider_id = "post-123"
    identity = {
        "schema_version": 1,
        "kind": "life_manager_effect_identity",
        "runtime_run_id": "run-1",
        "occurrence_id": "ebook-ja-instagram-daily:run-1",
        "loop_id": "ebook-ja-instagram-daily",
        "job_id": "marketing-video-publication:job-1",
        "effect_key": (
            f"marketing:video:ebook-ja:instagram:baseline.ebook-ja.d1.s1-20261006T220000000Z:"
            f"{video_sha}:{caption_sha}:{hashlib.sha256(slot.encode()).hexdigest()}"
        ),
        "product_id": "ebook-ja",
        "format_id": "ebook-watercolor",
        "form": "ebook-reflection-reel",
        "locale": "ja",
        "platform": "instagram",
        "creative_id": "baseline.ebook-ja.d1.s1-20261006T220000000Z",
        "slot": slot,
        "integration_ref": f"integration://postiz/instagram/{integration_id}",
        "account_id": "@obou.anicca",
        "video_sha256": video_sha,
        "caption_sha256": caption_sha,
    }
    provider_row = {
        "id": provider_id,
        "state": "PUBLISHED",
        "releaseURL": "https://www.instagram.com/reel/abc123",
        "integration": {"id": integration_id},
        "content": caption,
        "lifeManagerVideoSha256": video_sha,
    }
    readback = {
        "provider": "postiz",
        "state": "PUBLISHED",
        "post_id": provider_id,
        "public_url": provider_row["releaseURL"],
        "account_id": "@obou.anicca",
        "integration_ref": identity["integration_ref"],
        "content": {"caption_sha256": caption_sha, "video_sha256": video_sha},
        "local_content": {"caption_sha256": caption_sha, "video_sha256": video_sha},
    }
    monkeypatch.setattr(reconcile, "_request_json", lambda _url, _key: {"posts": [provider_row]})
    monkeypatch.setattr(reconcile, "_provider_readback", lambda *_args: readback)

    proof = reconcile.build_official_proof(identity, ledger, "secret-not-logged")

    assert proof["provider_receipt_id"] == provider_id
    assert proof["proof_kind"] == "postiz_official_readback"
    assert proof["provider_readback"]["account_id"] == "@obou.anicca"
    assert proof["provider_readback"]["remote_effect_locator"]["caption_sha256"] == caption_sha


def test_remote_recovery_accepts_the_english_campaign_token_for_heygen_posts(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    video_sha = "b" * 64
    slot = "2026-10-06T21:00:00.000Z"
    caption = "A calm reflection.\n\nhttps://aniccaai.com/go/ee_abcdefghijklmnopqrst\n\n#TheAniccaReset"
    caption_sha = hashlib.sha256(caption.encode()).hexdigest()
    caption_object = data_dir / "objects" / "sha256" / caption_sha
    caption_object.parent.mkdir(parents=True)
    caption_object.write_text(caption, encoding="utf-8")
    caption_object.chmod(0o600)
    ledger = (
        data_dir / "tenants" / "dais-local" / "marketing" / "video-publication"
        / "ebook-en" / "distribution.jsonl"
    )
    integration_id = "cmo5rwq2p00twn10yrsdglng3"
    provider_id = "post-en-123"
    identity = {
        "product_id": "ebook-en",
        "format_id": "ebook-avatar-iv",
        "form": "ebook-reflection-reel",
        "locale": "en",
        "creative_id": "baseline.ebook-en.d1.s3-20261006T210000000Z",
        "platform": "tiktok",
        "account_id": "@monk_anicca",
        "integration_ref": f"integration://postiz/tiktok/{integration_id}",
        "slot": slot,
        "effect_key": f"slot:{hashlib.sha256(slot.encode()).hexdigest()}",
        "caption_sha256": caption_sha,
        "video_sha256": video_sha,
    }
    provider_row = {
        "id": provider_id,
        "state": "PUBLISHED",
        "releaseURL": "https://www.tiktok.com/@monk_anicca/video/1234567890",
        "integration": {"id": integration_id},
        "content": caption,
        "lifeManagerVideoSha256": video_sha,
    }
    monkeypatch.setattr(reconcile, "_request_json", lambda *_args: {"posts": [provider_row]})

    recovered = reconcile._remote_video_receipt(identity, ledger, "test-only")

    assert recovered is not None
    receipt, recovered_id = recovered
    assert recovered_id == provider_id
    assert receipt["remote_effect_locator"]["integration_id"] == integration_id

    monkeypatch.setattr(reconcile, "_request_json", lambda *_args: {
        "posts": [provider_row, {**provider_row, "id": "post-en-456"}],
    })
    assert reconcile._remote_video_receipt(identity, ledger, "test-only") is None
    monkeypatch.setattr(reconcile, "_request_json", lambda *_args: {"posts": []})
    assert reconcile._remote_video_receipt(identity, ledger, "test-only") is None


def test_pending_owner_persists_remote_receipt_before_resolving_missing_local_row(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    identity_dir = data_dir / "marketing" / "effects"
    identity_dir.mkdir(parents=True)
    video_bytes = b"recovered distribution video bytes"
    video_sha = hashlib.sha256(video_bytes).hexdigest()
    slot = "2026-10-06T22:00:00.000Z"
    caption = "A Japanese reflection.\n\nhttps://aniccaai.com/go/ej_abcdefghijklmnopqrst\n\n#内省"
    caption_sha = hashlib.sha256(caption.encode()).hexdigest()
    caption_object = data_dir / "objects" / "sha256" / caption_sha
    caption_object.parent.mkdir(parents=True)
    caption_object.write_text(caption, encoding="utf-8")
    caption_object.chmod(0o600)
    video_object = data_dir / "objects" / "sha256" / video_sha
    video_object.write_bytes(video_bytes)
    video_object.chmod(0o600)
    identity = {
        "schema_version": 1,
        "kind": "life_manager_effect_identity",
        "runtime_run_id": "run-1",
        "occurrence_id": "ebook-ja-instagram-daily:run-1",
        "loop_id": "ebook-ja-instagram-daily",
        "job_id": "marketing-video-publication:job-1",
        "effect_key": (
            f"marketing:video:ebook-ja:instagram:baseline.ebook-ja.d1.s1-20261006T220000000Z:"
            f"{video_sha}:{caption_sha}:{hashlib.sha256(slot.encode()).hexdigest()}"
        ),
        "product_id": "ebook-ja",
        "format_id": "ebook-watercolor",
        "form": "ebook-reflection-reel",
        "locale": "ja",
        "platform": "instagram",
        "creative_id": "baseline.ebook-ja.d1.s1-20261006T220000000Z",
        "slot": slot,
        "integration_ref": "integration://postiz/instagram/cmooplxmu04tpmd0y4h3cpk33",
        "account_id": "@obou.anicca",
        "video_sha256": video_sha,
        "caption_sha256": caption_sha,
    }
    identity_path = identity_dir / "identity.jsonl"
    identity_path.write_text(json.dumps(identity) + "\n", encoding="utf-8")
    identity_path.chmod(0o600)
    ledger = (
        data_dir / "tenants" / "dais-local" / "marketing" / "video-publication"
        / "ebook-ja" / "distribution.jsonl"
    )
    provider_row = {
        "id": "post-123",
        "state": "PUBLISHED",
        "releaseURL": "https://www.instagram.com/reel/abc123",
        "integration": {"id": "cmooplxmu04tpmd0y4h3cpk33"},
        "content": caption,
        "lifeManagerVideoSha256": video_sha,
    }
    readback = {
        "provider": "postiz",
        "state": "PUBLISHED",
        "post_id": "post-123",
        "public_url": provider_row["releaseURL"],
        "account_id": "@obou.anicca",
        "integration_ref": identity["integration_ref"],
        "content": {"caption_sha256": caption_sha, "video_sha256": video_sha},
        "local_content": {"caption_sha256": caption_sha, "video_sha256": video_sha},
    }
    admission_db = tmp_path / "admission.sqlite3"
    monkeypatch.setattr(reconcile, "_authoritative_admission_db", lambda: admission_db.resolve())
    monkeypatch.setattr(reconcile, "_admission_state", lambda *_args: ("claimed", 1))
    listing_reads = []
    monkeypatch.setattr(
        reconcile, "_request_json",
        lambda url, _key: (listing_reads.append(url) or {"posts": [provider_row]}),
    )
    monkeypatch.setattr(reconcile, "_provider_readback", lambda *_args: dict(readback))
    resolved = []

    def resolve_unknown_occurrence(**kwargs):
        resolved.append(kwargs["occurrence_id"])
        assert reconcile._local_receipt(identity, ledger) is not None
        assert reconcile._local_receipt(identity, ledger)[1] == "post-123"
        kwargs["official_readback"]()
        return True

    monkeypatch.setattr(reconcile, "resolve_unknown_occurrence", resolve_unknown_occurrence)

    result = reconcile.reconcile_pending_owner(
        owner_id="ebook-ja-instagram-daily",
        identity_dir=identity_dir,
        data_dir=data_dir,
        tenant_id="dais-local",
        admission_db=admission_db,
        api_key="test-only",
        apply=True,
    )

    assert result["status"] == "resolved", result
    assert result["provider_receipt_id"] == "post-123"
    assert resolved == [identity["occurrence_id"]]
    rows = reconcile._safe_jsonl(ledger)
    assert rows is not None and len(rows) == 1
    assert rows[0]["product_id"] == identity["product_id"]
    assert rows[0]["slot"] == identity["slot"]
    assert rows[0]["provider_id"] == "post-123"
    assert rows[0]["provider_reconciled"] is True

    replay = reconcile.reconcile_pending_owner(
        owner_id="ebook-ja-instagram-daily",
        identity_dir=identity_dir,
        data_dir=data_dir,
        tenant_id="dais-local",
        admission_db=admission_db,
        api_key="test-only",
        apply=True,
    )
    assert replay["status"] == "resolved"
    rows = reconcile._safe_jsonl(ledger)
    assert rows is not None and len(rows) == 1
    assert len(listing_reads) == 1

    approval_path = data_dir / "tenants" / "dais-local" / "marketing" / "approvals" / "ebook.jsonl"
    approval_path.parent.mkdir(parents=True)
    approval_path.write_text(json.dumps({
        "status": "approved",
        "approval_mode": "standing_policy_no_additional_gate",
        "creative_id": identity["creative_id"],
    }) + "\n", encoding="utf-8")
    postiz_adapter = Path(__file__)
    config = distribute.DistributionConfig(
        creative_id=identity["creative_id"],
        video=video_object,
        caption=caption_object,
        ledger=ledger,
        instagram_adapter=postiz_adapter,
        tiktok_adapter=postiz_adapter,
        instagram_handle="obou.anicca",
        instagram_accounts=identity_dir / "unused.json",
        instagram_settings=None,
        instagram_credentials=None,
        instagram_profile_state=None,
        tiktok_integration="unused",
        approvals=approval_path,
        format_id=identity["format_id"],
        form=identity["form"],
        locale=identity["locale"],
        slot=identity["slot"],
        instagram_integration="cmooplxmu04tpmd0y4h3cpk33",
        postiz_adapter=postiz_adapter,
    )
    monkeypatch.setattr(distribute, "_run_json", lambda *_args: (_ for _ in ()).throw(
        AssertionError("replay must reuse the recovered provider receipt")
    ))
    published = distribute.distribute_platform(config, "instagram")
    assert published["provider_post_id"] == "post-123"
