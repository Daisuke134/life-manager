#!/usr/bin/env python3
"""Reclaim closed gig work and obsolete output after an official terminal receipt.

WHY: buyer source can be unique and is never cleanup material. Regenerable
`work/` may be reclaimed only when an official provider readback wrote a
hash-bound `project-terminal.json`. Closed delivery/artifact directories lose
only regular output files; source, evidence, context, state, receipts, secrets,
and the owner's retained latest package remain durable records.

SAFETY (fail-closed): state fields, age, and workflow flags never grant deletion
authority. A missing, symlinked, malformed, stale, or non-official terminal
receipt is skipped. One project's bad receipt must never stop the scan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

COMPLETE_STATE = "取引完了"
CANCELLED_STATE = "キャンセル"
TERMINAL_STATES = frozenset((COMPLETE_STATE, CANCELLED_STATE))
RECLAIM_DIRS = ("work",)
ARTIFACT_DIRS = ("artifacts", "delivery", "deliverables")
IMMUTABLE_ROOT_PARTS = frozenset((".cloak", ".openclaw"))
IMMUTABLE_ROOT_NAMES = frozenset(("memory", "state"))
OUTPUT_SUFFIXES = frozenset((
    ".zip", ".7z", ".tar", ".gz", ".mp4", ".mov", ".webm", ".png", ".jpg",
    ".jpeg", ".webp", ".pdf", ".docx", ".pptx", ".xlsx",
))
PROTECTED_DIRS = frozenset((
    "source", "src", "evidence", "context", "state", "memory", ".git", ".worktrees",
    ".cloak", ".openclaw", ".lm-protected", ".anicca-keep", ".lease",
))
PROTECTED_TOKENS = (
    "auth", "cookie", "credential", "receipt", "ledger", "vault", "lock", "lease",
    "recovery", "secret", "session", "wallet", "payment", "evidence", "readback",
    "key", "token", "password",
)


def _protected(path: Path) -> bool:
    name = path.name.lower()
    return (name in PROTECTED_DIRS or name == ".env" or name.startswith(".env.")
            or path.suffix.lower() in {".json", ".jsonl", ".csv", ".key", ".pem", ".p12", ".pfx", ".db", ".sqlite"}
            or any(token in name for token in PROTECTED_TOKENS))


def _has_symlink_ancestor(path: Path) -> bool:
    absolute = path.absolute()
    return any(part.is_symlink() for part in (absolute, *absolute.parents))


def _probe_error(error: OSError) -> None:
    raise error


def _open_paths() -> set[str]:
    result = subprocess.run(["/usr/sbin/lsof", "-nP", "-Fn"], capture_output=True,
                            text=True, timeout=15, check=False)
    if result.returncode not in (0, 1) or result.stderr.strip():
        raise OSError("open_file_probe_failed")
    return {line[1:] for line in result.stdout.splitlines() if line.startswith("n/")}


def _project_receipts_already_cleaned(ledger_path: Path) -> set[tuple[str, str]]:
    """Idempotency: a project already recorded as cleaned writes no new row."""
    done: set[tuple[str, str]] = set()
    if not ledger_path.exists():
        return done
    try:
        with ledger_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pid = row.get("project_id")
                state_sha = row.get("terminal_state_sha256")
                if isinstance(pid, str) and isinstance(state_sha, str):
                    done.add((pid, state_sha))
    except OSError:
        pass
    return done


def _dir_bytes(path: Path) -> int:
    total = 0
    for current, dirs, files in os.walk(path, onerror=_probe_error):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(current, d))]
        for name in files:
            try:
                total += os.lstat(os.path.join(current, name)).st_size
            except OSError:
                continue
    return total


def _remove_dir(path: Path) -> int:
    """Rename-then-delete so a kill mid-removal leaves reapable trash, not a
    half-deleted dir that looks intact."""
    if _has_symlink_ancestor(path):
        raise OSError("cleanup_path_symlink")
    size = _dir_bytes(path)
    trash = path.with_name(f"{path.name}.janitor-trash.{os.getpid()}")
    os.rename(path, trash)
    try:
        shutil.rmtree(trash)
    except OSError:
        if trash.exists() and not path.exists():
            os.rename(trash, path)
        raise
    return size


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _terminal_receipt(project_dir: Path, state_path: Path) -> tuple[dict | None, str]:
    path = project_dir / "project-terminal.json"
    try:
        if path.is_symlink() or not path.is_file():
            return None, "terminal_receipt_missing"
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "terminal_receipt_invalid"
    required = {
        "version", "authority", "terminal", "adapter", "project_id", "talkroom_id",
        "transaction_state", "talkroom_state", "state_sha256", "provider_snapshot_sha256",
        "observed_at",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        return None, "terminal_receipt_schema"
    project_id = project_dir.name
    if (
        receipt.get("version") != 1
        or receipt.get("authority") != "official_provider_readback"
        or receipt.get("terminal") is not True
        or receipt.get("adapter") != "coconala"
        or receipt.get("project_id") != project_id
        or not isinstance(receipt.get("talkroom_id"), str)
        or not receipt.get("talkroom_id")
        or receipt.get("transaction_state") not in TERMINAL_STATES
        or receipt.get("talkroom_state") != receipt.get("transaction_state")
        or not isinstance(receipt.get("observed_at"), (int, float))
        or isinstance(receipt.get("observed_at"), bool)
        or receipt.get("observed_at", 0) <= 0
    ):
        return None, "terminal_receipt_contract"
    for field in ("state_sha256", "provider_snapshot_sha256"):
        value = receipt.get(field)
        if not isinstance(value, str) or len(value) != 64:
            return None, f"terminal_receipt_{field}"
    try:
        if _sha256(state_path) != receipt["state_sha256"]:
            return None, "terminal_receipt_stale"
    except OSError:
        return None, "state_unreadable"
    return receipt, ""


def _prune_closed_outputs(project_dir: Path, *, dry_run: bool) -> dict:
    """Remove regular closed output, preserving protected subtrees and latest package."""
    receipt_path = project_dir / "context" / "owner-authorized-cleanup.json"
    result = {"deleted": [], "bytes_freed": 0}
    retained = None
    if receipt_path.is_symlink() or receipt_path.parent.is_symlink():
        raise OSError("owner_cleanup_receipt_symlink")
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("retained_path"):
            retained = Path(str(receipt["retained_path"])).resolve()
            result["retained_path"] = str(retained)

    for dirname in RECLAIM_DIRS + ARTIFACT_DIRS:
        root = project_dir / dirname
        if _has_symlink_ancestor(root) or not root.is_dir():
            continue
        for current, dirs, files in os.walk(root, followlinks=False, onerror=_probe_error):
            if set(dirs + files).intersection({".git", ".lease", ".lm-protected", ".anicca-keep"}):
                dirs.clear()
                continue
            dirs[:] = [name for name in dirs if not (Path(current) / name).is_symlink()
                       and not _protected(Path(current) / name)]
            for name in files:
                candidate = Path(current) / name
                info = candidate.lstat()
                if (candidate.resolve() == retained or _protected(candidate)
                        or candidate.suffix.lower() not in OUTPUT_SUFFIXES
                        or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_uid != os.getuid() or _has_symlink_ancestor(candidate)):
                    continue
                if not dry_run:
                    candidate.unlink()
                result["deleted"].append(str(candidate.relative_to(project_dir)))
                result["bytes_freed"] += info.st_size
    return result


def _immutable_root_reason(projects_root: Path) -> str | None:
    if _has_symlink_ancestor(projects_root):
        return "projects_root_symlink"
    try:
        resolved = projects_root.resolve()
    except OSError:
        return "projects_root_unresolvable"
    if resolved.name in IMMUTABLE_ROOT_NAMES or any(
        part in IMMUTABLE_ROOT_PARTS | {"memory", ".worktrees", "anicca-rtdash", "anicca-monk-factory"}
        for part in resolved.parts
    ):
        return "immutable_store_root"
    # The owner may version its projects container; individual worktrees stay protected.
    if resolved.name != "projects" and (resolved / ".git").exists():
        return "worktree_root"
    return None


def _contains_shared_reference(path: Path) -> bool:
    if _has_symlink_ancestor(path):
        return True
    try:
        for current, dirs, files in os.walk(path, followlinks=False, onerror=_probe_error):
            if any(_protected(Path(current) / name) for name in dirs + files):
                return True
            for name in dirs:
                if (Path(current) / name).is_symlink():
                    return True
            for name in files:
                candidate = Path(current) / name
                info = candidate.lstat()
                if (candidate.is_symlink() or info.st_nlink > 1
                        or info.st_uid != os.getuid()):
                    return True
    except OSError:
        return True
    return False


def scan(projects_root: Path, ledger_path: Path, *, dry_run: bool) -> dict:
    already_cleaned = _project_receipts_already_cleaned(ledger_path)
    summary = {
        "scanned": 0,
        "cleaned": 0,
        "skipped": 0,
        "errors": 0,
        "bytes_freed": 0,
        "dry_run": dry_run,
        "would_clean": [],
        "artifacts_cleaned": 0,
        "artifact_bytes_freed": 0,
    }
    if not projects_root.is_dir():
        return summary
    immutable_reason = _immutable_root_reason(projects_root)
    if immutable_reason:
        summary["errors"] = 1
        print(f"project_janitor: refusing {projects_root}: {immutable_reason}", file=sys.stderr)
        return summary
    try:
        opened = _open_paths()
    except (OSError, subprocess.TimeoutExpired):
        summary["errors"] = 1
        print("project_janitor: open_file_probe_failed", file=sys.stderr)
        return summary

    for project_dir in sorted(projects_root.iterdir()):
        if project_dir.is_symlink() or not project_dir.is_dir():
            continue
        state_path = project_dir / "state.json"
        if state_path.is_symlink() or not state_path.is_file():
            continue
        summary["scanned"] += 1
        project_id = project_dir.name
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            terminal, reclaim_reason = _terminal_receipt(project_dir, state_path)
            if terminal is None:
                summary["skipped"] += 1
                continue
            prefix = str(project_dir.resolve())
            if (any(path == prefix or path.startswith(prefix + "/") for path in opened)
                    or (project_dir / ".git").exists() or (project_dir / ".lease").exists()):
                summary["skipped"] += 1
                continue

            artifact_result = _prune_closed_outputs(project_dir, dry_run=dry_run)
            if artifact_result["deleted"]:
                summary["artifacts_cleaned"] += 1
                summary["artifact_bytes_freed"] += artifact_result["bytes_freed"]
                summary["bytes_freed"] += artifact_result["bytes_freed"]
                if dry_run:
                    summary["would_clean"].append({"project_id": project_id,
                                                  "deleted": artifact_result["deleted"],
                                                  "bytes_freed": artifact_result["bytes_freed"]})
                else:
                    artifact_ledger = ledger_path.with_name("artifact-janitor.jsonl")
                    artifact_record = {
                        "ts": int(time.time()),
                        "project_id": project_id,
                        "terminal_state_sha256": terminal["state_sha256"],
                        **artifact_result,
                    }
                    artifact_ledger.parent.mkdir(parents=True, exist_ok=True)
                    with artifact_ledger.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(artifact_record, ensure_ascii=False) + "\n")

            terminal_state_sha = terminal["state_sha256"]
            if (project_id, terminal_state_sha) in already_cleaned:
                continue  # source/work already recorded; artifact pruning still ran above

            targets = [
                project_dir / name
                for name in RECLAIM_DIRS
                if (project_dir / name).is_dir() and not (project_dir / name).is_symlink()
            ]
            if not targets:
                continue  # already clean (e.g. cleaned manually) -- no ledger row
            retained = artifact_result.get("retained_path")
            if any(_contains_shared_reference(target) or (retained and target.resolve() in Path(retained).parents)
                   for target in targets):
                summary["skipped"] += 1
                continue

            if dry_run:
                bytes_would_free = sum(_dir_bytes(t) for t in targets)
                summary["would_clean"].append(
                    {
                        "project_id": project_id,
                        "deleted": [t.name for t in targets],
                        "bytes_freed": bytes_would_free,
                    }
                )
                summary["cleaned"] += 1
                summary["bytes_freed"] += bytes_would_free
                continue

            deleted = []
            bytes_freed = 0
            for target in targets:
                bytes_freed += _remove_dir(target)
                deleted.append(target.name)

            record = {
                "ts": int(time.time()),
                "project_id": project_id,
                "deleted": deleted,
                "bytes_freed": bytes_freed,
                "transaction_state": state.get("transaction_state") or state.get("talkroom_state"),
                "terminal_state_sha256": terminal_state_sha,
            }
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

            summary["cleaned"] += 1
            summary["bytes_freed"] += bytes_freed
        except Exception as exc:  # noqa: BLE001 -- one bad project must not stop the scan
            summary["errors"] += 1
            print(f"project_janitor: skipping {project_id}: {exc}", file=sys.stderr)
            continue

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_root = Path(os.environ.get("GIG_STATE_DIR", str(Path.home() / "gig")))
    parser.add_argument(
        "--projects-root",
        type=Path,
        default=Path(os.environ.get("GIG_PROJECTS_ROOT", str(default_root / "projects"))),
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path(os.environ.get("GIG_JANITOR_LEDGER", str(default_root / "janitor.jsonl"))),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    summary = scan(args.projects_root, args.ledger, dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
