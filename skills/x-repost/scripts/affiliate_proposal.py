#!/usr/bin/env python3
"""Validate and claim one Affiliate-owned Repost proposal without tracking URLs."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


PROPOSAL_ID = re.compile(r"^[0-9a-f]{64}$")
PLACEMENT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
CONSUMPTION_STATES = {"EFFECT_STARTED", "POSTED", "UNVERIFIED", "NO_EFFECT"}
SAFE_FIELDS = (
    "receipt_type", "state", "proposal_id", "placement_id", "owned_article_url",
    "language", "disclosure_required", "tracking_link_state", "revenue_credit_state",
    "article_title", "buyer_intent",
)
JOB_FIELDS = {
    "schema_version", "receipt_type", "state", "job_id", "effect_identity",
    "placement_id", "owned_article_url", "content_sha256", "experiment_lineage",
    "target_x_account", "cadence_class", "policy_sha256", "source_set_sha256",
    "created_at", "private_tracking_url_state", "revenue_credit_state",
}
QUOTE_JOB_FIELDS = {"distribution_mode", "control_post_url"}
ROUTE_JOB_FIELDS = {"distribution_route_id"}
X_TRANSFORMED_URL_LENGTH = 23
UNVERIFIED_RECOVERY_WINDOW = timedelta(hours=6)
REVISION_REASONS = frozenset({"POSTIZ_RAW_LENGTH", "CONFIRMED_NO_EFFECT"})
URL = re.compile(r"https?://\S+")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("proposal unavailable") from error
    if not isinstance(value, dict):
        raise ValueError("proposal is not an object")
    return value


def valid(proposal: dict) -> bool:
    if not isinstance(proposal, dict):
        return False
    url = proposal.get("owned_article_url")
    if not isinstance(url, str) or any(char.isspace() or ord(char) < 32 for char in url):
        return False
    for field in ("article_title", "buyer_intent"):
        value = proposal.get(field)
        if value is not None and (
            not isinstance(value, str) or not 0 < len(value) <= 240
            or any(char in value for char in "\r\n")
            or "http" in value.casefold()
        ):
            return False
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return all((
        proposal.get("receipt_type") == "AFFILIATE_REPOST_PROPOSAL",
        proposal.get("state") == "READY_FOR_EXISTING_REPOST_OWNER",
        isinstance(proposal.get("proposal_id"), str)
        and bool(PROPOSAL_ID.fullmatch(proposal["proposal_id"])),
        isinstance(proposal.get("placement_id"), str)
        and bool(PLACEMENT_ID.fullmatch(proposal["placement_id"])),
        proposal.get("language") == "en",
        proposal.get("disclosure_required") is True,
        proposal.get("tracking_link_state") == "NOT_INCLUDED",
        proposal.get("revenue_credit_state") == "NO_REVENUE_CREDIT",
        parsed.scheme == "https"
        and parsed.hostname == "aniccaai.com"
        and bool(re.fullmatch(r"/blog/[a-z0-9][a-z0-9-]*", parsed.path))
        and not parsed.username and not parsed.password and port is None
        and not parsed.query and not parsed.fragment
    ))


def canonical(proposal: dict) -> dict:
    if not valid(proposal):
        raise ValueError("invalid proposal")
    return {field: proposal.get(field) for field in SAFE_FIELDS}


def valid_job(job: dict) -> bool:
    if not isinstance(job, dict) or set(job) not in {
        frozenset(JOB_FIELDS), frozenset(JOB_FIELDS | QUOTE_JOB_FIELDS),
        frozenset(JOB_FIELDS | QUOTE_JOB_FIELDS | ROUTE_JOB_FIELDS),
    }:
        return False
    url = job.get("owned_article_url")
    lineage = job.get("experiment_lineage")
    try:
        parsed = urlparse(url)
        port = parsed.port
        created = datetime.fromisoformat(job.get("created_at", "").replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return False
    lineage_valid = (
        isinstance(lineage, dict)
        and set(lineage) == {"kind", "decision_id", "control_placement_id"}
        and (
            lineage == {"kind": "BASE", "decision_id": None, "control_placement_id": None}
            or (
                lineage.get("kind") == "EXPERIMENT"
                and isinstance(lineage.get("decision_id"), str)
                and PROPOSAL_ID.fullmatch(lineage["decision_id"])
                and isinstance(lineage.get("control_placement_id"), str)
                and PLACEMENT_ID.fullmatch(lineage["control_placement_id"])
            )
        )
    )
    quote_valid = (
        not (set(job) & QUOTE_JOB_FIELDS)
        or (
            set(job) >= QUOTE_JOB_FIELDS
            and job.get("distribution_mode") in {
                "QUOTE_CONTROL_POST", "QUOTE_RELEVANT_EXTERNAL",
            }
            and isinstance(job.get("control_post_url"), str)
            and bool(re.fullmatch(
                r"https://x\.com/[A-Za-z0-9_]{1,15}/status/[0-9]+",
                job["control_post_url"],
            ))
        )
    )
    route_valid = (
        "distribution_route_id" not in job
        or (
            isinstance(job.get("distribution_route_id"), str)
            and PROPOSAL_ID.fullmatch(job["distribution_route_id"])
        )
    )
    return all((
        job.get("schema_version") == 1,
        job.get("receipt_type") == "AFFILIATE_X_DISTRIBUTION_JOB",
        job.get("state") == "QUEUED",
        isinstance(job.get("job_id"), str) and PROPOSAL_ID.fullmatch(job["job_id"]),
        isinstance(job.get("effect_identity"), str)
        and PROPOSAL_ID.fullmatch(job["effect_identity"]),
        isinstance(job.get("placement_id"), str)
        and PLACEMENT_ID.fullmatch(job["placement_id"]),
        isinstance(job.get("content_sha256"), str)
        and PROPOSAL_ID.fullmatch(job["content_sha256"]),
        isinstance(job.get("policy_sha256"), str)
        and PROPOSAL_ID.fullmatch(job["policy_sha256"]),
        isinstance(job.get("source_set_sha256"), str)
        and PROPOSAL_ID.fullmatch(job["source_set_sha256"]),
        lineage_valid,
        quote_valid,
        route_valid,
        isinstance(job.get("target_x_account"), str)
        and bool(re.fullmatch(r"[A-Za-z0-9_]{1,15}", job["target_x_account"])),
        job.get("cadence_class") == "AFFILIATE_MONETIZATION",
        job.get("private_tracking_url_state") == "NOT_INCLUDED",
        job.get("revenue_credit_state") == "NO_REVENUE_CREDIT",
        created.tzinfo is not None,
        parsed.scheme == "https" and parsed.hostname == "aniccaai.com"
        and bool(re.fullmatch(r"/blog/[a-z0-9][a-z0-9-]*", parsed.path))
        and not parsed.username and not parsed.password and port is None
        and not parsed.query and not parsed.fragment,
    ))


def distribution_jobs(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        try:
            jobs = [json.loads(line) for line in stream if line.strip()]
        except ValueError as error:
            raise ValueError("distribution job queue invalid") from error
    if any(not valid_job(job) for job in jobs):
        raise ValueError("distribution job queue invalid")
    if len({job["job_id"] for job in jobs}) != len(jobs):
        raise ValueError("distribution job queue contains duplicate job identity")
    if len({job["effect_identity"] for job in jobs}) != len(jobs):
        raise ValueError("distribution job queue contains duplicate effect identity")
    return jobs


def valid_job_claim(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    return all((
        row.get("schema_version") == 1,
        row.get("receipt_type") == "X_REPOST_DISTRIBUTION_JOB_CLAIM",
        row.get("state") == "EFFECT_STARTED",
        row.get("owner_label") == "ai.anicca.x-repost-pass",
        isinstance(row.get("job_id"), str) and PROPOSAL_ID.fullmatch(row["job_id"]),
        isinstance(row.get("effect_identity"), str)
        and PROPOSAL_ID.fullmatch(row["effect_identity"]),
        valid_job(row.get("job")),
        row.get("job_id") == (row.get("job") or {}).get("job_id"),
        row.get("effect_identity") == (row.get("job") or {}).get("effect_identity"),
        row.get("placement_id") == (row.get("job") or {}).get("placement_id"),
        isinstance(row.get("observed_at"), str),
    ))


def distribution_claims(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                  if line.strip()]
    except (OSError, ValueError) as error:
        raise ValueError("distribution job claim ledger invalid") from error
    if any(not valid_job_claim(row) for row in values):
        raise ValueError("distribution job claim ledger invalid")
    return values


def claim_next_job(
    queue_path: Path, claims_path: Path, results_path: Path | None = None,
) -> dict:
    jobs = distribution_jobs(queue_path)
    terminal = False
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    with claims_path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        claims = []
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError as error:
                raise ValueError("distribution job claim ledger invalid") from error
            if not valid_job_claim(row):
                raise ValueError("distribution job claim ledger invalid")
            claims.append(row)
        if claims:
            current = claims[-1]
            results = distribution_results(results_path) if results_path else []
            current_results = [
                row for row in results if row.get("job_id") == current["job_id"]
            ]
            exhausted_no_effect = bool(
                current_results and current_results[-1].get("state") == "NO_EFFECT"
                and sum(row.get("state") == "RETRY_READY" for row in current_results) >= 2
            )
            terminal = bool(current_results and (
                current_results[-1].get("state") == "POSTED"
                or exhausted_no_effect
            ))
            if not terminal:
                return {**current, "changed": False}
            claimed_ids = {row["job_id"] for row in claims}
            jobs = [job for job in jobs if job["job_id"] not in claimed_ids]
            latest_experiments = {}
            passthrough = []
            for job in jobs:
                lineage = job.get("experiment_lineage") or {}
                control = lineage.get("control_placement_id")
                if lineage.get("kind") != "EXPERIMENT" or not control:
                    passthrough.append(job)
                    continue
                prior = latest_experiments.get(control)
                if prior is None or (job["created_at"], job["job_id"]) > (
                    prior["created_at"], prior["job_id"],
                ):
                    latest_experiments[control] = job
            jobs = passthrough + list(latest_experiments.values())
        if not jobs:
            return ({"state": "NO_JOB", "changed": False} if terminal or not claims
                    else {**claims[-1], "changed": False})
        job = min(jobs, key=lambda value: (value["created_at"], value["job_id"]))
        row = {
            "schema_version": 1,
            "receipt_type": "X_REPOST_DISTRIBUTION_JOB_CLAIM",
            "state": "EFFECT_STARTED",
            "job_id": job["job_id"],
            "effect_identity": job["effect_identity"],
            "placement_id": job["placement_id"],
            "owner_label": "ai.anicca.x-repost-pass",
            "job": job,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        stream.seek(0, os.SEEK_END)
        stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        return {**row, "changed": True}


def render_claimed_job(
    claims_path: Path, payloads_dir: Path, copy_path: Path | None = None,
    candidates_path: Path | None = None,
) -> dict:
    claims = distribution_claims(claims_path)
    if not claims:
        return {"state": "NO_CLAIM", "changed": False}
    job = claims[-1]["job"]
    path = payloads_dir / f"{job['job_id']}.json"
    mode = job.get("distribution_mode")
    quote_mode = mode in {"QUOTE_CONTROL_POST", "QUOTE_RELEVANT_EXTERNAL"}
    if quote_mode and path.is_file() and copy_path is None:
        return {**distribution_payload(claims_path, payloads_dir), "changed": False}
    if quote_mode:
        if copy_path is None:
            raise ValueError("quote distribution requires model copy")
        copy = read_json(copy_path)
        wrapper = copy.get("text")
        external = mode == "QUOTE_RELEVANT_EXTERNAL"
        contract_fields = ({"text", "claims", "selected", "source_url"} if external
                           else {"text", "claims", "selected"})
        extras = {key: value for key, value in copy.items() if key not in contract_fields}
        if not (
            copy.get("claims") in (None, [])
            and copy.get("selected") in (None, True)
            and not any(value not in (None, []) for value in extras.values())
            and isinstance(wrapper, str) and wrapper == wrapper.strip()
            and 40 <= len(wrapper) <= (120 if external else 220)
            and not URL.search(wrapper)
            and "\n" not in wrapper and "\r" not in wrapper
        ):
            raise ValueError("quote distribution copy invalid")
        if external:
            if candidates_path is None:
                raise ValueError("external quote candidates unavailable")
            candidates = read_json(candidates_path).get("candidates")
            allowed = {
                row.get("url") for row in candidates or []
                if isinstance(row, dict) and isinstance(row.get("url"), str)
            }
            if copy.get("source_url") not in allowed:
                raise ValueError("external quote source is not a harvested candidate")
            text = (
                f"{wrapper}\n\nAffiliate disclosure: I may earn a commission through this link.\n"
                f"{job['owned_article_url']}"
            )
            source_url = copy["source_url"]
        else:
            text = wrapper
            source_url = job["control_post_url"]
    else:
        text = post_text({
            "receipt_type": "AFFILIATE_REPOST_PROPOSAL",
            "state": "READY_FOR_EXISTING_REPOST_OWNER",
            "proposal_id": job["job_id"],
            "placement_id": job["placement_id"],
            "owned_article_url": job["owned_article_url"],
            "language": "en",
            "disclosure_required": True,
            "tracking_link_state": "NOT_INCLUDED",
            "revenue_credit_state": "NO_REVENUE_CREDIT",
        })
    urls = URL.findall(text)
    expected_urls = (
        [job["owned_article_url"]] if mode == "QUOTE_RELEVANT_EXTERNAL"
        else [] if quote_mode else [job["owned_article_url"]]
    )
    if (urls != expected_urls
            or "try.elevenlabs.io" in text.casefold()):
        raise ValueError("distribution payload contains an unsafe link")
    text_sha256 = hashlib.sha256(text.encode()).hexdigest()
    payloads_dir.mkdir(parents=True, exist_ok=True)
    expected = {
        "schema_version": 1,
        "receipt_type": "X_REPOST_DISTRIBUTION_PAYLOAD",
        "state": "PAYLOAD_READY",
        "job_id": job["job_id"],
        "effect_identity": job["effect_identity"],
        "placement_id": job["placement_id"],
        "target_x_account": job["target_x_account"],
        "owned_article_url": job["owned_article_url"],
        "content_sha256": job["content_sha256"],
        "text": text,
        "text_sha256": text_sha256,
        "weighted_length": len(URL.sub("x" * X_TRANSFORMED_URL_LENGTH, text)),
        "private_tracking_url_state": "NOT_INCLUDED",
    }
    if quote_mode:
        expected.update({
            "distribution_mode": mode,
            "source_url": source_url,
        })
    if path.is_file():
        prior = read_json(path)
        comparable = {key: value for key, value in prior.items() if key != "created_at"}
        if comparable != expected:
            raise ValueError("distribution payload conflicts with existing receipt")
        return {**prior, "changed": False}
    receipt = {**expected, "created_at": datetime.now(timezone.utc).isoformat()}
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return {**receipt, "changed": True}


def distribution_payload(claims_path: Path, payloads_dir: Path) -> dict:
    claims = distribution_claims(claims_path)
    if not claims:
        raise ValueError("distribution job claim unavailable")
    job = claims[-1]["job"]
    revised_path = payloads_dir / f"{job['job_id']}-r1.json"
    payload = read_json(
        revised_path if revised_path.is_file() else payloads_dir / f"{job['job_id']}.json"
    )
    text = payload.get("text")
    urls = URL.findall(text) if isinstance(text, str) else []
    comparable = {
        "schema_version": 1,
        "receipt_type": "X_REPOST_DISTRIBUTION_PAYLOAD",
        "state": "PAYLOAD_READY",
        "job_id": job["job_id"],
        "effect_identity": job["effect_identity"],
        "placement_id": job["placement_id"],
        "target_x_account": job["target_x_account"],
        "owned_article_url": job["owned_article_url"],
        "content_sha256": job["content_sha256"],
        "text": text,
        "text_sha256": hashlib.sha256((text or "").encode()).hexdigest(),
        "weighted_length": len(URL.sub("x" * X_TRANSFORMED_URL_LENGTH, text or "")),
        "private_tracking_url_state": "NOT_INCLUDED",
    }
    mode = job.get("distribution_mode")
    quote_mode = mode in {"QUOTE_CONTROL_POST", "QUOTE_RELEVANT_EXTERNAL"}
    if quote_mode:
        source_url = (
            payload.get("source_url") if mode == "QUOTE_RELEVANT_EXTERNAL"
            else job["control_post_url"]
        )
        comparable.update({
            "distribution_mode": mode,
            "source_url": source_url,
        })
    revision = payload.get("revision", 0)
    revision_reason = payload.get("revision_reason")
    if revision == 1:
        comparable.update({
            "revision": 1,
            "prior_text_sha256": payload.get("prior_text_sha256"),
            "revision_reason": revision_reason,
        })
    if (
        revision not in {0, 1}
        or (revision == 1 and revision_reason not in REVISION_REASONS)
        or {key: value for key, value in payload.items() if key != "created_at"} != comparable
        or not isinstance(payload.get("created_at"), str)
        or urls != (
            [job["owned_article_url"]] if mode == "QUOTE_RELEVANT_EXTERNAL"
            else [] if quote_mode else [job["owned_article_url"]]
        )
        or (mode == "QUOTE_RELEVANT_EXTERNAL" and not (
            isinstance(payload.get("source_url"), str)
            and re.fullmatch(
                r"https://x\.com/[A-Za-z0-9_]{1,15}/status/[0-9]+",
                payload["source_url"],
            )
        ))
        or "try.elevenlabs.io" in (text or "").casefold()
        or comparable["weighted_length"] > 280
    ):
        raise ValueError("distribution payload invalid")
    return payload


def revise_payload_for_raw_limit(
    claims_path: Path, payloads_dir: Path, results_path: Path,
    copy_path: Path | None = None,
) -> dict:
    current = distribution_payload(claims_path, payloads_dir)
    results = [row for row in distribution_results(results_path)
               if row.get("job_id") == current["job_id"]]
    retry_count = sum(row.get("state") == "RETRY_READY" for row in results)
    if not results or results[-1].get("state") != "NO_EFFECT":
        raise ValueError("distribution payload revision requires confirmed no-effect")
    if current.get("revision") == 1:
        return {**current, "changed": False}
    revision_reason = "POSTIZ_RAW_LENGTH" if len(current["text"]) > 280 else "CONFIRMED_NO_EFFECT"
    subject_candidates = (
        "Check whether this AI tool fits your workflow, limits, and budget before subscribing.",
        "Compare workflow fit, limits, and total price before subscribing.",
    )
    mode = current.get("distribution_mode")
    if copy_path is not None:
        copy = read_json(copy_path)
        candidate = copy.get("text")
        extras = {key: value for key, value in copy.items() if key not in {"text", "claims"}}
        if copy.get("claims") not in (None, []) or any(value not in (None, []) for value in extras.values()):
            raise ValueError("model revision contract invalid")
        text_candidates = (candidate,)
    elif mode == "QUOTE_CONTROL_POST":
        text_candidates = subject_candidates
    else:
        text_candidates = tuple(
            f"{subject}\n\nAffiliate disclosure: I may earn a commission through this link.\n"
            f"{current['owned_article_url']}"
            for subject in subject_candidates
        )
    path = payloads_dir / f"{current['job_id']}-r1.json"
    expected_urls = (
        [] if mode == "QUOTE_CONTROL_POST" else [current["owned_article_url"]]
    )
    disclosure = "Affiliate disclosure: I may earn a commission through this link."
    for text in text_candidates:
        text_sha256 = hashlib.sha256(text.encode()).hexdigest()
        if text_sha256 == current["text_sha256"]:
            continue
        weighted_length = len(URL.sub("x" * X_TRANSFORMED_URL_LENGTH, text))
        if (not isinstance(text, str) or text != text.strip() or len(text) > 280
                or URL.findall(text) != expected_urls or weighted_length > 280):
            continue
        if mode != "QUOTE_CONTROL_POST" and text.count(disclosure) != 1:
            continue
        if mode == "QUOTE_CONTROL_POST" and disclosure in text:
            continue
        receipt = {
            **{key: value for key, value in current.items()
               if key not in {"text", "text_sha256", "weighted_length", "created_at"}},
            "text": text,
            "text_sha256": text_sha256,
            "weighted_length": weighted_length,
            "revision": 1,
            "prior_text_sha256": current["text_sha256"],
            "revision_reason": revision_reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with tempfile.TemporaryDirectory(dir=payloads_dir) as directory:
            temporary_dir = Path(directory)
            temporary = temporary_dir / path.name
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(receipt, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            try:
                validated = distribution_payload(claims_path, temporary_dir)
            except ValueError:
                continue
            os.replace(temporary, path)
            return {**validated, "changed": True}
    raise ValueError("revised distribution payload remains invalid")


def valid_distribution_result(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("state") == "RETRY_READY":
        hashes = (
            "job_id", "effect_identity", "content_sha256", "text_sha256",
            "prior_result_sha256",
        )
        return all((
            row.get("schema_version") == 1,
            row.get("receipt_type") == "X_REPOST_DISTRIBUTION_JOB_RETRY",
            all(isinstance(row.get(key), str) and PROPOSAL_ID.fullmatch(row[key])
                for key in hashes),
            isinstance(row.get("placement_id"), str)
            and PLACEMENT_ID.fullmatch(row["placement_id"]),
            (row.get("retry_number"), row.get("reason")) in {
                (1, "CONFIRMED_NO_EFFECT"),
                (2, "PAYLOAD_REVISED_AFTER_CONFIRMED_NO_EFFECT"),
            },
            row.get("owner_label") == "ai.anicca.x-repost-pass",
            isinstance(row.get("observed_at"), str),
        ))
    if row.get("state") not in {"POSTED", "UNVERIFIED", "NO_EFFECT"}:
        return False
    hashes = ("job_id", "effect_identity", "content_sha256", "text_sha256")
    if any(not isinstance(row.get(key), str) or not PROPOSAL_ID.fullmatch(row[key])
           for key in hashes):
        return False
    if row["state"] == "POSTED":
        try:
            parsed = urlparse(row.get("post_url"))
        except (TypeError, ValueError):
            return False
        if not (
            parsed.scheme == "https" and parsed.hostname == "x.com"
            and not parsed.username and not parsed.password and parsed.port is None
            and not parsed.query and not parsed.fragment
            and re.fullmatch(r"/[A-Za-z0-9_]+/status/[0-9]+", parsed.path)
            and isinstance(row.get("provider_submission_id"), str)
            and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", row["provider_submission_id"]))
        ):
            return False
    elif row.get("post_url") is not None:
        return False
    return all((
        row.get("schema_version") == 1,
        row.get("receipt_type") == "X_REPOST_DISTRIBUTION_JOB_RESULT",
        isinstance(row.get("placement_id"), str) and PLACEMENT_ID.fullmatch(row["placement_id"]),
        row.get("owner_label") == "ai.anicca.x-repost-pass",
        row.get("provider") == "postiz",
        isinstance(row.get("observed_at"), str),
    ))


def distribution_results(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                  if line.strip()]
    except (OSError, ValueError) as error:
        raise ValueError("distribution result ledger invalid") from error
    if any(not valid_distribution_result(row) for row in values):
        raise ValueError("distribution result ledger invalid")
    return values


def distribution_effect_state(claims_path: Path, payloads_dir: Path, results_path: Path) -> dict:
    payload = distribution_payload(claims_path, payloads_dir)
    results = [row for row in distribution_results(results_path)
               if row.get("job_id") == payload["job_id"]]
    if results:
        if results[-1]["state"] == "RETRY_READY":
            return {"state": "READY_TO_POST", "job_id": payload["job_id"],
                    "payload": payload, "retry_number": results[-1]["retry_number"],
                    "changed": False}
        return {**results[-1], "payload": payload,
                "retry_count": sum(row.get("state") == "RETRY_READY" for row in results),
                "changed": False}
    return {"state": "READY_TO_POST", "job_id": payload["job_id"],
            "payload": payload, "changed": False}


def record_distribution_result(
    claims_path: Path, payloads_dir: Path, results_path: Path,
    state: str, post_url: str | None, provider_submission_id: str | None,
) -> dict:
    if state not in {"POSTED", "UNVERIFIED", "NO_EFFECT"}:
        raise ValueError("invalid distribution result state")
    payload = distribution_payload(claims_path, payloads_dir)
    row = {
        "schema_version": 1,
        "receipt_type": "X_REPOST_DISTRIBUTION_JOB_RESULT",
        "state": state,
        "job_id": payload["job_id"],
        "effect_identity": payload["effect_identity"],
        "placement_id": payload["placement_id"],
        "content_sha256": payload["content_sha256"],
        "text_sha256": payload["text_sha256"],
        "post_url": post_url if state == "POSTED" else None,
        "provider": "postiz",
        "provider_submission_id": provider_submission_id,
        "owner_label": "ai.anicca.x-repost-pass",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    if not valid_distribution_result(row):
        raise ValueError("invalid distribution result")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        all_existing = [json.loads(line) for line in stream if line.strip()]
        if all_existing:
            if any(not valid_distribution_result(value) for value in all_existing):
                raise ValueError("distribution result ledger invalid")
            existing = [value for value in all_existing
                        if value.get("job_id") == payload["job_id"]]
        else:
            existing = []
        if existing:
            prior = existing[-1]
            if prior["state"] != "RETRY_READY":
                if (
                    prior["state"] == "UNVERIFIED"
                    and state == "POSTED"
                    and prior.get("provider_submission_id") == provider_submission_id
                    and all(prior.get(key) == row.get(key) for key in (
                        "job_id", "effect_identity", "placement_id",
                        "content_sha256", "text_sha256", "provider",
                    ))
                ):
                    pass
                else:
                    comparable = {key: value for key, value in prior.items() if key != "observed_at"}
                    expected = {key: value for key, value in row.items() if key != "observed_at"}
                    if comparable != expected:
                        raise ValueError("distribution result conflicts with terminal receipt")
                    return {**prior, "changed": False}
        stream.seek(0, os.SEEK_END)
        stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {**row, "changed": True}


def requeue_confirmed_no_effect(
    results_path: Path, job_id: str, text_sha256: str | None = None,
) -> dict:
    if not isinstance(job_id, str) or not PROPOSAL_ID.fullmatch(job_id):
        raise ValueError("invalid distribution job identity")
    with results_path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        try:
            values = [json.loads(line) for line in stream if line.strip()]
        except ValueError as error:
            raise ValueError("distribution result ledger invalid") from error
        if not values or any(not valid_distribution_result(row) for row in values):
            raise ValueError("distribution result ledger invalid")
        latest = values[-1]
        if latest.get("job_id") != job_id:
            raise ValueError("distribution retry job mismatch")
        if latest["state"] == "RETRY_READY":
            return {**latest, "changed": False}
        if latest["state"] != "NO_EFFECT":
            raise ValueError("distribution result is not safely retryable")
        retry_number = sum(
            row.get("state") == "RETRY_READY" and row.get("job_id") == job_id
            for row in values
        ) + 1
        if retry_number > 2:
            raise ValueError("distribution retry limit reached")
        next_text_sha256 = text_sha256 or latest["text_sha256"]
        if not isinstance(next_text_sha256, str) or not PROPOSAL_ID.fullmatch(next_text_sha256):
            raise ValueError("invalid distribution retry text identity")
        retry = {
            "schema_version": 1,
            "receipt_type": "X_REPOST_DISTRIBUTION_JOB_RETRY",
            "state": "RETRY_READY",
            "job_id": latest["job_id"],
            "effect_identity": latest["effect_identity"],
            "placement_id": latest["placement_id"],
            "content_sha256": latest["content_sha256"],
            "text_sha256": next_text_sha256,
            "prior_result_sha256": hashlib.sha256(json.dumps(
                latest, sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest(),
            "reason": (
                "CONFIRMED_NO_EFFECT" if retry_number == 1
                else "PAYLOAD_REVISED_AFTER_CONFIRMED_NO_EFFECT"
            ),
            "retry_number": retry_number,
            "owner_label": "ai.anicca.x-repost-pass",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        stream.seek(0, os.SEEK_END)
        stream.write(json.dumps(retry, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        return {**retry, "changed": True}


def post_text(proposal: dict) -> str:
    proposal = canonical(proposal)
    url = proposal["owned_article_url"]
    disclosure = "Affiliate disclosure: I may earn a commission if you subscribe through this link."
    intent = " ".join((proposal.get("buyer_intent") or "").split())
    title = " ".join((proposal.get("article_title") or "").split())
    match = re.fullmatch(r"Creators evaluating (.+?) before paying", intent, re.I)
    product = match.group(1).strip() if match else ""
    if not product:
        product = re.sub(r"^(?:Is|How to Evaluate)\s+", "", title, flags=re.I)
        product = re.split(r"(?:\?|:|\s+(?:a|the)\s+(?:right\s+)?fit\b|\s+before\b)", product,
                           maxsplit=1, flags=re.I)[0].strip()

    # Never slice prose to fit. The old renderer cut both the hook and title in the middle of
    # words, producing visibly broken public posts. Try complete-sentence variants and fall back
    # to a truthful generic noun when a provider-supplied product label is unusually long.
    for subject in (product, "this AI tool"):
        if not subject:
            continue
        text = (
            f"Considering {subject}? Check workflow fit, limits, and total price before you "
            f"subscribe. Use this decision checklist to compare the trade-offs.\n\n"
            f"{disclosure}\n{url}"
        )
        # Match twitter/twitter-text v3: each extracted URL contributes the
        # transformed URL length (23), not its raw display length.
        weighted_length = len(URL.sub("x" * X_TRANSFORMED_URL_LENGTH, text))
        if weighted_length <= 280:
            return text
    raise ValueError("affiliate proposal copy exceeds X limit")


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError("consumption ledger unavailable") from error
    values = []
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError as error:
            raise ValueError("consumption ledger invalid") from error
        if not isinstance(value, dict):
            raise ValueError("consumption ledger invalid")
        if (
            value.get("schema_version") != 1
            or value.get("receipt_type") != "X_REPOST_AFFILIATE_PROPOSAL_CONSUMPTION"
            or not isinstance(value.get("proposal_id"), str)
            or not PROPOSAL_ID.fullmatch(value["proposal_id"])
            or not isinstance(value.get("placement_id"), str)
            or not PLACEMENT_ID.fullmatch(value["placement_id"])
            or value.get("state") not in CONSUMPTION_STATES
            or not isinstance(value.get("observed_at"), str)
        ):
            raise ValueError("consumption ledger invalid")
        try:
            observed = datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00"))
            if observed.tzinfo is None:
                raise ValueError
        except ValueError as error:
            raise ValueError("consumption ledger invalid") from error
        values.append(value)
    return values


def select(proposal_path: Path, consumed_path: Path, posted_path: Path | None = None) -> dict:
    try:
        all_rows = rows(consumed_path)
    except ValueError:
        return {"state": "BLOCKED_CONSUMPTION_LEDGER"}
    latest_by_proposal = {}
    for row in all_rows:
        proposal_id = row.get("proposal_id")
        if isinstance(proposal_id, str):
            latest_by_proposal[proposal_id] = row
    posted_ids = set()
    if posted_path is not None and posted_path.exists():
        try:
            for line in posted_path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                proposal_id = row.get("affiliate_proposal_id")
                if isinstance(proposal_id, str):
                    posted_ids.add(proposal_id)
        except (OSError, ValueError, AttributeError):
            return {"state": "BLOCKED_CONSUMPTION_LEDGER"}
    legacy = [row for row in latest_by_proposal.values()
              if row.get("state") == "EFFECT_STARTED" and not valid(row.get("proposal"))]
    if legacy:
        return {"state": "BLOCKED_LEGACY_CLAIM"}
    unresolved = [row for row in latest_by_proposal.values()
                  if row.get("state") == "EFFECT_STARTED"]
    if unresolved:
        pending = min(unresolved, key=lambda row: row.get("observed_at", ""))
        snapshot = pending["proposal"]
        return {
            "state": "RECONCILE",
            "proposal": canonical(snapshot),
            "proposal_id": snapshot["proposal_id"],
            "placement_id": snapshot["placement_id"],
            "owned_article_url": snapshot["owned_article_url"],
            "language": "en",
        }
    try:
        proposal = read_json(proposal_path)
    except ValueError:
        proposal = None
    if proposal is not None and not valid(proposal):
        return {"state": "INVALID_PROPOSAL"}
    prior = [row for row in all_rows
             if proposal is not None and row.get("proposal_id") == proposal["proposal_id"]]
    if proposal is not None and not prior:
        return {
            "state": "READY",
            "proposal": canonical(proposal),
            "proposal_id": proposal["proposal_id"],
            "placement_id": proposal["placement_id"],
            "owned_article_url": proposal["owned_article_url"],
            "language": "en",
        }
    recoverable = []
    now = datetime.now(timezone.utc)
    for proposal_id, terminal in latest_by_proposal.items():
        if terminal.get("state") != "UNVERIFIED" or proposal_id in posted_ids:
            continue
        terminal_at = datetime.fromisoformat(terminal["observed_at"].replace("Z", "+00:00"))
        if now - terminal_at.astimezone(timezone.utc) > UNVERIFIED_RECOVERY_WINDOW:
            continue
        claim_row = next((row for row in reversed(all_rows)
                          if row.get("proposal_id") == proposal_id
                          and row.get("state") == "EFFECT_STARTED"
                          and valid(row.get("proposal"))), None)
        if claim_row:
            recoverable.append(claim_row)
    if recoverable:
        pending = max(recoverable, key=lambda row: row.get("observed_at", ""))
        snapshot = pending["proposal"]
        return {
            "state": "VERIFY_UNVERIFIED",
            "proposal": canonical(snapshot),
            "proposal_id": snapshot["proposal_id"],
            "placement_id": snapshot["placement_id"],
            "owned_article_url": snapshot["owned_article_url"],
            "language": "en",
        }
    if proposal is None:
        return {"state": "NO_PROPOSAL"}
    if any(row.get("state") in {"POSTED", "UNVERIFIED", "NO_EFFECT"} for row in prior):
        return {"state": "ALREADY_CONSUMED", "proposal_id": proposal["proposal_id"]}
    if any(row.get("state") == "EFFECT_STARTED" for row in prior):
        return {
            "state": "RECONCILE",
            "proposal_id": proposal["proposal_id"],
            "placement_id": proposal["placement_id"],
            "owned_article_url": proposal["owned_article_url"],
            "language": "en",
        }
    return {"state": "BLOCKED_CONSUMPTION_LEDGER"}


def _append_once(consumed_path: Path, proposal_id: str, row: dict, *, require_claim: bool) -> dict:
    consumed_path.parent.mkdir(parents=True, exist_ok=True)
    with consumed_path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        prior = []
        for line in stream:
            try:
                value = json.loads(line)
            except ValueError as error:
                raise ValueError("consumption ledger invalid") from error
            if not isinstance(value, dict):
                raise ValueError("consumption ledger invalid")
            if value.get("proposal_id") == proposal_id:
                prior.append(value)
        terminal = next((value for value in reversed(prior)
                         if value.get("state") in {"POSTED", "UNVERIFIED", "NO_EFFECT"}), None)
        if terminal is not None:
            return {**terminal, "changed": False}
        if require_claim and not any(value.get("state") == "EFFECT_STARTED" for value in prior):
            raise ValueError("proposal was not claimed")
        if not require_claim and prior:
            return {**prior[-1], "changed": False}
        stream.seek(0, os.SEEK_END)
        stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {**row, "changed": True}


def claim(consumed_path: Path, proposal: dict) -> dict:
    if not valid(proposal):
        raise ValueError("invalid proposal")
    row = {
        "schema_version": 1,
        "receipt_type": "X_REPOST_AFFILIATE_PROPOSAL_CONSUMPTION",
        "proposal_id": proposal["proposal_id"],
        "placement_id": proposal["placement_id"],
        "state": "EFFECT_STARTED",
        "proposal": canonical(proposal),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "revenue_credit_state": "NO_REVENUE_CREDIT_UNTIL_EXACT_AFFILIATE_JOIN",
    }
    return _append_once(consumed_path, proposal["proposal_id"], row, require_claim=False)


def record(consumed_path: Path, proposal: dict, state: str, post_url: str | None) -> dict:
    if state not in {"POSTED", "UNVERIFIED", "NO_EFFECT"}:
        raise ValueError("invalid consumption state")
    if not valid(proposal):
        raise ValueError("invalid proposal")
    if state == "POSTED":
        if not isinstance(post_url, str) or any(char.isspace() or ord(char) < 32 for char in post_url):
            raise ValueError("invalid published X URL")
        try:
            parsed = urlparse(post_url)
            port = parsed.port
        except ValueError:
            raise ValueError("invalid published X URL")
        if not (
            parsed.scheme == "https" and parsed.hostname == "x.com"
            and not parsed.username and not parsed.password and port is None
            and not parsed.query and not parsed.fragment
            and re.fullmatch(r"/[A-Za-z0-9_]+/status/[0-9]+", parsed.path)
        ):
            raise ValueError("invalid published X URL")
    row = {
        "schema_version": 1,
        "receipt_type": "X_REPOST_AFFILIATE_PROPOSAL_CONSUMPTION",
        "proposal_id": proposal["proposal_id"],
        "placement_id": proposal["placement_id"],
        "state": state,
        "post_url": post_url if state == "POSTED" else None,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "revenue_credit_state": "NO_REVENUE_CREDIT_UNTIL_EXACT_AFFILIATE_JOIN",
    }
    return _append_once(consumed_path, proposal["proposal_id"], row, require_claim=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--consumed", type=Path)
    parser.add_argument("--job-queue", type=Path)
    parser.add_argument("--job-claims", type=Path)
    parser.add_argument("--claim-next-job", action="store_true")
    parser.add_argument("--render-claimed-job", action="store_true")
    parser.add_argument("--job-payload-dir", type=Path)
    parser.add_argument("--job-copy", type=Path)
    parser.add_argument("--job-candidates", type=Path)
    parser.add_argument("--job-results", type=Path)
    parser.add_argument("--job-effect-state", action="store_true")
    parser.add_argument("--record-job-result", choices=("POSTED", "UNVERIFIED", "NO_EFFECT"))
    parser.add_argument("--requeue-no-effect", action="store_true")
    parser.add_argument("--job-id")
    parser.add_argument("--text-sha256")
    parser.add_argument("--revise-raw-limit", action="store_true")
    parser.add_argument("--revision-copy", type=Path)
    parser.add_argument("--posted", type=Path)
    parser.add_argument("--record", choices=("POSTED", "UNVERIFIED", "NO_EFFECT"))
    parser.add_argument("--claim", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--post-url")
    parser.add_argument("--provider-submission-id")
    args = parser.parse_args()
    if os.environ.get("X_REPOST_DISABLE_AFFILIATE") == "1" and (
        args.claim_next_job or args.render_claimed_job
        or (args.record_job_result is not None and args.record_job_result != "POSTED")
        or (args.record_job_result == "POSTED"
            and (not args.post_url or not args.provider_submission_id))
        or args.requeue_no_effect or args.revise_raw_limit or args.claim
        or args.record is not None
    ):
        print(json.dumps({"state": "AFFILIATE_DISABLED", "changed": False}, sort_keys=True))
        return 0
    if args.claim_next_job:
        if args.job_queue is None or args.job_claims is None:
            parser.error("--claim-next-job requires --job-queue and --job-claims")
        print(json.dumps(claim_next_job(
            args.job_queue, args.job_claims, args.job_results
        ), sort_keys=True))
        return 0
    if args.render_claimed_job:
        if args.job_claims is None or args.job_payload_dir is None:
            parser.error("--render-claimed-job requires --job-claims and --job-payload-dir")
        print(json.dumps(render_claimed_job(
            args.job_claims, args.job_payload_dir, args.job_copy, args.job_candidates
        ), sort_keys=True))
        return 0
    if args.job_effect_state:
        if args.job_claims is None or args.job_payload_dir is None or args.job_results is None:
            parser.error("--job-effect-state requires claim, payload, and result paths")
        print(json.dumps(distribution_effect_state(
            args.job_claims, args.job_payload_dir, args.job_results
        ), sort_keys=True))
        return 0
    if args.record_job_result:
        if args.job_claims is None or args.job_payload_dir is None or args.job_results is None:
            parser.error("--record-job-result requires claim, payload, and result paths")
        print(json.dumps(record_distribution_result(
            args.job_claims, args.job_payload_dir, args.job_results,
            args.record_job_result, args.post_url, args.provider_submission_id,
        ), sort_keys=True))
        return 0
    if args.requeue_no_effect:
        if args.job_results is None or args.job_id is None:
            parser.error("--requeue-no-effect requires --job-results and --job-id")
        print(json.dumps(requeue_confirmed_no_effect(
            args.job_results, args.job_id, args.text_sha256
        ), sort_keys=True))
        return 0
    if args.revise_raw_limit:
        if args.job_claims is None or args.job_payload_dir is None or args.job_results is None:
            parser.error("--revise-raw-limit requires claim, payload, and result paths")
        print(json.dumps(revise_payload_for_raw_limit(
            args.job_claims, args.job_payload_dir, args.job_results, args.revision_copy
        ), sort_keys=True))
        return 0
    if args.proposal is None or args.consumed is None:
        parser.error("legacy proposal mode requires --proposal and --consumed")
    if args.claim:
        print(json.dumps(claim(args.consumed, read_json(args.proposal)), sort_keys=True))
        return 0
    if args.render:
        print(post_text(read_json(args.proposal)), end="")
        return 0
    if not args.record:
        print(json.dumps(select(args.proposal, args.consumed, args.posted), sort_keys=True))
        return 0
    proposal = read_json(args.proposal)
    print(json.dumps(record(args.consumed, proposal, args.record, args.post_url), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"affiliate proposal: {error}", file=sys.stderr)
        raise SystemExit(2)
