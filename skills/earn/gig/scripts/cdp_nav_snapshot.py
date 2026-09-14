#!/usr/bin/env python3
"""cdp_nav_snapshot.py — deterministic hidden-target evidence helper for the gig reality-verifier
(feature gig-reality-verify, fresh-adversary FIND-001 fix: docs/loop-engineering/26-...md §8).

Unlike cdp_snapshot.py (which only screenshots whatever tab is ALREADY open), this helper actually
performs a real CDP `Page.navigate(url)` call, WAITS for the page to finish loading (Page.loadEventFired
event, with a document.readyState poll fallback), THEN captures rendered DOM text and appends a trajectory
row — so the fresh judge's navigation is a reproducible tool call, not freeform LLM-improvised Bash/CDP
that happened to work once.

get_tab()/navigate mechanics below are self-contained (copied IN, not imported from any path outside
this repo — behavioral-spec REQ-006 requires no dangling cross-repo reference).

Usage:
  python3 cdp_nav_snapshot.py <pass_id> <seq> <label> <url> [action_note]
    e.g. python3 cdp_nav_snapshot.py reality-1783800000 01 reality_check_01 https://coconala.com/mypage/services_lists

Writes:
  ~/gig/trajectory/<pass_id>/<seq>-<label>.json
  appends {ts,pass_id,seq,label,url,title,action,navigated_ok} to ~/gig/trajectory/<pass_id>/trajectory.jsonl
Prints the evidence path on success, or ERROR:<reason> on failure (never raises — capture must never abort
a verification run).
"""
from __future__ import annotations

import argparse, asyncio, base64, fcntl, hashlib, json, os, re, sys, subprocess, time, urllib.request
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import urlparse

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
BROWSER_SCRIPTS_DIR = SCRIPTS_DIR.parents[2] / "browser/scripts"
if str(BROWSER_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(BROWSER_SCRIPTS_DIR))
from application_eligibility import evaluate_application
from market_snapshot import parse_market
import target_ownership

try:
    import websockets
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets", "-q"], capture_output=True)
    import websockets

LOAD_TIMEOUT_SECS = 15  # bounded — never hang the judge indefinitely on a page that never settles
APPLICATION_CONFIRM_SELECTOR = (
    '#OfferAddForm button[type="submit"],'
    'form[action^="/offers/add/"] button[type="submit"]'
)
RETAINER_ULID_PATTERN = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")


def _cdp_base():
    # No silent default. The old fallback was http://127.0.0.1:9222, which on this host
    # is a proxy onto the SAME browser as gig production :9223 -- the 2026-07-26
    # collision. Whenever the env is set (gig_pass.sh exports :9223) nothing changes;
    # when it is missing we now fail loudly instead of quietly attaching to whatever
    # answers on the interactive port.
    base = os.environ.get("CLOAK_CDP_BASE_URL")
    if not base:
        raise RuntimeError(
            "CLOAK_CDP_BASE_URL is unset. Lease a browser first: "
            "~/.config/ai/bin/browser-guard.sh acquire <identity> "
            "(identities in ~/.config/ai/registry/browsers.toml). "
            "Refusing to guess a CDP port."
        )
    return base.rstrip("/")


def _target_operation_lock_path(
    ws_url: str,
    *,
    leases_path: Path | None = None,
) -> Path:
    target_id = urlparse(ws_url).path.rstrip("/").split("/")[-1]
    if not target_id:
        raise ValueError("target_operation_lock_missing_target")
    if leases_path is None:
        leases_path = Path(os.path.expanduser(
            os.environ.get(
                "CLOAK_CONTEXT_LEASES_FILE",
                "~/.cloak/vault/leases.json",
            )
        ))
    return Path(leases_path).parent / "operations" / f"{target_id}.lock"


@contextmanager
def _target_operation_lock(ws_url: str):
    lock_path = _target_operation_lock_path(ws_url)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def get_tab():
    data = json.loads(
        urllib.request.urlopen(f"{_cdp_base()}/json/list", timeout=8).read()
    )
    pages = [t for t in data if t.get("type") == "page"]
    for t in pages:
        if "coconala.com" in (t.get("url") or ""):
            return t["id"]
    if pages:
        return pages[0]["id"]
    raise RuntimeError(f"no page tab on {_cdp_base()}")


def _browser_ws_url():
    data = json.loads(
        urllib.request.urlopen(f"{_cdp_base()}/json/version", timeout=8).read()
    )
    return data["webSocketDebuggerUrl"]


@asynccontextmanager
async def hidden_page_target(url):
    """Own one authenticated default-context target without adding a browser window tab."""
    owner = target_ownership.require_owner(
        os.environ.get("CLOAK_BROWSER_OWNER") or f"gig-nav-snapshot-{os.getpid()}"
    )
    async with websockets.connect(
        _browser_ws_url(),
        ping_interval=None,
        open_timeout=10,
        max_size=40 * 1024 * 1024,
    ) as browser:
        opened = await _call(
            browser,
            "Target.createTarget",
            {"url": url, "hidden": True, "background": True},
            1,
        )
        if opened.get("error"):
            raise RuntimeError(f"hidden_target_create_failed:{opened['error']}")
        target_id = opened.get("result", {}).get("targetId")
        if not target_id:
            raise RuntimeError("hidden_target_create_missing_id")
        claimed = False
        try:
            target_ownership.claim_target(target_id, owner)
            claimed = True
            yield (
                f"ws://{urlparse(_cdp_base()).netloc}"
                f"/devtools/page/{target_id}"
            )
        finally:
            try:
                await _call(
                    browser,
                    "Target.closeTarget",
                    {"targetId": target_id},
                    2,
                )
            except Exception:
                pass
            finally:
                if claimed:
                    target_ownership.release_target(target_id, owner)


async def _connect():
    tab = get_tab()
    return await websockets.connect(
        f"ws://{urlparse(_cdp_base()).netloc}/devtools/page/{tab}",
        ping_interval=None, open_timeout=10, max_size=40 * 1024 * 1024,
    )


async def _call(ws, method, params, cid):
    await ws.send(json.dumps({"id": cid, "method": method, "params": params}))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=25)
        d = json.loads(raw)
        if d.get("id") == cid:
            return d


async def _wait_for_load(ws, deadline, start_cid):
    """Wait for Page.loadEventFired, falling back to a document.readyState poll if the event never
    arrives within the deadline (bounded — REQ-006 edge case: never hang indefinitely)."""
    cid = start_cid
    loop = asyncio.get_event_loop()
    while loop.time() < deadline:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(1.0, remaining))
        except asyncio.TimeoutError:
            continue
        try:
            d = json.loads(raw)
        except Exception:
            continue
        if d.get("method") == "Page.loadEventFired":
            return True, cid
    # fallback: poll document.readyState directly
    while loop.time() < deadline:
        r = await _call(ws, "Runtime.evaluate",
                         {"expression": "document.readyState", "returnByValue": True}, cid)
        cid += 1
        val = r.get("result", {}).get("result", {}).get("value")
        if val == "complete":
            return True, cid
        await asyncio.sleep(0.5)
    return False, cid


async def navigate_and_snapshot(
    pass_id, seq, label, url, action, settle_seconds=0, viewport_width=0,
):
    outdir = os.path.expanduser(f"~/gig/trajectory/{pass_id}")
    os.makedirs(outdir, exist_ok=True)
    evidence_path = os.path.join(outdir, f"{seq}-{label}.json")
    final_url, title, navigated_ok = "", "", False
    rendered_text = ""
    rendered_links = []

    async with hidden_page_target(url) as ws_url:
        async with websockets.connect(
            ws_url,
            ping_interval=None,
            open_timeout=10,
            max_size=40 * 1024 * 1024,
        ) as ws:
            cid = 1
            await _call(ws, "Page.enable", {}, cid); cid += 1
            if viewport_width:
                await _call(ws, "Emulation.setDeviceMetricsOverride", {
                    "width": viewport_width, "height": 900,
                    "deviceScaleFactor": 1, "mobile": False,
                }, cid)
                cid += 1
            await ws.send(json.dumps({"id": cid, "method": "Page.navigate", "params": {"url": url}}))
            cid += 1

            deadline = asyncio.get_event_loop().time() + LOAD_TIMEOUT_SECS
            navigated_ok, cid = await _wait_for_load(ws, deadline, cid)
            if settle_seconds:
                await asyncio.sleep(settle_seconds)

            # page state (url + title) — evidence beyond the pixels, and proof navigation actually landed
            try:
                r = await _call(ws, "Runtime.evaluate",
                                 {"expression": "document.location.href+'|||'+document.title",
                                  "returnByValue": True}, cid); cid += 1
                v = r.get("result", {}).get("result", {}).get("value", "") or ""
                if "|||" in v:
                    final_url, title = v.split("|||", 1)
            except Exception:
                pass

            # Hidden targets intentionally have no compositor window, so Chrome never
            # answers Page.captureScreenshot for them. Persist the rendered DOM text
            # instead: it is the exact server/JS result the judge must compare, without
            # opening or navigating a user-visible tab.
            r = await _call(
                ws,
                "Runtime.evaluate",
                {
                    "expression": (
                        "document.body ? "
                        "document.body.innerText.slice(0,120000) : ''"
                    ),
                    "returnByValue": True,
                },
                cid,
            )
            rendered_text = (
                r.get("result", {}).get("result", {}).get("value", "")
                or ""
            )
            cid += 1
            r = await _call(
                ws,
                "Runtime.evaluate",
                {
                    "expression": """JSON.stringify(Array.from(document.querySelectorAll('a[href]')).slice(0,2000).map(a=>{const c=a.closest('article,li,tr,[data-test],[data-qa]')||a.parentElement;return {href:a.href,text:(a.innerText||'').trim().slice(0,500),context:((c&&c.innerText)||'').trim().slice(0,2000),aria:a.getAttribute('aria-label')||'',data_qa:a.getAttribute('data-qa')||'',class_name:a.className||''}}))""",
                    "returnByValue": True,
                },
                cid,
            )
            raw_links = r.get("result", {}).get("result", {}).get("value", "[]")
            try:
                rendered_links = json.loads(raw_links)
            except (TypeError, json.JSONDecodeError):
                rendered_links = []

    evidence = {
        "url": final_url,
        "requested_url": url,
        "title": title,
        "rendered_text": rendered_text,
        "rendered_links": rendered_links,
        "navigated_ok": navigated_ok,
    }
    with open(evidence_path, "w", encoding="utf-8") as handle:
        json.dump(evidence, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    os.chmod(evidence_path, 0o600)

    row = {"ts": int(time.time()), "pass_id": str(pass_id), "seq": str(seq), "label": label,
           "requested_url": url, "url": final_url, "title": title, "action": action,
           "navigated_ok": navigated_ok, "evidence_kind": "rendered_dom_text",
           "artifact": evidence_path}
    with open(os.path.join(outdir, "trajectory.jsonl"), "a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return evidence_path


async def probe_session(url: str) -> dict[str, object]:
    """Check authenticated routing in a hidden target without changing a visible tab."""
    final_url = ""
    async with hidden_page_target(url) as ws_url:
        async with websockets.connect(
            ws_url,
            ping_interval=None,
            open_timeout=10,
            max_size=40 * 1024 * 1024,
        ) as ws:
            cid = 1
            await _call(ws, "Page.enable", {}, cid)
            cid += 1
            await ws.send(json.dumps({
                "id": cid,
                "method": "Page.navigate",
                "params": {"url": url},
            }))
            cid += 1
            _, cid = await _wait_for_load(
                ws,
                asyncio.get_event_loop().time() + LOAD_TIMEOUT_SECS,
                cid,
            )
            result = await _call(
                ws,
                "Runtime.evaluate",
                {
                    "expression": "document.location.href",
                    "returnByValue": True,
                },
                cid,
            )
            final_url = (
                result.get("result", {}).get("result", {}).get("value", "")
                or ""
            )
    lowered = final_url.lower()
    logged_out = any(
        marker in lowered
        for marker in ("/login", "/signin", "/sign_in")
    )
    return {
        "ok": not logged_out,
        "logged_out": logged_out,
        "url": url,
        "final_url": final_url,
        "hidden": True,
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(data)
    os.replace(temporary, path)


async def observe_target(
    ws_url: str,
    url: str,
    screenshot_path: Path,
    live_dom_path: Path,
) -> dict[str, object]:
    """Serialize navigation against irreversible work on this leased target."""
    with _target_operation_lock(ws_url):
        return await _observe_target_locked(
            ws_url,
            url,
            screenshot_path,
            live_dom_path,
        )


async def _observe_target_locked(
    ws_url: str,
    url: str,
    screenshot_path: Path,
    live_dom_path: Path,
) -> dict[str, object]:
    """Navigate one already-leased page target and emit bounded exact-route evidence."""
    async with websockets.connect(
        ws_url,
        ping_interval=None,
        open_timeout=10,
        max_size=40 * 1024 * 1024,
    ) as ws:
        cid = 1
        await _call(ws, "Page.enable", {}, cid)
        cid += 1
        await ws.send(json.dumps({"id": cid, "method": "Page.navigate", "params": {"url": url}}))
        cid += 1
        loaded, cid = await _wait_for_load(
            ws,
            asyncio.get_event_loop().time() + LOAD_TIMEOUT_SECS,
            cid,
        )
        if not loaded:
            raise RuntimeError("navigation_timeout")
        state = await _call(
            ws,
            "Runtime.evaluate",
            {
                "expression": "document.location.href+'|||'+document.title",
                "returnByValue": True,
            },
            cid,
        )
        cid += 1
        value = state.get("result", {}).get("result", {}).get("value", "") or ""
        final_url, separator, title = value.partition("|||")
        if not separator or final_url != url:
            raise RuntimeError(f"navigation_url_mismatch:{final_url}")
        shot = await _call(ws, "Page.captureScreenshot", {"format": "png"}, cid)
        screenshot_data = shot.get("result", {}).get("data")
        if not screenshot_data:
            raise RuntimeError("no_screenshot_data")

    live_dom = {
        "url": final_url,
        "not_found": False,
        "observed": True,
        "title": title,
    }
    _atomic_write(screenshot_path, base64.b64decode(screenshot_data))
    _atomic_write(
        live_dom_path,
        (json.dumps(live_dom, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"),
    )
    return live_dom


async def open_application_form(
    ws_url: str,
    request_id: str,
    screenshot_path: Path,
    evidence_path: Path,
) -> dict[str, object]:
    """Open Coconala's canonical application route and verify the real form controls."""
    request_id = str(request_id).strip()
    if not request_id.isdigit():
        raise ValueError("request_id_must_be_digits")
    expected_url = f"https://coconala.com/offers/add/{request_id}"
    async with websockets.connect(
        ws_url,
        ping_interval=None,
        open_timeout=10,
        max_size=40 * 1024 * 1024,
    ) as ws:
        cid = 1
        await _call(ws, "Page.enable", {}, cid)
        cid += 1
        await ws.send(json.dumps({
            "id": cid,
            "method": "Page.navigate",
            "params": {"url": expected_url},
        }))
        cid += 1
        loaded, cid = await _wait_for_load(
            ws,
            asyncio.get_event_loop().time() + LOAD_TIMEOUT_SECS,
            cid,
        )
        if not loaded:
            raise RuntimeError("application_form_navigation_timeout")
        state = await _call(
            ws,
            "Runtime.evaluate",
            {
                "expression": (
                    "JSON.stringify({"
                    "url:document.location.href,"
                    "title:document.title,"
                    "has_content:!!document.querySelector("
                    "'textarea[name=\"data[Offer][content]\"]'),"
                    "has_price:!!document.querySelector("
                    "'input[name=\"data[Offer][price]\"]'),"
                    "has_expire_date:!!document.querySelector("
                    "'input[name=\"data[Offer][expire_date]\"]'),"
                    "has_confirm:[...document.querySelectorAll('button')].some("
                    "button=>button.innerText.trim()==='確認する')"
                    "})"
                ),
                "returnByValue": True,
            },
            cid,
        )
        cid += 1
        raw_state = (
            state.get("result", {}).get("result", {}).get("value", "")
            or ""
        )
        try:
            form_state = json.loads(raw_state)
        except (TypeError, json.JSONDecodeError) as error:
            raise RuntimeError("application_form_state_invalid") from error
        if form_state.get("url") != expected_url:
            raise RuntimeError(
                f"application_form_url_mismatch:{form_state.get('url', '')}"
            )
        field_state = {
            "content": form_state.get("has_content") is True,
            "price": form_state.get("has_price") is True,
            "expire_date": form_state.get("has_expire_date") is True,
            "confirm": form_state.get("has_confirm") is True,
        }
        form_verified = (
            str(form_state.get("title", "")).startswith("応募する")
            and all(field_state.values())
        )
        if not form_verified:
            raise RuntimeError("application_form_controls_missing")
        shot = await _call(ws, "Page.captureScreenshot", {"format": "png"}, cid)
        screenshot_data = shot.get("result", {}).get("data")
        if not screenshot_data:
            raise RuntimeError("application_form_screenshot_missing")

    evidence = {
        "request_id": request_id,
        "url": expected_url,
        "title": form_state["title"],
        "form_verified": True,
        "fields": field_state,
    }
    _atomic_write(screenshot_path, base64.b64decode(screenshot_data))
    _atomic_write(
        evidence_path,
        (
            json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        ).encode("utf-8"),
    )
    return evidence


async def open_retainer_application_form(
    ws_url: str,
    outsource_ulid: str,
    screenshot_path: Path,
    evidence_path: Path,
) -> dict[str, object]:
    """Open and prove the measured retainer form before any irreversible click."""
    request_id = str(outsource_ulid).strip()
    if RETAINER_ULID_PATTERN.fullmatch(request_id) is None:
        raise ValueError("outsource_ulid_invalid")
    expected_url = f"https://coconala.com/job_matching/outsources/{request_id}/apply"
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=10, max_size=40 * 1024 * 1024) as ws:
        cid = 1
        await _call(ws, "Page.enable", {}, cid); cid += 1
        await ws.send(json.dumps({"id": cid, "method": "Page.navigate", "params": {"url": expected_url}})); cid += 1
        loaded, cid = await _wait_for_load(ws, asyncio.get_event_loop().time() + LOAD_TIMEOUT_SECS, cid)
        if not loaded:
            raise RuntimeError("retainer_application_form_navigation_timeout")
        state = await _call(ws, "Runtime.evaluate", {"expression": """JSON.stringify((()=>{const options=['WEEK_ONE','WEEK_TWO','WEEK_THREE','WEEK_FOUR','WEEK_FIVE','BIWEEKLY','MONTH_ONE'];const frequency=[...document.querySelectorAll('select')].filter(s=>options.every(v=>[...s.options].some(o=>o.value===v)));const count=s=>document.querySelectorAll(s).length;return {url:location.href,title:document.title,counts:{compensation:count('input[type="number"][name="desiredCompensation"]'),frequency:frequency.length,hours_start:count('input[name="weeklyWorkingHoursStart"]'),hours_end:count('input[name="weeklyWorkingHoursEnd"]'),message:count('textarea[placeholder="応募メッセージを入力してください"]'),confirm:[...document.querySelectorAll('button,[role="button"]')].filter(b=>b.offsetParent!==null&&(b.innerText||'').trim()==='確認画面に進む').length}})())""", "returnByValue": True}, cid); cid += 1
        raw = state.get("result", {}).get("result", {}).get("value", "") or ""
        form = json.loads(raw)
        if form.get("url") != expected_url or any(value != 1 for value in form.get("counts", {}).values()):
            raise RuntimeError("retainer_application_form_controls_missing")
        shot = await _call(ws, "Page.captureScreenshot", {"format": "png"}, cid)
        encoded = shot.get("result", {}).get("data")
        if not encoded:
            raise RuntimeError("retainer_application_form_screenshot_missing")
    evidence = {"request_id": request_id, "url": expected_url, "title": form.get("title"), "form_verified": True, "fields": form["counts"]}
    _atomic_write(screenshot_path, base64.b64decode(encoded))
    _atomic_write(evidence_path, (json.dumps(evidence, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
    return evidence


async def _mouse_click(ws, x: float, y: float, cid: int) -> int:
    for event_type, button, click_count in (
        ("mouseMoved", "none", 0),
        ("mousePressed", "left", 1),
        ("mouseReleased", "left", 1),
    ):
        await _call(
            ws,
            "Input.dispatchMouseEvent",
            {
                "type": event_type,
                "x": x,
                "y": y,
                "button": button,
                "clickCount": click_count,
            },
            cid,
        )
        cid += 1
    return cid


def _submit_intent_path(evidence_path: Path) -> Path:
    return evidence_path.with_suffix(".intent.json")


def _eligibility_evidence_path(evidence_path: Path) -> Path:
    return evidence_path.with_suffix(".eligibility.json")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_eligibility_evidence(
    evidence_path: Path,
    *,
    request_id: str,
    bucket: str,
    opportunity_url: str,
    brief_text: str,
    proposal_text: str,
    verdict: dict[str, object],
    market: dict[str, object] | None = None,
) -> None:
    """Write the verdict AND the market it was taken on, allowed or refused.

    This sidecar is the only durable trace of an application that never happened.
    A6 has to be able to count the opportunities A5-③ removed and check, later,
    whether removing them was right; a refusal that leaves nothing behind is a
    policy nobody can ever evaluate. It is also the row `application_report` reads
    the market off, so the numbers in the ledger are the numbers the gate saw.
    """
    payload = {
        **verdict,
        "request_id": request_id,
        "bucket": bucket,
        "opportunity_url": opportunity_url,
        "brief_sha256": _sha256_text(brief_text),
        "proposal_sha256": _sha256_text(proposal_text),
        "market": market,
    }
    _atomic_write(
        _eligibility_evidence_path(evidence_path),
        (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        ).encode("utf-8"),
    )


async def _load_opportunity_brief(opportunity_url: str) -> str:
    """Read an authenticated brief in a separate owned target."""
    async with hidden_page_target(opportunity_url) as brief_ws_url:
        async with websockets.connect(
            brief_ws_url,
            ping_interval=None,
            open_timeout=10,
            max_size=40 * 1024 * 1024,
        ) as ws:
            cid = 1
            await _call(ws, "Page.enable", {}, cid)
            cid += 1
            loaded, cid = await _wait_for_load(
                ws,
                asyncio.get_event_loop().time() + LOAD_TIMEOUT_SECS,
                cid,
            )
            if not loaded:
                raise RuntimeError("opportunity_brief_navigation_timeout")
            state = await _call(
                ws,
                "Runtime.evaluate",
                {
                    "expression": (
                        "JSON.stringify({url:location.href,"
                        "text:document.body?.innerText||''})"
                    ),
                    "returnByValue": True,
                },
                cid,
            )
    raw = state.get("result", {}).get("result", {}).get("value", "") or ""
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("opportunity_brief_state_invalid") from error
    if (
        not isinstance(parsed, dict)
        or parsed.get("url") != opportunity_url
        or not str(parsed.get("text") or "").strip()
    ):
        raise RuntimeError("opportunity_brief_unavailable")
    return str(parsed["text"])


def _write_submit_intent(
    evidence_path: Path,
    *,
    request_id: str,
    bucket: str,
    url: str,
    title: str | None,
    state: str,
) -> None:
    """Persist the mutation identity before a click whose ACK may be lost."""
    payload = {
        "request_id": request_id,
        "bucket": bucket,
        "url": url,
        "title": str(title).strip() if title else None,
        "state": state,
    }
    _atomic_write(
        _submit_intent_path(evidence_path),
        (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        ).encode("utf-8"),
    )


async def _application_submit_state(ws, cid: int) -> tuple[dict[str, object], int]:
    state = await _call(
        ws,
        "Runtime.evaluate",
        {
            "expression": (
                "/* application_submit_state_v1 */"
                "JSON.stringify((()=>{"
                "const body=document.body?.innerText||'';"
                "const visible=e=>{if(!e||e.offsetParent===null)return false;"
                "const r=e.getBoundingClientRect();return r.width>0&&r.height>0;};"
                "const buttons=[...document.querySelectorAll('button')];"
                "const modalApply=buttons.find(b=>visible(b)&&!b.disabled&&"
                "(b.innerText||'').trim()==='応募する'&&"
                "b.classList.contains('js_ignite-submit'));"
                "const confirmCandidate=document.querySelector("
                + json.dumps(APPLICATION_CONFIRM_SELECTOR)
                + ");"
                "const confirm=visible(confirmCandidate)&&"
                "(confirmCandidate.innerText||'').trim()==='確認する'"
                "?confirmCandidate:null;"
                "const apply=buttons.find(b=>visible(b)&&!b.disabled&&"
                "(b.innerText||'').trim()==='応募する');"
                "let button=modalApply||confirm||apply||null;"
                "let buttonState=null;"
                "if(button){button.scrollIntoView({block:'center'});"
                "const r=button.getBoundingClientRect();"
                "buttonState={kind:button===modalApply?'modal_apply':"
                "button===confirm?'confirm':'apply',"
                "x:r.left+r.width/2,y:r.top+r.height/2};}"
                "const content=document.querySelector("
                "'textarea[name=\"data[Offer][content]\"]');"
                "const price=document.querySelector("
                "'input[name=\"data[Offer][price]\"]');"
                "const date=document.querySelector("
                "'input[name=\"data[Offer][expire_date]\"]');"
                "const success=location.pathname.startsWith("
                "'/mypage/job_matching/applied/offers')&&"
                "body.includes('応募しました');"
                "return {url:location.href,title:document.title,"
                "body:body.slice(-4000),"
                "proposal_text:content?.value||'',"
                # A5-(1): the number WE are bidding, read off the form we filled
                # rather than reported afterwards by the model that filled it.
                "bid_jpy:price?.value||null,"
                "form_filled:!!(content?.value.trim()&&price?.value.trim()&&"
                "date?.value.trim()),"
                "validation_error:body.includes('入力情報を確認して下さい')||"
                "body.includes('入力内容をご確認'),"
                "success,button:buttonState};})())"
            ),
            "returnByValue": True,
        },
        cid,
    )
    cid += 1
    raw = state.get("result", {}).get("result", {}).get("value", "") or ""
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("application_submit_state_invalid") from error
    if not isinstance(parsed, dict):
        raise RuntimeError("application_submit_state_invalid")
    return parsed, cid


async def _submit_application_locked(
    ws_url: str,
    request_id: str,
    screenshot_path: Path,
    evidence_path: Path,
    *,
    wait_seconds: float = 2.5,
    opportunity_brief: str | None = None,
) -> dict[str, object]:
    """Finish both confirmation stages and create proof only after applied-page success."""
    request_id = str(request_id).strip()
    if not request_id.isdigit():
        raise ValueError("request_id_must_be_digits")
    expected_form_url = f"https://coconala.com/offers/add/{request_id}"
    opportunity_url = f"https://coconala.com/requests/{request_id}"
    applied_url_prefix = "https://coconala.com/mypage/job_matching/applied/offers"
    final_state: dict[str, object] | None = None
    if opportunity_brief is None:
        opportunity_brief = await _load_opportunity_brief(opportunity_url)
    policy_checked = False

    for _ in range(7):
        async with websockets.connect(
            ws_url,
            ping_interval=None,
            open_timeout=10,
            max_size=40 * 1024 * 1024,
        ) as ws:
            cid = 1
            await _call(ws, "Page.enable", {}, cid)
            cid += 1
            state, cid = await _application_submit_state(ws, cid)
            current_url = str(state.get("url") or "")
            if current_url != expected_form_url and not current_url.startswith(
                applied_url_prefix
            ):
                raise RuntimeError(f"application_submit_url_mismatch:{current_url}")
            if state.get("success") is True:
                shot = await _call(
                    ws, "Page.captureScreenshot", {"format": "png"}, cid
                )
                screenshot_data = shot.get("result", {}).get("data")
                if not screenshot_data:
                    raise RuntimeError("application_submit_screenshot_missing")
                final_state = state
                break
            if not policy_checked:
                proposal_text = str(state.get("proposal_text") or "")
                # A5-(1): the market is read HERE, from the brief this submit is
                # already required to load, and from the form as it stands one
                # instant before the irreversible click. Not from the model's later
                # report, which is the arrangement that produced bid_jpy on 0 of 311
                # rows, and not from a second page load, which would cost a
                # navigation for numbers already in hand.
                market = parse_market(
                    opportunity_brief,
                    now=time.time(),
                    bid_jpy=state.get("bid_jpy"),
                )
                verdict = evaluate_application(
                    opportunity_brief,
                    proposal_text,
                    form_text=str(state.get("body") or ""),
                    market=market,
                )
                _write_eligibility_evidence(
                    evidence_path,
                    request_id=request_id,
                    bucket="single",
                    opportunity_url=opportunity_url,
                    brief_text=opportunity_brief,
                    proposal_text=proposal_text,
                    verdict=verdict,
                    market=market,
                )
                policy_checked = True
                if verdict.get("allowed") is not True:
                    reasons = verdict.get("reason_codes")
                    reason = (
                        ",".join(str(item) for item in reasons)
                        if isinstance(reasons, list)
                        else "unknown"
                    )
                    raise RuntimeError(
                        f"application_eligibility_rejected:{reason}"
                    )
            if state.get("validation_error") is True:
                raise RuntimeError("application_form_validation_failed")
            button = state.get("button")
            if not isinstance(button, dict):
                break
            if button.get("kind") == "confirm" and state.get("form_filled") is not True:
                raise RuntimeError("application_form_incomplete")
            try:
                x = float(button["x"])
                y = float(button["y"])
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError("application_submit_button_invalid") from error
            if button.get("kind") in {"apply", "modal_apply"}:
                _write_submit_intent(
                    evidence_path,
                    request_id=request_id,
                    bucket="single",
                    url=f"https://coconala.com/requests/{request_id}",
                    title=None,
                    state="prepared",
                )
            await _mouse_click(ws, x, y, cid)
        if wait_seconds:
            await asyncio.sleep(wait_seconds)

    if final_state is None:
        raise RuntimeError("submission_not_verified")
    evidence = {
        "request_id": request_id,
        "url": str(final_state["url"]),
        "title": str(final_state.get("title") or ""),
        "submit_verified": True,
        "applied_page_verified": True,
        "confirmation_text": "応募しました",
    }
    _atomic_write(screenshot_path, base64.b64decode(screenshot_data))
    _atomic_write(
        evidence_path,
        (
            json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        ).encode("utf-8"),
    )
    _write_submit_intent(
        evidence_path,
        request_id=request_id,
        bucket="single",
        url=f"https://coconala.com/requests/{request_id}",
        title=None,
        state="confirmed",
    )
    return evidence


async def submit_application(
    ws_url: str,
    request_id: str,
    screenshot_path: Path,
    evidence_path: Path,
    *,
    wait_seconds: float = 2.5,
    opportunity_brief: str | None = None,
) -> dict[str, object]:
    """Serialize a submit against context release for this leased target."""
    with _target_operation_lock(ws_url):
        return await _submit_application_locked(
            ws_url,
            request_id,
            screenshot_path,
            evidence_path,
            wait_seconds=wait_seconds,
            opportunity_brief=opportunity_brief,
        )


def _open_application_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--screenshot", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(open_application_form(
            args.ws,
            args.request_id,
            args.screenshot,
            args.evidence,
        ))
    except Exception as error:
        print(json.dumps({
            "ok": False,
            "error": f"{type(error).__name__}:{error}",
        }, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, separators=(",", ":")))
    return 0


def _submit_application_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--screenshot", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(submit_application(
            args.ws,
            args.request_id,
            args.screenshot,
            args.evidence,
        ))
    except Exception as error:
        print(json.dumps({
            "ok": False,
            "error": f"{type(error).__name__}:{error}",
        }, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, separators=(",", ":")))
    return 0


def _open_retainer_application_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--screenshot", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(open_retainer_application_form(
            args.ws,
            args.request_id,
            args.screenshot,
            args.evidence,
        ))
    except Exception as error:
        print(json.dumps({
            "ok": False,
            "error": f"{type(error).__name__}:{error}",
        }, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, separators=(",", ":")))
    return 0


def _observe_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--screenshot", required=True, type=Path)
    parser.add_argument("--dom", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(observe_target(
            args.ws,
            args.url,
            args.screenshot,
            args.dom,
        ))
    except Exception as error:
        print(json.dumps({
            "ok": False,
            "error": f"{type(error).__name__}:{error}",
        }, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, separators=(",", ":")))
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in {
        "open-application", "submit-application",
        "open-retainer-application", "submit-retainer-application",
    }:
        # LIVE-1: these former model-facing commands split form-open/fill/submit
        # across an untrusted process.  They stay fail-closed for stale callers, but
        # no longer parse arguments or connect to a websocket before refusing.
        print(json.dumps({
            "ok": False,
            "error": "parent_owned_application_boundary",
        }, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 2
    if len(sys.argv) > 1 and sys.argv[1] == "probe-session":
        parser = argparse.ArgumentParser()
        parser.add_argument("--url", required=True)
        args = parser.parse_args(sys.argv[2:])
        try:
            print(json.dumps(
                asyncio.run(probe_session(args.url)),
                ensure_ascii=False,
                separators=(",", ":"),
            ))
        except Exception as error:
            print(json.dumps({
                "ok": False,
                "logged_out": False,
                "error": f"{type(error).__name__}:{error}",
            }, ensure_ascii=False, separators=(",", ":")))
            return 1
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "observe":
        return _observe_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] in {"-h", "--help"}:
        print(
            "usage: cdp_nav_snapshot.py "
            "{open-retainer-application,submit-retainer-application,observe,probe-session} [options]\n"
            "       cdp_nav_snapshot.py "
            "<pass_id> <seq> <label> <url> [action_note]\n\n"
            "commands:\n"
            "  application commands are parent-owned; direct invocation is refused\n"
            "  observe           navigate one leased target and capture evidence\n"
            "  probe-session     verify an authenticated session in a hidden target"
        )
        return 0
    if len(sys.argv) < 5:
        print("ERROR:usage: cdp_nav_snapshot.py <pass_id> <seq> <label> <url> [action_note]")
        return 0
    pass_id, seq, label, url = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    action = sys.argv[5] if len(sys.argv) > 5 else ""
    try:
        print(asyncio.run(navigate_and_snapshot(pass_id, seq, label, url, action)))
    except Exception as e:
        # capture must never abort a verification run
        print(f"ERROR:{type(e).__name__}:{e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
