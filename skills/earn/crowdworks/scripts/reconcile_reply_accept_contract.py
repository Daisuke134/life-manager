#!/usr/bin/env python3
"""Reconcile an uncertain Reply acceptance only from an exact provider receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import resolve_unknown_occurrence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from reply_adapter import CrowdWorksReplyAdapter  # noqa: E402


OWNER = "crowdworks-revenue-reply"


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


def occurrence_effects_accounted(state_root: Path, occurrence: str,
                                 target_thread_id: str) -> bool:
    """Require every intent in one wake to be terminal or the verified target."""
    matches: list[dict[str, Any]] = []
    for path in sorted(state_root.glob("threads/*/state.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, Mapping) and value.get("occurrence_id") == occurrence:
            matches.append(dict(value))
    if not matches:
        return False
    for value in matches:
        intent = value.get("intent")
        thread_id = intent.get("thread_id") if isinstance(intent, Mapping) else None
        if thread_id == target_thread_id and value.get("status") == "reconcile_unknown":
            continue
        if isinstance(intent, Mapping) and value.get("status") != "verified":
            return False
    return True


def official_accept_proof(*, owner: str, occurrence: str,
                          state: Mapping[str, Any],
                          readback: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Bind one exact occurrence to one persisted intent and provider receipt."""
    intent = state.get("intent")
    if (owner != OWNER or not occurrence.startswith(f"{OWNER}:")
            or state.get("occurrence_id") != occurrence
            or not isinstance(intent, Mapping)
            or intent.get("action") != "accept_contract"
            or not isinstance(readback, Mapping)
            or readback.get("verified") is not True
            or not isinstance(readback.get("provider_receipt_id"), str)
            or not readback["provider_receipt_id"].strip()):
        return None
    return {
        "owner_id": owner,
        "occurrence_id": occurrence,
        "verified": True,
        "provider_receipt_id": readback["provider_receipt_id"].strip(),
        "observed_at": readback.get("observed_at"),
        "proof_type": "official_effect",
        "evidence_ref": f"crowdworks://reply-receipt/{intent['thread_id']}",
    }


def read_provider_state(state_root: Path, thread_id: str) -> dict[str, Any]:
    state = _read_state(state_root, thread_id)
    if state is None:
        raise RuntimeError("exact_accept_contract_intent_unavailable")
    intent = dict(state["intent"])
    adapter = CrowdWorksReplyAdapter({}, state_path=state_root)
    try:
        adapter.observe_threads()
        if thread_id not in adapter.rows:
            raise RuntimeError("crowdworks_thread_unavailable")
        intent["thread_id"] = thread_id
        return {"state": state, "readback": adapter.readback(intent)}
    finally:
        adapter.close()


def reconcile(*, state_root: Path, owner: str, occurrence: str,
              thread_id: str, resolve: bool = False) -> dict[str, Any]:
    observed = read_provider_state(state_root, thread_id)
    proof = official_accept_proof(owner=owner, occurrence=occurrence,
                                  state=observed["state"],
                                  readback=observed["readback"])
    if proof is None:
        raise RuntimeError("exact_official_accept_receipt_unavailable")
    if not occurrence_effects_accounted(state_root, occurrence, thread_id):
        raise RuntimeError("occurrence_effects_unaccounted")
    resolved = False
    if resolve:
        resolved = resolve_unknown_occurrence(
            owner, occurrence, official_readback=lambda: proof,
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
                        help="release the exact claimed occurrence after receipt readback")
    args = parser.parse_args(argv)
    result = reconcile(state_root=args.state_root.expanduser().resolve(), owner=args.owner,
                       occurrence=args.occurrence, thread_id=args.thread_id,
                       resolve=args.resolve)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not args.resolve or result["resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
