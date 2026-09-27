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
            if r["kind"] == "receipt" and r.get("result") in ("entered", "exited", "unhedged"):
                return r["perp"] if r["result"] in ("entered", "unhedged") else None
        return None

    def needs_unwind(self) -> bool:
        for r in reversed(self.rows()):
            if r["kind"] == "receipt" and r.get("result") in ("entered", "exited", "unhedged"):
                return r["result"] == "unhedged"
        return False

    def mark_equity(self, equity: float) -> None:
        self.append("equity", equity=round(float(equity), 6))

    def risk_state(self, today: str) -> tuple[float, float]:
        marks = [r for r in self.rows() if r["kind"] == "equity"]
        if not marks:
            return 0.0, 0.0
        todays = [r["equity"] for r in marks if r["ts"][:10] == today]
        return (todays[0] if todays else marks[-1]["equity"]), max(r["equity"] for r in marks)
