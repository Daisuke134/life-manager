#!/usr/bin/env python3
"""Close one Alpaca effect_unknown admission fence from official Alpaca readback.

A wake that ran its entrypoint and then lost its host heartbeat leaves the owner
fenced (`resource_effect_unknown`); the pre-effect auto-proof cannot close it
because the entrypoint did run. This tool proves "no Alpaca effect" with GET
requests only: zero orders of any status submitted after the occurrence was
queued, and zero open orders. Any order, a full page, or any read failure is
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
ORDER_REF_LIMIT = 4
ORDER_REF_FIELD_LIMIT = 128


def _order_ref(row: Any) -> tuple[dict[str, str], bool]:
    if not isinstance(row, Mapping):
        return {"row_type": type(row).__name__}, True
    refs = {}
    truncated = False
    for key in ("id", "client_order_id"):
        value = row.get(key)
        if isinstance(value, str) and value:
            truncated |= len(value) > ORDER_REF_FIELD_LIMIT
            refs[key] = value[:ORDER_REF_FIELD_LIMIT]
    return refs, truncated or not refs


def _bounded_order_refs(after_orders: list[Any] | None,
                        open_orders: list[Any] | None) -> tuple[list[dict[str, str]], list[dict[str, str]], bool]:
    after_refs: list[dict[str, str]] = []
    open_refs: list[dict[str, str]] = []
    truncated = after_orders is None or open_orders is None
    after_orders = after_orders or []
    open_orders = open_orders or []
    for index in range(max(len(after_orders), len(open_orders))):
        for rows, refs in ((after_orders, after_refs), (open_orders, open_refs)):
            if index >= len(rows) or len(after_refs) + len(open_refs) >= ORDER_REF_LIMIT:
                continue
            ref, row_truncated = _order_ref(rows[index])
            refs.append(ref)
            truncated |= row_truncated
    truncated |= len(after_refs) < len(after_orders) or len(open_refs) < len(open_orders)
    return after_refs, open_refs, truncated


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


def build_proof(owner_id: str, occurrence_id: str, queued_at: str,
                get: Callable[[str], Any]) -> dict[str, Any]:
    if not occurrence_id.startswith(owner_id + ":"):
        raise ValueError("occurrence does not belong to owner")
    proof: dict[str, Any] = {"owner_id": owner_id, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at}
    responses: list[Any] = []
    for path in (f"/orders?status=all&after={queued_at}&limit={PAGE_LIMIT}&direction=asc",
                 f"/orders?status=open&limit={PAGE_LIMIT}"):
        try:
            responses.append(get(path))
        except Exception as exc:  # noqa: BLE001 - any read failure is inconclusive, fence stays
            _attach_readback_details(proof, responses)
            return _mark_inconclusive(proof, f"readback_failed:{type(exc).__name__}", exc)

    after_response, open_response = responses
    _attach_readback_details(proof, responses)
    if not isinstance(after_response, Mapping) or not isinstance(open_response, Mapping):
        reason = "readback_response_invalid"
    elif any(not isinstance(response.get("request_id"), str)
             or not response["request_id"].strip()
             for response in responses):
        reason = "provider_request_id_missing"
    elif any(not isinstance(response.get("data"), list) for response in responses):
        reason = "readback_not_a_list"
    else:
        after_orders, open_orders = after_response["data"], open_response["data"]
        if len(after_orders) >= PAGE_LIMIT or len(open_orders) >= PAGE_LIMIT:
            reason = "readback_page_full"
        elif after_orders or open_orders:
            reason = f"orders_present:after={len(after_orders)},open={len(open_orders)}"
        else:
            proof.update(verified=True, proof_kind="official_alpaca_no_order",
                         checked_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
            return proof
    return _mark_inconclusive(proof, reason)


def _attach_readback_details(proof: dict[str, Any], responses: list[Any]) -> None:
    request_ids = []
    request_sources = []
    orders_by_scope: list[list[Any] | None] = []
    for scope, response in zip(("after", "open"), responses):
        request_id = response.get("request_id") if isinstance(response, Mapping) else None
        if isinstance(request_id, str) and request_id.strip():
            request_ids.append(request_id)
            request_sources.append(scope)
        data = response.get("data") if isinstance(response, Mapping) else None
        orders = data if isinstance(data, list) else None
        orders_by_scope.append(orders)
        if orders is not None:
            proof[f"{scope}_order_count"] = len(orders)
    after_orders = orders_by_scope[0] if orders_by_scope else None
    open_orders = orders_by_scope[1] if len(orders_by_scope) > 1 else None
    if request_ids:
        proof.update(provider_receipt_id=request_ids[0], provider_request_ids=request_ids,
                     provider_request_id_scopes=request_sources)
    if after_orders is not None or open_orders is not None:
        after_refs, open_refs, truncated = _bounded_order_refs(after_orders, open_orders)
        proof.update(after_order_refs=after_refs, open_order_refs=open_refs,
                     order_refs_truncated=truncated)


def _mark_inconclusive(proof: dict[str, Any], reason: str,
                       error: Exception | None = None) -> dict[str, Any]:
    proof["reason"] = reason
    proof.update(phase="readback", status="held", effect_status="unknown",
                 error_class=type(error).__name__ if error else "official_readback_inconclusive",
                 retryable=isinstance(error, OSError),
                 next_action=("match_provider_orders_to_local_receipts"
                              if reason.startswith("orders_present:")
                              else "retry_or_repair_official_readback"))
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
        ) or os.environ.get("ANICCA_CREDENTIALS_FILE") \
            or "~/.local/share/anicca/credentials.json"
        state, queued_at = fenced_row(owner_id, args.occurrence_id)
        get = alpaca_get(Path(credential_value).expanduser(), args.mode)
        last_proof: dict[str, Any] = {}

        def official_readback() -> dict[str, Any]:
            proof = build_proof(owner_id, args.occurrence_id, queued_at, get)
            last_proof.clear()
            last_proof.update(proof)
            return proof

        if args.readback_only:
            proof = official_readback()
            print(json.dumps({**proof, "admission_state": state}, sort_keys=True,
                             separators=(",", ":")))
            if not proof["verified"]:
                print("ALPACA_EFFECT_RECONCILE=HELD")
                return 1
            print("ALPACA_EFFECT_RECONCILE=PROOF_READY")
            return 0
        from runtime.host.resource_admission import resolve_unknown_occurrence
        resolved = resolve_unknown_occurrence(owner_id, args.occurrence_id,
                                              official_readback=official_readback,
                                              expected_state=state)
        print(json.dumps({**last_proof, "admission_state": state}, sort_keys=True,
                         separators=(",", ":")))
        if not resolved:
            print("ALPACA_EFFECT_RECONCILE=HELD")
            return 1
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        message = str(exc)
        if message == "occurrence is not an effect_unknown row":
            reason_code, next_action, retryable = "occurrence_not_fenced", "refresh_exact_occurrence", False
        elif "credential" in message.lower():
            reason_code, next_action, retryable = "credentials_unavailable", "inspect_readback_credentials", False
        else:
            reason_code = type(exc).__name__
            next_action = "retry_official_readback" if not isinstance(exc, ValueError) else "inspect_readback_adapter"
            retryable = not isinstance(exc, ValueError)
        owner_id = _OWNER_BY_MODE.get(args.mode)
        run_id = args.occurrence_id.split(":", 1)[1] if args.occurrence_id.startswith(f"{owner_id}:") else None
        print(json.dumps({"owner_id": owner_id, "occurrence_id": args.occurrence_id,
            "run_id": run_id, "provider": "app.alpaca.markets", "phase": "readback",
            "status": "fail", "effect_status": "unknown", "error_class": type(exc).__name__,
            "reason_code": reason_code, "retryable": retryable, "next_action": next_action,
            "official_readback_ref": None}, sort_keys=True, separators=(",", ":")))
        print("ALPACA_EFFECT_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print("ALPACA_EFFECT_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
