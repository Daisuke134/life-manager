"""Arbitrum native USDC deposits to Hyperliquid Bridge2 from the agent wallet."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger

ARB_RPC = "https://arb1.arbitrum.io/rpc"
ARBITRUM_CHAIN_ID = 42161
USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
BRIDGE2 = "0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7"
MIN_USDC = 5.0
MIN_ETH = 0.00005
USDC_DECIMALS = 6
TRANSFER_SELECTOR = "a9059cbb"

ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "transfer",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
]


def plan(usdc_balance: float, eth_balance: float) -> dict:
    """Return a deposit decision without I/O, signing, or mutation."""
    if usdc_balance < MIN_USDC:
        return {"action": "wait", "amount": 0.0, "reason": "usdc_below_bridge_minimum"}
    if eth_balance < MIN_ETH:
        return {"action": "wait", "amount": 0.0, "reason": "no_arbitrum_gas"}
    return {"action": "deposit", "amount": float(usdc_balance), "reason": "funded"}


def may_send(decision: dict, live_value: str | None) -> bool:
    """Keep signing disabled unless both the plan and explicit live gate permit it."""
    return decision["action"] == "deposit" and live_value == "1"


def pending_deposits(lg: ledger.Ledger) -> list[dict]:
    return [row for row in lg.open_intents() if row.get("action") == "deposit"]


def may_submit(lg: ledger.Ledger) -> bool:
    """A pending or effect-unknown deposit is an effect fence, never a resend cue."""
    return not pending_deposits(lg)


def _last_receipt(lg: ledger.Ledger, intent_id: str) -> dict | None:
    return next((row for row in reversed(lg.rows())
                 if row["kind"] == "receipt" and row.get("intent_id") == intent_id), None)


def _receipt_status(receipt) -> int:
    return int(receipt["status"] if isinstance(receipt, dict) else receipt.status)


def _input_hex(value) -> str:
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    return str(value)


def _boundary_reason(w3, tx_hash: str, intent: dict) -> str | None:
    try:
        chain_id = int(w3.eth.chain_id)
    except Exception as e:
        return f"deposit_boundary_chain_readback_{type(e).__name__}"
    if chain_id != ARBITRUM_CHAIN_ID:
        return "deposit_boundary_chain_mismatch"
    try:
        recorded_chain = int(intent["chain"])
    except (KeyError, TypeError, ValueError):
        return "deposit_boundary_recorded_chain_missing"
    if recorded_chain != ARBITRUM_CHAIN_ID:
        return "deposit_boundary_recorded_chain_mismatch"
    try:
        tx = w3.eth.get_transaction(tx_hash)
    except Exception as e:
        return f"deposit_boundary_transaction_readback_{type(e).__name__}"
    if not tx:
        return "deposit_boundary_transaction_missing"
    if str(tx.get("from", "")).lower() != str(intent.get("sender", "")).lower():
        return "deposit_boundary_sender_mismatch"
    if str(tx.get("to", "")).lower() != str(intent.get("token", "")).lower():
        return "deposit_boundary_token_mismatch"
    data = _input_hex(tx.get("input", tx.get("data", ""))).lower()
    payload = data[2:] if data.startswith("0x") else data
    if len(payload) != 8 + 64 + 64:
        return "deposit_boundary_transfer_calldata_mismatch"
    try:
        bytes.fromhex(payload)
    except (TypeError, ValueError):
        return "deposit_boundary_transfer_calldata_mismatch"
    if payload[:8] != TRANSFER_SELECTOR:
        return "deposit_boundary_transfer_calldata_mismatch"
    target = "0x" + payload[8:72][-40:]
    if target.lower() != str(intent.get("bridge", "")).lower():
        return "deposit_boundary_bridge_mismatch"
    try:
        raw_amount = int(payload[72:136], 16)
    except (TypeError, ValueError):
        return "deposit_boundary_transfer_calldata_mismatch"
    if raw_amount != int(intent.get("raw_amount", -1)):
        return "deposit_boundary_amount_mismatch"
    return None


def _settle(w3, lg: ledger.Ledger, intent: dict, tx_hash: str, receipt) -> dict:
    reason = _boundary_reason(w3, tx_hash, intent)
    if reason:
        return lg.append("receipt", intent_id=intent["intent_id"], result="effect_unknown",
                         tx_hash=tx_hash, reason=reason)
    try:
        status = _receipt_status(receipt)
    except (AttributeError, KeyError, TypeError, ValueError):
        return lg.append("receipt", intent_id=intent["intent_id"], result="effect_unknown",
                         tx_hash=tx_hash, reason="deposit_receipt_status_unknown")
    if status not in (0, 1):
        return lg.append("receipt", intent_id=intent["intent_id"], result="effect_unknown",
                         tx_hash=tx_hash, reason="deposit_receipt_status_unknown")
    result = "deposited" if status == 1 else "failed"
    return lg.append("receipt", intent_id=intent["intent_id"], result=result, tx_hash=tx_hash)


def reconcile_pending(w3, lg: ledger.Ledger) -> dict | None:
    """Read back one pending deposit without ever resubmitting it."""
    pending = pending_deposits(lg)
    if not pending:
        return None
    intent = pending[0]
    prior = _last_receipt(lg, intent["intent_id"]) or {}
    tx_hash = prior.get("tx_hash")
    if not tx_hash:
        return {"result": "effect_unknown", "reason": "missing_tx_hash", "intent_id": intent["intent_id"]}
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception as e:
        return lg.append("receipt", intent_id=intent["intent_id"], result="effect_unknown", tx_hash=tx_hash,
                         error=type(e).__name__)
    if receipt is None:
        return {"result": "submitted", "tx_hash": tx_hash, "intent_id": intent["intent_id"]}
    return _settle(w3, lg, intent, tx_hash, receipt)


def _tx_hash(tx_hash) -> str:
    return tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)


def submit(w3, token, acct, raw_amount: int, lg: ledger.Ledger) -> dict:
    """Journal a live bridge transfer through its provider receipt; never retry here."""
    if not may_submit(lg):
        return {"result": "effect_unknown", "reason": "pending_deposit"}
    iid = uuid.uuid4().hex
    intent = lg.append("intent", intent_id=iid, action="deposit", sender=acct.address, token=USDC,
                       bridge=BRIDGE2, chain=ARBITRUM_CHAIN_ID, raw_amount=int(raw_amount))
    try:
        tx = token.functions.transfer(BRIDGE2, int(raw_amount)).build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "chainId": ARBITRUM_CHAIN_ID,
        })
        signed = acct.sign_transaction(tx)
    except Exception as e:
        return lg.append("receipt", intent_id=iid, result="failed", error=type(e).__name__)
    try:
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    except Exception as e:
        return lg.append("receipt", intent_id=iid, result="effect_unknown", error=type(e).__name__)
    tx_hex = _tx_hash(tx_hash)
    lg.append("receipt", intent_id=iid, result="submitted", tx_hash=tx_hex)
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    except Exception as e:
        return lg.append("receipt", intent_id=iid, result="effect_unknown", tx_hash=tx_hex,
                         error=type(e).__name__)
    return _settle(w3, lg, intent, tx_hex, receipt)


def exit_code(result: dict) -> int:
    return 0 if result.get("result") == "deposited" else 1


def main() -> int:
    import wallet
    from web3 import Web3

    acct = wallet.load_or_create()
    w3 = Web3(Web3.HTTPProvider(ARB_RPC))
    state = Path(os.environ.get("LIFE_MANAGER_STATE_ROOT",
                                Path.home() / ".local/state/life-manager/hyperliquid-carry"))
    lg = ledger.Ledger(state / "journal.jsonl")
    pending = reconcile_pending(w3, lg)
    if pending is not None:
        print({"address": acct.address, "deposit": pending})
        return exit_code(pending)
    token = w3.eth.contract(address=Web3.to_checksum_address(USDC), abi=ERC20_ABI)
    usdc_raw = token.functions.balanceOf(acct.address).call()
    usdc = usdc_raw / 10**USDC_DECIMALS
    eth = w3.eth.get_balance(acct.address) / 10**18
    decision = plan(usdc, eth)
    print({"address": acct.address, "usdc": usdc, "eth": eth, **decision})

    if not may_send(decision, os.environ.get("HL_CARRY_LIVE")):
        return 0
    if w3.eth.chain_id != ARBITRUM_CHAIN_ID:
        print({"error": "unexpected_chain_id", "chain_id": w3.eth.chain_id})
        return 1

    receipt = submit(w3, token, acct, usdc_raw, lg)
    print(receipt)
    return exit_code(receipt)


if __name__ == "__main__":
    raise SystemExit(main())
