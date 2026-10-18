"""Pure, fail-closed adapter for official paid model/tool/browser/infra cost.

The input is an already-read, sanitized provider billing readback.  This module deliberately
does not know credentials, provider clients, browser state, runner telemetry, or quote APIs.
Only an explicitly official and paid invoice/receipt with an explicit product-loop allocation is
converted to the B0 receipt contract.  An agent estimate, provider quote, or personal
subscription remains a coverage gap rather than becoming a zero-cost fact.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, DecimalException, localcontext
from typing import Any

from skills.cfo import economic_attribution as contract


ACTUAL_COST_CATEGORIES = ("model_cost", "tool_cost", "browser_cost", "infra_cost")
OFFICIAL_DOCUMENT_TYPES = {"invoice", "paid_receipt"}
OFFICIAL_SOURCE_TYPES = {
    "invoice": "official_invoice",
    "paid_receipt": "official_paid_receipt",
}
ACTUAL_BASES = {"official_invoice", "official_paid_receipt", "actual_billed"}
REASON_PRIORITY = (
    "stale_readback", "unsupported_currency", "unverified_receipt", "read_failed",
    "credential_missing", "missing_coverage", "missing_category",
)
MAX_B0_AMOUNT_INTEGER_DIGITS = 26
MAX_B0_AMOUNT_SIGNIFICANT_DIGITS = 28
_UNORDERED_PATHS = frozenset({
    ("sources",),
    ("sources", "[]", "product_loop_ids"),
    ("documents",),
    ("documents", "[]", "line_items"),
    ("documents", "[]", "line_items", "[]", "allocations"),
    ("invoices",),
    ("invoices", "[]", "line_items"),
    ("invoices", "[]", "line_items", "[]", "allocations"),
    ("paid_receipts",),
    ("paid_receipts", "[]", "line_items"),
    ("paid_receipts", "[]", "line_items", "[]", "allocations"),
    ("job_joins",),
    ("provider_pagination", "pages"),
    ("provider_pagination", "pages", "[]", "document_ids"),
    ("document_ids",),
    ("product_loop_ids",),
    ("estimates",),
    ("estimates", "[]", "product_loop_ids"),
    ("quotes",),
    ("quotes", "[]", "product_loop_ids"),
    ("personal_subscriptions",),
    ("personal_subscriptions", "[]", "product_loop_ids"),
})
_UNORDERED_ID_FIELDS = {
    "sources": ("provider",),
    "documents": ("provider", "document_type", "invoice_id", "receipt_id"),
    "invoices": ("provider", "document_type", "invoice_id", "receipt_id"),
    "paid_receipts": ("provider", "document_type", "invoice_id", "receipt_id"),
    "job_joins": ("provider", "job_id"),
    "line_items": ("line_item_id",),
    "allocations": ("allocation_id",),
    "pages": ("provider", "page"),
    "document_ids": (),
    "product_loop_ids": (),
    "estimates": ("provider", "product_loop_id", "product_loop_ids"),
    "quotes": ("provider", "product_loop_id", "product_loop_ids"),
    "personal_subscriptions": ("provider", "product_loop_id", "product_loop_ids"),
}


def _json_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _stable_identity(path: tuple[str, ...], value: Any) -> tuple[str, str]:
    collection = path[-1] if path else ""
    identity = {}
    if isinstance(value, dict):
        identity = {
            field: value[field]
            for field in _UNORDERED_ID_FIELDS.get(collection, ())
            if field in value
        }
    return _json_key(path), _json_key(identity if identity else value)


def _canonical(value: Any) -> str:
    """Canonicalize known set-like collections while preserving unknown list order."""
    def normalize(item: Any, path: tuple[str, ...] = ()) -> Any:
        if isinstance(item, dict):
            return {
                key: normalize(child, (*path, key))
                for key, child in item.items()
            }
        if isinstance(item, list):
            normalized = [normalize(child, (*path, "[]")) for child in item]
            if path not in _UNORDERED_PATHS:
                return normalized
            unique = {}
            for child in normalized:
                unique.setdefault(_json_key(child), child)
            return [
                child for _digest, child in sorted(
                    unique.items(),
                    key=lambda pair: (_stable_identity(path, pair[1]), pair[0]),
                )
            ]
        return item

    return _json_key(normalize(value))


def _digest(value: Any) -> str:
    try:
        encoded = _canonical(value).encode("utf-8")
    except (TypeError, ValueError):
        encoded = b"invalid-readback"
    return hashlib.sha256(encoded).hexdigest()


def _evidence(provider: str, digest: str) -> str:
    return f"lm-actual-cost://{provider}/readback/{digest}"


def _instant(value: Any) -> str | None:
    if not isinstance(value, str) or not contract.RFC3339.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError):
        return None


def _canonical_decimal_text(amount: Decimal) -> str:
    text = format(amount, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _amount(value: Any) -> str | None:
    if not isinstance(value, str) or not contract.POSITIVE_AMOUNT.fullmatch(value):
        return None
    integer_part, _, fractional_part = value.partition(".")
    if len(integer_part) > MAX_B0_AMOUNT_INTEGER_DIGITS:
        return None
    significant_digits = (integer_part + fractional_part).lstrip("0").rstrip("0")
    if len(significant_digits) > MAX_B0_AMOUNT_SIGNIFICANT_DIGITS:
        return None
    try:
        parsed = Decimal(value)
        if not parsed.is_finite() or parsed <= 0:
            return None
        exact = _canonical_decimal_text(parsed)
        with localcontext() as context:
            context.prec = MAX_B0_AMOUNT_SIGNIFICANT_DIGITS
            normalized = _canonical_decimal_text(parsed.normalize())
    except (DecimalException, ArithmeticError):
        return None
    if normalized != exact:
        return None
    return normalized


def _provider(value: Any) -> str | None:
    return value if isinstance(value, str) and contract.NAME.fullmatch(value) else None


def _loop_id(value: Any) -> str | None:
    return value if isinstance(value, str) and value in contract.PRODUCT_LOOP_IDS else None


def _currency(value: Any) -> str | None:
    if not isinstance(value, str) or not contract.CURRENCY.fullmatch(value):
        return None
    if value in {"UNKNOWN", "USD_API_EQUIV"}:
        return None
    return value


def _reason(value: Any, fallback: str = "unverified_receipt") -> str:
    return value if value in contract.GAP_REASONS else fallback


def _choose_reason(reasons: set[str], fallback: str = "missing_coverage") -> str:
    for candidate in REASON_PRIORITY:
        if candidate in reasons:
            return candidate
    return fallback


def _source_id(provider: str) -> str:
    return f"actual-cost-{provider}"


def _receipt(*, provider: str, document_id: str, document_type: str,
             line_id: str, allocation_id: str, loop_id: str, currency: str,
             occurred_at: str, settled_at: str, category: str, amount: str,
             evidence: str) -> dict:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "receipt",
        "receipt_id": (
            f"{provider}:actual-cost:{document_type}:{document_id}:line:{line_id}:"
            f"allocation:{allocation_id}"
        ),
        "product_loop_id": loop_id,
        "provider": provider,
        "currency": currency,
        "occurred_at": occurred_at,
        "settled_at": settled_at,
        "verification_state": "verified",
        "revenue_class": None,
        "evidence_refs": [evidence],
        "components": [{"category": category, "amount": amount}],
    })


def _coverage(*, loop_id: str, source_id: str, projection: str, start: str | None,
              end: str, state: str, reason: str | None, categories: set[str],
              observed_at: str, evidence: str) -> dict:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": loop_id,
        "source_id": source_id,
        "projection": projection,
        "window_start": start,
        "window_end": end,
        "coverage_state": state,
        "reason": reason,
        "covered_categories": sorted(categories),
        "observed_at": observed_at,
        "evidence_refs": [evidence],
    })


def _window_inputs(snapshot_at: Any, trailing_start: Any) -> tuple[str, str]:
    end = _instant(snapshot_at)
    start = _instant(trailing_start)
    if end is None or start is None or start >= end:
        raise ValueError("invalid_projection_window")
    return end, start


def _readback_state(payload: dict, *, end: str, start: str) -> tuple[str, dict[str, str]]:
    readback = payload.get("readback")
    if not isinstance(readback, dict) or readback.get("kind") != "official_billing_readback":
        return end, {"historical": "read_failed", "trailing": "read_failed"}

    observed_at = _instant(readback.get("observed_at"))
    if observed_at is None:
        return end, {"historical": "read_failed", "trailing": "read_failed"}
    reasons: dict[str, str] = {}
    fatal_window_shape = False
    for projection, expected_start in (("historical", None), ("trailing", start)):
        query = readback.get(projection)
        if not isinstance(query, dict) or query.get("complete") is not True:
            reasons[projection] = _reason(
                query.get("reason") if isinstance(query, dict) else None,
                "read_failed",
            )
            continue
        raw_start = query.get("window_start")
        query_start = None if raw_start is None else _instant(raw_start)
        if raw_start is not None and query_start is None:
            reasons[projection] = "read_failed"
            fatal_window_shape |= projection == "historical"
            continue
        query_end = _instant(query.get("window_end"))
        if query_start != expected_start or query_end != end or observed_at != end:
            reasons[projection] = "stale_readback"
    if observed_at != end:
        reasons = {projection: "stale_readback" for projection in ("historical", "trailing")}
    elif fatal_window_shape:
        reasons = {projection: "read_failed" for projection in ("historical", "trailing")}
    return observed_at, reasons


def _source_rows(payload: dict) -> tuple[dict[str, dict[str, Any]], set[str]]:
    raw_sources = payload.get("sources")
    if raw_sources is None:
        return {}, set()
    if not isinstance(raw_sources, list):
        return {}, {"read_failed"}

    sources: dict[str, dict[str, Any]] = {}
    failures: set[str] = set()
    for raw in raw_sources:
        if not isinstance(raw, dict):
            failures.add("unverified_receipt")
            continue
        provider = _provider(raw.get("provider"))
        if provider is None:
            failures.add("unverified_receipt")
            continue
        raw_loops = raw.get("product_loop_ids", [])
        loops: set[str] = set()
        if not isinstance(raw_loops, list):
            failures.add("unverified_receipt")
        else:
            for loop in raw_loops:
                normalized_loop = _loop_id(loop)
                if normalized_loop is None:
                    failures.add("unverified_receipt")
                else:
                    loops.add(normalized_loop)
        status = raw.get("status")
        source_reason = None
        if status != "available":
            default_reason = "unverified_receipt"
            if isinstance(status, str):
                default_reason = {
                    "missing": "credential_missing",
                    "credential_missing": "credential_missing",
                    "read_failed": "read_failed",
                    "stale": "stale_readback",
                }.get(status, default_reason)
            source_reason = _reason(raw.get("reason"), default_reason)
        value = {
            "loops": loops,
            "status": status,
            "reason": source_reason,
            "conflict": False,
        }
        prior = sources.get(provider)
        if prior is None:
            sources[provider] = value
        elif prior != value:
            prior["conflict"] = True
            prior["reason"] = "unverified_receipt"
    return sources, failures


def _document_rows(payload: dict) -> tuple[list[dict], str | None]:
    if "documents" in payload:
        rows = payload.get("documents")
    elif "invoices" in payload:
        rows = payload.get("invoices")
    elif "paid_receipts" in payload:
        rows = payload.get("paid_receipts")
    else:
        return [], None
    if not isinstance(rows, list):
        return [], "read_failed"
    return [row for row in rows if isinstance(row, dict)], (
        "unverified_receipt" if any(not isinstance(row, dict) for row in rows) else None
    )


def _job_index(payload: dict) -> tuple[dict[tuple[str, str], dict], set[tuple[str, str]]]:
    rows = payload.get("job_joins", [])
    if not isinstance(rows, list):
        return {}, {("blockrun", "*")}
    index: dict[tuple[str, str], dict] = {}
    conflicts: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            conflicts.add(("blockrun", "*"))
            continue
        if row.get("join_type") == "scope_query":
            continue
        provider = _provider(row.get("provider"))
        job_id = row.get("job_id")
        loop_id = _loop_id(row.get("product_loop_id"))
        if provider is None or not isinstance(job_id, str) or not job_id or loop_id is None:
            conflicts.add(("blockrun", job_id if isinstance(job_id, str) else "*"))
            continue
        key = (provider, job_id)
        prior = index.get(key)
        if prior is not None and prior != row:
            conflicts.add(key)
        else:
            index[key] = row
    return index, conflicts


def _excluded_failures(payload: dict, sources: dict[str, dict[str, Any]]) -> dict[tuple[str, str, str], set[str]]:
    """Keep non-actual producer rows visible as gaps without treating them as receipts."""
    failures: dict[tuple[str, str, str], set[str]] = {}

    def add_failure(provider: str, loop_id: str) -> None:
        source_id = _source_id(provider)
        failures.setdefault((provider, loop_id, source_id), set()).add("missing_coverage")

    def explicit_loops(row: dict) -> tuple[set[str], bool]:
        raw = row.get("product_loop_ids")
        if raw is None and "product_loop_id" in row:
            raw = [row.get("product_loop_id")]
        if raw is None:
            return set(), False
        if not isinstance(raw, list):
            return set(), True
        loops, malformed = set(), False
        for value in raw:
            loop_id = _loop_id(value)
            if loop_id is None:
                malformed = True
            else:
                loops.add(loop_id)
        return loops, malformed

    for field in ("estimates", "quotes", "personal_subscriptions"):
        rows = payload.get(field)
        if rows is None:
            continue
        if not isinstance(rows, list):
            sources.setdefault("exclusions", {
                "loops": set(), "status": "available", "reason": None, "conflict": False,
            })["loops"].add("cfo")
            add_failure("exclusions", "cfo")
            continue
        for row in rows:
            if not isinstance(row, dict):
                sources.setdefault("exclusions", {
                    "loops": set(), "status": "available", "reason": None, "conflict": False,
                })["loops"].add("cfo")
                add_failure("exclusions", "cfo")
                continue
            provider = _provider(row.get("provider"))
            loops, malformed = explicit_loops(row)
            source = sources.get(provider) if provider is not None else None
            source_loops = set(source.get("loops", set())) if source is not None else set()
            if provider is not None and source_loops:
                target_provider, target_loops = provider, source_loops
            elif provider is not None and loops and not malformed:
                target_provider, target_loops = provider, loops
                sources.setdefault(provider, {
                    "loops": set(), "status": "available", "reason": None, "conflict": False,
                })["loops"].update(loops)
            else:
                target_provider, target_loops = "exclusions", {"cfo"}
                sources.setdefault("exclusions", {
                    "loops": set(), "status": "available", "reason": None, "conflict": False,
                })["loops"].add("cfo")
            for loop_id in target_loops:
                add_failure(target_provider, loop_id)
            if malformed:
                sources.setdefault("exclusions", {
                    "loops": set(), "status": "available", "reason": None, "conflict": False,
                })["loops"].add("cfo")
                add_failure("exclusions", "cfo")
    return failures


def _document_identity(row: dict) -> tuple[str, str, str] | None:
    provider = _provider(row.get("provider"))
    document_type = row.get("document_type")
    if not isinstance(document_type, str):
        return None
    document_id = row.get("invoice_id") if document_type == "invoice" else row.get("receipt_id")
    if (provider is None or document_type not in OFFICIAL_DOCUMENT_TYPES
            or not isinstance(document_id, str) or not contract.IDENTITY.fullmatch(document_id)):
        return None
    return provider, document_type, document_id


def _document_rows_deduped(rows: list[dict]) -> tuple[list[dict], set[tuple[str, str]], set[str]]:
    unique: dict[tuple[str, str, str], tuple[str, dict]] = {}
    conflicts: set[tuple[str, str]] = set()
    failures: set[str] = set()
    for row in rows:
        identity = _document_identity(row)
        if identity is None:
            failures.add("unverified_receipt")
            continue
        provider, document_type, document_id = identity
        key = (provider, document_type, document_id)
        try:
            digest = _canonical(row)
        except (TypeError, ValueError):
            failures.add("unverified_receipt")
            conflicts.add((provider, document_id))
            continue
        prior = unique.get(key)
        if prior is None:
            unique[key] = (digest, row)
        elif prior[0] != digest:
            conflicts.add((provider, document_id))
    return [value[1] for key, value in unique.items() if (key[0], key[2]) not in conflicts], conflicts, failures


def _job_matches(*, provider: str, job_id: Any, loop_id: str, document_id: str,
                 line_id: str, jobs: dict[tuple[str, str], dict], conflicts: set[tuple[str, str]]) -> bool:
    if provider != "blockrun":
        return True
    if not isinstance(job_id, str) or not job_id:
        return False
    key = (provider, job_id)
    if key in conflicts or (provider, "*") in conflicts:
        return False
    row = jobs.get(key)
    if not isinstance(row, dict) or row.get("product_loop_id") != loop_id:
        return False
    if not isinstance(row.get("status"), str) or row.get("status") not in {"completed", "settled", "paid"}:
        return False
    if row.get("document_id") is not None and row.get("document_id") != document_id:
        return False
    if row.get("line_item_id") is not None and row.get("line_item_id") != line_id:
        return False
    return True


def _parse_document(row: dict, *, end: str, payload_digest: str,
                    jobs: dict[tuple[str, str], dict], job_conflicts: set[tuple[str, str]],
                    source_loops: set[str]) -> tuple[list[dict], set[tuple[str, str]], set[tuple[str, str, str]]]:
    """Return receipts, (loop, reason) failures, and source groups seen."""
    identity = _document_identity(row)
    if identity is None:
        return [], {(loop, "unverified_receipt") for loop in source_loops}, set()
    provider, document_type, document_id = identity
    source_id = _source_id(provider)
    evidence = _evidence(provider, payload_digest)
    failures: set[tuple[str, str]] = set()
    seen_groups: set[tuple[str, str, str]] = set()

    if (row.get("official") is not True
            or row.get("source_type") != OFFICIAL_SOURCE_TYPES[document_type]
            or not isinstance(row.get("status"), str)
            or row.get("status") not in {"paid", "settled"}
            or (provider == "blockrun" and document_type != "paid_receipt")):
        return [], {(loop, "unverified_receipt") for loop in source_loops}, set()
    currency = _currency(row.get("currency"))
    if currency is None:
        return [], {(loop, "unsupported_currency") for loop in source_loops}, set()
    period_start = _instant(row.get("billing_period_start"))
    period_end = _instant(row.get("billing_period_end"))
    paid_at = _instant(row.get("paid_at"))
    if (period_start is None or period_end is None or paid_at is None
            or period_start >= period_end or period_end > end or paid_at > end):
        return [], {(loop, "unverified_receipt") for loop in source_loops}, set()
    line_items = row.get("line_items")
    if not isinstance(line_items, list) or not line_items:
        return [], {(loop, "missing_coverage") for loop in source_loops}, set()

    unique_lines: dict[str, tuple[str, dict]] = {}
    line_conflicts: set[str] = set()
    for line in line_items:
        if (not isinstance(line, dict)
                or not isinstance(line.get("line_item_id"), str)
                or not contract.IDENTITY.fullmatch(line.get("line_item_id"))):
            failures.update((loop, "unverified_receipt") for loop in source_loops)
            continue
        line_id = line["line_item_id"]
        try:
            line_digest = _canonical(line)
        except (TypeError, ValueError):
            line_conflicts.add(line_id)
            continue
        prior = unique_lines.get(line_id)
        if prior is None:
            unique_lines[line_id] = (line_digest, line)
        elif prior[0] != line_digest:
            line_conflicts.add(line_id)

    result: list[dict] = []
    for line_id, (_line_digest, line) in unique_lines.items():
        if line_id in line_conflicts:
            failures.update((loop, "unverified_receipt") for loop in source_loops)
            continue
        category = line.get("category")
        occurred_at = _instant(line.get("occurred_at"))
        amount = _amount(line.get("amount"))
        basis = line.get("basis")
        if (category not in ACTUAL_COST_CATEGORIES or occurred_at is None or amount is None
                or not isinstance(basis, str) or basis not in ACTUAL_BASES
                or occurred_at < period_start or occurred_at >= period_end
                or paid_at < occurred_at):
            failures.update((loop, "unsupported_currency" if currency is None else "unverified_receipt")
                            for loop in source_loops)
            continue
        allocations = line.get("allocations")
        if not isinstance(allocations, list) or not allocations:
            failures.update((loop, "missing_coverage") for loop in source_loops)
            continue
        unique_allocations: dict[str, tuple[str, dict]] = {}
        allocation_conflicts: set[str] = set()
        for allocation in allocations:
            if not isinstance(allocation, dict):
                failures.update((loop, "unverified_receipt") for loop in source_loops)
                continue
            allocation_id = allocation.get("allocation_id")
            if not isinstance(allocation_id, str) or not contract.IDENTITY.fullmatch(allocation_id):
                failures.update((loop, "unverified_receipt") for loop in source_loops)
                continue
            try:
                allocation_digest = _canonical(allocation)
            except (TypeError, ValueError):
                allocation_conflicts.add(allocation_id)
                continue
            prior = unique_allocations.get(allocation_id)
            if prior is None:
                unique_allocations[allocation_id] = (allocation_digest, allocation)
            elif prior[0] != allocation_digest:
                allocation_conflicts.add(allocation_id)
        if allocation_conflicts:
            failures.update((loop, "unverified_receipt") for loop in source_loops)
            continue

        allocation_values: list[str] = []
        eligible: list[tuple[str, str, str]] = []
        for allocation_id, (_, allocation) in unique_allocations.items():
            allocation_amount = _amount(allocation.get("amount"))
            loop_id = _loop_id(allocation.get("product_loop_id"))
            if allocation_amount is None:
                failures.update((loop, "unverified_receipt") for loop in source_loops)
                continue
            allocation_values.append(allocation_amount)
            if (allocation.get("scope") == "personal"
                    or allocation.get("allocation_status") == "unallocated"):
                if loop_id is not None:
                    failures.add((loop_id, "missing_coverage"))
                else:
                    failures.update((loop, "missing_coverage") for loop in source_loops)
                continue
            if loop_id is None:
                failures.update((loop, "unverified_receipt") for loop in source_loops)
                continue
            eligible.append((allocation_id, loop_id, allocation_amount))
        with localcontext() as context:
            context.prec = max(
                MAX_B0_AMOUNT_SIGNIFICANT_DIGITS,
                max(
                    len(value.replace(".", ""))
                    + len(str(max(1, len(allocation_values))))
                    + 1
                    for value in (amount, *allocation_values)
                ),
            )
            allocation_total = sum(
                (Decimal(value) for value in allocation_values), Decimal(0)
            )
            line_total = Decimal(amount)
        if allocation_total != line_total:
            failures.update((loop, "unverified_receipt") for loop in source_loops)
            continue
        for allocation_id, loop_id, allocation_amount in eligible:
            seen_groups.add((provider, loop_id, source_id))
            allocation = unique_allocations[allocation_id][1]
            if not _job_matches(
                provider=provider,
                job_id=allocation.get("job_id"),
                loop_id=loop_id,
                document_id=document_id,
                line_id=line_id,
                jobs=jobs,
                conflicts=job_conflicts,
            ):
                failures.add((loop_id, "unverified_receipt"))
                continue
            result.append(_receipt(
                provider=provider, document_id=document_id, document_type=document_type,
                line_id=line_id, allocation_id=allocation_id, loop_id=loop_id,
                currency=currency, occurred_at=occurred_at, settled_at=paid_at,
                category=category, amount=allocation_amount, evidence=evidence,
            ))
    if not result and not failures:
        failures.update((loop, "missing_coverage") for loop in source_loops)
    return result, failures, seen_groups


def _query_ids(value, *, nonempty=False):
    return (isinstance(value,list) and (bool(value) or not nonempty)
        and all(isinstance(item,str) and item for item in value) and len(set(value))==len(value))


def _execution_ref_triples(value):
    fields=('execution_owner_id','run_id','occurrence_id')
    if not isinstance(value,list) or not value:raise ValueError('cost_query_execution_ref_missing')
    triples=set()
    for row in value:
        if (not isinstance(row,dict) or set(row)!=set(fields)
                or not all(isinstance(row[k],str) and contract.IDENTITY.fullmatch(row[k]) for k in fields)
                or not row['occurrence_id'].startswith(row['execution_owner_id']+':')):
            raise ValueError('cost_query_execution_ref_invalid')
        triple=tuple(row[k] for k in fields)
        if triple in triples:raise ValueError('cost_query_execution_ref_invalid')
        triples.add(triple)
    return triples


def paid_charge_identity(document,line,allocation):
    identity=_document_identity(document)
    if identity is None:return None
    provider,kind,document_id=identity;invoice=document.get('invoice_id')
    if isinstance(invoice,str) and invoice:
        if not contract.IDENTITY.fullmatch(invoice):return None
        kind,document_id='invoice',invoice
    ids=(line.get('line_item_id'),allocation.get('allocation_id'))
    if not all(isinstance(value,str) and contract.IDENTITY.fullmatch(value) for value in ids):return None
    return provider,kind,document_id,*ids


def _cost_scope_key(scope):
    return (scope.get('owner_id'),scope.get('mode'),scope.get('paper'),tuple(scope['order_ids']),
        _instant(scope.get('period_start')),_instant(scope.get('period_end')),scope.get('scope_kind','order_pair'))


def _same_cost_scope(left,right):
    return (type(left.get('paper')) is bool and _query_ids(left.get('order_ids'))
        and _query_ids(left.get('source_receipt_ids'),nonempty=True)
        and left.get('product_loop_id')==right.get('product_loop_id')
        and _cost_scope_key(left)==_cost_scope_key(right)
        and set(left['source_receipt_ids'])==set(right['source_receipt_ids']))


def _inventory_cost_scope(inventory,target,snapshot_at):
    invalid='cost_query_inventory_invalid'
    if (not isinstance(inventory,dict) or type(inventory.get('schema_version')) is not int or inventory['schema_version']!=1
            or inventory.get('gaps')!=[] or not isinstance(inventory.get('scopes'),list)):
        raise ValueError(invalid)
    mode=target.get('mode');owner=target.get('owner_id');kind=target.get('scope_kind','order_pair')
    start,finish=_instant(target.get('period_start')),_instant(target.get('period_end'))
    observed=_instant(inventory.get('observed_at'))
    if (mode not in ('paper','live') or owner!=f'alpaca-investment-{mode}' or target.get('paper') is not (mode=='paper')
            or inventory.get('beneficiary_owner_id')!=owner or kind not in ('order_pair','owner_period')
            or not _query_ids(target.get('order_ids'),nonempty=kind=='order_pair')
            or kind=='owner_period' and target['order_ids']!=[]
            or not _query_ids(target.get('source_receipt_ids'),nonempty=True)
            or None in (start,finish,observed) or not start<finish<=observed<=snapshot_at):
        raise ValueError(invalid)
    matches=[row for row in inventory['scopes'] if isinstance(row,dict) and _query_ids(row.get('order_ids'))
        and _cost_scope_key(row)==_cost_scope_key(target)]
    if len(matches)!=1:raise ValueError('cost_query_inventory_scope_missing')
    scope=matches[0]
    if (scope.get('scope_kind') not in ('order_pair','owner_period') or scope.get('paper') is not (mode=='paper')
            or not _query_ids(scope.get('source_receipt_ids'),nonempty=True)
            or not set(scope['source_receipt_ids'])<=set(target['source_receipt_ids'])
            or not _query_ids(scope.get('evidence_refs'),nonempty=True)
            or not isinstance(scope.get('gaps'),list)):
        raise ValueError(invalid)
    allowed={'history_coverage_unverified','shared_attribution_unproven'}
    if any(not isinstance(g,dict) or g.get('reason') not in allowed for g in scope['gaps']):raise ValueError('cost_query_inventory_gap')
    raw_refs=scope.get('execution_refs');refs=set();events=set();releases=set()
    ref_fields={'execution_owner_id','run_id','occurrence_id','release_sha','loaded_argv_sha256','loaded_env_sha256','start_event_id','terminal_event_id'}
    if not isinstance(raw_refs,list) or not raw_refs:raise ValueError(invalid)
    for row in raw_refs:
        if not isinstance(row,dict) or set(row)!=ref_fields:raise ValueError(invalid)
        refs.update(_execution_ref_triples([{k:row[k] for k in ('execution_owner_id','run_id','occurrence_id')}]))
        for key,length in (('release_sha',40),('loaded_argv_sha256',64),('loaded_env_sha256',64)):
            if not isinstance(row[key],str) or re.fullmatch('[a-f0-9]{'+str(length)+'}',row[key]) is None:raise ValueError(invalid)
        for key in ('start_event_id','terminal_event_id'):
            if not isinstance(row[key],str) or re.fullmatch('[a-f0-9]{24,64}',row[key]) is None or row[key] in events:raise ValueError(invalid)
            events.add(row[key])
        releases.add(row['release_sha'])
    if len(refs)!=len(raw_refs):raise ValueError(invalid)
    reads=inventory.get('input_reads');limits=inventory.get('read_limits')
    if (not isinstance(reads,dict) or not isinstance(limits,dict)
            or any(type(limits.get(k)) is not int or limits[k]<(0 if k=='runtime_archives_per_owner' else 1)
                   for k in ('owners','admission_rows_per_owner','runtime_archives_per_owner'))
            or len(reads)>limits['owners']):raise ValueError(invalid)
    for executor in {r[0] for r in refs}:
        data=reads.get(executor)
        if not isinstance(data,dict) or any(not isinstance(data.get(k),dict) or data[k].get('status')!='ok' for k in ('runtime','ledger','admission')):
            raise ValueError('cost_query_history_unverified')
        runtime=data['runtime'];first,last=_instant(runtime.get('first_event_at')),_instant(runtime.get('last_event_at'))
        if (None in (first,last) or not first<=start<finish<=last<=observed
                or type(runtime.get('archives_available')) is not int or not 0<=runtime['archives_available']<=limits['runtime_archives_per_owner']
                or any(type(data[k].get('row_count')) is not int or data[k]['row_count']<1 for k in ('runtime','ledger','admission'))
                or runtime['row_count']<2*sum(r[0]==executor for r in refs)
                or not len({r[2] for r in refs if r[0]==executor})<=data['admission']['row_count']<=limits['admission_rows_per_owner']):
            raise ValueError('cost_query_history_unverified')
    bindings=scope.get('known_paid_bindings')
    if not isinstance(bindings,list):raise ValueError(invalid)
    known=set()
    for binding in bindings:
        if (not isinstance(binding,dict) or binding.get('owner_id')!=owner or binding.get('mode')!=mode
                or binding.get('paper') is not (mode=='paper') or binding.get('order_ids')!=scope['order_ids']
                or _instant(binding.get('period_start'))!=start or _instant(binding.get('period_end'))!=finish
                or not isinstance(binding.get('receipt_id'),str) or not binding['receipt_id']
                or not _query_ids(binding.get('evidence_refs'),nonempty=True)
                or not isinstance(binding.get('charge_identity'),list) or len(binding['charge_identity'])!=5
                or not all(isinstance(v,str) and v for v in binding['charge_identity'])):raise ValueError(invalid)
        known.add((binding.get('provider'),binding.get('billing_account_ref'),binding.get('category')))
    required={}
    if not isinstance(scope.get('required_sources'),list) or not scope['required_sources']:raise ValueError('cost_query_source_missing')
    for source in scope['required_sources']:
        if (not isinstance(source,dict) or _provider(source.get('provider')) is None
                or not isinstance(source.get('billing_account_ref'),str) or not source['billing_account_ref'].strip()
                or source.get('category') not in ACTUAL_COST_CATEGORIES
                or not _query_ids(source.get('execution_owner_ids')) or not _query_ids(source.get('release_refs'))
                or not _query_ids(source.get('evidence_refs'),nonempty=True)):raise ValueError(invalid)
        key=(source['provider'],source['billing_account_ref'],source['category'])
        owners=set(source['execution_owner_ids'])
        if key in required or not owners<={r[0] for r in refs} or not set(source['release_refs'])<=releases:
            raise ValueError(invalid)
        if (not owners or not source['release_refs']) and key not in known:raise ValueError(invalid)
        required[key]=owners or {owner}
    if not known<=set(required) or {k[2] for k in required}!=set(ACTUAL_COST_CATEGORIES):raise ValueError('cost_query_source_missing')
    for gap in scope['gaps']:
        if gap['reason']=='shared_attribution_unproven' and (gap.get('execution_owner_id')==owner
                or gap.get('execution_owner_id') not in {v for values in required.values() for v in values}):raise ValueError(invalid)
    return {'scope':scope,'required':required,'refs':refs,'covered':set(),'evidence_refs':set(scope['evidence_refs'])}


def validate_official_cost_queries(payload: Any, *, snapshot_at: str, paid_records,
                                   scope=None, expected_inventory=None) -> dict[str, Any]:
    """Normalize scoped billing facts, never money or complete cost coverage.

    Explicit independent inventory can prove source coverage for exact scopes.
    Observations alone never produce zero-money receipts or complete coverage.
    """
    result = {"observations": [], "rejections": [], "coverage_state": "gap",
              "reason": "source_inventory_unverified"}
    end = _instant(snapshot_at)
    readback = payload.get("readback") if isinstance(payload, dict) else None
    billing_at = _instant(readback.get("observed_at")) if isinstance(readback, dict) else None
    if (end is None or not isinstance(readback, dict)
            or readback.get("kind") != "official_billing_readback"
            or billing_at is None or billing_at > end):
        result["rejections"].append({"reason": "read_failed"})
        return result

    ids = _query_ids

    sources = payload.get("sources", [])
    scopes = readback.get("cost_scopes", [])
    pagination = payload.get("provider_pagination", {})
    pages = pagination.get("pages", []) if isinstance(pagination, dict) else None
    joins = payload.get("job_joins", [])
    if (_document_rows(payload)[1] is not None
            or not all(isinstance(value, list) for value in (sources, scopes, pages, joins))):
        result["rejections"].append({"reason": "read_failed"})
        return result
    candidates = []
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("queries", []), list):
            result["rejections"].append({"reason": "read_failed"})
            continue
        candidates.extend((source, query) for query in source.get("queries", []))
    seen = set()
    query_bodies = {}
    duplicate = set()
    for source, query in candidates:
        if isinstance(query, dict):
            key = (source.get("provider"), query.get("billing_account_ref"), query.get("query_id"))
            if all(isinstance(item, str) and item for item in (*key, query.get("scope_id"))):
                try:
                    body = _canonical({field: value for field, value in query.items() if field != "scope_id"})
                except (TypeError, ValueError):
                    duplicate.add(key)
                    continue
                scoped_key = (*key, query["scope_id"])
                if scoped_key in seen or (key in query_bodies and query_bodies[key] != body):
                    duplicate.add(key)
                seen.add(scoped_key)
                query_bodies[key] = body
    jobs, job_conflicts = _job_index(payload)
    paid_document_cache = {}

    def paid_document_rows(document):
        # Reuse paid validation on this exact document; IDs are not parsed by prefix.
        signature = _canonical(document)
        if signature not in paid_document_cache:
            parsed, failures, _groups = _parse_document(document, end=end, payload_digest=_digest(payload),
                jobs=jobs, job_conflicts=job_conflicts, source_loops={"investment"})
            paid_document_cache[signature] = (parsed if not failures and parsed
                and all(row in paid_records for row in parsed) else [])
        return paid_document_cache[signature]

    prepared={}
    if expected_inventory is not None:
        try:
            if not isinstance(expected_inventory,dict) or not isinstance(expected_inventory.get('scopes'),list) or not expected_inventory['scopes']:
                raise ValueError('cost_query_inventory_invalid')
            wanted=[scope] if scope is not None else [target for target in scopes if isinstance(target,dict)
                and ids(target.get('order_ids')) and any(isinstance(r,dict) and ids(r.get('order_ids'))
                    and _cost_scope_key(r)==_cost_scope_key(target) for r in expected_inventory['scopes'])]
            if scope is None and len(wanted)!=len(expected_inventory['scopes']):raise ValueError('cost_query_inventory_scope_missing')
            for target in wanted:
                if not isinstance(target,dict) or not isinstance(target.get('scope_id'),str) or not target['scope_id'] or target['scope_id'] in prepared:
                    raise ValueError('cost_query_inventory_invalid')
                prepared[target['scope_id']]=_inventory_cost_scope(expected_inventory,target,end)
        except (ValueError,KeyError,TypeError,AttributeError) as error:
            result['reason']=str(error) if str(error).startswith('cost_query_') else 'cost_query_inventory_invalid'
            result['rejections'].append({'reason':result['reason']})
            diagnostic=validate_official_cost_queries(payload,snapshot_at=snapshot_at,paid_records=paid_records,scope=scope)
            result['observations']=[{**row,'inventory_verification':'unverified'} for row in diagnostic['observations']]
            return result

    for source, query in candidates:
        if isinstance(query,dict) and isinstance(query.get('scope_id'),str):
            if scope is not None and query['scope_id']!=scope.get('scope_id'):continue
            if expected_inventory is not None and query['scope_id'] not in prepared:continue
        context = {"provider": source.get("provider")}
        try:
            if not isinstance(query, dict):
                raise ValueError
            context.update({key: query.get(key) for key in ("billing_account_ref", "query_id", "scope_id")})
            key = tuple(context.get(field) for field in ("provider", "billing_account_ref", "query_id"))
            if not all(isinstance(item, str) and item for item in (*key, query.get("scope_id"))) or key in duplicate:
                raise ValueError
            if (source.get("status") != "available" or _provider(key[0]) is None
                    or not ids(source.get("billing_account_refs"), nonempty=True)
                    or key[1] not in source["billing_account_refs"]
                    or query.get("official") is not True or query.get("source_type") != "official_billing_query"
                    or query.get("currency") != "USD" or query.get("complete") is not True
                    or not ids(query.get("covered_categories"), nonempty=True)
                    or not set(query["covered_categories"]) <= set(ACTUAL_COST_CATEGORIES)
                    or not ids(query.get("evidence_refs"), nonempty=True)
                    or any(query.get(field) != [] for field in ("pending_item_ids", "unbilled_item_ids", "unpaid_item_ids"))
                    or not ids(query.get("document_ids"))):
                raise ValueError
            times = {field: _instant(query.get(field)) for field in
                     ("window_start", "window_end", "observed_at", "finalized_through")}
            if (any(value is None for value in times.values())
                    or not times["window_start"] < times["window_end"] <= times["finalized_through"] <= times["observed_at"] <= billing_at):
                raise ValueError
            matching = [item for item in scopes if isinstance(item, dict) and item.get("scope_id") == query.get("scope_id")]
            if len(matching) != 1:
                raise ValueError
            target = matching[0]
            if scope is not None and target != scope:
                raise ValueError
            matching = [item for item in joins if isinstance(item, dict)
                        and (item.get("provider"), item.get("billing_account_ref"), item.get("query_id")) == key
                        and item.get("scope_id") == target["scope_id"]]
            mode = target.get("mode")
            structured = expected_inventory is not None or any("execution_refs" in item for item in matching)
            kind=target.get("scope_kind","order_pair")
            start, finish = _instant(target.get("period_start")), _instant(target.get("period_end"))
            if (target.get("product_loop_id") != "investment" or not isinstance(target.get("owner_id"), str)
                    or not target["owner_id"] or mode not in ("paper", "live", "shadow")
                    or type(target.get("paper")) is not bool or target["paper"] != (mode == "paper")
                    or not ids(target.get("order_ids"), nonempty=not (structured and kind=='owner_period'))
                    or (structured and (kind not in ('order_pair','owner_period') or kind=='owner_period' and target['order_ids']!=[]))
                    or (not structured and len(target["order_ids"])!=2)
                    or not ids(target.get("source_receipt_ids"), nonempty=True)
                    or start is None or finish is None
                    or not times["window_start"] <= start < finish <= times["window_end"]):
                raise ValueError
            if not matching or any(not _same_cost_scope(item,target) for item in matching):
                raise ValueError
            information=prepared.get(target['scope_id'])
            wanted_refs=set();query_keys=set();joined_refs=set()
            if information is not None:
                if 'investment' not in source.get('product_loop_ids',[]):raise ValueError('cost_query_source_missing')
                query_keys={k for k in information['required'] if k[:2]==key[:2] and k[2] in query['covered_categories']}
                if not query_keys:raise ValueError('cost_query_source_not_expected')
                executors={v for k in query_keys for v in information['required'][k]}
                wanted_refs={r for r in information['refs'] if r[0] in executors}
            for item in matching:
                if 'execution_refs' in item or information is not None:
                    item_refs=_execution_ref_triples(item.get('execution_refs'))
                    if information is not None and not item_refs<=wanted_refs:raise ValueError('cost_query_execution_ref_mismatch')
                    if (item.get('join_type')=='scope_query' or 'run_ids' in item or 'occurrence_ids' in item) and (
                            not ids(item.get('run_ids'),nonempty=True) or not ids(item.get('occurrence_ids'),nonempty=True)
                            or set(item['run_ids'])!={r[1] for r in item_refs} or set(item['occurrence_ids'])!={r[2] for r in item_refs}):
                        raise ValueError('cost_query_execution_ref_mismatch')
                    joined_refs.update(item_refs)
                if item.get("join_type") == "scope_query":
                    if 'execution_refs' not in item and (not ids(item.get("run_ids"), nonempty=True) or not ids(item.get("occurrence_ids"), nonempty=True)
                            or set(item["occurrence_ids"]) != {f"{target['owner_id']}:{run}" for run in item["run_ids"]}):
                        raise ValueError
                elif item.get("join_type") == "paid_allocation":
                    if (query.get("settlement_state") != "paid_final" or item.get("document_id") not in query["document_ids"]
                            or item.get("status") not in ("completed", "settled", "paid")
                            or not isinstance(item.get("job_id"), str) or not item["job_id"]):
                        raise ValueError
                    if information is not None and (key[0],item['job_id']) in job_conflicts:raise ValueError('cost_query_paid_binding_conflict')
                    bound = False
                    for document in _document_rows(payload)[0]:
                        identity = _document_identity(document)
                        if (identity != (key[0], item.get("document_type"), item.get("document_id"))
                                or document.get("billing_account_ref") != key[1]):
                            continue
                        for line in document.get("line_items", []):
                            if not isinstance(line, dict) or line.get("line_item_id") != item.get("line_item_id"):
                                continue
                            for allocation in line.get("allocations", []):
                                if (not isinstance(allocation, dict) or allocation.get("allocation_id") != item.get("allocation_id")
                                        or allocation.get("job_id") != item["job_id"]
                                        or allocation.get("product_loop_id") != target["product_loop_id"]):
                                    continue
                                receipt_id = (f"{key[0]}:actual-cost:{identity[1]}:{identity[2]}:"
                                              f"line:{line['line_item_id']}:allocation:{allocation['allocation_id']}")
                                bound |= any(isinstance(row, dict) and row.get("receipt_id") == receipt_id
                                    and row.get("record_type") == "receipt" and row.get("verification_state") == "verified"
                                    and row.get("provider") == key[0] and row.get("currency") == "USD"
                                    and row.get("product_loop_id") == target["product_loop_id"] for row in paid_document_rows(document))
                    if not bound:
                        raise ValueError
                else:
                    raise ValueError
            if information is not None and joined_refs!=wanted_refs:raise ValueError('cost_query_execution_ref_missing')
            chain = [page for page in pages if isinstance(page, dict)
                     and (page.get("provider"), page.get("billing_account_ref"), page.get("query_id")) == key]
            if not chain or any(type(page.get("page")) is not int for page in chain):
                raise ValueError
            chain.sort(key=lambda page: page["page"])
            cursor, documents = None, []
            for index, page in enumerate(chain, 1):
                if (page["page"] != index or page.get("cursor") != cursor
                        or not isinstance(page.get("request_id"), str) or not page["request_id"]
                        or not ids(page.get("evidence_refs"), nonempty=True)
                        or not ids(page.get("document_ids"))):
                    raise ValueError
                documents.extend(page["document_ids"])
                if "cursor" not in page or "next_cursor" not in page:
                    raise ValueError
                cursor = page["next_cursor"]
                if index < len(chain) and (not isinstance(cursor, str) or not cursor):
                    raise ValueError
            if cursor is not None or not ids(documents) or set(documents) != set(query["document_ids"]):
                raise ValueError
            settlement = query.get("settlement_state")
            if settlement == "no_charge_final":
                if documents:
                    raise ValueError
                for document in _document_rows(payload)[0]:
                    if (document.get("provider"), document.get("billing_account_ref")) != key[:2]:
                        continue
                    doc_start = _instant(document.get("billing_period_start"))
                    doc_end = _instant(document.get("billing_period_end"))
                    if (doc_start is None or doc_end is None or doc_start >= doc_end
                            or (doc_start < times["window_end"] and doc_end > times["window_start"])):
                        raise ValueError
            elif settlement == "paid_final":
                paid_ids = set()
                for document in _document_rows(payload)[0]:
                    if (document.get("provider"), document.get("billing_account_ref")) != key[:2]:
                        continue
                    identity = _document_identity(document)
                    if identity is None or identity[2] not in query["document_ids"]:
                        doc_start = _instant(document.get("billing_period_start"))
                        doc_end = _instant(document.get("billing_period_end"))
                        if (doc_start is None or doc_end is None or doc_start >= doc_end
                                or (doc_start < times["window_end"] and doc_end > times["window_start"])):
                            raise ValueError
                        continue
                    rows = paid_document_rows(document)
                    if not rows or any(row.get("currency") != "USD" for row in rows):
                        raise ValueError
                    paid_ids.add(identity[2])
                if not documents or not set(documents) <= paid_ids:
                    raise ValueError
            else:
                raise ValueError
            if information is not None:
                for binding in information['scope']['known_paid_bindings']:
                    if (binding['provider'],binding['billing_account_ref'],binding['category']) not in query_keys:continue
                    if settlement!='paid_final':raise ValueError('cost_query_known_paid_missing')
                    aliases={tuple(binding['charge_identity'])}
                    receipt_ids={binding['receipt_id']}
                    for alias in binding.get('identity_aliases',[]):
                        if not isinstance(alias,list) or not all(isinstance(v,str) and v for v in alias):raise ValueError('cost_query_inventory_invalid')
                        if len(alias)==6 and alias[0]=='charge':aliases.add(tuple(alias[1:]))
                        elif len(alias)==2 and alias[0]=='receipt':receipt_ids.add(alias[1])
                        else:raise ValueError('cost_query_inventory_invalid')
                    found=False
                    for document in _document_rows(payload)[0]:
                        identity=_document_identity(document)
                        if identity is None or (identity[0],document.get('billing_account_ref'))!=key[:2] or identity[2] not in documents:continue
                        verified={r['receipt_id'] for r in paid_document_rows(document)}
                        if not verified:continue
                        for line in document.get('line_items',[]):
                            for allocation in line.get('allocations',[]):
                                receipt_id=f"{key[0]}:actual-cost:{identity[1]}:{identity[2]}:line:{line.get('line_item_id')}:allocation:{allocation.get('allocation_id')}"
                                linked=any(item.get('join_type')=='paid_allocation' and item.get('document_type')==identity[1]
                                    and item.get('document_id')==identity[2] and item.get('line_item_id')==line.get('line_item_id')
                                    and item.get('allocation_id')==allocation.get('allocation_id') and item.get('job_id')==allocation.get('job_id')
                                    for item in matching)
                                if (linked and receipt_id in verified and line.get('category')==binding['category'] and allocation.get('product_loop_id')=='investment'
                                        and (paid_charge_identity(document,line,allocation) in aliases or receipt_id in receipt_ids)):
                                    found=True
                    if not found:raise ValueError('cost_query_known_paid_missing')
                information['covered'].update(query_keys)
                information['evidence_refs'].update(query['evidence_refs'])
                information['evidence_refs'].update(ref for page in chain for ref in page['evidence_refs'])
            observation_fields = ("billing_account_ref", "query_id", "scope_id", "covered_categories",
                                  "window_start", "window_end", "observed_at", "finalized_through",
                                  "settlement_state", "document_ids", "evidence_refs")
            result["observations"].append({**{field: query[field] for field in observation_fields},
                "provider": key[0], **{field: target[field] for field in ("order_ids", "period_start", "period_end")}})
        except (KeyError, TypeError, ValueError) as error:
            reason=str(error) if str(error).startswith('cost_query_') else 'unverified_receipt'
            result["rejections"].append({**context, "reason": reason})
    if expected_inventory is not None:
        result['scope_coverages']=[]
        for scope_id,information in prepared.items():
            trusted=information['scope']
            complete=set(information['required'])<=information['covered'] and not any(
                rejection.get('scope_id') in (None,scope_id) for rejection in result['rejections'])
            result['scope_coverages'].append({**{k:trusted[k] for k in ('scope_kind','owner_id','mode','paper','order_ids','period_start','period_end','source_receipt_ids')},
                'scope_id':scope_id,'coverage_state':'complete' if complete else 'gap',
                'reason':None if complete else 'cost_query_sources_uncovered','evidence_refs':sorted(information['evidence_refs'])})
        if result['scope_coverages'] and all(row['coverage_state']=='complete' for row in result['scope_coverages']):
            result.update(coverage_state='complete',reason='official_queries_cover_expected_inventory')
        else:result['reason']='cost_query_sources_uncovered'
    return result


def _safe_gap_rows(*, end: str, start: str, digest: str, source_id: str,
                   loop_id: str, reason: str, observed_at: str) -> list[dict]:
    evidence = _evidence("readback", digest)
    return [
        _coverage(
            loop_id=loop_id, source_id=source_id, projection="historical", start=None,
            end=end, state="gap", reason=reason, categories=set(), observed_at=observed_at,
            evidence=evidence,
        ),
        _coverage(
            loop_id=loop_id, source_id=source_id, projection="trailing", start=start,
            end=end, state="gap", reason=reason, categories=set(), observed_at=observed_at,
            evidence=evidence,
        ),
    ]


def adapt(payload: dict, *, snapshot_at: str, trailing_start: str) -> list[dict]:
    """Convert a passed official billing readback; never performs provider or network I/O."""
    end, start = _window_inputs(snapshot_at, trailing_start)
    digest = _digest(payload)
    if not isinstance(payload, dict):
        return _safe_gap_rows(
            end=end, start=start, digest=digest, source_id="actual-cost-readback",
            loop_id="cfo", reason="read_failed", observed_at=end,
        )

    observed_at, projection_reasons = _readback_state(payload, end=end, start=start)
    sources, source_failures = _source_rows(payload)
    documents, document_shape_failure = _document_rows(payload)
    if document_shape_failure:
        source_failures.add(document_shape_failure)
    jobs, job_conflicts = _job_index(payload)
    exclusion_failures = _excluded_failures(payload, sources)

    deduped, document_conflicts, document_failures = _document_rows_deduped(documents)
    source_failures.update(document_failures)
    for provider, _document_id in document_conflicts:
        source = sources.setdefault(provider, {"loops": set(), "status": "available", "reason": None, "conflict": False})
        source["reason"] = "unverified_receipt"
        source["conflict"] = True

    # A source absent from metadata is inferred only from the official documents.  Estimates,
    # quotes, and personal_subscriptions are intentionally never inspected as actual documents.
    for document in deduped:
        identity = _document_identity(document)
        if identity is not None:
            provider = identity[0]
            sources.setdefault(provider, {
                "loops": set(), "status": "available", "reason": None, "conflict": False,
            })

    receipts_by_group: dict[tuple[str, str, str], list[dict]] = {}
    failures_by_group: dict[tuple[str, str, str], set[str]] = {
        group: set(reasons) for group, reasons in exclusion_failures.items()
    }
    if not projection_reasons.get("historical") or not projection_reasons.get("trailing"):
        for document in deduped:
            identity = _document_identity(document)
            if identity is None:
                continue
            provider, _document_type, _document_id = identity
            source = sources.get(provider) or {"loops": set()}
            if source.get("status") != "available" or source.get("conflict"):
                continue
            document_receipts, document_failures_for_loops, seen_groups = _parse_document(
                document,
                end=end,
                payload_digest=digest,
                jobs=jobs,
                job_conflicts=job_conflicts,
                source_loops=set(source.get("loops", set())),
            )
            for receipt in document_receipts:
                group = (receipt["provider"], receipt["product_loop_id"], _source_id(receipt["provider"]))
                receipts_by_group.setdefault(group, []).append(receipt)
                sources[receipt["provider"]]["loops"].add(receipt["product_loop_id"])
            for provider_name, loop_id, source_id in seen_groups:
                sources[provider_name]["loops"].add(loop_id)
            for loop_id, reason in document_failures_for_loops:
                group = (provider, loop_id, _source_id(provider))
                failures_by_group.setdefault(group, set()).add(reason)
            if not document_receipts and not document_failures_for_loops:
                for loop_id in source.get("loops", set()):
                    failures_by_group.setdefault((provider, loop_id, _source_id(provider)), set()).add(
                        "missing_coverage"
                    )

    query_result = validate_official_cost_queries(
        payload, snapshot_at=end,
        paid_records=[row for group in receipts_by_group.values() for row in group],
    )
    accepted_queries = {(row["provider"], row["billing_account_ref"], row["query_id"], row["scope_id"])
                        for row in query_result["observations"]}
    for join in payload.get("job_joins", []) if isinstance(payload.get("job_joins", []), list) else []:
        if isinstance(join, dict) and join.get("join_type") == "paid_allocation":
            key = tuple(join.get(field) for field in ("provider", "billing_account_ref", "query_id", "scope_id"))
            if (not all(isinstance(item, str) and item for item in key) or key not in accepted_queries):
                provider, loop_id = _provider(join.get("provider")), _loop_id(join.get("product_loop_id"))
                if provider is not None and loop_id is not None:
                    failures_by_group.setdefault((provider, loop_id, _source_id(provider)), set()).add("unverified_receipt")

    if not sources:
        return _safe_gap_rows(
            end=end, start=start, digest=digest, source_id="actual-cost-readback", loop_id="cfo",
            reason=_choose_reason(source_failures, "read_failed"), observed_at=observed_at,
        )

    groups: set[tuple[str, str, str]] = set()
    for provider, source in sources.items():
        loops = set(source.get("loops", set()))
        if not loops:
            loops = {"cfo"}
        groups.update((provider, loop_id, _source_id(provider)) for loop_id in loops)
    groups.update(receipts_by_group)
    groups.update(failures_by_group)

    output: list[dict] = []
    for group in sorted(groups):
        provider, loop_id, source_id = group
        source = sources.get(provider, {})
        evidence = _evidence(provider, digest)
        group_receipts = receipts_by_group.get(group, [])
        output.extend(group_receipts)
        base_reasons = set(source_failures)
        if source.get("conflict"):
            base_reasons.add("unverified_receipt")
        if source.get("status") != "available":
            base_reasons.add(source.get("reason") or "missing_coverage")
        base_reasons.update(failures_by_group.get(group, set()))
        for projection, window_start in (("historical", None), ("trailing", start)):
            reason = projection_reasons.get(projection)
            if reason is None and (base_reasons or not group_receipts):
                reason = _choose_reason(base_reasons, "missing_coverage")
            categories = {
                component["category"]
                for row in group_receipts
                if (row["settled_at"] or row["occurred_at"]) >= (window_start or "")
                and (row["settled_at"] or row["occurred_at"]) < end
                for component in row["components"]
            }
            if reason is None and not categories:
                reason = "missing_category"
            output.append(_coverage(
                loop_id=loop_id,
                source_id=source_id,
                projection=projection,
                start=window_start,
                end=end,
                state="complete" if reason is None else "gap",
                reason=reason,
                categories=categories if reason is None else set(),
                observed_at=observed_at,
                evidence=evidence,
            ))
    receipt_rows = sorted(
        (row for row in output if row["record_type"] == "receipt"),
        key=lambda row: row["receipt_id"],
    )
    coverage_rows = sorted(
        (row for row in output if row["record_type"] == "coverage"),
        key=lambda row: (row["source_id"], row["product_loop_id"], row["projection"]),
    )
    return [*receipt_rows, *coverage_rows]


def billed_expenses(payload: dict | None, *, snapshot_at: str,
                    trailing_start: str) -> dict:
    """Project official invoice totals separately; never add billed-only rows to B0."""
    end, start = _window_inputs(snapshot_at, trailing_start)
    if payload is None:
        return {"status": "unavailable", "reason": "source_unconnected", "invoices": []}
    if not isinstance(payload, dict):
        return {"status": "unverified", "reason": "read_failed", "invoices": []}

    digest = _digest(payload)
    observed_at, projection_reasons = _readback_state(payload, end=end, start=start)
    sources, source_failures = _source_rows(payload)
    documents, document_shape_failure = _document_rows(payload)
    deduped, document_conflicts, document_failures = _document_rows_deduped(documents)
    global_reasons = set(source_failures) | document_failures
    for source in sources.values():
        if source.get("conflict"):
            global_reasons.add("unverified_receipt")
        if source.get("status") != "available":
            global_reasons.add(source.get("reason") or "missing_coverage")
    if document_shape_failure:
        global_reasons.add(document_shape_failure)
    global_reasons.update(projection_reasons.values())
    if document_conflicts:
        global_reasons.add("unverified_receipt")

    invoices: list[dict] = []
    for row in deduped:
        identity = _document_identity(row)
        if identity is None or identity[1] != "invoice":
            continue
        provider, _document_type, document_id = identity
        source = sources.get(provider)
        reasons = set(projection_reasons.values())
        if (provider, document_id) in document_conflicts:
            reasons.add("unverified_receipt")
        if source is None:
            reasons.add("missing_coverage")
        else:
            if source.get("conflict"):
                reasons.add("unverified_receipt")
            if source.get("status") != "available":
                reasons.add(source.get("reason") or "missing_coverage")

        status = row.get("status")
        valid_status = isinstance(status, str) and status in {"billed", "paid", "settled"}
        if (row.get("official") is not True
                or row.get("source_type") != OFFICIAL_SOURCE_TYPES["invoice"]
                or not valid_status):
            reasons.add("unverified_receipt")
        currency = _currency(row.get("currency"))
        if currency is None:
            reasons.add("unsupported_currency")
        period_start = _instant(row.get("billing_period_start"))
        period_end = _instant(row.get("billing_period_end"))
        paid_at = _instant(row.get("paid_at"))
        if (period_start is None or period_end is None or period_start >= period_end
                or period_end > end or (paid_at is not None and paid_at > end)):
            reasons.add("unverified_receipt")

        raw_lines = row.get("line_items")
        if not isinstance(raw_lines, list) or not raw_lines:
            reasons.add("missing_coverage")
            raw_lines = []
        unique_lines: dict[str, tuple[str, dict]] = {}
        line_conflicts: set[str] = set()
        for line in raw_lines:
            if (not isinstance(line, dict)
                    or not isinstance(line.get("line_item_id"), str)
                    or not contract.IDENTITY.fullmatch(line.get("line_item_id"))):
                reasons.add("unverified_receipt")
                continue
            line_id = line["line_item_id"]
            try:
                line_digest = _canonical(line)
            except (TypeError, ValueError):
                reasons.add("unverified_receipt")
                continue
            prior = unique_lines.get(line_id)
            if prior is None:
                unique_lines[line_id] = (line_digest, line)
            elif prior[0] != line_digest:
                line_conflicts.add(line_id)
        if line_conflicts:
            reasons.add("unverified_receipt")

        amounts: list[str] = []
        for line_id, (_line_digest, line) in unique_lines.items():
            if line_id in line_conflicts:
                continue
            amount = _amount(line.get("amount"))
            occurred_at = _instant(line.get("occurred_at"))
            basis = line.get("basis")
            if (amount is None or occurred_at is None or period_start is None
                    or period_end is None or occurred_at < period_start
                    or occurred_at >= period_end or not isinstance(basis, str)
                    or basis not in ACTUAL_BASES):
                reasons.add("unverified_receipt")
                continue
            amounts.append(amount)

        billed_total: str | None = None
        if amounts:
            try:
                with localcontext() as context:
                    context.prec = max(
                        MAX_B0_AMOUNT_SIGNIFICANT_DIGITS,
                        max(len(value.replace(".", "")) for value in amounts)
                        + len(str(len(amounts))) + 1,
                    )
                    total = sum((Decimal(value) for value in amounts), Decimal(0))
                billed_total = _canonical_decimal_text(total)
            except (DecimalException, ArithmeticError):
                reasons.add("unverified_receipt")
        else:
            reasons.add("missing_coverage")

        for header_field in ("billed_total", "amount"):
            header_total = row.get(header_field)
            if header_total is not None:
                normalized_header_total = _amount(header_total)
                if normalized_header_total is None or normalized_header_total != billed_total:
                    reasons.add("unverified_receipt")

        invoice_status = "unverified" if reasons else "verified"
        if invoice_status != "verified":
            billed_total = None
        invoices.append({
            "status": invoice_status,
            "provider": provider,
            "invoice_period": period_start[:7] if period_start is not None else None,
            "currency": currency,
            "billed_total": billed_total,
            "cash_paid_status": (
                "paid" if valid_status and status in {"paid", "settled"}
                and paid_at is not None else "unknown"
            ),
            "allocation_status": "unattributed",
            "source_ref": _evidence(provider, digest),
            "reason": _choose_reason(reasons) if reasons else None,
        })

    if not invoices:
        reason = _choose_reason(global_reasons, "missing_coverage")
        result_status = "unverified" if global_reasons else "unavailable"
    else:
        invoice_reasons = {
            invoice["reason"] for invoice in invoices if invoice["reason"] is not None
        }
        all_reasons = global_reasons | invoice_reasons
        result_status = "verified" if not all_reasons else "unverified"
        reason = _choose_reason(all_reasons) if all_reasons else None
    return {
        "status": result_status,
        "reason": reason,
        "observed_at": observed_at,
        "invoices": invoices,
    }


__all__ = ["adapt", "billed_expenses"]
