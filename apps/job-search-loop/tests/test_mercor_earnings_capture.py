import unittest

from job_search_loop.mercor_earnings_capture import earnings_surface_ready, parse_earnings_text


class MercorEarningsCaptureTests(unittest.TestCase):
    def test_loading_shell_is_not_a_ready_earnings_surface(self):
        self.assertFalse(earnings_surface_ready(""))
        self.assertFalse(earnings_surface_ready("Earnings\nLoading..."))
        self.assertFalse(earnings_surface_ready("Payments\nPayout date\nStatus\nEarned"))
        self.assertTrue(
            earnings_surface_ready(
                "Your total earnings to date are $125.00.\nPayments\nPayout date\nStatus\nEarned"
            )
        )
        self.assertTrue(
            earnings_surface_ready(
                "Your total earnings to date are $0.00.\nNo payment history yet"
            )
        )

    def test_no_payment_history_becomes_empty_snapshot(self):
        snapshot = parse_earnings_text(
            "Your total earnings to date are $0.00.\nNo payment history yet\nOnce you receive your first payout, it will appear here",
            observed_at="2026-08-22T12:00:00+00:00",
            page_url="https://work.mercor.com/earnings",
        )
        self.assertEqual(snapshot["payment_history_status"], "empty")
        self.assertEqual(snapshot["rows"], [])
        self.assertEqual(snapshot["total_earnings_usd"], "0.00")

    def test_payment_table_without_structured_rows_is_blocked(self):
        snapshot = parse_earnings_text(
            "Your total earnings to date are $125.00.\nPayments\nPayout date\nType\nStatus\nEarned",
            observed_at="2026-08-22T12:00:00+00:00",
            page_url="https://work.mercor.com/earnings",
        )
        self.assertEqual(snapshot["status"], "blocked")
        self.assertEqual(snapshot["reason"], "payment_rows_require_structured_extraction")

    def test_login_redirect_is_classified_as_auth_readback_blocker(self):
        snapshot = parse_earnings_text(
            "Explore\nHome\nSign in\nGet Instant work offers\n$0",
            observed_at="2026-08-22T12:00:00+00:00",
            page_url="https://work.mercor.com/explore",
        )
        self.assertEqual(snapshot["status"], "blocked")
        self.assertEqual(snapshot["reason"], "earnings_surface_auth_unavailable")


if __name__ == "__main__":
    unittest.main()
