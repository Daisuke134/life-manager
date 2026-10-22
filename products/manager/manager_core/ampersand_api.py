"""Optional Ampersand Agents API (OpenAI SDK 3.24.0) read-only session adapter.

No API key stored here. No external tools. No provider retries on session creation.
Failure/unknown states must not be retried as if no work had happened.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any

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


def read_initial_turn(client: Any, prompt: str,
                      instructions: str = DEFAULT_INSTRUCTIONS) -> SessionEvidence:
    """Start exactly one remote session; verify that its final turn completed."""
    _bounded_str(prompt)
    _bounded_str(instructions)
    try:
        with client.beta.agents.sessions.create(
            agent={"model": MODEL, "instructions": instructions},
            environment={"type": "none"}, input=prompt, stream=True,
        ).with_result_collection() as stream:
            state = "MISSING_FINAL_EVENT"
            for index, event in enumerate(stream):
                if index >= 4000:
                    raise SessionFailure("event budget exceeded")
                typ = getattr(event, "type", "")
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
    if type(session_id) is not str or not session_id.startswith("sess_"):
        raise SessionFailure("initial provider session ID missing")
    if type(output) is not str or not output.strip():
        raise SessionFailure("empty/silent model response; no advisory action")
    if len(output) > 16000:
        raise SessionFailure("model output exceeds strict research limit")
    turn = _latest_completed_turn(client, session_id)
    tokens = _usage(turn)
    return SessionEvidence(session_id, turn.id, output, "completed", *tokens)


def read_followup_turn(client: Any, session_id: str, prompt: str, *,
                       key: str) -> SessionEvidence:
    """Submit exactly one idempotent message, read its completed reply in same session."""
    if type(session_id) is not str or not re.fullmatch(r"sess_[A-Za-z0-9_-]{8,128}", session_id):
        raise ValueError("session ID required")
    _bounded_str(prompt)
    if type(key) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{4,128}", key):
        raise ValueError("bounded stable event idempotency key required")
    event = {
        "type": "agent.session.input.message",
        "input": [{
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }],
    }
    completed = False
    response = None
    completed_turn_id = None
    try:
        # Stream starts BEFORE the event write so no completed event is missed.
        with client.beta.agents.sessions.events.stream(session_id) as stream:
            client.beta.agents.sessions.events.create(
                session_id, events=[event], idempotency_key=key)
            for i, item in enumerate(stream):
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
    if not completed or type(response) is not str or not response.strip():
        raise SessionFailure("missing completed follow-up response")
    if len(response) > 16000:
        raise SessionFailure("follow-up output exceeds research limit")
    turn = _latest_completed_turn(client, session_id)
    # An event may be about a different turn when multiple writers are active.
    if completed_turn_id and getattr(turn, "id", None) != completed_turn_id:
        raise SessionFailure("concurrent writer or mismatched saved turn")
    return SessionEvidence(session_id, turn.id, response, "completed", *_usage(turn))
