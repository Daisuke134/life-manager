"""Durable Ampersand session intent, event idempotency, and single-writer fences.

Creation is NOT idempotent at the Ampersand API. For a lost response this
journal quarantines UNKNOWN and requires independent pagination/reconciliation,
never creating a second session automatically. This module never calls a provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3


_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_SESSION_ID = re.compile(r"sess_[A-Za-z0-9_-]{4,128}\Z")
_EVENT_ID = re.compile(r"[A-Za-z0-9_-]{4,128}\Z")
_OWNER_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class SessionConflict(RuntimeError):
    """Conflicting or uncertain remote side effect; do not retry."""


@dataclass(frozen=True)
class Intent:
    request_id: str
    body_hash: str
    status: str
    session_id: str | None = None


def _check(value: str, pattern: re.Pattern[str], description: str) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        raise ValueError("invalid " + description)
    return value


class SessionJournal:
    """Single SQLite owner store: keep it on a durable volume, NOT ephemeral CI.

    One writer at a time; no time-based lease expiry that can enable duplicate
    sends after a stalled worker. Operators must reconcile/release explicitly.
    """
    def __init__(self, path: str | Path):
        self.path = str(Path(path))
        if self.path == ":memory:":
            raise ValueError("persistent path required for remote effects")
        with sqlite3.connect(self.path, timeout=15) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS amp_sessions (
                request_id TEXT PRIMARY KEY,
                body_hash TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('RESERVED','UNKNOWN','BOUND')),
                session_id TEXT UNIQUE,
                writer_id TEXT,
                created_at TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS amp_events (
                session_id TEXT NOT NULL,
                event_key TEXT NOT NULL,
                body_hash TEXT NOT NULL,
                PRIMARY KEY(session_id,event_key),
                FOREIGN KEY(session_id) REFERENCES amp_sessions(session_id)
            )""")

    def _txn(self, callback):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            result = callback(db)
            db.execute("COMMIT")
            return result
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _as_intent(row) -> Intent:
        if row is None:
            raise SessionConflict("unknown request intent")
        return Intent(row[0], row[1], row[2], row[3])

    @staticmethod
    def _get(db, request_id: str):
        return db.execute(
            "SELECT request_id,body_hash,status,session_id FROM amp_sessions WHERE request_id=?",
            (request_id,),
        ).fetchone()

    def get(self, request_id: str) -> Intent:
        """Read-only status; never authorize retry from returned data."""
        _check(request_id, _REQUEST_ID, "request ID")
        with sqlite3.connect(self.path, timeout=15) as db:
            return self._as_intent(self._get(db, request_id))

    def reserve_for_send(self, request_id: str) -> Intent:
        """One atomic transition BEFORE the first possible HTTP side effect.

        If a process crashes after marking UNKNOWN but before the provider call,
        the next process must reconcile it rather than risk two creations.
        """
        _check(request_id, _REQUEST_ID, "request ID")

        def action(db):
            row = self._get(db, request_id)
            if row is None or row[2] != "RESERVED":
                raise SessionConflict("creation already attempted or not reserved")
            db.execute("UPDATE amp_sessions SET status='UNKNOWN' WHERE request_id=?",
                       (request_id,))
            return self._as_intent(self._get(db, request_id))

        return self._txn(action)

    def begin(self, request_id: str, body_hash: str) -> Intent:
        _check(request_id, _REQUEST_ID, "request ID")
        _check(body_hash, _SHA, "canonical request body SHA-256")

        def action(db):
            row = self._get(db, request_id)
            if row:
                if row[1] != body_hash:
                    raise SessionConflict("request ID reused for changed body")
                return self._as_intent(row)
            db.execute(
                """INSERT INTO amp_sessions(request_id,body_hash,status,session_id,writer_id,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (request_id, body_hash, "RESERVED", None, None,
                 datetime.now(timezone.utc).isoformat()),
            )
            return self._as_intent(self._get(db, request_id))

        return self._txn(action)

    def mark_unknown(self, request_id: str) -> Intent:
        _check(request_id, _REQUEST_ID, "request ID")

        def action(db):
            row = self._get(db, request_id)
            if row is None:
                raise SessionConflict("request does not exist")
            if row[2] == "BOUND":
                return self._as_intent(row)
            db.execute("UPDATE amp_sessions SET status='UNKNOWN' WHERE request_id=?",
                       (request_id,))
            return self._as_intent(self._get(db, request_id))

        return self._txn(action)

    def bind(self, request_id: str, session_id: str) -> Intent:
        _check(request_id, _REQUEST_ID, "request ID")
        _check(session_id, _SESSION_ID, "provider session ID")

        def action(db):
            row = self._get(db, request_id)
            if row is None:
                raise SessionConflict("session was not reserved")
            if row[2] == "BOUND":
                if row[3] != session_id:
                    raise SessionConflict("attempt to rebind provider session")
                return self._as_intent(row)
            other = db.execute(
                "SELECT request_id FROM amp_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if other is not None and other[0] != request_id:
                raise SessionConflict("provider session already bound to another intent")
            db.execute(
                "UPDATE amp_sessions SET status='BOUND',session_id=? WHERE request_id=?",
                (session_id, request_id),
            )
            return self._as_intent(self._get(db, request_id))

        return self._txn(action)

    def reconcile(self, request_id: str, listed_sessions: list[dict]) -> Intent:
        """Caller MUST supply ALL provider pages, not just first response page."""
        _check(request_id, _REQUEST_ID, "request ID")
        if type(listed_sessions) is not list:
            raise ValueError("complete paginated sessions list required")
        matching = []
        for item in listed_sessions:
            if type(item) is not dict:
                raise ValueError("unexpected provider session item")
            meta = item.get("metadata")
            if type(meta) is dict and meta.get("manager_request_id") == request_id:
                matching.append(item.get("id"))
        if len(matching) > 1:
            raise SessionConflict("multiple matching external sessions: manual reconciliation")
        if matching:
            return self.bind(request_id, matching[0])
        return self.mark_unknown(request_id)

    def _require_bound(self, db, session_id: str):
        record = db.execute(
            "SELECT request_id,body_hash,status,session_id FROM amp_sessions WHERE session_id=? AND status='BOUND'",
            (session_id,),
        ).fetchone()
        if record is None:
            raise SessionConflict("session was never bound locally")
        return record

    def reserve_event(self, session_id: str, event_key: str, body_hash: str) -> bool:
        _check(session_id, _SESSION_ID, "provider session ID")
        _check(event_key, _EVENT_ID, "event idempotency key")
        _check(body_hash, _SHA, "event body SHA-256")

        def action(db):
            self._require_bound(db, session_id)
            old = db.execute(
                "SELECT body_hash FROM amp_events WHERE session_id=? AND event_key=?",
                (session_id, event_key),
            ).fetchone()
            if old is not None:
                if old[0] != body_hash:
                    raise SessionConflict("changed body for same idempotency key")
                return False
            db.execute(
                "INSERT INTO amp_events(session_id,event_key,body_hash) VALUES(?,?,?)",
                (session_id, event_key, body_hash),
            )
            return True

        return self._txn(action)

    def claim_writer(self, session_id: str, writer_id: str) -> None:
        _check(session_id, _SESSION_ID, "provider session ID")
        _check(writer_id, _OWNER_ID, "writer ID")

        def action(db):
            self._require_bound(db, session_id)
            row = db.execute(
                "SELECT writer_id FROM amp_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row[0] not in (None, writer_id):
                raise SessionConflict("one-writer fence: already claimed")
            db.execute("UPDATE amp_sessions SET writer_id=? WHERE session_id=?",
                       (writer_id, session_id))

        self._txn(action)

    def release_writer(self, session_id: str, writer_id: str) -> None:
        _check(session_id, _SESSION_ID, "provider session ID")
        _check(writer_id, _OWNER_ID, "writer ID")

        def action(db):
            self._require_bound(db, session_id)
            result = db.execute(
                "UPDATE amp_sessions SET writer_id=NULL WHERE session_id=? AND writer_id=?",
                (session_id, writer_id),
            )
            if result.rowcount != 1:
                raise SessionConflict("not the current session writer")

        self._txn(action)


def reconcile_session_pages(
    journal: SessionJournal, request_id: str, fetch_page,
    *, page_limit: int = 100, max_pages: int = 50,
) -> Intent:
    """Exhaustively scan session list by after cursor; never create effects.

    fetch_page(after, limit) must return provider JSON page with
    data:list, has_more:bool. Any malformed, truncated, looping or
    failed page raises SessionConflict, retaining UNKNOWN state. A complete
    absence is still UNKNOWN because provider list freshness does not prove
    no creation occurred after a request timeout.
    """
    _check(request_id, _REQUEST_ID, "request ID")
    if (type(journal) is not SessionJournal or not callable(fetch_page)
            or type(page_limit) is not int or not 1 <= page_limit <= 100
            or type(max_pages) is not int or not 1 <= max_pages <= 100):
        raise ValueError("typed journal, paginator and finite budget required")
    if journal.get(request_id).status == "BOUND":
        return journal.get(request_id)
    after = None
    cursors = set()
    rows = []
    for _ in range(max_pages):
        try:
            response = fetch_page(after, page_limit)
        except Exception as exc:
            raise SessionConflict("provider session scan failed; keep UNKNOWN") from exc
        if (type(response) is not dict or type(response.get("data")) is not list
                or type(response.get("has_more")) is not bool):
            raise SessionConflict("malformed provider page; keep UNKNOWN")
        items = response["data"]
        if len(items) > page_limit:
            raise SessionConflict("oversized provider page; keep UNKNOWN")
        for item in items:
            if type(item) is not dict or type(item.get("id")) is not str:
                raise SessionConflict("provider session without ID; keep UNKNOWN")
            _check(item["id"], _SESSION_ID, "provider session ID")
        rows.extend(items)
        if not response["has_more"]:
            return journal.reconcile(request_id, rows)
        if not items:
            raise SessionConflict("nonterminal empty provider page; keep UNKNOWN")
        cursor = items[-1]["id"]
        if cursor in cursors or cursor == after:
            raise SessionConflict("stalled provider pagination; keep UNKNOWN")
        cursors.add(cursor)
        after = cursor
    raise SessionConflict("incomplete bounded provider scan; keep UNKNOWN")


def reconcile_provider_sessions(
    client, journal: SessionJournal, request_id: str,
    *, page_limit: int = 100, max_pages: int = 50,
) -> Intent:
    """Use documented SDK session-list pagination for read-only reconciliation.

    The provider API lists sessions with limit/order/after, and session items
    carry metadata. This adapter does not create a session, retry a turn, or
    conclude a missing ID means the provider had no side effect.
    """
    def fetch(after: str | None, limit: int) -> dict:
        kwargs = {"limit": limit, "order": "desc"}
        if after is not None:
            kwargs["after"] = after
        try:
            page = client.beta.agents.sessions.list(**kwargs)
        except Exception as exc:
            raise SessionConflict("provider session list failed; no retry") from exc
        def get(obj, name):
            return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        rows = get(page, "data")
        more = get(page, "has_more")
        if type(rows) is not list or type(more) is not bool:
            raise SessionConflict("unexpected provider page schema")
        result = []
        for row in rows:
            ident = get(row, "id")
            meta = get(row, "metadata")
            if type(ident) is not str or (meta is not None and type(meta) is not dict):
                raise SessionConflict("unsupported provider session record")
            result.append({"id": ident, "metadata": meta or {}})
        return {"data": result, "has_more": more}
    return reconcile_session_pages(
        journal, request_id, fetch, page_limit=page_limit, max_pages=max_pages
    )
