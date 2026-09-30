#!/usr/bin/env python3
"""Release one exact marketplace fence from the host pre-effect marker.

The runtime creates ``loop-tmp/<owner>/<run>/entrypoint-result.json`` before
starting an allowlisted owner.  This adapter accepts only the exact private
marker ``{"status":"pre_effect_failure","effect":0}``, bound to the
occurrence supplied by the fence loop.  It never contacts a provider and never
retries a mutation; missing, stale, symlinked, or differently-shaped evidence
keeps the occurrence fenced.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.host.resource_admission import resolve_pre_effect_occurrence  # noqa: E402


SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
MARKER_NAME = "entrypoint-result.json"


def _read_private_marker(path: Path) -> dict[str, Any] | None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            return None
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = -1
            value = json.load(stream)
        if (
            not isinstance(value, dict)
            or set(value) != {"status", "effect"}
            or value.get("status") != "pre_effect_failure"
            or value.get("effect") != 0
        ):
            return None
        return value
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def marker_path(state_root: Path, owner: str, occurrence: str) -> Path | None:
    if (
        not SAFE_ID.fullmatch(owner)
        or not SAFE_ID.fullmatch(occurrence)
        or not occurrence.startswith(f"{owner}:")
    ):
        return None
    run_id = occurrence[len(owner) + 1 :]
    if not SAFE_ID.fullmatch(run_id):
        return None
    return state_root / "loop-tmp" / owner / run_id / MARKER_NAME


def find_pre_effect_proof(
    state_root: Path, owner: str, occurrence: str
) -> dict[str, object] | None:
    path = marker_path(state_root, owner, occurrence)
    if path is None or _read_private_marker(path) is None:
        return None
    run_id = occurrence[len(owner) + 1 :]
    return {
        "owner_id": owner,
        "occurrence_id": occurrence,
        "verified": True,
        "proof_type": "pre_effect",
        "evidence_ref": f"lm-pre-effect://{owner}/{run_id}/{MARKER_NAME}",
    }


def reconcile(
    *,
    state_root: Path,
    owner: str,
    occurrence: str,
    resolve: bool = False,
    resolver: Callable[..., bool] = resolve_pre_effect_occurrence,
) -> dict[str, object]:
    proof = find_pre_effect_proof(state_root, owner, occurrence)
    if proof is None:
        raise RuntimeError("exact_pre_effect_marker_unavailable")
    resolved = False
    if resolve:
        resolved = resolver(
            owner,
            occurrence,
            pre_effect_readback=lambda: proof,
            expected_state="claimed",
        )
    return {**proof, "resolved": resolved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    try:
        result = reconcile(
            state_root=state_root,
            owner=args.owner,
            occurrence=args.occurrence,
            resolve=args.resolve,
        )
    except RuntimeError as error:
        if str(error) != "exact_pre_effect_marker_unavailable":
            raise
        event = {
            "version": 1,
            "owner_id": args.owner,
            "occurrence_id": args.occurrence,
            "phase": "reconcile",
            "command": "reconcile_pre_effect_hint",
            "state_root": str(state_root),
            "exit_code": 75,
            "effect": "unknown",
            "effect_status": "unknown",
            "provider_receipt_id": None,
            "official_readback_ref": None,
            "evidence_refs": [],
            "error_class": str(error),
            "retryable": False,
            "next_action": "obtain_occurrence_bound_readback",
            "resolved": False,
        }
        print(json.dumps(event, ensure_ascii=False, sort_keys=True))
        return 75
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not args.resolve or result["resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
