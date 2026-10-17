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
V1_PLATFORM_PAIRS = {
    "note/ja": {("note", "ja")},
    "substack/ja": {("substack-ja", "ja"), ("substack", "ja")},
    "substack/en": {("substack-en", "en"), ("substack", "en")},
    "x-article/ja": {("x-article", "ja")},
}


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

    cta_mode = persisted_env.get("ARTICLE_PUBLISH_CTA_V1", "")
    if cta_mode and cta_mode != "1":
        raise SystemExit("refuse initialization: invalid ARTICLE_PUBLISH_CTA_V1")
    publisher_copy: Path | None = None
    if cta_mode == "1":
        if args.pair not in V1_PLATFORM_PAIRS:
            raise SystemExit("refuse initialization: publisher CTA v1 pair is not active")
        v1_pairs: list[str] = []
        landing_urls: set[str] = set()
        product_ids: set[str] = set()
        from publication_contract import NEWLY_DORMANT_PAIRS

        for item in rows:
            item_env = item.get("env")
            item_argv = item.get("argv")
            item_pair = (
                item_env.get("ARTICLE_PUBLISH_PAIR")
                if isinstance(item_env, dict)
                else None
            )
            if item_pair in NEWLY_DORMANT_PAIRS:
                # Manifests written while x-article/ja was still listed as
                # active carry its row; it is dormant and never staged here.
                continue
            if item_pair not in V1_PLATFORM_PAIRS:
                raise SystemExit("refuse initialization: v1 manifest contains a non-active pair")
            if item_env.get("ARTICLE_PUBLISH_CTA_V1") != "1":
                raise SystemExit("refuse initialization: all active rows must opt into publisher CTA v1")
            if (item.get("platform"), item.get("lang")) not in V1_PLATFORM_PAIRS[item_pair]:
                raise SystemExit("refuse initialization: v1 manifest pair/platform mismatch")
            if not isinstance(item_argv, list) or not all(isinstance(value, str) for value in item_argv):
                raise SystemExit("refuse initialization: v1 manifest argv is invalid")
            item_run_dir = Path(str(item_env.get("ARTICLE_RUN_DIR", ""))).resolve()
            item_state = Path(str(item_env.get("ARTICLE_PUBLICATION_STATE", ""))).resolve()
            item_ledger = Path(str(item_env.get("ARTICLE_LEDGER", ""))).resolve()
            if (
                item_run_dir != run_dir
                or item_state != state_path
                or item_ledger != ledger_path
            ):
                raise SystemExit("refuse initialization: v1 manifest paths do not match the current run")
            item_lang = item_pair.rsplit("/", 1)[1]
            item_source = run_dir / f"article-{item_lang}.md"
            matches = []
            for value in item_argv:
                try:
                    candidate = Path(value)
                    if candidate.is_absolute() and candidate.resolve(strict=True) == item_source.resolve(strict=True):
                        matches.append(value)
                except (OSError, RuntimeError):
                    continue
            if len(matches) != 1:
                raise SystemExit("refuse initialization: v1 argv must contain its frozen source exactly once")
            landing_urls.add(
                item_env.get("ARTICLE_PRODUCT_LANDING_URL")
                or os.environ.get("ARTICLE_PRODUCT_LANDING_URL", "")
            )
            product_ids.add(
                item_env.get("ARTICLE_PRODUCT_ID")
                or os.environ.get("ARTICLE_PRODUCT_ID", "")
            )
            v1_pairs.append(item_pair)
        from publisher_cta_copy import (
            ACTIVE_PUBLISHER_PAIRS,
            PublisherCTAError,
            prepare_all,
            publisher_copy_path,
        )
        # Resume does not inherit article-daily's product env; the CTA
        # contract persisted at first dispatch is the authoritative value.
        contract_path = run_dir / "gates" / "publisher-cta" / "contract.json"
        if "" in landing_urls | product_ids and contract_path.is_file():
            try:
                persisted = json.loads(contract_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise SystemExit("refuse initialization: publisher CTA contract is unreadable") from error
            landing_urls = {value or str(persisted.get("landing_url") or "") for value in landing_urls}
            product_ids = {value or str(persisted.get("product_id") or "") for value in product_ids}
        if (
            len(v1_pairs) != len(ACTIVE_PUBLISHER_PAIRS)
            or set(v1_pairs) != set(ACTIVE_PUBLISHER_PAIRS)
            or len(v1_pairs) != len(set(v1_pairs))
            or len(landing_urls) != 1
            or not next(iter(landing_urls))
            or len(product_ids) != 1
            or not next(iter(product_ids))
        ):
            raise SystemExit("refuse initialization: v1 manifest must bind every active pair once with one landing URL and product id")
        try:
            prepare_all(
                run_dir,
                landing_url=next(iter(landing_urls)),
                product_id=next(iter(product_ids)),
            )
            source = run_dir / f"article-{args.pair.rsplit('/', 1)[1]}.md"
            publisher_copy = publisher_copy_path(run_dir, args.pair, source)
        except (PublisherCTAError, OSError, ValueError) as error:
            raise SystemExit(f"refuse initialization: publisher CTA v1 copy is invalid: {error}") from error
    elif args.pair in V1_PLATFORM_PAIRS:
        from publisher_cta_copy import PublisherCTAError, verify_legacy_source

        try:
            verify_legacy_source(
                run_dir,
                args.pair,
                run_dir / f"article-{args.pair.rsplit('/', 1)[1]}.md",
            )
        except (PublisherCTAError, OSError, ValueError) as error:
            raise SystemExit(f"refuse initialization: v1 publisher copy is required: {error}") from error

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
    if publisher_copy is not None:
        env["ARTICLE_PUBLISH_COPY_PATH"] = str(publisher_copy)
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
