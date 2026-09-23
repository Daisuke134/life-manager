#!/usr/bin/env python3
"""Release one paid-loop fence from an exact zero-effect run marker."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from runtime.host.resource_admission import resolve_pre_effect_occurrence


SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def run_marker_path(state_root: Path, occurrence: str) -> Path:
    digest = hashlib.sha256(occurrence.encode()).hexdigest()
    return state_root / "paid" / "runs" / f"{digest}.json"


def find_paid_no_effect_proof(state_root: Path, owner: str,
                              occurrence: str) -> dict[str, Any] | None:
    if (not SAFE_ID.fullmatch(owner) or not SAFE_ID.fullmatch(occurrence)
            or not occurrence.startswith(f"{owner}:")):
        return None
    marker_path = run_marker_path(state_root, occurrence)
    marker = _read(marker_path)
    if (marker is None or marker.get("version") != 1
            or marker.get("occurrence_id") != occurrence
            or marker.get("status") not in {"pre_effect", "completed"}
            or marker.get("effect") != 0):
        return None
    evidence_ref = f"lm-paid-run://{owner}/{marker_path.name}"
    return {
        "owner_id": owner,
        "occurrence_id": occurrence,
        "verified": True,
        "proof_type": "pre_effect",
        # The host resolver consumes one canonical evidence_ref. Keep the
        # plural alias for report consumers that already expect a list.
        "evidence_ref": evidence_ref,
        "evidence_refs": [evidence_ref],
    }


def reconcile(*, state_root: Path, owner: str, occurrence: str,
              resolve: bool = False) -> dict[str, Any]:
    proof = find_paid_no_effect_proof(state_root, owner, occurrence)
    if proof is None:
        raise RuntimeError("exact_paid_zero_effect_proof_unavailable")
    resolved = False
    if resolve:
        resolved = resolve_pre_effect_occurrence(
            owner, occurrence, pre_effect_readback=lambda: proof,
            expected_state="claimed",
        )
    return {**proof, "resolved": resolved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path,
                        help="provider state root containing paid/")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true",
                        help="release the exact claimed occurrence after proof")
    args = parser.parse_args(argv)
    result = reconcile(state_root=args.state_root.expanduser().resolve(),
                       owner=args.owner, occurrence=args.occurrence,
                       resolve=args.resolve)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not args.resolve or result["resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
