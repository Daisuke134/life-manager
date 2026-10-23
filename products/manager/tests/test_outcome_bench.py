"""OutcomeBench preparation tests; every datum here is a fictional fixture."""
import importlib
import importlib.util
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from manager_core.models.source import Source


NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def bench():
    assert importlib.util.find_spec("manager_core.outcome_bench") is not None, "OutcomeBench implementation missing"
    return importlib.import_module("manager_core.outcome_bench")


def reference(kind, *, subject="case-1", source_id=None, metric_kind="technical"):
    m = bench()
    source_id = source_id or kind
    payload = json.dumps({"fixture": source_id, "kind": kind}).encode()
    source = Source(source_id, "https://example.org/" + source_id, "CC0-1.0",
                    "allowed_with_conditions", sha256(payload).hexdigest(), NOW,
                    "public_nonpersonal")
    return m.EvidenceReference(source, subject, kind, metric_kind), payload


def scope(**changes):
    values = dict(country="JP", income_group="aggregate-unspecified", domain="finance", period="2026-Q4")
    values.update(changes)
    return bench().PopulationScope(**values)


class OutcomeBenchTests(unittest.TestCase):
    def test_prediction_metrics_do_not_certify_real_world_effect(self):
        m = bench()
        result = m.prediction_metrics((2, 4), (1, 2), {"yes": .7, "no": .3}, {"yes": .5, "no": .5})
        self.assertEqual(result.mae, 1.5)
        self.assertAlmostEqual(result.tvd, .2)
        self.assertEqual(result.sample_count, 2)
        self.assertEqual(result.proof_level, "P0")

    def test_invalid_predictions_rejected_without_coercing_unknown_to_zero(self):
        m = bench()
        for predicted, observed in (((), ()), ((True,), (1,)), ((float("nan"),), (1,)),
                                    ((1,), (None,)), ((1,), (1, 2))):
            with self.subTest(predicted=predicted), self.assertRaises(ValueError):
                m.prediction_metrics(predicted, observed)
        with self.assertRaises(ValueError):
            m.prediction_metrics((1,), (1,), {"yes": 1}, None)

    def test_causal_error_requires_known_synthetic_reference_and_matching_unit(self):
        m = bench()
        known = m.SyntheticCausalReference("count", (0, 2), (2, 4))
        result = m.causal_error(1.5, "count", known)
        self.assertEqual(result.absolute_error, .5)
        self.assertEqual(result.status, "SYNTHETIC_REFERENCE_ONLY")
        self.assertEqual(result.proof_level, "P0")
        self.assertIsNone(m.causal_error(1.5, "count", None).absolute_error)
        ref, _ = reference("causal_analysis", metric_kind="mental")
        self.assertIsNone(m.causal_error(1.5, "count", ref).absolute_error)
        with self.assertRaises(ValueError):
            m.causal_error(1.5, "USD_minor", known)

    def test_complete_self_supplied_evidence_never_authenticates_p1_to_p4(self):
        m = bench()
        kinds = ("execution_receipt", "world_readback", "human_outcome", "causal_analysis",
                 "preregistration", "costs", "harms", "sensitivity")
        pairs = [reference(kind, metric_kind="mental" if kind == "human_outcome" else "technical") for kind in kinds]
        bundle = m.EvidenceBundle("case-1", "manager-executor", tuple(pair[0] for pair in pairs))
        result = m.assess_evidence(bundle, {ref.source.source_id: payload for ref, payload in pairs})
        self.assertEqual(set(result.levels), {"P0", "P1", "P2", "P3", "P4"})
        self.assertEqual(result.levels["P4"].status, "UNAUTHENTICATED")
        self.assertTrue(all(result.levels[level].status != "VERIFIED" for level in ("P1", "P2", "P3", "P4")))
        self.assertEqual(result.real_world_proof_level, "P0")
        self.assertEqual(result.human_welfare_status, "NOT_MEASURED")

    def test_proxy_and_executor_readback_cannot_be_clinical_outcomes(self):
        m = bench()
        proxy, _ = reference("human_outcome", metric_kind="technical")
        own_readback, _ = reference("world_readback", source_id="manager-executor")
        result = m.assess_evidence(m.EvidenceBundle("case-1", "manager-executor", (proxy, own_readback)))
        self.assertEqual(result.levels["P2"].status, "EXECUTOR_ONLY")
        self.assertEqual(result.levels["P3"].status, "PROXY_ONLY")
        self.assertEqual(result.levels["P4"].status, "INCOMPLETE")

    def test_hash_mismatch_subject_mismatch_and_duplicate_evidence_fail_closed(self):
        m = bench()
        ref, _ = reference("execution_receipt")
        with self.assertRaises(ValueError):
            m.assess_evidence(m.EvidenceBundle("case-1", "manager-executor", (ref,)), {ref.source.source_id: b"changed"})
        with self.assertRaises(ValueError):
            m.EvidenceBundle("wrong-case", "manager-executor", (ref,))
        with self.assertRaises(ValueError):
            m.EvidenceBundle("case-1", "manager-executor", (ref, ref))
        with self.assertRaises(ValueError):
            m.EvidenceReference(ref.source, "case-1", "clinical_cure", "mental")

    def test_evidence_manifest_is_replayable_and_contains_no_raw_snapshots(self):
        m = bench()
        ref, payload = reference("execution_receipt")
        bundle = m.EvidenceBundle("case-1", "manager-executor", (ref,))
        first = m.reproduction_manifest(bundle, code_version="a" * 40)
        second = m.reproduction_manifest(bundle, code_version="a" * 40)
        self.assertEqual(first, second)
        self.assertEqual(first["assessment"]["human_welfare_status"], "NOT_MEASURED")
        self.assertEqual(first["references"][0]["sha256"], sha256(payload).hexdigest())
        self.assertNotIn("fixture", json.dumps(first))
        with self.assertRaises(ValueError):
            m.reproduction_manifest(bundle, code_version="main")

    def test_holdout_leakage_and_repeated_population_are_rejected(self):
        m = bench()
        with self.assertRaises(ValueError):
            m.HoldoutEvaluation(("same",), ("same",), (scope(),), (.1,), .2, "public aggregates only", "MAE", "count")
        with self.assertRaises(ValueError):
            m.HoldoutEvaluation(("train",), ("test",), (scope(), scope()), (.1, .1), .2, "public aggregates only", "MAE", "count")

    def test_ood_in_any_dimension_or_unknown_error_stops_execution(self):
        m = bench()
        evaluation = m.HoldoutEvaluation(("train",), ("test",), (scope(),), (.1,), .2, "public aggregates only", "MAE", "count")
        self.assertEqual(m.assess_target(evaluation, scope()).action, "OFFLINE_CANDIDATE_ONLY")
        for dimension, value in (("country", "US"), ("income_group", "lower-income"),
                                 ("domain", "environment"), ("period", "2027-Q1")):
            result = m.assess_target(evaluation, scope(**{dimension: value}))
            self.assertEqual(result.action, "NO_ACTION")
            self.assertEqual(result.status, "OUT_OF_DISTRIBUTION")
        unknown = replace(evaluation, errors=(None,))
        self.assertEqual(m.assess_target(unknown, scope()).status, "ERROR_UNKNOWN")
        self.assertFalse(m.assess_target(evaluation, scope()).can_execute)
        self.assertEqual(m.assess_target(replace(evaluation, errors=(.3,)), scope()).action, "NO_ACTION")

    def test_portfolio_preserves_signed_null_unknown_without_unit_sums(self):
        m = bench()
        rows = (
            m.PortfolioEntry("positive", scope(), "income", "USD_minor/person", 10, 5, 15, 100, "USD", 0, "complaints", "count"),
            m.PortfolioEntry("negative", scope(domain="environment"), "exposure", "ug/m3", -2, -3, -1, 20, "JPY", 1, "noise", "dBA"),
            m.PortfolioEntry("unknown", scope(domain="mental"), "wellbeing", "validated-scale", None, None, None, None, "USD", None),
            m.PortfolioEntry("null", scope(), "income", "USD_minor/person", 0, 0, 0, 0, "USD", 0, "complaints", "count"),
        )
        result = m.summarize_portfolio(rows)
        self.assertEqual(result.counts, {"POSITIVE_ESTIMATE": 1, "NEGATIVE_ESTIMATE": 1, "NULL_ESTIMATE": 1, "UNKNOWN": 1})
        self.assertEqual(result.entries, rows)
        self.assertIsNone(result.cumulative_welfare)
        self.assertIsNone(result.costs_by_currency["USD"])
        self.assertEqual(result.costs_by_currency["JPY"], 20)
        self.assertEqual(result.human_welfare_status, "NOT_MEASURED")
        with self.assertRaises(ValueError):
            m.summarize_portfolio((rows[0], rows[0]))

    def test_unknown_harms_and_uncertain_interval_are_not_positive(self):
        m = bench()
        row = m.PortfolioEntry("case-1", scope(), "income", "USD_minor/person", 10, 5, 15, 0, "USD", None)
        self.assertEqual(m.summarize_portfolio((row,)).counts["UNKNOWN"], 1)
        row = replace(row, lower=-1, harms=0, harm_metric="complaints", harm_unit="count")
        self.assertEqual(m.summarize_portfolio((row,)).counts["UNKNOWN"], 1)

    def test_holdout_errors_require_explicit_metric_and_unit(self):
        m = bench()
        with self.assertRaises(ValueError):
            m.HoldoutEvaluation(("train",), ("test",), (scope(),), (.1,), .2, "public aggregates only")
        evaluated = m.HoldoutEvaluation(("train",), ("test",), (scope(),), (.1,), .2,
                                        "public aggregates only", "MAE", "count")
        decision = m.assess_target(evaluated, scope())
        self.assertEqual(getattr(decision, "error_metric", None), "MAE")
        self.assertEqual(getattr(decision, "error_unit", None), "count")

    def test_known_harms_require_their_own_metric_and_unit(self):
        m = bench()
        with self.assertRaises(ValueError):
            m.PortfolioEntry("case-1", scope(), "income", "USD_minor/person", 10, 5, 15, 0, "USD", 2)

    def test_known_negative_estimate_is_retained_even_when_harms_are_unknown(self):
        m = bench()
        row = m.PortfolioEntry("case-1", scope(), "income", "USD_minor/person", -10, -15, -5, 0, "USD", None)
        self.assertEqual(m.summarize_portfolio((row,)).counts["NEGATIVE_ESTIMATE"], 1)

    def test_three_domains_reuse_exact_fixture_contract_and_remain_p0(self):
        # Structural portability of the same allowed fixture, never field efficacy.
        bench()
        from manager_core.adapters.fixtures import OfflineFixtureAdapter, OfflineFixtureSensor
        from manager_core.audit import AuditTrail
        from manager_core.authority import AuthorityVerifier, Grant
        from manager_core.kernel import ManagerKernel
        from manager_core.models.intervention import InterventionOption, InterventionPlan
        from manager_core.models.observation import Observation
        from manager_core.models.problem import CausalHypothesis, Problem
        from manager_core.outbox import DurableOutbox

        ref, _ = reference("simulation")
        observation = Observation(ref.source, "public-count", "public-aggregate", 10, "count", NOW)
        problem = Problem("test-problem", "public-benefit", (observation,),
                          (CausalHypothesis("fictional mechanism", "fixture", (ref.source.source_id,)),), ("time trend",))
        authority = AuthorityVerifier({"fixture-owner": b"fixture-only-key-material"})
        with tempfile.TemporaryDirectory() as tmp:
            kernel = ManagerKernel(DurableOutbox(Path(tmp) / "effects.sqlite"), authority, AuditTrail(Path(tmp) / "audit.sqlite"))
            for domain in ("finance", "environment", "opportunity"):
                try:
                    adapter = OfflineFixtureAdapter(domain, "fixture_change", "public-aggregate")
                except ValueError as exc:
                    self.fail(f"common offline adapter does not yet support {domain}: {exc}")
                plan = InterventionPlan((
                    InterventionOption("none", domain, "public-aggregate", "NO_ACTION", 0, 0, None, True),
                    InterventionOption("change", domain, "public-aggregate", "fixture_change", 1, .1, (2, 3), False),
                ))
                grant = Grant("grant-" + domain, "fixture-owner", domain, "fixture_change", "public-aggregate", 5, NOW - timedelta(hours=1), NOW + timedelta(hours=1))
                result = kernel.run("run-" + domain, problem, plan, grant, authority.sign_for_fixture(grant), adapter, OfflineFixtureSensor(adapter), NOW, causal_support=True)
                self.assertEqual(result.status, "VERIFIED_FIXTURE_ONLY")
                self.assertEqual(result.proof_level, "P0")
                self.assertEqual(adapter.send_calls, 1)


if __name__ == "__main__":
    unittest.main()
