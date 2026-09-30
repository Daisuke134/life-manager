#!/usr/bin/env python3
"""Refresh the repo-external Capafy Publisher Console token before expiry."""

from __future__ import annotations

import base64
import datetime as dt
import contextlib
import fcntl
import tempfile
import urllib.error
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


API = "https://api.capafy.ai"
CREDENTIALS = Path.home() / ".local/share/anicca/credentials.json"
REFRESH_BEFORE_SECONDS = 300
AUTH_RETRY_SECONDS = 6 * 3600
WEB_PROBE_PATH = "/app/developer/settlement-statement/list?page=1&size=1"


def _post(path: str, body: dict) -> dict:
    request = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict) or value.get("code", 0) != 0:
        raise RuntimeError(f"Capafy auth failed: {value.get('code') if isinstance(value, dict) else 'shape'}")
    return value.get("data", value)


def _claims(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        value = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError, UnicodeError):
        return {}


def _expiry(token: str) -> int:
    try:
        return int(_claims(token).get("exp") or 0)
    except (ValueError, TypeError, OverflowError):
        return 0


def _refresh_window(token: str) -> int:
    claims = _claims(token)
    try:
        lifetime = int(claims["exp"]) - int(claims["iat"])
        if lifetime > 0:
            return max(1, min(REFRESH_BEFORE_SECONDS, lifetime // 10))
    except (KeyError, ValueError, TypeError, OverflowError):
        pass
    return 60


def _probe(token: str) -> str:
    # The stable /agent/account API key is NOT the Publisher Console JWT.
    request = urllib.request.Request(API + WEB_PROBE_PATH,
                                     headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            value = json.loads(response.read())
        return "valid" if isinstance(value, dict) and value.get("code", 0) == 0 else "unknown"
    except urllib.error.HTTPError as error:
        return "auth_failed" if error.code == 401 else "unknown"
    except (OSError, ValueError):
        return "unknown"


@contextlib.contextmanager
def _lock(path: Path):
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: dict) -> None:
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _receipt(action: str, ok: bool = True, **metadata) -> int:
    print(json.dumps({"ok": ok, "action": action, **metadata}))
    return 0 if ok else 1


def _credential_entry() -> tuple[dict, dict]:
    value = json.loads(CREDENTIALS.read_text())
    matches = [row for row in value.get("credentials", []) if row.get("service") == "capafy-publisher"]
    if len(matches) != 1:
        raise RuntimeError("capafy-publisher credential is not unique")
    return value, matches[0]


def _latest_otp(email: str, not_before_ms: int) -> str:
    env = dict(os.environ)
    for _ in range(12):
        raw = subprocess.check_output(
            ["gog", "gmail", "search", 'newer_than:1d from:noreply@capafy.ai subject:"login verification code"',
             "--account", email, "--json", "--results-only", "--no-input"],
            text=True, env=env, timeout=30,
        )
        threads = json.loads(raw)
        if threads:
            thread_id = threads[0]["id"]
            thread = json.loads(subprocess.check_output(
                ["gog", "gmail", "thread", "get", thread_id, "--account", email,
                 "--json", "--full", "--no-input"],
                text=True, env=env, timeout=30,
            ))["thread"]
            messages = [m for m in thread.get("messages", []) if int(m.get("internalDate") or 0) >= not_before_ms]
            if messages:
                message = max(messages, key=lambda m: int(m["internalDate"]))
                bodies: list[str] = []

                def collect(part: dict) -> None:
                    data = (part.get("body") or {}).get("data")
                    if data:
                        bodies.append(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace"))
                    for child in part.get("parts") or []:
                        collect(child)

                collect(message["payload"])
                codes = re.findall(r"font-size:32px[^>]*>(\d{6})</div>", "\n".join(bodies))
                if codes:
                    return codes[-1]
        time.sleep(5)
    raise RuntimeError("fresh Capafy OTP was not observed")


def _find_jwt(value: object) -> str:
    if isinstance(value, str) and _expiry(value):
        return value
    if isinstance(value, dict):
        for child in value.values():
            found = _find_jwt(child)
            if found:
                return found
    return ""


def _refresh_locked() -> int:
    _, entry = _credential_entry()
    token = str(entry.get("web_token") or "")
    exp = _expiry(token)
    now = int(time.time())
    status = _probe(token) if token else "missing"
    if status == "unknown":
        return _receipt("validation_unavailable", False)
    if status == "valid" and (not exp or exp - now > _refresh_window(token)):
        return _receipt("healthy_noop", expires_at=exp or None)
    # Record the attempt BEFORE sending a challenge, so failures also cool down.
    attempt_path = CREDENTIALS.with_name("capafy-web-auth-attempt.json")
    if attempt_path.exists():
        try:
            last_attempt = int(json.loads(attempt_path.read_text())["attempted_at"])
        except (OSError, ValueError, TypeError, KeyError):
            return _receipt("attempt_state_invalid", False)
        if now - last_attempt < AUTH_RETRY_SECONDS:
            return _receipt("auth_cooldown", False, retry_at=last_attempt + AUTH_RETRY_SECONDS)
    email = str(entry.get("email") or entry.get("username") or "")
    if not email:
        raise RuntimeError("Capafy publisher email missing")
    _atomic_json(attempt_path, {"attempted_at": now})
    started_ms = int(time.time() * 1000)
    challenge = _post("/auth/login", {"loginMethod": "email", "email": email})
    challenge_id = challenge.get("challengeId") if isinstance(challenge, dict) else None
    if not challenge_id:
        raise RuntimeError("Capafy challengeId missing")
    code = _latest_otp(email, started_ms)
    verified = _post("/auth/login/verify", {"challengeId": challenge_id, "code": code, "source": "web"})
    new_token = _find_jwt(verified)
    if not new_token or _expiry(new_token) <= int(time.time()) or _probe(new_token) != "valid":
        raise RuntimeError("Capafy replacement token could not be validated")
    # Use the latest document, not the snapshot taken before waiting for OTP.
    # Other credential writers must use this same lock to serialize their writes.
    with _lock(CREDENTIALS.with_name("credentials.write.lock")):
        document, current = _credential_entry()
        if str(current.get("web_token") or "") != token:
            return _receipt("credential_changed", False)
        current["web_token"] = new_token
        current["web_token_updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _atomic_json(CREDENTIALS, document)
        _, saved = _credential_entry()
        if saved.get("web_token") != new_token:
            raise RuntimeError("Capafy credential readback failed")
    return _receipt("refreshed", expires_at=_expiry(new_token))


def main() -> int:
    try:
        with _lock(CREDENTIALS.with_name("capafy-web-refresh.lock")):
            return _refresh_locked()
    except BlockingIOError:
        return _receipt("refresh_in_progress")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"ok": False, "error": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
