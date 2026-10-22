#!/usr/bin/env python3
"""Research-only Ampersand v0.1 API probe. NEVER executes a Manager intervention.

Modes:
  --offline      Build a real API-shaped request and validate fixture proposals.
  --check-access Verify model availability (requires AMPERSAND_API_KEY).
  --smoke        Opt-in billable session creation; requires explicit env guard.

This is a protocol/authorization smoke test, NOT a benchmark of Ampersand.
"""
from __future__ import annotations
import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://ampersand.humansand.ai/v1"
MODEL = "ampersand-v0.1"
ACCEPTED_DECISIONS = frozenset(("PASS", "ASK", "PROPOSE"))
DECISION_KEYS = frozenset(("decision", "reason", "source_ids"))


def session_payload(prompt: str) -> dict:
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ValueError("short nonempty input required")
    return {
        "agent": {
            "model": MODEL,
            "instructions": (
                "You are a research-only collaboration planner. Do not claim to have "
                "executed an action. Recommend PASS, ASK, or a PROPOSAL ONLY. "
                "Never infer causal benefit from a simulated conversation. "
                "Do not request secrets, payments, private data or tool execution."
            ),
            "ampersand": {"allow_silent_completion": False, "compaction": "auto"},
        },
        "environment": {"type": "none"},
        "input": prompt,
    }


def validate_proposal(value: object, approved_source_ids: set[str]) -> dict:
    """Validation boundary: never converts model text to execution authority."""
    if not isinstance(value, dict) or set(value) != DECISION_KEYS:
        raise ValueError("unexpected fields or missing proposal field")
    decision, reason, refs = value["decision"], value["reason"], value["source_ids"]
    if decision not in ACCEPTED_DECISIONS or not isinstance(reason, str) or not reason.strip():
        raise ValueError("invalid decision or rationale")
    if not isinstance(refs, list) or not all(isinstance(s, str) for s in refs):
        raise ValueError("source_ids must be strings")
    if len(refs) != len(set(refs)) or not set(refs).issubset(approved_source_ids):
        raise ValueError("unknown or duplicate source IDs")
    if decision == "PROPOSE" and not refs:
        raise ValueError("proposal requires at least one approved source")
    return {
        "status": "ADVISORY_ONLY",
        "decision": decision,
        "rationale": reason.strip(),
        "source_ids": list(refs),
        "proof_level": "P0",
        "causal_support": False,
        "authorized_execution": False,
    }


def request_json(method: str, endpoint: str, api_key: str, payload: dict | None = None, *, opener=urlopen) -> dict:
    if method not in ("GET", "POST") or endpoint not in ("/models", "/agents/sessions"):
        raise ValueError("endpoint/method not allowed for this probe")
    if (method, endpoint) not in (("GET", "/models"), ("POST", "/agents/sessions")):
        raise ValueError("method/endpoint mismatch")
    if not api_key or api_key.strip() != api_key:
        raise ValueError("API key absent or malformed")
    body = None if method == "GET" else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if endpoint != "/models":
        headers["OpenAI-Beta"] = "agents=v1"
    request = Request(BASE_URL + endpoint, data=body, headers=headers, method=method)
    with opener(request, timeout=15) as reply:
        return json.loads(reply.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="default: no network or billable requests")
    mode.add_argument("--check-access", action="store_true", help="GET /models only; requires key")
    mode.add_argument("--smoke", action="store_true", help="billable single session, double opt-in")
    args = parser.parse_args(argv)
    prompt = "Team is changing Friday's plan, but one member is unavailable. Suggest whether to ask or wait."
    if not (args.check_access or args.smoke):
        payload = session_payload(prompt)
        valid = validate_proposal({"decision": "ASK", "reason": "Resolve scheduling conflict", "source_ids": ["fixture:calendar"]}, {"fixture:calendar"})
        print(json.dumps({"mode": "OFFLINE_ONLY", "session_request": payload, "fixture_result": valid}, indent=2))
        return 0
    key = os.environ.get("AMPERSAND_API_KEY", "")
    if not key:
        print("BLOCKED_NO_API_KEY: No network request, no model inference, no charge.")
        return 2
    try:
        models = request_json("GET", "/models", key)
        ids = {x.get("id") for x in models.get("data", []) if isinstance(x, dict)}
        if MODEL not in ids:
            print("BLOCKED_MODEL_UNAVAILABLE: tenant does not list ampersand-v0.1")
            return 3
        if args.check_access:
            print("AUTHENTICATED_MODEL_LIST_OK; no inference attempted")
            return 0
        if os.environ.get("AMPERSAND_ALLOW_BILLABLE_PROBE") != "1":
            print("BLOCKED_BILLABLE_PROBE: set AMPERSAND_ALLOW_BILLABLE_PROBE=1 after reviewing pricing")
            return 4
        session = request_json("POST", "/agents/sessions", key, session_payload(prompt))
        print(json.dumps({"status": "SESSION_CREATED", "session_id": session.get("id"), "note": "No tools attached; no Manager effects. Inspect session via authorized account."}))
        return 0
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        print("API_PROBE_FAILED: " + type(exc).__name__ + " (credentials and response contents redacted)")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
