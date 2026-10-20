#!/usr/bin/env python3
"""Append and audit durable daily-owner terminal evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import string
import subprocess
from pathlib import Path


STATE_HOME = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", Path.home() / ".local/state/life-manager"))
DEFAULT_LEDGER = STATE_HOME / "state/capafy-daily-terminals.jsonl"
RESULT_STATUSES = {"success": 0, "no_op": 0, "failure": 1}


def append_event(path: Path, execution_id: str, phase: str, rc: int | None, verdict: str | None,
                 observed_at: str | None = None) -> dict:
    now = observed_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    event = {"schema_version": 1, "execution_id": execution_id, "phase": phase,
             "observed_at": now, "local_date": dt.datetime.fromisoformat(now.replace("Z", "+00:00")).astimezone().date().isoformat()}
    if phase == "terminal":
        event.update({"rc": rc, "verdict": verdict, "healthy": rc == 0})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, 0o600)
    return event


def streak_status(path: Path, today: str | None = None) -> dict:
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("execution_id") and row.get("local_date"):
                rows.append(row)
    by_execution: dict[str, dict] = {}
    for row in rows:
        state = by_execution.setdefault(str(row["execution_id"]), {"started": False, "terminal": None, "date": row["local_date"]})
        if row.get("phase") == "started":
            state["started"] = True
        elif row.get("phase") == "terminal":
            state["terminal"] = row
    by_day: dict[str, list[dict]] = {}
    for state in by_execution.values():
        by_day.setdefault(state["date"], []).append(state)
    day = dt.date.fromisoformat(today) if today else dt.datetime.now().astimezone().date()
    streak = 0
    while True:
        states = by_day.get(day.isoformat())
        if not states or any(not state["started"] or not state["terminal"] or not state["terminal"].get("healthy") for state in states):
            break
        streak += 1
        day -= dt.timedelta(days=1)
    return {"schema_version": 1, "consecutive_healthy_days": streak, "required": 7,
            "pass": streak >= 7, "days_observed": len(by_day)}


def _verify_offline_source(repo: Path, base: str, result: dict) -> dict:
    commit, slug = result.get("source_commit"), result.get("candidate_slug")
    if any(not isinstance(value, str) or len(value) != 40
           or any(c not in string.hexdigits.lower() for c in value)
           for value in (base, commit)):
        raise ValueError("invalid_source_commit")
    if (not isinstance(slug, str) or not slug
            or slug[0] not in string.ascii_lowercase
            or any(c not in string.ascii_lowercase + string.digits + "-" for c in slug)):
        raise ValueError("invalid_candidate_slug")

    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args], check=True,
                              capture_output=True, text=True, timeout=60).stdout

    # Fetch only objects/tracking refs. Never change the source checkout or branch.
    git("fetch", "--quiet", "--no-auto-maintenance", "origin", "main")
    main = git("rev-parse", "refs/remotes/origin/main").strip()
    git("merge-base", "--is-ancestor", base, commit)
    git("merge-base", "--is-ancestor", commit, main)
    prefix = f"skills/capafy/catalog/{slug}"
    if git("ls-tree", "--name-only", base, "--", prefix).strip():
        raise ValueError("source_candidate_already_existed")
    entries = {}
    for entry in git("ls-tree", "-rlz", commit, "--", prefix).split("\0"):
        if not entry:
            continue
        metadata, path = entry.split("\t", 1)
        mode, kind, oid, size = metadata.split()
        entries[path] = (mode, kind, size)
    required = ("SKILL.md", "LISTING.md", "icon.svg", "icon.png",
                "evidence/verified-demonstration.md")
    for name in required:
        mode, kind, size = entries.get(f"{prefix}/{name}", ("", "", "0"))
        if mode not in ("100644", "100755") or kind != "blob" or int(size) <= 0:
            raise ValueError(f"source_artifact_missing_or_not_regular:{name}")
    return {"source_commit": commit, "candidate_slug": slug, "main_commit": main,
            "source_status": "merged_main", "runtime_adoption": "pending"}


def classify_result(summary_path: Path, *, source_repo: Path | None = None,
                    source_base: str | None = None) -> tuple[int, dict]:
    """Classify a fresh runner result without trusting paths outside its evidence dir."""
    invalid = {"status": "invalid", "rc": 2}
    try:
        summary_path = summary_path.resolve(strict=True)
        evidence_dir = summary_path.parent
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(summary, dict):
            return 2, invalid
        raw_result = summary.get("result_path")
        if not isinstance(raw_result, str) or not raw_result.strip():
            return 2, invalid
        result_path = Path(raw_result).expanduser()
        if not result_path.is_absolute():
            result_path = evidence_dir / result_path
        result_path = result_path.resolve(strict=True)
        if result_path.parent != evidence_dir:
            return 2, invalid
        if result_path == evidence_dir or not result_path.is_file():
            return 2, invalid
        result = json.loads(result_path.read_text(encoding="utf-8"))
        expected_keys = {"status", "evidence"}
        if source_repo is not None:
            expected_keys |= {"source_commit", "candidate_slug"}
        if not isinstance(result, dict) or set(result) != expected_keys:
            return 2, invalid
        status = result.get("status")
        evidence = result.get("evidence")
        if status not in RESULT_STATUSES or not isinstance(evidence, list) or not evidence:
            return 2, invalid
        if any(not isinstance(item, str) or not item.strip() for item in evidence):
            return 2, invalid
        rc = RESULT_STATUSES[status]
        if source_repo is not None:
            if status != "success":
                return 1, {"status": status, "rc": 1, "reason": "offline_source_required"}
            try:
                source = _verify_offline_source(source_repo, source_base, result)
            except ValueError as exc:
                return 2, {**invalid, "reason": str(exc)}
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                return 2, {**invalid, "reason": "source_git_failed",
                           "command": exc.cmd, "exit_code": getattr(exc, "returncode", None)}
            return 0, {"status": status, "rc": 0, **source}
        return rc, {"status": status, "rc": rc}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 2, invalid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "finish", "status", "result", "offline-result"))
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--execution-id")
    parser.add_argument("--rc", type=int)
    parser.add_argument("--verdict")
    parser.add_argument("--today")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--source-repo", type=Path)
    parser.add_argument("--source-base")
    args = parser.parse_args()
    if args.action == "status":
        value = streak_status(args.ledger, args.today)
    elif args.action in ("result", "offline-result"):
        if not args.summary:
            parser.error("--summary is required for result")
        kwargs = {}
        if args.action == "offline-result":
            if not args.source_repo or not args.source_base:
                parser.error("--source-repo and --source-base are required for offline-result")
            kwargs = {"source_repo": args.source_repo, "source_base": args.source_base}
        rc, value = classify_result(args.summary, **kwargs)
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        return rc
    else:
        if not args.execution_id:
            parser.error("--execution-id is required")
        value = append_event(args.ledger, args.execution_id,
                             "started" if args.action == "start" else "terminal",
                             args.rc, args.verdict)
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
