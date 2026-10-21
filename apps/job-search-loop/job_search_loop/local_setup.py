from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import ConfigError, validate_profile


PROVIDERS = ("codex",)
SCHEDULERS = ("auto", "launchd", "systemd", "none")


class SetupError(RuntimeError):
    pass


def _absolute_root(env: dict[str, str], name: str, fallback: Path) -> Path:
    raw = env.get(name, "")
    path = Path(raw) if raw else fallback
    if not path.is_absolute():
        raise SetupError(f"{name} must be an absolute path")
    return path


def resolve_roots(env: dict[str, str]) -> dict[str, Path]:
    home_raw = env.get("HOME", "")
    home = Path(home_raw) if home_raw else Path.home()
    if not home.is_absolute():
        raise SetupError("HOME must be an absolute path")
    return {
        "config": _absolute_root(env, "XDG_CONFIG_HOME", home / ".config"),
        "state": _absolute_root(
            env, "XDG_STATE_HOME", home / ".local" / "state"
        ),
        "data": _absolute_root(env, "XDG_DATA_HOME", home / ".local" / "share"),
    }


def _provider_command(provider: str, executable: str) -> list[str]:
    if provider == "codex":
        return [executable, "login", "status"]
    raise SetupError(f"unsupported provider: {provider}")


def provider_authenticated(
    provider: str,
    *,
    env: dict[str, str],
    timeout_seconds: int = 15,
) -> bool:
    executable = shutil.which(provider, path=env.get("PATH"))
    if executable is None:
        return False
    try:
        completed = subprocess.run(
            _provider_command(provider, executable),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    return True


def select_provider(requested: str, *, env: dict[str, str]) -> str:
    if requested not in {"auto", "codex"}:
        raise SetupError("provider must be codex or auto")
    candidates = PROVIDERS if requested == "auto" else (requested,)
    for provider in candidates:
        if provider_authenticated(provider, env=env):
            return provider
    raise SetupError("no authenticated provider found for Codex; run `codex login`")


def resolve_scheduler(requested: str, *, system: str | None = None) -> str:
    if requested != "auto":
        return requested
    detected = system or platform.system()
    if detected == "Darwin":
        return "launchd"
    if detected == "Linux":
        return "systemd"
    raise SetupError(f"unsupported scheduler platform: {detected or 'unknown'}")


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def _atomic_private_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(data)
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _install_codex_auth_alias(config_dir: Path, env: dict[str, str]) -> Path:
    home = Path(env.get("HOME") or Path.home())
    codex_home = _absolute_root(env, "CODEX_HOME", home / ".codex")
    source = codex_home / "auth.json"
    if not source.is_file():
        raise SetupError(f"Codex auth file not found: {source}")
    source = source.resolve(strict=True)
    alias = config_dir / "codex-auth.json"
    if alias.exists() and not alias.is_symlink():
        raise SetupError(f"Codex auth alias is not a symlink: {alias}")
    temporary = alias.with_name(f".{alias.name}.tmp-{os.getpid()}")
    try:
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(source)
        temporary.replace(alias)
    finally:
        temporary.unlink(missing_ok=True)
    return alias


def _load_profile(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SetupError(f"profile not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return validate_profile(value)
    except (OSError, json.JSONDecodeError, ConfigError) as error:
        raise SetupError(f"invalid profile: {error}") from error


def _install_materials(profile: dict[str, Any], data_dir: Path) -> Path:
    materials = profile.get("materials")
    resumes = materials.get("resumes") if isinstance(materials, dict) else None
    engineering = resumes.get("engineering") if isinstance(resumes, dict) else None
    if not isinstance(engineering, str):
        raise SetupError("profile.materials.resumes.engineering is required")
    destination = data_dir / "materials"
    resume_dir = destination / "resumes"
    _private_dir(destination)
    _private_dir(resume_dir)
    installed = {}
    for variant in ("engineering", "technical_business", "japanese"):
        raw = resumes.get(variant) or engineering
        source = Path(str(raw)).expanduser()
        if not source.is_absolute() or not source.is_file():
            raise SetupError(f"resume file is unavailable: {variant}")
        target = resume_dir / f"{variant}.pdf"
        _atomic_private_write(target, source.read_bytes())
        installed[variant] = f"resumes/{variant}.pdf"
    manifest = destination / "manifest.v1.json"
    _atomic_private_write(
        manifest,
        (
            json.dumps(
                {"version": 1, "resumes": installed},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )
    return manifest


def install(
    *,
    profile_source: Path,
    provider: str,
    scheduler: str,
    replace_profile: bool,
    env: dict[str, str],
    system: str | None = None,
) -> dict[str, Any]:
    roots = resolve_roots(env)
    value = _load_profile(profile_source)
    selected_provider = select_provider(provider, env=env)
    selected_scheduler = resolve_scheduler(scheduler, system=system)

    config_dir = roots["config"] / "anicca" / "job-search"
    state_dir = roots["state"] / "anicca" / "job-search"
    data_dir = roots["data"] / "anicca" / "job-search"
    profile_path = config_dir / "profile.json"
    install_path = config_dir / "install.json"
    source_is_active = (
        profile_path.exists()
        and profile_source.resolve() == profile_path.resolve()
    )
    if profile_path.exists() and not replace_profile and not source_is_active:
        raise SetupError(
            f"private profile already exists: {profile_path}; "
            "use --replace-profile to replace it"
        )

    for directory in (config_dir, state_dir, data_dir):
        _private_dir(directory)
    material_manifest = _install_materials(value, data_dir)
    auth_alias = (
        _install_codex_auth_alias(config_dir, env)
        if selected_provider == "codex"
        else None
    )
    if not source_is_active:
        encoded_profile = (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _atomic_private_write(profile_path, encoded_profile)
    else:
        os.chmod(profile_path, 0o600)
    receipt = {
        "version": 1,
        "provider": selected_provider,
        "scheduler": selected_scheduler,
        "profile_path": str(profile_path),
        "state_root": str(state_dir),
        "data_root": str(data_dir),
        "material_manifest": str(material_manifest),
    }
    if auth_alias is not None:
        receipt["codex_auth_alias"] = str(auth_alias)
    _atomic_private_write(
        install_path,
        (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument(
        "--provider", choices=("auto", *PROVIDERS), default="auto"
    )
    parser.add_argument("--scheduler", choices=SCHEDULERS, default="auto")
    parser.add_argument("--replace-profile", action="store_true")
    parsed = parser.parse_args(argv)
    try:
        receipt = install(
            profile_source=parsed.profile,
            provider=parsed.provider,
            scheduler=parsed.scheduler,
            replace_profile=parsed.replace_profile,
            env=dict(os.environ),
        )
    except SetupError as error:
        print(f"job-search setup: {error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
