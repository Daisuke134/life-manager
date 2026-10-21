#!/usr/bin/env python3
"""Exercise actual pinned GrowthBook and SciPy on 3 fictional cohorts.

No experiment runs on the public website. Socket attempts fail this exercise.
The report contains aggregate synthetic diagnostics, never real participant IDs.
Run from products/manager with optional requirements installed, or prepend an
isolated dependency target to PYTHONPATH. No fixture allocator is substituted.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from manager_core.digital_experiment import (  # noqa: E402
    AssignmentSnapshot, OptInClaim, SyntheticUnit, assignment_health,
    config_for, config_hash, evaluate_candidate, prepare_assignment,
)


SIMULATION_CLOCK = datetime(2026, 10, 22, tzinfo=timezone.utc)
UNITS_PER_DOMAIN = 512


def opt_in(config, identifier):
    return OptInClaim(identifier, config_hash(config),
                      SIMULATION_CLOCK - timedelta(minutes=5),
                      SIMULATION_CLOCK + timedelta(hours=1))


def compact_decision(decision):
    return {name: getattr(decision, name) for name in (
        "decision", "reason", "candidate_route", "live_action_allowed",
        "experiment_enabled", "action_executed", "external_authority",
        "human_outcome", "causal_lift_status", "proof_level")}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def exercise_domain(domain):
    config = config_for(domain)
    records = []
    for number in range(UNITS_PER_DOMAIN):
        identifier = f"synthetic-unit-{number:06d}"
        unit = SyntheticUnit(identifier)
        consent = opt_in(config, identifier)
        first = prepare_assignment(config, unit, consent, SIMULATION_CLOCK)
        require(first.status == "SYNTHETIC_ASSIGNMENT_PREPARED", f"{domain}: {first.status}")
        repeated = prepare_assignment(config, unit, consent, SIMULATION_CLOCK, previous=first.assignment)
        require(repeated.status == "SYNTHETIC_ASSIGNMENT_REUSED" and repeated.assignment == first.assignment,
                f"{domain}: actual SDK assignment was not stable")
        records.append(first.assignment)
    snapshot = AssignmentSnapshot(config_hash(config), SIMULATION_CLOCK, tuple(records))
    health = assignment_health(config, snapshot, SIMULATION_CLOCK)
    require(health.status == "HEALTHY" and health.total_units == UNITS_PER_DOMAIN, f"{domain}: {health.reason}")
    control_id = next(r.unit_id for r in records if r.variation_id == 0)
    treatment_id = next(r.unit_id for r in records if r.variation_id == 1)
    control = evaluate_candidate(config, SyntheticUnit(control_id), opt_in(config, control_id), snapshot, SIMULATION_CLOCK)
    candidate = evaluate_candidate(config, SyntheticUnit(treatment_id), opt_in(config, treatment_id), snapshot, SIMULATION_CLOCK)
    require(control.decision == "NO_ACTION" and control.reason == "CONTROL_HOLDOUT", "holdout changed")
    require(candidate.decision == "SYNTHETIC_CANDIDATE" and candidate.candidate_route == f"/manager-support/{domain}.html",
            "candidate left the existing domain route")
    require(not candidate.live_action_allowed and not candidate.experiment_enabled and not candidate.action_executed,
            "offline exercise claimed a live effect")

    # Deliberately select a biased subset of authentic synthetic assignments.
    # This is a refusal probe, not an observed field fault or new experiment.
    biased_rows = tuple([r for r in records if r.variation_id == 0][:90]
                        + [r for r in records if r.variation_id == 1][:10])
    biased = replace(snapshot, assignments=biased_rows)
    biased_id = next(r.unit_id for r in biased_rows if r.variation_id == 1)
    mismatch = evaluate_candidate(config, SyntheticUnit(biased_id), opt_in(config, biased_id), biased, SIMULATION_CLOCK)
    require(mismatch.decision == "NO_ACTION" and mismatch.reason == "SAMPLE_RATIO_MISMATCH", "SRM did not stop candidate")

    refusal_inputs = {
        "revoked_consent": (SyntheticUnit(treatment_id), replace(opt_in(config, treatment_id), status="REVOKED"), snapshot),
        "expired_consent": (SyntheticUnit(treatment_id), replace(opt_in(config, treatment_id), expires_at=SIMULATION_CLOCK), snapshot),
        "missing_consent": (SyntheticUnit(treatment_id), None, snapshot),
        "real_participant_claim": (SyntheticUnit(treatment_id, "REAL_PARTICIPANT"), opt_in(config, treatment_id), snapshot),
        "health_missing": (SyntheticUnit(treatment_id), opt_in(config, treatment_id), None),
        "duplicate_unit": (SyntheticUnit(treatment_id), opt_in(config, treatment_id),
                           replace(snapshot, assignments=snapshot.assignments + (snapshot.assignments[0],))),
    }
    refusals = {}
    for label, (unit, consent, observed) in refusal_inputs.items():
        decision = evaluate_candidate(config, unit, consent, observed, SIMULATION_CLOCK)
        require(decision.decision == "NO_ACTION" and not decision.live_action_allowed, f"{label}: refusal failed")
        refusals[label] = compact_decision(decision)

    return {
        "configuration": asdict(config), "configuration_sha256": config_hash(config),
        "assignment_unit": "FICTIONAL_SYNTHETIC_UNIT", "units": UNITS_PER_DOMAIN,
        "deterministic_replay_units": UNITS_PER_DOMAIN,
        "assignment_counts": dict(zip(config.variations, health.counts)),
        "health": asdict(health), "control": compact_decision(control),
        "treatment_candidate": compact_decision(candidate),
        "constructed_srm_refusal_probe": {
            "selection": "First 90 control plus first 10 treatment from the fictional cohort",
            "observed_field_fault": False, "counts": list(mismatch.health.counts),
            "statistic": mismatch.health.statistic, "p_value": mismatch.health.p_value,
            "decision": compact_decision(mismatch),
        },
        "refusal_probes": refusals,
    }


def run():
    # Block real network access while exercising the real installed packages.
    # A hidden attempt also fails the final assertions even if an SDK catches it.
    with (
        patch("socket.create_connection", side_effect=RuntimeError("offline exercise forbids network")) as connect,
        patch("socket.socket.connect", side_effect=RuntimeError("offline exercise forbids network")) as socket_connect,
    ):
        domains = {domain: exercise_domain(domain) for domain in ("finance", "mental", "physical")}
        connect.assert_not_called()
        socket_connect.assert_not_called()
    return {
        "schema": "manager.synthetic-experiment-check.v1",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "simulation_clock": SIMULATION_CLOCK.isoformat(),
        "data_class": "SYNTHETIC_ONLY", "proof_level": "P0",
        "engines": {package: version(package) for package in ("growthbook", "scipy", "numpy")},
        "real_participants": 0, "external_writes": 0, "network_connection_attempts": 0,
        "live_action_allowed": False, "experiment_enabled": False,
        "external_authority": "NOT_ESTABLISHED", "human_outcome": "NOT_MEASURED",
        "causal_lift_status": "NOT_ESTIMATED", "domains": domains,
        "limits": [
            "Self-supplied synthetic consent and hashes authenticate no external permission.",
            "Unique assignment counts are not verified real exposures, participants or beneficiaries.",
            "SRM checks assignment balance only. It provides no causal lift or welfare estimate.",
            "The public static site is unchanged and has no enabled experiment or tracking.",
        ],
        "primary_sources": [
            "https://docs.growthbook.io/lib/python",
            "https://docs.growthbook.io/app/experiment-results#experiment-balance-srm",
            "https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.chisquare.html",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True,
                     default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value)))
