# Life Manager Mental and Physical Care Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair Telnyx call-limit rejection and extend the existing cloud MENTAL organ into a Japanese-first, context-aware mental and physical care system without creating another loop.

**Architecture:** The Telnyx fix lives in the shared dial-body builder and ships independently. Mental and physical interventions continue through `scheduler.js -> mentalUserOnce -> evaluateMentalTrigger -> buildMentalMessage -> Telegram -> lm_mental_send_log`, with new structured intents, fail-closed context handling, one shared attention budget, and Dais-only canary rollout.

**Tech Stack:** Node.js CommonJS, `node:test`, Supabase/Postgres REST, Telegram Bot API, Telnyx Call Control, Railway cloud worker, immutable Life Manager releases.

**Spec:** `docs/superpowers/specs/2026-09-16-life-manager-mental-physical-design.md`

## Global Constraints

- Reuse the existing cloud scheduler, Telegram transport, `lm_mental_send_log`, runtime preferences, and main-to-Railway deployment flow.
- Do not add a new daemon, scheduler, database, queue, transport, or LLM framework.
- Japanese ships first; localization starts only after the seven-day Japanese canary passes.
- Every care message uses observed facts, a believable reframe, and at most one 10–60 second action.
- The shared MENTAL/precepts hard ceiling remains three messages per local day; Dais canary uses a lower ceiling of two care messages.
- No diagnosis, treatment claim, crisis conclusion, passive mood inference, destiny claim, or guaranteed manifestation outcome.
- Provider effects require provider receipt/readback and replay-zero evidence; source code and exit 0 alone are insufficient.
- Railway production truth is the deployment `commitHash` plus service logs; local immutable releases are not proof of a cloud deployment.
- Work from latest `main` in a dedicated worktree; commit and push each independently testable task before continuing.

---

## File map

| File | Responsibility |
|---|---|
| `apps/life-manager/lib/call-logic.js` | Build Telnyx dial request and enforce provider minimum |
| `apps/life-manager/lib/lm-p0.test.js` | Focused Telnyx body contract |
| `apps/life-manager/lib/mental-trigger.js` | Pure eligibility, intent priority, caps, gaps, quiet/mute gates |
| `apps/life-manager/lib/mental-trigger.test.js` | Decision matrix for all mental/physical intents |
| `apps/life-manager/lib/mental-copy.js` | Structured Japanese templates and hard validation |
| `apps/life-manager/lib/mental-copy.test.js` | Copy safety, grounding, and exact-template tests |
| `apps/life-manager/lib/mental-runtime.js` | Context composition, delivery, and post-send recording |
| `apps/life-manager/lib/mental-runtime.test.js` | Runtime delivery and failure semantics |
| `apps/life-manager/lib/mental-send-log.js` | Shared attention history, unique feedback key, and feedback persistence |
| `apps/life-manager/lib/mental-send-log.test.js` | Strict read, append, feedback, and idempotency tests |
| `apps/life-manager/lib/mental-feedback.js` | Parse and apply the three feedback actions |
| `apps/life-manager/lib/mental-feedback.test.js` | Callback authorization and replay tests |
| `apps/life-manager/scheduler.js` | Supply structured context and log outcome receipts |
| `apps/life-manager/lib/mental-wiring.test.js` | Cloud scheduler wiring and sibling isolation |
| `apps/life-manager/migrations/2026-09-16-lm-mental-intents-feedback.sql` | Ledger intent/template/fingerprint/feedback fields |
| `apps/life-manager/lib/mental-migration.test.js` | Closed migration and append-only contract |
| `docs/evidence/life-manager-mental-canary.md` | Loaded release, provider effects, suppression, replay-zero, seven-day evidence |

## Milestone 1: Telnyx provider-boundary repair

### Task 1: Locate the failing Telnyx request producer

**Files:**
- Modify: `docs/evidence/life-manager-mental-canary.md`

**Interfaces:**
- Consumes: 08:02 Railway/Telnyx logs, current Railway service deployment metadata, and current `main`
- Produces: exact producer file/function, deployed commit SHA, and sanitized `time_limit_secs` value

- [ ] **Step 1: Create the evidence document with a closed incident table**

```markdown
| Field | Observed value | PASS condition |
|---|---|---|
| Railway service | | exact service name |
| Deployment commitHash | | 40-char SHA |
| Request producer | | file and function or external tool name |
| Sanitized time_limit_secs | | integer value, no phone/credential |
| Current main comparison | | same producer, drift, or second path |
```

- [ ] **Step 2: Read current Railway service and deployment metadata**

Run: `cd apps/life-manager && railway status --json`
Run: `cd apps/life-manager && railway deployment list --json`
Record the exact service, environment, deployment ID, status, and `commitHash`. Do not print environment variables.

- [ ] **Step 3: Read the bounded 08:02 error window**

Run: `cd apps/life-manager && railway logs --service life-call --since 2026-09-16T07:58:00+09:00 --until 2026-09-16T08:06:00+09:00`
If the service name from Step 2 differs, rerun against that exact service. Record only the producer marker and numeric limit; redact phone numbers, tokens, and user text.

- [ ] **Step 4: Compare the deployed SHA with current main**

Set `DEPLOYED_SHA` to the exact `commitHash` recorded in Step 2.
Run: `git show "$DEPLOYED_SHA":apps/life-manager/lib/call-logic.js | rg -n "time_limit_secs|telnyxDialBody"`
Run: `git show "$DEPLOYED_SHA":apps/life-manager/lib/dial.js | rg -n "time_limit_secs|telnyxDialBody|/calls"`
Run: `rg -n "time_limit_secs|telnyxDialBody|/v2/calls" apps/life-manager --glob '!node_modules'`.

- [ ] **Step 5: Close the producer identity**

The task passes only with one of these exact findings:

```text
deployed_drift plus exact SHA, file, and function
second_repo_path plus exact absolute source identity and function
external_call_tool plus exact tool name and request-field source
```

Do not begin Task 2 with only a guessed file.

- [ ] **Step 6: Commit and push the sanitized evidence**

```bash
git add docs/evidence/life-manager-mental-canary.md
git commit -m "docs(life-manager): identify Telnyx limit failure producer"
git push -u origin HEAD
```

### Task 2: Clamp explicit Telnyx call limits

**Files:**
- Modify: `apps/life-manager/lib/call-logic.js:337-357`
- Modify: `apps/life-manager/lib/lm-p0.test.js`

**Interfaces:**
- Consumes: `telnyxDialBody({ connectionId, to, from, streamUrl, timeLimitSecs? })`
- Produces: Telnyx `/v2/calls` JSON with absent `time_limit_secs` or an integer `>= 30`

- [ ] **Step 1: Add the failing body-contract tests**

```js
test("Telnyx dial clamps explicit limits to the provider minimum", () => {
  const base = { connectionId: "c", to: "+1", from: "+2", streamUrl: "wss://x" };
  assert.equal(telnyxDialBody({ ...base, timeLimitSecs: 29 }).time_limit_secs, 30);
  assert.equal(telnyxDialBody({ ...base, timeLimitSecs: 30 }).time_limit_secs, 30);
  assert.equal(telnyxDialBody({ ...base, timeLimitSecs: 90.9 }).time_limit_secs, 90);
});

test("Telnyx dial omits an absent or invalid call limit", () => {
  const base = { connectionId: "c", to: "+1", from: "+2", streamUrl: "wss://x" };
  assert.equal("time_limit_secs" in telnyxDialBody(base), false);
  assert.equal("time_limit_secs" in telnyxDialBody({ ...base, timeLimitSecs: "bad" }), false);
});
```

- [ ] **Step 2: Run the focused test and observe RED**

Run: `cd apps/life-manager && node --test lib/lm-p0.test.js`
Expected: FAIL because `time_limit_secs` is absent for `29`.

- [ ] **Step 3: Implement the shared clamp**

```js
function telnyxDialBody({ connectionId, to, from, streamUrl, timeLimitSecs }) {
  const limit = Number(timeLimitSecs);
  return {
    connection_id: connectionId,
    to,
    from,
    stream_url: streamUrl,
    stream_track: "inbound_track",
    stream_bidirectional_mode: "rtp",
    stream_bidirectional_codec: "PCMU",
    stream_bidirectional_target_legs: "self",
    ...(Number.isFinite(limit) ? { time_limit_secs: Math.max(30, Math.trunc(limit)) } : {}),
  };
}
```

- [ ] **Step 4: Run focused and adjacent call tests**

Run: `cd apps/life-manager && node --test lib/lm-p0.test.js lib/dial.test.js test/testcall-amd-hangup.test.js test/testcall-amd-hangup-http-contract.test.js`
Expected: all PASS.

- [ ] **Step 5: Route the observed producer through the shared builder**

If Task 1 found a direct raw `/calls` body, replace that construction with `telnyxDialBody(...)` and add its exact calling test to this task. If it found deployment drift, no second implementation is added; deploying current main plus this shared guard is the repair.

- [ ] **Step 6: Commit and push**

```bash
git add apps/life-manager/lib/call-logic.js apps/life-manager/lib/lm-p0.test.js
git commit -m "fix(life-manager): clamp Telnyx call time limit"
git push -u origin HEAD
```

### Task 3: Deploy and prove the call repair

**Files:**
- Create: `docs/evidence/life-manager-mental-canary.md`

**Interfaces:**
- Consumes: merged Tasks 1–2 commits and Railway main deployment
- Produces: successful Railway deployment `commitHash` plus one real Telnyx call-control receipt

- [ ] **Step 1: Merge the Telnyx repair only after focused tests pass**

Run the repository's existing PR creation and `--admin` merge path. Record PR URL and merge SHA in the evidence document.

- [ ] **Step 2: Observe the Railway deployment created from merged `main`**

Run: `cd apps/life-manager && railway deployment list --json`
Wait for the deployment whose `commitHash` equals the merge SHA to reach `SUCCESS`. A successful deployment for an older SHA does not pass.

- [ ] **Step 3: Verify the exact Railway service role**

Read `LM_DEPLOYMENT_ROLE` only as a redacted role value through Railway metadata and confirm whether the caller is the web/call service or worker. Do not redeploy or restart sibling services.

- [ ] **Step 4: Place one authorized real test call**

Expected evidence:

```text
HTTP /v2/calls accepted
call_control_id is non-empty
error 90029 absent
Railway deployment commitHash equals merged main SHA
```

- [ ] **Step 5: Re-read provider and service state**

Record Telnyx call ID, terminal call state, Railway deployment SHA, and one retry/replay check proving no duplicate call.

- [ ] **Step 6: Commit and push the evidence**

```bash
git add docs/evidence/life-manager-mental-canary.md
git commit -m "docs(life-manager): prove Telnyx call limit repair"
git push
```

## Milestone 2: Establish current cloud MENTAL truth

### Task 4: Audit loaded cloud wiring before changing behavior

**Files:**
- Modify: `docs/evidence/life-manager-mental-canary.md`

**Interfaces:**
- Consumes: current cloud worker deployment, database schema, scheduler logs, Dais tenant preferences
- Produces: PASS/FAIL table for runtime prerequisites

- [ ] **Step 1: Read the loaded deployment SHA and command**

Record the Railway/cloud worker deployment commit and the command that starts `internal-worker`.

- [ ] **Step 2: Verify the loaded source contains MENTAL wiring**

Confirm the loaded artifact includes calls to `mentalUserOnce`, `mentalDeps`, `readMentalSendState`, and `recordMentalSend`.

- [ ] **Step 3: Verify the production table and constraints**

Read `lm_mental_send_log` schema and confirm the existing unique/dedup and append-only protections. Do not write test data during this step.

- [ ] **Step 4: Verify Dais eligibility and configuration without exposing secrets**

Record only booleans or redacted values for:

```text
daily_automation_enabled
notifications_enabled
telegram_chat_id present
LM_MENTAL_SLEEP_TARGET parseable
user timezone/offset source
Telegram token present
```

- [ ] **Step 5: Read one natural tick**

Capture one `organ:mental` timing receipt and its terminal decision or suppression reason. Source wiring without a natural tick is FAIL.

- [ ] **Step 6: Update evidence and commit**

```bash
git add docs/evidence/life-manager-mental-canary.md
git commit -m "docs(life-manager): record cloud mental runtime truth"
git push
```

## Milestone 3: Expand pure trigger decisions

### Task 5: Add shared gates and eight intent decisions

**Files:**
- Modify: `apps/life-manager/lib/mental-trigger.js`
- Modify: `apps/life-manager/lib/mental-trigger.test.js`

**Interfaces:**
- Consumes: `evaluateMentalTrigger(input: MentalTriggerInput)` with existing time/event/send fields and new `quietHours`, `recentSignals`, and `preferences`
- Produces: `{ decision: "send", intent, reason, facts }` or `{ decision: "suppress", reason }`

- [ ] **Step 1: Add RED tests for global suppression gates**

Add table-driven cases asserting suppression for:

```js
[
  ["muted", { preferences: { mutedUntilMs: NOW + 1 } }],
  ["quiet-hours", { quietHours: { start: "22:30", end: "07:30" } }],
  ["daily-cap-reached", { sentTodayCount: 3 }],
  ["too-soon-after-last", { lastSentMs: NOW - 30 * 60_000 }],
  ["mid-event", { events: [{ startMs: NOW - 1, endMs: NOW + 1, important: true, intense: false, summary: "x" }] }],
  ["user-moving", { location: { state: "moving" } }],
];
```

- [ ] **Step 2: Add RED tests for all eight send intents and priority**

Create one grounded case each for `pre_event`, `post_strain`, `mindful_pause`, `small_win`, `self_compassion`, `intention`, `pre_sleep`, and `physical_reset`. Add one collision case where `self_compassion` wins over `pre_event`.

- [ ] **Step 3: Run the trigger tests and observe RED**

Run: `cd apps/life-manager && node --test lib/mental-trigger.test.js`
Expected: FAIL on new input keys/intents.

- [ ] **Step 4: Extend validation with closed key sets**

Define and export:

```js
const INTENTS = Object.freeze([
  "pre_event", "post_strain", "mindful_pause", "small_win",
  "self_compassion", "intention", "pre_sleep", "physical_reset",
]);
const INTENT_PRIORITY = Object.freeze([
  "self_compassion", "pre_event", "physical_reset", "post_strain",
  "mindful_pause", "small_win", "intention", "pre_sleep",
]);
```

Reject unknown keys and invalid enums before evaluating decisions.

- [ ] **Step 5: Implement smallest candidate-list evaluator**

Each intent appends either zero or one `{ intent, reason, facts }` candidate. Select the first candidate by `INTENT_PRIORITY`. Do not introduce classes, plugins, or a rule engine.

- [ ] **Step 6: Run trigger tests GREEN**

Run: `cd apps/life-manager && node --test lib/mental-trigger.test.js`
Expected: all PASS.

- [ ] **Step 7: Commit and push**

```bash
git add apps/life-manager/lib/mental-trigger.js apps/life-manager/lib/mental-trigger.test.js
git commit -m "feat(life-manager): expand contextual mental intents"
git push
```

## Milestone 4: Grounded Japanese copy

### Task 6: Replace hash-only stances with structured intent templates

**Files:**
- Modify: `apps/life-manager/lib/mental-copy.js`
- Modify: `apps/life-manager/lib/mental-copy.test.js`

**Interfaces:**
- Consumes: `buildMentalMessage({ intent, facts, templateIndex? })`
- Produces: `{ text, templateId }` satisfying `validateMentalMessage(text, facts)`

- [ ] **Step 1: Add RED exact-output tests for one template per intent**

Use deterministic facts:

```js
const FACTS = {
  eventName: "14時の発表",
  completedCount: 3,
  completedItem: "提案書",
  goalName: "英語で発表すること",
  nextAction: "冒頭の一文を開くこと",
  sittingMinutes: 90,
};
```

Assert exact Japanese output and stable `templateId` for all eight intents.

- [ ] **Step 2: Add RED safety tests**

Reject messages containing question marks, reply requests, more than one emoji, more than 120 characters, unsupported placeholders, destiny/guarantee phrases, diagnosis terms, or facts absent from the supplied fact object.

- [ ] **Step 3: Run copy tests and observe RED**

Run: `cd apps/life-manager && node --test lib/mental-copy.test.js`.

- [ ] **Step 4: Add the structured Japanese template bank**

Use a frozen object:

```js
const JA_TEMPLATES = Object.freeze({
  pre_event: Object.freeze([
    Object.freeze({ id: "ja.pre_event.01", text: "必要なものは持ってきています。あとは最初の一文を、ゆっくり話すだけです。" }),
  ]),
  post_strain: Object.freeze([
    Object.freeze({ id: "ja.post_strain.01", text: "連続した予定をここまで終えました。次の10分は、水と呼吸に使っていい時間です。" }),
  ]),
  mindful_pause: Object.freeze([
    Object.freeze({ id: "ja.mindful_pause.01", text: "いま息を一度、吸うより長く吐きます。次に触るものは一つだけで十分です。" }),
  ]),
  small_win: Object.freeze([
    Object.freeze({ id: "ja.small_win.01", text: "今日はすでに{completedCount}件を終えています。進んでいないという感覚より、この事実を残します。" }),
  ]),
  self_compassion: Object.freeze([
    Object.freeze({ id: "ja.self_compassion.01", text: "{eventName}がうまくいかなかったことと、あなた自身の価値は別です。修正を一つ選べば十分です。" }),
  ]),
  intention: Object.freeze([
    Object.freeze({ id: "ja.intention.01", text: "{goalName}を望む気持ちは、今日の一動作に変えられます。まず{nextAction}から始めます。" }),
  ]),
  pre_sleep: Object.freeze([
    Object.freeze({ id: "ja.pre_sleep.01", text: "🌙 今日はここまでで十分です。未完了は失敗ではなく、明日の続きです。" }),
  ]),
  physical_reset: Object.freeze([
    Object.freeze({ id: "ja.physical_reset.01", text: "{sittingMinutes}分座っています。立って10歩だけ歩く時間です。" }),
  ]),
});
```

Every placeholder must have an explicit formatter and maximum length. Event/goal/item text is single-line and truncated before interpolation.

- [ ] **Step 5: Return text and template identity together**

```js
function buildMentalMessage({ intent, facts = {}, templateIndex = 0 }) {
  const templates = JA_TEMPLATES[intent];
  if (!templates) throw new Error(`unknown mental intent ${String(intent)}`);
  const template = templates[templateIndex % templates.length];
  const text = renderTemplate(template.text, facts);
  const verdict = validateMentalMessage(text, facts);
  if (!verdict.ok) throw new Error(`invalid mental message: ${verdict.reason}`);
  return { text, templateId: template.id };
}
```

- [ ] **Step 6: Run copy tests GREEN**

Run: `cd apps/life-manager && node --test lib/mental-copy.test.js`.

- [ ] **Step 7: Generate and inspect the sample matrix**

Generate at least three grounded samples per intent. Confirm no invented personal detail, guarantee, diagnosis, or question.

- [ ] **Step 8: Commit and push**

```bash
git add apps/life-manager/lib/mental-copy.js apps/life-manager/lib/mental-copy.test.js
git commit -m "feat(life-manager): add grounded Japanese care messages"
git push
```

## Milestone 5: Durable intent receipts and feedback

### Task 7: Extend the mental send ledger

**Files:**
- Create: `apps/life-manager/migrations/2026-09-16-lm-mental-intents-feedback.sql`
- Create: `apps/life-manager/lib/mental-migration.test.js`
- Modify: `apps/life-manager/lib/mental-send-log.js`
- Modify: `apps/life-manager/lib/mental-send-log.test.js`

**Interfaces:**
- Consumes: `recordMentalSend(uid, intent, messageId, { templateId, contextFingerprint, feedbackKey }, supa)`
- Produces: append-only send row with deterministic feedback target

- [ ] **Step 1: Add RED migration contract tests**

Assert the migration adds non-empty `intent`, `template_id`, a 64-character lowercase hex `context_fingerprint`, and a unique 22-character base64url `feedback_key`; permits nullable `feedback` and `feedback_at`; restricts feedback to `effective|not_for_me|mute_today`; and preserves append-only identity fields.

- [ ] **Step 2: Write the additive migration**

Use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, backfill historical rows with explicit `legacy` values, then apply `NOT NULL` and checks. Do not delete or rewrite existing receipts.

- [ ] **Step 3: Add RED store tests**

Cover strict unreadable-state suppression, successful append, malformed fingerprint/key rejection, duplicate Telegram message ID idempotency, duplicate feedback-key rejection, feedback update, and duplicate feedback replay.

- [ ] **Step 4: Implement the minimal store changes**

Keep existing Supabase REST helpers. Add no ORM and no repository abstraction.

- [ ] **Step 5: Run migration and store tests**

Run: `cd apps/life-manager && node --test lib/mental-migration.test.js lib/mental-send-log.test.js`.

- [ ] **Step 6: Commit and push**

```bash
git add apps/life-manager/migrations/2026-09-16-lm-mental-intents-feedback.sql apps/life-manager/lib/mental-migration.test.js apps/life-manager/lib/mental-send-log.js apps/life-manager/lib/mental-send-log.test.js
git commit -m "feat(life-manager): record mental intent and feedback identity"
git push
```

### Task 8: Add three feedback callbacks

**Files:**
- Create: `apps/life-manager/lib/mental-feedback.js`
- Create: `apps/life-manager/lib/mental-feedback.test.js`
- Modify: `apps/life-manager/server.js`

**Interfaces:**
- Consumes: callback payload `mental:<feedbackKey>:e|n|m`
- Produces: one idempotent feedback update and optional `muted_until` preference change

- [ ] **Step 1: Add RED parser and authorization tests**

Require exact callback grammar, a 22-character base64url feedback key, matching Telegram chat/user ownership from the keyed ledger row, and one of the three closed action codes. Unrelated callbacks return `handled: false`.

- [ ] **Step 2: Add RED replay tests**

The same callback update ID twice must perform one durable update and one callback acknowledgment, with no second preference mutation.

- [ ] **Step 3: Implement pure parsing and bounded handler**

Export `parseMentalFeedback(data)` and `handleMentalFeedback(input, deps)`. Reuse existing Telegram callback acknowledgment and runtime-preference update functions.

- [ ] **Step 4: Wire the handler before generic callback routing**

In `server.js`, route only callbacks beginning with `mental:` to the new handler. Preserve every existing callback path unchanged.

- [ ] **Step 5: Run feedback and existing callback tests**

Run: `cd apps/life-manager && node --test lib/mental-feedback.test.js test/telegram-callback-http-contract.test.js lib/precepts-runtime.test.js`.

- [ ] **Step 6: Commit and push**

```bash
git add apps/life-manager/lib/mental-feedback.js apps/life-manager/lib/mental-feedback.test.js apps/life-manager/server.js
git commit -m "feat(life-manager): collect mental message feedback"
git push
```

## Milestone 6: Runtime and scheduler wiring

### Task 9: Compose grounded context and deliver validated messages

**Files:**
- Modify: `apps/life-manager/lib/mental-runtime.js`
- Modify: `apps/life-manager/lib/mental-runtime.test.js`
- Modify: `apps/life-manager/scheduler.js`
- Create: `apps/life-manager/lib/mental-wiring.test.js`

**Interfaces:**
- Consumes: trigger verdict `{ intent, reason, facts }` and structured scheduler signals
- Produces: delivered Telegram message plus ledger identity, or explicit suppression/failure result

- [ ] **Step 1: Add RED runtime tests**

Cover:

```text
trigger suppression performs zero Telegram and zero write
valid intent sends exact validated text
Telegram failure performs zero send-log write
send success plus ledger failure returns reconciliation_required with Telegram message ID
unreadable strict ledger suppresses
same context fingerprint already sent suppresses replay
```

- [ ] **Step 2: Add RED wiring tests**

Prove the scheduler supplies real `nowMs` to bedtime resolution, user timezone rather than fleet-wide default when present, sanitized event summary, recent completion/failure signals, and Dais canary cap. Prove a MENTAL failure does not block wake, care, diet, or precepts siblings.

- [ ] **Step 3: Implement canonical context fingerprinting**

Use Node `crypto.createHash("sha256")` over stable JSON containing only intent-relevant non-secret fields. Sort object keys deterministically. Do not hash raw credentials, message bodies, coordinates, or journal text.

- [ ] **Step 4: Update runtime delivery order**

Required order:

```text
read strict attention state
evaluate trigger
build and validate copy
check context replay
create randomBytes(16) base64url feedback key
send Telegram with compact feedback callbacks
record receipt with the same feedback key
return terminal outcome
```

- [ ] **Step 5: Add inline feedback buttons using Task 8**

Generate `feedbackKey = crypto.randomBytes(16).toString("base64url")` before delivery and build exactly three callback buttons: `効いた` -> `mental:${feedbackKey}:e`, `合わない` -> `mental:${feedbackKey}:n`, `今日は静かに` -> `mental:${feedbackKey}:m`. After delivery, persist the same key with the Telegram message ID. If persistence fails, return `reconciliation_required` with both values and never resend blindly.

- [ ] **Step 6: Run focused runtime and wiring tests**

Run: `cd apps/life-manager && node --test lib/mental-runtime.test.js lib/mental-wiring.test.js lib/mental-trigger.test.js lib/mental-copy.test.js lib/mental-send-log.test.js lib/precepts-wiring.test.js`.

- [ ] **Step 7: Run the Life Manager test command**

Read `apps/life-manager/package.json` and run its canonical full test script. Expected: zero failures.

- [ ] **Step 8: Commit and push**

```bash
git add apps/life-manager/lib/mental-runtime.js apps/life-manager/lib/mental-runtime.test.js apps/life-manager/scheduler.js apps/life-manager/lib/mental-wiring.test.js
git commit -m "feat(life-manager): wire grounded mental care context"
git push
```

## Milestone 7: Cloud deployment and Dais-only canary

### Task 10: Apply migration and deploy the cloud worker

**Files:**
- Modify: `docs/evidence/life-manager-mental-canary.md`

**Interfaces:**
- Consumes: merged main SHA containing Tasks 5–9
- Produces: migrated production schema and successful Railway worker deployment with exact `commitHash` readback

- [ ] **Step 1: Merge only after all focused and full tests pass**

Create one PR for the mental behavior milestones. Use the repository-required merge path and record the PR URL and merge SHA.

- [ ] **Step 2: Apply the additive migration**

Run the existing production migration mechanism. Read the resulting columns and constraints back from production.

- [ ] **Step 3: Observe the Railway worker deployment from the merge SHA**

Run: `cd apps/life-manager && railway deployment list --json`. Require the worker service deployment with the exact merge `commitHash` to reach `SUCCESS`, then verify startup logs show `node scripts/runtime-up.js internal-worker` and no dependency/import failure.

- [ ] **Step 4: Configure Dais-only canary**

Set the existing runtime-preference or cohort gate so only the Dais tenant receives expanded intents. Configure care cap `2`; retain shared MENTAL/precepts hard cap `3`.

- [ ] **Step 5: Verify only the named cloud worker owner**

Read back deployment ID, `commitHash`, start command, process health, and one natural `organ:mental` tick. Do not redeploy the web/call service unless its artifact also changed in the merged commit.

- [ ] **Step 6: Record deployment evidence and push**

```bash
git add docs/evidence/life-manager-mental-canary.md
git commit -m "docs(life-manager): record mental canary deployment"
git push
```

### Task 11: Complete the seven-day Japanese canary

**Files:**
- Modify: `docs/evidence/life-manager-mental-canary.md`

**Interfaces:**
- Consumes: seven local days of cloud outcomes
- Produces: rollout decision backed by message receipts, feedback, suppressions, and replay-zero

- [ ] **Step 1: Record each day's natural outcomes**

For every day record counts only, with private content redacted:

```text
eligible ticks by intent
suppression reasons
delivered Telegram message IDs
template IDs
context fingerprints
feedback values
shared daily cap usage
```

- [ ] **Step 2: Stage only missing acceptance intents**

If natural context does not produce required coverage by day 6, create a reversible test calendar event or explicit test completion/failure signal for Dais. Label it as staged and remove it after receipt. Do not fabricate a production outcome.

- [ ] **Step 3: Verify daily cap and quiet behavior**

For all seven days assert care sends `<= 2`, shared MENTAL/precepts sends `<= 3`, quiet-hour sends `0`, mid-event sends `0`, and moving sends `0`.

- [ ] **Step 4: Verify replay-zero**

Replay at least one already-processed context/tick through the same owner. Expected: zero additional Telegram message IDs and a durable duplicate/suppression result.

- [ ] **Step 5: Make the rollout decision**

Pass only if:

```text
0 invented-fact incidents
0 duplicate sends
0 cap violations
0 quiet/mid-event/moving violations
>= 1 pre_event receipt
>= 1 mindful_pause or physical_reset receipt
>= 1 self_compassion or small_win receipt
all provider message IDs read back successfully
```

- [ ] **Step 6: Commit and push final canary evidence**

```bash
git add docs/evidence/life-manager-mental-canary.md
git commit -m "docs(life-manager): close Japanese mental care canary"
git push
```

## Milestone 8: Localization and Anicca iOS reuse

### Task 12: Promote measured intents to shared catalogs

**Files:**
- Modify only after canary PASS: `anicca-project/apps/api/src/modules/affirmations/catalog/ja.json`
- Modify only after canary PASS: locale sibling catalogs selected by product priority
- Modify only if the iOS app still embeds a separate bank: `anicca-project/mobile-apps/rork-thankful-gratitude-app/ThankfulGratitudeApp/Models/AffirmationData.swift`
- Test: existing affirmation catalog/API tests in `anicca-project`

**Interfaces:**
- Consumes: canary-approved intent stances and template IDs
- Produces: locale-native affirmation catalog entries; no cloud runtime dependency added to iOS

- [ ] **Step 1: Select only measured templates**

Include templates with no safety incident and no `not_for_me` majority. Strip personal facts and placeholders before promotion to the generic iOS catalog.

- [ ] **Step 2: Add Japanese catalog tests before catalog changes**

Assert stable IDs, non-empty text, locale match, duplicate-free entries, and absence of guarantee/diagnosis phrases.

- [ ] **Step 3: Add Japanese catalog entries**

Map the approved stances into the existing schema. Do not introduce a second catalog format.

- [ ] **Step 4: Localize semantic intent, not Japanese wording**

For each locale, write native copy preserving the intent and action contract. Do not machine-copy Japanese sentence structure.

- [ ] **Step 5: Remove embedded duplication only if the existing app loading path supports the API catalog**

If the iOS app cannot yet consume the API catalog, leave `AffirmationData.swift` intact and record the duplication as a bounded follow-up. Do not build a sync framework in this task.

- [ ] **Step 6: Run catalog/API and focused iOS tests**

Run: `cd /Users/anicca/anicca-project/apps/api && npm test -- src/modules/affirmations`
Run: `cd /Users/anicca/anicca-project/mobile-apps/rork-thankful-gratitude-app && xcodebuild test -project ThankfulGratitudeApp.xcodeproj -scheme ThankfulGratitudeApp -destination 'platform=iOS Simulator,name=iPhone 16 Pro' -only-testing:ThankfulGratitudeAppTests`
Expected: all related tests PASS. If the named simulator is unavailable, select the first installed iPhone simulator from `xcrun simctl list devices available` and record its exact destination; do not skip the iOS test.

- [ ] **Step 7: Commit and push in the Anicca repository**

```bash
git add apps/api/src/modules/affirmations/catalog mobile-apps/rork-thankful-gratitude-app/ThankfulGratitudeApp/Models/AffirmationData.swift
git commit -m "feat(affirmations): promote measured mental care messages"
git push -u origin HEAD
```

## Final verification checklist

- [ ] Telnyx real call receipt proves error `90029` is gone.
- [ ] Loaded cloud worker SHA equals the merged main SHA.
- [ ] Production migration readback matches the checked-in migration.
- [ ] Focused mental tests and canonical Life Manager full tests pass.
- [ ] Seven-day Dais canary meets every quantitative acceptance condition.
- [ ] Replay of processed context produces zero duplicate Telegram effects.
- [ ] No sibling loop or unrelated owner was restarted.
- [ ] Japanese rollout decision is recorded before localization begins.
- [ ] Anicca iOS reuses approved stances without adding a parallel cloud generator.
