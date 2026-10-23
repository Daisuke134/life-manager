#!/usr/bin/env python3
"""Connect only an account observed in the leased Lancers mypage summary."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[4]
BROWSER = ROOT / "skills/browser"
sys.path.insert(0, str(ROOT / "skills/earn/gig/scripts"))
sys.path.insert(0, str(BROWSER))
sys.path.insert(0, str(BROWSER / "scripts"))
from money_loop_onboarding import _canonical, _write_private
from cdp_endpoint import configured_cdp_endpoint, endpoint_port


MYPAGE = "https://www.lancers.jp/mypage"
IDENTITY = "lancers:dais"
OWNER = "lancers-onboarding"
EXPRESSION = r"""(()=>({
  url: location.origin + location.pathname,
  ready: document.readyState,
  login_form: !!document.querySelector('#login_form, form[action*="/user/login"], input[type="password"]'),
  human_verification: /captcha/i.test(document.title||'') || /human verification|verify (that )?you('re| are) human|robot check|security verification|ユーザーが人間であることを確認/i.test(
    (document.title||'')+'\n'+(document.body?.innerText||'').slice(0,2048)),
  profile_links: [...document.querySelectorAll('.mypage.result-summary a[href*="/profile/"]')].map(a=>a.href)
}))()"""


def _required(field: str) -> dict:
    return {"ok": False, "error": "setup_required", "missing": [field]}


def _directory(home: Path) -> Path:
    return home / ".config/anicca/lancers"


def _invalidate(home: Path) -> None:
    path = _directory(home) / "onboarding-observation.json"
    path.unlink(missing_ok=True)
    _write_private(path,
                   {"version": 1, "platform": "lancers", "snapshot": None})


def observed_account(snapshot: dict) -> str | None:
    """Accept explicit negative login/challenge markers and one summary account."""
    if (not isinstance(snapshot, dict) or snapshot.get("url") not in (MYPAGE, MYPAGE + "/")
            or snapshot.get("ready") != "complete" or snapshot.get("login_form") is not False
            or snapshot.get("human_verification") is not False):
        return None
    links = snapshot.get("profile_links")
    if not isinstance(links, list) or not links:
        return None
    accounts = set()
    for link in links:
        if not isinstance(link, str):
            return None
        try:
            url = urlsplit(link)
        except ValueError:
            return None
        match = re.fullmatch(r"/profile/([^/]+)(?:/.*)?", url.path)
        if (url.scheme != "https" or url.netloc != "www.lancers.jp" or url.query or url.fragment
                or match is None or match[1] in {".", ".."}):
            return None
        accounts.add(match[1])
    return next(iter(accounts)) if len(accounts) == 1 else None


def connect(home: Path, snapshot: dict) -> dict:
    """Bind safe current evidence while preserving an existing same-account record."""
    try:
        _invalidate(home)
    except OSError:
        return _required("private_storage")
    account = observed_account(snapshot)
    if account is None:
        return _required("account_observation")
    profile_path = _directory(home) / "public-profile.json"
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        profile = {}
    except (OSError, ValueError):
        return _required("provider_profile")
    if not isinstance(profile, dict):
        return _required("provider_profile")
    if "account_id" in profile:
        previous = profile["account_id"]
        if not isinstance(previous, str) or previous.strip() != account:
            return _required("provider_profile.account_id")
    safe = {"url": MYPAGE, "ready": "complete", "login_form": False,
            "human_verification": False, "profile_links": [f"https://www.lancers.jp/profile/{account}"]}
    digest = hashlib.sha256(_canonical(safe)).hexdigest()
    profile.update(account_id=account, account_binding={"observation_sha256": digest})
    try:
        _write_private(profile_path, profile)
        _write_private(_directory(home) / "onboarding-observation.json", {
            "version": 1, "platform": "lancers", "snapshot": safe, "observation_sha256": digest,
        })
    except (OSError, ValueError):
        return _required("private_storage")
    return ready(home)


def connected_account(home: Path) -> str | None:
    """Return the private account only from a matching saved observation binding."""
    try:
        latest = json.loads((_directory(home) / "onboarding-observation.json").read_text(encoding="utf-8"))
        profile = json.loads((_directory(home) / "public-profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(latest, dict) or latest.get("version") != 1
            or latest.get("platform") != "lancers" or not isinstance(profile, dict)):
        return None
    snapshot = latest.get("snapshot")
    account = observed_account(snapshot)
    if account is None or profile.get("account_id") != account:
        return None
    digest = hashlib.sha256(_canonical(snapshot)).hexdigest()
    binding = profile.get("account_binding")
    if (latest.get("observation_sha256") != digest or not isinstance(binding, dict)
            or binding.get("observation_sha256") != digest):
        return None
    return account


def ready(home: Path) -> dict:
    """Account connection is independent of candidate/product/business readiness."""
    if connected_account(home) is None:
        return _required("account_observation")
    return {"ok": True, "status": "account_connected"}


def _inherited_lease() -> bool:
    pid = os.environ.get("LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID", "")
    token = os.environ.get("AI_BROWSER_HOLDER_START", "")
    endpoint = os.environ.get("CLOAK_CDP_BASE_URL", "").strip()
    cdp = os.environ.get("CDP", "").strip()
    if (os.environ.get("LIFE_MANAGER_BROWSER_LEASE_IDENTITY") != IDENTITY
            or not pid.isdigit() or int(pid) <= 0 or not token or not endpoint or not cdp
            or os.environ.get("LIFE_MANAGER_BROWSER_IDENTITY", IDENTITY) != IDENTITY):
        return False
    guard = os.environ.get("LIFE_MANAGER_BROWSER_GUARD") or str(BROWSER / "browser-guard.sh")
    try:
        endpoint = configured_cdp_endpoint(cdp)
        port = endpoint_port(endpoint)
        if cdp.rstrip("/") != endpoint:
            return False
        os.kill(int(pid), 0)
        result = subprocess.run([guard, "status"], capture_output=True, text=True, timeout=8, check=False)
        status = json.loads(result.stdout) if result.returncode == 0 else {}
        if not isinstance(status, dict):
            return False
        rows = status.get("identities")
        if not isinstance(rows, list):
            return False
        matches = [row for row in rows if isinstance(row, dict) and row.get("identity") == IDENTITY]
        if len(matches) != 1:
            return False
        row = matches[0]
        holder = json.loads(row.get("holder", ""))
        return (
            isinstance(holder, dict) and row.get("reachable") is True
            and row.get("endpoint") == endpoint and row.get("port") == port
            and isinstance(row.get("uuid"), str) and bool(row["uuid"])
            and not any(isinstance(other, dict) and other.get("identity") != IDENTITY
                        and other.get("uuid") == row["uuid"] for other in rows)
            and holder.get("identity") == IDENTITY and holder.get("pid") == int(pid)
            and holder.get("holder_start") == token
            and holder.get("host") == socket.gethostname().split(".")[0]
            and holder.get("port") == port and holder.get("uuid") == row["uuid"]
        )
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return False


def _load_cdp():
    # cdp binds its endpoint at import; load only after checking the inherited lease.
    spec = importlib.util.spec_from_file_location("lancers_onboarding_cdp", BROWSER / "scripts/cdp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe(home: Path) -> dict:
    """Observe one leased, actor-owned tab and connect only after its cleanup."""
    try:
        _invalidate(home)
    except OSError:
        return _required("private_storage")
    if not _inherited_lease():
        return _required("browser_lease")
    try:
        cdp = _load_cdp()
        target = cdp.new_target(MYPAGE, owner=OWNER)
        try:
            snapshot = None
            for _ in range(20):
                snapshot = cdp.evaluate(target, EXPRESSION)
                if observed_account(snapshot) is not None:
                    break
                time.sleep(0.5)
        finally:
            cdp.close_target(target, owner=OWNER)
    except Exception:
        return _required("account_observation")
    return connect(home, snapshot)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("observe", "status"))
    args = parser.parse_args(argv)
    result = observe(Path.home()) if args.command == "observe" else ready(Path.home())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 78


if __name__ == "__main__":
    raise SystemExit(main())
