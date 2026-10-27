"""D014: synthetic, offline family-composition counterexamples; no human rows."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager_core.public_aggregate_cross_release import preflight_cross_release
from manager_core.public_aggregate_preflight import preflight_public_aggregate
from manager_core.public_aggregate_release_family import preflight_release_family


def packet(suffix):
    return {
        "schema": "manager.public-aggregate-preflight.v1",
        "route": "existing_public",
        "release_state": "published",
        "granularity": "public_aggregate",
        "source": {
            "source_id": "fictional_family_" + suffix,
            "url": "https://www.ons.gov.uk/fictional-family-" + suffix,
            "license_id": "OGL-3.0-REVIEW_REQUIRED",
            "rights": "allowed_with_conditions",
            "content_sha256": suffix * 64,
            "retrieved_at": "2026-10-25T00:00:00+00:00",
            "privacy_class": "public_nonpersonal",
        },
        "population": {
            "description": "Fictional same cohort, no real records",
            "window": "fictional unchanged period",
            "unit": "fictional events",
            "geography": "regional",
        },
        "outcome": {
            "construct": "fictional outcomes",
            "unit": "events",
            "relation": "context_only",
        },
        "partition": {
            "total": 100,
            "cells": [
                {"category": "alpha", "count": 60, "sensitive": False},
                {"category": "beta", "count": 40, "sensitive": False},
            ],
        },
        "cross_release_review": "externally_documented",
    }


def cells(values):
    return [
        {"category": name, "count": value, "sensitive": True}
        for name, value in values.items()
    ]


class ReleaseFamilyTest(unittest.TestCase):
    def family(self):
        return [packet("a"), packet("b"), packet("c")]

    def test_three_way_reconstructs_last_hidden_cell_not_visible_from_any_pair(self):
        a, b, c = self.family()
        # Underlying synthetic totals: alpha15 + beta15 + gamma20 + delta10 + epsilon40.
        # All three releases separately hide at least three cells. Every pair
        # still hides two; the full family leaves just alpha unreported.
        a["partition"]["cells"] = cells({
            "alpha": None, "beta": None, "gamma": None, "delta": 10, "epsilon": 40})
        b["partition"]["cells"] = cells({
            "alpha": None, "beta": None, "gamma": 20, "delta": None, "epsilon": 40})
        c["partition"]["cells"] = cells({
            "alpha": None, "beta": 15, "gamma": None, "delta": None, "epsilon": 40})
        for release in (a, b, c):
            self.assertEqual(preflight_public_aggregate(release)["status"], "REVIEW_REQUIRED")
        for first, second in ((a, b), (a, c), (b, c)):
            self.assertNotIn(
                "CROSS_RELEASE_SINGLE_HIDDEN_CELL",
                preflight_cross_release(first, second)["reason_codes"])
        result = preflight_release_family([a, b, c])
        self.assertEqual(result["status"], "REJECT")
        self.assertIn("FAMILY_SINGLE_HIDDEN_CELL", result["reason_codes"])
        self.assertIn("FAMILY_SUPPRESSION_UNDONE", result["reason_codes"])

    def test_multiple_unreported_cells_remain_unknown_even_across_three_releases(self):
        releases = self.family()
        for release in releases:
            release["partition"]["cells"] = cells({
                "alpha": 40, "beta": 30, "gamma": None, "delta": None})
        result = preflight_release_family(tuple(releases))
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertNotIn("FAMILY_SINGLE_HIDDEN_CELL", result["reason_codes"])
        self.assertFalse(result["disclosure_certified"])

    def test_inconsistent_declared_scope_disables_joint_arithmetic(self):
        releases = self.family()
        releases[2]["population"]["window"] = "a different fictional cohort"
        result = preflight_release_family(releases)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn("FAMILY_SCOPE_NOT_COMPARABLE", result["reason_codes"])
        self.assertNotIn("FAMILY_SINGLE_HIDDEN_CELL", result["reason_codes"])

    def test_different_categories_disables_arithmetic(self):
        releases = self.family()
        releases[2]["partition"]["cells"][1]["category"] = "other"
        result = preflight_release_family(releases)
        self.assertIn("FAMILY_CATEGORIES_NOT_COMPARABLE", result["reason_codes"])
        self.assertNotIn("FAMILY_SINGLE_HIDDEN_CELL", result["reason_codes"])

    def test_different_total_disables_arithmetic(self):
        releases = self.family()
        releases[2]["partition"]["total"] = 110
        releases[2]["partition"]["cells"][1]["count"] = 50
        result = preflight_release_family(releases)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn("FAMILY_TOTALS_NOT_COMPARABLE", result["reason_codes"])
        self.assertNotIn("FAMILY_SINGLE_HIDDEN_CELL", result["reason_codes"])

    def test_conflicting_counts_fail_to_review_not_made_up_residual(self):
        releases = self.family()
        releases[2]["partition"]["cells"][0]["count"] = 55
        releases[2]["partition"]["cells"][1]["count"] = 45
        result = preflight_release_family(releases)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn("FAMILY_COUNTS_NOT_COMPARABLE", result["reason_codes"])
        self.assertNotIn("FAMILY_SINGLE_HIDDEN_CELL", result["reason_codes"])

    def test_sensitivity_conflict_disables_arithmetic(self):
        releases = self.family()
        releases[1]["partition"]["cells"][0]["sensitive"] = True
        result = preflight_release_family(releases)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn("FAMILY_SENSITIVITY_NOT_COMPARABLE", result["reason_codes"])

    def test_source_overlap_is_not_assumed_independent(self):
        releases = self.family()
        releases[2]["source"] = copy.deepcopy(releases[1]["source"])
        result = preflight_release_family(releases)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn("FAMILY_SOURCE_OVERLAP", result["reason_codes"])
        self.assertFalse(result["cross_release_independence_verified"])

    def test_fragment_alias_in_any_pair_propagates_to_family(self):
        releases = self.family()
        releases[0]["source"]["url"] = "https://www.ons.gov.uk/family#tab-a"
        releases[2]["source"]["url"] = "https://www.ons.gov.uk/family#tab-c"
        self.assertNotEqual(releases[0]["source"]["source_id"],
                            releases[2]["source"]["source_id"])
        self.assertNotEqual(releases[0]["source"]["content_sha256"],
                            releases[2]["source"]["content_sha256"])
        result = preflight_release_family(releases)
        self.assertIn("FAMILY_SOURCE_OVERLAP", result["reason_codes"])
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertFalse(result["cross_release_independence_verified"])
        self.assertNotIn("ons.gov.uk", json.dumps(result))

    def test_rejected_member_propagates_and_cannot_authorize(self):
        releases = self.family()
        releases[1]["release_state"] = "unknown"
        result = preflight_release_family(releases)
        self.assertEqual(result["status"], "REJECT")
        self.assertIn("FAMILY_MEMBER_REJECTED", result["reason_codes"])
        self.assertIn("FAMILY_PAIR_REJECTED", result["reason_codes"])

    def test_pairwise_suppression_risk_is_propagated(self):
        releases = self.family()
        releases[0]["partition"]["cells"] = cells({
            "alpha": 60, "beta": None, "gamma": None})
        releases[1]["partition"]["cells"] = cells({
            "alpha": None, "beta": None, "gamma": 35})
        releases[2]["partition"]["cells"] = cells({
            "alpha": 60, "beta": None, "gamma": None})
        result = preflight_release_family(releases)
        self.assertEqual(result["status"], "REJECT")
        self.assertIn("FAMILY_PAIR_REJECTED", result["reason_codes"])

    def test_rejects_unbounded_family_non_aggregate_and_private_fields(self):
        with self.assertRaises(ValueError):
            preflight_release_family([packet("a"), packet("b")])
        with self.assertRaises(ValueError):
            preflight_release_family([packet("a")] * 9)
        with self.assertRaises(ValueError):
            preflight_release_family({"untrusted": "input"})
        releases = self.family()
        releases[2]["person_rows"] = [{"name": "DO_NOT_ECHO"}]
        with self.assertRaises(ValueError):
            preflight_release_family(releases)

    def test_result_contains_only_static_codes_not_counts_or_untrusted_text(self):
        releases = self.family()
        releases[0]["population"]["description"] = "FICTIONAL_DO_NOT_ECHO"
        releases[1]["population"]["description"] = "FICTIONAL_DO_NOT_ECHO"
        releases[2]["population"]["description"] = "FICTIONAL_DO_NOT_ECHO"
        result = preflight_release_family(releases)
        serialized = json.dumps(result)
        for sensitive in ("FICTIONAL_DO_NOT_ECHO", "fictional-family-", "alpha",
                          "fictional_family_a", '"total": 100'):
            self.assertNotIn(sensitive, serialized)
        for field in ("can_ingest", "can_publish", "can_execute",
                      "can_contact_participants", "source_bytes_verified",
                      "publisher_identity_verified", "rights_verified_independently",
                      "cohort_identity_verified", "cross_release_independence_verified",
                      "disclosure_certified", "consent_or_ethics_approved",
                      "causal_effect_verified"):
            self.assertFalse(result[field], field)
        self.assertEqual(result["beneficiary_effect"], "NOT_MEASURED")
        self.assertEqual(result["next_action"], "NO_ACTION")


    def _disclosive_triple(self):
        a, b, c = self.family()
        # Fictional total 100: alpha15, beta15, gamma20, delta10, epsilon40.
        # Any pair still hides two categories. Three combined hide only alpha.
        a["partition"]["cells"] = cells({
            "alpha": None, "beta": None, "gamma": None,
            "delta": 10, "epsilon": 40,
        })
        b["partition"]["cells"] = cells({
            "alpha": None, "beta": None, "gamma": 20,
            "delta": None, "epsilon": 40,
        })
        c["partition"]["cells"] = cells({
            "alpha": None, "beta": 15, "gamma": None,
            "delta": None, "epsilon": 40,
        })
        return a, b, c

    def test_unrelated_fourth_release_does_not_mask_three_way_risk(self):
        a, b, c = self._disclosive_triple()
        fourth = packet("d")
        fourth["population"]["window"] = "Unrelated fictional date range"
        for family in ([a, b, c, fourth], [fourth, c, a, b]):
            with self.subTest(order=[x["source"]["source_id"] for x in family]):
                result = preflight_release_family(family)
                self.assertEqual(result["status"], "REJECT")
                self.assertIn("FAMILY_SCOPE_NOT_COMPARABLE", result["reason_codes"])
                self.assertIn("FAMILY_SINGLE_HIDDEN_CELL", result["reason_codes"])
                self.assertIn("FAMILY_SUPPRESSION_UNDONE", result["reason_codes"])
                self.assertFalse(result["can_publish"])
                rendered = json.dumps(result)
                for forbidden in ("fictional-family", "alpha", "epsilon", "Unrelated"):
                    self.assertNotIn(forbidden, rendered)

    def test_unrelated_total_must_not_mask_three_way_reconstruction(self):
        a, b, c = self._disclosive_triple()
        fourth = packet("d")
        fourth["partition"]["total"] = 110
        # Retain the same five-category partition, varying ONLY the denominator.
        fourth["partition"]["cells"] = cells({
            "alpha": 40, "beta": 20, "gamma": 20,
            "delta": 10, "epsilon": 20,
        })
        result = preflight_release_family([a, fourth, b, c])
        self.assertIn("FAMILY_TOTALS_NOT_COMPARABLE", result["reason_codes"])
        self.assertIn("FAMILY_SINGLE_HIDDEN_CELL", result["reason_codes"])
        self.assertFalse(result["disclosure_certified"])

    def test_incompatible_counts_cannot_be_used_to_infer_hidden_cell(self):
        a, b, c = self._disclosive_triple()
        # The only potential third same-scoped source conflicts with b's
        # published gamma count; no consistent 3-way reconstruction.
        c["partition"]["cells"] = cells({
            "alpha": None, "beta": 15, "gamma": 25,
            "delta": None, "epsilon": 40,
        })
        fourth = packet("d")
        fourth["population"]["window"] = "Another fictional period"
        result = preflight_release_family([a, b, c, fourth])
        self.assertIn("FAMILY_SCOPE_NOT_COMPARABLE", result["reason_codes"])
        self.assertNotIn("FAMILY_SINGLE_HIDDEN_CELL", result["reason_codes"])
        self.assertFalse(result["can_ingest"])

    def test_only_two_comparable_releases_cannot_form_a_three_way_subset(self):
        a, b, c = self._disclosive_triple()
        c["population"]["window"] = "Other fictional cohort C"
        fourth = packet("d")
        fourth["population"]["window"] = "Other fictional cohort D"
        result = preflight_release_family([a, b, c, fourth])
        self.assertNotIn("FAMILY_SINGLE_HIDDEN_CELL", result["reason_codes"])
        self.assertEqual(result["next_action"], "NO_ACTION")



    def test_family_catches_host_case_and_default_https_port_alias(self):
        a, b, c = self.family()
        a["source"]["url"] = "https://WWW.ONS.GOV.UK/fictional-family-a#one"
        b["source"]["url"] = "https://www.ons.gov.uk:443/fictional-family-a#two"
        result = preflight_release_family([a, b, c])
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn("FAMILY_SOURCE_OVERLAP", result["reason_codes"])
        self.assertFalse(result["source_bytes_verified"])
        self.assertFalse(result["can_ingest"])
        self.assertFalse(result["can_publish"])


if __name__ == "__main__":
    unittest.main()
