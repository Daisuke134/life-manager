#!/usr/bin/env python3
"""Write cited, open Marketing Engine content tactics as optional Writer context."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
from pathlib import Path


TACTIC_ID = re.compile(r"tactic\.[a-zA-Z0-9._-]+\Z")


def _jsonl(path: Path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _source_url(value):
    if not isinstance(value, str) or any(char.isspace() for char in value):
        return None
    parsed = urllib.parse.urlsplit(value)
    return value if parsed.scheme == "https" and parsed.netloc else None


def _one_line(value):
    return " ".join(str(value or "").split())


def write_content_strategy_context(skill_dir: Path, state_dir: Path):
    skill_dir = Path(skill_dir).resolve()
    state_dir = Path(state_dir)
    intel_dir = skill_dir.parent / "earn" / "marketing-engine" / "intel"
    playbook_path = intel_dir / "playbook.jsonl"
    if not playbook_path.is_file():
        raise FileNotFoundError(f"Marketing Engine playbook is missing: {playbook_path}")

    enrichments = {}
    for row in _jsonl(intel_dir / "source-enrichments.jsonl"):
        tactic_id = row.get("tactic_id")
        url = _source_url(row.get("source_url"))
        if tactic_id and url:
            enrichments.setdefault(tactic_id, url)

    candidates = []
    candidate_ids = set()
    for row in _jsonl(playbook_path):
        applies_to = row.get("applies_to")
        tactic_id = row.get("id")
        if (
            not isinstance(tactic_id, str)
            or not TACTIC_ID.fullmatch(tactic_id)
            or row.get("testable") is not True
            or row.get("status") not in {"new", "queued"}
            or not isinstance(applies_to, list)
            or "content" not in applies_to
            or tactic_id in candidate_ids
        ):
            continue
        url = (
            _source_url(row.get("evidence_url"))
            or _source_url(row.get("source_url"))
            or enrichments.get(tactic_id)
        )
        claim = row.get("claim")
        claim = _one_line(claim) if isinstance(claim, str) else ""
        if not url or not claim:
            continue
        candidates.append(
            {
                "id": tactic_id,
                "claim": claim,
                "mechanism": _one_line(row.get("mechanism")),
                "url": url,
            }
        )
        candidate_ids.add(tactic_id)

    context_dir = state_dir / "strategy-context"
    if context_dir.is_symlink():
        raise ValueError(f"Marketing Intel context directory is a symlink: {context_dir}")
    context_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if context_dir.is_symlink() or not context_dir.is_dir():
        raise ValueError(f"Marketing Intel context path is not a directory: {context_dir}")
    destination = context_dir / "marketing-intel.md"
    if destination.is_symlink():
        raise ValueError(f"Marketing Intel context file is a symlink: {destination}")

    lines = [
        "# Optional Marketing Engine content strategy context",
        "",
        "These externally sourced claims are unverified hypotheses, not proof of effectiveness or revenue.",
        "The validated paid-demand topic remains Writer's only topic and demand authority.",
        "",
        "## Open cited tactics",
    ]
    if not candidates:
        lines.extend(["", "No open source-cited content tactics currently qualify."])
    for row in candidates:
        lines.extend(
            [
                "",
                f"### {row['id']}",
                f"- Source claim: {row['claim']}",
                f"- Mechanism hypothesis: {row['mechanism']}",
                f"- Source: {row['url']}",
            ]
        )
    lines.append("")

    temporary = context_dir / f".marketing-intel.{os.getpid()}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "context_file": "strategy-context/marketing-intel.md",
        "tactic_ids": [row["id"] for row in candidates],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-dir", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    context = write_content_strategy_context(args.skill_dir, args.state_dir)
    print(json.dumps(context, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
