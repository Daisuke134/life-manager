from __future__ import annotations

import re
import base64
import hashlib
import hmac
import json
import urllib.request
from datetime import datetime
from typing import Any


_ALLOWED_SOURCES = {"gmail", "ats", "employer_portal", "signed_document"}
_ALLOWED_STAGES = {"interview", "offer"}
_OUTCOME_ID = re.compile(r"^outcome-[A-Za-z0-9_-]+$")


def _aware(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be RFC3339")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be RFC3339") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def build_mental_outcome_projection(row: dict[str, Any]) -> dict[str, str]:
    if not isinstance(row, dict):
        raise ValueError("outcome row must be an object")
    outcome_id = str(row.get("outcome_id") or "")
    if not _OUTCOME_ID.fullmatch(outcome_id):
        raise ValueError("outcome_id is invalid")
    source = str(row.get("evidence_source") or "")
    if source not in _ALLOWED_SOURCES:
        raise ValueError("outcome evidence source is not trusted")
    stage = str(row.get("funnel_stage") or "")
    disposition = str(row.get("disposition") or "")
    if stage not in _ALLOWED_STAGES:
        raise ValueError("mental projection requires interview or offer outcome")
    if disposition not in {"positive", "negative"}:
        raise ValueError("outcome disposition is invalid")
    evidence_hash = str(row.get("evidence_sha256") or "")
    if not re.fullmatch(r"[a-f0-9]{64}", evidence_hash):
        raise ValueError("outcome evidence hash is invalid")
    occurred = _aware(row.get("occurred_at"), "occurred_at")
    observed = _aware(row.get("observed_at"), "observed_at")
    if observed < occurred:
        raise ValueError("observed_at cannot predate occurred_at")
    company = str(row.get("company") or "").strip()
    title = str(row.get("title") or "").strip()
    if not company or not title:
        raise ValueError("application identity is required")
    if stage == "offer" and disposition != "positive":
        raise ValueError("offer mental outcome requires a positive disposition")
    kind = "interview" if stage == "interview" and disposition == "positive" else (
        "offer" if stage == "offer" else "rejection"
    )
    return {
        "source_outcome_id": f"job-search:{outcome_id}",
        "kind": kind,
        "company": company,
        "role": title,
        "verified_at": observed.isoformat(),
        "evidence_ref": f"job-search-outcome://{outcome_id}",
    }


def publish_mental_outcome(
    outcome: dict[str, str],
    *,
    endpoint: str,
    secret: str,
    now: datetime,
    opener=urllib.request.urlopen,
) -> dict[str, Any]:
    if not endpoint.startswith("https://"):
        raise ValueError("mental outcome endpoint must use HTTPS")
    if not secret or len(secret) < 32:
        raise ValueError("mental outcome signing secret is unavailable")
    timestamp = now.astimezone().isoformat().replace("+00:00", "Z")
    raw = json.dumps(outcome, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8") + b"\n" + raw, hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    request = urllib.request.Request(
        endpoint,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-LM-Outcome-Timestamp": timestamp,
            "X-LM-Outcome-Signature": signature,
        },
        method="POST",
    )
    with opener(request, timeout=10) as response:
        status = int(response.status)
        body = json.loads(response.read().decode("utf-8"))
    if status not in {200, 201} or body.get("ok") is not True:
        raise RuntimeError("mental outcome endpoint rejected projection")
    return {"status": str(body.get("result") or "accepted"), "http_status": status}
