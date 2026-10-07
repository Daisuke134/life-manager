#!/usr/bin/env python3
"""Use the owner's existing CapSolver account for reCAPTCHA v2 and AWS WAF."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


API_ROOT = "https://api.capsolver.com"


class CapSolverError(RuntimeError):
    def __init__(self, code: str, *, task_id: str | None = None,
                 status: str | None = None, cost: float | None = None,
                 definitive: bool = False):
        super().__init__(code)
        self.code = code
        self.task_id = task_id
        self.status = status
        self.cost = cost
        self.definitive = definitive


def api_key() -> str:
    private = Path.home() / ".local" / "share" / "anicca"
    path = private / "credentials.json"
    try:
        if (
            private.is_symlink() or path.is_symlink()
            or private.stat().st_uid != os.getuid()
            or stat.S_IMODE(private.stat().st_mode) != 0o700
            or path.stat().st_uid != os.getuid()
            or stat.S_IMODE(path.stat().st_mode) != 0o600
        ):
            raise ValueError
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("credentials", []) if isinstance(payload, dict) else []
        matches = [
            row for row in rows
            if isinstance(row, dict) and row.get("service") == "CapSolver"
        ]
        value = matches[0].get("api_key") if len(matches) == 1 else None
        if not isinstance(value, str) or not value.strip():
            raise ValueError
        return value.strip()
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise CapSolverError("CAPSOLVER_CREDENTIALS_UNAVAILABLE", definitive=True) from None


def post(path: str, payload: dict[str, object], *, timeout: float = 30) -> dict[str, object]:
    request = Request(
        f"{API_ROOT}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as response:
        return json.load(response)


def _cost(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def create_aws_waf_task(
    client_key: str, website_url: str, aws_key: str, aws_iv: str,
    aws_context: str, aws_challenge_js: str,
) -> dict[str, object]:
    try:
        response = post(
            "/createTask",
            {
                "clientKey": client_key,
                "task": {
                    "type": "AntiAwsWafTaskProxyLess",
                    "websiteURL": website_url,
                    "awsKey": aws_key,
                    "awsIv": aws_iv,
                    "awsContext": aws_context,
                    "awsChallengeJS": aws_challenge_js,
                },
            },
            timeout=15,
        )
    except Exception:
        raise CapSolverError("CAPSOLVER_CREATE_UNKNOWN") from None
    if not isinstance(response, dict):
        raise CapSolverError("CAPSOLVER_CREATE_UNKNOWN")
    if response.get("errorId"):
        code = "CAPSOLVER_NO_CREDITS" if response.get("errorCode") == "ERROR_ZERO_BALANCE" else "CAPSOLVER_API_ERROR"
        raise CapSolverError(code, cost=_cost(response.get("cost")), definitive=True)
    task_id = response.get("taskId")
    if not isinstance(task_id, str) or not task_id:
        raise CapSolverError("CAPSOLVER_CREATE_UNKNOWN")
    return {"task_id": task_id, "status": "processing", "cost": _cost(response.get("cost"))}


def solve_aws_waf_task(
    client_key: str, task_id: str, timeout: float = 75,
) -> dict[str, object]:
    deadline = time.monotonic() + max(0, timeout)
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            response = post(
                "/getTaskResult",
                {"clientKey": client_key, "taskId": task_id},
                timeout=max(0.1, min(15, remaining)),
            )
        except Exception:
            raise CapSolverError("CAPSOLVER_API_ERROR", task_id=task_id, status="processing") from None
        if not isinstance(response, dict):
            raise CapSolverError("CAPSOLVER_API_ERROR", task_id=task_id, status="processing")
        cost = _cost(response.get("cost"))
        if response.get("errorId"):
            error_code = response.get("errorCode")
            definitive = error_code in {"ERROR_TASK_TIMEOUT", "ERROR_TASKID_INVALID", "ERROR_CAPTCHA_UNSOLVABLE", "ERROR_TASK_NOT_FOUND"}
            code = "CAPSOLVER_NO_CREDITS" if error_code == "ERROR_ZERO_BALANCE" else "CAPSOLVER_API_ERROR"
            raise CapSolverError(code, task_id=task_id, status="failed" if definitive else "processing",
                                 cost=cost, definitive=definitive)
        status = response.get("status")
        if status == "ready":
            solution = response.get("solution")
            cookie = solution.get("cookie") if isinstance(solution, dict) else None
            if not isinstance(cookie, str) or not cookie.strip():
                raise CapSolverError("CAPSOLVER_COOKIE_MISSING", task_id=task_id,
                                     status="ready", cost=cost, definitive=True)
            return {"task_id": task_id, "status": "ready", "cookie": cookie,
                    **({"cost": cost} if cost is not None else {})}
        if status == "failed":
            raise CapSolverError("CAPSOLVER_TASK_FAILED", task_id=task_id,
                                 status="failed", cost=cost, definitive=True)
        if status not in {"idle", "processing"}:
            raise CapSolverError("CAPSOLVER_API_ERROR", task_id=task_id,
                                 status="processing", cost=cost)
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    raise CapSolverError("CAPSOLVER_TIMEOUT", task_id=task_id, status="processing")


def solve(website_url: str, website_key: str, timeout: int) -> str:
    key = api_key()
    created = post(
        "/createTask",
        {
            "clientKey": key,
            "task": {
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteURL": website_url,
                "websiteKey": website_key,
                "isInvisible": False,
            },
        },
    )
    task_id = str(created.get("taskId", ""))
    if not task_id:
        raise RuntimeError(str(created.get("errorCode", "CREATE_TASK_FAILED")))

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(2)
        result = post("/getTaskResult", {"clientKey": key, "taskId": task_id})
        if result.get("status") == "ready":
            solution = result.get("solution")
            if isinstance(solution, dict):
                token = str(solution.get("gRecaptchaResponse", ""))
                if token:
                    return token
            raise RuntimeError("CAPSOLVER_READY_WITHOUT_TOKEN")
        if result.get("status") == "failed" or result.get("errorId"):
            raise RuntimeError(str(result.get("errorCode", "SOLVE_FAILED")))
    raise RuntimeError("CAPSOLVER_TIMEOUT")


def inject(target_id: str, token: str) -> dict[str, object]:
    cdp_path = Path.cwd() / "skills" / "browser" / "scripts" / "cdp.py"
    spec = importlib.util.spec_from_file_location("fundraiser_cdp", cdp_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("CDP_HELPER_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    encoded = json.dumps(token)
    source = f"""
    (() => {{
      const token = {encoded};
      let textareas = 0;
      let callbacks = 0;
      document.querySelectorAll('textarea[name="g-recaptcha-response"]').forEach((element) => {{
        element.value = token;
        element.innerHTML = token;
        element.dispatchEvent(new Event('input', {{bubbles: true}}));
        element.dispatchEvent(new Event('change', {{bubbles: true}}));
        textareas += 1;
      }});
      document.querySelectorAll('[data-sitekey][data-callback]').forEach((element) => {{
        const name = element.getAttribute('data-callback');
        if (!name) return;
        let callback = window;
        for (const part of name.split('.')) callback = callback && callback[part];
        if (typeof callback === 'function') {{
          try {{ callback(token); callbacks += 1; }} catch (_) {{}}
        }}
      }});
      return {{textareas, callbacks}};
    }})()
    """
    result = module.evaluate(target_id, source)
    if not isinstance(result, dict) or int(result.get("textareas", 0)) < 1:
        raise RuntimeError("RECAPTCHA_TEXTAREA_UNAVAILABLE")
    if int(result.get("callbacks", 0)) != 1:
        raise RuntimeError("RECAPTCHA_NAMED_CALLBACK_UNAVAILABLE")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--website-url", required=True)
    parser.add_argument("--website-key", required=True)
    parser.add_argument("--target-id")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    try:
        token = solve(args.website_url, args.website_key, args.timeout)
        if args.target_id:
            result = inject(args.target_id, token)
    except Exception as error:
        print(f"capsolver: {error}", file=sys.stderr)
        return 1
    if args.target_id:
        print(
            "CAPSOLVER_INJECTED=true "
            f"TEXTAREAS={result['textareas']} CALLBACKS={result['callbacks']}"
        )
    else:
        print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
