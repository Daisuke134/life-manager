#!/usr/bin/env python3
"""Publish one Capafy catalog skill as a PromptBase "Prompt" listing.

Reuses the live "Hook Lab Win The First 3 Seconds" listing's proven shape:
item type Prompt, generation type Text, model Claude 5 Sonnet, price $4.99,
SKILL.md pasted as the (buyer-hidden) prompt template, evidence/
verified-demonstration.md split into one example input/output pair.

The PromptBase /sell wizard is a 3-step Angular SPA with NO name/id
attributes on its controls (selected by position/label text) and it
auto-saves an in-progress "Draft" the moment step 1 is submitted --
revisiting /sell resumes that draft instead of showing a blank step 1.
`_ensure_step1` walks any resumed wizard back to step 1 before filling it,
so a stale draft from a previous run never gets silently reused half-filled.

Usage (endpoint from the lease wrapper only -- never a hardcoded port):
    ENDPOINT=$(browser-guard.sh acquire interactive:dais) || exit 1
    python3 publish.py --catalog-dir skills/capafy/catalog/<slug> \\
        --endpoint "$ENDPOINT" [--confirm]
    browser-guard.sh release interactive:dais

Without --confirm this is a dry run: it fills the whole wizard, stops at the
step-3 review screen, and writes a screenshot + text dump for a human/agent
to check before any real submit. Fails closed: any unexpected form state
(missing field, wizard not on the expected step, submit control not found)
raises instead of clicking blind.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_listing import build_listing, INPUT_VARIABLE_LABEL  # noqa: E402
import ledger as ledger_mod  # noqa: E402

SELL_URL = "https://promptbase.com/sell"
PROMPTS_URL = "https://promptbase.com/account?view=prompts"


def _click_text(page, text: str, *, exact: bool = False, timeout_ms: int = 8000):
    """Click a visible-text control. PromptBase's "buttons" are plain <div>s
    with an Angular (click) binding that a synthetic DOM .click() does not
    fire reliably -- a real mouse event dispatched at the element's own
    bounding box is what actually advances the wizard (verified against the
    live app 2026-09-28)."""
    el = page.get_by_text(text, exact=exact)
    el.first.wait_for(state="visible", timeout=timeout_ms)
    el.first.scroll_into_view_if_needed()
    box = el.first.bounding_box()
    if not box:
        raise RuntimeError(f"unclickable_control:{text}")
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _current_step(page) -> str:
    head = page.inner_text("body")[:200]
    for step in ("1/3", "2/3", "3/3"):
        if step in head:
            return step
    return "unknown"


def _kick_render(page) -> None:
    """The /sell wizard's right-hand panel sometimes stays blank after a fresh
    navigation that resumes an in-progress draft (verified against the live
    app 2026-09-28: same URL/step text, empty form area until a resize fires
    -- looks like a responsive layout that only mounts its fields on a
    viewport/resize event). A same-size resize + scroll nudge is enough to
    make it mount without guessing at the underlying Angular cause."""
    size = page.viewport_size or {"width": 1280, "height": 800}
    page.set_viewport_size({"width": size["width"], "height": size["height"] - 1})
    page.wait_for_timeout(200)
    page.set_viewport_size(size)
    page.evaluate("window.dispatchEvent(new Event('resize'))")
    page.mouse.wheel(0, 50)
    page.wait_for_timeout(500)


def _ensure_step1(page) -> None:
    page.goto(SELL_URL, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(1500)
    _kick_render(page)
    for _ in range(4):
        if _current_step(page) == "1/3" and page.locator("select").count() > 0:
            return
        if page.get_by_text("Back", exact=True).count() > 0:
            _click_text(page, "Back", exact=True)
            page.wait_for_timeout(1000)
            _kick_render(page)
        else:
            page.wait_for_timeout(1000)
            _kick_render(page)
    if _current_step(page) != "1/3" or page.locator("select").count() == 0:
        raise RuntimeError(
            f"could_not_reach_step1:{_current_step(page)}:selects={page.locator('select').count()}"
        )


def _select_with_option(page, option_text: str):
    """Find whichever <select> currently offers `option_text` and pick it."""
    selects = page.locator("select")
    for i in range(selects.count()):
        opts = selects.nth(i).evaluate(
            "e => Array.from(e.options).map(o => o.textContent.trim())"
        )
        if option_text in opts:
            selects.nth(i).select_option(label=option_text)
            return
    raise RuntimeError(f"no_select_offers_option:{option_text}")


def _wait_for_select_count(page, minimum: int, timeout_ms: int = 10000) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if page.locator("select").count() >= minimum:
            return
        page.wait_for_timeout(200)
    raise RuntimeError(f"select_count_never_reached:{minimum}")


def _fill_step1(page, listing) -> None:
    _wait_for_select_count(page, 1)
    page.locator("select").nth(0).select_option(label=listing.item_type)
    _wait_for_select_count(page, 2)
    page.locator("select").nth(1).select_option(label=listing.generation_type)
    _wait_for_select_count(page, 3)
    page.locator("select").nth(2).select_option(label=listing.model)
    page.wait_for_timeout(300)
    page.locator("input[type=text]").first.fill(listing.title)
    page.locator("textarea").first.fill(listing.description)
    price_label = f"${listing.price_usd:.2f}"
    _select_with_option(page, price_label)
    page.wait_for_timeout(300)

    # Fail closed: re-read what the form actually holds before advancing.
    state = {
        "title": page.locator("input[type=text]").first.input_value(),
        "description": page.locator("textarea").first.input_value(),
    }
    if state["title"] != listing.title or state["description"] != listing.description:
        raise RuntimeError(f"step1_state_mismatch:{json.dumps(state, ensure_ascii=False)}")

    _click_text(page, "Next: Prompt File")
    page.wait_for_timeout(1200)
    if _current_step(page) != "2/3":
        raise RuntimeError(f"step1_did_not_advance:{_current_step(page)}")


def _fill_step2(page, listing) -> None:
    # "Prompt template" is the buyer-hidden field the whole SKILL.md (prefixed
    # with a "[VAR]: value" example-input line) is pasted into.
    page.locator("textarea").nth(0).fill(listing.prompt_instructions)
    _select_with_option(page, "5 Sonnet")
    page.wait_for_timeout(300)

    # "Example outputs" requires exactly 4 filled entries before PromptBase's
    # own submit validation passes (verified live 2026-09-28: submitting with
    # only one filled snapped back to step 2 with "Please upload 4 examples.",
    # final_url never left /sell). The single "Paste your output here"
    # textarea is where each entry is typed; clicking "Add example +" commits
    # the current text as one of the 4 and clears the box for the next one
    # (confirmed via "Examples uploaded: N/4" incrementing after each click).
    # PromptBase rejects 4 identical outputs ("Some of your example outputs
    # are the same", live 2026-09-29), so each slot gets its own real example
    # from evidence/examples.json (gen_examples.py).
    examples = listing.examples or []
    if len({e["output"] for e in examples}) != 4:
        raise RuntimeError("need_4_distinct_examples:run gen_examples.py")
    example_output_el = page.locator("textarea[placeholder='Paste your output here']")
    if example_output_el.count() == 0:
        raise RuntimeError("example_output_field_missing")
    for example in examples:
        example_output_el.first.fill(example["output"])
        page.wait_for_timeout(300)
        add_example_btn = page.get_by_text("Add example", exact=False)
        if add_example_btn.count() == 0:
            break  # last slot: no more "Add example" control needed
        add_example_btn.first.click(force=True)
        page.wait_for_timeout(500)
    uploaded_line = next(
        (ln for ln in page.inner_text("body").splitlines() if "Examples uploaded" in ln), ""
    )
    if "4/4" not in uploaded_line:
        raise RuntimeError(f"example_outputs_not_4_of_4:{uploaded_line!r}")

    # PromptBase auto-detects every "[...]" run inside the Prompt template as
    # a fillable "variable" and renders one text input per variable per
    # example row (verified live 2026-09-28: 4 examples x 2 detected
    # variables here = 8 input[type=text] boxes) -- submit fails closed with
    # "Please provide inputs for all of your examples" until every one has a
    # value. The variable this builder itself injects (INPUT_VARIABLE_LABEL)
    # maps back to the real verified example_input; any other variable
    # PromptBase found inside the catalog skill's own SKILL.md body (e.g. a
    # literal "[ADD: your number]") gets a generic, clearly-labeled
    # placeholder instead of a fabricated concrete value.
    variable_inputs = page.locator("input[type=text]")
    input_row = 0
    for i in range(variable_inputs.count()):
        el = variable_inputs.nth(i)
        placeholder = el.get_attribute("placeholder") or ""
        if placeholder == INPUT_VARIABLE_LABEL:
            # One such box per example row, in row order.
            el.fill(examples[min(input_row, 3)]["input"])
            input_row += 1
            continue
        # No square brackets allowed in the value itself (verified live
        # 2026-09-28: PromptBase's own validation rejects "Remove all square
        # brackets from your example inputs" for any that contain one).
        value = listing.example_input if placeholder == INPUT_VARIABLE_LABEL else placeholder
        el.fill(value)
    page.wait_for_timeout(300)

    # Prompt instructions field (buyer-facing usage tip) is the last textarea
    # on this step -- generic per-listing text, not hardcoded to one slug, so
    # this same code path is correct for every catalog skill the daily loop
    # ships, not just reels-hook-lab.
    textareas = page.locator("textarea")
    textareas.last.fill(
        f"Paste your input for {listing.title} and (optionally) any extra "
        "context this skill's SKILL.md asks for. The response follows that "
        "skill's own instructions end-to-end."
    )
    page.wait_for_timeout(300)

    _click_text(page, "Next: Finish")
    page.wait_for_timeout(1200)


def _already_visible_in_dashboard(page, title: str) -> bool:
    """True only if `title` already has a *submitted* card (Approved/Pending)
    -- an unsubmitted "Draft" (e.g. left over from a prior dry run of this
    same publisher) is not a listing and must not block a real submit."""
    page.goto(PROMPTS_URL, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(2000)
    cards = page.eval_on_selector_all(
        "body *",
        """els => {
            const statuses = new Set(['Approved','Pending','Scheduled','Draft','Declined','Archived','Disputed']);
            const rows = [];
            let pendingStatus = null;
            for (const el of els) {
                const t = (el.innerText || '').trim();
                if (statuses.has(t) && el.children.length === 0) pendingStatus = t;
                else if (pendingStatus && t && el.children.length === 0 && t.length < 100) {
                    rows.push([pendingStatus, t]);
                    pendingStatus = null;
                }
            }
            return rows;
        }""",
    )
    return any(status in ("Approved", "Pending", "Scheduled") and card_title == title
               for status, card_title in cards)


def _resolve_recaptcha_or_stop(page, evidence_dir: Path) -> None:
    """"Next: Finish" opens a "Confirm you're human" modal gating the actual
    submit -- there is no separate step-3 review screen. Click the reCAPTCHA
    v2 checkbox (a single real click, not a puzzle solve); Google's risk
    engine either passes it silently (verified against the live account
    2026-09-28: green check, no image grid) or escalates to a visible image
    challenge. Fail closed on the escalation per the task's explicit
    instruction: a CAPTCHA that needs a human stops the run here, not a
    guessed click on a puzzle.
    """
    anchor_frame = None
    for f in page.frames:
        if "recaptcha" in (f.url or "") and "anchor" in (f.url or ""):
            anchor_frame = f
            break
    if anchor_frame is None:
        raise RuntimeError("recaptcha_checkbox_not_found")
    checkbox = anchor_frame.locator("#recaptcha-anchor")
    checkbox.click()

    deadline = time.time() + 8
    while time.time() < deadline:
        if checkbox.get_attribute("aria-checked") == "true":
            return
        page.wait_for_timeout(300)

    page.screenshot(path=str(evidence_dir / "recaptcha_challenge.png"), full_page=True)
    raise RuntimeError("recaptcha_requires_human_verification")


def run(endpoint: str, catalog_dir: Path, confirm: bool, evidence_dir: Path) -> dict:
    from playwright.sync_api import sync_playwright

    listing = build_listing(catalog_dir)
    existing = ledger_mod.already_listed(listing.slug)
    if existing is not None:
        return {"ok": False, "reason": "already_in_ledger", "existing": existing}

    evidence_dir.mkdir(parents=True, exist_ok=True)
    result: dict = {"slug": listing.slug, "title": listing.title}

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint)
        ctx = browser.contexts[0]
        page = ctx.new_page()
        # PromptBase's real Submit click pops a native "leave/confirm" dialog
        # (verified live 2026-09-28: with no handler at all, Playwright's own
        # default auto-dismiss raced the dialog's own auto-close and crashed
        # its Node driver process with "No dialog is showing", hanging the
        # Python side indefinitely on the dead connection). Accepting it is
        # the same action a human clicking through the wizard takes --
        # unrelated to the reCAPTCHA policy, which only governs the
        # image-challenge modal. The dialog can still auto-close on its own
        # before this handler's accept() reaches it (same race, just no
        # longer fatal): swallow that one specific error instead of letting
        # it become an unhandled exception in Playwright's event loop.
        def _accept_dialog(dialog):
            try:
                dialog.accept()
            except Exception as exc:  # already resolved -- not a real failure
                if "No dialog is showing" not in str(exc):
                    raise

        page.on("dialog", _accept_dialog)
        try:
            if _already_visible_in_dashboard(page, listing.title):
                result.update(ok=False, reason="already_visible_in_dashboard")
                return result

            _ensure_step1(page)
            _fill_step1(page, listing)
            _fill_step2(page, listing)
            _resolve_recaptcha_or_stop(page, evidence_dir)

            page.screenshot(path=str(evidence_dir / "ready_to_submit.png"), full_page=True)
            (evidence_dir / "ready_to_submit_text.txt").write_text(page.inner_text("body")[:3000])

            if not confirm:
                result.update(ok=True, dry_run=True, evidence_dir=str(evidence_dir))
                return result

            submit_el = page.get_by_text("Submit", exact=True)
            if submit_el.count() == 0:
                raise RuntimeError("submit_control_not_found_after_recaptcha")
            _click_text(page, "Submit", exact=True)

            # Fail closed: only trust a submit that actually navigated to the
            # created listing's prompt-edit/<id> page -- verified live
            # 2026-09-28 that a silently-swallowed dialog error (see the
            # page.on("dialog", ...) handler above) can leave the click a
            # no-op, with the page still sitting on /sell. Absence of an
            # exception is not evidence of a real submission; poll for the
            # one URL shape that is.
            # Live 2026-09-29: a real submit can also stay on /sell and show
            # step 3/3 "Prompt Uploaded ... We are now reviewing your prompt"
            # (dashboard then lists it as Pending), so that page text counts too.
            deadline = time.time() + 10
            final_url = page.url
            uploaded = False
            while time.time() < deadline and "prompt-edit/" not in final_url and not uploaded:
                page.wait_for_timeout(500)
                final_url = page.url
                uploaded = "We are now reviewing your prompt" in page.inner_text("body")

            page.screenshot(path=str(evidence_dir / "after_submit.png"), full_page=True)
            (evidence_dir / "after_submit_text.txt").write_text(page.inner_text("body")[:6000])

            if "prompt-edit/" not in final_url and not uploaded:
                raise RuntimeError(f"submit_did_not_confirm:final_url={final_url}")
            promptbase_id = final_url.rstrip("/").rsplit("/", 1)[-1] if "prompt-edit/" in final_url else ""

            row = {
                "slug": listing.slug,
                "promptbase_id": promptbase_id,
                "url": final_url,
                "status": "submitted_pending_review",
                "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "title": listing.title,
                "price_usd": listing.price_usd,
            }
            ledger_mod.append(row)
            result.update(ok=True, dry_run=False, **row)
            return result
        finally:
            page.close()


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-dir", required=True, type=Path)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("~/.local/state/life-manager/state/promptbase-evidence").expanduser(),
    )
    args = parser.parse_args()
    try:
        result = run(args.endpoint, args.catalog_dir, args.confirm, args.evidence_dir)
    except Exception as error:  # fail closed, never guess at a submit
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}:{error}"}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_main())
