#!/usr/bin/env python3
"""Read the owner's business evidence; restored from the existing outcome watcher."""
from __future__ import annotations

import argparse
import json
import os
import time
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/earn/gig/scripts"))
from daily_verdict import SETTLED_STATES, _epoch

GIG = Path(os.environ.get("GIG_STATE_DIR", str(Path.home() / "gig"))).expanduser()
EARNINGS = GIG / "earnings.jsonl"
APPLIED = GIG / "applied.jsonl"
TOKENS = Path(os.environ.get("ANICCA_TOKEN_BUDGET_LEDGER", str(
    Path.home() / ".local/state/life-manager/telemetry/token-budget.jsonl"))).expanduser()

@dataclass
class Findings:
    window_hours: int
    spend_tokens: int = 0
    model_calls: int = 0
    earnings_rows: int = 0
    earnings_jpy: float = 0.0
    verified_applications: int = 0
    hours_since_outcome: float | None = None
    alerts: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def outcomes(self) -> int:
        return self.earnings_rows + self.verified_applications


def _rows(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    out.append(value)
            except json.JSONDecodeError:
                continue  # a truncated append must not blind the whole check
    return out


def collect(window_hours: int, now: float) -> Findings:
    f = Findings(window_hours=window_hours)
    cutoff = now - window_hours * 3600
    latest_outcome: float | None = None

    if TOKENS.exists():
        events = _rows(TOKENS)
        reservations = {str(row.get("event_id")): row for row in events
                        if row.get("type") == "reservation" and row.get("status") == "allowed"}
        settlements = {str(row.get("event_id")): row for row in events
                       if row.get("type") == "settlement"}
        for event_id, settlement in settlements.items():
            reservation = reservations.get(event_id, {})
            owner = str(reservation.get("loop") or "")
            ts = _epoch(settlement.get("timestamp"))
            if (owner != "gig" and not owner.startswith("hf-gig-")) or ts is None or not cutoff <= ts <= now:
                continue
            f.model_calls += 1
            f.spend_tokens += int(settlement["charged_tokens"])
        # Reservation rows carry no per-call charge; spend only shows up as the running
        # daily_consumed_tokens counter in legacy untyped rows. It resets each day. Sum
        # per-day (max - min), which survives both the reset and out-of-order rows.
        by_day: dict[str, list[int]] = {}
        for row in events:
            if row.get("type") or row.get("loop") != "gig":
                continue
            ts = _epoch(row.get("timestamp"))
            if ts is None or ts < cutoff:
                continue
            f.model_calls += 1
            consumed = row.get("daily_consumed_after_tokens")
            if consumed is None:
                consumed = row.get("daily_consumed_tokens")
            if consumed is None:
                continue
            by_day.setdefault(str(row.get("day") or ""), []).append(int(consumed))
        for values in by_day.values():
            f.spend_tokens += max(values) - min(values)
    else:
        f.missing.append(str(TOKENS))

    if EARNINGS.exists():
        for row in _rows(EARNINGS):
            if row.get("status") not in SETTLED_STATES or not row.get("evidence"):
                continue
            ts = _epoch(row.get("ts")) or _epoch(row.get("finished_at"))
            if ts is None:
                continue
            if latest_outcome is None or ts > latest_outcome:
                latest_outcome = ts
            if ts >= cutoff:
                f.earnings_rows += 1
                f.earnings_jpy += float(row.get("jpy") or 0)
    else:
        f.missing.append(str(EARNINGS))

    if APPLIED.exists():
        for row in _rows(APPLIED):
            # Only a readback against the marketplace's own applied page counts.
            if not (row.get("status") == "applied" and row.get("submit_verified") is True
                    and row.get("applied_page_verified") is True):
                continue
            ts = _epoch(row.get("ts"))
            if ts is None:
                continue
            if latest_outcome is None or ts > latest_outcome:
                latest_outcome = ts
            if ts >= cutoff:
                f.verified_applications += 1
    else:
        f.missing.append(str(APPLIED))

    if latest_outcome is not None:
        f.hours_since_outcome = round((now - latest_outcome) / 3600, 1)
    return f


def judge(f: Findings, *, min_spend: int, stale_hours: int) -> Findings:
    if f.missing:
        f.alerts.append("LEDGER_ABSENT")
    if f.spend_tokens >= min_spend and f.outcomes == 0:
        f.alerts.append("SILENT_SUCCESS")
    if f.hours_since_outcome is None or f.hours_since_outcome > stale_hours:
        f.alerts.append("STALE_OUTCOME")
    return f


def human(f: Findings) -> str:
    if not f.alerts:
        return (f"🟢 gig: 直近{f.window_hours}時間で成果{f.outcomes}件"
                f"（入金{int(f.earnings_jpy):,}円・応募{f.verified_applications}件）")
    lines = [f"🔴 gig loop が空回りしています（直近{f.window_hours}時間）", ""]
    if "SILENT_SUCCESS" in f.alerts:
        lines += [
            f"・モデル呼び出し {f.model_calls}回・{f.spend_tokens:,}トークンを消費しましたが、",
            "  外部から確認できる成果は0件です（入金も、検証済みの応募も0）。",
        ]
    if "STALE_OUTCOME" in f.alerts:
        since = "一度もありません" if f.hours_since_outcome is None else f"{f.hours_since_outcome}時間前です"
        lines.append(f"・最後に成果が出たのは{since}。")
    if "LEDGER_ABSENT" in f.alerts:
        lines.append(f"・台帳が読めません: {', '.join(f.missing)}（この状態だと上の検知自体が効きません）")
    lines += ["", "原因と公式の成果記録を確認します。"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=int, default=24)
    ap.add_argument("--min-spend-tokens", type=int, default=500_000)
    ap.add_argument("--stale-hours", type=int, default=48)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    f = judge(collect(args.window_hours, time.time()),
              min_spend=args.min_spend_tokens, stale_hours=args.stale_hours)
    if args.json:
        print(json.dumps({
            "window_hours": f.window_hours, "spend_tokens": f.spend_tokens,
            "model_calls": f.model_calls, "earnings_rows": f.earnings_rows,
            "earnings_jpy": f.earnings_jpy,
            "verified_applications": f.verified_applications,
            "outcomes": f.outcomes, "hours_since_outcome": f.hours_since_outcome,
            "alerts": f.alerts, "missing": f.missing,
        }, ensure_ascii=False))
    else:
        print(human(f))
    return 1 if f.alerts else 0


if __name__ == "__main__":
    raise SystemExit(main())
