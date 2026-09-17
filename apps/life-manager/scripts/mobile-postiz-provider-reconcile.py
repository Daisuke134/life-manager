#!/usr/bin/env python3
"""Perform one exact Postiz readback before releasing a publish fence."""

from __future__ import annotations

import argparse
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


def _receipt_matches(identity: dict[str, Any], row: dict[str, Any]) -> tuple[bool, str | None]:
    receipt, outer_effect, outer_job = _receipt_from_row(row)
    if outer_effect is not None and outer_effect != identity.get("effect_key"):
        return False, None
    if outer_job is not None and outer_job != identity.get("job_id"):
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
    rows = _safe_jsonl(ledger)
    if rows is None:
        return None
    candidates: list[tuple[dict[str, Any], str]] = []
    for row in rows:
        matches, provider_id = _receipt_matches(identity, row)
        if matches and provider_id is not None:
            receipt, _, _ = _receipt_from_row(row)
            candidates.append((receipt, provider_id))
    unique = {provider_id for _, provider_id in candidates}
    if len(unique) != 1:
        return None
    return candidates[-1]


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


def _caption(row: dict[str, Any]) -> str:
    value = row.get("content")
    if not isinstance(value, str):
        values = row.get("value")
        if isinstance(values, list) and values and isinstance(values[0], dict):
            value = values[0].get("content")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Postiz content is missing")
    return value


def _provider_readback(identity: dict[str, Any], provider_id: str, api_key: str) -> dict[str, Any]:
    row = _postiz_post(provider_id, api_key)
    postiz_path = ROOT / "skills/video/lm-distribution/postiz_video.py"
    spec = importlib.util.spec_from_file_location("life_manager_postiz_video", postiz_path)
    if spec is None or spec.loader is None:
        raise ValueError("Postiz adapter unavailable")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    state = adapter.find_post([row], provider_id, identity["platform"])
    if state.get("state") != "PUBLISHED":
        raise ValueError("Postiz post is not published")
    nested = row.get("integration")
    integration_id = nested.get("id") if isinstance(nested, dict) else row.get("integrationId")
    expected_integration_id = identity["integration_ref"].rsplit("/", 1)[-1]
    if integration_id != expected_integration_id:
        raise ValueError("Postiz post integration mismatch")
    account_id = _integration(str(integration_id), identity["platform"], api_key)
    caption_sha = hashlib.sha256(_caption(row).encode("utf-8")).hexdigest()
    if caption_sha != identity["caption_sha256"]:
        raise ValueError("Postiz caption hash mismatch")
    provider_video_sha = row.get("lifeManagerVideoSha256") or row.get("video_sha256")
    if provider_video_sha is not None and provider_video_sha != identity.get("video_sha256"):
        raise ValueError("Postiz video hash mismatch")
    content = {"caption_sha256": identity["caption_sha256"]}
    for key in ("video_sha256", "media_sha256", "pack_sha256", "media_order_sha256"):
        if key in identity:
            content[key] = identity[key]
    return {
        "provider": "postiz",
        "state": "PUBLISHED",
        "post_id": provider_id,
        "public_url": state.get("post_url"),
        "account_id": account_id,
        "integration_ref": identity["integration_ref"],
        "content": content,
    }


def build_official_proof(identity: dict[str, Any], ledger: Path, api_key: str) -> dict[str, Any]:
    owner_id = str(identity.get("loop_id", ""))
    occurrence_id = str(identity.get("occurrence_id", ""))
    if not _valid_identity(identity, owner_id, occurrence_id):
        raise ValueError("identity_missing_or_invalid")
    local = _local_receipt(identity, ledger)
    if local is None:
        raise ValueError("receipt_missing_or_ambiguous")
    _, provider_id = local
    readback = _provider_readback(identity, provider_id, api_key)
    if readback.get("account_id") != identity.get("account_id"):
        raise ValueError("provider_readback_not_exact")
    return {
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_kind": "postiz_official_readback",
        "provider_receipt_id": provider_id,
        "identity": identity,
        "provider_readback": readback,
    }


def reconcile_provider_effect(
    identity: dict[str, Any], ledger: Path, owner_id: str, occurrence_id: str,
    *, state: str | None, effect_unknown: int | None, api_key: str,
    apply: bool = False,
) -> dict[str, Any]:
    if owner_id != identity.get("loop_id") or occurrence_id != identity.get("occurrence_id"):
        return _inconclusive(owner_id, occurrence_id, "identity_occurrence_mismatch")
    if state != "released" or effect_unknown != 1:
        return _inconclusive(owner_id, occurrence_id, "claimed_or_already_resolved")
    if not api_key.strip():
        return _inconclusive(owner_id, occurrence_id, "provider_token_unavailable")
    if not apply:
        try:
            return {"status": "ready", **build_official_proof(identity, ledger, api_key)}
        except (OSError, RuntimeError, ValueError, KeyError, ImportError):
            return _inconclusive(owner_id, occurrence_id, "provider_readback_not_exact")
    latest: dict[str, Any] = {}

    # Preflight the exact proof before entering the mutating resolver. The
    # resolver calls the callback again, so the mutation is preceded by a fresh
    # official readback even if the provider changed between the two reads.
    try:
        latest.update(build_official_proof(identity, ledger, api_key))
    except (OSError, RuntimeError, ValueError, KeyError, ImportError):
        return _inconclusive(owner_id, occurrence_id, "provider_readback_not_exact")

    def official_readback() -> dict[str, Any]:
        proof = build_official_proof(identity, ledger, api_key)
        latest.update(proof)
        return proof

    try:
        changed = resolve_unknown_occurrence(
            owner_id=owner_id, occurrence_id=occurrence_id,
            official_readback=official_readback,
        )
    except (OSError, RuntimeError, ValueError, sqlite3.Error, ImportError):
        return _inconclusive(owner_id, occurrence_id, "resolve_rejected")
    if not changed:
        return _inconclusive(owner_id, occurrence_id, "resolve_rejected")
    return {"status": "resolved", **latest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument(
        "--admission-db", type=Path,
        default=Path.home() / ".local/state/life-manager/host-admission/resources/admission-v2.sqlite3",
    )
    parser.add_argument("--resolve", action="store_true", help="clear only after the fresh official proof")
    args = parser.parse_args(argv)
    identity = read_identity(args.identity, args.owner_id, args.occurrence_id)
    if identity is None:
        result = _inconclusive(args.owner_id, args.occurrence_id, "identity_missing_or_invalid")
    else:
        state, effect_unknown = _admission_state(args.admission_db, args.owner_id, args.occurrence_id)
        result = reconcile_provider_effect(
            identity, args.ledger, args.owner_id, args.occurrence_id,
            state=state, effect_unknown=effect_unknown,
            api_key=os.environ.get("POSTIZ_API_KEY", ""), apply=args.resolve,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"ready", "resolved"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
