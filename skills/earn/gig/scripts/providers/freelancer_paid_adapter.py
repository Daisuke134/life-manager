#!/usr/bin/env python3
"""Freelancer funded-contract boundary for the shared Paid kernel."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Mapping


def _load_shared():
    path = Path(__file__).resolve().parents[4] / "_shared/marketplace-core/scripts/paid_handoff.py"
    spec = importlib.util.spec_from_file_location("freelancer_shared_paid_handoff", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("freelancer_paid_handoff_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SHARED = _load_shared()


class FreelancerPaidAdapter:
    """Map one official Freelancer funded milestone without opening transport."""

    def __init__(self, *, account_id: str):
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("freelancer_account_id_invalid")
        self.account_id = account_id.strip()

    def paid_handoff(self, work_id: str, context: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            if not isinstance(work_id, str) or not work_id.strip() or not isinstance(context, Mapping):
                raise _SHARED.PaidHandoffMappingError("context_invalid")
            contract = context.get("contract")
            if not isinstance(contract, Mapping):
                raise _SHARED.PaidHandoffMappingError("contract_invalid")
            if contract.get("contract_id") != work_id.strip() or contract.get("state") != "funded":
                raise _SHARED.PaidHandoffMappingError("contract_not_funded")
            account = context.get("account_id") or contract.get("account_id")
            if account is not None and account != self.account_id:
                raise _SHARED.PaidHandoffMappingError("account_mismatch")
            project_id = contract.get("project_id")
            if not isinstance(project_id, str) or not project_id.strip():
                raise _SHARED.PaidHandoffMappingError("project_id_invalid")
            application_id = context.get("application_external_id")
            if not isinstance(application_id, str) or not application_id.strip():
                application_id = f"application:freelancer:{project_id.strip()}"
            funding_id = context.get("funding_external_id")
            if not isinstance(funding_id, str) or not funding_id.strip():
                funding_id = f"milestone:{work_id.strip()}"
            return _SHARED.build_paid_handoff(
                platform="freelancer",
                application_external_id=application_id,
                work_external_id=work_id,
                contract_external_id=work_id,
                funding_external_id=funding_id,
                thread_external_id=context.get("thread_external_id"),
                terms_sha256=contract.get("source_hash"),
                scope_sha256=context.get("scope_sha256"),
                artifact_requirement_sha256=context.get("artifact_requirement_sha256"),
                price_minor=contract.get("amount_minor"),
                currency=contract.get("currency"),
                observed_at=contract.get("observed_at"),
            )
        except _SHARED.PaidHandoffMappingError as error:
            raise RuntimeError("freelancer_paid_handoff_unavailable") from error

    def mutate(self, intent: Mapping[str, Any]) -> None:
        raise RuntimeError("freelancer_paid_owner_not_registered")

    def readback(self, intent: Mapping[str, Any]) -> dict[str, Any]:
        return {"verified": False, "authoritative_absent": False}


__all__ = ["FreelancerPaidAdapter"]
