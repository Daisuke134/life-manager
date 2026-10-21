"""Offline experiment contract tests. Doubles below are not an allocator.

The pinned GrowthBook/SciPy exercise lives in phase06_experiment_contract.py.
The default suite requires only the standard library and tests refusal paths.
"""
import importlib
import importlib.util
import subprocess
import sys
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch


NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def module():
    assert importlib.util.find_spec("manager_core.digital_experiment") is not None, "digital experiment implementation missing"
    return importlib.import_module("manager_core.digital_experiment")


def uid(index):
    return f"synthetic-unit-{index:06d}"


def fixed_sdk_response(config, identifier):
    # Explicit fixture groups for gate tests, not a randomization algorithm.
    fixtures = {uid(i): 0 for i in range(10)}
    fixtures.update({uid(i): 1 for i in range(10, 20)})
    index = fixtures[identifier]
    return index, config.variations[index]


class DigitalExperimentTests(unittest.TestCase):
    def setUp(self):
        self.m = module()
        self.config = self.m.config_for("finance")
        self.sdk = patch.object(self.m, "_assign_with_sdk", side_effect=fixed_sdk_response).start()
        self.stats = patch.object(self.m, "_chisquare_with_scipy", return_value=(0.0, 1.0)).start()
        self.addCleanup(patch.stopall)

    def consent(self, identifier, config=None, **changes):
        config = config or self.config
        value = self.m.OptInClaim(identifier, self.m.config_hash(config), NOW - timedelta(minutes=5), NOW + timedelta(hours=1))
        return replace(value, **changes)

    def record(self, i, config=None):
        config = config or self.config
        result = self.m.prepare_assignment(config, self.m.SyntheticUnit(uid(i)), self.consent(uid(i), config), NOW)
        self.assertEqual(result.status, "SYNTHETIC_ASSIGNMENT_PREPARED")
        return result.assignment

    def snapshot(self, config=None):
        config = config or self.config
        return self.m.AssignmentSnapshot(self.m.config_hash(config), NOW, tuple(self.record(i, config) for i in range(20)))

    def decide(self, *, config=None, unit=None, consent=None, snapshot=None, now=NOW):
        config = config or self.config
        unit = unit or self.m.SyntheticUnit(uid(10))
        return self.m.evaluate_candidate(config, unit, consent if consent is not None else self.consent(unit.unit_id, config), snapshot, now)

    def assert_no_live_effect(self, result):
        self.assertFalse(result.live_action_allowed)
        self.assertFalse(result.experiment_enabled)
        self.assertFalse(result.action_executed)
        self.assertEqual(result.external_authority, "NOT_ESTABLISHED")
        self.assertEqual(result.human_outcome, "NOT_MEASURED")
        self.assertEqual(result.causal_lift_status, "NOT_ESTIMATED")

    def test_config_hash_is_stable_and_separates_the_three_existing_routes(self):
        hashes = set()
        for domain in ("finance", "mental", "physical"):
            config = self.m.config_for(domain)
            self.assertEqual(config.treatment_route, f"/manager-support/{domain}.html")
            self.assertEqual(config.control_route, "/manager-support/control.html")
            self.assertEqual(config.variations[0], "NO_ACTION")
            self.assertEqual(config.seed, f"manager-support-{domain}-synthetic-v1")
            self.assertEqual(config.hash_attribute, "id")
            self.assertEqual(config.unit_type, "SYNTHETIC_UNIT")
            self.assertEqual(config.hash_version, 2)
            self.assertEqual(self.m.config_hash(config), self.m.config_hash(replace(config)))
            hashes.add(self.m.config_hash(config))
        self.assertEqual(len(hashes), 3)

    def test_configuration_drift_or_new_route_cannot_reach_sdk(self):
        for change in ({"seed": "different"}, {"weights": (.9, .1)}, {"coverage": True},
                       {"hash_attribute": "email"}, {"hash_version": 1},
                       {"treatment_route": "https://example.org/"}, {"control_route": "/"},
                       {"variations": ("TREATMENT", "NO_ACTION")}, {"srm_alpha": .05},
                       {"sdk_version": "unversioned"}, {"data_class": "REAL_PARTICIPANT"}):
            with self.subTest(change=change):
                result = self.decide(config=replace(self.config, **change), consent=self.consent(uid(10)))
                self.assertEqual((result.decision, result.reason), ("NO_ACTION", "INVALID_CONFIGURATION"))
        self.sdk.assert_not_called()

    def test_missing_or_wrong_configuration_is_no_action(self):
        for config in (None, {}, "finance"):
            result = self.m.evaluate_candidate(config, self.m.SyntheticUnit(uid(10)), self.consent(uid(10)), None, NOW)
            self.assertEqual(result.reason, "INVALID_CONFIGURATION")
            self.assert_no_live_effect(result)

    def test_real_participant_is_blocked_even_with_a_matching_self_asserted_consent(self):
        unit = self.m.SyntheticUnit(uid(10), data_class="REAL_PARTICIPANT")
        result = self.decide(unit=unit, consent=self.consent(uid(10), data_class="REAL_PARTICIPANT"))
        self.assertEqual((result.decision, result.reason), ("NO_ACTION", "REAL_PARTICIPANT_BLOCKED"))
        self.sdk.assert_not_called()
        self.assert_no_live_effect(result)

    def test_missing_private_looking_and_nonstring_ids_are_rejected_before_sdk(self):
        for identifier in (None, "", " ", "person@example.org", "synthetic-unit-1", 123, True):
            result = self.decide(unit=self.m.SyntheticUnit(identifier), consent=self.consent(uid(10)))
            self.assertEqual(result.reason, "INVALID_UNIT_ID")
        self.sdk.assert_not_called()

    def test_missing_or_untyped_consent_does_not_create_assignment(self):
        for consent in (None, {}, {"granted": True}, True):
            result = self.m.prepare_assignment(self.config, self.m.SyntheticUnit(uid(10)), consent, NOW)
            self.assertEqual(result.status, "MISSING_OR_INVALID_CONSENT")
            self.assertIsNone(result.assignment)
        self.sdk.assert_not_called()

    def test_consent_is_bound_to_unit_configuration_purpose_and_synthetic_scope(self):
        for change in ({"unit_id": uid(11)}, {"config_sha256": "a" * 64},
                       {"purpose": "ANY_USE"}, {"data_class": "REAL_PARTICIPANT"}):
            result = self.decide(consent=self.consent(uid(10), **change))
            self.assertEqual(result.reason, "CONSENT_BINDING_MISMATCH")
        self.sdk.assert_not_called()

    def test_revoked_refused_and_unknown_consent_are_no_action(self):
        for status in ("REVOKED", "REFUSED", "UNKNOWN", True):
            result = self.decide(consent=self.consent(uid(10), status=status))
            self.assertEqual(result.decision, "NO_ACTION")
            self.assertIsNone(result.assignment)
        self.sdk.assert_not_called()

    def test_expiry_is_exclusive_and_future_consent_cannot_be_used(self):
        result = self.decide(consent=self.consent(uid(10), expires_at=NOW))
        self.assertEqual(result.reason, "CONSENT_EXPIRED")
        result = self.decide(consent=self.consent(uid(10), issued_at=NOW + timedelta(seconds=1)))
        self.assertEqual(result.reason, "CONSENT_NOT_YET_VALID")
        self.sdk.assert_not_called()

    def test_naive_or_invalid_clocks_fail_closed(self):
        for now in (NOW.replace(tzinfo=None), None, "2026-10-22"):
            result = self.decide(now=now)
            self.assertEqual(result.reason, "INVALID_CLOCK")
        result = self.decide(consent=self.consent(uid(10), issued_at=NOW.replace(tzinfo=None)))
        self.assertEqual(result.reason, "MISSING_OR_INVALID_CONSENT")
        self.sdk.assert_not_called()

    def test_assignment_preparation_is_inert_and_bound_to_config(self):
        result = self.m.prepare_assignment(self.config, self.m.SyntheticUnit(uid(10)), self.consent(uid(10)), NOW)
        self.assertEqual(result.decision, "NO_ACTION")
        self.assertFalse(result.action_executed)
        self.assertEqual(result.assignment.config_sha256, self.m.config_hash(self.config))
        self.assertEqual(result.assignment.variation, "OFFICIAL_RESOURCE_DIRECTORY")
        self.assertEqual(result.assignment.data_class, "SYNTHETIC_ONLY")
        self.assertEqual(self.sdk.call_count, 2)

    def test_previous_assignment_is_reused_and_drift_is_rejected(self):
        previous = self.record(10)
        result = self.m.prepare_assignment(self.config, self.m.SyntheticUnit(uid(10)), self.consent(uid(10)), NOW, previous=previous)
        self.assertEqual(result.status, "SYNTHETIC_ASSIGNMENT_REUSED")
        self.assertIs(result.assignment, previous)
        for old in (replace(previous, unit_id=uid(11)), replace(previous, config_sha256="b" * 64),
                    replace(previous, variation_id=0, variation="NO_ACTION")):
            result = self.m.prepare_assignment(self.config, self.m.SyntheticUnit(uid(10)), self.consent(uid(10)), NOW, previous=old)
            self.assertEqual(result.status, "ASSIGNMENT_DRIFT")
            self.assertIsNone(result.assignment)

    def test_missing_sdk_has_no_fallback_allocator(self):
        self.sdk.side_effect = self.m.OptionalDependencyUnavailable("growthbook")
        result = self.decide()
        self.assertEqual((result.decision, result.reason), ("NO_ACTION", "SDK_UNAVAILABLE"))

    def test_nonrepeatable_sdk_assignment_is_no_action(self):
        self.sdk.side_effect = [(0, "NO_ACTION"), (1, "OFFICIAL_RESOURCE_DIRECTORY")]
        result = self.decide()
        self.assertEqual(result.reason, "ASSIGNMENT_DRIFT")

    def test_invalid_sdk_variation_cannot_produce_a_candidate(self):
        for value in ((True, "OFFICIAL_RESOURCE_DIRECTORY"), (2, "arbitrary"), (0, "OFFICIAL_RESOURCE_DIRECTORY"), None):
            self.sdk.side_effect = None
            self.sdk.return_value = value
            result = self.decide()
            self.assertEqual(result.decision, "NO_ACTION")
            self.assertIsNone(result.candidate_route)

    def test_missing_assignment_health_is_no_action(self):
        for snapshot in (None, {}, {"status": "HEALTHY"}):
            result = self.decide(snapshot=snapshot)
            self.assertEqual((result.decision, result.reason), ("NO_ACTION", "HEALTH_UNAVAILABLE"))
        self.stats.assert_not_called()

    def test_duplicate_units_are_rejected_instead_of_counted_or_silently_deduplicated(self):
        snapshot = self.snapshot()
        for extra in (snapshot.assignments[0], replace(snapshot.assignments[0], variation_id=1, variation="OFFICIAL_RESOURCE_DIRECTORY")):
            health = self.m.assignment_health(self.config, replace(snapshot, assignments=snapshot.assignments + (extra,)), NOW)
            self.assertEqual(health.reason, "DUPLICATE_UNIT")
            self.assertIsNone(health.p_value)
        self.stats.assert_not_called()

    def test_ledger_assignment_drift_is_detected_by_sdk_replay(self):
        snapshot = self.snapshot()
        altered = replace(snapshot.assignments[0], variation_id=1, variation="OFFICIAL_RESOURCE_DIRECTORY")
        result = self.decide(snapshot=replace(snapshot, assignments=(altered,) + snapshot.assignments[1:]))
        self.assertEqual(result.reason, "ASSIGNMENT_DRIFT")
        self.stats.assert_not_called()

    def test_absent_assignment_ids_are_rejected(self):
        snapshot = self.snapshot()
        bad = replace(snapshot.assignments[0], unit_id=None)
        result = self.decide(snapshot=replace(snapshot, assignments=(bad,) + snapshot.assignments[1:]))
        self.assertEqual(result.reason, "INVALID_ASSIGNMENT_RECORD")

    def test_snapshot_age_future_time_and_assignment_time_are_checked(self):
        snapshot = self.snapshot()
        stale = replace(snapshot, observed_at=NOW - timedelta(seconds=self.config.health_ttl_seconds + 1))
        self.assertEqual(self.decide(snapshot=stale).reason, "HEALTH_STALE")
        future = replace(snapshot, observed_at=NOW + timedelta(seconds=1))
        self.assertEqual(self.decide(snapshot=future).reason, "HEALTH_UNAVAILABLE")
        future_record = replace(snapshot.assignments[0], assigned_at=NOW + timedelta(seconds=1))
        self.assertEqual(self.decide(snapshot=replace(snapshot, assignments=(future_record,) + snapshot.assignments[1:])).reason,
                         "INVALID_ASSIGNMENT_RECORD")

    def test_snapshot_config_drift_and_mutable_row_container_are_rejected(self):
        snapshot = self.snapshot()
        self.assertEqual(self.decide(snapshot=replace(snapshot, config_sha256="a" * 64)).reason, "CONFIGURATION_DRIFT")
        self.assertEqual(self.decide(snapshot=replace(snapshot, assignments=list(snapshot.assignments))).reason, "HEALTH_UNAVAILABLE")

    def test_target_unit_must_exist_in_the_unique_assignment_snapshot(self):
        snapshot = self.snapshot()
        snapshot = replace(snapshot, assignments=tuple(r for r in snapshot.assignments if r.unit_id != uid(10)))
        result = self.decide(snapshot=snapshot)
        self.assertEqual((result.decision, result.reason), ("NO_ACTION", "ASSIGNMENT_MISSING"))

    def test_insufficient_observed_expected_or_total_counts_are_unavailable(self):
        snapshot = self.snapshot()
        for records in ((), snapshot.assignments[:5], snapshot.assignments[:6] + snapshot.assignments[10:16], snapshot.assignments[:10] + snapshot.assignments[10:14]):
            health = self.m.assignment_health(self.config, replace(snapshot, assignments=records), NOW)
            self.assertEqual(health.status, "UNAVAILABLE")
            self.assertEqual(health.reason, "INSUFFICIENT_COUNTS")
            self.assertIsNone(health.p_value)
        self.stats.assert_not_called()

    def test_srm_threshold_is_strictly_less_than_point_zero_zero_one(self):
        snapshot = self.snapshot()
        self.stats.return_value = (12.0, .000999)
        result = self.decide(snapshot=snapshot)
        self.assertEqual((result.decision, result.reason), ("NO_ACTION", "SAMPLE_RATIO_MISMATCH"))
        self.stats.return_value = (10.0, .001)
        result = self.decide(snapshot=snapshot)
        self.assertEqual(result.decision, "SYNTHETIC_CANDIDATE")
        self.assertEqual(result.health.status, "HEALTHY")

    def test_unavailable_or_nonfinite_health_engine_fails_closed(self):
        snapshot = self.snapshot()
        self.stats.side_effect = self.m.OptionalDependencyUnavailable("scipy")
        self.assertEqual(self.decide(snapshot=snapshot).reason, "HEALTH_UNAVAILABLE")
        self.stats.side_effect = None
        for statistic, p in ((float("nan"), .5), (1., float("inf")), (-1., .5), (1., -0.1), (1., 1.1)):
            self.stats.return_value = statistic, p
            self.assertEqual(self.decide(snapshot=snapshot).reason, "HEALTH_UNAVAILABLE")

    def test_sdk_failure_during_health_replay_is_unavailable(self):
        snapshot = self.snapshot()
        self.sdk.side_effect = self.m.OptionalDependencyUnavailable("growthbook")
        health = self.m.assignment_health(self.config, snapshot, NOW)
        self.assertEqual((health.status, health.reason), ("UNAVAILABLE", "HEALTH_UNAVAILABLE"))
        self.stats.assert_not_called()

    def test_healthy_treatment_is_only_an_offline_candidate_on_existing_route(self):
        for domain in ("finance", "mental", "physical"):
            config = self.m.config_for(domain)
            snapshot = self.snapshot(config)
            result = self.decide(config=config, snapshot=snapshot)
            self.assertEqual(result.decision, "SYNTHETIC_CANDIDATE")
            self.assertEqual(result.candidate_route, f"/manager-support/{domain}.html")
            self.assertEqual(result.health.counts, (10, 10))
            self.assertEqual(result.health.total_units, 20)
            self.assert_no_live_effect(result)

    def test_control_preserves_no_action_even_with_healthy_assignment(self):
        result = self.decide(unit=self.m.SyntheticUnit(uid(0)), snapshot=self.snapshot())
        self.assertEqual((result.decision, result.reason), ("NO_ACTION", "CONTROL_HOLDOUT"))
        self.assertIsNone(result.candidate_route)
        self.assertEqual(result.assignment.variation, "NO_ACTION")
        self.assert_no_live_effect(result)

    def test_health_recomputes_counts_and_does_not_mutate_inputs(self):
        snapshot = self.snapshot()
        before = asdict(snapshot)
        result = self.decide(snapshot=snapshot)
        self.assertEqual(asdict(snapshot), before)
        self.stats.assert_called_once_with((10, 10), (.5, .5))
        self.assertEqual(len(result.health.snapshot_sha256), 64)

    def test_unknown_domain_cannot_expand_the_route_allowlist(self):
        with self.assertRaises(ValueError):
            self.m.config_for("new-domain")

    def test_import_works_without_site_packages_and_does_not_load_optional_engines(self):
        code = "import manager_core.digital_experiment,sys; assert 'growthbook' not in sys.modules; assert 'scipy' not in sys.modules"
        result = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class GrowthBookAdapterTests(unittest.TestCase):
    def test_unpinned_optional_versions_are_unavailable_without_import_fallback(self):
        m = module()
        m._sdk_classes.cache_clear()
        m._scipy_chisquare.cache_clear()
        try:
            with patch.object(m, "version", return_value="999.0"):
                with self.assertRaises(m.OptionalDependencyUnavailable):
                    m._sdk_classes()
                with self.assertRaises(m.OptionalDependencyUnavailable):
                    m._scipy_chisquare()
        finally:
            m._sdk_classes.cache_clear()
            m._scipy_chisquare.cache_clear()

    def test_sdk_nonparticipation_or_wrong_hash_identity_is_rejected(self):
        m = module()
        for change in ({"inExperiment": False}, {"hashUsed": False},
                       {"hashValue": uid(11)}, {"hashAttribute": "email"},
                       {"stickyBucketUsed": True}):
            destroyed = []
            values = dict(variationId=1, value="OFFICIAL_RESOURCE_DIRECTORY", inExperiment=True,
                          hashUsed=True, hashAttribute="id", hashValue=uid(10), stickyBucketUsed=False)
            values.update(change)

            class Client:
                def __init__(self, **kwargs):
                    pass

                def run(self, experiment):
                    return SimpleNamespace(**values)

                def destroy(self):
                    destroyed.append(True)

            with patch.object(m, "_sdk_classes", return_value=(Client, lambda **kwargs: kwargs)):
                with self.assertRaises(ValueError):
                    m._assign_with_sdk(m.config_for("finance"), uid(10))
            self.assertEqual(destroyed, [True])

    def test_adapter_passes_seed_unit_version_and_explicitly_disables_network_features(self):
        m = module()
        seen = {}

        class Experiment:
            def __init__(self, **kwargs):
                seen["experiment"] = kwargs

        class Client:
            def __init__(self, **kwargs):
                seen["client"] = kwargs

            def run(self, experiment):
                return SimpleNamespace(variationId=1, value="OFFICIAL_RESOURCE_DIRECTORY", inExperiment=True,
                                       hashUsed=True, hashAttribute="id", hashValue=uid(10), stickyBucketUsed=False)

            def destroy(self):
                seen["destroyed"] = True

        with patch.object(m, "_sdk_classes", return_value=(Client, Experiment)):
            self.assertEqual(m._assign_with_sdk(m.config_for("finance"), uid(10)), (1, "OFFICIAL_RESOURCE_DIRECTORY"))
        self.assertEqual(seen["experiment"]["seed"], "manager-support-finance-synthetic-v1")
        self.assertEqual(seen["experiment"]["hashVersion"], 2)
        self.assertEqual(seen["experiment"]["weights"], [.5, .5])
        self.assertTrue(seen["experiment"]["disableStickyBucketing"])
        self.assertEqual(seen["client"]["attributes"], {"id": uid(10)})
        for key in ("remote_eval", "streaming", "defer_tracking"):
            self.assertFalse(seen["client"][key])
        for key in ("on_experiment_viewed", "on_feature_usage", "sticky_bucket_service"):
            self.assertIsNone(seen["client"][key])
        self.assertEqual(seen["client"]["client_key"], "")
        self.assertEqual(seen["client"]["api_host"], "")
        self.assertTrue(seen["destroyed"])


if __name__ == "__main__":
    unittest.main()
