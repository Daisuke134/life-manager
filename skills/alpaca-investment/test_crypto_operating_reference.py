"""Known cycle costs adjust reference cashflow without proving settled profit."""
import copy
from decimal import localcontext
from fractions import Fraction
import unittest

import crypto_performance as perf
from paper_operating_costs import summarize
from test_operating_cost_inventory import window_fixture
from test_crypto_fx_performance import value


FIELD = 'cashflow_after_observed_fees_and_scoped_operating_costs_usd'


def fixture(mode='paper'):
    payload, inventory, trip = window_fixture(mode)
    costs = summarize([trip], payload, owner_id=trip['owner_id'], mode=mode,
        observed_at=inventory['observed_at'], expected_inventory=inventory)
    cycle = {**trip, 'cycle_id':'cycle-1', 'strategy_id':'strategy-1', 'release_sha':'a'*40,
        'positive_sell_count':1, 'execution_cashflow_usdc':'0.5',
        'fx_reference':{'measurement_status':'reference_only', 'cash_conversion_proven':False,
            'cashflow_after_observed_quote_fees_usd':perf._reference_amount(Fraction('0.48'))}}
    return cycle, costs


class CryptoOperatingReferenceTests(unittest.TestCase):
    def test_exact_paid_cost_is_deducted_once_and_remains_reference_only(self):
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode):
                cycle, costs = fixture(mode)
                self.assertEqual(costs['model_cost_usd'], '1')
                original = copy.deepcopy(costs)
                with localcontext() as context:
                    context.prec = 2
                    for signal in context.traps: context.traps[signal] = True
                    perf._operating_references([cycle], costs)
                    perf._operating_references([cycle], costs)
                ref = cycle['fx_reference']
                self.assertEqual(value(ref[FIELD]), Fraction('-0.52'))
                self.assertEqual(ref['scoped_model_cost_usd'], '1')
                self.assertEqual(ref['scoped_system_cost_usd'], '0')
                self.assertFalse(ref['cash_conversion_proven'])
                self.assertEqual(ref['measurement_status'], 'reference_only')
                self.assertEqual(costs, original)

    def test_missing_fx_quote_fee_or_scoped_coverage_never_becomes_zero(self):
        for case in ('fx_or_fee', 'coverage', 'different_scope'):
            with self.subTest(case=case):
                cycle, costs = fixture()
                if case == 'fx_or_fee':
                    cycle['fx_reference']['cashflow_after_observed_quote_fees_usd'] = None
                elif case == 'coverage':
                    costs['operating_cost_scope_coverages'][0]['coverage_state'] = 'gap'
                else:
                    cycle['order_ids'] = ['other-entry', 'other-exit']
                perf._operating_references([cycle], costs)
                self.assertIsNone(cycle['fx_reference'][FIELD])
                self.assertIsNone(perf._summary([cycle])[FIELD])

    def test_strategy_and_day_selection_aggregate_only_their_own_cycles(self):
        first, costs = fixture()
        second = copy.deepcopy(first)
        second.update(cycle_id='cycle-2', strategy_id='strategy-2')
        perf._operating_references([first], costs)
        second['fx_reference'][FIELD] = perf._reference_amount(Fraction('0.25'))
        both = perf._summary([first, second])
        self.assertEqual(value(both[FIELD]), Fraction('-0.27'))
        self.assertEqual([value(r[FIELD]) for r in both['strategy_reports']],
            [Fraction('-0.52'), Fraction('0.25')])
        self.assertEqual(value(perf._summary([second])[FIELD]), Fraction('0.25'))
        self.assertIsNone(perf._summary([])[FIELD])
        second['fx_reference'][FIELD] = None
        self.assertIsNone(perf._summary([first, second])[FIELD])


if __name__ == '__main__': unittest.main()
