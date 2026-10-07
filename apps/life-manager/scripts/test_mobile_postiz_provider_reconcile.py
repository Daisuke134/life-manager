from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("mobile-postiz-provider-reconcile.py")
SPEC = importlib.util.spec_from_file_location("mobile_postiz_provider_reconcile", MODULE_PATH)
reconcile = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reconcile)
import distribute


def test_video_caption_normalization_matches_only_postiz_sender_strip(tmp_path):
    accepted_caption = "Exact caption\n"
    accepted_identity = {
        "video_sha256": "a" * 64,
        "caption_sha256": hashlib.sha256(accepted_caption.encode("utf-8")).hexdigest(),
    }
    assert reconcile._video_caption_normalization(
        accepted_identity, accepted_caption, accepted_caption.strip(),
    ) == "video_terminal_lf_removed"

    for raw_caption in ("Exact caption\n\n", "Exact caption\r\n", " Exact caption\n"):
        identity = {
            "video_sha256": "a" * 64,
            "caption_sha256": hashlib.sha256(raw_caption.encode("utf-8")).hexdigest(),
        }
        provider_caption = raw_caption[:-1]
        assert provider_caption != raw_caption.strip()
        assert reconcile._video_caption_normalization(
            identity, raw_caption, provider_caption,
        ) is None


def test_auto_owner_reconcile_fails_closed_when_an_unknown_receipt_is_unresolved(monkeypatch, capsys):
    owner = "life-manager-anicca-buddha-tiktok"

    for result, expected_exit in [
        ({"status": "no_match", "owner_id": owner, "inspected": 1}, 1),
        ({"status": "no_match", "owner_id": owner, "inspected": 0}, 1),
        ({"status": "inconclusive", "owner_id": owner, "reason": "provider_readback_not_exact"}, 1),
        ({"status": "clean", "owner_id": owner, "inspected": 0}, 0),
        ({"status": "resolved", "owner_id": owner, "occurrence_id": f"{owner}:run"}, 0),
    ]:
        monkeypatch.setattr(reconcile, "reconcile_pending_owner", lambda **_kwargs: result)
        assert reconcile.main(["--auto-owner", owner, "--tenant-id", "dais-local", "--resolve"]) == expected_exit
        assert json.loads(capsys.readouterr().out) == result


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


def test_pending_owner_expands_tilde_identity_directory(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    identity_dir = home / ".local/state/life-manager/ebook/effect-identities"
    identity_dir.mkdir(parents=True)
    occurrence_id = "ebook-ja-instagram-daily:run-1"
    identity_path = identity_dir / "run-1.jsonl"
    identity_path.write_text(json.dumps({"occurrence_id": occurrence_id}) + "\n", encoding="utf-8")
    identity_path.chmod(0o600)
    admission_db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(admission_db) as connection:
        connection.execute("CREATE TABLE occurrences (owner_id TEXT, occurrence_id TEXT, state TEXT, effect_unknown INTEGER)")
        connection.execute(
            "INSERT INTO occurrences VALUES (?, ?, 'claimed', 1)",
            ("ebook-ja-instagram-daily", occurrence_id),
        )
    seen = []
    monkeypatch.setattr(
        reconcile,
        "_valid_identity",
        lambda _identity, owner, occurrence: (seen.append((owner, occurrence)) or False),
    )

    result = reconcile.reconcile_pending_owner(
        owner_id="ebook-ja-instagram-daily",
        identity_dir=Path("~/.local/state/life-manager/ebook/effect-identities"),
        data_dir=tmp_path / "data",
        tenant_id="dais-local",
        admission_db=admission_db,
        api_key="unused",
        apply=False,
    )

    assert result["status"] == "no_match"
    assert seen == [("ebook-ja-instagram-daily", occurrence_id)]


def test_official_postiz_readback_recovers_post_missing_from_local_distribution_ledger(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    video_bytes = b"reconciled English/Japanese video bytes"
    video_sha = hashlib.sha256(video_bytes).hexdigest()
    caption = "A Japanese reflection.\n\nhttps://aniccaai.com/go/ej_abcdefghijklmnopqrst\n\n#内省\n"
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
        "content": caption[:-1],
        "lifeManagerVideoSha256": video_sha,
    }

    def request(url, _key):
        if url.startswith(f"{reconcile.POSTIZ_V1}/posts?"):
            return {"posts": [provider_row]}
        if url == f"{reconcile.POSTIZ_DETAILS}/{provider_id}":
            return provider_row
        if url == f"{reconcile.POSTIZ_V1}/integrations":
            return {"integrations": [{
                "id": integration_id,
                "identifier": "instagram-standalone",
                "profile": "obou.anicca",
            }]}
        raise AssertionError(f"unexpected Postiz readback URL: {url}")

    monkeypatch.setattr(reconcile, "_request_json", request)

    proof = reconcile.build_official_proof(identity, ledger, "secret-not-logged")

    assert proof["provider_receipt_id"] == provider_id
    assert proof["proof_kind"] == "postiz_official_readback"
    assert proof["provider_readback"]["account_id"] == "@obou.anicca"
    assert proof["provider_readback"]["remote_effect_locator"]["caption_sha256"] == caption_sha
    assert proof["provider_readback"]["caption_normalization"] == "video_terminal_lf_removed"
    assert proof["provider_readback"]["provider_caption_sha256"] == hashlib.sha256(caption[:-1].encode()).hexdigest()
    assert proof["provider_readback"]["local_wire_caption_sha256"] == hashlib.sha256(caption[:-1].encode()).hexdigest()

    provider_row["content"] = f"{caption[:-1]}!"
    try:
        reconcile.build_official_proof(identity, ledger, "secret-not-logged")
    except ValueError as error:
        assert str(error) == "receipt_missing_or_ambiguous"
    else:
        raise AssertionError("a changed provider caption must stay unresolved")


def test_verify_only_cli_returns_exact_postiz_proof_without_resolving(tmp_path, monkeypatch, capsys):
    owner_id = "ebook-ja-instagram-daily"
    occurrence_id = f"{owner_id}:run-1"
    integration_ref = "integration://postiz/instagram/cmooplxmu04tpmd0y4h3cpk33"
    identity = {"loop_id": owner_id, "occurrence_id": occurrence_id}
    proof = {
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_kind": "postiz_official_readback",
        "provider_receipt_id": "post-123",
        "identity": identity,
        "provider_readback": {
            "provider": "postiz",
            "state": "PUBLISHED",
            "post_id": "post-123",
            "public_url": "https://www.instagram.com/reel/abc123",
            "account_id": "@obou.anicca",
            "integration_ref": integration_ref,
        },
    }
    monkeypatch.setattr(reconcile, "read_identity", lambda *_args: identity)
    monkeypatch.setattr(reconcile, "build_official_proof", lambda *_args: proof)
    monkeypatch.setattr(
        reconcile,
        "resolve_unknown_occurrence",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("verify-only must not resolve")),
    )
    monkeypatch.setenv("POSTIZ_API_KEY", "test-only")
    try:
        code = reconcile.main([
            "--verify-only",
            "--identity", str(tmp_path / "identity.jsonl"),
            "--ledger", str(tmp_path / "distribution.jsonl"),
            "--owner-id", owner_id,
            "--occurrence-id", occurrence_id,
        ])
    except SystemExit as exc:
        code = exc.code

    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ready"
    assert output["provider_readback"]["integration_ref"] == integration_ref


def test_real_postiz_readback_carries_local_caption_hash_into_recovery_row(tmp_path, monkeypatch):
    integration_id = "cmooplxmu04tpmd0y4h3cpk33"
    provider_id = "post-124"
    caption = "A Japanese reflection.\n\nhttps://aniccaai.com/go/ej_abcdefghijklmnopqrst\n\n#内省"
    caption_sha = hashlib.sha256(caption.encode()).hexdigest()
    video_sha = "c" * 64
    identity = {
        "product_id": "ebook-ja",
        "format_id": "ebook-watercolor",
        "form": "ebook-reflection-reel",
        "locale": "ja",
        "creative_id": "baseline.ebook-ja.d1.s1",
        "platform": "instagram",
        "slot": "2026-10-06T22:00:00.000Z",
        "video_sha256": video_sha,
        "caption_sha256": caption_sha,
        "account_id": "@obou.anicca",
        "integration_ref": f"integration://postiz/instagram/{integration_id}",
    }
    provider_row = {
        "id": provider_id,
        "state": "PUBLISHED",
        "releaseURL": "https://www.instagram.com/reel/abc124",
        "integration": {"id": integration_id},
        "content": caption,
        "lifeManagerVideoSha256": video_sha,
    }

    def request(url, _key):
        if url.endswith(f"/public/posts/{provider_id}"):
            return provider_row
        if url.endswith("/public/v1/integrations"):
            return {"integrations": [{
                "id": integration_id, "identifier": "instagram-standalone",
                "profile": "obou.anicca",
            }]}
        raise AssertionError(f"unexpected provider read: {url}")

    class PublishedPostAdapter:
        @staticmethod
        def find_post(rows, post_id, platform):
            assert rows == [provider_row]
            assert post_id == provider_id and platform == "instagram"
            return {"state": "PUBLISHED", "post_url": provider_row["releaseURL"]}

    monkeypatch.setattr(reconcile, "_request_json", request)
    monkeypatch.setattr(reconcile, "_load_postiz_video_adapter", lambda: PublishedPostAdapter())
    readback = reconcile._provider_readback(identity, provider_id, "test-only")
    proof = {
        "verified": True,
        "identity": identity,
        "provider_receipt_id": provider_id,
        "provider_readback": readback,
    }
    ledger = (
        tmp_path / "data" / "tenants" / "dais-local" / "marketing"
        / "video-publication" / "ebook-ja" / "distribution.jsonl"
    )

    recovered = reconcile._recovered_distribution_row(identity, proof, ledger)

    assert readback["content"]["caption_sha256"] == caption_sha
    assert readback["local_content"]["caption_sha256"] == caption_sha
    assert recovered["caption_sha256"] == caption_sha


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
    unrelated_later_post = {
        **provider_row,
        "id": "post-en-unrelated",
        "content": "unrelated caption",
        "lifeManagerVideoSha256": None,
    }
    monkeypatch.setattr(reconcile, "_request_json", lambda *_args: {
        "posts": [provider_row, unrelated_later_post],
    })
    recovered_with_unrelated_tail = reconcile._remote_video_receipt(identity, ledger, "test-only")
    assert recovered_with_unrelated_tail is not None
    assert recovered_with_unrelated_tail[0]["provider_video_sha256"] == video_sha

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
    with sqlite3.connect(admission_db) as connection:
        connection.execute("CREATE TABLE occurrences (owner_id TEXT, occurrence_id TEXT, state TEXT, effect_unknown INTEGER)")
        connection.execute(
            "INSERT INTO occurrences VALUES (?, ?, 'claimed', 1)",
            ("ebook-ja-instagram-daily", identity["occurrence_id"]),
        )
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
        with sqlite3.connect(admission_db) as connection:
            connection.execute(
                "UPDATE occurrences SET state='released', effect_unknown=0 WHERE owner_id=? AND occurrence_id=?",
                ("ebook-ja-instagram-daily", identity["occurrence_id"]),
            )
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
    assert replay["status"] == "clean"
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


def test_jp1_readback_matches_postiz_profile_separately_from_native_handle(monkeypatch):
    integration_id = "cmlrv8jq000hun60yy57eaptx"
    provider_id = "cmukc2o0j069ipr0y2gduabj9"
    base_caption = "口癖5選"
    final_caption = base_caption + "\n\nアプリはプロフィールのリンクから\n"
    identity = {
        "platform": "tiktok",
        "integration_ref": f"integration://postiz/tiktok/{integration_id}",
        "account_id": "@anicca.jp1",
        "caption_sha256": hashlib.sha256(base_caption.encode()).hexdigest(),
        "video_sha256": None,
    }
    provider_row = {
        "id": provider_id,
        "state": "PUBLISHED",
        "releaseURL": "https://www.tiktok.com/@anicca.jpx",
        "releaseId": "p_pub_url~v2.123",
        "integration": {"id": integration_id},
        "content": final_caption,
        "settings": json.dumps({
            "__type": "tiktok",
            "title": "口癖5選",
            "content_posting_method": "DIRECT_POST",
        }),
    }

    def request_json(url: str, _api_key: str):
        if url.endswith("/integrations"):
            return {"integrations": [{
                "id": integration_id,
                "identifier": "tiktok",
                "profile": "anicca.jpx",
            }]}
        return {"posts": [provider_row]}

    monkeypatch.setattr(reconcile, "_request_json", request_json)
    readback = reconcile._provider_readback(
        identity,
        provider_id,
        "test-only",
        hashlib.sha256(final_caption.encode()).hexdigest(),
    )

    assert readback["state"] == "PUBLISHED"
    assert readback["account_id"] == "@anicca.jp1"
    assert readback["postiz_profile"] == "@anicca.jpx"
    assert readback["integration_ref"] == identity["integration_ref"]
