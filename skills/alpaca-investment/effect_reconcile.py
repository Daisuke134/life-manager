#!/usr/bin/env python3
"""Close one Alpaca effect_unknown admission fence from official Alpaca readback.

A wake that ran its entrypoint and then lost its host heartbeat leaves the owner
fenced (`resource_effect_unknown`); the pre-effect auto-proof cannot close it
because the entrypoint did run. This tool proves "no Alpaca effect" with GET
requests only: zero orders of any status submitted after the occurrence was
queued, and zero open orders. Any order, a full page, or any read failure is
inconclusive and keeps the fence. Closing goes through the host's
`resolve_unknown_occurrence`, which re-checks the proof and never retries a trade.

Usage:
    python3 effect_reconcile.py --occurrence-id alpaca-investment-live:<run_id> [--readback-only]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))

LIVE_ENDPOINT = "https://api.alpaca.markets/v2"
# Readback uses the LIVE account only, so the only fence it may prove is the live owner's.
OWNER_ID = "alpaca-investment-live"
PAGE_LIMIT = 500


def build_proof(owner_id: str, occurrence_id: str, queued_at: str,
                get: Callable[[str], Any]) -> dict[str, Any]:
    if not occurrence_id.startswith(owner_id + ":"):
        raise ValueError("occurrence does not belong to owner")
    proof: dict[str, Any] = {"owner_id": owner_id, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at}
    try:
        after = get(f"/orders?status=all&after={queued_at}&limit={PAGE_LIMIT}&direction=asc")
        open_orders = get(f"/orders?status=open&limit={PAGE_LIMIT}")
    except Exception as exc:  # noqa: BLE001 - any read failure is inconclusive, fence stays
        proof["reason"] = f"readback_failed:{type(exc).__name__}"
        return proof
    if not isinstance(after, list) or not isinstance(open_orders, list):
        proof["reason"] = "readback_not_a_list"
    elif len(after) >= PAGE_LIMIT or len(open_orders) >= PAGE_LIMIT:
        proof["reason"] = "readback_page_full"
    elif after or open_orders:
        proof["reason"] = f"orders_present:after={len(after)},open={len(open_orders)}"
    else:
        proof.update(verified=True, provider_receipt_id=f"alpaca-orders-none-after-{queued_at}",
                     proof_kind="official_alpaca_no_order",
                     checked_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    return proof


def alpaca_get(credentials_path: Path) -> Callable[[str], Any]:
    from alpaca_cli import _credentials  # same file checks (mode 600, owner) as the live loop
    private = _credentials(credentials_path, "live")
    headers = {"APCA-API-KEY-ID": private["api_key"], "APCA-API-SECRET-KEY": private["api_secret"]}

    def get(path: str) -> Any:
        request = urllib.request.Request(LIVE_ENDPOINT + path, headers=headers)
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    return get


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, str]:
    """Read (state, queued_at ISO) of the fenced row without mutating the ledger."""
    from runtime.host import resource_admission

    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            """SELECT state, queued_at FROM occurrences
                 WHERE owner_id=? AND occurrence_id=? AND effect_unknown=1""",
            (owner_id, occurrence_id),
        ).fetchone()
    if row is None or row[1] is None:
        raise ValueError("occurrence is not an effect_unknown row")
    queued = dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)
    return str(row[0]), queued.strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--credentials", type=Path,
                        default=os.environ.get("ALPACA_INVESTMENT_LIVE_CREDENTIALS_FILE")
                        or os.environ.get("ANICCA_CREDENTIALS_FILE")
                        or Path("~/.local/share/anicca/credentials.json").expanduser())
    parser.add_argument("--readback-only", action="store_true",
                        help="print the proof without closing the fence")
    args = parser.parse_args(argv)
    try:
        if not args.credentials:
            raise ValueError("ALPACA_INVESTMENT_LIVE_CREDENTIALS_FILE is not set")
        state, queued_at = fenced_row(OWNER_ID, args.occurrence_id)
        proof = build_proof(OWNER_ID, args.occurrence_id, queued_at,
                            alpaca_get(Path(args.credentials)))
        print(json.dumps({**proof, "admission_state": state}, sort_keys=True))
        if not proof["verified"]:
            print("ALPACA_EFFECT_RECONCILE=HELD")
            return 1
        if args.readback_only:
            print("ALPACA_EFFECT_RECONCILE=PROOF_READY")
            return 0
        from runtime.host.resource_admission import resolve_unknown_occurrence
        if not resolve_unknown_occurrence(OWNER_ID, args.occurrence_id,
                                          official_readback=lambda: proof,
                                          expected_state=state):
            raise ValueError("admission refused to close the occurrence")
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"ALPACA_EFFECT_RECONCILE=FAIL reason={type(exc).__name__}:{exc}", file=sys.stderr)
        return 1
    print("ALPACA_EFFECT_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
