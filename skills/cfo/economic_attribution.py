"""Repository-owned receipt contract for Product Loop economic attribution."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path


SCHEMA_VERSION = "lm.cfo.economic-attribution.v1"
ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "apps/life-manager/config/product-loop-catalog.json"
SCHEMA_PATH = Path(__file__).parent / "schemas/economic-attribution-v1.schema.json"
PRODUCT_LOOP_IDS = tuple(row["id"] for row in json.loads(CATALOG.read_text())["loops"])

REVENUE = "settled_external_revenue"
REFUND = "refund"
COST_CATEGORIES = (
    "provider_fee", "model_cost", "tool_cost", "browser_cost", "infra_cost",
    "payment_fee", "other_measured_cost",
)
EXCLUDED_CATEGORIES = (
    "pending_revenue", "payout", "owner_deposit", "self_payment", "internal_transfer",
    "token_appreciation", "unrealized_investment_pnl", "fundraising",
)
COUNTED_CATEGORIES = (REVENUE, REFUND, *COST_CATEGORIES)
AS_OF_CATEGORIES = ("mrr", "liquid_balance")
COVERED_CATEGORIES = (*COUNTED_CATEGORIES, *AS_OF_CATEGORIES)
ALL_CATEGORIES = (*COUNTED_CATEGORIES, *EXCLUDED_CATEGORIES)
VERIFICATION_STATES = ("verified", "unverified", "pending")
REVENUE_CLASSES = ("one_time", "monthly_recurring", "other_recurring")
COVERAGE_STATES = ("complete", "gap")
GAP_REASONS = (
    "source_unconnected", "credential_missing", "read_failed", "stale_readback",
    "unsupported_currency", "unverified_receipt", "missing_coverage", "missing_category",
)
FRESHNESS_MAX_AGE = timedelta(hours=24)

IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,511}$")
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
CURRENCY = re.compile(r"^[A-Z][A-Z0-9]{2,11}$")
EVIDENCE = re.compile(r"^[a-z][a-z0-9+.-]*://\S+$")
AMOUNT = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d{1,18})?$")
POSITIVE_AMOUNT = re.compile(r"^(?=.*[1-9])(?:0|[1-9]\d*)(?:\.\d{1,18})?$")
RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)

RECEIPT_REQUIRED = (
    "schema_version", "record_type", "receipt_id", "product_loop_id", "provider", "currency",
    "occurred_at", "settled_at", "verification_state", "revenue_class", "evidence_refs", "components",
)
COVERAGE_REQUIRED = (
    "schema_version", "record_type", "product_loop_id", "source_id", "projection",
    "window_start", "window_end", "coverage_state", "reason", "covered_categories",
    "observed_at", "evidence_refs",
)
BALANCE_REQUIRED = (
    "schema_version", "record_type", "snapshot_id", "account_id", "provider", "currency",
    "amount", "observed_at", "verification_state", "evidence_refs",
)
SUBSCRIPTION_REQUIRED = (
    "schema_version", "record_type", "snapshot_id", "subscription_id", "product_loop_id",
    "provider", "currency", "normalized_monthly_amount", "normalization_basis", "status",
    "observed_at", "verification_state", "evidence_refs",
)


class ContractError(ValueError):
    """Typed fail-closed validation error without provider payloads."""

    def __init__(self, code: str, field: str = "record"):
        super().__init__(f"{code}:{field}")
        self.code = code
        self.field = field


def _fail(code: str, field: str = "record"):
    raise ContractError(code, field)


def _exact_keys(value: dict, required: tuple[str, ...]):
    if not isinstance(value, dict):
        _fail("record_invalid")
    missing = set(required) - set(value)
    if missing:
        _fail("field_missing", sorted(missing)[0])
    extra = set(value) - set(required)
    if extra:
        _fail("field_unknown", sorted(extra)[0])


def _instant(value, field: str) -> str:
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        _fail("timestamp_invalid", field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("timestamp_invalid", field)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("timestamp_naive", field)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _text(value, field: str, pattern: re.Pattern) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        _fail("field_invalid", field)
    return value


def _evidence(value) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        _fail("evidence_invalid", "evidence_refs")
    refs = [_text(item, "evidence_refs", EVIDENCE) for item in value]
    if len(set(refs)) != len(refs):
        _fail("evidence_duplicate", "evidence_refs")
    return refs


def _amount(value, field: str, *, allow_zero: bool = False) -> str:
    if not isinstance(value, str) or not AMOUNT.fullmatch(value):
        _fail("amount_invalid", field)
    try:
        amount = Decimal(value)
    except InvalidOperation:
        _fail("amount_invalid", field)
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        _fail("amount_invalid", field)
    return format(amount.normalize(), "f")


def _common(record: dict):
    if record["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version_invalid", "schema_version")
    loop_id = record["product_loop_id"]
    if loop_id not in PRODUCT_LOOP_IDS:
        _fail("product_loop_invalid", "product_loop_id")
    return loop_id


def _validate_receipt(record: dict) -> dict:
    _exact_keys(record, RECEIPT_REQUIRED)
    loop_id = _common(record)
    if record["record_type"] != "receipt":
        _fail("record_type_invalid", "record_type")
    receipt_id = _text(record["receipt_id"], "receipt_id", IDENTITY)
    provider = _text(record["provider"], "provider", NAME)
    currency = _text(record["currency"], "currency", CURRENCY)
    if currency in {"UNKNOWN", "USD_API_EQUIV"}:
        _fail("currency_unmeasured", "currency")
    occurred_at = _instant(record["occurred_at"], "occurred_at")
    settled_at = None if record["settled_at"] is None else _instant(record["settled_at"], "settled_at")
    if settled_at is not None and settled_at < occurred_at:
        _fail("settlement_before_occurrence", "settled_at")
    state = record["verification_state"]
    if state not in VERIFICATION_STATES:
        _fail("verification_state_invalid", "verification_state")
    revenue_class = record["revenue_class"]
    if revenue_class is not None and revenue_class not in REVENUE_CLASSES:
        _fail("revenue_class_invalid", "revenue_class")
    components = record["components"]
    if not isinstance(components, list) or not components:
        _fail("components_invalid", "components")
    normalized, seen = [], set()
    for index, component in enumerate(components):
        _exact_keys(component, ("category", "amount"))
        category = component["category"]
        if category not in ALL_CATEGORIES:
            _fail("category_invalid", f"components.{index}.category")
        if category in seen:
            _fail("component_duplicate", f"components.{index}.category")
        seen.add(category)
        normalized.append({"category": category, "amount": _amount(component["amount"], f"components.{index}.amount")})
    if seen & set(EXCLUDED_CATEGORIES) and len(seen) != 1:
        _fail("excluded_component_mixed", "components")
    if "pending_revenue" in seen:
        if state != "pending" or settled_at is not None or revenue_class is None:
            _fail("pending_state_invalid", "verification_state")
    elif seen & set(COUNTED_CATEGORIES) and (state != "verified" or settled_at is None):
        _fail("verified_settlement_required", "verification_state")
    if REVENUE in seen and revenue_class is None:
        _fail("revenue_class_required", "revenue_class")
    return {
        "schema_version": SCHEMA_VERSION, "record_type": "receipt", "receipt_id": receipt_id,
        "product_loop_id": loop_id, "provider": provider, "currency": currency,
        "occurred_at": occurred_at, "settled_at": settled_at, "verification_state": state,
        "revenue_class": revenue_class, "evidence_refs": sorted(_evidence(record["evidence_refs"])),
        "components": sorted(normalized, key=lambda item: item["category"]),
    }


def _validate_coverage(record: dict) -> dict:
    _exact_keys(record, COVERAGE_REQUIRED)
    loop_id = _common(record)
    if record["record_type"] != "coverage":
        _fail("record_type_invalid", "record_type")
    projection = record["projection"]
    if projection not in ("historical", "trailing", "as_of"):
        _fail("projection_invalid", "projection")
    start = None if record["window_start"] is None else _instant(record["window_start"], "window_start")
    end = _instant(record["window_end"], "window_end")
    if (projection == "trailing") != (start is not None):
        _fail("coverage_window_invalid", "window_start")
    if start is not None and start >= end:
        _fail("coverage_window_invalid", "window_start")
    state, reason = record["coverage_state"], record["reason"]
    if state not in COVERAGE_STATES or (state == "complete" and reason is not None):
        _fail("coverage_state_invalid", "coverage_state")
    if state == "gap" and reason not in GAP_REASONS:
        _fail("coverage_reason_invalid", "reason")
    categories = record["covered_categories"]
    if not isinstance(categories, list) or len(set(categories)) != len(categories):
        _fail("covered_categories_invalid", "covered_categories")
    if any(category not in COVERED_CATEGORIES for category in categories):
        _fail("covered_categories_invalid", "covered_categories")
    return {
        "schema_version": SCHEMA_VERSION, "record_type": "coverage", "product_loop_id": loop_id,
        "source_id": _text(record["source_id"], "source_id", NAME), "projection": projection,
        "window_start": start, "window_end": end, "coverage_state": state, "reason": reason,
        "covered_categories": sorted(categories),
        "observed_at": _instant(record["observed_at"], "observed_at"),
        "evidence_refs": sorted(_evidence(record["evidence_refs"])),
    }


def _validate_balance(record: dict) -> dict:
    _exact_keys(record, BALANCE_REQUIRED)
    if record["schema_version"] != SCHEMA_VERSION or record["record_type"] != "liquid_balance":
        _fail("record_type_invalid", "record_type")
    currency = _text(record["currency"], "currency", CURRENCY)
    if currency in {"UNKNOWN", "USD_API_EQUIV"}:
        _fail("currency_unmeasured", "currency")
    state = record["verification_state"]
    if state not in ("verified", "unverified"):
        _fail("verification_state_invalid", "verification_state")
    return {
        "schema_version": SCHEMA_VERSION, "record_type": "liquid_balance",
        "snapshot_id": _text(record["snapshot_id"], "snapshot_id", IDENTITY),
        "account_id": _text(record["account_id"], "account_id", IDENTITY),
        "provider": _text(record["provider"], "provider", NAME), "currency": currency,
        "amount": _amount(record["amount"], "amount", allow_zero=True),
        "observed_at": _instant(record["observed_at"], "observed_at"),
        "verification_state": state, "evidence_refs": sorted(_evidence(record["evidence_refs"])),
    }


def _validate_subscription(record: dict) -> dict:
    _exact_keys(record, SUBSCRIPTION_REQUIRED)
    loop_id = _common(record)
    if record["record_type"] != "subscription_snapshot":
        _fail("record_type_invalid", "record_type")
    currency = _text(record["currency"], "currency", CURRENCY)
    if currency in {"UNKNOWN", "USD_API_EQUIV"}:
        _fail("currency_unmeasured", "currency")
    state = record["verification_state"]
    if state not in ("verified", "unverified"):
        _fail("verification_state_invalid", "verification_state")
    status = record["status"]
    if status not in ("active", "inactive"):
        _fail("subscription_status_invalid", "status")
    if record["normalization_basis"] != "provider_monthly":
        _fail("normalization_basis_invalid", "normalization_basis")
    amount = _amount(
        record["normalized_monthly_amount"], "normalized_monthly_amount",
        allow_zero=status == "inactive",
    )
    return {
        "schema_version": SCHEMA_VERSION, "record_type": "subscription_snapshot",
        "snapshot_id": _text(record["snapshot_id"], "snapshot_id", IDENTITY),
        "subscription_id": _text(record["subscription_id"], "subscription_id", IDENTITY),
        "product_loop_id": loop_id,
        "provider": _text(record["provider"], "provider", NAME), "currency": currency,
        "normalized_monthly_amount": amount, "normalization_basis": "provider_monthly",
        "status": status, "observed_at": _instant(record["observed_at"], "observed_at"),
        "verification_state": state,
        "evidence_refs": sorted(_evidence(record["evidence_refs"])),
    }


def validate_record(record: dict) -> dict:
    if not isinstance(record, dict):
        _fail("record_invalid")
    if record.get("record_type") == "receipt":
        return _validate_receipt(record)
    if record.get("record_type") == "coverage":
        return _validate_coverage(record)
    if record.get("record_type") == "liquid_balance":
        return _validate_balance(record)
    if record.get("record_type") == "subscription_snapshot":
        return _validate_subscription(record)
    _fail("record_type_invalid", "record_type")


def _money_text(value: Decimal) -> str:
    if not value:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _exact_add(*numbers: Decimal) -> Decimal:
    if not numbers:
        return Decimal("0")
    min_exponent = min(number.as_tuple().exponent for number in numbers)
    max_adjusted = max(number.adjusted() if number else 0 for number in numbers)
    precision = max(1, max_adjusted - min_exponent + 1) + len(numbers)
    with localcontext() as context:
        context.prec = precision
        return sum(numbers, Decimal("0"))


def _stale_at(observed_at: str, end: str) -> bool:
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        boundary = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if observed.tzinfo is None or boundary.tzinfo is None:
            return True
        age = boundary.astimezone(timezone.utc) - observed.astimezone(timezone.utc)
        return age < timedelta(0) or age >= FRESHNESS_MAX_AGE
    except (TypeError, ValueError, OverflowError):
        return True


def _coverage(rows: list[dict], loop_id: str, projection: str, start: str | None, end: str,
              required_categories: tuple[str, ...]) -> list[dict]:
    candidates = [row for row in rows if row["product_loop_id"] == loop_id
                  and row["projection"] == projection and row["window_start"] == start
                  and row["window_end"] == end]
    by_source: dict[str, list[dict]] = {}
    for row in candidates:
        by_source.setdefault(row["source_id"], []).append(row)
    matched, gaps = [], []
    for source_id, observations in by_source.items():
        eligible = [row for row in observations if row["observed_at"] <= end]
        if not eligible:
            gaps.append({"product_loop_id": loop_id, "source_id": source_id,
                         "reason": "stale_readback"})
            continue
        latest = max(eligible, key=lambda row: row["observed_at"])
        if _stale_at(latest["observed_at"], end):
            gaps.append({"product_loop_id": loop_id, "source_id": source_id,
                         "reason": "stale_readback"})
            continue
        matched.append(latest)
    gaps.extend(
        {"product_loop_id": loop_id, "source_id": row["source_id"], "reason": row["reason"]}
        for row in matched if row["coverage_state"] == "gap"
    )
    covered = {
        category
        for row in matched if row["coverage_state"] == "complete"
        for category in row["covered_categories"]
    }
    source_id = candidates[0]["source_id"] if candidates else "unreported"
    gaps.extend({
        "product_loop_id": loop_id, "source_id": source_id,
        "reason": "missing_category", "category": category,
    } for category in sorted(set(required_categories) - covered))
    return gaps


def _summarize(receipts: list[dict], gaps: list[dict]) -> dict:
    totals: dict[str, dict[str, Decimal]] = {}
    excluded, unverified = [], []
    for receipt in receipts:
        counted = any(item["category"] in COUNTED_CATEGORIES for item in receipt["components"])
        if counted and receipt["verification_state"] != "verified":
            unverified.append(receipt["receipt_id"])
            continue
        for component in receipt["components"]:
            category = component["category"]
            if category in EXCLUDED_CATEGORIES:
                excluded.append({
                    "receipt_id": receipt["receipt_id"], "product_loop_id": receipt["product_loop_id"],
                    "provider": receipt["provider"], "category": category,
                    "amount": component["amount"], "currency": receipt["currency"],
                })
                continue
            bucket = totals.setdefault(receipt["currency"], {name: Decimal(0) for name in COUNTED_CATEGORIES})
            bucket[category] = _exact_add(bucket[category], Decimal(component["amount"]))
    currencies = {}
    unknown_categories = set()
    if any("category" not in gap for gap in gaps):
        unknown_categories.update(COUNTED_CATEGORIES)
    else:
        unknown_categories.update(gap["category"] for gap in gaps)
    for currency, bucket in sorted(totals.items()):
        total_cost = _exact_add(*(bucket[name] for name in COST_CATEGORIES))
        values = {
            name: None if name in unknown_categories else _money_text(bucket[name])
            for name in COUNTED_CATEGORIES
        }
        values["status"] = "unknown" if unknown_categories else "verified"
        values["unknown_categories"] = sorted(unknown_categories)
        values["total_cost"] = (None if unknown_categories & set(COST_CATEGORIES)
                                else _money_text(total_cost))
        values["net"] = (None if unknown_categories
                         else _money_text(_exact_add(
                             bucket[REVENUE], -bucket[REFUND], -total_cost,
                         )))
        currencies[currency] = values
    all_gaps = [*gaps, *({"source_id": "receipt", "reason": "unverified_receipt", "receipt_id": value}
                         for value in sorted(set(unverified)))]
    status = "unknown" if all_gaps else "verified" if currencies else "zero"
    return {"status": status, "currencies": currencies, "excluded": sorted(excluded, key=lambda row: row["receipt_id"]),
            "coverage_gaps": all_gaps}


def _window(receipts: list[dict], coverage_rows: list[dict], projection: str,
            start: str | None, end: str) -> dict:
    selected = [row for row in receipts if (start is None or (row["settled_at"] or row["occurred_at"]) >= start)
                and (row["settled_at"] or row["occurred_at"]) < end]
    loops, company_gaps = {}, []
    for loop_id in PRODUCT_LOOP_IDS:
        gaps = _coverage(coverage_rows, loop_id, projection, start, end, COUNTED_CATEGORIES)
        company_gaps.extend(gaps)
        loops[loop_id] = _summarize([row for row in selected if row["product_loop_id"] == loop_id], gaps)
    return {"window_start": start, "window_end": end, "loops": loops,
            "company": _summarize(selected, company_gaps)}


def _as_of_gaps(coverage_rows: list[dict], end: str, category: str) -> list[dict]:
    gaps = []
    for loop_id in PRODUCT_LOOP_IDS:
        gaps.extend(_coverage(coverage_rows, loop_id, "as_of", None, end, (category,)))
    return gaps


def _latest_subscriptions(snapshots: list[dict], end: str) -> tuple[list[dict], set[str]]:
    by_subscription: dict[tuple[str, str], list[dict]] = {}
    for snapshot in snapshots:
        subscription_id = (snapshot["provider"], snapshot["subscription_id"])
        by_subscription.setdefault(subscription_id, []).append(snapshot)
    latest, stale_loops = [], set()
    for observations in by_subscription.values():
        by_observed_at = {}
        for row in observations:
            observed_at = row["observed_at"]
            if observed_at in by_observed_at and by_observed_at[observed_at] != row:
                _fail("subscription_observation_conflict", "observed_at")
            by_observed_at[observed_at] = row
        eligible = [row for row in observations if row["observed_at"] <= end]
        if not eligible:
            stale_loops.add(max(observations, key=lambda row: row["observed_at"])["product_loop_id"])
            continue
        selected = max(eligible, key=lambda row: row["observed_at"])
        latest.append(selected)
        if _stale_at(selected["observed_at"], end):
            stale_loops.add(selected["product_loop_id"])
    return latest, stale_loops


def _mrr_scope(snapshots: list[dict], coverage_gaps: list[dict], *, stale: bool) -> dict:
    reasons = []
    if coverage_gaps:
        reasons.append("mrr_coverage_unknown")
    if stale:
        reasons.append("subscription_snapshot_stale")
    if any(row["verification_state"] != "verified" for row in snapshots):
        reasons.append("subscription_snapshot_unverified")
    totals: dict[str, Decimal] = {}
    for row in snapshots:
        if row["status"] != "active" or row["verification_state"] != "verified":
            continue
        totals[row["currency"]] = (totals.get(row["currency"], Decimal(0))
                                    + Decimal(row["normalized_monthly_amount"]))
    return {"status": "unknown" if reasons else "verified",
            "currencies": ({} if reasons else {
                currency: _money_text(amount)
                for currency, amount in sorted(totals.items())
            }),
            "reasons": reasons, "coverage_gaps": coverage_gaps}


def _mrr(snapshots: list[dict], coverage_rows: list[dict], end: str) -> dict:
    latest, stale_loops = _latest_subscriptions(snapshots, end)
    loops = {}
    for loop_id in PRODUCT_LOOP_IDS:
        gaps = _coverage(coverage_rows, loop_id, "as_of", None, end, ("mrr",))
        loops[loop_id] = _mrr_scope(
            [row for row in latest if row["product_loop_id"] == loop_id], gaps,
            stale=loop_id in stale_loops,
        )
    company_totals: dict[str, Decimal] = {}
    company_reasons, company_gaps = set(), []
    for row in loops.values():
        company_reasons.update(row["reasons"])
        company_gaps.extend(row["coverage_gaps"])
        for currency, amount in row["currencies"].items():
            company_totals[currency] = company_totals.get(currency, Decimal(0)) + Decimal(amount)
    company = {
        "status": "unknown" if company_reasons else "verified",
        "currencies": ({} if company_reasons else {
            currency: _money_text(amount)
            for currency, amount in sorted(company_totals.items())
        }),
        "reasons": sorted(company_reasons), "coverage_gaps": company_gaps,
    }
    return {"as_of": end, "loops": loops, "company": company}


def _window_days(start: str, end: str) -> Decimal:
    start_at = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_at = datetime.fromisoformat(end.replace("Z", "+00:00"))
    delta = end_at - start_at
    microseconds = ((delta.days * 86400 + delta.seconds) * 1_000_000
                    + delta.microseconds)
    return Decimal(microseconds) / Decimal(86_400_000_000)


def _runway(trailing: dict, balances: list[dict], start: str, end: str,
            balance_coverage_gaps: list[dict]) -> dict:
    if trailing["company"]["status"] == "unknown":
        return {"status": "unknown", "currencies": {}, "reasons": ["trailing_burn_unknown"]}
    if balance_coverage_gaps:
        return {"status": "unknown", "currencies": {},
                "reasons": ["liquid_balance_coverage_unknown"]}

    by_account: dict[tuple[str, str], list[dict]] = {}
    for balance in balances:
        account = (balance["provider"], balance["account_id"])
        by_account.setdefault(account, []).append(balance)
    if not by_account:
        return {"status": "unknown", "currencies": {}, "reasons": ["liquid_balance_missing"]}
    latest, stale = {}, False
    for account, observations in by_account.items():
        by_observed_at = {}
        for row in observations:
            observed_at = row["observed_at"]
            if observed_at in by_observed_at and by_observed_at[observed_at] != row:
                _fail("balance_observation_conflict", "observed_at")
            by_observed_at[observed_at] = row
        eligible = [row for row in observations if row["observed_at"] <= end]
        if not eligible:
            stale = True
            continue
        selected = max(eligible, key=lambda row: row["observed_at"])
        latest[account] = selected
        stale = stale or _stale_at(selected["observed_at"], end)
    if stale:
        return {"status": "unknown", "currencies": {}, "reasons": ["liquid_balance_stale"]}
    if any(row["verification_state"] != "verified" for row in latest.values()):
        return {"status": "unknown", "currencies": {}, "reasons": ["liquid_balance_unverified"]}

    balance_totals: dict[str, Decimal] = {}
    for row in latest.values():
        balance_totals[row["currency"]] = balance_totals.get(row["currency"], Decimal(0)) + Decimal(row["amount"])
    burn_currencies = set(trailing["company"]["currencies"])
    if burn_currencies and burn_currencies != set(balance_totals):
        return {"status": "unknown", "currencies": {}, "reasons": ["currency_mismatch"]}

    days = _window_days(start, end)
    currencies = {}
    for currency, liquid_balance in sorted(balance_totals.items()):
        values = trailing["company"]["currencies"].get(currency, {})
        net_burn = (Decimal(values.get("total_cost", "0"))
                    + Decimal(values.get(REFUND, "0"))
                    - Decimal(values.get(REVENUE, "0")))
        state = "positive_cashflow" if net_burn <= 0 else "verified"
        currencies[currency] = {
            "status": state,
            "liquid_balance": _money_text(liquid_balance),
            "net_cash_burn": _money_text(net_burn),
            "window_days": _money_text(days),
            "runway_days": None if net_burn <= 0 else _money_text(liquid_balance * days / net_burn),
        }
    root_state = ("positive_cashflow"
                  if all(row["status"] == "positive_cashflow" for row in currencies.values())
                  else "verified")
    return {"status": root_state, "currencies": currencies, "reasons": []}


def project(records: list[dict], *, snapshot_at: str, trailing_start: str) -> dict:
    end, start = _instant(snapshot_at, "snapshot_at"), _instant(trailing_start, "trailing_start")
    if start >= end:
        _fail("projection_window_invalid", "trailing_start")
    receipts, balances, snapshots = {}, {}, {}
    coverage_by_key, duplicates = {}, set()
    for raw in records:
        row = validate_record(raw)
        if row["record_type"] == "coverage":
            key = (row["product_loop_id"], row["source_id"], row["projection"],
                   row["window_start"], row["window_end"], row["observed_at"])
            if key in coverage_by_key and coverage_by_key[key] != row:
                _fail("coverage_conflict", "source_id")
            coverage_by_key[key] = row
            continue
        if row["record_type"] == "liquid_balance":
            balance_id = (row["provider"], row["snapshot_id"])
            if balance_id in balances and balances[balance_id] != row:
                _fail("balance_conflict", "snapshot_id")
            balances[balance_id] = row
            continue
        if row["record_type"] == "subscription_snapshot":
            snapshot_id = (row["provider"], row["snapshot_id"])
            if snapshot_id in snapshots and snapshots[snapshot_id] != row:
                _fail("subscription_snapshot_conflict", "snapshot_id")
            snapshots[snapshot_id] = row
            continue
        receipt_id = (row["provider"], row["receipt_id"])
        if receipt_id in receipts:
            if receipts[receipt_id] != row:
                _fail("receipt_conflict", "receipt_id")
            duplicates.add(receipt_id)
        else:
            receipts[receipt_id] = row
    receipt_rows = list(receipts.values())
    coverage_rows = list(coverage_by_key.values())
    historical = _window(receipt_rows, coverage_rows, "historical", None, end)
    trailing = _window(receipt_rows, coverage_rows, "trailing", start, end)
    return {
        "schema_version": SCHEMA_VERSION, "snapshot_at": end, "trailing_start": start,
        "duplicate_receipts": [
            {"provider": provider, "receipt_id": receipt_id}
            for provider, receipt_id in sorted(duplicates)
        ],
        "historical": historical, "trailing": trailing,
        "mrr": _mrr(list(snapshots.values()), coverage_rows, end),
        "runway": _runway(
            trailing, list(balances.values()), start, end,
            _as_of_gaps(coverage_rows, end, "liquid_balance"),
        ),
    }


def economic_attribution_schema() -> dict:
    timestamp = {"type": "string", "format": "date-time", "pattern": RFC3339.pattern}
    nullable_timestamp = {"oneOf": [timestamp, {"type": "null"}]}
    evidence = {"type": "array", "minItems": 1, "maxItems": 32, "uniqueItems": True,
                "items": {"type": "string", "pattern": EVIDENCE.pattern}}
    currency = {"type": "string", "pattern": CURRENCY.pattern,
                "not": {"enum": ["UNKNOWN", "USD_API_EQUIV"]}}
    common = {"schema_version": {"const": SCHEMA_VERSION},
              "product_loop_id": {"type": "string", "enum": list(PRODUCT_LOOP_IDS)}}
    receipt_properties = {
        **common, "record_type": {"const": "receipt"},
        "receipt_id": {"type": "string", "pattern": IDENTITY.pattern},
        "provider": {"type": "string", "pattern": NAME.pattern},
        "currency": currency,
        "occurred_at": timestamp, "settled_at": nullable_timestamp,
        "verification_state": {"type": "string", "enum": list(VERIFICATION_STATES)},
        "revenue_class": {"oneOf": [
            {"type": "string", "enum": list(REVENUE_CLASSES)}, {"type": "null"},
        ]},
        "evidence_refs": evidence,
        "components": {"type": "array", "minItems": 1, "uniqueItems": True,
                       "items": {"$ref": "#/$defs/component"}},
    }
    coverage_properties = {
        **common, "record_type": {"const": "coverage"},
        "source_id": {"type": "string", "pattern": NAME.pattern},
        "projection": {"type": "string", "enum": ["historical", "trailing", "as_of"]},
        "window_start": nullable_timestamp, "window_end": timestamp,
        "coverage_state": {"type": "string", "enum": list(COVERAGE_STATES)},
        "reason": {"oneOf": [{"type": "string", "enum": list(GAP_REASONS)}, {"type": "null"}]},
        "covered_categories": {"type": "array", "uniqueItems": True,
                               "items": {"type": "string", "enum": list(COVERED_CATEGORIES)}},
        "observed_at": timestamp, "evidence_refs": evidence,
    }
    receipt_contains = lambda categories: {
        "properties": {"components": {"contains": {
            "type": "object", "properties": {
                "category": {"enum": list(categories)},
            }, "required": ["category"],
        }}},
        "required": ["components"],
    }
    receipt_rules = [
        {"if": receipt_contains(EXCLUDED_CATEGORIES),
         "then": {"properties": {"components": {"maxItems": 1}}}},
        {"if": receipt_contains(COUNTED_CATEGORIES), "then": {"properties": {
            "verification_state": {"const": "verified"}, "settled_at": timestamp,
        }}},
        {"if": receipt_contains(("pending_revenue",)), "then": {"properties": {
            "verification_state": {"const": "pending"}, "settled_at": {"type": "null"},
            "revenue_class": {"type": "string", "enum": list(REVENUE_CLASSES)},
        }}},
        {"if": receipt_contains((REVENUE,)), "then": {"properties": {
            "revenue_class": {"type": "string", "enum": list(REVENUE_CLASSES)},
        }}},
    ]
    receipt_rules.extend({
        "properties": {"components": {
            "contains": {"type": "object", "properties": {
                "category": {"const": category},
            }, "required": ["category"]},
            "minContains": 0, "maxContains": 1,
        }},
    } for category in ALL_CATEGORIES)
    coverage_rules = [
        {"if": {"properties": {"projection": {"const": "trailing"}},
                "required": ["projection"]},
         "then": {"properties": {"window_start": timestamp}},
         "else": {"properties": {"window_start": {"type": "null"}}}},
        {"if": {"properties": {"coverage_state": {"const": "complete"}},
                "required": ["coverage_state"]},
         "then": {"properties": {"reason": {"type": "null"}}},
         "else": {"properties": {"reason": {"type": "string", "enum": list(GAP_REASONS)}}}},
    ]
    balance_properties = {
        "schema_version": {"const": SCHEMA_VERSION}, "record_type": {"const": "liquid_balance"},
        "snapshot_id": {"type": "string", "pattern": IDENTITY.pattern},
        "account_id": {"type": "string", "pattern": IDENTITY.pattern},
        "provider": {"type": "string", "pattern": NAME.pattern}, "currency": currency,
        "amount": {"type": "string", "pattern": AMOUNT.pattern}, "observed_at": timestamp,
        "verification_state": {"type": "string", "enum": ["verified", "unverified"]},
        "evidence_refs": evidence,
    }
    subscription_properties = {
        **common, "record_type": {"const": "subscription_snapshot"},
        "snapshot_id": {"type": "string", "pattern": IDENTITY.pattern},
        "subscription_id": {"type": "string", "pattern": IDENTITY.pattern},
        "provider": {"type": "string", "pattern": NAME.pattern}, "currency": currency,
        "normalized_monthly_amount": {"type": "string", "pattern": AMOUNT.pattern},
        "normalization_basis": {"const": "provider_monthly"},
        "status": {"type": "string", "enum": ["active", "inactive"]},
        "observed_at": timestamp,
        "verification_state": {"type": "string", "enum": ["verified", "unverified"]},
        "evidence_refs": evidence,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": SCHEMA_VERSION,
        "x-lm-validation-contract": {
            "json_schema_scope": "structural_only",
            "canonical_validator": "skills.cfo.economic_attribution.validate_record",
            "semantic_rules_ref": "x-lm-semantic-rules",
        },
        "x-lm-semantic-rules": [
            "receipt.settled_at >= receipt.occurred_at",
            "coverage.window_start < coverage.window_end",
        ],
        "title": "Life Manager CFO economic attribution record", "oneOf": [
            {"$ref": "#/$defs/receipt"}, {"$ref": "#/$defs/coverage"},
            {"$ref": "#/$defs/liquid_balance"}, {"$ref": "#/$defs/subscription_snapshot"},
        ], "$defs": {
            "component": {"type": "object", "additionalProperties": False,
                          "required": ["category", "amount"], "properties": {
                              "category": {"type": "string", "enum": list(ALL_CATEGORIES)},
                              "amount": {"type": "string", "pattern": POSITIVE_AMOUNT.pattern},
                          }},
            "receipt": {"type": "object", "additionalProperties": False,
                        "required": list(RECEIPT_REQUIRED), "properties": receipt_properties,
                        "allOf": receipt_rules},
            "coverage": {"type": "object", "additionalProperties": False,
                         "required": list(COVERAGE_REQUIRED), "properties": coverage_properties,
                         "allOf": coverage_rules},
            "liquid_balance": {"type": "object", "additionalProperties": False,
                               "required": list(BALANCE_REQUIRED), "properties": balance_properties},
            "subscription_snapshot": {
                "type": "object", "additionalProperties": False,
                "required": list(SUBSCRIPTION_REQUIRED), "properties": subscription_properties,
                "allOf": [{
                    "if": {"properties": {"status": {"const": "active"}}, "required": ["status"]},
                    "then": {"properties": {
                        "normalized_monthly_amount": {"type": "string",
                                                      "pattern": POSITIVE_AMOUNT.pattern},
                    }},
                }],
            },
        },
    }


def render_schema() -> bytes:
    return (json.dumps(economic_attribution_schema(), indent=2, ensure_ascii=False) + "\n").encode()


if __name__ == "__main__":
    SCHEMA_PATH.write_bytes(render_schema())
