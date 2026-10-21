"""DoWhy adapter tests. All observations are generated fictional aggregates."""
import importlib
import importlib.util
import random
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from unittest.mock import patch

from manager_core.models.source import Source


START = datetime(2026, 10, 22, tzinfo=timezone.utc)


def causal():
    assert importlib.util.find_spec("manager_core.causal_analysis") is not None, "existing-library causal adapter missing"
    return importlib.import_module("manager_core.causal_analysis")


def source(name, payload, at=START - timedelta(days=1)):
    return Source(name, "https://example.org/" + name, "CC0-1.0", "allowed_with_conditions",
                  sha256(payload).hexdigest(), at, "public_nonpersonal")


def bound_plan(**changes):
    m = causal()
    values = dict(study_id="study-1", domain="financial", metric="outside_income", unit="JPY_minor/aggregate",
                  analysis_unit="fictional independent aggregate", started_at=START, ended_at=START + timedelta(days=28),
                  protocol=None, min_per_arm=20, placebo_tolerance=.5, minimum_robustness=.05,
                  confidence_level=.95, overlap_min=.05, simulations=30, random_seed=42)
    values.update(changes)
    plan = m.CausalAnalysisPlan(**values)
    return replace(plan, protocol=source("protocol", m.plan_snapshot(plan)))


def bind_data(data):
    return replace(data, source=source("aggregate-outcomes", causal().dataset_snapshot(data), START + timedelta(days=30)))


def dataset(plan=None, *, effect=2.0, kind="synthetic", count=160):
    m = causal()
    plan = plan or bound_plan()
    rng = random.Random(1019)
    rows = []
    for index in range(count):
        baseline = rng.gauss(0, 1)
        assigned = index % 2
        rows.append(m.CausalObservation(f"fictional-aggregate-{index}", assigned,
                                        effect * assigned + .7 * baseline + rng.gauss(0, .5), baseline, .5))
    return bind_data(m.CausalDataset(plan.study_id, plan.domain, plan.metric, plan.unit, tuple(rows), None, kind))


def safety():
    return causal().CausalSafety(0, "JPY", source("costs", b"fixture-costs"), 0,
                                 "adverse_events", "count", source("harms", b"fixture-harms"))


class CausalContractTests(unittest.TestCase):
    def test_missing_source_or_protocol_is_inconclusive_before_estimation(self):
        m = causal()
        plan, data = bound_plan(), dataset()
        for chosen_plan, chosen_data, reason in (
            (plan, replace(data, source=None), "OUTCOME_SOURCE_MISSING"),
            (replace(plan, protocol=None), data, "PROTOCOL_MISSING"),
        ):
            result = m.analyze_causal_study(chosen_plan, chosen_data)
            self.assertEqual(result.status, "INCONCLUSIVE")
            self.assertIn(reason, result.reasons)
            self.assertIsNone(result.estimate)
            self.assertEqual(result.harms_status, "UNKNOWN_HARMS")

    def test_missing_outcome_is_not_dropped_or_imputed(self):
        m = causal()
        plan, data = bound_plan(), dataset()
        data = bind_data(replace(data, observations=(replace(data.observations[0], outcome=None),) + data.observations[1:]))
        result = m.analyze_causal_study(plan, data)
        self.assertIn("MISSING_OUTCOMES", result.reasons)
        self.assertEqual(result.observation_count, len(data.observations))
        self.assertIsNone(result.estimate)

    def test_same_contract_preserves_domain_metric_and_units(self):
        m = causal()
        plan, data = bound_plan(), dataset()
        for field, value in (("unit", "ug/m3"), ("domain", "physical"), ("metric", "PM2.5"), ("study_id", "other")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.analyze_causal_study(plan, bind_data(replace(data, **{field: value})))

    def test_changed_data_or_plan_cannot_reuse_an_unrelated_source_hash(self):
        m = causal()
        plan, data = bound_plan(), dataset()
        changed = replace(data, observations=(replace(data.observations[0], outcome=99),) + data.observations[1:])
        with self.assertRaises(ValueError):
            m.analyze_causal_study(plan, changed)
        with self.assertRaises(ValueError):
            m.analyze_causal_study(replace(plan, placebo_tolerance=100), data)

    def test_small_or_single_arm_sample_is_inconclusive(self):
        m = causal()
        plan = bound_plan()
        result = m.analyze_causal_study(plan, dataset(plan, count=20))
        self.assertIn("INSUFFICIENT_ARM_COUNTS", result.reasons)
        self.assertIsNone(result.estimate)
        data = dataset(plan)
        data = bind_data(replace(data, observations=tuple(row for row in data.observations if row.assigned == 1)))
        self.assertIn("INSUFFICIENT_ARM_COUNTS", m.analyze_causal_study(plan, data).reasons)

    def test_missing_or_nonoverlapping_assignment_probabilities_fail_closed(self):
        m = causal()
        plan, data = bound_plan(), dataset()
        for value, reason in ((None, "PROPENSITY_UNKNOWN"), (0, "NO_PROPENSITY_OVERLAP"), (1, "NO_PROPENSITY_OVERLAP")):
            changed = bind_data(replace(data, observations=(replace(data.observations[0], propensity=value),) + data.observations[1:]))
            result = m.analyze_causal_study(plan, changed)
            self.assertIn(reason, result.reasons)
            self.assertIsNone(result.estimate)

    def test_disjoint_baseline_support_is_not_hidden_by_supplied_probability(self):
        m = causal()
        plan, data = bound_plan(), dataset()
        changed = bind_data(replace(data, observations=tuple(replace(row, baseline=100 + index if row.assigned else -100 - index)
                                                            for index, row in enumerate(data.observations))))
        result = m.analyze_causal_study(plan, changed)
        self.assertIn("NO_BASELINE_OVERLAP", result.reasons)
        self.assertIsNone(result.estimate)

    def test_invalid_rows_duplicate_units_and_self_asserted_welfare_kind_rejected(self):
        m = causal()
        data = dataset()
        for changes in ({"assigned": True}, {"outcome": float("nan")}, {"baseline": float("inf")}, {"propensity": 2}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(data.observations[0], **changes)
        with self.assertRaises(ValueError):
            replace(data, observations=data.observations + (data.observations[0],))
        with self.assertRaises(ValueError):
            replace(data, kind="independently_verified_welfare")

    def test_missing_dependency_has_no_builtin_estimator_fallback(self):
        m = causal()
        with patch.object(m, "_load_engine", side_effect=ImportError("optional library absent")):
            result = m.analyze_causal_study(bound_plan(), dataset())
        self.assertIn("DEPENDENCY_UNAVAILABLE", result.reasons)
        self.assertIsNone(result.estimate)
        self.assertIsNone(result.confidence_interval)
        self.assertEqual(result.action, "NO_ACTION")
        self.assertEqual(result.proof_level, "P0")

    def test_unknown_costs_and_harms_are_not_zero_or_clear(self):
        m = causal()
        plan, data = bound_plan(), dataset(count=20)
        for declared in (None, m.CausalSafety(0, "JPY", None, 0, "events", "count", None)):
            result = m.analyze_causal_study(plan, data, safety=declared)
            self.assertEqual(result.harms_status, "UNKNOWN_HARMS")
            self.assertEqual(result.cost_status, "UNKNOWN_COSTS")
            self.assertIsNone(result.net_benefit)
            self.assertEqual(result.human_welfare_status, "NOT_MEASURED")

    def test_late_protocol_and_early_outcome_publication_do_not_claim_prospective_evidence(self):
        m = causal()
        plan, data = bound_plan(), dataset()
        plan = replace(plan, protocol=replace(plan.protocol, retrieved_at=START + timedelta(days=1)))
        self.assertIn("PROTOCOL_NOT_PROSPECTIVE", m.analyze_causal_study(plan, data).reasons)
        data = replace(data, source=replace(data.source, retrieved_at=START))
        self.assertIn("OUTCOME_SOURCE_PRECEDES_END", m.analyze_causal_study(bound_plan(), data).reasons)


@unittest.skipUnless(importlib.util.find_spec("dowhy"), "optional pinned DoWhy dependencies required")
class RealDoWhyTests(unittest.TestCase):
    def test_library_estimate_ci_placebo_and_confounding_diagnostics_in_both_domains(self):
        m = causal()
        for domain, metric, unit in (("financial", "outside_income", "JPY_minor/aggregate"),
                                     ("physical", "PM2.5", "ug/m3")):
            plan = bound_plan(domain=domain, metric=metric, unit=unit)
            result = m.analyze_causal_study(plan, dataset(plan), safety=safety())
            self.assertEqual(result.status, "SYNTHETIC_DIAGNOSTICS_ONLY", result.reasons)
            self.assertAlmostEqual(result.estimate, 2, delta=.25)
            self.assertLess(result.confidence_interval[0], result.estimate)
            self.assertGreater(result.confidence_interval[1], result.estimate)
            self.assertEqual(result.unit, unit)
            self.assertEqual(result.engine_version, "0.14")
            self.assertEqual(result.overlap_status, "DECLARED_SUPPORT_ONLY")
            self.assertLess(abs(result.placebo_effect), .5)
            self.assertTrue(0 <= result.robustness_value <= 1)
            self.assertIsNone(result.verified_causal_effect)
            self.assertEqual(result.proof_level, "P0")

    def test_self_supplied_public_aggregate_can_compute_but_cannot_certify_welfare(self):
        m = causal()
        plan = bound_plan()
        result = m.analyze_causal_study(plan, dataset(plan, kind="declared_public_aggregate"), safety=safety())
        self.assertIsNotNone(result.estimate)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertIn("UNAUTHENTICATED_INPUTS", result.reasons)
        self.assertEqual(result.measurement_authentication, "NOT_VERIFIED")
        self.assertEqual(result.human_welfare_status, "NOT_MEASURED")
        self.assertEqual(result.harms_status, "DECLARED_ONLY")
        self.assertEqual(result.action, "NO_ACTION")

    def test_failed_sensitivity_and_placebo_thresholds_are_inconclusive(self):
        m = causal()
        plan = bound_plan(placebo_tolerance=0, minimum_robustness=.9999)
        result = m.analyze_causal_study(plan, dataset(plan), safety=safety())
        self.assertIsNotNone(result.estimate)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertIn("PLACEBO_DIAGNOSTIC_FAILED", result.reasons)
        self.assertIn("CONFOUNDING_SENSITIVITY", result.reasons)

    def test_interval_containing_null_does_not_become_positive_effect(self):
        m = causal()
        plan = bound_plan(minimum_robustness=0)
        result = m.analyze_causal_study(plan, dataset(plan, effect=0), safety=safety())
        self.assertLess(result.confidence_interval[0], 0)
        self.assertGreater(result.confidence_interval[1], 0)
        self.assertIn("INTERVAL_CONTAINS_NULL", result.reasons)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertIsNone(result.verified_causal_effect)

    def test_numerical_sensitivity_warnings_are_preserved_and_inconclusive(self):
        m = causal()
        plan = bound_plan()
        data = dataset(plan)
        data = bind_data(replace(data, observations=tuple(replace(row, outcome=row.outcome + 100000 * row.baseline)
                                                         for row in data.observations)))
        result = m.analyze_causal_study(plan, data, safety=safety())
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertIn("NUMERICAL_DIAGNOSTIC_WARNING", result.reasons)
        self.assertTrue(result.engine_warnings)
        self.assertIsNone(result.verified_causal_effect)


if __name__ == "__main__":
    unittest.main()
