from pathlib import Path

import pytest

from skills._shared.telegram import (
    TelegramClient,
    TelegramDeliveryUnknown,
    TelegramError,
    _split_text,
    load_config,
)


def test_alert_chat_id_is_the_portable_default(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token\nTELEGRAM_ALERT_CHAT_ID=12345\n",
        encoding="utf-8",
    )

    assert load_config(environ={}, env_file=env_file) == ("test-token", "12345")


def test_explicit_chat_id_wins_over_alert_chat_id(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token\nTELEGRAM_CHAT_ID=primary\n"
        "TELEGRAM_ALERT_CHAT_ID=fallback\n",
        encoding="utf-8",
    )

    assert load_config(environ={}, env_file=env_file) == ("test-token", "primary")


def test_split_text_preserves_the_delimiter_used_as_the_chunk_boundary() -> None:
    for delimiter in ("\n", " "):
        message = "a" * 3844 + delimiter + "b" * 3790

        chunks = _split_text(message)

        assert len(chunks) == 2
        assert all(len(chunk) <= 4000 for chunk in chunks)
        assert "".join(chunks) == message


def test_partial_multichunk_send_is_delivery_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TelegramClient(token="test-token", chat_id="12345")
    attempted_chunks = []

    def send(method: str, fields: dict[str, str], **_kwargs):
        assert method == "sendMessage"
        attempted_chunks.append(fields["text"])
        if len(attempted_chunks) == 1:
            return {"message_id": 101, "chat": {"id": 12345}, "date": 1}
        raise TelegramError("Too Many Requests", error_code=429, retry_after=3)

    monkeypatch.setattr(client, "_request", send)

    with pytest.raises(TelegramDeliveryUnknown) as error:
        client.send_text("a" * 4001)

    assert len(attempted_chunks) == 2
    assert len(attempted_chunks[0]) == 4000
    assert attempted_chunks[1] == "a"
    assert error.value.error_code == 429
