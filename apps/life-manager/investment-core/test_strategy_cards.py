from __future__ import annotations

from decimal import Decimal
import json
import unittest

from strategy_cards import StrategyCard, validate_strategy_card


def _valid_card(**overrides):
    value = {
        "strategy_id": "alpaca-btc-5m-reversion-v1",
        "venue": "alpaca",
        "instruments": ["BTC/USDC"],
        "timeframe": "5m",
        "entry_rules": {
            "all": ["rsi_14 <= 30", "tema_9 < bollinger_middle_20_2"],
        },
        "exit_rules": {
            "any": [
                "rsi_14 >= 70",
                "close >= bollinger_upper_20_2",
                "loss >= 1.5 * atr_14",
                "age_bars >= 12",
            ],
        },
        "sizing_rule": {"notional_usd": Decimal("100.00")},
        "cost_model": {"entry_fee_bps": Decimal("25.00"), "slippage_bps": "5.00"},
        "risk_limits": {"max_drawdown_usd": Decimal("20.00")},
        "kill_conditions": ["stale_quote", "effect_unknown"],
        "evidence_refs": ["https://example.test/evidence/alpaca-btc-reversion"],
        "status": "research",
    }
    value.update(overrides)
    return value


class StrategyCardContractTests(unittest.TestCase):
    def test_valid_read_only_card_round_trips_and_validates(self):
        source = _valid_card()

        card = StrategyCard.from_mapping(source)

        self.assertEqual(validate_strategy_card(card), ())
        source["entry_rules"]["all"].append("must_not_leak")
        self.assertNotIn("must_not_leak", card.to_mapping()["entry_rules"]["all"])
        self.assertEqual(card.to_mapping()["cost_model"]["entry_fee_bps"], "25.00")
        self.assertEqual(card.to_mapping()["sizing_rule"]["notional_usd"], "100.00")

    def test_missing_exit_rules_is_rejected(self):
        card = StrategyCard.from_mapping(_valid_card(exit_rules={}))

        errors = validate_strategy_card(card)

        self.assertIn("exit_rules_missing", errors)

    def test_missing_cost_model_is_rejected_without_a_default(self):
        card = StrategyCard.from_mapping(_valid_card(cost_model=None))

        errors = validate_strategy_card(card)

        self.assertIn("cost_model_missing", errors)
        self.assertIsNone(card.to_mapping()["cost_model"])

    def test_empty_instruments_are_rejected(self):
        card = StrategyCard.from_mapping(_valid_card(instruments=[]))

        self.assertIn("instruments_empty", validate_strategy_card(card))

    def test_missing_evidence_urls_are_rejected(self):
        card = StrategyCard.from_mapping(_valid_card(evidence_refs=["", "not-a-url"]))

        errors = validate_strategy_card(card)

        self.assertIn("evidence_ref_invalid", errors)

    def test_unknown_status_is_rejected(self):
        card = StrategyCard.from_mapping(_valid_card(status="approved"))

        self.assertIn("status_invalid", validate_strategy_card(card))

    def test_serialization_is_stable_for_different_input_key_order(self):
        first = StrategyCard.from_mapping(_valid_card())
        second_source = dict(reversed(list(_valid_card().items())))
        second = StrategyCard.from_mapping(second_source)

        first_json = json.dumps(first.to_mapping(), sort_keys=True, separators=(",", ":"))
        second_json = json.dumps(second.to_mapping(), sort_keys=True, separators=(",", ":"))

        self.assertEqual(first_json, second_json)

    def test_nested_card_data_is_immutable(self):
        card = StrategyCard.from_mapping(_valid_card())

        with self.assertRaises(TypeError):
            card.entry_rules["new_rule"] = "forbidden"
        with self.assertRaises(AttributeError):
            card.status = "paper"


if __name__ == "__main__":
    unittest.main()
