"""Bounded, deterministic Ashby discovery from the official ATS cache.

The cache seeds board identities; only fresh official posting API rows enter the
queue. The existing browser model decides candidate eligibility from the live
posting and grounded facts before the shared, fenced submission path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .ledger import Ledger
from .learning import LearningDriver
from .resume_routing import select_resume
from .state import canonical_url, is_excluded_employer


ROLE_RE = re.compile(
    r"ai|agent|machine learning|\bml\b|simulation|solutions|technical|customer success|"
    r"product|partnership|sales engineer|professional services|ecosystem sales|forward deployed",
    re.IGNORECASE,
)
JAPAN_RE = re.compile(r"tokyo|japan", re.IGNORECASE)
ASHBY_RE = re.compile(r"https://(?:jobs|app)\.ashbyhq\.com/[^/]+/[^/?#]+", re.IGNORECASE)


def _read_jobs(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    jobs = value.get("jobs") if isinstance(value, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("official ATS cache has no jobs array")
    return [job for job in jobs if isinstance(job, dict)]


def _role_family(title: str) -> str:
    return "technical_business" if re.search(
        r"solutions|customer success|partnership|sales|product", title, re.IGNORECASE
    ) else "applied_ai"


def _role_priority(title: str) -> int:
    value = title.casefold()
    if "forward deployed" in value or "solutions engineer" in value:
        return 5
    if "customer success" in value or "technical account" in value:
        return 4
    if "sales engineer" in value or "solutions" in value:
        return 3
    if "product manager" in value or "product management" in value:
        return 2
    return 1


def _board_slug(url: str) -> str:
    parts = urlsplit(url).path.strip("/").split("/")
    return parts[0] if len(parts) >= 2 else ""


def _candidate_jobs(
    jobs: list[dict[str, Any]], seen: set[str], limited_boards: set[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for job in jobs:
        company = str(job.get("company") or "").strip()
        title = str(job.get("title") or "").strip()
        url = canonical_url(str(job.get("url") or ""))
        location = " ".join(
            [str(job.get("location") or ""), *[str(x) for x in (job.get("secondary_locations") or [])]]
        )
        if str(job.get("ats") or "").casefold() != "ashby":
            continue
        if job.get("isListed") is False:
            continue
        if not company or not title or not ASHBY_RE.fullmatch(url):
            continue
        if (
            is_excluded_employer(company)
            or url.casefold() in seen
            or _board_slug(url).casefold() in limited_boards
        ):
            continue
        if not ROLE_RE.search(title):
            continue
        rows.append({**job, "company": company, "title": title, "url": url})
    rows.sort(
        key=lambda row: (
            _role_priority(str(row.get("title") or "")),
            int(row.get("posted_at_ms") or 0),
        ),
        reverse=True,
    )
    return rows


def _board_slugs(jobs: list[dict[str, Any]]) -> list[tuple[str, str]]:
    boards: dict[str, tuple[str, bool]] = {}
    for job in jobs:
        if str(job.get("ats") or "").casefold() != "ashby":
            continue
        if is_excluded_employer(str(job.get("company") or "")):
            continue
        if not ROLE_RE.search(str(job.get("title") or "")):
            continue
        location = " ".join(
            [str(job.get("location") or ""), *[str(x) for x in (job.get("secondary_locations") or [])]]
        )
        path = urlsplit(str(job.get("url") or "")).path.strip("/").split("/")
        if len(path) < 2 or not path[0]:
            continue
        slug = path[0]
        japan_priority = bool(JAPAN_RE.search(location))
        current = boards.get(slug)
        if current is None or (japan_priority and not current[1]):
            boards[slug] = (str(job.get("company") or slug), japan_priority)
    return [
        (slug, company)
        for slug, (company, _japan_priority) in sorted(
            boards.items(), key=lambda item: (not item[1][1], item[0])
        )
    ]


def _posted_at_ms(value: Any) -> int:
    if not isinstance(value, str):
        return 0
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return 0


def _live_board_jobs(slug: str, company: str) -> list[dict[str, Any]]:
    request = Request(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
        headers={"User-Agent": "Mozilla/5.0 job-search-loop/1.0", "Accept": "application/json"},
    )
    with urlopen(request, timeout=15) as response:
        value = json.load(response)
    source = value.get("jobs") if isinstance(value, dict) else None
    if not isinstance(source, list):
        return []
    rows: list[dict[str, Any]] = []
    for job in source:
        if not isinstance(job, dict):
            continue
        rows.append(
            {
                "ats": "ashby",
                "company": company,
                "title": job.get("title"),
                "url": job.get("jobUrl"),
                "location": job.get("location"),
                "secondary_locations": job.get("secondaryLocations") or [],
                "is_remote": job.get("isRemote") is True,
                "isListed": job.get("isListed"),
                "description": job.get("descriptionPlain") or "",
                "posted_at_ms": _posted_at_ms(job.get("publishedAt")),
            }
        )
    return rows


def _refresh_cursor(path: Path, count: int) -> int:
    if count <= 0:
        return 0
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return int(value.get("next_index", 0)) % count
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def _save_refresh_cursor(path: Path, next_index: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps({"version": 1, "next_index": next_index}) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _blocked_boards(path: Path) -> set[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return set()
    boards = value.get("boards") if isinstance(value, dict) else []
    return {str(board).casefold() for board in boards if isinstance(board, str)}


def _fresh_jobs(
    cached_jobs: list[dict[str, Any]], refresh_state: Path, board_batch: int
) -> tuple[list[dict[str, Any]], list[str], int, list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    boards = _board_slugs(cached_jobs)
    if not boards:
        return rows, errors, 0, []
    batch = max(1, min(board_batch, len(boards)))
    start = _refresh_cursor(refresh_state, len(boards))
    selected = [boards[(start + offset) % len(boards)] for offset in range(batch)]
    for slug, company in selected:
        try:
            rows.extend(_live_board_jobs(slug, company))
        except Exception as error:
            errors.append(f"{slug}:{type(error).__name__}")
    _save_refresh_cursor(refresh_state, (start + batch) % len(boards))
    return rows, errors, len(boards), [slug for slug, _company in selected]


def discover_one(
    *,
    cache_path: Path,
    ledger_path: Path,
    profile_path: Path,
    materials_root: Path,
    prompt_path: Path,
    refresh_state: Path,
    board_batch: int,
    board_blocker_state: Path,
    max_jobs: int = 1,
) -> dict[str, Any]:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    ledger = Ledger(ledger_path)
    try:
        exclusions = profile.get("candidate", {}).get("employer_exclusions", [])
        ledger.reject_excluded_employers(
            frozenset(str(value) for value in exclusions)
            if isinstance(exclusions, list)
            else None
        )
        seen = {
            str(row[0]).casefold()
            for row in ledger.connection.execute("SELECT canonical_url FROM applications")
        }
        limited_boards = {
            _board_slug(str(row[0])).casefold()
            for row in ledger.connection.execute(
                """
                SELECT applications.canonical_url
                FROM applications
                JOIN events ON events.application_id = applications.id
                WHERE events.payload_json LIKE '%provider_application_limit_visible%'
                """
            )
            if _board_slug(str(row[0]))
        }
        limited_boards.update(_blocked_boards(board_blocker_state))
        cached_jobs = _read_jobs(cache_path)
        live_jobs, refresh_errors, board_count, queried_boards = _fresh_jobs(
            cached_jobs, refresh_state, board_batch
        )
        private_exclusions = frozenset(str(value) for value in exclusions) if isinstance(exclusions, list) else frozenset()
        jobs = _candidate_jobs(
            [job for job in live_jobs if not is_excluded_employer(str(job.get("company") or ""), private_exclusions)],
            seen, limited_boards,
        )
        baseline = json.loads(
            (Path(__file__).resolve().parents[1] / "config" / "strategy.default.json").read_text()
        )
        replay = json.loads(
            (Path(__file__).resolve().parents[1] / "config" / "learning-replay.v1.json").read_text()
        )["cases"]
        driver = LearningDriver(ledger, baseline_strategy=baseline, replay_cases=replay)
        prompt_sha256 = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
        discovered: list[dict[str, Any]] = []
        for job in jobs[: max(0, max_jobs)]:
            posting = str(job.get("description") or job.get("descriptionPlain") or "")
            role_family = _role_family(str(job["title"]))
            routed = select_resume(
                posting_text=posting,
                role_family=role_family,
                materials_root=materials_root,
            )
            assignment = driver.assign(str(job["url"]))
            application_id = ledger.add_attributed_application(
                str(job["company"]),
                str(job["title"]),
                str(job["url"]),
                strategy_generation_id=assignment["strategy_generation_id"],
                source="official_ats",
                query_family="official_ashby_tokyo_discovery",
                rank_config=assignment["strategy"],
                role_family=role_family,
                material_variant=routed["resume_variant"],
                message_variant="none",
                model_route="codex",
                prompt_sha256=prompt_sha256,
                material_sha256=routed["resume_sha256"],
            )
            ledger.transition(application_id, "qualified")
            ledger.transition(application_id, "materials_ready")
            discovered.append(
                {
                    "application_id": application_id,
                    "company": str(job["company"]),
                    "title": str(job["title"]),
                    "url": str(job["url"]),
                    "state": "materials_ready",
                }
            )
        return {
            "status": "discovered" if discovered else "no_work",
            "discovered": discovered,
            "live_board_count": board_count,
            "queried_boards": queried_boards,
            "live_refresh_errors": refresh_errors,
            "provider_limited_boards": sorted(limited_boards),
        }
    finally:
        ledger.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--materials-root", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument(
        "--refresh-state",
        type=Path,
        default=Path.home() / ".local/state/anicca/job-search/ashby-live-board-cursor.json",
    )
    parser.add_argument("--board-batch", type=int, default=12)
    parser.add_argument(
        "--board-blocker-state",
        type=Path,
        default=Path.home() / ".local/state/anicca/job-search/ashby-board-blockers.json",
    )
    args = parser.parse_args()
    result = discover_one(
        cache_path=args.cache,
        ledger_path=args.ledger,
        profile_path=args.profile,
        materials_root=args.materials_root,
        prompt_path=args.prompt,
        refresh_state=args.refresh_state,
        board_batch=args.board_batch,
        board_blocker_state=args.board_blocker_state,
        max_jobs=args.max_jobs,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    os.chmod(args.output, 0o600)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
