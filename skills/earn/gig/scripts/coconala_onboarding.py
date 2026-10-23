#!/usr/bin/env python3
"""Create and read the secret-free resumable Coconala onboarding receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from money_loop_onboarding import _write_private


STATES = (
    "preflight", "authenticated", "email_verified", "sms_verified",
    "seller_information", "identity_approved", "bank_registered",
    "launchd_readback", "storefront_listing_readback",
)
ACCOUNT_GATES = STATES[:7]
OBSERVATION_PAGES = {
    "authenticated": "https://coconala.com/mypage",
    "sms_verified": "https://coconala.com/mypage/sms",
    "seller_information": "https://coconala.com/mypage/user_information",
    "identity_approved": "https://coconala.com/mypage/user_identification",
    "bank_registered": "https://coconala.com/mypage/bank",
}


def observed_authentication(pages: dict[str, dict[str, Any]]) -> bool | None:
    completed = [urlparse(str(row.get("url") or "")) for row in pages.values()
                 if row.get("ready") == "complete"]
    if any(url.hostname == "coconala.com" and url.path.rstrip("/") in {
        "/login", "/users/login", "/users/signup",
    } for url in completed):
        return False
    page = pages.get("authenticated", {})
    url = urlparse(str(page.get("url") or ""))
    if (page.get("ready") == "complete" and page.get("authenticated_identity") is True
            and url.scheme == "https" and url.hostname == "coconala.com"
            and (url.path == "/mypage" or url.path.startswith("/mypage/"))):
        return True
    return None


def _validate(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("version") != 2 or value.get("platform") != "coconala":
        raise ValueError("invalid_coconala_onboarding_receipt")
    states = value.get("states")
    if not isinstance(states, dict) or set(states) != set(STATES):
        raise ValueError("invalid_coconala_onboarding_states")
    for state in states.values():
        if not isinstance(state, dict) or set(state) != {"status", "evidence_sha256"}:
            raise ValueError("invalid_coconala_onboarding_state")
        if state["status"] == "pending" and state["evidence_sha256"] is not None:
            raise ValueError("invalid_coconala_onboarding_pending_evidence")
        if state["status"] == "complete" and re.fullmatch(r"[0-9a-f]{64}", str(state["evidence_sha256"] or "")) is None:
            raise ValueError("invalid_coconala_onboarding_complete_evidence")
        if state["status"] not in {"pending", "complete"}:
            raise ValueError("invalid_coconala_onboarding_state")
    return value


def receipt(home: Path) -> dict[str, Any]:
    path = home / ".config" / "anicca" / "gig" / "coconala-onboarding.json"
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(current, dict) and current.get("version") == 1 and isinstance(current.get("states"), dict):
            current = {
                "version": 2, "platform": "coconala",
                "states": {state: {"status": "pending", "evidence_sha256": None} for state in STATES},
            }
            _write_private(path, current)
        return _validate(current)
    value = {
        "version": 2,
        "platform": "coconala",
        "states": {state: {"status": "pending", "evidence_sha256": None} for state in STATES},
    }
    _write_private(path, value)
    return value


def record(home: Path, state: str, evidence_sha256: str) -> dict[str, Any]:
    if state not in STATES or re.fullmatch(r"[0-9a-f]{64}", evidence_sha256) is None:
        raise ValueError("invalid_coconala_onboarding_evidence")
    value = receipt(home)
    value["states"][state] = {"status": "complete", "evidence_sha256": evidence_sha256}
    _write_private(home / ".config" / "anicca" / "gig" / "coconala-onboarding.json", value)
    return _validate(value)


def ready(home: Path) -> tuple[dict[str, Any], int]:
    value = receipt(home)
    missing = [state for state in ACCOUNT_GATES if value["states"][state]["status"] != "complete"]
    observation = home / ".config" / "anicca" / "gig" / "onboarding-observation.json"
    authenticated = None
    if observation.exists():
        latest = json.loads(observation.read_text(encoding="utf-8"))
        if (not isinstance(latest, dict) or latest.get("version") != 1
                or latest.get("platform") != "coconala"
                or not isinstance(latest.get("classifications"), dict)):
            raise ValueError("invalid_coconala_onboarding_observation")
        authenticated = latest["classifications"].get("authenticated")
        if authenticated is True:
            pages = latest.get("pages")
            fields = {"url", "ready", "forms", "controls", "body_sha256", "body_length", "authenticated_identity"}
            if (not isinstance(pages, dict) or set(pages) != set(OBSERVATION_PAGES)
                    or any(not isinstance(row, dict) or set(row) != fields for row in pages.values())
                    or observed_authentication(pages) is not True):
                raise ValueError("invalid_coconala_onboarding_observation")
            digest = hashlib.sha256(json.dumps(
                pages["authenticated"], sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")).hexdigest()
            if digest != value["states"]["authenticated"]["evidence_sha256"]:
                raise ValueError("invalid_coconala_onboarding_observation")
    if authenticated is not True and "authenticated" not in missing:
        missing.insert(0, "authenticated")
    return {"status": "ready" if not missing else "blocked", "missing": missing}, 0 if not missing else 2


def configure(home: Path, **updates: str) -> dict[str, Any]:
    path = home / ".config" / "anicca" / "gig" / "install.json"
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("invalid_coconala_install_config")
    else:
        value = {}
    value.update(updates)
    _write_private(path, value)
    return {"status": "configured", "keys": sorted(updates)}


def configure_python(home: Path, python: Path) -> dict[str, Any]:
    python = python.expanduser().absolute()
    python.resolve(strict=True)
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError("invalid_coconala_python")
    return configure(home, PYTHON=str(python))


def configure_email(home: Path, account: str) -> dict[str, Any]:
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", account) is None:
        raise ValueError("invalid_gog_account")
    return configure(home, GIG_GOG_ACCOUNT=account, GIG_NOTIFY_EMAIL=account)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "init", "status", "record", "ready", "configure-python", "configure-email",
    ))
    parser.add_argument("--state", choices=STATES)
    parser.add_argument("--evidence-sha256")
    parser.add_argument("--python", type=Path)
    parser.add_argument("--account")
    args = parser.parse_args()
    exit_code = 0
    if args.command == "configure-python":
        if args.python is None:
            parser.error("configure-python requires --python")
        value = configure_python(Path.home(), args.python)
    elif args.command == "configure-email":
        if not args.account:
            parser.error("configure-email requires --account")
        value = configure_email(Path.home(), args.account)
    elif args.command == "status":
        path = Path.home() / ".config" / "anicca" / "gig" / "coconala-onboarding.json"
        if not path.exists():
            print(json.dumps({"status": "uninitialized"}, sort_keys=True))
            return 2
        receipt_value = _validate(json.loads(path.read_text(encoding="utf-8")))
        value = {
            "status": ("ready" if receipt_value["states"]["launchd_readback"]["status"] == "complete"
                       else "needs_setup"),
            "states": receipt_value["states"],
        }
    elif args.command == "record":
        if not args.state or not args.evidence_sha256:
            parser.error("record requires --state and --evidence-sha256")
        value = record(Path.home(), args.state, args.evidence_sha256)
    elif args.command == "ready":
        value, exit_code = ready(Path.home())
    else:
        value = receipt(Path.home())
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
