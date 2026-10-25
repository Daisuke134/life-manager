"""Per-owner host bindings. This file never reads or copies authentication values."""

from __future__ import annotations

import copy
import json
import os
import stat
import uuid
from pathlib import Path

HOST_ENVIRONMENT_KEYS = frozenset({
    "LIFE_MANAGER_HOST_PROFILE", "LIFE_MANAGER_RUNTIME_PYTHON", "LIFE_MANAGER_PYTHON",
    "LIFE_MANAGER_LEASE_PYTHON",
    "LIFE_MANAGER_RUNTIME_NODE", "LIFE_MANAGER_NODE", "AGENT_RUNNER_CONFIG",
    "AI_BROWSER_REGISTRY", "LIFE_MANAGER_ENV_FILE", "LIFE_MANAGER_HOME",
    "LM_SELFBUILD_SOURCE_REPO", "LIFE_MANAGER_SOURCE_REPO", "PATH",
})


def _home_path(value: str, home: Path) -> Path:
    return home / value[2:] if value.startswith("~/") else Path(value)


def _private_directory(path: Path) -> None:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("private host path contains symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _write_new(path: Path, content: str) -> None:
    _private_directory(path.parent)
    if path.is_symlink():
        raise ValueError("private host file is a symlink")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def load_host_profile(*, home: Path | None = None,
                      profile_path: Path | None = None) -> dict | None:
    raw_home = Path(home or Path.home()).absolute()
    home = raw_home.resolve()
    path = Path(profile_path or os.environ.get("LIFE_MANAGER_HOST_PROFILE")
                or home / ".config/life-manager/host.json").expanduser().absolute()
    if path.is_relative_to(raw_home):
        path = home / path.relative_to(raw_home)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("host profile contains symlink")
    if not path.exists():
        if profile_path is not None or os.environ.get("LIFE_MANAGER_HOST_PROFILE"):
            raise ValueError("explicit host profile is missing")
        return None
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("host profile must be owner-private (0600)")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("owner_home") != str(home):
        raise ValueError("host profile owner_home mismatch")
    for key in ("browser_registry", "agent_runner_config", "environment_file"):
        target = Path(value[key])
        if not target.is_absolute() or not target.is_relative_to(home):
            raise ValueError(f"host profile {key} must belong to owner_home")
    for key in ("python", "node"):
        executable = Path(value["runtime"][key])
        if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError(f"host runtime {key} is unavailable")
    if not Path(value["source_checkout"]).is_absolute():
        raise ValueError("host source_checkout must be absolute")
    if not isinstance(value.get("tenant_id"), str) or not value["tenant_id"].startswith("local-"):
        raise ValueError("host tenant_id is invalid")
    return value


def _browser_registry(registry: dict, home: Path) -> str:
    loops = registry["loops"]
    owners = {key: row["browser_owner"] for key, row in loops.items() if row.get("browser_owner")}
    bindings = {}
    for row in loops.values():
        identity = row.get("browser_identity")
        owner = row.get("browser_target_owner")
        if identity and owner in owners:
            bindings[identity] = (owner, owners[owner])
    # These aliases are used by committed consumers. They refer to this owner's
    # empty profiles, never the developer's session. Provisioning stays on demand.
    bindings["interactive:dais"] = ("life-manager-daily-driver", owners["life-manager-daily-driver"])
    bindings["mercor:dais"] = ("job-search-mercor-browser", {
        "profile": "~/.cloak/profiles/job-search-mercor", "cdp_port": 9334})
    bindings["promptbase:dais"] = ("promptbase-loop-daily", {
        "profile": "~/.cloak/profiles/promptbase", "cdp_port": 0})
    bindings["capafy:kosuke"] = ("capafy-browser", owners["capafy-browser"])
    assigned = {owner for owner, _ in bindings.values()}
    for owner, browser in owners.items():
        if owner not in assigned:
            bindings[f"{owner}:local"] = (owner, browser)
    lines = ["# Generated empty owner bindings; login is verified separately."]
    for identity, (owner, browser) in sorted(bindings.items()):
        lines.extend(("", "[[identity]]", f"id = {json.dumps(identity)}",
                      f"profile = {json.dumps(str(_home_path(browser['profile'], home)))}",
                      f"owner = {json.dumps(owner)}", f"declared_port = {browser['cdp_port']}"))
        launcher = loops[owner].get("label") if owner in owners else None
        external_label = f"ai.anicca.{owner}"
        if launcher is None and external_label in registry.get("external_labels", []):
            launcher = external_label
        if launcher:
            lines.append(f"launched_by = {json.dumps(launcher)}")
    return "\n".join(lines) + "\n"


def prepare_host(repo_root: Path, *, home: Path | None = None,
                 python: Path, node: Path, codex: Path | None = None) -> dict:
    raw_home = Path(home or Path.home()).absolute()
    existing = load_host_profile(home=raw_home)
    home = raw_home.resolve()
    if existing is not None:
        return existing
    config = home / ".config/life-manager"
    state = home / ".local/state/life-manager"
    value = {"schema_version": 1, "owner_home": str(home),
             "tenant_id": f"local-{uuid.uuid4().hex}",
             "source_checkout": str(repo_root.absolute()),
             "runtime": {"python": str(python.absolute()), "node": str(node.absolute())},
             "browser_registry": str(config / "browsers.toml"),
             "agent_runner_config": str(config / "agent-runner.json"),
             "environment_file": str(state / ".env")}
    registry = json.loads((repo_root / "config/loop-registry.json").read_text())
    runner = copy.deepcopy(json.loads((repo_root / "runtime/agent-runner/config.json").read_text()))
    provider = runner["providers"]["codex"]
    profiles = provider["profiles"]
    available = [alias for alias in provider["account_profile_order"]
                 if _home_path(profiles[alias]["auth_file"], home).is_file()]
    # No auth file is not an authenticated setup. Retain the single primary
    # reference so the existing runner reports its normal missing-auth result.
    selected = available or [provider["account_profile_order"][0]]
    provider["account_profile_order"] = selected
    provider["profiles"] = {alias: {key: str(_home_path(path, home))
                                    for key, path in profiles[alias].items()} for alias in selected}
    if codex is not None:
        provider["executable"] = str(codex.absolute())
        provider["executable_fallbacks"] = []
    else:
        provider["executable"] = str(home / ".local/bin/codex")
        provider["executable_fallbacks"] = []
    for task in runner["task_classes"].values():
        for candidate in task.get("candidates", []):
            if candidate.get("provider") == "codex" and candidate.get("profile_alias") not in selected:
                candidate["profile_alias"] = selected[0]
    _write_new(Path(value["browser_registry"]), _browser_registry(registry, home))
    _write_new(Path(value["agent_runner_config"]), _json(runner))
    _write_new(Path(value["environment_file"]), "# Add this owner's provider configuration here.\n")
    for row in registry["loops"].values():
        for key in ("state_root", "log_root"):
            target = _home_path(row[key], home)
            if not target.is_relative_to(home):
                raise ValueError(f"job {key} must belong to owner_home")
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
    _write_new(config / "host.json", _json(value))
    return load_host_profile(home=home)


def host_environment(*, home: Path | None = None) -> dict[str, str]:
    value = load_host_profile(home=home)
    if value is None:
        return {}
    runtime = value["runtime"]
    owner_home = Path(value["owner_home"])
    selected = Path(os.environ.get("LIFE_MANAGER_HOST_PROFILE") or owner_home / ".config/life-manager/host.json").expanduser()
    selected = selected.parent.resolve() / selected.name
    return {"LIFE_MANAGER_HOST_PROFILE": str(selected),
            "LIFE_MANAGER_RUNTIME_PYTHON": runtime["python"], "LIFE_MANAGER_PYTHON": runtime["python"],
            "LIFE_MANAGER_LEASE_PYTHON": runtime["python"],
            "LIFE_MANAGER_RUNTIME_NODE": runtime["node"], "LIFE_MANAGER_NODE": runtime["node"],
            "AGENT_RUNNER_CONFIG": value["agent_runner_config"],
            "AI_BROWSER_REGISTRY": value["browser_registry"],
            "LIFE_MANAGER_ENV_FILE": value["environment_file"],
            "LIFE_MANAGER_HOME": str(Path(value["environment_file"]).parent),
            "LM_SELFBUILD_SOURCE_REPO": value["source_checkout"],
            "LIFE_MANAGER_SOURCE_REPO": value["source_checkout"],
            "PATH": os.pathsep.join(dict.fromkeys((str(Path(runtime["python"]).parent),
                str(Path(runtime["node"]).parent), str(owner_home / ".local/bin"),
                "/opt/homebrew/bin", "/usr/local/bin", *os.defpath.split(os.pathsep))))}
