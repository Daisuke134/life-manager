"""E06: conservative persistent Ampersand token budget and cancel readback.

Usage is evidence of tokens, NOT an authoritative settled payment. Reservations
stay charged against the cap until separate provider billing is reconciled.
Pricing pinned to public Ampersand v0.1 pricing as of 2026-10-22.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_UP
from hashlib import sha256
from pathlib import Path
import json
import re
import sqlite3

_MICRO = Decimal("0.000001")
_RUN_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class BudgetExceeded(PermissionError):
    """Hard cumulative budget, unknown cost, or changed reservation."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None

    def __post_init__(self):
        for name in ("input_tokens","output_tokens","cached_input_tokens",
                     "reasoning_output_tokens"):
            v=getattr(self,name)
            if v is not None and (type(v) is not int or not 0<=v<=10**10):
                raise ValueError("bounded nonnegative integer token count required")
        if (self.cached_input_tokens is not None and
                self.cached_input_tokens > self.input_tokens):
            raise ValueError("cached input cannot exceed input total")
        if (self.reasoning_output_tokens is not None and
                self.reasoning_output_tokens > self.output_tokens):
            raise ValueError("reasoning is already part of output tokens")

    @classmethod
    def from_turn(cls, turn):
        usage=getattr(turn,"usage",None)
        if usage is None:
            return None
        ins=getattr(usage,"input_tokens",None)
        outs=getattr(usage,"output_tokens",None)
        if type(ins) is not int or type(outs) is not int:
            return None
        detail=getattr(usage,"input_tokens_details",None)
        odetail=getattr(usage,"output_tokens_details",None)
        return cls(ins,outs,
            getattr(detail,"cached_tokens",None) if detail else None,
            getattr(odetail,"reasoning_tokens",None) if odetail else None)


def _money(value: Decimal) -> int:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("finite Decimal USD required")
    q=value / _MICRO
    if value<=0 or q!=q.to_integral_value() or q>100_000_000:
        raise ValueError("USD amount must have at most 6 decimals and be in (0,100]")
    return int(q)


def estimate_cost_usd(usage: Usage) -> Decimal:
    """USD estimate from total input/cache/output including reasoning ONCE."""
    if type(usage) is not Usage:
        raise ValueError("typed measured token usage required")
    cached=usage.cached_input_tokens or 0
    # USD per million tokens: uncached input $1, cached input $0.20,
    # output including reasoning $5.20.
    total=(Decimal(usage.input_tokens-cached)
           +Decimal(cached)*Decimal("0.20")
           +Decimal(usage.output_tokens)*Decimal("5.20"))/Decimal(1_000_000)
    return total.quantize(_MICRO,rounding=ROUND_UP)


@dataclass(frozen=True)
class BudgetReservation:
    run_id: str
    reserved_usd: Decimal
    status: str
    usage: Usage | None = None
    settled_usd: Decimal | None = None
    estimated_usage_usd: Decimal | None = None


class BudgetLedger:
    def __init__(self,path: str | Path, *, cap_usd: Decimal):
        self.path=str(Path(path))
        if self.path==":memory:":
            raise ValueError("persistent budget ledger required")
        cap=_money(cap_usd)
        self.cap=cap
        with sqlite3.connect(self.path,timeout=15) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS budget_policy (
                id INTEGER PRIMARY KEY CHECK(id=1),cap_units INTEGER NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS budget_reservations (
                run_id TEXT PRIMARY KEY, reserved_units INTEGER NOT NULL,
                status TEXT NOT NULL, usage_json TEXT, measured_cost_units INTEGER,
                settled_units INTEGER
            )""")
            db.execute("INSERT OR IGNORE INTO budget_policy VALUES (1,?)",(cap,))
            stored=db.execute("SELECT cap_units FROM budget_policy WHERE id=1").fetchone()[0]
            if stored!=cap:
                raise BudgetExceeded("changing a live budget cap requires explicit audited rotation")

    @staticmethod
    def _row(row):
        if row is None:
            raise BudgetExceeded("unknown reservation")
        usage=Usage(**json.loads(row[3])) if row[3] is not None else None
        return BudgetReservation(
            run_id=row[0],reserved_usd=Decimal(row[1])*_MICRO,
            status=row[2],usage=usage,
            settled_usd=Decimal(row[5])*_MICRO if row[5] is not None else None,
            estimated_usage_usd=Decimal(row[4])*_MICRO if row[4] is not None else None)

    def _txn(self,callback):
        db=sqlite3.connect(self.path,timeout=15,isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            result=callback(db)
            db.execute("COMMIT")
            return result
        except BaseException:
            if db.in_transaction: db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def get(self,run_id: str) -> BudgetReservation:
        if type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
            raise ValueError("stable bounded budget run ID required")
        with sqlite3.connect(self.path,timeout=15) as db:
            return self._row(db.execute(
                "SELECT run_id,reserved_units,status,usage_json,measured_cost_units,settled_units "
                "FROM budget_reservations WHERE run_id=?",(run_id,)).fetchone())

    def available_usd(self) -> Decimal:
        with sqlite3.connect(self.path,timeout=15) as db:
            used=db.execute("SELECT COALESCE(SUM(reserved_units),0) FROM budget_reservations").fetchone()[0]
            return Decimal(self.cap-used)*_MICRO

    def reserve(self,run_id: str,estimated_upper_usd: Decimal) -> BudgetReservation:
        if type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
            raise ValueError("bounded stable run ID required")
        amount=_money(estimated_upper_usd)
        def body(db):
            row=db.execute(
                "SELECT run_id,reserved_units,status,usage_json,measured_cost_units,settled_units "
                "FROM budget_reservations WHERE run_id=?",(run_id,)).fetchone()
            if row:
                if row[1]!=amount: raise BudgetExceeded("run ID reused with changed ceiling")
                return self._row(row)
            if db.execute("SELECT 1 FROM budget_reservations WHERE measured_cost_units > reserved_units LIMIT 1").fetchone():
                raise BudgetExceeded("observed provider exposure exceeded reservation; reconcile before new requests")
            used=db.execute("SELECT COALESCE(SUM(reserved_units),0) FROM budget_reservations").fetchone()[0]
            if used+amount>self.cap:
                raise BudgetExceeded("provider budget exhausted; no new inference allowed")
            db.execute("INSERT INTO budget_reservations VALUES (?,?,?,?,?,?)",
                       (run_id,amount,"RESERVED",None,None,None))
            return self._row(db.execute(
                "SELECT run_id,reserved_units,status,usage_json,measured_cost_units,settled_units "
                "FROM budget_reservations WHERE run_id=?",(run_id,)).fetchone())
        return self._txn(body)

    def settle(self,reservation: BudgetReservation,usage: Usage | None) -> BudgetReservation:
        """Record token usage without asserting a settled provider dollar amount."""
        if type(reservation) is not BudgetReservation or (
            usage is not None and type(usage) is not Usage):
            raise ValueError("typed reservation and optional typed usage required")
        estimated=estimate_cost_usd(usage) if usage is not None else None
        serialized=(json.dumps({
            "input_tokens":usage.input_tokens,"output_tokens":usage.output_tokens,
            "cached_input_tokens":usage.cached_input_tokens,
            "reasoning_output_tokens":usage.reasoning_output_tokens,
        },sort_keys=True) if usage is not None else None)

        def body(db):
            row=db.execute(
                "SELECT run_id,reserved_units,status,usage_json,measured_cost_units,settled_units "
                "FROM budget_reservations WHERE run_id=?",(reservation.run_id,)).fetchone()
            if row is None or self._row(row).reserved_usd!=reservation.reserved_usd:
                raise BudgetExceeded("reservation not found or changed")
            if row[3] is not None and row[3]!=serialized and usage is not None:
                raise BudgetExceeded("usage cannot be silently rewritten")
            # Missing usage must remain UNKNOWN, not free budget or inferred $0.
            status=("TOKENS_OBSERVED_COST_UNSETTLED" if usage is not None
                    else row[2] if row[3] is not None else "UNKNOWN_USAGE")
            db.execute(
                "UPDATE budget_reservations SET status=?,usage_json=COALESCE(?,usage_json),"
                "measured_cost_units=COALESCE(?,measured_cost_units) WHERE run_id=?",
                (status,serialized,int(estimated/_MICRO) if estimated is not None else None,
                 reservation.run_id))
            return self._row(db.execute(
                "SELECT run_id,reserved_units,status,usage_json,measured_cost_units,settled_units "
                "FROM budget_reservations WHERE run_id=?",(reservation.run_id,)).fetchone())
        return self._txn(body)


@dataclass(frozen=True)
class CancellationReceipt:
    session_id: str
    turn_id: str
    status: str
    provider_turn_status: str
    cancellation_sent: bool


def cancel_and_reconcile(client,journal,session_id: str,turn_id: str, *,
                         event_key: str,writer_id: str) -> CancellationReceipt:
    """Request documented agent.session.input.cancel; check actual saved status.

    202 Accepted is not proof that the turn was cancelled. An uncertain send
    keeps the event reserved and never blindly retries.
    """
    from .provider_sessions import SessionJournal, SessionConflict
    from .ampersand_api import SessionFailure
    if type(journal) is not SessionJournal:
        raise ValueError("durable provider journal required")
    if type(turn_id) is not str or not re.fullmatch(r"turn_[A-Za-z0-9_-]{4,128}",turn_id):
        raise ValueError("exact bounded provider turn ID required")
    if type(writer_id) is not str or not _RUN_ID.fullmatch(writer_id):
        raise ValueError("bounded owner ID required")
    event={"type":"agent.session.input.cancel"}
    canonical=json.dumps(event,sort_keys=True,separators=(",",":")).encode()
    sent=False
    try:
        journal.claim_writer(session_id,writer_id)
        new=journal.reserve_event(session_id,event_key,sha256(canonical).hexdigest())
        if new:
            try:
                client.beta.agents.sessions.events.create(
                    session_id,events=[event],idempotency_key=event_key)
            except Exception:
                return CancellationReceipt(session_id,turn_id,
                    "CANCEL_REQUEST_UNKNOWN","UNKNOWN",False)
            sent=True
    except SessionConflict as exc:
        raise SessionFailure("cancellation journal conflict") from exc
    try:
        turn=client.beta.agents.sessions.turns.retrieve(
            turn_id,session_id=session_id)
        if getattr(turn,"id",None)!=turn_id:
            return CancellationReceipt(session_id,turn_id,"CANCEL_REQUEST_UNKNOWN","UNKNOWN",sent)
        state=getattr(turn,"status","UNKNOWN")
    except Exception:
        return CancellationReceipt(session_id,turn_id,
            "CANCEL_REQUEST_UNKNOWN","UNKNOWN",sent)
    result={
        "cancelled":"CANCELLED_VERIFIED",
        "completed":"FINISHED_BEFORE_CANCEL",
        "failed":"TURN_FAILED",
    }.get(state,"CANCEL_REQUESTED_UNCONFIRMED")
    if state in ("cancelled","completed","failed"):
        journal.release_writer(session_id,writer_id)
    return CancellationReceipt(session_id,turn_id,result,str(state),sent)
