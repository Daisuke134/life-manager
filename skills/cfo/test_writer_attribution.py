"""Writer Stripe receipt provenance tests using temporary local ledgers only."""

import sys
import json
import copy
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


def _b2_writer_objects():
    fixtures = ROOT / "skills" / "cfo" / "fixtures" / "economic_attribution"
    refunds = json.loads((fixtures / "stripe-refunds.json").read_text())["data"]
    charges = json.loads((fixtures / "stripe-charges.json").read_text())["data"]
    balances = json.loads((fixtures / "stripe-balance-transactions.json").read_text())["data"]
    charge = next(row for row in charges if row["id"] == "ch_external_usd")
    charge["payment_intent"] = "pi_external_usd"
    return {
        "payment_intents": [{
            "id": "pi_external_usd", "object": "payment_intent",
            "metadata": METADATA, "livemode": True,
            "status": "succeeded", "amount_received": charge["amount_captured"],
            "currency": charge["currency"], "latest_charge": charge,
        }],
        "refunds": refunds,
        "balance_transactions": balances,
    }


def _stripe_subscription_objects():
    metadata = {**METADATA, "product": "writer_archive"}
    subscriptions, invoices, balances = [], [], []
    for key, interval, count in (
        ("month_one", "month", 1), ("month_three", "month", 3),
        ("month_missing", "month", None), ("month_zero", "month", 0),
    ):
        subscription_id = f"sub_{key}"
        payment_intent_id = f"pi_{key}"
        charge_id = f"ch_{key}"
        balance_id = f"txn_{key}"
        epoch = 1790798400
        recurring = {"interval": interval}
        if count is not None:
            recurring["interval_count"] = count
        subscriptions.append({
            "id": subscription_id, "object": "subscription", "metadata": metadata,
            "livemode": True, "status": "active", "created": epoch,
            "items": {"data": [{"price": {
                "unit_amount": 1000, "currency": "usd", "recurring": recurring,
            }}]},
        })
        charge = {
            "id": charge_id, "object": "charge", "amount": 1000,
            "amount_captured": 1000, "amount_refunded": 0,
            "balance_transaction": balance_id, "captured": True, "created": epoch,
            "currency": "usd", "disputed": False, "livemode": True,
            "payment_intent": payment_intent_id, "paid": True, "status": "succeeded",
        }
        invoices.append({
            "id": f"in_{key}", "object": "invoice", "subscription": subscription_id,
            "currency": "usd", "status": "paid", "paid": True, "livemode": True,
            "status_transitions": {"paid_at": epoch}, "amount_paid": 1000,
            "payments": {"data": [{"payment": {
                "payment_intent": {
                    "id": payment_intent_id, "object": "payment_intent",
                    "metadata": metadata, "livemode": True, "status": "succeeded",
                    "amount_received": 1000, "currency": "usd", "latest_charge": charge,
                },
            }}]},
        })
        balances.append({
            "id": balance_id, "object": "balance_transaction", "amount": 1000,
            "fee": 50, "net": 950, "currency": "usd", "created": epoch,
            "available_on": 1790884800, "status": "available", "source": charge_id,
            "type": "charge",
        })
    return {"subscriptions": subscriptions, "invoices": invoices,
            "balance_transactions": balances}


def _commercial_fixture(tmp_path, *, settled_at=None):
    opportunity_db = Path(tmp_path) / "opportunity.sqlite3"
    payload = {
        "contract_id": "contract-1", "assignment_id": "assignment-1",
        "delivery_id": "delivery-1", "artifact_sha256": "c" * 64,
        "payment_trigger": "DELIVERY", "trigger_evidence_id": "delivery-evidence",
        "currency": "USD", "payment_receipt_id": "publisher-payment",
        "fee_receipt_id": "publisher-fee", "payout_receipt_id": "publisher-payout",
        "counterparty": "Publisher", "counterparty_kind": "EXTERNAL_PUBLISHER",
        "payment_status": "SETTLED", "received_by": "Writer",
        "revenue_type": "RECURRING_RETAINER", "recurring_contract_id": "retainer_month",
        "payment_source_url": "https://example.com/payment",
        "fee_source_url": "https://example.com/fee",
        "payout_source_url": "https://example.com/payout",
        "test": False, "estimated": False, "gross_amount": 40,
        "fee_amount": 4, "net_amount": 36,
    }
    if settled_at is not None:
        payload["settled_at"] = settled_at
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
    ledger = MoneyLedger(Path(tmp_path) / "money.sqlite3")
    ledger.record_subscription(
        acquisition_artifact_id=None, stream="editorial_retainer", amount=40,
        currency="USD", interval="month", interval_count=1, status="active",
        external_contract_id="retainer_month", source_url="https://example.com/retainer_month",
        test=False, started_at="2026-09-01T00:00:00Z", observed_at=OBSERVED,
    )
    return opportunity_db, ledger, payload


class WriterStripeProvenanceTest(unittest.TestCase):
    def test_refund_without_livemode_inherits_only_exact_live_parent_mode(self):
        rows = writer_stripe_sync.normalize_objects(
            _b2_writer_objects(), observed_at=OBSERVED,
        )

        refund = next(row for row in rows if row["receipt_type"] == "refund")
        self.assertFalse(refund["test"])
        self.assertEqual(refund["status"], "refunded")
        for mutate in (
            lambda objects: objects["payment_intents"][0].pop("livemode"),
            lambda objects: objects["refunds"][0].update(livemode=False),
        ):
            with self.subTest(mutate=mutate):
                uncertain = _b2_writer_objects()
                mutate(uncertain)
                uncertain_rows = writer_stripe_sync.normalize_objects(
                    uncertain, observed_at=OBSERVED,
                )
                self.assertFalse(any(
                    row["receipt_type"] == "refund" for row in uncertain_rows
                ))

    def test_payment_requires_matching_charge_mode_and_balance_source(self):
        valid = _b2_writer_objects()
        valid["balance_transactions"][0]["type"] = "payment"
        valid_rows = writer_stripe_sync.normalize_objects(valid, observed_at=OBSERVED)
        self.assertTrue(any(
            row.get("receipt_type") == "money" and row.get("status") == "verified_received"
            for row in valid_rows
        ))

        contradicted = _b2_writer_objects()
        contradicted["payment_intents"][0]["latest_charge"]["livemode"] = False
        contradicted["balance_transactions"][0]["source"] = "ch_unrelated"
        contradicted_rows = writer_stripe_sync.normalize_objects(
            contradicted, observed_at=OBSERVED,
        )
        self.assertFalse(any(
            row.get("receipt_type") == "money" and row.get("status") == "verified_received"
            for row in contradicted_rows
        ))

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
                    CREATE TABLE subscription_contracts (
                        subscription_id TEXT PRIMARY KEY, acquisition_artifact_id TEXT,
                        stream TEXT, amount REAL, currency TEXT, interval_name TEXT,
                        status TEXT, external_contract_id TEXT, source_url TEXT,
                        test INTEGER, started_at TEXT, ended_at TEXT, observed_at TEXT
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
                connection.execute(
                    "INSERT INTO subscription_contracts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("legacy-subscription", METADATA["artifact_id"],
                     "self_owned_subscription", 10, "USD", "month", "active",
                     "legacy-subscription", "https://example.com/subscription", 0,
                     "2026-09-01T00:00:00Z", None, OBSERVED),
                )

            before_migration = writer_adapter.adapt_path(
                database, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )
            ledger = MoneyLedger(database)
            ledger.register_artifact(
                artifact_id=METADATA["artifact_id"], run_id=METADATA["run_id"],
                platform="self-owned", lang="en", live_url="https://example.com/article",
                published_at="2026-09-30T19:00:00Z", artifact_sha256="9" * 64,
            )
            ledger.record_money_event(
                artifact_id=METADATA["artifact_id"], scope="artifact",
                stream="self_owned_subscription", revenue_class="direct_writing",
                kind="subscription_charge", amount=10, currency="USD",
                status="verified_received", counterparty="reader",
                external_receipt_id="legacy-invoice", source_url="https://example.com/invoice",
                test=False, occurred_at="2026-09-30T20:00:00Z",
                settled_at="2026-10-01T20:00:00Z",
                external_contract_id="legacy-subscription",
            )
            with ledger._connect() as connection:
                event = connection.execute(
                    "SELECT external_receipt_id,settled_at FROM money_events"
                ).fetchone()
                counts = (
                    connection.execute("SELECT COUNT(*) FROM money_events").fetchone()[0],
                    connection.execute("SELECT COUNT(*) FROM money_fees").fetchone()[0],
                )
                legacy_interval_count = connection.execute(
                    "SELECT interval_count FROM subscription_contracts "
                    "WHERE external_contract_id='legacy-subscription'"
                ).fetchone()["interval_count"]
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
        self.assertEqual(counts, (2, 1))
        self.assertIsNone(legacy_interval_count)
        self.assertEqual(receipt["verification_state"], "pending")
        self.assertIsNone(receipt["settled_at"])
        self.assertEqual(prior_receipt["verification_state"], "pending")
        self.assertIsNone(prior_receipt["settled_at"])
        self.assertNotIn(
            "writer:money_event:legacy-invoice",
            {row.get("receipt_id") for row in records},
        )

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

    def test_available_on_is_retained_and_refund_needs_its_balance_receipt(self):
        objects = _b2_writer_objects()
        rows = writer_stripe_sync.normalize_objects(objects, observed_at=OBSERVED)

        sale = next(row for row in rows if row["receipt_type"] == "money")
        fee = next(row for row in rows if row["receipt_type"] == "fee")
        refund = next(row for row in rows if row["receipt_type"] == "refund")
        self.assertEqual(sale["occurred_at"], "2026-09-30T20:00:00Z")
        self.assertEqual(sale.get("settled_at"), "2026-09-30T21:00:00Z")
        self.assertEqual(fee.get("settled_at"), "2026-09-30T21:00:00Z")
        self.assertEqual(refund["occurred_at"], "2026-09-30T21:30:00Z")
        self.assertEqual(refund["settled_at"], "2026-09-30T22:00:00Z")

        unsettled = copy.deepcopy(objects)
        unsettled["balance_transactions"] = [
            row for row in unsettled["balance_transactions"]
            if row["id"] != "txn_refund_usd"
        ]
        unsettled_rows = writer_stripe_sync.normalize_objects(
            unsettled, observed_at=OBSERVED,
        )
        self.assertFalse(any(row["receipt_type"] == "refund" for row in unsettled_rows))

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
            _b2_writer_objects(),
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
                    "SELECT settled_at FROM money_events "
                    "WHERE external_receipt_id='pi_external_usd'"
                ).fetchone()
                fee = connection.execute(
                    "SELECT occurred_at,settled_at FROM money_fees "
                    "WHERE external_receipt_id='txn_charge_usd'"
                ).fetchone()
            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipts = {row["receipt_id"]: row for row in records if row["record_type"] == "receipt"}
        self.assertEqual(report["inserted"], 3)
        self.assertEqual(event["settled_at"], "2026-09-30T21:00:00Z")
        self.assertEqual(fee["occurred_at"], "2026-09-30T20:00:00Z")
        self.assertEqual(fee["settled_at"], "2026-09-30T21:00:00Z")
        self.assertEqual(
            receipts["writer:money_event:pi_external_usd"]["settled_at"],
            "2026-09-30T21:00:00.000000Z",
        )
        self.assertEqual(
            receipts["writer:money_fee:txn_charge_usd"]["settled_at"],
            "2026-09-30T21:00:00.000000Z",
        )
        self.assertEqual(
            receipts["writer:money_event:re_external_usd"]["settled_at"],
            "2026-09-30T22:00:00.000000Z",
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
                    interval_count=1 if interval in {"month", "year"} else None,
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

    def test_interval_count_survives_stripe_ledger_and_cfo_chain(self):
        rows = writer_stripe_sync.normalize_objects(
            _stripe_subscription_objects(), observed_at=OBSERVED,
        )
        subscriptions = {
            row["external_contract_id"]: row for row in rows
            if row["receipt_type"] == "subscription"
        }
        self.assertEqual(subscriptions["sub_month_one"].get("interval_count"), 1)
        self.assertEqual(subscriptions["sub_month_three"].get("interval_count"), 3)

        with tempfile.TemporaryDirectory() as tmp:
            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            ledger.register_artifact(
                artifact_id=METADATA["artifact_id"], run_id=METADATA["run_id"],
                platform="self-owned", lang="en", live_url="https://example.com/article",
                published_at="2026-09-30T19:00:00Z", artifact_sha256="a" * 64,
            )
            report = _sync_stripe_receipts(ledger, rows)
            with ledger._connect() as connection:
                contract_columns = {
                    row["name"] for row in connection.execute(
                        "PRAGMA table_info(subscription_contracts)"
                    )
                }
                self.assertIn("interval_count", contract_columns)
            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipts = {
            row["receipt_id"]: row for row in records if row["record_type"] == "receipt"
        }
        self.assertEqual(report["rejected"], 1)
        self.assertEqual(
            receipts["writer:money_event:in_month_one"]["revenue_class"],
            "monthly_recurring",
        )
        self.assertEqual(
            receipts["writer:money_event:in_month_three"]["revenue_class"],
            "other_recurring",
        )
        self.assertNotIn("writer:money_event:in_month_missing", receipts)
        self.assertNotIn("writer:money_event:in_month_zero", receipts)
        self.assertFalse(any(
            row["record_type"] == "subscription_snapshot" for row in records
        ))

    def test_invoice_requires_matching_live_charge_and_balance_source(self):
        objects = _stripe_subscription_objects()
        payment = objects["invoices"][0]["payments"]["data"][0]["payment"]["payment_intent"]
        payment["latest_charge"]["livemode"] = False
        objects["balance_transactions"][0]["source"] = "ch_unrelated"

        rows = writer_stripe_sync.normalize_objects(objects, observed_at=OBSERVED)

        self.assertFalse(any(
            row.get("receipt_type") == "money"
            and row.get("external_receipt_id") == "in_month_one"
            and row.get("status") == "verified_received"
            for row in rows
        ))

    def test_contract_id_alone_cannot_cross_stream_currency_or_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MoneyLedger(Path(tmp) / "money.sqlite3")
            current_artifact = METADATA["artifact_id"]
            other_artifact = "other-run__self-owned__en"
            for artifact_id, run_id, lang in (
                (current_artifact, METADATA["run_id"], "en"),
                (other_artifact, "other-run", "en"),
            ):
                ledger.register_artifact(
                    artifact_id=artifact_id, run_id=run_id, platform="self-owned", lang=lang,
                    live_url=f"https://example.com/{run_id}",
                    published_at="2026-09-30T19:00:00Z", artifact_sha256="1" * 64,
                )
            ledger.record_subscription(
                acquisition_artifact_id=other_artifact, stream="self_owned_subscription",
                amount=40, currency="EUR", interval="month", status="active",
                interval_count=1,
                external_contract_id="cross-contract",
                source_url="https://example.com/cross-contract", test=False,
                started_at="2026-09-01T00:00:00Z", observed_at=OBSERVED,
            )
            for kind, scope, artifact_id, stream, currency, receipt in (
                ("subscription_charge", "artifact", current_artifact,
                 "self_owned_subscription", "USD", "wrong-artifact"),
                ("editorial_fee", "account", None, "editorial_fee", "USD", "wrong-stream"),
            ):
                ledger.record_money_event(
                    artifact_id=artifact_id, scope=scope, stream=stream,
                    revenue_class="direct_writing", kind=kind, amount=40,
                    currency=currency, status="verified_received", counterparty="reader",
                    external_receipt_id=receipt, source_url=f"https://example.com/{receipt}",
                    test=False, occurred_at="2026-09-30T20:00:00Z",
                    settled_at="2026-10-01T20:00:00Z",
                    external_contract_id="cross-contract",
                )
            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipts = {row["receipt_id"] for row in records if row["record_type"] == "receipt"}
        self.assertNotIn("writer:money_event:wrong-artifact", receipts)
        self.assertNotIn("writer:money_event:wrong-stream", receipts)

    def test_editorial_fee_contract_requires_real_billing_binding(self):
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
            receipts["writer:money_event:editorial_one_time"]["revenue_class"],
            "one_time",
        )
        self.assertNotIn("writer:money_event:editorial_month", receipts)
        self.assertNotIn("writer:money_event:editorial_year", receipts)
        self.assertNotIn("writer:money_event:editorial_unknown", receipts)

    def test_commercial_settlement_enrichment_preserves_existing_ids_and_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            opportunity_db, ledger, payload = _commercial_fixture(tmp)
            result = ledger.record_commercial_payment(
                opportunity_db=opportunity_db, payment_evidence_id="payment-evidence",
            )
            with ledger._connect() as connection:
                baseline = {
                    "event": tuple(connection.execute(
                        "SELECT event_id,occurred_at,settled_at FROM money_events "
                        "WHERE external_receipt_id='publisher-payment'"
                    ).fetchone()),
                    "fee": tuple(connection.execute(
                        "SELECT fee_id,event_id,occurred_at,settled_at FROM money_fees "
                        "WHERE external_receipt_id='publisher-fee'"
                    ).fetchone()),
                    "payout": tuple(connection.execute(
                        "SELECT payout_id,occurred_at FROM payouts "
                        "WHERE external_receipt_id='publisher-payout'"
                    ).fetchone()),
                    "allocation": tuple(connection.execute(
                        "SELECT payout_id,event_id,amount,currency FROM payout_allocations"
                    ).fetchone()),
                    "binding": tuple(connection.execute(
                        "SELECT payment_id,event_id,payout_id,received_at "
                        "FROM commercial_payment_bindings"
                    ).fetchone()),
                }
            payload["settled_at"] = "2026-10-01T23:30:00Z"
            with sqlite3.connect(opportunity_db) as connection:
                connection.execute(
                    "UPDATE opportunity_evidence SET observed_at=?,payload_json=? "
                    "WHERE evidence_id='payment-evidence'",
                    ("2026-10-02T01:00:00Z", json.dumps(payload)),
                )
            try:
                duplicate = ledger.record_commercial_payment(
                    opportunity_db=opportunity_db, payment_evidence_id="payment-evidence",
                )
            except (MoneyInvariant, sqlite3.Error) as error:
                duplicate = {"error": str(error)}
            with ledger._connect() as connection:
                after = {
                    "event": tuple(connection.execute(
                        "SELECT event_id,occurred_at,settled_at FROM money_events "
                        "WHERE external_receipt_id='publisher-payment'"
                    ).fetchone()),
                    "fee": tuple(connection.execute(
                        "SELECT fee_id,event_id,occurred_at,settled_at FROM money_fees "
                        "WHERE external_receipt_id='publisher-fee'"
                    ).fetchone()),
                    "payout": tuple(connection.execute(
                        "SELECT payout_id,occurred_at FROM payouts "
                        "WHERE external_receipt_id='publisher-payout'"
                    ).fetchone()),
                    "allocation": tuple(connection.execute(
                        "SELECT payout_id,event_id,amount,currency FROM payout_allocations"
                    ).fetchone()),
                    "binding": tuple(connection.execute(
                        "SELECT payment_id,event_id,payout_id,received_at "
                        "FROM commercial_payment_bindings"
                    ).fetchone()),
                }
            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at="2026-10-02T02:00:00Z",
                trailing_start="2026-09-01T00:00:00Z",
            )
            conflicting = dict(payload, settled_at="2026-10-01T22:30:00Z")
            with sqlite3.connect(opportunity_db) as connection:
                connection.execute(
                    "UPDATE opportunity_evidence SET payload_json=? WHERE evidence_id=?",
                    (json.dumps(conflicting), "payment-evidence"),
                )
            with self.assertRaisesRegex(MoneyInvariant, "provenance conflicts"):
                ledger.record_commercial_payment(
                    opportunity_db=opportunity_db, payment_evidence_id="payment-evidence",
                )
            conflicting = dict(payload, gross_amount=41, net_amount=37)
            with sqlite3.connect(opportunity_db) as connection:
                connection.execute(
                    "UPDATE opportunity_evidence SET payload_json=? WHERE evidence_id=?",
                    (json.dumps(conflicting), "payment-evidence"),
                )
            with self.assertRaisesRegex(MoneyInvariant, "contracted rate"):
                ledger.record_commercial_payment(
                    opportunity_db=opportunity_db, payment_evidence_id="payment-evidence",
                )

        receipts = {row["receipt_id"]: row for row in records if row["record_type"] == "receipt"}
        self.assertTrue(result.get("payment_id"), result.get("error"))
        self.assertEqual(duplicate.get("payment_id"), result.get("payment_id"))
        self.assertFalse(duplicate.get("inserted"))
        self.assertEqual(after["event"][0:2], baseline["event"][0:2])
        self.assertEqual(after["event"][2], "2026-10-01T23:30:00Z")
        self.assertEqual(after["fee"][0:3], baseline["fee"][0:3])
        self.assertEqual(after["fee"][3], "2026-10-01T23:30:00Z")
        self.assertEqual(after["payout"], baseline["payout"])
        self.assertEqual(after["allocation"], baseline["allocation"])
        self.assertEqual(after["binding"], baseline["binding"])
        self.assertEqual(
            receipts["writer:money_event:publisher-payment"]["settled_at"],
            None,
        )
        self.assertEqual(
            receipts["writer:money_event:publisher-payment"]["verification_state"],
            "pending",
        )
        self.assertEqual(
            receipts["writer:money_event:publisher-payment"]["components"],
            [{"category": "pending_revenue", "amount": "40"}],
        )
        self.assertEqual(
            receipts["writer:money_event:publisher-payment"]["revenue_class"],
            "monthly_recurring",
        )
        self.assertNotIn("writer:money_fee:publisher-fee", receipts)

    def test_formal_settled_publisher_receipt_reaches_cfo_as_editorial_fee(self):
        with tempfile.TemporaryDirectory() as tmp:
            opportunity_db, ledger, _ = _commercial_fixture(
                tmp, settled_at="2026-10-01T22:00:00Z",
            )
            result = ledger.record_commercial_payment(
                opportunity_db=opportunity_db, payment_evidence_id="payment-evidence",
            )
            records = writer_adapter.adapt_path(
                ledger.path, snapshot_at=OBSERVED, trailing_start="2026-09-01T00:00:00Z",
            )

        receipts = {row["receipt_id"]: row for row in records if row["record_type"] == "receipt"}
        self.assertTrue(result.get("payment_id"))
        self.assertEqual(
            receipts["writer:money_event:publisher-payment"]["settled_at"],
            "2026-10-01T22:00:00.000000Z",
        )
        self.assertEqual(
            receipts["writer:money_fee:publisher-fee"]["components"],
            [{"category": "other_measured_cost", "amount": "4"}],
        )


if __name__ == "__main__":
    unittest.main()
