#!/usr/bin/env python3
"""Recover missing application ledger rows from fresh canonical readback.

A durable submit intent is only a candidate.  The canonical applied-offers page
must independently contain the same identity before this script writes the
ledger.  It never retries an application submission.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import application_orphan_reconcile as orphan


IDENTITY = re.compile(r"(?:\d+|[0-7][0-9A-HJKMNP-TV-Z]{25})")
LEASE_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "_shared"
    / "browser"
    / "scripts"
    / "cdp_context_lease.py"
)


def _intent_ids(agent_dir: Path) -> list[str]:
    identities: set[str] = set()
    for path in sorted(agent_dir.glob("*-submitted.intent.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        request_id = str(
            payload.get("request_id") or payload.get("requestId") or ""
        )
        if IDENTITY.fullmatch(request_id):
            identities.add(request_id)
    return sorted(identities)


def discover_candidates(
    evidence_dir: Path,
    pass_id: str,
) -> list[dict[str, str]]:
    evidence_dir = Path(evidence_dir)
    if not pass_id or evidence_dir.name != f"gig-pass-{pass_id}":
        raise ValueError("pass_evidence_identity_invalid")
    agent_dir = evidence_dir / "agent-B2"
    candidates: list[dict[str, str]] = []
    for request_id in _intent_ids(agent_dir):
        paths = [
            agent_dir / f"{request_id}.json",
            agent_dir / f"request-{request_id}.json",
            agent_dir / f"retainer-{request_id}.json",
        ]
        candidate = None
        for path in paths:
            if not path.is_file():
                continue
            try:
                value = orphan.candidate_from_evidence(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if value["request_id"] == request_id:
                candidate = value
                break
        if candidate is None:
            raise ValueError(f"candidate_live_dom_missing:{request_id}")
        candidates.append(candidate)
    if not candidates:
        raise ValueError("durable_submit_intent_missing")
    return candidates


def _ledger_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("requestId") or row.get("request_id") or "")
        for row in rows
        if isinstance(row, dict)
        and "action" not in row
        and str(row.get("status") or "") == "applied"
    }


def reconcile_with_capture(
    *,
    evidence_dir: Path,
    pass_id: str,
    ledger_path: Path,
    output_path: Path,
    captured: dict[str, Any],
    observed_at: int,
) -> dict[str, Any]:
    candidates = discover_candidates(evidence_dir, pass_id)
    rows = orphan.readback._read_ledger(ledger_path)
    existing = _ledger_ids(rows)
    missing = [
        candidate
        for candidate in candidates
        if candidate["request_id"] not in existing
    ]
    if not missing:
        return {
            "status": "already_reconciled",
            "recovered": 0,
            "request_ids": [],
            "side_effect_performed": False,
        }
    recovery_id = f"ledger-heal:{pass_id}"
    reconciled, payload = orphan.reconcile_orphans(
        rows,
        candidates=missing,
        captured=captured,
        recovery_id=recovery_id,
        observed_at=observed_at,
        evidence_path=output_path,
    )
    orphan.readback._atomic_json(output_path, payload)
    orphan.readback._write_ledger(ledger_path, reconciled)
    return {
        "status": "reconciled",
        "recovered": len(payload["applications"]),
        "request_ids": payload["request_ids"],
        "output": str(output_path.resolve()),
        "side_effect_performed": True,
    }


def _lease(command: str, name: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(LEASE_SCRIPT), command, name],
        shell=False,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"context_{command}_failed:{result.stderr[-300:]}")
    payload = json.loads(result.stdout)
    if payload.get("ok") is not True:
        raise RuntimeError(f"context_{command}_failed:{payload}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--pass-id", required=True)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--screenshot", required=True, type=Path)
    args = parser.parse_args()
    lease_name = f"gig-ledger-heal-{args.pass_id}"
    acquired = False
    try:
        candidates = discover_candidates(args.evidence_dir, args.pass_id)
        lease = _lease("acquire", lease_name)
        acquired = True
        identities = {row["request_id"] for row in candidates}
        titles = {
            row["request_id"]: row["title"]
            for row in candidates
            if row["bucket"] == "retainer"
        }
        captured = asyncio.run(orphan.readback.capture_readback(
            str(lease["ws"]),
            screenshot_path=args.screenshot,
            expected_ids=identities,
            expected_retainer_titles=titles,
        ))
        result = reconcile_with_capture(
            evidence_dir=args.evidence_dir,
            pass_id=args.pass_id,
            ledger_path=args.ledger,
            output_path=args.output,
            captured=captured,
            observed_at=int(time.time()),
        )
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        print(json.dumps({
            "status": "failed",
            "error": f"{type(error).__name__}:{error}",
            "side_effect_performed": False,
        }, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1
    finally:
        if acquired:
            try:
                _lease("release", lease_name)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
