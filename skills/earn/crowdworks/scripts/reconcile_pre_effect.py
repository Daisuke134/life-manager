#!/usr/bin/env python3
"""Reconcile one CrowdWorks form timeout only when its POST fence was never prepared."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import resolve_pre_effect_occurrence
from google_form import _identity, pre_effect_receipt_absent


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _run_proves_no_dispatch(path: Path, occurrence_id: str) -> bool:
    value = _read(path)
    return (isinstance(value, dict) and value.get("version") == 1
            and value.get("occurrence_id") == occurrence_id
            and (value.get("status") == "pre_effect"
                 or (value.get("status") == "completed" and value.get("effect") == 0)))


def find_matching_intent(state_root: Path, contract_id: str,
                         form_sha256: str, occurrence_id: str) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for path in sorted(state_root.glob("items/*/state.json")):
        value = _read(path)
        if not value or value.get("status") != "intent_persisted":
            continue
        observation = value.get("observation")
        intent = value.get("intent")
        payload = intent.get("payload") if isinstance(intent, Mapping) else None
        if (value.get("occurrence_id") == occurrence_id
                and isinstance(observation, Mapping)
                and observation.get("work_id") == contract_id
                and isinstance(intent, Mapping) and intent.get("action") == "submit"
                and isinstance(payload, Mapping)
                and payload.get("form_sha256") == form_sha256):
            matches.append(value)
    return matches[0] if len(matches) == 1 else None


def reconcile(*, state_root: Path, owner: str, occurrence: str,
              contract_id: str, form_sha256: str,
              run_marker: Path, expected_state: str = "claimed") -> dict[str, Any]:
    value = find_matching_intent(state_root, contract_id, form_sha256, occurrence)
    if value is None:
        raise RuntimeError("exact_persisted_form_intent_unavailable")
    intent = value["intent"]
    payload = intent["payload"]
    account_id = str(intent.get("account_id") or "").strip()
    milestone_id = str(payload.get("milestone_id") or "").strip()
    if not account_id or not milestone_id:
        raise RuntimeError("persisted_form_binding_incomplete")
    binding = {"provider": "crowdworks", "account_id": account_id,
               "contract_id": contract_id, "milestone_id": milestone_id,
               "form_revision_sha256": form_sha256}
    buyer_event_id = payload.get("buyer_event_id")
    if isinstance(buyer_event_id, str) and buyer_event_id.strip():
        binding["buyer_event_id"] = buyer_event_id.strip()
    revision_event_id = payload.get("revision_event_id")
    if isinstance(revision_event_id, str) and revision_event_id.strip():
        binding["revision_event_id"] = revision_event_id.strip()

    def proof() -> dict[str, Any]:
        if (not _run_proves_no_dispatch(run_marker, occurrence)
                or not pre_effect_receipt_absent(state_root, binding)):
            return {"owner_id": owner, "occurrence_id": occurrence, "verified": False}
        return {"owner_id": owner, "occurrence_id": occurrence, "verified": True,
                "proof_type": "pre_effect",
                "evidence_ref": f"google-form-prepared-absent:{_identity(binding)}"}

    resolved = resolve_pre_effect_occurrence(
        owner, occurrence, pre_effect_readback=proof, expected_state=expected_state,
    )
    return {"resolved": resolved, "owner_id": owner, "occurrence_id": occurrence,
            "contract_id": contract_id, "form_revision_sha256": form_sha256,
            "proof_type": "pre_effect"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--owner", default="crowdworks-revenue-paid")
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--contract-id", required=True)
    parser.add_argument("--form-sha256", required=True)
    parser.add_argument("--run-marker", required=True, type=Path)
    parser.add_argument("--expected-state", choices=("claimed", "released"), default="claimed")
    args = parser.parse_args(argv)
    result = reconcile(state_root=args.state_root.expanduser().resolve(), owner=args.owner,
                       occurrence=args.occurrence, contract_id=args.contract_id,
                       form_sha256=args.form_sha256, run_marker=args.run_marker.expanduser().resolve(),
                       expected_state=args.expected_state)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
