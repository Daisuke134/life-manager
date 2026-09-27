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

    def test_unhedged_receipt_stays_open_like_entered(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            lg.append("intent", intent_id="i1", action="enter", perp="PURR")
            lg.append("receipt", intent_id="i1", result="unhedged", perp="PURR")
            self.assertEqual(lg.position(), "PURR")

    def test_needs_unwind_true_only_while_latest_receipt_is_unhedged(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            lg.append("intent", intent_id="i1", action="enter", perp="PURR")
            lg.append("receipt", intent_id="i1", result="unhedged", perp="PURR")
            self.assertTrue(lg.needs_unwind())
            lg.append("intent", intent_id="i2", action="exit", perp="PURR")
            lg.append("receipt", intent_id="i2", result="exited", perp="PURR")
            self.assertFalse(lg.needs_unwind())
            self.assertIsNone(lg.position())


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

FEE = 0.0007  # spot taker fee taken in the base asset, per real Hyperliquid spot fills


def _is_spot(name):
    return "/" in name or name.startswith("@")


def _spot_coin(name):
    return name.split("/")[0] if "/" in name else "UZEC"


def _ok_fill(sz):
    return {"status": "ok", "response": {"data": {"statuses": [{"filled": {"totalSz": str(sz), "avgPx": "0.2"}}]}}}


class FakeState:
    """Shared account state a FakeEx mutates and a FakeInfo reads back — no order response is trusted on its own."""

    def __init__(self, spot=None, perp_szi=None, withdrawable=25.0):
        self.spot = dict(spot) if spot else {"USDC": 1.0}
        self.perp_szi = dict(perp_szi) if perp_szi else {}
        self.withdrawable = withdrawable


class FakeEx:
    def __init__(self, state=None, fail_perp=False, fail_close=False, raise_on=None,
                 xfer_status="ok", lev_status="ok", perp_fill_ratio=1.0, fail_spot_buy=False):
        self.calls = []
        self.state = state if state is not None else FakeState()
        self.fail_perp = fail_perp
        self.fail_close = fail_close
        self.raise_on = raise_on or set()  # set of (name, is_buy) that raise RuntimeError, like a ClientError/network drop
        self.xfer_status = xfer_status
        self.lev_status = lev_status
        self.perp_fill_ratio = perp_fill_ratio  # <1.0 models a partial perp fill
        self.fail_spot_buy = fail_spot_buy  # spot buy rejected outright, no exception, no fill

    def usd_class_transfer(self, amount, to_perp):
        self.calls.append(("xfer", round(amount, 2), to_perp))
        return {"status": self.xfer_status}

    def update_leverage(self, lev, name, is_cross=True):
        self.calls.append(("lev", lev, name))
        return {"status": self.lev_status}

    def market_open(self, name, is_buy, sz, px=None, slippage=0.01, cloid=None):
        self.calls.append(("open", name, is_buy, sz))
        if (name, is_buy) in self.raise_on:
            raise RuntimeError("sdk_error")
        if _is_spot(name):
            coin = _spot_coin(name)
            if is_buy:
                if self.fail_spot_buy:
                    return {"status": "ok", "response": {"data": {"statuses": [{"error": "no liquidity"}]}}}
                fill = sz * (1 - FEE)
                self.state.spot[coin] = self.state.spot.get(coin, 0.0) + fill
                return _ok_fill(fill)
            bal = self.state.spot.get(coin, 0.0)
            if sz > bal + 1e-9:
                return {"status": "ok", "response": {"data": {"statuses": [{"error": "insufficient balance"}]}}}
            self.state.spot[coin] = bal - sz
            return _ok_fill(sz)
        if self.fail_perp:
            return {"status": "ok", "response": {"data": {"statuses": [{"error": "no liquidity"}]}}}
        filled_sz = sz * self.perp_fill_ratio
        delta = filled_sz if is_buy else -filled_sz
        self.state.perp_szi[name] = self.state.perp_szi.get(name, 0.0) + delta
        return _ok_fill(filled_sz)

    def market_close(self, coin, sz=None, px=None, slippage=0.01, cloid=None):
        self.calls.append(("close", coin, sz))
        cur = self.state.perp_szi.get(coin, 0.0)
        if cur == 0:
            return None  # real SDK: no open position to close
        if self.fail_close:
            return {"status": "ok", "response": {"data": {"statuses": [{"error": "no liquidity"}]}}}
        filled = abs(cur)
        self.state.perp_szi[coin] = 0.0
        return _ok_fill(filled)


class FakeInfo:
    def __init__(self, state=None):
        self.state = state if state is not None else FakeState()

    def all_mids(self):
        return {"PURR/USDC": "0.2", "PURR": "0.2", "@272": "30"}

    def spot_user_state(self, address):
        return {"balances": [{"coin": c, "total": str(v)} for c, v in self.state.spot.items()]}

    def user_state(self, address):
        return {
            "withdrawable": str(self.state.withdrawable),
            "assetPositions": [{"position": {"coin": p, "szi": str(v)}}
                               for p, v in self.state.perp_szi.items() if v != 0],
        }


class FakeInfoWithDecimals(FakeInfo):
    asset_to_sz_decimals = {1: 0, 2: 1}

    def name_to_asset(self, name):
        return 1 if "/" in name else 2


class RaisingReadbackInfo(FakeInfo):
    """Models info.user_state/spot_user_state itself raising (e.g. a dropped connection)."""

    def spot_user_state(self, address):
        raise RuntimeError("readback_error")

    def user_state(self, address):
        raise RuntimeError("readback_error")


def fakes(**ex_kwargs):
    state = FakeState()
    return FakeEx(state, **ex_kwargs), FakeInfo(state)


class ExecuteTest(unittest.TestCase):
    def test_enter_journals_then_hedges_off_balance_after_fees(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex, info = fakes()
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "entered")
            kinds = [x["kind"] for x in lg.rows()]
            self.assertEqual(kinds, ["intent", "receipt"])
            self.assertEqual(lg.position(), "PURR")
            opens = [c for c in ex.calls if c[0] == "open"]
            self.assertEqual(opens[0], ("open", "PURR/USDC", True, 120.0))
            # Hedge size is floored off the post-fee balance, never off the order size (C1).
            expected_hedge = execute._floor(120.0 * (1 - FEE), 2)
            self.assertEqual(opens[1], ("open", "PURR", False, expected_hedge))
            self.assertLess(expected_hedge, 120.0)

    def test_perp_order_fails_sells_back_floored_balance_and_stays_flat(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex, info = fakes(fail_perp=True)
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "partial")
            self.assertEqual(r["reason"], "flat")
            expected_sell = execute._floor(120.0 * (1 - FEE), 2)
            self.assertIn(("open", "PURR/USDC", False, expected_sell), ex.calls)
            self.assertIsNone(lg.position())
            self.assertEqual(r["xfer_back_status"], "ok")  # (N3) margin returned once flat

    def test_perp_exception_triggers_unwind_and_writes_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex, info = fakes(raise_on={("PURR", False)})
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "partial")
            self.assertEqual(r["error"], "RuntimeError")
            self.assertEqual([x["kind"] for x in lg.rows()], ["intent", "receipt"])
            self.assertIsNone(lg.position())

    def test_perp_exception_then_sellback_exception_leaves_unhedged(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex, info = fakes(raise_on={("PURR", False), ("PURR/USDC", False)})
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "unhedged")
            self.assertEqual(r["error"], "RuntimeError")
            self.assertEqual(lg.position(), "PURR")
            self.assertTrue(lg.needs_unwind())

    def test_partial_perp_fill_with_noop_close_leaves_unhedged_no_spot_sell(self):
        # (N1) close finds no liquidity and never clears the position; the old
        # code would have sold the *entire* spot balance anyway, creating a
        # naked short. It must now skip the spot sell and report unhedged.
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex, info = fakes(perp_fill_ratio=0.5, fail_close=True)
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "unhedged")
            self.assertLess(r["perp_szi"], 0)
            self.assertGreater(r["spot_sz"], 0)
            opens = [c for c in ex.calls if c[0] == "open"]
            # buy + the partial-fill hedge attempt only — no spot sell-back call.
            self.assertEqual(len(opens), 2)
            self.assertEqual([c[0] for c in ex.calls if c[0] == "close"], ["close"])
            self.assertEqual(lg.position(), "PURR")
            self.assertTrue(lg.needs_unwind())

    def test_spot_buy_exception_yields_unhedged_receipt(self):
        # (N2) the exchange may have accepted the buy even though the call
        # raised; "failed" would wrongly imply nothing happened.
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex, info = fakes(raise_on={("PURR/USDC", True)})
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "unhedged")
            self.assertEqual(r["error"], "RuntimeError")

    def test_final_readback_exception_yields_unhedged_receipt(self):
        # (N2) info.user_state/spot_user_state raising must not escape enter().
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            state = FakeState()
            ex, info = FakeEx(state), RaisingReadbackInfo(state)
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "unhedged")
            self.assertEqual(r["error"], "RuntimeError")

    def test_transfer_failure_stops_before_any_order(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex, info = fakes(xfer_status="err")
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "failed")
            self.assertEqual(r["reason"], "transfer_failed")
            self.assertEqual([c[0] for c in ex.calls], ["xfer"])

    def test_leverage_failure_stops_before_any_order_and_returns_margin(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex, info = fakes(lev_status="err")
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "failed")
            self.assertEqual(r["reason"], "leverage_failed")
            self.assertEqual([c[0] for c in ex.calls], ["xfer", "lev", "xfer"])  # (N3) margin sent back
            self.assertEqual(r["xfer_back_status"], "ok")

    def test_below_min_notional_makes_no_transfer_call_at_all(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex, info = fakes()
            r = execute.enter(ex, info, "0xabc", pair(0.3), 5.0, lg)
            self.assertEqual(r["result"], "failed")
            self.assertEqual(r["reason"], "below_min_notional")
            self.assertEqual(ex.calls, [])  # (N3) no transfer at all — nothing to unwind

    def test_spot_not_filled_returns_margin_to_spot(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            ex, info = fakes(fail_spot_buy=True)
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "failed")
            self.assertEqual(r["reason"], "spot_not_filled")
            self.assertIn(("xfer", 25.0, False), ex.calls)  # (N3) margin moved back to spot
            self.assertEqual(r["xfer_back_status"], "ok")

    def test_enter_uses_shared_min_sz_decimals_across_legs(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            state = FakeState()
            ex, info = FakeEx(state), FakeInfoWithDecimals(state)
            r = execute.enter(ex, info, "0xabc", pair(0.3), 24.0, lg)
            self.assertEqual(r["result"], "entered")
            opens = [c for c in ex.calls if c[0] == "open"]
            self.assertEqual(opens[0], ("open", "PURR/USDC", True, 120.0))
            expected_hedge = execute._floor(120.0 * (1 - FEE), 0)
            self.assertEqual(opens[1], ("open", "PURR", False, expected_hedge))

    def test_exit_closes_perp_then_spot_then_moves_usdc(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            hedge_sz = execute._floor(120.0 * (1 - FEE), 2)
            state = FakeState(spot={"USDC": 1.0, "PURR": 120.0 * (1 - FEE)},
                               perp_szi={"PURR": -hedge_sz}, withdrawable=25.0)
            ex, info = FakeEx(state), FakeInfo(state)
            r = execute.exit(ex, info, "0xabc", pair(0.02), lg)
            self.assertEqual(r["result"], "exited")
            names = [c[0] for c in ex.calls]
            self.assertLess(names.index("close"), names.index("open"))
            self.assertIn(("xfer", 25.0, False), ex.calls)
            self.assertEqual(r["xfer_status"], "ok")

    def test_exit_when_perp_stays_open_does_not_touch_spot_or_margin(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            hedge_sz = execute._floor(120.0 * (1 - FEE), 2)
            state = FakeState(spot={"USDC": 1.0, "PURR": 120.0 * (1 - FEE)},
                               perp_szi={"PURR": -hedge_sz}, withdrawable=25.0)
            ex, info = FakeEx(state, fail_close=True), FakeInfo(state)
            r = execute.exit(ex, info, "0xabc", pair(0.02), lg)
            self.assertEqual(r["result"], "partial")
            self.assertEqual(r["reason"], "perp_not_flat")
            self.assertEqual([c[0] for c in ex.calls], ["close"])
            self.assertEqual(r["xfer_status"], "not_attempted")

    def test_market_close_with_no_position_returns_none(self):
        self.assertIsNone(FakeEx(FakeState()).market_close("PURR"))

import run


class WakeTest(unittest.TestCase):
    def _wake(self, live, equity=50.0):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            sent, made = [], []
            post = lambda b: fake_post(b) if b["type"] not in ("clearinghouseState", "spotClearinghouseState") \
                else ({"marginSummary": {"accountValue": str(equity)}} if b["type"] == "clearinghouseState" else {"balances": []})
            def make():
                made.append(1); return fakes()
            r = run.wake(post, make, lg, "0xabc", policy.Caps(), live, "2099-01-01", sent.append)
            return r, sent, made, lg.position()

    def test_dry_wake_decides_and_reports_but_never_signs(self):
        r, sent, made, _ = self._wake(live=False)
        self.assertEqual(r["decision"]["action"], "enter")
        self.assertEqual(made, [])
        self.assertEqual(len(sent), 1)

    def test_live_wake_enters(self):
        r, _, made, position = self._wake(live=True)
        self.assertEqual(made, [1])
        self.assertEqual(position, "ZEC")

    def test_open_intent_reconciles_by_exit(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            lg.append("intent", intent_id="x", action="enter", perp="PURR", spot="PURR/USDC")
            made = []
            def make():
                made.append(1); return FakeEx(), FakeInfo()
            r = run.wake(fake_post, make, lg, "0xabc", policy.Caps(), True, "2099-01-01", lambda t: None)
            self.assertEqual(r["decision"]["action"], "reconcile_exit")
            self.assertEqual(made, [1])
            self.assertIsNotNone(r["receipt"])


    def test_reconcile_without_current_pair_uses_recorded_pair(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            lg.append("intent", intent_id="x", action="enter", perp="MISSING", spot="MISSING/USDC")
            made = []
            def make():
                made.append(1); return FakeEx(), FakeInfo()
            r = run.wake(fake_post, make, lg, "0xabc", policy.Caps(), True, "2099-01-01", lambda t: None)
            self.assertEqual(r["decision"]["action"], "reconcile_exit")
            self.assertEqual(r["decision"]["reason"], "open_intent_or_unhedged")
            self.assertEqual(made, [1])
            self.assertIsNotNone(r["receipt"])

    def test_reconcile_without_safe_pair_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            lg.append("intent", intent_id="x", action="enter", perp="MISSING")
            made = []
            def make():
                made.append(1); return FakeEx(), FakeInfo()
            r = run.wake(fake_post, make, lg, "0xabc", policy.Caps(), True, "2099-01-01", lambda t: None)
            self.assertEqual(r["decision"]["reason"], "reconciliation_pair_unavailable")
            self.assertEqual(r["receipt"]["result"], "reconciliation_pending")
            self.assertEqual(made, [])


import subprocess


class WakeReviewTest(unittest.TestCase):
    def _post_with_equity(self, equity):
        return lambda b: fake_post(b) if b["type"] not in ("clearinghouseState", "spotClearinghouseState") \
            else ({"marginSummary": {"accountValue": str(equity)}} if b["type"] == "clearinghouseState" else {"balances": []})

    def _position(self, lg):
        lg.append("receipt", intent_id="seed", result="entered", perp="PURR", spot="PURR/USDC")

    def _clients(self):
        state = FakeState(spot={"USDC": 1.0, "PURR": 10.0}, perp_szi={"PURR": -10.0})
        return FakeEx(state), FakeInfo(state), state

    def test_daily_loss_halt_flattens_live_position(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            lg.mark_equity(100.0)
            today = lg.rows()[-1]["ts"][:10]
            self._position(lg)
            ex, info, state = self._clients()
            r = run.wake(self._post_with_equity(94.0), lambda: (ex, info), lg, "0xabc", policy.Caps(), True, today, lambda t: None)
            self.assertEqual((r["decision"]["action"], r["decision"]["reason"]), ("halt", "day_loss_cap"))
            self.assertEqual(r["receipt"]["result"], "exited")
            self.assertEqual(state.perp_szi["PURR"], 0.0)
            self.assertEqual(state.spot["PURR"], 0.0)

    def test_drawdown_halt_flattens_live_position(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            lg.append("equity", equity=100.0, ts="2000-01-01T00:00:00+00:00")
            lg.mark_equity(95.0)
            today = lg.rows()[-1]["ts"][:10]
            self._position(lg)
            ex, info, state = self._clients()
            caps = policy.Caps(day_loss=0.50, drawdown=0.20)
            r = run.wake(self._post_with_equity(79.0), lambda: (ex, info), lg, "0xabc", caps, True, today, lambda t: None)
            self.assertEqual((r["decision"]["action"], r["decision"]["reason"]), ("halt", "drawdown_cap"))
            self.assertEqual(r["receipt"]["result"], "exited")
            self.assertEqual(state.perp_szi["PURR"], 0.0)
            self.assertEqual(state.spot["PURR"], 0.0)

    def test_at_spot_without_recorded_token_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            lg.append("intent", intent_id="x", action="enter", perp="ZEC", spot="@272")
            made = []
            def no_zec_post(body):
                if body["type"] == "metaAndAssetCtxs":
                    return [{"universe": [{"name": "PURR"}]}, []]
                return fake_post(body)
            def make():
                made.append(1); return fakes()
            r = run.wake(no_zec_post, make, lg, "0xabc", policy.Caps(), True, "2099-01-01", lambda t: None)
            self.assertEqual(r["receipt"]["result"], "reconciliation_pending")
            self.assertEqual(made, [])

    def test_failed_sender_does_not_mark_daily_report_sent(self):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            failed = subprocess.CompletedProcess(["send"], 1)
            with self.assertRaises(subprocess.CalledProcessError):
                run._report_once(lg, "2099-01-01", "report", lambda text: failed)
            self.assertFalse(any(r["kind"] == "report" for r in lg.rows()))


if __name__ == "__main__":
    unittest.main()
