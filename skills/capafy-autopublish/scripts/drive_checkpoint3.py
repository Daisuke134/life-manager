#!/usr/bin/env python3
"""Drive Capafy CP3 (Submit for Review) through a strict raw page-CDP flow."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from urllib.parse import parse_qsl, urlsplit

from drive_checkpoint2 import (
    _RawPage,
    _open_cp2_target,
    _bounded_page_call,
    _bounded_page_evaluate,
    _detect_cdp,
    _is_capafy_target_url,
    _raw_fill_workspace_conversation_fields,
    _validate_cdp_base,
    _open_responsive_page,
    _single_redirect_location,
    _target_url_key,
    _validate_ws_url,
)


CP3_HOST = "capafy.ai"
CP3_PATH = "/developer/createAgent"
CP3_NAV_TIMEOUT_S = 10.0
CP3_HYDRATE_TIMEOUT_S = 30.0
CP3_POLL_S = 0.25


def _is_review_url(url: str) -> bool:
    parts = urlsplit(str(url or ""))
    if (
        parts.scheme != "https"
        or parts.netloc.lower() != CP3_HOST
        or parts.path != CP3_PATH
        or parts.fragment
    ):
        return False
    try:
        query = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    keys = [key for key, _value in query]
    if len(set(keys)) != len(keys):
        return False
    values = dict(query)
    if set(keys) == {"page", "source", "token"}:
        token = values.get("token", "")
        return (
            len(query) == 3
            and values.get("page") == "review"
            and values.get("source") == "temp-link"
            and re.fullmatch(r"[0-9]+", token) is not None
        )
    if set(keys) == {"draftKey", "page"}:
        draft_key = values.get("draftKey", "")
        return (
            len(query) == 2
            and values.get("page") == "review"
            and bool(draft_key.strip())
        )
    return False


def _validate_review_url(url: str) -> str:
    if not _is_review_url(url):
        raise RuntimeError("CP3 URL must be exact HTTPS Capafy createAgent page=review")
    return str(url)


def _resolve_review_url(raw_url: str) -> str:
    raw_url = str(raw_url or "").strip()
    if _is_review_url(raw_url):
        return raw_url
    parts = urlsplit(raw_url)
    if (
        parts.scheme != "https"
        or parts.netloc.lower() != "api.capafy.ai"
        or not re.fullmatch(r"/R[0-9]+", parts.path)
        or parts.query
        or parts.fragment
    ):
        raise RuntimeError("CP3 short URL must be exactly https://api.capafy.ai/R<digits>")
    locations = _single_redirect_location(raw_url, "HEAD")
    if not locations:
        locations = _single_redirect_location(raw_url, "GET")
    if len(locations) != 1:
        raise RuntimeError("CP3 short URL must return exactly one redirect Location")
    return _validate_review_url(locations[0])


def _candidate_page_targets(cdp_base: str):
    cdp_base = _validate_cdp_base(cdp_base)
    import json

    with urllib.request.urlopen(f"{cdp_base}/json/list", timeout=8) as response:
        targets = json.loads(response.read())
    candidates = []
    for target in reversed(targets if isinstance(targets, list) else []):
        if not isinstance(target, dict) or target.get("type") != "page":
            continue
        if not _is_capafy_target_url(target.get("url")):
            continue
        try:
            _validate_ws_url(target.get("webSocketDebuggerUrl"))
        except RuntimeError:
            continue
        candidates.append(target)
    if not candidates:
        raise RuntimeError("no existing Capafy createAgent page target")
    return candidates


def _navigate(page: _RawPage, url: str) -> None:
    _validate_review_url(url)
    expected = _target_url_key(url)
    deadline = time.monotonic() + CP3_NAV_TIMEOUT_S
    result = _bounded_page_call(page, "Page.navigate", {"url": url}, deadline)
    error_text = str(result.get("errorText") or "").strip()
    if error_text:
        raise RuntimeError(f"CP3 Page.navigate failed: {error_text}")
    while time.monotonic() < deadline:
        state = _bounded_page_evaluate(page, "({ready:document.readyState,href:location.href})", deadline)
        if isinstance(state, dict) and state.get("ready") in {"interactive", "complete"}:
            if _target_url_key(str(state.get("href") or "")) != expected:
                raise RuntimeError("CP3 navigation reached the wrong exact target")
            return
        time.sleep(CP3_POLL_S)
    raise RuntimeError("CP3 navigation did not become ready before deadline")


SUBMIT_STATE_JS = """(() => {
  const visible = b => !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length);
  const all = [...document.querySelectorAll('button')].filter(b => visible(b) && b.classList.contains('finalReviewSubmitButton') && ['審査に提出','Submit for Review'].includes((b.textContent || '').trim()));
  const enabled = all.filter(b => !b.disabled);
  const confirms = [...document.querySelectorAll('button')].filter(b => visible(b) && ['提出を確認','Confirm Submit'].includes((b.textContent || '').trim()));
  const drafts = [...document.querySelectorAll('button')].filter(b => visible(b) && b.classList.contains('finalReviewSubmitButton') && ['下書き保存','Save Draft'].includes((b.textContent || '').trim()));
  return {count: all.length, enabled: enabled.length, disabled: all.filter(b => b.disabled).length, confirms: confirms.length, drafts: drafts.length};
})()"""


# Editing the version-update fields flips finalReviewSubmitButton to 下書き保存
# until the draft is saved; only then does it read 審査に提出 again (TikTok
# Script Pro 2844813315, 2026-09-29 14:50 JST: "did not hydrate before deadline").
DRAFT_SAVE_CLICK_JS = """(() => {
  const visible = b => !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length);
  const xs = [...document.querySelectorAll('button')].filter(b => visible(b) && b.classList.contains('finalReviewSubmitButton') && ['下書き保存','Save Draft'].includes((b.textContent || '').trim()) && !b.disabled);
  if (xs.length !== 1) return {ok:false, count:xs.length};
  xs[0].click();
  return {ok:true};
})()"""


SUBMIT_CLICK_JS = """(() => {
  const visible = b => !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length);
  const xs = [...document.querySelectorAll('button')].filter(b => visible(b) && b.classList.contains('finalReviewSubmitButton') && ['審査に提出','Submit for Review'].includes((b.textContent || '').trim()));
  if (xs.length !== 1 || xs[0].disabled) return {ok:false, reason:'submit-not-unique-or-disabled', count:xs.length};
  xs[0].click();
  return {ok:true};
})()"""


CONFIRM_CLICK_JS = """(() => {
  const visible = b => !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length);
  const xs = [...document.querySelectorAll('button')].filter(b => visible(b) && ['提出を確認','Confirm Submit'].includes((b.textContent || '').trim()));
  if (xs.length !== 1 || xs[0].disabled) return {ok:false, reason:'confirm-not-unique-or-disabled', count:xs.length};
  xs[0].click();
  return {ok:true};
})()"""


_VERSION_TAB_CLICK = """(() => {
  const xs = [...document.querySelectorAll('button,[role=tab]')].filter(e => ['バージョン','Version'].includes((e.textContent || '').trim()));
  if (xs.length !== 1) return {ok:false, count:xs.length};
  xs[0].click();
  return {ok:true};
})()"""


def _fill_version_update_if_required(page: _RawPage, update_info: str) -> None:
    """Populate the one required version-history textarea when the page has it."""
    deadline = time.monotonic() + CP3_HYDRATE_TIMEOUT_S
    state = None
    version_tab_clicked = False
    while time.monotonic() < deadline:
        state = page.evaluate("""(() => {
          const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
          const xs = [...document.querySelectorAll('textarea')].filter(e => visible(e) && /変更内容|変更履歴|changes/i.test(`${e.placeholder || ''} ${e.getAttribute('aria-label') || ''}`));
          const submit = [...document.querySelectorAll('button')].some(b => visible(b) && ['審査に提出','Submit for Review'].includes((b.textContent || '').trim()));
          if (xs.length === 0) return {ok:true, hydrated:submit, required:false};
          if (xs.length !== 1) return {ok:false, count:xs.length};
          const x=xs[0]; x.scrollIntoView({block:'center'}); x.focus(); x.select();
          return {ok:true, hydrated:true, required:true, empty:!(x.value || '').trim()};
        })()""")
        if isinstance(state, dict) and state.get("hydrated"):
            break
        if not version_tab_clicked:
            # An update version's review page opens on 基本情報; the change-note
            # textarea (and then 審査に提出) only appears under バージョン
            # (live, Hook Lab v1.0.3, 2026-09-28).
            version_tab_clicked = True
            clicked = page.evaluate(_VERSION_TAB_CLICK)
            if isinstance(clicked, dict) and clicked.get("ok"):
                time.sleep(1)
                continue
        time.sleep(CP3_POLL_S)
    if not isinstance(state, dict) or not state.get("ok"):
        raise RuntimeError(f"CP3 version-update field is ambiguous: {state}")
    if not state.get("hydrated"):
        raise RuntimeError("CP3 version form did not hydrate before deadline")
    if not state.get("required") or not state.get("empty"):
        return
    update_info = str(update_info or "").strip()
    if not update_info:
        raise RuntimeError("CP3 version update description is required")
    inserted = page.evaluate("""(() => {
      const value=%s;
      const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
      const xs = [...document.querySelectorAll('textarea')].filter(e => visible(e) && /変更内容|変更履歴|changes/i.test(`${e.placeholder || ''} ${e.getAttribute('aria-label') || ''}`));
      if (xs.length !== 1) return {ok:false,count:xs.length};
      const x=xs[0];
      const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;
      setter.call(x,value);
      x.dispatchEvent(new InputEvent('input',{bubbles:true,composed:true,inputType:'insertText',data:value}));
      x.dispatchEvent(new Event('change',{bubbles:true}));
      return {ok:true,value:x.value};
    })()""" % json.dumps(update_info))
    if not isinstance(inserted, dict) or not inserted.get("ok") or inserted.get("value") != update_info:
        raise RuntimeError(f"CP3 version update description did not persist: {inserted}")
    time.sleep(0.5)


def _wait_and_submit(page: _RawPage, update_info: str = "") -> None:
    # Runs FIRST (2026-09-28 12:4xZ): a new v1.0.0 page shows neither the
    # change-note textarea nor 審査に提出 until these fields and the DPA box are
    # set, so the version-form wait below timed out before this ever ran.
    # A resumed draft's Agent ワークスペース tab can still be missing its
    # welcome-message/input-placeholder/test-case/AI-service-provider fields
    # and its required DPA-agreement checkbox even after CP2 ran (2026-09-28,
    # 6273179459 / 9466718786): checking that checkbox is what makes
    # finalReviewSubmitButton switch from 下書きを保存 to 審査に提出 -- with
    # no separate "save the completed draft" action surviving a reload, so
    # this MUST run in CP3's own page session, immediately before the submit
    # click below, not in a separate CP2 process/navigation. Best-effort: a
    # fresh CP1-flow draft already has every field filled (a no-op here), and
    # a missing/unreadable LISTING must never block a submit that would have
    # otherwise hydrated on its own.
    listing_path = os.environ.get("CAPAFY_LISTING_PATH", "").strip()
    if listing_path:
        try:
            _raw_fill_workspace_conversation_fields(page, listing_path)
        except Exception as workspace_error:
            print(f"CP3 workspace-field fix: best-effort, did not complete ({workspace_error})")

    _fill_version_update_if_required(page, update_info)

    deadline = time.monotonic() + CP3_HYDRATE_TIMEOUT_S
    draft_saved = False
    while time.monotonic() < deadline:
        state = _bounded_page_evaluate(page, SUBMIT_STATE_JS, deadline)
        if not isinstance(state, dict):
            raise RuntimeError("CP3 submit state unavailable")
        if state.get("count", 0) == 0 and state.get("drafts") == 1 and not draft_saved:
            saved = _bounded_page_evaluate(page, DRAFT_SAVE_CLICK_JS, deadline)
            draft_saved = isinstance(saved, dict) and bool(saved.get("ok"))
            print(f"CP3 saved pending draft edits before submit: {draft_saved}")
            time.sleep(CP3_POLL_S)
            continue
        if state.get("count", 0) > 1 or state.get("enabled", 0) > 1:
            raise RuntimeError(f"CP3 submit button is ambiguous: {state}")
        if state.get("count") == 1:
            if state.get("disabled"):
                raise RuntimeError("CP3 submit button is disabled")
            break
        time.sleep(CP3_POLL_S)
    else:
        raise RuntimeError("CP3 submit button did not hydrate before deadline")

    clicked = _bounded_page_evaluate(page, SUBMIT_CLICK_JS, deadline)
    if not isinstance(clicked, dict) or not clicked.get("ok"):
        raise RuntimeError(f"CP3 submit click rejected: {clicked}")

    deadline = time.monotonic() + CP3_HYDRATE_TIMEOUT_S
    confirmed_clicked = False
    while time.monotonic() < deadline:
        state = _bounded_page_evaluate(page, SUBMIT_STATE_JS, deadline)
        if not isinstance(state, dict):
            raise RuntimeError("CP3 post-submit state unavailable")
        if state.get("confirms", 0) > 1:
            raise RuntimeError(f"CP3 confirmation is ambiguous: {state}")
        if state.get("confirms") == 1 and not confirmed_clicked:
            confirmed = _bounded_page_evaluate(page, CONFIRM_CLICK_JS, deadline)
            if not isinstance(confirmed, dict) or not confirmed.get("ok"):
                raise RuntimeError(f"CP3 confirmation click rejected: {confirmed}")
            confirmed_clicked = True
        elif state.get("count") == 1 and state.get("disabled") == 1:
            return
        time.sleep(CP3_POLL_S)
    raise RuntimeError("CP3 submit did not become disabled or show a unique confirmation")


def _playwright_submit(url: str, update_info: str) -> None:
    """Submit from one owned page so stale Capafy tabs cannot be selected."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    owned_page = None
    try:
        browser = pw.chromium.connect_over_cdp(_detect_cdp(), timeout=15000)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        owned_page = context.new_page()
        owned_page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if not _is_review_url(owned_page.url):
            raise RuntimeError("CP3 owned page reached the wrong target")

        field = owned_page.locator('textarea[placeholder*="変更内容"], textarea[placeholder*="changes" i]')
        field.first.wait_for(state="visible", timeout=15000)
        if field.count() != 1:
            raise RuntimeError(f"CP3 version-update field is ambiguous ({field.count()})")
        if not field.first.input_value().strip():
            if not update_info.strip():
                raise RuntimeError("CP3 version update description is required")
            field.first.fill(update_info)

        submit = owned_page.get_by_role("button", name=re.compile(r"^(審査に提出|Submit for Review)$"))
        submit.first.wait_for(state="visible", timeout=10000)
        if submit.count() != 1 or submit.first.is_disabled():
            raise RuntimeError(f"CP3 submit button is not uniquely enabled ({submit.count()})")
        submit.first.click()
        owned_page.wait_for_timeout(1500)

        confirm = owned_page.get_by_role("button", name=re.compile(r"^(提出を確認|Confirm Submit)$"))
        if confirm.count() == 1 and confirm.first.is_visible():
            if confirm.first.is_disabled():
                raise RuntimeError("CP3 confirmation button is disabled")
            confirm.first.click()
        owned_page.wait_for_timeout(4000)
        if _is_review_url(owned_page.url) and submit.count() == 1 and not submit.first.is_disabled():
            raise RuntimeError("CP3 submit did not reach a terminal UI state")
    finally:
        if owned_page is not None:
            try:
                owned_page.close()
            except Exception:
                pass
        pw.stop()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("ERR: need CP3 url")
        return 1
    resolved = _resolve_review_url(argv[1])
    update_info = argv[2] if len(argv) > 2 else ""
    if os.environ.get("CP3_TRANSPORT", "raw").strip().lower() != "raw":
        _playwright_submit(resolved, update_info)
        print("RESULT: submitted")
        return 0
    cdp = _detect_cdp()
    try:
        targets = _candidate_page_targets(cdp)
    except RuntimeError:
        # Deterministic resumes never ran the CP1 agent, so no createAgent tab
        # may exist (2026-09-28, Hook Lab v1.0.3); open the review page itself.
        _open_cp2_target(cdp, resolved)
        targets = _candidate_page_targets(cdp)
    page = _open_responsive_page(targets)
    try:
        page.call("Page.enable")
        page.call("Page.bringToFront")
        _navigate(page, resolved)
        _wait_and_submit(page, update_info)
        print("RESULT: submitted")
        return 0
    finally:
        page.close()


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:
        print(f"ERR: CP3 failed ({type(exc).__name__}: {str(exc)[:160]})")
        sys.exit(1)
