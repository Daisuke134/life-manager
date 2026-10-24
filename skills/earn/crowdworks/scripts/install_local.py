#!/usr/bin/env python3
"""Install this owner's existing CrowdWorks jobs through the local control plane."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.loop import local_install
from skills._shared import telegram
from skills.earn.crowdworks.scripts import profile as crowdworks_profile
from skills.earn.lancers.scripts.install_local import _codex_login
from skills.earn.lancers.scripts import lancers_onboarding as onboarding


PREFIX = "crowdworks-revenue-"
IDENTITY = "crowdworks:dais"
BROWSER = PREFIX + "browser"
JOBS = tuple(PREFIX + name for name in ("browser", "application", "reply", "paid", "report"))
ERRORS = (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError)


def _read_input(kind: str, path: Path, *, private: bool = False) -> dict:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or private and stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError(kind)
    if kind == "candidate_profile":
        return crowdworks_profile.validate_profile(json.loads(path.read_text(encoding="utf-8")))
    value = crowdworks_profile.load_config(path)
    if "avatar_path" in value:
        value["avatar_path"] = str(Path(value["avatar_path"]).resolve())
    return value


def _import_input(kind: str, source: Path | None, destination: Path, *, write: bool) -> tuple[dict | None, list[str]]:
    try:
        if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
            raise ValueError(kind)
        path = source.expanduser().absolute() if source is not None else destination
        value = _read_input(kind, path, private=source is None)
        if source is not None:
            if destination.exists():
                if value != _read_input(kind, destination, private=True):
                    return None, [kind + "_conflict"]
                if write:
                    destination.parent.chmod(0o700)
            elif write:
                onboarding._write_private(destination, value)
        return value, []
    except ERRORS:
        return None, [kind]


def _inherited_lease() -> bool:
    pid = os.environ.get("LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID", "")
    token = os.environ.get("AI_BROWSER_HOLDER_START", "")
    endpoint = os.environ.get("CLOAK_CDP_BASE_URL", "").strip()
    cdp = os.environ.get("CDP", "").strip()
    guard = os.environ.get("LIFE_MANAGER_BROWSER_GUARD", "")
    if (os.environ.get("LIFE_MANAGER_BROWSER_LEASE_IDENTITY") != IDENTITY
            or os.environ.get("LIFE_MANAGER_BROWSER_IDENTITY") != IDENTITY
            or os.environ.get("LIFE_MANAGER_BROWSER_TARGET_OWNER") != BROWSER
            or guard != str(ROOT / "skills/browser/browser-guard.sh")
            or not pid.isdigit() or int(pid) <= 0 or not token or not endpoint or not cdp):
        return False
    try:
        endpoint = onboarding.configured_cdp_endpoint(cdp)
        port = onboarding.endpoint_port(endpoint)
        if cdp.rstrip("/") != endpoint:
            return False
        os.kill(int(pid), 0)
        completed = subprocess.run([guard, "status"], capture_output=True, text=True, check=False, timeout=8)
        status = json.loads(completed.stdout) if completed.returncode == 0 else {}
        rows = status.get("identities") if isinstance(status, dict) else None
        if not isinstance(rows, list):
            return False
        matches = [row for row in rows if isinstance(row, dict) and row.get("identity") == IDENTITY]
        if len(matches) != 1:
            return False
        row = matches[0]
        holder = json.loads(row.get("holder", ""))
        return (isinstance(holder, dict) and row.get("reachable") is True
                and row.get("endpoint") == endpoint and row.get("port") == port
                and isinstance(row.get("uuid"), str) and bool(row["uuid"])
                and not any(isinstance(other, dict) and other.get("identity") != IDENTITY
                            and other.get("uuid") == row["uuid"] for other in rows)
                and holder.get("identity") == IDENTITY and holder.get("pid") == int(pid)
                and holder.get("holder_start") == token
                and holder.get("host") == socket.gethostname().split(".")[0]
                and holder.get("port") == port and holder.get("uuid") == row["uuid"])
    except ERRORS:
        return False


def _observe_owned() -> dict:
    """The immutable child only connects; browser recovery belongs to its owner."""
    observation = {"account_observed": False, "account_matches": False, "avatar_present": None}
    if not _inherited_lease():
        return observation
    try:
        account = crowdworks_profile._account_module()
        result = account.run_status(ownership_checker=_inherited_lease, browser_factory=account._browser)
        observation["account_observed"] = bool(
            result.ok and result.authenticated is True and isinstance(result.account_id, str) and result.account_id)
        path = Path.home() / ".config/anicca/crowdworks/public-profile.json"
        provider = crowdworks_profile.load_config(path)
        observation["account_matches"] = bool(observation["account_observed"]
                                               and result.account_id == provider["provider_employee_id"])
        if observation["account_matches"] and not provider.get("avatar_path"):
            observed = crowdworks_profile.run_observe(config_path=path, ownership_checker=_inherited_lease,
                                                      browser_factory=account._browser)
            if observed.get("ok") is True and observed.get("provider_employee_id") == result.account_id:
                aligned = observed.get("components", {}).get("avatar", {}).get("aligned")
                if type(aligned) is bool:
                    observation["avatar_present"] = aligned
    except ERRORS:
        pass
    return observation


def _observe(release: Path, environment: dict[str, str]) -> dict:
    try:
        env = {**os.environ, **environment, "AI_BROWSER_GUARD": str(release / "skills/browser/browser-guard.sh"),
               "LIFE_MANAGER_BROWSER_IDENTITY": IDENTITY, "LIFE_MANAGER_BROWSER_TARGET_OWNER": BROWSER,
               "AI_ENSURE_PROVISION_BROWSER": "/dev/null", "AI_ENSURE_BROWSER": "/dev/null",
               "CLOAK_BROWSER_LAUNCHD_LABEL": "", "BROWSER_WAIT_SECONDS": "0"}
        completed = subprocess.run([
            str(release / "skills/browser/with-browser.sh"), IDENTITY, "--",
            environment["LIFE_MANAGER_RUNTIME_PYTHON"],
            str(release / "skills/earn/crowdworks/scripts/install_local.py"), "observe",
        ], env=env, capture_output=True, text=True, check=False, timeout=180)
        result = json.loads(completed.stdout)
        if completed.returncode == 0 and isinstance(result, dict):
            return result
    except ERRORS:
        pass
    return {}


def _report_missing(home: Path, environment: dict[str, str]) -> list[str]:
    try:
        spec = importlib.util.spec_from_file_location("crowdworks_installer_report", ROOT / "skills/earn/crowdworks/scripts/telegram_report.py")
        reporter = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = reporter
        spec.loader.exec_module(reporter)
        telegram.load_config(environ={"TELEGRAM_CHAT_ID": reporter._report_chat()},
                             env_file=Path(environment.get("LIFE_MANAGER_ENV_FILE") or home / ".local/state/life-manager/.env"))
    except ERRORS:
        return ["telegram_notification"]
    return []


def _state_missing(state: Path, *, write: bool) -> list[str]:
    try:
        if (state.is_symlink() or any(parent.is_symlink() for parent in state.parents)
                or not state.is_dir() or not os.access(state, os.W_OK | os.X_OK)):
            raise ValueError("crowdworks_state")
        if write:
            with tempfile.TemporaryFile(dir=state) as stream:
                stream.write(b"state-write-probe")
                stream.flush()
                os.fsync(stream.fileno())
        return []
    except ERRORS:
        return ["crowdworks_state"]


def _apply_one(release: Path, owner: str, environment: dict[str, str], missing: dict, results: dict) -> None:
    try:
        rows = local_install.apply_targets(release, [owner], environment)
        if len(rows) != 1 or rows[0].get("loop_id") != owner or rows[0].get("ok") is not True:
            raise ValueError("owner_apply")
        results[owner] = rows[0]
    except ERRORS:
        missing[owner].append("owner_apply")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("command", choices=("install", "plan", "observe"), nargs="?", default="install")
    parser.add_argument("--candidate-profile", type=Path)
    parser.add_argument("--provider-profile", type=Path)
    args = parser.parse_args(argv)
    if args.command == "observe":
        print(json.dumps(_observe_owned(), sort_keys=True))
        return 0
    installing = args.command == "install"
    home = Path.home()
    candidate_path = home / ".config/anicca/job-search/profile.json"
    provider_path = home / ".config/anicca/crowdworks/public-profile.json"
    missing = {owner: [] for owner in JOBS}
    results: dict[str, dict] = {}
    phase = "host_profile"
    try:
        host = local_install.load_host_profile()
        environment = local_install.host_environment()
        release = None
        codex_missing = []
        if installing:
            if host is None:
                raise ValueError("host_profile")
            phase = "codex_login"
            try:
                authenticated = _codex_login(host, environment)
            except ERRORS:
                authenticated = False
            if not authenticated:
                codex_missing = ["codex_login"]
            phase = "immutable_release"
            release = local_install.cut_release(ROOT, environment)
            local_install.validate_release(release, host)
        phase = "private_input"
        _candidate, candidate_missing = _import_input("candidate_profile", args.candidate_profile, candidate_path, write=installing)
        provider, provider_missing = _import_input("provider_profile", args.provider_profile, provider_path, write=installing)
        identity_missing = candidate_missing + provider_missing
        if not identity_missing:
            try:
                crowdworks_profile.load_identity(
                    candidate_path if installing or args.candidate_profile is None else args.candidate_profile,
                    provider_path if installing or args.provider_profile is None else args.provider_profile)
            except crowdworks_profile.SetupRequired as error:
                identity_missing += error.missing
        state_missing = _state_missing(home / ".local/state/anicca/crowdworks", write=installing)
        missing[PREFIX + "report"] = _report_missing(home, environment) + state_missing
        observation = {}
        if installing:
            phase = "owner_apply"
            _apply_one(release, BROWSER, environment, missing, results)
            browser = results.get(BROWSER)
            if browser and browser.get("skipped") in (None, "loaded-running"):
                observation = _observe(release, environment)
        account_missing = (["account_observation"] if observation.get("account_observed") is not True else
                           [] if observation.get("account_matches") is True else ["provider_account_binding"])
        for name in ("application", "reply", "paid"):
            missing[PREFIX + name] = identity_missing + account_missing + state_missing + codex_missing
        if provider is not None:
            try:
                crowdworks_profile.require_apply_config(provider)
            except crowdworks_profile.SetupRequired as error:
                missing[PREFIX + "application"] += error.missing
            if not provider.get("avatar_path"):
                avatar = observation.get("avatar_present")
                if avatar is not True:
                    missing[PREFIX + "application"].append(
                        "provider_profile.avatar_path" if avatar is False else "profile_observation")
        if host is None:
            for owner in JOBS:
                missing[owner].append("host_profile")
        if installing:
            for owner in JOBS:
                if owner != BROWSER and not missing[owner]:
                    _apply_one(release, owner, environment, missing, results)
    except ERRORS:
        for owner in JOBS:
            if owner not in results:
                missing[owner].append(phase)
    jobs = []
    for owner in JOBS:
        fields = sorted(set(missing[owner]))
        result = results.get(owner)
        state = ("setup_required" if fields else "waiting" if result and result.get("skipped") else
                 "installed" if result else "planned")
        jobs.append({"loop_id": owner, "state": state, "missing": fields,
                     "next_action": "resolve_missing" if fields else "wait_for_owner_idle" if state == "waiting" else
                                    "install" if state == "planned" else "none"})
    status = "plan" if not installing else "installed" if all(row["state"] == "installed" for row in jobs) else "waiting"
    print(json.dumps({"status": status, "jobs": jobs, "business_outcomes_verified": False},
                     ensure_ascii=False, sort_keys=True))
    return 0 if status in {"plan", "installed"} else 78


if __name__ == "__main__":
    raise SystemExit(main())
