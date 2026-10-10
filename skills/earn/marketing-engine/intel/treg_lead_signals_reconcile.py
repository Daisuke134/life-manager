#!/usr/bin/env python3
"""Read back one Treg monitor's Telegram effect; never send or retry."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.host.resource_admission import (  # noqa: E402
    resolve_pre_effect_occurrence,
    resolve_unknown_occurrence,
    state_root as admission_state_root,
)
from skills._shared.telegram import TelegramClient, _split_text  # noqa: E402
from treg_lead_signals_weekly import (  # noqa: E402
    CSV_FIELDS,
    MonitorError,
    OWNER_ID,
    _assert_outside_repo,
    _atomic_json,
    _ensure_private_dir,
    _occurrence_id,
    _occurrence_key,
    _read_json,
    _read_private,
    _read_signals,
    _timestamp,
    _capture_partial,
    _mcp_events,
    _trace_call_receipts,
    _write_signals,
)


READBACK_WINDOW_SECONDS = 900
MAX_EVENT_BYTES = 24 * 1024 * 1024
USER_PYTHON = Path.home() / ".cache/telegram-user-venv/bin/python"
USER_SCRIPT = ROOT / "skills/tools/telegram-user/tg_user.py"


class ReconcileUnknown(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _parse_time(value: object) -> dt.datetime:
    if not isinstance(value, str):
        raise ReconcileUnknown("timestamp_invalid")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ReconcileUnknown("timestamp_invalid") from None
    if parsed.tzinfo is None:
        raise ReconcileUnknown("timestamp_timezone_missing")
    return parsed.astimezone(dt.timezone.utc)


def _record_path(state_root: Path, occurrence_id: str) -> Path:
    return state_root / "outbox" / f"{_occurrence_key(occurrence_id)}.json"


def _terminal_pair(state_root: Path, occurrence_id: str, release_sha: object) -> dict[str, Any]:
    path = state_root / "events.jsonl"
    try:
        raw = _read_private(path, max_bytes=MAX_EVENT_BYTES)
    except Exception:
        raise ReconcileUnknown("runtime_events_unreadable") from None
    try:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReconcileUnknown("runtime_events_invalid") from None
    run_id = occurrence_id[len(OWNER_ID) + 1 :]
    matches = [
        row for row in rows
        if isinstance(row, dict)
        and row.get("occurrence_id") == occurrence_id
        and row.get("loop_id") == OWNER_ID
        and row.get("owner_id") == OWNER_ID
        and row.get("job_id") == OWNER_ID
        and row.get("run_id") == run_id
    ]
    starts = [
        row for row in matches
        if row.get("phase") == "execute"
        and row.get("status") == "running"
        and row.get("effect_status") == "started"
        and row.get("effect_class") == "message"
    ]
    terminals = [
        row for row in matches
        if row.get("phase") == "report"
        and row.get("effect_class") == "message"
        and row.get("status") in {"pass", "fail", "deferred"}
    ]
    if len(starts) != 1 or len(terminals) != 1:
        raise ReconcileUnknown("runtime_event_pair_missing")
    start, terminal = starts[0], terminals[0]
    if _parse_time(start.get("timestamp")) > _parse_time(terminal.get("timestamp")):
        raise ReconcileUnknown("runtime_event_order_invalid")
    if start.get("release_sha") != terminal.get("release_sha"):
        raise ReconcileUnknown("runtime_event_release_mismatch")
    if isinstance(release_sha, str) and release_sha and release_sha != terminal.get("release_sha"):
        raise ReconcileUnknown("outbox_release_mismatch")
    return {
        "run_id": run_id,
        "start_event_id": start.get("event_id"),
        "terminal_event_id": terminal.get("event_id"),
        "terminal_status": terminal.get("status"),
        "terminal_exit_code": terminal.get("exit_code"),
        "terminal_effect_status": terminal.get("effect_status"),
        "release_sha": terminal.get("release_sha"),
    }


def _admission_state(occurrence_id: str) -> str:
    database = admission_state_root() / "admission-v2.sqlite3"
    if not database.is_file() or database.is_symlink():
        raise ReconcileUnknown("admission_database_missing")
    try:
        uri = f"{database.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT owner_id,state,effect_unknown FROM occurrences WHERE occurrence_id=?",
                (occurrence_id,),
            ).fetchone()
    except sqlite3.Error:
        raise ReconcileUnknown("admission_read_failed") from None
    if row is None or row["owner_id"] != OWNER_ID:
        raise ReconcileUnknown("occurrence_missing")
    if row["effect_unknown"] != 1 or row["state"] not in {"claimed", "released"}:
        raise ReconcileUnknown("occurrence_not_effect_unknown")
    return str(row["state"])


def _run_tg_user(*arguments: str) -> dict[str, Any]:
    if not USER_PYTHON.is_file() or not USER_SCRIPT.is_file():
        raise ReconcileUnknown("telegram_user_session_tool_unavailable")
    try:
        completed = subprocess.run(
            [str(USER_PYTHON), str(USER_SCRIPT), *arguments],
            text=True,
            capture_output=True,
            timeout=30,
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


def _official_telegram_readback(record: Mapping[str, Any]) -> dict[str, Any]:
    body = record.get("report_body")
    created = record.get("dispatch_started_at")
    if not isinstance(body, str) or not body or not isinstance(created, str):
        raise ReconcileUnknown("telegram_outbox_missing")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != record.get("report_sha256"):
        raise ReconcileUnknown("telegram_outbox_body_hash_mismatch")
    started = _parse_time(created)
    try:
        bot = TelegramClient.from_env()
        receipt = record.get("telegram_receipt")
        receipt_chat = receipt.get("chat_id") if isinstance(receipt, dict) else None
        chat_id = str(receipt_chat or bot.chat_id)
        if receipt_chat is not None and chat_id != str(bot.chat_id):
            raise ReconcileUnknown("telegram_receipt_chat_mismatch")
        bot_id = str(bot.get_me().get("bot_id"))
    except ReconcileUnknown:
        raise
    except Exception:
        raise ReconcileUnknown("telegram_bot_identity_read_failed") from None
    if not chat_id or not bot_id or bot_id == "None":
        raise ReconcileUnknown("telegram_bot_identity_invalid")

    dialogs = _run_tg_user("dialogs", "200").get("dialogs")
    if not isinstance(dialogs, list) or not any(str(row.get("id")) == chat_id for row in dialogs if isinstance(row, dict)):
        raise ReconcileUnknown("telegram_chat_not_in_user_dialogs")
    history = _run_tg_user("read", chat_id, "500").get("messages")
    if not isinstance(history, list):
        raise ReconcileUnknown("telegram_history_shape_invalid")
    chunks = _split_text(body)
    receipt = record.get("telegram_receipt")
    known_ids = receipt.get("message_ids") if isinstance(receipt, dict) else None
    if known_ids is not None and (
        not isinstance(known_ids, list)
        or len(known_ids) != len(chunks)
        or any(type(value) is not int or value <= 0 for value in known_ids)
    ):
        raise ReconcileUnknown("telegram_receipt_ids_invalid")
    if known_ids is not None and str(record.get("provider_receipt_id")) != str(known_ids[0]):
        raise ReconcileUnknown("telegram_primary_receipt_mismatch")

    messages: list[dict[str, Any]] = []
    used: set[str] = set()
    for index, chunk in enumerate(chunks):
        prefix = chunk[:500]
        if known_ids is not None:
            candidates = [
                row for row in history
                if isinstance(row, dict) and str(row.get("id")) == str(known_ids[index])
            ]
        else:
            candidates = [
                row for row in history
                if isinstance(row, dict)
                and isinstance(row.get("text"), str)
                and row["text"] == prefix
                and str(row.get("sender_id")) == bot_id
                and row.get("out") is False
                and abs((_parse_time(row.get("date")) - started).total_seconds()) <= READBACK_WINDOW_SECONDS
            ]
        if len(candidates) != 1:
            raise ReconcileUnknown("telegram_message_not_unique_in_history")
        message = candidates[0]
        message_id = message.get("id")
        if type(message_id) is not int or message_id <= 0 or str(message_id) in used:
            raise ReconcileUnknown("telegram_message_id_invalid")
        if str(message.get("sender_id")) != bot_id or message.get("out") is not False:
            raise ReconcileUnknown("telegram_message_sender_mismatch")
        if message.get("text") != prefix:
            raise ReconcileUnknown("telegram_message_body_prefix_mismatch")
        message_time = _parse_time(message.get("date"))
        if abs((message_time - started).total_seconds()) > READBACK_WINDOW_SECONDS:
            raise ReconcileUnknown("telegram_message_time_mismatch")
        used.add(str(message_id))
        messages.append({"message_id": message_id, "date": message["date"]})

    if known_ids is not None and [item["message_id"] for item in messages] != known_ids:
        raise ReconcileUnknown("telegram_provider_receipt_mismatch")
    return {
        "verified": True,
        "provider": "telegram",
        "chat_id": chat_id,
        "sender_id": bot_id,
        "message_ids": [item["message_id"] for item in messages],
        "message_dates": [item["date"] for item in messages],
        "expected_body_sha256": record["report_sha256"],
        "verified_body_prefix_sha256": hashlib.sha256(chunks[0][:500].encode("utf-8")).hexdigest(),
        "provider_receipt_id": str(messages[0]["message_id"]),
    }


def _merge_delivered_signals(state_root: Path, record: Mapping[str, Any]) -> None:
    rows = record.get("new_signal_rows")
    if not isinstance(rows, list):
        raise ReconcileUnknown("delivered_signal_rows_missing")
    current = _read_signals(state_root / "signals.csv") or []
    additions = []
    for row in rows:
        if not isinstance(row, dict) or any(field not in row for field in CSV_FIELDS):
            raise ReconcileUnknown("delivered_signal_row_invalid")
        additions.append({field: row[field] for field in CSV_FIELDS})
    product_order = {row["product_id"]: index for index, row in enumerate(additions)}
    _write_signals(state_root / "signals.csv", current + additions, product_order)


def reconcile_occurrence(
    state_root: Path,
    occurrence_id: str,
    *,
    resolve: bool = False,
) -> dict[str, Any]:
    occurrence_id = _occurrence_id(occurrence_id)
    state_root = _assert_outside_repo(Path(state_root))
    root_info = state_root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid() or stat.S_IMODE(root_info.st_mode) != 0o700:
        raise ReconcileUnknown("private_state_root_invalid")
    record = _read_json(_record_path(state_root, occurrence_id))
    if record.get("owner_id") != OWNER_ID or record.get("occurrence_id") != occurrence_id:
        raise ReconcileUnknown("outbox_occurrence_mismatch")
    outbox_dir = state_root / "outbox"
    outbox_info = outbox_dir.lstat()
    if not stat.S_ISDIR(outbox_info.st_mode) or outbox_info.st_uid != os.getuid() or stat.S_IMODE(outbox_info.st_mode) != 0o700:
        raise ReconcileUnknown("outbox_directory_not_private")
    dispatch_started = record.get("telegram_dispatch_started")
    if type(dispatch_started) is not bool:
        raise ReconcileUnknown("outbox_dispatch_marker_invalid")
    if not dispatch_started and record.get("status") in {"send_started", "send_unknown", "delivered", "reconciled_delivered"}:
        raise ReconcileUnknown("outbox_dispatch_state_mismatch")
    if dispatch_started and record.get("status") in {"started", "agent_running", "agent_failed", "baseline_established", "no_new_signals", "balance_floor", "telegram_preflight_failed"}:
        raise ReconcileUnknown("outbox_dispatch_state_mismatch")
    terminal = _terminal_pair(state_root, occurrence_id, record.get("release_sha"))
    admission_state = _admission_state(occurrence_id)
    proof_ref = f"treg-lead-signals://occurrence/{_occurrence_key(occurrence_id)}"

    if record.get("billing_status") in {"pending", "incomplete"}:
        try:
            evidence_dir = state_root / "evidence" / _occurrence_key(occurrence_id)
            events = _mcp_events(evidence_dir)
            trace_receipts = _trace_call_receipts([event for event in events if event.get("tool") == "call"])
            partial, partial_total = _capture_partial(trace_receipts)
            record.update({
                "treg_calls": partial,
                "partial_charged_micro": partial_total,
                "billing_status": "incomplete",
                "billing_readback": "captured_codex_mcp_events",
            })
        except Exception:
            record.update({"billing_status": "incomplete", "billing_readback": "trace_unavailable"})
        _atomic_json(_record_path(state_root, occurrence_id), record)

    if not dispatch_started:
        if record.get("status") == "baseline_established" and record.get("signal_rows"):
            current = _read_signals(state_root / "signals.csv") or []
            product_order = {row.get("product_id"): index for index, row in enumerate(record["signal_rows"])}
            _write_signals(state_root / "signals.csv", current + record["signal_rows"], product_order)
        proof = {
            "owner_id": OWNER_ID,
            "occurrence_id": occurrence_id,
            "verified": True,
            "proof_type": "pre_effect",
            "evidence_ref": proof_ref + "/no-telegram-dispatch",
        }
        resolved = False
        if resolve:
            resolved = resolve_pre_effect_occurrence(
                OWNER_ID,
                occurrence_id,
                pre_effect_readback=lambda: proof,
                expected_state=admission_state,
            )
        record.update({
            "status": "reconciled_no_telegram_effect",
            "effect": "not_applicable",
            "readback": "durable_no_dispatch_marker",
            "reconciled_at": _timestamp(),
        })
        _atomic_json(_record_path(state_root, occurrence_id), record)
        return {"status": "resolved" if resolved else "proof_ready", "occurrence_id": occurrence_id, "effect": "not_applicable", **terminal}

    readback = _official_telegram_readback(record)
    _merge_delivered_signals(state_root, record)
    record.update({
        "status": "reconciled_delivered",
        "effect": "verified",
        "readback": "telegram_user_history",
        "telegram_history_readback": readback,
        "provider_receipt_id": readback["provider_receipt_id"],
        "reconciled_at": _timestamp(),
    })
    receipt_path = state_root / "reconciliation" / f"{_occurrence_key(occurrence_id)}.json"
    _atomic_json(receipt_path, {
        "schema_version": 1,
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "terminal_event_id": terminal.get("terminal_event_id"),
        "release_sha": terminal.get("release_sha"),
        "readback": readback,
        "observed_at": _timestamp(),
    })
    _atomic_json(_record_path(state_root, occurrence_id), record)
    proof = {
        "owner_id": OWNER_ID,
        "occurrence_id": occurrence_id,
        "verified": True,
        "provider_receipt_id": readback["provider_receipt_id"],
        "provider": "telegram",
        "official_readback_ref": f"telegram-history://messages/{readback['provider_receipt_id']}",
    }
    resolved = False
    if resolve:
        resolved = resolve_unknown_occurrence(
            OWNER_ID,
            occurrence_id,
            official_readback=lambda: proof,
            expected_state=admission_state,
        )
    return {
        "status": "resolved" if resolved else "proof_ready",
        "occurrence_id": occurrence_id,
        "provider_receipt_id": readback["provider_receipt_id"],
        "message_count": len(readback["message_ids"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(os.environ.get("LIFE_MANAGER_STATE_ROOT", os.path.expanduser("~/.local/state/life-manager/marketing-treg-lead-signals")))
    parser.add_argument("--state-root", type=Path, default=default_root)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reconcile_occurrence(args.state_root.expanduser(), args.occurrence, resolve=args.resolve)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except ReconcileUnknown as error:
        print(json.dumps({"status": "unknown", "occurrence_id": args.occurrence, "reason": error.code}, sort_keys=True))
        return 0
    except MonitorError as error:
        print(json.dumps({"status": "unknown", "occurrence_id": args.occurrence, "reason": error.code}, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "unknown", "occurrence_id": args.occurrence, "reason": type(error).__name__}, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
