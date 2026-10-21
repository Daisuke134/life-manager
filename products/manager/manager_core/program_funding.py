"""D001–D003: declared program funding, displacement and report joins.

Pure offline accounting, not payment verification or causal/welfare estimation.
All sources and completeness statements are supplied declarations. Canonical
receipt IDs must refer to distinct transfers, not duplicate sides of a ledger.
"""
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from .economic_scorecard import CostCoverage, RECEIPT_STATES, _minor_units
from .models.source import Source, _aware, _text
from .opportunity_outcomes import _identifier
from .outcome_bench import _currency, _number
from .spillover import net_additional_resources


ORIGINS = ("outside_donor", "manager_matching", "sponsor")
COVERAGE = ("complete", "partial", "unknown")


def _source(value):
    if value is not None and type(value) is not Source:
        raise ValueError("public nonpersonal Source or explicit unknown required")


@dataclass(frozen=True)
class FundingWindow:
    start: datetime
    end: datetime
    currency: str

    def __post_init__(self):
        _aware(self.start)
        _aware(self.end)
        _currency(self.currency)
        if self.start >= self.end:
            raise ValueError("ordered accounting window required")


@dataclass(frozen=True)
class FundingReceipt:
    receipt_id: str
    program_id: str
    origin: str
    amount_minor: int | None
    refund_minor: int | None
    currency: str
    state: str
    occurred_at: datetime
    source: Source | None

    def __post_init__(self):
        _identifier(self.receipt_id)
        _identifier(self.program_id)
        if self.origin not in (*ORIGINS, "unknown") or self.state not in (*RECEIPT_STATES, "unknown"):
            raise ValueError("explicit origin and settlement state required")
        _minor_units(self.amount_minor, optional=True)
        _minor_units(self.refund_minor, optional=True)
        if self.amount_minor is not None and self.refund_minor is not None and self.refund_minor > self.amount_minor:
            raise ValueError("principal refund cannot exceed receipt; separate fees belong in costs")
        _currency(self.currency)
        _aware(self.occurred_at)
        _source(self.source)


@dataclass(frozen=True)
class FundingLedger:
    program_id: str
    beneficiary_group: str
    window: FundingWindow
    receipts: tuple[FundingReceipt, ...]
    coverage: str
    source: Source | None

    def __post_init__(self):
        _identifier(self.program_id)
        _identifier(self.beneficiary_group)
        if type(self.window) is not FundingWindow or self.coverage not in COVERAGE:
            raise ValueError("typed window and declared coverage required")
        if type(self.receipts) is not tuple or any(type(row) is not FundingReceipt for row in self.receipts):
            raise ValueError("typed immutable receipts required")
        if len({row.receipt_id for row in self.receipts}) != len(self.receipts):
            raise ValueError("same canonical transfer cannot be counted twice")
        for row in self.receipts:
            if row.program_id != self.program_id or row.currency != self.window.currency or not self.window.start <= row.occurred_at < self.window.end:
                raise ValueError("receipt must match exact program, currency and accounting window")
        _source(self.source)


@dataclass(frozen=True)
class ProgramCosts:
    program_id: str
    window: FundingWindow
    coverage: CostCoverage
    source: Source | None

    def __post_init__(self):
        _identifier(self.program_id)
        if type(self.window) is not FundingWindow or type(self.coverage) is not CostCoverage:
            raise ValueError("typed window and existing complete cost-category coverage required")
        _source(self.source)


@dataclass(frozen=True)
class ProgramComparison:
    """Same-window retained outside donations for one program and one control.

    Both numbers exclude matching/sponsor principal and refunds. This is an
    unweighted descriptive contrast between declared comparable program units,
    not a fitted counterfactual or population causal effect.
    """
    program_id: str
    control_program_id: str
    window: FundingWindow
    observed_outside_minor: int | None
    control_outside_minor: int | None
    observed_source: Source | None
    control_source: Source | None

    def __post_init__(self):
        _identifier(self.program_id)
        _identifier(self.control_program_id)
        if self.program_id == self.control_program_id or type(self.window) is not FundingWindow:
            raise ValueError("distinct program/control and typed window required")
        _minor_units(self.observed_outside_minor, optional=True)
        _minor_units(self.control_outside_minor, optional=True)
        _source(self.observed_source)
        _source(self.control_source)


@dataclass(frozen=True)
class DisplacementScope:
    target_program_id: str
    window: FundingWindow
    program_ids: tuple[str, ...]
    coverage: str
    source: Source | None

    def __post_init__(self):
        _identifier(self.target_program_id)
        if type(self.window) is not FundingWindow or self.coverage not in COVERAGE or type(self.program_ids) is not tuple:
            raise ValueError("explicit window, immutable affected-program scope and coverage required")
        for identifier in self.program_ids:
            _identifier(identifier)
        if len(set(self.program_ids)) != len(self.program_ids) or self.target_program_id in self.program_ids:
            raise ValueError("affected programs must be distinct and exclude the target")
        _source(self.source)
        if self.source is not None and self.source.retrieved_at > self.window.start:
            raise ValueError("prospective scope reference required, not proof of actual preregistration")


@dataclass(frozen=True)
class BeneficiaryReport:
    program_id: str
    beneficiary_group: str
    window: FundingWindow
    metric: str
    unit: str
    value: float | None
    denominator: int | None
    source: Source | None

    def __post_init__(self):
        _identifier(self.program_id)
        _identifier(self.beneficiary_group)
        if type(self.window) is not FundingWindow:
            raise ValueError("typed report observation window required")
        _text(self.metric)
        _text(self.unit)
        _number(self.value, optional=True)
        _minor_units(self.denominator, optional=True)
        if self.denominator == 0:
            raise ValueError("positive report denominator or explicit unknown required")
        _source(self.source)


@dataclass(frozen=True)
class OriginTotal:
    gross_minor: int | None
    refunds_minor: int | None
    retained_minor: int | None


@dataclass(frozen=True)
class OtherProgramChange:
    comparison: ProgramComparison
    change_minor: int | None


@dataclass(frozen=True)
class ProgramFundingResult:
    ledger: FundingLedger
    costs: ProgramCosts
    comparisons: tuple[ProgramComparison, ...]
    displacement_scope: DisplacementScope | None
    beneficiary_report: BeneficiaryReport | None
    sources: tuple[Source, ...]
    by_origin: Mapping[str, OriginTotal]
    recorded_refunds_minor: int | None
    operating_costs_minor: int | None
    declared_external_change_minor: int | None
    other_program_changes: tuple[OtherProgramChange, ...]
    displacement_status: str
    scoped_recorded_balance_minor: int | None
    beneficiary_report_status: str
    missing_fields: tuple[str, ...]
    proof_level: str = field(default="P0", init=False)
    measurement_authentication: str = field(default="NOT_VERIFIED", init=False)
    income_status: str = field(default="NOT_VERIFIED", init=False)
    human_welfare_status: str = field(default="NOT_MEASURED", init=False)
    action: str = field(default="NO_ACTION", init=False)
    verified_income_minor: None = field(default=None, init=False)
    verified_net_benefit_minor: None = field(default=None, init=False)


def _covers_window(source, window):
    return source is not None and source.retrieved_at >= window.end


def _change(comparison):
    if (comparison.observed_outside_minor is None or comparison.control_outside_minor is None
            or not _covers_window(comparison.observed_source, comparison.window)
            or not _covers_window(comparison.control_source, comparison.window)):
        return None
    return comparison.observed_outside_minor - comparison.control_outside_minor


def reconcile_program_funding(ledger: FundingLedger, costs: ProgramCosts, comparisons: tuple[ProgramComparison, ...], *,
                              displacement_scope: DisplacementScope | None = None,
                              beneficiary_report: BeneficiaryReport | None = None,
                              snapshots: Mapping[str, bytes] | None = None):
    """Join supplied evidence without upgrading its authenticity or welfare rank.

    Retained outside donations exclude own/sponsor principal. Refunds reconcile
    against CostCoverage.refunds and are subtracted exactly once; all other cost
    categories are operating costs. The final balance is scoped descriptive
    accounting, never economy-wide new wealth, income proof, or a causal effect.
    """
    if type(ledger) is not FundingLedger or type(costs) is not ProgramCosts:
        raise ValueError("typed funding ledger and program costs required")
    if (costs.program_id, costs.window) != (ledger.program_id, ledger.window):
        raise ValueError("costs must bind to the exact program and window/currency")
    if type(comparisons) is not tuple or any(type(row) is not ProgramComparison for row in comparisons):
        raise ValueError("typed immutable comparisons required")
    comparison_ids = [identifier for row in comparisons for identifier in (row.program_id, row.control_program_id)]
    if len(set(comparison_ids)) != len(comparison_ids) or any(row.window != ledger.window for row in comparisons):
        raise ValueError("contemporaneous disjoint program/control pairs in the same currency required")
    if displacement_scope is not None:
        if type(displacement_scope) is not DisplacementScope or (displacement_scope.target_program_id, displacement_scope.window) != (ledger.program_id, ledger.window):
            raise ValueError("displacement scope must bind to target and window")
        if any(row.program_id != ledger.program_id and row.program_id not in displacement_scope.program_ids for row in comparisons):
            raise ValueError("comparison outside the declared displacement scope")
    if beneficiary_report is not None and type(beneficiary_report) is not BeneficiaryReport:
        raise ValueError("typed public beneficiary report or explicit missing report required")
    references = [ledger.source, costs.source] + [row.source for row in ledger.receipts]
    references += [ref for row in comparisons for ref in (row.observed_source, row.control_source)]
    if displacement_scope is not None:
        references.append(displacement_scope.source)
    if beneficiary_report is not None:
        references.append(beneficiary_report.source)
    sources = {}
    for ref in references:
        if ref is not None:
            if ref.source_id in sources and sources[ref.source_id] != ref:
                raise ValueError("one source ID cannot bind conflicting provenance")
            sources[ref.source_id] = ref
    if snapshots is not None:
        if not isinstance(snapshots, Mapping) or not set(snapshots) <= set(sources):
            raise ValueError("snapshots must refer to declared sources")
        for source_id, payload in snapshots.items():
            sources[source_id].verify_content(payload)
    complete = ledger.coverage == "complete" and _covers_window(ledger.source, ledger.window) and all(row.origin != "unknown" for row in ledger.receipts)
    totals, missing = {}, []
    for origin in ORIGINS:
        rows = [row for row in ledger.receipts if row.origin == origin]
        usable = complete and all(row.state == "settled" and row.amount_minor is not None and row.refund_minor is not None
                                  and row.source is not None and row.source.retrieved_at >= row.occurred_at for row in rows)
        if usable:
            gross, refunds = sum(row.amount_minor for row in rows), sum(row.refund_minor for row in rows)
            _minor_units(gross)
            _minor_units(refunds)
            totals[origin] = OriginTotal(gross, refunds, gross - refunds)
        else:
            totals[origin] = OriginTotal(None, None, None)
            missing.append("funding." + origin)
    recorded_refunds = sum(total.refunds_minor for total in totals.values()) if all(total.refunds_minor is not None for total in totals.values()) else None
    amounts = costs.coverage.amounts_minor
    if recorded_refunds is not None and amounts["refunds"] is not None and recorded_refunds != amounts["refunds"]:
        raise ValueError("CostCoverage refunds must reconcile with receipt refunds, not be subtracted twice")
    operating = sum(amount for name, amount in amounts.items() if name != "refunds") if (
        _covers_window(costs.source, costs.window) and all(amount is not None for name, amount in amounts.items() if name != "refunds")) else None
    if operating is None:
        missing.append("operating_costs")
    if recorded_refunds is None or amounts["refunds"] is None:
        missing.append("refund_reconciliation")
    primary = next((row for row in comparisons if row.program_id == ledger.program_id), None)
    external_change = None
    outside = totals["outside_donor"].retained_minor
    if primary is not None:
        if primary.observed_source is not None and primary.observed_source != ledger.source:
            raise ValueError("target comparison must use the exact funding-ledger source")
        if outside is not None and primary.observed_outside_minor is not None and primary.observed_outside_minor != outside:
            raise ValueError("target comparison must use reconciled retained outside funds")
        if outside is not None:
            external_change = _change(primary)
    if external_change is None:
        missing.append("target_comparison")
    others = tuple(OtherProgramChange(row, _change(row)) for row in comparisons if row.program_id != ledger.program_id)
    displacement_complete = (displacement_scope is not None and displacement_scope.coverage == "complete" and displacement_scope.source is not None
                             and set(displacement_scope.program_ids) == {row.comparison.program_id for row in others}
                             and all(row.change_minor is not None for row in others))
    displacement_status = "DECLARED_COMPARISON_ONLY" if displacement_complete else "UNKNOWN_DISPLACEMENT"
    if not displacement_complete:
        missing.append("displacement")
    balance = None
    if external_change is not None and operating is not None and displacement_complete and recorded_refunds is not None and amounts["refunds"] is not None:
        other_changes = [row.change_minor for row in others]
        # The existing helper uses float. Keep every possible intermediate sum
        # within the exactly representable integer range before converting.
        if sum(abs(value) for value in (external_change, operating, *other_changes)) > 2**53 - 1:
            raise ValueError("amounts exceed exact-integer range of existing accounting helper")
        balance = int(net_additional_resources(external_change, other_changes, operating))
    report = beneficiary_report
    if report is None:
        report_status = "REPORT_MISSING"
    elif (report.program_id, report.beneficiary_group, report.window) != (ledger.program_id, ledger.beneficiary_group, ledger.window):
        report_status = "REPORT_BINDING_MISMATCH"
    elif report.source is None or not _covers_window(report.source, report.window) or report.value is None or report.denominator is None:
        report_status = "INCOMPLETE_REPORT"
    elif any(report.source.content_sha256.lower() == ref.content_sha256.lower() for ref in (ledger.source, *(row.source for row in ledger.receipts)) if ref is not None):
        report_status = "TRANSFER_REFERENCE_ONLY"
    else:
        report_status = "DECLARED_REPORT_NOT_VERIFIED"
    return ProgramFundingResult(ledger, costs, comparisons, displacement_scope, report, tuple(sources.values()), MappingProxyType(totals),
                                recorded_refunds, operating, external_change, others, displacement_status, balance, report_status, tuple(missing))
