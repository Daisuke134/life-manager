#!/usr/bin/env python3
"""Repository-independent single-owner fence for Writer publication workers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


ALLOWED_METADATA = {"owner.json"}


class FenceError(RuntimeError):
    pass


def process_start(pid: int) -> str:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        capture_output=True,
        text=True,
        check=False,
        timeout=2,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def read_owner(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads((path / "owner.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    if not all(isinstance(value.get(key), str) and value[key] for key in ("token", "start")):
        return None
    if not isinstance(value.get("pid"), int) or value["pid"] <= 0:
        return None
    return value


def owner_alive(owner: dict[str, object]) -> bool:
    pid = int(owner["pid"])
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return str(owner["start"]) == process_start(pid)


def identity(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return int(stat.st_dev), int(stat.st_ino), int(stat.st_mtime_ns)


def remove_quarantine(path: Path) -> None:
    children = list(path.iterdir())
    if any(child.name not in ALLOWED_METADATA or not child.is_file() for child in children):
        raise FenceError("stale owner fence contains unexpected files")
    for child in children:
        child.unlink()
    path.rmdir()


def acquire(path: Path, owner: str, root: str, state: str, run_id: str) -> str:
    path = path.expanduser().absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
    except FileExistsError as error:
        snapshot = identity(path)
        current = read_owner(path)
        if current is None:
            raise FenceError("owner fence identity is missing or invalid") from error
        if owner_alive(current):
            raise FenceError(f"owner fence is held by pid {current['pid']}") from error
        quarantine = path.with_name(f".{path.name}.stale-{os.getpid()}-{uuid.uuid4().hex}")
        path.rename(quarantine)
        try:
            if identity(quarantine) != snapshot:
                raise FenceError("owner fence identity changed during stale recovery")
            remove_quarantine(quarantine)
        except Exception:
            if not path.exists():
                quarantine.rename(path)
            raise
        path.mkdir()

    token = uuid.uuid4().hex
    payload = {
        "version": 1,
        "token": token,
        "pid": os.getpid(),
        "start": process_start(os.getpid()),
        "owner": owner,
        "root": str(Path(root).absolute()),
        "state": str(Path(state).absolute()),
        "run_id": run_id,
    }
    if not payload["start"]:
        path.rmdir()
        raise FenceError("owner process start time is unavailable")
    temporary = path / f".owner-{os.getpid()}.tmp"
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path / "owner.json")
    return token


def release(path: Path, token: str) -> None:
    path = path.expanduser().absolute()
    owner = read_owner(path)
    if owner is None or owner.get("token") != token:
        raise FenceError("owner fence token does not match")
    (path / "owner.json").unlink()
    path.rmdir()


def write_pre_effect_hint() -> None:
    path_value = os.environ.get("LIFE_MANAGER_RESULT_HINT_PATH", "")
    if not path_value:
        return
    path = Path(path_value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write('{"status":"pre_effect_failure","effect":0}\n')
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.chmod(path, 0o600)


def run(args: argparse.Namespace) -> int:
    try:
        token = acquire(Path(args.fence_dir), args.owner, args.root, args.state, args.run_id)
    except (FenceError, OSError, ValueError):
        # Acquisition refusal happens before the child publisher can start.
        # Preserve that exact boundary for lm-loop-run instead of creating an
        # effect-unknown fence for a provider action that never ran.
        try:
            write_pre_effect_hint()
        except OSError:
            pass
        raise
    environment = os.environ.copy()
    environment["ARTICLE_OWNER_FENCE_ACTIVE"] = "1"
    environment["ARTICLE_OWNER_FENCE_DIR"] = str(Path(args.fence_dir).expanduser().absolute())
    try:
        return subprocess.call(args.command, env=environment)
    finally:
        release(Path(args.fence_dir), token)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--fence-dir", required=True)
    common.add_argument("--owner", required=True)
    common.add_argument("--root", required=True)
    common.add_argument("--state", required=True)
    common.add_argument("--run-id", required=True)
    acquire_parser = subparsers.add_parser("acquire", parents=[common])
    run_parser = subparsers.add_parser("run", parents=[common])
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("--fence-dir", required=True)
    release_parser.add_argument("--token", required=True)
    args = parser.parse_args()
    if args.action == "acquire":
        print(acquire(Path(args.fence_dir), args.owner, args.root, args.state, args.run_id))
        return 0
    if args.action == "release":
        release(Path(args.fence_dir), args.token)
        return 0
    if not args.command or args.command[0] == "--":
        if args.command and args.command[0] == "--":
            args.command = args.command[1:]
        if not args.command:
            raise FenceError("run requires a command")
    return run(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FenceError, OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        raise SystemExit(75)
