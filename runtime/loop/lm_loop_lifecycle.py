"""Uniform launchd lifecycle operations with collect-all result semantics."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from runtime.loop.macos_loop_registry import validate_registry


def lifecycle_one(action: str, loop_id: str, entry: dict, agents_dir: Path,
                  launchctl: Callable[[list[str]], tuple[int, str]],
                  admission: Callable[[str], object] | None = None) -> dict:
    if action not in {"start", "stop", "restart"}:
        raise ValueError(f"invalid lifecycle action: {action}")
    label = entry["label"]
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{label}"
    plist = agents_dir / f"{label}.plist"
    operations = []

    def run(args: list[str]) -> tuple[int, str]:
        rc, detail = launchctl(args)
        operations.append({"command": args[0], "return_code": rc})
        return rc, detail

    if action == "stop":
        rc, detail = run(["bootout", service])
        if rc == 0 and admission is not None:
            admission("suspend")
        return {"loop_id": loop_id, "label": label, "action": action,
                "return_code": rc, "operations": operations, "detail": detail.strip()}

    if not plist.is_file():
        return {"loop_id": loop_id, "label": label, "action": action,
                "return_code": 2, "operations": operations,
                "detail": f"installed plist missing: {plist}"}

    if action == "start":
        print_rc, _ = run(["print", service])
        if print_rc == 0:
            action_rc, detail = run(["kickstart", service])
        else:
            action_rc, detail = run(["bootstrap", domain, str(plist)])
    else:
        run(["bootout", service])
        action_rc, detail = run(["bootstrap", domain, str(plist)])
    readback_rc, readback = run(["print", service])
    rc = action_rc or readback_rc
    if rc == 0 and admission is not None:
        admission("resume")
    return {"loop_id": loop_id, "label": label, "action": action,
            "return_code": rc, "operations": operations,
            "detail": (readback if readback_rc else detail).strip()}


def lifecycle(registry: dict, action: str, target: str,
              execute: Callable[[str, str, dict], dict]) -> list[dict]:
    validate_registry(registry)
    if action not in {"start", "stop", "restart"}:
        raise ValueError(f"invalid lifecycle action: {action}")
    if target == "all":
        loop_ids = sorted(registry["loops"])
    elif target in registry["loops"]:
        loop_ids = [target]
    else:
        raise ValueError(f"unknown loop id: {target}")
    results = []
    for loop_id in loop_ids:
        entry = registry["loops"][loop_id]
        try:
            results.append(execute(action, loop_id, entry))
        except Exception as exc:
            results.append({"loop_id": loop_id, "label": entry["label"],
                            "action": action, "return_code": 1,
                            "operations": [], "detail": str(exc)})
    return results
