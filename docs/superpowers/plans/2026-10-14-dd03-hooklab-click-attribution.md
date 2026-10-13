# DD03 Hook Lab Click Attribution Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` task by task. Dais explicitly delegated execution without a human approval gate.

**Goal:** Bind one owned click receipt to one Hook Lab publication and creative while keeping seller-level paid totals out of per-creative revenue.

**Architecture:** Keep the existing `aniccaai.com/go/<token>` redirect and `marketing_click_receipts` table. Life Manager creates a deterministic first-party `hl_` token from the exact publication identity; the existing redirect records that token and sends visitors to the fixed Hook Lab listing with Capafy's registered `hooklab_ig` CT. The evaluator checks the exact token/product/receipt IDs and leaves per-creative sales unknown without an order-level join.

**Tech Stack:** Python standard library, existing Life Manager publisher/attribution modules, Node.js built-in test runner, existing Netlify Function.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`, DD03.

## Global Constraints

- Product is fixed to Hook Lab agent `8123079349`; the official seller CT is exactly `hooklab_ig`.
- The internal first-party token uses `hl_` plus the existing 20-character base32 token body and is unique to one publication identity.
- A generated/unregistered seller `ct` is invalid. `hl_<hash>` is only our internal join key; the downstream Capafy `ct` remains the verified `hooklab_ig`.
- The redirect maps to the fixed Capafy URL and seller CT; caller-controlled destinations or seller CTs are rejected.
- Diagnostic requests create no click receipt and do not redirect.
- A click count is deterministic only when the exact product/token and a complete, unique receipt-ID list match.
- Capafy per-agent or per-channel paid totals are not per-creative orders; missing click-to-order joins remain unknown.
- Do not enable the publisher, send posts, change seller terms, increase cadence, or alter effect fences.
- The Capafy business CD1 lane remains separately owned; DD03 changes only the shared measurement binding.

## Review Focus

- An unregistered seller CT or other-product token must not count as Hook Lab attribution; an internal `hl_` token passes only when it matches the exact publication intent.
- The same token reused by two publication slots must fail before a click is counted.
- Missing, duplicate, or truncated receipt IDs must not support a deterministic click count.
- `?diagnostic=1` must produce no receipt and no provider redirect.
- A 30-day Hook Lab paid total without a receipt-to-order join must leave per-creative paid orders and revenue unknown.

---

### Task 1: Fixed Hook Lab owned redirect (`anicca-products`)

**Files:**
- Modify: `apps/landing/netlify/functions/_lib/marketing-go.js`
- Modify: `apps/landing/netlify/functions/marketing-go.js`
- Test: `apps/landing/netlify/functions/_lib/__tests__/marketing-go.test.js`

**Interface:** `hl_<20 base32 characters>` identifies a first-party publication token. The wrapper maps only prefix `hl` to `product_id=hook-lab`, agent `8123079349`, and downstream `ct=hooklab_ig`.

- [ ] Write a failing test through the production Netlify wrapper proving `hl_` stores a minimal `hook-lab` receipt and redirects only to `https://capafy.ai/agent/8123079349?ct=hooklab_ig`.
- [ ] Run `node --test apps/landing/netlify/functions/_lib/__tests__/marketing-go.test.js`; confirm the new case fails because `hl_` is not recognized.
- [ ] Write a failing test that a valid `?diagnostic=1` request returns 204 with no receipt and no `Location` header.
- [ ] Run the focused Node test; confirm the diagnostic case fails before the implementation.
- [ ] Add the fixed `hl` product mapping and diagnostic early return; do not copy arbitrary query values into the destination.
- [ ] Run the focused Node test and `git diff --check`.
- [ ] Commit and push the route change from its dedicated `anicca-products` worktree.

### Task 2: Per-publication token and receipt join (Life Manager)

**Files:**
- Modify: `skills/earn/marketing-engine/measure/attribution.py`
- Modify: `skills/earn/marketing-engine/publish/publish_cli.py`
- Modify: `skills/earn/marketing-engine/measure/experiment_attribution.py`
- Test: `skills/earn/marketing-engine/measure/test_attribution.py`
- Test: `skills/earn/marketing-engine/publish/test_intent_cli.py`
- Test: `skills/earn/marketing-engine/measure/test_experiment_attribution.py`

**Interface:** Derive the publication token from `experiment_id`, `creative_id`, `product_id`, `account_id`, `hook_id`, `renderer_id`, and `scheduled_at`. For Hook Lab only, replace the exact registered `hooklab_ig` placeholder URL with the generated owned `hl_` URL. The attribution snapshot retains each exact click receipt ID in its evidence references.

The `run_create_intent` regression test uses a temporary synthetic account fixture because DD01 intentionally adds no live Hook Lab publisher-account route; do not add that account route or enable publishing in production.

- [ ] Add a failing token test for repeatability on the same identity and distinct tokens for different publication slots.
- [ ] Add a failing `run_create_intent` test with the temporary synthetic Hook Lab account proving the static registered `hooklab_ig` placeholder becomes the deterministic owned `hl_` URL and an `ej_`/arbitrary token is rejected.
- [ ] Run `python3 -m pytest skills/earn/marketing-engine/publish/test_intent_cli.py`; confirm the new case fails before the implementation.
- [ ] Add a failing token test for a foreign product token and a shared token reused across two publication slots.
- [ ] Add failing receipt tests for incomplete/duplicate receipt IDs and channel-level Capafy paid totals without a per-creative order join.
- [ ] Run the two focused measurement test files and confirm each new assertion fails for the intended missing behavior.
- [ ] Implement the minimal per-intent token generation, caption binding, exact receipt validation, and receipt evidence references.
- [ ] Run `python3 skills/earn/marketing-engine/measure/test_attribution.py`, `python3 skills/earn/marketing-engine/measure/test_experiment_attribution.py`, `python3 -m pytest skills/earn/marketing-engine/publish/test_intent_cli.py`, source-boundary check, and `git diff --check`.
- [ ] Commit and push the Life Manager change from this dedicated worktree.

### Task 3: Close the DD03 SSOT entry

- [ ] Record both repositories' commits/PRs, focused test results, the official CT readback artifact, and any remaining deployment/readback limit in the canonical SSOT.
- [ ] Keep DD03 open until the route source is integrated and its diagnostic path is verified without creating a click receipt; do not claim any per-creative paid or net revenue.
