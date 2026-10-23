"""Offline AI Monk Factory plan construction."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

from render_eval.heygen_candidate import IDENTIFIER, build_request, require


def _fields(value: object, fields: set[str], label: str) -> dict:
    require(isinstance(value, dict) and value.keys() == fields, f"Factory {label} fields invalid")
    return value


def _url(value: object) -> None:
    require(isinstance(value, str) and bool(value) and not any(
        char.isspace() or unicodedata.category(char).startswith("C") or char == "\\" for char in value
    ), "Factory product URL invalid")
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == "https" and bool(parsed.hostname)
                 and parsed.username is None and parsed.password is None)
        parsed.port
    except ValueError:
        raise ValueError("Factory product URL invalid") from None
    require(valid, "Factory product URL invalid")


def build_plan(config: dict, script: str) -> dict:
    _fields(config, {"schema_version", "project_id", "language", "heygen", "postiz", "product", "state_root"}, "config")
    require(config["schema_version"] == "ai-monk-factory.config.v1", "Factory schema version invalid")
    project_id = config["project_id"]
    require(isinstance(project_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", project_id) is not None,
            "Factory project ID invalid")
    language = config["language"]
    require(isinstance(language, str) and language in {"en", "ja"}, "Factory language invalid")
    heygen = _fields(config["heygen"], {"avatar_id", "voice_id"}, "HeyGen")
    for name in ("avatar_id", "voice_id"):
        require(isinstance(heygen[name], str) and IDENTIFIER.fullmatch(heygen[name]) is not None,
                "Factory HeyGen ID invalid")
    postiz = _fields(config["postiz"], {"platform", "integration_id"}, "Postiz")
    require(isinstance(postiz["platform"], str) and postiz["platform"] in {"tiktok", "instagram"},
            "Factory platform invalid")
    integration = postiz["integration_id"]
    require(isinstance(integration, str) and 0 < len(integration) <= 128 and not any(
        char.isspace() or unicodedata.category(char).startswith("C") for char in integration
    ), "Factory integration ID invalid")
    product = _fields(config["product"], {"name", "url"}, "product")
    require(isinstance(product["name"], str) and bool(product["name"].strip()) and len(product["name"]) <= 200,
            "Factory product name invalid")
    _url(product["url"])
    state_root = config["state_root"]
    require(isinstance(state_root, str) and bool(state_root) and "\x00" not in state_root,
            "Factory state root invalid")
    try:
        expanded = Path(state_root).expanduser()
    except (RuntimeError, ValueError):
        raise ValueError("Factory state root invalid") from None
    require(expanded.is_absolute(), "Factory state root must be absolute")
    request = build_request(script, {"status": "ready", **heygen}, language=language)
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": "ai-monk-factory.plan.v1",
        "status": "planned",
        "project_id": project_id,
        "language": language,
        "state_root": os.path.normpath(str(expanded)),
        "render_request": request,
        "request_sha256": hashlib.sha256(encoded).hexdigest(),
        "publication_plan": {"provider": "postiz", **postiz, "product": dict(product)},
        "provider_calls": 0,
        "external_effects": [],
    }
