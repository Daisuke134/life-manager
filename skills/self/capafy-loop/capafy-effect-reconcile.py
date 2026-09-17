#!/usr/bin/env python3
"""Reconcile Capafy no-write occurrences from official readbacks."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


def _rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _run_report(events: Path, run_id: str) -> dict[str, Any]:
    matches = [row for row in _rows(events)
               if row.get("run_id") == run_id and row.get("phase") == "report"]
    row = matches[-1] if matches else {}
    if (row.get("status") != "pass" or row.get("blocker") is not None
            or row.get("effect_status") not in {"not_applicable", "reconciled"}):
        raise ValueError("run report is not a clean terminal pass")
    return row


def _cap_full_terminal(terminals: Path, observed: str) -> dict[str, Any]:
    stamp = dt.datetime.fromisoformat(observed.replace("Z", "+00:00"))
    candidates = []
    for row in _rows(terminals):
        if row.get("phase") != "terminal" or row.get("rc") != 0 or row.get("verdict") != "CAP_FULL":
            continue
        try:
            candidate = dt.datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if abs((candidate - stamp).total_seconds()) <= 180:
            candidates.append(row)
    if not candidates:
        raise ValueError("no matching CAP_FULL no-write terminal")
    return candidates[-1]


def _inventory(release_root: Path) -> dict[str, Any]:
    script = release_root / "skills/capafy-autopublish/scripts/inventory_status.py"
    environment = dict(os.environ)
    environment.update({
        "LIFE_MANAGER_REPO": str(release_root),
        "CAPAFY_AUTO": str(release_root / "skills/capafy-autopublish"),
        "CAPAFY_CATALOG_DIR": str(release_root / "skills/capafy/catalog"),
    })
    result = subprocess.run([sys.executable, str(script)], env=environment,
                            capture_output=True, text=True, timeout=90, check=False)
    if result.returncode != 0:
        raise ValueError("inventory read failed")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    payload = json.loads(lines[-1]) if lines else {}
    counts = payload.get("counts") if isinstance(payload, dict) else None
    if (not isinstance(payload, dict) or payload.get("verdict") != "CAP_FULL"
            or not isinstance(counts, dict) or counts.get("occupied") != 5):
        raise ValueError("official inventory is not CAP_FULL")
    return payload


def build_proof(*, owner_id: str, occurrence_id: str, run_id: str,
                events: Path, terminals: Path, release_root: Path) -> dict[str, Any]:
    report = _run_report(events, run_id)
    terminal = _cap_full_terminal(terminals, str(report["timestamp"]))
    inventory = _inventory(release_root)
    material = json.dumps({"report": report, "terminal": terminal,
                           "inventory": inventory}, sort_keys=True,
                          ensure_ascii=False).encode("utf-8")
    return {
        "owner_id": owner_id,
        "occurrence_id": occurrence_id,
        "verified": True,
        "provider_receipt_id": "capafy-no-write:" + hashlib.sha256(material).hexdigest(),
        "proof_kind": "official_cap_full_no_write",
        "inventory": inventory,
        "terminal_execution_id": terminal.get("execution_id"),
    }


def _released_unknown_occurrences(owner_id: str) -> list[str]:
    """Read released unknown rows without mutating the admission ledger."""
    from runtime.host import resource_admission

    _, _, _, database = resource_admission._durable_paths()
    if not database.exists():
        return []
    uri = f"file:{database}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            rows = connection.execute(
                """SELECT occurrence_id FROM occurrences
                     WHERE owner_id=? AND state='released' AND effect_unknown=1
                     ORDER BY sequence""",
                (owner_id,),
            )
            return [str(row[0]) for row in rows if isinstance(row[0], str)]
    except sqlite3.Error as exc:
        raise ValueError("admission ledger read failed") from exc


def reconcile_released_unknowns(*, owner_id: str, events: Path, terminals: Path,
                                release_root: Path) -> list[dict[str, Any]]:
    """Clear only released rows with exact official no-write proof.

    Claimed rows are never auto-reconciled. A released row is eligible only
    when its run report, matching CAP_FULL terminal, and current official
    inventory prove that the wake could not have written to Capafy.
    """
    from runtime.host import resource_admission

    reconciled: list[dict[str, Any]] = []
    for occurrence_id in _released_unknown_occurrences(owner_id):
        prefix = f"{owner_id}:"
        if not occurrence_id.startswith(prefix):
            continue
        run_id = occurrence_id[len(prefix):]
        try:
            proof = build_proof(
                owner_id=owner_id, occurrence_id=occurrence_id, run_id=run_id,
                events=events, terminals=terminals, release_root=release_root,
            )
        except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError,
                subprocess.SubprocessError):
            continue
        if resource_admission.resolve_unknown_occurrence(
                owner_id, occurrence_id, official_readback=lambda: proof):
            reconciled.append({
                "occurrence_id": occurrence_id,
                "provider_receipt_id": proof["provider_receipt_id"],
                "terminal_execution_id": proof.get("terminal_execution_id"),
            })
    return reconciled


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--occurrence-id")
    parser.add_argument("--run-id")
    parser.add_argument("--reconcile-released", action="store_true")
    parser.add_argument("--events", type=Path, default=Path.home() / ".local/state/life-manager/events.jsonl")
    parser.add_argument("--terminals", type=Path, default=Path.home() / ".local/state/life-manager/state/capafy-daily-terminals.jsonl")
    parser.add_argument("--release-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.reconcile_released:
            reconciled = reconcile_released_unknowns(
                owner_id=args.owner_id, events=args.events,
                terminals=args.terminals, release_root=args.release_root,
            )
            print(json.dumps({
                "owner_id": args.owner_id,
                "reconciled": reconciled,
                "count": len(reconciled),
            }, ensure_ascii=False, sort_keys=True))
            print("CAPAFY_EFFECT_RECONCILE=PASS")
            return 0
        if not args.occurrence_id or not args.run_id:
            parser.error("--occurrence-id and --run-id are required unless --reconcile-released")
        proof = build_proof(owner_id=args.owner_id, occurrence_id=args.occurrence_id,
                            run_id=args.run_id, events=args.events,
                            terminals=args.terminals, release_root=args.release_root)
        from runtime.host.resource_admission import resolve_unknown_occurrence
        if not resolve_unknown_occurrence(args.owner_id, args.occurrence_id,
                                          official_readback=lambda: proof):
            raise ValueError("occurrence was not an effect-unknown released row")
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError,
            subprocess.SubprocessError) as exc:
        print(f"CAPAFY_EFFECT_RECONCILE=FAIL reason={type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(proof, ensure_ascii=False, sort_keys=True))
    print("CAPAFY_EFFECT_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
