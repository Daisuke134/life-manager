#!/usr/bin/env python3
"""Verify the exact Agent version and CP1 model from Capafy's official detail API."""

import argparse
import json
import os
import sys
import urllib.request


def matches(payload: dict, agent_id: str, version_id: str, model: str) -> bool:
    data = payload.get("data") if isinstance(payload, dict) and payload.get("code") == 0 else None
    return (isinstance(data, dict)
            and str(data.get("agentId") or "") == agent_id
            and str(data.get("agentVersionId") or "") == version_id
            and data.get("model") == model
            and data.get("isConfirmedSkills") in (1, True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--version-id", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    token = os.environ.get("CAPAFY_ACCESS_TOKEN", "")
    if not args.agent_id.isdecimal() or not token:
        print("CP1_MODEL=UNKNOWN", file=sys.stderr)
        return 1
    request = urllib.request.Request(
        f"https://api.capafy.ai/agent/agents/{args.agent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        print("CP1_MODEL=UNKNOWN", file=sys.stderr)
        return 1
    if not matches(payload, args.agent_id, args.version_id, args.model):
        print("CP1_MODEL=MISMATCH", file=sys.stderr)
        return 1
    print("CP1_MODEL=VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
