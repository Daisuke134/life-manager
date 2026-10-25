#!/usr/bin/env python3
"""Reconcile one Coconala storefront fence, by exact pre-effect proof or official roster readback.

The exact pre-effect proof (``storefront_pre_effect_reconcile.py``) needs a stdout pass
line carrying ``runtime_run_id``/``runtime_occurrence_id``; releases before 2026-10-14
never wrote those fields, so their fences can never close that way. For those, this adapter
brackets the occurrence between two official readbacks of the seller catalogue:

* before: the newest official inventory the owner itself recorded before the claimant run
  started (``evidence/<pass>/official-inventory.json``);
* after: a live read of the official seller list through the leased ``coconala:kosuke``
  browser, now.

Every service id, state (公開/非公開/下書き …) and price must be identical, and no owner
effect may have been recorded since the before snapshot (effect ledger, write-ahead field
intents, retire intents). Then nothing the occurrence could have done to a listing survives
on the provider. Any difference, gap or unreadable source leaves the occurrence fenced.

ponytail: an unledgered blank draft would not appear if the seller list omits drafts; such a
draft is never buyer-visible and cannot republish anything, so it does not need this fence.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


SCRIPT = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT.parent
ROOT = SCRIPT.parents[4]
for entry in (SCRIPT_DIR, ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import storefront_pre_effect_reconcile as pre  # noqa: E402
from runtime.host.resource_admission import resolve_unknown_occurrence  # noqa: E402


OWNER_ID = pre.OWNER_ID
BROWSER_IDENTITY = "coconala:kosuke"
WITH_BROWSER = ROOT / "skills/browser/with-browser.sh"
GIG_VAULT = Path.home() / ".cloak/vault/gig-daily-driver/auth-state.json"
MARKER = "STOREFRONT_ROSTER "
DEFAULT_RUNTIME = Path("~/.local/state/life-manager/coconala/storefront")
DEFAULT_STORE = Path(os.environ.get("GIG_STATE_DIR", str(Path.home() / "gig"))) / "storefront-direct"


class Held(RuntimeError):
    pass


def _roster(services: object) -> dict[str, tuple]:
    if not isinstance(services, list) or not services:
        raise Held("official_roster_invalid")
    roster = {}
    for row in services:
        service_id = str(row.get("service_id") or "") if isinstance(row, dict) else ""
        if not service_id.isdigit() or service_id in roster:
            raise Held("official_roster_invalid")
        roster[service_id] = (row.get("state"), row.get("price_jpy"))
    return roster


def pre_occurrence_snapshot(store: Path, started: float) -> tuple[Path, dict, float]:
    """The newest official inventory the owner recorded strictly before the claimant run."""
    best = None
    for path in (store / "evidence").glob("storefront-direct-*/official-inventory.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            observed = pre._epoch(value["observed_at"])
        except (OSError, ValueError, KeyError, TypeError, pre.EvidenceError):
            continue
        if observed < started and (best is None or observed > best[2]):
            best = (path, value, observed)
    if best is None:
        raise Held("pre_occurrence_snapshot_missing")
    if best[1].get("service_count") != len(best[1].get("services") or []):
        raise Held("pre_occurrence_snapshot_invalid")
    _roster(best[1]["services"])
    return best


def _epoch_field(value: object, field: str) -> float:
    epoch = value.get(field) if isinstance(value, dict) else None
    if not isinstance(epoch, (int, float)) or isinstance(epoch, bool):
        raise Held("owner_ledger_invalid")
    return float(epoch)


def assert_owner_quiet_since(store: Path, since: float) -> None:
    """No owner effect, write-ahead intent or retire attempt was recorded after ``since``."""
    try:
        effects = (store / "effects.jsonl").read_text(encoding="utf-8").splitlines()
        if any(_epoch_field(json.loads(line), "accepted_at_epoch") >= since
               for line in effects if line.strip()):
            raise Held("effect_ledger_after_snapshot")
        for path in (store / "effect-intents").glob("*.json"):
            if _epoch_field(json.loads(path.read_text(encoding="utf-8")), "prepared_at_epoch") >= since:
                raise Held("write_ahead_intent_after_snapshot")
        for path in store.glob("retire-intent-*.json"):
            if _epoch_field(json.loads(path.read_text(encoding="utf-8")), "attempted_at_epoch") >= since:
                raise Held("retire_intent_after_snapshot")
    except (OSError, ValueError) as error:
        raise Held("owner_ledger_invalid") from error


def browser_readback(*, runner: Callable[..., subprocess.CompletedProcess] | None = None) -> dict:
    """Read the live official seller list once, inside one leased-and-released browser call."""
    environment = os.environ.copy()
    environment["BROWSER_WAIT_SECONDS"] = "0"
    environment["AI_ENSURE_PROVISION_BROWSER"] = "/dev/null"
    environment["AI_ENSURE_BROWSER"] = "/dev/null"
    # The fence reconciler has no Coconala session env (same fix as coconala_reply_effect_reconcile).
    environment.setdefault("CLOAK_SESSION_VAULT_FILE", str(GIG_VAULT))
    environment.setdefault("CLOAK_BROWSER_OWNER", "gig-storefront-reconcile")
    command = ["bash", str(WITH_BROWSER), BROWSER_IDENTITY, "--",
               sys.executable, str(SCRIPT), "--readback-child"]
    try:
        completed = (runner or subprocess.run)(
            command, cwd=ROOT, env=environment, capture_output=True, text=True,
            timeout=600, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise Held("official_roster_unavailable") from error
    records = [line[len(MARKER):] for line in (completed.stdout or "").splitlines()
               if line.startswith(MARKER)]
    if completed.returncode != 0 or len(records) != 1:
        raise Held("official_roster_unavailable")
    record = json.loads(records[0])
    if record.get("status") != "verified" or not isinstance(record.get("content_sha256"), str):
        raise Held("official_roster_unavailable")
    return record


def _child() -> int:
    import listing_inventory
    from cdp_nav_snapshot import hidden_page_target

    async def collect() -> list[dict]:
        async with hidden_page_target(listing_inventory.LISTINGS_URL) as ws_url:
            return await listing_inventory.collect_live(ws_url=ws_url)

    try:
        observed = listing_inventory.write_storefront_observation(
            asyncio.run(collect()),
            output_path=DEFAULT_RUNTIME.expanduser() / "reconciliation" / "official-roster-latest.json",
        )
        record = {"status": "verified", **observed}
    except Exception as error:  # every failure is an unknown readback, never an empty roster
        record = {"status": "unknown", "reason": type(error).__name__}
    print(MARKER + json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


def _claimant_runs(rows: list[dict], occurrence_id: str) -> tuple[float, list[str]]:
    """Earliest claimant start and every claimant run id for one occurrence.

    A wake retried after an in-run defer leaves several claimant terminals; the
    roster bracket covers them all when it opens before the earliest one starts.
    """
    run_ids = sorted({
        row.get("run_id") for row in rows
        if row.get("owner_id") == OWNER_ID and row.get("phase") == "report"
        and row.get("occurrence_id") == occurrence_id
        # Same exclusion as the exact proof: an admission defer never dispatched the owner.
        and not (str(row.get("error_class") or "").startswith("host_admission_deferred:")
                 and (row.get("effect_status") == "not_applicable"
                      or (row.get("status") == "blocked"
                          and row.get("failure_layer") == "admission"
                          and row.get("exit_code") == 75)))
    }, key=str)
    if not run_ids or not all(isinstance(run_id, str) and run_id for run_id in run_ids):
        raise pre.EvidenceError("runtime_occurrence_event_invalid")
    starts = []
    for run_id in run_ids:
        start = [row for row in rows if row.get("run_id") == run_id and row.get("phase") == "execute"]
        if len(start) != 1:
            raise pre.EvidenceError("runtime_event_phase_invalid")
        starts.append(pre._epoch(start[0]["timestamp"]))
    return min(starts), run_ids


def official_proof(occurrence_id: str, runtime: Path, store: Path, *,
                   runner=None) -> tuple[dict, dict]:
    started, run_ids = _claimant_runs(pre._read_runtime_events(runtime), occurrence_id)
    run_id = run_ids[-1]
    path, before, observed = pre_occurrence_snapshot(store, started)
    assert_owner_quiet_since(store, observed)
    live = browser_readback(runner=runner)
    if _roster(live.get("services")) != _roster(before["services"]):
        raise Held("official_roster_changed_since_snapshot")
    proof = {
        "owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
        "proof_type": "official_roster_unchanged_since_pre_occurrence_snapshot",
        "provider_receipt_id": f"coconala-storefront-roster:{live['content_sha256']}",
    }
    receipt = {
        **proof, "run_id": run_id, "claimant_run_ids": run_ids,
        "before": {"path": str(path), "observed_at": before["observed_at"]},
        "after": {"observed_at": live.get("observed_at"), "service_count": live.get("service_count")},
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    return proof, receipt


def main(argv: list[str] | None = None, *, runner=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrence")
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--state-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--readback-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.readback_child:
        return _child()
    if not args.occurrence:
        parser.error("--occurrence is required")
    runtime = args.state_root.expanduser().resolve()
    store = args.store.expanduser().resolve()
    base = {"owner_id": OWNER_ID, "occurrence_id": args.occurrence}

    exact = pre.reconcile(
        state_root=runtime, stdout_log=runtime / "logs" / "launchd.out.log",
        occurrence_id=args.occurrence, resolve=args.resolve,
    ) if args.occurrence.startswith(pre.OCCURRENCE_PREFIX) else {"state": "HELD"}
    if exact["state"] in {"PROOF_READY", "RECONCILED"}:
        print(json.dumps({**exact, **base, "verified": True}, ensure_ascii=False, sort_keys=True))
        return 0

    try:
        pre._validate_occurrence_id(args.occurrence)
        expected_state = pre._admission_state(
            pre.admission_root() / "admission-v2.sqlite3", args.occurrence)
        proof, receipt = official_proof(args.occurrence, runtime, store, runner=runner)
    except (Held, pre.EvidenceError, OSError, ValueError) as error:
        print(json.dumps({**base, "state": "HELD", "verified": False, "reason": str(error),
                          "pre_effect_reason": exact.get("reason"),
                          "next_action": "keep_fenced_until_official_roster_matches"},
                         ensure_ascii=False, sort_keys=True))
        return 1
    receipt_path = runtime / "reconciliation" / f"official-roster-{receipt['run_id']}.json"
    resolved = False
    if args.resolve:
        resolved = resolve_unknown_occurrence(
            OWNER_ID, args.occurrence, official_readback=lambda: proof,
            expected_state=expected_state,
        )
    pre._atomic_json(receipt_path, {**receipt, "resolved": resolved})
    state = "RECONCILED" if resolved else ("HELD" if args.resolve else "PROOF_READY")
    print(json.dumps({**proof, "verified": state != "HELD", "state": state, "resolved": resolved,
                      "receipt_path": str(receipt_path)}, ensure_ascii=False, sort_keys=True))
    return 0 if state != "HELD" else 1


if __name__ == "__main__":
    raise SystemExit(main())
