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
             amount, evidence_suffix: str, settled_at: str | None,
             revenue_class: str | None = None,
             verification_state: str = "verified") -> dict:
    occurred = _instant(occurred_at)
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "receipt",
        "receipt_id": receipt_id,
        "product_loop_id": LOOP_ID,
        "provider": PROVIDER,
        "currency": _currency(evidence_suffix.split(":", 1)[0]),
        "occurred_at": occurred,
        "settled_at": _instant(settled_at) if settled_at is not None else None,
        "verification_state": verification_state,
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


def _read_rows(database: Path) -> tuple[list[tuple], list[tuple], dict[str, str]]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        event_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(money_events)")
        }
        fee_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(money_fees)")
        }
        event_settled = "settled_at" if "settled_at" in event_columns else "NULL"
        contract_id = (
            "external_contract_id" if "external_contract_id" in event_columns else "NULL"
        )
        fee_occurred = "f.occurred_at" if "occurred_at" in fee_columns else "NULL"
        fee_settled = "f.settled_at" if "settled_at" in fee_columns else "NULL"
        events = connection.execute(
            "SELECT kind, amount, currency, status, external_receipt_id, occurred_at, "
            f"{event_settled}, {contract_id} "
            "FROM money_events WHERE test=0"
        ).fetchall()
        fees = connection.execute(
            "SELECT f.amount, f.currency, f.status, f.external_receipt_id, "
            f"{fee_occurred}, {fee_settled} "
            "FROM money_fees f JOIN money_events e ON e.event_id=f.event_id "
            "WHERE e.test=0"
        ).fetchall()
        try:
            intervals = dict(connection.execute(
                "SELECT external_contract_id, interval_name FROM subscription_contracts "
                "WHERE test=0"
            ).fetchall())
        except sqlite3.Error:
            intervals = {}
    finally:
        connection.close()
    return events, fees, intervals


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
        events, fees, intervals = _read_rows(database)
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
    for (kind, amount, currency, status, external_id, occurred_at, settled_at,
         external_contract_id) in events:
        if status not in {"verified_received", "refunded"}:
            continue
        if not external_id:
            continue
        occurred = _instant(occurred_at)
        if kind == "refund" or status == "refunded":
            if kind != "refund" or status != "refunded" or settled_at is None:
                continue
            category, revenue_class = "refund", None
            verification_state = "verified"
        elif kind in {"sale", "subscription_charge", "editorial_fee"}:
            if kind == "subscription_charge":
                interval = intervals.get(str(external_contract_id))
                if interval not in {"month", "year"}:
                    continue
                revenue_class = "monthly_recurring" if interval == "month" else "other_recurring"
            elif kind == "editorial_fee":
                if external_contract_id:
                    interval = intervals.get(str(external_contract_id))
                    if interval not in {"month", "year"}:
                        continue
                    revenue_class = "monthly_recurring" if interval == "month" else "other_recurring"
                else:
                    revenue_class = "one_time"
            else:
                revenue_class = "one_time"
            category = "settled_external_revenue" if settled_at is not None else "pending_revenue"
            verification_state = "verified" if settled_at is not None else "pending"
        else:
            continue
        receipts.append(_receipt(
            receipt_id=f"writer:money_event:{external_id}",
            occurred_at=occurred, settled_at=settled_at if category != "pending_revenue" else None,
            category=category, amount=amount,
            evidence_suffix=f"{currency}:events/{external_id}",
            revenue_class=revenue_class,
            verification_state=verification_state,
        ))

    for amount, currency, status, external_id, occurred_at, settled_at in fees:
        if (status != "verified" or not external_id or occurred_at is None
                or settled_at is None or amount == 0):
            continue
        receipts.append(_receipt(
            receipt_id=f"writer:money_fee:{external_id}",
            occurred_at=occurred_at, settled_at=settled_at,
            category="other_measured_cost", amount=amount,
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
