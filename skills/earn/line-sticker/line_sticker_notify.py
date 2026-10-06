#!/usr/bin/env python3
"""Submission notification for the LINE sticker factory.

No skill under skills/earn/ currently wires a Telegram business-report sender (that pattern only
exists in skills/_shared/marketplace-core for gig-reply flows, with its own outbox DB and chat-id
config this loop has no entry for). Rather than invent a new Telegram wiring, this appends one
durable event to the same factory-events.jsonl the state machine already writes to on every stage
transition -- the hourly owner report / Dais can already tail that ledger.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
import sys  # noqa: E402

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from factory import append_event  # noqa: E402


def notify(set_dir: Path, payload: dict) -> None:
    append_event(set_dir.parent, {"set": set_dir.name, "stage": "submit", "status": "submitted", **payload})
