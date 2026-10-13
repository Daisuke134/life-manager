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
- A Hook Lab click is deterministic only when exact product/token scope and a complete, unique receipt-ID list match; other products retain their existing exact `Content-Range` count behavior.
- Capafy per-agent or per-channel paid totals are not per-creative orders; missing click-to-order joins remain unknown.
- Do not enable the publisher, send posts, change seller terms, increase cadence, or alter effect fences.
- The Capafy business CD1 lane remains separately owned; DD03 changes only the shared measurement binding.

## Review Focus

- An unregistered seller CT or other-product token must not count as Hook Lab attribution; an internal `hl_` token passes only when it matches the exact publication intent.
- The same token reused by two publication slots must fail before a click is counted.
- Missing, duplicate, or truncated receipt IDs must not support a deterministic Hook Lab click count.
- `?diagnostic=1` must produce no receipt and no provider redirect.
- A 30-day Hook Lab paid total without a receipt-to-order join must leave per-creative paid orders and revenue unknown.

---

### Task 1: Fixed Hook Lab owned redirect (`anicca-products`)

**Files:**
- Modify: `apps/landing/netlify/functions/_lib/marketing-go.js`
- Modify: `apps/landing/netlify/functions/marketing-go.js`
- Test: `apps/landing/netlify/functions/_lib/__tests__/marketing-go.test.js`

**Interface:** `hl_<20 base32 characters>` identifies a first-party publication token. The wrapper maps only prefix `hl` to `product_id=hook-lab`, agent `8123079349`, and downstream `ct=hooklab_ig`.

- [x] Write failing test `production Hook Lab route records the exact publication token and fixed registered CT` through the production Netlify wrapper, proving `hl_` stores a minimal `hook-lab` receipt and redirects only to `https://capafy.ai/agent/8123079349?ct=hooklab_ig`.
- [x] Run `node --test apps/landing/netlify/functions/_lib/__tests__/marketing-go.test.js`; confirm the new case fails because `hl_` is not recognized.
- [x] Add only the `hl` token prefix and fixed Hook Lab product mapping; run the focused Node test and confirm this case passes.
- [x] Write failing test `Hook Lab diagnostics do not persist a click receipt or redirect`, proving a valid `?diagnostic=1` request returns 204 with no receipt and no `Location` header.
- [x] Run the focused Node test; confirm the diagnostic case fails before the implementation.
- [x] Add the diagnostic early return after token/product validation; do not copy arbitrary query values into the destination.
- [x] Run the focused Node test and `git diff --check`.
- [x] Commit and push the route change from its dedicated `anicca-products` worktree (`9fab16b0`). PR/merge/deployed diagnostic remain final integration steps.

### Task 2: Per-publication token and receipt join (Life Manager)

**Files:**
- Modify: `skills/earn/marketing-engine/measure/attribution.py`
- Modify: `skills/earn/marketing-engine/publish/publish_cli.py`
- Modify: `skills/earn/marketing-engine/measure/experiment_attribution.py`
- Test: `skills/earn/marketing-engine/measure/test_attribution.py`
- Test: `skills/earn/marketing-engine/publish/test_intent_cli.py`
- Test: `skills/earn/marketing-engine/measure/test_experiment_attribution.py`

**Interface:** Add `publication_campaign_token(intent: dict[str, str]) -> str` in `measure/attribution.py`. It serializes, in order, `experiment_id` (campaign identity), `creative_id`, `product_id`, `account_id`, `hook_id`, `renderer_id`, and `scheduled_at` with compact `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`, then passes that string to the existing product-scoped `campaign_token`. Golden vector: `experiment.dd03`, `creative.dd03`, `hook-lab`, `life-manager-capafy-ig`, `hook.dd03`, `watercolor-monk`, `2026-10-16T00:00:00Z` → `hl_r7py2zlsvjjafl4srigi`. For Hook Lab only, `publish_cli.run_create_intent` replaces the exact registered `hooklab_ig` placeholder URL with the resulting owned `hl_` URL. The attribution snapshot retains `experiment_id`, `creative_id`, `publish_key`, and each exact click receipt ID in evidence references.

The `run_create_intent` regression test uses a temporary synthetic account fixture because DD01 intentionally adds no live Hook Lab publisher-account route; do not add that account route or enable publishing in production.

- [x] Add failing test `test_publication_campaign_token_is_deterministic_and_slot_specific`, including the golden vector above and a distinct token for a different scheduled slot.
- [x] Run `python3 skills/earn/marketing-engine/measure/test_attribution.py`; confirm the new token case fails.
- [x] Add the minimal Hook Lab prefix and deterministic publication-token helper; run the focused test and confirm it passes.
- [x] Add failing tests `test_hook_lab_intent_rewrites_registered_ct` and `test_hook_lab_intent_rejects_foreign_ct` through `run_create_intent` with the temporary synthetic Hook Lab account. The first proves `hooklab_ig` becomes the deterministic owned `hl_` URL; the second rejects an `ej_`/arbitrary token.
- [x] Run `python3 -m pytest skills/earn/marketing-engine/publish/test_intent_cli.py`; confirm both new cases fail for the expected reasons.
- [x] Implement Hook Lab intent token/caption binding and strict input-token allowlist; run the focused publisher test file and confirm both cases pass.
- [x] Add failing test `test_hook_lab_snapshot_rejects_foreign_or_shared_token` for an unregistered seller CT and one shared token reused across two publication slots.
- [x] Run `python3 skills/earn/marketing-engine/measure/test_experiment_attribution.py`; confirm the three invalid-token subcases fail.
- [x] Recompute and require the exact per-publication Hook Lab token before snapshot construction; run the evaluator test file and confirm it passes.
- [x] Add failing query test `test_click_query_rejects_incomplete_or_duplicate_receipts` for a count/body mismatch and duplicate receipt IDs.
- [x] Run the focused experiment-attribution file; confirm both query cases incorrectly return `available`.
- [x] Return `unavailable` for incomplete rows, malformed IDs, or duplicate receipt IDs; run the focused file and confirm it passes.
- [x] Add failing regression test `test_non_hook_lab_click_query_keeps_exact_header_count_when_body_is_partial` to preserve existing count semantics for other products.
- [x] Run the focused query test; confirm the current global row-count guard makes the non-Hook Lab case unavailable.
- [x] Scope row completeness/duplicate-ID rejection to Hook Lab only; rerun both Hook Lab and non-Hook Lab query cases.
- [x] Add failing evaluator test `test_hook_lab_click_join_rejects_incomplete_or_duplicate_receipts` for missing or duplicate IDs in a supplied Hook Lab click query.
- [x] Add failing success test `test_hook_lab_click_receipt_id_is_saved_as_creative_evidence` proving the exact receipt ID is retained with the publication/creative snapshot.
- [x] Implement complete unique receipt-ID validation and add each exact receipt ID to Hook Lab evidence references; run the focused evaluator tests and confirm they pass.
- [x] Add failing test `test_hook_lab_paid_revenue_stays_unknown_without_capafy_order_join` showing a Stripe campaign-shaped or Capafy channel aggregate cannot become Hook Lab per-creative paid revenue without an order join.
- [x] Run the focused evaluator test; confirm it fails on the currently accepted Stripe campaign-shaped input.
- [x] Keep Hook Lab paid/revenue metrics unknown without a supported Capafy click-to-order join; run the focused evaluator test and confirm it passes.
- [x] Run `python3 skills/earn/marketing-engine/measure/test_attribution.py` (9/9), `python3 skills/earn/marketing-engine/measure/test_experiment_attribution.py` (14/14), `python3 -m pytest skills/earn/marketing-engine/publish/test_intent_cli.py` (4/4), source-boundary check, and `git diff --check`.
- [x] Commit and push the Life Manager change from this dedicated worktree.

### Task 3: Close the DD03 SSOT entry

- [ ] Record both repositories' commits/PRs, focused test results, the official CT readback artifact, and any remaining deployment/readback limit in the canonical SSOT.
- [ ] Keep DD03 open until the route source is integrated and its diagnostic path is verified without creating a click receipt; do not claim any per-creative paid or net revenue.
