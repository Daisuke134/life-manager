#!/usr/bin/env python3
"""Read the local candidate and Lancers account without creating private input."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps/job-search-loop"))
from job_search_loop.config import validate_profile


class SetupRequired(ValueError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("setup_required")


def load_identity(candidate_path: Path | None = None, provider_path: Path | None = None) -> dict:
    candidate_path = candidate_path or Path.home() / ".config/anicca/job-search/profile.json"
    provider_path = provider_path or Path.home() / ".config/anicca/lancers/public-profile.json"
    missing = []
    try:
        candidate = validate_profile(json.loads(candidate_path.expanduser().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        missing.append("candidate_profile")
    try:
        provider = json.loads(provider_path.expanduser().read_text(encoding="utf-8"))
        account_id = provider.get("account_id") if isinstance(provider, dict) else None
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError
    except (OSError, ValueError):
        missing.append("provider_profile.account_id")
    if missing:
        raise SetupRequired(missing)
    return {"candidate": candidate, "provider": provider, "account_id": account_id.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("account-id",))
    parser.parse_args(argv)
    try:
        identity = load_identity()
    except SetupRequired as error:
        print(json.dumps({"ok": False, "error": "setup_required", "missing": error.missing}))
        return 78
    print(identity["account_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
