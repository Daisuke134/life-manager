"""Governance engineering contracts; no test authorizes or executes live actions."""
import importlib
import importlib.util
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
            for outcome in ("INEFFECTIVE", "WORSENED", "UNKNOWN"):
                report = m.IncidentReport("run-1", outcome, "fixture observation", None if outcome == "UNKNOWN" else "b" * 64, NOW)
                m.record_incident(trail, report)
            inventory = m.incident_inventory(AuditTrail(path), ("run-1",))
            self.assertEqual(inventory.counts, {"INEFFECTIVE": 1, "WORSENED": 1, "UNKNOWN": 1})
            self.assertTrue(inventory.chain_valid)
            self.assertEqual(len(inventory.events["run-1"]), 3)
            self.assertEqual(inventory.external_audit_status, "NOT_PERFORMED")
            self.assertIsNone(inventory.events["run-1"][-1]["data"]["evidence_refs"])

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
