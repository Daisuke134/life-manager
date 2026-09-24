"""Tests for the occurrence-bound Solana/Relay/Base reconciler."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "sol_funding_reconcile.py"
SPEC = importlib.util.spec_from_file_location("sol_funding_reconcile", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


OWNER = "sol-funding"
OCCURRENCE = f"{OWNER}:fixture-1"
SIGNATURE = "5" * 64
DEST_TX = "0x" + "a" * 64
RECIPIENT = "0x" + "b" * 40


def _row(**overrides):
    row = {
        "occurrence_id": OCCURRENCE,
        "provider_receipt_id": SIGNATURE,
        "relay_check_endpoint": "/intents/status/fixture-1",
        "relay_status": "success",
        "destination_tx_hash": DEST_TX,
        "destination_chain_id": 8453,
        "destination_currency": MODULE.USDC_BASE,
        "recipient": RECIPIENT,
        "effect_status": "submitted",
    }
    row.update(overrides)
    return row


def _base_receipt(status="0x1"):
    return {
        "transactionHash": DEST_TX,
        "blockNumber": "0x7a",
        "status": status,
        "logs": [{
            "address": MODULE.USDC_BASE,
            "topics": [
                MODULE.TRANSFER_TOPIC,
                "0x" + "0" * 64,
                "0x" + "0" * 24 + RECIPIENT[2:],
            ],
            "data": "0x2710",
            "transactionHash": DEST_TX,
        }],
    }


def test_exact_occurrence_receipt_is_required_and_ambiguous_rows_hold():
    proof = MODULE.build_proof_from_rows([_row()], owner_id=OWNER, occurrence_id=OCCURRENCE)
    assert proof["status"] == "ready"
    assert proof["provider_receipt_id"] == SIGNATURE
    assert proof["official_readback_ref"] == "relay://intents/status/fixture-1"
    assert MODULE.build_proof_from_rows([_row(occurrence_id=None)], owner_id=OWNER,
                                        occurrence_id=OCCURRENCE)["reason"] == "occurrence_receipt_missing"
    assert MODULE.build_proof_from_rows([_row(), _row(destination_tx_hash="0x" + "c" * 64)],
                                        owner_id=OWNER, occurrence_id=OCCURRENCE)["reason"] == "occurrence_receipt_ambiguous"


def test_each_provider_boundary_requires_success_and_exact_identity():
    assert MODULE.verify_solana_status({"err": None, "confirmationStatus": "finalized"}) is True
    assert MODULE.verify_solana_status({"err": "failed", "confirmationStatus": "finalized"}) is False
    row = _row()
    assert MODULE.verify_relay_readback(row, {"status": "success", "txHashes": [DEST_TX]}) is True
    assert MODULE.verify_relay_readback(row, {"status": "success", "txHashes": []}) is False
    assert MODULE.verify_base_readback(row, {"number": "0x7b"}, _base_receipt()) is True
    assert MODULE.verify_base_readback(row, {"number": "0x7b"}, None) is False
    assert MODULE.verify_base_readback(row, None, _base_receipt()) is False
    assert MODULE.verify_base_readback(row, {"number": "0x79"}, _base_receipt()) is False


def test_official_proof_requires_all_three_fresh_readbacks():
    row = _row()

    def solana_rpc(method, _params):
        assert method == "getSignatureStatuses"
        return {"value": [{"err": None, "confirmationStatus": "confirmed"}]}

    proof = MODULE.build_official_proof(
        [row], owner_id=OWNER, occurrence_id=OCCURRENCE,
        solana_rpc=solana_rpc,
        relay_get=lambda endpoint: {"status": "success", "txHashes": [DEST_TX]},
        base_rpc=lambda method, _params: {
            "eth_chainId": "0x2105",
            "eth_getBlockByNumber": {"number": "0x7b"},
            "eth_getTransactionReceipt": _base_receipt(),
        }[method],
    )
    assert proof["status"] == "ready"
    assert proof["provider_readback"]["base"]["chain_id"] == 8453
