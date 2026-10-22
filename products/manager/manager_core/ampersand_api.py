"""Optional Ampersand Agents API (OpenAI SDK 3.24.0) read-only session adapter.

No API key stored here. No external tools. No provider retries on session creation.
Failure/unknown states must not be retried as if no work had happened.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any
from .provider_deadline import bounded_provider_call, observe_event

BASE_URL = "https://ampersand.humansand.ai/v1"
MODEL = "ampersand-v0.1"
DEFAULT_INSTRUCTIONS = (
    "You are a research-only, advisory collaboration model. "
    "Never claim to have executed, authorized, verified or measured an action. "
    "No external tools are available. No private user records are provided. "
    "Follow the requested output format exactly; when uncertain, choose PASS."
)


class SessionFailure(RuntimeError):
    """Do not leak request data or raw provider error bodies into reports."""


@dataclass(frozen=True)
class SessionEvidence:
    session_id: str
    turn_id: str
    output_text: str
    status: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    proof_level: str = "P0"
    actual_human_outcome: str = "NOT_MEASURED"


def valid_api_key(key: object) -> bool:
    return type(key) is str and re.fullmatch(r"hak_[A-Za-z0-9]{8,256}", key) is not None


def make_client(key: str, *, timeout: float = 120) -> Any:
    """Call only on an approved networked host; never normalize leaked tokens."""
    if not valid_api_key(key):
        raise ValueError("provider key must be a fresh ASCII console export")
    if type(timeout) not in (int, float) or not 5 <= timeout <= 180:
        raise ValueError("bounded request timeout required")
    try:
        from openai import OpenAI  # optional dependency, never imported by offline Manager
    except ImportError as exc:
        raise SessionFailure("openai==3.24.0 is required for live inference") from exc
    return OpenAI(base_url=BASE_URL, api_key=key, max_retries=0, timeout=timeout)


def _latest_completed_turn(client: Any, session_id: str):
    try:
        page = client.beta.agents.sessions.turns.list(
            session_id, limit=1, order="desc")
        turn = page.data[0] if page.data else None
    except Exception as exc:
        raise SessionFailure("cannot independently read saved turn state") from exc
    if not turn or getattr(turn, "status", None) != "completed":
        raise SessionFailure("current saved turn is absent, failed, or incomplete")
    return turn


def _usage(turn) -> tuple[int | None, int | None]:
    usage = getattr(turn, "usage", None)
    raw_in = getattr(usage, "input_tokens", None)
    raw_out = getattr(usage, "output_tokens", None)
    return (
        raw_in if type(raw_in) is int and raw_in >= 0 else None,
        raw_out if type(raw_out) is int and raw_out >= 0 else None,
    )


def _bounded_str(text: object, *, max_size=6000) -> str:
    if type(text) is not str or not text.strip() or len(text) > max_size:
        raise ValueError("nonempty bounded prompt required")
    return text


@bounded_provider_call
def read_initial_turn(client: Any, prompt: str,
                      instructions: str = DEFAULT_INSTRUCTIONS, *,
                      journal=None, request_id: str | None = None,
                      budget_ledger=None, budget_run_id: str | None = None,
                      upper_usd=None, deadline_monotonic: float | None = None,
                      allow_silent_completion: bool = False) -> SessionEvidence:
    """Start exactly one session, optionally guarded by durable external intent.

    Live automated callers must pass journal + stable request_id. Old offline
    fixture-only call sites retain journal=None for backward-compatible tests.
    A duplicate/UNKNOWN creation is quarantined, NEVER retried blindly.
    """
    _bounded_str(prompt)
    _bounded_str(instructions)
    if (journal is None) != (request_id is None):
        raise ValueError("journal and request_id must be supplied together")
    if (budget_ledger is None) != (budget_run_id is None):
        raise ValueError("budget ledger and run ID must be supplied together")
    if budget_ledger is None and upper_usd is not None:
        raise ValueError("budget estimate without budget ledger")
    if budget_ledger is not None and upper_usd is None:
        raise ValueError("budget estimate required for provider execution")
    if deadline_monotonic is not None:
        import time
        if (type(deadline_monotonic) not in (float, int) or
                time.monotonic() >= deadline_monotonic):
            raise SessionFailure("provider deadline elapsed before session creation")
    reservation = (budget_ledger.reserve(budget_run_id, upper_usd)
                   if budget_ledger is not None else None)
    create_kwargs = {
        "agent": {"model": MODEL, "instructions": instructions},
        "environment": {"type": "none"},
        "input": prompt,
        "stream": True,
    }
    if journal is not None:
        # Avoid saving input text or secrets in the journal. Identity is a
        # stable hash of the exact model request, including instructions.
        identity = json.dumps(
            {"model": MODEL, "instructions": instructions,
             "input": prompt, "environment": {"type": "none"}},
            ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf8")
        from .provider_sessions import SessionConflict
        try:
            journal.begin(request_id, sha256(identity).hexdigest())
            journal.reserve_for_send(request_id)  # RESERVED→UNKNOWN before HTTP
        except SessionConflict as exc:
            raise SessionFailure(
                "provider creation already attempted or uncertain; reconcile before retry"
            ) from exc
        # Official SessionCreate allows metadata and preserves it in list.
        create_kwargs["metadata"] = {"manager_request_id": request_id}
    try:
        with client.beta.agents.sessions.create(
            **create_kwargs,
        ).with_result_collection() as stream:
            state = "MISSING_FINAL_EVENT"
            for index, event in enumerate(stream):
                observe_event(event)
                if index >= 4000:
                    raise SessionFailure("event budget exceeded")
                typ = getattr(event, "type", "")
                if journal is not None and typ == "agent.session.created":
                    session = getattr(event, "session", None)
                    early_id = getattr(event, "session_id", None)
                    if early_id is None:
                        early_id = (session.get("id") if isinstance(session, dict)
                                    else getattr(session, "id", None))
                    if (isinstance(early_id, str) and
                            re.fullmatch(r"sess_[A-Za-z0-9_-]{4,128}", early_id)):
                        # Identity becomes durable before the potentially
                        # minutes-long stream proceeds; no retry on crash.
                        journal.bind(request_id, early_id)
                if typ in ("agent.session.idle", "agent.session.failed",
                           "agent.session.requires_action"):
                    state = typ
                    break
            if state != "agent.session.idle":
                raise SessionFailure("session did not reach idle without tools")
            result = stream.get_final_result()
    except SessionFailure:
        raise
    except Exception as exc:
        raise SessionFailure("initial provider session uncertain or failed; do not retry blindly") from exc
    session_id = getattr(result, "session_id", None)
    output = getattr(result, "output_text", None)
    if (type(session_id) is not str or
            not re.fullmatch(r"sess_[A-Za-z0-9_-]{4,128}", session_id)):
        raise SessionFailure("initial provider session ID missing")
    if journal is not None:
        try:
            journal.bind(request_id, session_id)  # bind BEFORE text validation
        except Exception as exc:
            raise SessionFailure("received provider session but durable bind failed") from exc
    silent = type(output) is not str or not output.strip()
    if silent and allow_silent_completion is not True:
        raise SessionFailure("empty model response without opt-in silence")
    if silent:
        output = ""
    if len(output) > 16000:
        raise SessionFailure("model output exceeds strict research limit")
    turn = _latest_completed_turn(client, session_id)
    tokens = _usage(turn)
    if reservation is not None:
        from .provider_budget import Usage
        budget_ledger.settle(reservation, Usage.from_turn(turn))
    return SessionEvidence(session_id, turn.id, output,
                           "SILENT_COMPLETED" if silent else "completed", *tokens)


@bounded_provider_call
def read_followup_turn(client: Any, session_id: str, prompt: str, *,
                       key: str, journal=None,
                       writer_id: str | None = None,
                       budget_ledger=None, budget_run_id: str | None = None,
                       upper_usd=None, deadline_monotonic: float | None = None,
                       allow_silent_completion: bool = False) -> SessionEvidence:
    """Submit exactly one idempotent message, read its completed reply in same session."""
    if type(session_id) is not str or not re.fullmatch(r"sess_[A-Za-z0-9_-]{8,128}", session_id):
        raise ValueError("session ID required")
    _bounded_str(prompt)
    if (journal is None) != (writer_id is None):
        raise ValueError("journal and stable writer_id must be supplied together")
    if (budget_ledger is None) != (budget_run_id is None):
        raise ValueError("budget ledger and run ID must be supplied together")
    if (budget_ledger is None and upper_usd is not None or
        budget_ledger is not None and upper_usd is None):
        raise ValueError("budget estimate must have a matching ledger")
    if deadline_monotonic is not None:
        import time
        if type(deadline_monotonic) not in (int,float) or time.monotonic() >= deadline_monotonic:
            raise SessionFailure("provider follow-up deadline elapsed before submission")
    reservation = (budget_ledger.reserve(budget_run_id,upper_usd)
                   if budget_ledger is not None else None)
    if type(key) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{4,128}", key):
        raise ValueError("bounded stable event idempotency key required")
    event = {
        "type": "agent.session.input.message",
        "input": [{
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }],
    }
    if journal is not None:
        # Fail closed if an uncertain previous event with the same key exists.
        # It can be reconciled and, if appropriate, retried with exactly the
        # same key/body, but never submitted twice automatically.
        from .provider_sessions import SessionConflict
        try:
            journal.claim_writer(session_id, writer_id)
            body = json.dumps(event, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")).encode("utf8")
            if not journal.reserve_event(session_id, key, sha256(body).hexdigest()):
                raise SessionFailure("event may already have been submitted; reconcile first")
        except SessionConflict as exc:
            raise SessionFailure("session writer/event conflict; reconcile first") from exc
    completed = False
    response = None
    completed_turn_id = None
    try:
        # Stream starts BEFORE the event write so no completed event is missed.
        with client.beta.agents.sessions.events.stream(session_id) as stream:
            client.beta.agents.sessions.events.create(
                session_id, events=[event], idempotency_key=key)
            for i, item in enumerate(stream):
                observe_event(item)
                if i >= 4000:
                    raise SessionFailure("event budget exceeded")
                typ = getattr(item, "type", "")
                if typ == "agent.session.turn.output_text.done":
                    response = getattr(item, "text", None)
                elif typ == "agent.session.turn.completed":
                    completed = True
                    completed_turn_id = getattr(item, "turn_id", None)
                    break
                elif typ in ("agent.session.turn.failed",
                             "agent.session.turn.cancelled", "agent.session.failed",
                             "agent.session.requires_action"):
                    raise SessionFailure("follow-up turn did not complete safely")
    except SessionFailure:
        raise
    except Exception as exc:
        raise SessionFailure("follow-up state uncertain; inspect saved session before retry") from exc
    if not completed:
        raise SessionFailure("missing completed follow-up turn; reconcile before retry")
    silent = type(response) is not str or not response.strip()
    if silent and allow_silent_completion is not True:
        raise SessionFailure("missing follow-up text without opt-in silence")
    if silent:
        response = ""
    if len(response) > 16000:
        raise SessionFailure("follow-up output exceeds research limit")
    turn = _latest_completed_turn(client, session_id)
    # An event may be about a different turn when multiple writers are active.
    if type(completed_turn_id) is not str or getattr(turn, "id", None) != completed_turn_id:
        raise SessionFailure("concurrent writer or missing/mismatched saved turn")
    if journal is not None:
        try:
            journal.release_writer(session_id, writer_id)
        except Exception as exc:
            raise SessionFailure("completed turn but journal writer release failed") from exc
    if reservation is not None:
        from .provider_budget import Usage
        budget_ledger.settle(reservation, Usage.from_turn(turn))
    return SessionEvidence(session_id, turn.id, response,
                           "SILENT_COMPLETED" if silent else "completed", *_usage(turn))


def read_completed_turn(client: Any, session_id: str, turn_id: str) -> SessionEvidence:
    """Read back the exact persisted provider turn, never latest by assumption.

    Provider endpoint: GET /agents/sessions/{session_id}/turns/{turn_id}.
    The optional SDK transport is injected so this is unit-testable; output
    text is not invented if the turn's saved object lacks a text field.
    """
    if (type(session_id) is not str or
        not re.fullmatch(r"sess_[A-Za-z0-9_-]{4,128}", session_id) or
        type(turn_id) is not str or
        not re.fullmatch(r"turn_[A-Za-z0-9_-]{4,128}", turn_id)):
        raise ValueError("bounded session and exact turn identifiers required")
    try:
        saved = client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id)
    except Exception as exc:
        raise SessionFailure("cannot independently read exact saved turn") from exc
    if getattr(saved, "id", None) != turn_id:
        raise SessionFailure("readback does not match requested provider turn")
    if getattr(saved, "status", None) != "completed":
        raise SessionFailure("saved provider turn is missing or non-completed")
    tokens = _usage(saved)
    output = getattr(saved, "output_text", None)
    if not isinstance(output, str):
        output = ""
    if len(output) > 16000:
        raise SessionFailure("saved provider output exceeds research limits")
    return SessionEvidence(session_id, turn_id, output, "completed", *tokens)


def read_saved_assistant_items(
    client: Any, session_id: str, turn_id: str,
    *, limit: int = 100, max_pages: int = 50,
) -> tuple[str, ...]:
    """Read only saved assistant messages belonging to one completed turn.

    Do not treat an SSE event or another turn's response as final readback.
    Empty tuple means the completed turn has no supported text items; E06
    distinguishes legitimate silence from transport failure.
    """
    read_completed_turn(client, session_id, turn_id)
    if (type(limit) is not int or not 1 <= limit <= 100 or
            type(max_pages) is not int or not 1 <= max_pages <= 50):
        raise ValueError("finite session item pagination budget required")
    def get(obj, key):
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    messages = []
    cursor = None
    seen = set()
    for _ in range(max_pages):
        kwargs = {"limit": limit, "order": "asc"}
        if cursor is not None:
            kwargs["after"] = cursor
        try:
            page = client.beta.agents.sessions.items.list(session_id, **kwargs)
        except Exception as exc:
            raise SessionFailure("cannot independently retrieve saved turn items") from exc
        rows, more = get(page, "data"), get(page, "has_more")
        if type(rows) is not list or type(more) is not bool or len(rows) > limit:
            raise SessionFailure("malformed provider item page")
        for row in rows:
            item_id = get(row, "id")
            if (type(item_id) is not str or not item_id.startswith("item_") or
                    item_id in seen):
                raise SessionFailure("provider item identity is missing or repeated")
            seen.add(item_id)
            if get(row, "turn_id") != turn_id or get(row, "type") != "message":
                continue
            if get(row, "role") != "assistant":
                continue
            content = get(row, "content")
            if type(content) is not list:
                raise SessionFailure("assistant message content shape unsupported")
            for chunk in content:
                kind = get(chunk, "type")
                raw = get(chunk, "text")
                if kind in ("output_text", "text"):
                    if type(raw) is not str:
                        raise SessionFailure("assistant response text unsupported")
                    if raw:
                        messages.append(raw)
        if not more:
            if sum(len(m) for m in messages) > 16000:
                raise SessionFailure("saved response exceeds research limits")
            return tuple(messages)
        if not rows:
            raise SessionFailure("nonterminal empty saved item page")
        next_cursor = get(rows[-1], "id")
        if next_cursor == cursor:
            raise SessionFailure("stalled provider item cursor")
        cursor = next_cursor
    raise SessionFailure("incomplete bounded saved item scan")
