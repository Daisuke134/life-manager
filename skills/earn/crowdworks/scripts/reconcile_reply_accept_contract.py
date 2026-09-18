#!/usr/bin/env python3
"""Reconcile one uncertain Reply contract acceptance from a live pending proposal page."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import resolve_pre_effect_occurrence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from reply_adapter import CrowdWorksReplyAdapter  # noqa: E402


OWNER = "crowdworks-revenue-reply"
PROPOSAL_ROUTE = re.compile(r"^/proposals/[0-9]+$")


def _read_state(state_root: Path, thread_id: str) -> dict[str, Any] | None:
    for path in sorted(state_root.glob("threads/*/state.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        intent = value.get("intent") if isinstance(value, Mapping) else None
        if (isinstance(intent, Mapping)
                and intent.get("action") == "accept_contract"
                and intent.get("thread_id") == thread_id):
            return dict(value)
    return None


def pending_proposal_proof(*, owner: str, occurrence: str,
                           state: Mapping[str, Any], row: Mapping[str, Any],
                           url: str, title: str, body: str,
                           progress: str) -> dict[str, Any] | None:
    if owner != OWNER or not occurrence.startswith(f"{OWNER}:"):
        return None
    intent = state.get("intent")
    payload = intent.get("payload") if isinstance(intent, Mapping) else None
    thread_id = intent.get("thread_id") if isinstance(intent, Mapping) else None
    if (not isinstance(payload, Mapping) or intent.get("action") != "accept_contract"
            or not isinstance(thread_id, str)
            or row.get("thread_id") != thread_id
            or str(row.get("id")) != str(state.get("inventory_event_id"))):
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "crowdworks.jp" or not PROPOSAL_ROUTE.fullmatch(parsed.path):
        return None
    required = [payload.get("title"), payload.get("amount"),
                payload.get("client"), payload.get("worker")]
    if any(not isinstance(value, str) or not value.strip() for value in required):
        return None
    if any(value not in title + "\n" + body for value in required):
        return None
    if ("まだクライアントが契約に同意していません" not in progress
            or "クライアントが契約に同意すると契約成立" not in progress):
        return None
    return {
        "owner_id": owner,
        "occurrence_id": occurrence,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"crowdworks://proposal-pending/{thread_id}/{state['inventory_event_id']}",
    }


def read_provider_state(state_root: Path, thread_id: str) -> dict[str, Any]:
    state = _read_state(state_root, thread_id)
    if state is None:
        raise RuntimeError("exact_accept_contract_intent_unavailable")
    adapter = CrowdWorksReplyAdapter({}, state_path=state_root)
    try:
        adapter.observe_threads()
        row = adapter.rows.get(thread_id)
        if row is None:
            raise RuntimeError("crowdworks_thread_unavailable")
        adapter._open_thread_page(thread_id)
        progress = adapter.page.locator("div.progress_detail")
        if progress.count() != 1:
            raise RuntimeError("crowdworks_contract_progress_unavailable")
        return {
            "state": state,
            "row": row,
            "url": adapter.page.url,
            "title": adapter.page.title(),
            "body": adapter.page.locator("body").inner_text(),
            "progress": progress.inner_text(),
        }
    finally:
        adapter.close()


def reconcile(*, state_root: Path, owner: str, occurrence: str,
              thread_id: str, resolve: bool = False) -> dict[str, Any]:
    observed = read_provider_state(state_root, thread_id)
    proof = pending_proposal_proof(owner=owner, occurrence=occurrence, **observed)
    if proof is None:
        raise RuntimeError("official_pending_proposal_proof_unavailable")
    resolved = False
    if resolve:
        resolved = resolve_pre_effect_occurrence(
            owner, occurrence, pre_effect_readback=lambda: proof,
            expected_state="claimed",
        )
    return {**proof, "resolved": resolved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--owner", choices=(OWNER,), default=OWNER)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--resolve", action="store_true",
                        help="release the exact claimed occurrence after live readback")
    args = parser.parse_args(argv)
    result = reconcile(state_root=args.state_root.expanduser().resolve(), owner=args.owner,
                       occurrence=args.occurrence, thread_id=args.thread_id,
                       resolve=args.resolve)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not args.resolve or result["resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
