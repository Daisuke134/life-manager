#!/usr/bin/env python3
"""Per-Product-Loop daily P&L from official receipts only.

Every figure is either a sum of entries that each carry an official receipt id, an explicit 0
from a source that was actually read for that day, or ``unverified:<reason>``. Currencies are
never converted: net is reported per currency.

Usage: loop_pnl.py [--date YYYY-MM-DD] [--json]   (date is the Asia/Tokyo reporting day)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from skills.cfo import economic_attribution as contract  # noqa: E402
from skills.cfo.adapters import actual_cost, affiliate, agent_economy_investment
from skills.cfo.adapters import capafy_mobile, marketplace, stripe, writer  # noqa: E402

CATALOG = ROOT / "apps/life-manager/config/product-loop-catalog.json"
CREDENTIALS = Path("~/.local/share/anicca/credentials.json").expanduser()
STATE = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", "~/.local/state/life-manager")).expanduser()
JST = timezone(timedelta(hours=9))
KINDS = ("revenue", "refund", "cost")
NOT_APPLICABLE_ROLES = {"non_economic", "aggregator"}
DISPLAY = Decimal("0.000001")  # text rounding only; --json keeps exact sums


@dataclass(frozen=True)
class Entry:
    loop_id: str
    kind: str  # revenue | refund | cost
    amount: Decimal
    currency: str
    receipt_id: str


@dataclass
class SourceResult:
    """One adapter's readback. ``covers`` = (loop_id, kind) pairs this source is authoritative for."""
    name: str
    covers: set[tuple[str, str]]
    entries: list[Entry] = field(default_factory=list)
    error: str | None = None  # set => every covered cell is unverified
    notes: dict = field(default_factory=dict)


B7_ADAPTER_ORDER = (
    "b1-capafy-mobile", "b2-stripe", "b3-affiliate", "b4-marketplace",
    "b5-agent-economy-investment", "b6-actual-cost", "b7-writer",
)
B7_SOURCE_LOOPS = {
    "b1-capafy": ("capafy",), "b1-mobile": ("mobile-apps",),
    "b2-stripe": ("self-build",), "b3-affiliate": ("affiliate",),
    "b4-marketplace": ("gig-coconala", "gig-lancers", "gig-crowdworks"),
    "b5-agent": ("agent-economy",), "b5-investment": ("investment",),
    "b7-writer": ("writer",),
}


def join_adapter_records(adapter_records: dict[str, list[dict]]) -> list[dict]:
    """Join B1-B6 normalized records once in a fixed order for the B0 projector."""
    joined: list[dict] = []
    for adapter_name in B7_ADAPTER_ORDER:
        rows = adapter_records.get(adapter_name, [])
        if rows is None:
            continue
        if not isinstance(rows, list):
            raise TypeError(f"adapter_records_invalid:{adapter_name}")
        joined.extend(rows)
    return joined


def project_records(records: list[dict], *, snapshot_at: str, trailing_start: str) -> dict:
    """Pass the joined B1-B6 array through B0 exactly once."""
    return contract.project(
        list(records), snapshot_at=snapshot_at, trailing_start=trailing_start,
    )


def _b7_gap_records(*, source_id: str, loop_ids: tuple[str, ...], reason: str,
                    snapshot_at: str, trailing_start: str) -> list[dict]:
    rows = []
    for loop_id in loop_ids:
        for projection, window_start, categories in (
            ("historical", None, []),
            ("trailing", trailing_start, []),
            ("as_of", None, []),
        ):
            rows.append(contract.validate_record({
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "coverage",
                "product_loop_id": loop_id,
                "source_id": source_id,
                "projection": projection,
                "window_start": window_start,
                "window_end": snapshot_at,
                "coverage_state": "gap",
                "reason": reason,
                "covered_categories": categories,
                "observed_at": snapshot_at,
                "evidence_refs": [f"adapter://{source_id}/{reason}"],
            }))
    return rows


def _read_b7_payload(path: str | Path):
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def _billing_decimal(value: object) -> Decimal:
    text = str(value or "").strip().replace(",", "").replace("¥", "")
    negative = text.startswith("(") and text.endswith(")") or text.startswith("-")
    text = text.strip("()")
    if text.startswith("-"):
        text = text[1:]
    if not text or any(character not in "0123456789." for character in text):
        raise ValueError("google_billing_amount_invalid")
    amount = Decimal(text)
    return -amount if negative else amount


def _billing_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def google_billing_actual_cost_readback(
    path: str | Path, *, invoice_month: str, snapshot_at: str, trailing_start: str,
) -> dict:
    """Build the B7 official-cost envelope from the already downloaded Cost Table bytes."""
    source = Path(path)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    header_index = next(
        (index for index, row in enumerate(rows)
         if "サービスの説明" in row or "Service description" in row),
        None,
    )
    if header_index is None:
        raise ValueError("google_billing_csv_header_invalid")
    headers = [str(value).strip() for value in rows[header_index]]
    japanese = "サービスの説明" in headers
    if japanese:
        required = {
            "service": "サービスの説明", "sku": "SKU の説明", "kind": "費用のタイプ",
            "date": "使用開始日", "raw": "四捨五入前の費用（¥）",
        }
        if any(value not in headers for value in required.values()):
            raise ValueError("google_billing_csv_header_invalid")
        index = {key: headers.index(value) for key, value in required.items()}
        invoice_total = None
        currency = "JPY"
        for row in rows[:header_index]:
            if row and row[0] == "合計お支払い額" and len(row) > 1:
                invoice_total = _billing_decimal(row[1])
            if row and row[0] == "通貨" and len(row) > 1:
                currency = row[1].strip().upper()
        if currency != "JPY":
            raise ValueError("google_billing_currency_invalid")
        lines: list[tuple[str, str, Decimal, str]] = []
        tax_total = Decimal(0)
        positive_cost_total = Decimal(0)
        for row in rows[header_index + 1:]:
            cells = row + [""] * max(0, len(headers) - len(row))
            kind = cells[index["kind"]].strip()
            amount = _billing_decimal(cells[index["raw"]])
            if kind in {"税金", "丸めエラー"}:
                tax_total += amount
                continue
            if kind == "合計":
                if invoice_total is None:
                    invoice_total = amount
                continue
            if cells[index["date"]].strip()[:7] != invoice_month:
                continue
            service = cells[index["service"]].strip()
            sku = cells[index["sku"]].strip()
            if not service or not sku or amount == 0:
                continue
            occurred = f"{cells[index['date']].strip()}T00:00:00Z"
            if amount > 0:
                positive_cost_total += amount
                lines.append((service, sku, amount, occurred))
    else:
        required = ["Service description", "SKU description", "Cost", "Currency", "Invoice month"]
        if any(value not in headers for value in required):
            raise ValueError("google_billing_csv_header_invalid")
        index = {value: headers.index(value) for value in required}
        tax_header = "Taxes" if "Taxes" in headers else "Tax" if "Tax" in headers else None
        lines = []
        tax_total = Decimal(0)
        positive_cost_total = Decimal(0)
        invoice_total = None
        for row in rows[header_index + 1:]:
            cells = row + [""] * max(0, len(headers) - len(row))
            if cells[index["Invoice month"]].strip() != invoice_month:
                continue
            if cells[index["Currency"]].strip().upper() != "JPY":
                raise ValueError("google_billing_currency_invalid")
            amount = _billing_decimal(cells[index["Cost"]])
            if tax_header:
                tax_total += _billing_decimal(cells[headers.index(tax_header)])
            if amount <= 0:
                continue
            positive_cost_total += amount
            lines.append((cells[index["Service description"]].strip(),
                          cells[index["SKU description"]].strip(), amount,
                          f"{invoice_month}-01T00:00:00Z"))
    if not lines:
        raise ValueError("google_billing_csv_empty")
    effective_tax = (invoice_total - positive_cost_total) if invoice_total is not None else tax_total
    if effective_tax < 0:
        raise ValueError("google_billing_total_mismatch")
    if effective_tax > 0:
        lines.append(("Google Cloud", "tax-and-rounding", effective_tax, f"{invoice_month}-01T00:00:00Z"))
    period_year, period_month = (int(value) for value in invoice_month.split("-"))
    if period_month == 12:
        next_month = f"{period_year + 1:04d}-01"
    else:
        next_month = f"{period_year:04d}-{period_month + 1:02d}"
    period_start = f"{invoice_month}-01T00:00:00Z"
    period_end = f"{next_month}-01T00:00:00Z"
    document_id = f"google-cloud-{invoice_month}-{digest[:16]}"
    line_items = []
    for number, (service, sku, amount, occurred_at) in enumerate(lines, 1):
        line_id = f"gcp-{digest[:12]}-{number}"
        line_items.append({
            "line_item_id": line_id, "category": "infra_cost", "basis": "official_invoice",
            "amount": _billing_text(amount), "occurred_at": occurred_at,
            "allocations": [{"allocation_id": f"{line_id}-cfo", "product_loop_id": "cfo",
                              "amount": _billing_text(amount)}],
        })
    return {
        "readback": {
            "kind": "official_billing_readback", "observed_at": snapshot_at,
            "historical": {"complete": True, "window_start": None, "window_end": snapshot_at},
            "trailing": {"complete": True, "window_start": trailing_start, "window_end": snapshot_at},
            "variance": {
                "invoice_total": _billing_text(invoice_total) if invoice_total is not None else None,
                "positive_cost_total": _billing_text(positive_cost_total),
                "tax_and_rounding": _billing_text(effective_tax),
            },
        },
        "sources": [{"provider": "google-cloud", "status": "available", "product_loop_ids": ["cfo"]}],
        "documents": [{
            "document_type": "invoice", "official": True, "provider": "google-cloud",
            "invoice_id": document_id, "source_type": "official_invoice", "status": "paid",
            "currency": "JPY", "billing_period_start": period_start,
            "billing_period_end": period_end, "paid_at": period_end, "line_items": line_items,
        }],
        "source_receipt_ref": f"google-billing://sha256/{digest}",
    }


def _paths(value: str | None) -> list[Path]:
    return [Path(item) for item in str(value or "").split(os.pathsep) if item.strip()]


def _safe_b7_adapter(call, *, source_id: str, loop_ids: tuple[str, ...],
                     snapshot_at: str, trailing_start: str) -> list[dict]:
    try:
        rows = call()
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError):
        rows = []
    return rows if rows else _b7_gap_records(
        source_id=source_id, loop_ids=loop_ids, reason="read_failed",
        snapshot_at=snapshot_at, trailing_start=trailing_start,
    )


def collect_b7_records(*, snapshot_at: str, trailing_start: str,
                       adapter_records: dict[str, list[dict]] | None = None,
                       env: dict[str, str] | None = None) -> list[dict]:
    """Read only already-captured B1-B6 artifacts and return one joined record array."""
    if adapter_records is not None:
        return join_adapter_records(adapter_records)
    env = os.environ if env is None else env
    sources: dict[str, list[dict]] = {name: [] for name in B7_ADAPTER_ORDER}

    capafy_path = env.get("LM_CFO_CAPAFY_ANALYTICS")
    sources["b1-capafy-mobile"].extend(
        _safe_b7_adapter(
            lambda: capafy_mobile.adapt_capafy(
                capafy_path, snapshot_at=snapshot_at, trailing_start=trailing_start,
            ) if capafy_path else [],
            source_id="capafy-orders", loop_ids=B7_SOURCE_LOOPS["b1-capafy"],
            snapshot_at=snapshot_at, trailing_start=trailing_start,
        )
    )
    mobile_path = env.get("LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES") or BUSINESS_OUTCOMES
    sources["b1-capafy-mobile"].extend(
        _safe_b7_adapter(
            lambda: capafy_mobile.adapt_mobile(
                mobile_path, snapshot_at=snapshot_at, trailing_start=trailing_start,
            ),
            source_id="app-store-connect-financial", loop_ids=B7_SOURCE_LOOPS["b1-mobile"],
            snapshot_at=snapshot_at, trailing_start=trailing_start,
        )
    )

    stripe_path = env.get("LM_CFO_STRIPE_READBACK")
    stripe_default_category = env.get("LM_CFO_STRIPE_DEFAULT_ECONOMIC_CATEGORY") or None
    if env.get("LM_CFO_STRIPE_LIVE_READBACK") == "1":
        stripe_reader = lambda: stripe.adapt(
            build_stripe_readback(
                snapshot_at=snapshot_at, trailing_start=trailing_start,
                default_economic_category=stripe_default_category,
            ),
            product_loop_id="self-build", observed_at=snapshot_at, trailing_start=trailing_start,
            default_economic_category=stripe_default_category,
        )
    else:
        stripe_reader = lambda: stripe.adapt(
            _read_b7_payload(stripe_path), product_loop_id="self-build",
            observed_at=snapshot_at, trailing_start=trailing_start,
            default_economic_category=stripe_default_category,
        ) if stripe_path else []
    sources["b2-stripe"] = _safe_b7_adapter(
        stripe_reader, source_id="stripe-financial-record", loop_ids=B7_SOURCE_LOOPS["b2-stripe"],
        snapshot_at=snapshot_at, trailing_start=trailing_start,
    )

    affiliate_path = env.get("LM_CFO_AFFILIATE_READBACK") or env.get("LM_CFO_AFFILIATE_LEDGER")
    sources["b3-affiliate"] = _safe_b7_adapter(
        lambda: affiliate.adapt_path(
            affiliate_path, snapshot_at=snapshot_at, trailing_start=trailing_start,
        ) if affiliate_path else [],
        source_id="affiliate-financial-record", loop_ids=B7_SOURCE_LOOPS["b3-affiliate"],
        snapshot_at=snapshot_at, trailing_start=trailing_start,
    )

    explicit_marketplace_paths: list[tuple[Path, str, str]] = []
    for env_name, platform, loop_id in (
        ("LM_CFO_MARKETPLACE_COCONALA_READBACK", "coconala", "gig-coconala"),
        ("LM_CFO_MARKETPLACE_LANCERS_READBACK", "lancers", "gig-lancers"),
        ("LM_CFO_MARKETPLACE_CROWDWORKS_READBACK", "crowdworks", "gig-crowdworks"),
    ):
        explicit_marketplace_paths.extend(
            (path, platform, loop_id) for path in _paths(env.get(env_name))
        )
    marketplace_paths = _paths(
        env.get("LM_CFO_MARKETPLACE_READBACK") or env.get("LM_CFO_MARKETPLACE_RECEIPTS")
    )
    if explicit_marketplace_paths:
        sources["b4-marketplace"] = []
        configured_loops = set()
        for source_path, platform, loop_id in explicit_marketplace_paths:
            configured_loops.add(loop_id)
            sources["b4-marketplace"].extend(_safe_b7_adapter(
                lambda source_path=source_path, platform=platform, loop_id=loop_id: marketplace.adapt_path(
                    source_path, snapshot_at=snapshot_at, trailing_start=trailing_start,
                    platform=platform, product_loop_id=loop_id,
                ),
                source_id="marketplace-financial-record", loop_ids=(loop_id,),
                snapshot_at=snapshot_at, trailing_start=trailing_start,
            ))
        for loop_id in B7_SOURCE_LOOPS["b4-marketplace"]:
            if loop_id not in configured_loops:
                sources["b4-marketplace"].extend(_b7_gap_records(
                    source_id="marketplace-financial-record", loop_ids=(loop_id,),
                    reason="source_unconnected", snapshot_at=snapshot_at, trailing_start=trailing_start,
                ))
    elif marketplace_paths:
        sources["b4-marketplace"] = []
        for source_path in marketplace_paths:
            sources["b4-marketplace"].extend(_safe_b7_adapter(
                lambda source_path=source_path: marketplace.adapt_path(
                    source_path, snapshot_at=snapshot_at, trailing_start=trailing_start,
                ),
                source_id="marketplace-financial-record",
                loop_ids=B7_SOURCE_LOOPS["b4-marketplace"],
                snapshot_at=snapshot_at, trailing_start=trailing_start,
            ))
    else:
        sources["b4-marketplace"] = _b7_gap_records(
            source_id="marketplace-financial-record", loop_ids=B7_SOURCE_LOOPS["b4-marketplace"],
            reason="source_unconnected", snapshot_at=snapshot_at, trailing_start=trailing_start,
        )

    alpaca_live = env.get("LM_CFO_ALPACA_LIVE_READBACK") == "1"
    b5_paths = _paths(
        (env.get("LM_CFO_AGENT_ECONOMY_READBACK")
         or env.get("LM_CFO_AGENT_ECONOMY_RECEIPTS")
         or env.get("REVENUE_RECEIPT_JOURNAL"))
        if alpaca_live else (
            env.get("LM_CFO_B5_READBACK")
            or env.get("LM_CFO_AGENT_ECONOMY_READBACK")
            or env.get("LM_CFO_INVESTMENT_READBACK")
            or env.get("LM_CFO_AGENT_ECONOMY_RECEIPTS")
            or env.get("REVENUE_RECEIPT_JOURNAL")
        )
    )
    if b5_paths:
        sources["b5-agent-economy-investment"] = []
        for source_path in b5_paths:
            adapted = _safe_b7_adapter(
                lambda source_path=source_path: agent_economy_investment.adapt_path(
                    source_path, snapshot_at=snapshot_at, trailing_start=trailing_start,
                ),
                source_id="b5-readback", loop_ids=("agent-economy", "investment"),
                snapshot_at=snapshot_at, trailing_start=trailing_start,
            )
            if alpaca_live:
                adapted = [row for row in adapted if row.get("product_loop_id") == "agent-economy"]
            sources["b5-agent-economy-investment"].extend(adapted)
    else:
        sources["b5-agent-economy-investment"] = [
            *_b7_gap_records(
                source_id="x402-readback", loop_ids=B7_SOURCE_LOOPS["b5-agent"],
                reason="source_unconnected", snapshot_at=snapshot_at, trailing_start=trailing_start,
            ),
        ]
        if not alpaca_live:
            sources["b5-agent-economy-investment"].extend(_b7_gap_records(
                source_id="alpaca-orders", loop_ids=B7_SOURCE_LOOPS["b5-investment"],
                reason="source_unconnected", snapshot_at=snapshot_at, trailing_start=trailing_start,
            ))
    if alpaca_live:
        sources["b5-agent-economy-investment"].extend(_safe_b7_adapter(
            lambda: agent_economy_investment.adapt(
                build_alpaca_readback(
                    trailing_start=trailing_start, observed_at=snapshot_at,
                ),
                snapshot_at=snapshot_at, trailing_start=trailing_start,
            ),
            source_id="alpaca-live-readback", loop_ids=B7_SOURCE_LOOPS["b5-investment"],
            snapshot_at=snapshot_at, trailing_start=trailing_start,
        ))

    actual_cost_path = env.get("LM_CFO_ACTUAL_COST_READBACK") or env.get("LM_CFO_ACTUAL_COST")
    sources["b6-actual-cost"] = _safe_b7_adapter(
        lambda: actual_cost.adapt(
            _read_b7_payload(actual_cost_path), snapshot_at=snapshot_at,
            trailing_start=trailing_start,
        ) if actual_cost_path else actual_cost.adapt(
            google_billing_actual_cost_readback(
                env["LM_CFO_GOOGLE_BILLING_CSV"],
                invoice_month=env.get("LM_CFO_GOOGLE_BILLING_INVOICE_MONTH", snapshot_at[:7]),
                snapshot_at=snapshot_at, trailing_start=trailing_start,
            ), snapshot_at=snapshot_at, trailing_start=trailing_start,
        ) if env.get("LM_CFO_GOOGLE_BILLING_CSV") else [],
        source_id="actual-cost-readback", loop_ids=("cfo",),
        snapshot_at=snapshot_at, trailing_start=trailing_start,
    )
    writer_path = env.get("LM_CFO_WRITER_MONEY") or str(STATE / "writer" / "money.sqlite3")
    sources["b7-writer"] = _safe_b7_adapter(
        lambda: writer.adapt_path(
            writer_path, snapshot_at=snapshot_at, trailing_start=trailing_start,
        ),
        source_id="writer-money-ledger", loop_ids=B7_SOURCE_LOOPS["b7-writer"],
        snapshot_at=snapshot_at, trailing_start=trailing_start,
    )
    return join_adapter_records(sources)


def build_b7_projection(*, snapshot_at: str, trailing_start: str,
                        adapter_records: dict[str, list[dict]] | None = None,
                        env: dict[str, str] | None = None) -> dict:
    return project_records(
        collect_b7_records(
            snapshot_at=snapshot_at, trailing_start=trailing_start,
            adapter_records=adapter_records, env=env,
        ),
        snapshot_at=snapshot_at, trailing_start=trailing_start,
    )


def day_window(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=JST)
    return start, start + timedelta(days=1)


def in_day(instant: str, day: date) -> bool:
    start, end = day_window(day)
    moment = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("naive timestamp")
    return start <= moment < end


def load_catalog(path: Path = CATALOG) -> list[dict]:
    return json.loads(path.read_text())["loops"]


def credential(service: str, path: Path = CREDENTIALS) -> dict | None:
    try:
        rows = json.loads(path.read_text())["credentials"]
    except (OSError, ValueError, KeyError):
        return None
    return next((row for row in rows if row.get("service") == service), None)


def http_json(url: str, headers: dict, data: bytes | None = None) -> object:
    request = urllib.request.Request(url, headers=headers, data=data)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def run_source(name: str, covers: set, fn, *args, notes: dict | None = None) -> SourceResult:
    result = SourceResult(name, covers, notes=notes if notes is not None else {})
    try:
        result.entries = list(fn(*args))
    except Exception as error:  # fail closed: the covered cells become unverified, nothing invented
        result.entries = []
        result.error = f"{name}:{type(error).__name__}:{str(error)[:120]}"
    return result


# ---------------------------------------------------------------- aggregation


def _cell(loop: dict, kind: str, sources: list[SourceResult]) -> dict:
    covering = [s for s in sources if (loop["id"], kind) in s.covers]
    if not covering:
        if loop["economic"]["role"] in NOT_APPLICABLE_ROLES and kind != "cost":
            return {"status": "zero", "amounts": {}, "receipts": [],
                    "reason": f"not_applicable:role={loop['economic']['role']}"}
        return {"status": "unverified", "reason": "no_source_adapter", "amounts": {}, "receipts": []}
    failed = [s.error for s in covering if s.error]
    if failed:
        return {"status": "unverified", "reason": ";".join(failed), "amounts": {}, "receipts": []}
    amounts: dict[str, Decimal] = {}
    receipts: list[str] = []
    for source in covering:
        for entry in source.entries:
            if entry.loop_id == loop["id"] and entry.kind == kind:
                amounts[entry.currency] = amounts.get(entry.currency, Decimal(0)) + entry.amount
                receipts.append(entry.receipt_id)
    incomplete = sum(s.notes.get("missing_cost_events", {}).get(loop["id"], 0) for s in covering)
    return {"status": "verified" if receipts else "zero", "amounts": amounts, "receipts": receipts,
            "sources": [s.name for s in covering], "incomplete": incomplete}


def build_table(loops: list[dict], sources: list[SourceResult], day: date) -> dict:
    rows = []
    for loop in loops:
        cells = {kind: _cell(loop, kind, sources) for kind in KINDS}
        if any(c["status"] == "unverified" for c in cells.values()):
            net = {"status": "unverified", "reason": "component_unverified", "amounts": {}}
        else:
            amounts: dict[str, Decimal] = {}
            for kind, sign in (("revenue", 1), ("refund", -1), ("cost", -1)):
                for currency, value in cells[kind]["amounts"].items():
                    amounts[currency] = amounts.get(currency, Decimal(0)) + sign * value
            net = {"status": "verified" if amounts else "zero", "amounts": amounts,
                   "incomplete": sum(c.get("incomplete", 0) for c in cells.values())}
        rows.append({"loop_id": loop["id"], **cells, "net": net})
    return {
        "reporting_date": day.isoformat(), "timezone": "Asia/Tokyo",
        "sources": [{"name": s.name, "ok": s.error is None, "error": s.error,
                     "entries": len(s.entries), "notes": s.notes} for s in sources],
        "rows": rows,
    }


def _fmt(cell: dict) -> str:
    if cell["status"] == "unverified":
        return "unverified"
    if not cell["amounts"]:
        return "0"
    text = " ".join(f"{cur} {value.quantize(DISPLAY).normalize():f}"
                    for cur, value in sorted(cell["amounts"].items()))
    return text + ("*" if cell.get("incomplete") else "")


def render(table: dict) -> str:
    header = ("loop", "revenue", "refunds", "cost", "net")
    lines = [[r["loop_id"], _fmt(r["revenue"]), _fmt(r["refund"]), _fmt(r["cost"]), _fmt(r["net"])]
             for r in table["rows"]]
    widths = [max(len(str(x)) for x in col) for col in zip(header, *lines)]
    out = [f"Loop P&L {table['reporting_date']} ({table['timezone']})",
           "  ".join(h.ljust(w) for h, w in zip(header, widths))]
    out += ["  ".join(c.ljust(w) for c, w in zip(line, widths)) for line in lines]
    out.append("")
    out.append("receipts / reasons:")
    for row in table["rows"]:
        for kind in KINDS:
            cell = row[kind]
            receipts = cell["receipts"]
            if receipts:
                shown = ", ".join(receipts[:3]) + (f", ... ({len(receipts)} receipts)" if len(receipts) > 3 else "")
                out.append(f"  {row['loop_id']}.{kind}: {shown}")
            elif cell.get("reason"):
                out.append(f"  {row['loop_id']}.{kind}: {cell['status']} ({cell['reason']})")
    for source in table["sources"]:
        for loop_id, count in sorted(source["notes"].get("missing_cost_events", {}).items()):
            out.append(f"  {loop_id}.cost*: +{count} usage events without provider_cost_usd (not counted)")
        for label, bucket in sorted(source["notes"].get("unattributed", {}).items()):
            out.append(f"  unattributed usage '{label}': {bucket['events']} events, "
                       f"{USAGE_CURRENCY} {bucket[USAGE_CURRENCY].normalize():f} (no Product Loop)")
        if source["notes"].get("unparsed_lines"):
            out.append(f"  {source['name']}: {source['notes']['unparsed_lines']} unparseable lines skipped")
        for product_id, value in sorted(source["notes"].get("mrr", {}).items()):
            out.append(f"  {source['name']}.mrr[{product_id}]: {value}")
    out.append(f"{USAGE_CURRENCY} = runner-reported API-price estimate, not a provider bill. "
               "Currencies are never converted; net is per currency.")
    out.append("sources: " + ", ".join(
        f"{s['name']}={'ok' if s['ok'] else 'FAILED'}({s['entries']})" for s in table["sources"]))
    return "\n".join(out)


def _jsonable(value):
    if isinstance(value, Decimal):
        return f"{value.normalize():f}"
    raise TypeError(type(value).__name__)


# ---------------------------------------------------------------- Alpaca (investment)

ALPACA_API = "https://api.alpaca.markets"
NEW_YORK = ZoneInfo("America/New_York")  # Alpaca date-only activities are US Eastern trade dates


def alpaca_activities(get=http_json, cred_path: Path = CREDENTIALS) -> list[dict]:
    cred = credential("app.alpaca.markets", cred_path)
    if not cred or not cred.get("live_api_key") or not cred.get("live_api_secret"):
        raise LookupError("credential_missing:app.alpaca.markets.live_api_key")
    headers = {"APCA-API-KEY-ID": cred["live_api_key"], "APCA-API-SECRET-KEY": cred["live_api_secret"]}
    rows: list[dict] = []
    token = None
    while True:
        query = {"direction": "asc", "page_size": "100", **({"page_token": token} if token else {})}
        page = get(f"{ALPACA_API}/v2/account/activities?{urllib.parse.urlencode(query)}", headers)
        rows += page
        if len(page) < 100:
            return rows
        token = page[-1]["id"]


def alpaca_entries(activities: list[dict], day: date, loop_id: str = "investment"):
    """FIFO-realized P&L of sells on ``day`` (gain=revenue, loss=cost) plus that day's fees."""
    lots: dict[str, list[list[Decimal]]] = {}
    for act in activities:
        kind = act.get("activity_type")
        receipt = f"alpaca:activity:{act['id']}"
        if kind == "FILL":
            symbol, qty, price = act["symbol"], Decimal(act["qty"]), Decimal(act["price"])
            quote = symbol.split("/")[1] if "/" in symbol else "USD"
            book = lots.setdefault(symbol, [])
            if act["side"] == "buy":
                book.append([qty, price])
                continue
            pnl, remaining = Decimal(0), qty
            while remaining > 0:
                if not book:
                    raise ValueError(f"alpaca_sell_without_lot:{act['id']}")
                lot = book[0]
                used = min(lot[0], remaining)
                pnl += used * (price - lot[1])
                lot[0] -= used
                remaining -= used
                if lot[0] == 0:
                    book.pop(0)
            if in_day(act["transaction_time"], day) and pnl:
                yield Entry(loop_id, "revenue" if pnl > 0 else "cost", abs(pnl), quote, receipt)
        elif kind == "CFEE" and in_day(act["created_at"], day):
            yield Entry(loop_id, "cost", -Decimal(act["qty"]) * Decimal(act["price"]), "USD", receipt)
        elif kind == "FEE" and in_day(act.get("created_at") or datetime.fromisoformat(act["date"])
                                      .replace(tzinfo=NEW_YORK).isoformat(), day):
            yield Entry(loop_id, "cost", -Decimal(act["net_amount"]), "USD", receipt)


# ---------------------------------------------------------------- Stripe (self-build subscriptions)

STRIPE_API = "https://api.stripe.com"
ZERO_DECIMAL = {"JPY", "KRW", "VND", "CLP", "PYG", "UGX", "XAF", "XOF", "BIF", "DJF", "GNF",
                "KMF", "MGA", "RWF", "VUV", "XPF"}


def stripe_live_key(cred_path: Path = CREDENTIALS) -> str:
    try:
        rows = json.loads(cred_path.read_text())["credentials"]
    except (OSError, ValueError, KeyError):
        rows = []
    for row in rows:
        if "stripe" in str(row.get("service", "")).lower():
            key = str(row.get("api_key", ""))
            if key.startswith(("sk_live_", "rk_live_")):
                return key
    env_key = str(os.environ.get("STRIPE_SECRET_KEY", "")).strip()
    if env_key.startswith(("sk_live_", "rk_live_")):
        return env_key
    raise LookupError("credential_missing:stripe_live_secret_key(sk_live_/rk_live_)")


def stripe_transactions(day: date, get=http_json, cred_path: Path = CREDENTIALS) -> list[dict]:
    key = stripe_live_key(cred_path)
    start, end = day_window(day)
    rows: list[dict] = []
    after = None
    while True:
        query = {"created[gte]": int(start.timestamp()), "created[lt]": int(end.timestamp()),
                 "limit": 100, **({"starting_after": after} if after else {})}
        page = get(f"{STRIPE_API}/v1/balance_transactions?{urllib.parse.urlencode(query)}",
                   {"Authorization": f"Bearer {key}"})
        rows += page["data"]
        if not page.get("has_more"):
            return rows
        after = page["data"][-1]["id"]


def _stripe_list_all(path: str, key: str, get=http_json, params: dict | None = None) -> dict:
    rows: list[dict] = []
    seen_ids: set[str] = set()
    query = {"limit": 100, **(params or {})}
    after = None
    while True:
        page_query = {**query, **({"starting_after": after} if after else {})}
        page = get(f"{STRIPE_API}{path}?{urllib.parse.urlencode(page_query)}",
                   {"Authorization": f"Bearer {key}"})
        if (not isinstance(page, dict) or page.get("object") != "list"
                or page.get("url") != path or not isinstance(page.get("data"), list)
                or type(page.get("has_more")) is not bool):
            raise ValueError(f"stripe_readback_payload_invalid:{path}")
        page_ids = [row.get("id") for row in page["data"] if isinstance(row, dict)]
        if (len(page_ids) != len(page["data"])
                or any(not isinstance(row_id, str) or not row_id for row_id in page_ids)
                or len(set(page_ids)) != len(page_ids)
                or bool(seen_ids.intersection(page_ids))):
            raise ValueError(f"stripe_readback_cursor_invalid:{path}")
        seen_ids.update(page_ids)
        rows.extend(page["data"])
        if page["has_more"] is False:
            return {"object": "list", "url": path, "data": rows, "has_more": False}
        if not page_ids or page_ids[-1] == after:
            raise ValueError(f"stripe_readback_cursor_invalid:{path}")
        after = page_ids[-1]


def build_stripe_readback(*, snapshot_at: str, trailing_start: str,
                          get=http_json, api_key: str | None = None,
                          cred_path: Path = CREDENTIALS,
                          default_economic_category: str | None = None) -> dict:
    """Read the complete official Stripe collections without mutating Stripe."""
    key = api_key or stripe_live_key(cred_path)
    if not key.startswith(("sk_live_", "rk_live_")):
        raise LookupError("credential_missing:stripe_live_secret_key(sk_live_/rk_live_)")
    collections = {
        "balance_transactions": _stripe_list_all("/v1/balance_transactions", key, get),
        "charges": _stripe_list_all("/v1/charges", key, get),
        "refunds": _stripe_list_all("/v1/refunds", key, get),
        "subscriptions": _stripe_list_all("/v1/subscriptions", key, get, {"status": "all"}),
    }
    created = [
        int(row["created"])
        for payload in collections.values()
        for row in payload["data"]
        if isinstance(row, dict) and isinstance(row.get("created"), int)
    ]
    history_start = (
        datetime.fromtimestamp(min(created), timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        if created else trailing_start
    )
    return {
        **collections,
        "readback": {
            "provider": "stripe", "provenance": "stripe_api", "read_at": snapshot_at,
            "queries": {
                "trailing": {"start": trailing_start, "end": snapshot_at, "has_more": False},
                "historical": {
                    "history_start": history_start, "end": snapshot_at,
                    "has_more": False, "account_inception": True,
                },
            },
            "classification_policy": {
                "default_economic_category": default_economic_category,
                "source": "explicit_runtime_config" if default_economic_category else "provider_metadata_only",
            },
        },
    }


def alpaca_live_credentials(cred_path: Path = CREDENTIALS) -> tuple[str, str, str]:
    row = credential("app.alpaca.markets", cred_path) or {}
    key = str(row.get("live_api_key", ""))
    secret = str(row.get("live_api_secret", ""))
    if not key or not secret:
        raise LookupError("credential_missing:alpaca_live_api")
    endpoint = str(row.get("live_endpoint") or "https://api.alpaca.markets").rstrip("/")
    base = endpoint if endpoint.endswith("/v2") else f"{endpoint}/v2"
    return base, key, secret


def _alpaca_orders(base: str, key: str, secret: str, get=http_json) -> list[dict]:
    rows: list[dict] = []
    token = None
    while True:
        query = {"status": "all", "limit": 500, "direction": "asc"}
        if token:
            query["page_token"] = token
        page = get(
            f"{base}/orders?{urllib.parse.urlencode(query)}",
            {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        )
        if not isinstance(page, list):
            raise ValueError("alpaca_orders_payload_invalid")
        rows.extend(page)
        if len(page) >= 500:
            raise ValueError("alpaca_orders_pagination_unknown")
        next_token = None
        # Alpaca returns a page token through response headers in some versions;
        # a list without a token is the complete readback used by this adapter.
        if next_token is None:
            return rows
        if next_token == token:
            raise ValueError("alpaca_orders_cursor_invalid")
        token = next_token


def build_alpaca_readback(*, trailing_start: str, get=http_json,
                          api_key: str | None = None, api_secret: str | None = None,
                          cred_path: Path = CREDENTIALS, observed_at: str | None = None) -> dict:
    """Read Alpaca account/orders without turning orders into invented P&L."""
    if api_key is None or api_secret is None:
        base, key, secret = alpaca_live_credentials(cred_path)
    else:
        base, key, secret = "https://api.alpaca.markets/v2", api_key, api_secret
    read_at = observed_at or _utc_text(datetime.now(timezone.utc))
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    account = get(f"{base}/account", headers)
    if not isinstance(account, dict) or not account.get("id"):
        raise ValueError("alpaca_account_payload_invalid")
    orders = _alpaca_orders(base, key, secret, get)
    cash = Decimal(str(account.get("cash", "")))
    if cash < 0:
        raise ValueError("alpaca_negative_cash_unsupported")
    currency = str(account.get("currency", "USD")).upper()
    if currency != "USD":
        raise ValueError("alpaca_currency_unsupported")
    return {
        "provider": "alpaca",
        "readback": {
            "provider": "alpaca", "provenance": "alpaca_api", "read_at": read_at,
            "observed_at": read_at, "window_start": trailing_start,
            "window_end": read_at, "history_complete": True,
            "historical_complete": True, "account_inception": True,
            "orders_count": len(orders),
        },
        "balance": {
            "verification_state": "verified", "finalized": True,
            "reorg_detected": False, "observed_at": read_at,
            "snapshot_id": f"alpaca:account:{account['id']}:{read_at}",
            "account_id": account["id"], "amount": str(account.get("cash")),
            "currency": currency,
        },
    }


STRIPE_MOVEMENTS = {"payout", "payout_cancel", "payout_failure", "transfer", "transfer_cancel",
                    "transfer_failure", "topup", "topup_reversal"}  # balance moves, not P&L


def stripe_entries(transactions: list[dict], loop_id: str = "self-build"):
    for txn in transactions:
        if txn["type"] in STRIPE_MOVEMENTS:
            continue
        if txn["type"] not in ("charge", "payment", "refund", "payment_refund"):
            raise ValueError(f"stripe_unhandled_txn_type:{txn['type']}")  # e.g. dispute adjustment
        currency = txn["currency"].upper()
        scale = Decimal(1) if currency in ZERO_DECIMAL else Decimal(100)
        receipt = f"stripe:{txn['id']}"
        amount = Decimal(txn["amount"]) / scale
        if txn["type"] in ("charge", "payment"):
            yield Entry(loop_id, "revenue", amount, currency, receipt)
        elif txn["type"] in ("refund", "payment_refund"):
            yield Entry(loop_id, "refund", -amount, currency, receipt)
        if txn["type"] in ("charge", "payment", "refund", "payment_refund") and txn.get("fee"):
            yield Entry(loop_id, "cost", Decimal(txn["fee"]) / scale, currency, receipt)


# ---------------------------------------------------------------- x402 on Base (agent-economy)

BASE_RPC = "https://mainnet.base.org"
USDC_BASE = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TRANSFER_WITH_AUTHORIZATION = "0xe3ee160e"  # EIP-3009 selector used by x402 "exact" EVM payments
LOG_SPAN = 2000  # mainnet.base.org rejects wider eth_getLogs ranges (HTTP 413)
X402_STATE = STATE / "x402-sell"


def x402_wallets(state: Path = X402_STATE) -> tuple[set[str], set[str]]:
    """(payTo wallets that sell, every wallet this system owns) from the seller's own state files."""
    pay_to, owned = set(), set()
    for path in state.glob("*-0x*"):
        address = "0x" + path.name.split("-0x", 1)[1][:40].lower()
        owned.add(address)
        if path.name.startswith(("sales-", "external-inflows-")):
            pay_to.add(address)
    extra = {a.strip().lower() for a in os.environ.get("LM_CFO_X402_PAY_TO", "").split(",") if a.strip()}
    return pay_to | extra, owned | extra


class BaseRpc:
    def __init__(self, url: str = BASE_RPC, post=None):
        self.url = url
        self.post = post or (lambda payload: http_json(
            url, {"content-type": "application/json", "user-agent": "life-manager-cfo/1"},
            json.dumps(payload).encode()))

    def __call__(self, method: str, params: list):
        body = self.post({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if "error" in body:
            raise RuntimeError(f"rpc_{method}:{body['error']}")
        return body["result"]

    def block_time(self, number: int) -> int:
        return int(self("eth_getBlockByNumber", [hex(number), False])["timestamp"], 16)

    def first_block_at(self, instant: int, high: int) -> int:
        """Smallest block with timestamp >= instant (binary search, seeded by Base's 2s blocks)."""
        guess = high - max(0, self.block_time(high) - instant) // 2 - 600
        low = guess if guess > 0 and self.block_time(guess) < instant else 0
        while low < high:
            mid = (low + high) // 2
            if self.block_time(mid) < instant:
                low = mid + 1
            else:
                high = mid
        return low


def _topic(address: str) -> str:
    return "0x" + "0" * 24 + address[2:]


def x402_entries(day: date, rpc: BaseRpc, pay_to: set[str], owned: set[str],
                 loop_id: str = "agent-economy"):
    """USDC moved by EIP-3009 authorization: into a payTo wallet from outside = revenue,
    out of an owned wallet to outside = cost (x402 purchases). Own-to-own is excluded."""
    if not pay_to:
        raise LookupError("x402_pay_to_wallets_not_found")
    start, end = day_window(day)
    latest = int(rpc("eth_blockNumber", []), 16)
    if rpc.block_time(latest) < int(end.timestamp()) - 1:
        last = latest  # the day is still running: read up to the chain head
    else:
        last = rpc.first_block_at(int(end.timestamp()), latest) - 1
    first = rpc.first_block_at(int(start.timestamp()), latest)
    logs: dict[tuple[str, str], dict] = {}
    for low in range(first, last + 1, LOG_SPAN):
        high = min(low + LOG_SPAN - 1, last)
        for topics in ([TRANSFER_TOPIC, None, [_topic(a) for a in sorted(pay_to)]],
                       [TRANSFER_TOPIC, [_topic(a) for a in sorted(owned)]]):
            for log in rpc("eth_getLogs", [{"fromBlock": hex(low), "toBlock": hex(high),
                                            "address": USDC_BASE, "topics": topics}]):
                logs[(log["transactionHash"], log["logIndex"])] = log
    selectors: dict[str, str] = {}
    for (tx, index), log in sorted(logs.items()):
        sender = "0x" + log["topics"][1][-40:].lower()
        recipient = "0x" + log["topics"][2][-40:].lower()
        if sender in owned and recipient in owned:
            continue
        if tx not in selectors:
            receipt = rpc("eth_getTransactionReceipt", [tx])
            transaction = rpc("eth_getTransactionByHash", [tx])
            selectors[tx] = transaction["input"][:10] if receipt["status"] == "0x1" else "failed"
        if selectors[tx] != TRANSFER_WITH_AUTHORIZATION:
            continue
        amount = Decimal(int(log["data"], 16)) / Decimal(10**6)
        receipt_id = f"base:{tx}:{int(index, 16)}"
        if recipient in pay_to:
            yield Entry(loop_id, "revenue", amount, "USDC", receipt_id)
        elif sender in owned:
            yield Entry(loop_id, "cost", amount, "USDC", receipt_id)


# ---------------------------------------------------------------- marketplace payment ledgers

MARKETPLACE_LOOPS = {"coconala": "gig-coconala", "lancers": "gig-lancers", "crowdworks": "gig-crowdworks"}
# platform -> the marketplace-core ledger its owner loop writes. Coconala/CrowdWorks have none yet.
MARKETPLACE_LEDGERS = {"lancers": Path("~/.local/state/anicca/lancers/marketplace-ledger.sqlite3").expanduser()}


def marketplace_ledgers() -> dict[str, Path]:
    ledgers = dict(MARKETPLACE_LEDGERS)
    for pair in os.environ.get("LM_CFO_MARKETPLACE_LEDGERS", "").split(","):
        if "=" in pair:
            platform, path = pair.split("=", 1)
            ledgers[platform.strip()] = Path(path.strip()).expanduser()
    return ledgers


def marketplace_entries(platform: str, ledger: Path, day: date):
    """Settled ``payment_received`` rows (net of platform fee) from the marketplace-core ledger."""
    import sqlite3
    if not ledger.is_file() or ledger.stat().st_size == 0:
        raise FileNotFoundError(f"marketplace_ledger_missing:{platform}")
    connection = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT receipt_id, amount_minor, currency, occurred_at FROM marketplace_events "
            "WHERE platform = ? AND event_type = 'payment_received'", (platform,)).fetchall()
    finally:
        connection.close()
    for receipt_id, amount_minor, currency, occurred_at in rows:
        if not in_day(occurred_at, day):
            continue
        if not receipt_id or amount_minor is None or not currency:
            raise ValueError(f"marketplace_payment_without_receipt:{platform}")
        scale = Decimal(1) if currency in ZERO_DECIMAL else Decimal(100)
        yield Entry(MARKETPLACE_LOOPS[platform], "revenue", Decimal(amount_minor) / scale, currency,
                    f"{platform}:{receipt_id}")


# ---------------------------------------------------------------- Capafy (product loop, web console)

CAPAFY_ANALYTICS = STATE / "state" / "capafy-skill-analytics.json"
CAPAFY_FRESH_MAX_AGE = timedelta(hours=6)  # capafy_hourly_reconcile.py writes this file hourly


def capafy_entries(day: date, path: Path = CAPAFY_ANALYTICS, now: datetime | None = None,
                   loop_id: str = "capafy"):
    """Web-console gross/refunds for ``day`` from the hourly reconcile snapshot's daily trend."""
    now = now or datetime.now(timezone.utc)
    text = path.read_text()
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    data = json.loads(text)
    observed_at = data.get("observed_at")
    if not observed_at:
        raise ValueError("capafy_snapshot_missing_observed_at")
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("capafy_snapshot_naive_observed_at")
    status = (data.get("account_totals") or {}).get("_status")
    if status != "fresh":
        raise ValueError(f"capafy_account_totals_status:{status}")
    if day == now.astimezone(JST).date() and now - observed > CAPAFY_FRESH_MAX_AGE:
        raise ValueError(f"capafy_snapshot_stale:age_seconds={(now - observed).total_seconds():.0f}")
    row = next((r for r in data.get("daily_revenue_trend_last_30d") or []
                if r.get("date") == day.isoformat()), None)
    if row is None:
        raise LookupError(f"capafy_no_trend_row_for_date:{day.isoformat()}")
    receipt = f"capafy:snapshot:{observed_at}:{digest}:{day.isoformat()}"
    revenue = Decimal(str(row.get("revenue", 0)))
    if revenue:
        yield Entry(loop_id, "revenue", revenue, "USD", receipt + ":revenue")
    refund = Decimal(str(row.get("refundAmount", 0)))
    if refund:
        yield Entry(loop_id, "refund", refund, "USD", receipt + ":refund")


# ------------------------------------------------------------- mobile apps (RevenueCat, local state)

BUSINESS_OUTCOMES = STATE / "marketing-metrics-daily" / "state" / "business-outcomes.jsonl"
MOBILE_APPS_PRODUCTS = ("anicca-ios", "honne-ai")
MOBILE_UNKNOWN_CURRENCY = "UNKNOWN"


def mobile_apps_entries(day: date, path: Path = BUSINESS_OUTCOMES, loop_id: str = "mobile-apps",
                        products: tuple[str, ...] = MOBILE_APPS_PRODUCTS, notes: dict | None = None):
    """Sum RevenueCat daily Revenue across ``products`` for ``day``; MRR per product goes in notes."""
    notes = notes if notes is not None else {}
    if not path.is_file():
        raise FileNotFoundError("mobile_apps_business_outcomes_missing")
    rows: dict[str, dict] = {}
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue  # a corrupt line leaves that product's day missing, not invented
            if row.get("business_date") == day.isoformat() and row.get("product_id") in products:
                rows[row["product_id"]] = row
    missing = [p for p in products if p not in rows]
    if missing:
        raise LookupError(f"mobile_apps_missing_business_date_row:{','.join(missing)}:{day.isoformat()}")
    mrr: dict[str, str] = {}
    for product_id in products:
        row = rows[product_id]
        rc = row.get("sources", {}).get("revenuecat", {})
        if rc.get("status") != "available":
            raise ValueError(f"mobile_apps_revenuecat_unavailable:{product_id}:{rc.get('reason')}")
        rc_data = rc.get("data") or {}
        charts = rc_data.get("charts") or {}
        revenue_metric = (charts.get("revenue") or {}).get("latest_complete", {}).get("Revenue")
        if not isinstance(revenue_metric, dict) or "value" not in revenue_metric:
            raise ValueError(f"mobile_apps_revenue_metric_missing:{product_id}")
        currency = rc_data.get("currency") or MOBILE_UNKNOWN_CURRENCY
        value = Decimal(str(revenue_metric["value"]))
        receipt = f"revenuecat:{product_id}:{row.get('snapshot_id', day.isoformat())}:revenue"
        if value:
            yield Entry(loop_id, "revenue", value, currency, receipt)
        mrr_metric = (charts.get("mrr") or {}).get("latest_complete", {}).get("MRR")
        if isinstance(mrr_metric, dict) and "value" in mrr_metric:
            mrr[product_id] = str(mrr_metric["value"])
            notes["mrr"] = mrr


# ---------------------------------------------------------------- agent-runner usage (model cost)

USAGE_CURRENCY = "USD_API_EQUIV"  # runner's provider_cost_usd is an API-price estimate, not a bill
# Deterministic usage-label -> Product Loop bookkeeping for labels that are not registry job ids.
USAGE_PREFIXES = (
    ("hf-gig-", "gig-coconala"), ("coconala", "gig-coconala"),
    ("lancers", "gig-lancers"), ("crowdworks", "gig-crowdworks"),
    ("writer", "writer"), ("article-", "writer"),
    ("affiliate", "affiliate"), ("alpaca", "investment"),
    ("x402", "agent-economy"), ("agent-economy", "agent-economy"), ("the402", "agent-economy"),
    ("job-search", "job-hunter"), ("mercor", "job-hunter"),
    ("fundraiser", "fundraiser"), ("connector", "connector"),
    ("life-manager-dev", "self-build"), ("life-manager-selfbuild", "self-build"),
    ("life-manager-recovery", "self-build"), ("self-improve", "self-build"),
    ("life-manager-anicca-", "mobile-apps"), ("life-manager-honne", "mobile-apps"),
    ("capafy", "capafy"), ("cfo", "cfo"), ("life-manager-cfo", "cfo"),
)


def usage_loop(label: str, job_map: dict[str, str]) -> str | None:
    if label in job_map:
        return job_map[label]
    return next((loop for prefix, loop in USAGE_PREFIXES if label.startswith(prefix)), None)


def usage_files(root: Path = Path("~/.local/state").expanduser()) -> list[Path]:
    return sorted(root.rglob("agent-usage.jsonl"))


def usage_entries(files: list[Path], day: date, job_map: dict[str, str], notes: dict):
    seen: set[str] = set()
    for path in files:
        with path.open() as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                    if not in_day(event["timestamp"], day):
                        continue
                except (ValueError, KeyError, TypeError):
                    notes["unparsed_lines"] = notes.get("unparsed_lines", 0) + 1
                    continue
                if event.get("event_id") in seen:
                    continue
                seen.add(event["event_id"])
                cost = event.get("provider_cost_usd")
                loop_id = usage_loop(str(event.get("loop", "")), job_map)
                if loop_id is None:
                    bucket = notes.setdefault("unattributed", {}).setdefault(
                        str(event.get("loop")), {"events": 0, USAGE_CURRENCY: Decimal(0)})
                    bucket["events"] += 1
                    bucket[USAGE_CURRENCY] += Decimal(str(cost or 0))
                    continue
                if cost is None:
                    missing = notes.setdefault("missing_cost_events", {})
                    missing[loop_id] = missing.get(loop_id, 0) + 1
                    continue
                yield Entry(loop_id, "cost", Decimal(str(cost)), USAGE_CURRENCY,
                            f"agent-usage:{event['event_id']}")


# ---------------------------------------------------------------- command


def collect(day: date, loops: list[dict]) -> list[SourceResult]:
    ids = [loop["id"] for loop in loops]
    job_map = {job: loop["id"] for loop in loops for job in loop["job_ids"]}
    sources = [
        run_source("alpaca", {("investment", k) for k in KINDS},
                   lambda: alpaca_entries(alpaca_activities(), day)),
        run_source("stripe", {("self-build", k) for k in KINDS},
                   lambda: stripe_entries(stripe_transactions(day))),
    ]
    pay_to, owned = x402_wallets()
    sources.append(run_source("x402-base", {("agent-economy", k) for k in KINDS},
                              lambda: x402_entries(day, BaseRpc(), pay_to, owned)))
    ledgers = marketplace_ledgers()
    for platform, loop_id in MARKETPLACE_LOOPS.items():
        covers = {(loop_id, "revenue"), (loop_id, "refund")}
        if platform in ledgers:
            sources.append(run_source(f"marketplace-{platform}", covers,
                                      lambda p=platform: marketplace_entries(p, ledgers[p], day)))
        else:
            sources.append(SourceResult(f"marketplace-{platform}", covers,
                                        error=f"marketplace-{platform}:no_payment_ledger_owner_writes"))
    sources.append(run_source("capafy", {("capafy", "revenue"), ("capafy", "refund")},
                              lambda: capafy_entries(day)))
    mobile_notes: dict = {}
    sources.append(run_source("mobile-apps", {("mobile-apps", "revenue")},
                              lambda: mobile_apps_entries(day, notes=mobile_notes), notes=mobile_notes))
    notes: dict = {}
    sources.append(run_source("agent-usage", {(i, "cost") for i in ids},
                              lambda: usage_entries(usage_files(), day, job_map, notes), notes=notes))
    return sources


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _b7_window(day: date, snapshot_at: str | None, trailing_start: str | None,
               now: datetime | None = None) -> tuple[str, str]:
    end = snapshot_at or _utc_text(now or datetime.now(timezone.utc))
    start = trailing_start or _utc_text(
        datetime.fromisoformat(end.replace("Z", "+00:00")) - timedelta(days=30)
    )
    return end, start


def _b7_table(day: date, projection: dict, *, snapshot_at: str, trailing_start: str) -> dict:
    return {
        "reporting_date": day.isoformat(),
        "timezone": "Asia/Tokyo",
        "snapshot_at": projection["snapshot_at"],
        "trailing_start": projection["trailing_start"],
        "economic_attribution": projection,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", help="Asia/Tokyo reporting day, default today")
    parser.add_argument("--snapshot-at", help="explicit B0 snapshot_at RFC3339 timestamp")
    parser.add_argument("--trailing-start", help="explicit B0 trailing_start RFC3339 timestamp")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    day = date.fromisoformat(args.date) if args.date else datetime.now(JST).date()
    snapshot_at, trailing_start = _b7_window(day, args.snapshot_at, args.trailing_start)
    try:
        projection = build_b7_projection(
            snapshot_at=snapshot_at, trailing_start=trailing_start,
        )
    except contract.ContractError as error:
        print(json.dumps({"status": "failed", "reason": error.code, "field": error.field}))
        return 1
    table = _b7_table(
        day, projection, snapshot_at=snapshot_at, trailing_start=trailing_start,
    )
    print(json.dumps(table, ensure_ascii=False, indent=1) if args.json else json.dumps(
        table, ensure_ascii=False, indent=1,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
