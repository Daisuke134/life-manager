from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path


class DeliveryUncertain(RuntimeError):
    pass


class Outbox:
    _CHANNELS = {
        "telegram": ("outbox", "telegram_message_id"),
        "email": ("email_outbox", "email_message_id"),
    }

    def __init__(self, path: Path, *, channel: str = "telegram"):
        try:
            self._table, self._message_id_column = self._CHANNELS[channel]
        except KeyError:
            raise ValueError("unsupported outbox channel") from None
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
              event_key TEXT PRIMARY KEY,
              payload TEXT NOT NULL,
              status TEXT NOT NULL,
              fence TEXT,
              {self._message_id_column} TEXT
            )
            """
        )
        os.chmod(path, 0o600)

    def close(self) -> None:
        self.connection.close()

    def enqueue(self, event_key: str, payload: str) -> str:
        self.connection.execute(
            f"INSERT OR IGNORE INTO {self._table}(event_key,payload,status) VALUES(?,?,'pending')",
            (event_key, payload),
        )
        return event_key

    def claim(self, event_key: str) -> str:
        row = self.connection.execute(
            f"SELECT status FROM {self._table} WHERE event_key=?", (event_key,)
        ).fetchone()
        if row is None:
            raise KeyError(event_key)
        if row[0] == "send_started":
            raise DeliveryUncertain("delivery outcome is unknown; blind retry forbidden")
        if row[0] != "pending":
            raise DeliveryUncertain(f"outbox is not claimable: {row[0]}")
        fence = uuid.uuid4().hex
        self.connection.execute(
            f"UPDATE {self._table} SET status='claimed',fence=? WHERE event_key=? AND status='pending'",
            (fence, event_key),
        )
        return fence

    def mark_send_started(self, event_key: str, fence: str) -> None:
        changed = self.connection.execute(
            f"""
            UPDATE {self._table} SET status='send_started'
            WHERE event_key=? AND fence=? AND status='claimed'
            """,
            (event_key, fence),
        ).rowcount
        if changed != 1:
            raise DeliveryUncertain("outbox fence mismatch")

    def mark_sent(self, event_key: str, fence: str, message_id: str) -> None:
        changed = self.connection.execute(
            f"""
            UPDATE {self._table} SET status='sent',{self._message_id_column}=?
            WHERE event_key=? AND fence=? AND status='send_started'
            """,
            (message_id, event_key, fence),
        ).rowcount
        if changed != 1:
            raise DeliveryUncertain("outbox fence mismatch")

    def payload(self, event_key: str) -> str:
        row = self.connection.execute(
            f"SELECT payload FROM {self._table} WHERE event_key=?", (event_key,)
        ).fetchone()
        if row is None:
            raise KeyError(event_key)
        return str(row[0])

    def status(self, event_key: str) -> dict[str, str | None]:
        row = self.connection.execute(
            f"SELECT status,{self._message_id_column} FROM {self._table} WHERE event_key=?",
            (event_key,),
        ).fetchone()
        if row is None:
            raise KeyError(event_key)
        return {"status": str(row[0]), "message_id": row[1]}
