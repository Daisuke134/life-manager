#!/usr/bin/env python3
"""Close one effect_unknown admission fence from the lane's own post-effect ledger.

Same shape as skills/earn/line-sticker/readback_fence_reconcile.py, shared by lanes whose only
external write lands in a ledger the lane appends *after* the provider accepted the effect:

  life-manager-daily    ~/.local/state/life-manager/state/lm-video/distribution.jsonl
                        a ``published`` row with ``public_readback_verified`` is the Postiz receipt
  marketing-mine-daily  ~/.local/state/life-manager/marketing-mine-daily/evidence/intel-daily/*.json
                        intel_gap writes one file per pass; ``telegram`` holds the send receipt

  - A receipt row at or after the occurrence's ``queued_at``: the run (or a sibling pass on the
    same route) did reach the provider; close as effected with that receipt.
  - No receipt row since ``queued_at`` and the fence is older than NO_EFFECT_MIN_AGE_SECONDS:
    nothing reached the provider through this lane's only route; close as no-effect.
  - Too recent: stay fenced, the ledger may still be written.

Usage:
    python3 ledger_fence_reconcile.py --owner life-manager-daily --occurrence <owner>:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

NO_EFFECT_MIN_AGE_SECONDS = 24 * 3600
STATE_HOME = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", "~/.local/state/life-manager")).expanduser()

SPECS: dict[str, dict[str, Any]] = {
    "life-manager-daily": {
        "paths": [STATE_HOME / "state/lm-video/distribution.jsonl"],
        "ts_key": "ts",
        "effected": lambda row: row.get("status") == "published" and row.get("public_readback_verified") is True,
        "receipt": lambda row: f"postiz:{row.get('provider_id')}:{row.get('public_url')}",
        "proof_kind": "distribution_ledger_published_row",
    },
    "marketing-mine-daily": {
        "paths": [STATE_HOME / "marketing-mine-daily/evidence/intel-daily/*.json"],
        "ts_key": "observed_at",
        "effected": lambda row: row.get("telegram") is not None,
        "receipt": lambda row: f"telegram:{json.dumps(row.get('telegram'), sort_keys=True)[:120]}",
        "proof_kind": "intel_gap_telegram_receipt",
    },
}


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, dt.datetime]:
    from runtime.host import resource_admission
    database = resource_admission.state_root() / "admission-v2.sqlite3"
    # busy-wait briefly: 80+ lm_loop_run processes share this database and a bare ro open raises
    # "database is locked" the moment one of them holds a write transaction.
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=5.0) as connection:
        row = connection.execute(
            """SELECT state, queued_at FROM occurrences
                 WHERE owner_id=? AND occurrence_id=? AND effect_unknown=1""",
            (owner_id, occurrence_id),
        ).fetchone()
    if row is None or row[1] is None:
        raise ValueError("occurrence is not an effect_unknown row")
    return str(row[0]), dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)


def load_rows(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for pattern in paths:
        for name in sorted(glob.glob(str(pattern))):
            path = Path(name)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                rows.append({"_unreadable": str(path)})
                continue
            if path.suffix == ".jsonl":
                for line in text.splitlines():
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        rows.append({"_unreadable": str(path)})
            else:
                try:
                    value = json.loads(text)
                except json.JSONDecodeError:
                    rows.append({"_unreadable": str(path)})
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    return rows


def _row_time(row: dict, ts_key: str) -> dt.datetime | None:
    value = row.get(ts_key)
    if not value:
        return None
    try:
        when = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)


def build_proof(owner_id: str, occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                rows: list[dict], spec: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec or SPECS[owner_id]
    effected: Callable[[dict], bool] = spec["effected"]
    proof: dict[str, Any] = {"owner_id": owner_id, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    unreadable = [row["_unreadable"] for row in rows if "_unreadable" in row]
    if unreadable:
        proof["reason"] = "ledger_unreadable:" + ",".join(sorted(set(unreadable)))
        return proof
    since = [row for row in rows if (when := _row_time(row, spec["ts_key"])) is not None and when >= queued_at]
    hits = [row for row in since if effected(row)]
    if hits:
        proof.update(verified=True, effected=True, provider_receipt_id=spec["receipt"](hits[0]),
                     proof_kind=spec["proof_kind"], receipt_rows=len(hits),
                     checked_at=now.isoformat(timespec="seconds"))
        return proof
    age = (now - queued_at).total_seconds()
    if age <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof
    proof.update(verified=True, effected=False, rows_since_queued=len(since),
                 provider_receipt_id=f"{owner_id}-no-ledger-receipt-since:{queued_at.isoformat()}",
                 proof_kind=f"no_{spec['proof_kind']}_since_run_start",
                 checked_at=now.isoformat(timespec="seconds"))
    return proof


def reconcile(owner_id: str, occurrence_id: str, *, resolve: bool = False) -> dict[str, Any]:
    if owner_id not in SPECS:
        raise ValueError(f"no ledger spec for owner {owner_id}")
    if not occurrence_id.startswith(f"{owner_id}:"):
        raise ValueError("occurrence does not belong to owner")
    now = dt.datetime.now(dt.timezone.utc)
    state, queued_at = fenced_row(owner_id, occurrence_id)
    proof = build_proof(owner_id, occurrence_id, queued_at, now=now, rows=load_rows(SPECS[owner_id]["paths"]))
    result = {**proof, "admission_state": state}
    if not proof.get("verified") or not resolve:
        return result
    from runtime.host.resource_admission import resolve_unknown_occurrence
    result["closed"] = resolve_unknown_occurrence(owner_id, occurrence_id,
                                                  official_readback=lambda: proof, expected_state=state)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--owner", required=True, choices=sorted(SPECS))
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    tag = "LEDGER_FENCE_RECONCILE"
    try:
        result = reconcile(args.owner, args.occurrence, resolve=args.resolve)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"owner_id": args.owner, "occurrence_id": args.occurrence,
                          "verified": False, "error": f"{type(exc).__name__}:{exc}"}))
        print(f"{tag}=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str, ensure_ascii=False))
    if not result.get("verified"):
        print(f"{tag}=HELD")
        return 1
    if not args.resolve:
        print(f"{tag}=PROOF_READY")
        return 0
    if not result.get("closed"):
        print(f"{tag}=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print(f"{tag}=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
