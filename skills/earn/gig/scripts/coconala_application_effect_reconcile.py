#!/usr/bin/env python3
"""Safely reconcile Coconala application fences through the registered browser.

The generic fence loop has no browser identity in its environment.  This adapter
therefore performs exact occurrence-to-request-set discovery first, without
opening a browser. Only fully bound requests for one occurrence start a readback, and that
readback is run through ``with-browser.sh coconala:kosuke`` so it cannot share the
identity with another loop.  It never opens an application form or clicks submit.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import application_occurrence_reconcile as reconciler  # noqa: E402


OWNER_ID = "hf-gig-apply-direct"
BROWSER_IDENTITY = "coconala:kosuke"
WITH_BROWSER = REPO_ROOT / "skills" / "browser" / "with-browser.sh"
RECONCILER = SCRIPT_DIR / "application_occurrence_reconcile.py"


def _scan_result_path(result: Path | None) -> Path:
    return result or Path.home() / "gig" / "apply-direct" / "evidence" / "occurrence-reconcile-scan.json"


def _write_scan_result(result_path: Path, result: Mapping[str, object]) -> None:
    reconciler._atomic_json(result_path, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def build_browser_command(
    *,
    occurrence_id: str,
    runtime_run_id: str,
    request_ids: Sequence[str],
    owner_id: str,
    intent_root: Path,
    evidence_dir: Path | None = None,
    result: Path | None = None,
    max_pages: int = 1000,
) -> list[str]:
    """Build the only command that may open a Coconala browser for reconciliation."""
    command = [
        "bash",
        str(WITH_BROWSER),
        BROWSER_IDENTITY,
        "--",
        sys.executable,
        str(RECONCILER),
        "--owner-id",
        owner_id,
        "--occurrence-id",
        occurrence_id,
        "--runtime-run-id",
        runtime_run_id,
        "--intent-root",
        str(intent_root),
        "--max-pages",
        str(max_pages),
    ]
    for request_id in request_ids:
        command.extend(["--request-id", request_id])
    if evidence_dir is not None:
        command.extend(["--evidence-dir", str(evidence_dir)])
    if result is not None:
        command.extend(["--result", str(result)])
    return command


def run_browser_reconcile(
    command: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> int:
    """Run one identity-leased readback without waiting behind a live owner."""
    environment = os.environ.copy()
    # A fence wake must defer when the production paid loop owns the identity; it
    # must never queue behind it long enough to overlap a later wake.
    environment["BROWSER_WAIT_SECONDS"] = "0"
    # Reconciliation is readback-only.  Do not provision or mutate a browser as a
    # side effect of discovering that the registered identity is unavailable.
    # ``with-browser.sh`` uses ``${VAR:-default}``; a blank value would therefore
    # re-enable its provisioning helper.  A non-executable sentinel disables it.
    environment["AI_ENSURE_PROVISION_BROWSER"] = "/dev/null"
    completed = (runner or subprocess.run)(command, cwd=REPO_ROOT, env=environment, check=False)
    return int(completed.returncode)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", default=OWNER_ID)
    parser.add_argument("--intent-root", type=Path, default=Path.home() / "gig" / "application-intents")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--max-pages", type=int, default=1000)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.owner_id != OWNER_ID:
        _write_scan_result(
            _scan_result_path(args.result),
            {
                "status": "unresolved",
                "reason": "owner_not_allowlisted",
                "retryable": False,
                "effect": 0,
                "readback": 0,
            },
        )
        return 0
    if args.max_pages < 1:
        _parser().error("--max-pages must be positive")

    try:
        target = reconciler.discover_single_target(
            owner_id=args.owner_id,
            intent_root=args.intent_root,
        )
    except reconciler.ReconcileContractError as error:
        _write_scan_result(
            _scan_result_path(args.result),
            {
                "status": "unresolved",
                "reason": str(error),
                "retryable": True,
                "effect": 0,
                "readback": 0,
                "next_action": "read admission and intent stores again; do not release or retry",
            },
        )
        return 0

    if target is None:
        _write_scan_result(
            _scan_result_path(args.result),
            {
                "status": "nothing_to_reconcile",
                "reason": "exact_occurrence_request_set_not_present",
                "retryable": False,
                "effect": 0,
                "readback": 0,
                "next_action": "wait for exact run/occurrence-bound intents; do not replay",
            },
        )
        return 0

    occurrence_id, runtime_run_id, request_ids = target
    command = build_browser_command(
        occurrence_id=occurrence_id,
        runtime_run_id=runtime_run_id,
        request_ids=request_ids,
        owner_id=args.owner_id,
        intent_root=args.intent_root,
        evidence_dir=args.evidence_dir,
        result=args.result,
        max_pages=args.max_pages,
    )
    return run_browser_reconcile(command, runner=runner)


if __name__ == "__main__":
    raise SystemExit(main())
