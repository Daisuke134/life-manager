#!/usr/bin/env python3
"""Product-scoped business outcome collector.

Provider failures are represented as unavailable/null. A numeric zero is emitted
only after a successful, product-scoped provider query.
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from decimal import Decimal, InvalidOperation
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gates"))
from product_router import canonical_product_id  # noqa: E402
DEFAULT_ENV = Path.home() / ".local" / "state" / "life-manager" / ".env"


def default_storage_paths(environment: dict[str, str] | None = None) -> tuple[Path, Path]:
    env = os.environ if environment is None else environment
    runtime_root = Path(env.get("LIFE_MANAGER_STATE_ROOT", str(ROOT)))
    return (
        runtime_root / "state" / "business-outcomes.jsonl",
        runtime_root / "evidence" / "business",
    )


DEFAULT_STATE, DEFAULT_EVIDENCE = default_storage_paths()

PRODUCTS = {
    "anicca-ios": {
        "asc_app_id": "6755129214",
        "revenuecat_app_id": "app511ef26659",
        "analytics": "mixpanel",
    },
    "honne-ai": {
        "asc_app_id": "6759667221",
        "revenuecat_app_id": "app3bbd298d22",
        "analytics": None,
    },
    "breath-reset": {
        "asc_app_id": "6760253231",
        "revenuecat_app_id": "app498e23effc",
        "analytics": None,
    },
    "sleep-ritual": {
        "asc_app_id": "6759916261",
        "revenuecat_app_id": "app92143da86e",
        "analytics": None,
    },
    "desk-stretch-timer": {
        "asc_app_id": "6760048397",
        "revenuecat_app_id": "appca8d955a75",
        "analytics": None,
    },
    "micro-mood": {
        "asc_app_id": "6759877003",
        "revenuecat_app_id": "appdda58236fa",
        "analytics": None,
    },
    "ebook-en": {"stripe_product_ids": ["prod_UQ2LTH66Rwict4"]},
    "ebook-ja": {"stripe_product_ids": ["prod_UQ2LrpVy4b1bAY"]},
}

RC_CHARTS = (
    "mrr",
    "actives",
    "trials",
    "revenue",
    "trials_new",
    "churn",
    "subscription_retention",
)

ASC_REPORTS = {
    "downloads": "App Downloads Standard",
    "discovery": "App Store Discovery and Engagement Standard",
    "purchases": "App Store Purchases Standard",
    "subscription_events": "App Store Subscription Event Report Standard",
    "subscription_state": "App Store Subscription State Report Standard",
}


def unavailable_source(reason: str, *, error: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "unavailable", "data": None, "reason": reason}
    if error:
        out["error"] = error[:240]
    return out


def available_source(data: Any, *, evidence_sha256: str | None = None) -> dict[str, Any]:
    out = {"status": "available", "data": data, "reason": None}
    if evidence_sha256:
        out["evidence_sha256"] = evidence_sha256
    return out


def revenuecat_app_filter(options: dict[str, Any], app_id: str) -> list[dict[str, Any]]:
    by_id = {entry.get("id"): entry for entry in options.get("filters", [])}
    dimension = "app_id" if "app_id" in by_id else (
        "app_config_id" if "app_config_id" in by_id else None
    )
    if dimension is None:
        raise ValueError("RevenueCat app filter is not offered by this chart")
    allowed = {item.get("id") for item in by_id[dimension].get("options", [])}
    if app_id not in allowed:
        raise ValueError(f"RevenueCat app {app_id} is not listed by chart options")
    return [{"name": dimension, "values": [app_id]}]


def _measure_name(measures: list[Any], index: int) -> str:
    if 0 <= index < len(measures):
        value = measures[index]
        if isinstance(value, dict):
            return str(value.get("id") or value.get("display_name") or index)
        return str(value)
    return str(index)


def _period_value(periods: list[Any], index: int) -> Any:
    if not 0 <= index < len(periods):
        return index
    value = periods[index]
    if isinstance(value, dict):
        return (
            value.get("date")
            or value.get("start_date")
            or value.get("display_name")
            or value.get("timestamp")
            or index
        )
    return value


def latest_complete_chart_points(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the latest complete value for every measure in a v3 chart.

    RevenueCat's current chart values are objects whose ``cohort`` indexes the
    period and whose ``measure`` indexes ``measures``.
    """
    measures = body.get("measures") or [{"id": "value"}]
    periods = body.get("periods") or []
    candidates: dict[str, list[dict[str, Any]]] = {}
    for value in body.get("values", []):
        if not isinstance(value, dict) or "value" not in value:
            continue
        if value.get("incomplete") is True:
            continue
        measure_index = int(value.get("measure", 0))
        cohort = value.get("cohort", value.get("period", 0))
        if not isinstance(cohort, int):
            continue
        name = _measure_name(measures, measure_index)
        candidates.setdefault(name, []).append({
            "value": value.get("value"),
            "period": _period_value(periods, cohort),
            "period_index": cohort,
            "incomplete": False,
        })
    return {
        name: max(points, key=lambda point: point["period_index"])
        for name, points in candidates.items()
    }


def sum_complete_chart_points(body: dict[str, Any], measure_name: str) -> float | None:
    """Sum every complete daily value for one measure across the queried window.

    A point-in-time measure (e.g. MRR, Active Subscriptions) wants
    ``latest_complete_chart_points``; a flow measure (e.g. Revenue) wants the
    window total, since RevenueCat's per-day values do not accumulate.
    Returns ``None`` only when the measure has no complete daily value at all.
    """
    measures = body.get("measures") or [{"id": "value"}]
    index = next(
        (i for i in range(len(measures)) if _measure_name(measures, i) == measure_name),
        None,
    )
    if index is None:
        return None
    total = 0.0
    seen = False
    for value in body.get("values", []):
        if not isinstance(value, dict) or "value" not in value:
            continue
        if value.get("incomplete") is True:
            continue
        if int(value.get("measure", 0)) != index:
            continue
        total += float(value.get("value") or 0)
        seen = True
    return total if seen else None


def parse_asc_tsv_gz(payload: bytes) -> list[dict[str, str]]:
    text = gzip.decompress(payload).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def _last_saturday_of_september(year: int) -> dt.date:
    last_day = dt.date(year, 9, 30)
    return last_day - dt.timedelta(days=(last_day.weekday() - 5) % 7)


def apple_finance_period_dates(report_month: str) -> tuple[str, str]:
    """Return the ASC fiscal-period bounds for a YYYY-PP finance report date.

    The 5-4-4 period sequence is inferred from official ASC FINANCE_DETAIL
    reads (2026-10 and 2026-12). Apple SEC filings establish the FY end and
    52/53-week rule. A downloaded report is still checked against these bounds.
    """
    try:
        year_text, period_text = report_month.split("-", 1)
        year, period = int(year_text), int(period_text)
    except (AttributeError, TypeError, ValueError):
        raise ValueError("finance_report_month_invalid") from None
    if len(year_text) != 4 or len(period_text) != 2 or not 1 <= period <= 12:
        raise ValueError("finance_report_month_invalid")

    fiscal_end = _last_saturday_of_september(year)
    prior_end = _last_saturday_of_september(year - 1)
    fiscal_start = prior_end + dt.timedelta(days=1)
    fiscal_days = (fiscal_end - fiscal_start).days + 1
    if fiscal_days not in {364, 371}:
        raise ValueError("apple_fiscal_year_length_invalid")

    period_weeks = [5, 4, 4] * 4
    if fiscal_days == 371:
        # SEC says the 53rd week is in Q1; assigning it to period 1 is an
        # inference, guarded by the report preamble bounds check on collection.
        period_weeks[0] += 1
    start = fiscal_start
    for index, weeks in enumerate(period_weeks, start=1):
        end = start + dt.timedelta(days=weeks * 7 - 1)
        if index == period:
            if end > fiscal_end:
                raise ValueError("apple_fiscal_period_out_of_year")
            return start.isoformat(), end.isoformat()
        start = end + dt.timedelta(days=1)
    raise ValueError("finance_report_month_invalid")


def latest_completed_apple_finance_month(as_of: dt.date) -> str:
    """Select the latest fiscal report period that has ended by ``as_of``."""
    if not isinstance(as_of, dt.date):
        raise ValueError("finance_as_of_date_invalid")
    candidates: list[tuple[dt.date, str]] = []
    for year in range(as_of.year - 1, as_of.year + 2):
        for period in range(1, 13):
            report_month = f"{year:04d}-{period:02d}"
            _, end_text = apple_finance_period_dates(report_month)
            end = dt.date.fromisoformat(end_text)
            if end <= as_of:
                candidates.append((end, report_month))
    if not candidates:
        raise ValueError("finance_completed_period_missing")
    return max(candidates)[1]


def _finance_report_date(value: str) -> str:
    value = str(value or "").strip()
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    except ValueError:
        try:
            return dt.date.fromisoformat(value).isoformat()
        except ValueError:
            raise ValueError("finance_report_date_invalid") from None


def parse_asc_finance_detail_tsv(payload: bytes | str) -> dict[str, Any]:
    """Parse one official ASC FINANCE_DETAIL TSV without retaining its preamble."""
    try:
        text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else str(payload)
    except UnicodeDecodeError:
        raise ValueError("finance_detail_encoding_invalid") from None
    lines = text.splitlines()
    required = {
        "Transaction Date", "Settlement Date", "Apple Identifier", "SKU",
        "Product Type Identifier", "Extended Partner Share",
        "Partner Share Currency", "Sale or Return",
    }
    period: dict[str, str] = {}
    header_index: int | None = None
    for index, line in enumerate(lines):
        fields = next(csv.reader([line], delimiter="\t"))
        if len(fields) == 2 and fields[0].strip() in {"Start Date", "End Date"}:
            key = "period_start" if fields[0].strip() == "Start Date" else "period_end"
            period[key] = _finance_report_date(fields[1])
        if required.issubset({field.strip() for field in fields}):
            header_index = index
            break
    if header_index is None:
        raise ValueError("finance_detail_header_missing")
    if set(period) != {"period_start", "period_end"}:
        raise ValueError("finance_detail_period_missing")
    if period["period_start"] > period["period_end"]:
        raise ValueError("finance_detail_period_invalid")

    rows = []
    detail_end = len(lines)
    summary_columns = {
        "country of sale", "partner share currency", "quantity", "extended partner share",
    }
    for index in range(header_index + 1, len(lines)):
        fields = {field.strip().casefold() for field in next(
            csv.reader([lines[index]], delimiter="\t")
        )}
        if summary_columns.issubset(fields) and "apple identifier" not in fields:
            detail_end = index
            break
    reader = csv.DictReader(
        io.StringIO("\n".join(lines[header_index:detail_end]), newline=""),
        delimiter="\t",
    )
    for raw in reader:
        if not raw or not any(value not in (None, "") for value in raw.values()):
            continue
        rows.append({
            "source_row_index": len(rows),
            "raw": {key: (value or "").strip() for key, value in raw.items() if key is not None},
        })
    return {**period, "rows": rows}


def normalize_asc_finance_rows(
    rows: list[dict[str, Any]],
    catalog_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve finance child IDs only by exact ASC record ID + product SKU."""
    app_products = {
        config["asc_app_id"]: product_id
        for product_id, config in PRODUCTS.items()
        if "asc_app_id" in config
    }
    by_product: dict[str, list[dict[str, Any]]] = {
        product_id: [] for product_id in PRODUCTS if "asc_app_id" in PRODUCTS[product_id]
    }
    indexed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in catalog_records:
        if not isinstance(record, dict):
            continue
        if record.get("record_type") not in {"subscription", "in_app_purchase"}:
            continue
        app_id = str(record.get("app_id") or "")
        record_id = str(record.get("record_id") or "")
        sku = str(record.get("sku") or "")
        product_id = app_products.get(app_id)
        if not product_id or not record_id or not sku:
            continue
        evidence = {
            "app_id": app_id, "record_type": record["record_type"],
            "record_id": record_id, "sku": sku,
            "name": str(record.get("name") or ""),
            "state": str(record.get("state") or ""),
        }
        collection = "subscriptions" if record["record_type"] == "subscription" else "in-app-purchases"
        indexed.setdefault((record_id, sku), []).append({
            **evidence,
            "product_id": product_id,
            "evidence_ref": f"appstoreconnect://{collection}/{record_id}",
            "evidence_sha256": _json_hash(evidence),
        })

    unassigned = []
    for entry in rows:
        raw = entry.get("raw") if isinstance(entry, dict) else None
        if not isinstance(raw, dict):
            unassigned.append({"source_row_index": None, "reason": "finance_row_invalid", "raw_row": raw})
            continue
        row_index = entry.get("source_row_index")
        apple_identifier = str(raw.get("Apple Identifier") or "").strip()
        sku = str(raw.get("SKU") or "").strip()
        matches = indexed.get((apple_identifier, sku), [])
        if len(matches) != 1:
            unassigned.append({
                "source_row_index": row_index,
                "reason": "catalog_ambiguous_match" if len(matches) > 1 else "catalog_no_exact_match",
                "raw_row": raw,
            })
            continue
        match = matches[0]
        by_product[match["product_id"]].append({
            "source_row_index": row_index,
            "apple_identifier": apple_identifier,
            "sku": sku,
            "parent_app_id": match["app_id"],
            "catalog_record_type": match["record_type"],
            "catalog_record_id": match["record_id"],
            "catalog_product_id": match["sku"],
            "catalog_evidence_ref": match["evidence_ref"],
            "catalog_evidence_sha256": match["evidence_sha256"],
            "partner_share_currency": str(raw.get("Partner Share Currency") or "").upper(),
            "extended_partner_share": str(raw.get("Extended Partner Share") or ""),
            "sale_or_return": str(raw.get("Sale or Return") or ""),
            "product_type_identifier": str(raw.get("Product Type Identifier") or ""),
            "transaction_date": _finance_report_date(raw.get("Transaction Date") or ""),
            "settlement_date": _finance_report_date(raw.get("Settlement Date") or ""),
            "raw_row": raw,
        })
    return {"by_product": by_product, "unassigned_rows": unassigned}


def _run_asc_json(env: dict[str, str], args: list[str], *, timeout: int = 120) -> dict[str, Any]:
    asc_bin = env.get("ASC_BIN") or shutil.which(
        "asc", path=env.get("PATH") or os.environ.get("PATH")
    )
    if not asc_bin:
        raise RuntimeError("asc_cli_missing")
    command_env = {**os.environ, **env, "ASC_BYPASS_KEYCHAIN": "true", "ASC_TIMEOUT": "90s"}
    try:
        completed = subprocess.run(
            [asc_bin, *args], capture_output=True, text=True, timeout=timeout,
            env=command_env, check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("asc_cli_timeout") from None
    if completed.returncode != 0:
        error_text = (completed.stderr or "").lower()
        if "there were no sales for the date specified" in error_text:
            raise RuntimeError("finance_report_no_sales")
        raise RuntimeError(f"asc_cli_failed:{args[0] if args else 'command'}")
    try:
        result = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        raise RuntimeError("asc_cli_json_invalid") from None
    if not isinstance(result, dict):
        raise RuntimeError("asc_cli_json_invalid")
    return result


def _catalog_rows(body: dict[str, Any], app_id: str, record_type: str) -> list[dict[str, str]]:
    rows = body.get("data")
    if not isinstance(rows, list):
        raise ValueError("asc_catalog_data_invalid")
    catalog = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("attributes"), dict):
            raise ValueError("asc_catalog_row_invalid")
        attributes = row["attributes"]
        record_id = str(row.get("id") or "")
        sku = str(attributes.get("productId") or "")
        if not record_id or not sku:
            continue
        catalog.append({
            "app_id": app_id,
            "record_type": record_type,
            "record_id": record_id,
            "sku": sku,
            "name": str(attributes.get("name") or ""),
            "state": str(attributes.get("state") or ""),
        })
    return catalog


def _write_private_evidence(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashlib.sha256(payload).hexdigest():
            raise ValueError("asc_finance_evidence_conflict")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_bytes(payload)
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def collect_asc_financial_sources(
    env: dict[str, str],
    report_month: str,
    products: list[str] | tuple[str, ...],
    evidence_root: Path,
    *,
    run_command=None,
) -> dict[str, dict[str, Any]]:
    """Download one final ASC Finance Detail report and map rows to exact product catalogs."""
    runner = run_command or _run_asc_json
    products = [product for product in products if product in PRODUCTS and "asc_app_id" in PRODUCTS[product]]
    if not products:
        return {}
    try:
        expected_period = apple_finance_period_dates(report_month)
        vendor = str(env.get("ASC_VENDOR_NUMBER") or "").strip()
        if not vendor or not vendor.isdigit():
            raise ValueError("asc_vendor_missing")
        with tempfile.TemporaryDirectory(
            prefix="lm-asc-finance-", dir=str(Path(tempfile.gettempdir()).resolve()),
        ) as temporary_directory:
            report_path = Path(temporary_directory) / "finance-detail.tsv"
            metadata = runner(env, [
                "finance", "reports", "--vendor", vendor,
                "--report-type", "FINANCE_DETAIL", "--region", "Z1",
                "--date", report_month, "--decompress", "--output", str(report_path),
                "--output-format", "json",
            ], timeout=120)
            if (
                metadata.get("reportType") != "FINANCE_DETAIL"
                or metadata.get("regionCode") != "Z1"
                or metadata.get("reportDate") != report_month
                or not report_path.is_file()
            ):
                raise ValueError("finance_report_identity_invalid")
            raw_report = report_path.read_bytes()
    except RuntimeError as error:
        reason = (
            "finance_report_no_sales" if str(error) == "finance_report_no_sales"
            else "provider_query_failed"
        )
        return {product: unavailable_source(reason, error=str(error)) for product in products}
    except (OSError, TypeError, ValueError) as error:
        return {
            product: unavailable_source("provider_query_failed", error=f"{type(error).__name__}: {error}")
            for product in products
        }

    report_sha256 = hashlib.sha256(raw_report).hexdigest()
    try:
        parsed = parse_asc_finance_detail_tsv(raw_report)
        if (parsed["period_start"], parsed["period_end"]) != expected_period:
            raise ValueError("finance_period_mismatch")
    except (KeyError, TypeError, ValueError) as error:
        return {
            product: unavailable_source("provider_query_failed", error=f"{type(error).__name__}: {error}")
            for product in products
        }

    catalog_cache: dict[tuple[str, str], list[dict[str, str]] | None] = {}
    catalog_records: list[dict[str, str]] = []
    catalog_errors: list[dict[str, str]] = []
    products_by_app_id = {
        PRODUCTS[product]["asc_app_id"]: product
        for product in PRODUCTS if "asc_app_id" in PRODUCTS[product]
    }
    for entry in parsed["rows"]:
        raw = entry["raw"]
        apple_identifier = str(raw.get("Apple Identifier") or "").strip()
        sku = str(raw.get("SKU") or "").strip()
        if not apple_identifier or not sku:
            continue
        found = False
        for product in products_by_app_id.values():
            app_id = PRODUCTS[product]["asc_app_id"]
            for record_type, command in (
                ("subscription", "subscriptions"),
                ("in_app_purchase", "iap"),
            ):
                cache_key = (app_id, record_type)
                if cache_key not in catalog_cache:
                    try:
                        body = runner(env, [
                            command, "list", "--app", app_id, "--paginate", "--output", "json",
                        ], timeout=120)
                        catalog_cache[cache_key] = _catalog_rows(body, app_id, record_type)
                        catalog_records.extend(catalog_cache[cache_key] or [])
                    except (OSError, RuntimeError, TypeError, ValueError) as error:
                        catalog_cache[cache_key] = None
                        catalog_errors.append({
                            "app_id": app_id, "record_type": record_type,
                            "error_class": type(error).__name__,
                        })
                records = catalog_cache[cache_key]
                if records and any(
                    record["record_id"] == apple_identifier and record["sku"] == sku
                    for record in records
                ):
                    found = True
                    break
            if found:
                break
    mapped = normalize_asc_finance_rows(parsed["rows"], catalog_records)
    if catalog_errors:
        for row in mapped["unassigned_rows"]:
            if row["reason"] == "catalog_no_exact_match":
                row["reason"] = "catalog_incomplete"

    unassigned_sha256 = _json_hash(mapped["unassigned_rows"])
    report_id = f"finance-{report_month}-Z1"
    report_content = {
        "report_id": report_id,
        "report_status": "final",
        "period_start": parsed["period_start"],
        "period_end": parsed["period_end"],
        "unassigned_row_count": len(mapped["unassigned_rows"]),
        "unassigned_rows_sha256": unassigned_sha256,
        "rows": sorted(
            [row for rows in mapped["by_product"].values() for row in rows],
            key=lambda row: row["source_row_index"],
        ),
    }
    content_sha256 = _json_hash(report_content)
    mapping_evidence = {
        "report_id": report_id,
        "report_sha256": report_sha256,
        "content_sha256": content_sha256,
        "catalog_records": sorted(catalog_records, key=lambda row: (
            row["app_id"], row["record_type"], row["record_id"], row["sku"],
        )),
        "catalog_errors": catalog_errors,
        "unassigned_rows": mapped["unassigned_rows"],
    }
    mapping_sha256 = _json_hash(mapping_evidence)
    evidence_dir = Path(evidence_root) / "asc-finance" / report_id
    report_evidence = evidence_dir / f"report-{report_sha256}.tsv"
    mapping_evidence_path = evidence_dir / f"mapping-{mapping_sha256}.json"
    try:
        _write_private_evidence(report_evidence, raw_report)
        _write_private_evidence(
            mapping_evidence_path,
            json.dumps(mapping_evidence, ensure_ascii=False, sort_keys=True).encode(),
        )
    except OSError as error:
        return {
            product: unavailable_source("evidence_write_failed", error=type(error).__name__)
            for product in products
        }

    unassigned_evidence_ref = f"appstoreconnect://financial-report-mappings/{report_id}/{mapping_sha256}"
    sources = {}
    for product in products:
        data = {
            "report_id": report_id,
            "report_sha256": report_sha256,
            "content_sha256": content_sha256,
            "report_status": "final",
            "app_id": PRODUCTS[product]["asc_app_id"],
            "period_start": parsed["period_start"],
            "period_end": parsed["period_end"],
            "rows": mapped["by_product"].get(product, []),
            "unassigned_row_count": len(mapped["unassigned_rows"]),
            "unassigned_rows_sha256": unassigned_sha256,
            "report_evidence_ref": f"appstoreconnect://financial-reports/{report_id}/{report_sha256}",
            "unassigned_evidence_ref": unassigned_evidence_ref,
        }
        sources[product] = available_source(data, evidence_sha256=_json_hash(data))
    return sources


def _required_columns(rows: list[dict[str, str]], required: set[str]) -> None:
    columns = set(rows[0]) if rows else set()
    missing = sorted(required - columns)
    if missing:
        raise ValueError("missing ASC columns: " + ", ".join(missing))


def _integer(value: str | int | None) -> int:
    if value in (None, ""):
        return 0
    return int(str(value).replace(",", ""))


def summarize_asc_downloads(rows: list[dict[str, str]]) -> dict[str, Any]:
    _required_columns(rows, {"Date", "Download Type", "Source Type", "Counts"})
    mapping = {
        "First-time download": "first_time_downloads",
        "Redownload": "redownloads",
        "Auto-update": "auto_updates",
        "Manual update": "manual_updates",
        "Restore": "restores",
    }
    totals = {field: 0 for field in mapping.values()}
    by_source: dict[str, dict[str, int]] = {}
    for row in rows:
        kind = row["Download Type"]
        if kind not in mapping:
            continue
        field = mapping[kind]
        count = _integer(row["Counts"])
        totals[field] += count
        source = row["Source Type"] or "Unknown"
        by_source.setdefault(source, {name: 0 for name in mapping.values()})
        by_source[source][field] += count
    return {**totals, "by_source": by_source, "row_count": len(rows)}


def summarize_asc_table(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Summarize an aggregate ASC table without discarding its schema.

    ASC analytics rows contain no person-level records. We retain the exact
    headers, row count, date bounds, and totals for numeric measure columns.
    Dimension combinations remain in the evidence file, not the compact state.
    """
    if not rows:
        return {"row_count": 0, "columns": [], "date_min": None, "date_max": None,
                "numeric_totals": {}}
    columns = list(rows[0])
    date_column = next((name for name in columns if name.lower() in {
        "date", "download date", "event date"
    }), None)
    dates = sorted(row.get(date_column, "") for row in rows) if date_column else []
    totals: dict[str, Decimal] = {}
    for column in columns:
        values: list[Decimal] = []
        for row in rows:
            raw = (row.get(column) or "").replace(",", "").strip()
            if not raw or raw.endswith("%"):
                continue
            try:
                values.append(Decimal(raw))
            except InvalidOperation:
                values = []
                break
        if values:
            totals[column] = sum(values, Decimal(0))
    return {
        "row_count": len(rows),
        "columns": columns,
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "numeric_totals": {
            key: int(value) if value == value.to_integral() else float(value)
            for key, value in totals.items()
        },
    }


def summarize_asc_sales(rows: list[dict[str, str]], apple_identifier: str) -> dict[str, Any]:
    """Summarize one day's ASC Sales Report rows for one app.

    Per Apple's Sales and Trends report reference, ``Developer Proceeds`` is
    the per-unit proceeds amount in ``Currency of Proceeds``; a row's total is
    ``Units * Developer Proceeds``. An empty account-wide report (no sales
    activity anywhere that day) is a successful zero, not a schema failure.
    """
    if rows:
        _required_columns(rows, {"Apple Identifier", "Units", "Developer Proceeds"})
    matched = [row for row in rows if row.get("Apple Identifier") == apple_identifier]
    units = 0
    proceeds: dict[str, Decimal] = {}
    for row in matched:
        row_units = _integer(row.get("Units"))
        units += row_units
        currency = (row.get("Currency of Proceeds") or "").strip() or "unknown"
        try:
            per_unit = Decimal((row.get("Developer Proceeds") or "0").strip())
        except InvalidOperation:
            continue
        proceeds[currency] = proceeds.get(currency, Decimal(0)) + per_unit * row_units
    return {
        "apple_identifier": apple_identifier,
        "units": units,
        "proceeds": {key: float(value) for key, value in sorted(proceeds.items())},
        "row_count": len(matched),
    }


def summarize_stripe_sessions(
    sessions: Iterable[dict[str, Any]], product_ids: set[str]
) -> dict[str, Any]:
    sessions = list(sessions)
    seen: set[str] = set()
    for session in sessions:
        session_id = session.get("id")
        if session_id in seen:
            raise ValueError(f"duplicate Stripe session: {session_id}")
        seen.add(session_id)
    matched: list[str] = []
    gross: dict[str, int] = {}
    refunded: dict[str, int] = {}
    for session in sessions:
        session_id = session.get("id")
        products = {
            (item.get("price") or {}).get("product")
            for item in (session.get("line_items") or {}).get("data", [])
        }
        if not products.intersection(product_ids) or session.get("payment_status") != "paid":
            continue
        matched.append(str(session_id))
        currency = str(session.get("currency") or "unknown")
        gross[currency] = gross.get(currency, 0) + int(session.get("amount_total") or 0)
        payment_intent = session.get("payment_intent")
        charge = payment_intent.get("latest_charge") if isinstance(payment_intent, dict) else None
        if not isinstance(charge, dict) or "amount_refunded" not in charge:
            raise ValueError(f"Stripe refund expansion missing: {session_id}")
        refunded[currency] = refunded.get(currency, 0) + int(charge["amount_refunded"] or 0)
    currencies = set(gross) | set(refunded)
    return {
        "paid_orders": len(matched),
        "gross_minor": gross,
        "refunded_minor": refunded,
        "net_minor": {
            currency: gross.get(currency, 0) - refunded.get(currency, 0)
            for currency in sorted(currencies)
        },
        "queried_product_ids": sorted(product_ids),
        "matched_session_ids": sorted(matched),
    }


def summarize_mixpanel_export(lines: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in lines:
        if not line.strip():
            continue
        event = json.loads(line).get("event")
        if event:
            counts[str(event)] = counts.get(str(event), 0) + 1
    return dict(sorted(counts.items()))


def validate_snapshots(rows: list[dict[str, Any]], products: set[str]) -> None:
    seen: set[str] = set()
    for row in rows:
        product_id = canonical_product_id(row.get("product_id"))
        if product_id not in products:
            raise ValueError(f"unknown product: {row.get('product_id')}")
        snapshot_id = f"{product_id}:{row.get('business_date')}"
        if snapshot_id in seen:
            raise ValueError(f"duplicate snapshot: {snapshot_id}")
        seen.add(snapshot_id)
        for name, source in (row.get("sources") or {}).items():
            if source.get("status") not in {"available", "unavailable"}:
                raise ValueError(f"invalid source status: {name}")
            if source.get("status") == "unavailable" and source.get("data") is not None:
                raise ValueError(f"unavailable source has data: {name}")


def verify_gate5_snapshots(rows: list[dict[str, Any]], business_date: str) -> dict[str, Any]:
    selected = [row for row in rows if row.get("business_date") == business_date]
    validate_snapshots(selected, set(PRODUCTS))
    by_product = {row["product_id"]: row for row in selected}
    if set(by_product) != set(PRODUCTS) or len(selected) != len(PRODUCTS):
        raise ValueError(f"Gate 5 requires exactly {len(PRODUCTS)} product snapshots")
    unavailable: list[dict[str, str]] = []
    for product_id, config in PRODUCTS.items():
        sources = by_product[product_id]["sources"]
        for source_name, source in sources.items():
            if source["status"] == "unavailable":
                unavailable.append({
                    "product_id": product_id,
                    "source": source_name,
                    "reason": source.get("reason") or "unspecified",
                })
        if "revenuecat_app_id" in config:
            revenuecat = sources.get("revenuecat")
            asc = sources.get("app_store_connect")
            if not revenuecat or revenuecat["status"] != "available":
                raise ValueError(f"{product_id} RevenueCat unavailable")
            if revenuecat["data"].get("app_id") != config["revenuecat_app_id"]:
                raise ValueError(f"{product_id} RevenueCat app mismatch")
            if not asc or asc["status"] != "available":
                raise ValueError(f"{product_id} ASC unavailable")
            if asc["data"].get("app_id") != config["asc_app_id"]:
                raise ValueError(f"{product_id} ASC app mismatch")
            downloads = asc["data"].get("reports", {}).get("downloads", {})
            if downloads.get("status") != "available":
                raise ValueError(f"{product_id} ASC downloads unavailable")
            download_data = downloads["data"]
            if "installs" in download_data:
                raise ValueError(f"{product_id} contains ambiguous installs")
            for field in (
                "first_time_downloads", "redownloads", "auto_updates",
                "manual_updates", "restores",
            ):
                if not isinstance(download_data.get(field), int):
                    raise ValueError(f"{product_id} missing separated download field: {field}")
        else:
            stripe = sources.get("stripe")
            if not stripe or stripe["status"] != "available":
                raise ValueError(f"{product_id} Stripe unavailable")
            data = stripe["data"]
            if sorted(data.get("queried_product_ids", [])) != sorted(config["stripe_product_ids"]):
                raise ValueError(f"{product_id} Stripe product mismatch")
            for field in ("paid_orders", "gross_minor", "refunded_minor", "net_minor"):
                if field not in data:
                    raise ValueError(f"{product_id} missing Stripe field: {field}")
    return {
        "gate_pass": True,
        "business_date": business_date,
        "products_verified": len(by_product),
        "unavailable_sources": sorted(
            unavailable, key=lambda item: (item["product_id"], item["source"])
        ),
    }


def load_env(path: Path = DEFAULT_ENV) -> dict[str, str]:
    env = dict(os.environ)
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip())
    return env


def http_json(
    url: str,
    headers: dict[str, str],
    *,
    timeout: int = 20,
) -> dict[str, Any]:
    with urllib.request.urlopen(
        urllib.request.Request(url, headers=headers), timeout=timeout
    ) as response:
        return json.load(response)


def _http_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    with urllib.request.urlopen(
        urllib.request.Request(url, headers=headers or {}), timeout=20
    ) as response:
        return response.read()


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def revenuecat_products(env: dict[str, str]) -> dict[str, list[str]]:
    project = env["REVENUECAT_PROJECT_ID"]
    headers = {"Authorization": "Bearer " + env["REVENUECAT_V2_SECRET_KEY"]}
    body = http_json(
        f"https://api.revenuecat.com/v2/projects/{project}/products?limit=100",
        headers,
    )
    out: dict[str, list[str]] = {}
    for product in body.get("items", []):
        app_id = product.get("app_id") or (product.get("app") or {}).get("id")
        if app_id and product.get("id"):
            out.setdefault(app_id, []).append(product["id"])
    return {key: sorted(value) for key, value in out.items()}


def _asc_headers(env: dict[str, str]) -> dict[str, str]:
    import jwt

    now = int(time.time())
    token = jwt.encode(
        {
            "iss": env["ASC_ISSUER_ID"],
            "iat": now,
            "exp": now + 600,
            "aud": "appstoreconnect-v1",
        },
        Path(env["ASC_KEY_PATH"]).read_text(),
        algorithm="ES256",
        headers={"kid": env["ASC_KEY_ID"], "typ": "JWT"},
    )
    return {"Authorization": "Bearer " + token}


def _asc_get(path_or_url: str, headers: dict[str, str]) -> dict[str, Any]:
    if path_or_url.startswith("http"):
        url = path_or_url
    else:
        url = "https://api.appstoreconnect.apple.com/v1" + path_or_url
    return http_json(url, headers)


def _latest_asc_instance(instances: list[dict[str, Any]]) -> dict[str, Any]:
    if not instances:
        raise ValueError("ASC report has no instances")
    granularity_rank = {"DAILY": 3, "WEEKLY": 2, "MONTHLY": 1}
    return max(
        instances,
        key=lambda item: (
            item.get("attributes", {}).get("processingDate", ""),
            granularity_rank.get(
                item.get("attributes", {}).get("granularity", ""), 0
            ),
        ),
    )


def collect_asc(
    env: dict[str, str],
    app_id: str,
    evidence_dir: Path,
) -> dict[str, Any]:
    headers = _asc_headers(env)
    requests = _asc_get(
        f"/apps/{app_id}/analyticsReportRequests?limit=200", headers
    ).get("data", [])
    active = [
        item for item in requests
        if not item.get("attributes", {}).get("stoppedDueToInactivity")
    ]
    ongoing = [
        item for item in active
        if item.get("attributes", {}).get("accessType") == "ONGOING"
    ]
    candidates = ongoing or active
    if not candidates:
        raise ValueError(f"ASC app {app_id} has no active analytics request")
    request = candidates[-1]
    reports = _asc_get(
        f"/analyticsReportRequests/{request['id']}/reports?limit=200", headers
    ).get("data", [])
    by_name = {item.get("attributes", {}).get("name"): item for item in reports}
    result: dict[str, Any] = {
        "app_id": app_id,
        "request_id": request["id"],
        "access_type": request.get("attributes", {}).get("accessType"),
        "reports": {},
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for key, name in ASC_REPORTS.items():
        report = by_name.get(name)
        if not report:
            result["reports"][key] = unavailable_source("report_not_offered")
            continue
        try:
            result["reports"][key] = _collect_asc_report(
                app_id, key, name, report, headers, evidence_dir
            )
        except Exception as error:
            # One report type (e.g. Purchases/Subscription Events) can legitimately have
            # zero instances when an app has no chargeable events yet. That must not
            # discard the other reports (downloads, discovery, ...) that did succeed.
            reason = "no_instances" if "no instances" in str(error) else "report_query_failed"
            result["reports"][key] = unavailable_source(
                reason, error=f"{type(error).__name__}: {error}"
            )
    return result


def _collect_asc_report(
    app_id: str,
    key: str,
    name: str,
    report: dict[str, Any],
    headers: dict[str, str],
    evidence_dir: Path,
) -> dict[str, Any]:
    instances = _asc_get(
        f"/analyticsReports/{report['id']}/instances?limit=200", headers
    ).get("data", [])
    instance = _latest_asc_instance(instances)
    segments = _asc_get(
        f"/analyticsReportInstances/{instance['id']}/segments?limit=200",
        headers,
    ).get("data", [])
    rows: list[dict[str, str]] = []
    segment_hashes: list[str] = []
    for segment in segments:
        attributes = segment.get("attributes", {})
        payload = _http_bytes(attributes["url"])
        expected_size = attributes.get("sizeInBytes")
        if expected_size is not None and len(payload) != int(expected_size):
            raise ValueError(f"ASC segment size mismatch: {segment['id']}")
        expected_md5 = attributes.get("checksum")
        actual_md5 = hashlib.md5(payload).hexdigest()
        if expected_md5 and actual_md5 != expected_md5:
            raise ValueError(f"ASC segment checksum mismatch: {segment['id']}")
        rows.extend(parse_asc_tsv_gz(payload))
        segment_hashes.append(hashlib.sha256(payload).hexdigest())
    compact = (
        summarize_asc_downloads(rows)
        if key == "downloads" else summarize_asc_table(rows)
    )
    evidence = {
        "app_id": app_id,
        "report_name": name,
        "processing_date": instance.get("attributes", {}).get("processingDate"),
        "granularity": instance.get("attributes", {}).get("granularity"),
        "segment_sha256": segment_hashes,
        "rows": rows,
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{app_id}-{key}.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    )
    return available_source(
        {
            **compact,
            "processing_date": evidence["processing_date"],
            "granularity": evidence["granularity"],
            "evidence_path": str(evidence_path),
        },
        evidence_sha256=_json_hash(evidence),
    )


def collect_asc_sales(
    env: dict[str, str],
    app_id: str,
    business_date: str,
    evidence_dir: Path,
) -> dict[str, Any]:
    """Fetch one day's account-wide ASC Sales Report and scope it to one app.

    The Sales Reports API (distinct from Analytics Reports) returns every app
    under the vendor in one gzipped TSV; ``app_id`` here is the numeric ASC
    "Apple Identifier", used to filter rows to this product.
    """
    headers = {**_asc_headers(env), "Accept": "application/a-gzip"}
    query = urllib.parse.urlencode({
        "filter[frequency]": "DAILY",
        "filter[reportDate]": business_date,
        "filter[reportSubType]": "SUMMARY",
        "filter[reportType]": "SALES",
        "filter[vendorNumber]": env["ASC_VENDOR_NUMBER"],
        "filter[version]": "1_1",
    })
    payload = _http_bytes(
        "https://api.appstoreconnect.apple.com/v1/salesReports?" + query, headers
    )
    rows = parse_asc_tsv_gz(payload)
    compact = summarize_asc_sales(rows, app_id)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence = {"app_id": app_id, "business_date": business_date, "rows": rows}
    evidence_path = evidence_dir / f"{app_id}-sales-{business_date}.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return {**compact, "business_date": business_date, "evidence_path": str(evidence_path)}, evidence


def collect_revenuecat(
    env: dict[str, str],
    app_id: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    project = env["REVENUECAT_PROJECT_ID"]
    headers = {"Authorization": "Bearer " + env["REVENUECAT_V2_SECRET_KEY"]}
    base = f"https://api.revenuecat.com/v2/projects/{project}/charts"
    result: dict[str, Any] = {"app_id": app_id, "charts": {}}
    for chart in RC_CHARTS:
        options = http_json(f"{base}/{chart}/options", headers)
        filters = revenuecat_app_filter(options, app_id)
        query = urllib.parse.urlencode({
            "start_date": start_date,
            "end_date": end_date,
            "resolution": "0",
            "filters": json.dumps(filters, separators=(",", ":")),
        })
        body = http_json(f"{base}/{chart}?{query}", headers)
        result["charts"][chart] = {
            "latest_complete": latest_complete_chart_points(body),
            "resolution": body.get("resolution"),
            "start_date": body.get("start_date"),
            "end_date": body.get("end_date"),
            "evidence_sha256": _json_hash(body),
        }
        if chart == "revenue":
            # Revenue is a flow metric: the queried window is exactly the
            # report's 28-day window (see collect_snapshot), so summing every
            # complete daily point gives the window total, not RevenueCat's
            # single latest per-day value.
            result["charts"][chart]["window_sum"] = sum_complete_chart_points(body, "Revenue")
    products = revenuecat_products(env).get(app_id, [])
    if products:
        chart = "conversion_to_paying"
        options = http_json(f"{base}/{chart}/options", headers)
        product_option = next(
            (item for item in options.get("filters", []) if item.get("id") == "product_id"),
            None,
        )
        allowed = {item.get("id") for item in (product_option or {}).get("options", [])}
        safe_products = [item for item in products if item in allowed]
        if safe_products:
            query = urllib.parse.urlencode({
                "start_date": start_date,
                "end_date": end_date,
                "resolution": "0",
                "filters": json.dumps(
                    [{"name": "product_id", "values": safe_products}],
                    separators=(",", ":"),
                ),
            })
            body = http_json(f"{base}/{chart}?{query}", headers)
            result["charts"][chart] = {
                "latest_complete": latest_complete_chart_points(body),
                "product_ids": safe_products,
                "evidence_sha256": _json_hash(body),
            }
        else:
            result["charts"][chart] = unavailable_source("products_not_offered_by_chart")
    else:
        result["charts"]["conversion_to_paying"] = unavailable_source("no_app_products")
    return result


def _stripe_headers(env: dict[str, str]) -> dict[str, str]:
    token = base64.b64encode((env["STRIPE_SECRET_KEY"] + ":").encode()).decode()
    return {"Authorization": "Basic " + token}


def stripe_session_query(since: int, until: int) -> str:
    if until <= since:
        raise ValueError("Stripe query end must be after start")
    return urllib.parse.urlencode([
        ("limit", "100"),
        ("created[gte]", str(since)),
        ("created[lt]", str(until)),
        ("expand[]", "data.line_items"),
        ("expand[]", "data.payment_intent.latest_charge"),
    ])


def collect_stripe_sessions(
    env: dict[str, str], product_ids: set[str], since: int, until: int
) -> dict[str, Any]:
    query = stripe_session_query(since, until)
    body = http_json(
        "https://api.stripe.com/v1/checkout/sessions?" + query,
        _stripe_headers(env),
    )
    if body.get("has_more"):
        raise ValueError("Stripe result exceeded 100 sessions; pagination required")
    return summarize_stripe_sessions(body.get("data", []), product_ids)


def collect_mixpanel(
    env: dict[str, str], start_date: str, end_date: str
) -> dict[str, Any]:
    token = base64.b64encode((env["MIXPANEL_API_SECRET"] + ":").encode()).decode()
    query = urllib.parse.urlencode({"from_date": start_date, "to_date": end_date})
    request = urllib.request.Request(
        "https://data.mixpanel.com/api/2.0/export/?" + query,
        headers={"Authorization": "Basic " + token},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        lines = response.read().decode("utf-8").splitlines()
    return {"event_counts": summarize_mixpanel_export(lines), "rows": len(lines)}


def collect_snapshot(
    env: dict[str, str],
    product_id: str,
    business_date: str,
) -> dict[str, Any]:
    config = PRODUCTS[product_id]
    sources: dict[str, Any] = {}
    if "revenuecat_app_id" in config:
        # 28-day inclusive window: matches the "revenue_28d" figure in the owner report.
        start = (dt.date.fromisoformat(business_date) - dt.timedelta(days=27)).isoformat()
        try:
            data = collect_revenuecat(
                env, config["revenuecat_app_id"], start, business_date
            )
            sources["revenuecat"] = available_source(data, evidence_sha256=_json_hash(data))
        except Exception as error:
            sources["revenuecat"] = unavailable_source(
                "provider_query_failed", error=f"{type(error).__name__}: {error}"
            )
        try:
            asc = collect_asc(
                env,
                config["asc_app_id"],
                DEFAULT_EVIDENCE / business_date / product_id,
            )
            sources["app_store_connect"] = available_source(
                asc, evidence_sha256=_json_hash(asc)
            )
        except Exception as error:
            sources["app_store_connect"] = unavailable_source(
                "provider_query_failed", error=f"{type(error).__name__}: {error}"
            )
        try:
            sales, sales_evidence = collect_asc_sales(
                env,
                config["asc_app_id"],
                business_date,
                DEFAULT_EVIDENCE / business_date / product_id,
            )
            sources["app_store_sales"] = available_source(
                sales, evidence_sha256=_json_hash(sales_evidence)
            )
        except Exception as error:
            sources["app_store_sales"] = unavailable_source(
                "provider_query_failed", error=f"{type(error).__name__}: {error}"
            )
        if config.get("analytics") == "mixpanel":
            try:
                sources["product_analytics"] = available_source(
                    collect_mixpanel(env, business_date, business_date)
                )
            except Exception as error:
                sources["product_analytics"] = unavailable_source(
                    "provider_query_failed", error=f"{type(error).__name__}: {error}"
                )
        else:
            sources["product_analytics"] = unavailable_source(
                "no_verified_readable_funnel"
            )
        sources["posthog"] = unavailable_source("missing_project_read_credential")
    else:
        since = int(
            dt.datetime.combine(
                dt.date.fromisoformat(business_date),
                dt.time.min,
                tzinfo=dt.timezone.utc,
            ).timestamp()
        )
        until = int(
            dt.datetime.combine(
                dt.date.fromisoformat(business_date) + dt.timedelta(days=1),
                dt.time.min,
                tzinfo=dt.timezone.utc,
            ).timestamp()
        )
        try:
            sources["stripe"] = available_source(
                collect_stripe_sessions(
                    env, set(config["stripe_product_ids"]), since, until
                )
            )
        except Exception as error:
            sources["stripe"] = unavailable_source(
                "provider_query_failed", error=f"{type(error).__name__}: {error}"
            )
        sources["kdp"] = unavailable_source("not_authenticated")
        sources["gumroad"] = unavailable_source("not_configured")
    return {
        "schema_version": 1,
        "snapshot_id": f"{product_id}:{business_date}",
        "product_id": product_id,
        "business_date": business_date,
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sources": sources,
    }


def upsert_snapshots(path: Path, new_rows: list[dict[str, Any]]) -> int:
    old: list[dict[str, Any]] = []
    if path.exists():
        old = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def logical_id(row: dict[str, Any]) -> str:
        return f"{canonical_product_id(row.get('product_id'))}:{row.get('business_date')}"

    by_id = {logical_id(row): row for row in old}
    before = len(by_id)
    for row in new_rows:
        by_id[logical_id(row)] = row
    rows = sorted(by_id.values(), key=lambda row: row["snapshot_id"])
    validate_snapshots(rows, set(PRODUCTS))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    )
    os.replace(temp, path)
    return len(by_id) - before


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=(dt.date.today() - dt.timedelta(days=1)).isoformat())
    parser.add_argument("--state", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--products", default=",".join(PRODUCTS))
    args = parser.parse_args()
    selected = [item for item in args.products.split(",") if item]
    unknown = sorted(set(selected) - set(PRODUCTS))
    if unknown:
        parser.error("unknown products: " + ", ".join(unknown))
    env = load_env()
    default_state, default_evidence = default_storage_paths(env)
    state_path = args.state or default_state
    evidence_root = args.evidence or default_evidence
    mobile_products = [
        product for product, config in PRODUCTS.items() if "asc_app_id" in config
    ]
    finance_sources: dict[str, dict[str, Any]] = {}
    selected_mobile = [product for product in selected if product in mobile_products]
    finance_report_month = env.get("ASC_FINANCE_REPORT_DATE")
    if selected_mobile:
        try:
            finance_report_month = finance_report_month or latest_completed_apple_finance_month(
                dt.date.fromisoformat(args.date)
            )
            finance_sources = collect_asc_financial_sources(
                env, finance_report_month, mobile_products,
                evidence_root,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            finance_sources = {
                product: unavailable_source(
                    "provider_query_failed", error=f"{type(error).__name__}: {error}"
                )
                for product in mobile_products
            }
    rows = [collect_snapshot(env, product, args.date) for product in selected]
    for row in rows:
        finance_source = finance_sources.get(row["product_id"])
        if finance_source is not None:
            row["sources"]["app_store_financial"] = finance_source
    added = upsert_snapshots(state_path, rows)
    status = {
        row["product_id"]: {
            source: value["status"] for source, value in row["sources"].items()
        }
        for row in rows
    }
    finance_status = None
    if selected_mobile:
        finance_status = next(iter(finance_sources.values()), {}).get("data")
    print(json.dumps({
        "date": args.date, "added": added, "sources": status,
        "asc_finance": ({
            "report_id": finance_status.get("report_id"),
            "unassigned_row_count": finance_status.get("unassigned_row_count"),
        } if isinstance(finance_status, dict) else {"status": "unavailable"}),
    }, sort_keys=True))
    required = [
        row for row in rows
        if all(value["status"] == "unavailable" for value in row["sources"].values())
    ]
    return 1 if required else 0


if __name__ == "__main__":
    raise SystemExit(main())
