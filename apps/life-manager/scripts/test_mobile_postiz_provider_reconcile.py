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
        "publishDate": "2026-10-07T00:00:00.000Z",
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


def test_provider_readback_rejects_conflicting_video_hash_fields(monkeypatch):
    integration_id = "cmn8y95rg02d2qx0y09bbk5pb"
    provider_id = "anicca-reel-456"
    caption = "An exact provider caption.\n"
    video_sha = "c" * 64
    identity = {
        "product_id": "anicca-ios",
        "format_id": "reelclaw-widget",
        "form": "lockscreen-affirmation-widget",
        "locale": "en",
        "creative_id": "EN-WIDGET-SELF-TALK-c20f73dbbfe5-20261013T223000000Z",
        "platform": "instagram",
        "account_id": "@anicca.en",
        "integration_ref": f"integration://postiz/instagram/{integration_id}",
        "caption_sha256": hashlib.sha256(caption.encode()).hexdigest(),
        "video_sha256": video_sha,
    }
    provider_row = {
        "id": provider_id,
        "state": "PUBLISHED",
        "releaseURL": "https://www.instagram.com/reel/anicca456",
        "integration": {"id": integration_id},
        "content": caption,
        "lifeManagerVideoSha256": video_sha,
        "video_sha256": "d" * 64,
    }

    def request(url, _key):
        if url == f"{reconcile.POSTIZ_DETAILS}/{provider_id}":
            return provider_row
        if url == f"{reconcile.POSTIZ_V1}/integrations":
            return {"integrations": [{
                "id": integration_id,
                "identifier": "instagram-standalone",
                "profile": "@anicca.en",
            }]}
        raise AssertionError(f"unexpected Postiz readback URL: {url}")

    monkeypatch.setattr(reconcile, "_request_json", request)

    with pytest.raises(ValueError, match="Postiz video hash mismatch"):
        reconcile._provider_readback(identity, provider_id, "test-only")


def _anicca_remote_video_case(
    tmp_path, monkeypatch, *, publish_date="2026-10-14T00:39:00.000Z",
    duplicate_identity=False,
):
    data_dir = tmp_path / "data"
    slot = "2026-10-13T22:30:00.000Z"
    caption = "I meet myself with kindness.\n"
    caption_sha = hashlib.sha256(caption.encode()).hexdigest()
    video_sha = "a" * 64
    caption_object = data_dir / "objects" / "sha256" / caption_sha
    caption_object.parent.mkdir(parents=True)
    caption_object.write_text(caption, encoding="utf-8")
    caption_object.chmod(0o600)
    ledger = (
        data_dir / "tenants" / "dais-local" / "marketing" / "video-publication"
        / "anicca-ios" / "distribution.jsonl"
    )
    ledger.parent.mkdir(parents=True)
    ledger.write_text("", encoding="utf-8")
    ledger.chmod(0o600)
    identity_dir = data_dir / "marketing" / "effects"
    identity_dir.mkdir(parents=True)
    integration_id = "cmn8y95rg02d2qx0y09bbk5pb"
    provider_id = "anicca-reel-123"
    owner_id = "life-manager-anicca-en-widget-instagram"
    occurrence_id = f"{owner_id}:run-1"
    creative_id = "EN-WIDGET-SELF-TALK-c20f73dbbfe5-20261013T223000000Z"
    identity = {
        "schema_version": 1,
        "kind": "life_manager_effect_identity",
        "runtime_run_id": "run-1",
        "occurrence_id": occurrence_id,
        "loop_id": owner_id,
        "job_id": "marketing-video-publication:job-1",
        "product_id": "anicca-ios",
        "format_id": "reelclaw-widget",
        "form": "lockscreen-affirmation-widget",
        "locale": "en",
        "creative_id": creative_id,
        "platform": "instagram",
        "account_id": "@anicca.en",
        "integration_ref": f"integration://postiz/instagram/{integration_id}",
        "slot": slot,
        "effect_key": (
            f"marketing:video:anicca-ios:instagram:{creative_id}:{video_sha}:{caption_sha}:"
            f"{hashlib.sha256(slot.encode()).hexdigest()}"
        ),
        "caption_sha256": caption_sha,
        "video_sha256": video_sha,
    }
    identity_path = identity_dir / "run-1.jsonl"
    identity_path.write_text(json.dumps(identity) + "\n", encoding="utf-8")
    identity_path.chmod(0o600)
    if duplicate_identity:
        duplicate = {
            **identity,
            "runtime_run_id": "run-2",
            "occurrence_id": f"{owner_id}:run-2",
            "job_id": "marketing-video-publication:job-2",
        }
        duplicate_path = identity_dir / "run-2.jsonl"
        duplicate_path.write_text(json.dumps(duplicate) + "\n", encoding="utf-8")
        duplicate_path.chmod(0o600)
    provider_row = {
        "id": provider_id,
        "state": "PUBLISHED",
        "releaseURL": "https://www.instagram.com/reel/anicca123",
        "integration": {"id": integration_id},
        "content": caption,
    }
    if publish_date is not None:
        provider_row["publishDate"] = publish_date

    def request(url, _key):
        if url.startswith(f"{reconcile.POSTIZ_V1}/posts?"):
            return {"posts": [provider_row]}
        if url == f"{reconcile.POSTIZ_DETAILS}/{provider_id}":
            return provider_row
        if url == f"{reconcile.POSTIZ_V1}/integrations":
            return {"integrations": [{
                "id": integration_id,
                "identifier": "instagram-standalone",
                "profile": "@anicca.en",
            }]}
        raise AssertionError(f"unexpected Postiz readback URL: {url}")

    monkeypatch.setattr(reconcile, "_request_json", request)
    return identity, ledger, identity_dir, provider_row, provider_id


def test_remote_anicca_video_receipt_recovers_unique_exact_post_without_local_row(tmp_path, monkeypatch):
    identity, ledger, identity_dir, _provider_row, provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )

    proof = reconcile.build_official_proof(
        identity, ledger, "test-only", identity_dir=identity_dir,
    )

    assert proof["provider_receipt_id"] == provider_id
    assert proof["provider_readback"]["account_id"] == "@anicca.en"
    assert proof["provider_readback"]["remote_effect_locator"]["integration_id"] == (
        "cmn8y95rg02d2qx0y09bbk5pb"
    )


def test_legacy_local_anicca_video_receipt_without_publish_time_still_reads_back(
    tmp_path, monkeypatch,
):
    identity, ledger, identity_dir, _provider_row, provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    receipt = {
        "schema_version": 1,
        "kind": "marketing_video_distribution",
        "status": "published",
        "product_id": identity["product_id"],
        "format_id": identity["format_id"],
        "form": identity["form"],
        "locale": identity["locale"],
        "creative_id": identity["creative_id"],
        "platform": identity["platform"],
        "account_id": identity["account_id"],
        "integration_ref": identity["integration_ref"],
        "slot": identity["slot"],
        "caption_sha256": identity["caption_sha256"],
        "video_sha256": identity["video_sha256"],
        "provider_post_id": provider_id,
        "provider_reconciled": True,
        "remote_effect_locator": {
            "source": "postiz_public_v1_posts",
            "post_id": provider_id,
            "integration_id": identity["integration_ref"].rsplit("/", 1)[-1],
            "caption_sha256": identity["caption_sha256"],
            "slot": identity["slot"],
        },
    }
    ledger.write_text(json.dumps({"effect_key": identity["effect_key"], "job_id": identity["job_id"], "receipt": receipt}) + "\n", encoding="utf-8")

    proof = reconcile.build_official_proof(
        identity, ledger, "test-only", identity_dir=identity_dir,
    )

    assert proof["provider_receipt_id"] == provider_id
    assert proof["provider_readback"]["state"] == "PUBLISHED"


@pytest.mark.parametrize("entrypoint", ["pending_owner", "current_occurrence"])
def test_anicca_video_receipt_recovery_is_reached_from_reconciler_entrypoints(
    tmp_path, monkeypatch, entrypoint,
):
    identity, _ledger, identity_dir, _provider_row, provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    data_dir = tmp_path / "data"
    admission_db = tmp_path / "admission.sqlite3"
    monkeypatch.setattr(reconcile, "_pending_unknown_count", lambda *_args: 1)
    monkeypatch.setattr(reconcile, "_admission_state", lambda *_args: ("claimed", 1))
    monkeypatch.setattr(
        reconcile, "_authoritative_admission_db", lambda: admission_db.resolve(),
    )

    if entrypoint == "pending_owner":
        result = reconcile.reconcile_pending_owner(
            owner_id=identity["loop_id"], identity_dir=identity_dir,
            data_dir=data_dir, tenant_id="dais-local", admission_db=admission_db,
            api_key="test-only", apply=False,
        )
    else:
        result = reconcile.reconcile_current_occurrence(
            owner_id=identity["loop_id"], occurrence_id=identity["occurrence_id"],
            identity_dir=identity_dir, data_dir=data_dir, tenant_id="dais-local",
            admission_db=admission_db, api_key="test-only", apply=False,
        )

    assert result["status"] == "ready"
    assert result["provider_receipt_id"] == provider_id


def test_remote_anicca_video_receipt_accepts_complete_100_row_post_list(tmp_path, monkeypatch):
    identity, ledger, identity_dir, _provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json
    post_list_urls = []

    def saturated_request(url, api_key):
        payload = request(url, api_key)
        if url.startswith(f"{reconcile.POSTIZ_V1}/posts?"):
            post_list_urls.append(url)
            payload = dict(payload)
            payload["posts"] = [
                *payload["posts"],
                *({
                    "id": f"unrelated-post-{index}",
                    "integration": {"id": "another-integration"},
                    "publishDate": "2026-10-14T00:39:00.000Z",
                } for index in range(99)),
            ]
        return payload

    monkeypatch.setattr(reconcile, "_request_json", saturated_request)

    proof = reconcile.build_official_proof(
        identity, ledger, "test-only", identity_dir=identity_dir,
    )

    assert proof["provider_receipt_id"] == _provider_id
    assert len(post_list_urls) == 1
    assert "limit=" not in post_list_urls[0]


@pytest.mark.parametrize("unknown_date", [None, "not-a-date", "2026-10-14T00:39:00"])
def test_remote_anicca_video_receipt_rejects_matching_row_with_unknown_date(
    tmp_path, monkeypatch, unknown_date,
):
    identity, ledger, identity_dir, provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json

    def unknown_date_request(url, api_key):
        payload = request(url, api_key)
        if url.startswith(f"{reconcile.POSTIZ_V1}/posts?"):
            payload = dict(payload)
            conflicting_row = {**provider_row, "id": "anicca-reel-duplicate"}
            if unknown_date is None:
                conflicting_row.pop("publishDate", None)
            else:
                conflicting_row["publishDate"] = unknown_date
            payload["posts"] = [*payload["posts"], conflicting_row]
        return payload

    monkeypatch.setattr(reconcile, "_request_json", unknown_date_request)

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_non_object_list_entry(tmp_path, monkeypatch):
    identity, ledger, identity_dir, _provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json

    def malformed_list_request(url, api_key):
        payload = request(url, api_key)
        if url.startswith(f"{reconcile.POSTIZ_V1}/posts?"):
            payload = dict(payload)
            payload["posts"] = [*payload["posts"], None]
        return payload

    monkeypatch.setattr(reconcile, "_request_json", malformed_list_request)

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


@pytest.mark.parametrize(
    "detail_publish_date",
    ["2026-10-14T01:39:00.000Z", "2026-10-15T10:31:00.000Z", None],
)
def test_remote_anicca_video_receipt_requires_detail_date_to_match_list_date(
    tmp_path, monkeypatch, detail_publish_date,
):
    identity, ledger, identity_dir, provider_row, provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json

    def conflicting_detail_request(url, api_key):
        if url == f"{reconcile.POSTIZ_DETAILS}/{provider_id}":
            detail = dict(provider_row)
            if detail_publish_date is None:
                detail.pop("publishDate", None)
            else:
                detail["publishDate"] = detail_publish_date
            return detail
        return request(url, api_key)

    monkeypatch.setattr(reconcile, "_request_json", conflicting_detail_request)

    with pytest.raises(ValueError, match="publish time"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


@pytest.mark.parametrize("publish_date", [None, "2026-10-15T10:31:00.000Z"])
def test_remote_anicca_video_receipt_requires_publish_date_inside_slot_window(
    tmp_path, monkeypatch, publish_date,
):
    identity, ledger, identity_dir, _provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch, publish_date=publish_date,
    )

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_conflicting_list_date_aliases(tmp_path, monkeypatch):
    identity, ledger, identity_dir, provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    provider_row["date"] = "2026-10-14T01:39:00.000Z"

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_null_list_date_alias(tmp_path, monkeypatch):
    identity, ledger, identity_dir, provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    provider_row["date"] = None

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_conflicting_detail_date_aliases(
    tmp_path, monkeypatch,
):
    identity, ledger, identity_dir, provider_row, provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json

    def conflicting_detail_request(url, api_key):
        if url == f"{reconcile.POSTIZ_DETAILS}/{provider_id}":
            return {**provider_row, "date": "2026-10-14T01:39:00.000Z"}
        return request(url, api_key)

    monkeypatch.setattr(reconcile, "_request_json", conflicting_detail_request)

    with pytest.raises(ValueError, match="publish time"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_null_detail_date_alias(
    tmp_path, monkeypatch,
):
    identity, ledger, identity_dir, provider_row, provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json

    def null_detail_date_request(url, api_key):
        if url == f"{reconcile.POSTIZ_DETAILS}/{provider_id}":
            return {**provider_row, "date": None}
        return request(url, api_key)

    monkeypatch.setattr(reconcile, "_request_json", null_detail_date_request)

    with pytest.raises(ValueError, match="publish time"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_conflicting_video_hash_fields(tmp_path, monkeypatch):
    identity, ledger, identity_dir, provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    provider_row["lifeManagerVideoSha256"] = identity["video_sha256"]
    provider_row["video_sha256"] = "b" * 64

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_conflicting_hash_on_competing_caption(
    tmp_path, monkeypatch,
):
    identity, ledger, identity_dir, provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json

    def competing_hash_request(url, api_key):
        payload = request(url, api_key)
        if url.startswith(f"{reconcile.POSTIZ_V1}/posts?"):
            payload = dict(payload)
            conflicting = {
                **provider_row,
                "id": "anicca-reel-conflicting-hash",
                "lifeManagerVideoSha256": "b" * 64,
            }
            payload["posts"] = [*payload["posts"], conflicting]
        return payload

    monkeypatch.setattr(reconcile, "_request_json", competing_hash_request)

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_same_id_at_multiple_publish_times(
    tmp_path, monkeypatch,
):
    identity, ledger, identity_dir, provider_row, provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json
    repeated_publish_date = "2026-10-15T00:39:00.000Z"

    def recurring_post_request(url, api_key):
        if url.startswith(f"{reconcile.POSTIZ_V1}/posts?"):
            payload = dict(request(url, api_key))
            repeated = {**provider_row, "publishDate": repeated_publish_date}
            payload["posts"] = [*payload["posts"], repeated]
            return payload
        if url == f"{reconcile.POSTIZ_DETAILS}/{provider_id}":
            return {**provider_row, "publishDate": repeated_publish_date}
        return request(url, api_key)

    monkeypatch.setattr(reconcile, "_request_json", recurring_post_request)

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_conflicting_list_integration_aliases(
    tmp_path, monkeypatch,
):
    identity, ledger, identity_dir, provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    provider_row["integrationId"] = "another-integration"

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_null_list_integration_alias(
    tmp_path, monkeypatch,
):
    identity, ledger, identity_dir, provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    provider_row["integrationId"] = None

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_conflicting_detail_integration_aliases(
    tmp_path, monkeypatch,
):
    identity, ledger, identity_dir, provider_row, provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json

    def conflicting_detail_request(url, api_key):
        if url == f"{reconcile.POSTIZ_DETAILS}/{provider_id}":
            return {**provider_row, "integrationId": "another-integration"}
        return request(url, api_key)

    monkeypatch.setattr(reconcile, "_request_json", conflicting_detail_request)

    with pytest.raises(ValueError, match="integration"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_null_detail_integration_alias(
    tmp_path, monkeypatch,
):
    identity, ledger, identity_dir, provider_row, provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json

    def null_detail_integration_request(url, api_key):
        if url == f"{reconcile.POSTIZ_DETAILS}/{provider_id}":
            return {**provider_row, "integrationId": None}
        return request(url, api_key)

    monkeypatch.setattr(reconcile, "_request_json", null_detail_integration_request)

    with pytest.raises(ValueError, match="integration"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_unverifiable_matching_list_row(
    tmp_path, monkeypatch,
):
    identity, ledger, identity_dir, provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    request = reconcile._request_json

    def uncertain_list_request(url, api_key):
        payload = request(url, api_key)
        if url.startswith(f"{reconcile.POSTIZ_V1}/posts?"):
            payload = dict(payload)
            uncertain_row = {
                **provider_row,
                "id": "anicca-reel-unknown",
                "lifeManagerVideoSha256": identity["video_sha256"],
            }
            uncertain_row.pop("state", None)
            uncertain_row.pop("releaseURL", None)
            payload["posts"] = [*payload["posts"], uncertain_row]
        return payload

    monkeypatch.setattr(reconcile, "_request_json", uncertain_list_request)

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_competing_identity_sidecar(tmp_path, monkeypatch):
    identity, ledger, identity_dir, _provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch, duplicate_identity=True,
    )

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


def test_remote_anicca_video_receipt_rejects_malformed_competing_sidecar(tmp_path, monkeypatch):
    identity, ledger, identity_dir, _provider_row, _provider_id = _anicca_remote_video_case(
        tmp_path, monkeypatch,
    )
    owner_id = identity["loop_id"]
    malformed = {
        **identity,
        "runtime_run_id": "run-2",
        "occurrence_id": f"{owner_id}:run-2",
        "job_id": "",
        "slot": "not-a-date",
    }
    sidecar = identity_dir / "malformed.jsonl"
    sidecar.write_text(json.dumps(malformed) + "\n", encoding="utf-8")
    sidecar.chmod(0o600)

    with pytest.raises(ValueError, match="receipt_missing_or_ambiguous"):
        reconcile.build_official_proof(
            identity, ledger, "test-only", identity_dir=identity_dir,
        )


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
        "publishDate": "2026-10-06T21:30:00.000Z",
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
        "publishDate": "2026-10-06T22:30:00.000Z",
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


def test_youtube_identity_from_existing_writer_accepts_its_exact_configured_postiz_profile():
    identity = {
        "platform": "youtube",
        "integration_ref": "integration://postiz/youtube/cmn8ymq6c02oio70y5ea1trv8",
        "account_id": "@anicca-affirmation-video",
    }

    assert "@anicca-affirmation-video" in reconcile._expected_postiz_profiles(identity)


def _native_carousel_recovery_fixture(tmp_path, monkeypatch, *, copies=1, corrupt_media=False, publish_date=None, platform="tiktok"):
    instagram = platform == "instagram"
    owner = "life-manager-anicca-en-affirmation-instagram" if instagram else "life-manager-anicca-jp1-tiktok"
    slot = "2026-10-07T09:00:00.000Z"
    integration_id = "cmp9pedr700ttqh0yj8o57fog" if instagram else "cmlrv8jq000hun60yy57eaptx"
    account_id = "@anicca.affirmation" if instagram else "@anicca.jp1"
    creative_id = "EN-AFFIRMATION-CAROUSEL-da8d8265" if instagram else "JA-LARRY-V1-JP1-test1"
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
            f"marketing:carousel:anicca-ios:{creative_id}:{pack_sha}:"
            f"{media_order_sha}:{caption_sha}:{hashlib.sha256(slot.encode()).hexdigest()}"
        ),
        "product_id": "anicca-ios",
        "format_id": "larry",
        "form": "affirmation-carousel",
        "locale": "en" if instagram else "ja",
        "platform": platform,
        "creative_id": creative_id,
        "slot": slot,
        "integration_ref": f"integration://postiz/{platform}/{integration_id}",
        "account_id": account_id,
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
            "publishDate": publish_date or f"2026-10-07T09:0{index + 1}:00.000Z",
            "integration": {"id": integration_id},
            "content": caption,
        }
        posts.append(row)
        details[provider_id] = {
            **row,
            "image": json.dumps(images),
            "releaseId": "18158245894509101" if instagram else f"p_pub_url~v2.{12345 + index}",
            "releaseURL": "https://www.instagram.com/p/abc123/" if instagram else "https://www.tiktok.com/@anicca.jp1",
            "settings": json.dumps({"__type": "instagram-standalone", "post_type": "post"} if instagram else {
                "__type": "tiktok",
                "title": "Exact title",
                "content_posting_method": "DIRECT_POST",
            }),
        }

    request_urls = []
    integration = {
        "id": integration_id,
        "identifier": "instagram-standalone" if instagram else "tiktok",
        "profile": "anicca.ios" if instagram else "anicca.jpx",
    }

    def request_json(url, _api_key):
        request_urls.append(url)
        if url.startswith(f"{reconcile.POSTIZ_V1}/posts?"):
            return {"posts": posts}
        if url == f"{reconcile.POSTIZ_V1}/integrations":
            return {"integrations": [integration]}
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
        if instagram and request.get_header("User-agent") != "postiz-cli":
            raise reconcile.urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        return FakeResponse(media_by_url[url], url)

    class PublishedPhotoAdapter:
        @staticmethod
        def find_post(rows, provider_id, platform):
            assert platform == "tiktok"
            return {"state": rows[0]["state"], "post_url": None}

    monkeypatch.setattr(reconcile, "_authoritative_admission_db", lambda: admission_db.resolve())
    monkeypatch.setattr(reconcile, "_request_json", request_json)
    if not instagram:
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
        "posts": posts,
        "details": details,
        "integration": integration,
    }


@pytest.mark.parametrize("profile", ["anicca.ios", "anicca.affirmation"])
def test_exact_instagram_carousel_recovers_standard_receipt_without_resending(tmp_path, monkeypatch, profile):
    fixture = _native_carousel_recovery_fixture(
        tmp_path, monkeypatch, platform="instagram", publish_date="2026-10-07T11:52:00.000Z",
    )
    fixture["integration"]["profile"] = profile
    identity = fixture["identity"]
    result = reconcile.reconcile_current_occurrence(
        owner_id=fixture["owner"], occurrence_id=identity["occurrence_id"],
        identity_dir=fixture["identity_dir"], data_dir=fixture["data_dir"], tenant_id="dais-local",
        admission_db=fixture["admission_db"], api_key="test-only", apply=False,
    )

    assert result["status"] == "ready", result
    assert result["verified"] is True
    assert result["provider_receipt_id"] == "post-photo-1"
    assert reconcile._READ_ONLY.evaluate_proof(identity, result)["status"] == "ready"
    assert not fixture["ledger"].exists()
    with sqlite3.connect(fixture["admission_db"]) as connection:
        assert connection.execute("SELECT state,effect_unknown FROM occurrences").fetchall() == [("claimed", 1)]
    recovered = reconcile._recovered_distribution_row(identity, result, fixture["ledger"])
    assert recovered["effect_key"] == identity["effect_key"]
    assert recovered["job_id"] == identity["job_id"]
    receipt = recovered["receipt"]
    assert receipt["kind"] == "marketing_native_carousel_distribution"
    assert receipt["public_url"] == "https://www.instagram.com/p/abc123/"
    assert receipt["media_sha256"] == fixture["media_sha"]
    assert "video_path" not in receipt
    node = shutil.which("node")
    assert node
    adapter_path = Path(reconcile.__file__).resolve().parents[1] / "lib" / "marketing-native-carousel-publication-adapter.js"
    checked = subprocess.run(
        [node, "-e", "const a=require(process.argv[1]);process.exit(a.verifyMarketingNativeCarouselPublicationReceipt(JSON.parse(process.argv[2]))?0:1)",
         str(adapter_path), json.dumps(receipt)], capture_output=True, text=True, check=False,
    )
    assert checked.returncode == 0, checked.stderr or checked.stdout
    reconcile._persist_recovered_distribution_row(identity, result, fixture["ledger"])
    reconcile._persist_recovered_distribution_row(identity, result, fixture["ledger"])
    stored = reconcile._safe_jsonl(fixture["ledger"])
    assert stored == [recovered]
    assert reconcile._local_receipt(identity, fixture["ledger"])[1] == "post-photo-1"


@pytest.mark.parametrize("change", ["caption", "integration", "media_order", "profile", "platform", "reel_url"])
def test_instagram_carousel_recovery_refuses_changed_provider_identity(tmp_path, monkeypatch, change):
    fixture = _native_carousel_recovery_fixture(tmp_path, monkeypatch, platform="instagram")
    detail = fixture["details"]["post-photo-1"]
    if change == "caption":
        detail["content"] = "Different caption"
    elif change == "integration":
        detail["integration"] = {"id": "another-integration"}
    elif change == "media_order":
        detail["image"] = json.dumps(list(reversed(json.loads(detail["image"]))))
    elif change == "profile":
        fixture["integration"]["profile"] = "anicca.jpx"
    elif change == "platform":
        fixture["integration"]["identifier"] = "tiktok"
    else:
        detail["releaseURL"] = "https://www.instagram.com/reel/abc123/"

    result = reconcile.verify_official_postiz_receipt(
        fixture["identity"], fixture["ledger"], "test-only", identity_dir=fixture["identity_dir"],
    )

    assert result["status"] == "inconclusive"
    assert not fixture["ledger"].exists()


def test_postiz_detail_get_accepts_proxy_requiring_cli_user_agent(monkeypatch):
    url = reconcile.POSTIZ_DETAILS + "/post-1"

    def urlopen(request, timeout):
        assert request.full_url == url
        assert request.get_method() == "GET"
        assert timeout > 0
        if request.get_header("User-agent") != "postiz-cli":
            raise reconcile.urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        return io.BytesIO(b'{"id":"post-1"}')

    monkeypatch.setattr(reconcile.urllib.request, "urlopen", urlopen)
    assert reconcile._request_json(url, "test-only") == {"id": "post-1"}


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

    assert result["status"] == "resolved"
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


def test_native_carousel_recovers_exact_same_day_late_catchup_post(tmp_path, monkeypatch):
    fixture = _native_carousel_recovery_fixture(
        tmp_path, monkeypatch, publish_date="2026-10-07T14:00:00.000Z",
    )
    result = reconcile.build_official_proof(
        fixture["identity"], fixture["ledger"], "test-only",
        identity_dir=fixture["identity_dir"],
    )

    assert result["verified"] is True, result
    assert result["provider_receipt_id"] == fixture["provider_id"]
    assert result["identity"] == fixture["identity"]
    assert result["provider_readback"]["published_at"] == "2026-10-07T14:00:00.000Z"


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


def test_native_carousel_late_publish_matches_only_the_same_jst_day():
    slot = reconcile.datetime.fromisoformat("2026-10-07T09:00:00.000Z")
    assert reconcile._native_carousel_publish_time_matches_slot(
        slot, reconcile.datetime.fromisoformat("2026-10-07T14:00:00.000Z"),
    )
    assert not reconcile._native_carousel_publish_time_matches_slot(
        slot, reconcile.datetime.fromisoformat("2026-10-07T15:01:00.000Z"),
    )
    assert not reconcile._native_carousel_publish_time_matches_slot(
        slot, reconcile.datetime.fromisoformat("2026-10-07T08:44:00.000Z"),
    )



def _claim_run_events(tmp_path, owner, occurrence, *, run="18dd-run", start="2026-10-09T03:55:50+00:00",
                      reports=1):
    events = tmp_path / "events.jsonl"
    rows = [{"owner_id": owner, "phase": "execute", "run_id": run,
             "occurrence_id": f"{owner}:{run}", "timestamp": start}]
    rows += [{"owner_id": owner, "phase": "report", "run_id": run, "occurrence_id": occurrence,
              "exit_code": 1, "effect_status": "unknown", "timestamp": start}] * reports
    events.write_text("".join(json.dumps(row) + "\n" for row in rows))
    events.chmod(0o600)
    return events


def _postiz_route_env(tmp_path, monkeypatch, owner, *, plist_env=None, ledger_rows=None, product="ebook-ja"):
    """Owner LaunchAgent, marketing.env and distribution ledger the route check reads."""
    import plistlib
    agents = tmp_path / "LaunchAgents"
    agents.mkdir(exist_ok=True)
    (agents / f"ai.anicca.life-manager-{owner}.plist").write_bytes(
        plistlib.dumps({"EnvironmentVariables": plist_env or {}}))
    marketing_env = tmp_path / "marketing.env"
    marketing_env.write_text("LM_POSTIZ_API_KEY=k\n")
    marketing_env.chmod(0o600)
    monkeypatch.setattr(reconcile, "LAUNCH_AGENTS", agents)
    monkeypatch.setattr(reconcile, "DEFAULT_MARKETING_ENV", marketing_env)
    monkeypatch.delenv("LM_TIKTOK_DIRECT_MIGRATION", raising=False)
    if ledger_rows is not None:
        ledger = (tmp_path / "tenants/dais-local/marketing/video-publication" / product
                  / "distribution.jsonl")
        ledger.parent.mkdir(parents=True)
        ledger.write_text("".join(json.dumps(row) + "\n" for row in ledger_rows))
        ledger.chmod(0o600)


def _identityless_kw(tmp_path, owner, occurrence, idir):
    return dict(owner_id=owner, occurrence_id=occurrence, identity_dir=idir, data_dir=tmp_path,
                tenant_id="dais-local", admission_db=tmp_path / "a.sqlite3", api_key="k")


def test_identityless_fence_closes_only_on_zero_posts_since_its_claim_run_started(tmp_path, monkeypatch):
    owner = "ebook-ja-tiktok-daily"
    occurrence = f"{owner}:18dc5e822e430b80-45345"
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmig"])
    _claim_run_events(tmp_path, owner, occurrence)
    _postiz_route_env(tmp_path, monkeypatch, owner, ledger_rows=[
        {"platform": "tiktok", "route": "tiktok_direct", "ts": "2026-10-07T07:03:41Z"},
        {"platform": "instagram", "route": "instagram_file_script", "ts": "2026-10-09T07:03:41Z"}])
    now = 1_791_600_000.0  # days after the claim run
    calls = []

    def posts(integration_id, start, end, api_key):
        calls.append((integration_id, start, end))
        if len(calls) == 1:  # the whole range overflows one page once: bisect, never day-by-day
            raise reconcile.PostizPageLimit("page limit")
        return []
    monkeypatch.setattr(reconcile, "_postiz_posts_between", posts)
    monkeypatch.setattr(reconcile, "_admission_state", lambda *_a: ("claimed", 1))
    monkeypatch.setattr(reconcile.time, "time", lambda: now)
    kw = _identityless_kw(tmp_path, owner, occurrence, idir)

    result = reconcile.reconcile_current_occurrence(apply=False, **kw)
    assert result["status"] == "ready"
    assert result["proof_type"] == "historical_integration_bound_no_dispatch"
    assert result["historical_integration_id"] == "cmig" and result["claim_run_id"] == "18dd-run"
    assert len(calls) == 3 and all(c[0] == "cmig" for c in calls)
    assert calls[0][1] == "2026-10-09T03:50:50Z" and calls[0][2] > "2026-10-16"
    assert calls[1][1] == calls[0][1] and calls[2][2] == calls[0][2] and calls[1][2] == calls[2][1]

    calls.clear()
    seen = {}
    monkeypatch.setattr(reconcile, "_authoritative_admission_db", lambda: (tmp_path / "a.sqlite3").resolve())
    monkeypatch.setattr(reconcile._resource_admission, "resolve_historical_no_dispatch_occurrence",
                        lambda o, occ, *, no_dispatch_proof, expected_state:
                        seen.update(proof=no_dispatch_proof(), state=expected_state) or True)
    result = reconcile.reconcile_current_occurrence(apply=True, **kw)
    assert result["status"] == "resolved" and seen["state"] == "claimed"
    assert seen["proof"]["occurrence_id"] == occurrence and seen["proof"]["verified"] is True
    assert len(calls) == 3  # the resolver reuses the proof; no second readback


def test_identityless_postiz_read_is_capped(tmp_path, monkeypatch):
    owner = "ebook-ja-tiktok-daily"
    occurrence = f"{owner}:18dc5e822e430b80-45345"
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmtt"])
    _claim_run_events(tmp_path, owner, occurrence)
    _postiz_route_env(tmp_path, monkeypatch, owner)
    calls = []

    def always_full(*a):
        calls.append(a)
        raise reconcile.PostizPageLimit("page limit")
    monkeypatch.setattr(reconcile, "_postiz_posts_between", always_full)
    monkeypatch.setattr(reconcile, "_admission_state", lambda *_a: ("claimed", 1))
    monkeypatch.setattr(reconcile.time, "time", lambda: 1_791_600_000.0)
    result = reconcile.reconcile_current_occurrence(apply=False, **_identityless_kw(tmp_path, owner, occurrence, idir))
    assert result["reason"] == "identity_missing_and_no_dispatch_unproven"
    assert len(calls) == reconcile.MAX_POSTIZ_READS


@pytest.mark.parametrize("case", [
    "post_after_claim", "deleted_post_listed_after_claim", "report_without_start", "too_recent", "no_integration",
    "no_run", "direct_migration_plist", "direct_migration_env", "direct_migration_marketing_env",
    "non_postiz_route_after_claim", "no_launch_agent",
])
def test_identityless_fence_stays_fenced_without_an_occurrence_bound_zero_post_proof(tmp_path, monkeypatch, case):
    owner = "ebook-ja-tiktok-daily"
    occurrence = f"{owner}:18dc5e822e430b80-45345"
    refs = [] if case == "no_integration" else ["integration://postiz/tiktok/cmtt"]
    idir = _hist_identity_dir(tmp_path, owner, refs)
    if case == "no_integration":  # no sidecar and no pack pin
        monkeypatch.setattr(reconcile, "EBOOK_PACKS_DIR", tmp_path / "no-packs")
    if case == "report_without_start":
        events = _claim_run_events(tmp_path, owner, occurrence)
        rows = [json.loads(line) for line in events.read_text().splitlines()]
        events.write_text("".join(json.dumps(row) + "\n" for row in rows if row["phase"] != "execute"))
    elif case != "no_run":
        _claim_run_events(tmp_path, owner, occurrence)
    _postiz_route_env(
        tmp_path, monkeypatch, owner,
        plist_env={"LM_TIKTOK_DIRECT_MIGRATION": "1"} if case == "direct_migration_plist" else None,
        ledger_rows=[{"platform": "tiktok", "route": "tiktok_direct", "ts": "2026-10-09T04:00:00Z"}]
        if case == "non_postiz_route_after_claim" else None)
    if case == "direct_migration_env":
        monkeypatch.setenv("LM_TIKTOK_DIRECT_MIGRATION", "1")
    if case == "direct_migration_marketing_env":
        reconcile.DEFAULT_MARKETING_ENV.write_text("LM_POSTIZ_API_KEY=k\nexport LM_TIKTOK_DIRECT_MIGRATION=1\n")
    if case == "no_launch_agent":
        for plist in reconcile.LAUNCH_AGENTS.iterdir():
            plist.unlink()
    now = 1_791_530_000.0 if case == "too_recent" else 1_791_600_000.0
    rows = {"post_after_claim": [{"id": "p"}],
            "deleted_post_listed_after_claim": [{"id": "p", "deletedAt": "2026-10-09T05:00:00Z"}]}.get(case, [])
    monkeypatch.setattr(reconcile, "_postiz_posts_between", lambda *a: rows)
    monkeypatch.setattr(reconcile, "_admission_state", lambda *_a: ("claimed", 1))
    monkeypatch.setattr(reconcile.time, "time", lambda: now)
    result = reconcile.reconcile_current_occurrence(
        apply=True, **_identityless_kw(tmp_path, owner, occurrence, idir))
    assert result["status"] == "inconclusive"
    assert result["reason"] == "identity_missing_and_no_dispatch_unproven"


@pytest.mark.parametrize("owner", ["life-manager-anicca-main-tiktok", "life-manager-honne-tiktok"])
def test_identityless_path_is_limited_to_postiz_only_ebook_owners(tmp_path, monkeypatch, owner):
    occurrence = f"{owner}:run-x"
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmtt"])
    _claim_run_events(tmp_path, owner, occurrence)
    _postiz_route_env(tmp_path, monkeypatch, owner)
    monkeypatch.setattr(reconcile, "_postiz_posts_between", lambda *a: pytest.fail("no Postiz read"))
    monkeypatch.setattr(reconcile, "_admission_state", lambda *_a: ("claimed", 1))
    monkeypatch.setattr(reconcile.time, "time", lambda: 1_791_600_000.0)
    result = reconcile.reconcile_current_occurrence(
        apply=False, **_identityless_kw(tmp_path, owner, occurrence, idir))
    assert result["reason"] == "identity_missing_or_invalid"
    assert set(reconcile.IDENTITYLESS_POSTIZ_OWNERS) == {
        "ebook-ja-tiktok-daily", "ebook-ja-instagram-daily", "ebook-en-instagram-daily",
        "ebook-en-tiktok-daily"}


@pytest.mark.parametrize("case", ["zero_posts", "post_after_claim", "file_script_after_claim"])
def test_identityless_ebook_instagram_fence_needs_zero_posts_on_its_own_integration(
        tmp_path, monkeypatch, case):
    # The eBook Instagram job always carries a Postiz integration ref (the adapter rejects a
    # job without one), so the file-script fallback is unreachable; a ledger row on any other
    # route after the claim still keeps the fence.
    owner = "ebook-ja-instagram-daily"
    occurrence = f"{owner}:18dc64be2b4087e0-5330"
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/instagram/cmig"])
    _claim_run_events(tmp_path, owner, occurrence, run="18dcc04408f9cac0-33517")
    rows = [{"platform": "instagram", "route": "instagram_file_script", "ts": "2026-10-07T07:03:41Z"}]
    if case == "file_script_after_claim":
        rows.append({"platform": "instagram", "route": "instagram_file_script", "ts": "2026-10-09T04:00:00Z"})
    _postiz_route_env(tmp_path, monkeypatch, owner, ledger_rows=rows)
    calls = []
    monkeypatch.setattr(reconcile, "_postiz_posts_between", lambda i, s, e, k: calls.append(i) or (
        [{"id": "p"}] if case == "post_after_claim" else []))
    monkeypatch.setattr(reconcile, "_admission_state", lambda *_a: ("claimed", 1))
    monkeypatch.setattr(reconcile.time, "time", lambda: 1_791_600_000.0)
    result = reconcile.reconcile_current_occurrence(
        apply=False, **_identityless_kw(tmp_path, owner, occurrence, idir))
    if case == "zero_posts":
        assert result["status"] == "ready" and result["occurrence_id"] == occurrence
        assert result["historical_integration_id"] == "cmig"
        assert result["claim_run_id"] == "18dcc04408f9cac0-33517" and calls == ["cmig"]
    else:
        assert result["status"] == "inconclusive"
        assert result["reason"] == "identity_missing_and_no_dispatch_unproven"


def _ebook_packs(tmp_path, monkeypatch, tiktok_integration="cmen"):
    packs = tmp_path / "ebook-packs"
    packs.mkdir()
    (packs / "ebook-en-anicca-monk.json").write_text(json.dumps({"product_id": "ebook-en", "accounts": [
        {"account_id": "tiktok.monk_anicca", "integration_id": tiktok_integration},
        {"account_id": "instagram.monk_anicca", "integration_id": None}]}))
    monkeypatch.setattr(reconcile, "EBOOK_PACKS_DIR", packs)


@pytest.mark.parametrize("case", ["died_without_report", "deferred_then_claimed", "sidecar_wins",
                                  "no_pack_integration", "post_after_claim"])
def test_identityless_ebook_en_tiktok_fence_uses_its_pack_integration_and_own_run_start(
        tmp_path, monkeypatch, case):
    # ebook-en-tiktok never wrote a sidecar, so its one Postiz integration comes from the pack the
    # job pins.  The window opens at the occurrence's own run, the earliest process that could act.
    owner = "ebook-en-tiktok-daily"
    own = "18ddc66eb902eba0-53359"
    occurrence = f"{owner}:{own}"
    idir = _hist_identity_dir(tmp_path, owner, ["integration://postiz/tiktok/cmside"]
                              if case == "sidecar_wins" else [])
    _ebook_packs(tmp_path, monkeypatch, None if case == "no_pack_integration" else "cmen")
    events = tmp_path / "events.jsonl"
    rows = [{"owner_id": owner, "phase": "execute", "run_id": own, "occurrence_id": occurrence,
             "timestamp": "2026-10-12T12:00:05+00:00"}]
    if case != "died_without_report":
        rows += [
            {"owner_id": owner, "phase": "report", "run_id": own, "occurrence_id": occurrence,
             "error_class": "host_admission_deferred:resource_capacity_busy", "exit_code": 75,
             "timestamp": "2026-10-12T12:00:09+00:00"},
            {"owner_id": owner, "phase": "execute", "run_id": "18ddd5e5-claim",
             "occurrence_id": f"{owner}:18ddd5e5-claim", "timestamp": "2026-10-12T16:43:28+00:00"},
            {"owner_id": owner, "phase": "report", "run_id": "18ddd5e5-claim", "occurrence_id": occurrence,
             "exit_code": 0, "timestamp": "2026-10-12T16:43:38+00:00"}]
    events.write_text("".join(json.dumps(row) + "\n" for row in rows))
    events.chmod(0o600)
    _postiz_route_env(tmp_path, monkeypatch, owner)
    calls = []
    monkeypatch.setattr(reconcile, "_postiz_posts_between", lambda i, s, e, k: calls.append((i, s)) or (
        [{"id": "p"}] if case == "post_after_claim" else []))
    monkeypatch.setattr(reconcile, "_admission_state", lambda *_a: ("claimed", 1))
    monkeypatch.setattr(reconcile.time, "time", lambda: 1_791_900_000.0)  # 2026-10-13
    result = reconcile.reconcile_current_occurrence(
        apply=False, **_identityless_kw(tmp_path, owner, occurrence, idir))
    if case in {"died_without_report", "deferred_then_claimed"}:
        assert result["status"] == "ready" and result["occurrence_id"] == occurrence
        assert result["historical_integration_id"] == "cmen"
        assert calls == [("cmen", "2026-10-12T11:55:05Z")]
        assert result["claim_run_id"] == (own if case == "died_without_report" else "18ddd5e5-claim")
    elif case == "sidecar_wins":
        assert result["status"] == "ready" and calls == [("cmside", "2026-10-12T11:55:05Z")]
    else:
        assert result["status"] == "inconclusive"
        assert result["reason"] == "identity_missing_and_no_dispatch_unproven"


# Retained, secret-free rows; fixture media and release bytes are isolated below.
_JATT_ORIGINAL_ROWS = json.loads('{"events":[{"blocker":null,"domain":"growth","effect_class":"publish","effect_status":"started","error_class":null,"event_id":"1794a0572e6285ff87038ae5","evidence_refs":["lm-loop://ebook-ja-tiktok-daily/18dfbf4b313011a8-82806/summary.json"],"exit_code":null,"failure_layer":"clean","job_id":"ebook-ja-tiktok-daily","loaded_argv_sha256":"3fbbb5030a25ee072b2780c91bdbfc57a62ce5e1321e47d1d56314bc8e61b0b2","loaded_env_sha256":"004a1c776ea2af56c7caaa5c4b62da81f4e2d6aeb31f476dbf005262b6cac586","loop_id":"ebook-ja-tiktok-daily","next_action":"monitor_running","occurrence_id":"ebook-ja-tiktok-daily:18dfbf4b313011a8-82806","official_readback_ref":null,"owner_id":"ebook-ja-tiktok-daily","phase":"execute","product_loop_id":"ebook","profile_alias":null,"provider":"deterministic","provider_receipt_id":null,"release_sha":"a7fb6c2822906102d7f453f03bacd8f7cfdaf169","retryable":false,"run_id":"18dfbf4b313011a8-82806","status":"running","timestamp":"2026-10-18T22:11:46.408424+00:00","version":1,"wake_id":"18dfbf4b313011a8-82806"},{"blocker":"host_admission_deferred:disk_floor_low","domain":"growth","effect_class":"publish","effect_identity_status":"not_written","effect_status":"unknown","error_class":"host_admission_deferred:disk_floor_low","event_id":"1bfe0270a14f2cc9528538a2","evidence_refs":["lm-loop://ebook-ja-tiktok-daily/18dfbf4b313011a8-82806/summary.json"],"exit_code":75,"failure_layer":"admission","job_id":"ebook-ja-tiktok-daily","loaded_argv_sha256":"3fbbb5030a25ee072b2780c91bdbfc57a62ce5e1321e47d1d56314bc8e61b0b2","loaded_env_sha256":"004a1c776ea2af56c7caaa5c4b62da81f4e2d6aeb31f476dbf005262b6cac586","loop_id":"ebook-ja-tiktok-daily","next_action":"retry_after_eligibility","occurrence_id":"ebook-ja-tiktok-daily:18dfbf4b313011a8-82806","official_readback_ref":null,"owner_id":"ebook-ja-tiktok-daily","phase":"report","product_loop_id":"ebook","profile_alias":null,"provider":"deterministic","provider_receipt_id":null,"release_sha":"a7fb6c2822906102d7f453f03bacd8f7cfdaf169","retryable":true,"run_id":"18dfbf4b313011a8-82806","status":"blocked","timestamp":"2026-10-18T22:11:46.606824+00:00","version":1,"wake_id":"18dfbf4b313011a8-82806"},{"blocker":null,"domain":"growth","effect_class":"publish","effect_status":"started","error_class":null,"event_id":"1a8c06ff46364663b0b02626","evidence_refs":["lm-loop://ebook-ja-tiktok-daily/18dff3a41b433450-51537/summary.json"],"exit_code":null,"failure_layer":"clean","job_id":"ebook-ja-tiktok-daily","loaded_argv_sha256":"7d0e652483120fa9eb582add850c17c30285e76b44815c444a5a305f61bcdc9d","loaded_env_sha256":"d5490e52d7302ccf5fce9ff207c8ad560fffbe094debf00926505e0107b482fc","loop_id":"ebook-ja-tiktok-daily","next_action":"monitor_running","occurrence_id":"ebook-ja-tiktok-daily:18dff3a41b433450-51537","official_readback_ref":null,"owner_id":"ebook-ja-tiktok-daily","phase":"execute","product_loop_id":"ebook","profile_alias":null,"provider":"deterministic","provider_receipt_id":null,"release_sha":"baac8c681314edd1fc430199f30da410d31a4c1c","retryable":false,"run_id":"18dff3a41b433450-51537","status":"running","timestamp":"2026-10-19T14:11:02.898615+00:00","version":1,"wake_id":"18dff3a41b433450-51537"},{"blocker":null,"domain":"growth","effect_class":"publish","effect_status":"reconciled","error_class":null,"event_id":"de2f3386e88fd1362284e198","evidence_refs":["lm-loop://ebook-ja-tiktok-daily/18dff3a41b433450-51537/summary.json","lm-occurrence://ebook-ja-tiktok-daily/18dfbf4b313011a8-82806/claim","postiz://posts/cmvf5cw4503uemw0y3fmvizy7"],"exit_code":0,"failure_layer":"clean","job_id":"ebook-ja-tiktok-daily","loaded_argv_sha256":"7d0e652483120fa9eb582add850c17c30285e76b44815c444a5a305f61bcdc9d","loaded_env_sha256":"862988ba771eec4d1e5675375f461acb682ba1129096ed54f0a5d0c213c5ace8","loop_id":"ebook-ja-tiktok-daily","next_action":"none","occurrence_id":"ebook-ja-tiktok-daily:18dfbf4b313011a8-82806","official_readback_ref":"postiz://posts/cmvf5cw4503uemw0y3fmvizy7","owner_id":"ebook-ja-tiktok-daily","phase":"report","product_loop_id":"ebook","profile_alias":null,"provider":"postiz","provider_receipt_id":"cmvf5cw4503uemw0y3fmvizy7","release_sha":"baac8c681314edd1fc430199f30da410d31a4c1c","retryable":false,"run_id":"18dff3a41b433450-51537","status":"pass","timestamp":"2026-10-19T14:11:10.268296+00:00","version":1,"wake_id":"18dff3a41b433450-51537"}],"jobs":[{"event":"enqueue","job":{"attempt":0,"available_at":"2026-10-19T11:04:02.681Z","capability":"marketing.video.publish","effect_class":"publish","effect_key":"marketing:video:ebook-ja:tiktok:baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily:6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4:417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8:b2a91d8ccda2ed4e7ffa0f4c55f72d19b269723b73f5b78e2597691e1cbb0c81","enqueued_at":"2026-10-19T11:04:09.875Z","input_refs":{"approval_ref":"object://sha256/e9929fa63ca4bea148f212ea178deff261755fca5ef35e64984bb1d72c3d10e5","caption_ref":"object://sha256/417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8","creative_ref":"creative://ebook-ja/baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily","form_ref":"form://ebook-reflection-reel","format_ref":"format://ebook-watercolor","instagram_profile_ref":"profile://instagram/unassigned","locale_ref":"locale://ja","platform_ref":"platform://tiktok","postiz_token_ref":"secret://postiz/api-key","product_ref":"product://ebook-ja","slot_ref":"schedule-slot://2026-10-19T11:00:00.000Z","tiktok_integration_ref":"integration://postiz/tiktok/cmo5s4edx00vgn10ygnu34a0n","video_ref":"object://sha256/6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4"},"job_id":"marketing-video-publication:50ffdcff4049aca47f626aa10883b104d5dc5a15d039e3a43e12fc90d4fb3b7c","lease_expires_at":null,"lease_owner":null,"loop_id":"marketing.video.publish","max_attempts":3,"status":"queued","tenant_id":"dais-local","unknown_effect":false,"updated_at":"2026-10-19T11:04:09.875Z"},"kind":"job","schema_version":1},{"event":"claim","job":{"attempt":1,"available_at":"2026-10-19T11:04:02.681Z","capability":"marketing.video.publish","effect_class":"publish","effect_key":"marketing:video:ebook-ja:tiktok:baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily:6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4:417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8:b2a91d8ccda2ed4e7ffa0f4c55f72d19b269723b73f5b78e2597691e1cbb0c81","enqueued_at":"2026-10-19T11:04:09.875Z","input_refs":{"approval_ref":"object://sha256/e9929fa63ca4bea148f212ea178deff261755fca5ef35e64984bb1d72c3d10e5","caption_ref":"object://sha256/417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8","creative_ref":"creative://ebook-ja/baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily","form_ref":"form://ebook-reflection-reel","format_ref":"format://ebook-watercolor","instagram_profile_ref":"profile://instagram/unassigned","locale_ref":"locale://ja","platform_ref":"platform://tiktok","postiz_token_ref":"secret://postiz/api-key","product_ref":"product://ebook-ja","slot_ref":"schedule-slot://2026-10-19T11:00:00.000Z","tiktok_integration_ref":"integration://postiz/tiktok/cmo5s4edx00vgn10ygnu34a0n","video_ref":"object://sha256/6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4"},"job_id":"marketing-video-publication:50ffdcff4049aca47f626aa10883b104d5dc5a15d039e3a43e12fc90d4fb3b7c","lease_expires_at":"2026-10-19T11:09:12.251Z","lease_owner":"ebook-ja-tiktok-daily","loop_id":"marketing.video.publish","max_attempts":3,"status":"running","tenant_id":"dais-local","unknown_effect":false,"updated_at":"2026-10-19T11:04:12.251Z"},"kind":"job","schema_version":1},{"event":"complete","job":{"attempt":1,"available_at":"2026-10-19T11:04:02.681Z","capability":"marketing.video.publish","completed_at":"2026-10-19T11:04:51.374Z","effect_class":"publish","effect_key":"marketing:video:ebook-ja:tiktok:baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily:6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4:417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8:b2a91d8ccda2ed4e7ffa0f4c55f72d19b269723b73f5b78e2597691e1cbb0c81","enqueued_at":"2026-10-19T11:04:09.875Z","input_refs":{"approval_ref":"object://sha256/e9929fa63ca4bea148f212ea178deff261755fca5ef35e64984bb1d72c3d10e5","caption_ref":"object://sha256/417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8","creative_ref":"creative://ebook-ja/baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily","form_ref":"form://ebook-reflection-reel","format_ref":"format://ebook-watercolor","instagram_profile_ref":"profile://instagram/unassigned","locale_ref":"locale://ja","platform_ref":"platform://tiktok","postiz_token_ref":"secret://postiz/api-key","product_ref":"product://ebook-ja","slot_ref":"schedule-slot://2026-10-19T11:00:00.000Z","tiktok_integration_ref":"integration://postiz/tiktok/cmo5s4edx00vgn10ygnu34a0n","video_ref":"object://sha256/6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4"},"job_id":"marketing-video-publication:50ffdcff4049aca47f626aa10883b104d5dc5a15d039e3a43e12fc90d4fb3b7c","lease_expires_at":null,"lease_owner":null,"loop_id":"marketing.video.publish","max_attempts":3,"status":"completed","tenant_id":"dais-local","unknown_effect":false,"updated_at":"2026-10-19T11:04:51.374Z"},"kind":"job","schema_version":1},{"event":"receipt_correct","job":{"attempt":1,"available_at":"2026-10-19T11:04:02.681Z","capability":"marketing.video.publish","completed_at":"2026-10-19T11:04:51.374Z","effect_class":"publish","effect_key":"marketing:video:ebook-ja:tiktok:baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily:6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4:417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8:b2a91d8ccda2ed4e7ffa0f4c55f72d19b269723b73f5b78e2597691e1cbb0c81","enqueued_at":"2026-10-19T11:04:09.875Z","input_refs":{"approval_ref":"object://sha256/e9929fa63ca4bea148f212ea178deff261755fca5ef35e64984bb1d72c3d10e5","caption_ref":"object://sha256/417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8","creative_ref":"creative://ebook-ja/baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily","form_ref":"form://ebook-reflection-reel","format_ref":"format://ebook-watercolor","instagram_profile_ref":"profile://instagram/unassigned","locale_ref":"locale://ja","platform_ref":"platform://tiktok","postiz_token_ref":"secret://postiz/api-key","product_ref":"product://ebook-ja","slot_ref":"schedule-slot://2026-10-19T11:00:00.000Z","tiktok_integration_ref":"integration://postiz/tiktok/cmo5s4edx00vgn10ygnu34a0n","video_ref":"object://sha256/6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4"},"job_id":"marketing-video-publication:50ffdcff4049aca47f626aa10883b104d5dc5a15d039e3a43e12fc90d4fb3b7c","lease_expires_at":null,"lease_owner":null,"loop_id":"marketing.video.publish","max_attempts":3,"receipt_corrected_at":"2026-10-22T16:16:34.669Z","status":"completed","tenant_id":"dais-local","unknown_effect":false,"updated_at":"2026-10-22T16:16:34.669Z"},"kind":"job","schema_version":1}],"receipts":[{"attempt":1,"job_id":"marketing-video-publication:50ffdcff4049aca47f626aa10883b104d5dc5a15d039e3a43e12fc90d4fb3b7c","kind":"receipt","receipt":{"caption_sha256":"417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8","creative_id":"baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily","form":"ebook-reflection-reel","format_id":"ebook-watercolor","kind":"marketing_video_distribution","locale":"ja","origin_occurrence_id":"ebook-ja-tiktok-daily:18dfbec0c5a2d540-51433","platform":"tiktok","product_id":"ebook-ja","provider_effect_created":true,"provider_post_id":"cmvf5cw4503uemw0y3fmvizy7","provider_reconciled":true,"provider_route":"postiz","public_url":"https://www.tiktok.com/@obou_anicca/video/7698332982763046932","published_at":"2026-10-19T11:04:45.542Z","schema_version":1,"slot":"2026-10-19T11:00:00.000Z","status":"published","video_sha256":"6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4"},"schema_version":1,"tenant_id":"dais-local"},{"attempt":1,"corrected_at":"2026-10-22T16:16:34.669Z","correction":"caption_matched_direct_url","job_id":"marketing-video-publication:50ffdcff4049aca47f626aa10883b104d5dc5a15d039e3a43e12fc90d4fb3b7c","kind":"receipt","receipt":{"caption_sha256":"417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8","creative_id":"baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily","form":"ebook-reflection-reel","format_id":"ebook-watercolor","kind":"marketing_video_distribution","locale":"ja","origin_occurrence_id":"ebook-ja-tiktok-daily:18dfbec0c5a2d540-51433","platform":"tiktok","product_id":"ebook-ja","provider_effect_created":true,"provider_post_id":"cmvf5cw4503uemw0y3fmvizy7","provider_reconciled":true,"provider_route":"postiz","public_url":"https://www.tiktok.com/@obou_anicca/video/7698333137004268821","published_at":"2026-10-19T11:04:45.542Z","schema_version":1,"slot":"2026-10-19T11:00:00.000Z","status":"published","video_sha256":"6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4"},"schema_version":1,"tenant_id":"dais-local"}],"distribution":[{"caption_path":"fixture/caption_path","caption_sha256":"417d2b2c27fcd7c12ee119639cebd066a95406dd2679d708b382817ba8f3e1d8","creative_id":"baseline.ebook-ja.d1.s3-20261019T110000000Z-ebook-ja-tiktok-daily","form":"ebook-reflection-reel","format_id":"ebook-watercolor","locale":"ja","logged_out_readback":null,"migration_date":null,"platform":"tiktok","provider_cost_usd":null,"provider_id":"cmvf5cw4503uemw0y3fmvizy7","provider_reconciled":true,"public_url":"https://www.tiktok.com/@obou_anicca/video/7698332982763046932","route":"postiz","slot":"2026-10-19T11:00:00.000Z","status":"published","ts":"2026-10-19T11:04:45.374136Z","video_path":"fixture/video_path","video_sha256":"6160de64571f6d3e73ad8b88f78c14302e9fc085b185af8dc38f4ebdf9ad57e4"}]}')


@pytest.fixture
def jatt_reuse(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from runtime.host import resource_admission as admission
    rows = json.loads(json.dumps(_JATT_ORIGINAL_ROWS))
    owner = "ebook-ja-tiktok-daily"
    occurrence = f"{owner}:18dfbf4b313011a8-82806"
    caption = "Existing Japanese publication fixture"
    video = b"existing rendered Japanese video fixture"
    video_sha = hashlib.sha256(video).hexdigest()
    caption_sha = hashlib.sha256(caption.encode()).hexdigest()
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    old_video = rows["receipts"][0]["receipt"]["video_sha256"]
    old_caption = rows["receipts"][0]["receipt"]["caption_sha256"]
    rows = json.loads(json.dumps(rows).replace(old_video, video_sha).replace(old_caption, caption_sha))
    original = rows["receipts"][0]["receipt"]
    corrected = rows["receipts"][1]["receipt"]
    spec = {
        "owner_id": owner, "occurrence_id": occurrence,
        "claim_run_id": "18dff3a41b433450-51537",
        "origin_occurrence_id": f"{owner}:18dfbec0c5a2d540-51433",
        "job_id": rows["jobs"][0]["job"]["job_id"],
        "post_id": original["provider_post_id"],
        "integration_id": "cmo5s4edx00vgn10ygnu34a0n",
        "public_url": corrected["public_url"],
        "video_sha256": video_sha, "caption_sha256": caption_sha,
        "release_sha": "baac8c681314edd1fc430199f30da410d31a4c1c",
        "event_sha256": {row["event_id"]: digest(row) for row in rows["events"]},
        "job_row_sha256": [digest(row) for row in rows["jobs"]],
        "receipt_row_sha256": [digest(row) for row in rows["receipts"]],
        "distribution_sha256": digest({key: value for key, value in rows["distribution"][0].items()
                                       if key not in {"video_path", "caption_path"}}),
    }
    retained = tmp_path / "retained-release"
    retained.mkdir()
    (retained / "RELEASE.json").write_text(json.dumps({"sha": spec["release_sha"]}))
    spec["source_sha256"] = {}
    for rel in ("apps/life-manager/scripts/ebook-distribute-daily.js",
                "apps/life-manager/lib/marketing-local-ledger.js"):
        path = retained / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("retained source fixture: " + rel)
        spec["source_sha256"][rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    paths = {}
    spec["journal_prefix"] = {}

    def write_rows(rel, values):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in values))
        path.chmod(0o600)
        paths[rel] = path
        return path

    for rel, key in (("ebook/events.jsonl", "events"), ("marketing/jobs.jsonl", "jobs"),
                     ("marketing/receipts.jsonl", "receipts")):
        prefix = {"retained_prefix": rel}
        historical = {"events": {"run_id": "unrelated-history", "phase": "report"},
                      "jobs": {"job": {"job_id": "unrelated-history"}},
                      "receipts": {"job_id": "unrelated-history", "receipt": {}}}[key]
        path = write_rows(rel, [prefix, historical, *rows[key]])
        raw = path.read_bytes()
        spec["journal_prefix"][rel] = (len(raw), hashlib.sha256(raw).hexdigest())
    objects = tmp_path / "objects/sha256"
    objects.mkdir(parents=True)
    for digest_value, data in ((video_sha, video), (caption_sha, caption.encode())):
        path = objects / digest_value
        path.write_bytes(data)
        path.chmod(0o600)
    distribution = rows["distribution"][0]
    distribution.update(video_path=str(objects / video_sha), caption_path=str(objects / caption_sha))
    ledger = write_rows("tenants/dais-local/marketing/video-publication/ebook-ja/distribution.jsonl",
                        rows["distribution"])
    key = hashlib.sha256(("dais-local\n" + spec["job_id"]).encode()).hexdigest()
    receipt = write_rows(f"marketing/receipts/{key}.json", [{
        "schema_version": 1, "tenant_id": "dais-local", "job_id": spec["job_id"], "receipt": corrected,
    }])
    spec["current_receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    idir = tmp_path / "ebook/effect-identities"
    idir.mkdir()
    admission_root = tmp_path / "admission"
    monkeypatch.setenv("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT", str(admission_root))
    admission.activate_durable_v2()
    admission.enqueue_durable("agent", owner, admission_class="revenue", occurrence_id=occurrence)
    claim, reason = admission.claim_durable("agent", owner, admission_class="revenue")
    assert claim is not None and reason == "acquired"
    admission.release_and_reserve(claim, effect_unknown=True, reserve=False)
    db = admission_root / "admission-v2.sqlite3"
    monkeypatch.setattr(reconcile, "JA_TIKTOK_REUSE", spec, raising=False)
    monkeypatch.setattr(reconcile, "JA_TIKTOK_REUSE_RELEASE", retained, raising=False)
    official = {
        "id": spec["post_id"], "state": "PUBLISHED", "integrationId": spec["integration_id"],
        "content": caption, "releaseURL": spec["public_url"], "releaseId": "7698333137004268821",
        "lifeManagerVideoSha256": video_sha,
    }
    calls = []
    fallback = []

    def request(url, _key):
        calls.append(url)
        if url.endswith("/" + spec["post_id"]):
            return official
        assert url.endswith("/integrations")
        return [{"id": spec["integration_id"], "identifier": "tiktok", "profile": "@obou_anicca"}]

    monkeypatch.setattr(reconcile, "_request_json", request)
    monkeypatch.setattr(reconcile, "_postiz_posts_between",
                        lambda *_args: fallback.append(True) or [official])
    kw = dict(owner_id=owner, occurrence_id=occurrence, identity_dir=idir, data_dir=tmp_path,
              tenant_id="dais-local", admission_db=db, api_key="fixture-key")
    return SimpleNamespace(spec=spec, rows=rows, paths=paths, retained=retained, receipt=receipt,
                           objects=objects, official=official, calls=calls, fallback=fallback,
                           write_rows=write_rows, kw=kw, db=db)


def test_jatt_historical_receipt_reuse_is_read_only_and_replays_without_reattribution(jatt_reuse):
    fixture = jatt_reuse
    before = {path: path.read_bytes() for path in fixture.paths.values()}
    dry = reconcile.reconcile_current_occurrence(apply=False, **fixture.kw)
    assert dry["status"] == "ready"
    assert dry["proof_type"] == "historical_postiz_receipt_reuse_no_dispatch"
    assert dry["effect"] == 0
    assert dry["original_origin_occurrence_id"] == fixture.spec["origin_occurrence_id"]
    with sqlite3.connect(fixture.db) as db:
        assert db.execute("SELECT effect_unknown FROM occurrences WHERE occurrence_id=?",
                          (fixture.kw["occurrence_id"],)).fetchone() == (1,)
    result = reconcile.reconcile_current_occurrence(apply=True, **fixture.kw)
    assert result["status"] == "resolved"
    calls = len(fixture.calls)
    assert reconcile.reconcile_current_occurrence(apply=True, **fixture.kw)["status"] == "clean"
    assert len(fixture.calls) == calls and fixture.fallback == []
    assert all(path.read_bytes() == raw for path, raw in before.items())
    with sqlite3.connect(fixture.db) as db:
        assert db.execute("SELECT state,effect_unknown FROM occurrences WHERE occurrence_id=?",
                          (fixture.kw["occurrence_id"],)).fetchone() == ("released", 0)


@pytest.mark.parametrize("relative,key", [
    ("ebook/events.jsonl", "events"), ("marketing/jobs.jsonl", "jobs"),
    ("marketing/receipts.jsonl", "receipts"),
])
@pytest.mark.parametrize("change", ["removed", "same_length_replacement"])
def test_jatt_historical_receipt_reuse_rejects_changed_interior_history(jatt_reuse, relative, key, change):
    fixture = jatt_reuse
    path = fixture.paths[relative]
    if change == "removed":
        prefix = json.loads(path.read_text().splitlines()[0])
        fixture.write_rows(relative, [prefix, *fixture.rows[key]])
    else:
        before = path.read_bytes()
        changed = before.replace(b"unrelated-history", b"unrelated-historx", 1)
        assert changed != before and len(changed) == len(before)
        path.write_bytes(changed)
    result = reconcile.reconcile_current_occurrence(apply=True, **fixture.kw)
    assert result["status"] == "inconclusive"
    assert fixture.calls == [] and fixture.fallback == []
    with sqlite3.connect(fixture.db) as db:
        assert db.execute("SELECT effect_unknown FROM occurrences WHERE occurrence_id=?",
                          (fixture.kw["occurrence_id"],)).fetchone() == (1,)


@pytest.mark.parametrize("container", ["identity", "runtime"])
def test_jatt_historical_receipt_reuse_rejects_nested_additional_claim(jatt_reuse, container):
    fixture = jatt_reuse
    extra = {**fixture.rows["events"][-1], "run_id": "another-claimant", "event_id": "extra",
             "occurrence_id": "another-owner:another-occurrence", "evidence_refs": [],
             container: {"occurrence_id": fixture.kw["occurrence_id"]}}
    path = fixture.paths["ebook/events.jsonl"]
    with path.open("a") as file:
        file.write(json.dumps(extra) + "\n")
    result = reconcile.reconcile_current_occurrence(apply=True, **fixture.kw)
    assert result["status"] == "inconclusive"
    assert fixture.calls == [] and fixture.fallback == []
    with sqlite3.connect(fixture.db) as db:
        assert db.execute("SELECT effect_unknown FROM occurrences WHERE occurrence_id=?",
                          (fixture.kw["occurrence_id"],)).fetchone() == (1,)


def test_jatt_historical_receipt_reuse_allows_unrelated_append(jatt_reuse):
    fixture = jatt_reuse
    for relative, extra in (
            ("ebook/events.jsonl", {"run_id": "unrelated-append", "phase": "report"}),
            ("marketing/jobs.jsonl", {"job": {"job_id": "unrelated-append"}}),
            ("marketing/receipts.jsonl", {"job_id": "unrelated-append", "receipt": {}})):
        with fixture.paths[relative].open("a") as file:
            file.write(json.dumps(extra) + "\n")
    assert reconcile.reconcile_current_occurrence(apply=False, **fixture.kw)["status"] == "ready"
    assert fixture.fallback == []


@pytest.mark.parametrize("case", [
    "additional_claim", "event_changed", "missing_history_prefix", "source_changed", "manifest_changed",
    "job_attempt", "job_completed_late", "new_job_in_claim", "second_provider_job",
    "origin_changed", "receipt_other_change", "current_receipt_changed", "video_changed",
    "caption_changed", "distribution_changed", "official_state", "official_integration",
    "official_caption", "official_url", "official_video_hash",
])
def test_jatt_historical_receipt_reuse_rejects_changed_original_boundary(jatt_reuse, case):
    fixture = jatt_reuse
    rows = fixture.rows
    if case in {"additional_claim", "event_changed", "missing_history_prefix"}:
        values = [json.loads(line) for line in fixture.paths["ebook/events.jsonl"].read_text().splitlines()]
        if case == "additional_claim":
            values.append({**rows["events"][-1], "run_id": "another-claimant", "event_id": "extra"})
        elif case == "event_changed":
            values[-1] = {**values[-1], "exit_code": 1}
        else:
            values = values[1:]
        fixture.write_rows("ebook/events.jsonl", values)
    elif case == "source_changed":
        with (fixture.retained / "apps/life-manager/scripts/ebook-distribute-daily.js").open("a") as file:
            file.write("changed")
    elif case == "manifest_changed":
        (fixture.retained / "RELEASE.json").write_text('{"sha":"wrong"}')
    elif case in {"job_attempt", "job_completed_late", "new_job_in_claim"}:
        if case == "job_attempt":
            rows["jobs"][2]["job"]["attempt"] = 2
        elif case == "job_completed_late":
            rows["jobs"][2]["job"]["completed_at"] = "2026-10-19T14:11:05.000Z"
        else:
            rows["jobs"].append(json.loads(json.dumps(rows["jobs"][1])))
            rows["jobs"][-1]["job"].update(job_id="another-job", updated_at="2026-10-19T14:11:05.000Z")
        prefix = [json.loads(line) for line in fixture.paths["marketing/jobs.jsonl"].read_text().splitlines()[:2]]
        fixture.write_rows("marketing/jobs.jsonl", [*prefix, *rows["jobs"]])
    elif case in {"second_provider_job", "origin_changed", "receipt_other_change"}:
        if case == "second_provider_job":
            rows["receipts"].append({**rows["receipts"][0], "job_id": "another-job"})
        elif case == "origin_changed":
            rows["receipts"][0]["receipt"]["origin_occurrence_id"] = fixture.kw["occurrence_id"]
        else:
            rows["receipts"][1]["receipt"]["provider_effect_created"] = False
        prefix = [json.loads(line) for line in fixture.paths["marketing/receipts.jsonl"].read_text().splitlines()[:2]]
        fixture.write_rows("marketing/receipts.jsonl", [*prefix, *rows["receipts"]])
    elif case == "current_receipt_changed":
        fixture.receipt.write_text(fixture.receipt.read_text() + " ")
    elif case in {"video_changed", "caption_changed"}:
        field = "video_sha256" if case == "video_changed" else "caption_sha256"
        (fixture.objects / fixture.spec[field]).write_bytes(b"changed")
    elif case == "distribution_changed":
        fixture.rows["distribution"][0]["route"] = "tiktok_direct"
        fixture.write_rows("tenants/dais-local/marketing/video-publication/ebook-ja/distribution.jsonl",
                           fixture.rows["distribution"])
    else:
        fields = {"official_state": ("state", "ERROR"), "official_integration": ("integrationId", "other"),
                  "official_caption": ("content", "changed"), "official_url": ("releaseURL", "https://www.tiktok.com/@obou_anicca/video/1"),
                  "official_video_hash": ("lifeManagerVideoSha256", "0" * 64)}
        field, value = fields[case]
        fixture.official[field] = value
    before = fixture.receipt.read_bytes()
    result = reconcile.reconcile_current_occurrence(apply=True, **fixture.kw)
    assert result["status"] == "inconclusive"
    assert fixture.receipt.read_bytes() == before and fixture.fallback == []
    with sqlite3.connect(fixture.db) as db:
        assert db.execute("SELECT effect_unknown FROM occurrences WHERE occurrence_id=?",
                          (fixture.kw["occurrence_id"],)).fetchone() == (1,)


def test_jatt_history_reader_keeps_default_limit_and_accepts_explicit_bound(tmp_path):
    path = tmp_path / "large-journal.jsonl"
    path.write_text(json.dumps({"fixture": "x" * (8 * 1024 * 1024)}) + "\n")
    path.chmod(0o600)
    assert reconcile._safe_jsonl(path) is None
    assert reconcile._safe_jsonl(path, max_bytes=64 * 1024 * 1024)[0]["fixture"].startswith("x")
