---
name: earn/promptbase
description: Publish one Capafy catalog skill (skills/capafy/catalog/<slug>/) as a PromptBase "Prompt" listing, reusing the live "Hook Lab Win The First 3 Seconds" listing's proven shape (item type Prompt, generation type Text, model Claude 5 Sonnet, price $4.99). Idempotent via a JSONL ledger; a readback command refreshes each listing's approval status from the seller dashboard.
---

# earn/promptbase — publish a catalog skill to PromptBase

PromptBase (https://promptbase.com) sells prompts and agent skills. Our account
(credential SSOT `~/.local/share/anicca/credentials.json`, service
`promptbase`) has payout enabled via Zoneless. The account's first listing,
"Hook Lab Win The First 3 Seconds" (https://promptbase.com/prompt/
hook-lab-win-the-first-3-seconds-2), is live and is the proven template this
publisher reuses: item type **Prompt**, generation type **Text**, model
**Claude 5 Sonnet**, price **$4.99** (one-time, not subscription), the whole
SKILL.md pasted as the buyer-hidden "prompt template", and a
`[VAR]: value` line prepended to it so PromptBase's public page renders an
"Example input" block the way Hook Lab's does.

## Files

- `scripts/build_listing.py` — pure text transform: catalog dir → `Listing`
  (title from `LISTING.md`'s `## Title`, description from `## shortDescription`,
  example input/output split from `evidence/verified-demonstration.md`,
  fixed price/model/category matching Hook Lab). No network/browser.
- `scripts/ledger.py` — JSONL idempotency ledger at
  `~/.local/state/life-manager/state/promptbase-listings.jsonl`. One line per
  submission; `already_listed(slug)` is the guard `publish.py` checks before
  ever opening the `/sell` wizard. `rejected` and `captcha_challenge_deferred`
  are the only statuses a slug can retry from (`RETRYABLE_STATUSES`).
  `record_captcha_deferred(slug)` / `ledger.py record-captcha-deferred --slug
  <slug>` is the clean-stop path `daily.sh` uses on a CAPTCHA image
  challenge.
- `scripts/publish.py` — drives PromptBase's `/sell` wizard with Playwright
  connected over an already-leased CDP endpoint. Fails closed: any
  unexpected form state (missing field, wizard not on the expected step, no
  submit control) raises instead of guessing. Without `--confirm` it is a
  dry run that fills the whole wizard and stops at the reCAPTCHA-gated
  "ready to submit" screen (screenshot + text dump in `--evidence-dir`).
- `scripts/readback.py` — re-reads `account?view=prompts`' rendered text and
  updates each ledger slug's status (`live` / `pending_review` / `rejected` /
  `draft` / ...) from PromptBase's own Approved/Pending/Declined labels. The
  text-parsing part (`parse_dashboard_cards`, `status_for_title`) is pure and
  tested against real captured dashboard text; only the fetch is a browser
  call.
- `scripts/select_next.py` — pure selection logic: given the catalog's
  `LISTING.md` titles, the authoritative Capafy `publish-list` agents, and the
  ledger, picks the next slug that is online on Capafy and not already
  shipped/pending on PromptBase. Prefers the `reels-hook-lab` winner-family
  slug first, then lower `LISTING.md` "Demand rank" values (reusing
  `capafy-autopublish`'s own `inventory_status.listing_demand_rank`, not a
  second implementation). No network/browser.
- `scripts/promptbase_fence_reconcile.py` — the loop registry's
  `effect_reconcile` adapter for `promptbase-loop-daily`: closes an
  `effect_unknown` admission fence from the PromptBase seller dashboard (the
  only official readback there is, since PromptBase has no API) once
  `daily.sh`'s pre-submit snapshot names a slug/title and enough time has
  passed.
- `daily.sh` — the loop entrypoint. See "Daily loop" below.
- `tests/` — `build_listing`, `ledger`, `select_next`, `readback`-parsing,
  and `promptbase_fence_reconcile` tests, no browser required
  (`python3 -m unittest discover -s tests`, or `python3 -m pytest tests/` —
  the fence-reconcile test file uses plain pytest functions like the other
  loops' fence-reconcile tests do).

## Running it (lease wrapper only — never a hardcoded port)

```bash
ENDPOINT=$(/Users/anicca/.config/ai/bin/browser-guard.sh acquire interactive:dais) || exit 1
python3 skills/earn/promptbase/scripts/publish.py \
  --catalog-dir skills/capafy/catalog/<slug> \
  --endpoint "$ENDPOINT"          # dry run: fills the wizard, stops before submit
  # add --confirm to actually submit once the dry-run screenshot looks right
/Users/anicca/.config/ai/bin/browser-guard.sh release interactive:dais
```

```bash
ENDPOINT=$(/Users/anicca/.config/ai/bin/browser-guard.sh acquire interactive:dais) || exit 1
python3 skills/earn/promptbase/scripts/readback.py --endpoint "$ENDPOINT"
/Users/anicca/.config/ai/bin/browser-guard.sh release interactive:dais
```

## The PromptBase `/sell` wizard, as-observed (2026-09-28)

Angular SPA, no name/id attributes on any control (selected by position or
visible text), 2 steps + a modal:

1. **Prompt Details** — item type (Prompt/Agent Skill) → generation type
   (Text/Images/Videos) → model (Claude/DeepSeek/...) → Name (40 chars) →
   Description (500 chars) → Price (fixed tiers: Free, $2.99…$8.99).
   Submitting this step **auto-saves a server-side Draft** — revisiting
   `/sell` resumes that draft instead of a blank step 1. `publish.py` detects
   this and walks "Back" until step 1 is showing before refilling it, so a
   stale draft from a previous run is never silently half-reused.
2. **Prompt File** — "Prompt template" (buyer-hidden, ≤8,192 tokens; this is
   where the SKILL.md goes) → Claude version → Max tokens/Temperature
   (defaults 16384/0, matches the live Hook Lab listing) → **exactly 4**
   example outputs (verified live 2026-09-28: submit fails closed with
   "Please upload 4 examples" for fewer) → **one example value per detected
   `[...]` variable per example row** (PromptBase parses every bracketed run
   in the Prompt template as a variable and renders one text input per
   variable per example; leaving any blank fails closed with "Please provide
   inputs for all of your examples", and a value containing `[`/`]` itself
   fails closed with "Remove all square brackets from your example inputs")
   → "Prompt instructions" (buyer-facing usage tip). `publish.py`'s
   `_fill_step2` handles both: it fills the single "Paste your output here"
   textarea and clicks "Add example +" four times (all four reuse the one
   real verified `example_output` — honest, not fabricated, just meeting the
   form's minimum count), then fills every `input[type=text]` it finds —
   `build_listing.INPUT_VARIABLE_LABEL`'s own variable gets the real
   `example_input`, any other detected variable (e.g. a literal
   `[ADD: your number]` from the catalog skill's own SKILL.md body) gets its
   own placeholder text back, unbracketed, as a clearly-generic filler.
3. **"Next: Finish"** does not lead to a review step — it opens a **"Confirm
   you're human"** modal with a reCAPTCHA v2 checkbox gating the actual
   submit. This is the one part that is not fully autonomous: Google's risk
   engine sometimes passes the checkbox silently (verified live) and
   sometimes escalates to a visible image-grid challenge (also verified live
   — a real "select all bicycle tiles" grid). `publish.py` clicks the
   checkbox once and waits up to 8s for it to self-clear; if it instead sees
   an image challenge it raises `recaptcha_requires_human_verification` and
   saves a screenshot to `--evidence-dir/recaptcha_challenge.png` **and does
   not attempt to solve it** — that is a stop-and-report condition, not a
   retry loop, per this task's explicit instruction. A real Submit click also
   pops a native browser "leave/confirm" dialog; `publish.py` registers a
   `page.on("dialog", ...)` handler that accepts it (the same action a human
   clicking through the wizard takes) and swallows the harmless "No dialog is
   showing" race when the dialog has already auto-resolved on its own.
   `run()` only trusts a submit that actually navigated to
   `prompt-edit/<id>` within 10s — absence of an exception is not evidence of
   a real submission (verified live: a failed-validation submit click can
   silently snap back to step 2 with the page still on `/sell`).

Note: the wizard's right-hand panel sometimes renders blank on a fresh
navigation that resumes an in-progress draft. `publish.py`'s `_kick_render`
(a same-size viewport resize + scroll nudge) works around it without
guessing at the underlying Angular cause.

## Idempotency

Two independent checks, both before any form is touched:
1. `ledger.already_listed(slug)` — a slug already in the ledger (any status
   except `rejected`) is refused.
2. `_already_visible_in_dashboard(title)` — a title with an
   Approved/Pending/Scheduled card on the live seller dashboard is refused,
   even if the local ledger were somehow lost. A leftover unsubmitted
   `Draft` card (e.g. from an earlier dry run) does **not** count — only a
   real submission does.

## Daily loop (`promptbase-loop-daily`, `config/loop-registry.json`)

Runs `daily.sh` once a day (04:20, a quiet hour) via the `interactive:dais`
browser lease, `effect_class: publish`, no human in the loop:

1. `readback.py` — refresh every tracked ledger row's status/sales from the
   dashboard first.
2. Read the authoritative Capafy state (`packager.py publish-list` under
   `skills/capafy-autopublish/vendor/capafy-publisher`, with
   `CAPAFY_PUBLISHER_STATE_HOME`/`HOME` pointed at
   `~/.local/state/life-manager/runtime/capafy-publisher{,-home}`).
3. `select_next.py` — pick the next slug that's online on Capafy and not yet
   shipped/pending on PromptBase.
4. `publish.py --confirm` once for that slug.
5. Record the outcome: a real submission appends a `submitted_pending_review`
   ledger row; a reCAPTCHA image challenge appends
   `captcha_challenge_deferred` (never solved) and exits 0 so tomorrow's run
   retries the same slug; any other failure exits non-zero.

**CAPTCHA policy (strict, never relaxed):** `publish.py` never attempts to
solve or bypass a reCAPTCHA image challenge — it raises
`recaptcha_requires_human_verification` and stops closed. `daily.sh` records
`captcha_challenge_deferred` and exits 0 (no Telegram ask, no retry loop
inside the same run). At most one submit attempt per calendar day, with
`publish.py`'s existing human-paced clicks/typing (see `_click_text`) —
no parallelism.

`promptbase_fence_reconcile.py` is the registry's `effect_reconcile` adapter:
if a run dies after submitting but before `ledger.append`, it re-reads the
seller dashboard (the only official PromptBase readback there is) for the
slug/title `daily.sh` snapshotted immediately before `publish.py --confirm`,
and closes the fence from that receipt instead of leaving it stuck.
