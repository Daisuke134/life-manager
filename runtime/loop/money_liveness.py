"""Outcome-freshness alarm for the money loops (Dais 2026-10-08).

A launchd job that exits 0 proves nothing: Capafy's factory ran every 15 minutes for a week
without submitting an agent, and the Writer was silent for nine days, while the health observer
only appended to a file nobody read. A lane is alive only if its typed outcome is fresh.
Stale lanes are sent to Telegram once per cooldown, and a recovery is announced once.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/money-liveness.json"
COOLDOWN_HOURS = 12


def _age_hours(path: Path, now: float) -> float | None:
    try:
        return (now - path.stat().st_mtime) / 3600
    except OSError:
        return None


def _timestamp(value, now: float) -> float | None:
    if not isinstance(value, str) or "T" not in value:
        return None  # Date-only legacy rows cannot prove an hourly outcome clock.
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        stamp = parsed.timestamp() if parsed.tzinfo else None
        return stamp if stamp is not None and stamp <= now else None
    except (ValueError, OverflowError, OSError):
        return None


def _records(path: Path):
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if isinstance(value, dict):
                    yield value
    except (OSError, UnicodeError):
        return


def _outcome_clocks(lane: dict, state_home: Path, now: float) -> dict:
    reader, path = lane.get("reader"), state_home / lane["path"]
    attempts, verified, healthy_terminals, terminal_results = [], [], [], []
    idle_at = None
    if reader == "capafy_distribution":
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            entries = {}
        for slot, entry in entries.items() if isinstance(entries, dict) else ():
            if not isinstance(entry, dict):
                continue
            # The existing receipt is keyed by its JST occurrence. A later file touch
            # cannot refresh a previous slot, including a partial/blocked write.
            match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:-h(\d{2})(?:m(\d{2}))?)?", slot)
            if not match:
                continue
            try:
                stamp = datetime.fromisoformat(f"{match[1]}T{match[2] or '00'}:{match[3] or '00'}:00").replace(tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()
            except ValueError:
                continue
            destinations = entry.get("destinations")
            article = destinations.get("aniccaai") if isinstance(destinations, dict) else None
            if (stamp <= now and entry.get("status") == "published"
                    and isinstance(article, dict) and article.get("status") == "published"
                    and str(article.get("url") or "").startswith("https://")):
                verified.append(stamp)
    else:
        for row in _records(path):
            if reader in {"capafy_factory", "capafy_submission"}:
                if reader == "capafy_submission":
                    if row.get("agent_id") and str(row.get("status") or "").startswith("submitted"):
                        verified.append(_timestamp(row.get("submitted_at"), now))
                    continue
                stamp = _timestamp(row.get("observed_at"), now)
                if row.get("schema_version") == 1 and row.get("execution_id"):
                    attempts.append(stamp)
                    if row.get("phase") == "terminal" and stamp is not None:
                        healthy = row.get("healthy") is True and type(row.get("rc")) is int and row["rc"] == 0
                        terminal_results.append((stamp, len(terminal_results), healthy))
                        if healthy:
                            healthy_terminals.append(stamp)
            elif reader == "writer_publication":
                attempts.append(_timestamp(row.get("ts"), now))
                if (row.get("published") is True and row.get("verified") is True
                        and row.get("identity_verified") is True and row.get("public_id")
                        and row.get("state") == "live"
                        and str(row.get("live_url") or "").startswith("https://")):
                    verified.append(_timestamp(row.get("published_at"), now))
            elif reader == "business_readback" and row.get("product_id") == lane.get("product_id"):
                stamp = _timestamp(row.get("observed_at"), now)
                attempts.append(stamp)
                sources = row.get("sources")
                for name in ("revenuecat", "app_store_sales"):
                    source = sources.get(name) if isinstance(sources, dict) else None
                    if (isinstance(source, dict) and source.get("status") == "available"
                            and re.fullmatch(r"[a-f0-9]{64}", str(source.get("evidence_sha256") or ""))
                            and isinstance(source.get("data"), dict) and source["data"]):
                        verified.append(stamp)
            elif reader == "marketing_publication":
                receipt = row.get("receipt")
                if not isinstance(receipt, dict) or (receipt.get("product_id") or receipt.get("product")) != lane.get("product_id"):
                    continue
                if (receipt.get("kind") in ("marketing_daily_distribution", "marketing_video_distribution", "marketing_native_carousel_distribution")
                        and receipt.get("status") == "published" and receipt.get("provider_reconciled") is True
                        and isinstance(receipt.get("provider_post_id"), str) and receipt["provider_post_id"].strip()
                        and str(receipt.get("public_url") or "").startswith("https://")):
                    verified.append(_timestamp(receipt.get("published_at"), now))
    if reader == "capafy_submission":
        terminals = [row for row in _records(state_home / lane["terminal_path"])
                     if row.get("schema_version") == 1 and row.get("execution_id")]
        for row in terminals:
            attempts.append(_timestamp(row.get("observed_at"), now))
        terminal = max(terminals, key=lambda row: str(row.get("observed_at") or ""), default={})
        if (terminal.get("phase") == "terminal" and terminal.get("healthy") is True
                and type(terminal.get("rc")) is int and terminal["rc"] == 0
                and terminal.get("verdict") in {"CAP_FULL", "DRAINED"}):
            idle_at = _timestamp(terminal.get("observed_at"), now)
    latest = lambda values: max((value for value in values if value is not None), default=None)
    return {"last_attempt": latest(attempts), "last_verified_outcome": latest(verified),
            "last_terminal_success": latest(healthy_terminals), "last_paid": None, "idle_at": idle_at,
            "latest_terminal_failed": bool(terminal_results and not max(terminal_results)[2])}


def evaluate(lanes: list[dict], state_home: Path, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    rows = []
    for lane in lanes:
        clocks = _outcome_clocks(lane, state_home, now)
        stamp = clocks["last_terminal_success"] if lane.get("reader") == "capafy_factory" else clocks["last_verified_outcome"]
        age = (now - stamp) / 3600 if stamp is not None else None
        no_work = (clocks["idle_at"] is not None and now - clocks["idle_at"] <= 3600
                   and (age is None or age > float(lane["max_age_hours"])))
        stale = not no_work and (clocks["latest_terminal_failed"] or age is None or age > float(lane["max_age_hours"]))
        reason = ("no_work" if no_work else "terminal_failed" if clocks["latest_terminal_failed"]
                  else "outcome_missing_or_unverified" if stamp is None else "outcome_stale" if stale else "verified_record")
        rows.append({**lane, **clocks, "mtime_age_hours": _age_hours(state_home / lane["path"], now),
                     "age_hours": age, "outcome_status": "no_work" if no_work else "stale" if stale and stamp is not None else "verified" if stamp is not None else "unknown",
                     "reason": reason, "stale": stale})
    return rows


def messages(rows: list[dict], memory: dict, now: float) -> tuple[list[str], dict]:
    """Return (telegram messages, new memory). memory maps lane id -> last alert epoch."""
    out, new = [], dict(memory)
    for row in rows:
        last = memory.get(row["id"])
        if row.get("outcome_status") == "no_work":
            continue
        if row["stale"]:
            if last is None or now - float(last) >= COOLDOWN_HOURS * 3600:
                age = "never" if row["age_hours"] is None else f"{row['age_hours']:.0f}h"
                out.append(f"STALE money loop [{row['id']}]: {row['meaning']}。経過 {age} "
                           f"(期限 {row['max_age_hours']}h)。確認先: {row['look_at']}")
                new[row["id"]] = now
        elif last is not None:
            fact = "正常な実行記録" if row.get("reader") == "capafy_factory" else "正式な成果記録"
            out.append(f"RECOVERED money loop [{row['id']}]: 新しい{fact}を確認しました。")
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
