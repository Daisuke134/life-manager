from __future__ import annotations

import unittest

from campaign import BUY_SYMBOL, SELL_SYMBOL, reconcile


def _closed_campaign_snapshot(unexpected_positions: list[str]) -> dict:
    return {
        "account": {"cash": "99996.76", "equity": "99996.76"},
        "clock": {"is_open": True, "observed_at": "2026-09-29T14:18:20Z"},
        "fills": [
            {"order_id": "buy-long", "price": "1.51", "qty": "1",
             "side": "buy", "symbol": BUY_SYMBOL},
            {"order_id": "sell-short", "price": "1.22", "qty": "1",
             "side": "sell", "symbol": SELL_SYMBOL},
            {"order_id": "sell-long", "price": "1.43", "qty": "1",
             "side": "sell", "symbol": BUY_SYMBOL},
            {"order_id": "buy-short", "price": "1.17", "qty": "1",
             "side": "buy", "symbol": SELL_SYMBOL},
        ],
        "mode": "paper",
        "options": [],
        "paper": True,
        "positions": [],
        "unexpected_positions": unexpected_positions,
    }


class CampaignPositionScopeTest(unittest.TestCase):
    def test_owned_external_position_does_not_invalidate_closed_campaign(self):
        result = reconcile(
            _closed_campaign_snapshot(["QQQ"]),
            allowed_external_symbols={"QQQ"},
        )

        self.assertEqual(result["status"], "CLOSED")
        self.assertEqual(result["realized_pnl_usd"], "-3.00")

    def test_unowned_external_position_remains_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "^campaign_position_scope_invalid$"):
            reconcile(
                _closed_campaign_snapshot(["AAPL"]),
                allowed_external_symbols={"QQQ"},
            )


if __name__ == "__main__":
    unittest.main()
