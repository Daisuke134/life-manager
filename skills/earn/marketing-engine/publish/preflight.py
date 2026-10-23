#!/usr/bin/env python3
"""Fail-closed product, account, asset, CTA, and visual publication preflight."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE / "gates"))

from intent_store import file_sha256  # noqa: E402
from publication_context import (PublishContext, require_exact_destination,
                                 resolve_publication_route)  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_jsonl(path: pathlib.Path) -> list[dict]:
    if not pathlib.Path(path).exists():
        return []
    return [json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def probe_media(path: pathlib.Path) -> dict:
    try:
        completed = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration,format_name:stream=codec_type,codec_name,width,height",
            "-of", "json", str(path),
        ], check=True, capture_output=True, text=True, timeout=30)
        payload = json.loads(completed.stdout)
    except (FileNotFoundError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise ValueError("ffprobe could not verify publication asset") from exc
    streams = payload.get("streams") or []
    video = next((row for row in streams if row.get("codec_type") == "video"), {})
    audio = next((row for row in streams if row.get("codec_type") == "audio"), {})
    format_row = payload.get("format") or {}
    try:
        duration = float(format_row.get("duration"))
        width = int(video.get("width"))
        height = int(video.get("height"))
    except (TypeError, ValueError) as exc:
        raise ValueError("publication asset media metadata incomplete") from exc
    return {
        "duration_seconds": duration,
        "format_names": str(format_row.get("format_name") or "").split(","),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "width": width,
        "height": height,
    }


def validate_media(media: dict) -> dict:
    require("mp4" in media.get("format_names", []), "publication asset must be MP4")
    require(media.get("video_codec") == "h264", "publication video must use H.264")
    require(media.get("audio_codec") == "aac", "publication audio must use AAC")
    width = media.get("width")
    height = media.get("height")
    require(isinstance(width, int) and isinstance(height, int) and height > 0,
            "publication asset dimensions are invalid")
    require(abs(width / height - 9 / 16) <= 0.02,
            "publication asset must use a 9:16 vertical aspect ratio")
    require(width >= 720 and height >= 1280,
            "publication asset must be at least 720x1280")
    duration = media.get("duration_seconds")
    require(isinstance(duration, (int, float)) and 1 <= duration <= 180,
            "publication asset duration must be between 1 and 180 seconds")
    return media


def validate_preflight(intent: dict, *, engine: pathlib.Path = ENGINE,
                       approvals_path: pathlib.Path,
                       media_probe=probe_media,
                       context: PublishContext | None = None) -> dict:
    account_id = intent.get("account_id")
    product_id = intent.get("product_id")
    account, product = resolve_publication_route(
        engine=engine, account_id=account_id, product_id=product_id, context=context)
    require(account["status"] == "approved_active", "account is not approved_active")
    require(account["product_id"] == product_id, "publication account product mismatch")
    require(account["platform"] == intent.get("platform"), "publication platform mismatch")
    require(account["publisher_integration_id"] == intent.get("integration_id"),
            "publication integration mismatch")
    require(account["native_handle"].casefold() == str(intent.get("native_handle") or "").casefold(),
            "publication native handle mismatch")
    require(account["publisher_settings"] == intent.get("provider_settings"),
            "publication provider settings mismatch")
    require(intent.get("renderer_id") in account["allowed_renderer_ids"],
            "publication renderer not allowed")
    asset = pathlib.Path(intent.get("asset_path") or "")
    require(asset.is_file(), "publication asset missing")
    require(file_sha256(asset) == intent.get("asset_sha256"), "publication asset hash mismatch")
    media = validate_media(media_probe(asset))
    caption = str(intent.get("caption") or "")
    require(product["cta"] in caption, "publication CTA missing")
    require(intent.get("attribution_token") in caption, "publication attribution token missing")
    if context is None:
        require(f"https://aniccaai.com/go/{intent['attribution_token']}" in caption,
                "owned attribution URL missing")
    else:
        require_exact_destination(caption, context.destination_url)
    approvals = [row for row in read_jsonl(approvals_path)
                 if row.get("approval_id") == intent.get("visual_approval_id") and
                 row.get("status") == "accepted"]
    require(len(approvals) == 1, "accepted visual approval missing")
    approval = approvals[0]
    require(approval.get("asset_sha256") == intent["asset_sha256"],
            "visual approval asset mismatch")
    require(approval.get("product_id") == product_id and approval.get("account_id") == account_id,
            "visual approval route mismatch")
    return {"status": "dispatchable", "publish_key": intent["publish_key"],
            "product_id": product_id, "account_id": account_id,
            "asset_sha256": intent["asset_sha256"], "media": media,
            "external_effects": []}
