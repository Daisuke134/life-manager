from __future__ import annotations

import json
import asyncio
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "note-publish"))

import publication_remote  # noqa: E402
import note_inplace_repair  # noqa: E402
from publication_resume import PublicationStore  # noqa: E402
from media_integrity import descriptor_from_file  # noqa: E402
from media_integrity import content_proof  # noqa: E402


def test_visual_media_proof_normalizes_transparent_background_reencoding(
    tmp_path: Path,
) -> None:
    expected_path = tmp_path / "body.png"
    source = Image.new("RGBA", (526, 582), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    draw.rectangle((100, 80, 420, 500), outline=(20, 20, 20, 255), width=8)
    source.save(expected_path, format="PNG")
    remote = Image.new("RGBA", source.size, (255, 255, 255, 255))
    remote.alpha_composite(source)
    output = io.BytesIO()
    remote.convert("RGB").save(output, format="PNG")

    proof = content_proof(
        {"path": str(expected_path), **descriptor_from_file(expected_path)},
        output.getvalue(),
        "https://example.test/body.png",
    )

    assert proof is not None
    assert proof["match_method"] == "visual-dhash"
    assert proof["expected_dhash"] == proof["remote_dhash"]


def note_media_gap() -> dict[str, object]:
    return {
        "status": "live",
        "live_url": "https://note.com/anicca123/n/n-test",
        "verified": True,
        "public_id": "n-test",
        "content_verified": True,
        "authenticated_content_verified": True,
        "monetization_verified": True,
        "asset_verified": False,
        "eyecatch_verified": True,
        "body_media_verified": False,
        "destination_identity": "anicca123",
        "identity_verified": True,
        "identity_source": "note-public-canonical-url",
        "source": "note-api+anonymous-public-html",
    }


def test_note_live_media_gap_exposes_only_same_key_repair_shape() -> None:
    """A content/identity-proven note with missing body media is repairable, not bare unknown."""
    observed = note_media_gap()
    result = {
        "status": "unknown",
        "reason": "public-asset-readback-failed",
    }

    assert publication_remote.note_media_evidence_gap(observed, result) == {
        "status": "live-media-mismatch",
        "reason": "public-asset-readback-failed",
        "verified": True,
        "live_url": "https://note.com/anicca123/n/n-test",
        "public_id": "n-test",
        "destination_identity": "anicca123",
        "identity_verified": True,
        "identity_source": "note-public-canonical-url",
        "source": "note-api+anonymous-public-html",
    }


def test_note_media_mismatch_recovers_to_protected_same_key_repair(
    tmp_path: Path,
) -> None:
    """The guard authorizes repair-required without creating or replacing a note key."""
    state_path = tmp_path / "publication-state.json"
    ledger_path = tmp_path / "articles.jsonl"
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "destination_identities": {"note/ja": "anicca123"},
                "pairs": {
                    "note/ja": {
                        "status": "ambiguous",
                        "error": "public-asset-readback-failed",
                        "target_kind": "note-key",
                        "target": "n-test",
                    }
                },
            }
        )
    )
    ledger_path.write_text("")

    recovered = PublicationStore(
        state_path, ledger_path
    ).recover_ambiguous_intent("note/ja", publication_remote.note_media_evidence_gap(
        note_media_gap(),
        {"status": "unknown", "reason": "public-asset-readback-failed"},
    ))

    assert recovered["status"] == "repair-required"
    assert recovered["target"] == "n-test"
    assert recovered["existing_publication"] == {
        "live_url": "https://note.com/anicca123/n/n-test",
        "public_id": "n-test",
    }


def test_note_preserves_eyecatch_proof_when_body_asset_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """A missing body image must not erase the independently valid cover proof."""
    headline = tmp_path / "headline.png"
    body = tmp_path / "body.png"
    headline.write_bytes(b"canonical-headline")
    body.write_bytes(b"canonical-body")
    state = {
        "media": {
            "headline_image": {
                "path": str(headline),
                **descriptor_from_file(headline),
            },
            "body_assets": [
                {"path": str(body), **descriptor_from_file(body)}
            ],
        }
    }
    headline_url = "https://assets.st-note.com/headline.png"
    stale_body_url = "https://assets.st-note.com/stale.png"
    monkeypatch.setattr(
        publication_remote,
        "get_bytes",
        lambda url: {
            headline_url: b"canonical-headline",
            stale_body_url: b"stale-body",
        }[url],
    )

    assert publication_remote.note_asset_evidence(
        state, headline_url, [stale_body_url]
    ) == {
        "asset_proofs": [
            {
                "expected_sha256": descriptor_from_file(headline)["sha256"],
                "remote_sha256": descriptor_from_file(headline)["sha256"],
                "remote_url": headline_url,
                "match_method": "exact-sha256",
                "expected_dhash": None,
                "remote_dhash": None,
                "dhash_distance": None,
                "expected_width": None,
                "expected_height": None,
                "remote_width": None,
                "remote_height": None,
            }
        ],
        "asset_verified": False,
        "body_media_verified": False,
        "eyecatch_verified": True,
    }


def test_note_media_repair_reuses_preverified_existing_eyecatch(
    tmp_path: Path, monkeypatch
) -> None:
    """A body-only repair must not upload a new cover after recovery proved it."""
    calls: list[str] = []
    adapter = note_inplace_repair.NoteMcpAdapter.__new__(
        note_inplace_repair.NoteMcpAdapter
    )
    adapter.session = object()

    async def upload(*_args):
        calls.append("upload")
        return type("Image", (), {"url": "https://assets.st-note.com/new.png"})()

    adapter._upload_eyecatch = upload
    monkeypatch.setattr(
        note_inplace_repair,
        "browser_eyecatch",
        lambda _path, _target: "https://assets.st-note.com/existing.png",
    )

    result = asyncio.run(
        adapter.upload_eyecatch(str(tmp_path / "headline.png"), "n-test")
    )

    assert result == "https://assets.st-note.com/existing.png"
    assert calls == []
