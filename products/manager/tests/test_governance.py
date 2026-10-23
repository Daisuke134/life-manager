"""Governance engineering contracts; no test authorizes or executes live actions."""
import importlib
import importlib.util
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from manager_core.audit import AuditTrail
from manager_core.authority import AuthorityVerifier, Grant
from manager_core.learning import PolicyLearner
from manager_core.models.source import Source
from manager_core.outcome_bench import HoldoutEvaluation, PopulationScope, assess_target, summarize_portfolio


NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def governance():
    assert importlib.util.find_spec("manager_core.governance") is not None, "governance implementation missing"
    return importlib.import_module("manager_core.governance")


def grant():
    return Grant("grant-1", "fixture-owner", "opportunity", "fixture_change", "public-aggregate",
                 100, NOW - timedelta(hours=1), NOW + timedelta(hours=1))


def verifier():
    return AuthorityVerifier({"fixture-owner": b"fixture-only-authority-material"})


def charter():
    return governance().PublicInterestCharter("charter-1", "a" * 64, "fixture-owner", grant(),
                                              "USD_minor", "https://example.org/audit", "https://example.org/appeal",
                                              ("operator_stop", "unknown_effect", "harm", "authority_revoked", "out_of_distribution"))


def evaluation():
    return HoldoutEvaluation(("train",), ("holdout",),
                             (PopulationScope("JP", "aggregate-unspecified", "opportunity", "2026-Q4"),),
                             (.1,), .2, "public nonpersonal aggregates", "MAE", "count")


def preflight(**changes):
    m = governance()
    authority = verifier()
    values = dict(charter=charter(), proposed_grant=grant(), signature=authority.sign_for_fixture(grant()),
                  verifier=authority, cost=10, at=NOW, assessment=assess_target(evaluation(), evaluation().scopes[0]),
                  stopped=False, unresolved_effects=0)
    values.update(changes)
    return m.governance_preflight(**values)


def source():
    return Source("public-aggregate", "https://example.org/public.csv", "CC0-1.0", "allowed_with_conditions",
                  sha256(b"public aggregate").hexdigest(), NOW, "public_nonpersonal")


class GovernanceTests(unittest.TestCase):
    def test_scoped_preflight_reuses_standing_grant_without_live_permission(self):
        result = preflight()
        self.assertEqual(result.status, "OFFLINE_PREFLIGHT_PASSED")
        self.assertFalse(result.can_execute)
        self.assertEqual(result.action, "OFFLINE_CANDIDATE_ONLY")

    def test_policy_cannot_expand_budget_scope_expiry_or_issuer(self):
        for field, value in (("limit", 101), ("domain", "finance"), ("action", "pay"),
                             ("target", "another"), ("issuer", "model"),
                             ("expires_at", NOW + timedelta(days=1))):
            result = preflight(proposed_grant=replace(grant(), **{field: value}))
            self.assertEqual(result.status, "AUTHORITY_EXPANSION_BLOCKED")
            self.assertEqual(result.action, "NO_ACTION")
        self.assertEqual(preflight(signature="forged").status, "GRANT_NOT_AUTHORIZED")
        self.assertEqual(preflight(at=NOW + timedelta(hours=2)).status, "GRANT_NOT_AUTHORIZED")

    def test_stop_unknown_effect_and_unknown_coverage_each_fail_closed(self):
        self.assertEqual(preflight(stopped=True).status, "OPERATOR_STOP")
        self.assertEqual(preflight(unresolved_effects=1).status, "UNKNOWN_EFFECT")
        self.assertEqual(preflight(assessment=None).status, "EVALUATION_NOT_READY")
        outside = PopulationScope("US", "aggregate-unspecified", "opportunity", "2026-Q4")
        self.assertEqual(preflight(assessment=assess_target(evaluation(), outside)).status, "EVALUATION_NOT_READY")
        with self.assertRaises(ValueError):
            preflight(unresolved_effects=False)

    def test_charter_requires_owner_audit_appeal_and_stop_conditions(self):
        with self.assertRaises(ValueError):
            replace(charter(), owner_id="model")
        with self.assertRaises(ValueError):
            replace(charter(), appeal_url="")
        with self.assertRaises(ValueError):
            replace(charter(), stop_conditions=("operator_stop",))
        with self.assertRaises(ValueError):
            replace(charter(), version_sha256="draft")

    def test_policy_promotion_and_rollback_reuse_existing_learner(self):
        m = governance()
        with tempfile.TemporaryDirectory() as tmp:
            learner = PolicyLearner(Path(tmp) / "policy.sqlite")
            learner.initialize("baseline")
            learner.propose("candidate", .1, .2, ("train",), ("test",))
            blocked = m.promote_offline_policy(learner, "candidate", baseline_loss=.4, preflight=preflight(stopped=True), rollback_version="baseline")
            self.assertFalse(blocked.promoted)
            self.assertEqual(learner.active(), "baseline")
            promoted = m.promote_offline_policy(learner, "candidate", baseline_loss=.4, preflight=preflight(), rollback_version="baseline")
            self.assertTrue(promoted.promoted)
            self.assertFalse(promoted.can_execute)
            self.assertEqual(learner.observe_loss(.8, max_allowed_loss=.4), "baseline")
            self.assertEqual(PolicyLearner(Path(tmp) / "policy.sqlite").active(), "baseline")

    def test_promotion_requires_actual_rollback_version_and_nonregressing_shadow(self):
        m = governance()
        with tempfile.TemporaryDirectory() as tmp:
            learner = PolicyLearner(Path(tmp) / "policy.sqlite")
            learner.initialize("baseline")
            learner.propose("bad-shadow", .1, .8, ("train",), ("test",))
            result = m.promote_offline_policy(learner, "bad-shadow", baseline_loss=.4, preflight=preflight(), rollback_version="baseline")
            self.assertFalse(result.promoted)
            with self.assertRaises(ValueError):
                m.promote_offline_policy(learner, "bad-shadow", baseline_loss=.4, preflight=preflight(), rollback_version="missing")

    def test_incidents_preserve_ineffective_worsened_unknown_after_restart(self):
        m = governance()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.sqlite"
            trail = AuditTrail(path)
            run_ids = ("ineffective", "worsened", "unknown")
            for run_id, outcome in zip(run_ids, ("INEFFECTIVE", "WORSENED", "UNKNOWN")):
                report = m.IncidentReport(run_id, outcome, "fixture observation", None if outcome == "UNKNOWN" else "b" * 64, NOW)
                m.record_incident(trail, report)
            inventory = m.incident_inventory(AuditTrail(path), run_ids, population_run_ids=run_ids)
            self.assertEqual(inventory.counts, {"INEFFECTIVE": 1, "WORSENED": 1, "UNKNOWN": 1})
            self.assertTrue(inventory.chain_valid)
            self.assertIs(inventory.population_reconciled, True)
            self.assertEqual(inventory.missing_population_run_ids, ())
            self.assertEqual(inventory.unexpected_run_ids, ())
            self.assertEqual(inventory.missing_trace_run_ids, ())
            self.assertEqual(inventory.external_audit_status, "NOT_PERFORMED")
            self.assertIsNone(inventory.events["unknown"][0]["data"]["evidence_refs"])
            for trace in inventory.events.values():
                self.assertEqual(len(trace), 1)
                self.assertEqual(trace[0]["data"]["benefit_status"], "NOT_MEASURED")
                self.assertEqual(trace[0]["data"]["proof_level"], "P0")

    def test_population_omission_is_visible_without_broadening_requested_events(self):
        m = governance()
        with tempfile.TemporaryDirectory() as tmp:
            trail = AuditTrail(Path(tmp) / "audit.sqlite")
            m.record_incident(trail, m.IncidentReport("selected", "INEFFECTIVE", "fixture observation", None, NOW))
            m.record_incident(trail, m.IncidentReport("omitted", "WORSENED", "fixture observation", None, NOW))
            inventory = m.incident_inventory(trail, ("selected",), population_run_ids=("selected", "omitted"))
            self.assertIs(inventory.population_reconciled, False)
            self.assertEqual(inventory.missing_population_run_ids, ("omitted",))
            self.assertEqual(inventory.unexpected_run_ids, ())
            self.assertEqual(inventory.missing_trace_run_ids, ())
            self.assertTrue(inventory.chain_valid)
            self.assertEqual(tuple(inventory.events), ("selected",))
            self.assertEqual(inventory.counts, {"INEFFECTIVE": 1})

    def test_unexpected_requested_run_is_explicit_even_with_valid_trace(self):
        m = governance()
        with tempfile.TemporaryDirectory() as tmp:
            trail = AuditTrail(Path(tmp) / "audit.sqlite")
            trail.append("expected", "decision", {"status": "NO_ACTION"})
            m.record_incident(trail, m.IncidentReport("extra", "UNKNOWN", "fixture observation", None, NOW))
            inventory = m.incident_inventory(trail, ("extra", "expected"), population_run_ids=("expected",))
            self.assertIs(inventory.population_reconciled, False)
            self.assertEqual(inventory.unexpected_run_ids, ("extra",))
            self.assertEqual(inventory.missing_population_run_ids, ())
            self.assertTrue(inventory.chain_valid)
            self.assertEqual(inventory.counts, {"UNKNOWN": 1})

    def test_selected_population_id_without_trace_never_counts_as_coverage(self):
        m = governance()
        with tempfile.TemporaryDirectory() as tmp:
            trail = AuditTrail(Path(tmp) / "audit.sqlite")
            inventory = m.incident_inventory(trail, ("absent",), population_run_ids=("absent",))
            self.assertIs(inventory.population_reconciled, False)
            self.assertFalse(inventory.chain_valid)
            self.assertEqual(inventory.missing_trace_run_ids, ("absent",))
            self.assertEqual(inventory.missing_population_run_ids, ())
            self.assertEqual(inventory.unexpected_run_ids, ())
            self.assertEqual(inventory.events, {"absent": ()})
            self.assertEqual(inventory.counts, {})

    def test_corrupt_chain_blocks_population_reconciliation(self):
        m = governance()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.sqlite"
            trail = AuditTrail(path)
            m.record_incident(trail, m.IncidentReport("corrupt", "WORSENED", "fixture observation", None, NOW))
            with sqlite3.connect(path) as db:
                db.execute("UPDATE events SET digest = ? WHERE run_id = ?", ("0" * 64, "corrupt"))
            inventory = m.incident_inventory(AuditTrail(path), ("corrupt",), population_run_ids=("corrupt",))
            self.assertIs(inventory.population_reconciled, False)
            self.assertFalse(inventory.chain_valid)
            self.assertEqual(inventory.missing_trace_run_ids, ())
            self.assertEqual(inventory.counts, {"WORSENED": 1})

    def test_legacy_call_leaves_population_unassessed(self):
        m = governance()
        with tempfile.TemporaryDirectory() as tmp:
            trail = AuditTrail(Path(tmp) / "audit.sqlite")
            trail.append("selected", "decision", {"status": "NO_ACTION"})
            inventory = m.incident_inventory(trail, ("selected",))
            self.assertIsNone(inventory.population_reconciled)
            self.assertTrue(inventory.chain_valid)
            self.assertEqual(inventory.missing_population_run_ids, ())
            self.assertEqual(inventory.unexpected_run_ids, ())
            self.assertEqual(inventory.counts, {})
            self.assertEqual(inventory.external_audit_status, "NOT_PERFORMED")

    def test_explicit_empty_population_and_selection_are_finitely_reconciled(self):
        m = governance()
        with tempfile.TemporaryDirectory() as tmp:
            trail = AuditTrail(Path(tmp) / "audit.sqlite")
            inventory = m.incident_inventory(trail, (), population_run_ids=())
            self.assertIs(inventory.population_reconciled, True)
            self.assertEqual(inventory.events, {})
            self.assertEqual(inventory.counts, {})
            self.assertEqual(inventory.external_audit_status, "NOT_PERFORMED")
            missing = m.incident_inventory(trail, (), population_run_ids=("omitted",))
            self.assertIs(missing.population_reconciled, False)
            self.assertEqual(missing.missing_population_run_ids, ("omitted",))
            with self.assertRaises(ValueError):
                m.incident_inventory(trail, ())

    def test_population_ids_require_distinct_nonblank_immutable_texts(self):
        m = governance()
        with tempfile.TemporaryDirectory() as tmp:
            trail = AuditTrail(Path(tmp) / "audit.sqlite")
            for invalid in (("selected", "selected"), ("",), ("  ",), (None,), ["selected"]):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(ValueError):
                        m.incident_inventory(trail, ("selected",), population_run_ids=invalid)
                    with self.assertRaises(ValueError):
                        m.incident_inventory(trail, invalid, population_run_ids=("selected",))

    def test_incident_report_rejects_unknown_enum_and_unsafe_public_detail(self):
        m = governance()
        with self.assertRaises(ValueError):
            m.IncidentReport("run-1", "SUCCESS", "not an incident", "b" * 64, NOW)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                m.record_incident(AuditTrail(Path(tmp) / "audit.sqlite"),
                                  m.IncidentReport("run-1", "UNKNOWN", "bearer credential", None, NOW))

    def test_limited_coverage_does_not_extrapolate_to_other_regions_or_world(self):
        m = governance()
        local = evaluation().scopes[0]
        other = replace(local, country="US")
        result = m.coverage_inventory(evaluation(), (local, other),
                                      unmeasured_domains=("mental", "animal_welfare"),
                                      inequalities=("No low-income subgroup measurement",),
                                      failures=("Unknown follow-up",), next_questions=("Obtain lawful independent outcomes",))
        self.assertEqual(result.decisions[other].status, "OUT_OF_DISTRIBUTION")
        self.assertEqual(result.unmeasured_domains, ("mental", "animal_welfare"))
        self.assertEqual(result.failures, ("Unknown follow-up",))
        self.assertFalse(result.universal_claim_allowed)
        self.assertEqual(result.human_welfare_status, "NOT_MEASURED")

    def test_public_api_contract_discloses_sources_permissions_budget_responsibility(self):
        m = governance()
        contract = m.PublicAPIContract("api-1", "nonprofit", "https://example.org/public-api/v1",
                                       (source(),), ("https://example.org/permission",),
                                       ("opportunity", "read_public_aggregate", "public-aggregate"),
                                       100, "USD", "organization-owner")
        result = m.api_contract_manifest(contract)
        self.assertEqual(result["schema"], "manager.public-api.v1")
        self.assertEqual(result["budget_minor"], 100)
        self.assertEqual(result["responsibility_owner"], "organization-owner")
        self.assertEqual(result["permission_status"], "DECLARED_NOT_AUTHENTICATED")
        self.assertFalse(result["can_connect"])
        with self.assertRaises(ValueError):
            replace(contract, permission_refs=())
        with self.assertRaises(ValueError):
            replace(contract, budget_minor=True)

    def test_company_margin_funding_and_beneficiary_outcomes_stay_distinct(self):
        m = governance()
        model = m.OperatingCostModel("USD", 100, 200, 50, 1000, 500)
        result = m.evaluate_operating_model(model, summarize_portfolio(()))
        self.assertEqual(result.total_declared_cost_minor, 350)
        self.assertEqual(result.declared_company_margin_minor, 150)
        self.assertEqual(result.declared_cash_balance_delta_minor, 1150)
        self.assertEqual(result.human_welfare_status, "NOT_MEASURED")
        self.assertIsNone(result.cumulative_human_benefit)

    def test_unmeasured_operating_or_measurement_cost_never_becomes_zero(self):
        m = governance()
        result = m.evaluate_operating_model(m.OperatingCostModel("USD", 100, 200, None, None, 500), summarize_portfolio(()))
        self.assertIsNone(result.total_declared_cost_minor)
        self.assertIsNone(result.declared_company_margin_minor)
        self.assertIsNone(result.declared_cash_balance_delta_minor)
        self.assertEqual(result.missing_fields, ("measurement_minor", "funding_minor"))


if __name__ == "__main__":
    unittest.main()
