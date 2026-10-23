#!/usr/bin/env python3
"""Connect the existing local installer to this owner's independent Lancers jobs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.loop import local_install
from skills.earn.lancers.scripts import lancers_onboarding as onboarding, local_identity, storefront_offer as offer


PREFIX = "lancers-revenue-"
JOBS = tuple(PREFIX + name for name in (
    "browser", "application", "storefront", "negotiate", "paid", "work-sync", "telegram-report"))


def _read_input(kind: str, path: Path, catalog: Path | None) -> dict:
    if kind == "listing_catalog":
        return offer._reach_marketplace_core().load(path)
    if kind == "candidate_profile":
        return local_identity.validate_profile(json.loads(path.read_text(encoding="utf-8")))
    value = offer._load_product_file(path)
    _product, image, avatar = offer._product(path, catalog, creating=True, raw_value=value)
    return value | {"image_path": str(image.resolve()), "profile_avatar_path": str(avatar.resolve())}


def _import_input(kind: str, source: Path | None, destination: Path,
                  catalog: Path | None = None, *, write: bool) -> tuple[dict | None, list[str]]:
    path = source.expanduser().resolve() if source is not None else destination
    if not path.is_file():
        return None, [] if kind == "listing_catalog" and source is None else [kind]
    try:
        value = _read_input(kind, path, catalog)
        if source is not None and destination.exists():
            previous = _read_input(kind, destination, catalog)
            if kind == "storefront_product":
                if value.get("listing_external_id") == "":
                    value["listing_external_id"] = previous.get("listing_external_id", "")
                for key in ("portfolio", "software_portfolio"):
                    for field in ("external_id", "listing_external_id"):
                        if value[key].get(field) == "" and previous[key].get(field):
                            value[key][field] = previous[key][field]
            if value != previous:
                return None, [kind + "_conflict"]
            if write:
                destination.parent.chmod(0o700)
                destination.chmod(0o600)
        elif source is not None and write:
            onboarding._write_private(destination, value)
        return value, []
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return None, [kind]


def _codex_login(profile: dict, environment: dict[str, str]) -> bool:
    configuration = json.loads(Path(profile["agent_runner_config"]).read_text(encoding="utf-8"))
    provider = configuration["providers"]["codex"]
    selected = provider["profiles"][provider["account_profile_order"][0]]
    executable = str(Path(provider["executable"]).expanduser())
    auth_home = str(Path(selected["auth_file"]).expanduser().parent)
    environment = {**os.environ, **environment, "CODEX_HOME": auth_home}
    command = [executable, "login"]
    options = {"env": environment, "capture_output": True, "text": True, "check": False}
    if subprocess.run(command + ["status"], timeout=30, **options).returncode == 0:
        return True
    subprocess.run(command, env=environment, check=False, timeout=300)
    return subprocess.run(command + ["status"], timeout=30, **options).returncode == 0


def _observe(release: Path, environment: dict[str, str], home: Path) -> str | None:
    completed = subprocess.run([
        str(release / "skills/browser/with-browser.sh"), onboarding.IDENTITY, "--",
        environment["LIFE_MANAGER_RUNTIME_PYTHON"],
        str(release / "skills/earn/lancers/scripts/lancers_onboarding.py"), "observe",
    ], env={**os.environ, **environment}, capture_output=True, text=True, check=False, timeout=180)
    try:
        result = json.loads(completed.stdout)
        if completed.returncode == 0 and isinstance(result, dict) and result.get("ok") is True:
            return onboarding.connected_account(home)
    except (ValueError, TypeError):
        pass
    return None


def _report_missing(home: Path) -> list[str]:
    try:
        reporter = offer._load("lancers_installer_report", ROOT / "skills/earn/lancers/scripts/telegram_report.py")
        telegram = offer._load("lancers_installer_telegram", ROOT / "skills/_shared/telegram.py")
        telegram.load_config(environ={"TELEGRAM_CHAT_ID": reporter._report_chat()},
                             env_file=home / ".local/state/life-manager/.env")
    except (OSError, ValueError, RuntimeError):
        return ["telegram_notification"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "plan"), nargs="?", default="install")
    parser.add_argument("--candidate-profile", type=Path)
    parser.add_argument("--product", type=Path)
    parser.add_argument("--catalog", type=Path)
    args = parser.parse_args(argv)
    installing = args.command == "install"
    home = Path.home()
    private = home / ".config/anicca/lancers"
    state = home / ".local/state/anicca/lancers"
    missing = {job: [] for job in JOBS}
    applied: list[dict] = []
    phase = "host_profile"
    try:
        profile = local_install.load_host_profile()
        if installing and profile is None:
            raise ValueError("host_profile")
        environment = local_install.host_environment()
        release = None
        account = None
        if installing:
            phase = "codex_login"
            if not _codex_login(profile, environment):
                raise ValueError("codex_login")
            phase = "immutable_release"
            release = local_install.cut_release(ROOT, environment)
            local_install.validate_release(release, profile)
        phase = "private_input"
        catalog_path = private / "listing-catalog.json"
        _catalog, catalog_missing = _import_input("listing_catalog", args.catalog, catalog_path, write=installing)
        selected_catalog = (catalog_path if installing or args.catalog is None else args.catalog.expanduser().resolve())
        if _catalog is None:
            selected_catalog = None
        _candidate, candidate_missing = _import_input(
            "candidate_profile", args.candidate_profile, home / ".config/anicca/job-search/profile.json", write=installing)
        product, product_missing = _import_input(
            "storefront_product", args.product, private / "storefront-product.json", selected_catalog, write=installing)
        product_missing += catalog_missing
        if installing:
            phase = "owner_apply"
            applied = local_install.apply_targets(release, [PREFIX + "browser"], environment)
            if applied and all(row.get("ok") is True and row.get("skipped") in (None, "loaded-running") for row in applied):
                try:
                    account = _observe(release, environment, home)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                    account = None
        else:
            account = onboarding.connected_account(home)
        account_missing = [] if account is not None else ["account_observation"]
        identity_missing = list(candidate_missing)
        try:
            local_identity.load_identity()
        except local_identity.SetupRequired as error:
            identity_missing += error.missing
        writable = state.is_dir() and os.access(state, os.W_OK | os.X_OK)
        state_missing = [] if writable else ["lancers_state"]
        for name in ("application", "negotiate", "paid"):
            missing[PREFIX + name] = account_missing + identity_missing + state_missing
        if product is not None and account is not None and product["seller_profile"]["public_path"] != f"/profile/{account}":
            product_missing += ["seller_account_mismatch"]
        missing[PREFIX + "storefront"] = account_missing + product_missing + state_missing
        missing[PREFIX + "work-sync"] = account_missing + state_missing
        missing[PREFIX + "telegram-report"] = _report_missing(home) + state_missing
        if profile is None:
            for job in JOBS:
                missing[job].append("host_profile")
        if installing:
            eligible = [job for job in JOBS if job != PREFIX + "browser" and not missing[job]]
            if eligible:
                applied += local_install.apply_targets(release, eligible, environment)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        confirmed = {row["loop_id"] for row in applied}
        for job in JOBS:
            if job not in confirmed:
                missing[job].append(phase)
    results = {row["loop_id"]: row for row in applied}
    jobs = []
    for job in JOBS:
        fields = sorted(set(missing[job]))
        result = results.get(job)
        status = ("setup_required" if fields else "waiting" if result and result.get("skipped") else
                  "installed" if result else "planned")
        jobs.append({"loop_id": job, "state": status, "missing": fields,
                     "next_action": "resolve_missing" if fields else "wait_for_owner_idle" if status == "waiting" else
                                    "install" if status == "planned" else "none"})
    status = "plan" if not installing else "installed" if all(row["state"] == "installed" for row in jobs) else "waiting"
    print(json.dumps({"status": status, "jobs": jobs, "business_outcomes_verified": False},
                     ensure_ascii=False, sort_keys=True))
    return 0 if status in {"plan", "installed"} else 78


if __name__ == "__main__":
    raise SystemExit(main())
