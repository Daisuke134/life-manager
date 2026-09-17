#!/usr/bin/env python3
"""Generate one article headline through the OpenAI Image API exactly once."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import struct
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

MODEL = "gpt-image-2-2026-04-21"
# The local OpenAI-compatible proxy accepts the same dated model identity as
# the public API.  The short alias can ignore the requested 1536x1024 size and
# return a square image, which is rejected by the immutable media contract.
CLIPROXY_MODEL = MODEL
ENDPOINT = "https://api.openai.com/v1/images/generations"
SIZE = "1536x1024"
QUALITY = "high"
EXPECTED_DIMENSIONS = (1536, 1024)
KNOWN_PRE_EFFECT_REFUSALS = {"OPENAI_API_KEY-unavailable"}


class HeadlineImageRefused(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _read_object(path: Path, reason: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HeadlineImageRefused(reason) from error
    if not isinstance(value, dict):
        raise HeadlineImageRefused(reason)
    return value


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise HeadlineImageRefused("image-response-is-not-png")
    width, height = struct.unpack(">II", data[16:24])
    if width < 1 or height < 1:
        raise HeadlineImageRefused("image-dimensions-invalid")
    if (width, height) != EXPECTED_DIMENSIONS:
        raise HeadlineImageRefused("image-dimensions-do-not-match-request")
    return width, height


def _fingerprint(
    prompt: bytes,
    output: Path,
    endpoint: str = ENDPOINT,
    model: str = MODEL,
) -> dict[str, Any]:
    return {"endpoint": endpoint, "model": model, "output": str(output.resolve()),
            "prompt_sha256": _sha(prompt), "quality": QUALITY, "size": SIZE}


def _api_credentials() -> tuple[str, str, str]:
    """Resolve the owner-configured OpenAI-compatible image endpoint without exposing keys."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return ENDPOINT, key, "openai"
    key = os.environ.get("CLIPROXY_API_KEY", "").strip()
    base = os.environ.get("ARTICLE_CODEX_PROVIDER_BASE_URL", "").strip().rstrip("/")
    if key and base:
        return f"{base}/images/generations", key, "cliproxy"
    return ENDPOINT, "", "none"


def verify(candidate: Path, receipt_path: Path) -> dict[str, Any]:
    receipt = _read_object(receipt_path, "headline-api-receipt-invalid")
    data = candidate.read_bytes()
    width, height = _png_dimensions(data)
    required = {"schema": "writer.gpt-image-headline-receipt", "version": 1,
                "status": "committed", "request_model": MODEL,
                "candidate": str(candidate.resolve()), "file_sha256": _sha(data),
                "byte_length": len(data), "width": width, "height": height}
    if any(receipt.get(key) != value for key, value in required.items()):
        raise HeadlineImageRefused("headline-api-receipt-mismatch")
    for key in (
        "x_request_id",
        "request_sha256",
        "prompt_sha256",
        "response_sha256",
        "alt",
        "rights_provenance",
    ):
        if not isinstance(receipt.get(key), str) or not str(receipt[key]).strip():
            raise HeadlineImageRefused(f"headline-api-receipt-missing:{key}")
    return receipt


def generate(*, prompt_path: Path, alt_path: Path, candidate: Path, intent_path: Path,
             receipt_path: Path, opener: Callable[..., Any] = urllib.request.urlopen) -> dict[str, Any]:
    if receipt_path.exists():
        recorded = _read_object(receipt_path, "headline-api-receipt-invalid")
        known_refusal = (
            recorded.get("status") == "refused"
            and recorded.get("reason") in KNOWN_PRE_EFFECT_REFUSALS
        )
        if not known_refusal:
            return {**verify(candidate, receipt_path), "replay": "reused"}
        retryable_intent = False
        if intent_path.exists():
            prior_intent = _read_object(intent_path, "headline-api-intent-invalid")
            retryable_intent = (
                prior_intent.get("status") == "failed_known"
                and prior_intent.get("http_status") in {400, 404, 422}
            ) or (
                prior_intent.get("status") == "response_missing_request_id"
                and bool(os.environ.get("CLIPROXY_API_KEY", "").strip())
                and bool(os.environ.get("ARTICLE_CODEX_PROVIDER_BASE_URL", "").strip())
            )
        if candidate.exists() or (intent_path.exists() and not retryable_intent):
            raise HeadlineImageRefused("headline-api-refusal-state-conflict")
    prompt = prompt_path.read_bytes()
    alt = alt_path.read_text(encoding="utf-8").strip()
    if not prompt.strip() or not alt:
        raise HeadlineImageRefused("headline-prompt-or-alt-empty")
    endpoint, key, key_source = _api_credentials()
    provider_model = CLIPROXY_MODEL if key_source == "cliproxy" else MODEL
    fingerprint = _fingerprint(prompt, candidate, endpoint, provider_model)
    client_request_id = "lm-" + _sha(
        json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )[:32]
    if intent_path.exists():
        intent = _read_object(intent_path, "headline-api-intent-invalid")
        known_http_refusal = (
            intent.get("status") == "failed_known"
            and intent.get("http_status") in {400, 404, 422}
            and not candidate.exists()
        ) or (
            intent.get("status") == "response_missing_request_id"
            and bool(os.environ.get("CLIPROXY_API_KEY", "").strip())
            and bool(os.environ.get("ARTICLE_CODEX_PROVIDER_BASE_URL", "").strip())
            and not candidate.exists()
        )
        if not known_http_refusal and intent.get("fingerprint") != fingerprint:
            raise HeadlineImageRefused("headline-api-intent-conflict")
        if not known_http_refusal:
            raise HeadlineImageRefused("headline-api-outcome-unknown-reconcile-before-retry")
    if candidate.exists():
        raise HeadlineImageRefused("headline-candidate-without-receipt")
    if not key:
        raise HeadlineImageRefused("OPENAI_API_KEY/CLIPROXY_API_KEY-unavailable")
    intent = {"schema": "writer.gpt-image-headline-intent", "version": 1,
              "status": "request_started", "fingerprint": fingerprint,
              "created_at": datetime.now(timezone.utc).isoformat()}
    _atomic_json(intent_path, intent)
    body = json.dumps({"model": provider_model, "prompt": prompt.decode("utf-8"),
                       "quality": QUALITY, "size": SIZE, "output_format": "png"},
                      ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request_sha256 = _sha(body)
    request = urllib.request.Request(
        endpoint, data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Request-ID": client_request_id,
        },
        method="POST")
    try:
        with opener(request, timeout=300) as response:
            raw = response.read()
            request_id = str(response.headers.get("x-request-id") or "").strip()
            request_id_source = "provider-header"
    except urllib.error.HTTPError as error:
        raw = error.read()
        _atomic_json(intent_path, {**intent, "status": "failed_known", "http_status": error.code,
                                   "response_sha256": _sha(raw),
                                   "x_request_id": str(error.headers.get("x-request-id") or "")})
        raise HeadlineImageRefused(f"headline-api-http-{error.code}") from error
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        _atomic_json(intent_path, {**intent, "status": "delivery_unknown",
                                   "error_class": type(error).__name__})
        raise HeadlineImageRefused("headline-api-delivery-unknown-reconcile-before-retry") from error
    try:
        payload = json.loads(raw)
        image = base64.b64decode(payload["data"][0]["b64_json"], validate=True)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        _atomic_json(intent_path, {**intent, "status": "response_invalid",
                                   "response_sha256": _sha(raw), "x_request_id": request_id})
        raise HeadlineImageRefused("headline-api-response-invalid") from error
    if not request_id and key_source == "cliproxy":
        request_id = client_request_id
        request_id_source = "client-generated"
    if not request_id:
        _atomic_json(intent_path, {**intent, "status": "response_missing_request_id",
                                   "response_sha256": _sha(raw)})
        raise HeadlineImageRefused("headline-api-response-missing-request-id")
    width, height = _png_dimensions(image)
    _atomic_bytes(candidate, image)
    receipt = {"schema": "writer.gpt-image-headline-receipt", "version": 1,
               "status": "committed", "candidate": str(candidate.resolve()),
               "request_model": MODEL, "provider_model": provider_model,
               "x_request_id": request_id, "request_id_source": request_id_source,
               "request_sha256": request_sha256,
               "prompt_sha256": _sha(prompt), "response_sha256": _sha(raw),
               "file_sha256": _sha(image), "byte_length": len(image),
               "width": width, "height": height, "size": SIZE, "quality": QUALITY,
               "alt": alt,
               "rights_provenance": "Generated for the account owner through the configured OpenAI-compatible Image API; use is subject to the provider terms.",
               "endpoint": endpoint, "api_key_source": key_source,
               "created_at": datetime.now(timezone.utc).isoformat()}
    _atomic_json(receipt_path, receipt)
    _atomic_json(intent_path, {**intent, "status": "committed",
                               "receipt_sha256": _sha(receipt_path.read_bytes())})
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "verify"))
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--alt-file", type=Path)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--intent", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "verify":
            result = verify(args.candidate, args.receipt)
        else:
            if args.prompt_file is None or args.alt_file is None or args.intent is None:
                parser.error("generate requires --prompt-file, --alt-file, and --intent")
            result = generate(prompt_path=args.prompt_file, alt_path=args.alt_file,
                              candidate=args.candidate, intent_path=args.intent,
                              receipt_path=args.receipt)
    except (HeadlineImageRefused, OSError) as error:
        print(json.dumps({"status": "refused", "reason": str(error)}, sort_keys=True), file=os.sys.stderr)
        return 75
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
