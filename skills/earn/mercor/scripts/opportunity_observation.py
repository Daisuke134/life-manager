#!/usr/bin/env python3
"""Persist read-only Mercor pass observations in the shared marketplace store."""

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


_adapter = _load(HERE / "opportunity_adapter.py", "mercor_opportunity_adapter_for_observation")
_runner = _load(SHARED / "opportunity_discovery.py", "mercor_opportunity_runner_for_observation")
_store = _load(SHARED / "opportunity_observation_store.py", "mercor_opportunity_store_for_observation")
MercorSnapshotSource = _adapter.MercorSnapshotSource
run_opportunity_discovery = _runner.run_opportunity_discovery
OpportunityObservationStore = _store.OpportunityObservationStore


class MercorObservationError(ValueError):
    """The Mercor pass result cannot be safely recorded."""


def _decision_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = snapshot.get("inspected_listings")
    if not isinstance(rows, list):
        raise MercorObservationError("inspected_listings_invalid")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise MercorObservationError("listing_row_invalid")
        listing_id = str(row.get("listing_id") or "").strip()
        if not listing_id or listing_id in result:
            raise MercorObservationError("listing_id_invalid")
        result[listing_id] = row
    return result


def _judge_factory(rows: dict[str, dict[str, Any]], evidence_ref: str):
    def judge(opportunity: Any, _detail: Any) -> dict[str, Any]:
        listing_id = str(opportunity.opportunity_id).removeprefix("listing:")
        row = rows.get(listing_id)
        if row is None:
            return {
                "decision": "hold",
                "reasons": ["pass_decision_missing"],
                "evidence_refs": [evidence_ref],
                "next_action": "await_mercor_pass_decision",
            }
        decision = str(row.get("decision") or "")
        fit = str(row.get("provider_fit_status") or "")
        state = str(row.get("application_state") or "")
        if decision == "submit_required" and fit != "blocked" and state not in {"submitted", "submitted_pending_review", "submitted_pending_review_observed"}:
            return {
                "decision": "eligible",
                "reasons": ["pass_submit_required"],
                "evidence_refs": [evidence_ref],
                "next_action": "mercor_application_effect",
            }
        if fit == "blocked" or decision in {"no_reasonable_shot", "hard_prohibited"}:
            return {
                "decision": "hold",
                "reasons": ["pass_provider_fit_blocked" if fit == "blocked" else "pass_do_not_apply"],
                "evidence_refs": [evidence_ref],
                "next_action": "do_not_apply",
            }
        return {
            "decision": "hold",
            "reasons": ["pass_observation_only"],
            "evidence_refs": [evidence_ref],
            "next_action": "retain_mercor_effect_fence",
        }

    return judge


def observe_mercor_opportunities(
    snapshot: dict[str, Any], *, store_root: str | Path, evidence_ref: str, max_items: int = 40,
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise MercorObservationError("snapshot_invalid")
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        raise MercorObservationError("evidence_ref_invalid")
    rows = _decision_map(snapshot)
    source = MercorSnapshotSource(lambda: snapshot, max_items=max_items)
    store = OpportunityObservationStore(store_root)
    try:
        return run_opportunity_discovery(
            source,
            _judge_factory(rows, evidence_ref.strip()),
            store,
            max_items=max_items,
        )
    except MercorObservationError:
        raise
    except Exception as error:  # noqa: BLE001 - typed read-only boundary
        raise MercorObservationError("observation_failed") from error


__all__ = ["MercorObservationError", "observe_mercor_opportunities"]
