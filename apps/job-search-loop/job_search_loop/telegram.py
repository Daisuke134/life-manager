from __future__ import annotations

import hashlib
import json
import os
import shlex
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib import request

from .outbox import Outbox


TelegramRequester = Callable[..., dict[str, Any]]


def _telegram_config_value(config_name: str, supplied: str | None) -> str:
    if supplied:
        return supplied
    if os.environ.get(config_name):
        return str(os.environ[config_name])
    env_file = Path(
        os.environ.get(
            "JOB_SEARCH_TELEGRAM_ENV",
            str(Path.home() / ".config" / "anicca" / "job-search" / "telegram.env"),
        )
    ).expanduser()
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parsed_name, separator, encoded = line.removeprefix("export ").partition("=")
        if separator and parsed_name.strip() == config_name:
            values = shlex.split(encoded, comments=True, posix=True)
            if len(values) == 1 and values[0]:
                return values[0]
    raise RuntimeError(f"{config_name} is unavailable")


def _telegram_token(token: str | None) -> str:
    return _telegram_config_value("TELEGRAM_BOT_TOKEN", token)


def _telegram_target(target: str | None) -> str:
    return _telegram_config_value("JOB_SEARCH_TELEGRAM_CHAT_ID", target)


def is_configured() -> bool:
    try:
        _telegram_token(None)
        _telegram_target(None)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _telegram_request(
    *,
    method: str,
    token: str,
    fields: dict[str, str],
    document: Path | None = None,
) -> dict[str, Any]:
    base_url = os.environ.get(
        "TELEGRAM_BOT_API_BASE_URL", "https://api.telegram.org/bot"
    ).rstrip("/")
    url = f"{base_url}{token}/{method}"
    headers: dict[str, str]
    if document is None:
        body = json.dumps(fields, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
    else:
        boundary = f"anicca-{uuid.uuid4().hex}"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )
        safe_name = "".join(
            character
            for character in document.name
            if character.isalnum() or character in "._-"
        ) or "document"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    'Content-Disposition: form-data; name="document"; '
                    f'filename="{safe_name}"\r\n'
                ).encode(),
                b"Content-Type: application/octet-stream\r\n\r\n",
                document.read_bytes(),
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        body = b"".join(chunks)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    with request.urlopen(request.Request(url, data=body, headers=headers), timeout=60) as response:
        result = json.loads(response.read())
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("Telegram Bot API rejected the request")
    return result


def _message_id(result: dict[str, Any]) -> str:
    payload = result.get("result")
    message_id = payload.get("message_id") if isinstance(payload, dict) else None
    if message_id is None:
        raise RuntimeError("Telegram ACK has no message ID")
    return str(message_id)


def send_daily_report(
    *,
    database: Path,
    japan_day: str,
    message: str,
    material_digest: str | None = None,
    target: str | None = None,
    token: str | None = None,
    requester: TelegramRequester = _telegram_request,
) -> dict[str, str | None]:
    base_key = f"job-search-daily:{japan_day}"
    if material_digest is not None:
        if len(material_digest) != 64 or any(
            character not in "0123456789abcdef" for character in material_digest
        ):
            raise ValueError("daily material digest is invalid")
        base_key = f"{base_key}:state:{material_digest[:16]}"
    outbox = Outbox(database)
    try:
        existing = outbox.connection.execute(
            "SELECT payload FROM outbox WHERE event_key=?",
            (base_key,),
        ).fetchone()
    finally:
        outbox.close()

    if existing is None or str(existing[0]) == message:
        event_key = base_key
    else:
        digest = hashlib.sha256(message.encode("utf-8")).hexdigest()[:16]
        event_key = f"{base_key}:correction:{digest}"

    result = send_once(
        database=database,
        event_key=event_key,
        message=message,
        target=target,
        token=token,
        requester=requester,
    )
    return {**result, "event_key": event_key}


def send_once(
    *,
    database: Path,
    event_key: str,
    message: str,
    target: str | None = None,
    token: str | None = None,
    requester: TelegramRequester = _telegram_request,
) -> dict[str, str | None]:
    outbox = Outbox(database)
    try:
        outbox.enqueue(event_key, message)
        existing = outbox.status(event_key)
        if existing["status"] in {"sent", "send_started"}:
            return existing
        fence = outbox.claim(event_key)
        outbox.mark_send_started(event_key, fence)
        result = requester(
            method="sendMessage",
            token=_telegram_token(token),
            fields={"chat_id": _telegram_target(target), "text": outbox.payload(event_key)},
        )
        outbox.mark_sent(event_key, fence, _message_id(result))
        return outbox.status(event_key)
    finally:
        outbox.close()


def send_document_once(
    *,
    database: Path,
    event_key: str,
    message: str,
    document: Path,
    media_root: Path,
    target: str | None = None,
    token: str | None = None,
    requester: TelegramRequester = _telegram_request,
) -> dict[str, str | None]:
    outbox = Outbox(database)
    try:
        outbox.enqueue(event_key, message)
        existing = outbox.status(event_key)
        if existing["status"] in {"sent", "send_started"}:
            return existing

        source = Path(document).expanduser().resolve()
        if not source.is_file():
            raise ValueError(f"Telegram document is not a file: {source}")
        fence = outbox.claim(event_key)
        outbox.mark_send_started(event_key, fence)
        result = requester(
            method="sendDocument",
            token=_telegram_token(token),
            fields={"chat_id": _telegram_target(target), "caption": outbox.payload(event_key)},
            document=source,
        )
        outbox.mark_sent(event_key, fence, _message_id(result))
        return outbox.status(event_key)
    finally:
        outbox.close()
