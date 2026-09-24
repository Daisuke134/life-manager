#!/usr/bin/env python3
"""Read-only reconciliation of one x402 settlement occurrence.

The adapter never sends a transaction and never edits admission state.  It only
returns a resolver-compatible proof after an occurrence-bound ledger row and a
fresh finalized Base receipt agree exactly.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable


OWNER_ID = "x402-settlement-recorder"
OCCURRENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TX = re.compile(r"^0x[0-9a-f]{64}$")
ADDRESS = re.compile(r"^0x[0-9a-f]{40}$")
USDC_ADDRESS = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _inconclusive(owner_id: str, occurrence_id: str, reason: str) -> dict[str, Any]:
    return {
        "status": "inconclusive",
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "reason": reason,
    }


def _hex_or_int(value: Any) -> int | None:
    try:
        number = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _valid_receipt(row: Any, owner_id: str, occurrence_id: str) -> bool:
    if not isinstance(row, dict) or row.get("occurrence_id") != occurrence_id:
        return False
    provider_id = str(row.get("provider_receipt_id", "")).lower()
    tx = str(row.get("tx", "")).lower()
    readback = row.get("official_readback_ref")
    return (
        row.get("verified") is True
        and row.get("proof_kind") == "base_finalized_usdc_transfer"
        and provider_id == tx
        and TX.fullmatch(tx) is not None
        and readback == f"base://tx/{tx}"
        and _hex_or_int(row.get("block")) is not None
        and row.get("finalized") is True
        and row.get("status") == "success"
        and row.get("external") is True
        and ADDRESS.fullmatch(str(row.get("from", "")).lower()) is not None
        and ADDRESS.fullmatch(str(row.get("payTo", "")).lower()) is not None
        and isinstance(row.get("usdc_atomic"), str)
        and row["usdc_atomic"].isdigit()
        and int(row["usdc_atomic"]) > 0
        and owner_id == OWNER_ID
        and OCCURRENCE.fullmatch(occurrence_id) is not None
    )


def build_proof_from_rows(
    rows: Iterable[dict[str, Any]], *, owner_id: str, occurrence_id: str,
) -> dict[str, Any]:
    """Build a proof candidate from occurrence-bound local rows, fail-closed."""
    matches = [
        row for row in rows
        if _valid_receipt(row, owner_id, occurrence_id)
    ]
    if not matches:
        return _inconclusive(owner_id, occurrence_id, "occurrence_receipt_missing")
    if len(matches) != 1:
        return _inconclusive(owner_id, occurrence_id, "occurrence_receipt_ambiguous")
    row = matches[0]
    tx = str(row["tx"]).lower()
    return {
        "status": "ready",
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_kind": "base_finalized_usdc_transfer",
        "provider_receipt_id": tx,
        "official_readback_ref": f"base://tx/{tx}",
        "local_receipt": row,
    }


def verify_base_readback(
    local: dict[str, Any], finalized: dict[str, Any], receipt: dict[str, Any],
) -> bool:
    """Check the exact finalized USDC transfer against the local occurrence row."""
    tx = str(local.get("tx", "")).lower()
    if not TX.fullmatch(tx):
        return False
    finalized_block = _hex_or_int(finalized.get("number")) if isinstance(finalized, dict) else None
    receipt_block = _hex_or_int(receipt.get("blockNumber")) if isinstance(receipt, dict) else None
    if (
        str(receipt.get("transactionHash", "")).lower() != tx
        or receipt.get("status") != "0x1"
        or finalized_block is None
        or receipt_block is None
        or receipt_block > finalized_block
    ):
        return False
    expected_from = str(local.get("from", "")).lower()
    expected_to = str(local.get("payTo", "")).lower()
    expected_atomic = str(local.get("usdc_atomic", ""))
    matches: list[dict[str, Any]] = []
    for log in receipt.get("logs", []) if isinstance(receipt.get("logs"), list) else []:
        topics = log.get("topics") if isinstance(log, dict) else None
        if (
            not isinstance(log, dict)
            or str(log.get("address", "")).lower() != USDC_ADDRESS
            or not isinstance(topics, list)
            or len(topics) < 3
            or str(topics[0]).lower() != TRANSFER_TOPIC
            or str(log.get("transactionHash", tx)).lower() != tx
        ):
            continue
        from_topic = str(topics[1]).lower()
        to_topic = str(topics[2]).lower()
        if not (from_topic.startswith("0x" + "0" * 24)
                and to_topic.startswith("0x" + "0" * 24)):
            continue
        source = "0x" + from_topic[-40:]
        destination = "0x" + to_topic[-40:]
        try:
            atomic = int(str(log.get("data", "")), 0)
        except (TypeError, ValueError):
            continue
        if source == expected_from and destination == expected_to and str(atomic) == expected_atomic:
            matches.append(log)
    return len(matches) == 1


def _rpc_call(url: str, method: str, params: list[Any]) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(url, data=payload, headers={"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode())
    if body.get("error") or "result" not in body:
        raise RuntimeError("base_rpc_error")
    return body["result"]


def build_official_proof(
    rows: Iterable[dict[str, Any]], *, owner_id: str, occurrence_id: str,
    rpc: Callable[[str, list[Any]], Any],
) -> dict[str, Any]:
    """Return a resolver proof only after a fresh Base finalized readback."""
    candidate = build_proof_from_rows(rows, owner_id=owner_id, occurrence_id=occurrence_id)
    if candidate.get("status") != "ready":
        return candidate
    local = candidate["local_receipt"]
    try:
        chain = _hex_or_int(rpc("eth_chainId", []))
        finalized = rpc("eth_getBlockByNumber", ["finalized", False])
        receipt = rpc("eth_getTransactionReceipt", [local["tx"]])
    except (OSError, RuntimeError, TypeError, ValueError, urllib.error.URLError):
        return _inconclusive(owner_id, occurrence_id, "base_readback_unavailable")
    if chain != 8453:
        return _inconclusive(owner_id, occurrence_id, "base_chain_mismatch")
    if not verify_base_readback(local, finalized, receipt):
        return _inconclusive(owner_id, occurrence_id, "base_readback_not_exact")
    return {
        **candidate,
        "provider_readback": {
            "provider": "base",
            "chain_id": chain,
            "transaction_hash": local["tx"],
            "finalized_block": finalized.get("number"),
            "status": "success",
        },
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(value, dict):
                rows.append(value)
        return rows
    except (OSError, UnicodeDecodeError):
        return []


def _admission_state(database: Path, owner_id: str, occurrence_id: str) -> tuple[str | None, int | None]:
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT state,effect_unknown FROM occurrences WHERE owner_id=? AND occurrence_id=?",
                (owner_id, occurrence_id),
            ).fetchone()
    except sqlite3.Error:
        return None, None
    return (row[0], int(row[1])) if row else (None, None)


def reconcile(
    *, state_dir: Path, admission_db: Path, owner_id: str, occurrence_id: str,
    rpc: Callable[[str, list[Any]], Any],
) -> dict[str, Any]:
    state, effect_unknown = _admission_state(admission_db, owner_id, occurrence_id)
    if state not in {"claimed", "released"} or effect_unknown != 1:
        return _inconclusive(owner_id, occurrence_id, "claimed_or_already_resolved")
    rows: list[dict[str, Any]] = []
    for ledger in sorted(state_dir.glob("external-inflows-*.jsonl")):
        rows.extend(_read_jsonl(ledger))
    return build_official_proof(rows, owner_id=owner_id, occurrence_id=occurrence_id, rpc=rpc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--owner-id", default=OWNER_ID)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path.home() / ".local/state/life-manager/x402-sell",
    )
    parser.add_argument(
        "--admission-db",
        type=Path,
        default=Path.home() / ".local/state/life-manager/host-admission/resources/admission-v2.sqlite3",
    )
    parser.add_argument("--rpc-url", default="https://mainnet.base.org")
    args = parser.parse_args(argv)
    if args.owner_id != OWNER_ID or not OCCURRENCE.fullmatch(args.occurrence_id):
        parser.error("owner and occurrence IDs are invalid")
    result = reconcile(
        state_dir=args.state_dir,
        admission_db=args.admission_db,
        owner_id=args.owner_id,
        occurrence_id=args.occurrence_id,
        rpc=lambda method, params: _rpc_call(args.rpc_url, method, params),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
