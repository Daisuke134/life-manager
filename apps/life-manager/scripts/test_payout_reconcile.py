"""Tests for the occurrence-bound, read-only payout reconciler."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("payout-reconcile.py")
SPEC = importlib.util.spec_from_file_location("payout_reconcile", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


OWNER = "life-manager-payout"
OCCURRENCE = f"{OWNER}:fixture-1"
TX = "0x" + "a" * 64
FROM = "0x" + "b" * 40
TO = "0x" + "c" * 40


def _row(**overrides):
    value = {
        "occurrence_id": OCCURRENCE,
        "provider_receipt_id": TX,
        "official_readback_ref": f"base://tx/{TX}",
        "proof_kind": "base_provider_settlement_receipt",
        "verified": True,
        "tx_hash": TX,
        "amount_atomic": "7000000",
        "from": FROM,
        "to": TO,
        "block_number": "123",
        "status": "transferred",
        "effect_status": "submitted",
    }
    value.update(overrides)
    return value


def _receipt(status="0x1"):
    return {
        "transactionHash": TX,
        "blockNumber": "0x7a",
        "status": status,
        "logs": [{
            "address": MODULE.USDC_BASE,
            "topics": [
                MODULE.TRANSFER_TOPIC,
                "0x" + "0" * 24 + FROM[2:],
                "0x" + "0" * 24 + TO[2:],
            ],
            "data": "0x6acfc0",
            "transactionHash": TX,
        }],
    }


def test_exact_occurrence_and_unique_provider_receipt_are_required():
    result = MODULE.build_proof_from_rows([_row()], owner_id=OWNER, occurrence_id=OCCURRENCE)
    assert result["status"] == "ready"
    assert result["provider_receipt_id"] == TX
    assert result["official_readback_ref"] == f"base://tx/{TX}"
    assert MODULE.build_proof_from_rows([_row(occurrence_id=None)], owner_id=OWNER,
                                        occurrence_id=OCCURRENCE)["reason"] == "occurrence_receipt_missing"
    assert MODULE.build_proof_from_rows([_row(), _row(tx_hash="0x" + "d" * 64,
                                                      provider_receipt_id="0x" + "d" * 64,
                                                      official_readback_ref="base://tx/0x" + "d" * 64)],
                                        owner_id=OWNER, occurrence_id=OCCURRENCE)["reason"] == "occurrence_receipt_ambiguous"


def test_base_readback_requires_exact_finalized_transfer():
    row = _row()
    assert MODULE.verify_base_readback(row, {"number": "0x7b"}, _receipt()) is True
    assert MODULE.verify_base_readback(row, {"number": "0x7b"}, None) is False
    assert MODULE.verify_base_readback(row, None, _receipt()) is False
    assert MODULE.verify_base_readback(row, {"number": "0x79"}, _receipt()) is False
    assert MODULE.verify_base_readback(row, {"number": "0x7b"}, _receipt("0x0")) is False


def test_official_proof_requires_fresh_base_readback():
    result = MODULE.build_official_proof(
        [_row()], owner_id=OWNER, occurrence_id=OCCURRENCE,
        rpc=lambda method, _params: {
            "eth_chainId": "0x2105",
            "eth_getBlockByNumber": {"number": "0x7b"},
            "eth_getTransactionReceipt": _receipt(),
        }[method],
    )
    assert result["status"] == "ready"
    assert result["provider_readback"]["chain_id"] == 8453
