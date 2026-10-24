#!/usr/bin/env python3
"""Connect this owner's profile to the existing three Mercor revenue owners."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
for directory in (ROOT, ROOT / "apps/job-search-loop"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from job_search_loop import local_setup, mercor_auth_readback, mercor_page_ready, profile_setup
from job_search_loop.config import validate_profile
from runtime.loop import local_install
from skills._shared import telegram
from skills.earn.lancers.scripts.install_local import _codex_login
from skills.earn.lancers.scripts import lancers_onboarding as onboarding


IDENTITY = "mercor:dais"
TASK = "mercor-revenue-application"
JOBS = (TASK, "mercor-revenue-reply", "mercor-revenue-paid")
BROWSER = local_install.MERCOR_BROWSER
ERRORS = (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError)


def _safe(path: Path) -> None:
    if path.is_symlink() or any(parent.is_symlink() and not (
            parent in (Path("/tmp"), Path("/var"), Path("/etc"))
            and parent.resolve() == Path("/private") / parent.name) for parent in path.parents):
        raise ValueError("linked_private_path")


def _read(path: Path, *, private: bool = True) -> dict:
    _safe(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or private and stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("private_file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("private_object")
    return value


def _write_once(path: Path, value: dict) -> None:
    _safe(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.TemporaryDirectory(prefix=f".{path.name}.", dir=path.parent) as directory:
        staged = Path(directory) / path.name
        local_setup._atomic_private_write(staged, (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode())
        try:
            os.link(staged, path)
        except FileExistsError:
            if _read(path) != value:
                raise ValueError("private_input_conflict")


def _profile(value: dict) -> tuple[dict, list[str]]:
    value = validate_profile(value)
    email = value["candidate"].get("application_email")
    if (profile_setup._contains_placeholder(value) or not isinstance(email, str) or "@" not in email
            or any(character.isspace() for character in email)):
        raise ValueError("candidate_profile")
    try:
        return profile_setup.prepare_profile(value), []
    except profile_setup.ProfileSetupError:
        return value, ["application_profile"]


def _candidate(source: Path | None, home: Path, environment: dict, *, write: bool) -> tuple[dict | None, list[str], list[str]]:
    destination = home / ".config/anicca/job-search/profile.json"
    try:
        value, application_missing = _profile(_read(source.expanduser().absolute() if source else destination,
                                                    private=source is None))
        if destination.exists() or destination.is_symlink():
            if _profile(_read(destination))[0] != value:
                return None, ["candidate_profile_conflict"], []
        alias = destination.with_name("codex-auth.json")
        _safe(alias.parent)
        if alias.exists() or alias.is_symlink():
            expected = Path(environment.get("CODEX_HOME") or home / ".codex") / "auth.json"
            if not alias.is_symlink() or alias.resolve(strict=True) != expected.resolve(strict=True):
                return None, ["codex_auth_binding"], []
        roots = local_setup.resolve_roots(environment)
        if any(roots[key] != path for key, path in (
            ("config", home / ".config"), ("state", home / ".local/state"), ("data", home / ".local/share"))):
            return None, ["job_search_paths"], []
        if application_missing:
            if write and not destination.exists():
                _write_once(destination, value)
            return value, [], application_missing
        data = roots["data"] / "anicca/job-search/materials"
        manifest = {"version": 1, "resumes": {variant: f"resumes/{variant}.pdf"
                                             for variant in ("engineering", "technical_business", "japanese")}}
        complete = True
        for variant in manifest["resumes"]:
            target = data / manifest["resumes"][variant]
            _safe(target)
            if target.exists():
                if not target.is_file() or target.read_bytes() != Path(value["materials"]["resumes"][variant]).read_bytes():
                    return None, ["resume_materials_conflict"], []
            else:
                complete = False
        manifest_path = data / "manifest.v1.json"
        _safe(manifest_path)
        if manifest_path.exists() and _read(manifest_path) != manifest:
            return None, ["resume_materials_conflict"], []
        complete = complete and manifest_path.exists()
        receipt = destination.with_name("install.json")
        _safe(receipt)
        if receipt.exists():
            previous = _read(receipt)
            if (not complete or previous.get("profile_path") != str(destination)
                    or previous.get("provider") != "codex"):
                return None, ["job_search_install_conflict"], []
        if write:
            if not destination.exists():
                _write_once(destination, value)
            if not receipt.exists():
                local_setup.install(profile_source=destination, provider="codex", scheduler="none",
                                    replace_profile=False, env=environment)
        return value, [], []
    except ERRORS:
        return None, ["candidate_profile"], []


def _resume(home: Path, environment: dict, *, write: bool) -> list[str]:
    installed = home / ".local/share/anicca/job-search/materials/resumes/engineering.pdf"
    path = home / ".local/state/anicca/job-search/mercor/application/resume-state.json"
    legacy = path.parent.parent / "resume-state.json"
    try:
        _safe(installed)
        selected = path if path.exists() or path.is_symlink() else legacy
        value = _read(selected) if selected.exists() or selected.is_symlink() else {"resume_file": str(installed)}
        if value.get("resume_file") != str(installed):
            return ["resume_state_conflict"]
        override = environment.get("MERCOR_RESUME")
        if override and override != str(installed):
            return ["resume_runtime_reference"]
        _safe(path)
        if write and not path.exists():
            _write_once(path, value)
        return [] if installed.is_file() else ["resume_runtime_reference"]
    except ERRORS:
        return ["resume_state_conflict"]


def _gmail_missing(account: str | None, environment: dict, *, observe: bool) -> list[str]:
    executable = environment.get("JOB_SEARCH_GOG") or shutil.which("gog", path=environment.get("PATH"))
    if not executable:
        return ["gmail_executable", "gmail_authorization"]
    if observe and account:
        try:
            result = subprocess.run([executable, "auth", "list", "--json", "--no-input"],
                                    env=environment, capture_output=True, text=True, check=False, timeout=30)
            accounts = json.loads(result.stdout).get("accounts", []) if result.returncode == 0 else []
            if any(isinstance(row, dict) and row.get("email", "").casefold() == account.casefold()
                   and "gmail" in (row.get("services") or []) for row in accounts):
                return []
        except ERRORS:
            pass
    return ["gmail_authorization"]


def _telegram_missing(home: Path) -> list[str]:
    try:
        path = home / ".config/anicca/job-search/telegram.env"
        _safe(path)
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ValueError("telegram_permissions")
        values = telegram._parse_env_file(path)
        chat = next((value.strip() for key, value in values.items() if key in {
            "CROWDWORKS_REPORT_CHAT", "LANCERS_REPORT_CHAT", "GIG_REPORT_CHAT", "JOB_SEARCH_TELEGRAM_CHAT_ID"
        } and value.strip()), "")
        if not re.fullmatch(r"-?\d+", chat):
            raise ValueError("telegram_destination")
        token, _chat = telegram.load_config(environ={"TELEGRAM_CHAT_ID": chat}, env_file=path)
        if profile_setup._contains_placeholder(token):
            raise ValueError("telegram_token")
    except ERRORS:
        return ["telegram_notification"]
    return []


def _inherited_lease() -> bool:
    pid = os.environ.get("LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID", "")
    token = os.environ.get("AI_BROWSER_HOLDER_START", "")
    guard = str(ROOT / "skills/browser/browser-guard.sh")
    if (os.environ.get("LIFE_MANAGER_BROWSER_LEASE_IDENTITY") != IDENTITY
            or os.environ.get("LIFE_MANAGER_BROWSER_IDENTITY") != IDENTITY
            or os.environ.get("LIFE_MANAGER_BROWSER_GUARD") != guard
            or not pid.isdigit() or int(pid) <= 0 or not token):
        return False
    try:
        endpoint = onboarding.configured_cdp_endpoint(os.environ.get("CDP", ""))
        port = onboarding.endpoint_port(endpoint)
        if os.environ.get("CLOAK_CDP_BASE_URL") != endpoint:
            return False
        os.kill(int(pid), 0)
        result = subprocess.run([guard, "status"], capture_output=True, text=True, check=False, timeout=8)
        rows = json.loads(result.stdout).get("identities", []) if result.returncode == 0 else []
        matches = [row for row in rows if isinstance(row, dict) and row.get("identity") == IDENTITY]
        if len(matches) != 1:
            return False
        row = matches[0]
        holder = json.loads(row.get("holder", ""))
        return (row.get("reachable") is True and row.get("endpoint") == endpoint and row.get("port") == port
                and bool(row.get("uuid")) and holder.get("identity") == IDENTITY
                and holder.get("pid") == int(pid) and holder.get("holder_start") == token
                and holder.get("host") == socket.gethostname().split(".")[0]
                and holder.get("uuid") == row["uuid"] and holder.get("port") == port
                and not any(isinstance(other, dict) and other.get("identity") != IDENTITY
                            and other.get("uuid") == row["uuid"] for other in rows))
    except ERRORS:
        return False


def _observe_owned() -> dict:
    if not _inherited_lease():
        return {}
    lease: dict = {}
    observation: dict = {}
    command = [sys.executable, str(ROOT / "skills/browser/scripts/cdp_context_lease.py")]
    env = {**os.environ, "AI_BROWSER_HOLDER_PID": str(os.getpid())}
    try:
        profile, _application_missing = _profile(_read(Path.home().resolve() / ".config/anicca/job-search/profile.json"))
        result = subprocess.run(command + ["acquire", TASK, "https://work.mercor.com/explore"],
                                env=env, capture_output=True, text=True, check=False, timeout=60)
        if result.returncode:
            return {}
        lease = json.loads(result.stdout)
        if not all(lease.get(key) for key in ("ws", "token", "generation")):
            return {}
        asyncio.run(mercor_page_ready.prepare(lease["ws"]))
        observation = asyncio.run(mercor_auth_readback.observe(
            lease["ws"], expected_email=profile["candidate"]["application_email"]))
        if observation.get("status") == "authenticated" and observation.get("firebase_identity_matched") is True:
            saved = subprocess.run(command + ["commit-cookies", TASK, "--domain", "mercor.com", "--origin",
                "https://work.mercor.com", "--local-storage-key", "mercor-auth-store",
                "--session-storage-key", "mercor-session-id", "--session-storage-key", "mercor-user-ip",
                "--indexeddb", "firebaseLocalStorageDb/firebaseLocalStorage", "--token", lease["token"],
                "--generation", str(lease["generation"])], env=env, capture_output=True, text=True, check=False, timeout=30)
            if saved.returncode or json.loads(saved.stdout).get("ok") is not True:
                observation = {}
    except ERRORS:
        observation = {}
    finally:
        if lease.get("token") and lease.get("generation"):
            try:
                parked = subprocess.run(command + ["park", TASK, "--token", lease["token"], "--generation",
                    str(lease["generation"])], env=env, capture_output=True, text=True, check=False, timeout=30)
                if parked.returncode:
                    observation = {}
            except ERRORS:
                observation = {}
    return {key: observation.get(key) for key in ("status", "firebase_identity_matched")}


def _observe(release: Path, environment: dict) -> dict:
    home = Path.home().resolve()
    application = home / ".local/state/anicca/job-search/mercor/application"
    env = {**environment, "AI_BROWSER_GUARD": str(release / "skills/browser/browser-guard.sh"),
        "LIFE_MANAGER_BROWSER_IDENTITY": IDENTITY, "LIFE_MANAGER_BROWSER_TARGET_OWNER": BROWSER["id"],
        "AI_ENSURE_BROWSER": "/dev/null", "AI_ENSURE_PROVISION_BROWSER": "/dev/null",
        "CLOAK_BROWSER_LAUNCHD_LABEL": "", "BROWSER_WAIT_SECONDS": "0",
        "CLOAK_CONTEXT_LEASES_FILE": str(application / "context-leases.json"),
        "CLOAK_SESSION_VAULT_FILE": str(application / "auth-overlay.json"),
        "CLOAK_SESSION_VAULT_WRITEBACK_FILE": str(application / "auth-overlay.json"),
        "CLOAK_CONTEXT_COOKIE_DOMAINS": "mercor.com"}
    try:
        result = subprocess.run([str(release / "skills/browser/with-browser.sh"), IDENTITY, "--",
            environment["LIFE_MANAGER_RUNTIME_PYTHON"], str(release / "skills/earn/mercor/scripts/install_local.py"), "observe"],
            env=env, capture_output=True, text=True, check=False, timeout=180)
        return json.loads(result.stdout) if result.returncode == 0 else {}
    except ERRORS:
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("command", choices=("install", "plan", "observe"), nargs="?", default="install")
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args(argv)
    if args.command == "observe":
        print(json.dumps(_observe_owned(), sort_keys=True))
        return 0
    installing = args.command == "install"
    home = Path.home().resolve()
    missing = {owner: [] for owner in JOBS}
    results: dict[str, dict] = {}
    browser = {"state": "planned", "missing": []}
    phase = "host_profile"
    try:
        host = local_install.load_host_profile()
        environment = {**os.environ, **local_install.host_environment(), "HOME": str(home)}
        codex_missing = ["codex_login"]
        release = None
        if installing:
            if host is None:
                raise ValueError("host_profile")
            phase = "codex_login"
            if _codex_login(host, environment):
                codex_missing = []
            config = json.loads(Path(host["agent_runner_config"]).read_text())["providers"]["codex"]
            selected = config["profiles"][config["account_profile_order"][0]]
            environment["CODEX_HOME"] = str(Path(selected["auth_file"]).expanduser().parent)
            environment["PATH"] = str(Path(config["executable"]).expanduser().parent) + os.pathsep + environment.get("PATH", "")
            phase = "immutable_release"
            release = local_install.cut_release(ROOT, environment)
            local_install.validate_release(release, host)
        phase = "private_input"
        candidate, candidate_missing, application_missing = _candidate(
            args.profile, home, environment, write=installing and not codex_missing)
        resume_missing = _resume(home, environment, write=installing and candidate is not None
                                 and not codex_missing and not application_missing)
        email = candidate["candidate"]["application_email"] if candidate else None
        gmail_missing = _gmail_missing(email, environment, observe=installing)
        observation = {}
        if installing:
            phase = "browser_owner"
            applied = local_install.apply_host_owners(release, [BROWSER], environment)
            browser = {"state": "waiting" if any(row.get("skipped") for row in applied) else "installed", "missing": []}
            if candidate is not None:
                observation = _observe(release, environment)
        account_missing = ([] if observation.get("status") == "authenticated"
                           and observation.get("firebase_identity_matched") is True else ["account_observation"])
        for owner in JOBS:
            missing[owner] += account_missing
        for owner in JOBS[:2]:
            missing[owner] += candidate_missing + codex_missing + gmail_missing
        missing[TASK] += resume_missing + application_missing
        missing["mercor-revenue-reply"] += _telegram_missing(home)
        missing["mercor-revenue-paid"].append("paid_account_binding")
        if host is None:
            browser["missing"].append("host_profile")
            for owner in JOBS:
                missing[owner].append("host_profile")
        if installing:
            for owner in JOBS:
                if not missing[owner]:
                    try:
                        results[owner] = local_install.apply_targets(release, [owner], environment)[0]
                    except ERRORS:
                        missing[owner].append("owner_apply")
    except ERRORS:
        for owner in JOBS:
            if owner not in results:
                missing[owner].append(phase)
    missing["mercor-revenue-paid"].append("paid_account_binding")
    jobs = []
    for owner in JOBS:
        fields = sorted(set(missing[owner]))
        result = results.get(owner)
        state = "setup_required" if fields else "waiting" if result and result.get("skipped") else "installed" if result else "planned"
        jobs.append({"loop_id": owner, "state": state, "missing": fields,
                     "next_action": "resolve_missing" if fields else "wait_for_owner_idle" if state == "waiting" else
                                    "install" if state == "planned" else "none"})
    status = "plan" if not installing else "installed" if all(row["state"] == "installed" for row in jobs) else "waiting"
    print(json.dumps({"status": status, "jobs": jobs, "browser": browser, "business_outcomes_verified": False}, sort_keys=True))
    return 0 if status in {"plan", "installed"} else 78


if __name__ == "__main__":
    raise SystemExit(main())
