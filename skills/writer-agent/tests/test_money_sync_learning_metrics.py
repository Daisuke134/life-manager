from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
import sqlite3
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from money_ledger import MoneyInvariant, MoneyLedger  # noqa: E402
from money_sync import _sync_learning_metrics  # noqa: E402
from writer_learning_worker import _artifact_measurements  # noqa: E402


RUN_ID = "fixture-run"
ARTIFACT_ID = f"{RUN_ID}__note__ja"
LIVE_URL = "https://note.com/writer/n/fixture"
RECEIPT_URL = "https://receipts.example.test/fixture"
OBSERVED_AT = "2026-10-04T04:00:00Z"
PUBLISHED_AT = "2026-10-04T00:00:00Z"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[MoneyLedger, Path]:
    state_dir = tmp_path / "state"
    ledger = MoneyLedger(tmp_path / "money.sqlite3")
    ledger.register_artifact(
        artifact_id=ARTIFACT_ID,
        run_id=RUN_ID,
        platform="note",
        lang="ja",
        live_url=LIVE_URL,
        published_at=PUBLISHED_AT,
        artifact_sha256="a" * 64,
    )
    for metric, value, unit in (
        ("price", 500, "JPY"),
        ("paywall_active", 1, "boolean"),
        ("views", 3, "count"),
    ):
        ledger.record_metric(
            artifact_id=ARTIFACT_ID,
            scope="artifact",
            metric=metric,
            value=value,
            unit=unit,
            status="verified",
            reason=None,
            observed_at=OBSERVED_AT,
            source_url=LIVE_URL,
            receipt_sha256=_sha(metric),
        )
    generation_path = (
        state_dir / "runs" / RUN_ID / "gates" / "generation-state.json"
    )
    generation_path.parent.mkdir(parents=True)
    generation_path.write_text(json.dumps({
        "run_id": RUN_ID,
        "status": "complete",
        "attempts": [{
            "started_at": "2026-10-04T03:00:00Z",
            "finished_at": "2026-10-04T03:00:12Z",
        }],
    }))
    return ledger, state_dir


def _metric(
    ledger: MoneyLedger,
    metric: str,
    value: float,
    unit: str,
    *,
    source_url: str = LIVE_URL,
) -> None:
    ledger.record_metric(
        artifact_id=ARTIFACT_ID,
        scope="artifact",
        metric=metric,
        value=value,
        unit=unit,
        status="verified",
        reason=None,
        observed_at=OBSERVED_AT,
        source_url=source_url,
        receipt_sha256=_sha(f"{metric}:{value}:{source_url}"),
    )


def _money_event(
    ledger: MoneyLedger, kind: str, amount: float, receipt: str
) -> str:
    result = ledger.record_money_event(
        artifact_id=ARTIFACT_ID,
        scope="artifact",
        stream="note",
        revenue_class="product_derived",
        kind=kind,
        amount=amount,
        currency="JPY",
        status="refunded" if kind == "refund" else "verified_received",
        counterparty="fixture-buyer",
        external_receipt_id=f"test-receipt-{receipt}",
        source_url=f"{RECEIPT_URL}/{receipt}",
        test=False,
        occurred_at=OBSERVED_AT,
    )
    return str(result["event_id"])


def _fee(ledger: MoneyLedger, event_id: str, receipt: str, amount: float = 0) -> None:
    ledger.record_fee(
        event_id=event_id,
        fee_kind="platform",
        amount=amount,
        currency="JPY",
        status="verified",
        external_receipt_id=f"test-fee-{receipt}",
        source_url=f"{RECEIPT_URL}/fees/{receipt}",
        observed_at=OBSERVED_AT,
    )


def _sync(ledger: MoneyLedger, state_dir: Path) -> None:
    _sync_learning_metrics(ledger, state_dir, observed_at=OBSERVED_AT)


def _worker_measurements(ledger: MoneyLedger):
    with ledger._connect() as connection:
        return _artifact_measurements(
            connection,
            artifact_id=ARTIFACT_ID,
            published_at=datetime.fromisoformat(PUBLISHED_AT.replace("Z", "+00:00")),
            cutoff=datetime.fromisoformat("2026-10-05T00:00:00+00:00"),
            currency="JPY",
            expected_price=500,
        )


def test_missing_financial_coverage_stays_unknown_and_legacy_zero_is_not_consumed(tmp_path):
    ledger, state_dir = _fixture(tmp_path)
    for metric, unit in (
        ("purchases", "count"),
        ("refunds", "JPY"),
        ("net_received", "JPY"),
    ):
        _metric(ledger, metric, 0, unit)

    _sync(ledger, state_dir)

    with sqlite3.connect(ledger.path) as connection:
        rows = connection.execute(
            "SELECT metric,value,status,reason FROM metric_observations "
            "WHERE artifact_id=? AND metric IN ('purchases','refunds','net_received') "
            "AND observed_at=? AND source_url=? AND status='unknown'",
            (ARTIFACT_ID, OBSERVED_AT, LIVE_URL),
        ).fetchall()
    assert {row[0] for row in rows} == {"purchases", "refunds", "net_received"}
    assert all(row[2] == "unknown" and row[1] is None and row[3] for row in rows)

    values, missing, _ = _worker_measurements(ledger)
    assert values is None
    assert {"purchases", "refunds", "net_received"}.issubset(missing)
    with sqlite3.connect(ledger.path) as connection:
        preserved = dict(connection.execute(
            "SELECT metric,value FROM metric_observations "
            "WHERE artifact_id=? AND metric IN ('qualified_cta_clicks','compute_cost') "
            "AND observed_at=? AND status='verified'",
            (ARTIFACT_ID, OBSERVED_AT),
        ).fetchall())
    assert preserved == {"qualified_cta_clicks": 0.0, "compute_cost": 12.0}


def test_arbitrary_url_and_hash_do_not_prove_artifact_financial_coverage(tmp_path):
    ledger, state_dir = _fixture(tmp_path)
    arbitrary_url = "https://arbitrary.example.invalid/financial-zero"
    _metric(ledger, "purchases", 0, "count", source_url=arbitrary_url)
    _metric(ledger, "refunds", 0, "JPY", source_url=arbitrary_url)
    _metric(ledger, "net_received", 100, "JPY", source_url=arbitrary_url)

    _sync(ledger, state_dir)

    values, missing, _ = _worker_measurements(ledger)
    assert values is None
    assert {"purchases", "refunds", "net_received"}.issubset(missing)


def test_legacy_verified_financial_rows_are_rejected_without_a_new_sync(tmp_path):
    ledger, _ = _fixture(tmp_path)
    _metric(ledger, "qualified_cta_clicks", 0, "count")
    _metric(ledger, "compute_cost", 12, "wall_seconds")
    _metric(ledger, "purchases", 1, "count", source_url=RECEIPT_URL)
    _metric(ledger, "refunds", 0, "JPY", source_url=RECEIPT_URL)
    _metric(ledger, "net_received", 100, "JPY", source_url=RECEIPT_URL)

    values, missing, _ = _worker_measurements(ledger)

    assert values is None
    assert {"purchases", "refunds", "net_received"}.issubset(missing)


def test_complete_receipts_preserve_individual_positive_values_and_zero_fees(tmp_path):
    ledger, state_dir = _fixture(tmp_path)
    sale_id = _money_event(ledger, "sale", 100, "sale-1")
    refund_id = _money_event(ledger, "refund", 100, "refund-1")
    _fee(ledger, sale_id, "sale-1")
    _fee(ledger, refund_id, "refund-1")

    _sync(ledger, state_dir)

    values, missing, _ = _worker_measurements(ledger)
    assert values is None
    assert {"purchases", "refunds", "net_received"}.issubset(missing)
    with sqlite3.connect(ledger.path) as connection:
        events = connection.execute(
            "SELECT kind,amount,status FROM money_events WHERE artifact_id=? ORDER BY kind",
            (ARTIFACT_ID,),
        ).fetchall()
        fees = connection.execute(
            "SELECT amount,status FROM money_fees ORDER BY fee_id"
        ).fetchall()
    assert events == [("refund", 100.0, "refunded"), ("sale", 100.0, "verified_received")]
    assert fees == [(0.0, "verified"), (0.0, "verified")]


def test_partial_receipts_and_same_time_legacy_positive_do_not_become_period_totals(tmp_path):
    ledger, state_dir = _fixture(tmp_path)
    sale_id = _money_event(ledger, "sale", 100, "sale-1")
    _fee(ledger, sale_id, "sale-1", amount=0)

    _sync(ledger, state_dir)

    with sqlite3.connect(ledger.path) as connection:
        generated_unknowns = set(connection.execute(
            "SELECT metric FROM metric_observations WHERE artifact_id=? AND observed_at=? "
            "AND source_url=? AND status='unknown'",
            (ARTIFACT_ID, OBSERVED_AT, LIVE_URL),
        ).fetchall())
        event = connection.execute(
            "SELECT amount,status FROM money_events WHERE event_id=?", (sale_id,)
        ).fetchone()
        fee = connection.execute(
            "SELECT amount,status FROM money_fees WHERE event_id=?", (sale_id,)
        ).fetchone()
    assert generated_unknowns == {("purchases",), ("refunds",), ("net_received",)}
    assert event == (100.0, "verified_received")
    assert fee == (0.0, "verified")

    # A verified legacy row at the exact same timestamp cannot override missing coverage.
    _metric(
        ledger,
        "net_received",
        100,
        "JPY",
        source_url="https://dashboard.stripe.com/payments/legacy",
    )

    values, missing, _ = _worker_measurements(ledger)
    assert values is None
    assert {"purchases", "refunds", "net_received"}.issubset(missing)


def test_period_net_without_coverage_is_unknown_even_when_partial_receipts_are_negative(tmp_path):
    ledger, state_dir = _fixture(tmp_path)
    sale_id = _money_event(ledger, "sale", 100, "sale-1")
    refund_id = _money_event(ledger, "refund", 150, "refund-1")
    _fee(ledger, sale_id, "sale-1")
    _fee(ledger, refund_id, "refund-1")

    _sync(ledger, state_dir)

    with sqlite3.connect(ledger.path) as connection:
        row = connection.execute(
            "SELECT value,status,reason FROM metric_observations "
            "WHERE artifact_id=? AND metric='net_received' AND observed_at=? "
            "ORDER BY source_url DESC LIMIT 1",
            (ARTIFACT_ID, OBSERVED_AT),
        ).fetchone()
    assert row is not None
    assert row[0] is None and row[1] == "unknown"
    assert "coverage" in row[2]


def test_metric_ledger_allows_only_finite_signed_net_received(tmp_path):
    ledger, _ = _fixture(tmp_path)

    for value in (-1, 0, 100):
        ledger.record_metric(
            artifact_id=ARTIFACT_ID,
            scope="artifact",
            metric="net_received",
            value=value,
            unit="JPY",
            status="verified",
            reason=None,
            observed_at=OBSERVED_AT,
            source_url=RECEIPT_URL,
            receipt_sha256=_sha(f"net:{value}"),
        )

    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute(
            "SELECT value,status FROM metric_observations WHERE metric='net_received' "
            "AND receipt_sha256 IN (?,?,?) ORDER BY value",
            (_sha("net:-1"), _sha("net:0"), _sha("net:100")),
        ).fetchall() == [(-1.0, "verified"), (0.0, "verified"), (100.0, "verified")]

    for metric in ("purchases", "refunds"):
        with pytest.raises(MoneyInvariant):
            ledger.record_metric(
                artifact_id=ARTIFACT_ID,
                scope="artifact",
                metric=metric,
                value=-1,
                unit="count" if metric == "purchases" else "JPY",
                status="verified",
                reason=None,
                observed_at=OBSERVED_AT,
                source_url=RECEIPT_URL,
                receipt_sha256=_sha(f"negative-{metric}"),
            )

    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(MoneyInvariant):
            ledger.record_metric(
                artifact_id=ARTIFACT_ID,
                scope="artifact",
                metric="net_received",
                value=value,
                unit="JPY",
                status="verified",
                reason=None,
                observed_at=OBSERVED_AT,
                source_url=RECEIPT_URL,
                receipt_sha256=_sha(f"nonfinite-{value}"),
            )

    sale_id = _money_event(ledger, "sale", 100, "signed-contract")
    with pytest.raises(MoneyInvariant):
        ledger.record_fee(
            event_id=sale_id,
            fee_kind="platform",
            amount=-1,
            currency="JPY",
            status="verified",
            external_receipt_id="negative-fee",
            source_url=RECEIPT_URL,
            observed_at=OBSERVED_AT,
        )
    with pytest.raises(MoneyInvariant):
        ledger.record_money_event(
            artifact_id=ARTIFACT_ID,
            scope="artifact",
            stream="note",
            revenue_class="product_derived",
            kind="sale",
            amount=-1,
            currency="JPY",
            status="verified_received",
            counterparty="fixture-buyer",
            external_receipt_id="negative-sale",
            source_url=RECEIPT_URL,
            test=False,
            occurred_at=OBSERVED_AT,
        )
