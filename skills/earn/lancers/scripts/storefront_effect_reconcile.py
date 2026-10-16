#!/usr/bin/env python3
"""Reconcile one Lancers storefront fence from an official roster readback.

A storefront wake can only (a) align the canonical listing to the product file,
(b) archive superseded listings, (c) create one catalogue listing, (d) create one of the
product's two portfolios, (e) update the profile. (a), (b) and (e) converge on a fixed
target; (c) and (d) create new provider objects. So whatever an interrupted wake did is
fully accounted for when the live official state shows: the seller's listing roster equals
the owner ledger (``listing.json``), the canonical listing matches the product, every
superseded listing is archived, and each portfolio exists exactly once with its known id.
Then nothing the occurrence did is orphaned or can be duplicated by the next wake.

The host pre-effect marker cannot prove this: a wake that reached the browser never
writes it, and the marker path is the occurrence id while the claimant run differs.
Any mismatch or unreadable readback leaves the occurrence fenced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.host.resource_admission import resolve_unknown_occurrence  # noqa: E402


OWNER_ID = "lancers-revenue-storefront"
BROWSER_IDENTITY = "lancers:dais"
BROWSER_TARGET_OWNER = "lancers-revenue-browser"
WITH_BROWSER = ROOT / "skills/browser/with-browser.sh"
OFFER = SCRIPT.parent / "storefront_offer.py"
DEFAULT_PRODUCT = SCRIPT.parents[1] / "products" / "monthly-sns-content-ops-v1.json"
PORTFOLIO_KEYS = ("portfolio", "software_portfolio")


class Held(RuntimeError):
    pass


def browser_readback(state_root: Path, product: Path, *,
                     runner: Callable[..., subprocess.CompletedProcess] | None = None) -> dict:
    environment = os.environ.copy()
    environment.update({
        "BROWSER_WAIT_SECONDS": "0",
        "AI_ENSURE_PROVISION_BROWSER": "/dev/null",
        "LIFE_MANAGER_BROWSER_IDENTITY": BROWSER_IDENTITY,
        "LIFE_MANAGER_BROWSER_TARGET_OWNER": BROWSER_TARGET_OWNER,
    })
    command = ["bash", str(WITH_BROWSER), BROWSER_IDENTITY, "--", sys.executable, str(OFFER),
               "--roster-readback", "--product", str(product),
               "--state-path", str(state_root / "application.json")]
    try:
        completed = (runner or subprocess.run)(
            command, cwd=ROOT, env=environment, capture_output=True, text=True,
            timeout=600, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise Held("official_roster_unavailable") from error
    records = []
    for line in (completed.stdout or "").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    if (completed.returncode != 0 or len(records) != 1 or records[0].get("ok") is not True
            or records[0].get("action") != "roster_readback"):
        raise Held("official_roster_unavailable")
    return records[0]


def official_proof(occurrence_id: str, state_root: Path, product_path: Path, *,
                   runner=None) -> dict:
    try:
        ledger = json.loads((state_root / "listing.json").read_text(encoding="utf-8"))
        product = json.loads(product_path.read_text(encoding="utf-8"))
        expected_ids = {str(ledger["listing_external_id"])} | {
            str(row["listing_external_id"]) for row in ledger.get("catalog_listings", {}).values()}
        superseded = [str(value) for value in product["superseded_listing_ids"]]
        portfolios = {key: str(product[key]["external_id"]) for key in PORTFOLIO_KEYS}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise Held("owner_ledger_invalid") from error
    live = browser_readback(state_root, product_path, runner=runner)
    listing_ids = live.get("listing_ids")
    if (not isinstance(listing_ids, list) or len(set(listing_ids)) != len(listing_ids)
            or set(map(str, listing_ids)) != expected_ids):
        raise Held("official_listing_roster_differs_from_ledger")
    if (live.get("listing_external_id") != ledger["listing_external_id"]
            or live.get("aligned") is not True or live.get("mismatched_fields")):
        raise Held("canonical_listing_not_aligned")
    if live.get("superseded_status") != {listing_id: "archived" for listing_id in superseded}:
        raise Held("superseded_listing_not_archived")
    if live.get("portfolio_external_ids") != portfolios:
        raise Held("portfolio_roster_differs_from_product")
    fingerprint = json.dumps({"listing_ids": sorted(expected_ids), "portfolios": portfolios,
                              "superseded": superseded}, sort_keys=True, separators=(",", ":"))
    return {
        "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
        "proof_type": "official_roster_matches_owner_ledger",
        "provider_receipt_id": "lancers-storefront-roster:"
                               + hashlib.sha256(fingerprint.encode()).hexdigest(),
    }


def main(argv: list[str] | None = None, *, runner=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--state-root", type=Path, default=Path("~/.local/state/anicca/lancers"))
    parser.add_argument("--product", type=Path, default=DEFAULT_PRODUCT)
    args = parser.parse_args(argv)
    base = {"owner_id": OWNER_ID, "occurrence_id": args.occurrence}
    try:
        if not args.occurrence.startswith(f"{OWNER_ID}:"):
            raise Held("occurrence_owner_mismatch")
        proof = official_proof(args.occurrence, args.state_root.expanduser().resolve(),
                               args.product, runner=runner)
    except Held as error:
        print(json.dumps({**base, "state": "HELD", "verified": False, "reason": str(error),
                          "next_action": "keep_fenced_until_official_roster_matches"},
                         sort_keys=True))
        return 1
    resolved = args.resolve and resolve_unknown_occurrence(
        OWNER_ID, args.occurrence, official_readback=lambda: proof, expected_state="claimed")
    state = "RECONCILED" if resolved else ("HELD" if args.resolve else "PROOF_READY")
    print(json.dumps({**proof, "verified": state != "HELD", "state": state,
                      "resolved": bool(resolved)}, sort_keys=True))
    return 0 if state != "HELD" else 1


if __name__ == "__main__":
    raise SystemExit(main())
