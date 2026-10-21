#!/usr/bin/env python3
"""Render an evidence-bounded eBook case note or X draft from the intel playbook."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

from intel_store import StoreError, read_jsonl, validate_store


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PLAYBOOK_PATH = HERE / "playbook.jsonl"
CASE_NOTE_PATH = ROOT / "docs/articles/2026-10-21-ai-monk-creator-economy-en.md"
PUBLIC_ARTICLE_LINK = re.compile(
    r"\[published free on Anicca\]\((https://[^\s)]+)\)"
)
URL = re.compile(r"https?://\S+")
X_LIMIT = 280

PROVENANCE_PREFIX = {
    "live_observed": "Observed in public material: ",
    "owner_supplied_summary": "Owner-supplied, not independently verified: ",
    "imported_oss": "Open-source record: ",
}


class CaseStudyError(ValueError):
    """An eBook case is absent or does not meet the evidence contract."""


def load_case(case_id: str, playbook_path: pathlib.Path = PLAYBOOK_PATH) -> dict:
    """Return one schema-valid eBook tactic by exact ID."""
    playbook_path = pathlib.Path(playbook_path)
    validate_store(playbook_path, "playbook")
    rows = read_jsonl(playbook_path)
    row = next((item for item in rows if item["id"] == case_id), None)
    if row is None:
        raise CaseStudyError(f"case ID not found: {case_id}")
    if "ebook" not in row["applies_to"]:
        raise CaseStudyError(f"case {case_id} does not apply to ebook")
    return row


def public_article_url(case_note_path: pathlib.Path = CASE_NOTE_PATH) -> str:
    """Read the canonical free article URL from the public case note."""
    note = pathlib.Path(case_note_path).read_text(encoding="utf-8")
    match = PUBLIC_ARTICLE_LINK.search(note)
    if not match:
        raise CaseStudyError("free Anicca article URL not found in case note")
    return match.group(1)


def _source_lines(row: dict) -> list[str]:
    linked: dict[str, list[str]] = {}
    missing: list[str] = []
    for label, url_field, reason_field in (
        ("Source URL", "source_url", "source_null_reason"),
        ("Evidence URL", "evidence_url", "evidence_null_reason"),
    ):
        url = row[url_field]
        if url:
            linked.setdefault(url, []).append(label)
        else:
            missing.append(f"- {label} unavailable: {row[reason_field]}")
    lines = [f"- {', '.join(labels)}: {url}" for url, labels in linked.items()]
    return lines + missing


def render_article(row: dict, article_url: str) -> str:
    """Render a small Markdown case note without upgrading claims to results."""
    outcome = (
        f"- Anicca result recorded: {row['our_result']}"
        if row["our_result"] is not None
        else "- Anicca result: not recorded."
    )
    result_evidence = (
        f"- Result evidence: {row['result_evidence']}"
        if row["result_evidence"] is not None
        else "- Result evidence: not recorded."
    )
    lines = [
        f"# eBook case note: {row['id']}",
        "",
        f"**Captured:** {row['captured_at']}",
        f"**Claim provenance:** `{row['provenance']}` (`{row['source_type']}`)",
        f"**Status:** `{row['status']}`",
        "",
        "## Claim",
        row["claim"],
        "",
        "## Recorded mechanism",
        row["mechanism"],
        "",
        "## Sources",
        *_source_lines(row),
        "",
        "## Unknowns",
        outcome,
        result_evidence,
        "",
        f"Full Anicca case note: {article_url}",
        "",
    ]
    return "\n".join(lines)


def x_weighted_length(text: str) -> int:
    """Conservatively count X text, treating each URL as its 23-character t.co form."""
    total = 0
    cursor = 0
    for match in URL.finditer(text):
        total += sum(1 if ord(char) < 128 else 2 for char in text[cursor:match.start()])
        total += 23
        cursor = match.end()
    total += sum(1 if ord(char) < 128 else 2 for char in text[cursor:])
    return total


def render_x_post(row: dict, article_url: str) -> str:
    """Render one source-linked, outcome-bounded X draft; never publishes it."""
    prefix = PROVENANCE_PREFIX[row["provenance"]]
    source_urls = list(dict.fromkeys(
        url for url in (row["source_url"], row["evidence_url"]) if url
    ))
    result_note = (
        f"Anicca result: {row['our_result']}."
        if row["our_result"] is not None
        else "No Anicca result is recorded."
    )
    parts = [prefix + row["claim"].strip()]
    if source_urls:
        parts.append(f"Sources: {' '.join(source_urls)}")
    parts.extend((result_note, f"Free Anicca case note: {article_url}"))
    draft = " ".join(parts)
    weighted_length = x_weighted_length(draft)
    if weighted_length > X_LIMIT:
        raise CaseStudyError(
            f"X draft is {weighted_length} weighted characters; limit is {X_LIMIT}"
        )
    return draft + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--format", choices=("article", "x-post"), required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        row = load_case(args.case_id)
        article_url = public_article_url()
        rendered = (
            render_article(row, article_url)
            if args.format == "article"
            else render_x_post(row, article_url)
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    except (OSError, StoreError, CaseStudyError) as exc:
        print(f"ebook_case_study: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
