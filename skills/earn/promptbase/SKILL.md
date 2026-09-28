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
  ever opening the `/sell` wizard. `rejected` is the only status a slug can
  retry from.
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
- `tests/` — `build_listing`, `ledger`, and `readback`-parsing tests, no
  browser required (`python3 -m unittest discover -s tests`).

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
   (defaults 16384/0, matches the live Hook Lab listing) → one "Example
   outputs" textarea (the "Add example +" button only adds *further* slots,
   up to 4 total — the first slot is already present) → "Prompt instructions"
   (buyer-facing usage tip).
3. **"Next: Finish"** does not lead to a review step — it opens a **"Confirm
   you're human"** modal with a reCAPTCHA v2 checkbox gating the actual
   submit. This is the one part that is not fully autonomous: Google's risk
   engine sometimes passes the checkbox silently (verified live) and
   sometimes escalates to a visible image-grid challenge. `publish.py` clicks
   the checkbox once and waits up to 8s for it to self-clear; if it instead
   sees an image challenge it raises `recaptcha_requires_human_verification`
   and saves a screenshot to `--evidence-dir/recaptcha_challenge.png` **and
   does not attempt to solve it** — that is a stop-and-report condition, not
   a retry loop, per this task's explicit instruction.

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

## Cadence (not wired to a loop yet, per task scope)

One catalog skill approved on Capafy roughly translates to one PromptBase
candidate. A reasonable cadence would be a **weekly** check: for every
catalog dir under `skills/capafy/catalog/*` not yet in the ledger, run
`publish.py` once (dry run first, `--confirm` only after a human/agent reads
the screenshot), then run `readback.py` daily to catch the reCAPTCHA-free
window and approval/rejection status. Not added as a launchd job in this
change — the reCAPTCHA gate above makes a fully unattended loop unsafe until
either PromptBase whitelists this session or a documented human-checkpoint
step is added to the loop design.
