#!/usr/bin/env python3
"""Close one capafy-reel-daily effect_unknown admission fence.

capafy-reel-daily schedules one reel per target date on two Postiz integrations
(Instagram 13:00Z, X 17:00Z). capafy_reel_daily.py writes a durable
dispatch-<net>.json marker in the run directory before each Postiz upload/create,
and the wrapper writes occurrence.json (owner, occurrence, target date) before
running it.

Decision:
  - every net that has a dispatch marker reads back its own Postiz post at its slot
    -> effected; provider_receipt_id = the post ids; close via resolve_unknown_occurrence.
    "Its own" = the create postId in that marker's <slug>/<net>-receipts-v3.jsonl for the
    same slot. No create id (crash between dispatch and receipt) -> held: the integrations are
    shared, so a post in the slot's minute (even the only one) never proves ours.
  - no dispatch marker was ever written -> pre-effect proof; close via
    resolve_pre_effect_occurrence.
  - a marker without a read-back post, or any read failure -> held.

Usage: capafy_reel_fence_reconcile.py --occurrence capafy-reel-daily:<run_id> [--resolve]
       capafy_reel_fence_reconcile.py --occurrence capafy-reel-daily:<run_id> --result-hint PATH
       (passing wake: same proof, written as the runtime's private entrypoint-result.json)
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


def create_post_id(receipts_dir: Path, marker: Path, net: str, slot: str) -> str | None:
    """This marker's Postiz create postId (sibling: postiz_video.extract_post_id), else None.

    Owner-scoped admission holds the next run while this occurrence is fenced, so the slot's
    receipt is this occurrence's own create.
    """
    try:
        slug = json.loads(marker.read_text())["slug"]
        rec = json.loads((receipts_dir / slug / f"{net}-receipts-v3.jsonl").read_text())
        post_id = rec["create"][0]["postId"]
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return None
    return post_id if rec.get("scheduled_for") == slot and isinstance(post_id, str) and post_id else None


def build_proof(occurrence_id: str, run_dir: Path, *, posts_fn: Callable[[str, str], list[str]],
                receipts_dir: Path | None = None) -> dict:
    from capafy_reel_daily import BASE, slots  # noqa: PLC0415

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
    created = {m: create_post_id(receipts_dir or BASE, run_dir / f"dispatch-{m}.json", *at(m)) for m in dispatched}
    candidates = {m: posts_fn(*at(m)) for m in dispatched}
    found = {m: created[m] if created[m] and created[m] in candidates[m] else None for m in dispatched}
    if all(found.values()):
        return {**base, "verified": True, "outcome": "effected",
                "provider_receipt_id": ",".join(f"{n}:{found[n]}" for n in dispatched)}
    return {**base, "verified": False, "outcome": "held", "dispatched": dispatched, "read_back": found,
            "create_ids": created, "candidates": candidates}


def write_result_hint(proof: dict, path: Path) -> bool:
    """Report a passing wake's effect to lm_loop_run from the same official proof.

    Private, never-overwritten entrypoint-result.json (sibling: article-run-complete.py).
    A held proof writes nothing, so the wrapper exits nonzero and the fence reconciler owns it.
    """
    if proof.get("verified") is not True or proof.get("owner_id") != OWNER_ID:
        return False
    base = {"schema_version": 1, "owner_id": OWNER_ID, "occurrence_id": proof["occurrence_id"]}
    if proof.get("outcome") == "no_dispatch":  # every slot of the target date was already scheduled
        value = {**base, "kind": "life_manager_no_effect_result", "status": "verified_no_effect",
                 "effect": 0, "reason": "no_due_slot"}
    elif proof.get("outcome") == "effected":
        # Runtime receipt ids exclude ':' and ','; name the occurrence by its first read-back post
        # (build_proof already read back every dispatched post).
        from runtime.loop.lm_loop_run import SAFE_RUN_ID  # noqa: PLC0415  (the reader's own charset)

        receipt = proof["provider_receipt_id"].split(",")[0].partition(":")[2]
        if not SAFE_RUN_ID.fullmatch(receipt):
            return False
        value = {**base, "kind": "life_manager_effect_result", "status": "verified_effect", "effect": 1,
                 "provider": "postiz", "provider_receipt_id": receipt, "effect_status": "reconciled"}
    else:
        return False
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return True


def postiz_posts_at(net: str, slot: str) -> list[str]:
    """Every live post on this net's integration within a minute of the slot (any owner)."""
    from capafy_distribute_fence_reconcile import postiz_key  # noqa: PLC0415
    from capafy_reel_daily import IG_ID, TT_ID, X_ID  # noqa: PLC0415

    key = postiz_key()
    if not key:
        raise RuntimeError("postiz_key_missing")
    at = dt.datetime.fromisoformat(slot.replace("Z", "+00:00"))
    q = urllib.parse.urlencode({"startDate": (at - dt.timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                                "endDate": (at + dt.timedelta(minutes=1)).isoformat().replace("+00:00", "Z")})
    req = urllib.request.Request(f"https://api.postiz.com/public/v1/posts?{q}", headers={"Authorization": key})
    data = json.load(urllib.request.urlopen(req, timeout=60))
    integration = {"ig": IG_ID, "x": X_ID, "tt": TT_ID, "tc": TT_ID}[net]
    return [str(post["id"]) for post in (data.get("posts") if isinstance(data, dict) else data) or []
            if (post.get("integration") or {}).get("id") == integration and not post.get("deletedAt")]


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
    parser.add_argument("--result-hint", type=Path, help="passing wake: write the runtime result hint instead")
    args = parser.parse_args(argv)
    if args.result_hint is not None:
        if args.resolve:
            parser.error("--result-hint and --resolve are exclusive")
        try:
            proof = build_proof(args.occurrence, run_dir_for(args.occurrence), posts_fn=postiz_posts_at)
        except (OSError, ValueError, KeyError) as exc:
            print(f"CAPAFY_REEL_RESULT_HINT=FAIL {type(exc).__name__}:{exc}", file=sys.stderr)
            return 1
        print(json.dumps(proof, sort_keys=True))
        written = write_result_hint(proof, args.result_hint)
        print("CAPAFY_REEL_RESULT_HINT=" + ("PASS" if written else "HELD"))
        return 0 if written else 1
    try:
        state = fenced_state(args.occurrence)
        proof = build_proof(args.occurrence, run_dir_for(args.occurrence), posts_fn=postiz_posts_at)
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
