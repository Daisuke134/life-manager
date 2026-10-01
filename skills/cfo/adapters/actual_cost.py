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
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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
_UNORDERED_COLLECTIONS = frozenset({
    "sources", "documents", "invoices", "paid_receipts", "job_joins",
    "line_items", "allocations", "pages", "document_ids", "product_loop_ids",
    "estimates", "quotes", "personal_subscriptions",
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
            if not path or path[-1] not in _UNORDERED_COLLECTIONS:
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
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _amount(value: Any) -> str | None:
    if not isinstance(value, str) or not contract.POSITIVE_AMOUNT.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return format(parsed.normalize(), "f")


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

        allocation_total = Decimal(0)
        eligible: list[tuple[str, str, str]] = []
        for allocation_id, (_, allocation) in unique_allocations.items():
            allocation_amount = _amount(allocation.get("amount"))
            loop_id = _loop_id(allocation.get("product_loop_id"))
            if allocation_amount is None:
                failures.update((loop, "unverified_receipt") for loop in source_loops)
                continue
            allocation_total += Decimal(allocation_amount)
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
        if allocation_total != Decimal(amount):
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


__all__ = ["adapt"]
