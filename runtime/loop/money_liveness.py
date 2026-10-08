"""Outcome-freshness alarm for the money loops (Dais 2026-10-08).

A launchd job that exits 0 proves nothing: Capafy's factory ran every 15 minutes for a week
without submitting an agent, and the Writer was silent for nine days, while the health observer
only appended to a file nobody read. A lane is alive only if its outcome artifact is fresh.
Stale lanes are sent to Telegram once per cooldown, and a recovery is announced once.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/money-liveness.json"
COOLDOWN_HOURS = 12


def _age_hours(path: Path, now: float) -> float | None:
    try:
        return (now - path.stat().st_mtime) / 3600
    except OSError:
        return None


def evaluate(lanes: list[dict], state_home: Path, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    rows = []
    for lane in lanes:
        age = _age_hours(state_home / lane["path"], now)
        rows.append({**lane, "age_hours": age,
                     "stale": age is None or age > float(lane["max_age_hours"])})
    return rows


def messages(rows: list[dict], memory: dict, now: float) -> tuple[list[str], dict]:
    """Return (telegram messages, new memory). memory maps lane id -> last alert epoch."""
    out, new = [], dict(memory)
    for row in rows:
        last = memory.get(row["id"])
        if row["stale"]:
            if last is None or now - float(last) >= COOLDOWN_HOURS * 3600:
                age = "never" if row["age_hours"] is None else f"{row['age_hours']:.0f}h"
                out.append(f"STALE money loop [{row['id']}]: {row['meaning']} for {age} "
                           f"(limit {row['max_age_hours']}h). Look at: {row['look_at']}")
                new[row["id"]] = now
        elif last is not None:
            out.append(f"RECOVERED money loop [{row['id']}]: outcome is fresh again.")
            new.pop(row["id"], None)
    return out, new


def telegram(text: str) -> bool:
    script = ROOT / "skills/_shared/scripts/telegram-notify.sh"
    result = subprocess.run(
        ["bash", "-c", f'. "{script}" && telegram_notify "$1"', "_", text],
        capture_output=True, text=True, timeout=60, check=False)
    return result.returncode == 0


def run(state_home: Path, state_root: Path, *, send=telegram, now: float | None = None,
        config: Path = CONFIG) -> dict:
    now = time.time() if now is None else now
    lanes = json.loads(config.read_text(encoding="utf-8"))["lanes"]
    memory_path = state_root / "money-liveness-state.json"
    try:
        memory = json.loads(memory_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        memory = {}
    rows = evaluate(lanes, state_home, now)
    texts, new_memory = messages(rows, memory, now)
    sent = []
    for text in texts:
        if send(text):
            sent.append(text)
        else:  # not delivered: keep the old memory so the next tick retries
            lane = text.split("[", 1)[1].split("]", 1)[0]
            if lane in memory:
                new_memory[lane] = memory[lane]
            else:
                new_memory.pop(lane, None)
    state_root.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(json.dumps(new_memory, sort_keys=True), encoding="utf-8")
    return {"stale": [r["id"] for r in rows if r["stale"]], "sent": len(sent), "attempted": len(texts)}


if __name__ == "__main__":
    home = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", "~/.local/state/life-manager")).expanduser()
    print(json.dumps(run(home, home / "health-observer"), sort_keys=True))
