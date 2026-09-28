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


class CapitalLadderAppTest(unittest.TestCase):
    def test_negative_and_one_round_trip_evidence_rejects_expansion(self):
        result = recommend_next_cap(
            evidence(net_pnl_usd="-0.04", completed_round_trips=1),
            current_cap="100",
            requested_cap="1000",
        )
        self.assertEqual(result["status"], "reject")
        self.assertIn("net_non_positive", result["reasons"])
        self.assertIn("sample_insufficient", result["reasons"])

    def test_positive_live_sample_recommends_only_the_next_discrete_cap(self):
        result = recommend_next_cap(evidence(), current_cap="100", requested_cap="1000")
        self.assertEqual(result["status"], "recommend")
        self.assertEqual(result["next_cap_usd"], "1000.00")
        self.assertFalse(result["capital_expansion_allowed"])

    def test_report_fields_cannot_authorize_from_a_message(self):
        report = promotion_report_fields(
            recommend_next_cap(evidence(), current_cap="100", requested_cap="1000")
        )
        self.assertTrue(report["owner_authorization_required"])
        self.assertFalse(report["message_can_authorize"])
        self.assertEqual(report["promotion_evidence_ids"], ["fill-1", "fill-2"])


if __name__ == "__main__":
    unittest.main()
