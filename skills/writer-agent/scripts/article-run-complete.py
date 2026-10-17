#!/usr/bin/env python3
"""Validate completion evidence for one immutable article run."""

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path

from article_completion import (
    ACTIVE_REQUIRED_LIVE,
    LEGACY_REQUIRED_LIVE,
    validate_live_set,
)
from publication_contract_resolver import (
    PublicationContractError,
    resolve_publication_contract,
)


def load_rows(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


OWNER_ID = "article-daily"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SAFE_URL = re.compile(r"https://[A-Za-z0-9._:/-]{1,504}\Z")


def write_effect_result_hint(path: Path, occurrence_id: str, run_id: str, live: list[dict]) -> bool:
    """Tell the loop runtime this occurrence's publication is verified (lm_loop_run reads it).

    Same contract as the CFO/treg/eBook hints: a private, never-overwritten file in the
    runtime's private scratch dir. Any doubt leaves the effect unknown for the fence reconciler.
    """
    urls = sorted(row["live_url"] for row in live)
    parent = path.parent
    if (path.name != "entrypoint-result.json" or not path.is_absolute()
            or not occurrence_id.startswith(f"{OWNER_ID}:")
            or not SAFE_ID.fullmatch(run_id)
            or not all(SAFE_URL.fullmatch(url) for url in urls)
            or parent.is_symlink() or not parent.is_dir()):
        return False
    info = parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        return False
    value = {
        "schema_version": 1,
        "kind": "life_manager_effect_result",
        "status": "verified_effect",
        "effect": 1,
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "provider": "writer",
        "provider_receipt_id": run_id,
        "effect_status": "verified",
        "live_urls": urls,
    }
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--armed", required=True, choices=("0", "1"))
    parser.add_argument("--publication-state", required=True)
    parser.add_argument("--effect-result-hint")
    parser.add_argument("--occurrence-id")
    args = parser.parse_args()
    if bool(args.effect_result_hint) != bool(args.occurrence_id):
        parser.error("--effect-result-hint and --occurrence-id go together")

    rows = [row for row in load_rows(Path(args.ledger)) if row.get("run_id") == args.run_id]
    if args.armed == "0":
        # Unarmed rows are drafts, never a publication effect.
        return 1 if args.effect_result_hint else (0 if rows else 1)

    try:
        contract = resolve_publication_contract(
            Path(args.publication_state), Path(args.ledger), args.run_id
        )
    except PublicationContractError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    required = LEGACY_REQUIRED_LIVE if contract == "legacy-exact8" else ACTIVE_REQUIRED_LIVE
    valid, live, _ = validate_live_set(rows, args.run_id, required)
    if valid and args.effect_result_hint:
        return 0 if write_effect_result_hint(
            Path(args.effect_result_hint), args.occurrence_id, args.run_id, live) else 1
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
