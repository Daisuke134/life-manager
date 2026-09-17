from __future__ import annotations

import re
import argparse
import base64
import hashlib
import hmac
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
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


def project_model_outcomes(
    result: dict[str, Any], candidates: dict[str, Any], ledger: Any, *, observed_at: str
) -> list[dict[str, str]]:
    """Record only model outcomes bound to an exact fetched Gmail message, then project them."""
    rows = result.get("outcomes", []) if isinstance(result, dict) else []
    messages = candidates.get("messages", []) if isinstance(candidates, dict) else []
    by_id = {str(row.get("message_id")): row for row in messages if isinstance(row, dict)}
    if not isinstance(rows, list):
        raise ValueError("outcomes must be an array")
    projected: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("outcome must be an object")
        allowed = {"application_id", "funnel_stage", "disposition", "message_id", "occurred_at", "observation_policy_version"}
        if set(row) != allowed:
            raise ValueError("outcome keys are not closed")
        message_id = str(row["message_id"])
        candidate = by_id.get(message_id)
        if candidate is None:
            raise ValueError("outcome message ID was not scanned")
        app_id = str(row["application_id"])
        application = ledger.connection.execute(
            "SELECT company,title FROM applications WHERE id=?", (app_id,)
        ).fetchone()
        if application is None:
            raise ValueError("outcome application is unknown")
        evidence_material = json.dumps({
            "message_id": message_id,
            "thread_id": candidate.get("thread_id"),
            "subject": candidate.get("subject"),
            "sender": candidate.get("sender"),
            "received_at": candidate.get("received_at"),
            "body": candidate.get("body"),
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        evidence_sha256 = hashlib.sha256(evidence_material.encode("utf-8")).hexdigest()
        outcome_id = ledger.record_funnel_outcome(
            application_id=app_id,
            funnel_stage=str(row["funnel_stage"]),
            disposition=str(row["disposition"]),
            evidence_source="gmail",
            evidence_sha256=evidence_sha256,
            occurred_at=str(row["occurred_at"]),
            observed_at=observed_at,
            observation_policy_version=row["observation_policy_version"],
        )
        kind = "interview" if row["funnel_stage"] == "interview" and row["disposition"] == "positive" else (
            "offer" if row["funnel_stage"] == "offer" else "rejection"
        )
        projected.append({
            "source_outcome_id": f"job-search:{outcome_id}",
            "kind": kind,
            "company": str(application["company"]),
            "role": str(application["title"]),
            "verified_at": observed_at,
            "evidence_ref": f"job-search-outcome://{outcome_id}",
            "evidence_sha256": evidence_sha256,
        })
    return projected


def record_and_publish_outcomes(
    *, ledger_path: Path, candidates_path: Path, result_path: Path,
    output_path: Path, endpoint: str | None = None, secret: str | None = None,
) -> dict[str, Any]:
    from .ledger import Ledger

    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    observed_at = datetime.now(timezone.utc).isoformat()
    ledger = Ledger(ledger_path)
    try:
        projections = project_model_outcomes(result, candidates, ledger, observed_at=observed_at)
    finally:
        ledger.close()
    deliveries = []
    if endpoint:
        if not secret:
            raise ValueError("mental outcome endpoint secret is unavailable")
        for projection in projections:
            deliveries.append(publish_mental_outcome(projection, endpoint=endpoint, secret=secret, now=datetime.now(timezone.utc)))
    payload = {"status": "ok", "count": len(projections), "projections": projections, "deliveries": deliveries}
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(output_path, 0o600)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint")
    parser.add_argument("--secret")
    args = parser.parse_args(argv)
    print(json.dumps(record_and_publish_outcomes(
        ledger_path=args.ledger,
        candidates_path=args.candidates,
        result_path=args.result,
        output_path=args.output,
        endpoint=args.endpoint,
        secret=args.secret,
    ), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
