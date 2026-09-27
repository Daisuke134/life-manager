import json, os, stat, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wallet


class WalletTest(unittest.TestCase):
    def test_creates_once_then_reuses_with_private_modes(self):
        with tempfile.TemporaryDirectory() as d:
            ssot = Path(d) / "anicca" / "credentials.json"
            a = wallet.load_or_create(ssot)
            b = wallet.load_or_create(ssot)
            self.assertEqual(a.address, b.address)
            self.assertEqual(stat.S_IMODE(ssot.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(ssot.parent.stat().st_mode), 0o700)
            rows = json.loads(ssot.read_text())["credentials"]
            self.assertEqual([r["service"] for r in rows], [wallet.SERVICE])

    def test_preserves_existing_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            ssot = Path(d) / "anicca" / "credentials.json"
            ssot.parent.mkdir(mode=0o700)
            ssot.write_text(json.dumps({"credentials": [{"service": "other", "password": "x"}]}))
            os.chmod(ssot, 0o600)
            wallet.load_or_create(ssot)
            services = [r["service"] for r in json.loads(ssot.read_text())["credentials"]]
            self.assertEqual(services, ["other", wallet.SERVICE])


import policy


def pair(apr, vol=1_000_000, name="PURR"):
    return policy.Pair(perp=name, spot=f"{name}/USDC", spot_vol_usd=vol, funding_apr_24h=apr)


class PolicyTest(unittest.TestCase):
    caps = policy.Caps()

    def test_enters_best_pair_when_expected_carry_beats_cost(self):
        d = policy.decide([pair(0.11), pair(0.30, name="ZEC")], None, 50, 50, 50, self.caps)
        self.assertEqual((d["action"], d["pair"].perp), ("enter", "ZEC"))
        self.assertEqual(d["leg_usd"], 24.0)

    def test_idle_when_carry_does_not_beat_round_trip_cost(self):
        d = policy.decide([pair(0.05)], None, 50, 50, 50, self.caps)
        self.assertEqual(d["action"], "idle")

    def test_skips_illiquid_spot(self):
        d = policy.decide([pair(0.50, vol=10_000)], None, 50, 50, 50, self.caps)
        self.assertEqual(d["action"], "idle")

    def test_idle_when_equity_too_small_for_min_order(self):
        d = policy.decide([pair(0.30)], None, 20, 20, 20, self.caps)
        self.assertEqual(d["action"], "idle")
        self.assertIn("min_leg", d["reason"])

    def test_exits_when_funding_decays(self):
        d = policy.decide([pair(0.02)], "PURR", 50, 50, 50, self.caps)
        self.assertEqual(d["action"], "exit")

    def test_holds_while_funding_stays_high(self):
        d = policy.decide([pair(0.11)], "PURR", 50, 50, 50, self.caps)
        self.assertEqual(d["action"], "hold")

    def test_halts_on_daily_loss_and_drawdown(self):
        self.assertEqual(policy.decide([pair(0.3)], "PURR", 47.4, 50, 50, self.caps)["action"], "halt")
        self.assertEqual(policy.decide([pair(0.3)], None, 39.9, 40, 50, self.caps)["action"], "halt")


import ledger


class LedgerTest(unittest.TestCase):
    def test_intent_without_receipt_is_open(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            lg.append("intent", intent_id="i1", action="enter", perp="PURR")
            self.assertEqual([r["intent_id"] for r in lg.open_intents()], ["i1"])
            lg.append("receipt", intent_id="i1", result="entered", perp="PURR")
            self.assertEqual(lg.open_intents(), [])
            self.assertEqual(lg.position(), "PURR")
            lg.append("intent", intent_id="i2", action="exit", perp="PURR")
            lg.append("receipt", intent_id="i2", result="exited", perp="PURR")
            self.assertIsNone(lg.position())

    def test_risk_state_uses_first_mark_of_day_and_peak(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            for e in (50.0, 52.0, 51.0):
                lg.mark_equity(e)
            today = lg.rows()[-1]["ts"][:10]
            self.assertEqual(lg.risk_state(today), (50.0, 52.0))


import market

SPOT_META = [{"tokens": [{"index": 0, "name": "USDC"}, {"index": 1, "name": "PURR"}, {"index": 2, "name": "UZEC"}],
              "universe": [{"name": "PURR/USDC", "tokens": [1, 0]}, {"name": "@272", "tokens": [2, 0]}]},
             [{"dayNtlVlm": "1000000", "markPx": "0.2"}, {"dayNtlVlm": "200000", "markPx": "30"}]]
PERP_META = [{"universe": [{"name": "PURR"}, {"name": "ZEC"}]}, [{"funding": "0.0000125"}, {"funding": "0.00003"}]]


def fake_post(body):
    t = body["type"]
    if t == "spotMetaAndAssetCtxs":
        return SPOT_META
    if t == "metaAndAssetCtxs":
        return PERP_META
    if t == "fundingHistory":
        rate = "0.0000125" if body["coin"] == "PURR" else "0.00003"
        return [{"time": 1, "fundingRate": rate}] * 24
    if t == "clearinghouseState":
        return {"marginSummary": {"accountValue": "24.5"}}
    if t == "spotClearinghouseState":
        return {"balances": [{"coin": "USDC", "total": "1.0"}, {"coin": "PURR", "total": "120"}]}
    raise AssertionError(t)


class MarketTest(unittest.TestCase):
    def test_pairs_map_u_prefixed_spot_tokens_to_perps(self):
        ps = {p.perp: p for p in market.pairs(fake_post, now_ms=10**13)}
        self.assertEqual(ps["PURR"].spot, "PURR/USDC")
        self.assertEqual(ps["ZEC"].spot, "@272")
        self.assertEqual(ps["ZEC"].spot_token, "UZEC")
        self.assertAlmostEqual(ps["PURR"].funding_apr_24h, 0.0000125 * 24 * 365)

    def test_equity_sums_perp_spot_usdc_and_marked_tokens(self):
        self.assertAlmostEqual(market.equity(fake_post, "0xabc"), 24.5 + 1.0 + 120 * 0.2)


import execute


class FakeEx:
    def __init__(self, perp_fills=True):
        self.calls, self.perp_fills = [], perp_fills

    def usd_class_transfer(self, amount, to_perp):
        self.calls.append(("xfer", round(amount, 2), to_perp)); return {"status": "ok"}

    def update_leverage(self, lev, name, is_cross=True):
        self.calls.append(("lev", lev, name)); return {"status": "ok"}

    def market_open(self, name, is_buy, sz, px=None, slippage=0.01, cloid=None):
        self.calls.append(("open", name, is_buy, sz))
        filled = self.perp_fills or "/" in name or name.startswith("@")
        st = {"filled": {"totalSz": str(sz), "avgPx": "0.2"}} if filled else {"error": "no liquidity"}
        return {"status": "ok", "response": {"data": {"statuses": [st]}}}

    def market_close(self, coin, sz=None, px=None, slippage=0.01, cloid=None):
        self.calls.append(("close", coin, sz))
        return {"status": "ok", "response": {"data": {"statuses": [{"filled": {"totalSz": str(sz or 0), "avgPx": "0.2"}}]}}}


class FakeInfo:
    def all_mids(self):
        return {"PURR/USDC": "0.2", "PURR": "0.2", "@272": "30"}

    def spot_user_state(self, address):
        return {"balances": [{"coin": "PURR", "total": "120"}]}

    def user_state(self, address):
        return {"withdrawable": "25.0"}


class FakeInfoWithDecimals(FakeInfo):
    asset_to_sz_decimals = {1: 0, 2: 1}

    def name_to_asset(self, name):
        return 1 if "/" in name else 2


class ExecuteTest(unittest.TestCase):
    def test_enter_journals_then_hedges_same_size(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            r = execute.enter(FakeEx(), FakeInfo(), "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "entered")
            kinds = [x["kind"] for x in lg.rows()]
            self.assertEqual(kinds, ["intent", "receipt"])
            self.assertEqual(lg.position(), "PURR")

    def test_unhedged_spot_is_sold_back(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex = FakeEx(perp_fills=False)
            r = execute.enter(ex, FakeInfo(), "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "partial")
            self.assertIn(("open", "PURR/USDC", False, 120.0), ex.calls)
            self.assertIsNone(lg.position())

    def test_exit_closes_perp_then_spot(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex = FakeEx()
            r = execute.exit(ex, FakeInfo(), "0xabc", pair(0.02), lg)
            self.assertEqual(r["result"], "exited")
            names = [c[0] for c in ex.calls]
            self.assertLess(names.index("close"), names.index("open"))

    def test_enter_uses_shared_min_sz_decimals_across_legs(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex = FakeEx()
            r = execute.enter(ex, FakeInfoWithDecimals(), "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "entered")
            opens = [c for c in ex.calls if c[0] == "open"]
            self.assertEqual(opens[0], ("open", "PURR/USDC", True, 120.0))
            self.assertEqual(opens[1], ("open", "PURR", False, 120.0))


if __name__ == "__main__":
    unittest.main()
