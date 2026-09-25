#!/usr/bin/env python3
"""Fail-closed health gate for macOS user launchd mutations."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

Runner = Callable[..., subprocess.CompletedProcess[str]]


def probe(runner: Runner = subprocess.run) -> dict:
    observations: dict[str, dict] = {}

    def run(name: str, argv: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            result = runner(argv, capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = subprocess.CompletedProcess(argv, 124, "", f"{type(exc).__name__}: {exc}")
        stdout = result.stdout.strip()
        # A domain dump can contain unrelated service environment.  The gate
        # needs only the return code; retain one identifying line, never the dump.
        if name == "gui_domain":
            stdout = stdout.splitlines()[0] if stdout else ""
        observations[name] = {
            "argv": argv,
            "returncode": int(result.returncode),
            "stdout": stdout,
            "stderr": result.stderr.strip()[-2000:],
        }
        return result

    uid_result = run("uid", ["/usr/bin/id", "-u"])
    user_result = run("username", ["/usr/bin/id", "-un"])
    uid = uid_result.stdout.strip()
    username = user_result.stdout.strip()
    if uid.isdigit() and username and not username.isdigit():
        run("directory_services", ["/usr/bin/dscl", ".", "-read", f"/Users/{username}", "UniqueID"])
    else:
        observations["directory_services"] = {
            "argv": [], "returncode": 75, "stdout": "", "stderr": "username_unresolved"
        }
    managername = run("managername", ["/bin/launchctl", "managername"])
    manageruid = run("manageruid", ["/bin/launchctl", "manageruid"])
    managerpid = run("managerpid", ["/bin/launchctl", "managerpid"])
    owner_ready = (
        uid.isdigit()
        and bool(username) and not username.isdigit()
        and observations["directory_services"]["returncode"] == 0
        and f"UniqueID: {uid}" in observations["directory_services"]["stdout"]
        and managername.returncode == 0 and managername.stdout.strip() == "Aqua"
        and manageruid.returncode == 0 and manageruid.stdout.strip() == uid
        and managerpid.returncode == 0 and managerpid.stdout.strip().isdigit()
    )
    if owner_ready:
        run("gui_domain", ["/bin/launchctl", "print", f"gui/{uid}"])
    else:
        observations["gui_domain"] = {
            "argv": [], "returncode": 75, "stdout": "",
            "stderr": "owner_prerequisites_failed_before_gui_probe",
        }

    errors = []
    if not uid.isdigit():
        errors.append("uid_unresolved")
    if not username or username.isdigit():
        errors.append("username_unresolved")
    ds = observations["directory_services"]
    if ds["returncode"] != 0 or (uid.isdigit() and f"UniqueID: {uid}" not in ds["stdout"]):
        errors.append("directory_services_unresolved")
    if observations["managername"]["returncode"] != 0 or observations["managername"]["stdout"] != "Aqua":
        errors.append("manager_not_aqua")
    if observations["manageruid"]["returncode"] != 0 or observations["manageruid"]["stdout"] != uid:
        errors.append("manager_uid_mismatch")
    if observations["managerpid"]["returncode"] != 0 or not observations["managerpid"]["stdout"].isdigit():
        errors.append("manager_pid_unresolved")
    if observations["gui_domain"]["returncode"] != 0:
        errors.append("gui_domain_unreadable")

    return {
        "schema": "life-manager.launchd-control-plane-preflight.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not errors else "blocked_control_plane",
        "mutation_allowed": not errors,
        "errors": errors,
        "observations": observations,
    }


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path.home() / ".local/state/life-manager/launchd-control-plane-preflight.json",
    )
    args = parser.parse_args()
    payload = probe()
    try:
        write_atomic(args.receipt, payload)
    except OSError as exc:
        failure = dict(payload)
        failure["status"] = "blocked_control_plane"
        failure["mutation_allowed"] = False
        failure["receipt_written"] = False
        failure["errors"] = [*payload.get("errors", []), "receipt_write_failed"]
        receipt_error = {"error_class": type(exc).__name__}
        if isinstance(exc.errno, int):
            receipt_error["errno"] = exc.errno
        failure["receipt_write_error"] = receipt_error
        print(json.dumps(failure, ensure_ascii=False))
        return 75
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["mutation_allowed"] else 75


if __name__ == "__main__":
    raise SystemExit(main())
