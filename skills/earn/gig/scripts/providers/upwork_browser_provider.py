#!/usr/bin/env python3
"""Read authenticated Upwork zero-spend state through the existing CloakBrowser CDP helper."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from cdp_nav_snapshot import navigate_and_snapshot  # noqa: E402
from connector_outbox import ConnectorBusy, ConnectorOutbox  # noqa: E402
from market_form_operator import operate as operate_market_form  # noqa: E402
from project_workspace import WorkspaceError, create_workspace, load_workspace  # noqa: E402
from provider_authorization import DEFAULT_RECEIPT_PATH  # noqa: E402
import report_envelope  # noqa: E402
from upwork_inbound_planner import invoke as plan_inbound, invoke_batch as plan_batch, write_sealed_proposal  # noqa: E402
from upwork_offer_gate import invoke as qualify_direct_offer  # noqa: E402
from upwork_offer_browser import accept_offer_after_fence  # noqa: E402
from upwork_offer_effect import SealedUpworkOfferEffect  # noqa: E402
from upwork_inbox import append_changed_heads, normalize_observation  # noqa: E402
from upwork_negotiate import invoke as plan_negotiation  # noqa: E402
from upwork_message_browser import send_message_after_fence  # noqa: E402
from upwork_message_effect import SealedUpworkMessageEffect  # noqa: E402
from upwork_sealed_effect import (  # noqa: E402
    SealedUpworkProposalEffect, active_upwork_browser_account,
)
from upwork_platform_manifest import build_live_snapshot  # noqa: E402
from upwork_platform_manifest_runtime import (  # noqa: E402
    run_upwork_platform_manifest_wake,
)
from upwork_transport import UpworkTransport  # noqa: E402
from workflow_executor import general_agent_workflow  # noqa: E402
from work_event_projector import _read_jsonl  # noqa: E402


CONNECTS_URL = "https://www.upwork.com/nx/plans/connects/history"
INVITES_URL = "https://www.upwork.com/nx/find-work/invites"
PROPOSALS_URL = "https://www.upwork.com/nx/proposals/"
CATALOG_URL = "https://www.upwork.com/nx/project-dashboard/?step=approved"
CONTRACTS_URL = "https://www.upwork.com/nx/wm/freelancer/home"
MESSAGES_URL = "https://www.upwork.com/ab/messages/rooms"
TRANSACTIONS_URL = "https://www.upwork.com/nx/payments/reports/transaction-history"
WITHDRAWALS_URL = "https://www.upwork.com/nx/payments/disbursement-methods"
WORKING_STYLE_URL = "https://www.upwork.com/nx/skills-assesment/assessment-results"
SEARCH_URL = "https://www.upwork.com/nx/search/jobs/?q=AI%20automation&sort=recency"
DEFAULT_CANDIDATES = SCRIPTS.parent / "config" / "upwork-candidates.public.json"
DEFAULT_TRANSITIONS = Path.home() / "gig/state/upwork-free-transitions.jsonl"
DEFAULT_PROPOSALS = Path.home() / ".config/anicca/gig/upwork-proposals"
DEFAULT_DATABASE = Path.home() / "gig/connector-outbox.sqlite3"
DEFAULT_MANIFEST = SCRIPTS.parent / "config/connectors/coconala.json"
DEFAULT_BROWSER_IDENTITY = os.environ.get("LIFE_MANAGER_BROWSER_IDENTITY", "upwork:dais")
DEFAULT_BROWSER_REGISTRY = Path(
    os.environ.get("AI_BROWSER_REGISTRY", "~/.config/ai/registry/browsers.toml")
).expanduser()
DEFAULT_BROWSER_RESOLVER = Path(
    os.environ.get(
        "LIFE_MANAGER_BROWSER_RESOLVER",
        str(SCRIPTS.parents[2] / "browser" / "resolve_cdp_endpoint.py"),
    )
).expanduser()
DEFAULT_BROWSER_PROFILE = Path.home() / ".cloak/profiles/gig-upwork"
DEFAULT_INBOUND_DIR = Path.home() / ".config/anicca/gig/upwork-inbound"
DEFAULT_INBOUND_PROPOSALS = Path.home() / ".config/anicca/gig/upwork-inbound-proposals"
DEFAULT_INBOUND_EVIDENCE = Path.home() / "gig/state/upwork-inbound-planner"
DEFAULT_SEARCH_CURSOR = Path.home() / "gig/state/upwork-search-cursor.json"
DEFAULT_OFFER_EVIDENCE = Path.home() / "gig/state/upwork-offer-gate"
DEFAULT_INBOX_LEDGER = Path.home() / "gig/state/upwork-inbox.jsonl"
DEFAULT_NEGOTIATION_EVIDENCE = Path.home() / "gig/state/upwork-negotiation-planner"


def record_upwork_platform_manifest_wake(
    state: dict[str, Any],
    *,
    account_id: str,
    run_id: str,
    candidate_root: Path | None = None,
    run_root: Path | None = None,
) -> dict[str, Any]:
    """Record account/source health before any Upwork provider mutation."""

    adapter_source = Path(__file__).resolve().parents[1] / "upwork_platform_manifest.py"
    snapshot = build_live_snapshot(
        state,
        account_id=account_id,
        adapter_source_sha256=hashlib.sha256(adapter_source.read_bytes()).hexdigest(),
    )
    return run_upwork_platform_manifest_wake(
        snapshot=snapshot,
        candidate_root=candidate_root,
        run_root=run_root,
        run_id=run_id,
        observed_at=str(state["observed_at"]),
    )
DEFAULT_OWNER_PROFILE = Path.home() / ".config/anicca/gig/owner-profile.json"
DEFAULT_GIG_DIR = Path.home() / "gig"
DEFAULT_PROJECTS_ROOT = DEFAULT_GIG_DIR / "projects"
DEFAULT_PROJECT_WORKER = SCRIPTS / "project_worker.py"
DEFAULT_AGENT_RUNNER = SCRIPTS.parent.parents[2] / "runtime/agent-runner/agent_runner.py"
TERMINAL_JOB_STATUSES = {"closed", "removed"}
_COUNT_LABELS = {
    "offers": r"Offers\s*\((\d+)\)",
    "invites": r"Invites from clients\s*\((\d+)\)",
    "active_proposals": r"Active proposals?\s*\((\d+)\)",
    "submitted_proposals": r"Submitted proposals?\s*\((\d+)\)",
}
_CONNECTS_REQUIRED = re.compile(
    r"Send a proposal for:\s*(\d+)\s+Connects|"
    r"Required Connects to submit a proposal:\s*(\d+)",
    re.IGNORECASE,
)


def resolve_browser_identity(
    identity: str,
    *,
    registry: Path = DEFAULT_BROWSER_REGISTRY,
    resolver: Path = DEFAULT_BROWSER_RESOLVER,
) -> dict[str, str]:
    """Resolve one registered, profile-owned Upwork browser endpoint.

    A numeric CDP port or a caller-provided profile is not an identity.  The
    resolver verifies the registry row, live HTTP endpoint, websocket shape,
    and owning process before this provider is allowed to attach.
    """
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("upwork_browser_identity_invalid")
    command = [
        sys.executable, str(resolver.expanduser()),
        "--registry", str(registry.expanduser()), "--identity", identity,
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=10,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        raise ValueError("upwork_browser_identity_unavailable") from None
    if (
        result.returncode != 0
        or not isinstance(payload, dict)
        or payload.get("identity") != identity
        or payload.get("reachable") is not True
        or payload.get("http_status") != 200
        or payload.get("websocket_url_valid") is not True
        or not isinstance(payload.get("endpoint"), str)
        or not payload["endpoint"].startswith(("http://127.0.0.1:", "http://[::1]:"))
        or not isinstance(payload.get("profile"), str)
        or not payload["profile"].startswith("/")
    ):
        raise ValueError("upwork_browser_identity_unavailable")
    return {
        "identity": identity,
        "profile": payload["profile"],
        "endpoint": payload["endpoint"],
    }


def publish_application_decisions(events: list[dict[str, Any]]) -> None:
    """Persist provider-neutral WorkEvents; observers own optional notifications."""
    for event in events:
        report_envelope.append_work_event(DEFAULT_GIG_DIR / "work-events.jsonl", event)


def load_terminal_upwork_application_ids(path: Path) -> set[str]:
    return {
        event["entity_id"]
        for event in _read_jsonl(path)
        if (
            event.get("kind") == "application"
            and event.get("state") == "skipped"
            and isinstance(event.get("attributes"), dict)
            and event["attributes"].get("platform") == "upwork"
            and event["attributes"].get("terminal") is True
            and isinstance(event.get("entity_id"), str)
            and event["entity_id"]
        )
    }


def proposal_submitted_event(
    payload: dict[str, Any], *, proposal_id: str, connects_before: int,
    connects_after: int,
) -> dict[str, Any]:
    terms = payload["terms"]
    return {
        "event_key": f"gig:application:upwork:{proposal_id}",
        "kind": "application",
        "entity_id": payload["job_id"],
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "state": "verified",
        "action": "応募送信",
        "result": "公式Proposal IDとConnects差分を確認しました",
        "next_action": "返信、Offer、契約を自動で監視します",
        "evidence": ["proposal_id", "connects_readback", "provider_effect_ledger"],
        "attributes": {
            "platform": "upwork", "title": payload["title"], "url": payload["job_url"],
            "job_id": payload["job_id"], "proposal_id": proposal_id,
            "connects_before": connects_before, "connects_after": connects_after,
            "connects_spent": connects_before - connects_after,
            "quote": {"currency": "USD", "amount": terms["bid_usd"], "unit": terms["type"]},
        },
    }


def parse_connects(text: str) -> dict[str, Any]:
    match = re.search(r"My balance\s+(\d+)\s+Connects\b", text or "", re.IGNORECASE)
    if match is None:
        raise ValueError("upwork_readback_incomplete")
    return {
        "balance": int(match.group(1)),
        "transactions_empty": "No Connects transactions." in text,
    }


def parse_inventory(text: str, working_style_text: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field, pattern in _COUNT_LABELS.items():
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match is None:
            raise ValueError("upwork_readback_incomplete")
        result[field] = int(match.group(1))
    strengths = [
        label for label in ("Accountable for outcomes", "Detail-oriented")
        if label.casefold() in working_style_text.casefold()
    ]
    working_style_complete = (
        "working style assessment results" in working_style_text.casefold()
        and working_style_text.casefold().count("shown on profile") >= 2
        and len(strengths) == 2
    )
    tasks: list[str] = []
    if (
        re.search(r"Take the working style assessment", text, re.IGNORECASE)
        and not working_style_complete
    ):
        tasks.append("working_style_assessment")
    result["account_tasks"] = tasks
    result["working_style"] = {
        "completed": working_style_complete,
        "strengths": strengths,
    }
    return result


def parse_catalog(text: str) -> dict[str, Any]:
    normalized = (text or "").casefold()
    if all(marker in normalized for marker in (
        "upwork", "sorry, we can't let you in", "error 403",
    )):
        return {
            "catalog_readback_state": "forbidden",
            "catalog_approved": None,
            "catalog_under_review": None,
            "catalog_drafts": None,
            "catalog_projects": [],
        }
    result: dict[str, Any] = {}
    for field, label in (
        ("catalog_approved", "Approved"),
        ("catalog_under_review", "Under Review"),
        ("catalog_drafts", "Drafts"),
    ):
        match = re.search(rf"{label}\s*\((\d+)\)", text or "", re.IGNORECASE)
        if match is None:
            raise ValueError("upwork_readback_incomplete")
        result[field] = int(match.group(1))
    projects = []
    for match in re.finditer(
        r"Visible\s+([^\n]+)\s+(\d+)\s+(\d+)\s+More Project Options",
        text or "", re.IGNORECASE,
    ):
        projects.append({
            "title": match.group(1).strip(),
            "visible": True,
            "views_30d": int(match.group(2)),
            "orders": int(match.group(3)),
        })
    if not projects:
        for match in re.finditer(
            r"(?m)^(?P<title>[^\n]+?)\s*\n\s*More Project Options\b",
            text or "", re.IGNORECASE,
        ):
            title = match.group("title").strip()
            if title:
                projects.append({
                    "title": title,
                    "visible": True,
                    "views_30d": None,
                    "orders": None,
                })
    if result["catalog_approved"] and not projects:
        raise ValueError("upwork_readback_incomplete")
    result["catalog_projects"] = projects
    return result


def _stable_link(link: dict[str, Any]) -> dict[str, str] | None:
    href = str(link.get("href") or "")
    parsed = urlsplit(href)
    if parsed.path.startswith("/nx/proposals/interview"):
        match = re.fullmatch(r"/nx/proposals/interview/uid/(\d+)", parsed.path)
        if (
            match is None
            or parsed.scheme != "https"
            or parsed.netloc != "www.upwork.com"
        ):
            return None
        return {
            "id": match.group(1),
            "href": f"https://www.upwork.com{parsed.path}",
            "title": str(link.get("text") or "").strip(),
        }
    match = re.search(r"/jobs/[^/?#]*(~[A-Za-z0-9]+)(?:[/?#]|$)", href)
    if match is None:
        match = re.search(
            r"/(?:proposals|workroom|rooms)/([^/?#]+)(?:[/?#]|$)", href,
        )
    if match is None or match.group(1).lower() in {"archived", "referrals"}:
        return None
    return {
        "id": match.group(1),
        "href": href.split("?", 1)[0],
        "title": str(link.get("text") or "").strip(),
    }


def _dedupe_links(links: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for link in links:
        entity = _stable_link(link)
        if entity is None:
            continue
        key = (entity["id"], entity["href"])
        if key not in seen:
            seen.add(key)
            result.append(entity)
    return result


def parse_stable_entities(
    *, invite_links: list[dict[str, Any]], proposal_links: list[dict[str, Any]],
) -> dict[str, Any]:
    invitations = _dedupe_links(invite_links)
    offers: list[dict[str, str]] = []
    active: list[dict[str, str]] = []
    submitted: list[dict[str, str]] = []
    unknown: list[dict[str, str]] = []
    for link in proposal_links:
        entity = _stable_link(link)
        if entity is None:
            continue
        context = " ".join(str(link.get(key) or "") for key in (
            "context", "text", "aria", "data_qa", "class_name",
        )).lower()
        if re.fullmatch(
            r"https://www\.upwork\.com/nx/proposals/interview/uid/\d+",
            entity["href"],
        ):
            target = invitations
        elif "offer" in context:
            target = offers
        elif "submitted" in context or "initiated" in context:
            target = submitted
        elif entity["id"].isdigit() and "received" in context:
            target = active
        elif "active" in context:
            target = active
        else:
            target = unknown
        if entity not in target:
            target.append(entity)
    return {
        "invitation_entities": invitations,
        "proposal_offer_entities": offers,
        "active_proposal_entities": active,
        "submitted_proposal_entities": submitted,
        "unclassified_proposal_entities": unknown,
    }


def parse_contracts(text: str, links: list[dict[str, Any]]) -> dict[str, Any]:
    match = re.search(r"Earnings available now:\s*\$([\d,]+\.\d{2})", text or "")
    if match is None:
        raise ValueError("upwork_readback_incomplete")
    contracts = [
        item for item in _dedupe_links(links)
        if "/workroom/" in item["href"] or "contract" in item["href"].lower()
    ]
    if "There are no active contracts." not in text and not contracts:
        raise ValueError("upwork_readback_incomplete")
    return {
        "earnings_available_usd_minor": int(
            Decimal(match.group(1).replace(",", "")) * 100
        ),
        "active_contracts": contracts,
    }


def parse_payment_observer(transactions: str, withdrawals: str) -> dict[str, Any]:
    def amount_after(label: str, text: str) -> int:
        match = re.search(rf"{label}\s*\n[+]?\$([\d,]+\.\d{{2}})", text, re.IGNORECASE)
        if match is None:
            raise ValueError("upwork_readback_incomplete")
        return int(Decimal(match.group(1).replace(",", "")) * 100)

    available = amount_after("Available balance", transactions)
    pending = amount_after("Pending earnings", transactions)
    exception = re.search(r"(?:^|\n)(?:Refund|Chargeback|Reversed)(?:\n|$)", transactions, re.I)
    state = "exception" if exception else "pending" if pending else "payout_available" if available else "clear"
    tax_complete = False if re.search(
        r"Complete your tax profile|update your tax information", withdrawals, re.I,
    ) else None
    method_configured = False if re.search(
        r"haven.t set up any withdrawal methods", withdrawals, re.I,
    ) else None
    return {
        "state": state, "priority": 2, "owner": "upwork-payment-observer",
        "next_check": "next_wake", "available_usd_minor": available,
        "pending_usd_minor": pending, "tax_profile_complete": tax_complete,
        "withdrawal_method_configured": method_configured,
        "recognized_revenue_usd_minor": None,
    }


def parse_messages(text: str, links: list[dict[str, Any]]) -> dict[str, Any]:
    rooms = [
        item for item in _dedupe_links(links)
        if "/ab/messages/rooms/" in item["href"]
    ]
    if not any(marker in text for marker in (
        "Conversations will appear here", "Welcome to Messages",
        "Once you connect with a client",
    )) and not rooms:
        raise ValueError("upwork_readback_incomplete")
    unread = []
    for link in links:
        entity = _stable_link(link)
        marker = " ".join(str(link.get(key) or "") for key in (
            "context", "aria", "data_qa", "class_name",
        )).lower()
        if entity and "/ab/messages/rooms/" in entity["href"] and "unread" in marker:
            unread.append(entity["id"])
    return {"message_rooms": rooms, "unread_message_room_ids": sorted(set(unread))}


def prioritize_message_rooms(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    unread = set(inventory["unread_message_room_ids"])
    return sorted(inventory["message_rooms"], key=lambda room: room["id"] not in unread)


def load_candidates(path: Path) -> list[dict[str, str]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    candidates = value.get("candidates") if isinstance(value, dict) else None
    if not isinstance(candidates, list):
        raise ValueError("upwork_candidate_config_invalid")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError("upwork_candidate_config_invalid")
        job_id = str(item.get("job_id") or "")
        job_url = str(item.get("job_url") or "")
        if not re.fullmatch(r"~\d{15,}", job_id) or job_id not in job_url or job_id in seen:
            raise ValueError("upwork_candidate_config_invalid")
        seen.add(job_id)
        candidate = {key: str(item.get(key) or "") for key in (
            "job_id", "job_url", "queue", "title", "proposal_payload_sha256",
        )}
        if candidate["queue"] == "ready" and not re.fullmatch(
            r"[0-9a-f]{64}", candidate["proposal_payload_sha256"],
        ):
            raise ValueError("upwork_candidate_config_invalid")
        result.append(candidate)
    return result


_SEALED_PROPOSAL_KEYS = {
    "attachments", "cover_letter", "job_id", "job_source_sha256", "job_url",
    "payload_sha256", "provider", "screening_answers", "status", "terms",
    "title", "unsupported_claims",
}
_SEALED_TERMS_KEYS = {
    "type", "bid_usd", "delivery_days", "required_connects",
    "available_connects_before",
}


def load_sealed_candidates(root: Path) -> list[dict[str, str]]:
    """Resume immutable proposals as the durable ready queue across wakes."""
    root = root.expanduser()
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o777 != 0o700:
        raise ValueError("upwork_proposal_store_invalid")
    rows = []
    for path in sorted(root.glob("*.json")):
        if path.is_symlink() or path.stat().st_mode & 0o777 != 0o600:
            raise ValueError("upwork_sealed_proposal_invalid")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("upwork_sealed_proposal_invalid") from exc
        if (
            not isinstance(payload, dict) or set(payload) != _SEALED_PROPOSAL_KEYS
            or payload.get("provider") != "upwork"
            or payload.get("status") != "frozen_waiting_for_connects"
            or not isinstance(payload.get("job_id"), str)
            or not isinstance(payload.get("job_url"), str)
            or not isinstance(payload.get("title"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("payload_sha256") or ""))
        ):
            raise ValueError("upwork_sealed_proposal_invalid")
        rows.append({
            "job_id": payload["job_id"], "job_url": payload["job_url"],
            "queue": "ready", "title": payload["title"],
            "proposal_payload_sha256": payload["payload_sha256"],
        })
    return rows


def plan_free_proposal(
    state: dict[str, Any], proposals_dir: Path, completed_job_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    """Return the first exact sealed proposal covered by the observed free balance."""
    balance = state.get("balance")
    candidates = state.get("candidate_jobs")
    if type(balance) is not int or balance < 0 or not isinstance(candidates, list):
        raise ValueError("upwork_free_action_state_invalid")
    proposals_dir = proposals_dir.expanduser()
    if (
        proposals_dir.is_symlink() or not proposals_dir.is_dir()
        or proposals_dir.stat().st_mode & 0o777 != 0o700
    ):
        raise ValueError("upwork_proposal_store_invalid")
    completed_job_ids = completed_job_ids or set()
    for candidate in candidates:
        if (
            not isinstance(candidate, dict) or candidate.get("status") != "open"
            or candidate.get("queue") != "ready"
            or candidate.get("job_id") in completed_job_ids
        ):
            continue
        required = candidate.get("connects_required")
        if type(required) is not int or required < 0 or balance < required:
            continue
        job_id = candidate.get("job_id")
        expected_hash = candidate.get("proposal_payload_sha256")
        if (
            not isinstance(job_id, str) or not job_id.startswith("~")
            or not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
        ):
            raise ValueError("upwork_free_action_candidate_invalid")
        path = proposals_dir / f"{job_id.lstrip('~')}.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 != 0o600:
            raise ValueError("upwork_sealed_proposal_invalid")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("upwork_sealed_proposal_invalid") from exc
        if not isinstance(payload, dict) or set(payload) != _SEALED_PROPOSAL_KEYS:
            raise ValueError("upwork_sealed_proposal_invalid")
        terms = payload.get("terms")
        answers = payload.get("screening_answers")
        proposal_url = urlsplit(str(payload.get("job_url") or ""))
        if (
            payload.get("provider") != "upwork" or payload.get("job_id") != job_id
            or proposal_url.scheme != "https" or proposal_url.netloc != "www.upwork.com"
            or job_id not in proposal_url.path
            or payload.get("status") != "frozen_waiting_for_connects"
            or not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("job_source_sha256") or ""))
            or not isinstance(payload.get("cover_letter"), str)
            or not payload["cover_letter"].strip()
            or not isinstance(terms, dict) or set(terms) != _SEALED_TERMS_KEYS
            or not isinstance(answers, list)
            or any(
                not isinstance(answer, dict) or set(answer) != {"question", "answer"}
                or not all(isinstance(answer[key], str) and answer[key].strip() for key in answer)
                for answer in answers
            )
            or payload.get("unsupported_claims") != []
            or not isinstance(payload.get("attachments"), list)
        ):
            raise ValueError("upwork_sealed_proposal_invalid")
        if terms.get("required_connects") != required:
            continue
        canonical = dict(payload)
        recorded_hash = canonical.pop("payload_sha256")
        canonical_line = json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ) + "\n"
        actual_hash = hashlib.sha256(canonical_line.encode()).hexdigest()
        if recorded_hash != expected_hash or actual_hash != expected_hash:
            raise ValueError("upwork_sealed_proposal_hash_mismatch")
        return payload
    return None


def plan_zero_connect_inbound(
    state: dict[str, Any], excluded_entity_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    """Prioritize one stable-ID inbound acquisition that needs no Connects."""
    excluded_entity_ids = excluded_entity_ids or set()
    for field, kind in (
        ("proposal_offer_entities", "direct_offer_detected"),
        ("invitation_entities", "invitation_detected"),
    ):
        entities = state.get(field)
        if not isinstance(entities, list):
            raise ValueError("upwork_free_action_state_invalid")
        for entity in entities:
            resource_url = urlsplit(str(entity.get("href") or "")) if isinstance(entity, dict) else None
            if (
                not isinstance(entity, dict) or not isinstance(entity.get("id"), str)
                or not isinstance(entity.get("href"), str)
                or resource_url is None or resource_url.scheme != "https"
                or resource_url.netloc != "www.upwork.com"
                or entity["id"] not in entity["href"]
            ):
                raise ValueError("upwork_free_action_state_invalid")
            if entity["id"] in excluded_entity_ids:
                continue
            return {
                "state": kind, "resource_id": entity["id"],
                "resource_url": entity["href"],
            }
    projects = state.get("catalog_projects")
    if not isinstance(projects, list):
        raise ValueError("upwork_free_action_state_invalid")
    ordered = next(
        (
            item for item in projects
            if isinstance(item, dict)
            and type(item.get("orders")) is int
            and item["orders"] > 0
        ),
        None,
    )
    if ordered is not None:
        return {"state": "catalog_order_identity_pending", "order_count": ordered["orders"]}
    return None


def parse_zero_connect_detail(kind: str, text: str) -> str:
    """Classify only official controls; never infer that an inbound is actionable."""
    normalized = " ".join((text or "").lower().split())
    if kind == "invitation_detected":
        accept = any(marker in normalized for marker in (
            "accept and send a proposal", "submit a proposal", "accept interview",
        ))
    elif kind == "direct_offer_detected":
        accept = "accept offer" in normalized
    else:
        raise ValueError("upwork_inbound_kind_invalid")
    return "actionable" if accept and "decline" in normalized else "unknown"


def seal_inbound_detail(
    inbound: dict[str, Any], text: str, evidence_sha256: str, root: Path,
    observed_at: str,
) -> str:
    """Persist one actionable inbound privately for the existing model runner."""
    if (
        inbound.get("state") not in {"invitation_detected", "direct_offer_detected", "public_job"}
        or not isinstance(inbound.get("resource_id"), str)
        or not isinstance(inbound.get("resource_url"), str)
        or not isinstance(text, str) or not text.strip()
        or not re.fullmatch(r"[0-9a-f]{64}", evidence_sha256)
    ):
        raise ValueError("upwork_inbound_packet_invalid")
    root = root.expanduser()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    packet = {
        "version": 1, "provider": "upwork", "kind": inbound["state"],
        "resource_id": inbound["resource_id"], "resource_url": inbound["resource_url"],
        "detail_evidence_sha256": evidence_sha256, "observed_at": observed_at,
        "rendered_text": text, "title": str(inbound.get("title") or inbound["resource_id"]),
    }
    if inbound["state"] == "public_job":
        required = inbound.get("required_connects")
        available = inbound.get("available_connects_before")
        if type(required) is not int or type(available) is not int or not 0 <= required <= available:
            raise ValueError("upwork_inbound_packet_invalid")
        packet.update({
            "required_connects": required,
            "available_connects_before": available,
        })
    body = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    path = root / f"{digest}.json"
    if not path.exists():
        _atomic_write(path, packet)
    if path.is_symlink() or path.stat().st_mode & 0o777 != 0o600:
        raise ValueError("upwork_inbound_packet_invalid")
    return digest


def parse_candidate(
    candidate: dict[str, str], text: str, evidence_sha256: str,
) -> dict[str, Any]:
    lowered = (text or "").lower()
    if "this job has been removed" in lowered or "removed from upwork" in lowered:
        status, marker = "removed", "removed"
    elif "this job is no longer available" in lowered:
        status, marker = "closed", "no_longer_available"
    elif _CONNECTS_REQUIRED.search(text or "") and "Available Connects:" in (text or ""):
        status, marker = "open", "proposal_entry"
    else:
        status, marker = "unknown", "no_authoritative_marker"
    connects = _CONNECTS_REQUIRED.search(text or "")
    return {
        **candidate,
        "status": status,
        "official_marker": marker,
        "connects_required": int(next(value for value in connects.groups() if value))
        if connects else None,
        "evidence_sha256": evidence_sha256,
    }


async def discover_affordable_proposal(
    state: dict[str, Any], *, pass_id: str, sequence: int,
    proposals_dir: Path, inbound_dir: Path, inbound_evidence: Path,
    cursor_path: Path,
) -> dict[str, Any] | None:
    """Ask the existing proposal brain about current public jobs the balance can fund."""
    next_page = 2
    if cursor_path.exists():
        cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
        if (not isinstance(cursor, dict) or cursor.get("version") != 1
                or type(cursor.get("next_page")) is not int or cursor["next_page"] < 2):
            raise ValueError("upwork_search_cursor_invalid")
        next_page = cursor["next_page"]
    known = {str(row.get("job_id")) for row in state["candidate_jobs"]}
    state["proposal_discovery"] = {"pages": 0, "inspected": 0, "affordable": 0}
    pages = (1, next_page, next_page + 1)
    for page in pages:
        search_url = SEARCH_URL if page == 1 else f"{SEARCH_URL}&page={page}"
        base = sequence + (page - 1) * 11
        artifact = Path(await navigate_and_snapshot(
            pass_id, f"{base:02d}-1", "public-search", search_url,
            "read_only", 2, 1440,
        ))
        search_text, search_hash, search_links = _read_evidence(artifact, search_url)
        state["evidence_sha256"][f"public-search-{page}"] = search_hash
        state["proposal_discovery"]["pages"] += 1
        if "abnormally high volume of traffic" in search_text.casefold():
            state["proposal_discovery"].update({
                "provider_state": "unavailable", "retry_page": page,
            })
            return None
        jobs = [row for row in _dedupe_links(search_links)
                if "/jobs/" in row["href"] and row["id"] not in known]
        packet_paths: list[Path] = []
        batch_identities: list[str] = []
        observed_by_id: dict[str, tuple[dict[str, str], str, str]] = {}
        selected_jobs = jobs
        for job in selected_jobs:
            known.add(job["id"])
        detail_results = await read_public_job_details(
            selected_jobs, pass_id=pass_id, base=base,
        )
        for job, detail_read in detail_results:
            if detail_read is None:
                state["proposal_discovery"]["incomplete"] = (
                    state["proposal_discovery"].get("incomplete", 0) + 1
                )
                continue
            text, digest, _ = detail_read
            candidate = {
                "job_id": job["id"], "job_url": job["href"], "queue": "discovered",
                "title": job["title"], "proposal_payload_sha256": "",
            }
            observed = parse_candidate(candidate, text, digest)
            state["proposal_discovery"]["inspected"] += 1
            required = observed["connects_required"]
            if observed["status"] != "open" or type(required) is not int or required > state["balance"]:
                continue
            state["proposal_discovery"]["affordable"] += 1
            packet_sha = seal_inbound_detail({
                "state": "public_job", "resource_id": job["id"],
                "resource_url": job["href"], "required_connects": required,
                "available_connects_before": state["balance"],
                "title": job["title"],
            }, text, digest, inbound_dir, state["observed_at"])
            packet_paths.append(inbound_dir / f"{packet_sha}.json")
            batch_identities.append(f"{job['id']}|{digest}|{required}|{state['balance']}")
            observed_by_id[job["id"]] = (candidate, text, digest)
        if packet_paths:
            batch_key = hashlib.sha256("\n".join(batch_identities).encode()).hexdigest()
            proposals = await asyncio.to_thread(
                plan_batch, packet_paths, profile=DEFAULT_OWNER_PROFILE,
                evidence_dir=inbound_evidence / f"batch-{batch_key}",
                decision_sink=publish_application_decisions,
            )
            if not proposals:
                continue
            proposals_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(proposals_dir, 0o700)
            for proposal in proposals:
                candidate, text, digest = observed_by_id[proposal["job_id"]]
                public = dict(proposal)
                _atomic_write(proposals_dir / f"{proposal['job_id'].lstrip('~')}.json", public)
                ready = {**candidate, "queue": "ready",
                         "proposal_payload_sha256": public["payload_sha256"]}
                state["candidate_jobs"].append(parse_candidate(ready, text, digest))
            _atomic_write(cursor_path, {"version": 1, "next_page": page + 1})
            state["proposal_discovery"]["next_page"] = page + 1
            return proposals[0]
    _atomic_write(cursor_path, {"version": 1, "next_page": next_page + 2})
    state["proposal_discovery"]["next_page"] = next_page + 2
    return None


def _read_evidence(path: Path, expected_url: str) -> tuple[str, str, list[dict[str, Any]]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    observed_url = value.get("url")
    url_matches = observed_url == expected_url
    if not url_matches and isinstance(observed_url, str):
        try:
            expected = urlsplit(expected_url)
            observed = urlsplit(observed_url)
        except ValueError:
            observed = None
        if observed is not None:
            same_origin = (
                expected.scheme == observed.scheme == "https"
                and expected.netloc == observed.netloc == "www.upwork.com"
            )
            expected_room = re.fullmatch(
                r"/ab/messages/rooms/room_[^/?#]+", expected.path,
            )
            observed_room = re.fullmatch(
                r"/ab/messages/rooms/room_[^/?#]+", observed.path,
            )
            url_matches = same_origin and observed_room is not None and (
                expected_url == MESSAGES_URL
                or expected_room is not None and expected.path == observed.path
            )
            url_matches = url_matches or (
                same_origin and expected_url == TRANSACTIONS_URL
                and re.fullmatch(r"/nx/payments/reports/transactions/\d+", observed.path) is not None
            )
    if value.get("navigated_ok") is not True or not url_matches:
        raise ValueError("upwork_readback_incomplete")
    text = value.get("rendered_text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("upwork_readback_incomplete")
    links = value.get("rendered_links", [])
    if not isinstance(links, list):
        raise ValueError("upwork_readback_incomplete")
    return text, hashlib.sha256(path.read_bytes()).hexdigest(), links


async def read_public_job_details(
    jobs: list[dict[str, str]], *, pass_id: str, base: int,
) -> list[tuple[dict[str, str], tuple[str, str, list[dict[str, Any]]] | None]]:
    """Read independent hidden job targets concurrently, preserving source order."""
    async def read_one(offset: int, job: dict[str, str]):
        for attempt in range(1, 4):
            detail = Path(await navigate_and_snapshot(
                pass_id, f"{base + offset:02d}-{attempt}", "public-job",
                job["href"], "read_only", 2, 1440,
            ))
            try:
                return job, _read_evidence(detail, job["href"])
            except ValueError:
                if attempt < 3:
                    await asyncio.sleep(attempt)
        return job, None

    return list(await asyncio.gather(*(
        read_one(offset, job) for offset, job in enumerate(jobs, start=1)
    )))


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _read_previous_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("upwork_previous_state_invalid") from error
    if not isinstance(value, dict):
        raise ValueError("upwork_previous_state_invalid")
    return value


def retain_last_official_candidate_costs(
    current: list[dict[str, Any]], previous: dict[str, Any],
) -> list[dict[str, Any]]:
    prior = {
        str(item.get("job_id")): item
        for item in previous.get("candidate_jobs", [])
        if isinstance(item, dict) and item.get("job_id")
    }
    result = []
    for item in current:
        row = dict(item)
        old = prior.get(str(row.get("job_id")), {})
        cost = old.get("connects_required")
        if row.get("connects_required") is None and type(cost) is int and cost >= 0:
            row["connects_required"] = cost
            row["connects_evidence_sha256"] = old.get("connects_evidence_sha256") or old.get("evidence_sha256")
        result.append(row)
    return result


def reconcile_terminal_transitions(
    output: Path, ledger: Path, state: dict[str, Any],
) -> dict[str, Any]:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a+", encoding="utf-8") as handle:
        os.chmod(ledger, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            previous = _read_previous_state(output)
            state = dict(state)
            state["candidate_jobs"] = retain_last_official_candidate_costs(
                state.get("candidate_jobs", []), previous,
            )
            handle.seek(0)
            rows = []
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError("upwork_transition_ledger_invalid") from error
                if not isinstance(row, dict) or not row.get("event_id"):
                    raise ValueError("upwork_transition_ledger_invalid")
                rows.append(row)
            existing_ids = {str(row["event_id"]) for row in rows}
            existing_terminal = {
                (str(row.get("job_id")), str(row.get("to_status"))) for row in rows
            }
            previous_jobs = {
                str(item.get("job_id")): item
                for item in previous.get("candidate_jobs", [])
                if isinstance(item, dict) and item.get("job_id")
            }
            appended = []
            for candidate in state.get("candidate_jobs", []):
                if not isinstance(candidate, dict):
                    continue
                job_id = str(candidate.get("job_id") or "")
                to_status = str(candidate.get("status") or "")
                if not job_id or to_status not in TERMINAL_JOB_STATUSES:
                    continue
                prior = previous_jobs.get(job_id, {})
                prior_status = str(prior.get("status") or "unobserved")
                if prior_status == to_status and (job_id, to_status) in existing_terminal:
                    continue
                from_status = "legacy_observed" if prior_status == to_status else prior_status
                source_observed_at = str(previous.get("observed_at") or "unobserved")
                event_material = "|".join((
                    job_id, from_status, to_status, source_observed_at,
                ))
                event_id = hashlib.sha256(event_material.encode("utf-8")).hexdigest()
                if event_id in existing_ids:
                    continue
                event = {
                    "event_id": event_id,
                    "job_id": job_id,
                    "from_status": from_status,
                    "to_status": to_status,
                    "official_reason": str(candidate.get("official_marker") or "unknown"),
                    "observed_at": str(state.get("observed_at") or ""),
                    "source_observed_at": source_observed_at,
                    "receipt_hash": str(candidate.get("evidence_sha256") or ""),
                }
                handle.write(json.dumps(
                    event, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ) + "\n")
                appended.append(event)
                existing_ids.add(event_id)
                existing_terminal.add((job_id, to_status))
            for intent in state.get("negotiation_intents", []):
                if not isinstance(intent, dict) or intent.get("decision") != "no_reply":
                    continue
                source_event_id = str(intent.get("event_id") or "")
                room_id = str(intent.get("room_id") or "")
                if not source_event_id or not room_id:
                    continue
                event_id = hashlib.sha256(
                    f"buyer_head|{source_event_id}|terminal".encode("utf-8")
                ).hexdigest()
                if event_id in existing_ids:
                    continue
                event = {
                    "event_id": event_id,
                    "resource_kind": "buyer_head",
                    "resource_id": room_id,
                    "source_event_id": source_event_id,
                    "from_status": "buyer_head",
                    "to_status": "terminal",
                    "official_reason": ",".join(intent.get("reason_codes") or ["no_reply"]),
                    "observed_at": str(state.get("observed_at") or ""),
                    "receipt_hash": str(intent.get("head_sha256") or ""),
                }
                handle.write(json.dumps(
                    event, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ) + "\n")
                appended.append(event)
                existing_ids.add(event_id)
            handle.flush()
            os.fsync(handle.fileno())
            state = dict(state)
            state["terminal_transition_count"] = len(rows) + len(appended)
            state["terminal_transitions_appended"] = len(appended)
            state["terminal_transition_event_ids"] = [
                event["event_id"] for event in appended
            ]
            _atomic_write(output, state)
            return state
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


async def execute_sealed_proposal(
    payload: dict[str, Any], *, pass_id: str, sequence: int, database: Path,
    manifest: Path, browser_profile: Path, connects_pre: int, connects_pre_hash: str,
    existing_proposals: list[dict[str, Any]], proposals_pre_hash: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    """Run either public or invitation proposal through the same durable effect."""
    effect_now = datetime.now(timezone.utc)
    effect = SealedUpworkProposalEffect(
        ConnectorOutbox(database.expanduser(), manifest.expanduser()),
        UpworkTransport(
            active_upwork_browser_account(DEFAULT_RECEIPT_PATH, effect_now), effect_now,
            browser_profile=browser_profile.expanduser(),
            profiles_root=browser_profile.expanduser().parent,
        ),
    )
    selection, planned = effect.intent(payload)
    existing = effect.store.provider_effect(planned)
    base = {"proposal_payload_sha256": payload["payload_sha256"]}
    if existing is not None and existing["reconciliation_state"] == "verified":
        return {**base, "state": "submitted", "proposal_id": existing["proposal_id"]}, None, None
    if existing is not None and existing["state"] == "reconcile_pending":
        matches = [item for item in existing_proposals if item.get("title") == payload["title"]]
        if len(matches) == 1 and connects_pre == existing["connects_pre"] - payload["terms"]["required_connects"]:
            receipt = {
                "state": "submitted", "job_id": payload["job_id"],
                "proposal_id": str(matches[0]["id"]), "evidence_sha256": proposals_pre_hash,
            }
            effect.verify(
                planned, receipt, connects_post=connects_pre,
                connects_evidence_sha256=connects_pre_hash,
            )
            publish_application_decisions([proposal_submitted_event(
                payload, proposal_id=receipt["proposal_id"],
                connects_before=int(existing["connects_pre"]), connects_after=connects_pre,
            )])
            return {**base, "state": "submitted", "proposal_id": receipt["proposal_id"]}, None, None
        if not matches:
            no_effect_hash = hashlib.sha256(json.dumps({
                "proposals": proposals_pre_hash, "connects": connects_pre_hash,
            }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            effect.store.reopen_provider_effect_after_no_effect(
                planned, authorization=selection.authorization, connects_current=connects_pre,
                connects_evidence_sha256=connects_pre_hash,
                no_effect_readback_hash=no_effect_hash, now=int(effect_now.timestamp()),
            )
        else:
            return {**base, "state": "reconcile_unknown"}, None, None
    preflight = {
        "ready": True, "job_id": payload["job_id"],
        "required_connects": payload["terms"]["required_connects"],
        "available_connects": connects_pre, "evidence_sha256": connects_pre_hash,
    }
    intent, started = effect.start(payload, preflight)
    if started is not True:
        return {**base, "state": "reconcile_unknown"}, None, None
    form_url = (
        payload["job_url"] if payload["status"] == "frozen_waiting_for_invitation"
        else f"https://www.upwork.com/nx/proposals/job/{payload['job_id']}/apply/#/"
    )
    await asyncio.to_thread(
        operate_market_form, provider="upwork", resource_id=payload["job_id"],
        form_url=form_url, sealed_intent=payload,
        live_effect_context={
            "current_balance": connects_pre,
            "required_charge": payload["terms"]["required_connects"],
            "balance_unit": "connects",
        },
        cdp_base=os.environ["CLOAK_CDP_BASE_URL"],
    )
    proposal_artifact = Path(await navigate_and_snapshot(
        pass_id, f"{sequence:02d}-1", "proposal-post", PROPOSALS_URL,
        "read_only", 2, 1440,
    ))
    proposal_text, proposal_hash, proposal_links = _read_evidence(
        proposal_artifact, PROPOSALS_URL,
    )
    proposal_state = {
        **parse_inventory(proposal_text),
        **parse_stable_entities(invite_links=[], proposal_links=proposal_links),
    }
    receipt = submitted_proposal_receipt(
        payload, proposal_state, evidence_sha256=proposal_hash,
        existing_proposal_ids={str(item["id"]) for item in existing_proposals},
    )
    artifact = Path(await navigate_and_snapshot(
        pass_id, f"{sequence + 1:02d}-1", "connects-post", CONNECTS_URL,
        "read_only", 2, 1440,
    ))
    post_text, post_hash, _ = _read_evidence(artifact, CONNECTS_URL)
    post_connects = parse_connects(post_text)
    effect.verify(
        intent, receipt, connects_post=post_connects["balance"],
        connects_evidence_sha256=post_hash,
    )
    publish_application_decisions([proposal_submitted_event(
        payload, proposal_id=receipt["proposal_id"], connects_before=connects_pre,
        connects_after=post_connects["balance"],
    )])
    return {
        **base, "state": "submitted", "proposal_id": receipt["proposal_id"],
    }, post_connects, post_hash


def submitted_proposal_receipt(
    payload: dict[str, Any], state: dict[str, Any], *, evidence_sha256: str,
    existing_proposal_ids: set[str],
) -> dict[str, str]:
    entities = [
        item for key in ("submitted_proposal_entities", "active_proposal_entities")
        for item in state.get(key, []) if isinstance(item, dict)
    ]
    matches = [
        item for item in entities
        if item.get("title") == payload.get("title")
        and str(item.get("id") or "") not in existing_proposal_ids
    ]
    if len(matches) != 1 or not re.fullmatch(r"[0-9]+", str(matches[0].get("id") or "")):
        raise ValueError("upwork_proposal_submit_unconfirmed")
    return {
        "state": "submitted", "job_id": payload["job_id"],
        "proposal_id": str(matches[0]["id"]), "evidence_sha256": evidence_sha256,
    }


def create_offer_workspace(
    decision: dict[str, Any], *, contract_id: str, contract_readback_sha256: str,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
) -> dict[str, str]:
    offer = decision["offer"]
    return create_workspace(projects_root, {
        "version": 1, "provider": "upwork", "contract_id": contract_id,
        "offer_id": offer["offer_id"], "scope": offer["scope"],
        "deadline": offer["deadline"], "terms_sha256": decision["decision_sha256"],
        "contract_readback_sha256": contract_readback_sha256,
    }, general_agent_workflow())


def start_project_worker(workspace: dict[str, str]) -> None:
    subprocess.Popen([
        sys.executable, str(DEFAULT_PROJECT_WORKER), "--workspace", workspace["workspace"],
        "--revision-sha256", workspace["revision_sha256"],
        "--skills-root", str(SCRIPTS.parents[2]), "--agent-runner", str(DEFAULT_AGENT_RUNNER),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def resume_active_contract_workers(
    contracts: list[dict[str, Any]], *, projects_root: Path = DEFAULT_PROJECTS_ROOT,
) -> list[dict[str, str]]:
    owners = []
    for contract in contracts:
        contract_id = contract["id"]
        if not (projects_root / "upwork" / contract_id).exists():
            owners.append({"contract_id": contract_id, "state": "compile_pending"})
            continue
        try:
            workspace = load_workspace(projects_root, "upwork", contract_id)
        except WorkspaceError as exc:
            owners.append({"contract_id": contract_id, "state": "owner_blocked",
                           "reason": str(exc)})
            continue
        start_project_worker(workspace)
        owners.append({"contract_id": contract_id, "state": "worker_resumed",
                       "workspace": workspace["workspace"],
                       "revision_sha256": workspace["revision_sha256"]})
    return owners


async def execute_direct_offer(
    decision: dict[str, Any], *, database: Path, manifest: Path, browser_profile: Path,
    active_contract_ids: list[str], concurrent_job_cap: int,
) -> dict[str, Any]:
    """Accept one qualified Direct Offer through the shared durable effect ledger."""
    effect_now = datetime.now(timezone.utc)
    effect = SealedUpworkOfferEffect(
        ConnectorOutbox(database.expanduser(), manifest.expanduser()),
        UpworkTransport(
            active_upwork_browser_account(DEFAULT_RECEIPT_PATH, effect_now, "accept_offer"),
            effect_now, browser_profile=browser_profile.expanduser(),
            profiles_root=browser_profile.expanduser().parent,
        ),
    )
    _, planned = effect.intent(decision)
    existing = effect.store.provider_effect(planned)
    base = {"offer_decision_sha256": decision["decision_sha256"]}
    if existing is not None and existing["reconciliation_state"] == "verified":
        workspace = create_offer_workspace(
            decision, contract_id=existing["proposal_id"],
            contract_readback_sha256=existing["readback_hash"],
        )
        start_project_worker(workspace)
        return {**base, "state": "accepted", "contract_id": existing["proposal_id"],
                "project_workspace": workspace}
    if existing is not None and existing["state"] == "reconcile_pending":
        return {**base, "state": "reconcile_unknown"}
    holder: dict[str, Any] = {}

    def start_effect(preflight: dict[str, Any]) -> bool:
        holder["intent"], started = effect.start(decision, preflight, capacity={
            "active_contract_ids": active_contract_ids,
            "concurrent_job_cap": concurrent_job_cap,
        })
        return started

    try:
        receipt = await accept_offer_after_fence(decision, start_effect)
    except ConnectorBusy:
        return {**base, "state": "capacity_full"}
    verified = effect.verify(holder["intent"], receipt)
    workspace = create_offer_workspace(
        decision, contract_id=receipt["contract_id"],
        contract_readback_sha256=verified["readback_hash"],
    )
    start_project_worker(workspace)
    return {**base, "state": "accepted", "contract_id": receipt["contract_id"],
            "project_workspace": workspace}


async def execute_negotiation_message(
    decision: dict[str, Any], *, database: Path, manifest: Path, browser_profile: Path,
) -> dict[str, Any]:
    """Send one current-head-bound negotiation through the durable effect ledger."""
    effect_now = datetime.now(timezone.utc)
    effect = SealedUpworkMessageEffect(
        ConnectorOutbox(database.expanduser(), manifest.expanduser()),
        UpworkTransport(
            active_upwork_browser_account(DEFAULT_RECEIPT_PATH, effect_now, "message"),
            effect_now, browser_profile=browser_profile.expanduser(),
            profiles_root=browser_profile.expanduser().parent,
        ),
    )
    _, planned = effect.intent(decision)
    existing = effect.store.provider_effect(planned)
    base = {"intent_sha256": decision["intent_sha256"]}
    if existing is not None and existing["reconciliation_state"] == "verified":
        return {**base, "state": "sent", "message_id": existing["proposal_id"]}
    if existing is not None and existing["state"] == "reconcile_pending":
        return {**base, "state": "reconcile_unknown"}
    holder: dict[str, Any] = {}

    def start_effect(preflight: dict[str, Any]) -> bool:
        holder["intent"], started = effect.start(decision, preflight)
        return started

    receipt = await send_message_after_fence(decision, start_effect)
    effect.verify(holder["intent"], receipt)
    return {**base, "state": "sent", "message_id": receipt["message_id"]}


async def observe(
    candidates_path: Path = DEFAULT_CANDIDATES,
    proposals_dir: Path = DEFAULT_PROPOSALS,
    database: Path = DEFAULT_DATABASE,
    manifest: Path = DEFAULT_MANIFEST,
    browser_profile: Path = DEFAULT_BROWSER_PROFILE,
    inbound_dir: Path = DEFAULT_INBOUND_DIR,
    inbound_proposals: Path = DEFAULT_INBOUND_PROPOSALS,
    inbound_evidence: Path = DEFAULT_INBOUND_EVIDENCE,
    inbox_ledger: Path = DEFAULT_INBOX_LEDGER,
    search_cursor: Path = DEFAULT_SEARCH_CURSOR,
) -> dict[str, Any]:
    pass_id = f"upwork-free-{time.time_ns()}-{os.getpid()}"
    artifacts: dict[str, str] = {}
    pages: dict[str, str] = {}
    links: dict[str, list[dict[str, Any]]] = {}
    candidates = load_candidates(candidates_path)
    known_candidate_ids = {item["job_id"] for item in candidates}
    candidates.extend(
        item for item in load_sealed_candidates(proposals_dir)
        if item["job_id"] not in known_candidate_ids
    )
    targets = [
        ("connects", CONNECTS_URL), ("invites", INVITES_URL),
        ("proposals", PROPOSALS_URL), ("catalog", CATALOG_URL),
        ("contracts", CONTRACTS_URL), ("transactions", TRANSACTIONS_URL),
        ("withdrawals", WITHDRAWALS_URL), ("messages", MESSAGES_URL),
        ("working-style", WORKING_STYLE_URL),
    ] + [
        (f"candidate-{item['job_id'].lstrip('~')}", item["job_url"])
        for item in candidates
    ]
    for sequence, (label, url) in enumerate(targets, start=1):
        for attempt in range(1, 4):
            artifact = Path(await navigate_and_snapshot(
                pass_id, f"{sequence:02d}-{attempt}", label, url, "read_only", 2,
                1440,
            ))
            try:
                pages[label], artifacts[label], links[label] = _read_evidence(artifact, url)
                break
            except ValueError:
                if attempt == 3:
                    raise
                await asyncio.sleep(attempt)
    message_inventory = parse_messages(pages["messages"], links["messages"])
    inbox_observations: list[dict[str, Any]] = []
    for offset, room in enumerate(prioritize_message_rooms(message_inventory), start=1):
        label = f"room-{hashlib.sha256(room['id'].encode()).hexdigest()[:16]}"
        artifact = Path(await navigate_and_snapshot(
            pass_id, f"{len(targets) + offset:02d}-1", label, room["href"],
            "read_only", 2, 1440,
        ))
        room_text, room_hash, room_links = _read_evidence(artifact, room["href"])
        pages[label], artifacts[label] = room_text, room_hash
        inbox_observations.append(normalize_observation(
            kind="message_room", resource_id=room["id"], resource_url=room["href"],
            rendered_text=room_text, source_evidence_sha256=room_hash,
            observed_at=datetime.now(timezone.utc).isoformat(),
            rendered_links=room_links,
        ))
    contract_inventory = parse_contracts(pages["contracts"], links["contracts"])
    for contract in contract_inventory["active_contracts"]:
        inbox_observations.append(normalize_observation(
            kind="contract", resource_id=contract["id"], resource_url=contract["href"],
            rendered_text=pages["contracts"], source_evidence_sha256=artifacts["contracts"],
            observed_at=datetime.now(timezone.utc).isoformat(),
        ))
    inbox_reconciliation = append_changed_heads(inbox_ledger, inbox_observations)
    state = {
        "version": 1,
        "provider": "upwork",
        "mode": "zero_spend",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        **parse_connects(pages["connects"]),
        **parse_inventory(
            pages["proposals"] + "\n" + pages["invites"],
            pages["working-style"],
        ),
        **parse_stable_entities(
            invite_links=links["invites"], proposal_links=links["proposals"],
        ),
        **parse_catalog(pages["catalog"]),
        **contract_inventory,
        "payment_observer": parse_payment_observer(
            pages["transactions"], pages["withdrawals"],
        ),
        **message_inventory,
        "inbox_reconciliation": inbox_reconciliation,
        "candidate_jobs": [
            parse_candidate(
                item,
                pages[f"candidate-{item['job_id'].lstrip('~') }"],
                artifacts[f"candidate-{item['job_id'].lstrip('~') }"],
            )
            for item in candidates
        ],
        "evidence_sha256": artifacts,
    }
    try:
        account_id = active_upwork_browser_account(
            DEFAULT_RECEIPT_PATH, datetime.now(timezone.utc), "inspect",
        )
        state["platform_manifest"] = record_upwork_platform_manifest_wake(
            state,
            account_id=account_id,
            run_id=f"{pass_id}-platform-manifest",
        )
    except Exception as error:  # noqa: BLE001 - fail closed before provider effects
        raise ValueError(
            f"upwork_platform_manifest_wake_failed:{type(error).__name__}"
        ) from error
    state["contract_owners"] = resume_active_contract_workers(state["active_contracts"])
    state["negotiation_intents"] = []
    for head in inbox_reconciliation["heads"]:
        if head["kind"] != "message_room" or head["changed"] is not True:
            continue
        intent = await asyncio.to_thread(
            plan_negotiation, head["resource_id"], inbox=inbox_ledger,
            loop_state_value=state,
            evidence_dir=DEFAULT_NEGOTIATION_EVIDENCE / head["event_id"],
        )
        public_intent = {
            "room_id": head["resource_id"], "event_id": head["event_id"],
            "head_sha256": head["head_sha256"], "revision": head["revision"],
            "decision": intent["decision"], "reason_codes": intent["reason_codes"],
            "intent_sha256": intent["intent_sha256"],
        }
        if intent["decision"] != "no_reply":
            public_intent.update(await execute_negotiation_message(
                intent, database=database, manifest=manifest,
                browser_profile=browser_profile,
            ))
        state["negotiation_intents"].append(public_intent)
    inbound = plan_zero_connect_inbound(
        state,
        excluded_entity_ids=load_terminal_upwork_application_ids(
            DEFAULT_GIG_DIR / "work-events.jsonl"
        ),
    )
    if inbound is not None:
        state["can_submit_public_job"] = False
        if inbound["state"] in {"invitation_detected", "direct_offer_detected"}:
            detail_artifact = Path(await navigate_and_snapshot(
                pass_id, f"{len(targets) + 1:02d}-1", "inbound-detail",
                inbound["resource_url"], "read_only", 2, 1440,
            ))
            detail_text, detail_hash, detail_links = _read_evidence(
                detail_artifact, inbound["resource_url"],
            )
            state["evidence_sha256"]["inbound-detail"] = detail_hash
            detail_state = parse_zero_connect_detail(inbound["state"], detail_text)
            state["free_acquisition"] = {
                **inbound,
                "detail_state": detail_state,
                "detail_evidence_sha256": detail_hash,
            }
            if inbound["state"] == "direct_offer_detected":
                offer_reconciliation = append_changed_heads(inbox_ledger, [normalize_observation(
                    kind="offer", resource_id=inbound["resource_id"],
                    resource_url=inbound["resource_url"], rendered_text=detail_text,
                    source_evidence_sha256=detail_hash, observed_at=state["observed_at"],
                    rendered_links=detail_links,
                )])
                state["inbox_reconciliation"] = {
                    "observed": inbox_reconciliation["observed"] + offer_reconciliation["observed"],
                    "appended": inbox_reconciliation["appended"] + offer_reconciliation["appended"],
                    "heads": inbox_reconciliation["heads"] + offer_reconciliation["heads"],
                }
            if detail_state == "actionable" and inbound["state"] == "invitation_detected":
                packet_sha = seal_inbound_detail(
                    inbound, detail_text, detail_hash, inbound_dir, state["observed_at"],
                )
                state["free_acquisition"]["private_packet_sha256"] = packet_sha
                proposal = await asyncio.to_thread(
                    plan_inbound, inbound_dir.expanduser() / f"{packet_sha}.json",
                    evidence_dir=inbound_evidence.expanduser() / packet_sha,
                    decision_sink=publish_application_decisions,
                    title=str(inbound.get("title") or inbound["resource_id"]),
                )
                if proposal is None:
                    state["free_acquisition"]["proposal_state"] = "model_skip"
                else:
                    write_sealed_proposal(proposal, inbound_proposals)
                    acquisition, post_connects, post_hash = await execute_sealed_proposal(
                        proposal, pass_id=pass_id, sequence=len(targets) + 2,
                        database=database, manifest=manifest, browser_profile=browser_profile,
                        connects_pre=state["balance"],
                        connects_pre_hash=state["evidence_sha256"]["connects"],
                        existing_proposals=[
                            item for key in (
                                "submitted_proposal_entities", "active_proposal_entities",
                            ) for item in state.get(key, []) if isinstance(item, dict) and item.get("id")
                        ],
                        proposals_pre_hash=state["evidence_sha256"]["proposals"],
                    )
                    state["free_acquisition"].update(acquisition)
                    if post_connects is not None and post_hash is not None:
                        state.update(post_connects)
                        state["evidence_sha256"]["connects-post"] = post_hash
            elif detail_state == "actionable":
                packet_sha = seal_inbound_detail(
                    inbound, detail_text, detail_hash, inbound_dir, state["observed_at"],
                )
                state["free_acquisition"]["private_packet_sha256"] = packet_sha
                decision = await asyncio.to_thread(
                    qualify_direct_offer, inbound_dir.expanduser() / f"{packet_sha}.json",
                    evidence_dir=DEFAULT_OFFER_EVIDENCE.expanduser() / packet_sha,
                )
                state["free_acquisition"]["offer_state"] = {
                    "accept": "accept_ready",
                    "request_changes": "request_changes",
                    "decline": "decline",
                }[decision["action"]]
                state["free_acquisition"]["offer_reason_codes"] = decision["reason_codes"]
                if decision["action"] == "accept":
                    owner = json.loads(DEFAULT_OWNER_PROFILE.read_text(encoding="utf-8"))
                    cap = owner.get("bounds", {}).get("concurrent_job_cap")
                    if type(cap) is not int or cap < 1:
                        raise ValueError("upwork_capacity_invalid")
                    state["free_acquisition"].update(await execute_direct_offer(
                        decision, database=database, manifest=manifest,
                        browser_profile=browser_profile,
                        active_contract_ids=[item["id"] for item in state["active_contracts"]],
                        concurrent_job_cap=cap,
                    ))
        else:
            state["free_acquisition"] = inbound
        return state
    completed_jobs = ConnectorOutbox(
        database.expanduser(), manifest.expanduser(),
    ).verified_provider_resource_ids("upwork", "propose")
    selected = plan_free_proposal(state, proposals_dir, completed_jobs)
    if selected is None:
        selected = await discover_affordable_proposal(
            state, pass_id=pass_id, sequence=len(targets) + 21,
            proposals_dir=proposals_dir, inbound_dir=inbound_dir,
            inbound_evidence=inbound_evidence, cursor_path=search_cursor,
        )
    state["can_submit_public_job"] = selected is not None
    if selected is None:
        state["free_acquisition"] = {"state": "waiting_free_capacity"}
    else:
        acquisition, post_connects, post_hash = await execute_sealed_proposal(
            selected, pass_id=pass_id, sequence=len(targets) + 1,
            database=database, manifest=manifest, browser_profile=browser_profile,
            connects_pre=state["balance"],
            connects_pre_hash=state["evidence_sha256"]["connects"],
            existing_proposals=[
                item for key in (
                    "submitted_proposal_entities", "active_proposal_entities",
                ) for item in state.get(key, []) if isinstance(item, dict) and item.get("id")
            ],
            proposals_pre_hash=state["evidence_sha256"]["proposals"],
        )
        state["free_acquisition"] = acquisition
        if post_connects is not None and post_hash is not None:
            state.update(post_connects)
            state["evidence_sha256"]["connects-post"] = post_hash
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-identity", default=DEFAULT_BROWSER_IDENTITY)
    parser.add_argument("--browser-registry", type=Path, default=DEFAULT_BROWSER_REGISTRY)
    parser.add_argument("--browser-resolver", type=Path, default=DEFAULT_BROWSER_RESOLVER)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--inbound-dir", type=Path, default=DEFAULT_INBOUND_DIR)
    parser.add_argument("--inbound-proposals", type=Path, default=DEFAULT_INBOUND_PROPOSALS)
    parser.add_argument("--inbound-evidence", type=Path, default=DEFAULT_INBOUND_EVIDENCE)
    parser.add_argument("--inbox-ledger", type=Path, default=DEFAULT_INBOX_LEDGER)
    parser.add_argument("--search-cursor", type=Path, default=DEFAULT_SEARCH_CURSOR)
    parser.add_argument("--transitions", type=Path, default=DEFAULT_TRANSITIONS)
    parser.add_argument(
        "--output", type=Path,
        default=Path(os.path.expanduser("~/gig/state/upwork-free-loop.json")),
    )
    args = parser.parse_args()
    browser = resolve_browser_identity(
        args.browser_identity,
        registry=args.browser_registry,
        resolver=args.browser_resolver,
    )
    os.environ["CLOAK_CDP_BASE_URL"] = browser["endpoint"].rstrip("/")
    os.environ["LIFE_MANAGER_BROWSER_IDENTITY"] = browser["identity"]
    state = asyncio.run(observe(
        args.candidates.expanduser(), args.proposals.expanduser(), args.database.expanduser(),
        args.manifest.expanduser(), Path(browser["profile"]), args.inbound_dir.expanduser(),
        args.inbound_proposals.expanduser(), args.inbound_evidence.expanduser(),
        args.inbox_ledger.expanduser(), args.search_cursor.expanduser(),
    ))
    state = reconcile_terminal_transitions(
        args.output.expanduser(), args.transitions.expanduser(), state,
    )
    print(json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
