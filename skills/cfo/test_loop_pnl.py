"""Fixture tests for loop_pnl: one per source adapter plus the table/unverified contract."""

import json
import sqlite3
import sys
import tempfile
import unittest
import copy
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import loop_pnl as m  # noqa: E402
from skills.cfo import economic_attribution as contract  # noqa: E402
from skills.cfo.adapters import writer as writer_adapter  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "loop_pnl"
DAY = date(2026, 9, 26)  # Asia/Tokyo: 2026-09-25T15:00Z .. 2026-09-26T15:00Z
SNAPSHOT = "2026-10-01T00:00:00.000000Z"
TRAILING_START = "2026-09-24T00:00:00.000000Z"


def fixture(name):
    return json.loads((FIX / name).read_text())


def sums(entries):
    out = {}
    for e in entries:
        key = (e.loop_id, e.kind, e.currency)
        out[key] = out.get(key, Decimal(0)) + e.amount
    return out


def b7_receipt(receipt_id, *, loop_id="self-build", provider="stripe",
               occurred_at="2026-09-30T12:00:00Z", components=None,
               currency="USD"):
    components = components or [{"category": contract.REVENUE, "amount": "1"}]
    return {
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "receipt",
        "receipt_id": receipt_id,
        "product_loop_id": loop_id,
        "provider": provider,
        "currency": currency,
        "occurred_at": occurred_at,
        "settled_at": occurred_at,
        "verification_state": "verified",
        "revenue_class": "one_time" if any(
            component["category"] == contract.REVENUE
            for component in components
        ) else None,
        "evidence_refs": [f"{provider}://receipts/{receipt_id}"],
        "components": components,
    }


def b7_coverage(loop_id, projection, *, categories=None, source_id=None):
    return {
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": loop_id,
        "source_id": source_id or f"{loop_id}-b7",
        "projection": projection,
        "window_start": TRAILING_START if projection == "trailing" else None,
        "window_end": SNAPSHOT,
        "coverage_state": "complete",
        "reason": None,
        "covered_categories": categories or (
            ["mrr", "liquid_balance"] if projection == "as_of"
            else list(contract.COUNTED_CATEGORIES)
        ),
        "observed_at": SNAPSHOT,
        "evidence_refs": [f"lm-cfo://coverage/{loop_id}/{projection}"],
    }


def complete_b7_coverage(*, omit=()):
    return [
        b7_coverage(loop_id, projection)
        for loop_id in contract.PRODUCT_LOOP_IDS
        if loop_id not in set(omit)
        for projection in ("historical", "trailing", "as_of")
    ]


class AlpacaTest(unittest.TestCase):
    def test_builds_official_alpaca_account_readback_without_inventing_pnl(self):
        pages = {
            "/v2/account": {
                "id": "acct-1", "cash": "0", "currency": "USD",
                "status": "ACTIVE",
            },
            "/v2/orders": [],
        }

        def get(url, headers):
            from urllib.parse import urlparse
            return pages[urlparse(url).path]

        payload = m.build_alpaca_readback(
            trailing_start=TRAILING_START, get=get,
            api_key="key", api_secret="secret", observed_at=SNAPSHOT,
        )
        self.assertEqual(payload["provider"], "alpaca")
        self.assertEqual(payload["balance"]["amount"], "0")
        self.assertEqual(payload["readback"]["orders_count"], 0)
        self.assertNotIn("outcomes", payload)

    def test_alpaca_order_page_at_limit_fails_closed_without_cursor_proof(self):
        pages = {
            "/v2/account": {"id": "acct-1", "cash": "0", "currency": "USD"},
            "/v2/orders": [{} for _ in range(500)],
        }

        def get(url, headers):
            from urllib.parse import urlparse
            return pages[urlparse(url).path]

        with self.assertRaisesRegex(ValueError, "alpaca_orders_pagination_unknown"):
            m.build_alpaca_readback(
                trailing_start=TRAILING_START, get=get,
                api_key="key", api_secret="secret", observed_at=SNAPSHOT,
            )

    def test_fifo_realized_and_fees_for_the_jst_day(self):
        entries = list(m.alpaca_entries(fixture("alpaca_activities.json"), DAY))
        self.assertEqual(sums(entries), {
            ("investment", "revenue", "USDC"): Decimal("0.5"),  # 0.001*(81000-80000) + 0.0005*(81000-82000)
            ("investment", "revenue", "USD"): Decimal("10"),
            ("investment", "cost", "USD"): Decimal("0.02"),
        })
        self.assertTrue(all(e.receipt_id.startswith("alpaca:activity:") for e in entries))

    def test_date_only_fee_uses_us_eastern_trade_date(self):
        fee = {"id": "f", "activity_type": "FEE", "date": "2026-09-25", "net_amount": "-0.03"}
        # 2026-09-25 00:00 EDT = 13:00 JST on 09-25; not on 09-26.
        self.assertEqual(list(m.alpaca_entries([fee], DAY)), [])
        self.assertEqual(sums(m.alpaca_entries([fee], date(2026, 9, 25))),
                         {("investment", "cost", "USD"): Decimal("0.03")})

    def test_sell_without_lot_fails_closed(self):
        rows = [{"id": "s", "activity_type": "FILL", "symbol": "X", "side": "sell", "qty": "1",
                 "price": "1", "transaction_time": "2026-09-26T01:00:00Z"}]
        with self.assertRaises(ValueError):
            list(m.alpaca_entries(rows, DAY))

    def test_paginates_and_requires_live_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            creds = Path(tmp) / "c.json"
            creds.write_text(json.dumps({"credentials": [{"service": "app.alpaca.markets"}]}))
            with self.assertRaises(LookupError):
                m.alpaca_activities(cred_path=creds)
            creds.write_text(json.dumps({"credentials": [{"service": "app.alpaca.markets",
                                                          "live_api_key": "k", "live_api_secret": "s"}]}))
            pages = [[{"id": str(i)} for i in range(100)], [{"id": "last"}]]
            urls = []
            rows = m.alpaca_activities(get=lambda url, h: (urls.append(url), pages.pop(0))[1],
                                       cred_path=creds)
        self.assertEqual(len(rows), 101)
        self.assertIn("page_token=99", urls[1])


class StripeTest(unittest.TestCase):
    def test_b7_window_defaults_to_runtime_now_not_future_day_end(self):
        now = datetime(2026, 10, 3, 0, 5, tzinfo=timezone.utc)
        try:
            end, start = m._b7_window(
                DAY, snapshot_at=None, trailing_start=None, now=now,
            )
        except TypeError:
            self.fail("_b7_window must accept an injected runtime instant")
        self.assertEqual(end, "2026-10-03T00:05:00.000000Z")
        self.assertEqual(start, "2026-09-03T00:05:00.000000Z")

    def test_builds_complete_official_stripe_readback_envelope(self):
        pages = {
            "/v1/balance_transactions": [
                {"object": "list", "url": "/v1/balance_transactions", "data": [{"id": "txn_1", "created": 1759000000}], "has_more": False},
            ],
            "/v1/charges": [
                {"object": "list", "url": "/v1/charges", "data": [{"id": "ch_1", "created": 1759000000}], "has_more": False},
            ],
            "/v1/refunds": [
                {"object": "list", "url": "/v1/refunds", "data": [], "has_more": False},
            ],
            "/v1/subscriptions": [
                {"object": "list", "url": "/v1/subscriptions", "data": [], "has_more": False},
            ],
        }
        calls = []

        def get(url, headers):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            calls.append(parsed.path)
            return pages[parsed.path].pop(0)

        payload = m.build_stripe_readback(
            snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
            get=get, api_key="rk_live_test",
            default_economic_category=contract.REVENUE,
        )
        self.assertEqual(payload["readback"]["provider"], "stripe")
        self.assertEqual(payload["readback"]["provenance"], "stripe_api")
        self.assertEqual(payload["readback"]["read_at"], SNAPSHOT)
        self.assertEqual(
            payload["readback"]["classification_policy"],
            {
                "default_economic_category": contract.REVENUE,
                "source": "explicit_runtime_config",
            },
        )
        self.assertEqual(payload["readback"]["queries"]["trailing"]["start"], TRAILING_START)
        self.assertTrue(payload["readback"]["queries"]["historical"]["account_inception"])
        self.assertEqual(set(calls), set(pages))

    def test_stripe_list_requires_explicit_boolean_has_more(self):
        def get(url, headers):
            return {"object": "list", "url": "/v1/charges", "data": []}

        with self.assertRaisesRegex(ValueError, "stripe_readback_payload_invalid"):
            m._stripe_list_all("/v1/charges", "rk_live_test", get)

    def test_stripe_list_paginates_with_strict_cursor_progress(self):
        pages = [
            {"object": "list", "url": "/v1/charges", "data": [{"id": "ch_1"}], "has_more": True},
            {"object": "list", "url": "/v1/charges", "data": [{"id": "ch_2"}], "has_more": False},
        ]
        urls = []

        def get(url, headers):
            urls.append(url)
            return pages.pop(0)

        result = m._stripe_list_all("/v1/charges", "rk_live_test", get)
        self.assertEqual([row["id"] for row in result["data"]], ["ch_1", "ch_2"])
        self.assertIn("starting_after=ch_1", urls[1])

    def test_stripe_list_rejects_non_progressing_cursor(self):
        pages = [
            {"object": "list", "url": "/v1/charges", "data": [{"id": "ch_1"}], "has_more": True},
            {"object": "list", "url": "/v1/charges", "data": [{"id": "ch_1"}], "has_more": False},
        ]

        with self.assertRaisesRegex(ValueError, "stripe_readback_cursor_invalid"):
            m._stripe_list_all("/v1/charges", "rk_live_test", lambda url, headers: pages.pop(0))

    def test_stripe_list_rejects_cursor_cycle_across_pages(self):
        pages = [
            {"object": "list", "url": "/v1/charges", "data": [{"id": "ch_a"}], "has_more": True},
            {"object": "list", "url": "/v1/charges", "data": [{"id": "ch_b"}], "has_more": True},
            {"object": "list", "url": "/v1/charges", "data": [{"id": "ch_a"}], "has_more": False},
        ]

        with self.assertRaisesRegex(ValueError, "stripe_readback_cursor_invalid"):
            m._stripe_list_all("/v1/charges", "rk_live_test", lambda url, headers: pages.pop(0))

    def test_stripe_list_rejects_duplicate_ids_inside_page(self):
        page = {
            "object": "list", "url": "/v1/charges",
            "data": [{"id": "ch_a"}, {"id": "ch_a"}], "has_more": False,
        }
        with self.assertRaisesRegex(ValueError, "stripe_readback_cursor_invalid"):
            m._stripe_list_all("/v1/charges", "rk_live_test", lambda url, headers: page)

    def test_stripe_list_rejects_empty_page_with_more(self):
        page = {"object": "list", "url": "/v1/refunds", "data": [], "has_more": True}
        with self.assertRaisesRegex(ValueError, "stripe_readback_cursor_invalid"):
            m._stripe_list_all("/v1/refunds", "rk_live_test", lambda url, headers: page)

    def test_balance_transactions_to_entries(self):
        entries = list(m.stripe_entries(fixture("stripe_balance_transactions.json")))
        self.assertEqual(sums(entries), {
            ("self-build", "revenue", "USD"): Decimal("19.99"),
            ("self-build", "revenue", "JPY"): Decimal("3000"),
            ("self-build", "refund", "USD"): Decimal("5"),
            ("self-build", "cost", "USD"): Decimal("0.88"),
            ("self-build", "cost", "JPY"): Decimal("108"),
        })

    def test_unhandled_type_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "stripe_unhandled_txn_type:adjustment"):
            list(m.stripe_entries([{"id": "txn_d", "type": "adjustment", "amount": -1999,
                                    "fee": 1500, "currency": "usd"}]))

    def test_google_billing_csv_becomes_official_actual_cost_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cost-table.csv"
            rows = [
                ["合計お支払い額", "¥10.50", ""],
                ["通貨", "JPY", ""],
                [
                    "サービスの説明", "SKU の説明", "費用のタイプ", "使用開始日",
                    "四捨五入前の費用（¥）", "プロジェクト ID",
                ],
                ["Places API", "Places Text Search", "使用量", "2026-09-30", "10", "project"],
                ["Google Cloud", "税", "税金", "2026-09-30", "1", "project"],
                ["Google Cloud", "丸め", "丸めエラー", "2026-09-30", "-0.5", "project"],
            ]
            with path.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream).writerows(rows)
            payload = m.google_billing_actual_cost_readback(
                path, invoice_month="2026-09", snapshot_at=SNAPSHOT,
                trailing_start=TRAILING_START,
            )

        self.assertEqual(payload["readback"]["kind"], "official_billing_readback")
        self.assertEqual(payload["sources"][0]["product_loop_ids"], ["cfo"])
        self.assertEqual(payload["documents"][0]["provider"], "google-cloud")
        self.assertEqual(
            [line["amount"] for line in payload["documents"][0]["line_items"]],
            ["10", "0.5"],
        )
        self.assertEqual(
            payload["documents"][0]["line_items"][0]["allocations"][0]["product_loop_id"],
            "cfo",
        )

    def test_google_billing_readback_exposes_invoice_variance_without_estimate_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cost-table.csv"
            rows = [
                ["合計お支払い額", "¥20", ""],
                ["通貨", "JPY", ""],
                ["サービスの説明", "SKU の説明", "費用のタイプ", "使用開始日", "四捨五入前の費用（¥）", "プロジェクト ID"],
                ["Geocoding API", "Geocoding", "使用量", "2026-09-30", "12", "project"],
                ["Google Cloud", "税", "税金", "2026-09-30", "2", "project"],
            ]
            with path.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream).writerows(rows)
            payload = m.google_billing_actual_cost_readback(
                path, invoice_month="2026-09", snapshot_at=SNAPSHOT,
                trailing_start=TRAILING_START,
            )
        self.assertEqual(payload["readback"]["variance"], {
            "invoice_total": "20", "positive_cost_total": "12", "tax_and_rounding": "8",
        })
        self.assertTrue(all(line["basis"] == "official_invoice" for line in payload["documents"][0]["line_items"]))

    def test_google_billing_includes_previous_month_usage_row_in_selected_invoice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cost-table.csv"
            rows = [
                ["合計お支払い額", "¥0.000300", ""],
                ["通貨", "JPY", ""],
                ["サービスの説明", "SKU の説明", "費用のタイプ", "使用開始日", "四捨五入前の費用（¥）", "プロジェクト ID"],
                ["Cloud Storage", "Standard storage", "使用量", "2026-08-31", "0.000300", "project"],
            ]
            with path.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream).writerows(rows)
            payload = m.google_billing_actual_cost_readback(
                path, invoice_month="2026-09", snapshot_at=SNAPSHOT,
                trailing_start=TRAILING_START,
            )

        line = payload["documents"][0]["line_items"][0]
        self.assertEqual(line["amount"], "0.0003")
        self.assertEqual(line["occurred_at"], "2026-08-31T00:00:00Z")
        self.assertEqual(payload["readback"]["variance"], {
            "invoice_total": "0.0003", "positive_cost_total": "0.0003", "tax_and_rounding": "0",
        })

    def test_google_billing_rejects_missing_and_invalid_usage_dates(self):
        for usage_date in ("", "2026-02-30"):
            with self.subTest(usage_date=usage_date):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "cost-table.csv"
                    rows = [
                        ["合計お支払い額", "¥0.000300", ""],
                        ["通貨", "JPY", ""],
                        ["サービスの説明", "SKU の説明", "費用のタイプ", "使用開始日", "四捨五入前の費用（¥）", "プロジェクト ID"],
                        ["Cloud Storage", "Standard storage", "使用量", usage_date, "0.000300", "project"],
                    ]
                    with path.open("w", encoding="utf-8", newline="") as stream:
                        csv.writer(stream).writerows(rows)
                    with self.assertRaisesRegex(ValueError, "google_billing_usage_date_invalid"):
                        m.google_billing_actual_cost_readback(
                            path, invoice_month="2026-09", snapshot_at=SNAPSHOT,
                            trailing_start=TRAILING_START,
                        )

    def test_test_mode_key_is_not_a_live_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            creds = Path(tmp) / "c.json"
            creds.write_text(json.dumps({"credentials": [{"service": "stripe-test", "api_key": "rk_test_x"}]}))
            with self.assertRaisesRegex(LookupError, "credential_missing"):
                m.stripe_transactions(DAY, cred_path=creds)
            creds.write_text(json.dumps({"credentials": [{"service": "stripe", "api_key": "rk_live_x"}]}))
            pages = [{"data": [{"id": "txn_1"}], "has_more": True}, {"data": [{"id": "txn_2"}], "has_more": False}]
            rows = m.stripe_transactions(DAY, get=lambda url, h: pages.pop(0), cred_path=creds)
        self.assertEqual([r["id"] for r in rows], ["txn_1", "txn_2"])


class X402Test(unittest.TestCase):
    def fake_rpc(self):
        data = fixture("base_rpc.json")
        start = int(m.day_window(DAY)[0].timestamp())
        genesis, first = start - 2000, 1000  # day starts at block 1000; head is after the day
        head = first + 43200 + 100
        for log in data["logs"]:
            log["blockNumber"] = hex(first + 5)
            log["topics"][0] = m.TRANSFER_TOPIC

        def post(payload):
            method, params = payload["method"], payload["params"]
            if method == "eth_blockNumber":
                return {"result": hex(head)}
            if method == "eth_getBlockByNumber":
                return {"result": {"timestamp": hex(genesis + 2 * int(params[0], 16))}}
            if method == "eth_getLogs":
                f = params[0]
                self.assertLessEqual(int(f["toBlock"], 16) - int(f["fromBlock"], 16), m.LOG_SPAN - 1)

                def match(log):
                    if not int(f["fromBlock"], 16) <= int(log["blockNumber"], 16) <= int(f["toBlock"], 16):
                        return False
                    return all(want is None or log["topics"][i] in want
                               for i, want in enumerate(f["topics"]) if i)
                return {"result": [log for log in data["logs"] if match(log)]}
            tx = data["transactions"][params[0]]
            return {"result": {"status": tx["status"]} if method == "eth_getTransactionReceipt"
                    else {"input": tx["input"]}}
        return m.BaseRpc(post=post)

    def test_authorized_transfers_only_and_own_wallets_excluded(self):
        pay_to = {"0x" + "a" * 40}
        owned = pay_to | {"0x" + "b" * 40}
        entries = list(m.x402_entries(DAY, self.fake_rpc(), pay_to, owned))
        self.assertEqual(sums(entries), {
            ("agent-economy", "revenue", "USDC"): Decimal("0.01"),
            ("agent-economy", "cost", "USDC"): Decimal("0.003"),
        })
        self.assertEqual(sorted(e.receipt_id for e in entries), ["base:0xbuy:4", "base:0xpay:1"])

    def test_wallets_from_seller_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("sales-0x" + "A" * 40 + ".jsonl", "llm-resale-spend-0x" + "b" * 40 + ".json"):
                (Path(tmp) / name).write_text("")
            pay_to, owned = m.x402_wallets(Path(tmp))
        self.assertEqual(pay_to, {"0x" + "a" * 40})
        self.assertEqual(owned, {"0x" + "a" * 40, "0x" + "b" * 40})


class MarketplaceTest(unittest.TestCase):
    def test_payment_received_rows_for_the_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "marketplace-ledger.sqlite3"
            db = sqlite3.connect(ledger)
            db.execute("CREATE TABLE marketplace_events (platform TEXT, event_type TEXT, receipt_id TEXT,"
                       " amount_minor INTEGER, currency TEXT, occurred_at TEXT)")
            db.executemany("INSERT INTO marketplace_events VALUES (:platform, :event_type, :receipt_id,"
                           " :amount_minor, :currency, :occurred_at)", fixture("marketplace_payments.json"))
            db.commit()
            db.close()
            entries = list(m.marketplace_entries("lancers", ledger, DAY))
        self.assertEqual(entries, [m.Entry("gig-lancers", "revenue", Decimal(45000), "JPY",
                                           "lancers:lancers-pay-1")])

    def test_missing_or_empty_ledger_is_an_error_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.sqlite3"
            empty.write_text("")
            for path in (empty, Path(tmp) / "absent.sqlite3"):
                with self.assertRaises(FileNotFoundError):
                    list(m.marketplace_entries("coconala", path, DAY))


class CapafyTest(unittest.TestCase):
    NOW = datetime(2026, 9, 26, 2, 0, 0, tzinfo=timezone.utc)  # 11:00 JST 09-26: DAY is "today"

    def test_fresh_snapshot_yields_revenue_and_refund_for_the_day(self):
        entries = list(m.capafy_entries(DAY, FIX / "capafy_analytics_fresh.json", now=self.NOW))
        self.assertEqual(sums(entries), {
            ("capafy", "revenue", "USD"): Decimal("12.5"),
            ("capafy", "refund", "USD"): Decimal("1.0"),
        })
        self.assertTrue(all(e.receipt_id.startswith("capafy:snapshot:2026-09-26T01:00:00Z:") for e in entries))

    def test_snapshot_older_than_6h_for_todays_run_is_stale(self):
        stale_now = self.NOW.replace(hour=8)  # observed_at 01:00Z, now 08:00Z -> 7h old, still JST 09-26
        with self.assertRaisesRegex(ValueError, "capafy_snapshot_stale"):
            list(m.capafy_entries(DAY, FIX / "capafy_analytics_fresh.json", now=stale_now))

    def test_account_totals_not_fresh_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "capafy_account_totals_status:stale"):
            list(m.capafy_entries(DAY, FIX / "capafy_analytics_stale_status.json", now=self.NOW))

    def test_no_trend_row_for_date_fails_closed(self):
        with self.assertRaisesRegex(LookupError, "capafy_no_trend_row_for_date"):
            list(m.capafy_entries(DAY, FIX / "capafy_analytics_missing_row.json", now=self.NOW))

    def test_malformed_snapshot_fails_closed(self):
        with self.assertRaises(ValueError):
            list(m.capafy_entries(DAY, FIX / "capafy_analytics_malformed.json", now=self.NOW))


class MobileAppsTest(unittest.TestCase):
    def test_fresh_rows_sum_revenue_and_expose_mrr_notes(self):
        notes = {}
        entries = list(m.mobile_apps_entries(DAY, FIX / "business_outcomes_fresh.jsonl", notes=notes))
        self.assertEqual(sums(entries), {("mobile-apps", "revenue", "UNKNOWN"): Decimal("7.75")})
        self.assertEqual(notes["mrr"], {"anicca-ios": "20.34", "honne-ai": "0.0"})

    def test_revenuecat_unavailable_for_one_product_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "mobile_apps_revenuecat_unavailable:anicca-ios"):
            list(m.mobile_apps_entries(DAY, FIX / "business_outcomes_stale.jsonl"))

    def test_missing_business_date_row_fails_closed(self):
        with self.assertRaisesRegex(LookupError, "mobile_apps_missing_business_date_row:honne-ai"):
            list(m.mobile_apps_entries(DAY, FIX / "business_outcomes_missing.jsonl"))

    def test_malformed_line_leaves_that_product_missing(self):
        with self.assertRaisesRegex(LookupError, "mobile_apps_missing_business_date_row:anicca-ios"):
            list(m.mobile_apps_entries(DAY, FIX / "business_outcomes_malformed.jsonl"))

    def test_missing_file_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            list(m.mobile_apps_entries(DAY, FIX / "does-not-exist.jsonl"))


class WriterMoneyTest(unittest.TestCase):
    def test_verified_money_events_and_fees_become_receipt_backed_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "money.sqlite3"
            db = sqlite3.connect(database)
            db.execute("CREATE TABLE money_events (event_id TEXT, kind TEXT, amount REAL, currency TEXT, status TEXT, external_receipt_id TEXT, occurred_at TEXT)")
            db.execute("CREATE TABLE money_fees (fee_id TEXT, fee_kind TEXT, amount REAL, currency TEXT, status TEXT, external_receipt_id TEXT, observed_at TEXT)")
            db.executemany("INSERT INTO money_events VALUES (?,?,?,?,?,?,?)", [
                ("sale-1", "sale", 12.5, "USD", "verified_received", "pub-1", "2026-09-26T03:00:00Z"),
                ("refund-1", "refund", 2.5, "USD", "refunded", "refund-1", "2026-09-26T04:00:00Z"),
                ("pending-1", "sale", 99, "USD", "pending", "pending-1", "2026-09-26T05:00:00Z"),
            ])
            db.execute("INSERT INTO money_fees VALUES (?,?,?,?,?,?,?)",
                       ("fee-1", "platform", 1.0, "USD", "verified", "fee-1", "2026-09-26T06:00:00Z"))
            db.commit()
            db.close()

            records = writer_adapter.adapt_path(
                database, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
            )

        receipts = [record for record in records if record["record_type"] == "receipt"]
        self.assertEqual(
            {record["receipt_id"] for record in receipts},
            {"writer:money_event:pub-1", "writer:money_event:refund-1", "writer:money_fee:fee-1"},
        )
        self.assertEqual(
            {record["receipt_id"]: record["components"] for record in receipts},
            {
                "writer:money_event:pub-1": [{"category": "settled_external_revenue", "amount": "12.5"}],
                "writer:money_event:refund-1": [{"category": "refund", "amount": "2.5"}],
                "writer:money_fee:fee-1": [{"category": "other_measured_cost", "amount": "1"}],
            },
        )


class UsageTest(unittest.TestCase):
    def test_dedupe_map_missing_and_unattributed(self):
        notes = {}
        job_map = {"hf-gig-reply-detector": "gig-coconala"}
        entries = list(m.usage_entries([FIX / "agent_usage.jsonl"], DAY, job_map, notes))
        self.assertEqual(sums(entries), {
            ("gig-lancers", "cost", m.USAGE_CURRENCY): Decimal("0.5"),
            ("gig-coconala", "cost", m.USAGE_CURRENCY): Decimal("0.25"),
        })
        self.assertEqual(notes["missing_cost_events"], {"job-hunter": 1})
        self.assertEqual(notes["unattributed"]["codex-brain"]["events"], 1)
        self.assertEqual(notes["unparsed_lines"], 1)


class B7IntegrationTest(unittest.TestCase):
    def test_absent_b1_b3_artifacts_are_unconnected_and_read_errors_keep_adapter_status(self):
        source_loops = ("capafy", "self-build", "affiliate")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            isolated_env = {
                "LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES": str(root / "mobile.jsonl"),
                "LM_CFO_WRITER_MONEY": str(root / "writer.sqlite3"),
            }
            absent = m.collect_b7_records(
                snapshot_at=SNAPSHOT, trailing_start=TRAILING_START, env=isolated_env,
            )
            configured = m.collect_b7_records(
                snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                env={
                    **isolated_env,
                    "LM_CFO_CAPAFY_ANALYTICS": str(root / "missing-capafy.json"),
                    "LM_CFO_STRIPE_READBACK": str(root / "missing-stripe.json"),
                    "LM_CFO_AFFILIATE_READBACK": str(root / "missing-affiliate.json"),
                },
            )

        configured_reasons = {
            "capafy": {
                "historical": "source_unconnected", "trailing": "source_unconnected",
                "as_of": "source_unconnected",
            },
            "self-build": {
                "historical": "read_failed", "trailing": "read_failed", "as_of": "read_failed",
            },
            "affiliate": {
                "historical": "read_failed", "trailing": "read_failed", "as_of": "missing_category",
            },
        }
        for records, expected_reasons in (
            (absent, {
                loop_id: {
                    "historical": "source_unconnected", "trailing": "source_unconnected",
                    "as_of": "source_unconnected",
                }
                for loop_id in source_loops
            }),
            (configured, configured_reasons),
        ):
            for loop_id in source_loops:
                rows = [
                    row for row in records
                    if row.get("record_type") == "coverage"
                    and row.get("product_loop_id") == loop_id
                ]
                self.assertEqual(len(rows), 3, loop_id)
                self.assertEqual(
                    {row["projection"]: row["reason"] for row in rows}, expected_reasons[loop_id],
                )

    def test_b2_category_tag_without_product_loop_stays_unverified(self):
        charge_created = 1790769600  # 2026-09-30T12:00:00Z

        def stripe_list(name, data):
            return {
                "object": "list",
                "url": f"/v1/{name}",
                "data": data,
                "has_more": False,
            }

        payload = {
            "balance_transactions": stripe_list("balance_transactions", [{
                "object": "balance_transaction",
                "id": "txn_untagged",
                "type": "charge",
                "source": "ch_untagged",
                "amount": 1000,
                "fee": 0,
                "net": 1000,
                "currency": "usd",
                "status": "available",
                "created": charge_created,
                "available_on": charge_created,
            }]),
            "charges": stripe_list("charges", [{
                "object": "charge",
                "id": "ch_untagged",
                "created": charge_created,
                "amount": 1000,
                "amount_captured": 1000,
                "amount_refunded": 0,
                "currency": "usd",
                "status": "succeeded",
                "paid": True,
                "captured": True,
                "livemode": True,
                "disputed": False,
                "balance_transaction": "txn_untagged",
                "description": "Anicca Pro",
                "metadata": {
                    "lm_economic_category": contract.REVENUE,
                    "owner": "self-build",
                },
            }]),
            "refunds": stripe_list("refunds", []),
            "subscriptions": stripe_list("subscriptions", []),
            "readback": {
                "provider": "stripe",
                "provenance": "stripe_api",
                "read_at": SNAPSHOT,
                "queries": {
                    "trailing": {
                        "start": TRAILING_START,
                        "end": SNAPSHOT,
                        "has_more": False,
                    },
                    "historical": {
                        "history_start": "2026-01-01T00:00:00Z",
                        "end": SNAPSHOT,
                        "has_more": False,
                        "account_inception": True,
                    },
                },
                "classification_policy": {
                    "default_economic_category": contract.REVENUE,
                    "source": "explicit_runtime_config",
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readback_path = root / "stripe.json"
            readback_path.write_text(json.dumps(payload), encoding="utf-8")
            env = {
                "LM_CFO_STRIPE_READBACK": str(readback_path),
                "LM_CFO_STRIPE_DEFAULT_ECONOMIC_CATEGORY": contract.REVENUE,
                "LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES": str(root / "mobile.jsonl"),
                "LM_CFO_WRITER_MONEY": str(root / "writer.sqlite3"),
            }
            with patch.object(m, "marketplace_ledgers", return_value={}):
                records = m.collect_b7_records(
                    snapshot_at=SNAPSHOT,
                    trailing_start=TRAILING_START,
                    env=env,
                )

        stripe_rows = [
            row for row in records
            if row.get("product_loop_id") == "self-build"
            and any(str(ref).startswith("stripe://") for ref in row.get("evidence_refs", []))
        ]
        verified_revenue = [
            row for row in stripe_rows
            if row.get("record_type") == "receipt"
            and row.get("verification_state") == "verified"
            and any(component.get("category") == contract.REVENUE
                    for component in row.get("components", []))
        ]
        self.assertEqual(verified_revenue, [])

        stripe_coverage = [
            row for row in stripe_rows
            if row.get("record_type") == "coverage"
            and row.get("source_id") == "stripe-financial-record"
            and row.get("projection") in {"historical", "trailing"}
        ]
        self.assertEqual(
            {row["projection"]: row["reason"] for row in stripe_coverage},
            {
                "historical": "unverified_receipt",
                "trailing": "unverified_receipt",
            },
        )

    def test_mobile_readback_uses_default_business_outcomes_path(self):
        expected_products = {
            "anicca-ios", "honne-ai", "breath-reset", "sleep-ritual",
            "desk-stretch-timer", "micro-mood",
        }
        rows = [
            {
                "schema_version": 1,
                "snapshot_id": f"{product}:2026-09-30",
                "business_date": "2026-09-30",
                "observed_at": "2026-10-01T00:00:00Z",
                "product_id": product,
                "sources": {},
            }
            for product in sorted(expected_products)
        ]
        self.assertEqual(len(rows), 6)

        with tempfile.TemporaryDirectory() as tmp:
            default_path = Path(tmp) / "marketing-metrics-daily" / "state" / "business-outcomes.jsonl"
            default_path.parent.mkdir(parents=True)
            default_path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )
            with patch.object(m, "BUSINESS_OUTCOMES", default_path):
                records = m.collect_b7_records(
                    snapshot_at=SNAPSHOT, trailing_start=TRAILING_START, env={},
                )

        mobile_coverage = [
            row for row in records
            if row.get("record_type") == "coverage"
            and row.get("product_loop_id") == "mobile-apps"
        ]
        self.assertEqual(
            {(row["source_id"], row["reason"]) for row in mobile_coverage},
            {
                ("app-store-connect-financial", "missing_coverage"),
                ("revenuecat-mrr", "missing_coverage"),
            },
        )

    def test_platform_specific_crowdworks_readback_preserves_unconnected_siblings(self):
        import hashlib
        payload = {
            "schema_version": 1,
            "record_type": "marketplace_financial_readback",
            "platform": "crowdworks",
            "product_loop_id": "gig-crowdworks",
            "observed_at": SNAPSHOT,
            "coverage": {
                "historical": {"complete": False, "window_start": None, "window_end": SNAPSHOT},
                "trailing": {"complete": False, "window_start": TRAILING_START, "window_end": SNAPSHOT},
            },
            "pagination": {"complete": True, "pages_fetched": 1, "records_fetched": 1, "next_cursor": None},
            "receipt_map": {"complete": True, "records": [{
                "schema_version": 1, "record_type": "payment_receipt", "platform": "crowdworks",
                "work_external_id": "contract-1", "payment_external_id": "payment-1",
                "receipt_id": "payment-1", "gross_amount_minor": 12, "fee_amount_minor": 2,
                "cost_amount_minor": 0, "net_amount_minor": 10, "currency": "JPY",
                "status": "settled", "occurred_at": "2026-09-30T00:00:00Z", "observed_at": SNAPSHOT,
            }]},
            "aggregate": {"currency": "JPY", "sales_count": 1, "net_amount_minor": 10},
        }
        unsigned = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        digest = hashlib.sha256(unsigned).hexdigest()
        payload["content_sha256"] = digest
        payload["evidence_ref"] = f"marketplace://crowdworks/financial-readback/sha256/{digest}"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "crowdworks.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            records = m.collect_b7_records(
                snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                env={"LM_CFO_MARKETPLACE_CROWDWORKS_READBACK": str(path)},
            )
        self.assertTrue(any(
            row.get("receipt_id") == "marketplace:crowdworks:payment:payment-1"
            for row in records
        ))
        gaps = {
            (row.get("product_loop_id"), row.get("reason"))
            for row in records if row.get("record_type") == "coverage"
        }
        self.assertIn(("gig-coconala", "source_unconnected"), gaps)
        self.assertIn(("gig-lancers", "source_unconnected"), gaps)

    def test_platform_specific_marketplace_readback_preserves_unconnected_siblings(self):
        import hashlib
        payload = {
            "schema_version": 1,
            "record_type": "marketplace_financial_readback",
            "platform": "lancers",
            "product_loop_id": "gig-lancers",
            "observed_at": SNAPSHOT,
            "coverage": {
                "historical": {"complete": True, "window_start": None, "window_end": SNAPSHOT},
                "trailing": {"complete": True, "window_start": TRAILING_START, "window_end": SNAPSHOT},
            },
            "pagination": {"complete": True, "pages_fetched": 1, "records_fetched": 0, "next_cursor": None},
            "receipt_map": {"complete": True, "records": []},
            "aggregate": {"currency": "JPY", "sales_count": 0, "net_amount_minor": 0},
        }
        unsigned = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        digest = hashlib.sha256(unsigned).hexdigest()
        payload["content_sha256"] = digest
        payload["evidence_ref"] = f"marketplace://lancers/financial-readback/sha256/{digest}"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lancers.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            records = m.collect_b7_records(
                snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                env={"LM_CFO_MARKETPLACE_LANCERS_READBACK": str(path)},
            )
        gaps = {
            (row.get("product_loop_id"), row.get("reason"))
            for row in records if row.get("record_type") == "coverage"
        }
        self.assertNotIn(("gig-lancers", "source_unconnected"), gaps)
        self.assertIn(("gig-coconala", "source_unconnected"), gaps)
        self.assertIn(("gig-crowdworks", "source_unconnected"), gaps)

    def test_platform_specific_path_rejects_mismatched_envelope_on_expected_lane(self):
        import hashlib
        payload = {
            "schema_version": 1,
            "record_type": "marketplace_financial_readback",
            "platform": "coconala",
            "product_loop_id": "gig-coconala",
            "observed_at": SNAPSHOT,
            "coverage": {
                "historical": {"complete": True, "window_start": None, "window_end": SNAPSHOT},
                "trailing": {"complete": True, "window_start": TRAILING_START, "window_end": SNAPSHOT},
            },
            "pagination": {"complete": True, "pages_fetched": 1, "records_fetched": 0, "next_cursor": None},
            "receipt_map": {"complete": True, "records": []},
            "aggregate": {"currency": "JPY", "sales_count": 0, "net_amount_minor": 0},
        }
        unsigned = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        digest = hashlib.sha256(unsigned).hexdigest()
        payload["content_sha256"] = digest
        payload["evidence_ref"] = f"marketplace://coconala/financial-readback/sha256/{digest}"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wrong-lane.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            records = m.collect_b7_records(
                snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
                env={"LM_CFO_MARKETPLACE_LANCERS_READBACK": str(path)},
            )
        self.assertFalse(any(
            row.get("record_type") == "receipt" for row in records
        ))
        lancers = [
            row for row in records
            if row.get("record_type") == "coverage"
            and row.get("product_loop_id") == "gig-lancers"
            and row.get("projection") != "as_of"
        ]
        self.assertEqual({row["reason"] for row in lancers}, {"unverified_receipt"})

    def test_injected_b1_to_b6_records_project_once_with_fourteen_lanes_and_gaps(self):
        adapter_records = {
            "b1-capafy-mobile": [b7_receipt(
                "capafy:payment:1", loop_id="capafy", provider="capafy",
            )],
            "b2-stripe": [b7_receipt("stripe:balance_transaction:1")],
            "b3-affiliate": [b7_receipt(
                "partnerstack:commission:1", loop_id="affiliate", provider="partnerstack",
            )],
            "b4-marketplace": [b7_receipt(
                "marketplace:lancers:payment:1", loop_id="gig-lancers", provider="lancers",
            )],
            "b5-agent-economy-investment": [b7_receipt(
                "x402:base:1:0", loop_id="agent-economy", provider="base",
            )],
            "b6-actual-cost": [b7_receipt(
                "openai:invoice:1", loop_id="writer", provider="openai",
                components=[{"category": "model_cost", "amount": "0.4"}],
            )],
        }
        records = m.join_adapter_records(adapter_records)
        records.extend(complete_b7_coverage(omit=("job-hunter",)))

        result = m.project_records(
            records, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )

        self.assertEqual(set(result["historical"]["loops"]), set(contract.PRODUCT_LOOP_IDS))
        self.assertEqual(set(result["trailing"]["loops"]), set(contract.PRODUCT_LOOP_IDS))
        self.assertEqual(set(result["mrr"]["loops"]), set(contract.PRODUCT_LOOP_IDS))
        self.assertEqual(result["snapshot_at"], SNAPSHOT)
        self.assertEqual(result["trailing_start"], TRAILING_START)
        self.assertEqual(result["historical"]["loops"]["job-hunter"]["status"], "unknown")
        self.assertEqual(result["trailing"]["loops"]["job-hunter"]["status"], "unknown")

    def test_source_cross_duplicate_is_counted_once_and_conflict_fails_closed(self):
        row = b7_receipt("shared:receipt:1", provider="stripe")
        result = m.project_records(
            [row, copy.deepcopy(row), *complete_b7_coverage()],
            snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        self.assertEqual(result["duplicate_receipts"], [
            {"provider": "stripe", "receipt_id": "shared:receipt:1"},
        ])
        self.assertEqual(
            result["historical"]["company"]["currencies"]["USD"][contract.REVENUE],
            "1",
        )

        conflict = copy.deepcopy(row)
        conflict["components"] = [{"category": contract.REVENUE, "amount": "2"}]
        with self.assertRaisesRegex(contract.ContractError, "receipt_conflict"):
            m.project_records(
                [row, conflict, *complete_b7_coverage()],
                snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
            )

    def test_trailing_boundary_mrr_cost_complete_net_and_runway_are_separate(self):
        rows = complete_b7_coverage()
        rows.extend([
            b7_receipt(
                "before-boundary:receipt", occurred_at="2026-09-23T23:59:59Z",
                components=[{"category": contract.REVENUE, "amount": "10"}],
            ),
            b7_receipt(
                "on-boundary:receipt", occurred_at=TRAILING_START,
                components=[{"category": contract.REVENUE, "amount": "2"}],
            ),
            b7_receipt(
                "trailing:receipt", occurred_at="2026-09-25T00:00:00Z",
                components=[
                    {"category": contract.REVENUE, "amount": "5"},
                    {"category": contract.REFUND, "amount": "1"},
                    *[{
                        "category": category, "amount": "1"
                    } for category in contract.COST_CATEGORIES],
                ],
            ),
            {
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "subscription_snapshot",
                "snapshot_id": "stripe:sub:active:2026-10-01",
                "subscription_id": "stripe:sub:active",
                "product_loop_id": "self-build",
                "provider": "stripe",
                "currency": "USD",
                "normalized_monthly_amount": "30",
                "normalization_basis": "provider_monthly",
                "status": "active",
                "observed_at": SNAPSHOT,
                "verification_state": "verified",
                "evidence_refs": ["stripe://subscriptions/active"],
            },
            {
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "subscription_snapshot",
                "snapshot_id": "stripe:sub:inactive:2026-10-01",
                "subscription_id": "stripe:sub:inactive",
                "product_loop_id": "self-build",
                "provider": "stripe",
                "currency": "USD",
                "normalized_monthly_amount": "90",
                "normalization_basis": "provider_monthly",
                "status": "inactive",
                "observed_at": SNAPSHOT,
                "verification_state": "verified",
                "evidence_refs": ["stripe://subscriptions/inactive"],
            },
            {
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "liquid_balance",
                "snapshot_id": "stripe:balance:2026-10-01",
                "account_id": "operating",
                "provider": "stripe",
                "currency": "USD",
                "amount": "100",
                "observed_at": SNAPSHOT,
                "verification_state": "verified",
                "evidence_refs": ["stripe://balances/2026-10-01"],
            },
        ])

        result = m.project_records(
            rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )
        historical = result["historical"]["company"]["currencies"]["USD"]
        trailing = result["trailing"]["company"]["currencies"]["USD"]
        self.assertEqual(historical[contract.REVENUE], "17")
        self.assertEqual(trailing[contract.REVENUE], "7")
        self.assertEqual(trailing["total_cost"], "7")
        self.assertEqual(trailing["net"], "-1")
        self.assertEqual(result["mrr"]["company"], {
            "status": "verified", "currencies": {"USD": "30"},
            "reasons": [], "coverage_gaps": [],
        })
        self.assertEqual(result["runway"]["status"], "verified")
        self.assertEqual(result["runway"]["currencies"]["USD"]["liquid_balance"], "100")
        self.assertEqual(result["runway"]["currencies"]["USD"]["net_cash_burn"], "1")


class TableTest(unittest.TestCase):
    def test_every_catalog_loop_is_a_row_and_nothing_is_invented(self):
        loops = m.load_catalog()
        self.assertEqual(len(loops), 14)
        ids = [loop["id"] for loop in loops]
        sources = [
            m.SourceResult("alpaca", {("investment", k) for k in m.KINDS},
                           [m.Entry("investment", "revenue", Decimal("0.5"), "USDC", "alpaca:activity:a3")]),
            m.SourceResult("stripe", {("self-build", k) for k in m.KINDS}, error="stripe:credential_missing"),
            m.SourceResult("usage", {(i, "cost") for i in ids},
                           [m.Entry("investment", "cost", Decimal("0.1"), "USDC", "agent-usage:u")],
                           notes={"missing_cost_events": {"investment": 2}}),
        ]
        table = m.build_table(loops, sources, DAY)
        rows = {r["loop_id"]: r for r in table["rows"]}
        self.assertEqual(list(rows), ids)
        inv = rows["investment"]
        self.assertEqual(inv["net"]["amounts"], {"USDC": Decimal("0.4")})
        self.assertEqual(inv["refund"]["status"], "zero")
        self.assertEqual(inv["cost"]["incomplete"], 2)
        self.assertEqual(rows["self-build"]["revenue"]["status"], "unverified")
        self.assertEqual(rows["self-build"]["net"]["status"], "unverified")
        self.assertEqual(rows["writer"]["revenue"]["reason"], "no_source_adapter")
        self.assertEqual(rows["connector"]["revenue"]["status"], "zero")
        for row in table["rows"]:
            for kind in m.KINDS:
                cell = row[kind]
                self.assertTrue(cell["status"] != "verified" or cell["receipts"])
                self.assertTrue(cell["status"] != "unverified" or not cell["amounts"])
        text = m.render(table)
        self.assertIn("USDC 0.1*", text)
        self.assertIn("alpaca:activity:a3", text)

    def test_source_exception_becomes_unverified(self):
        def boom():
            raise RuntimeError("rpc down")
            yield
        result = m.run_source("x402-base", {("agent-economy", "revenue")}, boom)
        self.assertIn("rpc down", result.error)
        self.assertEqual(result.entries, [])


if __name__ == "__main__":
    unittest.main()
