from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "coconala_queue_snapshot.py"
SPEC = importlib.util.spec_from_file_location("coconala_queue_snapshot_latest_date", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
queue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(queue)


def test_latest_schedule_event_wins_over_first_historical_match() -> None:
    messages = [
        {
            "side": "system",
            "text": "納品予定日が変更されました。\n修正後納品予定日：2026/09/18",
        },
        {
            "side": "buyer",
            "text": "資料を追加しました。",
        },
        {
            "side": "system",
            "text": "納品予定日が変更されました。\n修正後納品予定日：2026/09/30",
        },
    ]

    assert queue.latest_delivery_date_from_messages(messages, "2026/09/10") == "2026/09/30"


def test_schedule_falls_back_when_no_system_event_has_a_date() -> None:
    messages = [{"side": "buyer", "text": "納期について相談したいです。"}]

    assert queue.latest_delivery_date_from_messages(messages, "2026/09/10") == "2026/09/10"
