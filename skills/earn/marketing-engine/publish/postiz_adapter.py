#!/usr/bin/env python3
"""At-most-once Postiz draft/promote adapter over durable publication intents."""

from __future__ import annotations

import datetime as dt
import json
import mimetypes
import pathlib
import urllib.parse
import urllib.request
import uuid

from intent_store import IntentStore, caption_sha256

POSTIZ = "https://api.postiz.com/public/v1"


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def unique_remote_match(intent: dict, posts: list[dict], window_seconds: int = 900) -> dict | None:
    expected = parse_time(intent["scheduled_at"])
    matches = []
    for post in posts:
        integration = post.get("integration") or {}
        if str(integration.get("id") or "") != intent["integration_id"]:
            continue
        if caption_sha256(str(post.get("content") or "")) != intent["caption_sha256"]:
            continue
        try:
            observed = parse_time(str(post.get("publishDate") or ""))
        except ValueError:
            continue
        if abs((observed - expected).total_seconds()) <= window_seconds:
            matches.append(post)
    if len(matches) > 1:
        raise ValueError("multiple remote candidates")
    return matches[0] if matches else None


class HttpPostizClient:
    def __init__(self, api_key: str, base_url: str = POSTIZ):
        if not api_key:
            raise ValueError("POSTIZ_API_KEY missing")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _json(self, method: str, path: str, payload: dict | None = None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base_url + path, method=method, data=data,
            headers={"Authorization": self.api_key, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    def create_draft(self, payload: dict):
        return self._json("POST", "/posts", payload)

    def list_integrations(self):
        return self._json("GET", "/integrations")

    def list_posts(self, start: dt.datetime, end: dt.datetime):
        query = urllib.parse.urlencode({
            "startDate": start.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "endDate": end.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        })
        body = self._json("GET", f"/posts?{query}")
        if isinstance(body, list):
            return body
        if not isinstance(body, dict) or not isinstance(body.get("posts"), list):
            raise ValueError("Postiz posts response malformed")
        return body["posts"]

    def upload_file(self, path: pathlib.Path):
        path = pathlib.Path(path)
        boundary = f"----anicca-{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            self.base_url + "/upload", method="POST", data=body,
            headers={"Authorization": self.api_key,
                     "Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)

    def promote(self, post_id: str):
        return self._json("PUT", f"/posts/{urllib.parse.quote(post_id)}/status",
                          {"status": "schedule"})


class PostizAdapter:
    def __init__(self, store: IntentStore, client):
        self.store = store
        self.client = client

    def _draft_payload(self, intent: dict) -> dict:
        current = self.store.get(intent["publish_key"])
        media_id = current.get("provider_media_id")
        media_path = current.get("provider_media_path")
        if not media_id or not media_path:
            raise ValueError("cannot create draft without stored media receipt")
        return {
            "type": "draft", "date": intent["scheduled_at"], "shortLink": False,
            "tags": [], "posts": [{"integration": {"id": intent["integration_id"]},
                "value": [{"content": intent["caption"], "image": [
                    {"id": media_id, "path": media_path}
                ]}],
                "settings": intent["provider_settings"]}],
        }

    def upload_media(self, publish_key: str, owner: str, fence: int, *, now: str) -> dict:
        intent = self.store.get(publish_key)["intent"]
        request = {"asset_path": intent["asset_path"],
                   "asset_sha256": intent["asset_sha256"], "mime_type": "video/mp4"}
        attempt = self.store.begin_dispatch(publish_key, owner=owner, fence=fence,
                                            operation="upload_media", request=request, now=now)
        if not attempt["created"]:
            return attempt
        try:
            response = self.client.upload_file(pathlib.Path(intent["asset_path"]))
        except (TimeoutError, ConnectionError, OSError) as exc:
            return self.store.mark_uncertain(attempt["attempt_id"],
                                             f"{type(exc).__name__}: {exc}", now=now)
        try:
            return self.store.record_response(attempt["attempt_id"], response, now=now)
        except ValueError as exc:
            self.store.mark_rejected(attempt["attempt_id"], str(exc), now=now)
            raise

    def create_draft(self, publish_key: str, owner: str, fence: int, *, now: str) -> dict:
        intent = self.store.get(publish_key)["intent"]
        payload = self._draft_payload(intent)
        attempt = self.store.begin_dispatch(publish_key, owner=owner, fence=fence,
                                            operation="create_draft", request=payload, now=now)
        if not attempt["created"]:
            return attempt
        try:
            response = self.client.create_draft(payload)
        except (TimeoutError, ConnectionError, OSError) as exc:
            return self.store.mark_uncertain(attempt["attempt_id"],
                                             f"{type(exc).__name__}: {exc}", now=now)
        first = response[0] if isinstance(response, list) and response else response
        integration = first.get("integration") if isinstance(first, dict) else None
        try:
            if integration != intent["integration_id"]:
                raise ValueError("Postiz create integration mismatch")
            return self.store.record_response(attempt["attempt_id"], response, now=now)
        except ValueError as exc:
            self.store.mark_rejected(attempt["attempt_id"], str(exc), now=now)
            raise

    def promote(self, publish_key: str, owner: str, fence: int, *, now: str) -> dict:
        current = self.store.get(publish_key)
        post_id = current["provider_post_id"]
        if not post_id:
            raise ValueError("cannot promote without stored postId")
        request = {"post_id": post_id, "status": "schedule"}
        attempt = self.store.begin_dispatch(publish_key, owner=owner, fence=fence,
                                            operation="promote", request=request, now=now)
        if not attempt["created"]:
            return attempt
        try:
            response = self.client.promote(post_id)
        except (TimeoutError, ConnectionError, OSError) as exc:
            return self.store.mark_uncertain(attempt["attempt_id"],
                                             f"{type(exc).__name__}: {exc}", now=now)
        try:
            if (not isinstance(response, dict) or
                    str(response.get("id") or "") != post_id or
                    response.get("state") != "QUEUE"):
                raise ValueError("Postiz promote response mismatch")
            return self.store.record_response(attempt["attempt_id"], response, now=now)
        except ValueError as exc:
            self.store.mark_rejected(attempt["attempt_id"], str(exc), now=now)
            raise

    def shadow(self, publish_key: str, owner: str, fence: int, *, now: str) -> dict:
        self.store.assert_lease(publish_key, owner, fence, now)
        intent = self.store.get(publish_key)["intent"]
        payload = {"asset_path": intent["asset_path"], "asset_sha256": intent["asset_sha256"],
                   "caption_sha256": intent["caption_sha256"],
                   "integration_id": intent["integration_id"]}
        return {"status": "shadow_valid", "publish_key": publish_key,
                "request_sha256": __import__("hashlib").sha256(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                "external_effects": []}
