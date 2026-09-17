# Voice Outcome and Allowance UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record every wake-call result as conversation, no answer, or dial failure, charge only real conversation seconds to the monthly voice allowance, and show the result and remaining conversation time in the existing panel timeline.

**Architecture:** Keep `lm_wake_log` as the existing provider correlation ledger. Add outcome fields and one idempotent outcome RPC beside the existing Telnyx receipt RPC; the webhook writes provider facts first, then the derived outcome. Extend the existing timeline DTO and renderer so no new endpoint or frontend dependency is introduced.

**Tech Stack:** Node.js 20, PostgreSQL/Supabase SQL migrations, Telnyx signed webhooks, existing Node test runner, server-rendered HTML.

**Spec:** `docs/superpowers/specs/2026-09-06-life-manager-cloud-cost-pricing-design.md`

## Global Constraints

- A `conversation` consumes only the official connected seconds, once.
- A `no_answer` records a provider-accepted attempt with zero conversation seconds and does not consume the 3,600-second voice allowance.
- A `dial_failed` never appears as a delivered call; it remains retry/reconciliation evidence.
- A repeated Telnyx webhook must not duplicate a wake result, managed action, or voice seconds.
- User-visible Japanese copy must say `予定前に発信しました（応答なし）` for no answer and must not claim that the handset notification was seen.
- Use the existing `lm_wake_log`, `lm_wake_miss`, voice allowance, panel, and test patterns; add no dependency or parallel ledger.

---

### Task 1: Persist and classify terminal call outcomes

**Files:**
- Create: `apps/life-manager/lib/call-outcome.js`
- Create: `apps/life-manager/lib/call-outcome.test.js`
- Create: `apps/life-manager/migrations/2026-09-17-lm-wake-call-outcome.sql`
- Modify: `apps/life-manager/lib/telnyx-receipt.js:24-95`
- Modify: `apps/life-manager/lib/telnyx-receipt.test.js:20-220`

**Interfaces:**
- `classifyCallOutcome({ amdResult, connectedSeconds, hangupCause })` returns `"conversation"`, `"no_answer"`, `"dial_failed"`, or `null`.
- `recordTelnyxWakeOutcome({ uid, eventKey, claimToken, callControlId, callOutcome, hangupCause, connectedSeconds }, deps)` posts to `record_lm_wake_telnyx_outcome` and returns `{ ok, matched }`.
- The migration adds nullable `call_outcome`, `telnyx_hangup_cause`, and `telnyx_call_duration_seconds` columns and an owner-token, provider-identity-checked RPC that is idempotent.

- [ ] **Step 1: Write the failing classifier and RPC client tests**

Add assertions for timeout plus zero seconds → `no_answer`, human AMD → `conversation`, busy/rejected → `dial_failed`, positive seconds with no terminal proof → `null`, invalid inputs failing closed, and the exact outcome RPC body.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `node --test lib/call-outcome.test.js lib/telnyx-receipt.test.js`

Expected: FAIL because the classifier and outcome client do not exist.

- [ ] **Step 3: Implement the classifier and outcome RPC client**

Use bounded cause sets in `call-outcome.js`. Extend the existing receipt module with strict optional validation and a single POST helper; do not change the existing receipt response contract.

- [ ] **Step 4: Add the migration**

Create the three columns with checks (`call_outcome` in the three allowed values, duration 0–14,400), an index on `(uid, called_at, call_outcome)`, and `record_lm_wake_telnyx_outcome` that updates only the matching `uid + event_key + claim_token + call_control_id` row. Preserve `conversation` when a later replay reports a weaker outcome; let a later `conversation` upgrade `no_answer`.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run: `node --test lib/call-outcome.test.js lib/telnyx-receipt.test.js`

Expected: PASS with zero failures.

- [ ] **Step 6: Commit the persistence slice**

Run: `git add apps/life-manager/lib/call-outcome.js apps/life-manager/lib/call-outcome.test.js apps/life-manager/lib/telnyx-receipt.js apps/life-manager/lib/telnyx-receipt.test.js apps/life-manager/migrations/2026-09-17-lm-wake-call-outcome.sql && git commit -m "feat: persist wake call outcomes" && git push origin docs/voice-e2e-readback-20260917`

### Task 2: Settle webhook results without double counting

**Files:**
- Modify: `apps/life-manager/server.js:671-835`
- Modify: `apps/life-manager/lib/late-notice.js:500-539`
- Modify: `apps/life-manager/test/telnyx-events-retry-http-contract.test.js:203-510`
- Modify: `apps/life-manager/lib/late-notice.test.js:418-575`

**Interfaces:**
- A signed `call.hangup` stores the hangup cause and official duration, derives a terminal outcome when evidence is sufficient, and settles the voice allowance exactly once.
- A signed AMD event upgrades an existing outcome to `conversation` for `human` or `not_sure`; `machine` waits for the terminal hangup evidence instead of releasing the managed action early.
- `no_answer` completes the managed-action reservation once; `dial_failed` releases it; an unknown provider result leaves it pending for reconciliation.

- [ ] **Step 1: Add failing HTTP contract cases**

Cover timeout/zero duration → no-answer outcome and completed managed action, human AMD after hangup → conversation upgrade, dial failure release, replay with no second settlement, and the existing 5xx retry behavior.

- [ ] **Step 2: Run the webhook tests and verify the new cases fail**

Run: `node --test test/telnyx-events-retry-http-contract.test.js lib/late-notice.test.js`

Expected: the new outcome assertions fail while existing receipt assertions remain green.

- [ ] **Step 3: Wire the classifier and outcome RPC into `server.js`**

On hangup, fetch the official duration, call `recordTelnyxWakeOutcome`, then complete/release the managed action only for a derived terminal outcome. On AMD, record the raw result as before, call the outcome RPC only for `human`/`not_sure`, and do not release on `machine`.

- [ ] **Step 4: Run the webhook tests and verify they pass**

Run: `node --test test/telnyx-events-retry-http-contract.test.js lib/late-notice.test.js lib/managed-allowance.test.js`

Expected: PASS with zero failures.

- [ ] **Step 5: Commit the webhook slice**

Run: `git add apps/life-manager/server.js apps/life-manager/lib/late-notice.js apps/life-manager/test/telnyx-events-retry-http-contract.test.js apps/life-manager/lib/late-notice.test.js && git commit -m "fix: settle unanswered wake calls" && git push origin docs/voice-e2e-readback-20260917`

### Task 3: Expose outcome history and remaining conversation time

**Files:**
- Modify: `apps/life-manager/lib/panel-api.js:136-181`
- Modify: `apps/life-manager/lib/panel-presentation.js:64-111`
- Modify: `apps/life-manager/lib/panel-ui.js:797-980`
- Modify: `apps/life-manager/eval/panel-privacy-harness.js:103-136`
- Modify: `apps/life-manager/lib/panel-api.test.js:694-715`
- Modify: `apps/life-manager/lib/panel-ui.test.js:627-640`
- Modify: `apps/life-manager/lib/panel-privacy-browser.test.js:113-180`

**Interfaces:**
- Timeline source returns each call's `call_outcome`, provider cause, duration, and a `voice_usage` aggregate for the current tenant month.
- Projected timeline returns a closed DTO with `voice_usage: { available, used_seconds, limit_seconds, remaining_seconds, reset_at }` and safe Japanese sentences/statuses.
- The browser renders the existing timeline plus one compact line for remaining conversation time; it never exposes provider IDs or raw causes.

- [ ] **Step 1: Extend panel fixture and write failing DTO tests**

Add one conversation, one no-answer, one dial-failed fixture and a 3,600-second allowance aggregate. Assert the exact projected copy and remaining seconds.

- [ ] **Step 2: Run panel tests and verify they fail**

Run: `node --test lib/panel-api.test.js lib/panel-ui.test.js lib/panel-privacy-browser.test.js`

Expected: FAIL because the DTO does not yet contain outcome statuses or `voice_usage`.

- [ ] **Step 3: Implement the existing timeline extension**

Read the new wake columns and current-month voice ledger, project only safe outcome labels, and render `今月の会話残り時間: X分Y秒`. If the new table is unavailable, render a neutral unavailable state instead of `0秒`.

- [ ] **Step 4: Run panel tests and verify they pass**

Run: `node --test lib/panel-api.test.js lib/panel-ui.test.js lib/panel-privacy-browser.test.js`

Expected: PASS with zero failures and no provider identifiers in the browser HTML.

- [ ] **Step 5: Commit the panel slice**

Run: `git add apps/life-manager/lib/panel-api.js apps/life-manager/lib/panel-presentation.js apps/life-manager/lib/panel-ui.js apps/life-manager/lib/panel-api.test.js apps/life-manager/lib/panel-ui.test.js apps/life-manager/lib/panel-privacy-browser.test.js && git commit -m "feat: show wake outcomes and voice balance" && git push origin docs/voice-e2e-readback-20260917`

### Task 4: Release and prove the product behavior

**Files:**
- Modify: `docs/superpowers/specs/2026-09-06-life-manager-cloud-cost-pricing-design.md` only if deployment evidence changes the current As-is/To-be status.
- No new runtime files.

**Interfaces:**
- Production receives the new migration before the immutable application release.
- The final receipt includes focused tests, migration/schema readback, deployed health/build readback, and one natural calendar wake path when an eligible event is available.

- [ ] **Step 1: Run the complete focused voice and panel suite**

Run: `node --test lib/call-outcome.test.js lib/telnyx-receipt.test.js test/telnyx-events-retry-http-contract.test.js lib/late-notice.test.js lib/managed-allowance.test.js lib/panel-api.test.js lib/panel-ui.test.js lib/panel-privacy-browser.test.js test/wake-loop-isolation.test.js`

Expected: PASS with zero failures.

- [ ] **Step 2: Inspect the complete diff and run `git diff --check`**

Expected: only the files in Tasks 1–3 and the migration/spec evidence are changed; no secrets or provider identifiers are added to UI output.

- [ ] **Step 3: Apply the migration and read back the schema**

Run the existing production migration path for `2026-09-17-lm-wake-call-outcome.sql`, then read back the three columns, RPC, and index through the existing Supabase service-role probe. Do not claim the deploy from a local test.

- [ ] **Step 4: Deploy the immutable branch release and read `/health`**

Declare the production change immediately before the Railway deploy, deploy the pushed commit, and verify the returned build SHA matches the pushed commit.

- [ ] **Step 5: Read back one natural wake result**

For an eligible calendar event, verify the T-10/T-5 rows show the new outcome, the voice ledger counts only conversation seconds, and a repeated webhook leaves counts unchanged. If no eligible event exists, report the production code/schema receipt and leave only this external natural-wake proof open.

- [ ] **Step 6: Update the spec status, commit, and push the final evidence**

Change only the status/evidence lines needed to reflect observed production results, then run `git diff --check`, `git commit`, and `git push`.
