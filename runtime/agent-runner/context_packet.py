#!/usr/bin/env python3
"""Deterministic bounded context packets shared by repository loop adapters."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any


class ContextPacketError(ValueError):
    pass


_CAPSULE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CAPSULE_REF = re.compile(r"^[a-z][a-z0-9+.-]*://[A-Za-z0-9._:/-]{1,512}$")
_CAPSULE_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_CAPSULE_SECRET = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~+/-]+|(?:token|secret|password|credential|api.?key|auth\.json)\s*[=:]|"
    r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}|/Users/)"
)
_CAPSULE_FRESHNESS = frozenset(("fresh", "stale", "unknown"))


def _capsule_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not _CAPSULE_ID.fullmatch(value):
        raise ContextPacketError(f"invalid capsule {name}")
    return value


def _capsule_ref(value: object, name: str) -> str:
    if not isinstance(value, str) or not _CAPSULE_REF.fullmatch(value):
        raise ContextPacketError(f"invalid capsule {name}")
    return value


def _capsule_sha(value: object, name: str) -> str:
    if not isinstance(value, str) or not _CAPSULE_SHA256.fullmatch(value):
        raise ContextPacketError(f"invalid capsule {name}")
    return value


def _capsule_timestamp(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContextPacketError(f"invalid capsule {name}")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContextPacketError(f"invalid capsule {name}") from error
    return value


def _capsule_int(value: object, name: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContextPacketError(f"invalid capsule {name}")
    if maximum is not None and value > maximum:
        raise ContextPacketError(f"invalid capsule {name}")
    return value


def _capsule_text(value: object, name: str, *, maximum_bytes: int, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value) or "\x00" in value:
        raise ContextPacketError(f"invalid capsule {name}")
    return _truncate_utf8(value, maximum_bytes)


def _capsule_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def build_context_capsule(
    *, tenant_id: str, owner_id: str, product_loop_id: str, job_id: str, wake_id: str,
    goal: dict[str, Any], sources: list[dict[str, Any]],
    decisions: list[dict[str, Any]] | None = None,
    open_questions: list[str] | None = None,
    max_bytes: int = 8192, max_tokens: int = 2048,
    max_age_seconds: int = 300, compiled_at: str | None = None,
) -> dict[str, Any]:
    """Compile a deterministic, provenance-bound capsule from already-authoritative facts."""
    for value, name in (
        (tenant_id, "tenant_id"), (owner_id, "owner_id"),
        (product_loop_id, "product_loop_id"), (job_id, "job_id"), (wake_id, "wake_id"),
    ):
        _capsule_id(value, name)
    max_bytes = _capsule_int(max_bytes, "budget.max_bytes", minimum=128, maximum=65536)
    max_tokens = _capsule_int(max_tokens, "budget.max_tokens", minimum=1, maximum=128000)
    max_age_seconds = _capsule_int(max_age_seconds, "freshness.max_age_seconds", maximum=604800)
    compiled_at = _capsule_timestamp(
        compiled_at or datetime.now(timezone.utc).isoformat(), "freshness.compiled_at"
    )
    if not isinstance(goal, dict) or set(goal) != {"text", "success_condition", "revision"}:
        raise ContextPacketError("invalid capsule goal")
    normalized_goal = {
        "text": _capsule_text(goal["text"], "goal.text", maximum_bytes=4096),
        "success_condition": _capsule_text(
            goal["success_condition"], "goal.success_condition", maximum_bytes=1024
        ),
        "revision": _capsule_int(goal["revision"], "goal.revision", minimum=1),
    }
    if not isinstance(sources, list) or not 1 <= len(sources) <= 32:
        raise ContextPacketError("invalid capsule sources")
    normalized_sources: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict) or set(source) != {
            "ref", "observed_at", "content_sha256", "freshness", "excerpt",
        }:
            raise ContextPacketError("invalid capsule source")
        freshness = source["freshness"]
        if freshness not in _CAPSULE_FRESHNESS:
            raise ContextPacketError("invalid capsule source freshness")
        normalized_sources.append({
            "ref": _capsule_ref(source["ref"], "source.ref"),
            "observed_at": _capsule_timestamp(source["observed_at"], "source.observed_at"),
            "content_sha256": _capsule_sha(source["content_sha256"], "source.content_sha256"),
            "freshness": freshness,
            "excerpt": _capsule_text(source["excerpt"], "source.excerpt", maximum_bytes=1024, required=False),
        })
    source_refs = {source["ref"] for source in normalized_sources}
    decisions = [] if decisions is None else decisions
    if not isinstance(decisions, list) or len(decisions) > 32:
        raise ContextPacketError("invalid capsule decisions")
    normalized_decisions: list[dict[str, Any]] = []
    for decision in decisions:
        if not isinstance(decision, dict) or set(decision) != {"id", "summary", "source_refs"}:
            raise ContextPacketError("invalid capsule decision")
        refs = decision["source_refs"]
        if not isinstance(refs, list) or not 1 <= len(refs) <= 32:
            raise ContextPacketError("invalid capsule decision source_refs")
        normalized_refs = [_capsule_ref(ref, "decision.source_ref") for ref in refs]
        if any(ref not in source_refs for ref in normalized_refs):
            raise ContextPacketError("capsule decision source is not present")
        normalized_decisions.append({
            "id": _capsule_id(decision["id"], "decision.id"),
            "summary": _capsule_text(decision["summary"], "decision.summary", maximum_bytes=1024),
            "source_refs": normalized_refs,
        })
    open_questions = [] if open_questions is None else open_questions
    if not isinstance(open_questions, list) or len(open_questions) > 16:
        raise ContextPacketError("invalid capsule open_questions")
    normalized_questions = [
        _capsule_text(value, "open_question", maximum_bytes=1024)
        for value in open_questions
    ]
    base: dict[str, Any] = {
        "schema_version": 1,
        "tenant_id": tenant_id,
        "owner_id": owner_id,
        "product_loop_id": product_loop_id,
        "job_id": job_id,
        "wake_id": wake_id,
        "goal": normalized_goal,
        "sources": normalized_sources,
        "decisions": normalized_decisions,
        "open_questions": normalized_questions,
        "budget": {"max_bytes": max_bytes, "max_tokens": max_tokens},
        "freshness": {
            "compiled_at": compiled_at,
            "max_age_seconds": max_age_seconds,
            "stale_source_count": sum(source["freshness"] != "fresh" for source in normalized_sources),
        },
        "privacy": {"redaction": "secret_free", "payload_mode": "references_only"},
    }
    canonical_base = _capsule_json(base)
    if _CAPSULE_SECRET.search(canonical_base):
        raise ContextPacketError("secret-like context value forbidden")
    content_sha256 = hashlib.sha256(canonical_base.encode("utf-8")).hexdigest()
    capsule_id = hashlib.sha256(
        f"{tenant_id}\n{owner_id}\n{wake_id}\n{content_sha256}".encode("utf-8")
    ).hexdigest()[:32]
    capsule = {**base, "capsule_id": capsule_id, "content_sha256": content_sha256}
    encoded = _capsule_json(capsule).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ContextPacketError(f"context capsule exceeds {max_bytes} bytes")
    return capsule


def _truncate_utf8(value: str, limit: int) -> str:
    raw = value.encode("utf-8")
    if len(raw) <= limit:
        return value
    suffix = "…"
    room = max(0, limit - len(suffix.encode("utf-8")))
    return raw[:room].decode("utf-8", errors="ignore") + suffix


def _bounded(value: Any, *, depth: int, string_bytes: int, list_items: int, map_items: int) -> Any:
    if depth < 0:
        raise ContextPacketError("context packet depth exceeded")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate_utf8(value, string_bytes)
    if isinstance(value, list):
        return [
            _bounded(
                item,
                depth=depth - 1,
                string_bytes=string_bytes,
                list_items=list_items,
                map_items=map_items,
            )
            for item in value[:list_items]
        ]
    if isinstance(value, dict):
        return {
            str(key): _bounded(
                child,
                depth=depth - 1,
                string_bytes=string_bytes,
                list_items=list_items,
                map_items=map_items,
            )
            for key, child in list(value.items())[:map_items]
        }
    raise ContextPacketError(f"unsupported context value: {type(value).__name__}")


def _encode(packet: dict[str, Any]) -> bytes:
    return json.dumps(
        packet,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def build_packet(
    *,
    kind: str,
    fields: dict[str, Any],
    max_bytes: int = 8192,
    max_fields: int = 24,
    string_bytes: int = 512,
    list_items: int = 8,
    map_items: int = 24,
    max_depth: int = 4,
) -> dict[str, Any]:
    if not kind or len(fields) > max_fields:
        raise ContextPacketError("context packet kind/field limit invalid")
    bounded = _bounded(
        fields,
        depth=max_depth,
        string_bytes=string_bytes,
        list_items=list_items,
        map_items=map_items,
    )
    packet = {
        "version": 1,
        "kind": kind,
        "fields": bounded,
        "limits": {
            "max_bytes": max_bytes,
            "max_fields": max_fields,
            "string_bytes": string_bytes,
            "list_items": list_items,
            "map_items": map_items,
            "max_depth": max_depth,
        },
        "metrics": {
            "field_count": len(bounded),
            "byte_count": 0,
            # A tokenizer can emit at most one token per input byte. This is a
            # deliberately conservative provider-independent ceiling.
            "conservative_token_ceiling": 0,
        },
    }
    for _ in range(8):
        byte_count = len(_encode(packet))
        if (
            packet["metrics"]["byte_count"] == byte_count
            and packet["metrics"]["conservative_token_ceiling"] == byte_count
        ):
            break
        packet["metrics"]["byte_count"] = byte_count
        packet["metrics"]["conservative_token_ceiling"] = byte_count
    final_size = len(_encode(packet))
    if final_size != packet["metrics"]["byte_count"]:
        raise ContextPacketError("context packet metrics did not stabilize")
    if final_size > max_bytes:
        raise ContextPacketError(f"context packet exceeds {max_bytes} bytes")
    return packet


def serialize_packet(packet: dict[str, Any]) -> bytes:
    encoded = _encode(packet)
    metrics = packet.get("metrics")
    if not isinstance(metrics, dict) or metrics.get("byte_count") != len(encoded):
        raise ContextPacketError("context packet byte_count mismatch")
    return encoded
