from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from .telegram import is_configured as telegram_is_configured, send_once


class ConnectorPreflightError(RuntimeError):
    pass


def _optional_telegram_sender(sender: Callable[..., dict[str, str | None]] | None):
    if sender is None:
        return lambda **_: {"status": "not_configured", "message_id": None}

    def send(**kwargs):
        try:
            result = sender(**kwargs)
        except Exception as error:
            return {"status": "unavailable", "message_id": None, "error_class": type(error).__name__}
        if result.get("status") != "sent" or not result.get("message_id"):
            return {"status": "unavailable", "message_id": None}
        return result

    return send


def _application_email(profile_path: Path) -> str:
    value = json.loads(profile_path.read_text(encoding="utf-8"))
    email = (value.get("candidate") or {}).get("application_email")
    if (
        not isinstance(email, str)
        or "@" not in email
        or any(character.isspace() for character in email)
    ):
        raise ConnectorPreflightError("candidate application email is unavailable")
    return email


def _gmail_readback(
    email: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    completed = runner(
        [
            "gog",
            "--account",
            email,
            "gmail",
            "messages",
            "search",
            "in:anywhere newer_than:365d",
            "--max=1",
            "--json",
            "--no-input",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise ConnectorPreflightError("Gmail readback failed")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ConnectorPreflightError("Gmail readback was not JSON") from error
    if not isinstance(value, (dict, list)):
        raise ConnectorPreflightError("Gmail readback shape is invalid")
    return {"status": "ready", "account_bound": True}


def _write_private(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_connectors(
    *,
    profile_path: Path,
    outbox_path: Path,
    output_path: Path,
    gmail_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    telegram_sender: Callable[..., dict[str, str | None]] | None = None,
) -> dict[str, Any]:
    email = _application_email(profile_path)
    gmail = _gmail_readback(email, runner=gmail_runner)
    telegram_sender = _optional_telegram_sender(telegram_sender)
    telegram = telegram_sender(
        database=outbox_path,
        event_key="job-search-oss-setup:v1",
        message=(
            "Codex::: [Job Hunter][セットアップ]\n"
            "✅ Gmail接続を確認しました。Telegramは任意です。\n\n"
            "次に自動で行うこと\n"
            "受領を確認したWorkday応募をメールで報告し、日次briefingを届けます。"
        ),
    )
    message_id = telegram.get("message_id")
    telegram_status = (
        {"status": "ready", "message_id": str(message_id)}
        if telegram.get("status") == "sent" and message_id
        else {"status": str(telegram.get("status") or "unavailable")}
    )
    receipt = {
        "version": 1,
        "status": "ready",
        "gmail": gmail,
        "telegram": telegram_status,
    }
    _write_private(output_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--outbox", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = verify_connectors(
            profile_path=args.profile,
            outbox_path=args.outbox,
            output_path=args.output,
            telegram_sender=send_once if telegram_is_configured() else None,
        )
    except (ConnectorPreflightError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
