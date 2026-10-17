#!/usr/bin/env python3
"""Close one capafy-reel-daily effect_unknown admission fence.

capafy-reel-daily schedules one reel per target date on two Postiz integrations
(Instagram 13:00Z, X 17:00Z). capafy_reel_daily.py writes a durable
dispatch-<net>.json marker in the run directory before each Postiz upload/create,
and the wrapper writes occurrence.json (owner, occurrence, target date) before
running it.

Decision:
  - every net that has a dispatch marker reads back a Postiz post at its slot
    -> effected; provider_receipt_id = the post ids; close via resolve_unknown_occurrence.
  - no dispatch marker was ever written -> pre-effect proof; close via
    resolve_pre_effect_occurrence.
  - a marker without a read-back post, or any read failure -> held.

Usage: capafy_reel_fence_reconcile.py --occurrence capafy-reel-daily:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(HERE))

OWNER_ID = "capafy-reel-daily"
STATE_ROOT = Path(os.environ.get("CAPAFY_REEL_STATE_DIR", "~/.local/state/life-manager/capafy-reel")).expanduser()


def run_dir_for(occurrence_id: str) -> Path:
    owner, _, run_id = occurrence_id.partition(":")
    if owner != OWNER_ID or not run_id or "/" in run_id:
        raise ValueError("not a capafy-reel-daily occurrence")
    return STATE_ROOT / "runs" / run_id


def build_proof(occurrence_id: str, run_dir: Path, *, posts_fn: Callable[[str, str], str | None]) -> dict:
    from capafy_reel_daily import slots  # noqa: PLC0415

    manifest_path = run_dir / "occurrence.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"occurrence manifest unreadable: {exc}") from exc
    if manifest.get("owner_id") != OWNER_ID or manifest.get("occurrence_id") != occurrence_id:
        raise ValueError("occurrence manifest is bound to another occurrence")
    day = dt.date.fromisoformat(manifest["target_date"])
    base = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id, "target_date": day.isoformat()}
    dispatched = sorted(p.stem.removeprefix("dispatch-") for p in run_dir.glob("dispatch-*.json"))  # "x", "ig-s2", ...
    if not dispatched:
        return {**base, "verified": True, "proof_type": "pre_effect", "outcome": "no_dispatch",
                "evidence_ref": str(manifest_path)}
    def at(marker: str) -> tuple[str, str]:
        net, _, slot = marker.partition("-s")
        return net, slots(day, int(slot) if slot else 1)[net]
    found = {m: posts_fn(*at(m)) for m in dispatched}
    if all(found.values()):
        return {**base, "verified": True, "outcome": "effected",
                "provider_receipt_id": ",".join(f"{n}:{found[n]}" for n in dispatched)}
    return {**base, "verified": False, "outcome": "held", "dispatched": dispatched, "read_back": found}


def postiz_post_at(net: str, slot: str) -> str | None:
    from capafy_reel_daily import IG_ID, TT_ID, X_ID  # noqa: PLC0415

    key = os.environ["LM_POSTIZ_API_KEY"]
    at = dt.datetime.fromisoformat(slot.replace("Z", "+00:00"))
    q = urllib.parse.urlencode({"startDate": (at - dt.timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                                "endDate": (at + dt.timedelta(minutes=1)).isoformat().replace("+00:00", "Z")})
    req = urllib.request.Request(f"https://api.postiz.com/public/v1/posts?{q}", headers={"Authorization": key})
    data = json.load(urllib.request.urlopen(req, timeout=60))
    integration = {"ig": IG_ID, "x": X_ID, "tt": TT_ID}[net]
    for post in (data.get("posts") if isinstance(data, dict) else data) or []:
        if (post.get("integration") or {}).get("id") == integration and not post.get("deletedAt"):
            return str(post["id"])
    return None


def fenced_state(occurrence_id: str) -> str:
    from runtime.host import resource_admission  # noqa: PLC0415

    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute("SELECT state FROM occurrences WHERE owner_id=? AND occurrence_id=? AND effect_unknown=1",
                                 (OWNER_ID, occurrence_id)).fetchone()
    if row is None:
        raise ValueError("occurrence is not an effect_unknown row")
    return str(row[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        state = fenced_state(args.occurrence)
        proof = build_proof(args.occurrence, run_dir_for(args.occurrence), posts_fn=postiz_post_at)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        print(json.dumps({"owner_id": OWNER_ID, "occurrence_id": args.occurrence, "verified": False,
                          "error": f"{type(exc).__name__}:{exc}"}))
        print("CAPAFY_REEL_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(proof, sort_keys=True))
    if not proof["verified"]:
        print("CAPAFY_REEL_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("CAPAFY_REEL_FENCE_RECONCILE=PROOF_READY")
        return 0
    from runtime.host.resource_admission import resolve_pre_effect_occurrence, resolve_unknown_occurrence  # noqa: PLC0415
    if proof.get("proof_type") == "pre_effect":
        closed = resolve_pre_effect_occurrence(OWNER_ID, args.occurrence, pre_effect_readback=lambda: proof,
                                               expected_state=state)
    else:
        closed = resolve_unknown_occurrence(OWNER_ID, args.occurrence, official_readback=lambda: proof,
                                            expected_state=state)
    print("CAPAFY_REEL_FENCE_RECONCILE=" + ("PASS" if closed else "FAIL reason=admission_refused_close"))
    return 0 if closed else 1


if __name__ == "__main__":
    raise SystemExit(main())
