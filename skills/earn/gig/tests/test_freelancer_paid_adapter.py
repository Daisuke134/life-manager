from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


PATH = Path(__file__).resolve().parents[1] / "scripts" / "providers" / "freelancer_paid_adapter.py"
CONTRACTS_PATH = Path(__file__).resolve().parents[3] / "_shared" / "marketplace-core" / "scripts" / "contracts.py"


def _load():
    assert PATH.is_file(), "Freelancer Paid adapter is not implemented"
    spec = importlib.util.spec_from_file_location("freelancer_paid_adapter_test", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate(bundle):
    spec = importlib.util.spec_from_file_location("freelancer_marketplace_contracts_test", CONTRACTS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.validate_paid_handoff(bundle["handoff"], bundle["contract"])


def _context(state: str = "funded"):
    return {
        "contract": {
            "project_id": "40620700",
            "contract_id": "project-40620700-milestone-7001",
            "state": state,
            "currency": "USD",
            "amount_minor": 25000,
            "source_url": "https://www.freelancer.com/projects/40620700",
            "source_hash": "a" * 64,
            "observed_at": "2026-09-29T00:00:00Z",
        },
        "application_external_id": "application:freelancer:40620700",
        "thread_external_id": "thread:buyer-1",
        "funding_external_id": "milestone:7001",
        "scope_sha256": "b" * 64,
        "artifact_requirement_sha256": "c" * 64,
    }


def test_funded_freelancer_contract_maps_to_shared_paid_handoff():
    module = _load()
    adapter = module.FreelancerPaidAdapter(account_id="94117802")

    bundle = adapter.paid_handoff(
        "project-40620700-milestone-7001", _context(),
    )

    _validate(bundle)
    assert bundle["contract"]["platform"] == "freelancer"
    assert bundle["handoff"]["price_minor"] == 25000
    assert bundle["handoff"]["currency"] == "USD"
    assert bundle["handoff"]["status"] == "funded"


def test_unfunded_freelancer_contract_is_rejected_before_mapping():
    module = _load()
    adapter = module.FreelancerPaidAdapter(account_id="94117802")

    with pytest.raises(RuntimeError, match="freelancer_paid_handoff_unavailable"):
        adapter.paid_handoff(
            "project-40620700-milestone-7001", _context(state="active"),
        )


def test_freelancer_handoff_requires_thread_and_artifact_evidence():
    module = _load()
    adapter = module.FreelancerPaidAdapter(account_id="94117802")
    context = _context()
    context.pop("thread_external_id")

    with pytest.raises(RuntimeError, match="freelancer_paid_handoff_unavailable"):
        adapter.paid_handoff(
            "project-40620700-milestone-7001", context,
        )
