"""D014: metadata-only aggregate gate remains inert and fails closed."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager_core.public_aggregate_preflight import preflight_public_aggregate


class PublicAggregatePreflightTest(unittest.TestCase):
    def packet(self):
        return {
            "schema": "manager.public-aggregate-preflight.v1",
            "route": "existing_public",
            "release_state": "published",
            "granularity": "public_aggregate",
            "source": {
                "source_id": "official_aggregate",
                "url": "https://www.ons.gov.uk/peoplepopulationandcommunity",
                "license_id": "OGL-3.0-REVIEW_REQUIRED",
                "rights": "allowed_with_conditions",
                "content_sha256": "a" * 64,
                "retrieved_at": "2026-10-23T00:00:00+00:00",
                "privacy_class": "public_nonpersonal",
            },
            "population": {
                "description": "Example synthetic regional population, not real responses",
                "window": "synthetic period",
                "unit": "synthetic public records",
                "geography": "regional",
            },
            "outcome": {
                "construct": "synthetic count",
                "unit": "records",
                "relation": "context_only",
            },
            "partition": {
                "total": 100,
                "cells": [
                    {"category": "control", "count": 60, "sensitive": False},
                    {"category": "treatment", "count": 40, "sensitive": False},
                ],
            },
            "cross_release_review": "externally_documented",
        }

    def test_screen_pass_does_not_grant_authority_or_benefit(self):
        result = preflight_public_aggregate(self.packet())
        self.assertEqual(result["status"], "PRELIMINARY_METADATA_ONLY")
        for key in ("can_ingest", "can_publish", "can_execute", "can_contact_participants",
                    "disclosure_certified", "consent_or_ethics_approved", "causal_effect_verified",
                    "publisher_identity_verified", "source_bytes_verified"):
            self.assertFalse(result[key], key)
        self.assertEqual(result["beneficiary_effect"], "NOT_MEASURED")

    def test_small_sensitive_cell_rejected(self):
        p = self.packet()
        p["partition"]["cells"][0]["count"] = 7
        p["partition"]["cells"][1]["count"] = 93
        result = preflight_public_aggregate(p)
        self.assertEqual(result["status"], "REJECT")
        self.assertIn("SMALL_RELEASED_CELL", result["reason_codes"])

    def test_zero_sensitive_cell_requires_review(self):
        p = self.packet()
        p["partition"]["cells"][0].update(count=0, sensitive=True)
        p["partition"]["cells"][1]["count"] = 100
        result = preflight_public_aggregate(p)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn("SENSITIVE_ZERO_CELL_REVIEW", result["reason_codes"])

    def test_single_hidden_cell_reconstructed_even_above_10(self):
        p = self.packet()
        p["partition"]["cells"][0]["count"] = None
        result = preflight_public_aggregate(p)
        self.assertEqual(result["status"], "REJECT")
        self.assertIn("SINGLE_SUPPRESSED_CELL_RECONSTRUCTABLE", result["reason_codes"])

    def test_multiple_hidden_complement_below_minimum(self):
        p = self.packet()
        p["partition"]["cells"] = [
            {"category": "major", "count": 96, "sensitive": False},
            {"category": "small_a", "count": None, "sensitive": True},
            {"category": "small_b", "count": None, "sensitive": True},
        ]
        result = preflight_public_aggregate(p)
        self.assertEqual(result["status"], "REJECT")
        self.assertIn("SUPPRESSED_COMPLEMENT_BELOW_MINIMUM", result["reason_codes"])

    def test_multiple_hidden_nontrivial_complement_still_needs_review(self):
        p = self.packet()
        p["partition"]["cells"] = [
            {"category": "major", "count": 50, "sensitive": False},
            {"category": "hidden_a", "count": None, "sensitive": True},
            {"category": "hidden_b", "count": None, "sensitive": True},
        ]
        result = preflight_public_aggregate(p)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")

    def test_bad_partition_rejected(self):
        p = self.packet()
        p["partition"]["cells"][0]["count"] = 90
        self.assertIn("INCONSISTENT_PARTITION", preflight_public_aggregate(p)["reason_codes"])
        p["partition"]["cells"][0]["count"] = 51
        self.assertIn("INCONSISTENT_PARTITION", preflight_public_aggregate(p)["reason_codes"])

    def test_total_below_ten_not_safe(self):
        p = self.packet()
        p["partition"] = {"total": 4, "cells": [{"category": "total", "count": 4, "sensitive": True}]}
        self.assertIn("SMALL_TOTAL", preflight_public_aggregate(p)["reason_codes"])

    def test_numeric_bool_and_duplicate_categories_rejected(self):
        p = self.packet()
        p["partition"]["cells"][0]["count"] = True
        with self.assertRaises(ValueError):
            preflight_public_aggregate(p)
        p = self.packet()
        p["partition"]["cells"][1]["category"] = "control"
        with self.assertRaises(ValueError):
            preflight_public_aggregate(p)

    def test_individual_rows_and_unknown_material_are_rejected(self):
        p = self.packet()
        p["granularity"] = "individual"
        self.assertIn("NOT_AGGREGATE_ONLY", preflight_public_aggregate(p)["reason_codes"])
        p = self.packet()
        p["individual_responses"] = [{"private_note": "dont-log-me"}]
        with self.assertRaises(ValueError):
            preflight_public_aggregate(p)
        p = self.packet()
        p["partition"]["cells"][0]["person_name"] = "dont-log-me"
        with self.assertRaises(ValueError):
            preflight_public_aggregate(p)

    def test_source_boundaries_fail_closed(self):
        for field, value in (("rights", "hold"), ("privacy_class", "unknown"),
                             ("url", "http://example.com"), ("content_sha256", "invalid"),
                             ("retrieved_at", "2026-10-23")):
            with self.subTest(field=field):
                p = self.packet()
                p["source"][field] = value
                with self.assertRaises(ValueError):
                    preflight_public_aggregate(p)

    def test_unpublished_not_ingested(self):
        p = self.packet()
        p["release_state"] = "not_published"
        self.assertIn("NOT_PUBLICLY_RELEASED", preflight_public_aggregate(p)["reason_codes"])

    def test_partner_cannot_self_certify_consent(self):
        p = self.packet()
        p["route"] = "partner_public"
        p["outcome"]["relation"] = "proposed_study_outcome"
        r = preflight_public_aggregate(p)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertFalse(r["consent_or_ethics_approved"])
        self.assertFalse(r["causal_effect_verified"])
        self.assertIn("PARTNER_ETHICS_CONSENT_NOT_AUTHENTICATED", r["reason_codes"])

    def test_unreviewed_cross_release_inference_stops(self):
        p = self.packet()
        p["cross_release_review"] = "not_assessed"
        self.assertEqual(preflight_public_aggregate(p)["status"], "REVIEW_REQUIRED")

    def test_no_row_or_group_text_emitted_in_diagnostics(self):
        p = self.packet()
        p["partition"]["cells"][0]["category"] = "sensitive_group"
        text = json.dumps(preflight_public_aggregate(p))
        self.assertNotIn("sensitive_group", text)
        self.assertNotIn("official_aggregate", text)
        self.assertNotIn("www.ons.gov.uk", text)
        self.assertNotIn('"total": 100', text)


if __name__ == "__main__":
    unittest.main()
