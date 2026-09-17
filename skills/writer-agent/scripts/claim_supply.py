#!/usr/bin/env python3
"""Refill the Writer topic queue from new claims using one model choice at a time."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from claim_store import (  # noqa: E402
    ClaimStore,
    SHA256_RE,
    _text,
    _timestamp,
    canonicalize_url,
)
from claim_topic import materialize_topic  # noqa: E402
from demand_card import (  # noqa: E402
    DEMAND_SOURCE_FAMILIES,
    FULL_BODY_CAPTURE_METHODS,
    MAX_OBSERVATIONS_PER_FAMILY,
    MIN_FULL_SOURCE_BODIES,
    DemandCardError,
    build_demand_card,
    normalize_observation_id,
    select_demand_observations,
    validate_demand_card,
)


class ChooserUnavailable(RuntimeError):
    pass


class NoUsefulClaim(RuntimeError):
    pass


DEMAND_PREVIEW_LIMIT = 800
DISALLOWED_OPPORTUNITY_STATES = frozenset({"CLOSED", "REJECTED_POLICY", "EXPIRED"})


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def demand_topic_id(demand_card: Mapping[str, Any]) -> str:
    """Return the stable topic identity for one normalized paid-demand card."""

    canonical = json.dumps(
        demand_card,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"paid-demand:{hashlib.sha256(canonical).hexdigest()}"


def demand_primary_evidence_plan(
    demand_card: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Build primary evidence refs only from the selected demand observations."""

    observations = demand_card.get("observations")
    if not isinstance(observations, list):
        raise DemandCardError("demand card observations are required")
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, observation in enumerate(observations):
        if not isinstance(observation, Mapping):
            raise DemandCardError(f"demand card observation[{index}] is invalid")
        source_url = observation.get("url")
        if not isinstance(source_url, str) or not source_url.strip():
            raise DemandCardError(
                f"demand card observation[{index}] has no source URL"
            )
        source_url = source_url.strip()
        if source_url in seen:
            continue
        seen.add(source_url)
        refs.append({"method": "browse", "ref": source_url})
    if not refs:
        raise DemandCardError("demand card has no primary source URLs")
    return refs


def _demand_evidence_digest(
    observations: list[Mapping[str, Any]] | None,
) -> dict[str, Any] | None:
    if observations is None:
        return None
    digest_rows: list[dict[str, Any]] = []
    for row in observations:
        body = row.get("full_body")
        if not isinstance(body, str) or not body.strip():
            body = row.get("evidence_excerpt")
        if isinstance(body, str):
            body = body.strip()
            if len(body) > DEMAND_PREVIEW_LIMIT:
                body = body[:DEMAND_PREVIEW_LIMIT] + "…"
        else:
            body = None
        digest_rows.append(
            {
                "observation_id": row.get("observation_id"),
                "source_family": row.get("source_family"),
                "source_url": row.get("source_url"),
                "source_sha256": row.get("source_sha256"),
                "capture_method": row.get("capture_method"),
                "metrics": row.get("metrics"),
                "captured_at": row.get("captured_at"),
                "observed_at": row.get("observed_at"),
                "published_at": row.get("published_at"),
                "evidence_preview": body,
            }
        )
    return {
        "version": 1,
        "observations": digest_rows,
    }


def build_prompt(
    rows: list[dict[str, Any]],
    demand_observations: list[Mapping[str, Any]] | None = None,
) -> str:
    demand_mode = demand_observations is not None
    visible = [
        {
            "claim_id": row["claim_id"],
            "source_kind": row["source_kind"],
            "source_name": row["source_name"],
            "canonical_url": row["canonical_url"],
            "title": row["title"],
            "claim": row["claim"],
            "evidence_excerpt": row["evidence_excerpt"],
            "reader_job": row["reader_job"],
            "published_at": row["published_at"],
            "source_family": row.get("source_family"),
            "full_body": row.get("full_body"),
            "source_sha256": row.get("source_sha256"),
            "capture_method": row.get("capture_method"),
        }
        for row in rows
    ]
    prompt = """You are the topic selector for Writer Agent.

Choose at most one genuinely new external claim that can become a useful article for a
specific reader. Judge the reader's real job, the usefulness of the outcome, evidence
strength, freshness, and whether the angle adds more than paraphrasing the source. Do not
choose by a fixed subject taxonomy. Do not write about Writer Agent's internal machinery
unless that is itself the external reader's concrete job.

Every SELECT is a paid-demand card. It MUST bind observations from all four source
families: paid_market, reader_demand, publisher_opportunity, and owned_funnel. Keep no
more than two observations per family. Bind buyer, problem, transformation, deliverable,
price_hypothesis, and distribution_path. Include at least two independent full_body
receipts with source_sha256 and capture_method. An X Article is valid only when its
capture_method is rendered_cdp_dom; a twitter_cli_json excerpt is never a full body.
When a Demand evidence digest is present, choose only its immutable observation_id values.
Return demand_card with only the six bindings, observation_ids, and a
binding_observation_ids map that gives supporting observation_id values for every
binding. Do not return source_bodies or full bodies: code binds those immutable receipts
after validating the IDs. If demand observations are present but this contract cannot
be satisfied, return NO_USEFUL_CLAIM. Never fall back to an excerpt-only topic card.

The selected proposal MUST preserve candidate.reader_job exactly as reader.job and MUST
include candidate.canonical_url exactly in evidence_plan with method "browse". Never
invent experience, measurements, a customer, a product, a source, or revenue.

If none is useful, return exactly:
{"decision":"NO_USEFUL_CLAIM","reason":"<specific reason>"}

Otherwise return exactly one JSON object with this shape and no prose:
{
  "decision":"SELECT",
  "claim_id":"<existing claim_id>",
  "title":"<reader-facing title>",
  "angle":"<what the article proves or helps decide>",
  "topic_source":"timely-event|customer-pain|search-demand|product-proof|market-winner|paid-demand",
  "reader":{"audience":"<specific reader>","job":"<exact candidate.reader_job>","outcome":"<observable reader outcome>"},
  "evidence_plan":[{"method":"browse","ref":"<exact candidate.canonical_url>"}],
  "editorial_form":"explainer|how-to|comparison|opinion|report",
  "product_link":{"audience":"<why this reader belongs in the writing business>"},
  "demand_card":{"buyer":"<buyer>","problem":"<problem>","transformation":"<transformation>","deliverable":"<deliverable>","price_hypothesis":{"amount":49,"currency":"USD","basis":"<evidence>"},"distribution_path":[{"channel":"<channel>","role":"<role>"}],"observation_ids":["<immutable observation_id>"],"binding_observation_ids":{"buyer":["<observation_id>"],"problem":["<observation_id>"],"transformation":["<observation_id>"],"deliverable":["<observation_id>"],"price_hypothesis":["<observation_id>"],"distribution_path":["<observation_id>"]}},
  "priority":1
}

Candidates:
""" + json.dumps(visible, ensure_ascii=False, indent=2, sort_keys=True)
    if demand_mode:
        prompt = prompt.replace(
            "The selected proposal MUST preserve candidate.reader_job exactly as reader.job and MUST\n"
            "include candidate.canonical_url exactly in evidence_plan with method \"browse\". Never\n"
            "invent experience, measurements, a customer, a product, a source, or revenue.",
            "Demand mode is authoritative: legacy claim rows are evidence only and MUST NOT constrain\n"
            "the title, reader audience/job/outcome, topic, editorial form, price, or evidence plan.\n"
            "Select those fields independently from the immutable Demand evidence digest and its\n"
            "supporting observations. Do not copy a legacy claim title, reader_job, claim_id, or URL\n"
            "into the demand selection. Code anchors consumption to one legacy claim only after this\n"
            "proposal is validated. Never invent experience, measurements, a customer, a product, a\n"
            "source, or revenue.",
        )
        prompt = prompt.replace(
            '"claim_id":"<existing claim_id>",',
            '"claim_id":"<optional legacy evidence anchor>",',
        )
        prompt = prompt.replace(
            '"reader":{"audience":"<specific reader>","job":"<exact candidate.reader_job>","outcome":"<observable reader outcome>"},',
            '"reader":{"audience":"<specific demand buyer>","job":"<demand-derived reader job>","outcome":"<observable reader outcome>"},',
        )
        prompt = prompt.replace(
            '"evidence_plan":[{"method":"browse","ref":"<exact candidate.canonical_url>"}],',
            '"evidence_plan":[{"method":"browse","ref":"<exact selected demand observation source_url>"}],',
        )
    demand_digest = _demand_evidence_digest(demand_observations)
    if demand_digest is not None:
        prompt += (
            "\n\nDemand evidence digest (canonical, bounded, immutable IDs; full source bodies "
            "remain durable outside this prompt):\n"
            + json.dumps(demand_digest, ensure_ascii=False, indent=2, sort_keys=True)
        )
    return prompt


def _extract_json(stdout: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    found: list[tuple[int, int, dict[str, Any]]] = []
    for index, character in enumerate(stdout):
        if character != "{":
            continue
        try:
            value, consumed = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            found.append((consumed, index, value))
    if not found:
        raise ChooserUnavailable("model returned no JSON proposal")
    return max(found, key=lambda item: (item[0], item[1]))[2]


def interpret_model_proposal(
    proposal: dict[str, Any],
    *,
    demand_mode: bool = False,
) -> dict[str, Any]:
    decision = proposal.get("decision")
    if decision == "NO_USEFUL_CLAIM":
        raise NoUsefulClaim(str(proposal.get("reason") or "no useful claim selected"))
    required = {
        "title", "angle", "topic_source", "reader", "evidence_plan",
        "editorial_form", "product_link", "priority",
    }
    if not demand_mode:
        required.add("claim_id")
    if decision is None and required <= set(proposal):
        proposal = {**proposal, "decision": "SELECT"}
        decision = "SELECT"
    if decision != "SELECT":
        raise ChooserUnavailable("model proposal has no valid decision or required fields")
    missing = required - set(proposal)
    if missing:
        raise ChooserUnavailable(
            "model SELECT proposal is missing required fields: " + ",".join(sorted(missing))
        )
    return proposal


def model_choose(
    rows: list[dict[str, Any]],
    *,
    runner: Path,
    run_id: str,
    timeout: int = 300,
    demand_observations: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    prompt = build_prompt(rows, demand_observations=demand_observations)
    environment = {**os.environ, "ARTICLE_RUN_ID": run_id}
    try:
        result = subprocess.run(
            [str(runner), "judge", "--prompt-file", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            env=environment,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ChooserUnavailable(type(error).__name__) from error
    if result.returncode != 0:
        raise ChooserUnavailable(f"model runner returned {result.returncode}")
    return interpret_model_proposal(
        _extract_json(result.stdout),
        demand_mode=demand_observations is not None,
    )


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _queue_frontmatter(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    try:
        value = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    return value if isinstance(value, dict) else None


def _opportunity_policy_disallowed(
    database: Path | None,
    source_url: str,
    *,
    observation_id: str | None = None,
    unknown_is_disallowed: bool = True,
) -> bool:
    """Return True unless one unambiguous, current opportunity row authorizes use.

    Demand cards are untrusted serialized input.  A missing store, a URL spelling
    variant, or moving a prohibited opportunity into another source family must
    never turn into an allow decision.  When an observation carries an
    ``opportunity:<id>:...`` identity, the ID is authoritative and its URL is
    checked against the same row; otherwise the canonical URL must resolve to one
    and only one opportunity row.
    """

    if database is None or not database.exists():
        return unknown_is_disallowed
    if database.is_symlink() or not database.is_file():
        return unknown_is_disallowed
    try:
        canonical_source_url = canonicalize_url(source_url, "rss")
        source_parts = urlsplit(canonical_source_url)
        canonical_source_key = urlunsplit(
            (source_parts.scheme, source_parts.netloc, source_parts.path, "", "")
        )
    except (TypeError, ValueError):
        return True
    try:
        connection = sqlite3.connect(
            f"file:{database.resolve()}?mode=ro", uri=True, timeout=2
        )
        try:
            if isinstance(observation_id, str) and observation_id.startswith("opportunity:"):
                parts = observation_id.split(":")
                if len(parts) < 2 or not parts[1].strip():
                    return True
                rows = connection.execute(
                    "SELECT opportunity_id,state,ai_policy,official_program_url,"
                    "application_url,supporting_urls_json "
                    "FROM opportunities WHERE opportunity_id=?",
                    (parts[1],),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT opportunity_id,state,ai_policy,official_program_url,"
                    "application_url,supporting_urls_json "
                    "FROM opportunities"
                ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return unknown_is_disallowed
    matches = []
    for row in rows:
        row_urls: list[str] = [row[3], row[4]]
        try:
            supporting_urls = json.loads(row[5] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            supporting_urls = []
        if isinstance(supporting_urls, list):
            row_urls.extend(item for item in supporting_urls if isinstance(item, str))
        row_matches = False
        for candidate_url in row_urls:
            try:
                row_url = canonicalize_url(candidate_url, "rss")
            except (TypeError, ValueError):
                continue
            row_parts = urlsplit(row_url)
            row_key = urlunsplit(
                (row_parts.scheme, row_parts.netloc, row_parts.path, "", "")
            )
            if row_key == canonical_source_key:
                row_matches = True
                break
        if row_matches:
            matches.append(row)
    if not matches:
        return unknown_is_disallowed
    # A duplicated canonical URL is ambiguous even when the observation does
    # not carry an opportunity identity.  Never let a prohibited row be hidden
    # behind another row's state or family.
    if len(matches) != 1:
        return True
    if isinstance(observation_id, str) and observation_id.startswith("opportunity:"):
        parts = observation_id.split(":")
        if str(matches[0][0]) != parts[1]:
            return True
    state = str(matches[0][1] or "").upper()
    ai_policy = str(matches[0][2] or "").upper()
    return state in DISALLOWED_OPPORTUNITY_STATES or ai_policy == "PROHIBITED"


def _is_paid_demand_queue_card(
    path: Path, *, opportunity_database: Path | None = None
) -> bool:
    frontmatter = _queue_frontmatter(path)
    if not frontmatter or frontmatter.get("topic_source") != "paid-demand":
        return False
    try:
        card = validate_demand_card(frontmatter.get("demand_card"))
    except DemandCardError:
        return False
    for observation in card.get("observations", []):
        if not isinstance(observation, Mapping):
            continue
        source_url = observation.get("url")
        observation_id = observation.get("observation_id")
        is_opportunity_observation = (
            isinstance(observation_id, str) and observation_id.startswith("opportunity:")
        )
        is_opportunity_family = observation.get("source_family") in {
            "paid_market",
            "publisher_opportunity",
        }
        is_opportunity_signal = is_opportunity_observation or is_opportunity_family
        if not isinstance(source_url, str):
            if is_opportunity_signal:
                return False
            continue
        # Every URL is checked against the opportunity DB.  This catches a
        # prohibited opportunity that has been relabeled as reader demand;
        # only an unknown URL without an opportunity signal remains ordinary
        # evidence and is allowed to proceed.
        if _opportunity_policy_disallowed(
            opportunity_database,
            source_url,
            observation_id=observation_id if isinstance(observation_id, str) else None,
            unknown_is_disallowed=is_opportunity_signal,
        ):
            return False
    return True


def _quarantine_legacy_queue(
    queue: Path, *, opportunity_database: Path | None = None
) -> list[str]:
    rejected = queue.parent / "rejected"
    moved: list[str] = []
    for path in sorted(queue.glob("*.md")):
        if not path.is_file() or path.is_symlink() or _is_paid_demand_queue_card(
            path, opportunity_database=opportunity_database
        ):
            continue
        rejected.mkdir(parents=True, exist_ok=True)
        destination = rejected / path.name
        if destination.exists():
            destination = rejected / f"{path.stem}-{hashlib.sha256(path.read_bytes()).hexdigest()[:12]}{path.suffix}"
        os.replace(path, destination)
        moved.append(str(destination))
    return moved


def _queue_count(
    queue: Path,
    *,
    demand_mode: str = "legacy-migration",
    opportunity_database: Path | None = None,
) -> int:
    paths = [path for path in queue.glob("*.md") if path.is_file() and not path.is_symlink()]
    if demand_mode == "required":
        return sum(
            _is_paid_demand_queue_card(
                path, opportunity_database=opportunity_database
            )
            for path in paths
        )
    return len(paths)


def _demand_topic_exists(queue: Path, topic_id: str) -> bool:
    """Check queue/in-progress/done cards before retrying an exact demand card."""

    root = queue.parent
    for stage in ("queue", "in-progress", "done"):
        directory = root / stage
        if not directory.is_dir():
            continue
        for path in directory.glob("*.md"):
            if not path.is_file() or path.is_symlink():
                continue
            frontmatter = _queue_frontmatter(path)
            if not isinstance(frontmatter, dict):
                continue
            if frontmatter.get("topic_source") != "paid-demand":
                continue
            if frontmatter.get("topic_id") == topic_id:
                return True
            card = frontmatter.get("demand_card")
            try:
                if isinstance(card, Mapping) and demand_topic_id(card) == topic_id:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _normalize_model_demand_observation_ids(
    selected_card: Mapping[str, Any],
    selected_observations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Make the model's IDs satisfy the immutable two-body independence contract.

    The model may choose two ordinary opportunity excerpts even though the durable
    evidence view contains a verified publisher body.  Rejecting that proposal makes
    supply depend on model wording rather than evidence.  Add or replace only with
    bounded, already-selected immutable rows; never fetch, invent, or relabel evidence.
    """

    raw_ids = selected_card.get("observation_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise DemandCardError("model demand_card must list unique observation_ids")

    chosen_ids: list[str] = []
    for value in raw_ids:
        try:
            normalized_id = normalize_observation_id(
                value, "model demand_card observation_id"
            )
        except DemandCardError as error:
            raise DemandCardError(
                "model demand_card must list unique observation_ids"
            ) from error
        if normalized_id in chosen_ids:
            raise DemandCardError("model demand_card must list unique observation_ids")
        chosen_ids.append(normalized_id)

    by_id: dict[str, Mapping[str, Any]] = {}
    for row in selected_observations:
        if not isinstance(row, Mapping) or not isinstance(row.get("observation_id"), str):
            continue
        normalized_id = normalize_observation_id(row["observation_id"], "observation_id")
        if normalized_id in by_id:
            raise DemandCardError("selected observation IDs must be unique")
        by_id[normalized_id] = row
    if not set(chosen_ids) <= set(by_id):
        raise DemandCardError("model demand_card references an unsupported observation_id")
    supporting = selected_card.get("binding_observation_ids")
    if isinstance(supporting, Mapping):
        for field, values in supporting.items():
            if not isinstance(values, list):
                continue
            for value in values:
                try:
                    normalized_id = normalize_observation_id(
                        value, f"binding_observation_ids.{field}"
                    )
                except DemandCardError:
                    continue
                if normalized_id in by_id and normalized_id not in chosen_ids:
                    chosen_ids.append(normalized_id)
    chosen = [by_id[value] for value in chosen_ids]

    def is_full_body(row: Mapping[str, Any]) -> bool:
        body = row.get("full_body")
        digest = row.get("source_sha256")
        return (
            isinstance(body, str)
            and bool(body.strip())
            and row.get("capture_method") in FULL_BODY_CAPTURE_METHODS
            and isinstance(digest, str)
            and hashlib.sha256(body.strip().encode("utf-8")).hexdigest()
            == digest.lower()
        )

    def body_key(row: Mapping[str, Any]) -> tuple[str, str] | None:
        if not is_full_body(row):
            return None
        host = urlsplit(str(row.get("source_url") or "")).hostname
        family = row.get("source_family")
        if not isinstance(family, str) or not isinstance(host, str) or not host:
            return None
        return family, host.lower().rstrip(".")

    def family_count(family: str) -> int:
        return sum(row.get("source_family") == family for row in chosen)

    body_keys = {key for row in chosen if (key := body_key(row)) is not None}
    if len(body_keys) >= MIN_FULL_SOURCE_BODIES:
        normalized = dict(selected_card)
        normalized["observation_ids"] = chosen_ids
        normalized["_evidence_normalization"] = {
            "added": [],
            "replaced": [],
            "reason": "model-selection-already-has-independent-full-body-receipts",
        }
        return normalized

    added: list[str] = []
    replaced: list[dict[str, str]] = []
    candidates = [
        row
        for row in selected_observations
        if isinstance(row, Mapping)
        and isinstance(row.get("observation_id"), str)
        and normalize_observation_id(row["observation_id"], "observation_id")
        not in chosen_ids
        and body_key(row) is not None
    ]
    for candidate in candidates:
        key = body_key(candidate)
        if key is None or key in body_keys:
            continue
        family = str(candidate.get("source_family"))
        candidate_id = normalize_observation_id(
            candidate["observation_id"], "observation_id"
        )
        if family_count(family) < MAX_OBSERVATIONS_PER_FAMILY:
            chosen.append(candidate)
            chosen_ids.append(candidate_id)
            added.append(candidate_id)
        else:
            replacement_index = next(
                (
                    index
                    for index, row in enumerate(chosen)
                    if row.get("source_family") == family and body_key(row) is None
                ),
                None,
            )
            if replacement_index is None:
                continue
            old_id = str(chosen[replacement_index]["observation_id"])
            chosen[replacement_index] = candidate
            chosen_ids[replacement_index] = candidate_id
            replaced.append({"from": old_id, "to": candidate_id})
        body_keys.add(key)
        if len(body_keys) >= MIN_FULL_SOURCE_BODIES:
            break

    if len(body_keys) < MIN_FULL_SOURCE_BODIES:
        raise DemandCardError(
            "full source bodies must span at least two independent source families or hosts"
        )
    normalized = dict(selected_card)
    normalized["observation_ids"] = chosen_ids
    normalized["_evidence_normalization"] = {
        "added": added,
        "replaced": replaced,
        "reason": "model-selection-missing-independent-full-body-receipt",
    }
    return normalized


def refill_queue(
    database: Path | str,
    queue: Path | str,
    receipt_path: Path | str,
    *,
    floor: int,
    chooser: Callable[[list[dict[str, Any]]], dict[str, Any]],
    now: str,
    demand_observations: list[Mapping[str, Any]] | None = None,
    demand_bindings: Mapping[str, Any] | None = None,
    demand_chooser: Callable[
        [list[dict[str, Any]], list[Mapping[str, Any]]], dict[str, Any]
    ] | None = None,
    demand_mode: str = "legacy-migration",
) -> dict[str, Any]:
    if floor < 1:
        raise ValueError("floor must be positive")
    observed_at = str(_timestamp(now, "now"))
    if demand_mode not in {"required", "legacy-migration"}:
        raise ValueError("demand_mode must be required or legacy-migration")
    if demand_observations is not None and demand_mode == "legacy-migration":
        demand_mode = "required"
    queue = Path(queue)
    queue.mkdir(parents=True, exist_ok=True)
    opportunity_database = Path(database).with_name("opportunities.sqlite3")
    if not opportunity_database.exists():
        opportunity_database = None
    quarantined_topics = (
        _quarantine_legacy_queue(
            queue,
            opportunity_database=opportunity_database,
        ) if demand_mode == "required" else []
    )
    queue_before = _queue_count(
        queue,
        demand_mode=demand_mode,
        opportunity_database=opportunity_database,
    )
    created: list[dict[str, Any]] = []
    status = "SUFFICIENT" if queue_before >= floor else "FILLING"
    reason = ""
    if demand_mode == "required" and queue_before < floor and demand_observations is None:
        status = "DEMAND_CARD_INVALID"
        reason = "required demand mode needs immutable demand observations"
    store = ClaimStore(database)
    demand_card: dict[str, Any] | None = None
    demand_selection: dict[str, Any] | None = None
    selected_observations: list[Mapping[str, Any]] | None = None
    if queue_before < floor and demand_observations is not None:
        if not demand_observations:
            status = "DEMAND_CARD_INVALID"
            reason = "demand card observations must be a non-empty list"
        else:
            try:
                selection = select_demand_observations(demand_observations)
                selected_observations = selection["observations"]
                demand_selection = selection["receipt"]
                if demand_bindings is not None:
                    demand_card = build_demand_card(selected_observations, demand_bindings)
            except DemandCardError as error:
                status = "DEMAND_CARD_INVALID"
                reason = str(error)
    prompt_hashes: list[str] = []
    while _queue_count(
        queue,
        demand_mode=demand_mode,
        opportunity_database=opportunity_database,
    ) < floor:
        if status == "DEMAND_CARD_INVALID":
            break
        if demand_mode == "required" and demand_card is not None:
            topic_id = demand_topic_id(demand_card)
            if _demand_topic_exists(queue, topic_id):
                status = "NO_PROGRESS"
                reason = "duplicate paid-demand card already exists in topic state"
                break
        # Required demand selection is driven by the immutable demand view.
        # Legacy ClaimStore rows are optional evidence and never enumerate the
        # candidate set or gate a paid-demand topic.
        candidates = [] if demand_mode == "required" else store.list_unconsumed(limit=12)
        if not candidates and demand_mode != "required":
            status = "CLAIMS_UNAVAILABLE"
            reason = "no unconsumed claims"
            break
        prompt = build_prompt(candidates, demand_observations=selected_observations)
        prompt_hashes.append(prompt_sha256(prompt))
        try:
            if demand_observations is not None and demand_bindings is None:
                if demand_chooser is None or selected_observations is None:
                    raise ChooserUnavailable("demand-aware chooser is required")
                proposal = demand_chooser(candidates, selected_observations)
            else:
                proposal = chooser(candidates)
        except NoUsefulClaim as error:
            status = "NO_USEFUL_CLAIM"
            reason = str(error)
            break
        except ChooserUnavailable as error:
            status = "MODEL_UNAVAILABLE"
            reason = str(error)
            break
        if not isinstance(proposal, dict):
            status = "INVALID_PROPOSAL"
            reason = "model proposal must be an object"
            break
        if demand_observations is not None and demand_card is None:
            selected_card = proposal.get("demand_card")
            if not isinstance(selected_card, Mapping):
                status = "DEMAND_CARD_INVALID"
                reason = "model SELECT proposal must include demand_card bindings"
                break
            try:
                selected_card = _normalize_model_demand_observation_ids(
                    selected_card,
                    selected_observations or [],
                )
                observation_ids = selected_card["observation_ids"]
                by_id = {
                    str(row["observation_id"]): row
                    for row in selected_observations or []
                }
                bindings = {
                    field: selected_card.get(field)
                    for field in (
                        "buyer",
                        "problem",
                        "transformation",
                        "deliverable",
                        "price_hypothesis",
                        "distribution_path",
                    )
                }
                bindings["binding_observation_ids"] = selected_card.get(
                    "binding_observation_ids"
                )
                selected_for_card = [by_id[value] for value in observation_ids]
                demand_card = build_demand_card(selected_for_card, bindings)
            except DemandCardError as error:
                status = "DEMAND_CARD_INVALID"
                reason = str(error)
                break
        if demand_card is not None:
            proposal = dict(proposal)
            selected_card = proposal.get("demand_card")
            if selected_card is not None and demand_bindings is not None:
                try:
                    if validate_demand_card(selected_card) != demand_card:
                        raise DemandCardError(
                            "model demand_card does not match durable observations"
                        )
                except DemandCardError as error:
                    status = "DEMAND_CARD_INVALID"
                    reason = str(error)
                    break
            proposal["demand_card"] = demand_card
            proposal["topic_source"] = "paid-demand"
        if demand_mode == "required":
            if demand_card is None:
                status = "DEMAND_CARD_INVALID"
                reason = "required demand mode did not produce a demand card"
                break
            proposal = dict(proposal)
            # A legacy claim_id, when returned, is audit metadata only. Its
            # title, reader job, URL, and topic metadata never enter the route.
            proposal.pop("claim_id", None)
            proposal["topic_id"] = demand_topic_id(demand_card)
            try:
                proposal["evidence_plan"] = demand_primary_evidence_plan(demand_card)
            except DemandCardError as error:
                status = "DEMAND_CARD_INVALID"
                reason = str(error)
                break
            proposal["topic_source"] = "paid-demand"
            # With no configured bindings, the stable demand card only exists after
            # model selection. Re-check every durable topic stage before attempting
            # materialization so a card moved out of queue cannot be reinstalled.
            if _demand_topic_exists(queue, proposal["topic_id"]):
                status = "NO_PROGRESS"
                reason = "duplicate paid-demand card already exists in topic state"
                break
        try:
            materialized = materialize_topic(
                database,
                queue,
                proposal,
                created_at=observed_at,
                demand_mode=demand_mode,
            )
            created.append(materialized)
            if demand_mode == "required" and materialized.get("installed") is False:
                status = "NO_PROGRESS"
                reason = "duplicate paid-demand card; no queue growth"
                break
        except (KeyError, ValueError) as error:
            status = "INVALID_PROPOSAL"
            reason = str(error)
            break
    queue_after = _queue_count(
        queue,
        demand_mode=demand_mode,
        opportunity_database=opportunity_database,
    )
    if queue_after >= floor:
        status = "FILLED" if created else "SUFFICIENT"
        reason = ""
    receipt: dict[str, Any] = {
        "version": 1,
        "observed_at": observed_at,
        "status": status,
        "floor": floor,
        "queue_before": queue_before,
        "queue_after": queue_after,
        "created_topics": created,
        "quarantined_topics": quarantined_topics,
    }
    if reason:
        receipt["reason"] = reason
    if demand_card is not None:
        canonical_card = json.dumps(
            demand_card, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        receipt["demand_card_sha256"] = hashlib.sha256(canonical_card).hexdigest()
        body_by_id = {
            body["observation_id"]: body for body in demand_card["source_bodies"]
        }
        receipt["demand_observation_receipts"] = [
            {
                **observation,
                "body_sha256": (
                    body_by_id[observation["observation_id"]]["sha256"]
                    if observation["observation_id"] in body_by_id
                    else None
                ),
            }
            for observation in demand_card["observations"]
        ]
        observation_receipt_bytes = json.dumps(
            receipt["demand_observation_receipts"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        receipt["demand_observations_sha256"] = hashlib.sha256(
            observation_receipt_bytes
        ).hexdigest()
        receipt["source_body_sha256s"] = sorted(
            body["sha256"] for body in demand_card["source_bodies"]
        )
    if demand_selection is not None:
        receipt["demand_selection"] = demand_selection
    if prompt_hashes:
        receipt["prompt_sha256s"] = prompt_hashes
    _atomic_json(Path(receipt_path), receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--floor", type=int, default=3)
    parser.add_argument(
        "--runner",
        type=Path,
        default=SCRIPT_DIR.parent / "runtime" / "model-runner.sh",
    )
    parser.add_argument(
        "--now",
        default=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    args = parser.parse_args(argv)
    now = args.now() if callable(args.now) else args.now
    run_id = f"claim-supply-{str(now).replace(':', '').replace('-', '')}"
    receipt = refill_queue(
        args.db,
        args.queue,
        args.receipt,
        floor=args.floor,
        chooser=lambda rows: model_choose(rows, runner=args.runner, run_id=run_id),
        now=now,
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["status"] in {"FILLED", "SUFFICIENT"} else 75


if __name__ == "__main__":
    raise SystemExit(main())
