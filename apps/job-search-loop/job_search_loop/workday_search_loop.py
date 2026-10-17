from __future__ import annotations

import argparse
import json
import os
import uuid
from collections import Counter, deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .agent_runner import AgentRunner
from .application_reporting import deliver_fit_decision
from .ats import detect_provider
from .ledger import Ledger
from .state import canonical_url, is_excluded_employer, same_application_surface
from .workday_discovery import _fetch_jobs, discover_one
from .workday_qualification import POLICY_VERSION, fetch_official_description, qualify_one
from .browser_agent.workday_account import MachineWorkdayCredentialStore

PRIORITY_WINDOW_SIZE = 24
ROLLING_APPLICATION_TARGET = 48


def normalize_company_name(value: str) -> str:
    return str(value).strip().casefold()


def rolling_submission_metrics(
    ledger_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must include a timezone")
    current = current.astimezone(timezone.utc)
    cutoff = (current - timedelta(hours=24)).isoformat()
    ledger = Ledger(ledger_path)
    try:
        row = ledger.connection.execute(
            """
            SELECT COUNT(DISTINCT submission_confirmations.intent_id)
            FROM submission_confirmations
            JOIN submit_intents
              ON submit_intents.intent_id = submission_confirmations.intent_id
            WHERE datetime(submission_confirmations.received_at) >= datetime(?)
              AND datetime(submission_confirmations.received_at) <= datetime(?)
            """,
            (cutoff, current.isoformat()),
        ).fetchone()
    finally:
        ledger.close()
    confirmed_count = int(row[0] or 0)
    return {
        "target": ROLLING_APPLICATION_TARGET,
        "confirmed_count": confirmed_count,
        "deficit": max(0, ROLLING_APPLICATION_TARGET - confirmed_count),
    }


def rotated_sources(
    sources: tuple[dict[str, str], ...], index: int
) -> tuple[dict[str, str], ...]:
    if not sources:
        return ()
    offset = index % len(sources)
    return sources[offset:] + sources[:offset]


def unique_sources(
    sources: tuple[dict[str, str], ...],
) -> tuple[dict[str, str], ...]:
    unique = []
    seen = set()
    for source in sources:
        key = (source["host"].casefold(), source["tenant"], source["site"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)
    return tuple(unique)


def qualified_queue_ids(
    ledger_path: Path,
    allowed_hosts: set[str],
    *,
    policy_version: str = POLICY_VERSION,
) -> tuple[str, ...]:
    ledger = Ledger(ledger_path)
    credential_path = os.environ.get("JOB_SEARCH_MACHINE_CREDENTIALS")
    credentials = (
        MachineWorkdayCredentialStore(Path(credential_path)) if credential_path else None
    )
    try:
        rows = (
            *((row, False) for row in ledger.pending_materials_ready_applications()),
            *((row, True) for row in ledger.retryable_applications()),
        )
        return tuple(
            dict.fromkeys(
                str(row["application_id"])
                for row, retryable in rows
                if detect_provider(str(row["canonical_url"])) == "workday"
                and (
                    retryable
                    or (urlsplit(str(row["canonical_url"])).hostname or "").casefold()
                    in allowed_hosts
                )
                and (
                    credentials is None
                    or credentials.account_status(str(row["canonical_url"]))
                    != "recovery_requested"
                )
                and ledger.workday_fit_qualified(
                    str(row["application_id"]), policy_version
                )
            )
        )
    finally:
        ledger.close()


def cached_source_fetcher(
    fetch: Callable[[dict[str, str]], list[dict[str, Any]]],
    cache: dict[str, list[dict[str, Any]]] | None = None,
) -> Callable[[dict[str, str]], list[dict[str, Any]]]:
    values = cache if cache is not None else {}

    def cached(source: dict[str, str]) -> list[dict[str, Any]]:
        key = json.dumps(source, ensure_ascii=False, sort_keys=True)
        if key not in values:
            values[key] = fetch(source)
        return values[key]

    return cached


def reject_stale_workday_rows(
    ledger_path: Path,
    jobs_by_source: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, str], ...]:
    current_urls_by_source: dict[tuple[str, str, str], set[str]] = {}
    for key, jobs in jobs_by_source.items():
        try:
            source = json.loads(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(source, dict):
            continue
        host = str(source.get("host") or "").strip().casefold()
        tenant = str(source.get("tenant") or "").strip().casefold()
        site = str(source.get("site") or "").strip("/")
        if not host or not tenant or not site or not isinstance(jobs, list) or not jobs:
            continue
        source_key = (host, tenant, site.casefold())
        urls: set[str] = set()
        for job in jobs:
            if not isinstance(job, dict):
                continue
            path = str(job.get("externalPath") or "")
            if not path.startswith("/job/"):
                continue
            urls.add(canonical_url(f"https://{host}/{site}{path}"))
        if urls:
            current_urls_by_source.setdefault(source_key, set()).update(urls)

    receipt: list[dict[str, str]] = []
    ledger = Ledger(ledger_path)
    try:
        for row in ledger.pending_materials_ready_applications():
            url = canonical_url(str(row["canonical_url"]))
            parsed = urlsplit(url)
            host = (parsed.hostname or "").casefold()
            segments = tuple(part for part in parsed.path.split("/") if part)
            job_index = next(
                (index for index, part in enumerate(segments) if part.casefold() == "job"),
                -1,
            )
            if job_index < 1:
                continue
            site = segments[job_index - 1].casefold()
            matching_sources = [
                urls
                for (source_host, _tenant, source_site), urls in current_urls_by_source.items()
                if source_host == host and source_site == site
            ]
            if len(matching_sources) != 1 or any(
                same_application_surface(url, current_url)
                for current_url in matching_sources[0]
            ):
                continue
            ledger.transition(
                str(row["application_id"]),
                "rejected",
                {"reason": "official_listing_absent"},
            )
            receipt.append(
                {
                    "application_id": str(row["application_id"]),
                    "company": str(row["company"]),
                    "title": str(row["title"]),
                    "canonical_url": url,
                    "reason": "official_listing_absent",
                }
            )
    finally:
        ledger.close()
    return tuple(receipt)


def qualify_with_wake_cursor(
    qualify: Callable[[frozenset[str]], dict[str, Any]],
    failed_ids: set[str],
) -> dict[str, Any]:
    decision = qualify(frozenset(failed_ids))
    if decision.get("status") == "qualification_retryable_failure":
        application_id = decision.get("application_id")
        if application_id:
            failed_ids.add(str(application_id))
    return decision


def snapshot_candidates(
    *,
    ledger_path: Path,
    sources: tuple[dict[str, str], ...],
    fetch_jobs: Callable[[dict[str, str]], list[dict[str, Any]]],
    exclusions: frozenset[str] = frozenset(),
) -> list[dict[str, str]]:
    ledger = Ledger(ledger_path)
    try:
        seen = {
            canonical_url(str(row["canonical_url"])).casefold()
            for row in ledger.connection.execute(
                """
                SELECT applications.canonical_url
                FROM applications
                LEFT JOIN submit_intents
                  ON submit_intents.application_id = applications.id
                LEFT JOIN workday_fit_decisions
                  ON workday_fit_decisions.application_id = applications.id
                WHERE NOT (
                  applications.current_state = 'materials_ready'
                  AND submit_intents.application_id IS NULL
                  AND (
                    workday_fit_decisions.application_id IS NULL
                    OR workday_fit_decisions.decision = 'hold'
                  )
                )
                """
            )
        }
        unfinished_urls = {
            canonical_url(str(row["canonical_url"])).casefold()
            for row in ledger.pending_materials_ready_applications()
            if canonical_url(str(row["canonical_url"])).casefold() not in seen
        }
    finally:
        ledger.close()
    candidates = []
    for source in sources:
        if is_excluded_employer(source["company"], exclusions):
            continue
        try:
            jobs = fetch_jobs(source)
        except Exception:
            continue
        for job in jobs:
            title = " ".join(str(job.get("title") or "").split())
            location = " ".join(str(job.get("locationsText") or "").split())
            path = str(job.get("externalPath") or "")
            if not title or not path.startswith("/job/"):
                continue
            url = canonical_url(f"https://{source['host']}/{source['site']}{path}")
            if url.casefold() in seen:
                continue
            candidates.append(
                {
                    "company": source["company"],
                    "title": title,
                    "location": location,
                    "url": url,
                }
            )
    unfinished_candidates = [
        row for row in candidates if row["url"].casefold() in unfinished_urls
    ]
    if not unfinished_candidates:
        return candidates
    if len(unfinished_candidates) >= 400:
        return unfinished_candidates
    fresh_candidates = [
        row for row in candidates if row["url"].casefold() not in unfinished_urls
    ]
    return unfinished_candidates + interleave_companies(fresh_candidates)[
        : 400 - len(unfinished_candidates)
    ]


def interleave_companies(
    candidates: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Keep each ranking window company-diverse without deciding candidate fit."""
    buckets: dict[str, deque[dict[str, str]]] = {}
    order: list[str] = []
    for row in candidates:
        key = normalize_company_name(
            row.get("company")
            or urlsplit(str(row.get("url") or "")).hostname
            or "unknown"
        )
        if key not in buckets:
            buckets[key] = deque()
            order.append(key)
        buckets[key].append(row)
    result: list[dict[str, str]] = []
    while any(buckets[key] for key in order):
        for key in order:
            if buckets[key]:
                result.append(buckets[key].popleft())
    return result


def priority_candidate_urls(
    candidates: list[dict[str, str]],
    company_exposure: dict[str, int],
    *,
    limit: int = PRIORITY_WINDOW_SIZE,
) -> tuple[str, ...]:
    """Prefer companies with fewer prior submit attempts, then interleave fairly."""
    if limit < 1:
        raise ValueError("limit must be positive")
    exposure_by_company: Counter[str] = Counter()
    for company, attempts in company_exposure.items():
        if isinstance(attempts, int) and not isinstance(attempts, bool) and attempts > 0:
            exposure_by_company[normalize_company_name(company)] += attempts
    ordered = sorted(
        candidates,
        key=lambda row: exposure_by_company.get(
            normalize_company_name(str(row.get("company") or "")), 0
        ),
    )
    diversified = interleave_companies(ordered)
    return tuple(str(row["url"]) for row in diversified[:limit])


def company_submit_attempt_exposure(ledger_path: Path) -> dict[str, int]:
    ledger = Ledger(ledger_path)
    try:
        rows = ledger.connection.execute(
            """
            SELECT company
            FROM (
                SELECT DISTINCT applications.id, applications.company
                FROM applications
                JOIN submit_intents
                  ON submit_intents.application_id = applications.id
                WHERE applications.current_state IN
                        ('submit_claimed', 'submit_unknown', 'submitted')
                  AND submit_intents.status IN
                        ('submit_claimed', 'submit_unknown', 'submitted')
            )
            """
        ).fetchall()
    finally:
        ledger.close()
    return dict(Counter(str(row[0]) for row in rows))


def submit_attempt_hosts(ledger_path: Path) -> frozenset[str]:
    ledger = Ledger(ledger_path)
    try:
        rows = ledger.connection.execute(
            """
            SELECT DISTINCT applications.canonical_url
            FROM applications
            JOIN submit_intents
              ON submit_intents.application_id = applications.id
            WHERE submit_intents.status IN
                ('submit_claimed', 'submit_unknown', 'submitted')
            """
        ).fetchall()
    finally:
        ledger.close()
    hosts = {
        (urlsplit(str(row[0])).hostname or "").strip().casefold()
        for row in rows
    }
    return frozenset(host for host in hosts if host)


def filter_submit_attempt_sources(
    sources: tuple[dict[str, str], ...], attempted_hosts: set[str] | frozenset[str]
) -> tuple[dict[str, str], ...]:
    normalized_hosts = {
        str(host).strip().casefold() for host in attempted_hosts
    }
    return tuple(
        source
        for source in sources
        if str(source["host"]).strip().casefold() not in normalized_hosts
    )


def candidate_employer_exclusions(candidate_memory_path: Path) -> frozenset[str]:
    value = json.loads(candidate_memory_path.read_text(encoding="utf-8"))
    for concept in value.get("concepts", []):
        if concept.get("concept") == "candidate.employer_exclusions":
            exclusions = concept.get("value")
            if not isinstance(exclusions, list) or any(
                not isinstance(item, str) or not item.strip() for item in exclusions
            ):
                raise ValueError("candidate employer exclusions are invalid")
            return frozenset(item.strip() for item in exclusions)
    return frozenset()


def search_until_qualified(
    *,
    discover: Callable[[], dict[str, Any]],
    qualify: Callable[[], dict[str, Any]],
    max_candidates: int,
    target_qualified: int | None = None,
) -> dict[str, Any]:
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    target = 1 if target_qualified is None else int(target_qualified)
    if target < 0:
        raise ValueError("target_qualified must be nonnegative")
    target = min(target, max_candidates)
    discoveries = []
    decisions = []
    qualified_application_ids: list[str] = []
    qualified_seen: set[str] = set()
    sources_exhausted = False
    if target == 0:
        return {
            "status": "deficit_satisfied",
            "discoveries": discoveries,
            "decisions": decisions,
            "qualified_application_ids": qualified_application_ids,
        }
    for _ in range(max_candidates):
        if not sources_exhausted:
            discovery = discover()
            discoveries.append(discovery)
            sources_exhausted = discovery.get("status") == "no_fresh_workday"
        try:
            decision = qualify()
        except Exception as error:
            decisions.append(
                {
                    "status": "qualification_retryable_failure",
                    "error": type(error).__name__,
                }
            )
            continue
        decisions.append(decision)
        if decision.get("decision") == "qualified":
            application_id = decision.get("application_id")
            if application_id:
                application_id = str(application_id)
                if application_id not in qualified_seen:
                    qualified_seen.add(application_id)
                    qualified_application_ids.append(application_id)
            if len(qualified_application_ids) >= target:
                return {
                    "status": "qualified",
                    "discoveries": discoveries,
                    "decisions": decisions,
                    "qualified_application_ids": qualified_application_ids,
                }
        if decision.get("status") == "no_pending_workday_fit":
            return {
                "status": "sources_exhausted",
                "discoveries": discoveries,
                "decisions": decisions,
                "qualified_application_ids": qualified_application_ids,
            }
    return {
        "status": "budget_exhausted",
        "discoveries": discoveries,
        "decisions": decisions,
        "qualified_application_ids": qualified_application_ids,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--candidate-memory", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--max-candidates", type=int, default=8)
    args = parser.parse_args()
    runner = AgentRunner(evidence_root=args.evidence_root, runner_path=args.runner)
    source_payload = json.loads(args.sources.read_text(encoding="utf-8"))
    sources = unique_sources(
        tuple(dict(row) for row in source_payload.get("sources", []))
    )
    employer_exclusions = candidate_employer_exclusions(args.candidate_memory)
    company_exposure = company_submit_attempt_exposure(args.ledger)
    attempted_hosts = submit_attempt_hosts(args.ledger)
    sources = filter_submit_attempt_sources(sources, attempted_hosts)
    sources = tuple(
        source
        for source in sources
        if not is_excluded_employer(source["company"], employer_exclusions)
    )
    allowed_hosts = {str(row["host"]).casefold() for row in sources}
    source_cursor = 0
    jobs_by_source: dict[str, list[dict[str, Any]]] = {}
    fetch_jobs = cached_source_fetcher(_fetch_jobs, jobs_by_source)
    candidates = snapshot_candidates(
        ledger_path=args.ledger,
        sources=sources,
        fetch_jobs=fetch_jobs,
        exclusions=employer_exclusions,
    )
    snapshot = {
        "version": 1,
        "sources": [
            {"source": json.loads(key), "jobs": jobs}
            for key, jobs in jobs_by_source.items()
        ],
    }
    args.snapshot.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.snapshot.write_text(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(args.snapshot, 0o600)
    stale_rows = reject_stale_workday_rows(args.ledger, jobs_by_source)
    queued_ids = qualified_queue_ids(
        args.ledger, allowed_hosts, policy_version=POLICY_VERSION
    )
    rolling = rolling_submission_metrics(args.ledger)
    # Keep durable queued rows in the result, but do not let them suppress fresh
    # qualification: a materials-ready row can remain blocked on a required fact.
    preferred_urls: tuple[str, ...] = ()
    if candidates:
        preferred_urls = priority_candidate_urls(
            candidates,
            company_exposure,
        )

    def discover_next() -> dict[str, Any]:
        nonlocal source_cursor
        ordered = rotated_sources(sources, source_cursor)
        source_cursor += 1
        return discover_one(
            ledger_path=args.ledger,
            sources=ordered,
            fetch_jobs=fetch_jobs,
            preferred_urls=preferred_urls,
            prefer_fresh=True,
        )

    wake_failed_ids: set[str] = set()

    def qualify_next() -> dict[str, Any]:
        decision = qualify_with_wake_cursor(
            lambda excluded_application_ids: qualify_one(
                ledger_path=args.ledger,
                candidate_memory_path=args.candidate_memory,
                fetch_description=lambda url: fetch_official_description(url, sources),
                run_model=lambda prompt: runner.run(
                    task="improve",
                    prompt=prompt,
                    schema_path=args.schema,
                    workdir=args.workdir,
                    run_id=f"workday-fit-{uuid.uuid4().hex}",
                ),
                allowed_hosts=allowed_hosts,
                excluded_application_ids=excluded_application_ids,
                preferred_urls=preferred_urls,
            ),
            wake_failed_ids,
        )
        if decision.get("status") == "decided":
            try:
                delivery = deliver_fit_decision(
                    decision=decision,
                    outbox_path=args.ledger.parent / "telegram-outbox.sqlite3",
                )
                decision["telegram_message_id"] = delivery.get("message_id")
                decision["telegram_status"] = delivery.get("status")
            except Exception as error:
                decision["telegram_status"] = "failed"
                decision["telegram_error"] = type(error).__name__
        return decision

    result = search_until_qualified(
        discover=discover_next,
        qualify=qualify_next,
        max_candidates=args.max_candidates,
        target_qualified=min(1, rolling["deficit"], args.max_candidates),
    )
    result["stale_rows"] = list(stale_rows)
    result["discovered"] = [
        row
        for discovery in result["discoveries"]
        for row in discovery.get("discovered", [])
    ]
    result["shortlist"] = list(preferred_urls)
    newly_qualified = list(result.get("qualified_application_ids") or [])
    result["queued_application_ids"] = list(
        dict.fromkeys(newly_qualified + list(queued_ids))
    )
    result.update(rolling)
    result["remaining_deficit"] = rolling["deficit"]
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
