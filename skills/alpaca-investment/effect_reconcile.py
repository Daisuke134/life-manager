#!/usr/bin/env python3
"""Close one Alpaca effect_unknown admission fence from official Alpaca readback.

A wake that ran its entrypoint and then lost its host heartbeat leaves the owner
fenced (`resource_effect_unknown`); the pre-effect auto-proof cannot close it
because the entrypoint did run. This tool proves "no Alpaca effect" with GET
requests only: zero orders of any status submitted between the occurrence's
queue time and its own single terminal report (+5 min skew grace; unbounded when
that terminal is missing or ambiguous), and zero open orders. Credentials default
to the SSOT file the lane plists set, so the minimal-env fence reconciler works. Any order, a full page, or any read failure is
inconclusive and keeps the fence. Closing passes a fresh official GET proof to
the host's `resolve_unknown_occurrence` and never retries a trade.

Usage:
    python3 effect_reconcile.py --occurrence-id <owner>:<run_id> [--mode live|paper] [--readback-only]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))

LIVE_ENDPOINT = "https://api.alpaca.markets/v2"
PAPER_ENDPOINT = "https://paper-api.alpaca.markets/v2"
OWNER_ID = "alpaca-investment-live"
PAPER_OWNER_ID = "alpaca-investment-paper"
_OWNER_BY_MODE = {"live": OWNER_ID, "paper": PAPER_OWNER_ID}
_ENDPOINT_BY_MODE = {"live": LIVE_ENDPOINT, "paper": PAPER_ENDPOINT}
PAGE_LIMIT = 500
# Same file both lane plists set; lm-fence-reconciler runs without lane env.
CREDENTIALS_SSOT = "~/.local/share/anicca/credentials.json"
STATE_ROOT_TEMPLATE = "~/.local/state/life-manager/{owner}"  # registry state_root


def owner_for_mode(mode: str) -> str:
    try:
        return _OWNER_BY_MODE[mode]
    except (KeyError, TypeError) as error:
        raise ValueError("investment_mode_invalid") from error


def endpoint_for_mode(mode: str) -> str:
    try:
        return _ENDPOINT_BY_MODE[mode]
    except (KeyError, TypeError) as error:
        raise ValueError("investment_mode_invalid") from error


# The occurrence's own process cannot submit after its terminal report; the
# grace only absorbs clock skew between the host and Alpaca.
WINDOW_GRACE = dt.timedelta(minutes=5)


def occurrence_window_end(events_path: Path, occurrence_id: str) -> str | None:
    """Exactly one terminal report event of this occurrence -> window end, else None."""
    try:
        with events_path.open(encoding="utf-8") as handle:
            lines = [line for line in handle if occurrence_id in line]
    except OSError:
        return None
    ends = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            return None
        if (isinstance(row, dict) and row.get("occurrence_id") == occurrence_id
                and row.get("phase") == "report" and row.get("exit_code") is not None):
            ends.append(row.get("timestamp"))
    if len(ends) != 1 or not isinstance(ends[0], str):
        return None
    try:
        end = dt.datetime.fromisoformat(ends[0])
    except ValueError:
        return None
    if end.tzinfo is None:
        return None
    end = (end + WINDOW_GRACE).astimezone(dt.timezone.utc)
    return (end.replace(microsecond=0) + dt.timedelta(seconds=1 if end.microsecond else 0)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_proof(owner_id: str, occurrence_id: str, queued_at: str,
                get: Callable[[str], Any], until: str | None = None) -> dict[str, Any]:
    if not occurrence_id.startswith(owner_id + ":"):
        raise ValueError("occurrence does not belong to owner")
    proof: dict[str, Any] = {"owner_id": owner_id, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at, "window_end": until}
    bound = f"&until={until}" if until else ""
    try:
        after_response = get(
            f"/orders?status=all&after={queued_at}{bound}&limit={PAGE_LIMIT}&direction=asc")
        open_response = get(f"/orders?status=open&limit={PAGE_LIMIT}")
    except Exception as exc:  # noqa: BLE001 - any read failure is inconclusive, fence stays
        proof["reason"] = f"readback_failed:{type(exc).__name__}"
        return proof
    if not isinstance(after_response, Mapping) or not isinstance(open_response, Mapping):
        proof["reason"] = "readback_response_invalid"
    elif any(not isinstance(response.get("request_id"), str)
             or not response["request_id"].strip()
             for response in (after_response, open_response)):
        proof["reason"] = "provider_request_id_missing"
    elif (not isinstance(after_response.get("data"), list)
          or not isinstance(open_response.get("data"), list)):
        proof["reason"] = "readback_not_a_list"
    elif (len(after_response["data"]) >= PAGE_LIMIT
          or len(open_response["data"]) >= PAGE_LIMIT):
        proof["reason"] = "readback_page_full"
    elif after_response["data"] or open_response["data"]:
        proof["reason"] = (
            f"orders_present:after={len(after_response['data'])},"
            f"open={len(open_response['data'])}"
        )
    else:
        request_ids = [after_response["request_id"], open_response["request_id"]]
        proof.update(verified=True, provider_receipt_id=request_ids[0],
                     provider_request_ids=request_ids,
                     proof_kind="official_alpaca_no_order",
                     checked_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    return proof


def alpaca_get(credentials_path: Path, mode: str = "live") -> Callable[[str], Any]:
    from alpaca_cli import _credentials  # same file checks (mode 600, owner) as the live loop
    private = _credentials(credentials_path, mode)
    headers = {"APCA-API-KEY-ID": private["api_key"], "APCA-API-SECRET-KEY": private["api_secret"]}
    endpoint = endpoint_for_mode(mode)

    def get(path: str) -> Any:
        request = urllib.request.Request(endpoint + path, headers=headers)
        with urllib.request.urlopen(request, timeout=20) as response:
            return {"data": json.load(response),
                    "request_id": response.headers.get("X-Request-ID")}
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
    parser.add_argument("--mode", choices=("live", "paper"), default="live")
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--readback-only", action="store_true",
                        help="print the proof without closing the fence")
    args = parser.parse_args(argv)
    try:
        owner_id = owner_for_mode(args.mode)
        credential_value = args.credentials or os.environ.get(
            f"ALPACA_INVESTMENT_{args.mode.upper()}_CREDENTIALS_FILE"
        ) or os.environ.get("ANICCA_CREDENTIALS_FILE") or CREDENTIALS_SSOT
        state, queued_at = fenced_row(owner_id, args.occurrence_id)
        until = occurrence_window_end(
            Path(STATE_ROOT_TEMPLATE.format(owner=owner_id)).expanduser() / "events.jsonl",
            args.occurrence_id)
        get = alpaca_get(Path(credential_value).expanduser(), args.mode)
        last_proof: dict[str, Any] = {}

        def official_readback() -> dict[str, Any]:
            proof = build_proof(owner_id, args.occurrence_id, queued_at, get, until)
            last_proof.clear()
            last_proof.update(proof)
            return proof

        if args.readback_only:
            proof = official_readback()
            print(json.dumps({**proof, "admission_state": state}, sort_keys=True))
            if not proof["verified"]:
                print("ALPACA_EFFECT_RECONCILE=HELD")
                return 1
            print("ALPACA_EFFECT_RECONCILE=PROOF_READY")
            return 0
        from runtime.host.resource_admission import resolve_unknown_occurrence
        resolved = resolve_unknown_occurrence(owner_id, args.occurrence_id,
                                              official_readback=official_readback,
                                              expected_state=state)
        print(json.dumps({**last_proof, "admission_state": state}, sort_keys=True))
        if not resolved:
            print("ALPACA_EFFECT_RECONCILE=HELD")
            return 1
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"ALPACA_EFFECT_RECONCILE=FAIL reason={type(exc).__name__}:{exc}", file=sys.stderr)
        return 1
    print("ALPACA_EFFECT_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
