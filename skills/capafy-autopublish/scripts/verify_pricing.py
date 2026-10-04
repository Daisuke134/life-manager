#!/usr/bin/env python3
"""Compare a Capafy Agent's currently-saved subscription billing rows against its
catalog LISTING.md's pricing table.

Why: the 2026-09-29 Hook Lab reprice (agent 8123079349) was approved and went
live (v1.0.4) carrying the OLD prices (day $1.99/week $4.99/month $9.99, no
year row) even though LISTING.md's pricing table already targeted day $3.99/
week $9.99/month $19.99/year $99.99. Nothing in the publish pipeline ever
compared the saved billing rows to the LISTING target -- publish_finish.sh's
FINAL VERIFY only reads platform_status/is_confirmed_skills/is_confirmed_
config_keys/audit_status/package_uploaded (see its step [7]), and
verify_cp1_model.py/check_hosted_model.py only ever compared the hosted MODEL,
never price/cap/trial. The CP1_AGENTIC.md driver's own success signal is a
green 価格設定 tab + is_confirmed_skills -- a tab that is already green from a
stale prior save (old prices) passes that gate without ever being re-entered.

This fills that gap the same way check_hosted_model.py/verify_cp1_model.py
already verify the hosted model: a direct read of the owner-side
`GET /agent/agents/{agentId}` detail (the same endpoint, NOT the normalized
`publish-remote-status`, which deliberately strips billing -- see
PUBLISHING_RUNBOOK.md and the publisher's own API docs, "Billing ... fields
may still occur in raw backend details, but the current publisher runtime
does not consume them"). Verified live 2026-10-04 against agent 8123079349:
`data.billings[]` carries `cycleType`/`cyclePrice`/`cycleMaxMessageCount`/
`supportFreeTrial`/`freeTrialHours`/`freeTrialCount` per plan row -- exactly
what is needed to reconcile cycle, price, cap, and trial.

Usage: verify_pricing.py --agent-id <id> --listing <LISTING.md>
Prints one of, to stdout:
  PRICING_MATCH <n_plans>
  PRICING_MISMATCH <details>
  PRICING_UNKNOWN <reason>
Exit 0 for PRICING_MATCH and the "nothing to compare yet" PRICING_UNKNOWN
cases (download-mode listing, or no billings saved yet -- e.g. a brand-new
draft that has never reached CP1's price save). Exit 1 for PRICING_MISMATCH
or a genuine lookup failure, so a caller can gate submission on this exact
exit code the same way it already gates on verify_cp1_model.py.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

NO_FREE_TRIAL = re.compile(r"no[\s_-]+free[\s_-]+trial", re.I)
FREE_TRIAL = re.compile(r"free[\s_-]+trial\s+(\d+)\s*h\s*/\s*(\d+)\s*requests?", re.I)


def listing_plans(listing_path: str) -> list[dict] | None:
    """[{cycle, price, cap, trial}] parsed the same way build_config.py does,
    or None for a download-mode listing (no subscription plans to compare)."""
    text = open(listing_path, encoding="utf-8").read()
    if re.search(r"\|\s*download\s*\|\s*\$?[0-9.]+\s*\|", text, re.I):
        return None
    plans = []
    for row in re.findall(
        r"\|\s*(day|week|month|year)\s*\|\s*\$?([0-9.]+)\s*\|\s*([0-9]+)\s*\|\s*([^|]+)\|",
        text, re.I,
    ):
        cyc, price, cap, trial = row
        trial = trial.strip()
        trial_match = FREE_TRIAL.fullmatch(trial)
        if trial_match:
            trial_value = {"hours": int(trial_match.group(1)), "requests": int(trial_match.group(2))}
        elif NO_FREE_TRIAL.fullmatch(trial):
            trial_value = None
        else:
            trial_value = None
        plans.append({"cycle": cyc.lower(), "price": price, "cap": cap, "trial": trial_value})
    return plans


def confirmed_billings(agent_id: str, token: str) -> list[dict]:
    request = urllib.request.Request(
        f"https://api.capafy.ai/agent/agents/{agent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    data = payload.get("data") if isinstance(payload, dict) and payload.get("code") == 0 else None
    billings = data.get("billings") if isinstance(data, dict) else None
    return [b for b in billings if isinstance(b, dict)] if isinstance(billings, list) else []


def _billing_trial_matches(target_trial, billing: dict) -> bool:
    supports = bool(billing.get("supportFreeTrial"))
    if target_trial is None:
        return not supports
    return (
        supports
        and billing.get("freeTrialHours") == target_trial["hours"]
        and billing.get("freeTrialCount") == target_trial["requests"]
    )


def find_mismatches(plans: list[dict], billings: list[dict]) -> list[str]:
    by_cycle = {
        b.get("cycleType"): b
        for b in billings
        if b.get("billingMode") == "subscription" and b.get("cycleType")
    }
    mismatches = []
    for plan in plans:
        billing = by_cycle.get(plan["cycle"])
        if billing is None:
            mismatches.append(f"{plan['cycle']}: missing (target price=${plan['price']})")
            continue
        actual_price = billing.get("cyclePrice")
        if actual_price is None or f"{float(actual_price):g}" != f"{float(plan['price']):g}":
            mismatches.append(f"{plan['cycle']}: price target=${plan['price']} actual={actual_price}")
        actual_cap = billing.get("cycleMaxMessageCount")
        if str(actual_cap) != str(int(plan["cap"])):
            mismatches.append(f"{plan['cycle']}: cap target={plan['cap']} actual={actual_cap}")
        if not _billing_trial_matches(plan["trial"], billing):
            mismatches.append(f"{plan['cycle']}: trial target={plan['trial']} actual_supportFreeTrial={billing.get('supportFreeTrial')}")
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--listing", required=True)
    args = parser.parse_args()

    try:
        plans = listing_plans(args.listing)
    except OSError as exc:
        print(f"PRICING_UNKNOWN listing-unreadable:{exc}")
        return 1
    if plans is None:
        print("PRICING_UNKNOWN listing-has-no-subscription-plans")
        return 0
    if not plans:
        print("PRICING_UNKNOWN listing-has-no-pricing-rows")
        return 0

    token = os.environ.get("CAPAFY_ACCESS_TOKEN", "")
    if not args.agent_id.isdecimal() or not token:
        print("PRICING_UNKNOWN missing-agent-id-or-token")
        return 1
    try:
        billings = confirmed_billings(args.agent_id, token)
    except (OSError, urllib.error.URLError, ValueError, KeyError) as exc:
        print(f"PRICING_UNKNOWN detail-fetch-failed:{type(exc).__name__}")
        return 1

    if not billings:
        print("PRICING_UNKNOWN no-billings-saved-yet")
        return 0

    mismatches = find_mismatches(plans, billings)
    if mismatches:
        print(f"PRICING_MISMATCH {'; '.join(mismatches)}")
        return 1
    print(f"PRICING_MATCH {len(plans)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
