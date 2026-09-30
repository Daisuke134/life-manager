#!/usr/bin/env python3
"""Fail-closed contracts for filling an Upwork proposal before any submit click."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import websockets


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from cdp_nav_snapshot import (  # noqa: E402
    LOAD_TIMEOUT_SECS, _call, _wait_for_load, hidden_page_target,
)


_SNAPSHOT_KEYS = {
    "attachments", "available_connects", "bid_usd", "cover_letter", "duration_label", "form_url",
    "job_id", "required_connects", "screening_answers", "submit_enabled",
    "submit_label", "validation_errors",
}
_SUBMIT_KEYS = {"form_url", "job_id", "proposal_id", "state"}
GIG_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNNER = GIG_ROOT.parents[2] / "runtime/agent-runner/agent_runner.py"
DEFAULT_STEP_SCHEMA = GIG_ROOT / "schemas/gig_step_result.schema.json"
DEFAULT_OPERATOR_EVIDENCE = Path.home() / "gig/evidence/upwork-browser-operator"


def _duration_label(days: Any) -> str:
    if type(days) is not int or days < 1:
        raise ValueError("upwork_proposal_preflight_mismatch")
    if days <= 30:
        return "Less than 1 month"
    if days <= 90:
        return "1 to 3 months"
    if days <= 180:
        return "3 to 6 months"
    return "More than 6 months"


def fill_preflight_expression(payload: dict[str, Any]) -> str:
    """Build one DOM fill/read expression with no submit click."""
    terms = payload.get("terms") if isinstance(payload, dict) else None
    if not isinstance(terms, dict):
        raise ValueError("upwork_proposal_preflight_mismatch")
    duration = _duration_label(terms.get("delivery_days"))
    sealed = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    duration_json = json.dumps(duration)
    return f'''(async()=>{{
const p={sealed},duration={duration_json},wait=ms=>new Promise(r=>setTimeout(r,ms));
const norm=x=>(x||'').replace(/\\s+/g,' ').trim();
const setValue=(x,v)=>{{if(!x)throw Error('upwork_form_control_missing');const proto=x.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(x,String(v));x.dispatchEvent(new Event('input',{{bubbles:true}}));x.dispatchEvent(new Event('change',{{bubbles:true}}));}};
const cover=document.querySelector('.cover-letter-area textarea,textarea[data-test*="cover" i],textarea[aria-label*="cover" i],textarea[aria-labelledby="cover_letter_label"],textarea.inner-textarea');
const hourly=p.terms.type==='hourly',bid=document.querySelector(hourly?'#step-rate':'#charged-amount-id,input[data-test*="bid" i],input[name*="bid" i],.fe-proposal-job-rate input,input[data-test="currency-input"]:not([disabled])');
setValue(cover,p.cover_letter);setValue(bid,p.terms.bid_usd);
let durationLabel=null;if(!hourly){{const durationRoot=document.querySelector('.fe-proposal-job-estimated-duration,[data-test*="duration" i]');
const combo=document.querySelector('[role="combobox"][aria-labelledby="duration-label"]')||durationRoot?.querySelector('[role="combobox"],button');if(!combo)throw Error('upwork_duration_missing');combo.click();await wait(100);
const option=[...document.querySelectorAll('[role="option"]')].find(x=>norm(x.innerText)===duration)||[...(durationRoot?.querySelectorAll('li,[role="option"]')||[])].find(x=>norm(x.innerText)===duration);if(!option)throw Error('upwork_duration_option_missing');option.click();await wait(100);durationLabel=norm(combo.innerText);}}
if(hourly){{const sri=document.querySelector('[data-test="sri-input"]'),frequency=[...(sri?.querySelectorAll('[role="combobox"]')||[])][0];if(!frequency)throw Error('upwork_rate_increase_frequency_missing');frequency.click();await wait(100);const never=[...document.querySelectorAll('[role="option"]')].find(x=>norm(x.innerText)==='Never');if(!never)throw Error('upwork_rate_increase_never_missing');never.click();await wait(100);}}
const areas=[...document.querySelectorAll('.fe-proposal-job-questions textarea')];if(areas.length!==p.screening_answers.length)throw Error('upwork_question_count_mismatch');
const answers=p.screening_answers.map(item=>{{const area=areas.find(x=>norm((x.closest('label,.up-form-group,.air3-form-group,[data-test]')||x.parentElement).innerText).includes(norm(item.question)));if(!area)throw Error('upwork_question_mismatch');setValue(area,item.answer);return{{question:item.question,answer:area.value}};}});
const submit=[...document.querySelectorAll('button')].find(x=>['submit proposal','send proposal'].includes(norm(x.innerText).toLowerCase()))||document.querySelector('footer .air3-btn-primary,footer button[type="submit"],button[data-test*="submit" i]');if(!submit)throw Error('upwork_submit_control_missing');
const body=norm(document.body.innerText),required=p.terms.required_connects,isInvite=p.status==='frozen_waiting_for_invitation',costs=[...body.matchAll(/(\\d+)\\s+Connects/gi)].map(x=>Number(x[1])),connects=isInvite?(costs.some(x=>x>0)?null:0):(body.includes(String(required)+' Connects')?required:null),availableMatch=body.match(/Available Connects:?\\s*(\\d+)/i),remainingMatch=body.match(/you(?:'|’)ll have\\s+(\\d+)\\s+Connects remaining/i),available=isInvite?0:(availableMatch?Number(availableMatch[1]):remainingMatch?Number(remainingMatch[1])+required:null);
const errors=[...document.querySelectorAll('.form-error,.air3-form-error,.up-alert-danger,[role="alert"]')].filter(x=>x.offsetParent).map(x=>norm(x.innerText)).filter(Boolean);
return{{job_id:p.job_id,form_url:location.href,required_connects:connects,available_connects:available,bid_usd:Number(String(bid.value).replace(/[^0-9.-]/g,'')),duration_label:durationLabel,cover_letter:cover.value,screening_answers:answers,attachments:[],submit_label:norm(submit.innerText),submit_enabled:!submit.disabled,validation_errors:errors}};
}})()'''


def invitation_accept_expression() -> str:
    """Enter the zero-Connect invitation form without submitting it."""
    return '''(()=>{const norm=x=>(x||'').replace(/\\s+/g,' ').trim().toLowerCase();
const controls=[...document.querySelectorAll('button,a')];
const accept=controls.find(x=>['accept and send a proposal','submit a proposal','accept interview'].includes(norm(x.innerText)));
if(!accept||accept.disabled)throw Error('upwork_invitation_accept_missing');accept.click();return true;})()'''


def submit_readback_expression(job_id: str) -> str:
    """Read a post-click receipt without proposal copy."""
    sealed_job = json.dumps(job_id)
    return f'''(()=>{{
const job={sealed_job},body=(document.body.innerText||'').replace(/\\s+/g,' ').trim(),url=location.href;
const hrefs=[...document.querySelectorAll('a[href]')].map(x=>x.href).concat([url]);
const match=hrefs.map(x=>x.match(new RegExp('/proposals/(?!job(?:/|$))([^/?#]+)'))).find(Boolean);
const submitted=/proposal (?:was )?submitted|proposal submitted|view proposal/i.test(body);
return{{job_id:job,form_url:url,proposal_id:match?match[1]:null,state:submitted&&match?'submitted':'unknown'}};
}})()'''


def browser_operator_prompt(job_id: str, form_url: str, cdp_endpoint: str) -> str:
    """Build the operator prompt from the already-resolved local endpoint."""
    endpoint = cdp_endpoint.rstrip("/") if isinstance(cdp_endpoint, str) else ""
    parsed = urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}:
        raise ValueError("upwork_browser_endpoint_invalid")
    return f"""Operate the current authenticated Upwork proposal page as a browser agent.
The exact immutable proposal for job {job_id} is already filled and its exactly-once effect fence is
already closed. Inspect the live browser at {endpoint} and find the existing page whose URL
is {form_url}. Use current page feedback to handle ordinary non-financial UI and submit that already
filled proposal exactly once. Do not edit proposal fields, buy anything, boost, subscribe, open another
job, change account settings, edit code, or claim success from a click. Stop after the page visibly
leaves the editable proposal state or shows a provider-authored result. Return status ok if you acted,
blocked if a human-only ceremony appears, or error if the live result remains unknown. You may accept
ordinary educational or marketplace-safety acknowledgements needed to continue this already-authorized
submission when they do not change price, proposal content, contract terms, identity, tax or payment
facts. CAPTCHA, identity proof and personal legal/tax declarations remain human-only. Evidence must name
only safe page state or local evidence paths; never include proposal text or credentials."""


def _run_browser_operator(job_id: str, form_url: str) -> None:
    endpoint = os.environ.get("CLOAK_CDP_BASE_URL", "")
    prompt = browser_operator_prompt(job_id, form_url, endpoint)
    evidence = DEFAULT_OPERATOR_EVIDENCE / f"{time.time_ns()}-{job_id.lstrip('~')}"
    evidence.mkdir(parents=True, exist_ok=False, mode=0o700)
    completed = subprocess.run([
        sys.executable, str(DEFAULT_RUNNER), "--task-class", "browser-lane-agent",
        "--prompt-stdin",
        "--schema", str(DEFAULT_STEP_SCHEMA), "--evidence-dir", str(evidence),
        "--task-label", "upwork-proposal-submit", "--loop", "gig-upwork",
        "--workdir", str(Path.home()), "--timeout-seconds", "900",
    ], input=prompt, text=True, capture_output=True, timeout=930, check=False)
    if completed.returncode != 0:
        (evidence / "operator-return-code.txt").write_text(
            f"{completed.returncode}\n", encoding="utf-8",
        )


def validate_submit_readback(snapshot: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
    """Require an exact official proposal identifier after the one click."""
    if not isinstance(snapshot, dict) or set(snapshot) != _SUBMIT_KEYS:
        raise ValueError("upwork_proposal_submit_unconfirmed")
    job_id = payload.get("job_id") if isinstance(payload, dict) else None
    proposal_id = snapshot.get("proposal_id")
    url = urlsplit(str(snapshot.get("form_url") or ""))
    if (
        snapshot.get("job_id") != job_id or snapshot.get("state") != "submitted"
        or not isinstance(proposal_id, str) or not proposal_id.strip()
        or url.scheme != "https" or url.netloc != "www.upwork.com"
    ):
        raise ValueError("upwork_proposal_submit_unconfirmed")
    evidence = hashlib.sha256(json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return {"state": "submitted", "job_id": job_id, "proposal_id": proposal_id,
            "evidence_sha256": evidence}


def require_effect_start(
    preflight: dict[str, Any], start_effect: Callable[[dict[str, Any]], bool],
) -> None:
    """Make a durable positive fence decision mandatory before the click expression."""
    if not callable(start_effect) or start_effect(preflight) is not True:
        raise ValueError("upwork_proposal_effect_not_started")


async def fill_proposal_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    """Fill and read one authenticated hidden proposal form without submit."""
    job_id = payload.get("job_id") if isinstance(payload, dict) else None
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("upwork_proposal_preflight_mismatch")
    apply_url = f"https://www.upwork.com/nx/proposals/job/{job_id}/apply/#/"
    async with hidden_page_target(apply_url) as ws_url:
        async with websockets.connect(
            ws_url, ping_interval=None, open_timeout=10, max_size=40 * 1024 * 1024,
        ) as ws:
            await _call(ws, "Page.enable", {}, 1)
            await _call(ws, "Page.navigate", {"url": apply_url}, 2)
            _, cid = await _wait_for_load(
                ws, asyncio.get_event_loop().time() + LOAD_TIMEOUT_SECS, 3,
            )
            await asyncio.sleep(2)
            result = await _call(ws, "Runtime.evaluate", {
                "expression": fill_preflight_expression(payload),
                "awaitPromise": True, "returnByValue": True,
            }, cid)
    value = result.get("result", {}).get("result", {}).get("value")
    if result.get("error") or not isinstance(value, dict):
        raise ValueError("upwork_proposal_preflight_mismatch")
    return validate_preflight(value, payload)


async def submit_proposal_after_fence(
    payload: dict[str, Any], start_effect: Callable[[dict[str, Any]], bool],
) -> dict[str, str]:
    """Fill, verify, cross a durable fence, click once, then require official readback."""
    job_id = payload.get("job_id") if isinstance(payload, dict) else None
    if not isinstance(job_id, str) or not job_id or not callable(start_effect):
        raise ValueError("upwork_proposal_preflight_mismatch")
    apply_url = f"https://www.upwork.com/nx/proposals/job/{job_id}/apply/#/"
    is_invitation = payload.get("status") == "frozen_waiting_for_invitation"
    entry_url = str(payload.get("job_url") or "") if is_invitation else apply_url
    async with hidden_page_target(entry_url) as ws_url:
        async with websockets.connect(
            ws_url, ping_interval=None, open_timeout=10, max_size=40 * 1024 * 1024,
        ) as ws:
            await _call(ws, "Page.enable", {}, 1)
            await _call(ws, "Page.navigate", {"url": entry_url}, 2)
            _, cid = await _wait_for_load(
                ws, asyncio.get_event_loop().time() + LOAD_TIMEOUT_SECS, 3,
            )
            await asyncio.sleep(2)
            if is_invitation:
                await _call(ws, "Runtime.evaluate", {
                    "expression": invitation_accept_expression(), "returnByValue": True,
                }, cid)
                await asyncio.sleep(2)
            filled = await _call(ws, "Runtime.evaluate", {
                "expression": fill_preflight_expression(payload),
                "awaitPromise": True, "returnByValue": True,
            }, cid)
            snapshot = filled.get("result", {}).get("result", {}).get("value")
            preflight = validate_preflight(snapshot, payload)
            require_effect_start(preflight, start_effect)
            await asyncio.to_thread(_run_browser_operator, job_id, str(snapshot["form_url"]))
            await asyncio.sleep(5)
            readback = await _call(ws, "Runtime.evaluate", {
                "expression": submit_readback_expression(job_id), "returnByValue": True,
            }, cid + 1)
            value = readback.get("result", {}).get("result", {}).get("value")
            if isinstance(value, dict) and value.get("state") == "unknown":
                diagnostic = await _call(ws, "Runtime.evaluate", {
                    "expression": """(()=>{const n=x=>(x||'').replace(/\\s+/g,' ').trim();return{url:location.href,buttons:[...document.querySelectorAll('button')].filter(x=>x.offsetParent).map(x=>n(x.innerText)).filter(Boolean).slice(-12),dialogs:[...document.querySelectorAll('[role=dialog]')].filter(x=>x.offsetParent).map(x=>n(x.innerText).slice(0,300)),alerts:[...document.querySelectorAll('[role=alert],.air3-alert')].filter(x=>x.offsetParent).map(x=>n(x.innerText).slice(0,300))}})()""",
                    "returnByValue": True,
                }, cid + 2)
                detail = diagnostic.get("result", {}).get("result", {}).get("value")
                raise ValueError("upwork_proposal_submit_unconfirmed:" + json.dumps(
                    detail, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ))
    value = readback.get("result", {}).get("result", {}).get("value")
    return validate_submit_readback(value, payload)


def validate_preflight(snapshot: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Require an exact filled-form readback and return no proposal copy."""
    if not isinstance(snapshot, dict) or set(snapshot) != _SNAPSHOT_KEYS:
        raise ValueError("upwork_proposal_preflight_mismatch")
    terms = payload.get("terms") if isinstance(payload, dict) else None
    if not isinstance(terms, dict):
        raise ValueError("upwork_proposal_preflight_mismatch")
    job_id = payload.get("job_id")
    url = urlsplit(str(snapshot.get("form_url") or ""))
    required = terms.get("required_connects")
    expected = {
        "job_id": job_id,
        "required_connects": required,
        "bid_usd": terms.get("bid_usd"),
        "duration_label": None if terms.get("type") == "hourly" else _duration_label(terms.get("delivery_days")),
        "cover_letter": payload.get("cover_letter"),
        "screening_answers": payload.get("screening_answers"),
        "attachments": payload.get("attachments"),
    }
    if (
        not isinstance(job_id, str) or not job_id
        or url.scheme != "https" or url.netloc != "www.upwork.com"
        or not any(f"/{prefix}/proposals/job/{job_id}/apply" in url.path for prefix in ("ab", "nx"))
        or any(snapshot.get(key) != value for key, value in expected.items())
        or type(snapshot.get("available_connects")) is not int
        or snapshot["available_connects"] < required
        or snapshot.get("submit_enabled") is not True
        or snapshot.get("validation_errors") != []
        or not isinstance(snapshot.get("submit_label"), str)
        or (
            payload.get("status") == "frozen_waiting_for_invitation"
            and not re.search(r"submit|send", snapshot["submit_label"], re.IGNORECASE)
        )
        or (
            payload.get("status") != "frozen_waiting_for_invitation"
            and not re.search(r"submit|send", snapshot["submit_label"], re.IGNORECASE)
        )
    ):
        raise ValueError("upwork_proposal_preflight_mismatch")
    evidence = hashlib.sha256(json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return {
        "ready": True,
        "job_id": job_id,
        "required_connects": required,
        "available_connects": snapshot["available_connects"],
        "evidence_sha256": evidence,
    }
