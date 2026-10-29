"""D010-D012 public opportunity intake and explicitly unverified accounting.

Posting, delivery, approval and settlement have separate public availability.
Known declared amounts can be reconciled without pretending to authenticate a
payment. No account access, private recipient data, earnings action or welfare
inference occurs here. Amounts are integer minor units in one explicit currency.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit

from .economic_scorecard import CostCoverage
from .models.source import Source
from .outcome_bench import _currency, _minor


STAGES = ("posting", "delivery", "approval", "settlement")


def _identifier(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is None:
        raise ValueError("bounded opaque aggregate identifier required")


def _hash(value, *, optional=False):
    if optional and value is None:
        return
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("immutable lowercase SHA256 artifact reference required")


def _resource_url(url: str) -> tuple:
    """Conservative HTTPS resource alias key, never verified payment identity.

    RFC 9110 4.2.2-4.2.3: HTTPS host case, default port 443, fragments,
    and empty-versus-root paths cannot establish separate payment documents.
    Normalize only unreserved percent escapes; preserve reserved escapes,\n    case-sensitive literal paths/queries and non-default ports.
    """
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("invalid public opportunity source port") from None
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("invalid public opportunity source port")
    return (parsed.scheme.lower(), parsed.hostname.lower(),
            None if port in (None, 443) else port,
            _normalize_percent_unreserved(parsed.path or "/"),
            _normalize_percent_unreserved(parsed.query))


_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")


def _normalize_percent_unreserved(component: str) -> str:
    """RFC 3986 6.2.2.2: decode only unreserved triplets, uppercase others.

    Do not decode reserved delimiters (e.g. %2F), sort query parameters,
    or repeatedly decode nested escapes. This remains an offline alias key.
    """
    if re.search(r"%(?![0-9A-Fa-f]{2})", component):
        raise ValueError("invalid public opportunity percent encoding")

    def replace(match):
        char = chr(int(match.group(1), 16))
        return char if char in _UNRESERVED else "%" + match.group(1).upper()

    return _PERCENT_ESCAPE.sub(replace, component)


@dataclass(frozen=True)
class OpportunityStage:
    name: str
    visibility: str
    source: Source | None = None

    def __post_init__(self):
        if self.name not in STAGES or self.visibility not in {"public", "not_public", "unknown"}:
            raise ValueError("explicit opportunity stage and public availability required")
        if self.visibility == "public":
            if type(self.source) is not Source:
                raise ValueError("public stage requires a rights-reviewed source reference")
        elif self.source is not None:
            raise ValueError("nonpublic/unknown material must not enter this public-only adapter")


@dataclass(frozen=True)
class SettlementClaim:
    opportunity_id: str
    beneficiary_group: str
    artifact_sha256: str
    currency: str
    amount_minor: int
    state: str
    source: Source

    def __post_init__(self):
        _identifier(self.opportunity_id)
        _identifier(self.beneficiary_group)
        _hash(self.artifact_sha256)
        _currency(self.currency)
        _minor(self.amount_minor)
        if self.state not in {"settled", "pending", "reversed", "disputed"}:
            raise ValueError("explicit payment lifecycle state required")
        if type(self.source) is not Source:
            raise ValueError("public nonpersonal receipt source required")


@dataclass(frozen=True)
class OpportunityRecord:
    opportunity_id: str
    beneficiary_group: str
    currency: str
    nominal_award_minor: int | None
    posting: OpportunityStage
    delivery: OpportunityStage
    approval: OpportunityStage
    settlement: OpportunityStage
    delivered_artifact_sha256: str | None
    approved_artifact_sha256: str | None
    receipt: SettlementClaim | None

    def __post_init__(self):
        _identifier(self.opportunity_id)
        _identifier(self.beneficiary_group)
        _currency(self.currency)
        _minor(self.nominal_award_minor, optional=True)
        for name in STAGES:
            stage = getattr(self, name)
            if type(stage) is not OpportunityStage or stage.name != name:
                raise ValueError("each named stage must retain its own evidence column")
        _hash(self.delivered_artifact_sha256, optional=True)
        _hash(self.approved_artifact_sha256, optional=True)
        if self.receipt is not None and type(self.receipt) is not SettlementClaim:
            raise ValueError("typed receipt claim or explicit missing receipt required")


@dataclass(frozen=True)
class OpportunityCosts:
    expenses: CostCoverage
    labor_minutes: int | None
    opportunity_cost_minor: int | None
    opportunities_considered: int | None

    def __post_init__(self):
        if type(self.expenses) is not CostCoverage:
            raise ValueError("every expense category must be covered or explicitly unknown")
        _minor(self.labor_minutes, optional=True)
        _minor(self.opportunity_cost_minor, optional=True)
        _minor(self.opportunities_considered, optional=True)
        if self.opportunities_considered == 0:
            raise ValueError("opportunity denominator must be positive or unknown")


@dataclass(frozen=True)
class OpportunityOutcome:
    stage_visibility: Mapping[str, str]
    evidence_status: str
    nominal_award_minor: int | None
    declared_received_minor: int | None
    expenses_minor: int | None
    labor_minutes: int | None
    opportunity_cost_minor: int | None
    opportunities_considered: int | None
    declared_cash_net_minor: int | None
    declared_economic_net_minor: int | None
    net_per_labor_hour_minor: float | None
    net_per_opportunity_minor: float | None
    missing_fields: tuple[str, ...]
    income_status: str = "NOT_VERIFIED"
    verified_income_minor: None = None
    human_welfare_status: str = "NOT_MEASURED"


def reconcile_opportunity(record: OpportunityRecord, costs: OpportunityCosts, *,
                          snapshots: Mapping[str, bytes] | None = None) -> OpportunityOutcome:
    """Calculate only declared settlement amounts with exact chain binding.

    Expense labor money, elapsed labor time and foregone opportunities are
    separate. Time is never silently priced. Opportunity cost must exclude
    amounts already counted as expenses to avoid double counting. No causal
    income increase follows from gross or net receipts without a comparator.
    """
    if type(record) is not OpportunityRecord or type(costs) is not OpportunityCosts:
        raise ValueError("typed public opportunity and explicit cost coverage required")
    stages = tuple(getattr(record, name) for name in STAGES)
    references = [stage.source for stage in stages if stage.source is not None]
    if record.receipt is not None:
        references.append(record.receipt.source)
    sources = {}
    for source in references:
        # Validate every declared source before any ID match can short-circuit.
        _resource_url(source.url)
        if source.source_id in sources and sources[source.source_id] != source:
            raise ValueError("same source ID cannot describe conflicting snapshots")
        sources[source.source_id] = source
    if snapshots is not None:
        if not isinstance(snapshots, Mapping) or not set(snapshots) <= set(sources):
            raise ValueError("snapshot must match a declared public source")
        for source_id, payload in snapshots.items():
            sources[source_id].verify_content(payload)

    receipt = record.receipt
    received = None
    if receipt is None:
        status = "RECEIPT_MISSING"
    elif receipt.state != "settled":
        status = "SETTLEMENT_INCOMPLETE"
    elif any(stage.visibility != "public" for stage in stages):
        status = "PUBLIC_EVIDENCE_CHAIN_INCOMPLETE"
    elif (record.delivered_artifact_sha256 is None or record.approved_artifact_sha256 is None
          or record.delivered_artifact_sha256 != record.approved_artifact_sha256):
        status = "ARTIFACT_MISMATCH"
    elif (receipt.opportunity_id, receipt.beneficiary_group, receipt.artifact_sha256, receipt.currency) != (
            record.opportunity_id, record.beneficiary_group, record.approved_artifact_sha256, record.currency):
        status = "RECEIPT_BINDING_MISMATCH"
    elif receipt.source != record.settlement.source:
        status = "RECEIPT_SOURCE_MISMATCH"
    elif any(
        stage.source is not None and (
            stage.source.source_id == receipt.source.source_id
            or _resource_url(stage.source.url) == _resource_url(receipt.source.url)
            or stage.source.content_sha256.lower() == receipt.source.content_sha256.lower()
        )
        for stage in stages if stage.name != "settlement"
    ):
        # A copied approval/delivery/posting page is not a separate payment
        # receipt, even when relabeled with a new source ID or URL. Passing
        # this necessary condition still does NOT authenticate bank receipt.
        status = "RECEIPT_EVIDENCE_REUSED"
    else:
        status = "DECLARED_SETTLEMENT_RECONCILED"
        received = receipt.amount_minor

    amounts = costs.expenses.amounts_minor
    missing = ["expenses." + category for category, amount in amounts.items() if amount is None]
    for field in ("labor_minutes", "opportunity_cost_minor", "opportunities_considered"):
        if getattr(costs, field) is None:
            missing.append(field)
    if received is None:
        missing.append("reconciled_settlement")
    expenses = None if any(amount is None for amount in amounts.values()) else sum(amounts.values())
    cash_net = None if received is None or expenses is None else received - expenses
    economic_net = None if cash_net is None or costs.opportunity_cost_minor is None else cash_net - costs.opportunity_cost_minor
    per_hour = None if economic_net is None or not costs.labor_minutes else economic_net * 60 / costs.labor_minutes
    per_opportunity = None if economic_net is None or costs.opportunities_considered is None else economic_net / costs.opportunities_considered
    return OpportunityOutcome(
        MappingProxyType({stage.name: stage.visibility for stage in stages}), status,
        record.nominal_award_minor, received, expenses, costs.labor_minutes,
        costs.opportunity_cost_minor, costs.opportunities_considered, cash_net,
        economic_net, per_hour, per_opportunity, tuple(sorted(missing)),
    )
