import base64
import importlib.util
import json
import struct
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/gpt_image_headline.py"
SPEC = importlib.util.spec_from_file_location("gpt_image_headline", SCRIPT)
image = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(image)


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PNG = PNG[:16] + struct.pack(">II", 1536, 1024) + PNG[24:]
SQUARE_PNG = PNG[:16] + struct.pack(">II", 1024, 1024) + PNG[24:]


class Response:
    headers = {"x-request-id": "req_test_123"}

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self):
        return json.dumps({"data": [{"b64_json": base64.b64encode(PNG).decode()}]}).encode()


class ResponseNoRequestID(Response):
    headers = {}


class ResponseWrongDimensions(Response):
    def read(self):
        return json.dumps(
            {"data": [{"b64_json": base64.b64encode(SQUARE_PNG).decode()}]}
        ).encode()


def test_generate_records_complete_receipt_and_replay_calls_api_zero_times(
    tmp_path: Path, monkeypatch
) -> None:
    prompt, alt = tmp_path / "prompt.txt", tmp_path / "alt.txt"
    candidate, intent, receipt = tmp_path / "candidate.png", tmp_path / "intent.json", tmp_path / "receipt.json"
    prompt.write_text("Article-specific visual about verified writing revenue")
    alt.write_text("A writer connecting an article to a verified payout receipt")
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    calls = []

    def opener(request, timeout):
        calls.append((request, timeout))
        return Response()

    result = image.generate(prompt_path=prompt, alt_path=alt, candidate=candidate,
                            intent_path=intent, receipt_path=receipt, opener=opener)
    replay = image.generate(prompt_path=prompt, alt_path=alt, candidate=candidate,
                            intent_path=intent, receipt_path=receipt,
                            opener=lambda *_a, **_k: pytest.fail("replay called API"))
    assert len(calls) == 1
    assert result["request_model"] == "gpt-image-2-2026-04-21"
    assert result["x_request_id"] == "req_test_123"
    assert result["request_sha256"] == image._sha(calls[0][0].data)
    assert result["file_sha256"] == image._sha(PNG)
    assert (result["width"], result["height"]) == (1536, 1024)
    assert replay["replay"] == "reused"
    assert image.verify(candidate, receipt)["status"] == "committed"


def test_existing_unreceipted_intent_refuses_resend(tmp_path: Path, monkeypatch) -> None:
    prompt, alt = tmp_path / "prompt.txt", tmp_path / "alt.txt"
    candidate, intent, receipt = tmp_path / "candidate.png", tmp_path / "intent.json", tmp_path / "receipt.json"
    prompt.write_text("specific prompt")
    alt.write_text("specific alt")
    intent.write_text(json.dumps({"fingerprint": image._fingerprint(prompt.read_bytes(), candidate),
                                  "status": "request_started"}))
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    with pytest.raises(image.HeadlineImageRefused, match="outcome-unknown"):
        image.generate(prompt_path=prompt, alt_path=alt, candidate=candidate,
                       intent_path=intent, receipt_path=receipt,
                       opener=lambda *_a, **_k: pytest.fail("unknown intent resent"))


def test_missing_key_creates_no_intent(tmp_path: Path, monkeypatch) -> None:
    prompt, alt = tmp_path / "prompt.txt", tmp_path / "alt.txt"
    candidate, intent, receipt = tmp_path / "candidate.png", tmp_path / "intent.json", tmp_path / "receipt.json"
    prompt.write_text("specific prompt")
    alt.write_text("specific alt")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(image.HeadlineImageRefused, match="OPENAI_API_KEY"):
        image.generate(prompt_path=prompt, alt_path=alt, candidate=candidate,
                       intent_path=intent, receipt_path=receipt)
    assert not intent.exists()


def test_known_pre_effect_refusal_can_retry_after_key_is_available(
    tmp_path: Path, monkeypatch
) -> None:
    prompt, alt = tmp_path / "prompt.txt", tmp_path / "alt.txt"
    candidate, intent, receipt = (
        tmp_path / "candidate.png",
        tmp_path / "intent.json",
        tmp_path / "receipt.json",
    )
    prompt.write_text("specific prompt")
    alt.write_text("specific alt")
    receipt.write_text(
        json.dumps({"status": "refused", "reason": "OPENAI_API_KEY-unavailable"})
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    calls = []

    def opener(request, timeout):
        calls.append((request, timeout))
        return Response()

    result = image.generate(
        prompt_path=prompt,
        alt_path=alt,
        candidate=candidate,
        intent_path=intent,
        receipt_path=receipt,
        opener=opener,
    )

    assert len(calls) == 1
    assert result["status"] == "committed"


def test_local_cliproxy_is_an_openai_compatible_image_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    prompt, alt = tmp_path / "prompt.txt", tmp_path / "alt.txt"
    candidate, intent, receipt = (
        tmp_path / "candidate.png",
        tmp_path / "intent.json",
        tmp_path / "receipt.json",
    )
    prompt.write_text("specific prompt")
    alt.write_text("specific alt")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CLIPROXY_API_KEY", "proxy-secret")
    monkeypatch.setenv("ARTICLE_CODEX_PROVIDER_BASE_URL", "http://127.0.0.1:8317/v1")
    calls = []

    def opener(request, timeout):
        calls.append((request, timeout))
        return ResponseNoRequestID()

    result = image.generate(
        prompt_path=prompt,
        alt_path=alt,
        candidate=candidate,
        intent_path=intent,
        receipt_path=receipt,
        opener=opener,
    )

    assert result["status"] == "committed"
    assert calls[0][0].full_url == "http://127.0.0.1:8317/v1/images/generations"
    assert json.loads(calls[0][0].data)["model"] == "gpt-image-1.5"
    assert calls[0][0].headers["X-request-id"].startswith("lm-")
    assert result["request_id_source"] == "client-generated"


def test_known_dimension_refusal_is_recorded_and_allows_one_safe_retry(
    tmp_path: Path, monkeypatch
) -> None:
    prompt, alt = tmp_path / "prompt.txt", tmp_path / "alt.txt"
    candidate, intent, receipt = (
        tmp_path / "candidate.png",
        tmp_path / "intent.json",
        tmp_path / "receipt.json",
    )
    prompt.write_text("specific prompt")
    alt.write_text("specific alt")
    monkeypatch.setenv("CLIPROXY_API_KEY", "proxy-secret")
    monkeypatch.setenv("ARTICLE_CODEX_PROVIDER_BASE_URL", "http://127.0.0.1:8317/v1")

    with pytest.raises(image.HeadlineImageRefused, match="dimensions"):
        image.generate(
            prompt_path=prompt,
            alt_path=alt,
            candidate=candidate,
            intent_path=intent,
            receipt_path=receipt,
            opener=lambda *_a, **_k: ResponseWrongDimensions(),
        )

    failed = json.loads(intent.read_text(encoding="utf-8"))
    assert failed["status"] == "failed_known"
    assert failed["reason"] == "image-dimensions-do-not-match-request"

    result = image.generate(
        prompt_path=prompt,
        alt_path=alt,
        candidate=candidate,
        intent_path=intent,
        receipt_path=receipt,
        opener=lambda *_a, **_k: Response(),
    )
    assert result["status"] == "committed"
