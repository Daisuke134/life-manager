"""Read already-captured Google Cloud Cost Table CSVs as billed, not paid, expense facts."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any


MONTH_FILE = re.compile(r"^(20\d{2}-(?:0[1-9]|1[0-2]))-cost-table\.csv$")
AMOUNT = re.compile(
    r"^(?P<sign>-?)(?:[¥￥])?"
    r"(?P<whole>(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+))"
    r"(?P<fraction>\.[0-9]{1,18})?$"
)
REQUIRED_HEADERS = (
    "サービスの説明", "SKU の説明", "クレジットの種類", "費用のタイプ",
    "四捨五入前の費用（¥）", "費用（¥）",
)
METADATA_KEYS = {"通貨", "合計お支払い額"}
USAGE = "使用量"
TAX = "税金"
ROUNDING = "丸めエラー"
SUMMARY = "合計"


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    if not result or len(result) > 160 or any(ord(char) < 32 or ord(char) == 127 for char in result):
        return None
    return result


def _amount(value: Any) -> Decimal | None:
    if not isinstance(value, str):
        return None
    match = AMOUNT.fullmatch(value.strip())
    if match is None:
        return None
    text = match.group("sign") + match.group("whole").replace(",", "") + (match.group("fraction") or "")
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _invoice_result(*, period: str, source_ref: str, reason: str) -> dict:
    return {
        "status": "unverified",
        "invoice_period": period,
        "currency": "JPY",
        "billed_total_jpy": None,
        "service_sku": [],
        "adjustments": {
            "usage_gross_jpy": None,
            "credits_jpy": None,
            "tax_jpy": None,
            "rounding_jpy": None,
        },
        "cash_paid_status": "unknown",
        "allocation_status": "unattributed",
        "source_ref": source_ref,
        "reason": reason,
    }


def parse_cost_table_csv(data: bytes, *, invoice_period: str) -> dict:
    """Parse one invoice file; never expose account, project, or invoice IDs."""
    digest = hashlib.sha256(data).hexdigest()
    source_ref = f"google-cloud-cost-table://sha256/{digest}"
    if not MONTH_FILE.fullmatch(f"{invoice_period}-cost-table.csv"):
        return _invoice_result(period="unknown", source_ref=source_ref, reason="invoice_period_invalid")
    try:
        text = data.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (UnicodeError, csv.Error):
        return _invoice_result(period=invoice_period, source_ref=source_ref, reason="csv_invalid")

    required = set(REQUIRED_HEADERS)
    header_indexes = [index for index, row in enumerate(rows) if required.issubset(row)]
    if len(header_indexes) != 1:
        return _invoice_result(period=invoice_period, source_ref=source_ref, reason="csv_header_invalid")
    header_index = header_indexes[0]
    headers = [item.strip() for item in rows[header_index]]
    if any(headers.count(key) != 1 for key in REQUIRED_HEADERS):
        return _invoice_result(period=invoice_period, source_ref=source_ref, reason="csv_header_duplicate")
    indexes = {key: headers.index(key) for key in REQUIRED_HEADERS}

    metadata: dict[str, str] = {}
    for row in rows[:header_index]:
        if len(row) < 2:
            continue
        key, value = row[0].strip(), row[1].strip()
        if key in METADATA_KEYS:
            if key in metadata and metadata[key] != value:
                return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_metadata_conflict")
            metadata[key] = value
    if metadata.get("通貨") != "JPY":
        return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_currency_unsupported")
    billed_total = _amount(metadata.get("合計お支払い額"))
    if billed_total is None:
        return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_total_missing")

    try:
        with localcontext() as context:
            context.prec = 64
            service_rows: dict[tuple[str, str], list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
            usage_gross = credits = tax = rounding = Decimal(0)
            summary_total = None
            summary_count = 0
            for row in rows[header_index + 1:]:
                if not row or all(not cell.strip() for cell in row):
                    continue
                if len(row) != len(headers):
                    return _invoice_result(period=invoice_period, source_ref=source_ref, reason="csv_row_shape_invalid")
                cost_type = row[indexes["費用のタイプ"]].strip()
                exact_amount = _amount(row[indexes["四捨五入前の費用（¥）"]])
                display_amount = _amount(row[indexes["費用（¥）"]])
                if exact_amount is None or display_amount is None:
                    return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_line_amount_invalid")
                if cost_type == SUMMARY:
                    summary_count += 1
                    summary_total = exact_amount
                    if display_amount != billed_total:
                        return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_summary_mismatch")
                    continue
                if cost_type == USAGE:
                    credit_type = row[indexes["クレジットの種類"]].strip()
                    if credit_type:
                        if exact_amount > 0:
                            return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_credit_sign_invalid")
                        credits += exact_amount
                    else:
                        if exact_amount < 0:
                            return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_usage_sign_invalid")
                        usage_gross += exact_amount
                    service = _text(row[indexes["サービスの説明"]]) or "unclassified"
                    sku = _text(row[indexes["SKU の説明"]]) or "unclassified"
                    bucket = service_rows[(service, sku)]
                    if credit_type:
                        bucket[1] += exact_amount
                    else:
                        bucket[0] += exact_amount
                elif cost_type == TAX:
                    tax += exact_amount
                elif cost_type == ROUNDING:
                    rounding += exact_amount
                else:
                    return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_cost_type_unknown")

            if summary_count != 1 or summary_total != billed_total:
                return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_summary_mismatch")
            if usage_gross + credits + tax + rounding != billed_total:
                return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_total_mismatch")

            detail = []
            for (service, sku), (gross, credit) in sorted(service_rows.items()):
                detail.append({
                    "service": service,
                    "sku": sku,
                    "usage_gross_jpy": _decimal_text(gross),
                    "credits_jpy": _decimal_text(credit),
                    "net_billed_jpy": _decimal_text(gross + credit),
                })
            return {
                "status": "verified",
                "invoice_period": invoice_period,
                "currency": "JPY",
                "billed_total_jpy": _decimal_text(billed_total),
                "service_sku": detail,
                "adjustments": {
                    "usage_gross_jpy": _decimal_text(usage_gross),
                    "credits_jpy": _decimal_text(credits),
                    "tax_jpy": _decimal_text(tax),
                    "rounding_jpy": _decimal_text(rounding),
                },
                "cash_paid_status": "unknown",
                "allocation_status": "unattributed",
                "source_ref": source_ref,
                "reason": None,
            }
    except (ArithmeticError, InvalidOperation):
        return _invoice_result(period=invoice_period, source_ref=source_ref, reason="invoice_arithmetic_invalid")


def load_directory(directory: Path) -> dict:
    """Read exact month-named CSVs from a private evidence directory without network I/O."""
    if directory.is_symlink() or not directory.is_dir():
        return {"status": "unavailable", "reason": "source_missing", "invoices": []}
    try:
        entries = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError:
        return {"status": "unverified", "reason": "source_list_failed", "invoices": []}
    candidates = []
    for path in entries:
        match = MONTH_FILE.fullmatch(path.name)
        if match:
            candidates.append((path, match.group(1)))
    if not candidates:
        return {"status": "unavailable", "reason": "source_missing", "invoices": []}

    invoices = []
    for path, period in candidates:
        if path.is_symlink() or not path.is_file():
            invoices.append(_invoice_result(
                period=period, source_ref="google-cloud-cost-table://unavailable",
                reason="source_path_invalid",
            ))
            continue
        try:
            invoices.append(parse_cost_table_csv(path.read_bytes(), invoice_period=period))
        except OSError:
            invoices.append(_invoice_result(
                period=period, source_ref="google-cloud-cost-table://unavailable",
                reason="source_read_failed",
            ))
    status = "verified" if all(row["status"] == "verified" for row in invoices) else "unverified"
    reason = next((row["reason"] for row in invoices if row["reason"]), None)
    return {"status": status, "reason": reason, "invoices": invoices}


__all__ = ["load_directory", "parse_cost_table_csv"]
