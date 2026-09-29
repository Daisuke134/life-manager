from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


PATH = Path(__file__).resolve().parents[1] / "scripts" / "providers" / "upwork_paid_adapter.py"
CONTRACTS_PATH = Path(__file__).resolve().parents[3] / "_shared" / "marketplace-core" / "scripts" / "contracts.py"


def _load():
    assert PATH.is_file(), "Upwork Paid adapter is not implemented"
    spec = importlib.util.spec_from_file_location("upwork_paid_adapter_test", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate(bundle):
    spec = importlib.util.spec_from_file_location("upwork_marketplace_contracts_test", CONTRACTS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.validate_paid_handoff(bundle["handoff"], bundle["contract"])


def _context(state: str = "funded"):
    return {
        "contract": {
            "contract_id": "contract-1",
            "state": state,
            "funded_milestone_minor": 50000,
            "source_url": "https://www.upwork.com/ab/workroom/contract-1",
            "source_hash": "a" * 64,
            "observed_at": "2026-09-29T00:00:00Z",
        },
        "application_external_id": "application:upwork:contract-1",
        "thread_external_id": "room:buyer-1",
        "funding_external_id": "milestone:contract-1",
        "currency": "USD",
        "scope_sha256": "b" * 64,
        "artifact_requirement_sha256": "c" * 64,
    }


def test_funded_upwork_contract_maps_to_shared_paid_handoff():
    module = _load()
    adapter = module.UpworkPaidAdapter(account_id="upwork-account-1")

    bundle = adapter.paid_handoff("contract-1", _context())

    _validate(bundle)
    assert bundle["contract"]["platform"] == "upwork"
    assert bundle["handoff"]["price_minor"] == 50000
    assert bundle["handoff"]["currency"] == "USD"
    assert bundle["handoff"]["status"] == "funded"


def test_upwork_contract_without_funded_milestone_is_rejected():
    module = _load()
    adapter = module.UpworkPaidAdapter(account_id="upwork-account-1")
    context = _context()
    context["contract"]["funded_milestone_minor"] = 0

    with pytest.raises(RuntimeError, match="upwork_paid_handoff_unavailable"):
        adapter.paid_handoff("contract-1", context)


def test_upwork_handoff_requires_scope_and_artifact_evidence():
    module = _load()
    adapter = module.UpworkPaidAdapter(account_id="upwork-account-1")
    context = _context()
    context.pop("artifact_requirement_sha256")

    with pytest.raises(RuntimeError, match="upwork_paid_handoff_unavailable"):
        adapter.paid_handoff("contract-1", context)


def test_upwork_handoff_does_not_assume_currency():
    module = _load()
    adapter = module.UpworkPaidAdapter(account_id="upwork-account-1")
    context = _context()
    context.pop("currency")

    with pytest.raises(RuntimeError, match="upwork_paid_handoff_unavailable"):
        adapter.paid_handoff("contract-1", context)
