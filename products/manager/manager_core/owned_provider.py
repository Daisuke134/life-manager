"""Checkpoint-bound, public-source advisory calls for the owned Manager cycle.

This adapter does not grant execution authority or provide automatic recovery
for a provider turn whose exact identifier was not durably recorded.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import re
import sqlite3

from .ampersand_api import (
    SessionEvidence, read_followup_turn, read_initial_turn,
)
from .collaboration import (
    AdvisoryResult, PlannerContext, safe_advisory, render_prompt,
)
from .owned_checkpoint import PrivateCheckpoint, CheckpointUnavailable
from .provider_budget import BudgetLedger, cancel_and_reconcile, Usage, estimate_cost_usd
from .provider_deadline import provider_deadline
from .provider_sessions import Intent, SessionJournal, reconcile_provider_sessions

_PROVIDER_TABLES = {
    "amp_sessions", "amp_events", "budget_policy", "budget_reservations",
}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REQUEST = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_SESSION = re.compile(r"sess_[A-Za-z0-9_-]{4,128}\Z")
_EVENT = re.compile(r"[A-Za-z0-9_-]{4,128}\Z")
_OWNER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_BUDGET = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def validate_provider_tables(db: sqlite3.Connection, tables: set[str]) -> None:
    """Validate an optional provider-state group without creating or repairing it."""
    present = _PROVIDER_TABLES & tables
    if not present:
        return
    if present != _PROVIDER_TABLES:
        raise ValueError("partial checkpointed provider tables")

    expected = {
        "amp_sessions": {"request_id", "body_hash", "status", "session_id", "writer_id", "created_at"},
        "amp_events": {"session_id", "event_key", "body_hash"},
        "budget_policy": {"id", "cap_units"},
        "budget_reservations": {"run_id", "reserved_units", "status", "usage_json", "measured_cost_units", "settled_units"},
    }
    for table, required in expected.items():
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if not required <= columns:
            raise ValueError("invalid provider checkpoint schema")

    sessions = {}
    for request_id, body_hash, status, session_id, writer_id, created_at in db.execute(
        "SELECT request_id,body_hash,status,session_id,writer_id,created_at FROM amp_sessions"
    ):
        if (type(request_id) is not str or not _REQUEST.fullmatch(request_id) or
                type(body_hash) is not str or not _SHA.fullmatch(body_hash) or
                status not in ("RESERVED", "UNKNOWN", "BOUND") or
                type(created_at) is not str or not created_at):
            raise ValueError("invalid provider session intent")
        if session_id is not None and (type(session_id) is not str or not _SESSION.fullmatch(session_id)):
            raise ValueError("invalid provider session reference")
        if writer_id is not None and (type(writer_id) is not str or not _OWNER.fullmatch(writer_id)):
            raise ValueError("invalid provider writer reference")
        if (status == "BOUND") != (session_id is not None):
            raise ValueError("provider intent status and session reference disagree")
        if status != "BOUND" and writer_id is not None:
            raise ValueError("provider writer claim is detached from a bound session")
        if session_id is not None:
            if session_id in sessions:
                raise ValueError("provider session bound more than once")
            sessions[session_id] = status

    for session_id, event_key, body_hash in db.execute(
        "SELECT session_id,event_key,body_hash FROM amp_events"
    ):
        if (session_id not in sessions or sessions[session_id] != "BOUND" or
                type(event_key) is not str or not _EVENT.fullmatch(event_key) or
                type(body_hash) is not str or not _SHA.fullmatch(body_hash)):
            raise ValueError("invalid provider event/session reference")

    policies = db.execute("SELECT id,cap_units FROM budget_policy").fetchall()
    if (len(policies) != 1 or policies[0][0] != 1 or
            type(policies[0][1]) is not int or not 1 <= policies[0][1] <= 100_000_000):
        raise ValueError("invalid checkpointed budget cap")
    cap = policies[0][1]
    total = 0
    for run_id, reserved, status, usage_json, measured, settled in db.execute(
        "SELECT run_id,reserved_units,status,usage_json,measured_cost_units,settled_units FROM budget_reservations"
    ):
        if (type(run_id) is not str or not _BUDGET.fullmatch(run_id) or
                type(reserved) is not int or not 1 <= reserved <= 100_000_000 or
                status not in ("RESERVED", "UNKNOWN_USAGE", "TOKENS_OBSERVED_COST_UNSETTLED")):
            raise ValueError("invalid provider budget reservation")
        total += reserved
        if settled is not None:
            raise ValueError("provider settlement is not supported by token estimates")
        if usage_json is None:
            if measured is not None or status == "TOKENS_OBSERVED_COST_UNSETTLED":
                raise ValueError("provider usage and estimate disagree")
        else:
            try:
                usage_value = json.loads(usage_json)
                if type(usage_value) is not dict or set(usage_value) != {
                    "input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens"
                }:
                    raise ValueError
                usage = Usage(**usage_value)
                estimated_units = int(estimate_cost_usd(usage) * 1_000_000)
            except (TypeError, ValueError, json.JSONDecodeError):
                raise ValueError("invalid saved provider usage") from None
            if (status != "TOKENS_OBSERVED_COST_UNSETTLED" or type(measured) is not int or
                    measured != estimated_units):
                raise ValueError("provider usage estimate/status mismatch")
    if total > cap:
        raise ValueError("provider reservation total exceeds recorded cap")


@dataclass(frozen=True)
class ProviderAdvice:
    evidence: SessionEvidence
    advice: AdvisoryResult


class CheckpointedProvider:
    """One acquired private checkpoint owns the session journal and budget."""

    def __init__(self, checkpoint: PrivateCheckpoint, *, cap_usd: Decimal):
        if type(checkpoint) is not PrivateCheckpoint:
            raise ValueError("exact acquired PrivateCheckpoint required")
        self.checkpoint = checkpoint
        self._require_active()
        if type(cap_usd) is not Decimal:
            raise ValueError("finite Decimal cap required")
        # Acquisition already rejects partial state. Initialize both table sets
        # before attaching a hook so no valid checkpoint can contain a partial
        # group between schema creation steps.
        self.journal = SessionJournal(checkpoint.db)
        self.ledger = BudgetLedger(checkpoint.db, cap_usd=cap_usd)
        self.journal.after_commit = self._after_commit
        self.ledger.after_commit = self._after_commit
        self._after_commit()

    def _require_active(self) -> None:
        cp = self.checkpoint
        if (type(cp) is not PrivateCheckpoint or cp.db is None or cp.broken or
                cp.revision is None):
            raise CheckpointUnavailable("active acquired private checkpoint required")

    def _after_commit(self) -> None:
        self._require_active()
        self.checkpoint.save()

    @staticmethod
    def _operation_id(namespace: str, value: str) -> str:
        if type(value) is not str:
            raise ValueError("stable operation identity required")
        return namespace + sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _public_context(context: PlannerContext) -> str:
        if type(context) is not PlannerContext:
            raise ValueError("typed public PlannerContext required")
        return render_prompt(context, fictional=False)

    def initial(self, client, context: PlannerContext, *, request_id: str,
                upper_usd: Decimal, deadline_monotonic: float) -> ProviderAdvice:
        self._require_active()
        prompt = self._public_context(context)
        budget_id = self._operation_id("initial_", request_id)
        evidence = read_initial_turn(
            client, prompt, journal=self.journal, request_id=request_id,
            budget_ledger=self.ledger, budget_run_id=budget_id,
            upper_usd=upper_usd, deadline_monotonic=deadline_monotonic,
        )
        self._require_active()
        return ProviderAdvice(evidence, safe_advisory(evidence.output_text, context))

    def followup(self, client, session_id: str, context: PlannerContext, *,
                 key: str, upper_usd: Decimal,
                 deadline_monotonic: float) -> ProviderAdvice:
        self._require_active()
        prompt = self._public_context(context)
        op = session_id + "\0" + key
        digest = sha256(op.encode("utf-8")).hexdigest()
        evidence = read_followup_turn(
            client, session_id, prompt, key=key, journal=self.journal,
            writer_id="followup_" + digest,
            budget_ledger=self.ledger, budget_run_id="followup_" + digest,
            upper_usd=upper_usd, deadline_monotonic=deadline_monotonic,
        )
        self._require_active()
        return ProviderAdvice(evidence, safe_advisory(evidence.output_text, context))

    def reconcile(self, client, request_id: str, *,
                  deadline_monotonic: float) -> Intent:
        self._require_active()
        with provider_deadline(deadline_monotonic):
            result = reconcile_provider_sessions(client, self.journal, request_id)
        self._require_active()
        return result

    def cancel(self, client, session_id: str, turn_id: str, *, key: str):
        """Send one cancellation event only after its event and writer are saved."""
        self._require_active()
        if type(key) is not str:
            raise ValueError("stable cancellation key required")
        writer_id = "cancel_" + sha256(
            (session_id + "\0" + turn_id + "\0" + key).encode("utf-8")
        ).hexdigest()
        receipt = cancel_and_reconcile(
            client, self.journal, session_id, turn_id,
            event_key=key, writer_id=writer_id,
        )
        self._require_active()
        return receipt
