"""Arbitrum native USDC deposits to Hyperliquid Bridge2 from the agent wallet."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ARB_RPC = "https://arb1.arbitrum.io/rpc"
ARBITRUM_CHAIN_ID = 42161
USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
BRIDGE2 = "0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7"
MIN_USDC = 5.0
MIN_ETH = 0.00005
USDC_DECIMALS = 6

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


def main() -> int:
    import wallet
    from web3 import Web3

    acct = wallet.load_or_create()
    w3 = Web3(Web3.HTTPProvider(ARB_RPC))
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

    tx = token.functions.transfer(Web3.to_checksum_address(BRIDGE2), usdc_raw).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "chainId": ARBITRUM_CHAIN_ID,
    })
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    print({"tx": tx_hash.hex(), "status": receipt.status})
    return 0 if receipt.status == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
