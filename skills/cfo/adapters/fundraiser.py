"""Read-only Fundraiser coverage adapter.

Fundraiser applications are financing activity, not settled customer revenue or MRR.
The adapter records that the application receipt source was read while explicitly
leaving financial categories uncovered.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from skills.cfo import economic_attribution as contract


LOOP_ID = "fundraiser"
SOURCE_ID = "fundraiser-application-receipt"
DEFAULT_PATH = Path("~/.local/state/life-manager/fundraiser/application-receipts.jsonl").expanduser()


def _coverage(*, projection: str, start: str | None, end: str,
              reason: str, evidence: str) -> dict:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": LOOP_ID,
        "source_id": SOURCE_ID,
        "projection": projection,
        "window_start": start,
        "window_end": end,
        "coverage_state": "gap",
        "reason": reason,
        "covered_categories": [],
        "observed_at": end,
        "evidence_refs": [evidence],
    })


def adapt_path(path: str | Path | None, *, snapshot_at: str,
               trailing_start: str) -> list[dict]:
    """Read application receipts and never turn fundraising into P&L revenue."""
    source = Path(path or DEFAULT_PATH).expanduser()
    reason = "missing_category"
    evidence = "fundraiser-money://application-receipts/missing-category"
    try:
        raw = source.read_bytes()
        rows = [
            json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()
        ]
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError("receipt_row_invalid")
        digest = hashlib.sha256(raw).hexdigest()
        evidence = f"fundraiser-money://application-receipts/sha256/{digest}"
    except FileNotFoundError:
        reason = "read_failed"
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        reason = "read_failed"

    return [
        _coverage(projection="historical", start=None, end=snapshot_at,
                  reason=reason, evidence=evidence),
        _coverage(projection="trailing", start=trailing_start, end=snapshot_at,
                  reason=reason, evidence=evidence),
        _coverage(projection="as_of", start=None, end=snapshot_at,
                  reason="missing_category", evidence=evidence),
    ]
