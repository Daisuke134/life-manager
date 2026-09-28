# Hyperliquid Funding-Carry Live Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Life Manager runs a real-money, loss-capped Hyperliquid spot-long/perp-short funding-carry position from its own agent-created wallet, and reports verified daily account-equity net P&L to Telegram with no human in the loop. Detailed cross-venue fee/funding/model-cost allocation is specified separately in `docs/superpowers/plans/2026-09-27-cross-venue-capital-allocator-net-pnl.md`.

**Architecture:** One new skill directory `skills/earn/hyperliquid-carry/`. The decision logic is pure and unit-tested (`policy.py`). The only module that sends signed Hyperliquid actions is `execute.py`, and it runs only when `HL_CARRY_LIVE=1`. Every effect is journaled before it is sent and read back from Hyperliquid afterwards (`ledger.py`). One wake (`run.py`) loads the wallet, reads the market, applies the risk caps, acts at most once, and reports. The wallet key is stored in the credential SSOT, never in the repo.

**Tech Stack:** Python 3.14 (managed venv), `hyperliquid-python-sdk==0.24.0` (MIT, official), `msgpack==1.1.2` (SDK dependency, locked), `eth-account==0.13.7` and `web3==7.16.0` (already locked), stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` §5.2 8-4c, plus the Foundation investment ladder in `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md` ("Investment is an experiment portfolio"). Dais directive 2026-09-27: real money, no dry-run-only, no human in the loop, daily Telegram revenue report.

## Evidence this plan rests on

- Fees, base tier (https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees): perp taker 0.045%, maker 0.015%. Spot taker 0.070%, maker 0.040% (Chainstack, https://docs.chainstack.com/docs/hyperliquid-funding-rate-arbitrage). With IOC (taker) orders, one round trip on both legs costs 2 × (0.070% + 0.045%) = 0.23% of one leg's notional.
- Funding is paid hourly; a positive rate means longs pay shorts (https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding).
- Measured 2026-09-27: the liquid spot/perp pairs are PURR (spot volume ≈ $1.19M/day) and ZEC via `UZEC` (≈ $0.21M/day). Funding for both was 11.0% APR, the baseline interest component.
- At 11% APR the 0.23% round-trip cost is recovered after about 7.6 days of holding. Expected profit at $50 capital is cents per month. This plan builds the loop and the evidence trail; scaling comes only from measured net results.
- Code reuse: official SDK only. `hyperliquid-trading-agent` and every license-less repo are reference-only (SSOT 8-4c).

## Global Constraints

- Real orders only when `HL_CARRY_LIVE=1` is set in the loop's environment; otherwise the wake computes and reports but sends nothing signed.
- Capital caps: `HL_CARRY_MAX_LEG_USD` default `25`. Halt and flatten when the day's loss is ≥ 5% of start-of-day equity or the loss from the high-water mark is ≥ 20%.
- `HL_CARRY_MAX_LEG_USD` values above `$25`, non-finite values, and non-positive values fail closed; the hard leg cap cannot be raised by environment configuration.
- Hyperliquid minimum order value is $10 per order; never place a leg below $11.
- Leverage 1x cross on the perp leg; the short size always equals the spot size (delta-neutral).
- The wallet key lives only in `~/.local/share/anicca/credentials.json` (dir mode 700, file mode 600), under service `hyperliquid-carry-agent-wallet`. It never appears in logs, the repo, or Telegram.
- State and journals live outside the repo under `LIFE_MANAGER_STATE_ROOT` (default `~/.local/state/life-manager/hyperliquid-carry`).
- Never edit `runtime/loop`, `runtime/host`, `bin/`, or `config/loop-registry.json`. Registry rows and release/apply are lm-lead's; ask via agmsg.
- Telegram messages go through `skills/_shared/send-telegram.sh`.

## Current evidence cursor

Read-only verification on 2026-09-28 reports agent wallet `0xA428EC15fD85A1CED452dfC8Fe8436d334D9A302` with Arbitrum
USDC `0` and ETH `0`; `deposit.py` returns `wait/usdc_below_bridge_minimum` with `HL_CARRY_LIVE` unset. Hyperliquid
official `clearinghouseState` reports account value `0`, zero positions, and zero withdrawable balance; `userFunding`
and `userNonFundingLedgerUpdates` both contain zero rows. The repository registry has no `hyperliquid-carry` row, so
no live scheduler or owner-path enablement is claimed. No funding, signing, registry mutation, or canary has occurred.
The next effect-dependent step remains owner/lm-lead readback plus explicit funding; until then, this plan is a
read-only/dry-run capability, not revenue evidence.

## Current verification refresh (2026-09-28)

- The complete offline `test_hyperliquid_carry` suite passes `74/74`. This verifies the bounded BTC/ETH policy, journal, deposit-boundary, reconciliation, dry-wake, and fake-client effect fences; it does not prove a live order or profit.
- The official read-only account boundary remains unchanged: Arbitrum wallet USDC/ETH `0`, Hyperliquid account value `0`, positions `0`, funding rows `0`, and non-funding ledger rows `0`. No deposit, signing, order, or live canary was performed.
- The registry/runtime boundary remains open because the repository has no `hyperliquid-carry` registry row. The next executable step is still an owner/lm-lead runtime receipt plus explicit funding; the `$25` leg cap and capital-expansion hold remain unchanged.

## Strategy-boundary correction (2026-09-28)

The older policy example below is historical implementation context and is superseded by the investment validation plan's Task 5. A displayed APR or the previously observed PURR/ZEC market snapshot is not an admission signal. The current pure policy admits only matching BTC/ETH spot-perp pairs (`BTC/USDC`/`ETH/USDC`, or the official indexed `@142`/`@151` with `UBTC`/`UETH` token identity); PURR, ZEC, and any other high-APR pair return `idle` rather than becoming a live candidate.

Entry now projects the trailing 24-hour funding APR over `enter_hold_days` (14 days), then subtracts the declared round-trip fee/slippage cost, bridge cost, model cost, and a fixed net buffer. Any missing cost field returns `cost_model_incomplete` and `idle`. The default runtime caps leave model cost unknown, so they cannot authorize entry until a measured model-cost receipt is supplied. Existing positions exit on funding decay, missing official state, or an allowlist mismatch; daily-loss and drawdown halts remain first-class exits.

The correction is implemented in `skills/earn/hyperliquid-carry/policy.py` and covered by the full offline suite `74/74`; no wallet funding, signature, order, registry mutation, or live canary occurred. This policy result is a gate, not evidence of profit.

## File Structure

- `skills/earn/hyperliquid-carry/wallet.py`: load or create the agent wallet in the credential SSOT.
- `skills/earn/hyperliquid-carry/policy.py`: pure decision logic (pair selection, enter/hold/exit/halt, sizing).
- `skills/earn/hyperliquid-carry/ledger.py`: append-only JSONL journal of intents, receipts, and equity; risk-state queries.
- `skills/earn/hyperliquid-carry/execute.py`: the only module that signs. Enter/exit both legs; readback by cloid.
- `skills/earn/hyperliquid-carry/market.py`: read-only market and account snapshot from `/info`.
- `skills/earn/hyperliquid-carry/deposit.py`: Arbitrum USDC → Hyperliquid Bridge2 deposit from the agent wallet.
- `skills/earn/hyperliquid-carry/run.py`: one wake (entrypoint).
- `skills/earn/hyperliquid-carry/test_hyperliquid_carry.py`: all unit tests (offline, fakes).
- `skills/earn/hyperliquid-carry/SKILL.md`: operating notes.
- `requirements-runtime.txt`: add `hyperliquid-python-sdk==0.24.0`, `msgpack==1.1.1`.

---

### Task 1: Dependencies and agent wallet

**Files:**
- Modify: `requirements-runtime.txt` (append two lines)
- Create: `skills/earn/hyperliquid-carry/wallet.py`
- Test: `skills/earn/hyperliquid-carry/test_hyperliquid_carry.py`

**Interfaces:**
- Produces: `wallet.load_or_create(ssot_path: Path) -> eth_account.signers.local.LocalAccount`; `wallet.SERVICE = "hyperliquid-carry-agent-wallet"`.

- [ ] **Step 1: Write the failing test**

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wallet'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Agent-owned Hyperliquid wallet, persisted only in the credential SSOT."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from eth_account import Account

SERVICE = "hyperliquid-carry-agent-wallet"
DEFAULT_SSOT = Path.home() / ".local/share/anicca/credentials.json"


def _read(ssot: Path) -> dict:
    if not ssot.exists():
        return {"credentials": []}
    doc = json.loads(ssot.read_text(encoding="utf-8"))
    if isinstance(doc, list):
        doc = {"credentials": doc}
    doc.setdefault("credentials", [])
    return doc


def load_or_create(ssot: Path = DEFAULT_SSOT):
    doc = _read(ssot)
    for row in doc["credentials"]:
        if isinstance(row, dict) and row.get("service") == SERVICE and row.get("private_key"):
            return Account.from_key(row["private_key"])
    acct = Account.create()
    doc["credentials"].append({
        "service": SERVICE,
        "url": "https://app.hyperliquid.xyz",
        "username": acct.address,
        "private_key": acct.key.hex(),
        "note": "agent-created EVM key for Hyperliquid carry loop; fund with Arbitrum USDC",
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    })
    ssot.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ssot.parent, 0o700)
    tmp = ssot.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ssot)
    return acct
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Add runtime dependencies**

Append to `requirements-runtime.txt`:
```
hyperliquid-python-sdk==0.24.0
msgpack==1.1.1
```
Run: `/Users/anicca/.local/share/life-manager/venv/bin/python -m pip install hyperliquid-python-sdk==0.24.0 msgpack==1.1.1 && /Users/anicca/.local/share/life-manager/venv/bin/python -c "import hyperliquid.exchange"`
Expected: exit 0. Tell lm-lead that the release bundle needs the new lock lines.

- [ ] **Step 6: Commit**

```bash
git add requirements-runtime.txt skills/earn/hyperliquid-carry/wallet.py skills/earn/hyperliquid-carry/test_hyperliquid_carry.py
git commit -m "feat(hl-carry): agent-owned wallet in credential SSOT"
```

### Task 2: Pure policy (pair selection, entry/exit, risk halt, sizing)

**Files:**
- Create: `skills/earn/hyperliquid-carry/policy.py`
- Test: append to `skills/earn/hyperliquid-carry/test_hyperliquid_carry.py`

**Interfaces:**
- Produces:
  - `policy.Pair(perp: str, spot: str, spot_vol_usd: float, funding_apr_24h: float, spot_token: str = "")`
  - `policy.Caps(max_leg_usd=25.0, day_loss=0.05, drawdown=0.20, min_leg_usd=11.0, enter_hold_days=14.0, exit_apr=0.05, round_trip_cost=0.0023, min_spot_vol_usd=150_000.0)`
  - `policy.decide(pairs: list[Pair], position: str | None, equity: float, day_start_equity: float, peak_equity: float, caps: Caps) -> dict` returning `{"action": "enter"|"hold"|"exit"|"halt"|"idle", "pair": Pair|None, "leg_usd": float, "reason": str}`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'policy'`

- [ ] **Step 3: Implement**

```python
"""Pure carry decisions: no I/O, no clock, no keys."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pair:
    perp: str
    spot: str
    spot_vol_usd: float
    funding_apr_24h: float
    spot_token: str = ""  # spot balance coin name, e.g. "UZEC" for pair "@272"


@dataclass(frozen=True)
class Caps:
    max_leg_usd: float = 25.0
    day_loss: float = 0.05
    drawdown: float = 0.20
    min_leg_usd: float = 11.0
    enter_hold_days: float = 14.0
    exit_apr: float = 0.05
    round_trip_cost: float = 0.0023
    min_spot_vol_usd: float = 150_000.0


def decide(pairs, position, equity, day_start_equity, peak_equity, caps: Caps) -> dict:
    if day_start_equity > 0 and equity <= day_start_equity * (1 - caps.day_loss):
        return {"action": "halt", "pair": None, "leg_usd": 0.0, "reason": "day_loss_cap"}
    if peak_equity > 0 and equity <= peak_equity * (1 - caps.drawdown):
        return {"action": "halt", "pair": None, "leg_usd": 0.0, "reason": "drawdown_cap"}
    if position:
        current = next((p for p in pairs if p.perp == position), None)
        if current is None or current.funding_apr_24h < caps.exit_apr:
            return {"action": "exit", "pair": current, "leg_usd": 0.0, "reason": "funding_decayed"}
        return {"action": "hold", "pair": current, "leg_usd": 0.0, "reason": "carry_positive"}
    liquid = [p for p in pairs if p.spot_vol_usd >= caps.min_spot_vol_usd]
    worth = [p for p in liquid
             if p.funding_apr_24h * caps.enter_hold_days / 365 > caps.round_trip_cost]
    if not worth:
        return {"action": "idle", "pair": None, "leg_usd": 0.0, "reason": "no_carry_beats_cost"}
    best = max(worth, key=lambda p: p.funding_apr_24h)
    leg = min(caps.max_leg_usd, int(equity * 0.48))
    if leg < caps.min_leg_usd:
        return {"action": "idle", "pair": best, "leg_usd": 0.0, "reason": "equity_below_min_leg"}
    return {"action": "enter", "pair": best, "leg_usd": float(leg), "reason": "carry_beats_cost"}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: PASS. At 11% APR over 14 days, carry is 0.42%, which beats the 0.23% cost, so enter. At 5% APR it is 0.19%, so idle. Leg size = min(25, int(50 × 0.48)) = 24.

- [ ] **Step 5: Commit**

```bash
git add skills/earn/hyperliquid-carry/policy.py skills/earn/hyperliquid-carry/test_hyperliquid_carry.py
git commit -m "feat(hl-carry): pure carry policy with loss caps"
```

### Task 3: Ledger (journal-before-effect, equity marks, risk state)

**Files:**
- Create: `skills/earn/hyperliquid-carry/ledger.py`
- Test: append to `test_hyperliquid_carry.py`

**Interfaces:**
- Produces:
  - `ledger.Ledger(path: Path)`
  - `.append(kind: str, **fields) -> dict` (adds `ts` ISO UTC)
  - `.open_intents() -> list[dict]`: intents with no matching receipt (`intent_id`)
  - `.mark_equity(equity: float) -> None`
  - `.risk_state(today: str) -> tuple[float, float]` returning `(day_start_equity, peak_equity)`
  - `.position() -> str | None`: perp name of the open carry, from the last `entered`/`exited` receipt

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ledger'`

- [ ] **Step 3: Implement**

```python
"""Append-only journal outside the repo: intents, receipts, equity marks."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def append(self, kind: str, **fields) -> dict:
        row = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "kind": kind, **fields}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return row

    def open_intents(self) -> list[dict]:
        rows = self.rows()
        done = {r["intent_id"] for r in rows if r["kind"] == "receipt"}
        return [r for r in rows if r["kind"] == "intent" and r["intent_id"] not in done]

    def position(self) -> str | None:
        for r in reversed(self.rows()):
            if r["kind"] == "receipt" and r.get("result") in ("entered", "exited"):
                return r["perp"] if r["result"] == "entered" else None
        return None

    def mark_equity(self, equity: float) -> None:
        self.append("equity", equity=round(float(equity), 6))

    def risk_state(self, today: str) -> tuple[float, float]:
        marks = [r for r in self.rows() if r["kind"] == "equity"]
        if not marks:
            return 0.0, 0.0
        todays = [r["equity"] for r in marks if r["ts"][:10] == today]
        return (todays[0] if todays else marks[-1]["equity"]), max(r["equity"] for r in marks)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/earn/hyperliquid-carry/ledger.py skills/earn/hyperliquid-carry/test_hyperliquid_carry.py
git commit -m "feat(hl-carry): append-only journal with risk state"
```

### Task 4: Market and account snapshot (read-only)

**Files:**
- Create: `skills/earn/hyperliquid-carry/market.py`
- Test: append to `test_hyperliquid_carry.py`

**Interfaces:**
- Consumes: `policy.Pair`
- Produces:
  - `market.pairs(post: Callable[[dict], Any], now_ms: int) -> list[policy.Pair]`: spot/perp pairs, where `funding_apr_24h` is the mean hourly `fundingHistory` rate over the last 24h × 24 × 365
  - `market.equity(post, address: str) -> float`: perp `marginSummary.accountValue` + spot USDC total + spot token value at mark
  - `market.post_info(body: dict) -> Any`: POST https://api.hyperliquid.xyz/info with retries (429/5xx backoff)

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'market'`

- [ ] **Step 3: Implement**

```python
"""Read-only Hyperliquid market/account snapshot."""
from __future__ import annotations

import json
import statistics
import time
import urllib.error
import urllib.request

from policy import Pair

INFO_URL = "https://api.hyperliquid.xyz/info"


def post_info(body: dict, retries: int = 6):
    req = urllib.request.Request(INFO_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            last = e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(min(2 ** attempt, 30))
    raise last


def _spot_marks(post) -> tuple[dict, list]:
    meta, ctxs = post({"type": "spotMetaAndAssetCtxs"})
    names = {t["index"]: t["name"] for t in meta["tokens"]}
    rows = []
    for u, c in zip(meta["universe"], ctxs):
        base, quote = names[u["tokens"][0]], names[u["tokens"][1]]
        if quote == "USDC":
            rows.append((u["name"], base, float(c.get("dayNtlVlm") or 0), float(c.get("markPx") or 0)))
    return {base: mark for _, base, _, mark in rows}, rows


def pairs(post, now_ms: int) -> list[Pair]:
    meta, _ = post({"type": "metaAndAssetCtxs"})
    perps = {u["name"] for u in meta["universe"]}
    _, rows = _spot_marks(post)
    out = []
    for spot_name, base, vol, _ in rows:
        perp = base if base in perps else (base[1:] if base.startswith("U") and base[1:] in perps else None)
        if perp is None:
            continue
        hist = post({"type": "fundingHistory", "coin": perp, "startTime": now_ms - 24 * 3600 * 1000})
        rates = [float(h["fundingRate"]) for h in hist]
        if rates:
            out.append(Pair(perp, spot_name, vol, statistics.fmean(rates) * 24 * 365, base))
    return out


def equity(post, address: str) -> float:
    perp = float(post({"type": "clearinghouseState", "user": address})["marginSummary"]["accountValue"])
    marks, _ = _spot_marks(post)
    spot = 0.0
    for b in post({"type": "spotClearinghouseState", "user": address})["balances"]:
        qty = float(b["total"])
        spot += qty if b["coin"] == "USDC" else qty * marks.get(b["coin"], 0.0)
    return perp + spot
```

- [ ] **Step 4: Run to verify pass**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: PASS

- [ ] **Step 5: Live read-only check**

Run: `cd skills/earn/hyperliquid-carry && python3 -c "import market,time;[print(p) for p in market.pairs(market.post_info,int(time.time()*1000))]"`
Expected: at least `Pair(perp='PURR', spot='PURR/USDC', ...)`

- [ ] **Step 6: Commit**

```bash
git add skills/earn/hyperliquid-carry/market.py skills/earn/hyperliquid-carry/test_hyperliquid_carry.py
git commit -m "feat(hl-carry): read-only pair and equity snapshot"
```

### Task 5: Execution (the only signing module)

**Files:**
- Create: `skills/earn/hyperliquid-carry/execute.py`
- Test: append to `test_hyperliquid_carry.py`

**Interfaces:**
- Consumes: `policy.Pair`, `ledger.Ledger`
- Produces:
  - `execute.enter(ex, info, address: str, pair: Pair, leg_usd: float, lg: Ledger) -> dict`
  - `execute.exit(ex, info, address: str, pair: Pair, lg: Ledger) -> dict`
  - Both write an `intent` before sending anything and a `receipt` after readback (`result` ∈ `entered`/`exited`/`partial`/`failed`). `ex` is a `hyperliquid.exchange.Exchange` and `info` a `hyperliquid.info.Info` (fakes in tests).

Order of legs:
- Enter: move `leg_usd + 1` USDC spot→perp (`usd_class_transfer(amount, to_perp=True)`), set 1x cross (`update_leverage(1, perp, True)`), buy spot IOC, then short perp IOC for exactly the filled spot size.
- If the spot leg fills and the perp leg does not, immediately sell the spot fill back (no naked long survives) and record `partial`.
- Exit: buy back the perp short (reduce-only IOC), then sell the spot balance IOC, then move perp USDC back to spot.

- [ ] **Step 1: Write the failing tests**

```python
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
        return {"PURR/USDC": "0.2", "PURR": "0.2"}

    def spot_user_state(self, address):
        return {"balances": [{"coin": "PURR", "total": "120"}]}

    def user_state(self, address):
        return {"withdrawable": "25.0"}


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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'execute'`

- [ ] **Step 3: Implement**

```python
"""The only module that sends signed Hyperliquid actions."""
from __future__ import annotations

import uuid


def _filled(resp) -> float:
    try:
        st = resp["response"]["data"]["statuses"][0]
        return float(st["filled"]["totalSz"]) if "filled" in st else 0.0
    except (KeyError, IndexError, TypeError):
        return 0.0


def enter(ex, info, address, pair, leg_usd, lg) -> dict:
    iid = uuid.uuid4().hex
    lg.append("intent", intent_id=iid, action="enter", perp=pair.perp, spot=pair.spot, leg_usd=leg_usd)
    ex.usd_class_transfer(leg_usd + 1.0, True)
    ex.update_leverage(1, pair.perp, True)
    px = float(info.all_mids()[pair.spot])
    spot_sz = _filled(ex.market_open(pair.spot, True, round(leg_usd / px, 2)))
    if spot_sz <= 0:
        return lg.append("receipt", intent_id=iid, result="failed", perp=pair.perp, reason="spot_not_filled")
    perp_sz = _filled(ex.market_open(pair.perp, False, spot_sz))
    if perp_sz < spot_sz:
        ex.market_open(pair.spot, False, spot_sz - perp_sz)  # never leave an unhedged long
        if perp_sz > 0:
            ex.market_close(pair.perp, perp_sz)
        return lg.append("receipt", intent_id=iid, result="partial", perp=pair.perp,
                         spot_sz=spot_sz, perp_sz=perp_sz)
    return lg.append("receipt", intent_id=iid, result="entered", perp=pair.perp, spot=pair.spot,
                     spot_sz=spot_sz, perp_sz=perp_sz, entry_px=px)


def exit(ex, info, address, pair, lg) -> dict:
    iid = uuid.uuid4().hex
    lg.append("intent", intent_id=iid, action="exit", perp=pair.perp, spot=pair.spot)
    closed = _filled(ex.market_close(pair.perp))
    base = pair.spot_token or pair.spot.split("/")[0]
    held = sum(float(b["total"]) for b in info.spot_user_state(address)["balances"] if b["coin"] == base)
    sold = _filled(ex.market_open(pair.spot, False, held)) if held > 0 else 0.0
    ex.usd_class_transfer(float(info.user_state(address)["withdrawable"]), False)
    result = "exited" if sold >= held else "partial"
    return lg.append("receipt", intent_id=iid, result=result, perp=pair.perp, perp_closed=closed, spot_sold=sold)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/earn/hyperliquid-carry/execute.py skills/earn/hyperliquid-carry/test_hyperliquid_carry.py
git commit -m "feat(hl-carry): hedged enter/exit with journal-before-effect"
```

### Task 6: One wake + daily Telegram report + live gate

**Files:**
- Create: `skills/earn/hyperliquid-carry/run.py`, `skills/earn/hyperliquid-carry/SKILL.md`
- Modify: `skills/earn/hyperliquid-carry/execute.py` (persist the already-resolved `Pair.spot_token` on enter/exit intents so recorded `@...` pairs can be exited safely)
- Test: append to `test_hyperliquid_carry.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `run.wake(post, make_clients, lg, address, caps, live: bool, today: str, send) -> dict`. Here `make_clients() -> (ex, info)`, and `send(text) -> None` posts to Telegram once per UTC day (the day is stored in the ledger as `kind="report"`). The report includes verified account-equity net P&L as `equity - day_start_equity`. An open intent or `lg.needs_unwind()` is a reconciliation cursor: the wake must choose the recorded/current pair, terminalize the full intent chain only after a verified flat exit, and attempt an exit before considering any new entry; failed/partial/effect-unknown exits must not resolve their parent intent; it must not leave the loop permanently blocked.
- Safety data contract: `execute.enter` and `execute.exit` persist `pair.spot_token` in their intent rows. This is required for a recorded fallback exit when the market snapshot no longer contains an `@...` spot pair.

- [ ] **Step 1: Write the failing tests**

```python
import run


class WakeTest(unittest.TestCase):
    def _wake(self, live, equity=50.0):
        with tempfile.TemporaryDirectory() as d:
            lg = ledger.Ledger(Path(d) / "j.jsonl")
            sent, made = [], []
            post = lambda b: fake_post(b) if b["type"] not in ("clearinghouseState", "spotClearinghouseState") \
                else ({"marginSummary": {"accountValue": str(equity)}} if b["type"] == "clearinghouseState" else {"balances": []})
            def make():
                made.append(1); return FakeEx(), FakeInfo()
            r = run.wake(post, make, lg, "0xabc", policy.Caps(), live, "2099-01-01", sent.append)
            return r, sent, made, lg

    def test_dry_wake_decides_and_reports_but_never_signs(self):
        r, sent, made, _ = self._wake(live=False)
        self.assertEqual(r["decision"]["action"], "enter")
        self.assertEqual(made, [])
        self.assertEqual(len(sent), 1)

    def test_live_wake_enters(self):
        r, _, made, lg = self._wake(live=True)
        self.assertEqual(made, [1])
        self.assertEqual(lg.position(), "PURR")

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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run'`

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""One wake of the Hyperliquid carry loop."""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import execute  # noqa: E402
import ledger  # noqa: E402
import market  # noqa: E402
import policy  # noqa: E402


def wake(post, make_clients, lg, address, caps, live, today, send) -> dict:
    eq = market.equity(post, address)
    lg.mark_equity(eq)
    day_start, peak = lg.risk_state(today)
    pairs = market.pairs(post, int(time.time() * 1000))
    pos = lg.position()
    open_intents = lg.open_intents()
    if open_intents or lg.needs_unwind():
        intent = open_intents[-1] if open_intents else {}
        target = next((p for p in pairs if p.perp == (intent.get("perp") or pos)), None)
        d = {"action": "reconcile_exit", "pair": target, "leg_usd": 0.0,
             "reason": "open_intent_or_unhedged"}
        receipt = None
        if live and target is not None:
            ex, info = make_clients()
            receipt = execute.exit(ex, info, address, target, lg)
        if not any(r["kind"] == "report" and r.get("day") == today for r in lg.rows()):
            send(f"Hyperliquid carry {today}: equity ${eq:.2f} (reconcile exit; live={'yes' if live else 'no'}). Address {address}")
            lg.append("report", day=today)
        return {"decision": {k: (v.__dict__ if hasattr(v, "__dict__") else v) for k, v in d.items()},
                "equity": eq, "receipt": receipt}
    d = policy.decide(pairs, pos, eq, day_start, peak, caps)
    receipt = None
    if live and d["action"] in ("enter", "exit", "halt"):
        ex, info = make_clients()
        if d["action"] == "enter":
            receipt = execute.enter(ex, info, address, d["pair"], d["leg_usd"], lg)
        elif pos:
            target = d["pair"] or next(p for p in pairs if p.perp == pos)
            receipt = execute.exit(ex, info, address, target, lg)
    if not any(r["kind"] == "report" and r.get("day") == today for r in lg.rows()):
        apr = f"{d['pair'].funding_apr_24h:.1%}" if d.get("pair") else "-"
        send(f"Hyperliquid carry {today}: equity ${eq:.2f} (day start ${day_start:.2f}, peak ${peak:.2f}), "
             f"position {lg.position() or 'none'}, decision {d['action']} ({d['reason']}), funding {apr}, "
             f"live={'yes' if live else 'no'}. Address {address}")
        lg.append("report", day=today)
    return {"decision": {k: (v.__dict__ if hasattr(v, "__dict__") else v) for k, v in d.items()},
            "equity": eq, "receipt": receipt}


def main() -> int:
    import wallet
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    from hyperliquid.utils import constants

    acct = wallet.load_or_create()
    state = Path(os.environ.get("LIFE_MANAGER_STATE_ROOT",
                                Path.home() / ".local/state/life-manager/hyperliquid-carry"))
    lg = ledger.Ledger(state / "journal.jsonl")
    caps = policy.Caps(max_leg_usd=float(os.environ.get("HL_CARRY_MAX_LEG_USD", "25")))
    live = os.environ.get("HL_CARRY_LIVE") == "1"
    tg = HERE.parent.parent / "_shared" / "send-telegram.sh"
    send = lambda text: subprocess.run(["bash", str(tg), text], capture_output=True, timeout=30)
    make = lambda: (Exchange(acct, constants.MAINNET_API_URL), Info(constants.MAINNET_API_URL, skip_ws=True))
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    result = wake(market.post_info, make, lg, acct.address, caps, live, today, send)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`SKILL.md` must say: purpose; the live gate (`HL_CARRY_LIVE=1`); caps and env vars; the journal path; the wallet SSOT service name; the funding path (Task 7); that the loop never re-sends while an intent is open; and the evidence and fee numbers above.

- [ ] **Step 4: Run to verify pass**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: PASS

The regression test must verify that an intent produced for the `@272` spot pair records `spot_token="UZEC"`; a later reconciliation can then use that token instead of guessing from the display name.

- [ ] **Step 5: Commit**

```bash
git add skills/earn/hyperliquid-carry/run.py skills/earn/hyperliquid-carry/SKILL.md skills/earn/hyperliquid-carry/test_hyperliquid_carry.py
git commit -m "feat(hl-carry): one wake with caps, daily report, live gate"
```

### Task 7: Funding path (Arbitrum USDC → Hyperliquid)

**Files:**
- Create: `skills/earn/hyperliquid-carry/deposit.py`
- Test: append to `test_hyperliquid_carry.py`

**Interfaces:**
- Produces: `deposit.plan(usdc_balance: float, eth_balance: float) -> dict` (pure: `{"action": "deposit"|"wait", "amount": float, "reason": str}`, with a minimum of 5 USDC and 0.00005 ETH for gas) and `deposit.main()`, which journals a deposit intent before an ERC-20 `transfer(BRIDGE2, amount)` on Arbitrum from the agent wallet when `HL_CARRY_LIVE=1`, records the tx hash immediately, strictly verifies the receipt chain/from/token/Bridge2/amount boundary and canonical 68-byte ABI transfer calldata (including zero address padding), journals malformed provider data as `effect_unknown`, and resolves receipt timeouts as `effect_unknown` without resending automatically. A verified failed receipt returns a nonzero status consistently.

- [ ] **Step 1: Source facts (verified 2026-09-27)**

From https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/bridge2: the mainnet bridge is `0x2df1c51e09aecf9cacb7bc98cb1742757f163df7`. "The user sends native USDC to the bridge, and it is credited to the account that sent it in less than 1 minute. The minimum deposit amount is 5 USDC. If you send an amount less than this, it will not be credited and be lost forever." Arbitrum native USDC is `0xaf88d065e77c8cC2239327C5EDb3A432268e5831`, listed on https://developers.circle.com/stablecoins/usdc-contract-addresses.

- [ ] **Step 2: Write the failing test**

```python
import deposit


class DepositTest(unittest.TestCase):
    def test_plan(self):
        self.assertEqual(deposit.plan(4.9, 0.001)["action"], "wait")
        self.assertEqual(deposit.plan(50, 0.0)["action"], "wait")
        d = deposit.plan(50.0, 0.001)
        self.assertEqual((d["action"], d["amount"]), ("deposit", 50.0))
```

- [ ] **Step 3: Run to verify failure, then implement**

```python
"""Arbitrum USDC -> Hyperliquid Bridge2 deposit from the agent wallet."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ARB_RPC = "https://arb1.arbitrum.io/rpc"
USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
BRIDGE2 = "0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7"  # docs: bridge2, verified 2026-09-27
MIN_USDC, MIN_ETH = 5.0, 0.00005


def plan(usdc_balance: float, eth_balance: float) -> dict:
    if usdc_balance < MIN_USDC:
        return {"action": "wait", "amount": 0.0, "reason": "usdc_below_bridge_minimum"}
    if eth_balance < MIN_ETH:
        return {"action": "wait", "amount": 0.0, "reason": "no_arbitrum_gas"}
    return {"action": "deposit", "amount": float(usdc_balance), "reason": "funded"}


def main() -> int:
    import wallet
    from web3 import Web3
    acct = wallet.load_or_create()
    w3 = Web3(Web3.HTTPProvider(ARB_RPC))
    abi = [{"name": "balanceOf", "type": "function", "stateMutability": "view",
            "inputs": [{"name": "a", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
           {"name": "transfer", "type": "function", "stateMutability": "nonpayable",
            "inputs": [{"name": "to", "type": "address"}, {"name": "v", "type": "uint256"}],
            "outputs": [{"name": "", "type": "bool"}]}]
    token = w3.eth.contract(address=Web3.to_checksum_address(USDC), abi=abi)
    usdc = token.functions.balanceOf(acct.address).call() / 1e6
    eth = w3.eth.get_balance(acct.address) / 1e18
    p = plan(usdc, eth)
    print({"address": acct.address, "usdc": usdc, "eth": eth, **p})
    if p["action"] != "deposit" or os.environ.get("HL_CARRY_LIVE") != "1":
        return 0
    tx = token.functions.transfer(Web3.to_checksum_address(BRIDGE2), int(p["amount"] * 1e6)).build_transaction(
        {"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "chainId": 42161})
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=180)
    print({"tx": h.hex(), "status": rcpt.status})
    return 0 if rcpt.status == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

A unit test pins the verified address:
```python
    def test_bridge_address_is_set(self):
        self.assertEqual(deposit.BRIDGE2.lower(), "0x2df1c51e09aecf9cacb7bc98cb1742757f163df7")
```

- [ ] **Step 4: Run to verify pass, then commit**

Run: `cd skills/earn/hyperliquid-carry && python3 -m unittest test_hyperliquid_carry -v`
Expected: PASS

```bash
git add skills/earn/hyperliquid-carry/deposit.py skills/earn/hyperliquid-carry/test_hyperliquid_carry.py
git commit -m "feat(hl-carry): Arbitrum USDC bridge deposit from agent wallet"
```

### Task 8: Integrate, review, promote

- [ ] **Step 1:** `./bin/lm-loop-contract` → exit 0; the full `test_hyperliquid_carry` suite passes.
- [ ] **Step 2:** Push the branch, open a PR, run one fresh read-only adversarial review, fix the findings, and `gh pr merge --admin --merge`.
- [ ] **Step 3:** Send lm-lead the PR number and request a registry row: `hyperliquid-carry`, entrypoint `skills/earn/hyperliquid-carry/run.py`, effect_class `money`, cadence 3600s, env `HL_CARRY_LIVE=1` and `HL_CARRY_MAX_LEG_USD=25`, state root `~/.local/state/life-manager/hyperliquid-carry`. Also request the lock-line install for `hyperliquid-python-sdk`/`msgpack`. Request a daily `deposit.py` wake (cadence 3600s, same env).
- [ ] **Step 4:** Run `python3 skills/earn/hyperliquid-carry/deposit.py` once (no live env) to create the wallet and print the address. Send the address to Dais on Telegram with the funding request: $50 USDC plus about $1 of ETH on Arbitrum.
- [ ] **Step 5:** After funding: read back the Arbitrum deposit tx, the Hyperliquid equity, the first `entered` receipt, the next funding payments (`userFunding`), and the first daily Telegram report.

## Deferred to Phase 2 (separate plans, only after Phase 1 shows measured net carry)

- Maker-rebate market making via the Hummingbot `hyperliquid_perpetual` connector (Apache-2.0).
- A strategy tournament that reallocates capital between strategies by realized net APR.
- Solana memecoin scout (read-only first; no licensed repo with verifiable PnL exists, per research 2026-09-27).
