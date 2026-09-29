#!/usr/bin/env python3
"""Persist planner-grounded CrowdWorks observations before any provider effect."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
SHARED = Path(__file__).resolve().parents[3] / "_shared" / "marketplace-core" / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name}_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_adapter = _load(HERE / "opportunity_adapter.py", "crowdworks_opportunity_adapter_for_observation")
_runner = _load(SHARED / "opportunity_discovery.py", "crowdworks_opportunity_runner_for_observation")
_store = _load(SHARED / "opportunity_observation_store.py", "crowdworks_opportunity_store_for_observation")
CrowdWorksSnapshotSource = _adapter.CrowdWorksSnapshotSource
run_opportunity_discovery = _runner.run_opportunity_discovery
OpportunityObservationStore = _store.OpportunityObservationStore


class CrowdWorksObservationError(ValueError):
    """The CrowdWorks snapshot cannot be safely recorded."""


def _decision_map(decisions: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(decisions, dict) or not isinstance(decisions.get("decisions"), list):
        raise CrowdWorksObservationError("decisions_invalid")
    result: dict[str, dict[str, Any]] = {}
    for row in decisions["decisions"]:
        if not isinstance(row, dict):
            raise CrowdWorksObservationError("decision_row_invalid")
        request_id = str(row.get("request_id") or "").strip()
        if not request_id or request_id in result:
            raise CrowdWorksObservationError("decision_request_id_invalid")
        result[request_id] = row
    return result


def _judge_factory(decision_by_id: dict[str, dict[str, Any]], evidence_ref: str):
    def judge(opportunity: Any, _detail: Any) -> dict[str, Any]:
        job_id = str(opportunity.opportunity_id).removeprefix("job:")
        decision = decision_by_id.get(job_id)
        if decision is None:
            return {
                "decision": "hold",
                "reasons": ["planner_decision_missing"],
                "evidence_refs": [evidence_ref],
                "next_action": "await_planner_decision",
            }
        business_class = str(decision.get("business_class") or "")
        if business_class == "submit_required":
            return {
                "decision": "eligible",
                "reasons": ["planner_submit_required"],
                "evidence_refs": [evidence_ref],
                "next_action": "crowdworks_application_effect",
            }
        if business_class == "hard_prohibited":
            reasons = decision.get("reason_codes")
            reason = str(reasons[0]) if isinstance(reasons, list) and reasons else "hard_prohibited"
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
            "next_action": "retain_crowdworks_effect_fence",
        }

    return judge


def observe_crowdworks_opportunities(
    snapshot: dict[str, Any],
    decisions: dict[str, Any],
    *,
    store_root: str | Path,
    evidence_ref: str,
    max_items: int = 40,
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise CrowdWorksObservationError("snapshot_invalid")
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        raise CrowdWorksObservationError("evidence_ref_invalid")
    decision_by_id = _decision_map(decisions)
    source = CrowdWorksSnapshotSource(lambda: snapshot, max_items=max_items)
    store = OpportunityObservationStore(store_root)
    try:
        return run_opportunity_discovery(
            source,
            _judge_factory(decision_by_id, evidence_ref.strip()),
            store,
            max_items=max_items,
        )
    except CrowdWorksObservationError:
        raise
    except Exception as error:  # noqa: BLE001 - typed read-only boundary
        raise CrowdWorksObservationError("observation_failed") from error


__all__ = ["CrowdWorksObservationError", "observe_crowdworks_opportunities"]
