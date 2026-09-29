#!/usr/bin/env python3
"""Connect one live Coconala application snapshot to shared read-only observations."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any


SCRIPTS = Path(__file__).resolve().parent
SHARED = Path(__file__).resolve().parents[3] / "_shared" / "marketplace-core" / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name}_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from coconala_opportunity_adapter import CoconalaSnapshotSource
except ModuleNotFoundError:  # pragma: no cover - direct module loading fallback
    CoconalaSnapshotSource = _load(
        SCRIPTS / "coconala_opportunity_adapter.py",
        "coconala_opportunity_adapter_for_observation",
    ).CoconalaSnapshotSource

_runner = _load(
    SHARED / "opportunity_discovery.py", "coconala_opportunity_discovery_for_observation",
)
_store = _load(
    SHARED / "opportunity_observation_store.py", "coconala_opportunity_store_for_observation",
)
run_opportunity_discovery = _runner.run_opportunity_discovery
OpportunityObservationStore = _store.OpportunityObservationStore


class CoconalaObservationError(ValueError):
    """The live snapshot cannot be converted into a safe observation wake."""


def _decision_map(decisions: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(decisions, dict) or not isinstance(decisions.get("decisions"), list):
        raise CoconalaObservationError("decisions_invalid")
    result: dict[str, dict[str, Any]] = {}
    for row in decisions["decisions"]:
        if not isinstance(row, dict):
            raise CoconalaObservationError("decision_row_invalid")
        request_id = str(row.get("request_id") or "").strip()
        if not request_id or request_id in result:
            raise CoconalaObservationError("decision_request_id_invalid")
        result[request_id] = row
    return result


def _judge_factory(
    decision_by_id: dict[str, dict[str, Any]], evidence_ref: str,
):
    def judge(opportunity: Any, _detail: Any) -> dict[str, Any]:
        request_id = str(opportunity.opportunity_id).removeprefix("request:")
        decision = decision_by_id.get(request_id)
        if decision is None:
            return {
                "decision": "hold",
                "reasons": ["planner_decision_missing"],
                "evidence_refs": [evidence_ref],
                "next_action": "await_planner_decision",
            }
        business_class = str(decision.get("business_class") or "")
        if business_class == "submit_required" or decision.get("eligibility") == "eligible":
            return {
                "decision": "eligible",
                "reasons": ["planner_submit_required"],
                "evidence_refs": [evidence_ref],
                "next_action": "application_parent_commit",
            }
        if business_class == "hard_prohibited":
            reason_codes = decision.get("reason_codes")
            reason = str(reason_codes[0]) if isinstance(reason_codes, list) and reason_codes else "hard_prohibited"
            return {
                "decision": "hold",
                "reasons": ["planner_hard_prohibited", reason],
                "evidence_refs": [evidence_ref],
                "next_action": "do_not_apply",
            }
        return {
            "decision": "hold",
            "reasons": ["planner_not_submit_required"],
            "evidence_refs": [evidence_ref],
            "next_action": "retain_application_parent_fence",
        }

    return judge


def observe_coconala_opportunities(
    snapshot: dict[str, Any],
    decisions: dict[str, Any],
    *,
    store_root: str | Path,
    evidence_ref: str,
    max_items: int = 40,
) -> dict[str, Any]:
    """Persist planner-grounded opportunity observations without provider mutation."""

    if not isinstance(snapshot, dict):
        raise CoconalaObservationError("snapshot_invalid")
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        raise CoconalaObservationError("evidence_ref_invalid")
    decision_by_id = _decision_map(decisions)
    source = CoconalaSnapshotSource(lambda: snapshot, max_items=max_items)
    store = OpportunityObservationStore(store_root)
    try:
        return run_opportunity_discovery(
            source,
            _judge_factory(decision_by_id, evidence_ref.strip()),
            store,
            max_items=max_items,
        )
    except CoconalaObservationError:
        raise
    except Exception as error:  # noqa: BLE001 - preserve one typed boundary for the caller
        raise CoconalaObservationError("observation_failed") from error


__all__ = ["CoconalaObservationError", "observe_coconala_opportunities"]
