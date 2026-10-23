#!/usr/bin/env python3
"""Guard independent Manager's runtime package against foreign imports and effects."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "manager_core"
BANNED_MODULES = {"life_manager", "lifemanager", "agentforce", "src"}
BANNED_MODULE_PREFIXES = {"apps.life_manager", "apps.life-manager"}


def validate() -> None:
    for file in RUNTIME.rglob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if module.split(".")[0].lower() in BANNED_MODULES or any(
                    module.lower().startswith(prefix) for prefix in BANNED_MODULE_PREFIXES
                ):
                    raise ValueError(f"Foreign runtime dependency {module!r} in {file}")
    print("PASS: manager_core has no banned Life Manager imports")


if __name__ == "__main__":
    validate()
