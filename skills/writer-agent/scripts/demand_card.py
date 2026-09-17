#!/usr/bin/env python3
"""Validate the paid-demand evidence contract used by topic selection."""

from __future__ import annotations

import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from claim_store import SHA256_RE, _text
from x_article_identity import is_link_only_x_article_shell_title


DEMAND_SOURCE_FAMILIES = (
    "paid_market",
    "reader_demand",
    "publisher_opportunity",
    "owned_funnel",
)
MAX_OBSERVATIONS_PER_FAMILY = 2
MIN_FULL_SOURCE_BODIES = 2
FULL_BODY_CAPTURE_METHODS = frozenset({"http_full_body", "rendered_cdp_dom"})


class DemandCardError(ValueError):
    """A selected topic cannot be trusted as a paid-demand card."""


_BINDING_FIELDS = (
    "buyer",
    "problem",
    "transformation",
    "deliverable",
    "price_hypothesis",
    "distribution_path",
)


def _body_digest(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def _observation_timestamp(observation: Mapping[str, Any]) -> float:
    for field in ("captured_at", "observed_at", "published_at", "created_at"):
        value = observation.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return 0.0


def _observation_receipt(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "observation_id": observation.get("observation_id"),
        "source_family": observation.get("source_family"),
        "source_url": observation.get("source_url"),
        "body_sha256": _body_digest(observation.get("full_body")),
        "source_sha256": observation.get("source_sha256"),
        "capture_method": observation.get("capture_method"),
        "captured_at": observation.get("captured_at"),
        "observed_at": observation.get("observed_at"),
        "published_at": observation.get("published_at"),
    }


def select_demand_observations(
    observations: list[Mapping[str, Any]],
    *,
    max_per_family: int = MAX_OBSERVATIONS_PER_FAMILY,
) -> dict[str, Any]:
    """Select a bounded, deterministic evidence view from accumulated receipts.

    Selection is read-only. Full-body receipts outrank excerpts, then newer
    observations outrank older ones; an independent URL/body hash is preferred
    before filling the family cap with duplicates. Every considered row is
    retained in the receipt so a dropped stronger signal is never silent.
    """

    if not isinstance(observations, list) or not observations:
        raise DemandCardError("demand card observations must be a non-empty list")
    if max_per_family < 1:
        raise ValueError("max_per_family must be positive")

    grouped: dict[str, list[Mapping[str, Any]]] = {
        family: [] for family in DEMAND_SOURCE_FAMILIES
    }
    for index, observation in enumerate(observations):
        if not isinstance(observation, Mapping):
            raise DemandCardError(f"observation[{index}] must be an object")
        family = observation.get("source_family")
        if family not in grouped:
            raise DemandCardError(f"observation[{index}] has unsupported source family")
        grouped[family].append(observation)

    missing = [family for family, rows in grouped.items() if not rows]
    if missing:
        raise DemandCardError(
            "demand card requires observations from: " + ",".join(missing)
        )

    def rank(row: Mapping[str, Any]) -> tuple[int, float, str, str, str]:
        body_hash = _body_digest(row.get("full_body")) or ""
        capture_method = row.get("capture_method")
        return (
            (
                0
                if body_hash and capture_method in FULL_BODY_CAPTURE_METHODS
                else 1
                if body_hash
                else 2
            ),
            -_observation_timestamp(row),
            str(row.get("source_url") or ""),
            body_hash,
            str(row.get("observation_id") or ""),
        )

    selected: list[Mapping[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for family in DEMAND_SOURCE_FAMILIES:
        ordered = sorted(grouped[family], key=rank)
        family_selected: list[Mapping[str, Any]] = []
        used_urls: set[str] = set()
        used_body_hashes: set[str] = set()
        # First pass keeps the strongest independent receipts.
        for independent_pass in (True, False):
            for row in ordered:
                if len(family_selected) >= max_per_family:
                    break
                if row in family_selected:
                    continue
                url = str(row.get("source_url") or "")
                body_hash = _body_digest(row.get("full_body")) or ""
                independent = url not in used_urls and (
                    not body_hash or body_hash not in used_body_hashes
                )
                if independent != independent_pass:
                    continue
                family_selected.append(row)
                used_urls.add(url)
                if body_hash:
                    used_body_hashes.add(body_hash)
        selected.extend(family_selected)
        selected_ids = {str(row.get("observation_id")) for row in family_selected}
        for row in ordered:
            if str(row.get("observation_id")) not in selected_ids:
                dropped.append(
                    {
                        **_observation_receipt(row),
                        "reason": (
                            f"family cap {max_per_family}; retained stronger/newer "
                            "or independent receipt"
                        ),
                    }
                )

    selected_receipts = [_observation_receipt(row) for row in selected]
    full_body_receipts = [
        row
        for row in selected
        if _body_digest(row.get("full_body"))
        and row.get("capture_method") in FULL_BODY_CAPTURE_METHODS
    ]
    independent_body_keys = {
        (str(row.get("source_url")), _body_digest(row.get("full_body")))
        for row in full_body_receipts
    }
    if len(independent_body_keys) < MIN_FULL_SOURCE_BODIES:
        raise DemandCardError(
            "demand card requires at least two independent full source bodies"
        )
    body_source_keys = {
        (
            str(row.get("source_family")),
            urlsplit(str(row.get("source_url") or "")).hostname,
        )
        for row in full_body_receipts
    }
    if len(body_source_keys) < MIN_FULL_SOURCE_BODIES:
        raise DemandCardError(
            "full source bodies must span at least two independent source families or hosts"
        )
    return {
        "observations": list(selected),
        "receipt": {
            "version": 1,
            "max_per_family": max_per_family,
            "considered": [_observation_receipt(row) for row in observations],
            "selected": selected_receipts,
            "dropped": dropped,
            "rationale": (
                "full-body receipts outrank excerpts; recency then independent "
                "source URL/body hash determine each family selection"
            ),
        },
    }


def _source_url(value: Any) -> str:
    try:
        url = _text(value, "source_url")
    except ValueError as error:
        raise DemandCardError(str(error)) from error
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise DemandCardError("source_url must be public HTTPS")
    if parsed.username or parsed.password:
        raise DemandCardError("source_url authority is invalid")
    return url


def _validated_x_rendered_identity(
    *,
    url: str,
    body: str,
    article_identity: Any,
    target_id: Any,
    rendered_identity: Any,
) -> dict[str, Any]:
    """Re-prove X Article identity from raw facts before card normalization."""

    path_parts = [part for part in urlsplit(url).path.split("/") if part]
    expected_target_id = (
        path_parts[-1]
        if len(path_parts) >= 3
        and path_parts[-2] in {"status", "article"}
        and path_parts[-1].isdigit()
        else None
    )
    if expected_target_id is None or article_identity is not True:
        raise DemandCardError("X Article rendered identity is not proven")
    if str(target_id) != expected_target_id or not isinstance(rendered_identity, Mapping):
        raise DemandCardError("X Article target identity facts are invalid")
    shell_title = rendered_identity.get("shell_title")
    rendered_url = rendered_identity.get("rendered_url")
    if (
        rendered_identity.get("exact_status_url") is not True
        or not isinstance(rendered_url, str)
        or rendered_url.rstrip("/") != url.rstrip("/")
        or rendered_identity.get("target_id_match") is not True
        or str(rendered_identity.get("status_target_id")) != expected_target_id
        or rendered_identity.get("shell_link_only") is not True
        or not is_link_only_x_article_shell_title(shell_title)
        or rendered_identity.get("article_count") != 1
        or rendered_identity.get("article_container_count") != 1
        or rendered_identity.get("container_selector") != "article"
        or rendered_identity.get("longform_chars") != len(body)
        or not isinstance(rendered_identity.get("block_count"), int)
        or rendered_identity.get("block_count", 0) < 3
    ):
        raise DemandCardError("X Article compound rendered identity facts are invalid")
    return dict(rendered_identity)


def _required_binding(bindings: Mapping[str, Any], field: str) -> str:
    try:
        return _text(bindings.get(field), field)
    except ValueError as error:
        raise DemandCardError(f"demand card {field} is required") from error


def _validate_bindings(
    bindings: Mapping[str, Any],
    *,
    observation_ids: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(bindings, Mapping):
        raise DemandCardError("demand card bindings must be an object")
    normalized: dict[str, Any] = {
        field: _required_binding(bindings, field)
        for field in ("buyer", "problem", "transformation", "deliverable")
    }
    price = bindings.get("price_hypothesis")
    if not isinstance(price, Mapping):
        raise DemandCardError("demand card price_hypothesis is required")
    amount = price.get("amount")
    if (
        not isinstance(amount, (int, float))
        or isinstance(amount, bool)
        or amount <= 0
    ):
        raise DemandCardError("price_hypothesis.amount must be positive")
    currency = price.get("currency")
    if not isinstance(currency, str) or currency.upper() != currency or len(currency) != 3:
        raise DemandCardError("price_hypothesis.currency must be an uppercase code")
    basis = price.get("basis")
    try:
        basis = _text(basis, "price_hypothesis.basis")
    except ValueError as error:
        raise DemandCardError("price_hypothesis.basis is required") from error
    normalized["price_hypothesis"] = {
        "amount": amount,
        "currency": currency,
        "basis": basis,
    }

    distribution = bindings.get("distribution_path")
    if not isinstance(distribution, list) or not distribution:
        raise DemandCardError("distribution_path must contain at least one channel")
    normalized_distribution: list[dict[str, str]] = []
    for index, item in enumerate(distribution):
        if not isinstance(item, Mapping):
            raise DemandCardError(f"distribution_path[{index}] must be an object")
        try:
            channel = _text(item.get("channel"), f"distribution_path[{index}].channel")
            role = _text(item.get("role"), f"distribution_path[{index}].role")
        except ValueError as error:
            raise DemandCardError(str(error)) from error
        normalized_distribution.append({"channel": channel, "role": role})
    normalized["distribution_path"] = normalized_distribution
    supporting = bindings.get("binding_observation_ids")
    if supporting is not None:
        if not isinstance(supporting, Mapping):
            raise DemandCardError("binding_observation_ids must be an object")
        normalized_supporting: dict[str, list[str]] = {}
        for field in _BINDING_FIELDS:
            values = supporting.get(field)
            if not isinstance(values, list) or not values:
                raise DemandCardError(
                    f"binding_observation_ids.{field} must be a non-empty list"
                )
            clean_values: list[str] = []
            for value in values:
                if not isinstance(value, str) or not value.strip():
                    raise DemandCardError(
                        f"binding_observation_ids.{field} must contain strings"
                    )
                value = value.strip()
                if value not in clean_values:
                    clean_values.append(value)
            if observation_ids is not None and not set(clean_values) <= observation_ids:
                raise DemandCardError(
                    f"binding_observation_ids.{field} references an unsupported "
                    "supporting observation"
                )
            normalized_supporting[field] = clean_values
        normalized["binding_observation_ids"] = normalized_supporting
    return normalized


def build_demand_card(
    observations: list[Mapping[str, Any]],
    bindings: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one paid-demand selection from existing evidence receipts.

    This is a pure adapter: it does not open or mutate any claim, opportunity,
    publisher, or funnel store. Callers supply their durable observations and
    receive one queue-card payload only after every hard evidence check passes.
    """
    if not isinstance(observations, list) or not observations:
        raise DemandCardError("demand card observations must be a non-empty list")
    observation_ids: set[str] = set()
    for index, observation in enumerate(observations):
        if not isinstance(observation, Mapping):
            continue
        try:
            observation_id = _text(observation.get("observation_id"), "observation_id")
        except ValueError:
            continue
        if observation_id in observation_ids:
            raise DemandCardError("demand card observation IDs must be unique")
        observation_ids.add(observation_id)
    normalized_bindings = _validate_bindings(
        bindings,
        observation_ids=observation_ids,
    )
    counts = {family: 0 for family in DEMAND_SOURCE_FAMILIES}
    source_bodies: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    normalized_observations: list[dict[str, Any]] = []
    for index, observation in enumerate(observations):
        if not isinstance(observation, Mapping):
            raise DemandCardError(f"observation[{index}] must be an object")
        family = observation.get("source_family")
        if family not in DEMAND_SOURCE_FAMILIES:
            raise DemandCardError(f"observation[{index}] has unsupported source family")
        counts[family] += 1
        if counts[family] > MAX_OBSERVATIONS_PER_FAMILY:
            raise DemandCardError(
                f"source family cap exceeded: {family} > {MAX_OBSERVATIONS_PER_FAMILY}"
            )
        try:
            observation_id = _text(observation.get("observation_id"), "observation_id")
        except ValueError as error:
            raise DemandCardError(str(error)) from error
        url = _source_url(observation.get("source_url"))
        capture_method = observation.get("capture_method")
        try:
            capture_method = _text(capture_method, "capture_method")
        except ValueError as error:
            raise DemandCardError(str(error)) from error
        parsed = urlsplit(url)
        is_x_source = parsed.hostname and parsed.hostname.lower().rstrip(".") in {
            "x.com",
            "www.x.com",
            "twitter.com",
            "www.twitter.com",
        }
        if is_x_source and capture_method != "rendered_cdp_dom":
            raise DemandCardError(
                "X Article full body requires rendered_cdp_dom receipt"
            )
        full_body = observation.get("full_body")
        if isinstance(full_body, str) and full_body.strip():
            full_body = full_body.strip()
            digest = observation.get("source_sha256")
            if not isinstance(digest, str) or SHA256_RE.fullmatch(digest.lower()) is None:
                raise DemandCardError("full source body requires a SHA-256 receipt")
            digest = digest.lower()
            actual_digest = hashlib.sha256(full_body.encode("utf-8")).hexdigest()
            if actual_digest != digest:
                raise DemandCardError("full source body hash does not match receipt")
            if url in seen_urls:
                raise DemandCardError("full source bodies must use independent URLs")
            seen_urls.add(url)
            if capture_method in FULL_BODY_CAPTURE_METHODS:
                source_body = {
                    "observation_id": observation_id,
                    "source_family": family,
                    "url": url,
                    "sha256": digest,
                    "body": full_body,
                    "capture_method": capture_method,
                }
                if is_x_source:
                    source_body["article_identity"] = observation.get("article_identity")
                    source_body["target_id"] = observation.get("target_id")
                    source_body["rendered_identity"] = _validated_x_rendered_identity(
                        url=url,
                        body=full_body,
                        article_identity=observation.get("article_identity"),
                        target_id=observation.get("target_id"),
                        rendered_identity=observation.get("rendered_identity"),
                    )
                source_bodies.append(source_body)
        normalized_observation = {
            "observation_id": observation_id,
            "source_family": family,
            "url": url,
            "sha256": observation.get("source_sha256"),
            "capture_method": capture_method,
        }
        if is_x_source:
            normalized_observation["article_identity"] = observation.get("article_identity")
            normalized_observation["target_id"] = observation.get("target_id")
            if isinstance(full_body, str) and full_body.strip():
                normalized_observation["rendered_identity"] = _validated_x_rendered_identity(
                    url=url,
                    body=full_body,
                    article_identity=observation.get("article_identity"),
                    target_id=observation.get("target_id"),
                    rendered_identity=observation.get("rendered_identity"),
                )
        normalized_observations.append(normalized_observation)
    missing_families = [family for family in DEMAND_SOURCE_FAMILIES if not counts[family]]
    if missing_families:
        raise DemandCardError(
            "demand card requires observations from: " + ",".join(missing_families)
        )
    if len(source_bodies) < MIN_FULL_SOURCE_BODIES:
        raise DemandCardError(
            "demand card requires at least two independent full source bodies"
        )
    body_source_keys = {
        (body["source_family"], urlsplit(body["url"]).hostname)
        for body in source_bodies
    }
    if len(body_source_keys) < MIN_FULL_SOURCE_BODIES:
        raise DemandCardError(
            "full source bodies must span at least two independent source families or hosts"
        )
    return {
        "version": 1,
        "source_families": list(DEMAND_SOURCE_FAMILIES),
        **normalized_bindings,
        "observations": normalized_observations,
        "source_bodies": source_bodies,
    }


def validate_demand_card(card: Mapping[str, Any]) -> dict[str, Any]:
    """Revalidate a normalized queue-card payload without trusting its hashes."""

    if not isinstance(card, Mapping):
        raise DemandCardError("demand_card must be an object")
    if card.get("version") != 1:
        raise DemandCardError("demand_card.version must be 1")
    if card.get("source_families") != list(DEMAND_SOURCE_FAMILIES):
        raise DemandCardError("demand_card.source_families are invalid")
    observations = card.get("observations")
    source_bodies = card.get("source_bodies")
    if not isinstance(observations, list) or not isinstance(source_bodies, list):
        raise DemandCardError("demand_card observations and source_bodies are required")
    body_by_id: dict[str, Mapping[str, Any]] = {}
    for index, body in enumerate(source_bodies):
        if not isinstance(body, Mapping):
            raise DemandCardError(f"demand_card.source_bodies[{index}] must be an object")
        try:
            body_id = _text(body.get("observation_id"), "source body observation_id")
        except ValueError as error:
            raise DemandCardError(str(error)) from error
        if body_id in body_by_id:
            raise DemandCardError("demand_card source body IDs must be unique")
        body_by_id[body_id] = body
    original: list[dict[str, Any]] = []
    for index, observation in enumerate(observations):
        if not isinstance(observation, Mapping):
            raise DemandCardError(f"demand_card.observations[{index}] must be an object")
        try:
            observation_id = _text(
                observation.get("observation_id"), "observation.observation_id"
            )
            source_url = _text(observation.get("url"), "observation.url")
            capture_method = _text(
                observation.get("capture_method"), "observation.capture_method"
            )
        except ValueError as error:
            raise DemandCardError(str(error)) from error
        rebuilt: dict[str, Any] = {
            "observation_id": observation_id,
            "source_family": observation.get("source_family"),
            "source_url": source_url,
            "source_sha256": observation.get("sha256"),
            "capture_method": capture_method,
        }
        if urlsplit(source_url).hostname in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            rebuilt.update(
                {
                    "article_identity": observation.get("article_identity"),
                    "target_id": observation.get("target_id"),
                    "rendered_identity": observation.get("rendered_identity"),
                }
            )
        body = body_by_id.get(observation_id)
        if body is not None:
            rebuilt.update(
                {
                    "full_body": body.get("body"),
                    "source_sha256": body.get("sha256"),
                    "capture_method": body.get("capture_method"),
                }
            )
            if urlsplit(source_url).hostname in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
                rebuilt.update(
                    {
                        "article_identity": body.get("article_identity"),
                        "target_id": body.get("target_id"),
                        "rendered_identity": body.get("rendered_identity"),
                    }
                )
        original.append(rebuilt)
    bindings = {
        field: card.get(field)
        for field in _BINDING_FIELDS
    }
    if "binding_observation_ids" in card:
        bindings["binding_observation_ids"] = card["binding_observation_ids"]
    normalized = build_demand_card(original, bindings)
    if normalized != dict(card):
        raise DemandCardError("demand_card normalization or hash mismatch")
    return normalized
