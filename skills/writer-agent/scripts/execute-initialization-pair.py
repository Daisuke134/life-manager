#!/usr/bin/env python3
"""Execute one persisted, already-preflighted staging row for a missing target."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone


TARGET_KINDS = {
    "note/ja": "note-key",
    "devto/en": "devto-article-id",
}
RELEASE_NAME = re.compile(r"^[0-9]{8}T[0-9]{6}-[0-9a-f]{8,40}$")


def _writer_root() -> Path:
    """Return the caller's immutable Writer release, never a compatibility path."""
    raw = os.environ.get("ARTICLE_ROOT", "").strip()
    if not raw:
        raise SystemExit("refuse initialization rebind: ARTICLE_ROOT is required")
    root = Path(raw)
    if root.is_symlink():
        raise SystemExit("refuse initialization rebind: ARTICLE_ROOT must not be a symlink")
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise SystemExit("refuse initialization rebind: ARTICLE_ROOT is unavailable") from error
    release = root.parent.parent
    if (
        root.name != "writer-agent"
        or root.parent.name != "skills"
        or release.parent.name != "releases"
        or not RELEASE_NAME.fullmatch(release.name)
        or release.is_symlink()
    ):
        raise SystemExit("refuse initialization rebind: ARTICLE_ROOT is not an immutable release")
    return root


def rebind_missing_writer_argv(argv: list[str]) -> tuple[list[str], bool]:
    """Repoint only a missing script from a deleted Writer release.

    The dispatch manifest is immutable historical evidence.  If its executable
    disappeared during release GC, derive the same relative script from the
    immutable release selected by the current worker and leave every payload
    argument untouched.  Unknown paths are not guessed or rewritten.
    """
    rebound = list(argv)
    changed = False
    writer_root: Path | None = None
    for index, value in enumerate(argv):
        if not isinstance(value, str) or Path(value).exists():
            continue
        parts = Path(value).parts
        marker = next(
            (
                position
                for position in range(len(parts) - 1)
                if parts[position : position + 2] == ("skills", "writer-agent")
            ),
            None,
        )
        if marker is None:
            continue
        if marker + 2 >= len(parts) or parts[marker + 2] != "scripts":
            continue
        if writer_root is None:
            writer_root = _writer_root()
        candidate = writer_root.joinpath(*parts[marker + 2 :])
        if candidate.is_symlink() or not candidate.is_file():
            continue
        rebound[index] = str(candidate)
        changed = True
    return rebound, changed


def _argv_sha256(argv: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def write_rebind_receipt(
    run_dir: Path,
    pair: str,
    original_argv: list[str],
    rebound_argv: list[str],
    manifest_path: Path,
) -> Path:
    """Persist an idempotent audit of a historical executable rebind."""
    receipt = run_dir / "gates" / f"platform-dispatch-rebind-{pair.replace('/', '-')}.json"
    payload = {
        "schema": "writer.platform-dispatch-rebind",
        "version": 1,
        "pair": pair,
        "reason": "frozen release executable missing; current immutable release selected",
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "old_argv_sha256": _argv_sha256(original_argv),
        "new_argv_sha256": _argv_sha256(rebound_argv),
        "old_executables": [value for value in original_argv if "/skills/writer-agent/scripts/" in value],
        "new_executables": [value for value in rebound_argv if "/skills/writer-agent/scripts/" in value],
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if receipt.exists():
        try:
            existing = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SystemExit("refuse initialization rebind: existing receipt is unreadable") from error
        immutable = (
            "schema",
            "version",
            "pair",
            "manifest_path",
            "manifest_sha256",
            "old_argv_sha256",
            "new_argv_sha256",
        )
        if any(existing.get(key) != payload[key] for key in immutable):
            raise SystemExit("refuse initialization rebind: receipt conflicts with manifest")
        return receipt
    receipt.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{receipt.name}.", suffix=".tmp", dir=receipt.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, receipt)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", required=True, choices=tuple(TARGET_KINDS))
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--ledger", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    state_path = Path(args.state).resolve()
    ledger_path = Path(args.ledger).resolve()
    manifest_path = run_dir / "gates" / "platform-dispatch.jsonl"
    state = json.loads(state_path.read_text())
    if args.pair in state.get("pairs", {}):
        raise SystemExit(f"refuse initialization: {args.pair} already has a persisted pair")

    platform, lang = args.pair.split("/", 1)
    rows = [
        json.loads(line)
        for line in manifest_path.read_text().splitlines()
        if line.strip()
    ]
    matching = [
        row
        for row in rows
        if row.get("platform") == platform and row.get("lang") == lang
    ]
    if len(matching) != 1:
        raise SystemExit(
            f"refuse initialization: expected one {args.pair} manifest row, got {len(matching)}"
        )
    row = matching[0]
    argv = row.get("argv")
    persisted_env = row.get("env")
    if not isinstance(argv, list) or not argv or not all(
        isinstance(value, str) and value for value in argv
    ):
        raise SystemExit("refuse initialization: invalid argv")
    if not isinstance(persisted_env, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in persisted_env.items()
    ):
        raise SystemExit("refuse initialization: invalid env")

    required_paths = {
        "ARTICLE_RUN_DIR": run_dir,
        "ARTICLE_PUBLICATION_STATE": state_path,
        "ARTICLE_LEDGER": ledger_path,
    }
    for key, expected in required_paths.items():
        actual = persisted_env.get(key)
        if not actual or Path(actual).resolve() != expected:
            raise SystemExit(
                f"refuse initialization: manifest {key} does not match authoritative plan"
            )
    managed_controls = {
        "ARTICLE_AUTOPUBLISH": "1",
        "ARTICLE_PUBLISH_PAIR": args.pair,
    }
    for key, expected in managed_controls.items():
        # Early dispatch manifests froze only payload-bound paths.  These two
        # controls are derived from this guarded pair, not article content, so
        # backfill a missing legacy value but reject an explicit conflict.
        actual = persisted_env.get(key)
        if actual is not None and actual != expected:
            raise SystemExit(
                f"refuse initialization: manifest {key} does not match authoritative plan"
            )

    original_argv = list(argv)
    argv, rebound = rebind_missing_writer_argv(argv)
    if rebound:
        write_rebind_receipt(run_dir, args.pair, original_argv, argv, manifest_path)

    env = os.environ.copy()
    env.update(persisted_env)
    env.update(managed_controls)
    completed = subprocess.run(argv, env=env, check=False)
    if completed.returncode != 0:
        return completed.returncode

    updated = json.loads(state_path.read_text())
    pair = updated.get("pairs", {}).get(args.pair, {})
    if (
        pair.get("status") != "intent"
        or pair.get("target_kind") != TARGET_KINDS[args.pair]
        or not pair.get("target")
    ):
        raise SystemExit(
            f"managed staging returned success without a durable {args.pair} intent"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
