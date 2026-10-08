from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
import pytest


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


def test_runtime_auto_owner_passes_a_clean_occurrence_while_older_occurrences_remain_unknown(
    tmp_path, monkeypatch, capsys,
):
    owner = "life-manager-anicca-main-tiktok"
    old_occurrence = f"{owner}:run-old"
    current_occurrence = f"{owner}:run-current"
    admission_db = tmp_path / "admission.sqlite3"
    identity_dir = tmp_path / "effect-identities"
    identity_dir.mkdir()
    old_sidecar = identity_dir / "run-old.jsonl"
    old_sidecar.write_text(json.dumps({"occurrence_id": old_occurrence}) + "\n", encoding="utf-8")
    old_sidecar.chmod(0o600)
    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            "CREATE TABLE occurrences (owner_id TEXT, occurrence_id TEXT, state TEXT, effect_unknown INTEGER)"
        )
        connection.executemany(
            "INSERT INTO occurrences VALUES (?, ?, ?, ?)",
            [
                (owner, old_occurrence, "released", 1),
                (owner, current_occurrence, "released", 0),
            ],
        )
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", current_occurrence)
    monkeypatch.setenv("LIFE_MANAGER_RUN_ID", "run-current")
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", owner)
    scanned_sidecars = []
    safe_jsonl = reconcile._safe_jsonl

    def record_sidecar_read(path):
        scanned_sidecars.append(path)
        return safe_jsonl(path)

    monkeypatch.setattr(reconcile, "_safe_jsonl", record_sidecar_read)

    result_code = reconcile.main([
        "--auto-owner", owner,
        "--identity-dir", str(identity_dir),
        "--data-dir", str(tmp_path / "data"),
        "--admission-db", str(admission_db),
        "--tenant-id", "dais-local",
        "--resolve",
    ])
    result = json.loads(capsys.readouterr().out)

    assert result_code == 0, result
    assert result["status"] == "clean"
    assert result["occurrence_id"] == current_occurrence
    assert scanned_sidecars == []
    with sqlite3.connect(admission_db) as connection:
        assert connection.execute(
            "SELECT state,effect_unknown FROM occurrences WHERE occurrence_id=?",
            (old_occurrence,),
        ).fetchone() == ("released", 1)


@pytest.mark.parametrize("occurrence_id", [
    None,
    "life-manager-anicca-main-tiktok:invalid/id",
    "life-manager-anicca-buddha-tiktok:run-1",
])
def test_runtime_auto_owner_fails_closed_when_occurrence_identity_is_missing_or_invalid(
    tmp_path, monkeypatch, capsys, occurrence_id,
):
    owner = "life-manager-anicca-main-tiktok"
    admission_db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            "CREATE TABLE occurrences (owner_id TEXT, occurrence_id TEXT, state TEXT, effect_unknown INTEGER)"
        )
    if occurrence_id is None:
        monkeypatch.delenv("LIFE_MANAGER_OCCURRENCE_ID", raising=False)
    else:
        monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", occurrence_id)
    monkeypatch.setenv("LIFE_MANAGER_RUN_ID", "run-current")
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", owner)

    result_code = reconcile.main([
        "--auto-owner", owner,
        "--data-dir", str(tmp_path / "data"),
        "--admission-db", str(admission_db),
        "--tenant-id", "dais-local",
        "--resolve",
    ])
    result = json.loads(capsys.readouterr().out)

    assert result_code == 1, result
    assert result["status"] == "inconclusive"
    assert result["reason"] == "runtime_occurrence_missing_or_invalid"


def test_runtime_auto_owner_does_not_substitute_an_older_identity_for_current_unknown(
    tmp_path, monkeypatch, capsys,
):
    owner = "life-manager-anicca-main-tiktok"
    old_occurrence = f"{owner}:run-old"
    current_occurrence = f"{owner}:run-current"
    admission_db = tmp_path / "admission.sqlite3"
    identity_dir = tmp_path / "effect-identities"
    identity_dir.mkdir()
    old_sidecar = identity_dir / "run-old.jsonl"
    old_sidecar.write_text(json.dumps({"occurrence_id": old_occurrence}) + "\n", encoding="utf-8")
    old_sidecar.chmod(0o600)
    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            "CREATE TABLE occurrences (owner_id TEXT, occurrence_id TEXT, state TEXT, effect_unknown INTEGER)"
        )
        connection.executemany(
            "INSERT INTO occurrences VALUES (?, ?, ?, ?)",
            [
                (owner, old_occurrence, "released", 1),
                (owner, current_occurrence, "claimed", 1),
            ],
        )
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", current_occurrence)
    monkeypatch.setenv("LIFE_MANAGER_RUN_ID", "run-current")
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", owner)

    result_code = reconcile.main([
        "--auto-owner", owner,
        "--identity-dir", str(identity_dir),
        "--data-dir", str(tmp_path / "data"),
        "--admission-db", str(admission_db),
        "--tenant-id", "dais-local",
        "--resolve",
    ])
    result = json.loads(capsys.readouterr().out)

    assert result_code == 1, result
    assert result["status"] == "inconclusive"
    assert result["occurrence_id"] == current_occurrence
    assert result["reason"] == "identity_missing_or_invalid"
    assert old_sidecar.read_text(encoding="utf-8") == json.dumps({"occurrence_id": old_occurrence}) + "\n"


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

    def build_proof(*_args, identity_dir=None):
        assert identity_dir == tmp_path
        return proof

    monkeypatch.setattr(reconcile, "build_official_proof", build_proof)
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


def _native_carousel_recovery_fixture(tmp_path, monkeypatch, *, copies=1, corrupt_media=False):
    owner = "life-manager-anicca-jp1-tiktok"
    slot = "2026-10-07T09:00:00.000Z"
    integration_id = "cmlrv8jq000hun60yy57eaptx"
    caption = "A short, steady reminder."
    caption_sha = hashlib.sha256(caption.encode()).hexdigest()
    media_bytes = [f"approved-slide-{index}".encode() for index in range(6)]
    media_sha = [hashlib.sha256(value).hexdigest() for value in media_bytes]
    media_order_sha = hashlib.sha256(
        json.dumps(media_sha, separators=(",", ":")).encode()
    ).hexdigest()
    pack_bytes = json.dumps(
        {"slides": [{"text": "Exact title"}, *({"text": f"Slide {index}"} for index in range(2, 7))]},
        separators=(",", ":"),
    ).encode()
    pack_sha = hashlib.sha256(pack_bytes).hexdigest()
    data_dir = tmp_path / "data"
    objects = data_dir / "objects" / "sha256"
    objects.mkdir(parents=True)
    pack_path = objects / pack_sha
    pack_path.write_bytes(pack_bytes)
    pack_path.chmod(0o600)
    identity = {
        "schema_version": 1,
        "kind": "life_manager_effect_identity",
        "runtime_run_id": "run-1",
        "occurrence_id": f"{owner}:run-1",
        "loop_id": owner,
        "job_id": "marketing-native-carousel-publication:job-1",
        "effect_key": (
            f"marketing:carousel:anicca-ios:JA-LARRY-V1-JP1-test1:{pack_sha}:"
            f"{media_order_sha}:{caption_sha}:{hashlib.sha256(slot.encode()).hexdigest()}"
        ),
        "product_id": "anicca-ios",
        "format_id": "larry",
        "form": "affirmation-carousel",
        "locale": "ja",
        "platform": "tiktok",
        "creative_id": "JA-LARRY-V1-JP1-test1",
        "slot": slot,
        "integration_ref": f"integration://postiz/tiktok/{integration_id}",
        "account_id": "@anicca.jp1",
        "video_sha256": None,
        "caption_sha256": caption_sha,
        "media_sha256": media_sha,
        "pack_sha256": pack_sha,
        "media_order_sha256": media_order_sha,
    }
    identity_dir = tmp_path / "runtime" / "effect-identities"
    identity_dir.mkdir(parents=True)
    identity_path = identity_dir / "run-1.jsonl"
    identity_path.write_text(json.dumps(identity) + "\n", encoding="utf-8")
    identity_path.chmod(0o600)
    ledger = (
        data_dir / "tenants" / "dais-local" / "marketing"
        / "native-carousel-publication" / "anicca-ios" / "distribution.jsonl"
    )
    admission_db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            "CREATE TABLE occurrences (owner_id TEXT, occurrence_id TEXT, state TEXT, effect_unknown INTEGER)"
        )
        connection.execute(
            "INSERT INTO occurrences VALUES (?, ?, 'claimed', 1)",
            (owner, identity["occurrence_id"]),
        )

    media_by_url = {
        f"https://uploads.postiz.com/slide-{index}.jpg": value
        for index, value in enumerate(media_bytes)
    }
    if corrupt_media:
        media_by_url["https://uploads.postiz.com/slide-0.jpg"] = b"wrong-image-bytes"
    posts = []
    details = {}
    for index in range(copies):
        provider_id = f"post-photo-{index + 1}"
        images = [{"id": f"media-{i}", "path": f"https://uploads.postiz.com/slide-{i}.jpg"} for i in range(6)]
        row = {
            "id": provider_id,
            "state": "PUBLISHED",
            "publishDate": f"2026-10-07T09:0{index + 1}:00.000Z",
            "integration": {"id": integration_id},
            "content": caption,
        }
        posts.append(row)
        details[provider_id] = {
            **row,
            "image": json.dumps(images),
            "releaseId": f"p_pub_url~v2.{12345 + index}",
            "releaseURL": "https://www.tiktok.com/@anicca.jp1",
            "settings": json.dumps({
                "__type": "tiktok",
                "title": "Exact title",
                "content_posting_method": "DIRECT_POST",
            }),
        }

    request_urls = []

    def request_json(url, _api_key):
        request_urls.append(url)
        if url.startswith(f"{reconcile.POSTIZ_V1}/posts?"):
            return {"posts": posts}
        if url == f"{reconcile.POSTIZ_V1}/integrations":
            return {"integrations": [{
                "id": integration_id, "identifier": "tiktok", "profile": "anicca.jpx",
            }]}
        for provider_id, row in details.items():
            if url == f"{reconcile.POSTIZ_DETAILS}/{provider_id}":
                return row
        raise AssertionError(f"unexpected Postiz GET: {url}")

    class FakeResponse(io.BytesIO):
        headers = {"Content-Type": "image/jpeg"}

        def __init__(self, payload, url):
            super().__init__(payload)
            self.url = url

        def geturl(self):
            return self.url

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    image_urls = []

    def urlopen(request, timeout=0):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        image_urls.append(url)
        assert timeout > 0
        return FakeResponse(media_by_url[url], url)

    class PublishedPhotoAdapter:
        @staticmethod
        def find_post(rows, provider_id, platform):
            assert platform == "tiktok"
            return {"state": rows[0]["state"], "post_url": None}

    monkeypatch.setattr(reconcile, "_authoritative_admission_db", lambda: admission_db.resolve())
    monkeypatch.setattr(reconcile, "_request_json", request_json)
    monkeypatch.setattr(reconcile, "_load_postiz_video_adapter", lambda: PublishedPhotoAdapter())
    monkeypatch.setattr(reconcile.urllib.request, "urlopen", urlopen)
    return {
        "owner": owner,
        "identity": identity,
        "identity_dir": identity_dir,
        "data_dir": data_dir,
        "ledger": ledger,
        "admission_db": admission_db,
        "media_sha": media_sha,
        "request_urls": request_urls,
        "image_urls": image_urls,
        "provider_id": "post-photo-1",
    }


def test_pending_owner_recovers_only_one_exact_native_carousel_receipt(tmp_path, monkeypatch):
    fixture = _native_carousel_recovery_fixture(tmp_path, monkeypatch)
    owner = fixture["owner"]
    identity = fixture["identity"]
    fixture["ledger"].parent.mkdir(parents=True)
    fixture["ledger"].write_text(json.dumps({
        "effect_key": "another-effect",
        "job_id": "another-job",
        "receipt": {"status": "published"},
    }) + "\n", encoding="utf-8")
    fixture["ledger"].chmod(0o600)
    resolved = []

    def resolve_unknown_occurrence(**kwargs):
        assert kwargs["owner_id"] == owner
        assert kwargs["occurrence_id"] == identity["occurrence_id"]
        proof = kwargs["official_readback"]()
        assert proof["provider_receipt_id"] == fixture["provider_id"]
        stored = reconcile._local_receipt(identity, fixture["ledger"])
        assert stored is not None and stored[1] == fixture["provider_id"]
        resolved.append(kwargs["occurrence_id"])
        with sqlite3.connect(fixture["admission_db"]) as connection:
            connection.execute(
                "UPDATE occurrences SET state='released',effect_unknown=0 WHERE owner_id=? AND occurrence_id=?",
                (owner, identity["occurrence_id"]),
            )
        return True

    monkeypatch.setattr(reconcile, "resolve_unknown_occurrence", resolve_unknown_occurrence)
    result = reconcile.reconcile_pending_owner(
        owner_id=owner,
        identity_dir=fixture["identity_dir"],
        data_dir=fixture["data_dir"],
        tenant_id="dais-local",
        admission_db=fixture["admission_db"],
        api_key="test-only",
        apply=True,
    )

    assert result["status"] == "resolved", result
    assert result["provider_receipt_id"] == fixture["provider_id"]
    assert resolved == [identity["occurrence_id"]]
    assert fixture["image_urls"]
    assert all("/public/posts/" not in url for url in fixture["image_urls"])
    rows = reconcile._safe_jsonl(fixture["ledger"])
    assert rows is not None and len(rows) == 2
    recovered = rows[-1]
    assert recovered["effect_key"] == identity["effect_key"]
    assert recovered["job_id"] == identity["job_id"]
    receipt = recovered["receipt"]
    assert receipt["provider_post_id"] == fixture["provider_id"]
    assert receipt["media_sha256"] == fixture["media_sha"]
    assert receipt["provider_content_sha256"] == identity["caption_sha256"]
    reconcile._persist_recovered_distribution_row(identity, result, fixture["ledger"])
    replayed_rows = reconcile._safe_jsonl(fixture["ledger"])
    assert replayed_rows is not None and len(replayed_rows) == 2

    node = shutil.which("node")
    assert node
    adapter_path = Path(reconcile.__file__).resolve().parents[1] / "lib" / "marketing-native-carousel-publication-adapter.js"
    code = (
        "const adapter=require(process.argv[1]);let data='';"
        "process.stdin.on('data',x=>data+=x);"
        "process.stdin.on('end',()=>process.exit(adapter.verifyMarketingNativeCarouselPublicationReceipt(JSON.parse(data))?0:1));"
    )
    checked = subprocess.run(
        [node, "-e", code, str(adapter_path)], input=json.dumps(receipt),
        text=True, capture_output=True, cwd=Path(reconcile.__file__).resolve().parents[3], check=False,
    )
    assert checked.returncode == 0, checked.stderr or checked.stdout


def test_runtime_auto_owner_resolves_current_proof_and_leaves_other_fence_for_receipt_dedup(
    tmp_path, monkeypatch, capsys,
):
    fixture = _native_carousel_recovery_fixture(tmp_path, monkeypatch)
    owner = fixture["owner"]
    identity = fixture["identity"]
    fixture_occurrence = identity["occurrence_id"]
    identity["occurrence_id"] = f"{owner}:18d864fa9d9c6858-71847"
    identity["runtime_run_id"] = "18d87e42d43a1de0-7377"
    current_sidecar = fixture["identity_dir"] / f"{identity['runtime_run_id']}.jsonl"
    original_sidecar = fixture["identity_dir"] / "run-1.jsonl"
    original_sidecar.unlink()
    current_sidecar.write_text(json.dumps(identity) + "\n", encoding="utf-8")
    current_sidecar.chmod(0o600)

    old_identity = _identity_for_neighbor_slot(
        identity, run_id="18d87e42d43a1de0-1111", slot="2026-10-06T09:00:00.000Z",
    )
    old_occurrence = old_identity["occurrence_id"]
    old_sidecar = fixture["identity_dir"] / f"{old_identity['runtime_run_id']}.jsonl"
    old_sidecar.write_text(json.dumps(old_identity) + "\n", encoding="utf-8")
    old_sidecar.chmod(0o600)
    with sqlite3.connect(fixture["admission_db"]) as connection:
        connection.execute(
            "UPDATE occurrences SET occurrence_id=? WHERE owner_id=? AND occurrence_id=?",
            (identity["occurrence_id"], owner, fixture_occurrence),
        )
        connection.execute(
            "INSERT INTO occurrences VALUES (?, ?, 'released', 1)",
            (owner, old_occurrence),
        )
    fixture["ledger"].parent.mkdir(parents=True)
    fixture["ledger"].write_text(json.dumps({
        "effect_key": "another-effect",
        "job_id": "another-job",
        "receipt": {"status": "published"},
    }) + "\n", encoding="utf-8")
    fixture["ledger"].chmod(0o600)
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", identity["occurrence_id"])
    monkeypatch.setenv("LIFE_MANAGER_RUN_ID", "run-1")
    monkeypatch.setenv("LIFE_MANAGER_LOOP_ID", owner)
    monkeypatch.setenv("POSTIZ_API_KEY", "test-only")
    resolved = []

    def resolve_unknown_occurrence(**kwargs):
        assert kwargs["owner_id"] == owner
        assert kwargs["occurrence_id"] == identity["occurrence_id"]
        proof = kwargs["official_readback"]()
        assert proof["provider_receipt_id"] == fixture["provider_id"]
        assert reconcile._local_receipt(identity, fixture["ledger"])[1] == fixture["provider_id"]
        resolved.append(kwargs["occurrence_id"])
        with sqlite3.connect(fixture["admission_db"]) as connection:
            connection.execute(
                "UPDATE occurrences SET state='released',effect_unknown=0 WHERE owner_id=? AND occurrence_id=?",
                (owner, identity["occurrence_id"]),
            )
        return True

    monkeypatch.setattr(reconcile, "resolve_unknown_occurrence", resolve_unknown_occurrence)
    result_code = reconcile.main([
        "--auto-owner", owner,
        "--identity-dir", str(fixture["identity_dir"]),
        "--data-dir", str(fixture["data_dir"]),
        "--admission-db", str(fixture["admission_db"]),
        "--tenant-id", "dais-local",
        "--resolve",
    ])
    result = json.loads(capsys.readouterr().out)

    assert result_code == 0, result
    assert result["status"] == "resolved"
    assert result["occurrence_id"] == identity["occurrence_id"]
    assert resolved == [identity["occurrence_id"]]
    with sqlite3.connect(fixture["admission_db"]) as connection:
        assert connection.execute(
            "SELECT state,effect_unknown FROM occurrences WHERE occurrence_id=?",
            (old_occurrence,),
        ).fetchone() == ("released", 1)
    rows = reconcile._safe_jsonl(fixture["ledger"])
    assert rows is not None and rows[-1]["effect_key"] == identity["effect_key"]
    assert rows[-1]["receipt"]["provider_post_id"] == fixture["provider_id"]

    node = shutil.which("node")
    assert node
    adapter_path = Path(reconcile.__file__).resolve().parents[1] / "lib" / "marketing-native-carousel-publication-adapter.js"
    code = (
        "const adapter=require(process.argv[1]).createMarketingNativeCarouselPublicationLoopAdapter({ledgerPath:()=>process.argv[2]});"
        "adapter.reconcile({tenant_id:'dais-local',effect_key:process.argv[3]}).then(result=>{"
        "process.stdout.write(JSON.stringify(result));process.exit(result.state==='present'?0:1);});"
    )
    checked = subprocess.run(
        [node, "-e", code, str(adapter_path), str(fixture["ledger"]), identity["effect_key"]],
        text=True, capture_output=True, cwd=Path(reconcile.__file__).resolve().parents[3], check=False,
    )
    assert checked.returncode == 0, checked.stderr or checked.stdout
    dedup = json.loads(checked.stdout)
    assert dedup["state"] == "present"
    assert dedup["receipt"]["provider_post_id"] == fixture["provider_id"]


def test_native_carousel_recovery_refuses_ambiguous_or_changed_remote_media(tmp_path, monkeypatch):
    ambiguous = _native_carousel_recovery_fixture(tmp_path / "ambiguous", monkeypatch, copies=2)
    result = reconcile.reconcile_pending_owner(
        owner_id=ambiguous["owner"], identity_dir=ambiguous["identity_dir"],
        data_dir=ambiguous["data_dir"], tenant_id="dais-local",
        admission_db=ambiguous["admission_db"], api_key="test-only", apply=True,
    )
    assert result["status"] != "resolved"
    assert not ambiguous["ledger"].exists()

    mismatched = _native_carousel_recovery_fixture(tmp_path / "mismatch", monkeypatch, corrupt_media=True)
    result = reconcile.reconcile_pending_owner(
        owner_id=mismatched["owner"], identity_dir=mismatched["identity_dir"],
        data_dir=mismatched["data_dir"], tenant_id="dais-local",
        admission_db=mismatched["admission_db"], api_key="test-only", apply=True,
    )
    assert result["status"] != "resolved"
    assert not mismatched["ledger"].exists()
    with sqlite3.connect(mismatched["admission_db"]) as connection:
        assert connection.execute(
            "SELECT state,effect_unknown FROM occurrences WHERE occurrence_id=?",
            (mismatched["identity"]["occurrence_id"],),
        ).fetchone() == ("claimed", 1)


def _identity_for_neighbor_slot(identity, *, run_id, slot):
    value = dict(identity)
    value["runtime_run_id"] = run_id
    value["occurrence_id"] = f'{identity["loop_id"]}:{run_id}'
    value["job_id"] = f"marketing-native-carousel-publication:job-{run_id}"
    value["slot"] = slot
    value["effect_key"] = ":".join((
        "marketing", "carousel", value["product_id"], value["creative_id"],
        value["pack_sha256"], value["media_order_sha256"], value["caption_sha256"],
        hashlib.sha256(slot.encode()).hexdigest(),
    ))
    return value


def _store_pending_identity(fixture, identity):
    path = fixture["identity_dir"] / f'{identity["runtime_run_id"]}.jsonl'
    path.write_text(json.dumps(identity) + "\n", encoding="utf-8")
    path.chmod(0o600)
    with sqlite3.connect(fixture["admission_db"]) as connection:
        connection.execute(
            "INSERT INTO occurrences VALUES (?, ?, 'claimed', 1)",
            (identity["loop_id"], identity["occurrence_id"]),
        )


@pytest.mark.parametrize("variant", ["format_id", "pack_metadata"])
def test_native_carousel_recovery_refuses_candidate_shared_with_neighbor_slot(tmp_path, monkeypatch, variant):
    fixture = _native_carousel_recovery_fixture(tmp_path, monkeypatch)
    neighbor = _identity_for_neighbor_slot(
        fixture["identity"], run_id="run-2", slot="2026-10-07T09:10:00.000Z",
    )
    if variant == "format_id":
        neighbor["format_id"] = "alternate-format"
    else:
        pack = {"slides": [{"text": "Exact title"}, *({"text": f"Slide {index}"} for index in range(2, 7))], "metadata": "alternate"}
        payload = json.dumps(pack, separators=(",", ":")).encode()
        pack_sha = hashlib.sha256(payload).hexdigest()
        pack_path = fixture["data_dir"] / "objects" / "sha256" / pack_sha
        pack_path.write_bytes(payload)
        pack_path.chmod(0o600)
        neighbor["pack_sha256"] = pack_sha
        neighbor["effect_key"] = ":".join((
            "marketing", "carousel", neighbor["product_id"], neighbor["creative_id"],
            pack_sha, neighbor["media_order_sha256"], neighbor["caption_sha256"],
            hashlib.sha256(neighbor["slot"].encode()).hexdigest(),
        ))
    _store_pending_identity(fixture, neighbor)
    resolved = []
    monkeypatch.setattr(reconcile, "resolve_unknown_occurrence", lambda **kwargs: resolved.append(kwargs["occurrence_id"]) or True)

    result = reconcile.reconcile_pending_owner(
        owner_id=fixture["owner"], identity_dir=fixture["identity_dir"],
        data_dir=fixture["data_dir"], tenant_id="dais-local",
        admission_db=fixture["admission_db"], api_key="test-only", apply=True,
    )

    assert result["status"] != "resolved"
    assert resolved == []
    assert not fixture["ledger"].exists()


def test_pending_owner_stops_after_one_resolver_rejection(tmp_path, monkeypatch):
    fixture = _native_carousel_recovery_fixture(tmp_path, monkeypatch)
    neighbor = _identity_for_neighbor_slot(
        fixture["identity"], run_id="run-2", slot="2026-10-07T14:00:00.000Z",
    )
    _store_pending_identity(fixture, neighbor)
    attempted = []

    def reject_once(**kwargs):
        proof = kwargs["official_readback"]()
        assert proof["provider_receipt_id"] == fixture["provider_id"]
        attempted.append(kwargs["occurrence_id"])
        return False

    monkeypatch.setattr(reconcile, "resolve_unknown_occurrence", reject_once)
    result = reconcile.reconcile_pending_owner(
        owner_id=fixture["owner"], identity_dir=fixture["identity_dir"],
        data_dir=fixture["data_dir"], tenant_id="dais-local",
        admission_db=fixture["admission_db"], api_key="test-only", apply=True,
    )

    assert result["reason"] == "resolve_rejected"
    assert result["resolution_attempted"] is True
    assert result["inspected"] == 1
    assert attempted == [fixture["identity"]["occurrence_id"]]


def test_nested_distribution_receipt_cannot_reuse_provider_post_id(tmp_path):
    ledger = tmp_path / "distribution.jsonl"
    first = {
        "effect_key": "effect-one", "job_id": "job-one",
        "receipt": {"provider_post_id": "post-photo-1", "status": "published"},
    }
    second = {
        "effect_key": "effect-two", "job_id": "job-two",
        "receipt": {"provider_post_id": "post-photo-1", "status": "published"},
    }
    error_type = reconcile.append_distribution_row.__globals__["DistributionError"]

    reconcile.append_distribution_row(ledger, first)
    with pytest.raises(error_type, match="provider post ID"):
        reconcile.append_distribution_row(ledger, second)
    rows = reconcile._safe_jsonl(ledger)
    assert rows is not None and rows == [first]


# ---- historical no-dispatch (identity-less fences) -------------------------------------------

def _hist_db(tmp_path, owner, rows):
    db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE occurrences (owner_id TEXT, occurrence_id TEXT, state TEXT, "
                  "effect_unknown INTEGER, queued_at REAL)")
        c.executemany("INSERT INTO occurrences VALUES (?,?,?,?,?)",
                      [(owner, oid, "claimed", 1, ts) for oid, ts in rows])
    return db


def _hist_identity_dir(tmp_path, owner, refs):
    d = tmp_path / "effect-identities"
    d.mkdir()
    for n, ref in enumerate(refs):
        f = d / f"run-{n}.jsonl"
        f.write_text(json.dumps({"kind": "life_manager_effect_identity", "loop_id": owner,
                                 "occurrence_id": f"{owner}:old-{n}", "integration_ref": ref}) + "\n")
        f.chmod(0o600)
    return d


def test_historical_no_dispatch_proof_requires_zero_posts_in_the_window_for_the_one_integration(tmp_path):
    owner = "life-manager-anicca-main-tiktok"
    ts = 1_790_000_000.0
    db = _hist_db(tmp_path, owner, [(f"{owner}:gone", ts)])
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmx1"] * 2)
    seen = {}

    def posts(integration_id, start, end, api_key):
        seen["call"] = (integration_id, start, end)
        return []

    proofs = reconcile.build_historical_no_dispatch_proof(
        owner, f"{owner}:gone", queued_at=ts, identity_dir=idir, api_key="k",
        list_posts=posts, window_seconds=1800)
    assert proofs["verified"] is True
    assert proofs["proof_type"] == "historical_integration_bound_no_dispatch"
    assert proofs["provider"] == "postiz" and proofs["historical_integration_id"] == "cmx1"
    assert "count=0" in proofs["evidence_ref"]
    from datetime import datetime
    parse = lambda v: datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ")
    assert seen["call"][0] == "cmx1"
    assert (parse(seen["call"][2]) - parse(seen["call"][1])).total_seconds() == 3600


def test_historical_no_dispatch_never_closes_when_a_post_exists_or_the_integration_is_ambiguous(tmp_path):
    owner = "life-manager-anicca-main-tiktok"
    ts = 1_790_000_000.0
    one = _hist_identity_dir(tmp_path / "a", owner, ["integration://postiz/tiktok/cmx1"]) \
        if (tmp_path / "a").mkdir() is None else None
    two = _hist_identity_dir(tmp_path / "b", owner, ["integration://postiz/tiktok/cmx1",
                                                     "integration://postiz/tiktok/cmx2"]) \
        if (tmp_path / "b").mkdir() is None else None
    kw = dict(queued_at=ts, api_key="k", window_seconds=1800)
    assert reconcile.build_historical_no_dispatch_proof(
        owner, f"{owner}:x", identity_dir=one, list_posts=lambda *a: [{"id": "p1"}], **kw) is None
    assert reconcile.build_historical_no_dispatch_proof(
        owner, f"{owner}:x", identity_dir=two, list_posts=lambda *a: [], **kw) is None

    def boom(*a):
        raise OSError("postiz down")
    assert reconcile.build_historical_no_dispatch_proof(
        owner, f"{owner}:x", identity_dir=one, list_posts=boom, **kw) is None


def test_historical_sweep_closes_only_proven_occurrences_and_only_when_asked_to_resolve(tmp_path):
    owner = "life-manager-anicca-main-tiktok"
    t0 = 1_790_000_000.0
    rows = [(f"{owner}:a", t0), (f"{owner}:b", t0 + 7200), (f"{owner}:c", t0 + 14400)]
    db = _hist_db(tmp_path, owner, rows)
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmx1"])
    closed = []

    def posts(integration_id, start, end, api_key):
        return [{"id": "p"}] if "T" in start and start.startswith(
            reconcile.datetime.fromtimestamp(t0 + 7200 - 1800, reconcile.timezone.utc).strftime("%Y-%m-%dT%H")) else []

    def resolver(owner_id, occurrence_id, *, no_dispatch_proof, expected_state="claimed"):
        assert no_dispatch_proof()["verified"] is True
        closed.append(occurrence_id)
        return True

    dry = reconcile.sweep_historical_no_dispatch(
        owner, identity_dir=idir, admission_db=db, api_key="k", apply=False,
        list_posts=posts, resolver=resolver, max_items=10)
    assert closed == [] and dry["provable"] == 2 and dry["kept"] == 1 and dry["resolved"] == 0

    done = reconcile.sweep_historical_no_dispatch(
        owner, identity_dir=idir, admission_db=db, api_key="k", apply=True,
        list_posts=posts, resolver=resolver, max_items=10)
    assert sorted(closed) == [f"{owner}:a", f"{owner}:c"] and done["resolved"] == 2 and done["kept"] == 1


def test_historical_sweep_respects_the_item_cap(tmp_path):
    owner = "life-manager-anicca-main-tiktok"
    t0 = 1_790_000_000.0
    db = _hist_db(tmp_path, owner, [(f"{owner}:{n}", t0 + n * 7200) for n in range(6)])
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmx1"])
    out = reconcile.sweep_historical_no_dispatch(
        owner, identity_dir=idir, admission_db=db, api_key="k", apply=False,
        list_posts=lambda *a: [], resolver=lambda *a, **k: True, max_items=4)
    assert out["inspected"] == 4


def test_historical_flag_runs_the_sweep_and_prints_a_summary(tmp_path, monkeypatch, capsys):
    owner = "life-manager-anicca-main-tiktok"
    db = _hist_db(tmp_path, owner, [(f"{owner}:a", 1_790_000_000.0)])
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmx1"])
    monkeypatch.setattr(reconcile, "_postiz_posts_between", lambda *a: [])
    monkeypatch.setattr(reconcile, "sweep_historical_no_dispatch", lambda owner_id, **kw: {
        "status": "swept", "owner_id": owner_id, "applied": kw["apply"], "inspected": 1})
    code = reconcile.main(["--auto-owner", owner, "--historical-no-dispatch",
                           "--identity-dir", str(idir), "--admission-db", str(db)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["applied"] is False and out["owner_id"] == owner


def test_per_occurrence_call_without_resolve_never_sweeps(tmp_path, monkeypatch, capsys):
    owner = "life-manager-anicca-main-tiktok"
    db = _hist_db(tmp_path, owner, [(f"{owner}:a", 1_790_000_000.0)])
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmx1"])
    monkeypatch.setattr(reconcile, "sweep_historical_no_dispatch",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not sweep")))
    monkeypatch.delenv("LIFE_MANAGER_OCCURRENCE_ID", raising=False)
    reconcile.main(["--auto-owner", owner, "--occurrence-id", f"{owner}:a",
                    "--identity-dir", str(idir), "--admission-db", str(db)])
    assert json.loads(capsys.readouterr().out)["status"] == "inconclusive"


def test_sweep_goes_newest_first_and_never_touches_fences_younger_than_the_safety_margin(tmp_path):
    """Oldest-first stalled: the oldest windows genuinely contain posts, so the same 25 were
    kept every call. Newest-first (older than the margin) reaches provable windows, and a fence
    younger than the margin may belong to a run that is still going."""
    import time
    owner = "life-manager-anicca-main-tiktok"
    now = time.time()
    rows = [(f"{owner}:old", now - 40 * 3600), (f"{owner}:mid", now - 20 * 3600),
            (f"{owner}:young", now - 1 * 3600)]
    db = _hist_db(tmp_path, owner, rows)
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmx1"])
    seen = []

    def resolver(owner_id, occurrence_id, *, no_dispatch_proof, expected_state="claimed"):
        seen.append(occurrence_id)
        return True

    out = reconcile.sweep_historical_no_dispatch(
        owner, identity_dir=idir, admission_db=db, api_key="k", apply=True,
        list_posts=lambda *a: [], resolver=resolver, max_items=1)
    assert seen == [f"{owner}:mid"], seen          # newest that is older than the margin
    assert out["inspected"] == 1
    out2 = reconcile.sweep_historical_no_dispatch(
        owner, identity_dir=idir, admission_db=db, api_key="k", apply=True,
        list_posts=lambda *a: [], resolver=resolver, max_items=10)
    assert f"{owner}:young" not in seen


def test_api_key_is_read_from_marketing_env_only_when_the_environment_lacks_it(tmp_path, monkeypatch):
    """2026-10-09: the fence reconciler runs this adapter without the Postiz key, every readback
    failed closed and 30k Anicca fences stayed open. mobile-app loads the key from marketing.env;
    do the same, narrowly: one exact LM_POSTIZ_API_KEY line, never `source`."""
    env = tmp_path / "marketing.env"
    env.write_text("OTHER=1\nLM_POSTIZ_API_KEY='abc123'\nexport EVIL=$(touch /tmp/pwned)\n")
    env.chmod(0o600)
    monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
    monkeypatch.delenv("LM_POSTIZ_API_KEY", raising=False)
    assert reconcile._postiz_api_key(env_file=env) == "abc123"
    monkeypatch.setenv("POSTIZ_API_KEY", "from-env")
    assert reconcile._postiz_api_key(env_file=env) == "from-env"


def test_api_key_loader_ignores_unsafe_or_missing_files(tmp_path, monkeypatch):
    monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
    monkeypatch.delenv("LM_POSTIZ_API_KEY", raising=False)
    assert reconcile._postiz_api_key(env_file=tmp_path / "missing.env") == ""
    world = tmp_path / "world.env"
    world.write_text("LM_POSTIZ_API_KEY=abc\n")
    world.chmod(0o644)
    assert reconcile._postiz_api_key(env_file=world) == ""


def _hist_db(tmp_path, owner, rows):
    db = tmp_path / "admission.sqlite3"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE occurrences (owner_id TEXT, occurrence_id TEXT, state TEXT, "
                  "effect_unknown INTEGER, queued_at REAL)")
        c.executemany("INSERT INTO occurrences VALUES (?,?,?,?,?)",
                      [(owner, oid, "claimed", 1, ts) for oid, ts in rows])
    return db


def _hist_identity_dir(tmp_path, owner, refs):
    d = tmp_path / "effect-identities"
    d.mkdir(exist_ok=True)
    for n, ref in enumerate(refs):
        f = d / f"run-{n}.jsonl"
        f.write_text(json.dumps({"kind": "life_manager_effect_identity", "loop_id": owner,
                                 "occurrence_id": f"{owner}:old-{n}", "integration_ref": ref}) + "\n")
        f.chmod(0o600)
    return d


def test_identity_less_fence_is_never_closed_by_a_time_window_alone(tmp_path, monkeypatch, capsys):
    """2026-10-09: a real post's slot sits 25 min to 30 h after the occurrence's queued_at
    (p50 ~7 h), so 'no post within +-30 min' proves nothing.  316 fences were closed on that
    proof before it was caught.  Until a proof bound to the occurrence itself exists, the
    per-occurrence call must NOT sweep, even with --resolve."""
    owner = "life-manager-anicca-main-tiktok"
    db = _hist_db(tmp_path, owner, [(f"{owner}:a", 1_790_000_000.0)])
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmx1"])
    monkeypatch.setattr(reconcile, "sweep_historical_no_dispatch",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not sweep")))
    monkeypatch.delenv("LIFE_MANAGER_OCCURRENCE_ID", raising=False)
    reconcile.main(["--auto-owner", owner, "--occurrence-id", f"{owner}:a", "--resolve",
                    "--identity-dir", str(idir), "--admission-db", str(db)])
    assert json.loads(capsys.readouterr().out)["status"] == "inconclusive"


def test_historical_sweep_cli_flag_refuses_to_resolve(tmp_path, capsys):
    owner = "life-manager-anicca-main-tiktok"
    db = _hist_db(tmp_path, owner, [(f"{owner}:a", 1_790_000_000.0)])
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmx1"])
    code = reconcile.main(["--auto-owner", owner, "--historical-no-dispatch", "--resolve",
                           "--identity-dir", str(idir), "--admission-db", str(db)])
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["status"] == "inconclusive" and out["reason"] == "historical_window_proof_unsound"
