#!/usr/bin/env python3
"""Persist Capafy candidates that are built and tested before platform submission."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path


STATE_HOME = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", Path.home() / ".local/state/life-manager")).expanduser()
DEFAULT_FEATURES = STATE_HOME / "features"
DEFAULT_ICONS = STATE_HOME / "assets/capafy/icons"
DEFAULT_OUTPUT = STATE_HOME / "state/capafy-candidate-backlog.json"
REPO_ROOT = Path(os.environ.get("LIFE_MANAGER_REPO", Path(__file__).resolve().parents[3]))
DEFAULT_CATALOG = REPO_ROOT / "skills/capafy/catalog"
TERMINAL_PLATFORM_STATES = {"online"}
RETRY_PLATFORM_STATES = {"review_rejected"}


def _candidate_state(remote_status: str | None, complete: bool) -> str:
    if remote_status in TERMINAL_PLATFORM_STATES:
        return "listed"
    if remote_status in RETRY_PLATFORM_STATES:
        return "ready_retry" if complete else "building"
    if remote_status:
        return "submitted"
    return "ready" if complete else "building"


def _title(listing: Path) -> str | None:
    try:
        lines = listing.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for index, line in enumerate(lines[:-1]):
        if line.strip() == "## Title":
            value = lines[index + 1].strip()
            return value or None
    return None


def _content_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda value: str(value)):
        digest.update(path.name.encode())
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _candidate_dirs(features: Path) -> list[Path]:
    if not features.is_dir():
        return []
    return sorted(path for path in features.iterdir() if path.is_dir() and path.name.startswith("capafy-"))


def _platform_by_title(inventory: dict) -> dict[str, dict]:
    rows = inventory.get("agents") if isinstance(inventory, dict) else None
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("name") or "").strip(): row
        for row in rows
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    }


def refresh_backlog(existing: dict, inventory: dict, features: Path, icons: Path, observed_at: str,
                    catalog: Path | None = None) -> dict:
    old_items = existing.get("items") if isinstance(existing, dict) else None
    old_by_id = {
        item.get("candidate_id"): item
        for item in old_items if isinstance(item, dict) and item.get("candidate_id")
    } if isinstance(old_items, list) else {}
    platform = _platform_by_title(inventory)
    items = []
    for directory in _candidate_dirs(features):
        match = re.match(r"^capafy-([a-z][0-9]+)-", directory.name)
        if not match:
            continue
        skill = directory / "SKILL.md"
        listing = directory / "LISTING.md"
        icon = icons / f"{match.group(1)}.png"
        tests = sorted(path for path in (directory / "test").glob("*") if path.is_file()) if (directory / "test").is_dir() else []
        title = _title(listing)
        gates = {
            "skill": "pass" if skill.is_file() and skill.stat().st_size > 0 else "missing",
            "listing": "pass" if title else "missing",
            "icon": "pass" if icon.is_file() and icon.stat().st_size > 0 else "missing",
            "tests": "pass" if tests and all(path.stat().st_size > 0 for path in tests) else "missing",
        }
        complete = all(value == "pass" for value in gates.values())
        remote = platform.get(title or "")
        remote_status = remote.get("remote_status") if remote else None
        platform_state = remote_status or "not_submitted"
        state = _candidate_state(remote_status, complete)
        paths = [skill, listing, icon, *tests]
        old = old_by_id.get(directory.name, {})
        item = {
            "candidate_id": directory.name,
            "title": title,
            "state": state,
            "platform_state": platform_state,
            "gates": gates,
            "content_sha256": _content_hash(paths),
            "paths": {"feature": str(directory), "skill": str(skill), "listing": str(listing), "icon": str(icon), "tests": [str(path) for path in tests]},
            "first_observed_at": old.get("first_observed_at") or observed_at,
            "last_observed_at": observed_at,
        }
        if remote and remote.get("agent_id"):
            item["agent_id"] = str(remote["agent_id"])
        items.append(item)
    if catalog and catalog.is_dir():
        for directory in sorted(path for path in catalog.iterdir() if path.is_dir()):
            skill = directory / "SKILL.md"
            listing = directory / "LISTING.md"
            # Capafy's CP1 logo cropper accepts raster files only. Prefer a
            # publishable listing asset over the source SVG.
            icon = next((directory / name for name in ("icon.png", "icon.jpg", "icon.webp", "icon.svg")
                         if (directory / name).is_file()), directory / "icon.svg")
            title = _title(listing)
            gates = {
                "skill": "pass" if skill.is_file() and skill.stat().st_size > 0 else "missing",
                "listing": "pass" if title else "missing",
                "icon": "pass" if icon.is_file() and icon.stat().st_size > 0 else "missing",
                "tests": "not_required",
            }
            complete = all(gates[key] == "pass" for key in ("skill", "listing", "icon"))
            remote = platform.get(title or "")
            remote_status = remote.get("remote_status") if remote else None
            platform_state = remote_status or "not_submitted"
            state = _candidate_state(remote_status, complete)
            candidate_id = f"catalog:{directory.name}"
            old = old_by_id.get(candidate_id, {})
            item = {
                "candidate_id": candidate_id,
                "title": title,
                "state": state,
                "platform_state": platform_state,
                "gates": gates,
                "content_sha256": _content_hash([skill, listing, icon]),
                "paths": {"feature": str(directory), "skill": str(skill), "listing": str(listing), "icon": str(icon), "tests": []},
                "first_observed_at": old.get("first_observed_at") or observed_at,
                "last_observed_at": observed_at,
            }
            if remote and remote.get("agent_id"):
                item["agent_id"] = str(remote["agent_id"])
            items = [prior for prior in items if prior.get("title") != title]
            items.append(item)
    return {
        "schema_version": 1,
        "updated_at": observed_at,
        "items": items,
        "counts": {
            "total": len(items),
            "building": sum(item["state"] == "building" for item in items),
            "ready": sum(item["state"] == "ready" for item in items),
            "ready_retry": sum(item["state"] == "ready_retry" for item in items),
            "submitted": sum(item["state"] == "submitted" for item in items),
            "listed": sum(item["state"] == "listed" for item in items),
        },
    }


def atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("refresh", nargs="?")
    parser.add_argument("--inventory-stdin", action="store_true")
    parser.add_argument("--inventory-json", type=Path)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--icons", type=Path, default=DEFAULT_ICONS)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--observed-at")
    args = parser.parse_args(argv)
    if args.inventory_stdin:
        inventory = json.load(sys.stdin)
    elif args.inventory_json:
        inventory = json.loads(args.inventory_json.read_text())
    else:
        print(json.dumps({"ok": False, "reason": "inventory_required"}))
        return 2
    try:
        existing = json.loads(args.output.read_text()) if args.output.exists() else {}
    except (OSError, json.JSONDecodeError):
        print(json.dumps({"ok": False, "reason": "existing_backlog_invalid"}))
        return 1
    observed_at = args.observed_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    backlog = refresh_backlog(existing, inventory, args.features, args.icons, observed_at, args.catalog)
    atomic_write(args.output, backlog)
    print(json.dumps({"ok": True, "path": str(args.output), **backlog["counts"]}, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
