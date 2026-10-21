"""D001–D003 program joins. All records below are fictional public fixtures."""
import importlib
import importlib.util
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from manager_core.economic_scorecard import COST_CATEGORIES, CostCoverage
from manager_core.models.source import Source


START = datetime(2026, 10, 1, tzinfo=timezone.utc)
END = START + timedelta(days=28)


def funding():
    assert importlib.util.find_spec("manager_core.program_funding") is not None, "typed program funding join missing"
    return importlib.import_module("manager_core.program_funding")


def source(name, at=END + timedelta(days=1)):
    return Source(name, "https://example.org/" + name, "CC0-1.0", "allowed_with_conditions",
                  sha256(name.encode()).hexdigest(), at, "public_nonpersonal")


def fixture():
    m = funding()
    window = m.FundingWindow(START, END, "USD")
    receipts = tuple(m.FundingReceipt(name, "program-a", origin, amount, refunded, "USD", "settled",
                                      START + timedelta(days=1), source(name)) for name, origin, amount, refunded in (
        ("donation-a", "outside_donor", 1000, 100),
        ("matching-a", "manager_matching", 10000, 0),
        ("sponsor-a", "sponsor", 5000, 0),
    ))
    ledger = m.FundingLedger("program-a", "group-a", window, receipts, "complete", source("funding-ledger"))
    amounts = {category: 0 for category in COST_CATEGORIES}
    amounts.update(platform=50, compute=20, refunds=100)
    costs = m.ProgramCosts("program-a", window, CostCoverage(amounts), source("program-costs"))
    primary = m.ProgramComparison("program-a", "control-a", window, 900, 500, ledger.source, source("control-a"))
    other = m.ProgramComparison("program-b", "control-b", window, 150, 350, source("program-b"), source("control-b"))
    scope = m.DisplacementScope("program-a", window, ("program-b",), "complete", source("scope", START - timedelta(days=1)))
    report = m.BeneficiaryReport("program-a", "group-a", window, "food_support", "days/household",
                                 3.5, 10, source("beneficiary-report"))
    return ledger, costs, (primary, other), scope, report


def reconcile(*, ledger=None, costs=None, comparisons=None, scope="fixture", report="fixture", snapshots=None):
    base_ledger, base_costs, base_comparisons, base_scope, base_report = fixture()
    return funding().reconcile_program_funding(
        ledger or base_ledger, costs or base_costs, base_comparisons if comparisons is None else comparisons,
        displacement_scope=base_scope if scope == "fixture" else scope,
        beneficiary_report=base_report if report == "fixture" else report, snapshots=snapshots,
    )


class ProgramFundingTests(unittest.TestCase):
    def test_manager_and_sponsor_principal_are_never_outside_donor_gains(self):
        result = reconcile()
        self.assertEqual(result.by_origin["outside_donor"].gross_minor, 1000)
        self.assertEqual(result.by_origin["outside_donor"].refunds_minor, 100)
        self.assertEqual(result.by_origin["outside_donor"].retained_minor, 900)
        self.assertEqual(result.by_origin["manager_matching"].retained_minor, 10000)
        self.assertEqual(result.by_origin["sponsor"].retained_minor, 5000)
        self.assertEqual(result.declared_external_change_minor, 400)
        self.assertEqual(result.scoped_recorded_balance_minor, 130)
        ledger, _, _, _, _ = fixture()
        larger = replace(ledger, receipts=(ledger.receipts[0], replace(ledger.receipts[1], amount_minor=800000),
                                           replace(ledger.receipts[2], amount_minor=900000)))
        self.assertEqual(reconcile(ledger=larger).scoped_recorded_balance_minor, 130)

    def test_refunds_reconcile_once_and_fees_are_separate_operating_costs(self):
        result = reconcile()
        self.assertEqual(result.recorded_refunds_minor, 100)
        self.assertEqual(result.operating_costs_minor, 70)
        self.assertEqual(result.scoped_recorded_balance_minor, 400 - 200 - 70)
        _, costs, _, _, _ = fixture()
        bad = dict(costs.coverage.amounts_minor)
        bad["refunds"] = 0
        with self.assertRaises(ValueError):
            reconcile(costs=replace(costs, coverage=CostCoverage(bad)))

    def test_pending_reversed_disputed_or_unknown_receipts_do_not_become_income(self):
        ledger, _, _, _, _ = fixture()
        for changes in ({"state": "pending"}, {"state": "reversed"}, {"state": "disputed"},
                        {"amount_minor": None}, {"refund_minor": None}, {"source": None}):
            changed = replace(ledger, receipts=(replace(ledger.receipts[0], **changes),) + ledger.receipts[1:])
            with self.subTest(changes=changes):
                result = reconcile(ledger=changed)
                self.assertIsNone(result.by_origin["outside_donor"].retained_minor)
                self.assertIsNone(result.declared_external_change_minor)
                self.assertIsNone(result.scoped_recorded_balance_minor)
                self.assertEqual(result.income_status, "NOT_VERIFIED")

    def test_unknown_coverage_or_origin_never_turns_empty_categories_into_zero(self):
        ledger, costs, _, _, _ = fixture()
        amounts = dict(costs.coverage.amounts_minor)
        amounts["refunds"] = 0
        costs = replace(costs, coverage=CostCoverage(amounts))
        unknown = replace(ledger, receipts=(), coverage="unknown")
        result = reconcile(ledger=unknown, costs=costs, comparisons=(), scope=None, report=None)
        self.assertTrue(all(total.retained_minor is None for total in result.by_origin.values()))
        known_empty = replace(unknown, coverage="complete")
        result = reconcile(ledger=known_empty, costs=costs, comparisons=(), scope=None, report=None)
        self.assertTrue(all(total.retained_minor == 0 for total in result.by_origin.values()))
        self.assertIsNone(result.scoped_recorded_balance_minor)
        unknown_origin = replace(ledger, receipts=(replace(ledger.receipts[0], origin="unknown"),) + ledger.receipts[1:])
        self.assertTrue(all(total.retained_minor is None for total in reconcile(ledger=unknown_origin).by_origin.values()))

    def test_unknown_cost_or_displacement_preserves_known_target_arithmetic(self):
        _, costs, comparisons, scope, _ = fixture()
        amounts = dict(costs.coverage.amounts_minor)
        amounts["compute"] = None
        result = reconcile(costs=replace(costs, coverage=CostCoverage(amounts)))
        self.assertEqual(result.declared_external_change_minor, 400)
        self.assertIsNone(result.operating_costs_minor)
        self.assertIsNone(result.scoped_recorded_balance_minor)
        result = reconcile(comparisons=(comparisons[0], replace(comparisons[1], control_outside_minor=None)))
        self.assertEqual(result.declared_external_change_minor, 400)
        self.assertIsNone(result.other_program_changes[0].change_minor)
        self.assertEqual(result.displacement_status, "UNKNOWN_DISPLACEMENT")
        self.assertIsNone(reconcile(scope=replace(scope, coverage="partial")).scoped_recorded_balance_minor)
        self.assertIsNone(reconcile(scope=None).scoped_recorded_balance_minor)

    def test_contemporaneous_loss_is_preserved_and_can_reverse_the_recorded_balance(self):
        _, _, comparisons, _, _ = fixture()
        other = replace(comparisons[1], observed_outside_minor=0, control_outside_minor=1000)
        result = reconcile(comparisons=(comparisons[0], other))
        self.assertEqual(result.other_program_changes[0].change_minor, -1000)
        self.assertEqual(result.scoped_recorded_balance_minor, -670)
        self.assertEqual(result.displacement_status, "DECLARED_COMPARISON_ONLY")
        self.assertIsNone(result.verified_net_benefit_minor)

    def test_wrong_windows_currencies_programs_and_reused_controls_are_rejected(self):
        m = funding()
        ledger, costs, comparisons, scope, _ = fixture()
        wrong_windows = (replace(ledger.window, start=START - timedelta(days=1), end=END - timedelta(days=1)),
                         replace(ledger.window, currency="JPY"))
        for window in wrong_windows:
            with self.subTest(window=window), self.assertRaises(ValueError):
                reconcile(comparisons=(comparisons[0], replace(comparisons[1], window=window)))
        with self.assertRaises(ValueError):
            reconcile(costs=replace(costs, program_id="unrelated"))
        with self.assertRaises(ValueError):
            reconcile(comparisons=(comparisons[0], replace(comparisons[1], control_program_id="control-a")))
        with self.assertRaises(ValueError):
            reconcile(scope=replace(scope, program_ids=("program-a", "program-b")))
        with self.assertRaises(ValueError):
            m.FundingWindow(END, START, "USD")

    def test_target_comparison_must_match_the_exact_ledger_total_and_source(self):
        _, _, comparisons, _, _ = fixture()
        for changes in ({"observed_outside_minor": 901}, {"observed_source": source("unrelated-ledger")}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                reconcile(comparisons=(replace(comparisons[0], **changes), comparisons[1]))

    def test_receipt_double_counting_wrong_binding_and_impossible_refund_fail_closed(self):
        ledger, _, _, _, _ = fixture()
        with self.assertRaises(ValueError):
            replace(ledger, receipts=ledger.receipts + (ledger.receipts[0],))
        for changes in ({"program_id": "other"}, {"currency": "EUR"}, {"occurred_at": END}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                reconcile(ledger=replace(ledger, receipts=(replace(ledger.receipts[0], **changes),) + ledger.receipts[1:]))
        for changes in ({"amount_minor": True}, {"refund_minor": 1001}, {"amount_minor": 1.5}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(ledger.receipts[0], **changes)

    def test_beneficiary_report_is_separate_and_mismatched_or_transfer_only_is_not_welfare(self):
        ledger, _, _, _, report = fixture()
        result = reconcile()
        self.assertEqual(result.beneficiary_report, report)
        self.assertEqual(result.beneficiary_report_status, "DECLARED_REPORT_NOT_VERIFIED")
        self.assertEqual(result.scoped_recorded_balance_minor, 130)
        self.assertEqual(result.human_welfare_status, "NOT_MEASURED")
        self.assertEqual(reconcile(report=None).beneficiary_report_status, "REPORT_MISSING")
        self.assertEqual(reconcile(report=replace(report, program_id="other")).beneficiary_report_status, "REPORT_BINDING_MISMATCH")
        self.assertEqual(reconcile(report=replace(report, beneficiary_group="other")).beneficiary_report_status, "REPORT_BINDING_MISMATCH")
        self.assertEqual(reconcile(report=replace(report, source=ledger.source)).beneficiary_report_status, "TRANSFER_REFERENCE_ONLY")
        self.assertEqual(reconcile(report=replace(report, denominator=None)).beneficiary_report_status, "INCOMPLETE_REPORT")

    def test_supplied_hashes_do_not_authenticate_income_or_benefit(self):
        ledger, _, _, _, _ = fixture()
        with self.assertRaises(ValueError):
            reconcile(snapshots={ledger.source.source_id: b"tampered"})
        result = reconcile(snapshots={ledger.source.source_id: ledger.source.source_id.encode()})
        self.assertEqual(result.proof_level, "P0")
        self.assertEqual(result.measurement_authentication, "NOT_VERIFIED")
        self.assertEqual(result.income_status, "NOT_VERIFIED")
        self.assertEqual(result.action, "NO_ACTION")
        self.assertIsNone(result.verified_income_minor)
        self.assertIsNone(result.verified_net_benefit_minor)
        self.assertIn(ledger.source, result.sources)

    def test_missing_sources_and_incomplete_declared_scope_are_not_zero_displacement(self):
        ledger, costs, comparisons, scope, _ = fixture()
        result = reconcile(costs=replace(costs, source=None))
        self.assertIsNone(result.operating_costs_minor)
        result = reconcile(comparisons=(comparisons[0], replace(comparisons[1], observed_source=None)))
        self.assertIsNone(result.other_program_changes[0].change_minor)
        result = reconcile(scope=replace(scope, program_ids=("program-b", "unobserved-program")))
        self.assertEqual(result.displacement_status, "UNKNOWN_DISPLACEMENT")
        self.assertIsNone(result.scoped_recorded_balance_minor)
        result = reconcile(ledger=replace(ledger, source=None), comparisons=())
        self.assertIsNone(result.by_origin["outside_donor"].retained_minor)


if __name__ == "__main__":
    unittest.main()
