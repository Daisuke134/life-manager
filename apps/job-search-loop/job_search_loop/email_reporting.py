from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from .outbox import DeliveryUncertain, Outbox


GogRunner = Callable[..., subprocess.CompletedProcess[str]]


def _gmail_message_id(stdout: str) -> str:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        raise DeliveryUncertain("Gmail send returned an unreadable receipt") from None
    if not isinstance(value, dict):
        raise DeliveryUncertain("Gmail send returned an invalid receipt")
    message = value.get("message")
    message_id = value.get("id") or value.get("messageId")
    if not message_id and isinstance(message, dict):
        message_id = message.get("id") or message.get("messageId")
    if not isinstance(message_id, str) or not message_id.strip():
        raise DeliveryUncertain("Gmail send receipt has no message ID")
    return message_id.strip()


def send_email_once(
    *,
    database: Path,
    event_key: str,
    recipient: str,
    subject: str,
    message: str,
    account: str | None = None,
    executable: str | None = None,
    runner: GogRunner = subprocess.run,
    timeout_seconds: int = 60,
) -> dict[str, str | None]:
    recipient = recipient.strip()
    account = (account or recipient).strip()
    if not event_key.strip() or not recipient or "@" not in recipient or any(
        character.isspace() for character in recipient
    ):
        raise ValueError("Gmail recipient or event key is invalid")
    if not account or "@" not in account or any(character.isspace() for character in account):
        raise ValueError("Gmail account is invalid")
    if not subject.strip() or "\r" in subject or "\n" in subject:
        raise ValueError("Gmail subject is invalid")
    if not message.strip():
        raise ValueError("Gmail message is empty")

    binary = executable or os.environ.get("JOB_SEARCH_GOG") or shutil.which("gog")
    if not binary:
        raise FileNotFoundError("gog CLI is unavailable")

    payload = json.dumps(
        {"recipient": recipient, "subject": subject, "message": message},
        ensure_ascii=False,
        sort_keys=True,
    )
    outbox = Outbox(database, channel="email")
    try:
        outbox.enqueue(event_key, payload)
        existing = outbox.status(event_key)
        if existing["status"] in {"sent", "send_started"}:
            return {**existing, "event_key": event_key}
        if outbox.payload(event_key) != payload:
            raise DeliveryUncertain("Gmail outbox event payload changed")
        fence = outbox.claim(event_key)
        outbox.mark_send_started(event_key, fence)
        argv = [
            binary,
            "gmail",
            "send",
            "--json",
            "--no-input",
            "--account",
            account,
            "--to",
            recipient,
            "--subject",
            subject,
            "--body-file",
            "-",
        ]
        try:
            result = runner(
                argv,
                input=message,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise DeliveryUncertain("Gmail send outcome is unknown") from None
        if result.returncode != 0:
            raise DeliveryUncertain("Gmail send outcome is unknown")
        message_id = _gmail_message_id(str(result.stdout or ""))
        outbox.mark_sent(event_key, fence, message_id)
        return {**outbox.status(event_key), "event_key": event_key}
    finally:
        outbox.close()
