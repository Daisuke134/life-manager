#!/usr/bin/env python3
"""Observe Coconala setup pages without emitting form values or page text."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
GIG_ROOT = SCRIPTS.parent
BROWSER_SCRIPTS = GIG_ROOT.parents[1] / "browser" / "scripts"
sys.path.insert(0, str(BROWSER_SCRIPTS))

import cdp_default_tab  # noqa: E402
import websockets  # noqa: E402
from coconala_onboarding import (  # noqa: E402
    OBSERVATION_PAGES as PAGES, _write_private, observed_authentication, record,
)

# Use the own-profile navigation proof from application_parent._authenticated_identity_async.
EXPRESSION = r"""(()=>{
  const path=a=>{try{
    const u=new URL(a.href,location.origin), m=u.pathname.match(/^\/(?:users|smartphone\/users)\/(\d+)\/?$/);
    return u.origin==='https://coconala.com'&&m?`/users/${m[1]}`:null;
  }catch(_){return null}};
  const links=[...document.querySelectorAll('a[href]')].map(node=>({node,path:path(node)})).filter(x=>x.path);
  const own=links.find(x=>x.node.closest('.sidebar-profile'))||
    links.find(x=>x.node.closest('header,nav,[class*="header"],[class*="Header"]'));
  return JSON.stringify({
  url: location.origin + location.pathname,
  ready: document.readyState,
  own_user_path: own?.path||null,
  forms: document.forms.length,
  controls: [...document.querySelectorAll('input,select,textarea')].map(x=>({
    tag:x.tagName.toLowerCase(), type:(x.type||''), name:(x.name||''), id:(x.id||''),
    required:!!x.required, disabled:!!x.disabled, checked:!!x.checked,
    has_value: x.type==='file' ? x.files.length>0 : String(x.value||'').trim().length>0
  })),
  body: (document.body?.innerText||'').trim()
})})()"""


async def _evaluate(ws_url: str) -> dict[str, object]:
    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "id": 1, "method": "Runtime.evaluate",
            "params": {"expression": EXPRESSION, "returnByValue": True, "awaitPromise": True},
        }))
        while True:
            message = json.loads(await ws.recv())
            if message.get("id") != 1:
                continue
            value = message.get("result", {}).get("result", {}).get("value")
            if not isinstance(value, str):
                raise RuntimeError("onboarding_dom_unavailable")
            return json.loads(value)


def _safe_snapshot(raw: dict[str, object]) -> dict[str, object]:
    controls = raw.get("controls") if isinstance(raw.get("controls"), list) else []
    safe_controls = [
        {key: row.get(key) for key in (
            "tag", "type", "name", "id", "required", "disabled", "checked", "has_value"
        )}
        for row in controls if isinstance(row, dict)
    ]
    body = str(raw.get("body") or "")
    return {
        "url": str(raw.get("url") or ""),
        "ready": raw.get("ready"),
        "authenticated_identity": re.fullmatch(r"/users/[1-9][0-9]*", str(raw.get("own_user_path") or "")) is not None,
        "forms": int(raw.get("forms") or 0),
        "controls": safe_controls,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "body_length": len(body),
    }


def _required_form_complete(snapshot: dict[str, object]) -> bool:
    controls = [row for row in snapshot.get("controls") or [] if isinstance(row, dict)]
    required = [
        row for row in controls
        if row.get("required") is True and row.get("disabled") is not True
        and row.get("type") not in {"hidden", "submit", "button", "file"}
    ]
    return bool(required) and all(
        row.get("checked") is True if row.get("type") in {"checkbox", "radio"}
        else row.get("has_value") is True
        for row in required
    )


def _sms_approved(body: str) -> bool:
    text = re.sub(r"\s+", "", body)
    return any(token in text for token in (
        "SMS認証済み", "SMS認証済", "電話番号認証済み", "電話番号認証済",
    ))


def _identity_approved(body: str) -> bool:
    text = re.sub(r"\s+", "", body)
    approved = any(token in text for token in (
        "本人確認✓", "本人確認✔", "本人確認済み", "本人確認承認済み",
    ))
    return approved and "非承認" not in text and "申請中" not in text


def observe(home: Path) -> dict[str, object]:
    output = home / ".config" / "anicca" / "gig" / "onboarding-observation.json"
    # A failed current attempt must not leave a previous authentication success current.
    _write_private(output, {"version": 1, "platform": "coconala", "pages": {},
                            "classifications": {"authenticated": None}})
    os.environ["CLOAK_CDP_BASE_URL"] = "http://127.0.0.1:9223"
    os.environ["CLOAK_TARGET_OWNERS_FILE"] = str(
        home / ".cloak" / "vault" / "gig-target-owners.json"
    )
    snapshots: dict[str, object] = {}
    raw_bodies: dict[str, str] = {}
    for state, url in PAGES.items():
        tab = cdp_default_tab.open_tab(url, background=True, owner="gig-onboarding")
        try:
            raw = {}
            for _ in range(20):
                time.sleep(0.5)
                raw = asyncio.run(_evaluate(str(tab["ws"])))
                if raw.get("ready") == "complete":
                    break
            raw_bodies[state] = str(raw.get("body") or "")
            snapshots[state] = _safe_snapshot(raw)
        finally:
            cdp_default_tab.close_tab(str(tab["target_id"]), owner="gig-onboarding")
    evidence = {"version": 1, "platform": "coconala", "pages": snapshots}

    classifications = {state: False for state in PAGES}
    classifications["email_verified"] = False
    classifications["authenticated"] = observed_authentication(snapshots)
    if classifications["authenticated"] is True:
        digest = hashlib.sha256(
            json.dumps(snapshots["authenticated"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        record(home, "authenticated", digest)
        record(home, "email_verified", digest)
        classifications["authenticated"] = True
        classifications["email_verified"] = True
    for state in ("seller_information", "bank_registered"):
        if classifications["authenticated"] is True and _required_form_complete(snapshots[state]):
            digest = hashlib.sha256(
                json.dumps(snapshots[state], sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            record(home, state, digest)
            classifications[state] = True
    if classifications["authenticated"] is True and _sms_approved(raw_bodies.get("sms_verified", "")):
        digest = hashlib.sha256(
            json.dumps(snapshots["sms_verified"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        record(home, "sms_verified", digest)
        classifications["sms_verified"] = True
    if classifications["authenticated"] is True and _identity_approved(raw_bodies.get("identity_approved", "")):
        digest = hashlib.sha256(
            json.dumps(snapshots["identity_approved"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        record(home, "identity_approved", digest)
        classifications["identity_approved"] = True
    evidence["classifications"] = classifications
    _write_private(output, evidence)
    return evidence


def main() -> int:
    evidence = observe(Path.home())
    print(json.dumps({
        "status": "observed",
        "pages": {state: row["url"] for state, row in evidence["pages"].items()},
        "complete": sorted(state for state, complete in evidence["classifications"].items() if complete),
        "pending": sorted(state for state, complete in evidence["classifications"].items() if not complete),
        "evidence": "private:onboarding-observation.json",
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
