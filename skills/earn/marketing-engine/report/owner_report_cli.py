#!/usr/bin/env python3
"""CLI sweeps for canonical Japanese owner reports."""

from __future__ import annotations

import argparse
import datetime as dt
import os
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


TELEGRAM_TARGET = os.environ.get("MKT_TELEGRAM_TARGET")
DEFAULT_STATE_ROOT = REPO_ROOT / "skills" / "earn" / "marketing-engine" / "state"
CLOUD_BOT_ENV_FILE = pathlib.Path.home() / ".config" / "env" / "global.env"


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


def _cloud_bot_token() -> str:
    token = os.environ.get("LM_TELEGRAM_BOT_TOKEN")
    if token:
        return token
    if CLOUD_BOT_ENV_FILE.is_file():
        for raw in CLOUD_BOT_ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, value = line.partition("=")
            if not separator or key.strip() != "LM_TELEGRAM_BOT_TOKEN":
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if value:
                return value
    raise TelegramError("Cloud Life Manager Telegram token is unavailable")


def _send_text(text: str) -> dict:
    environ = dict(os.environ)
    environ["TELEGRAM_BOT_TOKEN"] = _cloud_bot_token()
    client = TelegramClient.from_env(environ=environ)
    return client.send_text(text, chat_id=TELEGRAM_TARGET)


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
        store = owner_report.OwnerReportStore(report_path, delivery_path)
        failed = False
        for event in events:
            text = owner_report.render_japanese(event)
            print(text)
            if args.no_send:
                store.record(event)
                continue
            receipt = owner_report.deliver(event, store, _send_text)
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
