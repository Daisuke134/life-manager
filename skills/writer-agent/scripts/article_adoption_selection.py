#!/usr/bin/env python3
"""Select one safe prepublication adoption candidate for Writer resume."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ALLOWED_STATUSES = {"provider-failed-ambiguous", "quality-repair-ready"}
RUN_ID_RE = re.compile(r"(?:daily-\d{4}-\d{2}-\d{2}|\d{8}-\d{6})")


def _status(runs: Path, run_id: str) -> str | None:
    if not RUN_ID_RE.fullmatch(run_id):
        return None
    run_dir = runs / run_id
    state_path = run_dir / "gates/generation-state.json"
    prompt = run_dir / "article-daily-prompt.txt"
    if state_path.is_symlink() or prompt.is_symlink():
        raise ValueError("adoption evidence is not regular")
    if not state_path.is_file() or not prompt.is_file():
        return None
    value = json.loads(state_path.read_text(encoding="utf-8"))
    return value.get("status")


def _publication_complete(runs: Path, run_id: str) -> bool:
    """Exclude a generation-repair marker whose publication contract is terminal."""
    path = runs / run_id / "gates/publication-state.json"
    if path.is_symlink() or not path.is_file():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    pairs = value.get("pairs")
    if not isinstance(pairs, dict):
        return False
    if value.get("publication_contract") == "legacy-exact8":
        required = [
            "note/ja",
            "zenn-article/ja",
            "devto/en",
            "substack/ja",
            "substack/en",
            "x-article/ja",
            "x-article/en",
            "x-post/ja",
        ]
    else:
        required = ["note/ja", "substack/ja", "substack/en", "x-article/ja"]
    return all(
        isinstance(pairs.get(pair), dict)
        and pairs[pair].get("status") == "live"
        and isinstance(pairs[pair].get("receipt", {}).get("live_url"), str)
        and pairs[pair]["receipt"]["live_url"].startswith("https://")
        for pair in required
    )


def _has_completed_publication(runs: Path) -> bool:
    for path in runs.glob("*/gates/publication-state.json"):
        run_id = path.parent.parent.name
        if _publication_complete(runs, run_id):
            return True
    return False


def select(state_root: Path, ledger: Path, decision: dict) -> str | None:
    runs = state_root / "runs"
    selected = decision.get("run_id")
    if isinstance(selected, str) and _status(runs, selected) in ALLOWED_STATUSES:
        return selected

    ledger_ids: set[str] = set()
    if ledger.is_file() and not ledger.is_symlink():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            run_id = row.get("run_id") if isinstance(row, dict) else None
            if isinstance(run_id, str) and run_id:
                ledger_ids.add(run_id)
    completed_publication_exists = _has_completed_publication(runs)
    candidates = sorted(
        run_id
        for run_id in ledger_ids
        if _status(runs, run_id) in ALLOWED_STATUSES
        and not _publication_complete(runs, run_id)
        and (
            not completed_publication_exists
            or (runs / run_id / "gates/publication-state.json").is_file()
        )
    )
    if len(candidates) > 1:
        publication_candidates = [
            run_id
            for run_id in candidates
            if (runs / run_id / "gates/publication-state.json").is_file()
        ]
        if len(publication_candidates) == 1:
            return publication_candidates[0]
        if len(publication_candidates) > 1:
            raise ValueError("multiple ledger-backed publication adoption candidates")
        # Generation-only quality markers have no publication target. Leave
        # them to their quality owner and keep the publication queue moving.
        return None
    return candidates[0] if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--decision", required=True)
    args = parser.parse_args()
    try:
        decision = json.loads(args.decision)
        result = select(args.state_root.resolve(), args.ledger.resolve(), decision)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"REFUSED: {exc}")
        return 1
    if result:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
