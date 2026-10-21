"""K008: sqlite write-ahead effect reservation; NEVER retry an uncertain send.

The only supported adapter class is an explicitly offline fixture. One signed
grant may authorize multiple intent IDs, but a single SQLite transaction guards
the total reserved budget across them. Crash between DISPATCHING and send remains
uncertain and requires reconciliation, not retry.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3
from .authority import Grant, AuthorityVerifier


def _units(amount):
    try:
        d=Decimal(str(amount))
        q=d*1000000
        if not d.is_finite() or q!=q.to_integral_value() or not 0<=q<=10**15:
            raise ValueError("cost must be finite, positive-compatible and <=6 decimals")
        return int(q)
    except (InvalidOperation,TypeError):
        raise ValueError("invalid budget amount") from None


@dataclass(frozen=True)
class EffectRecord:
    key: str
    grant_id: str
    domain: str
    action: str
    target: str
    cost: float
    status: str
    receipt_ref: str | None = None
    dispatched_at: datetime | None = None


class DurableOutbox:
    def __init__(self,path: str | Path):
        self.path=str(path)
        with sqlite3.connect(self.path,timeout=15) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS effects (
                key TEXT PRIMARY KEY, grant_id TEXT NOT NULL, domain TEXT NOT NULL,
                action TEXT NOT NULL, target TEXT NOT NULL, cost_units INTEGER NOT NULL,
                status TEXT NOT NULL, receipt_ref TEXT, dispatched_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_effect_grant ON effects(grant_id)")

    @staticmethod
    def _as_record(row):
        if row is None: return None
        return EffectRecord(row[0],row[1],row[2],row[3],row[4],row[5]/1e6,
                            row[6],row[7],datetime.fromisoformat(row[8]))

    def record(self,key):
        with sqlite3.connect(self.path,timeout=15) as db:
            return self._as_record(db.execute(
                "SELECT key,grant_id,domain,action,target,cost_units,status,receipt_ref,dispatched_at FROM effects WHERE key=?",(key,)).fetchone())

    def execute(self,key: str,grant: Grant,signature: str,verifier: AuthorityVerifier,
                adapter,cost: float,at: datetime) -> EffectRecord:
        if not isinstance(key,str) or not key.strip() or len(key)>256:
            raise ValueError("nonempty stable intent key required")
        if getattr(adapter,"offline_fixture",None) is not True:
            raise PermissionError("live effects are forbidden, even with a fixture grant")
        verifier.authorize(grant,signature,adapter.domain,adapter.action,adapter.target,cost,at)
        units=_units(cost)
        db=sqlite3.connect(self.path,timeout=15,isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT key,grant_id,domain,action,target,cost_units,status,receipt_ref,dispatched_at FROM effects WHERE key=?",(key,)).fetchone()
            if row is not None:
                if (row[1],row[2],row[3],row[4],row[5]) != (grant.grant_id,adapter.domain,adapter.action,adapter.target,units):
                    raise ValueError("idempotency key reused for a different effect")
                db.execute("COMMIT")
                return self._as_record(row)
            committed=db.execute("SELECT COALESCE(SUM(cost_units),0) FROM effects WHERE grant_id=?",(grant.grant_id,)).fetchone()[0]
            if committed + units > _units(grant.limit):
                raise PermissionError("cumulative grant budget exceeded")
            db.execute("""INSERT INTO effects
                (key,grant_id,domain,action,target,cost_units,status,receipt_ref,dispatched_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (key,grant.grant_id,adapter.domain,adapter.action,adapter.target,
                 units,"DISPATCHING",None,at.isoformat()))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction: db.execute("ROLLBACK")
            raise
        finally:
            db.close()
        try:
            receipt=adapter.send(key)
            if not isinstance(receipt,str) or not receipt:
                raise ValueError("empty fixture receipt")
        except Exception:
            self._set_status(key,"UNKNOWN",None)
        else:
            self._set_status(key,"SUBMITTED",receipt)
        return self.record(key)

    def _set_status(self,key,status,receipt_ref):
        if status not in {"UNKNOWN","SUBMITTED","PRESENT","ABSENT"}:
            raise ValueError("unsupported outbox state")
        with sqlite3.connect(self.path,timeout=15) as db:
            db.execute("UPDATE effects SET status=?,receipt_ref=? WHERE key=?",
                       (status,receipt_ref,key))
