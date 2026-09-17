"""Collect bounded, source-labeled Mercor learning observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from .mercor_learning import build_learning_candidate
from .mercor_funnel import project_funnel


_EVIDENCE_GRADES = frozenset({
    "official", "first_person", "marketing", "code", "unavailable",
})
_OFFICIAL_URL = "https://talent.docs.mercor.com/how-to/apply"
_OFFICIAL_MARKERS = (
    "navigate to explore", "job fit", "newest", "submit application", "resume later",
)
_DEFAULT_QUERY = "Mercor Japanese AI evaluator application"
_STRATEGY_VERSION = "mercor-fit-evidence-v1"
_FUNNEL_STAGES = ("application", "reply", "offer", "trial", "contract", "work", "payment")
_FUNNEL_VARIABLES = {
    "application": ("listing_order", {"listing_order": "page_one_to_four"}),
    "reply": ("application_presentation", {"application_presentation": "profile_fit_summary"}),
    "offer": ("qualification_evidence", {"qualification_evidence": "verified_requirement_evidence"}),
    "trial": ("interview_readiness", {"interview_readiness": "human_gate_preparation"}),
    "contract": ("assessment_selection", {"assessment_selection": "completed_permitted_steps"}),
    "work": ("work_trial_followthrough", {"work_trial_followthrough": "deadline_tracking"}),
    "payment": ("payment_followup", {"payment_followup": "official_earnings_readback"}),
}


def classify_x_source_kind(text: str) -> str:
    """Call an X post firsthand only when it states a personal outcome."""
    value = str(text or "").casefold()
    achieved_outcome = (
        re.search(
            r"\b(?:i|we)\b[^.!?]{0,80}\b(?:got hired|was hired|got an offer|got a contract)\b",
            value,
        )
        or re.search(
            r"\b(?:i|we)\b[^.!?]{0,80}\b(?:received|earned)\b[^.!?]{0,40}\b(?:payout|payment|earnings|income|usd|dollars)\b",
            value,
        )
        or re.search(r"\b(?:my|our)\s+(?:first|latest|actual)?\s*(?:payout|payment|earnings|contract)\b", value)
    )
    return "first_person" if achieved_outcome else "marketing"


def _text(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is required")
    result = value.strip()
    if not result and not allow_empty:
        raise ValueError(f"{name} is required")
    return result


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def build_source_observation(
    *,
    source_url: str,
    source_kind: str,
    observation: str,
    hypothesis: str,
    target_stage: str,
    one_variable: str,
    strategy_version: str,
    baseline_cohort: Mapping[str, Any],
    proposed_change: Mapping[str, Any],
    published_at: str | None,
    observed_at: str,
    author: str,
    claimed_outcome: str,
    evidence_grade: str,
    source_unavailable: bool,
) -> dict[str, Any]:
    """Add provenance to one hypothesis without promoting it to a fact."""
    if published_at is not None:
        _text(published_at, "published_at")
    _text(observed_at, "observed_at")
    _text(author, "author", allow_empty=True)
    _text(claimed_outcome, "claimed_outcome", allow_empty=True)
    grade = _text(evidence_grade, "evidence_grade")
    if grade not in _EVIDENCE_GRADES:
        raise ValueError("unsupported evidence_grade")
    if type(source_unavailable) is not bool:
        raise ValueError("source_unavailable must be boolean")
    if source_unavailable and grade != "unavailable":
        raise ValueError("unavailable source must use unavailable evidence_grade")
    candidate = build_learning_candidate(
        source_url=source_url,
        source_kind=source_kind,
        observation=observation,
        hypothesis=hypothesis,
        target_stage=target_stage,
        one_variable=one_variable,
        strategy_version=strategy_version,
        baseline_cohort=baseline_cohort,
        proposed_change=proposed_change,
    )
    candidate.update({
        "published_at": published_at,
        "observed_at": observed_at,
        "author": author.strip(),
        "claimed_outcome": claimed_outcome.strip(),
        "evidence_grade": grade,
        "source_unavailable": source_unavailable,
    })
    return candidate


def _run(command: list[str], *, timeout: int = 30) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, "", type(error).__name__
    return result.returncode, result.stdout, result.stderr[-500:]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _funnel_context(funnel: Mapping[str, Any] | None) -> dict[str, Any]:
    """Choose the next learning target from measured funnel counts."""
    raw_counts = funnel.get("stage_counts") if isinstance(funnel, Mapping) else None
    counts = {
        stage: (
            value if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            else 0
        )
        for stage in _FUNNEL_STAGES
        for value in [raw_counts.get(stage) if isinstance(raw_counts, Mapping) else 0]
    }
    loss_stage = "application"
    for index, stage in enumerate(_FUNNEL_STAGES):
        if counts[stage] == 0:
            loss_stage = stage
            break
        if index == len(_FUNNEL_STAGES) - 1:
            loss_stage = "retention"
    resolved = funnel.get("resolved") if isinstance(funnel, Mapping) else 0
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved < 0:
        resolved = 0
    if loss_stage == "retention":
        variable, proposed = ("availability", {"availability": "repeat_work_capacity"})
    else:
        variable, proposed = _FUNNEL_VARIABLES[loss_stage]
    return {
        "resolved": resolved,
        "stage_counts": counts,
        "loss_stage": loss_stage,
        "source": str((funnel or {}).get("source") or "mercor-funnel")[:80],
    } | {
        "target_stage": loss_stage,
        "one_variable": variable,
        "proposed_change": proposed,
    }


def _base_kwargs(*, source_url: str, source_kind: str, observed_at: str,
                 observation: str, hypothesis: str, author: str = "",
                 claimed_outcome: str = "", evidence_grade: str,
                 source_unavailable: bool,
                 funnel_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = _funnel_context(funnel_context)
    return dict(
        source_url=source_url,
        source_kind=source_kind,
        observation=observation,
        hypothesis=hypothesis,
        target_stage=context["target_stage"],
        one_variable=context["one_variable"],
        strategy_version=_STRATEGY_VERSION,
        baseline_cohort={
            "resolved": context["resolved"],
            "source": context["source"],
            "stage_counts": context["stage_counts"],
            "loss_stage": context["loss_stage"],
        },
        proposed_change=context["proposed_change"],
        published_at=None,
        observed_at=observed_at,
        author=author,
        claimed_outcome=claimed_outcome,
        evidence_grade=evidence_grade,
        source_unavailable=source_unavailable,
    )


def _unavailable(*, source_url: str, source_kind: str, observed_at: str,
                 reason: str,
                 funnel_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return build_source_observation(**_base_kwargs(
        source_url=source_url,
        source_kind=source_kind,
        observed_at=observed_at,
        observation=f"Source surface unavailable: {reason}.",
        hypothesis="Keep the official Mercor application-order hypothesis until this source is available.",
        evidence_grade="unavailable",
        source_unavailable=True,
        funnel_context=funnel_context,
    ))


def _official_snapshot_funnel(path: Path | None) -> dict[str, Any]:
    """Project only stable metadata from the private official snapshot."""
    if path is None or not Path(path).is_file():
        return {"source": "official-snapshot-unavailable", "resolved": 0, "stage_counts": {}}
    try:
        snapshot = _read_object(Path(path))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"source": "official-snapshot-invalid", "resolved": 0, "stage_counts": {}}

    raw_applications = snapshot.get("applications")
    if isinstance(raw_applications, Mapping):
        raw_applications = raw_applications.get("applications")
    applications = raw_applications if isinstance(raw_applications, list) else []
    application_rows = []
    for row in applications:
        if not isinstance(row, Mapping):
            continue
        identifier = row.get("applicationId") or row.get("id") or row.get("listingId")
        if not isinstance(identifier, str) or not identifier.strip():
            continue
        application_rows.append({
            "application_id": identifier.strip(),
            "listing_id": str(row.get("listingId") or identifier).strip(),
            "status": str(row.get("status") or row.get("next_step") or "submitted"),
            "observed_at": str(row.get("updatedAt") or row.get("appliedAt") or snapshot.get("observed_at") or ""),
            "evidence_ref": str(path),
        })

    raw_notifications = snapshot.get("notifications")
    if isinstance(raw_notifications, Mapping):
        raw_notifications = raw_notifications.get("notifications")
    notifications = raw_notifications if isinstance(raw_notifications, list) else []
    reply_rows = []
    for row in notifications:
        if not isinstance(row, Mapping):
            continue
        identifier = row.get("replyId") or row.get("notificationId") or row.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            continue
        reply_rows.append({
            "reply_id": identifier.strip(),
            "application_id": row.get("applicationId"),
            "listing_id": row.get("listingId"),
            "status": str(row.get("event") or row.get("type") or "received"),
            "observed_at": str(row.get("createdAt") or row.get("occurredAt") or snapshot.get("observed_at") or ""),
            "evidence_ref": str(path),
        })

    contracts = snapshot.get("contracts")
    contract_rows = contracts if isinstance(contracts, list) else []
    work_rows = []
    for row in contract_rows:
        if not isinstance(row, Mapping):
            continue
        identifier = row.get("contractId") or row.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            continue
        work_rows.append({
            "work_id": identifier.strip(),
            "contract_id": identifier.strip(),
            "status": str(row.get("status") or "contracted"),
            "observed_at": str(row.get("updatedAt") or row.get("createdAt") or snapshot.get("observed_at") or ""),
            "evidence_ref": str(path),
        })

    payment_rows = []
    for key in ("payments", "earnings"):
        values = snapshot.get(key)
        if not isinstance(values, list):
            continue
        for row in values:
            if not isinstance(row, Mapping):
                continue
            identifier = row.get("paymentId") or row.get("earningsId") or row.get("id")
            if not isinstance(identifier, str) or not identifier.strip():
                continue
            payment_rows.append({
                "payment_id": identifier.strip(),
                "work_id": row.get("workId"),
                "contract_id": row.get("contractId"),
                "status": str(row.get("status") or "unknown"),
                "amount_usd": row.get("amountUsd"),
                "received": row.get("received") is True,
                "observed_at": str(row.get("updatedAt") or row.get("createdAt") or snapshot.get("observed_at") or ""),
                "evidence_ref": str(path),
            })

    projection = project_funnel(
        application_receipts=application_rows,
        reply_receipts=reply_rows,
        work_receipts=work_rows,
        payment_receipts=payment_rows,
    )
    resolved = sum(
        1 for row in application_rows
        if str(row.get("status") or "").casefold()
        in {"rejected", "not_selected", "declined", "closed", "failed", "accepted", "offer", "contracted"}
    )
    return {
        "source": "official-snapshot",
        "resolved": resolved,
        "stage_counts": projection["stage_counts"],
        "observed_at": snapshot.get("observed_at"),
    }


def collect_sources(*, query: str = _DEFAULT_QUERY,
                    observed_at: str | None = None,
                    funnel: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Fetch one bounded observation from each source surface."""
    timestamp = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    query = _text(query, "query")
    context = _funnel_context(funnel)
    sources: list[dict[str, Any]] = []

    crwl = shutil.which("crwl") or "/Users/anicca/.local/bin/crwl"
    code, stdout, stderr = _run([crwl, "crawl", _OFFICIAL_URL, "-o", "markdown-fit"])
    official_text = stdout.casefold()
    official_ok = code == 0 and stdout.strip() and all(
        marker in official_text for marker in _OFFICIAL_MARKERS
    )
    if official_ok:
        source = build_source_observation(**_base_kwargs(
            source_url=_OFFICIAL_URL,
            source_kind="official_guidance",
            observed_at=timestamp,
            observation="Official guidance was fetched; it documents Job fit/Newest ordering and resume-later behavior.",
            hypothesis="Collect pages one through four before ranking so plausible roles reach the detail budget.",
            author="Mercor",
            claimed_outcome="Guidance only; no hire, contract, or payout claimed.",
            evidence_grade="official",
            source_unavailable=False,
            funnel_context=context,
        ))
        source.update({
            "content_sha256": _sha256_text(stdout),
            "content_bytes": len(stdout.encode()),
        })
        sources.append(source)
    else:
        sources.append(_unavailable(
            source_url=_OFFICIAL_URL, source_kind="official_guidance",
            observed_at=timestamp,
            reason=stderr or ("document_markers_missing" if code == 0 else f"exit_{code}"),
            funnel_context=context,
        ))

    x_script = Path(os.environ.get(
        "MERCOR_X_SEARCH_SCRIPT", "/Users/anicca/.agents/skills/x-search-cdp/x_search.py"
    ))
    uv = shutil.which("uv") or "/opt/homebrew/bin/uv"
    x_url = f"https://x.com/search?q={quote(query)}"
    if x_script.is_file() and Path(uv).exists():
        code, stdout, stderr = _run(
            [uv, "run", str(x_script), query, "--mode", "top", "--count", "5"],
            timeout=60,
        )
        try:
            payload = json.loads(stdout) if code == 0 else {}
        except json.JSONDecodeError:
            payload = {}
        results = payload.get("results") if isinstance(payload, dict) else None
        if isinstance(results, list) and results:
            for item in results[:5]:
                if not isinstance(item, Mapping) or not isinstance(item.get("url"), str):
                    continue
                text = str(item.get("text") or "").strip()[:1000]
                handle = str(item.get("handle") or "").strip()[:200]
                source_kind = classify_x_source_kind(text)
                sources.append(build_source_observation(**_base_kwargs(
                    source_url=item["url"], source_kind=source_kind,
                    observed_at=timestamp,
                    observation=text or "X post text unavailable.",
                    hypothesis="Treat the post as a discovery lead only; compare any claimed funnel outcome with official receipts.",
                    author=handle, claimed_outcome=text,
                    evidence_grade=source_kind, source_unavailable=False,
                    funnel_context=context,
                )))
        else:
            sources.append(_unavailable(
                source_url=x_url, source_kind="first_person",
                observed_at=timestamp, reason=stderr or f"exit_{code}", funnel_context=context,
            ))
    else:
        sources.append(_unavailable(
            source_url=x_url, source_kind="first_person",
            observed_at=timestamp, reason="x_search_dependency_missing",
            funnel_context=context,
        ))

    gh = shutil.which("gh") or "/opt/homebrew/bin/gh"
    gh_code, gh_stdout, gh_stderr = _run(
        [gh, "search", "repos", "mercor jobs", "--limit", "5",
         "--json", "fullName,url,description"],
        timeout=30,
    )
    try:
        repos = json.loads(gh_stdout) if gh_code == 0 else []
    except json.JSONDecodeError:
        repos = []
    if isinstance(repos, list) and repos:
        for repo in repos[:5]:
            if not isinstance(repo, Mapping) or not isinstance(repo.get("url"), str):
                continue
            description = str(repo.get("description") or "").strip()[:500]
            sources.append(build_source_observation(**_base_kwargs(
                source_url=repo["url"], source_kind="code",
                observed_at=timestamp,
                observation=description or "Public Mercor-related repository.",
                hypothesis="Use public code to understand discovery only; never copy token extraction or treat code as a hiring receipt.",
                author=str(repo.get("fullName") or "").strip(),
                claimed_outcome="Code listing only; no verified hire or payout.",
                evidence_grade="code", source_unavailable=False,
                funnel_context=context,
            )))
    else:
        sources.append(_unavailable(
            source_url="https://github.com/search?q=mercor+jobs&type=repositories",
            source_kind="code", observed_at=timestamp,
            reason=gh_stderr or f"exit_{gh_code}",
            funnel_context=context,
        ))

    return {
        "version": 1,
        "query": query,
        "observed_at": timestamp,
        "sources": sources,
        "source_count": len(sources),
        "income_receipts_promoted": 0,
        "funnel_context": context,
    }


def _write_private(path: Path, value: Mapping[str, Any]) -> None:
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("collect",))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--query", default=_DEFAULT_QUERY)
    parser.add_argument("--observed-at")
    parser.add_argument("--official-snapshot", type=Path)
    args = parser.parse_args(argv)
    funnel = _official_snapshot_funnel(args.official_snapshot)
    _write_private(args.output, collect_sources(
        query=args.query, observed_at=args.observed_at, funnel=funnel,
    ))
    print(json.dumps({"status": "success", "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
