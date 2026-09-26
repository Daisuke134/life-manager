"""Fixture tests for loop_pnl: one per source adapter plus the table/unverified contract."""

import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import loop_pnl as m  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "loop_pnl"
DAY = date(2026, 9, 26)  # Asia/Tokyo: 2026-09-25T15:00Z .. 2026-09-26T15:00Z


def fixture(name):
    return json.loads((FIX / name).read_text())


def sums(entries):
    out = {}
    for e in entries:
        key = (e.loop_id, e.kind, e.currency)
        out[key] = out.get(key, Decimal(0)) + e.amount
    return out


class AlpacaTest(unittest.TestCase):
    def test_fifo_realized_and_fees_for_the_jst_day(self):
        entries = list(m.alpaca_entries(fixture("alpaca_activities.json"), DAY))
        self.assertEqual(sums(entries), {
            ("investment", "revenue", "USDC"): Decimal("0.5"),  # 0.001*(81000-80000) + 0.0005*(81000-82000)
            ("investment", "revenue", "USD"): Decimal("10"),
            ("investment", "cost", "USD"): Decimal("0.02"),
        })
        self.assertTrue(all(e.receipt_id.startswith("alpaca:activity:") for e in entries))

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
    def test_balance_transactions_to_entries(self):
        entries = list(m.stripe_entries(fixture("stripe_balance_transactions.json")))
        self.assertEqual(sums(entries), {
            ("self-build", "revenue", "USD"): Decimal("19.99"),
            ("self-build", "revenue", "JPY"): Decimal("3000"),
            ("self-build", "refund", "USD"): Decimal("5"),
            ("self-build", "cost", "USD"): Decimal("0.88"),
            ("self-build", "cost", "JPY"): Decimal("108"),
        })

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
