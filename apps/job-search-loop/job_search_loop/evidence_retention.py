"""Bounded, owner-scoped retention for job-search run evidence.

The job-search drivers write directly below ``.../job-search/evidence`` rather
than the central agent-runner evidence layout.  This module is the owner of
that tree.  It only removes old runs with an explicit no-effect terminal
marker; unknown, submitted, failed, blocked, and active runs are retained.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


KNOWN_PREFIXES = ("daily-", "inbox-", "learning-", "mercor-")
TERMINAL_FILES = (
    "inbox-terminal.json",
    "mercor-pass-terminal.json",
    "wake-report.json",
    "learning-decision.json",
    "summary.json",
    "result.json",
)
RESULT_GLOB = "attempt-*.result.json"
UNSAFE_WORDS = (
    "unknown",
    "submitted",
    "blocked",
    "failed",
    "needs_human",
    "delivery_unknown",
    "effect_unknown",
    "entrypoint_exit",
    "transport_failed",
)


def _safe_root(root: Path) -> Path:
    if root.is_symlink() or root.name != "evidence":
        raise ValueError("job-search retention root must be the real evidence directory")
    resolved = root.resolve()
    if resolved.name != "evidence":
        raise ValueError("job-search retention root resolved outside evidence directory")
    return resolved


def _json_files(run_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for name in TERMINAL_FILES:
        path = run_dir / name
        if path.is_file() and not path.is_symlink():
            paths.append(path)
    for path in run_dir.glob(RESULT_GLOB):
        if path.is_file() and not path.is_symlink():
            paths.append(path)
    return paths


def _read_markers(run_dir: Path) -> tuple[list[dict[str, Any]], bool]:
    markers: list[dict[str, Any]] = []
    present = False
    for path in _json_files(run_dir):
        present = True
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return [], True
        if not isinstance(value, dict):
            return [], True
        markers.append(value)
    return markers, present


def _truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, (list, dict, str)):
        return bool(value)
    return True


def _unsafe(value: Any, *, key: str = "") -> bool:
    key = key.lower()
    if key in {"submitted", "submit_unknown", "blocked", "needs_human"} and _truthy(value):
        return True
    if isinstance(value, str):
        text = value.strip().lower()
        if key in {"status", "outcome", "reason", "next_action", "blocker"}:
            return any(word in text for word in UNSAFE_WORDS)
        return False
    if isinstance(value, dict):
        return any(_unsafe(item, key=str(name)) for name, item in value.items())
    if isinstance(value, list):
        return any(_unsafe(item, key=key) for item in value)
    return False


def _explicit_no_effect(markers: list[dict[str, Any]]) -> bool:
    for marker in markers:
        outcome = str(marker.get("outcome") or "").strip().lower()
        status = str(marker.get("status") or "").strip().lower()
        if outcome == "no_work":
            return True
        if status in {"no_new_recruiting_email", "observed_no_action"}:
            return True
    return False


def _has_active_marker(run_dir: Path) -> bool:
    for relative in (
        "scratch/command.lock",
        "scratch/terminal-effect.lock",
        "scratch/active-command.json",
        ".pass.lock",
    ):
        path = run_dir / relative
        if path.exists() or path.is_symlink():
            return True
    return False


def classify_run(run_dir: Path, *, now: float | None = None, min_age_seconds: int = 7 * 86400) -> dict[str, Any]:
    """Classify one run without changing it."""
    now = time.time() if now is None else now
    if run_dir.is_symlink() or not run_dir.is_dir():
        return {"eligible": False, "reason": "not_directory"}
    if not run_dir.name.startswith(KNOWN_PREFIXES):
        return {"eligible": False, "reason": "owner_prefix_unknown"}
    try:
        age = max(0.0, now - run_dir.stat().st_mtime)
    except OSError:
        return {"eligible": False, "reason": "stat_failed"}
    if age < min_age_seconds:
        return {"eligible": False, "reason": "too_new", "age_seconds": int(age)}
    if _has_active_marker(run_dir):
        return {"eligible": False, "reason": "active_marker", "age_seconds": int(age)}
    markers, present = _read_markers(run_dir)
    if not present:
        return {"eligible": False, "reason": "terminal_marker_missing", "age_seconds": int(age)}
    if not markers:
        return {"eligible": False, "reason": "terminal_marker_invalid", "age_seconds": int(age)}
    if _unsafe(markers):
        return {"eligible": False, "reason": "effect_or_uncertainty", "age_seconds": int(age)}
    if not _explicit_no_effect(markers):
        return {"eligible": False, "reason": "no_explicit_no_effect", "age_seconds": int(age)}
    return {"eligible": True, "reason": "explicit_no_effect", "age_seconds": int(age)}


def _tree_size(path: Path) -> int:
    total = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(base) / name).is_symlink()]
        for name in files:
            item = Path(base) / name
            try:
                if not item.is_symlink():
                    total += item.stat().st_size
            except OSError:
                continue
    return total


@contextmanager
def _retention_lock(root: Path) -> Iterator[None]:
    lock_path = root.parent / ".evidence-retention.lock"
    lock_path.touch(mode=0o600, exist_ok=True)
    with lock_path.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def reclaim_evidence(
    root: Path,
    *,
    current_run: Path | None = None,
    min_age_seconds: int = 7 * 86400,
    min_free_bytes: int = 512 * 1024 * 1024,
    max_evidence_bytes: int = 2 * 1024 * 1024 * 1024,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Reclaim only owner-classified terminal no-effect runs.

    A normal caller returns immediately while the filesystem has the requested
    free-space floor.  ``force=True`` is reserved for a bounded maintenance
    probe or test.  The current run is never a candidate.
    """
    if min_age_seconds < 0 or min_free_bytes < 0 or max_evidence_bytes < 0:
        raise ValueError("retention thresholds must be non-negative")
    root = _safe_root(root)
    if not root.exists():
        return {"scanned_runs": 0, "eligible_runs": 0, "reclaimed_runs": 0, "reclaimed_bytes": 0, "errors": 0}
    current = current_run.resolve() if current_run is not None else None
    with _retention_lock(root):
        initial_free = shutil.disk_usage(root).free
        if not force and initial_free >= min_free_bytes:
            # ``max_evidence_bytes`` is an owner-tree invariant independent
            # of the filesystem floor.  Probe the tree before taking the fast
            # path so a healthy-looking volume cannot let this writer grow
            # without bound (the previous shortcut did exactly that).
            if max_evidence_bytes <= 0 or _tree_size(root) <= max_evidence_bytes:
                return {
                    "scanned_runs": 0,
                    "eligible_runs": 0,
                    "reclaimed_runs": 0,
                    "reclaimed_bytes": 0,
                    "errors": 0,
                    "skipped": "capacity_ok",
                    "free_bytes": initial_free,
                }
        candidates: list[tuple[float, Path, int]] = []
        total = 0
        scanned = 0
        eligible = 0
        errors = 0
        for run_dir in root.iterdir():
            if run_dir.is_symlink() or not run_dir.is_dir():
                continue
            scanned += 1
            size = _tree_size(run_dir)
            total += size
            if current is not None and run_dir.resolve() == current:
                continue
            result = classify_run(run_dir, min_age_seconds=min_age_seconds)
            if not result["eligible"]:
                continue
            eligible += 1
            try:
                candidates.append((run_dir.stat().st_mtime, run_dir, size))
            except OSError:
                errors += 1
        reclaimed_bytes = 0
        reclaimed_runs = 0
        free = shutil.disk_usage(root).free
        for _, run_dir, size in sorted(candidates, key=lambda item: item[0]):
            cap_ok = max_evidence_bytes > 0 and total <= max_evidence_bytes
            if cap_ok and free >= min_free_bytes:
                break
            if dry_run:
                total -= size
                reclaimed_bytes += size
                reclaimed_runs += 1
                continue
            trash = root / f".{run_dir.name}.gc-trash.{os.getpid()}"
            try:
                os.replace(run_dir, trash)
                shutil.rmtree(trash)
            except OSError:
                errors += 1
                try:
                    if trash.exists() and not run_dir.exists():
                        os.replace(trash, run_dir)
                except OSError:
                    errors += 1
                continue
            total -= size
            reclaimed_bytes += size
            reclaimed_runs += 1
            free = shutil.disk_usage(root).free
        return {
            "scanned_runs": scanned,
            "eligible_runs": eligible,
            "reclaimed_runs": reclaimed_runs,
            "reclaimed_bytes": reclaimed_bytes,
            "errors": errors,
            "dry_run": dry_run,
            "min_age_seconds": min_age_seconds,
            "min_free_bytes": min_free_bytes,
            "max_evidence_bytes": max_evidence_bytes,
            "free_bytes_before": initial_free,
        }


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--current-run", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--min-age-seconds", type=int, default=7 * 86400)
    parser.add_argument("--min-free-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--max-evidence-bytes", type=int, default=2 * 1024 * 1024 * 1024)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reclaim_evidence(
            args.root,
            current_run=args.current_run,
            min_age_seconds=args.min_age_seconds,
            min_free_bytes=args.min_free_bytes,
            max_evidence_bytes=args.max_evidence_bytes,
            dry_run=args.dry_run,
            force=args.force,
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return errno.ENOSPC if isinstance(error, OSError) and error.errno == errno.ENOSPC else 2
    receipt = {"status": "dry_run" if args.dry_run else "completed", **result}
    if args.receipt:
        _write_receipt(args.receipt, receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
