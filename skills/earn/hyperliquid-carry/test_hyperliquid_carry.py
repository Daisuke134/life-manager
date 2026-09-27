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


if __name__ == "__main__":
    unittest.main()
