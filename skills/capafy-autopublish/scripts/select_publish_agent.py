#!/usr/bin/env python3
"""Select one existing Capafy Agent from the 0.9.11 publish-list shape."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter


KNOWN_STATUSES = frozenset(
    {"draft", "review_rejected", "under_review", "approved", "online"}
)
UNLISTED_STATUSES = frozenset({"draft", "under_review", "review_rejected"})
CAPACITY_STATUSES = KNOWN_STATUSES | frozenset({
    "banned", "offline", "user_offline", "user_delisted", "taken_down",
    "pending_online", "audit_passed_pending_online",
})
CAPAFY_REVIEW_CAP = 5


def _fail(message: str) -> int:
    print(f"select_publish_agent: {message}", file=sys.stderr)
    return 1


def _load_agents() -> tuple[list[dict[str, str]] | None, int]:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, _fail(f"invalid JSON input: {exc}")
    if not isinstance(payload, dict) or not isinstance(payload.get("agents"), list):
        return None, _fail("expected top-level agents array")

    agents: list[dict[str, str]] = []
    for index, raw in enumerate(payload["agents"]):
        if not isinstance(raw, dict):
            return None, _fail(f"agents[{index}] is not an object")
        required = ("agent_id", "name", "agent_status")
        if any(key not in raw for key in required):
            return None, _fail(f"agents[{index}] is missing required snake_case fields")
        agent_id = str(raw.get("agent_id") or "").strip()
        name = str(raw.get("name") or "").strip()
        status = str(raw.get("agent_status") or "").strip().lower()
        if not agent_id or not name or not status:
            return None, _fail(f"agents[{index}] has invalid identity or status")
        agents.append({"agent_id": agent_id, "name": name, "agent_status": status,
                       "latest_agent_version_id": str(raw.get("latest_agent_version_id") or "").strip()})

    duplicates = sorted(agent_id for agent_id, count in Counter(a["agent_id"] for a in agents).items() if count > 1)
    if duplicates:
        return None, _fail("duplicate agent_id in agents array")
    return agents, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--reuse-agent-id", default="")
    parser.add_argument("--require-free-slot", action="store_true")
    parser.add_argument("--expected-agent-id", default="")
    parser.add_argument("--expected-version-id", default="")
    args = parser.parse_args(argv)

    agents, code = _load_agents()
    if agents is None:
        return code
    title = str(args.title or "").strip()
    if not title:
        return _fail("title must not be empty")
    title_matches = [agent for agent in agents if agent["name"] == title]
    if len(title_matches) > 1:
        return _fail("exact title matches more than one Agent")
    expected_id = str(args.expected_agent_id or "").strip()
    expected_version = str(args.expected_version_id or "").strip()
    if bool(expected_id) != bool(expected_version):
        return _fail("same-Agent update requires both Agent and source version ID")
    if expected_id:
        if (len(title_matches) != 1 or title_matches[0]["agent_id"] != expected_id
                or title_matches[0]["agent_status"] != "online"
                or title_matches[0]["latest_agent_version_id"] != expected_version):
            return _fail("same-Agent source version changed; no new version is created")
    if args.require_free_slot:
        if any(agent["agent_status"] not in CAPACITY_STATUSES for agent in agents):
            return _fail("inventory has unsupported status; review capacity unknown")
        if sum(agent["agent_status"] in UNLISTED_STATUSES for agent in agents) >= CAPAFY_REVIEW_CAP:
            return _fail("CAP_FULL: no slot for a new Agent/version")

    reuse_id = str(args.reuse_agent_id or "").strip()
    if reuse_id:
        reuse_matches = [agent for agent in agents if agent["agent_id"] == reuse_id]
        if len(reuse_matches) != 1:
            return _fail("explicit reuse agent_id is not exactly one Agent")
        if reuse_matches[0]["name"] != title:
            return _fail("explicit reuse Agent name does not match the requested title")
        if reuse_matches[0]["agent_status"] not in {"draft", "review_rejected"}:
            return _fail("explicit reuse Agent is not draft/review_rejected")
        print(reuse_id)
        return 0

    if not title_matches:
        return 0
    if title_matches[0]["agent_status"] not in KNOWN_STATUSES:
        return _fail("exact-title Agent has an unsupported status")
    print(title_matches[0]["agent_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
