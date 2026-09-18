#!/usr/bin/env python3
"""Persistent per-run attempt bookkeeping for bounded quality gates."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import stat
from typing import Any


MAX_ATTEMPTS = 3


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def payload_from_output(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def paths(run_dir: Path, gate: str, lang: str) -> tuple[Path, Path, Path, Path]:
    gates = run_dir / "gates"
    return (
        gates / ".attempts" / f"{gate}-{lang}.json",
        gates / f"{gate}-{lang}.terminal.json",
        gates / f"{gate}-{lang}.json",
        gates / ".attempts" / f"{gate}-{lang}.lock",
    )


def legacy_status(gate: str, payload: dict[str, Any]) -> str | None:
    verdict = payload.get("verdict")
    if gate in {"rubric-judge", "reader-testing-gate"} and verdict == "PASS":
        return "pass"
    return None


def article_sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matches_article(payload: dict[str, Any], current_hash: str) -> bool:
    saved_hash = payload.get("article_sha256")
    return isinstance(saved_hash, str) and saved_hash == current_hash


def bounded_attempts(payload: dict[str, Any], label: str, minimum: int) -> int:
    value = payload.get("attempts")
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > MAX_ATTEMPTS
    ):
        raise ValueError(f"{label} attempts evidence is outside the bounded range")
    return value


VALID_TERMINAL_STATUSES = {"revision-required", "advisory", "pass"}


def read_evidence(
    path: Path, label: str, *, allow_empty: bool = False
) -> dict[str, Any] | None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if stat.S_ISLNK(mode):
        raise ValueError(f"{label} is a symlink")
    if not stat.S_ISREG(mode):
        raise ValueError(f"{label} is not a regular file")
    if allow_empty and path.stat().st_size == 0:
        return None
    value = read_json(path)
    if value is None:
        raise ValueError(f"{label} is malformed")
    return value


def state_attempts(
    path: Path, args: argparse.Namespace, current_hash: str
) -> int:
    state = read_evidence(path, "attempt state")
    if state is None:
        return 0
    state_hash = state.get("article_sha256")
    if (
        state.get("gate") != args.gate
        or state.get("lang") != args.lang
        or not isinstance(state_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", state_hash) is None
    ):
        raise ValueError("attempt state identity is malformed")
    attempts = bounded_attempts(state, "attempt state", 0)
    return attempts if state_hash == current_hash else 0


def terminal_record(
    path: Path, args: argparse.Namespace, *, allow_empty: bool = False
) -> tuple[dict[str, Any], int] | None:
    # A shell caller may redirect stdout directly to the canonical terminal
    # path. The shell truncates that file before `begin` runs, so an empty
    # regular file is not evidence yet; `finish` still writes and validates
    # the strict terminal receipt later.
    terminal = read_evidence(
        path, "terminal attempt evidence", allow_empty=allow_empty
    )
    if terminal is None:
        return None
    article_hash = terminal.get("article_sha256")
    status = terminal.get("status")
    if (
        terminal.get("gate") != args.gate
        or terminal.get("lang") != args.lang
        or status not in VALID_TERMINAL_STATUSES
        or not isinstance(article_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", article_hash) is None
    ):
        raise ValueError("terminal attempt evidence identity is malformed")
    attempts = bounded_attempts(terminal, "terminal", 1)
    exit_code = terminal.get("exit_code")
    non_bool_exit = isinstance(exit_code, int) and not isinstance(exit_code, bool)
    if status == "pass":
        payload = terminal.get("payload")
        if exit_code != 0 or not non_bool_exit or not isinstance(payload, dict) or payload.get("verdict") != "PASS":
            raise ValueError("terminal PASS evidence is contradictory")
    elif status == "revision-required":
        if args.gate != "reader-testing-gate" or not non_bool_exit or exit_code == 0:
            raise ValueError("terminal revision evidence is contradictory")
    elif attempts != MAX_ATTEMPTS or (
        terminal.get("reason") == "max-attempts-reached"
        and "exit_code" in terminal
    ) or (
        terminal.get("reason") != "max-attempts-reached"
        and (
            "reason" in terminal
            or not non_bool_exit
            or exit_code == 0
        )
    ):
        raise ValueError("terminal advisory evidence is contradictory")
    return terminal, attempts


def begin(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    current_hash = article_sha256(args.markdown_file)
    state_path, terminal_path, legacy_path, lock_path = paths(run_dir, args.gate, args.lang)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        state_count = state_attempts(state_path, args, current_hash)
        terminal_info = terminal_record(terminal_path, args, allow_empty=True)
        # A shell caller may redirect stdout to this legacy path. The shell
        # truncates the file before this process starts, so empty regular
        # evidence means "not present yet", not malformed evidence. Attempt
        # state and terminal evidence remain strict and fail closed.
        legacy = read_evidence(
            legacy_path, "legacy gate evidence", allow_empty=True
        )
        status = legacy_status(args.gate, legacy) if legacy else None
        legacy_current_pass = bool(status and matches_article(legacy, current_hash))
        terminal = terminal_info[0] if terminal_info else None
        terminal_count = terminal_info[1] if terminal_info else None
        current_terminal = bool(
            terminal and terminal.get("article_sha256") == current_hash
        )
        if current_terminal and terminal.get("status") in {"pass", "advisory"}:
            if state_count > 0 and state_count != terminal_count:
                raise ValueError("current terminal and attempt state disagree")
        if legacy_current_pass and current_terminal:
            if terminal.get("status") != "pass":
                raise ValueError("legacy PASS conflicts with current terminal")
            print(json.dumps({
                "action": "skip-pass",
                "attempts": terminal_count,
                "payload": terminal.get("payload"),
            }, ensure_ascii=False))
            return 0
        if legacy_current_pass:
            if state_count > 0:
                raise ValueError("legacy PASS conflicts with current attempt state")
            print(json.dumps({"action": "skip-pass", "attempts": 0, "payload": legacy}, ensure_ascii=False))
            return 0

        attempt_floor: int | None = None
        if current_terminal and terminal.get("status") == "revision-required":
            attempt_floor = max(state_count, terminal_count or 0)
        if (
            current_terminal
            and terminal.get("status") == "advisory"
        ):
            print(json.dumps({
                "action": "skip-advisory",
                "attempts": terminal_count,
                "payload": terminal.get("payload"),
            }, ensure_ascii=False))
            return 0
        if current_terminal and terminal.get("status") == "pass":
            print(json.dumps({
                "action": f"skip-{terminal['status']}",
                "attempts": terminal_count,
                "payload": terminal.get("payload"),
            }, ensure_ascii=False))
            return 0

        if attempt_floor is None:
            attempts = state_count
        else:
            attempts = attempt_floor
        if attempts >= MAX_ATTEMPTS:
            terminal = {
                "gate": args.gate,
                "lang": args.lang,
                "status": "advisory",
                "attempts": attempts,
                "reason": "max-attempts-reached",
                "article_sha256": current_hash,
            }
            atomic_write(terminal_path, terminal)
            print(json.dumps({"action": "skip-advisory", "attempts": attempts, "payload": None}))
            return 0

        attempts += 1
        atomic_write(
            state_path,
            {
                "gate": args.gate,
                "lang": args.lang,
                "attempts": attempts,
                "article_sha256": current_hash,
            },
        )
        print(json.dumps({"action": "run", "attempt": attempts}))
        return 0


def finish(args: argparse.Namespace) -> int:
    bounded_attempts({"attempts": args.attempt}, "finish", 1)
    run_dir = Path(args.run_dir)
    _, terminal_path, _, lock_path = paths(run_dir, args.gate, args.lang)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output_file) if args.output_file else None
    payload = payload_from_output(output_path)
    status = (
        "pass"
        if args.exit_code == 0
        else (
            "revision-required"
            if args.gate == "reader-testing-gate"
            else ("advisory" if args.attempt >= MAX_ATTEMPTS else None)
        )
    )
    effective_payload = payload
    if args.gate == "reader-testing-gate" and isinstance(payload, dict):
        effective_payload = payload.get("payload", payload)
    if (
        status == "pass"
        and (
            not isinstance(effective_payload, dict)
            or effective_payload.get("verdict") != "PASS"
        )
    ):
        raise ValueError("finish PASS requires a PASS payload")
    if status is None:
        return 0
    terminal = {
        "gate": args.gate,
        "lang": args.lang,
        "status": status,
        "attempts": args.attempt,
        "exit_code": args.exit_code,
        "article_sha256": article_sha256(args.markdown_file),
    }
    if effective_payload is not None:
        terminal["payload"] = effective_payload
    if output_path and output_path.is_file():
        terminal["output_sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        atomic_write(terminal_path, terminal)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--run-dir", required=True)
    common.add_argument("--gate", required=True, choices=("rubric-judge", "reader-testing-gate"))
    common.add_argument("--lang", required=True, choices=("ja", "en"))
    common.add_argument("--markdown-file", required=True)
    sub.add_parser("begin", parents=[common])
    finish_parser = sub.add_parser("finish", parents=[common])
    finish_parser.add_argument(
        "--attempt", required=True, type=int, choices=range(1, MAX_ATTEMPTS + 1)
    )
    finish_parser.add_argument("--exit-code", required=True, type=int)
    finish_parser.add_argument("--output-file")
    args = parser.parse_args()
    return begin(args) if args.command == "begin" else finish(args)


if __name__ == "__main__":
    raise SystemExit(main())
