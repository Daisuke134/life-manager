"""Tests for the occurrence-bound, read-only x402 settlement reconciler."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "settlement_reconcile.py"
SPEC = importlib.util.spec_from_file_location("x402_settlement_reconcile", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


OWNER = "x402-settlement-recorder"
OCCURRENCE = f"{OWNER}:fixture-1"
TX = "0x" + "a" * 64
PAY_TO = "0x" + "b" * 40
FROM = "0x" + "c" * 40


def _receipt(**overrides):
    value = {
        "occurrence_id": OCCURRENCE,
        "provider_receipt_id": TX,
        "official_readback_ref": f"base://tx/{TX}",
        "proof_kind": "base_finalized_usdc_transfer",
        "verified": True,
        "tx": TX,
        "block": 123,
        "from": FROM,
        "payTo": PAY_TO,
        "usdc_atomic": "10000",
        "finalized": True,
        "status": "success",
        "external": True,
    }
    value.update(overrides)
    return value


def test_exact_occurrence_and_provider_receipt_are_required():
    proof = MODULE.build_proof_from_rows(
        [_receipt()], owner_id=OWNER, occurrence_id=OCCURRENCE,
    )
    assert proof["verified"] is True
    assert proof["owner_id"] == OWNER
    assert proof["occurrence_id"] == OCCURRENCE
    assert proof["provider_receipt_id"] == TX
    assert proof["official_readback_ref"] == f"base://tx/{TX}"

    missing = MODULE.build_proof_from_rows(
        [_receipt(occurrence_id=None)], owner_id=OWNER, occurrence_id=OCCURRENCE,
    )
    assert missing["status"] == "inconclusive"
    assert missing["reason"] == "occurrence_receipt_missing"


def test_multiple_matching_receipts_fail_closed_as_ambiguous():
    result = MODULE.build_proof_from_rows(
        [_receipt(), _receipt(provider_receipt_id="0x" + "d" * 64,
                              official_readback_ref="base://tx/0x" + "d" * 64,
                              tx="0x" + "d" * 64)],
        owner_id=OWNER, occurrence_id=OCCURRENCE,
    )
    assert result["status"] == "inconclusive"
    assert result["reason"] == "occurrence_receipt_ambiguous"


def test_base_readback_must_match_finalized_usdc_transfer():
    local = _receipt()
    finalized = {"number": hex(124)}
    chain_receipt = {
        "transactionHash": TX,
        "blockNumber": hex(123),
        "status": "0x1",
        "logs": [{
            "address": MODULE.USDC_ADDRESS,
            "topics": [
                MODULE.TRANSFER_TOPIC,
                "0x" + "0" * 24 + FROM[2:],
                "0x" + "0" * 24 + PAY_TO[2:],
            ],
            "data": hex(10000),
            "transactionHash": TX,
        }],
    }
    assert MODULE.verify_base_readback(local, finalized, chain_receipt) is True
    assert MODULE.verify_base_readback(local, {"number": hex(122)}, chain_receipt) is False
    assert MODULE.verify_base_readback(local, finalized,
                                      {**chain_receipt, "status": "0x0"}) is False


def test_official_proof_requires_fresh_base_readback():
    local = _receipt()

    def rpc(method, _params):
        return {
            "eth_chainId": "0x2105",
            "eth_getBlockByNumber": {"number": hex(124)},
            "eth_getTransactionReceipt": {
                "transactionHash": TX,
                "blockNumber": hex(123),
                "status": "0x1",
                "logs": [{
                    "address": MODULE.USDC_ADDRESS,
                    "topics": [
                        MODULE.TRANSFER_TOPIC,
                        "0x" + "0" * 24 + FROM[2:],
                        "0x" + "0" * 24 + PAY_TO[2:],
                    ],
                    "data": hex(10000),
                    "transactionHash": TX,
                }],
            },
        }[method]

    proof = MODULE.build_official_proof(
        [local], owner_id=OWNER, occurrence_id=OCCURRENCE, rpc=rpc,
    )
    assert proof["status"] == "ready"
    assert proof["provider_readback"]["chain_id"] == 8453
