"""One fail-closed operator-brake probe shared by every marketplace lane."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def status(
    script: Path, *, path: Path | None = None, timeout: float = 5.0,
    environment: dict[str, str] | None = None,
) -> str:
    env = dict(environment or os.environ)
    effective_path = path
    if effective_path is None and env.get("GIG_OPERATOR_BRAKE_FILE"):
        effective_path = Path(env["GIG_OPERATOR_BRAKE_FILE"])
    if effective_path is not None:
        try:
            if not effective_path.exists():
                return "free"
        except OSError:
            return "failed"
        env["GIG_OPERATOR_BRAKE_FILE"] = str(effective_path)
    if not script.is_file():
        return "failed"
    for attempt in range(2):
        try:
            completed = subprocess.run(
                [str(script), "status"], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                timeout=timeout, check=False, env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            if attempt == 0:
                continue
            return "failed"
        return {0: "held", 1: "free"}.get(completed.returncode, "failed")
    return "failed"
