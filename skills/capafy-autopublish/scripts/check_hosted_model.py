#!/usr/bin/env python3
"""Compare a Capafy Agent's currently-confirmed hosted model against its
catalog LISTING.md's Primary Model.

Why: a catalog-wide model switch (e.g. Sonnet -> DeepSeek per Dais decision,
2026-09-28) updates LISTING.md, but a draft whose package/hosted-key were
already prepared+confirmed under the OLD model keeps that old model server
side until publish_prepare.sh is re-run for it (see CP1_AGENTIC.md
"Switching an EXISTING agent's hosted model resets Skill confirmation").
resume_draft's deterministic finish must not silently keep resaving the old
model — it must detect the mismatch and re-prepare first.

The official Agent detail's top-level `model` field is dead (always null on
a draft -- verified live 2026-09-29, agent 4973250899, isConfirmedConfigKeys=1
yet model=null). The one place the CONFIRMED hosted model actually lives is
`requiredCredentials.url_proxy[0].model` (a JSON-encoded string field), so
that is what this checks.

Usage: check_hosted_model.py --agent-id <id> --listing <LISTING.md>
Prints one of, to stdout:
  MODEL_MATCH <model_id>
  MODEL_MISMATCH <confirmed_model_id> <listing_model_id>
  MODEL_UNKNOWN <reason>
Exit 0 for MODEL_MATCH and the "nothing to compare yet" MODEL_UNKNOWN cases
(download-mode listing, or no hosted model confirmed yet -- e.g. a brand-new
draft that has never reached CP2). Exit 1 only for MODEL_MISMATCH or a
genuine lookup failure (network/token/malformed-response), so a caller can
`|| true` past a lookup failure but must act on MODEL_MISMATCH specifically.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

# Same mapping as build_config.py -- kept in sync manually (both are tiny and
# rarely change; a shared import would require packaging this as a module).
MODEL_IDS = {
    "Claude Sonnet 4.6": "anthropic/claude-sonnet-4.6",
    "Claude Sonnet 5.5": "anthropic/claude-sonnet-5.5",
    "Claude Sonnet 5": "anthropic/claude-sonnet-5",
    "DeepSeek V4.1 Flash": "deepseek/deepseek-v4.1-flash",
}


def listing_model_id(listing_path: str) -> str | None:
    text = open(listing_path, encoding="utf-8").read()
    if re.search(r"\|\s*download\s*\|\s*\$?[0-9.]+\s*\|", text, re.I):
        return None  # download-mode listing: no hosted model to compare
    m = re.search(r"Primary Model:\s*([^·\n]+)", text)
    return MODEL_IDS.get(m.group(1).strip()) if m else None


def confirmed_model_id(agent_id: str, token: str) -> str | None:
    request = urllib.request.Request(
        f"https://api.capafy.ai/agent/agents/{agent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    data = payload.get("data") if isinstance(payload, dict) and payload.get("code") == 0 else None
    if not isinstance(data, dict) or data.get("agentType") == "download":
        return None
    raw = data.get("requiredCredentials")
    creds = json.loads(raw) if isinstance(raw, str) else raw
    proxies = creds.get("url_proxy") if isinstance(creds, dict) else None
    if not isinstance(proxies, list) or not proxies:
        return None
    model = proxies[0].get("model") if isinstance(proxies[0], dict) else None
    return model if isinstance(model, str) and model else None


def cp1_confirmed(agent_id: str, token: str) -> bool:
    """True when the agent's latest version already has a saved CP1 card
    (`isConfirmedSkills`). Re-preparing such a draft resets that confirmation."""
    request = urllib.request.Request(
        f"https://api.capafy.ai/agent/agents/{agent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    data = payload.get("data") if isinstance(payload, dict) and payload.get("code") == 0 else None
    return isinstance(data, dict) and bool(data.get("isConfirmedSkills"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--listing", required=True)
    args = parser.parse_args()

    try:
        target_id = listing_model_id(args.listing)
    except OSError as exc:
        print(f"MODEL_UNKNOWN listing-unreadable:{exc}")
        return 1
    if target_id is None:
        print("MODEL_UNKNOWN listing-has-no-hosted-model")
        return 0

    token = os.environ.get("CAPAFY_ACCESS_TOKEN", "")
    if not args.agent_id.isdecimal() or not token:
        print("MODEL_UNKNOWN missing-agent-id-or-token")
        return 1
    try:
        confirmed_id = confirmed_model_id(args.agent_id, token)
    except (OSError, urllib.error.URLError, ValueError, KeyError) as exc:
        print(f"MODEL_UNKNOWN detail-fetch-failed:{type(exc).__name__}")
        return 1

    if confirmed_id is None:
        # CP2 (which confirms the hosted model) runs after CP1. A draft whose CP1 is
        # already saved must go on to CP2, not be re-prepared (2026-10-05 Hook Lab
        # v1.0.5 was re-prepared every pass and lost its CP1 each time).
        try:
            awaiting_cp2 = cp1_confirmed(args.agent_id, token)
        except (OSError, urllib.error.URLError, ValueError, KeyError):
            awaiting_cp2 = False
        print("MODEL_UNKNOWN cp1-confirmed-awaiting-cp2" if awaiting_cp2 else "MODEL_UNKNOWN no-confirmed-model-yet")
        return 0
    if confirmed_id == target_id:
        print(f"MODEL_MATCH {target_id}")
        return 0
    print(f"MODEL_MISMATCH {confirmed_id} {target_id}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
