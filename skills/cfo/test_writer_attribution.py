"""Writer Stripe receipt provenance tests using temporary local ledgers only."""

import sys
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills" / "writer-agent" / "scripts"))

import writer_stripe_sync  # noqa: E402
from money_ledger import MoneyInvariant, MoneyLedger  # noqa: E402
from money_sync import _sync_stripe_receipts  # noqa: E402
from skills.cfo.adapters import writer as writer_adapter  # noqa: E402


OBSERVED = "2026-10-02T00:00:00Z"
METADATA = {
    "product": "writer_article",
    "slug": "settled-article",
    "artifact_id": "writer-run__self-owned__en",
    "run_id": "writer-run",
    "lang": "en",
    "client_reference_id": "writer-run",
}


class WriterStripeProvenanceTest(unittest.TestCase):
    def test_settlement_order_compares_instants_across_timezone_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            try:
                result = ledger.record_money_event(
                    artifact_id=None, scope="account", stream="self_owned_publication",
                    revenue_class="direct_writing", kind="sale", amount=10,
                    currency="USD", status="verified_received", counterparty="reader",
                    external_receipt_id="offset-sale", source_url="https://example.com/offset-sale",
                    test=False, occurred_at="2026-09-30T23:00:00+09:00",
                    settled_at="2026-09-30T14:30:00Z",
                )
            except MoneyInvariant:
                result = {"inserted": False}

        self.assertTrue(result["inserted"])

    def test_same_receipt_enriches_missing_provenance_but_rejects_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            base = {
                "artifact_id": None, "scope": "account", "stream": "self_owned_publication",
                "revenue_class": "direct_writing", "kind": "sale", "amount": 10,
                "currency": "USD", "status": "verified_received", "counterparty": "reader",
                "external_receipt_id": "enrich-sale", "source_url": "https://example.com/enrich-sale",
                "test": False, "occurred_at": "2026-09-30T20:00:00Z",
            }
            event = ledger.record_money_event(**base)
            enriched = ledger.record_money_event(
                **base, settled_at="2026-10-01T20:00:00Z",
            )
            try:
                ledger.record_money_event(
                    **base, settled_at="2026-10-02T05:00:00+09:00",
                )
                same_instant = True
            except MoneyInvariant:
                same_instant = False
            with ledger._connect() as connection:
                event_settlement = connection.execute(
                    "SELECT settled_at FROM money_events WHERE external_receipt_id='enrich-sale'"
                ).fetchone()["settled_at"]
            with self.assertRaisesRegex(MoneyInvariant, "provenance conflicts"):
                ledger.record_money_event(
                    **base, settled_at="2026-10-02T20:00:00Z",
                )

            ledger.record_fee(
                event_id=event["event_id"], fee_kind="stripe", amount=1,
                currency="USD", status="verified", external_receipt_id="enrich-fee",
                source_url="https://example.com/enrich-fee", observed_at=OBSERVED,
            )
            ledger.record_fee(
                event_id=event["event_id"], fee_kind="stripe", amount=1,
                currency="USD", status="verified", external_receipt_id="enrich-fee",
                source_url="https://example.com/enrich-fee", observed_at=OBSERVED,
                occurred_at="2026-09-30T20:00:00Z",
                settled_at="2026-10-01T20:00:00Z",
            )
            try:
                ledger.record_fee(
                    event_id=event["event_id"], fee_kind="stripe", amount=1,
                    currency="USD", status="verified", external_receipt_id="enrich-fee",
                    source_url="https://example.com/enrich-fee", observed_at=OBSERVED,
                    occurred_at="2026-10-01T05:00:00+09:00",
                    settled_at="2026-10-02T05:00:00+09:00",
                )
                same_fee_instants = True
            except MoneyInvariant:
                same_fee_instants = False
            with ledger._connect() as connection:
                fee_times = connection.execute(
                    "SELECT occurred_at,settled_at FROM money_fees "
                    "WHERE external_receipt_id='enrich-fee'"
                ).fetchone()
            with self.assertRaisesRegex(MoneyInvariant, "fee receipt provenance conflicts"):
                ledger.record_fee(
                    event_id=event["event_id"], fee_kind="stripe", amount=1,
                    currency="USD", status="verified", external_receipt_id="enrich-fee",
                    source_url="https://example.com/enrich-fee", observed_at=OBSERVED,
                    settled_at="2026-10-02T20:00:00Z",
                )

        self.assertEqual(enriched["inserted"], False)
        self.assertTrue(same_instant)
        self.assertTrue(same_fee_instants)
        self.assertEqual(event_settlement, "2026-10-01T20:00:00Z")
        self.assertEqual(fee_times["occurred_at"], "2026-09-30T20:00:00Z")
        self.assertEqual(fee_times["settled_at"], "2026-10-01T20:00:00Z")

    def test_legacy_ledger_rows_survive_additive_provenance_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "legacy.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.executescript("""
                    CREATE TABLE money_events (
                        event_id TEXT PRIMARY KEY, artifact_id TEXT, scope TEXT,
                        stream TEXT, revenue_class TEXT, kind TEXT, amount REAL,
                        currency TEXT, status TEXT, counterparty TEXT,
                        external_receipt_id TEXT, source_url TEXT, test INTEGER,
                        occurred_at TEXT
                    );
                    CREATE TABLE money_fees (
                        fee_id TEXT PRIMARY KEY, event_id TEXT, fee_kind TEXT,
                        amount REAL, currency TEXT, status TEXT,
                        external_receipt_id TEXT, source_url TEXT, observed_at TEXT
                    );
                """)
                connection.execute(
                    "INSERT INTO money_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("legacy-event", None, "account", "self_owned_publication",
                     "direct_writing", "sale", 10, "USD", "verified_received", "reader",
                     "legacy-sale", "https://example.com/legacy", 0,
                     "2026-09-30T20:00:00Z"),
                )
                connection.execute(
                    "INSERT INTO money_fees VALUES(?,?,?,?,?,?,?,?,?)",
                    ("legacy-fee", "legacy-event", "stripe", 1, "USD", "verified",
                     "legacy-fee", "https://example.com/fee", OBSERVED),
                )

            before_migration = writer_adapter.adapt_path(
                database, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )
            ledger = MoneyLedger(database)
            with ledger._connect() as connection:
                event = connection.execute(
                    "SELECT external_receipt_id,settled_at FROM money_events"
                ).fetchone()
                counts = (
                    connection.execute("SELECT COUNT(*) FROM money_events").fetchone()[0],
                    connection.execute("SELECT COUNT(*) FROM money_fees").fetchone()[0],
                )
            records = writer_adapter.adapt_path(
                database, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipt = next(row for row in records if row.get("receipt_id") == "writer:money_event:legacy-sale")
        prior_receipt = next(
            row for row in before_migration
            if row.get("receipt_id") == "writer:money_event:legacy-sale"
        )
        self.assertEqual(event["external_receipt_id"], "legacy-sale")
        self.assertIsNone(event["settled_at"])
        self.assertEqual(counts, (1, 1))
        self.assertEqual(receipt["verification_state"], "pending")
        self.assertIsNone(receipt["settled_at"])
        self.assertEqual(prior_receipt["verification_state"], "pending")
        self.assertIsNone(prior_receipt["settled_at"])

    def test_product_purchase_insert_path_survives_provenance_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            artifact_id = METADATA["artifact_id"]
            ledger.register_artifact(
                artifact_id=artifact_id, run_id=METADATA["run_id"],
                platform="self-owned", lang="en", live_url="https://example.com/article",
                published_at="2026-09-30T18:00:00Z", artifact_sha256="d" * 64,
            )
            for event_type, target_id, occurred_at in (
                ("visit", "visit-1", "2026-09-30T19:00:00Z"),
                ("activation", "activation-1", "2026-09-30T20:00:00Z"),
            ):
                ledger.record_product_event(
                    event_id=target_id, event_type=event_type, product_id="newsletter",
                    run_id=METADATA["run_id"], artifact_id=artifact_id, variant_id="default",
                    click_id="click-1", target_id=target_id, occurred_at=occurred_at,
                    source_url="https://example.com/article", receipt_sha256="e" * 64,
                    amount=None, currency=None, external_receipt_id=None,
                    counterparty=None, test=False,
                )
            result = ledger.record_product_event(
                event_id="purchase-1", event_type="purchase", product_id="newsletter",
                run_id=METADATA["run_id"], artifact_id=artifact_id, variant_id="default",
                click_id="click-1", target_id="purchase-1", occurred_at="2026-09-30T21:00:00Z",
                source_url="https://example.com/article", receipt_sha256="f" * 64,
                amount=10, currency="USD", external_receipt_id="product-purchase",
                counterparty="reader", test=False,
            )
            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipt = next(row for row in records if row.get("receipt_id") == "writer:money_event:product-purchase")
        self.assertTrue(result["inserted"])
        self.assertEqual(receipt["verification_state"], "pending")
        self.assertIsNone(receipt["settled_at"])

    def test_invoice_receipt_retains_the_provider_subscription_identity(self):
        archive_metadata = {**METADATA, "product": "writer_archive"}
        rows = writer_stripe_sync.normalize_objects(
            {
                "subscriptions": [{
                    "id": "sub_month",
                    "object": "subscription",
                    "metadata": archive_metadata,
                    "livemode": True,
                    "status": "active",
                    "created": 1790798400,
                    "items": {"data": [{"price": {
                        "unit_amount": 1000,
                        "currency": "usd",
                        "recurring": {"interval": "month"},
                    }}]},
                }],
                "invoices": [{
                    "id": "in_month",
                    "object": "invoice",
                    "subscription": "sub_month",
                    "currency": "usd",
                    "status": "paid",
                    "paid": True,
                    "status_transitions": {"paid_at": 1790798400},
                    "amount_paid": 1000,
                    "payments": {"data": [{"payment": {
                        "payment_intent": {"latest_charge": {
                            "balance_transaction": "txn_month",
                        }},
                    }}]},
                }],
                "balance_transactions": [{
                    "id": "txn_month",
                    "object": "balance_transaction",
                    "amount": 1000,
                    "fee": 0,
                    "net": 1000,
                    "currency": "usd",
                    "created": 1790798400,
                    "available_on": 1790884800,
                    "status": "available",
                    "source": "ch_month",
                    "type": "charge",
                }],
            },
            observed_at=OBSERVED,
        )

        invoice = next(
            row for row in rows
            if row["receipt_type"] == "money" and row["external_receipt_id"] == "in_month"
        )
        self.assertEqual(invoice.get("external_contract_id"), "sub_month")

    def test_available_on_is_retained_and_refund_needs_its_balance_receipt(self):
        rows = writer_stripe_sync.normalize_objects(
            {
                "payment_intents": [{
                    "id": "pi_writer",
                    "object": "payment_intent",
                    "metadata": METADATA,
                    "livemode": True,
                    "status": "succeeded",
                    "amount_received": 1000,
                    "currency": "usd",
                    "latest_charge": {"balance_transaction": "txn_charge"},
                }],
                "balance_transactions": [{
                    "id": "txn_charge",
                    "object": "balance_transaction",
                    "amount": 1000,
                    "fee": 50,
                    "net": 950,
                    "currency": "usd",
                    "created": 1790798400,
                    "available_on": 1790884800,
                    "status": "available",
                    "source": "ch_writer",
                    "type": "charge",
                }],
                "refunds": [{
                    "id": "re_unsettled",
                    "object": "refund",
                    "amount": 500,
                    "currency": "usd",
                    "created": 1790802000,
                    "livemode": True,
                    "payment_intent": "pi_writer",
                    "status": "succeeded",
                }],
            },
            observed_at=OBSERVED,
        )

        sale = next(row for row in rows if row["receipt_type"] == "money")
        fee = next(row for row in rows if row["receipt_type"] == "fee")
        self.assertEqual(sale["occurred_at"], "2026-09-30T20:00:00Z")
        self.assertEqual(sale.get("settled_at"), "2026-10-01T20:00:00Z")
        self.assertEqual(fee.get("settled_at"), "2026-10-01T20:00:00Z")
        self.assertFalse(any(row["receipt_type"] == "refund" for row in rows))

        settled_rows = writer_stripe_sync.normalize_objects(
            {
                "payment_intents": [{
                    "id": "pi_writer",
                    "metadata": METADATA,
                    "livemode": True,
                    "status": "succeeded",
                    "amount_received": 1000,
                    "currency": "usd",
                    "latest_charge": {"balance_transaction": "txn_missing_charge"},
                }],
                "refunds": [{
                    "id": "re_settled",
                    "object": "refund",
                    "amount": 500,
                    "currency": "usd",
                    "created": 1790802000,
                    "livemode": True,
                    "payment_intent": "pi_writer",
                    "balance_transaction": "txn_refund",
                    "status": "succeeded",
                }],
                "balance_transactions": [{
                    "id": "txn_refund",
                    "object": "balance_transaction",
                    "amount": -500,
                    "fee": 0,
                    "net": -500,
                    "currency": "usd",
                    "created": 1790802000,
                    "available_on": 1790892000,
                    "status": "available",
                    "source": "re_settled",
                    "type": "refund",
                }],
            },
            observed_at=OBSERVED,
        )
        refund = next(row for row in settled_rows if row["receipt_type"] == "refund")
        self.assertEqual(refund["occurred_at"], "2026-09-30T21:00:00Z")
        self.assertEqual(refund["settled_at"], "2026-10-01T22:00:00Z")

    def test_adapter_excludes_test_refund_and_its_verified_fee(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            sale = ledger.record_money_event(
                artifact_id=None, scope="account", stream="self_owned_publication",
                revenue_class="direct_writing", kind="sale", amount=10,
                currency="USD", status="verified_received", counterparty="reader",
                external_receipt_id="live-sale", source_url="https://example.com/sale",
                test=False, occurred_at="2026-09-30T20:00:00Z",
            )
            test_refund = ledger.record_money_event(
                artifact_id=None, scope="account", stream="self_owned_publication",
                revenue_class="direct_writing", kind="refund", amount=5,
                currency="USD", status="refunded", counterparty="reader",
                external_receipt_id="test-refund", source_url="https://example.com/refund",
                test=True, occurred_at="2026-09-30T21:00:00Z",
            )
            ledger.record_fee(
                event_id=test_refund["event_id"], fee_kind="stripe", amount=1,
                currency="USD", status="verified", external_receipt_id="test-fee",
                source_url="https://example.com/fee", observed_at="2026-09-30T21:01:00Z",
            )

            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipts = [row for row in records if row["record_type"] == "receipt"]
        self.assertEqual(
            {row["receipt_id"] for row in receipts},
            {"writer:money_event:live-sale"},
        )

    def test_zero_fee_is_omitted_without_losing_positive_sale(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            sale = ledger.record_money_event(
                artifact_id=None, scope="account", stream="self_owned_publication",
                revenue_class="direct_writing", kind="sale", amount=10,
                currency="USD", status="verified_received", counterparty="reader",
                external_receipt_id="zero-fee-sale", source_url="https://example.com/sale",
                test=False, occurred_at="2026-09-30T20:00:00Z",
                settled_at="2026-10-01T20:00:00Z",
            )
            ledger.record_fee(
                event_id=sale["event_id"], fee_kind="stripe", amount=0,
                currency="USD", status="verified", external_receipt_id="zero-fee",
                source_url="https://example.com/fee", observed_at=OBSERVED,
                occurred_at="2026-09-30T20:00:00Z", settled_at="2026-10-01T20:00:00Z",
            )
            try:
                records = writer_adapter.adapt_path(
                    ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
                )
                adapted = True
            except ValueError:
                records, adapted = [], False

        receipts = [row for row in records if row["record_type"] == "receipt"]
        self.assertTrue(adapted)
        self.assertEqual(
            {row["receipt_id"] for row in receipts},
            {"writer:money_event:zero-fee-sale"},
        )

    def test_stripe_settlement_survives_sync_and_is_used_by_cfo(self):
        rows = writer_stripe_sync.normalize_objects(
            {
                "payment_intents": [{
                    "id": "pi_pipeline",
                    "object": "payment_intent",
                    "metadata": METADATA,
                    "livemode": True,
                    "status": "succeeded",
                    "amount_received": 1000,
                    "currency": "usd",
                    "latest_charge": {"balance_transaction": "txn_pipeline"},
                }],
                "balance_transactions": [{
                    "id": "txn_pipeline",
                    "object": "balance_transaction",
                    "amount": 1000,
                    "fee": 50,
                    "net": 950,
                    "currency": "usd",
                    "created": 1790798400,
                    "available_on": 1790884800,
                    "status": "available",
                    "source": "ch_pipeline",
                    "type": "charge",
                }],
            },
            observed_at=OBSERVED,
        )

        with tempfile.TemporaryDirectory() as tmp:
            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            ledger.register_artifact(
                artifact_id=METADATA["artifact_id"], run_id=METADATA["run_id"],
                platform="self-owned", lang="en", live_url="https://example.com/article",
                published_at="2026-09-30T19:00:00Z", artifact_sha256="a" * 64,
            )
            report = _sync_stripe_receipts(ledger, rows)
            with ledger._connect() as connection:
                event_columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(money_events)")
                }
                fee_columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(money_fees)")
                }
                self.assertIn("settled_at", event_columns)
                self.assertIn("occurred_at", fee_columns)
                self.assertIn("settled_at", fee_columns)
                event = connection.execute(
                    "SELECT settled_at FROM money_events WHERE external_receipt_id='pi_pipeline'"
                ).fetchone()
                fee = connection.execute(
                    "SELECT occurred_at,settled_at FROM money_fees "
                    "WHERE external_receipt_id='txn_pipeline'"
                ).fetchone()
            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipts = {row["receipt_id"]: row for row in records if row["record_type"] == "receipt"}
        self.assertEqual(report["inserted"], 2)
        self.assertEqual(event["settled_at"], "2026-10-01T20:00:00Z")
        self.assertEqual(fee["occurred_at"], "2026-09-30T20:00:00Z")
        self.assertEqual(fee["settled_at"], "2026-10-01T20:00:00Z")
        self.assertEqual(
            receipts["writer:money_event:pi_pipeline"]["settled_at"],
            "2026-10-01T20:00:00.000000Z",
        )
        self.assertEqual(
            receipts["writer:money_fee:txn_pipeline"]["settled_at"],
            "2026-10-01T20:00:00.000000Z",
        )

    def test_subscription_receipt_class_uses_its_linked_contract_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            artifact_id = METADATA["artifact_id"]
            ledger.register_artifact(
                artifact_id=artifact_id, run_id=METADATA["run_id"],
                platform="self-owned", lang="en", live_url="https://example.com/article",
                published_at="2026-09-30T19:00:00Z", artifact_sha256="b" * 64,
            )
            for interval in ("month", "year", "unknown"):
                contract_id = f"sub_{interval}"
                ledger.record_subscription(
                    acquisition_artifact_id=artifact_id, stream="self_owned_subscription",
                    amount=10, currency="USD", interval=interval, status="active",
                    external_contract_id=contract_id,
                    source_url=f"https://example.com/{contract_id}", test=False,
                    started_at="2026-09-01T00:00:00Z", observed_at=OBSERVED,
                )
                ledger.record_money_event(
                    artifact_id=artifact_id, scope="artifact", stream="self_owned_subscription",
                    revenue_class="direct_writing", kind="subscription_charge", amount=10,
                    currency="USD", status="verified_received", counterparty="reader",
                    external_receipt_id=f"invoice_{interval}",
                    source_url=f"https://example.com/invoice/{interval}", test=False,
                    occurred_at="2026-09-30T20:00:00Z", settled_at="2026-10-01T20:00:00Z",
                    external_contract_id=contract_id,
                )
            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipts = {
            row["receipt_id"]: row for row in records if row["record_type"] == "receipt"
        }
        self.assertEqual(
            receipts["writer:money_event:invoice_month"]["revenue_class"],
            "monthly_recurring",
        )
        self.assertEqual(
            receipts["writer:money_event:invoice_year"]["revenue_class"],
            "other_recurring",
        )
        self.assertNotIn("writer:money_event:invoice_unknown", receipts)

    def test_editorial_fee_recurring_class_requires_a_billing_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            for interval in ("month", "year", "unknown"):
                contract_id = f"retainer_{interval}"
                ledger.record_subscription(
                    acquisition_artifact_id=None, stream="editorial_retainer",
                    amount=40, currency="USD", interval=interval, status="active",
                    external_contract_id=contract_id,
                    source_url=f"https://example.com/{contract_id}", test=False,
                    started_at="2026-09-01T00:00:00Z", observed_at=OBSERVED,
                )
                ledger.record_money_event(
                    artifact_id=None, scope="account", stream="editorial_fee",
                    revenue_class="direct_writing", kind="editorial_fee", amount=40,
                    currency="USD", status="verified_received", counterparty="publisher",
                    external_receipt_id=f"editorial_{interval}",
                    source_url=f"https://example.com/editorial/{interval}", test=False,
                    occurred_at="2026-09-30T20:00:00Z", settled_at="2026-10-01T20:00:00Z",
                    external_contract_id=contract_id,
                )
            ledger.record_money_event(
                artifact_id=None, scope="account", stream="editorial_fee",
                revenue_class="direct_writing", kind="editorial_fee", amount=40,
                currency="USD", status="verified_received", counterparty="publisher",
                external_receipt_id="editorial_one_time",
                source_url="https://example.com/editorial/one-time", test=False,
                occurred_at="2026-09-30T20:00:00Z", settled_at="2026-10-01T20:00:00Z",
            )
            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipts = {
            row["receipt_id"]: row for row in records if row["record_type"] == "receipt"
        }
        self.assertEqual(
            receipts["writer:money_event:editorial_month"]["revenue_class"],
            "monthly_recurring",
        )
        self.assertEqual(
            receipts["writer:money_event:editorial_year"]["revenue_class"],
            "other_recurring",
        )
        self.assertEqual(
            receipts["writer:money_event:editorial_one_time"]["revenue_class"],
            "one_time",
        )
        self.assertNotIn("writer:money_event:editorial_unknown", receipts)

    def test_formal_settled_publisher_receipt_reaches_cfo_as_editorial_fee(self):
        with tempfile.TemporaryDirectory() as tmp:
            opportunity_db = Path(tmp) / "opportunity.sqlite3"
            payload = {
                "contract_id": "contract-1", "assignment_id": "assignment-1",
                "delivery_id": "delivery-1", "artifact_sha256": "c" * 64,
                "payment_trigger": "DELIVERY", "trigger_evidence_id": "delivery-evidence",
                "currency": "USD", "payment_receipt_id": "publisher-payment",
                "fee_receipt_id": "publisher-fee", "payout_receipt_id": "publisher-payout",
                "counterparty": "Publisher", "counterparty_kind": "EXTERNAL_PUBLISHER",
                "payment_status": "SETTLED", "received_by": "Writer",
                "settled_at": "2026-10-01T22:00:00Z",
                "revenue_type": "ONE_TIME", "payment_source_url": "https://example.com/payment",
                "fee_source_url": "https://example.com/fee",
                "payout_source_url": "https://example.com/payout",
                "test": False, "estimated": False, "gross_amount": 40,
                "fee_amount": 4, "net_amount": 36,
            }
            with sqlite3.connect(opportunity_db) as connection:
                connection.executescript("""
                    CREATE TABLE opportunity_evidence (
                        evidence_id TEXT, opportunity_id TEXT, kind TEXT, url TEXT,
                        observed_at TEXT, payload_json TEXT
                    );
                    CREATE TABLE opportunities (opportunity_id TEXT, publisher TEXT);
                    CREATE TABLE opportunity_contracts (
                        contract_id TEXT, opportunity_id TEXT, payment_trigger TEXT,
                        currency TEXT, rate_amount REAL, status TEXT
                    );
                    CREATE TABLE opportunity_assignments (
                        assignment_id TEXT, contract_id TEXT, opportunity_id TEXT, status TEXT
                    );
                    CREATE TABLE opportunity_deliveries (
                        delivery_id TEXT, assignment_id TEXT, opportunity_id TEXT,
                        status TEXT, artifact_sha256 TEXT, delivery_evidence_id TEXT
                    );
                    CREATE TABLE opportunity_publications (
                        delivery_id TEXT, opportunity_id TEXT, publication_id TEXT,
                        status TEXT, publication_evidence_id TEXT
                    );
                """)
                connection.execute(
                    "INSERT INTO opportunity_evidence VALUES(?,?,?,?,?,?)",
                    ("payment-evidence", "opp-1", "payment", "https://example.com/payment",
                     OBSERVED, json.dumps(payload)),
                )
                connection.execute("INSERT INTO opportunities VALUES(?,?)", ("opp-1", "Publisher"))
                connection.execute(
                    "INSERT INTO opportunity_contracts VALUES(?,?,?,?,?,?)",
                    ("contract-1", "opp-1", "DELIVERY", "USD", 40, "TERMS_COMPLETE"),
                )
                connection.execute(
                    "INSERT INTO opportunity_assignments VALUES(?,?,?,?)",
                    ("assignment-1", "contract-1", "opp-1", "DELIVERED"),
                )
                connection.execute(
                    "INSERT INTO opportunity_deliveries VALUES(?,?,?,?,?,?)",
                    ("delivery-1", "assignment-1", "opp-1", "ACCEPTED", "c" * 64,
                     "delivery-evidence"),
                )

            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            try:
                result = ledger.record_commercial_payment(
                    opportunity_db=opportunity_db, payment_evidence_id="payment-evidence",
                )
                duplicate = ledger.record_commercial_payment(
                    opportunity_db=opportunity_db, payment_evidence_id="payment-evidence",
                )
            except sqlite3.Error as error:
                result = {"error": str(error)}
                duplicate = {}
            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipts = {row["receipt_id"]: row for row in records if row["record_type"] == "receipt"}
        self.assertTrue(result.get("payment_id"), result.get("error"))
        self.assertEqual(duplicate.get("payment_id"), result.get("payment_id"))
        self.assertFalse(duplicate.get("inserted"))
        self.assertEqual(
            receipts["writer:money_event:publisher-payment"]["settled_at"],
            "2026-10-01T22:00:00.000000Z",
        )
        self.assertEqual(
            receipts["writer:money_event:publisher-payment"]["components"],
            [{"category": "settled_external_revenue", "amount": "40"}],
        )
        self.assertEqual(
            receipts["writer:money_fee:publisher-fee"]["settled_at"],
            "2026-10-01T22:00:00.000000Z",
        )


if __name__ == "__main__":
    unittest.main()
