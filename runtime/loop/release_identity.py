"""Fail-closed identity checks for one immutable Life Manager loop release."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path


RELEASE_SHA = re.compile(r"[0-9a-f]{40}\Z")
CONTROL_PLANE_LOOP_IDS = frozenset({"life-manager-release-reconciler"})


class ReleaseIdentityError(RuntimeError):
    """A launch identity cannot be trusted to execute the requested loop."""

    def __init__(self, blocker: str, detail: str):
        self.blocker = blocker
        super().__init__(f"{blocker}: {detail}")


def _canonical_root(value: str | Path, *, field: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ReleaseIdentityError("runtime_identity_mismatch", f"{field} is not absolute")
    try:
        root = candidate.resolve(strict=True)
    except OSError as error:
        raise ReleaseIdentityError(
            "runtime_identity_mismatch", f"{field} is not readable"
        ) from error
    if not root.is_dir():
        raise ReleaseIdentityError("runtime_identity_mismatch", f"{field} is not a directory")
    return root


def read_release_manifest(release_root: str | Path) -> tuple[Path, dict]:
    root = _canonical_root(release_root, field="release_root")
    try:
        manifest = json.loads((root / "RELEASE.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ReleaseIdentityError("runtime_identity_mismatch", "release manifest is invalid") from error
    if not isinstance(manifest, dict) or not RELEASE_SHA.fullmatch(str(manifest.get("sha", ""))):
        raise ReleaseIdentityError("runtime_identity_mismatch", "release manifest SHA is invalid")
    return root, manifest


def _env_root(environment: Mapping[str, str], key: str, expected: Path) -> None:
    value = environment.get(key)
    if value is None:
        return
    actual = _canonical_root(value, field=key)
    if actual != expected:
        raise ReleaseIdentityError("runtime_identity_mismatch", f"{key} does not match release_root")


def _env_equal(environment: Mapping[str, str], key: str, expected: str) -> None:
    value = environment.get(key)
    if value is not None and value != expected:
        raise ReleaseIdentityError("runtime_identity_mismatch", f"{key} does not match registry")


def _resource_class(entry: dict) -> str:
    return entry.get("resource_class") or (
        "agent" if entry["provider_route"] == "shared-agent-runner" else "deterministic"
    )


def _state_path(value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ReleaseIdentityError("runtime_identity_mismatch", "state root is not absolute")
    return candidate.resolve(strict=False)


def _current_sha(current: str | Path) -> str | None:
    path = Path(current).expanduser()
    if not path.exists() and not path.is_symlink():
        return None
    _root, manifest = read_release_manifest(path)
    return str(manifest["sha"])


def validate_runtime_identity(
    registry: dict,
    loop_id: str,
    release_root: str | Path,
    *,
    environment: Mapping[str, str] | None = None,
    current: str | Path = "~/loops/current",
    allow_current_drift: bool = False,
) -> dict[str, str]:
    """Validate argv/env/registry identity before an entrypoint can run."""
    root, manifest = read_release_manifest(release_root)
    entry = registry.get("loops", {}).get(loop_id)
    if not isinstance(entry, dict):
        raise ReleaseIdentityError("runtime_identity_mismatch", f"unknown loop id: {loop_id}")
    env = environment or os.environ
    release_sha = str(manifest["sha"])
    entrypoint = str(entry["entrypoint"])
    executable = root / entrypoint
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ReleaseIdentityError("runtime_identity_mismatch", "entrypoint is missing or not executable")

    _env_equal(env, "LIFE_MANAGER_LOOP_ID", loop_id)
    _env_equal(env, "LIFE_MANAGER_ENTRYPOINT", entrypoint)
    _env_equal(env, "LIFE_MANAGER_OWNER_ID", loop_id)
    _env_equal(env, "LIFE_MANAGER_RESOURCE_CLASS", _resource_class(entry))
    _env_equal(env, "LIFE_MANAGER_RELEASE_SHA", release_sha)
    _env_root(env, "LIFE_MANAGER_REPO", root)
    _env_root(env, "LIFE_MANAGER_RELEASE_ROOT", root)

    state_value = env.get("LIFE_MANAGER_STATE_ROOT", os.path.expanduser(entry["state_root"]))
    state_root = _state_path(state_value)
    try:
        state_root.relative_to(root)
    except ValueError:
        pass
    else:
        raise ReleaseIdentityError("runtime_identity_mismatch", "state root is inside release root")

    current_sha = _current_sha(current)
    if (current_sha is not None and current_sha != release_sha and not allow_current_drift):
        raise ReleaseIdentityError("release_drift", "loaded release differs from current release")

    return {
        "loop_id": loop_id,
        "owner_id": loop_id,
        "entrypoint": entrypoint,
        "release_sha": release_sha,
        "state_root": str(state_root),
        "resource_class": _resource_class(entry),
        "current_release_sha": current_sha or release_sha,
    }
