#!/usr/bin/env python3
"""Close one capafy-ig-marketing-daily effect_unknown admission fence.

capafy-ig-marketing-daily posts Reels through the shared instagrapi poster
(``skills/earn/marketing-engine/poster.py``), not the Graph API and never
direct CDP. The official readback here is therefore the account's own
authenticated media list -- the same instagrapi session (loaded read-only via
``Client.load_settings``) the poster and ``ig_metrics.py`` already use --
never a fresh login and never a mutating call.

Decision (2026-09-26 CrowdWorks incident: a reconciler falsely closed 179/180
fences that had actually executed -- this adapter never repeats that):
  - A Reel whose ``taken_at`` falls inside [queued_at, queued_at + max run
    duration] proves the effect happened: append the missing ledger row (the
    Reel URL is the receipt) and close the fence as effected.
  - Zero Reels in that window AND the listing is provably complete (the full
    account history was fetched, so it either passes back before queued_at or
    the account has fewer posts than that) AND enough time has passed (max
    run duration + a posting-processing delay) proves no effect: close as
    no-effect, citing the listing readback as the receipt.
  - Any readback failure (dead/absent session, exception) is inconclusive:
    stays fenced.
  - Not enough time has passed yet: stays fenced (never guess early).

Usage:
    python3 capafy_ig_fence_reconcile.py --occurrence capafy-ig-marketing-daily:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "capafy-ig-marketing-daily"
# Generous ceiling for one agent-driven render+post pass (video render, TTS,
# instagrapi upload). If a Reel lands inside this window of queued_at, the
# occurrence dispatched it.
MAX_RUN_SECONDS = 5400
# Extra buffer after MAX_RUN_SECONDS before a clean listing is trusted as
# "no effect" -- IG's own media-list can lag a publish by a few minutes.
POST_PROCESSING_DELAY_SECONDS = 1800
NO_EFFECT_MIN_AGE_SECONDS = MAX_RUN_SECONDS + POST_PROCESSING_DELAY_SECONDS  # 2h

ACCOUNTS_PATH = Path("~/.cloak/clip-accounts-capafy.json").expanduser()
IG_LEDGER_PATH = Path(
    "~/.local/state/life-manager/state/capafy-marketing-ig-ledger.jsonl"
).expanduser()


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
    queued = dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)
    return str(row[0]), queued


def resolve_handle(accounts_path: Path) -> str | None:
    """Pick the same 'active' account clip-accounts-capafy.json resolution the
    bash helper (account_state.sh -> resolve_ig_handle) uses."""
    try:
        accounts = json.loads(accounts_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(accounts, list):
        return None
    usable = []
    for account in accounts:
        if not isinstance(account, Mapping):
            continue
        status = str(account.get("status") or "").lower()
        if not (status.startswith("ready") or status.startswith("warming")
                or status.endswith("_ready")):
            continue
        if any(word in status for word in ("poison", "frozen", "blocked")):
            continue
        if any(account.get(key) for key in
               ("poisoned", "poisoned_at", "frozen_at", "blocked_at")):
            continue
        if not account.get("handle"):
            continue
        usable.append(account)
    if not usable:
        return None
    return str(usable[-1]["handle"])


def read_media(handle: str, settings_path: Path,
                client_factory: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Read-only authenticated readback of the account's own posted media.

    Never logs in and never relogs in -- a dead/absent saved session is a
    readback failure, not a license to authenticate a different way. Returns
    ``{"ok": True, "media": [{"code","taken_at"}, ...]}`` (the whole account
    history, i.e. provably complete) or ``{"ok": False, "reason": ...}``.
    """
    if not settings_path.is_file():
        return {"ok": False, "reason": "no_saved_session"}
    try:
        if client_factory is None:
            from instagrapi import Client
            client_factory = Client
        client = client_factory()
        client.delay_range = [1, 3]
        client.load_settings(str(settings_path))
        account = client.account_info()
        username = getattr(account, "username", None)
        if username is None and isinstance(account, Mapping):
            username = account.get("username")
        if not isinstance(username, str) or username.casefold() != handle.casefold():
            return {"ok": False, "reason": "authenticated_identity_mismatch"}
        user_id = getattr(account, "pk", None)
        if user_id is None and isinstance(account, Mapping):
            user_id = account.get("pk")
        if not user_id:
            return {"ok": False, "reason": "authenticated_user_id_unavailable"}
        medias = client.user_medias(user_id, amount=0)
    except Exception as exc:  # noqa: BLE001 - any read failure keeps the fence
        return {"ok": False, "reason": f"readback_failed:{type(exc).__name__}"}
    rows: list[dict[str, Any]] = []
    for media in medias:
        taken_at = getattr(media, "taken_at", None)
        code = getattr(media, "code", None)
        if taken_at is None or not code:
            continue
        if taken_at.tzinfo is None:
            taken_at = taken_at.replace(tzinfo=dt.timezone.utc)
        rows.append({"code": str(code), "taken_at": taken_at})
    return {"ok": True, "media": rows}


def build_proof(owner_id: str, occurrence_id: str, queued_at: dt.datetime,
                 media_readback: Mapping[str, Any], *,
                 now: dt.datetime | None = None) -> tuple[dict[str, Any], str | None]:
    """Turn one media readback into a resolve_unknown_occurrence-shaped proof.

    Returns ``(proof, reel_url_or_none)``. ``reel_url`` is set only when the
    proof is an "effected" close, so the caller can append the ledger row.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    proof: dict[str, Any] = {
        "owner_id": owner_id, "occurrence_id": occurrence_id, "verified": False,
        "queued_at": queued_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if not media_readback.get("ok"):
        proof["reason"] = str(media_readback.get("reason") or "readback_failed")
        return proof, None
    window_end = queued_at + dt.timedelta(seconds=MAX_RUN_SECONDS)
    media = media_readback.get("media") or []
    hits = [m for m in media if queued_at <= m["taken_at"] <= window_end]
    if hits:
        hit = min(hits, key=lambda m: m["taken_at"])
        reel_url = f"https://www.instagram.com/reel/{hit['code']}/"
        proof.update(
            verified=True, effected=True, provider_receipt_id=reel_url,
            proof_kind="official_instagram_authenticated_media_listing",
            checked_at=now.isoformat(timespec="seconds"),
        )
        return proof, reel_url
    age_seconds = (now - queued_at).total_seconds()
    if age_seconds <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age_seconds)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof, None
    proof.update(
        verified=True, effected=False,
        provider_receipt_id=f"instagram-media-listing-no-reel-in-window:{proof['queued_at']}",
        proof_kind="official_instagram_authenticated_media_listing",
        checked_at=now.isoformat(timespec="seconds"),
    )
    return proof, None


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def append_ledger_row_if_missing(ledger_path: Path, occurrence_id: str,
                                  handle: str, reel_url: str,
                                  taken_at: dt.datetime) -> bool:
    """Append the missing ledger row for a fence-reconciled Reel, once.

    Only fields this reconciler can prove (reel_url, handle, taken_at,
    provenance) are written; the original agent_id/caption/hook were lost
    with the dead run and are never fabricated.
    """
    if ledger_path.is_file():
        with ledger_path.open(encoding="utf-8") as source:
            for line in source:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("reel_url") == reel_url:
                    return False
    _append_jsonl(ledger_path, {
        "platform": "ig",
        "reel_url": reel_url,
        "handle": handle,
        "taken_at": taken_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "occurrence_id": occurrence_id,
        "source": "capafy_ig_fence_reconcile",
        "agent_id": None,
        "listing_name": None,
        "caption": None,
        "hook": None,
        "note": "recovered from official Instagram media-listing readback; "
                "original run died before it could report agent_id/caption/hook",
    })
    return True


def reconcile(
    occurrence_id: str, *,
    accounts_path: Path = ACCOUNTS_PATH,
    handle: str | None = None,
    settings_path: Path | None = None,
    ledger_path: Path = IG_LEDGER_PATH,
    fenced_row_fn: Callable[[str, str], tuple[str, dt.datetime]] = fenced_row,
    read_media_fn: Callable[..., dict[str, Any]] = read_media,
    resolve_fn: Callable[..., bool] | None = None,
    now: dt.datetime | None = None,
    resolve: bool = False,
) -> dict[str, Any]:
    state, queued_at = fenced_row_fn(OWNER_ID, occurrence_id)
    resolved_handle = handle or resolve_handle(accounts_path)
    if not resolved_handle:
        return {"owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": False,
                "reason": "active_ig_handle_unresolvable"}
    resolved_settings = settings_path or Path(
        f"~/.cloak/instagrapi-{resolved_handle}.json"
    ).expanduser()
    media_readback = read_media_fn(resolved_handle, resolved_settings)
    proof, reel_url = build_proof(OWNER_ID, occurrence_id, queued_at, media_readback, now=now)
    result: dict[str, Any] = {**proof, "admission_state": state, "handle": resolved_handle}
    if not proof.get("verified") or not resolve:
        return result
    if proof.get("effected") and reel_url:
        hit_taken_at = next(
            (m["taken_at"] for m in (media_readback.get("media") or [])
             if f"https://www.instagram.com/reel/{m['code']}/" == reel_url),
            queued_at,
        )
        result["ledger_appended"] = append_ledger_row_if_missing(
            ledger_path, occurrence_id, resolved_handle, reel_url, hit_taken_at,
        )
    if resolve_fn is None:
        from runtime.host.resource_admission import resolve_unknown_occurrence
        resolve_fn = resolve_unknown_occurrence
    result["closed"] = resolve_fn(
        OWNER_ID, occurrence_id, official_readback=lambda: proof, expected_state=state,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--accounts-path", type=Path, default=ACCOUNTS_PATH)
    parser.add_argument("--handle")
    parser.add_argument("--settings-path", type=Path)
    parser.add_argument("--ledger-path", type=Path, default=IG_LEDGER_PATH)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reconcile(
            args.occurrence, accounts_path=args.accounts_path, handle=args.handle,
            settings_path=args.settings_path, ledger_path=args.ledger_path,
            resolve=args.resolve,
        )
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({
            "owner_id": OWNER_ID, "occurrence_id": args.occurrence, "verified": False,
            "error": f"{type(exc).__name__}:{exc}",
        }, sort_keys=True))
        print("CAPAFY_IG_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str))
    if not result.get("verified"):
        print("CAPAFY_IG_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("CAPAFY_IG_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("CAPAFY_IG_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("CAPAFY_IG_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
