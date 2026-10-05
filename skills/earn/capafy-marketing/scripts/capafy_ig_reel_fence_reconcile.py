#!/usr/bin/env python3
"""Close one life-manager-capafy-ig effect_unknown admission fence.

Same decision shape as capafy_distribute_fence_reconcile.py (one effected /
no-effect proof per occurrence, never a guess). life-manager-capafy-ig's only
external effect is posting a Capafy reel to Instagram @capafy.hooklab through
Postiz (``CAPAFY_IG_POSTIZ_INTEGRATION_ID``); it never posts directly. The
official readback is therefore Postiz's own post listing for that integration:

  - A Postiz post for CAPAFY_IG_POSTIZ_INTEGRATION_ID inside
    [queued_at, queued_at + MAX_RUN_SECONDS] proves the effect happened: close
    as effected (the Postiz post id is the receipt).
  - No such post AND enough time has passed proves no effect: close as
    no-effect, citing the Postiz listing.
  - Any readback failure, a missing integration id, or not enough time yet
    stays fenced.

Usage:
    python3 capafy_ig_reel_fence_reconcile.py --occurrence life-manager-capafy-ig:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "life-manager-capafy-ig"
# capafy-ig-reel's hard run-with-timeout (1200s + 10s grace) plus a Postiz
# listing-indexing buffer before a clean listing is trusted as "no effect".
MAX_RUN_SECONDS = 1210
NO_EFFECT_MIN_AGE_SECONDS = MAX_RUN_SECONDS + 900


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, dt.datetime]:
    """Read (state, queued_at) of the fenced row without mutating the ledger."""
    from runtime.host import resource_admission

    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            """SELECT state, queued_at FROM occurrences
                 WHERE owner_id=? AND occurrence_id=? AND effect_unknown=1""",
            (owner_id, occurrence_id),
        ).fetchone()
    if row is None or row[1] is None:
        raise ValueError("occurrence is not an effect_unknown row")
    return str(row[0]), dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)


def postiz_key(credentials_path: Path | None = None) -> str:
    """Resolve Postiz from runtime env, then the private credential SSOT."""
    value = os.environ.get("POSTIZ_API_KEY") or os.environ.get("LM_POSTIZ_API_KEY")
    if value:
        return value
    path = credentials_path or Path.home() / ".local/share/anicca/credentials.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("credentials")
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    if not isinstance(rows, list):
        return ""
    matches = [
        str(row.get("api_key") or "").strip()
        for row in rows
        if isinstance(row, dict) and row.get("service") == "postiz"
        and str(row.get("api_key") or "").strip()
    ]
    return matches[0] if len(matches) == 1 else ""


def read_ig_posts(start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    key = postiz_key()
    if not key:
        return {"ok": False, "reason": "postiz_key_missing"}
    try:
        sys.path.insert(0, str(REPO_ROOT / "skills/earn/marketing-engine/publish"))
        from postiz_adapter import HttpPostizClient  # noqa: PLC0415
        posts = HttpPostizClient(key).list_posts(start, end)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"postiz_readback_failed:{type(exc).__name__}"}
    return {"ok": True, "posts": posts}


def build_proof(occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                posts: dict[str, Any], integration_id: str) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    if not integration_id:
        proof["reason"] = "integration_id_missing"
        return proof
    if not posts.get("ok"):
        proof["reason"] = posts.get("reason")
        return proof
    hits = [
        post for post in posts["posts"]
        if str((post.get("integration") or {}).get("id") or "") == integration_id
    ]
    if hits:
        proof.update(verified=True, effected=True,
                     provider_receipt_id=f"postiz:{hits[0].get('id')}",
                     proof_kind="official_postiz_post_listing",
                     checked_at=now.isoformat(timespec="seconds"))
        return proof
    age = (now - queued_at).total_seconds()
    if age <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof
    proof.update(verified=True, effected=False,
                 provider_receipt_id=f"postiz-listing-empty:{integration_id}:{queued_at.isoformat()}",
                 proof_kind="official_postiz_post_listing",
                 checked_at=now.isoformat(timespec="seconds"))
    return proof


def reconcile(occurrence_id: str, *, resolve: bool = False, now: dt.datetime | None = None,
              fenced_row_fn=fenced_row, posts_fn=read_ig_posts, resolve_fn=None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    integration_id = os.environ.get("CAPAFY_IG_POSTIZ_INTEGRATION_ID", "")
    state, queued_at = fenced_row_fn(OWNER_ID, occurrence_id)
    end = queued_at + dt.timedelta(seconds=MAX_RUN_SECONDS)
    proof = build_proof(occurrence_id, queued_at, now=now, posts=posts_fn(queued_at, end),
                        integration_id=integration_id)
    result = {**proof, "admission_state": state}
    if not proof.get("verified") or not resolve:
        return result
    if resolve_fn is None:
        from runtime.host.resource_admission import resolve_unknown_occurrence
        resolve_fn = resolve_unknown_occurrence
    result["closed"] = resolve_fn(OWNER_ID, occurrence_id,
                                  official_readback=lambda: proof, expected_state=state)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reconcile(args.occurrence, resolve=args.resolve)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"owner_id": OWNER_ID, "occurrence_id": args.occurrence,
                          "verified": False, "error": f"{type(exc).__name__}:{exc}"}))
        print("CAPAFY_IG_REEL_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str))
    if not result.get("verified"):
        print("CAPAFY_IG_REEL_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("CAPAFY_IG_REEL_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("CAPAFY_IG_REEL_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("CAPAFY_IG_REEL_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
