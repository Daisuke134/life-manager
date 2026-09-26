#!/usr/bin/env python3
"""Per-Product-Loop daily P&L from official receipts only.

Every figure is either a sum of entries that each carry an official receipt id, an explicit 0
from a source that was actually read for that day, or ``unverified:<reason>``. Currencies are
never converted: net is reported per currency.

Usage: loop_pnl.py [--date YYYY-MM-DD] [--json]   (date is the Asia/Tokyo reporting day)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "apps/life-manager/config/product-loop-catalog.json"
CREDENTIALS = Path("~/.local/share/anicca/credentials.json").expanduser()
STATE = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", "~/.local/state/life-manager")).expanduser()
JST = timezone(timedelta(hours=9))
KINDS = ("revenue", "refund", "cost")
NOT_APPLICABLE_ROLES = {"non_economic", "aggregator"}
DISPLAY = Decimal("0.000001")  # text rounding only; --json keeps exact sums


@dataclass(frozen=True)
class Entry:
    loop_id: str
    kind: str  # revenue | refund | cost
    amount: Decimal
    currency: str
    receipt_id: str


@dataclass
class SourceResult:
    """One adapter's readback. ``covers`` = (loop_id, kind) pairs this source is authoritative for."""
    name: str
    covers: set[tuple[str, str]]
    entries: list[Entry] = field(default_factory=list)
    error: str | None = None  # set => every covered cell is unverified
    notes: dict = field(default_factory=dict)


def day_window(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=JST)
    return start, start + timedelta(days=1)


def in_day(instant: str, day: date) -> bool:
    start, end = day_window(day)
    moment = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("naive timestamp")
    return start <= moment < end


def load_catalog(path: Path = CATALOG) -> list[dict]:
    return json.loads(path.read_text())["loops"]


def credential(service: str, path: Path = CREDENTIALS) -> dict | None:
    try:
        rows = json.loads(path.read_text())["credentials"]
    except (OSError, ValueError, KeyError):
        return None
    return next((row for row in rows if row.get("service") == service), None)


def http_json(url: str, headers: dict, data: bytes | None = None) -> object:
    request = urllib.request.Request(url, headers=headers, data=data)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def run_source(name: str, covers: set, fn, *args, notes: dict | None = None) -> SourceResult:
    result = SourceResult(name, covers, notes=notes if notes is not None else {})
    try:
        result.entries = list(fn(*args))
    except Exception as error:  # fail closed: the covered cells become unverified, nothing invented
        result.entries = []
        result.error = f"{name}:{type(error).__name__}:{str(error)[:120]}"
    return result


# ---------------------------------------------------------------- aggregation


def _cell(loop: dict, kind: str, sources: list[SourceResult]) -> dict:
    covering = [s for s in sources if (loop["id"], kind) in s.covers]
    if not covering:
        if loop["economic"]["role"] in NOT_APPLICABLE_ROLES and kind != "cost":
            return {"status": "zero", "amounts": {}, "receipts": [],
                    "reason": f"not_applicable:role={loop['economic']['role']}"}
        return {"status": "unverified", "reason": "no_source_adapter", "amounts": {}, "receipts": []}
    failed = [s.error for s in covering if s.error]
    if failed:
        return {"status": "unverified", "reason": ";".join(failed), "amounts": {}, "receipts": []}
    amounts: dict[str, Decimal] = {}
    receipts: list[str] = []
    for source in covering:
        for entry in source.entries:
            if entry.loop_id == loop["id"] and entry.kind == kind:
                amounts[entry.currency] = amounts.get(entry.currency, Decimal(0)) + entry.amount
                receipts.append(entry.receipt_id)
    incomplete = sum(s.notes.get("missing_cost_events", {}).get(loop["id"], 0) for s in covering)
    return {"status": "verified" if receipts else "zero", "amounts": amounts, "receipts": receipts,
            "sources": [s.name for s in covering], "incomplete": incomplete}


def build_table(loops: list[dict], sources: list[SourceResult], day: date) -> dict:
    rows = []
    for loop in loops:
        cells = {kind: _cell(loop, kind, sources) for kind in KINDS}
        if any(c["status"] == "unverified" for c in cells.values()):
            net = {"status": "unverified", "reason": "component_unverified", "amounts": {}}
        else:
            amounts: dict[str, Decimal] = {}
            for kind, sign in (("revenue", 1), ("refund", -1), ("cost", -1)):
                for currency, value in cells[kind]["amounts"].items():
                    amounts[currency] = amounts.get(currency, Decimal(0)) + sign * value
            net = {"status": "verified" if amounts else "zero", "amounts": amounts,
                   "incomplete": sum(c.get("incomplete", 0) for c in cells.values())}
        rows.append({"loop_id": loop["id"], **cells, "net": net})
    return {
        "reporting_date": day.isoformat(), "timezone": "Asia/Tokyo",
        "sources": [{"name": s.name, "ok": s.error is None, "error": s.error,
                     "entries": len(s.entries), "notes": s.notes} for s in sources],
        "rows": rows,
    }


def _fmt(cell: dict) -> str:
    if cell["status"] == "unverified":
        return "unverified"
    if not cell["amounts"]:
        return "0"
    text = " ".join(f"{cur} {value.quantize(DISPLAY).normalize():f}"
                    for cur, value in sorted(cell["amounts"].items()))
    return text + ("*" if cell.get("incomplete") else "")


def render(table: dict) -> str:
    header = ("loop", "revenue", "refunds", "cost", "net")
    lines = [[r["loop_id"], _fmt(r["revenue"]), _fmt(r["refund"]), _fmt(r["cost"]), _fmt(r["net"])]
             for r in table["rows"]]
    widths = [max(len(str(x)) for x in col) for col in zip(header, *lines)]
    out = [f"Loop P&L {table['reporting_date']} ({table['timezone']})",
           "  ".join(h.ljust(w) for h, w in zip(header, widths))]
    out += ["  ".join(c.ljust(w) for c, w in zip(line, widths)) for line in lines]
    out.append("")
    out.append("receipts / reasons:")
    for row in table["rows"]:
        for kind in KINDS:
            cell = row[kind]
            receipts = cell["receipts"]
            if receipts:
                shown = ", ".join(receipts[:3]) + (f", ... ({len(receipts)} receipts)" if len(receipts) > 3 else "")
                out.append(f"  {row['loop_id']}.{kind}: {shown}")
            elif cell.get("reason"):
                out.append(f"  {row['loop_id']}.{kind}: {cell['status']} ({cell['reason']})")
    for source in table["sources"]:
        for loop_id, count in sorted(source["notes"].get("missing_cost_events", {}).items()):
            out.append(f"  {loop_id}.cost*: +{count} usage events without provider_cost_usd (not counted)")
        for label, bucket in sorted(source["notes"].get("unattributed", {}).items()):
            out.append(f"  unattributed usage '{label}': {bucket['events']} events, "
                       f"{USAGE_CURRENCY} {bucket[USAGE_CURRENCY].normalize():f} (no Product Loop)")
        if source["notes"].get("unparsed_lines"):
            out.append(f"  {source['name']}: {source['notes']['unparsed_lines']} unparseable lines skipped")
    out.append(f"{USAGE_CURRENCY} = runner-reported API-price estimate, not a provider bill. "
               "Currencies are never converted; net is per currency.")
    out.append("sources: " + ", ".join(
        f"{s['name']}={'ok' if s['ok'] else 'FAILED'}({s['entries']})" for s in table["sources"]))
    return "\n".join(out)


def _jsonable(value):
    if isinstance(value, Decimal):
        return f"{value.normalize():f}"
    raise TypeError(type(value).__name__)


# ---------------------------------------------------------------- Alpaca (investment)

ALPACA_API = "https://api.alpaca.markets"
NEW_YORK = ZoneInfo("America/New_York")  # Alpaca date-only activities are US Eastern trade dates


def alpaca_activities(get=http_json, cred_path: Path = CREDENTIALS) -> list[dict]:
    cred = credential("app.alpaca.markets", cred_path)
    if not cred or not cred.get("live_api_key") or not cred.get("live_api_secret"):
        raise LookupError("credential_missing:app.alpaca.markets.live_api_key")
    headers = {"APCA-API-KEY-ID": cred["live_api_key"], "APCA-API-SECRET-KEY": cred["live_api_secret"]}
    rows: list[dict] = []
    token = None
    while True:
        query = {"direction": "asc", "page_size": "100", **({"page_token": token} if token else {})}
        page = get(f"{ALPACA_API}/v2/account/activities?{urllib.parse.urlencode(query)}", headers)
        rows += page
        if len(page) < 100:
            return rows
        token = page[-1]["id"]


def alpaca_entries(activities: list[dict], day: date, loop_id: str = "investment"):
    """FIFO-realized P&L of sells on ``day`` (gain=revenue, loss=cost) plus that day's fees."""
    lots: dict[str, list[list[Decimal]]] = {}
    for act in activities:
        kind = act.get("activity_type")
        receipt = f"alpaca:activity:{act['id']}"
        if kind == "FILL":
            symbol, qty, price = act["symbol"], Decimal(act["qty"]), Decimal(act["price"])
            quote = symbol.split("/")[1] if "/" in symbol else "USD"
            book = lots.setdefault(symbol, [])
            if act["side"] == "buy":
                book.append([qty, price])
                continue
            pnl, remaining = Decimal(0), qty
            while remaining > 0:
                if not book:
                    raise ValueError(f"alpaca_sell_without_lot:{act['id']}")
                lot = book[0]
                used = min(lot[0], remaining)
                pnl += used * (price - lot[1])
                lot[0] -= used
                remaining -= used
                if lot[0] == 0:
                    book.pop(0)
            if in_day(act["transaction_time"], day) and pnl:
                yield Entry(loop_id, "revenue" if pnl > 0 else "cost", abs(pnl), quote, receipt)
        elif kind == "CFEE" and in_day(act["created_at"], day):
            yield Entry(loop_id, "cost", -Decimal(act["qty"]) * Decimal(act["price"]), "USD", receipt)
        elif kind == "FEE" and in_day(act.get("created_at") or datetime.fromisoformat(act["date"])
                                      .replace(tzinfo=NEW_YORK).isoformat(), day):
            yield Entry(loop_id, "cost", -Decimal(act["net_amount"]), "USD", receipt)


# ---------------------------------------------------------------- Stripe (self-build subscriptions)

STRIPE_API = "https://api.stripe.com"
ZERO_DECIMAL = {"JPY", "KRW", "VND", "CLP", "PYG", "UGX", "XAF", "XOF", "BIF", "DJF", "GNF",
                "KMF", "MGA", "RWF", "VUV", "XPF"}


def stripe_live_key(cred_path: Path = CREDENTIALS) -> str:
    try:
        rows = json.loads(cred_path.read_text())["credentials"]
    except (OSError, ValueError, KeyError):
        rows = []
    for row in rows:
        if "stripe" in str(row.get("service", "")).lower():
            key = str(row.get("api_key", ""))
            if key.startswith(("sk_live_", "rk_live_")):
                return key
    raise LookupError("credential_missing:stripe_live_secret_key(sk_live_/rk_live_)")


def stripe_transactions(day: date, get=http_json, cred_path: Path = CREDENTIALS) -> list[dict]:
    key = stripe_live_key(cred_path)
    start, end = day_window(day)
    rows: list[dict] = []
    after = None
    while True:
        query = {"created[gte]": int(start.timestamp()), "created[lt]": int(end.timestamp()),
                 "limit": 100, **({"starting_after": after} if after else {})}
        page = get(f"{STRIPE_API}/v1/balance_transactions?{urllib.parse.urlencode(query)}",
                   {"Authorization": f"Bearer {key}"})
        rows += page["data"]
        if not page.get("has_more"):
            return rows
        after = page["data"][-1]["id"]


STRIPE_MOVEMENTS = {"payout", "payout_cancel", "payout_failure", "transfer", "transfer_cancel",
                    "transfer_failure", "topup", "topup_reversal"}  # balance moves, not P&L


def stripe_entries(transactions: list[dict], loop_id: str = "self-build"):
    for txn in transactions:
        if txn["type"] in STRIPE_MOVEMENTS:
            continue
        if txn["type"] not in ("charge", "payment", "refund", "payment_refund"):
            raise ValueError(f"stripe_unhandled_txn_type:{txn['type']}")  # e.g. dispute adjustment
        currency = txn["currency"].upper()
        scale = Decimal(1) if currency in ZERO_DECIMAL else Decimal(100)
        receipt = f"stripe:{txn['id']}"
        amount = Decimal(txn["amount"]) / scale
        if txn["type"] in ("charge", "payment"):
            yield Entry(loop_id, "revenue", amount, currency, receipt)
        elif txn["type"] in ("refund", "payment_refund"):
            yield Entry(loop_id, "refund", -amount, currency, receipt)
        if txn["type"] in ("charge", "payment", "refund", "payment_refund") and txn.get("fee"):
            yield Entry(loop_id, "cost", Decimal(txn["fee"]) / scale, currency, receipt)


# ---------------------------------------------------------------- x402 on Base (agent-economy)

BASE_RPC = "https://mainnet.base.org"
USDC_BASE = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TRANSFER_WITH_AUTHORIZATION = "0xe3ee160e"  # EIP-3009 selector used by x402 "exact" EVM payments
LOG_SPAN = 2000  # mainnet.base.org rejects wider eth_getLogs ranges (HTTP 413)
X402_STATE = STATE / "x402-sell"


def x402_wallets(state: Path = X402_STATE) -> tuple[set[str], set[str]]:
    """(payTo wallets that sell, every wallet this system owns) from the seller's own state files."""
    pay_to, owned = set(), set()
    for path in state.glob("*-0x*"):
        address = "0x" + path.name.split("-0x", 1)[1][:40].lower()
        owned.add(address)
        if path.name.startswith(("sales-", "external-inflows-")):
            pay_to.add(address)
    extra = {a.strip().lower() for a in os.environ.get("LM_CFO_X402_PAY_TO", "").split(",") if a.strip()}
    return pay_to | extra, owned | extra


class BaseRpc:
    def __init__(self, url: str = BASE_RPC, post=None):
        self.url = url
        self.post = post or (lambda payload: http_json(
            url, {"content-type": "application/json", "user-agent": "life-manager-cfo/1"},
            json.dumps(payload).encode()))

    def __call__(self, method: str, params: list):
        body = self.post({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if "error" in body:
            raise RuntimeError(f"rpc_{method}:{body['error']}")
        return body["result"]

    def block_time(self, number: int) -> int:
        return int(self("eth_getBlockByNumber", [hex(number), False])["timestamp"], 16)

    def first_block_at(self, instant: int, high: int) -> int:
        """Smallest block with timestamp >= instant (binary search, seeded by Base's 2s blocks)."""
        guess = high - max(0, self.block_time(high) - instant) // 2 - 600
        low = guess if guess > 0 and self.block_time(guess) < instant else 0
        while low < high:
            mid = (low + high) // 2
            if self.block_time(mid) < instant:
                low = mid + 1
            else:
                high = mid
        return low


def _topic(address: str) -> str:
    return "0x" + "0" * 24 + address[2:]


def x402_entries(day: date, rpc: BaseRpc, pay_to: set[str], owned: set[str],
                 loop_id: str = "agent-economy"):
    """USDC moved by EIP-3009 authorization: into a payTo wallet from outside = revenue,
    out of an owned wallet to outside = cost (x402 purchases). Own-to-own is excluded."""
    if not pay_to:
        raise LookupError("x402_pay_to_wallets_not_found")
    start, end = day_window(day)
    latest = int(rpc("eth_blockNumber", []), 16)
    if rpc.block_time(latest) < int(end.timestamp()) - 1:
        last = latest  # the day is still running: read up to the chain head
    else:
        last = rpc.first_block_at(int(end.timestamp()), latest) - 1
    first = rpc.first_block_at(int(start.timestamp()), latest)
    logs: dict[tuple[str, str], dict] = {}
    for low in range(first, last + 1, LOG_SPAN):
        high = min(low + LOG_SPAN - 1, last)
        for topics in ([TRANSFER_TOPIC, None, [_topic(a) for a in sorted(pay_to)]],
                       [TRANSFER_TOPIC, [_topic(a) for a in sorted(owned)]]):
            for log in rpc("eth_getLogs", [{"fromBlock": hex(low), "toBlock": hex(high),
                                            "address": USDC_BASE, "topics": topics}]):
                logs[(log["transactionHash"], log["logIndex"])] = log
    selectors: dict[str, str] = {}
    for (tx, index), log in sorted(logs.items()):
        sender = "0x" + log["topics"][1][-40:].lower()
        recipient = "0x" + log["topics"][2][-40:].lower()
        if sender in owned and recipient in owned:
            continue
        if tx not in selectors:
            receipt = rpc("eth_getTransactionReceipt", [tx])
            transaction = rpc("eth_getTransactionByHash", [tx])
            selectors[tx] = transaction["input"][:10] if receipt["status"] == "0x1" else "failed"
        if selectors[tx] != TRANSFER_WITH_AUTHORIZATION:
            continue
        amount = Decimal(int(log["data"], 16)) / Decimal(10**6)
        receipt_id = f"base:{tx}:{int(index, 16)}"
        if recipient in pay_to:
            yield Entry(loop_id, "revenue", amount, "USDC", receipt_id)
        elif sender in owned:
            yield Entry(loop_id, "cost", amount, "USDC", receipt_id)


# ---------------------------------------------------------------- marketplace payment ledgers

MARKETPLACE_LOOPS = {"coconala": "gig-coconala", "lancers": "gig-lancers", "crowdworks": "gig-crowdworks"}
# platform -> the marketplace-core ledger its owner loop writes. Coconala/CrowdWorks have none yet.
MARKETPLACE_LEDGERS = {"lancers": Path("~/.local/state/anicca/lancers/marketplace-ledger.sqlite3").expanduser()}


def marketplace_ledgers() -> dict[str, Path]:
    ledgers = dict(MARKETPLACE_LEDGERS)
    for pair in os.environ.get("LM_CFO_MARKETPLACE_LEDGERS", "").split(","):
        if "=" in pair:
            platform, path = pair.split("=", 1)
            ledgers[platform.strip()] = Path(path.strip()).expanduser()
    return ledgers


def marketplace_entries(platform: str, ledger: Path, day: date):
    """Settled ``payment_received`` rows (net of platform fee) from the marketplace-core ledger."""
    import sqlite3
    if not ledger.is_file() or ledger.stat().st_size == 0:
        raise FileNotFoundError(f"marketplace_ledger_missing:{platform}")
    connection = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT receipt_id, amount_minor, currency, occurred_at FROM marketplace_events "
            "WHERE platform = ? AND event_type = 'payment_received'", (platform,)).fetchall()
    finally:
        connection.close()
    for receipt_id, amount_minor, currency, occurred_at in rows:
        if not in_day(occurred_at, day):
            continue
        if not receipt_id or amount_minor is None or not currency:
            raise ValueError(f"marketplace_payment_without_receipt:{platform}")
        scale = Decimal(1) if currency in ZERO_DECIMAL else Decimal(100)
        yield Entry(MARKETPLACE_LOOPS[platform], "revenue", Decimal(amount_minor) / scale, currency,
                    f"{platform}:{receipt_id}")


# ---------------------------------------------------------------- agent-runner usage (model cost)

USAGE_CURRENCY = "USD_API_EQUIV"  # runner's provider_cost_usd is an API-price estimate, not a bill
# Deterministic usage-label -> Product Loop bookkeeping for labels that are not registry job ids.
USAGE_PREFIXES = (
    ("hf-gig-", "gig-coconala"), ("coconala", "gig-coconala"),
    ("lancers", "gig-lancers"), ("crowdworks", "gig-crowdworks"),
    ("writer", "writer"), ("article-", "writer"),
    ("affiliate", "affiliate"), ("alpaca", "investment"),
    ("x402", "agent-economy"), ("agent-economy", "agent-economy"), ("the402", "agent-economy"),
    ("job-search", "job-hunter"), ("mercor", "job-hunter"),
    ("fundraiser", "fundraiser"), ("connector", "connector"),
    ("life-manager-dev", "self-build"), ("life-manager-selfbuild", "self-build"),
    ("life-manager-recovery", "self-build"), ("self-improve", "self-build"),
    ("life-manager-anicca-", "mobile-apps"), ("life-manager-honne", "mobile-apps"),
    ("capafy", "capafy"), ("cfo", "cfo"), ("life-manager-cfo", "cfo"),
)


def usage_loop(label: str, job_map: dict[str, str]) -> str | None:
    if label in job_map:
        return job_map[label]
    return next((loop for prefix, loop in USAGE_PREFIXES if label.startswith(prefix)), None)


def usage_files(root: Path = Path("~/.local/state").expanduser()) -> list[Path]:
    return sorted(root.rglob("agent-usage.jsonl"))


def usage_entries(files: list[Path], day: date, job_map: dict[str, str], notes: dict):
    seen: set[str] = set()
    for path in files:
        with path.open() as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                    if not in_day(event["timestamp"], day):
                        continue
                except (ValueError, KeyError, TypeError):
                    notes["unparsed_lines"] = notes.get("unparsed_lines", 0) + 1
                    continue
                if event.get("event_id") in seen:
                    continue
                seen.add(event["event_id"])
                cost = event.get("provider_cost_usd")
                loop_id = usage_loop(str(event.get("loop", "")), job_map)
                if loop_id is None:
                    bucket = notes.setdefault("unattributed", {}).setdefault(
                        str(event.get("loop")), {"events": 0, USAGE_CURRENCY: Decimal(0)})
                    bucket["events"] += 1
                    bucket[USAGE_CURRENCY] += Decimal(str(cost or 0))
                    continue
                if cost is None:
                    missing = notes.setdefault("missing_cost_events", {})
                    missing[loop_id] = missing.get(loop_id, 0) + 1
                    continue
                yield Entry(loop_id, "cost", Decimal(str(cost)), USAGE_CURRENCY,
                            f"agent-usage:{event['event_id']}")


# ---------------------------------------------------------------- command


def collect(day: date, loops: list[dict]) -> list[SourceResult]:
    ids = [loop["id"] for loop in loops]
    job_map = {job: loop["id"] for loop in loops for job in loop["job_ids"]}
    sources = [
        run_source("alpaca", {("investment", k) for k in KINDS},
                   lambda: alpaca_entries(alpaca_activities(), day)),
        run_source("stripe", {("self-build", k) for k in KINDS},
                   lambda: stripe_entries(stripe_transactions(day))),
    ]
    pay_to, owned = x402_wallets()
    sources.append(run_source("x402-base", {("agent-economy", k) for k in KINDS},
                              lambda: x402_entries(day, BaseRpc(), pay_to, owned)))
    ledgers = marketplace_ledgers()
    for platform, loop_id in MARKETPLACE_LOOPS.items():
        covers = {(loop_id, "revenue"), (loop_id, "refund")}
        if platform in ledgers:
            sources.append(run_source(f"marketplace-{platform}", covers,
                                      lambda p=platform: marketplace_entries(p, ledgers[p], day)))
        else:
            sources.append(SourceResult(f"marketplace-{platform}", covers,
                                        error=f"marketplace-{platform}:no_payment_ledger_owner_writes"))
    notes: dict = {}
    sources.append(run_source("agent-usage", {(i, "cost") for i in ids},
                              lambda: usage_entries(usage_files(), day, job_map, notes), notes=notes))
    return sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", help="Asia/Tokyo reporting day, default today")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    day = date.fromisoformat(args.date) if args.date else datetime.now(JST).date()
    loops = load_catalog()
    table = build_table(loops, collect(day, loops), day)
    print(json.dumps(table, default=_jsonable, indent=1) if args.json else render(table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
