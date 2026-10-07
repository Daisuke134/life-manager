#!/usr/bin/env python3
"""Perform one exact Postiz readback before releasing a publish fence."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
READ_ONLY_SCRIPT = Path(__file__).with_name("mobile-postiz-effect-reconcile.py")
POSTIZ_V1 = "https://api.postiz.com/public/v1"
POSTIZ_DETAILS = "https://api.postiz.com/public/posts"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
ACCOUNT = re.compile(r"^@[A-Za-z0-9._-]{1,127}$")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VIDEO_DISTRIBUTION = ROOT / "skills/video/lm-distribution"
if str(VIDEO_DISTRIBUTION) not in sys.path:
    sys.path.insert(0, str(VIDEO_DISTRIBUTION))

from distribute import append_distribution_row  # noqa: E402

EBOOK_TOKEN_PREFIXES = {"ebook-en": "ee_", "ebook-ja": "ej_"}


def _load_read_only_module():
    spec = importlib.util.spec_from_file_location(
        "mobile_postiz_effect_reconcile", READ_ONLY_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("read-only reconciler unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_READ_ONLY = _load_read_only_module()
read_identity = _READ_ONLY.read_identity
_valid_identity = _READ_ONLY._valid_identity
_admission_state = _READ_ONLY._admission_state

try:
    from runtime.host import resource_admission as _resource_admission
    from runtime.host.resource_admission import resolve_unknown_occurrence
except ImportError as exc:  # pragma: no cover - only reached from a malformed release
    raise RuntimeError("resource admission unavailable") from exc


def _inconclusive(owner_id: str, occurrence_id: str, reason: str) -> dict[str, str]:
    return {
        "status": "inconclusive",
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "reason": reason,
    }


def _authoritative_admission_db() -> Path:
    return Path(_resource_admission._durable_paths()[3]).expanduser().resolve()


def _pending_unknown_count(admission_db: Path, owner_id: str) -> int | None:
    try:
        database = admission_db.expanduser().resolve()
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM occurrences WHERE owner_id=? "
                "AND state IN ('claimed','released') AND effect_unknown=1",
                (owner_id,),
            ).fetchone()
    except (OSError, sqlite3.Error):
        return None
    return int(row[0]) if row else None


def _request_json(url: str, api_key: str) -> Any:
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("Postiz API key unavailable")
    request = urllib.request.Request(url, headers={"Authorization": api_key})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ValueError("Postiz official readback failed") from exc


def _safe_jsonl(path: Path) -> list[dict[str, Any]] | None:
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600):
            return None
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                data = handle.read(8 * 1024 * 1024 + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    except OSError:
        return None
    if len(data) > 8 * 1024 * 1024:
        return None
    rows: list[dict[str, Any]] = []
    try:
        for raw in data.splitlines():
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                return None
            rows.append(value)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return rows


def _receipt_from_row(row: dict[str, Any]) -> tuple[dict[str, Any], str | None, str | None]:
    receipt = row.get("receipt") if isinstance(row.get("receipt"), dict) else row
    outer_effect = row.get("effect_key") if "receipt" in row else None
    outer_job = row.get("job_id") if "receipt" in row else None
    return receipt, outer_effect, outer_job


def _slot_scoped(identity: dict[str, Any]) -> bool:
    suffix = hashlib.sha256(str(identity.get("slot", "")).encode("utf-8")).hexdigest()
    return str(identity.get("effect_key", "")).endswith(f":{suffix}")


def _receipt_matches(identity: dict[str, Any], row: dict[str, Any]) -> tuple[bool, str | None]:
    receipt, outer_effect, outer_job = _receipt_from_row(row)
    if "receipt" in row:
        if (outer_effect != identity.get("effect_key")
                or outer_job != identity.get("job_id")
                or receipt.get("account_id") != identity.get("account_id")
                or receipt.get("integration_ref") != identity.get("integration_ref")):
            return False, None
        if receipt.get("slot") is not None:
            if receipt.get("slot") != identity.get("slot"):
                return False, None
        elif not _slot_scoped(identity):
            return False, None
    elif receipt.get("slot") != identity.get("slot"):
        return False, None
    common = {
        "product_id": identity.get("product_id"),
        "format_id": identity.get("format_id"),
        "form": identity.get("form"),
        "locale": identity.get("locale"),
        "creative_id": identity.get("creative_id"),
        "platform": identity.get("platform"),
        "caption_sha256": identity.get("caption_sha256"),
    }
    if any(receipt.get(key) != value for key, value in common.items()):
        return False, None
    if receipt.get("slot") is not None and receipt.get("slot") != identity.get("slot"):
        return False, None
    if receipt.get("status") != "published" or receipt.get("provider_reconciled") is not True:
        return False, None
    if identity.get("video_sha256") is not None:
        if receipt.get("video_sha256") != identity.get("video_sha256"):
            return False, None
        provider_id = receipt.get("provider_post_id") or receipt.get("provider_id")
    else:
        if (receipt.get("pack_sha256") != identity.get("pack_sha256")
                or receipt.get("media_sha256") != identity.get("media_sha256")
                or receipt.get("media_order_sha256") != identity.get("media_order_sha256")):
            return False, None
        provider_id = receipt.get("provider_post_id")
    if not isinstance(provider_id, str) or not PROVIDER_ID.fullmatch(provider_id):
        return False, None
    if receipt.get("account_id") is not None and receipt.get("account_id") != identity.get("account_id"):
        return False, None
    expected_integration = identity.get("integration_ref")
    if receipt.get("integration_ref") is not None and receipt.get("integration_ref") != expected_integration:
        return False, None
    return True, provider_id


def _local_receipt(identity: dict[str, Any], ledger: Path) -> tuple[dict[str, Any], str] | None:
    scoped_ledger = ledger.expanduser().resolve()
    expected_product = urllib.parse.quote(str(identity.get("product_id", "")), safe="")
    if scoped_ledger.name != "distribution.jsonl" or scoped_ledger.parent.name != expected_product:
        return None
    rows = _safe_jsonl(ledger)
    if rows is None:
        return None
    candidates: list[tuple[dict[str, Any], str]] = []
    for row in rows:
        candidate = row
        if "receipt" not in row and row.get("product_id") is None:
            # Legacy flat rows omit product_id because their file is product-scoped.
            # Infer it only after validating that exact path.
            candidate = {**row, "product_id": identity.get("product_id")}
        matches, provider_id = _receipt_matches(identity, candidate)
        if matches and provider_id is not None:
            receipt, _, _ = _receipt_from_row(candidate)
            candidates.append((receipt, provider_id))
    unique = {provider_id for _, provider_id in candidates}
    if len(unique) != 1:
        return None
    return candidates[-1]


def _stored_caption(identity: dict[str, Any], ledger: Path) -> str | None:
    if identity.get("video_sha256") is None:
        return None
    descriptor = -1
    try:
        data_dir = ledger.expanduser().resolve().parents[5]
        digest = str(identity["caption_sha256"])
        path = data_dir / "objects" / "sha256" / digest
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600):
            return None
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            content = handle.read(1024 * 1024 + 1)
    except (OSError, KeyError, IndexError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (len(content) > 1024 * 1024
            or hashlib.sha256(content).hexdigest() != identity.get("caption_sha256")):
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _video_caption_normalization(
    identity: dict[str, Any], expected_caption: str | None, provider_caption: str,
) -> str | None:
    """Recognize only the video sender's verified one-terminal-LF trim."""
    if (identity.get("video_sha256") is None
            or not isinstance(expected_caption, str)
            or hashlib.sha256(expected_caption.encode("utf-8")).hexdigest()
            != identity.get("caption_sha256")
            or not expected_caption.endswith("\n")
            or expected_caption[:-1] != expected_caption.strip()
            or expected_caption[:-1] != provider_caption):
        return None
    return "video_terminal_lf_removed"


def _native_carousel_pack_title(identity: dict[str, Any], ledger: Path) -> str:
    pack_sha = str(identity.get("pack_sha256", ""))
    if not HASH.fullmatch(pack_sha):
        raise ValueError("native carousel pack hash is invalid")
    data_root = ledger.expanduser().resolve().parents[5]
    path = data_root / "objects" / "sha256" / pack_sha
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600
            or info.st_size > 1024 * 1024):
        raise ValueError("native carousel pack object is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        payload = handle.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024 or hashlib.sha256(payload).hexdigest() != pack_sha:
        raise ValueError("native carousel pack object hash mismatch")
    pack = json.loads(payload.decode("utf-8"))
    slides = pack.get("slides") if isinstance(pack, dict) else None
    if not isinstance(slides, list) or len(slides) != 6 or not isinstance(slides[0], dict):
        raise ValueError("native carousel pack slides are invalid")
    title = slides[0].get("text")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("native carousel pack title is missing")
    return title


def _is_native_carousel_identity(identity: dict[str, Any]) -> bool:
    return (
        identity.get("product_id") == "anicca-ios"
        and identity.get("platform") == "tiktok"
        and identity.get("video_sha256") is None
        and isinstance(identity.get("media_sha256"), list)
        and len(identity["media_sha256"]) == 6
    )


def _native_carousel_image_hashes(row: dict[str, Any], identity: dict[str, Any]) -> list[str]:
    images = row.get("image")
    if isinstance(images, str):
        images = json.loads(images)
    expected = identity.get("media_sha256")
    if (not isinstance(expected, list) or len(expected) != 6
            or not isinstance(images, list) or len(images) != len(expected)):
        raise ValueError("Postiz carousel image list is invalid")
    hashes: list[str] = []
    for image in images:
        url = image.get("path") if isinstance(image, dict) else None
        parsed = urllib.parse.urlsplit(url) if isinstance(url, str) else None
        if (parsed is None or parsed.scheme != "https" or parsed.hostname != "uploads.postiz.com"
                or parsed.username or parsed.password or parsed.port):
            raise ValueError("Postiz carousel image URL is not allowlisted")
        request = urllib.request.Request(url, headers={"Accept": "image/*"})
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(request, timeout=30) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname != "uploads.postiz.com":
                raise ValueError("Postiz carousel image redirected outside allowlist")
            if not str(response.headers.get("Content-Type", "")).lower().startswith("image/"):
                raise ValueError("Postiz carousel media is not an image")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 20 * 1024 * 1024:
                    raise ValueError("Postiz carousel image exceeds size bound")
                digest.update(chunk)
        hashes.append(digest.hexdigest())
    if hashes != expected:
        raise ValueError("Postiz carousel image bytes or order mismatch")
    order_hash = hashlib.sha256(
        json.dumps(hashes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if order_hash != identity.get("media_order_sha256"):
        raise ValueError("Postiz carousel image order hash mismatch")
    return hashes


def _load_postiz_video_adapter():
    postiz_path = ROOT / "skills/video/lm-distribution/postiz_video.py"
    spec = importlib.util.spec_from_file_location("life_manager_postiz_video", postiz_path)
    if spec is None or spec.loader is None:
        raise ValueError("Postiz adapter unavailable")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return adapter


def _remote_video_receipt(identity: dict[str, Any], ledger: Path,
                          api_key: str) -> tuple[dict[str, Any], str] | None:
    """Recover an exact Postiz post when its local published row was not flushed."""
    caption = _stored_caption(identity, ledger)
    token_prefix = EBOOK_TOKEN_PREFIXES.get(str(identity.get("product_id", "")))
    if (token_prefix is None or caption is None
            or not re.search(
                rf"https://aniccaai\.com/go/{re.escape(token_prefix)}[a-z2-7]{{20}}(?:\b|$)",
                caption,
            )):
        return None
    try:
        slot = datetime.fromisoformat(str(identity["slot"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    if slot.tzinfo is None:
        return None
    slot_utc = slot.astimezone(timezone.utc)
    start = (slot_utc - timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
    end = (slot_utc + timedelta(hours=36)).isoformat().replace("+00:00", "Z")
    query = urllib.parse.urlencode({"startDate": start, "endDate": end, "limit": "100"})
    payload = _request_json(f"{POSTIZ_V1}/posts?{query}", api_key)
    integration_id = str(identity["integration_ref"]).rsplit("/", 1)[-1]
    adapter = _load_postiz_video_adapter()
    matches: dict[str, tuple[dict[str, Any], str | None, str]] = {}
    for row in _rows(payload):
        nested = row.get("integration")
        row_integration = nested.get("id") if isinstance(nested, dict) else row.get("integrationId")
        row_video_sha = row.get("lifeManagerVideoSha256") or row.get("video_sha256")
        provider_id = row.get("id")
        if (row_integration != integration_id
                or (row_video_sha is not None and row_video_sha != identity.get("video_sha256"))
                or not isinstance(provider_id, str)
                or not PROVIDER_ID.fullmatch(provider_id)):
            continue
        try:
            row_caption = _caption(row)
        except ValueError:
            continue
        provider_caption_sha256 = hashlib.sha256(row_caption.encode("utf-8")).hexdigest()
        caption_normalization = _video_caption_normalization(identity, caption, row_caption)
        if (provider_caption_sha256 != identity.get("caption_sha256")
                and caption_normalization is None):
            continue
        try:
            state = adapter.find_post([row], provider_id, identity["platform"])
        except (RuntimeError, ValueError):
            continue
        if (state.get("state") != "PUBLISHED"
                or not adapter._valid_public_url(identity["platform"], state.get("post_url"))):
            continue
        matches[provider_id] = (row, caption_normalization, provider_caption_sha256)
    if len(matches) != 1:
        return None
    provider_id, (row, caption_normalization, provider_caption_sha256) = next(iter(matches.items()))
    selected_video_sha = row.get("lifeManagerVideoSha256") or row.get("video_sha256")
    remote_effect_locator = {
        "source": "postiz_public_v1_posts",
        "post_id": provider_id,
        "integration_id": integration_id,
        "caption_sha256": identity["caption_sha256"],
        "slot": identity["slot"],
    }
    if caption_normalization is not None:
        remote_effect_locator.update({
            "caption_normalization": caption_normalization,
            "provider_caption_sha256": provider_caption_sha256,
        })
    return ({
        "caption_sha256": identity["caption_sha256"],
        "slot": identity["slot"],
        "provider_video_sha256": (
            selected_video_sha if selected_video_sha == identity.get("video_sha256") else None
        ),
        "remote_effect_locator": remote_effect_locator,
    }, provider_id)


def _native_carousel_slot_is_unique(
    identity: dict[str, Any], identity_dir: Path, ledger: Path,
    published_at: datetime, provider_caption: str, provider_title: str,
) -> bool:
    identity_dir = identity_dir.expanduser()
    try:
        sidecars = sorted(identity_dir.glob("*.jsonl"), key=lambda item: item.name)
    except OSError:
        return False
    if not sidecars:
        return False
    occurrence_id = str(identity.get("occurrence_id", ""))
    owner_id = str(identity.get("loop_id", ""))
    published_utc = published_at.astimezone(timezone.utc)
    for sidecar in sidecars:
        rows = _safe_jsonl(sidecar)
        if rows is None:
            return False
        for other in rows:
            other_occurrence = str(other.get("occurrence_id", ""))
            other_owner = str(other.get("loop_id", ""))
            if (other_occurrence == occurrence_id
                    or not _valid_identity(other, other_owner, other_occurrence)
                    or other.get("platform") != identity.get("platform")
                    or other.get("platform") != "tiktok"
                    or other.get("video_sha256") is not None
                    or other.get("account_id") != identity.get("account_id")
                    or other.get("integration_ref") != identity.get("integration_ref")
                    or not isinstance(other.get("media_sha256"), list)
                    or len(other["media_sha256"]) != 6
                    or other.get("media_sha256") != identity.get("media_sha256")
                    or other.get("media_order_sha256") != identity.get("media_order_sha256")
                    or not _native_carousel_caption_matches(provider_caption, other)):
                continue
            try:
                other_title = _native_carousel_pack_title(other, ledger)
                other_slot = datetime.fromisoformat(str(other["slot"]).replace("Z", "+00:00"))
            except (OSError, KeyError, IndexError, TypeError, ValueError):
                return False
            if other_title != provider_title:
                continue
            if (other_slot.tzinfo is None
                    or abs((other_slot.astimezone(timezone.utc) - published_utc).total_seconds()) <= 15 * 60):
                return False
    return True


def _remote_native_carousel_receipt(
    identity: dict[str, Any], ledger: Path, api_key: str,
) -> tuple[dict[str, Any], str] | None:
    if not _is_native_carousel_identity(identity):
        return None
    title = _native_carousel_pack_title(identity, ledger)
    try:
        slot = datetime.fromisoformat(str(identity["slot"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    if slot.tzinfo is None:
        return None
    slot_utc = slot.astimezone(timezone.utc)
    start = (slot_utc - timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
    end = (slot_utc + timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
    query = urllib.parse.urlencode({"startDate": start, "endDate": end, "limit": "100"})
    rows = _rows(_request_json(f"{POSTIZ_V1}/posts?{query}", api_key))
    if len(rows) >= 100:
        return None
    integration_id = str(identity["integration_ref"]).rsplit("/", 1)[-1]
    caption_candidates: list[tuple[dict[str, Any], str, str, datetime]] = []
    for row in rows:
        nested = row.get("integration")
        row_integration = nested.get("id") if isinstance(nested, dict) else row.get("integrationId")
        provider_id = row.get("id")
        if (row.get("state") != "PUBLISHED" or row_integration != integration_id
                or not isinstance(provider_id, str) or not PROVIDER_ID.fullmatch(provider_id)):
            continue
        try:
            published_at = datetime.fromisoformat(str(row["publishDate"]).replace("Z", "+00:00"))
            caption = _caption(row)
        except (KeyError, TypeError, ValueError):
            continue
        if (published_at.tzinfo is None
                or abs((published_at.astimezone(timezone.utc) - slot_utc).total_seconds()) > 15 * 60):
            continue
        caption_sha = hashlib.sha256(caption.encode("utf-8")).hexdigest()
        allowed_caption = _native_carousel_caption_matches(caption, identity)
        if allowed_caption:
            caption_candidates.append((row, provider_id, caption, caption_sha, published_at))
    if len(caption_candidates) != 1:
        return None
    _, provider_id, caption, caption_sha, published_at = caption_candidates[0]
    readback = _provider_readback(
        identity, provider_id, api_key, caption_sha,
        expected_pack_title=title,
    )
    receipt = {
        "schema_version": 1,
        "kind": "marketing_native_carousel_distribution",
        "status": "published",
        "product_id": identity["product_id"],
        "format_id": identity["format_id"],
        "form": identity["form"],
        "locale": identity["locale"],
        "platform": identity["platform"],
        "account_id": identity["account_id"],
        "integration_ref": identity["integration_ref"],
        "creative_id": identity["creative_id"],
        "pack_sha256": identity["pack_sha256"],
        "media_sha256": identity["media_sha256"],
        "media_order_sha256": identity["media_order_sha256"],
        "caption_sha256": identity["caption_sha256"],
        "caption_with_cta_sha256": caption_sha,
        "provider_post_id": provider_id,
        "provider_reconciled": True,
        "public_url": None,
        "provider_state": readback["provider_state"],
        "provider_integration_id": readback["provider_integration_id"],
        "provider_content_sha256": readback["provider_content_sha256"],
        "provider_title": readback["provider_title"],
        "provider_posting_method": readback["provider_posting_method"],
        "provider_release_id": readback["provider_release_id"],
        "published_at": readback["published_at"],
    }
    return receipt, provider_id


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("posts", "integrations", "rows", "data"):
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
        if payload.get("id") is not None:
            return [payload]
    return []


def _postiz_post(post_id: str, api_key: str) -> dict[str, Any]:
    payload = _request_json(
        f"{POSTIZ_DETAILS}/{urllib.parse.quote(post_id, safe='')}", api_key,
    )
    row = next((row for row in _rows(payload) if row.get("id") == post_id), None)
    if row is None:
        raise ValueError("Postiz post is missing")
    return row


def _account(value: Any) -> str | None:
    if isinstance(value, dict):
        candidates = [
            _account(value.get(key))
            for key in ("handle", "username", "profile", "name", "account", "account_id")
            if key in value
        ]
        candidates = [candidate for candidate in candidates if candidate is not None]
        return candidates[0] if candidates and all(item == candidates[0] for item in candidates) else None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = urllib.parse.urlparse(text)
    except ValueError:
        parsed = None
    if parsed and parsed.scheme == "https" and parsed.netloc:
        text = parsed.path.strip("/").split("/")[0]
    text = text if text.startswith("@") else f"@{text}"
    return text if ACCOUNT.fullmatch(text) else None


def _integration(integration_id: str, platform: str, api_key: str) -> str:
    payload = _request_json(f"{POSTIZ_V1}/integrations", api_key)
    row = next((item for item in _rows(payload) if item.get("id") == integration_id), None)
    if row is None:
        raise ValueError("Postiz integration is missing")
    provider = str(row.get("identifier") or row.get("providerIdentifier") or "").lower()
    if provider == "instagram-standalone":
        provider = "instagram"
    if provider != platform:
        raise ValueError("Postiz integration platform mismatch")
    profile = _account(row.get("profile"))
    if profile is None:
        raise ValueError("Postiz integration account is missing")
    return profile


def _expected_postiz_profile(identity: dict[str, Any]) -> str:
    manifest_path = ROOT / "config/marketing-destinations.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("marketing destination manifest unavailable") from exc
    targets = manifest.get("targets") if isinstance(manifest, dict) else None
    if not isinstance(targets, list):
        raise ValueError("marketing destination targets unavailable")
    integration_id = str(identity["integration_ref"]).rsplit("/", 1)[-1]
    matches = [target for target in targets if isinstance(target, dict)
               and target.get("integration_id") == integration_id]
    if not matches:
        return str(identity["account_id"])
    if (len(matches) != 1
            or matches[0].get("platform") != identity.get("platform")
            or matches[0].get("native_handle") != identity.get("account_id")):
        raise ValueError("Postiz destination native account mismatch")
    profile = _account(matches[0].get("postiz_profile"))
    if profile is None:
        raise ValueError("Postiz destination profile is missing")
    return profile


def _caption(row: dict[str, Any]) -> str:
    value = row.get("content")
    if not isinstance(value, str):
        values = row.get("value")
        if isinstance(values, list) and values and isinstance(values[0], dict):
            value = values[0].get("content")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Postiz content is missing")
    return value


# Mirrors CTA_COPY / APP_STORE_URLS in apps/life-manager/lib/marketing-app-store-cta.js:
# the only suffixes the carousel adapter ever appends to an approved caption.
_KNOWN_CTA_LINES = (
    "Link in bio for the app",
    "アプリはプロフィールのリンクから",
    "Get the app → https://apps.apple.com/app/id6755129214",
    "Get the app → https://apps.apple.com/app/id6759667221",
    "アプリはこちら → https://apps.apple.com/app/id6755129214",
    "アプリはこちら → https://apps.apple.com/app/id6759667221",
)


def _ends_with_known_cta(caption: str) -> bool:
    return any(caption.endswith(f"\n\n{line}\n") for line in _KNOWN_CTA_LINES)


def _native_carousel_caption_matches(caption: str, identity: dict[str, Any]) -> bool:
    if hashlib.sha256(caption.encode("utf-8")).hexdigest() == identity.get("caption_sha256"):
        return True
    for line in _KNOWN_CTA_LINES:
        suffix = f"\n\n{line}\n"
        if (caption.endswith(suffix)
                and hashlib.sha256(caption[:-len(suffix)].encode("utf-8")).hexdigest()
                == identity.get("caption_sha256")):
            return True
    return False


def _final_caption_sha256(identity: dict[str, Any], receipt: dict[str, Any]) -> str:
    """Hash of the caption actually sent to Postiz.

    The carousel adapter appends the App Store CTA only to the on-wire copy and
    records that hash as receipt.caption_with_cta_sha256; identity.caption_sha256
    stays the approved base caption. Compare the official readback against the
    exact final hash -- no suffix stripping, no alternative CTA accepted.
    """
    final = receipt.get("caption_with_cta_sha256")
    if final is None:
        return str(identity["caption_sha256"])
    if not isinstance(final, str) or not re.fullmatch(r"[0-9a-f]{64}", final):
        raise ValueError("receipt caption_with_cta_sha256 is invalid")
    return final


def _provider_readback(identity: dict[str, Any], provider_id: str, api_key: str,
                       expected_caption_sha256: str | None = None,
                       expected_caption_text: str | None = None,
                       expected_pack_title: str | None = None) -> dict[str, Any]:
    row = _postiz_post(provider_id, api_key)
    adapter = _load_postiz_video_adapter()
    state = adapter.find_post([row], provider_id, identity["platform"])
    if state.get("state") != "PUBLISHED":
        raise ValueError("Postiz post is not published")
    nested = row.get("integration")
    integration_id = nested.get("id") if isinstance(nested, dict) else row.get("integrationId")
    expected_integration_id = identity["integration_ref"].rsplit("/", 1)[-1]
    if integration_id != expected_integration_id:
        raise ValueError("Postiz post integration mismatch")
    postiz_profile = _integration(str(integration_id), identity["platform"], api_key)
    if postiz_profile != _expected_postiz_profile(identity):
        raise ValueError("Postiz integration profile mismatch")
    caption = _caption(row)
    caption_sha = hashlib.sha256(caption.encode("utf-8")).hexdigest()
    expected_caption_sha = expected_caption_sha256 or identity["caption_sha256"]
    caption_normalization = None
    if caption_sha != expected_caption_sha:
        if expected_caption_sha == identity.get("caption_sha256"):
            caption_normalization = _video_caption_normalization(
                identity, expected_caption_text, caption,
            )
        if caption_normalization is None:
            raise ValueError("Postiz caption hash mismatch")
    if (caption_sha != identity["caption_sha256"]
            and not _ends_with_known_cta(caption)
            and caption_normalization is None):
        raise ValueError("Postiz caption CTA suffix is not a known App Store CTA")
    provider_video_sha = row.get("lifeManagerVideoSha256") or row.get("video_sha256")
    if provider_video_sha is not None and provider_video_sha != identity.get("video_sha256"):
        raise ValueError("Postiz video hash mismatch")
    provider_content = {"caption_sha256": identity["caption_sha256"]}
    local_content: dict[str, Any] = {}
    for key in ("video_sha256", "caption_sha256", "media_sha256", "pack_sha256",
                "media_order_sha256"):
        if key in identity:
            local_content[key] = identity[key]
    if provider_video_sha is not None:
        provider_content["video_sha256"] = provider_video_sha
    native_photo = (
        identity.get("platform") == "tiktok"
        and identity.get("video_sha256") is None
        and isinstance(identity.get("media_sha256"), list)
    )
    native_photo_details: dict[str, Any] = {}
    if native_photo:
        settings = row.get("settings")
        if isinstance(settings, str):
            settings = json.loads(settings)
        if (not isinstance(settings, dict) or not isinstance(expected_pack_title, str)
                or settings.get("title") != expected_pack_title
                or settings.get("content_posting_method") != "DIRECT_POST"
                or not re.fullmatch(r"p_pub_url~v2\.[0-9]+", str(row.get("releaseId", "")))
                or state.get("post_url") is not None):
            raise ValueError("Postiz native carousel publication metadata mismatch")
        remote_media = _native_carousel_image_hashes(row, identity)
        provider_content["media_sha256"] = remote_media
        provider_content["media_order_sha256"] = identity["media_order_sha256"]
        try:
            published_at = datetime.fromisoformat(str(row["publishDate"]).replace("Z", "+00:00"))
            slot_at = datetime.fromisoformat(str(identity["slot"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Postiz native carousel publish time is invalid") from exc
        if (published_at.tzinfo is None or slot_at.tzinfo is None
                or abs((published_at - slot_at).total_seconds()) > 15 * 60):
            raise ValueError("Postiz native carousel publish time does not match slot")
        native_photo_details = {
            "provider_state": state["state"],
            "provider_integration_id": str(integration_id),
            "provider_content_sha256": caption_sha,
            "provider_caption_sha256": caption_sha,
            "provider_title": settings["title"],
            "provider_posting_method": settings["content_posting_method"],
            "provider_release_id": row["releaseId"],
            "published_at": published_at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "_verified_caption_text": caption,
        }
    readback = {
        "provider": "postiz",
        "state": "PUBLISHED",
        "post_id": provider_id,
        "public_url": state.get("post_url"),
        "account_id": identity["account_id"],
        "postiz_profile": postiz_profile,
        "integration_ref": identity["integration_ref"],
        "content": provider_content,
        "local_content": local_content,
        **native_photo_details,
    }
    if caption_normalization is not None and expected_caption_text is not None:
        local_wire_caption_sha256 = hashlib.sha256(
            expected_caption_text[:-1].encode("utf-8"),
        ).hexdigest()
        if local_wire_caption_sha256 != caption_sha:
            raise ValueError("Postiz normalized caption does not match local wire text")
        readback.update({
            "caption_normalization": caption_normalization,
            "provider_caption_sha256": caption_sha,
            "local_wire_caption_sha256": local_wire_caption_sha256,
        })
    return readback


def build_official_proof(
    identity: dict[str, Any], ledger: Path, api_key: str,
    *, identity_dir: Path | None = None,
) -> dict[str, Any]:
    owner_id = str(identity.get("loop_id", ""))
    occurrence_id = str(identity.get("occurrence_id", ""))
    if not _valid_identity(identity, owner_id, occurrence_id):
        raise ValueError("identity_missing_or_invalid")
    native_carousel = _is_native_carousel_identity(identity)
    expected_pack_title = _native_carousel_pack_title(identity, ledger) if native_carousel else None
    local = _local_receipt(identity, ledger)
    if local is None:
        if native_carousel:
            local = _remote_native_carousel_receipt(identity, ledger, api_key)
        if local is None:
            local = _remote_video_receipt(identity, ledger, api_key)
    if local is None:
        raise ValueError("receipt_missing_or_ambiguous")
    receipt, provider_id = local
    expected_caption_text = (
        _stored_caption(identity, ledger) if identity.get("video_sha256") is not None else None
    )
    readback = _provider_readback(
        identity, provider_id, api_key, _final_caption_sha256(identity, receipt),
        expected_caption_text, expected_pack_title,
    )
    if readback.get("account_id") != identity.get("account_id"):
        raise ValueError("provider_readback_not_exact")
    if native_carousel:
        if identity_dir is None:
            raise ValueError("native carousel identity directory unavailable")
        try:
            published_at = datetime.fromisoformat(str(readback["published_at"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("native carousel publish time unavailable") from exc
        provider_caption = readback.pop("_verified_caption_text", None)
        if (published_at.tzinfo is None or not isinstance(provider_caption, str)
                or not _native_carousel_slot_is_unique(
                    identity, identity_dir, ledger, published_at, provider_caption,
                    str(readback.get("provider_title") or ""),
                )):
            raise ValueError("native carousel candidate is shared with another slot identity")
    if receipt.get("remote_effect_locator") is not None:
        readback["remote_effect_locator"] = receipt["remote_effect_locator"]
    if receipt.get("provider_video_sha256") == identity.get("video_sha256"):
        readback["content"]["video_sha256"] = identity["video_sha256"]
    proof = {
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_kind": "postiz_official_readback",
        "provider_receipt_id": provider_id,
        "identity": identity,
        "provider_readback": readback,
    }
    if _READ_ONLY.evaluate_proof(identity, proof)["status"] != "ready":
        raise ValueError("provider proof contract mismatch")
    return proof


def verify_official_postiz_receipt(
    identity: dict[str, Any], ledger: Path, api_key: str,
    *, identity_dir: Path | None = None,
) -> dict[str, Any]:
    """Read the exact Postiz post without changing admission state."""
    owner_id = str(identity.get("loop_id", ""))
    occurrence_id = str(identity.get("occurrence_id", ""))
    if not api_key.strip():
        return _inconclusive(owner_id, occurrence_id, "provider_token_unavailable")
    try:
        return {"status": "ready", **build_official_proof(identity, ledger, api_key, identity_dir=identity_dir)}
    except (OSError, RuntimeError, ValueError, KeyError, ImportError):
        return _inconclusive(owner_id, occurrence_id, "provider_readback_not_exact")


def reconcile_provider_effect(
    identity: dict[str, Any], ledger: Path, owner_id: str, occurrence_id: str,
    *, state: str | None, effect_unknown: int | None, api_key: str,
    apply: bool = False, admission_db: Path | None = None,
    identity_dir: Path | None = None,
) -> dict[str, Any]:
    if owner_id != identity.get("loop_id") or occurrence_id != identity.get("occurrence_id"):
        return _inconclusive(owner_id, occurrence_id, "identity_occurrence_mismatch")
    if state not in {"claimed", "released"} or effect_unknown != 1:
        return _inconclusive(owner_id, occurrence_id, "claimed_or_already_resolved")
    if admission_db is not None:
        try:
            if _authoritative_admission_db() != admission_db.expanduser().resolve():
                return _inconclusive(owner_id, occurrence_id, "admission_db_mismatch")
        except (OSError, RuntimeError, ValueError):
            return _inconclusive(owner_id, occurrence_id, "admission_db_unavailable")
    elif apply:
        return _inconclusive(owner_id, occurrence_id, "admission_db_required")
    if not api_key.strip():
        return _inconclusive(owner_id, occurrence_id, "provider_token_unavailable")
    if not apply:
        try:
            return {"status": "ready", **build_official_proof(identity, ledger, api_key, identity_dir=identity_dir)}
        except (OSError, RuntimeError, ValueError, KeyError, ImportError):
            return _inconclusive(owner_id, occurrence_id, "provider_readback_not_exact")
    latest: dict[str, Any] = {}

    # Preflight the exact proof before entering the mutating resolver. The
    # resolver calls the callback again, so the mutation is preceded by a fresh
    # official readback even if the provider changed between the two reads.
    try:
        latest.update(build_official_proof(identity, ledger, api_key, identity_dir=identity_dir))
    except (OSError, RuntimeError, ValueError, KeyError, ImportError):
        return _inconclusive(owner_id, occurrence_id, "provider_readback_not_exact")
    if _local_receipt(identity, ledger) is None:
        try:
            _persist_recovered_distribution_row(identity, latest, ledger)
        except (OSError, RuntimeError, ValueError, KeyError, ImportError) as exc:
            return _inconclusive(
                owner_id, occurrence_id,
                f"provider_receipt_persist_failed:{type(exc).__name__}:{exc}",
            )

    def official_readback() -> dict[str, Any]:
        proof = build_official_proof(identity, ledger, api_key, identity_dir=identity_dir)
        latest.update(proof)
        return proof

    try:
        changed = resolve_unknown_occurrence(
            owner_id=owner_id, occurrence_id=occurrence_id,
            official_readback=official_readback, expected_state=state,
        )
    except (OSError, RuntimeError, ValueError, sqlite3.Error, ImportError):
        return {**_inconclusive(owner_id, occurrence_id, "resolve_rejected"), "resolution_attempted": True}
    if not changed:
        return {**_inconclusive(owner_id, occurrence_id, "resolve_rejected"), "resolution_attempted": True}
    return {"status": "resolved", **latest}


def _ledger_for_identity(identity: dict[str, Any], data_dir: Path, tenant_id: str) -> Path | None:
    product_id = str(identity.get("product_id", ""))
    if (not ID.fullmatch(tenant_id) or not ID.fullmatch(product_id)
            or tenant_id in {".", ".."} or product_id in {".", ".."}):
        return None
    publication = (
        "video-publication"
        if identity.get("video_sha256") is not None
        else "native-carousel-publication"
    )
    return (
        data_dir / "tenants" / urllib.parse.quote(tenant_id, safe="")
        / "marketing" / publication / urllib.parse.quote(product_id, safe="")
        / "distribution.jsonl"
    )


def _recovered_distribution_row(identity: dict[str, Any], proof: dict[str, Any],
                                ledger: Path) -> dict[str, Any]:
    provider_id = proof.get("provider_receipt_id")
    readback = proof.get("provider_readback")
    if (proof.get("verified") is not True or proof.get("identity") != identity
            or not isinstance(provider_id, str) or not PROVIDER_ID.fullmatch(provider_id)
            or not isinstance(readback, dict)
            or readback.get("provider") != "postiz"
            or readback.get("state") != "PUBLISHED"
            or readback.get("post_id") != provider_id
            or readback.get("account_id") != identity.get("account_id")
            or readback.get("integration_ref") != identity.get("integration_ref")
            or readback.get("local_content", {}).get("caption_sha256") != identity.get("caption_sha256")):
        raise ValueError("recovered Postiz receipt does not match the exact identity")
    if _is_native_carousel_identity(identity):
        content = readback.get("content")
        if (readback.get("public_url") is not None
                or readback.get("local_content", {}).get("pack_sha256") != identity.get("pack_sha256")
                or readback.get("local_content", {}).get("media_sha256") != identity.get("media_sha256")
                or readback.get("local_content", {}).get("media_order_sha256") != identity.get("media_order_sha256")
                or not isinstance(content, dict)
                or content.get("media_sha256") != identity.get("media_sha256")
                or content.get("media_order_sha256") != identity.get("media_order_sha256")
                or readback.get("provider_state") != "PUBLISHED"
                or readback.get("provider_integration_id") != identity["integration_ref"].rsplit("/", 1)[-1]
                or readback.get("provider_caption_sha256") != readback.get("provider_content_sha256")
                or not isinstance(readback.get("provider_title"), str)
                or readback.get("provider_posting_method") != "DIRECT_POST"
                or not re.fullmatch(r"p_pub_url~v2\.[0-9]+", str(readback.get("provider_release_id", "")))):
            raise ValueError("recovered native carousel receipt does not match the exact identity")
        receipt = {
            "schema_version": 1,
            "kind": "marketing_native_carousel_distribution",
            "status": "published",
            "product_id": identity["product_id"],
            "format_id": identity["format_id"],
            "form": identity["form"],
            "locale": identity["locale"],
            "platform": identity["platform"],
            "account_id": identity["account_id"],
            "integration_ref": identity["integration_ref"],
            "creative_id": identity["creative_id"],
            "pack_sha256": identity["pack_sha256"],
            "media_sha256": identity["media_sha256"],
            "media_order_sha256": identity["media_order_sha256"],
            "caption_sha256": identity["caption_sha256"],
            "caption_with_cta_sha256": readback["provider_caption_sha256"],
            "provider_post_id": provider_id,
            "provider_reconciled": True,
            "public_url": None,
            "provider_state": readback["provider_state"],
            "provider_integration_id": readback["provider_integration_id"],
            "provider_content_sha256": readback["provider_content_sha256"],
            "provider_title": readback["provider_title"],
            "provider_posting_method": readback["provider_posting_method"],
            "provider_release_id": readback["provider_release_id"],
            "published_at": readback["published_at"],
        }
        return {"effect_key": identity["effect_key"], "job_id": identity["job_id"], "receipt": receipt}
    if (readback.get("local_content", {}).get("video_sha256") != identity.get("video_sha256")
            or not isinstance(readback.get("public_url"), str)):
        raise ValueError("recovered Postiz receipt does not match the exact identity")
    data_root = ledger.expanduser().resolve().parents[5]
    return {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "platform": identity["platform"],
        "status": "published",
        "product_id": identity["product_id"],
        "creative_id": identity["creative_id"],
        "video_path": str(data_root / "objects" / "sha256" / str(identity["video_sha256"])),
        "video_sha256": identity["video_sha256"],
        "caption_path": str(data_root / "objects" / "sha256" / str(identity["caption_sha256"])),
        "caption_sha256": identity["caption_sha256"],
        "public_url": readback["public_url"],
        "provider_id": provider_id,
        "route": "postiz",
        "provider_cost_usd": None,
        "logged_out_readback": None,
        "migration_date": None,
        "provider_reconciled": True,
        "format_id": identity["format_id"],
        "form": identity["form"],
        "locale": identity["locale"],
        "slot": identity["slot"],
        "account_id": identity["account_id"],
        "integration_ref": identity["integration_ref"],
        "remote_effect_locator": readback.get("remote_effect_locator"),
    }


def _persist_recovered_distribution_row(identity: dict[str, Any], proof: dict[str, Any],
                                        ledger: Path) -> None:
    append_distribution_row(ledger, _recovered_distribution_row(identity, proof, ledger))
    stored = _local_receipt(identity, ledger)
    if stored is None or stored[1] != proof.get("provider_receipt_id"):
        raise ValueError("recovered Postiz receipt was not durable in the distribution ledger")


def reconcile_pending_owner(
    *, owner_id: str, identity_dir: Path, data_dir: Path, tenant_id: str,
    admission_db: Path, api_key: str, apply: bool,
) -> dict[str, Any]:
    """Resolve at most one exact historical Postiz occurrence for this owner."""
    if not ID.fullmatch(owner_id):
        return _inconclusive(owner_id, "", "owner_id_invalid")
    pending_count = _pending_unknown_count(admission_db, owner_id)
    if pending_count is None:
        return _inconclusive(owner_id, "", "admission_pending_read_failed")
    if pending_count == 0:
        return {"status": "clean", "owner_id": owner_id, "reason": "no_pending_effects", "inspected": 0}
    identity_dir = identity_dir.expanduser()
    try:
        candidates = sorted(identity_dir.iterdir(), key=lambda item: item.name)
    except OSError:
        candidates = []
    seen: set[str] = set()
    inspected = 0
    limit_reached = False
    last_inconclusive: dict[str, Any] | None = None
    for sidecar in candidates:
        rows = _safe_jsonl(sidecar)
        if rows is None:
            continue
        for identity in rows:
            occurrence_id = str(identity.get("occurrence_id", ""))
            if occurrence_id in seen or not _valid_identity(identity, owner_id, occurrence_id):
                continue
            seen.add(occurrence_id)
            state, effect_unknown = _admission_state(admission_db, owner_id, occurrence_id)
            if state not in {"claimed", "released"} or effect_unknown != 1:
                continue
            if inspected >= 256:
                limit_reached = True
                break
            inspected += 1
            ledger = _ledger_for_identity(identity, data_dir, tenant_id)
            if ledger is None:
                continue
            if (_local_receipt(identity, ledger) is None
                    and identity.get("product_id") not in EBOOK_TOKEN_PREFIXES
                    and not _is_native_carousel_identity(identity)):
                continue
            result = reconcile_provider_effect(
                identity, ledger, owner_id, occurrence_id,
                state=state, effect_unknown=effect_unknown, api_key=api_key,
                apply=apply, admission_db=admission_db,
                identity_dir=identity_dir,
            )
            result = {**result, "inspected": inspected}
            if result.get("resolution_attempted") is True:
                return result
            if result.get("status") != "inconclusive":
                if apply and result.get("status") == "resolved":
                    remaining = _pending_unknown_count(admission_db, owner_id)
                    if remaining is None:
                        return _inconclusive(owner_id, occurrence_id, "admission_pending_read_failed_after_resolve")
                    if remaining > 0:
                        return {
                            "status": "pending_after_resolve",
                            "owner_id": owner_id,
                            "occurrence_id": occurrence_id,
                            "provider_receipt_id": result.get("provider_receipt_id"),
                            "pending_count": remaining,
                            "inspected": inspected,
                        }
                return result
            last_inconclusive = result
        if limit_reached:
            break
    if last_inconclusive is not None:
        return last_inconclusive
    return {
        "status": "no_match",
        "owner_id": owner_id,
        "reason": "exact_pending_receipt_unavailable",
        "inspected": inspected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--owner-id")
    parser.add_argument("--occurrence-id")
    parser.add_argument("--auto-owner")
    parser.add_argument(
        "--identity-dir", type=Path,
        default=Path.home() / ".local/state/life-manager/effect-identities",
    )
    parser.add_argument(
        "--data-dir", type=Path,
        default=Path(os.environ.get("LM_DATA_DIR", Path.home() / ".local/state/life-manager")),
    )
    parser.add_argument("--tenant-id", default=os.environ.get("LM_RUNTIME_TENANT_ID", ""))
    parser.add_argument(
        "--admission-db", type=Path,
        default=Path.home() / ".local/state/life-manager/host-admission/resources/admission-v2.sqlite3",
    )
    parser.add_argument("--resolve", action="store_true", help="clear only after the fresh official proof")
    parser.add_argument(
        "--verify-only", action="store_true",
        help="read the exact Postiz post without resolving admission state",
    )
    args = parser.parse_args(argv)
    if args.verify_only:
        if args.resolve or args.auto_owner:
            parser.error("--verify-only requires exact identity arguments and cannot resolve")
        if not all((args.identity, args.ledger, args.owner_id, args.occurrence_id)):
            parser.error("--verify-only requires --identity, --ledger, --owner-id and --occurrence-id")
        identity = read_identity(args.identity, args.owner_id, args.occurrence_id)
        if identity is None:
            result = _inconclusive(args.owner_id, args.occurrence_id, "identity_missing_or_invalid")
        else:
            result = verify_official_postiz_receipt(
                identity, args.ledger,
                os.environ.get("POSTIZ_API_KEY") or os.environ.get("LM_POSTIZ_API_KEY", ""),
                identity_dir=args.identity.expanduser().parent,
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "ready" else 1
    if args.auto_owner:
        if any((args.identity, args.ledger, args.owner_id, args.occurrence_id)):
            parser.error("--auto-owner cannot be combined with exact reconciliation arguments")
        result = reconcile_pending_owner(
            owner_id=args.auto_owner,
            identity_dir=args.identity_dir,
            data_dir=args.data_dir,
            tenant_id=args.tenant_id,
            admission_db=args.admission_db,
            api_key=os.environ.get("POSTIZ_API_KEY") or os.environ.get("LM_POSTIZ_API_KEY", ""),
            apply=args.resolve,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if result.get("status") in {"clean", "resolved"}:
            return 0
        if not args.resolve and result.get("status") == "ready":
            return 0
        return 1
    if not all((args.identity, args.ledger, args.owner_id, args.occurrence_id)):
        parser.error("exact reconciliation requires --identity, --ledger, --owner-id and --occurrence-id")
    identity = read_identity(args.identity, args.owner_id, args.occurrence_id)
    if identity is None:
        result = _inconclusive(args.owner_id, args.occurrence_id, "identity_missing_or_invalid")
    else:
        state, effect_unknown = _admission_state(args.admission_db, args.owner_id, args.occurrence_id)
        result = reconcile_provider_effect(
            identity, args.ledger, args.owner_id, args.occurrence_id,
            state=state, effect_unknown=effect_unknown,
            api_key=os.environ.get("POSTIZ_API_KEY") or os.environ.get("LM_POSTIZ_API_KEY", ""), apply=args.resolve,
            admission_db=args.admission_db,
            identity_dir=args.identity.expanduser().parent,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"ready", "resolved"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
