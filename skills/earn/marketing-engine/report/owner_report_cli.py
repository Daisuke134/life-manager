#!/usr/bin/env python3
"""CLI sweeps for canonical Japanese owner reports."""

from __future__ import annotations

import argparse
import datetime as dt
from functools import partial
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]

try:
    from skills._shared.telegram import TelegramClient, TelegramError
except ModuleNotFoundError:  # direct file loading in the transport contract
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from skills._shared.telegram import TelegramClient, TelegramError

import owner_report


DEFAULT_STATE_ROOT = REPO_ROOT / "skills" / "earn" / "marketing-engine" / "state"
CREDENTIALS_FILE = pathlib.Path.home() / ".local" / "share" / "anicca" / "credentials.json"


def _parse_as_of(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--as-of must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--as-of must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _local_telegram_credentials() -> tuple[str, str]:
    try:
        data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TelegramError("Local Life Manager Telegram credential is unavailable") from exc
    credentials = data.get("credentials") if isinstance(data, dict) else None
    matches = [
        row for row in credentials
        if isinstance(row, dict) and row.get("service") == "telegram-life-manager"
    ] if isinstance(credentials, list) else []
    if len(matches) != 1:
        raise TelegramError("Local Life Manager Telegram credential is unavailable")
    row = matches[0]
    token = row.get("bot_token")
    chat_id = row.get("chat_id")
    if not isinstance(token, str) or not token.strip() or chat_id is None or not str(chat_id).strip():
        raise TelegramError("Local Life Manager Telegram credential is incomplete")
    return token, str(chat_id)


def _send_text(text: str, credentials: tuple[str, str] | None = None) -> dict:
    token, chat_id = credentials or _local_telegram_credentials()
    client = TelegramClient.from_env(
        environ={"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat_id},
    )
    return client.send_text(text, chat_id=chat_id)


def send(message: str) -> bool:
    """Compatibility helper used by the direct Telegram transport contract."""

    try:
        receipt = _send_text(message)
        message_ids = receipt.get("message_ids") if isinstance(receipt, dict) else None
        if not isinstance(message_ids, list) or not any(item is not None for item in message_ids):
            raise TelegramError("Telegram receipt did not contain message_ids")
    except TelegramError as exc:
        print(f"send failed: {exc}", file=sys.stderr)
        return False
    print(f"telegram_message_ids={receipt['message_ids']}")
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    sweep = subparsers.add_parser("sweep")
    sweep.add_argument("--kind", choices=owner_report.KINDS, required=True)
    sweep.add_argument("--product-id", choices=owner_report.PRODUCTS)
    sweep.add_argument("--state-root", type=pathlib.Path, default=DEFAULT_STATE_ROOT)
    sweep.add_argument("--as-of", type=str)
    sweep.add_argument("--no-send", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "sweep":
        return 2
    try:
        as_of = _parse_as_of(args.as_of)
        report_path = pathlib.Path(args.state_root) / "owner-reports.jsonl"
        delivery_path = pathlib.Path(args.state_root) / "owner-report-deliveries.jsonl"
        latest_deliveries = {}
        if not args.no_send:
            for row in owner_report.load_jsonl(delivery_path):
                message_key = row.get("message_key")
                if isinstance(message_key, str):
                    latest_deliveries[message_key] = row
        delivered_keys = {
            message_key
            for message_key, row in latest_deliveries.items()
            if row.get("status") == "delivered"
        }
        events = owner_report.build_events(
            args.state_root,
            args.kind,
            product_id=args.product_id,
            as_of=as_of,
            skip_message_keys=delivered_keys,
        )
        credentials = _local_telegram_credentials() if not args.no_send and events else None
        send_text = partial(_send_text, credentials=credentials) if credentials else _send_text
        store = owner_report.OwnerReportStore(report_path, delivery_path)
        failed = False
        for event in events:
            text = owner_report.render_japanese(event)
            print(text)
            if args.no_send:
                store.record(event)
                continue
            receipt = owner_report.deliver(event, store, send_text)
            status = receipt.get("status") if isinstance(receipt, dict) else None
            if status != "delivered":
                failed = True
            elif receipt.get("message_ids"):
                print(f"telegram_message_ids={receipt['message_ids']}")
        return 1 if failed else 0
    except (owner_report.OwnerReportError, OSError, TelegramError, argparse.ArgumentTypeError) as exc:
        print(f"owner report failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
