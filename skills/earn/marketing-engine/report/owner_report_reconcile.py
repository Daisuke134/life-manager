#!/usr/bin/env python3
"""Read back open owner-report Telegram deliveries; never send or retry.

Shape copied from ``intel/treg_lead_signals_reconcile.py``: the official readback is the
owner's MTProto user session (``skills/tools/telegram-user/tg_user.py``).  Per open key
(``delivery_unknown`` or a stale ``sending`` claim) the attempt window after its claim is
read completely in every Life Manager bot dialog:

* exactly one bot message whose full text equals the event's rendering (Telegram trims
  surrounding whitespace) -> ``delivered`` via ``OwnerReportStore.reconcile_delivery``;
* complete windows with no same-kind message carrying the event's post URL and none
  lacking a link (an older renderer printed no URL) -> ``not_delivered_confirmed``;
  the normal sweep re-sends;
* a complete but ambiguous readback of a checkpoint or incident claimed over 7 days ago ->
  ``expired_unknown`` (never re-sent: a late checkpoint or health warning has no value);
* an incident text names no post, day or platform, so every same-kind message is
  ambiguous: incidents close only by complete absence or by that expiry;
* anything else stays open.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import pathlib
import subprocess
import sys
from typing import Any, Callable, Iterable

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
ROOT = HERE.parents[3]

import owner_report  # noqa: E402


READBACK_WINDOW_SECONDS = 900  # same window as the Treg sibling; one send takes < 2 min
CLOCK_SKEW_SECONDS = 300
EXPIRY_AGE = dt.timedelta(days=7)
USER_PYTHON = pathlib.Path.home() / ".cache/telegram-user-venv/bin/python"
USER_SCRIPT = ROOT / "skills/tools/telegram-user/tg_user.py"
CREDENTIALS_FILE = pathlib.Path.home() / ".local/share/anicca/credentials.json"
# Owner reports were sent by the env/local bot before 2026-10-08, the cloud bot until
# 2026-10-15 and the local bot since; both credentials name every bot that ever sent them.
BOT_SERVICES = ("telegram-life-manager", "telegram-cloud-life-manager")
KIND_MARKERS = {"action": "📣", "checkpoint": "📊", "incident": "⚠️"}
EXPIRING_KINDS = {"checkpoint", "incident"}
OPEN_STATUSES = {"delivery_unknown", "sending"}


class ReconcileUnknown(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


ReadWindow = Callable[[int, dt.datetime, dt.datetime], dict]


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _attempt_window(rows: list[dict], message_key: str, now: dt.datetime) -> tuple[dt.datetime, dt.datetime, dt.datetime]:
    claims = [row for row in rows if row.get("message_key") == message_key and row.get("status") == "sending"]
    claimed = owner_report._parse_time(claims[-1].get("claimed_at")) if claims else None
    if claimed is None:
        raise ReconcileUnknown("claim_time_missing")
    start = claimed - dt.timedelta(seconds=CLOCK_SKEW_SECONDS)
    end = claimed + dt.timedelta(seconds=READBACK_WINDOW_SECONDS)
    if end >= now:
        raise ReconcileUnknown("readback_window_open")
    return claimed, start, end


def _identity(store: owner_report.OwnerReportStore, message_key: str) -> tuple[dict, str | None, str, str | None]:
    events = [row for row in store._reports() if row.get("message_key") == message_key]
    if len(events) != 1:
        raise ReconcileUnknown("owner_report_event_missing")
    event = events[0]
    url = (event.get("facts") or {}).get("native_url")
    marker = KIND_MARKERS.get(event.get("kind"))
    if event.get("kind") == "incident":
        return event, None, marker, None  # its text carries no identity to match
    if marker is None or not isinstance(url, str) or not url.startswith("https://"):
        raise ReconcileUnknown("event_identity_unavailable")
    rendered = owner_report.render_japanese(event).strip()
    if event["kind"] == "checkpoint":
        # An unmeasured checkpoint text omits the age, so 6h/24h/72h of one post read the same.
        probe = copy.deepcopy(event)
        probe["facts"]["target_age_hours"] = -1
        if owner_report.render_japanese(probe).strip() == rendered:
            rendered = None
    return event, url, marker, rendered


def _reconcile_key(
    store: owner_report.OwnerReportStore,
    rows: list[dict],
    message_key: str,
    *,
    bot_ids: list[int],
    read_window: ReadWindow,
    now: dt.datetime,
) -> dict:
    claimed, start, end = _attempt_window(rows, message_key, now)
    event, url, marker, rendered = _identity(store, message_key)
    exact, same_url, linkless, scanned = [], 0, 0, 0
    for bot_id in bot_ids:
        window = read_window(bot_id, start, end)
        if not isinstance(window, dict) or window.get("complete") is not True or not isinstance(window.get("messages"), list):
            raise ReconcileUnknown("telegram_history_incomplete")
        for message in window["messages"]:
            if not isinstance(message, dict) or str(message.get("sender_id")) != str(bot_id) or message.get("out") is not False:
                continue
            when = owner_report._parse_time(message.get("date"))
            text = message.get("text")
            if when is None or not start <= when <= end or not isinstance(text, str):
                continue
            scanned += 1
            if not text.startswith(marker):
                continue  # another report kind, even when it shows the same post URL
            if rendered is not None and text.strip() == rendered:
                exact.append((bot_id, message))
            elif url is not None and url in text.split():
                same_url += 1  # same post, other checkpoint age or another renderer version
            elif url is None or "https://" not in text:
                linkless += 1
    observed_at = _iso(now)
    readback = {
        "source": "telegram_mtproto_history",
        "observed_at": observed_at,
        "window_start": _iso(start),
        "window_end": _iso(end),
        "bot_ids": list(bot_ids),
        "messages_scanned": scanned,
    }
    if len(exact) == 1:
        bot_id, message = exact[0]
        message_id = message.get("id")
        if type(message_id) is not int or message_id <= 0:
            raise ReconcileUnknown("telegram_message_id_invalid")
        readback.update({
            "matched_by": "immutable_event_identity",
            "message_id": message_id,
            "message_date": message.get("date"),
            "sender_bot_id": bot_id,
        })
        store.reconcile_delivery(message_key, {"status": "delivered", "message_ids": [message_id], "provider_readback": readback})
        return {"message_key": message_key, "status": "delivered"}
    ambiguity = (
        "event_identity_not_unique" if exact
        else "same_kind_message_with_same_url" if same_url
        else "same_kind_message_without_identity" if linkless
        else None
    )
    if ambiguity is not None:
        if event["kind"] not in EXPIRING_KINDS or now - claimed < EXPIRY_AGE:
            raise ReconcileUnknown(ambiguity)
        readback.update({
            "matched_by": "complete_window_ambiguous",
            "complete": True,
            "ambiguity": ambiguity,
            "claim_age_seconds": int((now - claimed).total_seconds()),
        })
        store.expire_unknown(message_key, f"stale_{event['kind']}_identity_unprovable", readback)
        return {"message_key": message_key, "status": "expired_unknown"}
    readback.update({"matched_by": "complete_window_absence", "complete": True})
    store.confirm_not_delivered(message_key, readback)
    return {"message_key": message_key, "status": "not_delivered_confirmed"}


def reconcile_open_deliveries(
    state_root: pathlib.Path,
    *,
    bot_ids: Iterable[int],
    read_window: ReadWindow,
    now: dt.datetime | None = None,
) -> list[dict]:
    state_root = pathlib.Path(state_root)
    store = owner_report.OwnerReportStore(state_root / "owner-reports.jsonl", state_root / "owner-report-deliveries.jsonl")
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = store._deliveries()
    latest: dict[str, dict] = {}
    for row in rows:
        if isinstance(row.get("message_key"), str):
            latest[row["message_key"]] = row
    bots = list(bot_ids)
    results = []
    for message_key, row in latest.items():
        if row.get("status") not in OPEN_STATUSES:
            continue
        try:
            if not bots:
                raise ReconcileUnknown("bot_identity_unavailable")
            results.append(_reconcile_key(store, rows, message_key, bot_ids=bots, read_window=read_window, now=now))
        except ReconcileUnknown as error:
            results.append({"message_key": message_key, "status": "unknown", "reason": error.code})
        except owner_report.OwnerReportError as error:
            results.append({"message_key": message_key, "status": "unknown", "reason": type(error).__name__})
    return results


def _known_bot_ids() -> list[int]:
    try:
        rows = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8")).get("credentials") or []
    except (OSError, ValueError, AttributeError):
        return []
    ids = []
    for row in rows:
        if isinstance(row, dict) and row.get("service") in BOT_SERVICES:
            prefix = str(row.get("bot_token") or "").split(":", 1)[0]
            if prefix.isdigit() and int(prefix) not in ids:
                ids.append(int(prefix))
    return ids


def _run_tg_user(*arguments: str) -> dict[str, Any]:
    if not USER_PYTHON.is_file() or not USER_SCRIPT.is_file():
        raise ReconcileUnknown("telegram_user_session_tool_unavailable")
    try:
        completed = subprocess.run(
            [str(USER_PYTHON), str(USER_SCRIPT), *arguments],
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ReconcileUnknown("telegram_user_history_read_failed") from None
    if completed.returncode != 0:
        raise ReconcileUnknown("telegram_user_history_read_failed")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise ReconcileUnknown("telegram_user_history_invalid") from None
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise ReconcileUnknown("telegram_user_history_invalid")
    return result


def _tg_user_window(bot_id: int, start: dt.datetime, end: dt.datetime) -> dict:
    return _run_tg_user("window", str(bot_id), _iso(start), _iso(end))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        results = reconcile_open_deliveries(args.state_root, bot_ids=_known_bot_ids(), read_window=_tg_user_window)
    except Exception as error:  # an unreadable ledger leaves every key open for the sweep to report
        results = [{"status": "unknown", "reason": type(error).__name__}]
    print(json.dumps({"owner_report_reconcile": results}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
