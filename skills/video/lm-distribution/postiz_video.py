#!/usr/bin/env python3
"""Post one existing MP4 to TikTok or YouTube through Postiz."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


BASE_URL = "https://api.postiz.com/public/v1"
PUBLIC_POST_DETAILS_URL = "https://api.postiz.com/public/posts"
POSTIZ_API_HOST = "api.postiz.com"


class PostizError(RuntimeError):
    pass


def validate_resolve_ip(value: str | None) -> str | None:
    """Validate the opt-in Postiz IPv4 endpoint override."""
    if value is None:
        return None
    if not isinstance(value, str) or not value or value != value.strip():
        raise PostizError("LM_POSTIZ_RESOLVE_IP must be a public IPv4 address")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise PostizError("LM_POSTIZ_RESOLVE_IP must be a public IPv4 address") from exc
    if (
        not isinstance(address, ipaddress.IPv4Address)
        or not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise PostizError("LM_POSTIZ_RESOLVE_IP must be a public IPv4 address")
    return str(address)


@contextmanager
def postiz_resolve_override(resolve_ip: str | None):
    """Temporarily resolve only Postiz's API hostname to one IPv4 literal."""
    address = validate_resolve_ip(resolve_ip)
    if address is None:
        yield
        return
    original = socket.getaddrinfo

    def resolve(host, port, family=0, type=0, proto=0, flags=0):
        if host != POSTIZ_API_HOST or family not in (0, socket.AF_UNSPEC, socket.AF_INET):
            return original(host, port, family, type, proto, flags)
        return original(address, port, family, type, proto, flags)

    socket.getaddrinfo = resolve
    try:
        yield
    finally:
        socket.getaddrinfo = original


def build_payload(
    *,
    integration: str,
    caption: str,
    title: str,
    upload_id: str | None = None,
    upload_path: str | None = None,
    now_iso: str = "",
    platform: str = "tiktok",
    upload_ids: list[str] | None = None,
    upload_paths: list[str] | None = None,
) -> dict:
    if (upload_ids is None) != (upload_paths is None):
        raise PostizError("Postiz upload ids/paths must be supplied together")
    if upload_ids is not None:
        if len(upload_ids) != len(upload_paths) or not upload_ids:
            raise PostizError("Postiz carousel uploads are invalid")
        uploads = [{"id": item_id, "path": item_path} for item_id, item_path in zip(upload_ids, upload_paths)]
    else:
        uploads = [{"id": upload_id, "path": upload_path}]
    if platform == "instagram" and upload_ids is not None and len(uploads) < 2:
        raise PostizError("Instagram carousel requires at least two images")
    if upload_ids is not None and platform not in ("instagram", "tiktok"):
        raise PostizError("carousel images require Instagram or TikTok")
    if upload_ids is not None and any(not re.search(r"\.(?:jpe?g)(?:\?.*)?$", str(item), re.I) for item in upload_paths):
        raise PostizError("carousel media must be JPEG images")
    if platform == "youtube":
        settings = {
            "__type": "youtube",
            "title": title,
            "type": "public",
            "selfDeclaredMadeForKids": "no",
            "thumbnail": None,
            "tags": [],
        }
    elif platform == "instagram":
        settings = {
            "__type": "instagram-standalone",
            "post_type": "post",
            "is_trial_reel": False,
            "collaborators": [],
        }
    elif platform == "tiktok":
        settings = {
            "__type": "tiktok",
            "title": title,
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "duet": False,
            "stitch": False,
            "comment": True,
            "autoAddMusic": "yes",
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
            "video_made_with_ai": True,
            "content_posting_method": "DIRECT_POST",
        }
    else:
        raise PostizError("Postiz platform is invalid")
    return {
        "type": "now",
        "date": now_iso,
        "shortLink": False,
        "tags": [],
        "posts": [
            {
                "integration": {"id": integration},
                "value": [{"content": caption, "image": uploads}],
                "settings": settings,
            }
        ],
    }


def extract_post_id(response) -> str:
    if isinstance(response, list) and response and isinstance(response[0], dict):
        post_id = response[0].get("postId")
        if isinstance(post_id, str) and post_id:
            return post_id
    raise PostizError("Postiz create response did not contain postId")


def _valid_public_url(platform: str, value: str | None) -> bool:
    if platform == "instagram":
        return bool(re.fullmatch(r"https://www\.instagram\.com/(?:reel|p)/[A-Za-z0-9_-]+/?", value or ""))
    if platform == "tiktok":
        return bool(re.fullmatch(r"https://www\.tiktok\.com/@[^/]+/video/[0-9]+/?", value or ""))
    if platform == "youtube":
        return bool(re.fullmatch(
            r"https://www\.youtube\.com/(?:shorts/[A-Za-z0-9_-]+|watch\?v=[A-Za-z0-9_-]+(?:&[^#]+)?)/?",
            value or "",
        ))
    return False


def _valid_tiktok_profile_url(value: str | None) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"https://www\.tiktok\.com/@[^/]+/?", value))


def _parse_post_settings(value) -> dict | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _tiktok_photo_proof_from_row(row: dict, url: str | None) -> dict | None:
    if row.get("state") != "PUBLISHED":
        return None
    if url is not None and not _valid_tiktok_profile_url(url):
        return None
    release_id = row.get("releaseId")
    if not isinstance(release_id, str) or not re.fullmatch(r"p_pub_url~v2\.[0-9]+", release_id):
        return None
    settings = _parse_post_settings(row.get("settings"))
    if not settings or settings.get("__type") != "tiktok":
        return None
    title = settings.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    posting_method = settings.get("content_posting_method")
    if posting_method != "DIRECT_POST":
        return None
    integration = row.get("integration")
    integration_id = integration.get("id") if isinstance(integration, dict) else row.get("integrationId")
    if not isinstance(integration_id, str) or not integration_id.strip():
        return None
    content = row.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return {
        "state": "PUBLISHED",
        "post_url": None,
        "integration_id": integration_id,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "title": title,
        "posting_method": posting_method,
        "release_id": release_id,
    }


def _valid_instagram_carousel_url(value: str | None) -> bool:
    """A native photo carousel is a direct Instagram post, never a Reel/profile URL."""
    return bool(re.fullmatch(
        r"https://www\.instagram\.com/p/(?=[A-Za-z0-9_-]*[A-Za-z_-])[A-Za-z0-9_-]+/?",
        value or "",
    ))


def find_post(response, post_id: str, platform: str = "tiktok") -> dict:
    posts = response.get("posts", []) if isinstance(response, dict) else response
    if not isinstance(posts, list):
        raise PostizError("Postiz list response has no posts array")
    match = next((row for row in posts if isinstance(row, dict) and row.get("id") == post_id), None)
    if not match:
        return {"state": "UNKNOWN", "post_url": None}
    state = match.get("state") or "UNKNOWN"
    url = match.get("releaseURL")
    if url is None:
        url = match.get("releaseUrl")
    release_id = match.get("releaseId")
    if state == "PUBLISHED" and platform == "tiktok" and re.fullmatch(
        r"https://www\.tiktok\.com/@[^/]+/?", url or "",
    ):
        video = re.fullmatch(r"v_pub_file~v2(?:-1)?\.([0-9]+)", str(release_id or ""))
        if video:
            url = f"{url.rstrip('/')}/video/{video.group(1)}"
    if state == "PUBLISHED" and platform == "youtube" and not _valid_public_url(platform, url):
        # Postiz may expose a channel URL while the provider row carries the
        # authoritative YouTube video id. Construct only from that exact id;
        # the caller still requires a direct URL before recording a receipt.
        youtube_release_id = str(release_id or "")
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", youtube_release_id):
            url = f"https://www.youtube.com/watch?v={youtube_release_id}"
    if state == "PUBLISHED" and platform == "tiktok":
        photo_proof = _tiktok_photo_proof_from_row(match, url)
        if photo_proof:
            return photo_proof
        if isinstance(release_id, str) and release_id.startswith("p_pub_url~"):
            raise PostizError("Postiz PUBLISHED TikTok photo proof is invalid")
    if state == "PUBLISHED" and (not isinstance(url, str) or not url.startswith("https://")):
        raise PostizError("Postiz marked PUBLISHED without a public release URL")
    return {"state": state, "post_url": url if isinstance(url, str) else None}


def find_existing_post(
    response,
    *,
    integration: str,
    caption: str,
    video_sha256: str,
    platform: str = "tiktok",
) -> dict | None:
    posts = response.get("posts", []) if isinstance(response, dict) else response
    if not isinstance(posts, list):
        raise PostizError("Postiz list response has no posts array")
    for row in reversed(posts):
        if not isinstance(row, dict):
            continue
        row_integration = row.get("integration")
        integration_id = (
            row_integration.get("id") if isinstance(row_integration, dict) else row.get("integrationId")
        )
        # Caption equality cannot identify a publication effect: scheduled lanes
        # legitimately reuse copy for different video bytes. Postiz's normal list
        # response does not carry this Life Manager digest, so it fails closed and
        # the exact creative/video/caption local ledger remains the only reuse path.
        if (
            integration_id != integration
            or _normalized(str(row.get("content") or "")) != _normalized(caption)
            or row.get("lifeManagerVideoSha256") != video_sha256
        ):
            continue
        post_id = row.get("id")
        if not isinstance(post_id, str) or not post_id:
            continue
        state = find_post([row], post_id, platform)
        if state["state"] != "PUBLISHED":
            continue
        if _valid_public_url(platform, state.get("post_url")):
            if platform == "tiktok" and not verify_tiktok_public_url(
                state["post_url"],
                caption,
                posted_after=_published_after_epoch(row.get("publishDate") or row.get("date")),
            ):
                raise PostizError("TikTok public readback did not match the provider URL")
            return {"post_id": post_id, **state, "reconciled": True}
        if platform == "tiktok":
            posted_after = _published_after_epoch(row.get("publishDate") or row.get("date"))
            resolved = resolve_profile_release_url(
                str(state.get("post_url") or ""),
                caption,
                posted_after=posted_after,
                browser_resolver=_resolve_profile_release_url_browser,
            )
            if resolved and verify_tiktok_public_url(resolved, caption, posted_after=posted_after):
                return {
                    "post_id": post_id,
                    "state": "PUBLISHED",
                    "post_url": resolved,
                    "reconciled": True,
                }
    return None


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _published_after_epoch(value) -> int:
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError, OverflowError):
        return int(time.time()) - 7200


def _matching_profile_url(rows, caption_prefix: str, posted_after: int) -> str | None:
    candidates = []
    for row in rows if isinstance(rows, list) else []:
        url = row.get("href") if isinstance(row, dict) else None
        alt = row.get("alt") if isinstance(row, dict) else ""
        match = re.fullmatch(r"https://www\.tiktok\.com/@[^/]+/video/([0-9]+)/?", url or "")
        if (
            match
            and caption_prefix
            and caption_prefix in _normalized(str(alt))
            and (int(match.group(1)) >> 32) >= posted_after - 5
        ):
            candidates.append((int(match.group(1)), url))
    return max(candidates)[1] if candidates else None


def verify_tiktok_public_url(
    public_url: str,
    caption: str,
    *,
    posted_after: int,
    browser_resolver=None,
) -> bool:
    """Require a visible profile receipt for the exact provider URL and caption.

    Postiz can report PUBLISHED while TikTok later hides or rejects the video. The
    profile readback is the existing browser-owned observation path; matching the
    exact URL prevents a newer duplicate with the same caption from proving the
    older provider row.
    """
    match = re.fullmatch(r"https://www\.tiktok\.com/@([^/]+)/video/[0-9]+/?", public_url or "")
    if not match or not isinstance(caption, str) or not caption.strip():
        return False
    resolver = browser_resolver or _resolve_profile_release_url_browser
    observed = resolver(
        f"https://www.tiktok.com/@{match.group(1)}",
        caption,
        posted_after=posted_after,
        caption_prefix=_normalized(caption)[:24].strip(),
    )
    return observed == public_url


def resolve_profile_release_url(
    profile_url: str,
    caption: str,
    *,
    posted_after: int,
    runner=subprocess.run,
    browser_resolver=None,
) -> str | None:
    if not re.fullmatch(r"https://www\.tiktok\.com/@[^/]+/?", profile_url):
        return None
    caption_prefix = _normalized(caption)[:24].strip()
    try:
        proc = runner(
            [
                "yt-dlp",
                "--flat-playlist",
                "--playlist-end",
                "12",
                "--dump-single-json",
                profile_url,
            ],
            text=True,
            capture_output=True,
            timeout=60,
        )
    except OSError:
        proc = None
    if proc is not None and proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = None
        entries = data.get("entries", []) if isinstance(data, dict) else []
        candidates = []
        for row in entries:
            if not isinstance(row, dict):
                continue
            url = row.get("url")
            title = row.get("title") or row.get("description") or ""
            timestamp = row.get("timestamp")
            if (
                isinstance(url, str)
                and re.fullmatch(r"https://www\.tiktok\.com/@[^/]+/video/[0-9]+/?", url)
                and isinstance(timestamp, (int, float))
                and timestamp >= posted_after - 5
                and _normalized(str(title)).startswith(caption_prefix)
            ):
                candidates.append((timestamp, url))
        if candidates:
            return max(candidates)[1]
    if browser_resolver is not None:
        return browser_resolver(
            profile_url,
            caption,
            posted_after=posted_after,
            caption_prefix=caption_prefix,
        )
    return None


def _resolve_profile_release_url_browser(
    profile_url: str,
    caption: str,
    *,
    posted_after: int,
    caption_prefix: str | None = None,
) -> str | None:
    """Read the newest profile DOM when yt-dlp cannot read TikTok's JS page."""
    del caption
    try:
        import websockets
    except ImportError:
        return None
    prefix = caption_prefix or ""

    async def read_profile():
        host = os.environ.get("CDP_HOST", "127.0.0.1")
        port = os.environ.get("CDP_PORT", "9222")
        version = json.loads(urllib.request.urlopen(
            f"http://{host}:{port}/json/version", timeout=8,
        ).read())
        websocket_url = version["webSocketDebuggerUrl"]
        async with websockets.connect(
            websocket_url, open_timeout=10, ping_interval=None, max_size=64 * 1024 * 1024,
        ) as socket:
            sequence = 0

            async def call(method, params=None, session_id=None):
                nonlocal sequence
                sequence += 1
                request = {"id": sequence, "method": method, "params": params or {}}
                if session_id:
                    request["sessionId"] = session_id
                await socket.send(json.dumps(request))
                while True:
                    response = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
                    if response.get("id") == sequence:
                        if response.get("error"):
                            raise RuntimeError("TikTok profile CDP read failed")
                        return response.get("result", {})

            target_id = (await call("Target.createTarget", {"url": profile_url}))["targetId"]
            try:
                session_id = (await call(
                    "Target.attachToTarget", {"targetId": target_id, "flatten": True},
                ))["sessionId"]
                await asyncio.sleep(8)
                expression = "JSON.stringify([...document.querySelectorAll('a[href*=\"/video/\"]')].slice(0,20).map(e=>({href:e.href,alt:e.querySelector('img')?.alt||''})))"
                result = await call(
                    "Runtime.evaluate", {"expression": expression, "returnByValue": True}, session_id,
                )
                value = result.get("result", {}).get("value")
                return _matching_profile_url(json.loads(value), prefix, posted_after) if isinstance(value, str) else None
            finally:
                await call("Target.closeTarget", {"targetId": target_id})

    try:
        return asyncio.run(read_profile())
    except Exception:
        return None


def _request_json(request: urllib.request.Request, timeout: int = 90):
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        status = getattr(exc, "code", None)
        suffix = f" HTTP {status}" if status else ""
        raise PostizError(f"Postiz request failed{suffix}") from exc


def read_post_error(post_id: str, api_key: str) -> str | None:
    """Read the provider-owned terminal reason without exposing credentials.

    The public v1 list intentionally omits Postiz's ``error`` column.  The
    public preview endpoint still returns that field for one post, so only
    terminal ERROR states make this extra read.  A missing detail is kept as
    unknown rather than being converted into success or zero.
    """
    request = urllib.request.Request(
        f"{PUBLIC_POST_DETAILS_URL}/{urllib.parse.quote(post_id, safe='')}",
        headers={"Authorization": api_key},
    )
    try:
        response = _request_json(request)
    except PostizError:
        return None
    rows = response if isinstance(response, list) else []
    row = rows[0] if rows and isinstance(rows[0], dict) else None
    reason = row.get("error") if row else None
    return reason.strip() if isinstance(reason, str) and reason.strip() else None


def upload_media(media: Path, api_key: str, *, default_suffix: str, default_mime: str) -> tuple[str, str]:
    boundary = "----life-manager-" + uuid.uuid4().hex
    filename = media.name.replace('"', "")
    if not Path(filename).suffix:
        filename = f"{filename}{default_suffix}"
    mime = mimetypes.guess_type(filename)[0] or default_mime
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode()
    body = head + media.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"{BASE_URL}/upload",
        data=body,
        method="POST",
        headers={
            "Authorization": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    response = _request_json(request)
    upload_id = response.get("id") if isinstance(response, dict) else None
    upload_path = response.get("path") if isinstance(response, dict) else None
    if not isinstance(upload_id, str) or not upload_id or not isinstance(upload_path, str) or not upload_path:
        raise PostizError("Postiz upload response is missing id/path")
    return upload_id, upload_path


def upload_video(video: Path, api_key: str) -> tuple[str, str]:
    return upload_media(video, api_key, default_suffix=".mp4", default_mime="video/mp4")


def upload_image(image: Path, api_key: str) -> tuple[str, str]:
    if not image.is_file() or image.stat().st_size == 0:
        raise PostizError("carousel image is missing or empty")
    if not image.read_bytes().startswith(b"\xff\xd8\xff"):
        raise PostizError("carousel image is not JPEG")
    return upload_media(image, api_key, default_suffix=".jpg", default_mime="image/jpeg")


def create_post(payload: dict, api_key: str) -> str:
    request = urllib.request.Request(
        f"{BASE_URL}/posts",
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
    )
    return extract_post_id(_request_json(request))


def read_publish_state(post_id: str, api_key: str, platform: str = "tiktok") -> dict:
    now = datetime.now(timezone.utc)
    query = urllib.parse.urlencode(
        {
            "startDate": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "endDate": (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "limit": "100",
        }
    )
    request = urllib.request.Request(
        f"{BASE_URL}/posts?{query}",
        headers={"Authorization": api_key},
    )
    state = find_post(_request_json(request), post_id, platform)
    if state.get("state") == "ERROR":
        reason = read_post_error(post_id, api_key)
        if reason:
            state["error"] = reason
    return state


def read_recent_posts(api_key: str, hours: int = 6):
    now = datetime.now(timezone.utc)
    query = urllib.parse.urlencode(
        {
            "startDate": (now - timedelta(hours=hours)).isoformat().replace("+00:00", "Z"),
            "endDate": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "limit": "100",
        }
    )
    request = urllib.request.Request(
        f"{BASE_URL}/posts?{query}",
        headers={"Authorization": api_key},
    )
    return _request_json(request)


def is_tiktok_photo_proof(
    state: dict,
    integration: str | None = None,
    caption: str | None = None,
    title: str | None = None,
) -> bool:
    if not isinstance(state, dict) or state.get("state") != "PUBLISHED" or state.get("post_url") is not None:
        return False
    if not isinstance(state.get("integration_id"), str) or not state["integration_id"].strip():
        return False
    if integration is not None and state.get("integration_id") != integration:
        return False
    content_sha256 = state.get("content_sha256")
    if not isinstance(content_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", content_sha256):
        return False
    if caption is not None and content_sha256 != hashlib.sha256(caption.encode("utf-8")).hexdigest():
        return False
    if not isinstance(state.get("title"), str) or not state["title"].strip():
        return False
    if title is not None and state.get("title") != title:
        return False
    return (
        state.get("posting_method") == "DIRECT_POST"
        and isinstance(state.get("release_id"), str)
        and re.fullmatch(r"p_pub_url~v2\.[0-9]+", state["release_id"]) is not None
    )


def is_reconciled_state(state: dict, platform: str = "tiktok") -> bool:
    return (
        isinstance(state, dict)
        and state.get("state") == "PUBLISHED"
        and (_valid_public_url(platform, state.get("post_url")) or (
            platform == "tiktok" and is_tiktok_photo_proof(state)
        ))
    )


def read_caption(caption_file: Path, *, carousel: bool = False) -> str:
    raw = caption_file.read_text(encoding="utf-8")
    if not raw.strip():
        raise PostizError("caption is empty")
    return raw if carousel else raw.strip()


def _publish(args, api_key: str, caption: str) -> int:
    if args.image:
        if args.platform not in ("instagram", "tiktok"):
            raise PostizError("carousel images require Instagram or TikTok")
        if len(args.image) < 2:
            raise PostizError("photo carousel requires at least two images")
        for image in args.image:
            if not image.is_file() or image.stat().st_size == 0:
                raise PostizError("carousel image is missing or empty")
            if not image.read_bytes().startswith(b"\xff\xd8\xff"):
                raise PostizError("carousel image is not JPEG")

        upload_ids = []
        upload_paths = []
        for image in args.image:
            upload_id, upload_path = upload_image(image, api_key)
            upload_ids.append(upload_id)
            upload_paths.append(upload_path)
        expected_title = args.title[:100]
        payload = build_payload(
            integration=args.integration,
            caption=caption,
            title=expected_title,
            upload_id="",
            upload_path="",
            upload_ids=upload_ids,
            upload_paths=upload_paths,
            now_iso=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            platform=args.platform,
        )
        post_id = create_post(payload, api_key)
        state = {"state": "QUEUE", "post_url": None}
        for _ in range(18):
            time.sleep(10)
            state = read_publish_state(post_id, api_key, args.platform)
            if state["state"] == "PUBLISHED":
                if args.platform == "instagram" and _valid_instagram_carousel_url(state.get("post_url")):
                    break
                if args.platform == "tiktok":
                    if is_tiktok_photo_proof(state, args.integration, caption, expected_title):
                        break
            if state["state"] == "ERROR":
                break
        photo_proof = args.platform == "tiktok" and is_tiktok_photo_proof(
            state, args.integration, caption, expected_title,
        )
        result = {
            "post_id": post_id,
            **state,
            "reconciled": state.get("state") == "PUBLISHED" and (
                _valid_instagram_carousel_url(state.get("post_url")) if args.platform == "instagram"
                else photo_proof
            ),
        }
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        valid_url = _valid_instagram_carousel_url(state.get("post_url")) if args.platform == "instagram" else photo_proof
        if state["state"] != "PUBLISHED" or not valid_url:
            reason = state.get("error")
            suffix = f": {reason}" if isinstance(reason, str) and reason else ""
            raise PostizError(f"Postiz terminal state is {state['state']}{suffix}")
        return 0

    if not args.video.is_file() or args.video.stat().st_size == 0:
        raise PostizError("video is missing or empty")

    title = args.title
    if args.platform == "youtube" and title == "Life Manager":
        title = next((line.strip() for line in caption.splitlines() if line.strip()), title)
    title = title[:100]
    if len(title) < 2:
        raise PostizError("Postiz title is too short")

    existing = find_existing_post(
        read_recent_posts(api_key),
        integration=args.integration,
        caption=caption,
        video_sha256=hashlib.sha256(args.video.read_bytes()).hexdigest(),
        platform=args.platform,
    )
    if existing:
        print(json.dumps(existing, ensure_ascii=False, separators=(",", ":")))
        return 0

    posted_after = int(time.time())
    upload_id, upload_path = upload_video(args.video, api_key)
    payload = build_payload(
        integration=args.integration,
        caption=caption,
        title=title,
        upload_id=upload_id,
        upload_path=upload_path,
        now_iso=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        platform=args.platform,
    )
    post_id = create_post(payload, api_key)
    state = {"state": "QUEUE", "post_url": None}
    public_verified = False
    for _ in range(18):
        time.sleep(10)
        state = read_publish_state(post_id, api_key, args.platform)
        if state["state"] == "PUBLISHED" and state["post_url"]:
            if _valid_public_url(args.platform, state["post_url"]):
                if args.platform != "tiktok" or verify_tiktok_public_url(
                    state["post_url"], caption, posted_after=posted_after,
                ):
                    public_verified = True
                    break
            if args.platform == "tiktok":
                resolved = resolve_profile_release_url(
                    state["post_url"],
                    caption,
                    posted_after=posted_after,
                    browser_resolver=_resolve_profile_release_url_browser,
                )
                if resolved and verify_tiktok_public_url(
                    resolved, caption, posted_after=posted_after,
                ):
                    state["post_url"] = resolved
                    public_verified = True
                    break
        if state["state"] == "ERROR":
            break
    # Postiz's PUBLISHED state plus an exact /video/<id> URL is the provider
    # readback required by Life Manager; preserve that provenance in the
    # publication receipt instead of silently downgrading it to false.
    result = {
        "post_id": post_id,
        **state,
        "reconciled": is_reconciled_state(state, args.platform)
        and (args.platform != "tiktok" or public_verified),
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if (
        state["state"] != "PUBLISHED"
        or not _valid_public_url(args.platform, state.get("post_url"))
        or (args.platform == "tiktok" and not public_verified)
    ):
        reason = state.get("error") or (
            "TikTok public readback did not match the provider URL"
            if args.platform == "tiktok" and state["state"] == "PUBLISHED"
            else None
        )
        suffix = f": {reason}" if isinstance(reason, str) and reason else ""
        raise PostizError(f"Postiz terminal state is {state['state']}{suffix}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path)
    parser.add_argument("--image", type=Path, action="append", default=[])
    parser.add_argument("--caption-file", type=Path, required=True)
    parser.add_argument("--integration", required=True)
    parser.add_argument("--title", default="Life Manager")
    parser.add_argument("--platform", choices=("instagram", "tiktok", "youtube"), default="tiktok")
    args = parser.parse_args()

    api_key = os.environ.get("POSTIZ_API_KEY", "")
    if not api_key:
        raise PostizError("POSTIZ_API_KEY is unavailable")
    caption = read_caption(args.caption_file, carousel=bool(args.image))

    if args.video is None and not args.image:
        raise PostizError("video or carousel images are required")
    if args.video is not None and args.image:
        raise PostizError("video and carousel images are mutually exclusive")

    resolve_ip = validate_resolve_ip(os.environ.get("LM_POSTIZ_RESOLVE_IP"))
    with postiz_resolve_override(resolve_ip):
        return _publish(args, api_key, caption)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PostizError as exc:
        print(json.dumps({"state": "ERROR", "error": str(exc)}, separators=(",", ":")))
        raise SystemExit(1)
