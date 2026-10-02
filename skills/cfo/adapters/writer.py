"""Read-only Writer money.sqlite3 adapter for the B0 attribution contract."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from skills.cfo import economic_attribution as contract


LOOP_ID = "writer"
SOURCE_ID = "writer-money-ledger"
PROVIDER = "writer-money"
DEFAULT_PATH = Path("~/.local/state/life-manager/writer/money.sqlite3").expanduser()


def _instant(value: str) -> str:
    probe = {
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": LOOP_ID,
        "source_id": SOURCE_ID,
        "projection": "historical",
        "window_start": None,
        "window_end": value,
        "coverage_state": "gap",
        "reason": "missing_category",
        "covered_categories": [],
        "observed_at": value,
        "evidence_refs": ["writer-money://validation/timestamp"],
    }
    return contract.validate_record(probe)["window_end"]


def _amount(value, field: str) -> str:
    try:
        amount = Decimal(str(value))
    except Exception as error:
        raise ValueError(f"writer_{field}_invalid") from error
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"writer_{field}_invalid")
    return format(amount.normalize(), "f")


def _currency(value) -> str:
    currency = str(value or "")
    if len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
        raise ValueError("writer_currency_invalid")
    return currency


def _receipt(*, receipt_id: str, occurred_at: str, category: str,
             amount, evidence_suffix: str, revenue_class: str | None = None) -> dict:
    occurred = _instant(occurred_at)
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "receipt",
        "receipt_id": receipt_id,
        "product_loop_id": LOOP_ID,
        "provider": PROVIDER,
        "currency": _currency(evidence_suffix.split(":", 1)[0]),
        "occurred_at": occurred,
        "settled_at": occurred,
        "verification_state": "verified",
        "revenue_class": revenue_class,
        "evidence_refs": [f"writer-money://{evidence_suffix}"],
        "components": [{"category": category, "amount": _amount(amount, "amount")}],
    })


def _coverage(*, projection: str, start: str | None, end: str,
              observed_at: str, reason: str, evidence: str) -> dict:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": LOOP_ID,
        "source_id": SOURCE_ID,
        "projection": projection,
        "window_start": start,
        "window_end": end,
        "coverage_state": "gap",
        "reason": reason,
        "covered_categories": ["settled_external_revenue", "refund", "other_measured_cost"],
        "observed_at": observed_at,
        "evidence_refs": [evidence],
    })


def _read_rows(database: Path) -> tuple[list[tuple], list[tuple]]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        events = connection.execute(
            "SELECT kind, amount, currency, status, external_receipt_id, occurred_at "
            "FROM money_events"
        ).fetchall()
        fees = connection.execute(
            "SELECT amount, currency, status, external_receipt_id, observed_at "
            "FROM money_fees"
        ).fetchall()
    finally:
        connection.close()
    return events, fees


def adapt_path(path: str | Path | None, *, snapshot_at: str,
               trailing_start: str) -> list[dict]:
    """Read Writer's local ledger; provider/payout rows are never mutated."""
    database = Path(path or DEFAULT_PATH).expanduser().resolve()
    end = _instant(snapshot_at)
    start = _instant(trailing_start)
    observed_at = datetime.fromtimestamp(database.stat().st_mtime).astimezone().isoformat()
    observed_at = _instant(observed_at)
    digest_ref = f"writer-money://sqlite/{database.name}/{int(database.stat().st_mtime)}"
    try:
        events, fees = _read_rows(database)
    except (OSError, sqlite3.Error):
        return [
            _coverage(projection="historical", start=None, end=end, observed_at=end,
                      reason="read_failed", evidence="writer-money://read-failed"),
            _coverage(projection="trailing", start=start, end=end, observed_at=end,
                      reason="read_failed", evidence="writer-money://read-failed"),
            _coverage(projection="as_of", start=None, end=end, observed_at=end,
                      reason="missing_category", evidence="writer-money://read-failed"),
        ]

    receipts = []
    for kind, amount, currency, status, external_id, occurred_at in events:
        if status not in {"verified_received", "refunded"}:
            continue
        if not external_id:
            raise ValueError("writer_money_event_receipt_missing")
        occurred = _instant(occurred_at)
        if kind == "refund" or status == "refunded":
            category, revenue_class = "refund", None
        elif kind in {"sale", "subscription_charge"}:
            category = "settled_external_revenue"
            revenue_class = "monthly_recurring" if kind == "subscription_charge" else "one_time"
        else:
            raise ValueError(f"writer_money_event_kind_invalid:{kind}")
        receipts.append(_receipt(
            receipt_id=f"writer:money_event:{external_id}",
            occurred_at=occurred, category=category, amount=amount,
            evidence_suffix=f"{currency}:events/{external_id}",
            revenue_class=revenue_class,
        ))

    for amount, currency, status, external_id, observed in fees:
        if status != "verified":
            continue
        if not external_id:
            raise ValueError("writer_money_fee_receipt_missing")
        receipts.append(_receipt(
            receipt_id=f"writer:money_fee:{external_id}",
            occurred_at=observed, category="other_measured_cost", amount=amount,
            evidence_suffix=f"{currency}:fees/{external_id}",
        ))

    return [
        *receipts,
        _coverage(projection="historical", start=None, end=end, observed_at=observed_at,
                  reason="missing_category", evidence=digest_ref),
        _coverage(projection="trailing", start=start, end=end, observed_at=observed_at,
                  reason="missing_category", evidence=digest_ref),
        _coverage(projection="as_of", start=None, end=end, observed_at=observed_at,
                  reason="missing_category", evidence=digest_ref),
    ]
