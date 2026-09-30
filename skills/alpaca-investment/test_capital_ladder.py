import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from capital_ladder import recommend_next_cap
from performance_gate import promotion_report_fields


def evidence(**changes):
    value = {
        "measurement_status": "measured",
        "measurement_mode": "live",
        "paper": False,
        "net_pnl_usd": "1.00",
        "completed_round_trips": 30,
        "drawdown_usd": "1.00",
        "drawdown_limit_usd": "20.00",
        "costs_complete": True,
        "unknown_costs": [],
        "risk_breach": False,
        "venue_health": "healthy",
        "source_receipt_ids": ["fill-1", "fill-2"],
    }
    value.update(changes)
    return value


class CapitalLadderTest(unittest.TestCase):
    def test_negative_and_one_round_trip_evidence_rejects_expansion(self):
        result = recommend_next_cap(
            evidence(net_pnl_usd="-0.04", completed_round_trips=1),
            current_cap="100",
            requested_cap="1000",
        )

        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["current_cap_usd"], "100.00")
        self.assertIn("net_non_positive", result["reasons"])
        self.assertIn("sample_insufficient", result["reasons"])
        self.assertFalse(result["capital_expansion_allowed"])

    def test_paper_evidence_rejects_expansion(self):
        result = recommend_next_cap(
            evidence(measurement_status="paper", measurement_mode="paper", paper=True),
            current_cap="100",
            requested_cap="1000",
        )

        self.assertEqual(result["status"], "reject")
        self.assertIn("paper_evidence", result["reasons"])
        self.assertFalse(result["capital_expansion_allowed"])

    def test_unknown_cost_evidence_rejects_expansion(self):
        result = recommend_next_cap(
            evidence(costs_complete=False, unknown_costs=["gas"]),
            current_cap="100",
            requested_cap="1000",
        )

        self.assertEqual(result["status"], "reject")
        self.assertIn("cost_unknown", result["reasons"])
        self.assertFalse(result["capital_expansion_allowed"])

    def test_missing_unknown_cost_vector_rejects_expansion(self):
        incomplete = evidence()
        incomplete.pop("unknown_costs")

        result = recommend_next_cap(incomplete, current_cap="100", requested_cap="1000")

        self.assertEqual(result["status"], "reject")
        self.assertIn("cost_unknown", result["reasons"])

    def test_positive_live_sample_recommends_only_the_next_discrete_cap(self):
        result = recommend_next_cap(
            evidence(),
            current_cap="100",
            requested_cap="1000",
        )

        self.assertEqual(result["status"], "recommend")
        self.assertEqual(result["current_cap_usd"], "100.00")
        self.assertEqual(result["next_cap_usd"], "1000.00")
        self.assertEqual(result["evidence_ids"], ["fill-1", "fill-2"])
        self.assertFalse(result["capital_expansion_allowed"])
        self.assertTrue(result["owner_authorization_required"])

    def test_skipping_a_discrete_cap_rejects_expansion(self):
        result = recommend_next_cap(
            evidence(),
            current_cap="100",
            requested_cap="10000",
        )

        self.assertEqual(result["status"], "reject")
        self.assertIn("next_discrete_cap_required", result["reasons"])

    def test_missing_requested_cap_rejects_expansion(self):
        result = recommend_next_cap(evidence(), current_cap="100", requested_cap=None)

        self.assertEqual(result["status"], "reject")
        self.assertIn("requested_cap_required", result["reasons"])

    def test_report_fields_are_receipt_backed_and_not_message_authority(self):
        recommendation = recommend_next_cap(
            evidence(),
            current_cap="100",
            requested_cap="1000",
        )

        report = promotion_report_fields(recommendation)

        self.assertEqual(report["capital_promotion_status"], "recommend")
        self.assertEqual(report["promotion_evidence_ids"], ["fill-1", "fill-2"])
        self.assertTrue(report["owner_authorization_required"])
        self.assertFalse(report["capital_expansion_allowed"])
        self.assertFalse(report["message_can_authorize"])
        self.assertNotIn("private_key", report)
        self.assertNotIn("secret", report)


if __name__ == "__main__":
    unittest.main()
