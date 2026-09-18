import importlib.util
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image


MODULE = Path(__file__).parents[1] / "scripts" / "media_create_once.py"
SPEC = importlib.util.spec_from_file_location("media_create_once", MODULE)
assert SPEC and SPEC.loader
media = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(media)


def _png(path: Path, height: int) -> None:
    Image.new("RGB", (1300, height), "white").save(path, format="PNG")


def test_body_candidate_below_x_readability_floor_is_refused(tmp_path):
    candidate = tmp_path / "candidate.png"
    _png(candidate, 70)
    with pytest.raises(media.MediaCreateRefused, match="outside-x-render-range"):
        media.commit(
            candidate,
            tmp_path / "body-diagram.png",
            tmp_path / "body-receipt.json",
            "body",
        )


def test_body_candidate_at_x_readability_floor_commits(tmp_path):
    candidate = tmp_path / "candidate.png"
    _png(candidate, 244)
    receipt = media.commit(
        candidate,
        tmp_path / "body-diagram.png",
        tmp_path / "body-receipt.json",
        "body",
    )
    assert receipt["height"] == 244


def test_tall_body_candidate_is_padded_without_upscaling_content(tmp_path):
    candidate = tmp_path / "candidate.png"
    original_pixel = (10, 20, 30, 128)
    Image.new("RGBA", (276, 510), original_pixel).save(candidate, format="PNG")
    receipt = media.commit(
        candidate,
        tmp_path / "body-diagram.png",
        tmp_path / "body-receipt.json",
        "body",
    )
    assert receipt["height"] == 510
    assert receipt["width"] == 461
    assert receipt["width"] > 276
    padded = Image.open(candidate).convert("RGBA")
    assert padded.getpixel(((461 - 276) // 2, 0)) == original_pixel


def test_new_run_requires_matching_gpt_image_receipt(tmp_path):
    run = tmp_path / "run"
    (run / "gates/media-candidates").mkdir(parents=True)
    media.arm(run)
    headline_candidate = run / media.HEADLINE_API_CANDIDATE
    body_candidate = run / "gates/media-candidates/body.png"
    _png(headline_candidate, 800)
    _png(body_candidate, 400)
    headline = media.commit(headline_candidate, run / "headline-image.png",
                            run / "gates/headline-image-create.json", "headline")
    media.commit(body_candidate, run / "body-diagram.png",
                 run / "gates/body-diagram-create.json", "body")
    api_receipt = {
        "schema": "writer.gpt-image-headline-receipt", "version": 1,
        "status": "committed", "candidate": str(headline_candidate),
        "request_model": "gpt-image-2-2026-04-21",
        "provider_model": "gpt-image-2-2026-04-21",
        "api_key_source": "openai",
        "endpoint": "https://api.openai.com/v1/images/generations",
        "file_sha256": headline["sha256"], "byte_length": headline["byte_length"],
        "width": headline["width"], "height": headline["height"],
        "x_request_id": "req_123", "prompt_sha256": "a" * 64,
        "response_sha256": "b" * 64, "alt": "article-specific alt",
        "rights_provenance": "OpenAI terms",
    }
    (run / media.HEADLINE_API_RECEIPT).write_text(json.dumps(api_receipt))
    api_receipt_sha = hashlib.sha256(
        (run / media.HEADLINE_API_RECEIPT).read_bytes()
    ).hexdigest()
    (run / "gates/headline-image-api-intent.json").write_text(
        json.dumps(
            {
                "status": "committed",
                "fingerprint": {
                    "endpoint": api_receipt["endpoint"],
                    "model": api_receipt["provider_model"],
                    "output": api_receipt["candidate"],
                },
                "receipt_sha256": api_receipt_sha,
            }
        )
    )

    assert media.verify(run)["headline_api_verified"] is True


def test_new_run_without_gpt_image_receipt_is_refused(tmp_path):
    run = tmp_path / "run"
    (run / "gates/media-candidates").mkdir(parents=True)
    media.arm(run)
    headline_candidate = run / media.HEADLINE_API_CANDIDATE
    body_candidate = run / "gates/media-candidates/body.png"
    _png(headline_candidate, 800)
    _png(body_candidate, 400)
    media.commit(headline_candidate, run / "headline-image.png",
                 run / "gates/headline-image-create.json", "headline")
    media.commit(body_candidate, run / "body-diagram.png",
                 run / "gates/body-diagram-create.json", "body")
    with pytest.raises(media.MediaCreateRefused, match="headline-api-receipt-invalid"):
        media.verify(run)
