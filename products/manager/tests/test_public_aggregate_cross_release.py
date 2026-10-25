"""D014: synthetic adversarial cross-publication arithmetic; zero real records."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager_core.public_aggregate_cross_release import preflight_cross_release
from manager_core.public_aggregate_preflight import preflight_public_aggregate


def packet(suffix):
    return {
        "schema": "manager.public-aggregate-preflight.v1",
        "route": "existing_public",
        "release_state": "published",
        "granularity": "public_aggregate",
        "source": {
            "source_id": "fictional_source_" + suffix,
            "url": "https://www.ons.gov.uk/example-" + suffix,
            "license_id": "OGL-3.0-REVIEW_REQUIRED",
            "rights": "allowed_with_conditions",
            "content_sha256": ("a" if suffix == "a" else "b") * 64,
            "retrieved_at": "2026-10-24T00:00:00+00:00",
            "privacy_class": "public_nonpersonal",
        },
        "population": {
            "description": "Completely fictional same cohort; not actual people",
            "window": "synthetic fixed interval",
            "unit": "fictional events",
            "geography": "regional",
        },
        "outcome": {
            "construct": "fictional event count",
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


def cells(**kwargs):
    # Category sensitivity is intrinsic to the fictional construct and does
    # not change when a release hides or reveals its aggregate count.
    return [
        {"category": category, "count": count, "sensitive": True}
        for category, count in kwargs.items()
    ]


class CrossReleaseTest(unittest.TestCase):
    def pair(self):
        return packet("a"), packet("b")

    def test_individually_review_only_can_reconstruct_cross_release_small_cell(self):
        a, b = self.pair()
        a["partition"]["cells"] = cells(alpha=60, beta=None, gamma=None)
        b["partition"]["cells"] = cells(alpha=None, beta=None, gamma=35)
        self.assertEqual(preflight_public_aggregate(a)["status"], "REVIEW_REQUIRED")
        self.assertEqual(preflight_public_aggregate(b)["status"], "REVIEW_REQUIRED")
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REJECT")
        self.assertIn("CROSS_RELEASE_SINGLE_HIDDEN_CELL", r["reason_codes"])
        self.assertIn("CROSS_RELEASE_SUPPRESSION_UNDONE", r["reason_codes"])

    def test_large_hidden_count_still_reconstructable(self):
        a, b = self.pair()
        a["partition"]["cells"] = cells(alpha=40, beta=None, gamma=None)
        b["partition"]["cells"] = cells(alpha=None, beta=None, gamma=30)
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REJECT")
        self.assertIn("CROSS_RELEASE_SINGLE_HIDDEN_CELL", r["reason_codes"])

    def test_two_unknown_cells_remain_underdetermined_but_not_certified(self):
        a, b = self.pair()
        a["partition"]["cells"] = cells(alpha=40, beta=None, gamma=None, delta=None)
        b["partition"]["cells"] = cells(alpha=None, beta=None, gamma=30, delta=None)
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REJECT")  # A visible cell undoes B's suppression.
        self.assertNotIn("CROSS_RELEASE_SINGLE_HIDDEN_CELL", r["reason_codes"])
        self.assertNotIn("CROSS_RELEASE_SMALL_COMPLEMENT", r["reason_codes"])
        self.assertFalse(r["disclosure_certified"])

    def test_two_unknown_cells_small_complement_flagged(self):
        a, b = self.pair()
        a["partition"]["cells"] = cells(alpha=95, beta=None, gamma=None, delta=None)
        b["partition"]["cells"] = cells(alpha=None, beta=None, gamma=0, delta=None)
        # Each member has its own warnings; none is sufficient for approval.
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REJECT")
        self.assertIn("CROSS_RELEASE_SMALL_COMPLEMENT", r["reason_codes"])

    def test_identical_fully_disclosed_members_still_require_review(self):
        a, b = self.pair()
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertEqual(r["reason_codes"], [])
        self.assertEqual(r["next_action"], "NO_ACTION")

    def test_conflicting_published_counts_do_not_create_spurious_inference(self):
        a, b = self.pair()
        b["partition"]["cells"] = cells(alpha=55, beta=45)
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertIn("CROSS_RELEASE_COUNTS_CONFLICT", r["reason_codes"])
        self.assertNotIn("CROSS_RELEASE_SINGLE_HIDDEN_CELL", r["reason_codes"])

    def test_different_population_is_not_assumed_identical(self):
        a, b = self.pair()
        b["population"]["window"] = "another synthetic interval"
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertIn("COHORT_OR_CONSTRUCT_NOT_COMPARABLE", r["reason_codes"])

    def test_conflicting_sensitivity_flags_block_arithmetic_inference(self):
        a, b = self.pair()
        a["partition"]["cells"] = cells(alpha=60, beta=None, gamma=None)
        b["partition"]["cells"] = cells(alpha=None, beta=None, gamma=35)
        # An apparently matching category was classified differently by
        # two purported releases. Their partition semantics are ambiguous.
        b["partition"]["cells"][-1]["sensitive"] = False
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertIn("CROSS_RELEASE_SENSITIVITY_NOT_COMPARABLE", r["reason_codes"])
        self.assertNotIn("CROSS_RELEASE_SINGLE_HIDDEN_CELL", r["reason_codes"])
        self.assertNotIn("CROSS_RELEASE_SUPPRESSION_UNDONE", r["reason_codes"])
        self.assertFalse(r["can_ingest"])
        self.assertFalse(r["can_publish"])
        self.assertFalse(r["can_execute"])
        self.assertFalse(r["disclosure_certified"])

    def test_consistent_category_sensitivity_still_detects_reconstruction(self):
        a, b = self.pair()
        a["partition"]["cells"] = cells(alpha=60, beta=None, gamma=None)
        b["partition"]["cells"] = cells(alpha=None, beta=None, gamma=35)
        self.assertEqual(preflight_public_aggregate(a)["status"], "REVIEW_REQUIRED")
        self.assertEqual(preflight_public_aggregate(b)["status"], "REVIEW_REQUIRED")
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REJECT")
        self.assertIn("CROSS_RELEASE_SINGLE_HIDDEN_CELL", r["reason_codes"])

    def test_different_categories_are_not_subtracted(self):
        a, b = self.pair()
        b["partition"]["cells"] = cells(alpha=60, other=40)
        r = preflight_cross_release(a, b)
        self.assertIn("CROSS_RELEASE_CATEGORIES_DIFFER", r["reason_codes"])
        self.assertNotIn("CROSS_RELEASE_SINGLE_HIDDEN_CELL", r["reason_codes"])

    def test_different_totals_not_assumed_a_stable_cohort(self):
        a, b = self.pair()
        b["partition"]["total"] = 110
        b["partition"]["cells"] = cells(alpha=60, beta=50)
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertIn("CROSS_RELEASE_TOTALS_DIFFER", r["reason_codes"])

    def test_both_release_source_reused_cannot_be_independently_authenticated(self):
        a, b = self.pair()
        b["source"] = copy.deepcopy(a["source"])
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertIn("RELEASE_SOURCE_OVERLAP", r["reason_codes"])
        self.assertFalse(r["cross_release_independence_verified"])

    def test_rejected_member_cannot_be_upgraded_by_pair(self):
        a, b = self.pair()
        b["release_state"] = "unknown"
        r = preflight_cross_release(a, b)
        self.assertEqual(r["status"], "REJECT")
        self.assertIn("MEMBER_RELEASE_REJECTED", r["reason_codes"])

    def test_invalid_source_and_unknown_person_fields_are_rejected(self):
        a, b = self.pair()
        b["source"]["rights"] = "hold"
        with self.assertRaises(ValueError):
            preflight_cross_release(a, b)
        a, b = self.pair()
        b["hidden_person_rows"] = [{"name": "DO_NOT_ECHO"}]
        with self.assertRaises(ValueError):
            preflight_cross_release(a, b)

    def test_never_outputs_sensitive_labels_counts_source_or_authority(self):
        a, b = self.pair()
        a["partition"]["cells"] = cells(alpha=60, beta=None, gamma=None)
        b["partition"]["cells"] = cells(alpha=None, beta=None, gamma=35)
        a["population"]["description"] = "fictional secret group"
        b["population"]["description"] = "fictional secret group"
        r = preflight_cross_release(a, b)
        printed = json.dumps(r)
        for secret in ("fictional secret group", "example-a", "alpha", "gamma",
                       "fictional_source_a", '"total": 100'):
            self.assertNotIn(secret, printed)
        for key in ("can_ingest", "can_publish", "can_execute",
                    "can_contact_participants", "disclosure_certified",
                    "consent_or_ethics_approved", "cohort_identity_verified",
                    "causal_effect_verified", "publisher_identity_verified"):
            self.assertFalse(r[key], key)
        self.assertEqual(r["beneficiary_effect"], "NOT_MEASURED")


if __name__ == "__main__":
    unittest.main()
