#!/usr/bin/env python3
"""Read-only reconciliation of one Sol-funding occurrence.

The adapter proves the complete cross-chain chain only from an occurrence-bound
receipt: Solana signature confirmation, Relay success/readback, and a finalized
Base USDC transfer to the configured recipient.  It never submits or mutates.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable


OWNER_ID = "sol-funding"
OCCURRENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SOL_SIGNATURE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,128}$")
TX = re.compile(r"^0x[0-9a-f]{64}$")
ADDRESS = re.compile(r"^0x[0-9a-f]{40}$")
USDC_BASE = "0x833589fcd6edb6e08f4c7c32d4f71b54bdA02913".lower()
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
RELAY_ENDPOINT = re.compile(r"^/intents/status/[A-Za-z0-9._:-]{1,200}$")


def _inconclusive(owner_id: str, occurrence_id: str, reason: str) -> dict[str, Any]:
    return {"status": "inconclusive", "owner_id": owner_id,
            "occurrence_id": occurrence_id, "reason": reason}


def _number(value: Any) -> int | None:
    try:
        number = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _valid_row(row: Any, owner_id: str, occurrence_id: str) -> bool:
    if not isinstance(row, dict) or row.get("occurrence_id") != occurrence_id:
        return False
    signature = str(row.get("provider_receipt_id", ""))
    destination_tx = row.get("destination_tx_hash")
    endpoint = row.get("relay_check_endpoint")
    recipient = str(row.get("recipient", "")).lower()
    return (
        owner_id == OWNER_ID
        and OCCURRENCE.fullmatch(occurrence_id) is not None
        and SOL_SIGNATURE.fullmatch(signature) is not None
        and isinstance(destination_tx, str)
        and TX.fullmatch(destination_tx.lower()) is not None
        and isinstance(endpoint, str)
        and RELAY_ENDPOINT.fullmatch(endpoint) is not None
        and ADDRESS.fullmatch(recipient) is not None
        and row.get("destination_chain_id") == 8453
        and str(row.get("destination_currency", "")).lower() == USDC_BASE
        and row.get("relay_status") == "success"
        and row.get("effect_status") == "submitted"
    )


def build_proof_from_rows(
    rows: Iterable[dict[str, Any]], *, owner_id: str, occurrence_id: str,
) -> dict[str, Any]:
    matches = [row for row in rows if _valid_row(row, owner_id, occurrence_id)]
    if not matches:
        return _inconclusive(owner_id, occurrence_id, "occurrence_receipt_missing")
    if len(matches) != 1:
        return _inconclusive(owner_id, occurrence_id, "occurrence_receipt_ambiguous")
    row = matches[0]
    return {
        "status": "ready",
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "verified": True,
        "proof_kind": "solana_relay_base_finalized_transfer",
        "provider_receipt_id": str(row["provider_receipt_id"]),
        "official_readback_ref": f"relay://{row['relay_check_endpoint'].lstrip('/')}",
        "local_receipt": row,
    }


def verify_solana_status(status: dict[str, Any]) -> bool:
    return (
        isinstance(status, dict)
        and status.get("err") is None
        and status.get("confirmationStatus") in {"confirmed", "finalized"}
    )


def verify_relay_readback(row: dict[str, Any], readback: dict[str, Any]) -> bool:
    txs = readback.get("txHashes") if isinstance(readback, dict) else None
    return (
        isinstance(readback, dict)
        and readback.get("status") == "success"
        and isinstance(txs, list)
        and len(txs) == 1
        and isinstance(txs[0], str)
        and txs[0].lower() == str(row.get("destination_tx_hash", "")).lower()
    )


def verify_base_readback(
    row: dict[str, Any], finalized: dict[str, Any], receipt: dict[str, Any],
) -> bool:
    tx = str(row.get("destination_tx_hash", "")).lower()
    recipient = str(row.get("recipient", "")).lower()
    final_block = _number(finalized.get("number")) if isinstance(finalized, dict) else None
    block = _number(receipt.get("blockNumber")) if isinstance(receipt, dict) else None
    if (
        not TX.fullmatch(tx)
        or str(receipt.get("transactionHash", "")).lower() != tx
        or receipt.get("status") != "0x1"
        or final_block is None or block is None or block > final_block
    ):
        return False
    matches = []
    for log in receipt.get("logs", []) if isinstance(receipt.get("logs"), list) else []:
        topics = log.get("topics") if isinstance(log, dict) else None
        if (
            not isinstance(log, dict)
            or str(log.get("address", "")).lower() != USDC_BASE
            or not isinstance(topics, list) or len(topics) < 3
            or str(topics[0]).lower() != TRANSFER_TOPIC
            or str(log.get("transactionHash", tx)).lower() != tx
        ):
            continue
        to_topic = str(topics[2]).lower()
        if not to_topic.startswith("0x" + "0" * 24) or "0x" + to_topic[-40:] != recipient:
            continue
        try:
            amount = int(str(log.get("data", "")), 0)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            expected = row.get("destination_usdc_atomic")
            if expected is None or str(amount) == str(expected):
                matches.append(log)
    return len(matches) == 1


def build_official_proof(
    rows: Iterable[dict[str, Any]], *, owner_id: str, occurrence_id: str,
    solana_rpc: Callable[[str, list[Any]], Any],
    relay_get: Callable[[str], dict[str, Any]],
    base_rpc: Callable[[str, list[Any]], Any],
) -> dict[str, Any]:
    candidate = build_proof_from_rows(rows, owner_id=owner_id, occurrence_id=occurrence_id)
    if candidate.get("status") != "ready":
        return candidate
    row = candidate["local_receipt"]
    try:
        signature_status = solana_rpc("getSignatureStatuses", [[row["provider_receipt_id"]],
                                                                {"searchTransactionHistory": True}])
        values = signature_status.get("value", []) if isinstance(signature_status, dict) else []
        relay = relay_get(row["relay_check_endpoint"])
        chain = _number(base_rpc("eth_chainId", []))
        finalized = base_rpc("eth_getBlockByNumber", ["finalized", False])
        receipt = base_rpc("eth_getTransactionReceipt", [row["destination_tx_hash"]])
    except (OSError, RuntimeError, TypeError, ValueError, urllib.error.URLError):
        return _inconclusive(owner_id, occurrence_id, "provider_readback_unavailable")
    if not values or not verify_solana_status(values[0]):
        return _inconclusive(owner_id, occurrence_id, "solana_signature_not_confirmed")
    if not verify_relay_readback(row, relay):
        return _inconclusive(owner_id, occurrence_id, "relay_readback_not_exact")
    if chain != 8453 or not verify_base_readback(row, finalized, receipt):
        return _inconclusive(owner_id, occurrence_id, "base_readback_not_exact")
    return {
        **candidate,
        "provider_readback": {
            "solana": values[0],
            "relay": relay,
            "base": {"chain_id": chain, "finalized_block": finalized.get("number"),
                     "transaction_hash": row["destination_tx_hash"]},
        },
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
            return []
        rows = []
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


def _rpc(url: str, method: str, params: list[Any]) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if payload.get("error") or "result" not in payload:
        raise RuntimeError("rpc_error")
    return payload["result"]


def _get(url: str, endpoint: str) -> dict[str, Any]:
    with urllib.request.urlopen(url.rstrip("/") + endpoint, timeout=30) as response:
        value = json.loads(response.read().decode())
    return value if isinstance(value, dict) else {}


def reconcile(
    *, state_dir: Path, admission_db: Path, owner_id: str, occurrence_id: str,
    solana_rpc: Callable[[str, list[Any]], Any],
    relay_get: Callable[[str], dict[str, Any]],
    base_rpc: Callable[[str, list[Any]], Any],
) -> dict[str, Any]:
    state, effect_unknown = _admission_state(admission_db, owner_id, occurrence_id)
    if state not in {"claimed", "released"} or effect_unknown != 1:
        return _inconclusive(owner_id, occurrence_id, "claimed_or_already_resolved")
    rows = _read_jsonl(state_dir / "sol-funding-receipts.jsonl")
    return build_official_proof(rows, owner_id=owner_id, occurrence_id=occurrence_id,
                                solana_rpc=solana_rpc, relay_get=relay_get, base_rpc=base_rpc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--owner-id", default=OWNER_ID)
    parser.add_argument("--state-dir", type=Path,
                        default=Path.home() / ".local/state/life-manager/sol-funding")
    parser.add_argument("--admission-db", type=Path,
                        default=Path.home() / ".local/state/life-manager/host-admission/resources/admission-v2.sqlite3")
    parser.add_argument("--solana-rpc-url", default="https://api.mainnet-beta.solana.com")
    parser.add_argument("--relay-api", default="https://api.relay.link")
    parser.add_argument("--base-rpc-url", default="https://mainnet.base.org")
    args = parser.parse_args(argv)
    if args.owner_id != OWNER_ID or not OCCURRENCE.fullmatch(args.occurrence_id):
        parser.error("owner and occurrence IDs are invalid")
    result = reconcile(
        state_dir=args.state_dir, admission_db=args.admission_db,
        owner_id=args.owner_id, occurrence_id=args.occurrence_id,
        solana_rpc=lambda method, params: _rpc(args.solana_rpc_url, method, params),
        relay_get=lambda endpoint: _get(args.relay_api, endpoint),
        base_rpc=lambda method, params: _rpc(args.base_rpc_url, method, params),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
