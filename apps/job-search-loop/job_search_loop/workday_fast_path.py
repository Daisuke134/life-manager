"""Deterministic Workday preflight for the resident job-search browser owner.

Workday renders an empty step shell before the My Information controls arrive.
This lane advances one visible provider surface at a time and only fills values
grounded in the private profile.  It never force-clicks hidden Workday controls,
guesses unknown required answers, or claims a slot before a final form snapshot.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from .ashby_fast_path import (
    _body_text,
    _context,
    _field_metadata,
    _label,
    _safe_text,
    _write_json,
)
from .ats import evaluate_snapshot
from .ledger import Ledger
from .resume_routing import select_resume
from .state import canonical_url
from .workday_credentials import WorkdayCredentialError, load_credentials


CONTROL_SELECTOR = (
    "input, textarea, select, button, a, "
    "[role='combobox'], [role='button'], [role='radio'], [role='checkbox']"
)
CONFIRMATION_RE = re.compile(
    r"thank you|thanks for applying|application received|successfully submitted|"
    r"応募情報が送信|応募を受け付け",
    re.IGNORECASE,
)
ACTION_LABELS = {
    "Apply": ("Apply", "応募"),
    "Apply Manually": ("Apply Manually", "手動で応募"),
    "Save and Continue": ("Save and Continue", "保存して次へ"),
    "Submit": ("Submit", "送信"),
    "Sign In": ("Sign In", "サインイン"),
}


def _manual_completed_urls(path: Path) -> set[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    rows = value.get("urls") if isinstance(value, dict) else []
    return {canonical_url(str(row)) for row in rows if isinstance(row, str)}


async def _snapshot(page: Any) -> dict[str, Any]:
    frames: list[dict[str, Any]] = []
    script = """
    elements => elements.map(element => {
      const labels = element.labels
        ? Array.from(element.labels).map(label => (label.innerText || '').trim())
        : [];
      return {
        tag: element.tagName.toLowerCase(),
        type: element.getAttribute('type'),
        role: element.getAttribute('role'),
        automation_id: element.getAttribute('data-automation-id'),
        label: (element.getAttribute('aria-label') || labels.join(' | ')).trim(),
        name: element.getAttribute('name'),
        text: (element.innerText || '').trim()
      };
    })
    """
    for frame in page.frames:
        try:
            controls = await frame.locator(CONTROL_SELECTOR).evaluate_all(script)
        except Exception:
            controls = []
        frames.append(
            {
                "url": _safe_text(frame.url, 1000),
                "controls": [
                    {
                        key: _safe_text(control.get(key))
                        for key in (
                            "tag",
                            "type",
                            "role",
                            "automation_id",
                            "label",
                            "name",
                            "text",
                        )
                    }
                    for control in controls
                    if isinstance(control, dict)
                ],
            }
        )
    return {
        "version": 1,
        "url": page.url,
        "navigation_committed": True,
        "frames": frames,
    }


def _signature(snapshot: dict[str, Any]) -> str:
    controls = [
        control
        for frame in snapshot.get("frames") or []
        for control in frame.get("controls") or []
        if str(control.get("role") or "").casefold() not in {"alert", "status"}
    ]
    return hashlib.sha256(
        json.dumps(controls, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _error_fields(snapshot: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for frame in snapshot.get("frames") or []:
        for control in frame.get("controls") or []:
            text = str(control.get("text") or "").strip()
            if text.casefold().startswith("error-"):
                fields.append(_safe_text(text[6:].strip()))
    return sorted(set(fields))


async def _wait_surface(page: Any, *, timeout_ms: int = 20_000) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_ms / 1000
    last_snapshot = await _snapshot(page)
    last_evaluation = evaluate_snapshot(last_snapshot)
    while time.monotonic() < deadline:
        if last_evaluation.get("ready"):
            return last_snapshot, last_evaluation
        await page.wait_for_timeout(500)
        last_snapshot = await _snapshot(page)
        last_evaluation = evaluate_snapshot(last_snapshot)
    return last_snapshot, last_evaluation


async def _visible_exact(page: Any, role: str, name: str) -> Any | None:
    locator = page.get_by_role(role, name=name, exact=True)
    visible: list[Any] = []
    for index in range(await locator.count()):
        candidate = locator.nth(index)
        try:
            if await candidate.is_visible():
                visible.append(candidate)
        except Exception:
            continue
    return visible[0] if len(visible) == 1 else None


def _field_element(page: Any, item: dict[str, Any], locator: Any | None = None) -> Any:
    item_id = str(item.get("id") or "")
    if item_id:
        return page.locator(f"#{item_id}")
    name = str(item.get("name") or "")
    if name:
        return page.locator(f"[name={json.dumps(name)}]").first
    labels = [str(value).strip() for value in item.get("labels") or [] if str(value).strip()]
    if labels:
        return page.get_by_label(labels[0], exact=True).first
    if locator is None:
        raise ValueError("field metadata has no stable locator")
    return locator.nth(int(item["index"]))


async def _click_surface(page: Any, name: str) -> bool:
    # Workday sometimes exposes an <a role="button"> and sometimes a visible
    # click_filter overlay.  Both are user-facing and must be ordinary clicks.
    for label in ACTION_LABELS.get(name, (name,)):
        overlay = page.locator(
            f"[data-automation-id='click_filter'][aria-label='{label}']"
        )
        visible_overlay: list[Any] = []
        for index in range(await overlay.count()):
            candidate = overlay.nth(index)
            if await candidate.is_visible():
                visible_overlay.append(candidate)
        if len(visible_overlay) == 1:
            await visible_overlay[0].click(timeout=10_000, no_wait_after=True)
            return True
        button = await _visible_exact(page, "button", label)
        if button is None:
            button = await _visible_exact(page, "link", label)
        if button is not None:
            await button.click(timeout=10_000, no_wait_after=True)
            return True
    return False


def _profile_values(profile: dict[str, Any]) -> dict[str, str]:
    candidate = profile.get("candidate") or {}
    romaji = candidate.get("name_romaji_parts") or {}
    kanji = candidate.get("name_ja_parts") or {}
    address = candidate.get("mailing_address") or {}
    address_ja = candidate.get("mailing_address_ja") or {}
    values = {
        "legalName--lastNameLocal": str(kanji.get("family") or ""),
        "legalName--firstNameLocal": str(kanji.get("given") or ""),
        "legalName--lastName": str(romaji.get("family") or ""),
        "legalName--firstName": str(romaji.get("given") or ""),
        "postalCode": str(address.get("postal_code") or ""),
        "cityLocal": str(address_ja.get("municipality") or ""),
        "addressLine1Local": str(address_ja.get("street_building") or ""),
        "city": str(address.get("city") or ""),
        "addressLine1": str(address.get("address_line_1") or ""),
        "phoneNumber": str(candidate.get("phone") or ""),
        "countryRegion": str(address.get("state_region") or address_ja.get("prefecture") or ""),
    }
    return {key: value for key, value in values.items() if value}


def _known_value(item: dict[str, Any], profile: dict[str, Any], values: dict[str, str]) -> str | None:
    item_id = str(item.get("id") or "")
    name = str(item.get("name") or "")
    labels = _label(item)
    context = _context(item)
    if item_id in values:
        return values[item_id]
    if name in values:
        return values[name]
    if item_id == "source--source":
        return "Job Boards"
    candidate = profile.get("candidate") or {}
    if "email" in context:
        value = candidate.get("application_email")
        return str(value) if value else None
    if "linkedin" in context:
        value = candidate.get("linkedin_url")
        return str(value) if value else None
    if "github" in context:
        value = candidate.get("github_url")
        return str(value) if value else None
    if "work authorization" in context and any(
        str(item.get("id") or "") == "legal_japan_work_authorization_20260730"
        for item in profile.get("facts") or []
        if isinstance(item, dict)
    ):
        return "Yes"
    if "sponsorship" in context and any(
        str(item.get("id") or "") == "legal_no_japan_sponsorship_required_20260806"
        for item in profile.get("facts") or []
        if isinstance(item, dict)
    ):
        return "No"
    if "start date" in context or "when can you start" in context:
        value = candidate.get("start_date")
        return str(value) if value else None
    if "how did you hear" in context or "how did you hear" in labels:
        return "Job Boards"
    if "previously worked" in context or "former worker" in context:
        return "No"
    if "country phone code" in context:
        return "+81"
    return None


def _is_unknown_required(item: dict[str, Any], value: str | None) -> bool:
    if str(item.get("id") or "") == "source--source":
        return False
    if not item.get("required"):
        return False
    if str(item.get("name") or "") == "candidateIsPreviousWorker":
        return value is None
    context = _context(item)
    if "previously worked" in context or "former worker" in context:
        return value is None
    return value is None or not value.strip()


async def _choose(page: Any, locator: Any, value: str) -> bool:
    tag = (await locator.evaluate("node => node.tagName.toLowerCase()"))
    if tag == "select":
        try:
            await locator.select_option(label=value)
            return True
        except Exception:
            return False
    await locator.click(timeout=10_000)
    if tag == "input":
        await locator.fill(value)
        prompt_option = page.locator(
            "[data-automation-id='promptOption'][data-automation-label="
            f"{json.dumps(value)}]"
        )
        for _ in range(10):
            if await prompt_option.count() and await prompt_option.first.is_visible():
                break
            await page.wait_for_timeout(500)
        else:
            return False
        await locator.press("ArrowDown")
        await locator.press("Enter")
        return True
    prompt_option = page.locator(
        f"[data-automation-id='promptOption'][data-automation-label='{value}']"
    )
    if await prompt_option.count():
        await prompt_option.first.click(timeout=10_000)
        return True
    for _ in range(10):
        prompt_option = page.locator(
            f"[data-automation-id='promptOption'][data-automation-label='{value}']"
        )
        if await prompt_option.count():
            await prompt_option.first.click(timeout=10_000)
            return True
        option = page.get_by_role("option", name=value, exact=True)
        if await option.count() == 0:
            option = page.locator("[role='option']").filter(has_text=value)
        if await option.count():
            await option.first.click(timeout=10_000)
            return True
        await page.wait_for_timeout(500)
    text = page.get_by_text(value, exact=True)
    if await text.count():
        await text.first.click(timeout=10_000)
        return True
    return False


async def _fill_step(
    page: Any,
    profile: dict[str, Any],
    resume_path: Path,
) -> list[str]:
    fields = sorted(
        await _field_metadata(page),
        key=lambda item: "how did you hear" in _context(item),
    )
    values = _profile_values(profile)
    locator = page.locator(
        "input, textarea, select, [role='combobox'], [role='radio'], [role='checkbox']"
    )
    blockers: list[str] = []
    for item in fields:
        element = _field_element(page, item, locator)
        kind = str(item.get("type") or "").casefold()
        role = str(item.get("role") or "").casefold()
        item_id = str(item.get("id") or "")
        label = _safe_text(_label(item) or item.get("context") or item_id)
        if kind == "hidden" or item_id == "beecatcher" or str(item.get("name") or "") == "website":
            continue
        if kind == "file":
            if "resume" in _context(item) or "cv" in _context(item):
                await element.set_input_files(str(resume_path))
            elif item.get("required"):
                blockers.append(label)
            continue
        value = _known_value(item, profile, values)
        if kind in {"radio", "checkbox"} or role in {"radio", "checkbox"}:
            # Optional demographics and unknown prior-employer answers remain untouched.
            if _is_unknown_required(item, value):
                blockers.append(label)
            elif value and kind == "radio" and _label(item) == value.casefold():
                control_id = await element.get_attribute("id")
                radio_label = (
                    page.locator(f"label[for='{control_id}']")
                    if control_id
                    else page.get_by_text(value, exact=True)
                )
                if await radio_label.count() and await radio_label.first.is_visible():
                    if control_id:
                        await page.wait_for_function(
                            """() => ![...document.querySelectorAll('[aria-busy="true"]')]
                              .some(element => element.offsetParent !== null)""",
                            timeout=15_000,
                        )
                    custom_radio = radio_label.first.locator(
                        "xpath=preceding-sibling::div[1]"
                    )
                    if await custom_radio.count() and await custom_radio.first.is_visible():
                        await custom_radio.first.click(timeout=10_000)
                    else:
                        await radio_label.first.click(timeout=10_000)
                else:
                    await element.check(timeout=10_000)
            continue
        if (
            kind in {"button"}
            or role == "combobox"
            or "how did you hear" in _context(item)
            or item_id in {"source--source", "address--countryRegion", "country--country"}
        ):
            if value and not await _choose(page, element, value):
                if item.get("required"):
                    blockers.append(label)
            elif _is_unknown_required(item, value):
                blockers.append(label)
            continue
        if value:
            await element.fill(value)
        elif _is_unknown_required(item, value):
            blockers.append(label)
    return sorted(set(blockers))


async def _confirmation(page: Any) -> bool:
    for _ in range(20):
        try:
            body = await page.locator("body").inner_text(timeout=1_000)
        except Exception:
            body = ""
        if CONFIRMATION_RE.search(body):
            return True
        await page.wait_for_timeout(500)
    return False


async def _login(page: Any, job_url: str, store_path: Path) -> str | None:
    snapshot, evaluation = await _wait_surface(page)
    surface = evaluation.get("surface")
    if surface == "workday_account_create":
        # A fresh dedicated profile can land on Workday's account-creation
        # shell even when the tenant already has a private account.  Switch to
        # the explicit form link, never provision a second account.
        sign_in_link = page.locator("[data-automation-id='signInLink']")
        visible_links: list[Any] = []
        for index in range(await sign_in_link.count()):
            candidate = sign_in_link.nth(index)
            if await candidate.is_visible():
                visible_links.append(candidate)
        if len(visible_links) != 1:
            return "workday_account_sign_in_link_missing"
        await visible_links[0].click(timeout=10_000)
        await page.wait_for_timeout(1_000)
        snapshot, evaluation = await _wait_surface(page)
        surface = evaluation.get("surface")
    if surface == "workday_sign_in_entry":
        if not await _click_surface(page, "Sign In"):
            # A transient Workday auth-entry shell can win the first snapshot
            # while the already-authenticated application form is mounting.
            # Give that same page a bounded chance to settle before declaring
            # a missing control; never click a hidden or stale element.
            for _ in range(20):
                await page.wait_for_timeout(500)
                snapshot, evaluation = await _wait_surface(page, timeout_ms=500)
                if evaluation.get("surface") != "workday_sign_in_entry":
                    surface = evaluation.get("surface")
                    break
            else:
                return "workday_sign_in_entry_control_missing"
        else:
            await page.wait_for_timeout(1_000)
            snapshot, evaluation = await _wait_surface(page)
            surface = evaluation.get("surface")
    if surface != "workday_sign_in":
        return None
    try:
        credentials = load_credentials(store_path, job_url)
    except WorkdayCredentialError:
        return "workday_credentials_unavailable"
    email = page.locator("input[name='email'], input[aria-label*='Email'], input").first
    password = page.locator("input[type='password']").first
    if await email.count() == 0 or await password.count() == 0:
        return "workday_sign_in_fields_missing"
    await email.fill(credentials["application_email"])
    await password.fill(credentials["password"])
    await page.wait_for_timeout(6_500)
    if not await _click_surface(page, "Sign In"):
        return "workday_sign_in_control_missing"
    await page.wait_for_timeout(2_000)
    return None


async def _process_one(
    page: Any,
    row: dict[str, Any],
    *,
    profile: dict[str, Any],
    materials_root: Path,
    ledger: Ledger,
    evidence_dir: Path,
    japan_day: str,
    store_path: Path,
) -> dict[str, Any]:
    application_id = str(row["application_id"])
    url = canonical_url(str(row["canonical_url"]))
    if "myworkdayjobs.com" not in url:
        return {"application_id": application_id, "status": "skipped_non_workday"}
    await page.goto(url, wait_until="commit", timeout=45_000)
    snapshot, evaluation = await _wait_surface(page)
    if evaluation.get("surface") == "workday_job":
        if not await _click_surface(page, "Apply"):
            return {"application_id": application_id, "status": "blocked", "blocker": "workday_apply_control_missing"}
        snapshot, evaluation = await _wait_surface(page)
    if evaluation.get("surface") == "workday_apply_choice":
        if not await _click_surface(page, "Apply Manually"):
            return {"application_id": application_id, "status": "blocked", "blocker": "workday_manual_control_missing"}
        # The step shell is intentionally not enough; wait for actual profile controls.
        await page.wait_for_timeout(6_500)
        snapshot, evaluation = await _wait_surface(page)
    login_blocker = await _login(page, url, store_path)
    if login_blocker:
        return {"application_id": application_id, "company": row["company"], "title": row["title"], "status": "blocked", "blocker": login_blocker}
    snapshot, evaluation = await _wait_surface(page)
    if evaluation.get("surface") not in {"workday_application_step", "workday_application", "workday_review"}:
        return {"application_id": application_id, "company": row["company"], "title": row["title"], "status": "blocked", "blocker": ",".join(evaluation.get("blockers") or ["application_surface_not_found"])}
    posting = await _body_text(page)
    routed = select_resume(posting_text=posting, role_family="technical_business", materials_root=materials_root)
    for step in range(1, 9):
        snapshot = await _snapshot(page)
        evaluation = evaluate_snapshot(snapshot)
        snapshot_path = evidence_dir / f"workday-ats-{application_id[:16]}-step-{step:02d}.json"
        _write_json(snapshot_path, snapshot)
        if evaluation.get("surface") in {"workday_application", "workday_review"} and evaluation.get("claim_ready"):
            snapshot_sha256 = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
            payload_hash = hashlib.sha256(
                json.dumps({"canonical_url": url, "resume_sha256": routed["resume_sha256"]}, sort_keys=True).encode("utf-8")
            ).hexdigest()
            intent = ledger.claim_submission(
                application_id,
                japan_day,
                payload_hash,
                resume_path=Path(routed["resume_path"]),
                resume_sha256=routed["resume_sha256"],
                ats_snapshot_path=snapshot_path,
                ats_snapshot_sha256=snapshot_sha256,
            )
            if intent is None:
                return {"application_id": application_id, "status": "already_claimed"}
            await page.wait_for_timeout(6_500)
            if not await _click_surface(page, "Submit"):
                ledger.complete_submission(intent.intent_id, intent.fence, "not_submitted")
                return {"application_id": application_id, "company": row["company"], "title": row["title"], "status": "not_submitted", "blocker": "workday_submit_control_missing"}
            outcome = "submitted" if await _confirmation(page) else "submit_unknown"
            ledger.complete_submission(intent.intent_id, intent.fence, outcome)
            return {"application_id": application_id, "company": row["company"], "title": row["title"], "status": outcome, "url": url}
        if evaluation.get("surface") != "workday_application_step":
            return {"application_id": application_id, "company": row["company"], "title": row["title"], "status": "blocked", "blocker": ",".join(evaluation.get("blockers") or ["workday_step_not_ready"])}
        blockers = await _fill_step(page, profile, Path(routed["resume_path"]))
        if blockers:
            return {"application_id": application_id, "company": row["company"], "title": row["title"], "status": "blocked", "blocker": "unknown_required_field", "fields": blockers[:12], "advanced_steps": step - 1}
        previous = _signature(snapshot)
        await page.wait_for_timeout(6_500)
        if not await _click_surface(page, "Save and Continue"):
            return {"application_id": application_id, "company": row["company"], "title": row["title"], "status": "blocked", "blocker": "workday_save_and_continue_missing", "advanced_steps": step - 1}
        deadline = time.monotonic() + 20
        progressed = False
        while time.monotonic() < deadline:
            await page.wait_for_timeout(500)
            current = await _snapshot(page)
            if _signature(current) != previous:
                errors = _error_fields(current)
                if errors:
                    return {
                        "application_id": application_id,
                        "company": row["company"],
                        "title": row["title"],
                        "status": "blocked",
                        "blocker": "unknown_required_field",
                        "fields": errors[:12],
                        "advanced_steps": step - 1,
                    }
                progressed = True
                break
        if not progressed:
            return {"application_id": application_id, "company": row["company"], "title": row["title"], "status": "blocked", "blocker": "workday_save_and_continue_no_progress", "advanced_steps": step - 1}
    return {"application_id": application_id, "company": row["company"], "title": row["title"], "status": "blocked", "blocker": "workday_step_limit_reached"}


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    ledger = Ledger(args.ledger)
    exclusions = profile.get("candidate", {}).get("employer_exclusions", [])
    excluded = ledger.reject_excluded_employers(frozenset(str(value) for value in exclusions) if isinstance(exclusions, list) else None)
    pending = ledger.pending_materials_ready_applications()
    retryable = ledger.retryable_applications()
    manual_completed = _manual_completed_urls(args.manual_completed_state)
    rows_by_id = {
        str(row["application_id"]): row
        for row in [*pending, *retryable]
        if "myworkdayjobs.com" in str(row["canonical_url"])
        and canonical_url(str(row["canonical_url"])) not in manual_completed
    }
    rows = list(rows_by_id.values())
    if args.max_jobs > 0:
        rows = rows[:args.max_jobs]
    result: dict[str, Any] = {"status": "no_work" if not rows else "completed", "processed": [], "excluded": excluded, "owner": "ai.anicca.job-search-daily"}
    if not rows:
        _write_json(args.output, result)
        ledger.close()
        return result
    pw = await async_playwright().start()
    page = None
    try:
        browser = await pw.chromium.connect_over_cdp(args.endpoint)
        if not browser.contexts:
            raise RuntimeError("shared CDP browser has no context")
        page = await browser.contexts[0].new_page()
        for row in rows:
            try:
                result["processed"].append(await _process_one(page, row, profile=profile, materials_root=args.materials_root, ledger=ledger, evidence_dir=args.evidence_dir, japan_day=args.japan_day, store_path=args.store_path))
            except Exception as error:
                result["processed"].append({"application_id": row["application_id"], "company": row["company"], "title": row["title"], "status": "blocked", "blocker": "fast_path_exception", "error_type": type(error).__name__, "error": _safe_text(str(error), 500)})
    finally:
        if page is not None:
            await page.close()
        await pw.stop()
        ledger.close()
    _write_json(args.output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://localhost:9222")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--materials-root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--store-path", type=Path, required=True)
    parser.add_argument("--japan-day", required=True)
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument(
        "--manual-completed-state",
        type=Path,
        default=Path.home() / ".local/state/anicca/job-search/workday-manual-completed.json",
    )
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    print(json.dumps(asyncio.run(_run(args)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
