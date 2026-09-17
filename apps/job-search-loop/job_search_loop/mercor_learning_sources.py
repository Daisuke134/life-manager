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


_EVIDENCE_GRADES = frozenset({
    "official", "first_person", "marketing", "code", "unavailable",
})
_OFFICIAL_URL = "https://talent.docs.mercor.com/how-to/apply"
_OFFICIAL_MARKERS = (
    "navigate to explore", "job fit", "newest", "submit application", "resume later",
)
_DEFAULT_QUERY = "Mercor Japanese AI evaluator application"
_STRATEGY_VERSION = "mercor-fit-evidence-v1"


def classify_x_source_kind(text: str) -> str:
    """Call an X post firsthand only when it states a personal outcome."""
    value = str(text or "").casefold()
    achieved_outcome = re.search(
        r"\b(?:i|we)\b[^.!?]{0,80}\b(?:got hired|was hired|received|earned|got an offer|got a contract)\b",
        value,
    ) or re.search(r"\b(?:my|our)\s+(?:payout|contract|offer)\b", value)
    return "first_person" if achieved_outcome else "marketing"


def _text(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is required")
    result = value.strip()
    if not result and not allow_empty:
        raise ValueError(f"{name} is required")
    return result


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


def _base_kwargs(*, source_url: str, source_kind: str, observed_at: str,
                 observation: str, hypothesis: str, author: str = "",
                 claimed_outcome: str = "", evidence_grade: str,
                 source_unavailable: bool) -> dict[str, Any]:
    return dict(
        source_url=source_url,
        source_kind=source_kind,
        observation=observation,
        hypothesis=hypothesis,
        target_stage="application",
        one_variable="listing_order",
        strategy_version=_STRATEGY_VERSION,
        baseline_cohort={"resolved": 0, "source": "mercor-funnel"},
        proposed_change={"listing_order": "page_one_to_four"},
        published_at=None,
        observed_at=observed_at,
        author=author,
        claimed_outcome=claimed_outcome,
        evidence_grade=evidence_grade,
        source_unavailable=source_unavailable,
    )


def _unavailable(*, source_url: str, source_kind: str, observed_at: str,
                 reason: str) -> dict[str, Any]:
    return build_source_observation(**_base_kwargs(
        source_url=source_url,
        source_kind=source_kind,
        observed_at=observed_at,
        observation=f"Source surface unavailable: {reason}.",
        hypothesis="Keep the official Mercor application-order hypothesis until this source is available.",
        evidence_grade="unavailable",
        source_unavailable=True,
    ))


def collect_sources(*, query: str = _DEFAULT_QUERY,
                    observed_at: str | None = None) -> dict[str, Any]:
    """Fetch one bounded observation from each source surface."""
    timestamp = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    query = _text(query, "query")
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
                )))
        else:
            sources.append(_unavailable(
                source_url=x_url, source_kind="first_person",
                observed_at=timestamp, reason=stderr or f"exit_{code}",
            ))
    else:
        sources.append(_unavailable(
            source_url=x_url, source_kind="first_person",
            observed_at=timestamp, reason="x_search_dependency_missing",
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
            )))
    else:
        sources.append(_unavailable(
            source_url="https://github.com/search?q=mercor+jobs&type=repositories",
            source_kind="code", observed_at=timestamp,
            reason=gh_stderr or f"exit_{gh_code}",
        ))

    return {
        "version": 1,
        "query": query,
        "observed_at": timestamp,
        "sources": sources,
        "source_count": len(sources),
        "income_receipts_promoted": 0,
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
    args = parser.parse_args(argv)
    _write_private(args.output, collect_sources(query=args.query, observed_at=args.observed_at))
    print(json.dumps({"status": "success", "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
