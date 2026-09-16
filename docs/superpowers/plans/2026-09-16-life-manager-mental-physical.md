# Life Manager Mental Messages V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Follow the tasks in order and preserve checkbox state.

**Goal:** Repair Telnyx call-limit rejection and ship Japanese affirmation, manifestation, and mindfulness-inquiry messages that never invent personal context.

**Architecture:** The Telnyx repair ships independently through the actual observed `/calls` producer. Mental V1 reuses `scheduler.js -> mentalUserOnce -> evaluateMentalTrigger -> buildMentalMessage -> Telegram -> lm_mental_send_log`; context is used first to avoid interruption, while copy uses only context-free templates or explicit stable user preferences.

**Tech Stack:** Node.js CommonJS, `node:test`, Supabase/Postgres REST, Telegram Bot API, Telnyx Call Control, Railway.

**Spec:** `docs/superpowers/specs/2026-09-16-life-manager-mental-physical-design.md`

## Global constraints

- Reuse the existing scheduler, Telegram transport, send ledger, runtime preferences, and Railway deployment path.
- Do not add a daemon, scheduler, database, queue, feedback UI, inline keyboard, or LLM framework.
- V1 enables only `affirmation`, `manifestation`, and `mindfulness_inquiry`.
- Messages are plain Telegram text with zero buttons, zero callback data, and zero reply instruction.
- Maximum two V1 messages per local day and minimum four hours between them.
- Calendar context is used only to suppress delivery during an event.
- No preparation, achievement, emotion, activity, hydration, posture, or physical-state claim without an exact authoritative source.
- A template variable is legal only with a source, timestamp, freshness limit, transformation, and matching claim.
- Railway production truth is the deployment `commitHash`, live service logs, Telegram message ID, durable send row, and replay-zero.

## File map

| File | Responsibility |
|---|---|
| `apps/life-manager/lib/call-logic.js` | Shared Telnyx dial-body boundary |
| `apps/life-manager/lib/lm-p0.test.js` | Telnyx minimum contract |
| `apps/life-manager/lib/mental-trigger.js` | Right-window opportunity and suppression gates |
| `apps/life-manager/lib/mental-trigger.test.js` | Three-family decision matrix |
| `apps/life-manager/lib/mental-copy.js` | Deterministic Japanese message bank and validation |
| `apps/life-manager/lib/mental-copy.test.js` | Exact copy and forbidden-claim tests |
| `apps/life-manager/lib/mental-runtime.js` | Select, send, and record one plain message |
| `apps/life-manager/lib/mental-runtime.test.js` | Delivery, failure, and no-button contracts |
| `apps/life-manager/lib/mental-send-log.js` | Cap, spacing, 14-day template dedupe, receipt |
| `apps/life-manager/lib/mental-send-log.test.js` | Strict history and replay tests |
| `apps/life-manager/scheduler.js` | Timezone, busy-state, quiet-hours, explicit preferences |
| `apps/life-manager/lib/mental-wiring.test.js` | Scheduler wiring and sibling isolation |
| `apps/life-manager/migrations/2026-09-16-lm-mental-message-family.sql` | Family/template/local-day/window fields |
| `apps/life-manager/lib/mental-migration.test.js` | Additive schema contract |
| `docs/evidence/life-manager-mental-canary.md` | Production truth and seven-day canary |

---

## Milestone 1: Repair Telnyx 422 independently

### Task 1: Locate the actual `time_limit_secs` producer

**Files:**
- Create: `docs/evidence/life-manager-mental-canary.md`

**Produces:** Exact service, deployment SHA, producer, sanitized bad value, and comparison with current `main`.

- [ ] Add this incident table to the evidence file:

```markdown
| Field | Observed value | PASS condition |
|---|---|---|
| Railway service | | exact service name |
| Deployment commitHash | | 40-character SHA |
| Request producer | | exact file/function or external tool |
| Sanitized time_limit_secs | | numeric value only |
| Current-main comparison | | same path, deployment drift, or second producer |
```

- [ ] Read deployment metadata without printing variables:

```bash
cd apps/life-manager
railway status --json
railway deployment list --json
```

- [ ] Read the bounded failure window:

```bash
railway logs --service life-call \
  --since 2026-09-16T07:58:00+09:00 \
  --until 2026-09-16T08:06:00+09:00
```

- [ ] Set `DEPLOYED_SHA` to the observed `commitHash` and compare paths:

```bash
git show "$DEPLOYED_SHA":apps/life-manager/lib/call-logic.js | rg -n 'time_limit_secs|telnyxDialBody'
git show "$DEPLOYED_SHA":apps/life-manager/lib/dial.js | rg -n 'time_limit_secs|telnyxDialBody|/calls'
rg -n 'time_limit_secs|telnyxDialBody|/v2/calls' apps/life-manager --glob '!node_modules'
```

- [ ] Stop unless the producer is proven as deployed drift, an exact second code path, or an exact external call tool.

- [ ] Commit and push the sanitized evidence.

### Task 2: Clamp the verified producer at the shared boundary

**Files:**
- Modify: `apps/life-manager/lib/call-logic.js`
- Modify: `apps/life-manager/lib/lm-p0.test.js`
- Modify the exact second producer only if Task 1 proves one exists.

**Interface:**

```js
telnyxDialBody({ connectionId, to, from, streamUrl, timeLimitSecs })
```

- [ ] Add RED tests:

```js
test("explicit Telnyx limits are integer and at least 30", () => {
  const base = { connectionId: "c", to: "+1", from: "+2", streamUrl: "wss://x" };
  assert.equal(telnyxDialBody({ ...base, timeLimitSecs: 29 }).time_limit_secs, 30);
  assert.equal(telnyxDialBody({ ...base, timeLimitSecs: 30 }).time_limit_secs, 30);
  assert.equal(telnyxDialBody({ ...base, timeLimitSecs: 90.9 }).time_limit_secs, 90);
  assert.equal("time_limit_secs" in telnyxDialBody(base), false);
  assert.equal("time_limit_secs" in telnyxDialBody({ ...base, timeLimitSecs: "bad" }), false);
});
```

- [ ] Run RED:

```bash
cd apps/life-manager
node --test lib/lm-p0.test.js
```

- [ ] Implement only the shared clamp:

```js
const limit = Number(timeLimitSecs);
const safeLimit = Number.isFinite(limit) ? Math.max(30, Math.trunc(limit)) : null;
```

Include `time_limit_secs` only when `safeLimit !== null`.

- [ ] Run focused call tests:

```bash
node --test \
  lib/lm-p0.test.js \
  lib/dial.test.js \
  test/testcall-amd-hangup.test.js \
  test/testcall-amd-hangup-http-contract.test.js
```

- [ ] Commit, push, merge, and wait for the Railway deployment whose `commitHash` equals merged `main`.

- [ ] Place one authorized real test call. Record non-empty `call_control_id`, terminal provider state, absence of `90029`, and replay-zero.

---

## Milestone 2: Prove current mental-runtime inputs

### Task 3: Audit what production can truthfully know

**Files:**
- Modify: `docs/evidence/life-manager-mental-canary.md`

- [ ] Record the worker service deployment ID, `commitHash`, start command, and health.

- [ ] Read back the production `lm_mental_send_log` schema and constraints.

- [ ] Record only redacted/boolean results for:

```text
timezone source present and parseable
calendar read available
notifications enabled
Telegram chat id present
Telegram token present
quiet-hours preference available
explicit values/goals profile available
```

- [ ] Record current unsupported inputs as absent unless proven:

```text
preparation receipt
completed-action count
mood input
focus-duration measurement
hydration state
posture or sitting duration
explicit important-event classification
```

- [ ] Capture one natural `organ:mental` tick and its exact terminal decision.

- [ ] Commit and push the audit. This audit is the boundary for all later copy claims.

---

## Milestone 3: Implement right-window opportunity gates

### Task 4: Replace event-story triggers with three V1 families

**Files:**
- Modify: `apps/life-manager/lib/mental-trigger.js`
- Modify: `apps/life-manager/lib/mental-trigger.test.js`

**Consumes:**

```js
{
  nowMs,
  utcOffsetHours,
  events: [{ startMs, endMs }],
  sentTodayCount,
  lastSentMs,
  sentFamiliesToday,
  quietHours,
  recentTemplateIds,
  explicitPreferences
}
```

**Produces:**

```js
{ decision: "send", family, window, localDay }
// or
{ decision: "suppress", reason }
```

- [ ] Add RED suppression tests for invalid timezone, calendar unavailable, current event, quiet hours, two-message cap, four-hour gap, family already used, and no eligible template.

- [ ] Add RED send cases:

```text
07:30–10:00 -> affirmation or manifestation
12:00–16:00 -> mindfulness_inquiry
20:00–23:00 -> affirmation or mindfulness_inquiry
```

- [ ] Add a deterministic-per-user/day/window minute test. The same input must return the same minute; different users may differ.

- [ ] Run RED:

```bash
cd apps/life-manager
node --test lib/mental-trigger.test.js
```

- [ ] Define the only V1 families:

```js
const FAMILIES = Object.freeze([
  "affirmation",
  "manifestation",
  "mindfulness_inquiry",
]);
```

- [ ] Delete `pre_event`, `between_events`, and context claims from the V1 decision path. Calendar events become suppression inputs only.

- [ ] Implement local-day/window calculation with existing timezone helpers. Do not create a scheduling framework.

- [ ] Run GREEN and commit:

```bash
node --test lib/mental-trigger.test.js
git add lib/mental-trigger.js lib/mental-trigger.test.js
git commit -m "feat(life-manager): gate context-light mental messages"
git push
```

---

## Milestone 4: Build the Japanese plain-message bank

### Task 5: Add deterministic affirmation, manifestation, and inquiry copy

**Files:**
- Modify: `apps/life-manager/lib/mental-copy.js`
- Modify: `apps/life-manager/lib/mental-copy.test.js`

**Interface:**

```js
buildMentalMessage({ family, templateIndex, explicitGoal })
// -> { text, templateId }
```

- [ ] Add exact-output RED tests for all messages listed in spec sections 7.1–7.3.

- [ ] Add RED rejection tests for:

```text
more than 80 Japanese characters
inline keyboard or callback payload in the returned value
reply-seeking phrases
unsupported template variable
numeric personal achievement
preparation claim
activity-duration claim
emotion claim
diagnosis or guaranteed outcome
```

- [ ] Prove that `？` is legal only for `mindfulness_inquiry`; `返信して`, `教えて`, `答えて`, `押して`, and `選んで` remain illegal in every family.

- [ ] Run RED:

```bash
cd apps/life-manager
node --test lib/mental-copy.test.js
```

- [ ] Implement frozen `JA_TEMPLATES` arrays with stable IDs such as:

```js
const JA_TEMPLATES = Object.freeze({
  affirmation: Object.freeze([
    Object.freeze({ id: "ja.affirmation.01", text: "そのままの自分で、今日を始めていい。" }),
    Object.freeze({ id: "ja.affirmation.02", text: "全部を完璧にしなくても、価値は減らない。" }),
  ]),
  manifestation: Object.freeze([
    Object.freeze({ id: "ja.manifestation.01", text: "望む未来は、今日の小さな選択から形になる。" }),
    Object.freeze({ id: "ja.manifestation.02", text: "未来を保証する必要はない。向かう方向は、いま選べる。" }),
  ]),
  mindfulness_inquiry: Object.freeze([
    Object.freeze({ id: "ja.mindfulness.01", text: "いま、何に意識を使っている？" }),
    Object.freeze({ id: "ja.mindfulness.02", text: "いまの呼吸は、浅い？ 深い？" }),
  ]),
});
```

Add every remaining exact message from the spec, not generated variations.

- [ ] Permit `{goal}` only when `explicitGoal` is non-empty, user-authored, single-line, and length-bounded. Otherwise select a context-free manifestation.

- [ ] Run GREEN and commit:

```bash
node --test lib/mental-copy.test.js
git add lib/mental-copy.js lib/mental-copy.test.js
git commit -m "feat(life-manager): add Japanese mental message bank"
git push
```

---

## Milestone 5: Extend send receipts without feedback UI

### Task 6: Record family, template, day, and window

**Files:**
- Create: `apps/life-manager/migrations/2026-09-16-lm-mental-message-family.sql`
- Create: `apps/life-manager/lib/mental-migration.test.js`
- Modify: `apps/life-manager/lib/mental-send-log.js`
- Modify: `apps/life-manager/lib/mental-send-log.test.js`

**Interface:**

```js
recordMentalSend(uid, messageId, { family, templateId, localDay, window }, supa)
```

- [ ] Add RED migration tests for closed family values, non-empty template ID, valid local day, closed window, and append-only preservation.

- [ ] Write an additive migration. Backfill historical rows with `legacy` values; do not delete or rewrite receipts.

- [ ] Add RED store tests for strict unreadable-history failure, two-message cap, four-hour gap, same-family/day lookup, 14-day template lookup, duplicate Telegram message ID, and replay of the same user/day/window.

- [ ] Implement with existing Supabase REST helpers. Add no ORM and no feedback fields.

- [ ] Run and commit:

```bash
cd apps/life-manager
node --test lib/mental-migration.test.js lib/mental-send-log.test.js
git add migrations/2026-09-16-lm-mental-message-family.sql \
  lib/mental-migration.test.js \
  lib/mental-send-log.js \
  lib/mental-send-log.test.js
git commit -m "feat(life-manager): record plain mental message identity"
git push
```

---

## Milestone 6: Wire plain Telegram delivery

### Task 7: Send one message with no buttons or reply contract

**Files:**
- Modify: `apps/life-manager/lib/mental-runtime.js`
- Modify: `apps/life-manager/lib/mental-runtime.test.js`
- Modify: `apps/life-manager/scheduler.js`
- Create: `apps/life-manager/lib/mental-wiring.test.js`

- [ ] Add RED runtime tests proving:

```text
suppress verdict -> zero Telegram, zero row
eligible window -> one exact plain text message
Telegram call has no reply_markup
Telegram call has no callback_data
Telegram call has no sender signature
Telegram failure -> zero row
row failure after delivery -> reconciliation_required with message ID
same user/day/window replay -> zero additional Telegram sends
```

- [ ] Add RED wiring tests proving scheduler provides current `nowMs`, user timezone, event start/end only, quiet hours, explicit preferences, and strict send history.

- [ ] Prove scheduler does not map `location` or `attendees` to `important`, does not map duration to `focused`, and does not supply completed count, mood, hydration, or posture.

- [ ] Required runtime order:

```text
read strict send history
evaluate opportunity gate
select non-repeated template
validate copy and authorized variables
send plain Telegram text
record message ID and template identity
return terminal outcome
```

- [ ] Run focused tests:

```bash
cd apps/life-manager
node --test \
  lib/mental-trigger.test.js \
  lib/mental-copy.test.js \
  lib/mental-send-log.test.js \
  lib/mental-runtime.test.js \
  lib/mental-wiring.test.js \
  lib/precepts-wiring.test.js
```

- [ ] Run the canonical Life Manager test script and require zero failures:

```bash
npm test
```

- [ ] Commit and push.

---

## Milestone 7: Deploy Dais-only Japanese canary

### Task 8: Apply migration and exact Railway deployment

**Files:**
- Modify: `docs/evidence/life-manager-mental-canary.md`

- [ ] Merge only after focused and full tests pass.

- [ ] Apply the additive migration and read columns/constraints back from production.

- [ ] Require the Railway worker deployment with the merge `commitHash` to reach `SUCCESS`.

- [ ] Verify startup logs show `node scripts/runtime-up.js internal-worker` and no import/schema failure.

- [ ] Enable the three V1 families for the Dais tenant only, cap two/day, gap four hours.

- [ ] Read one natural `organ:mental` tick. Record deployment ID, SHA, decision, family/window, template ID, Telegram message ID if sent, and send row ID.

- [ ] Verify the actual Telegram message contains no button, callback, sender signature, reply instruction, or unsupported context claim.

- [ ] Commit and push the deployment evidence.

### Task 9: Close the seven-day canary

**Files:**
- Modify: `docs/evidence/life-manager-mental-canary.md`

- [ ] For each local day record:

```text
eligible windows
suppression reasons
family and template ID
Telegram message ID
durable row ID
daily count and spacing
```

- [ ] Assert across all seven days:

```text
messages per day <= 2
gap >= 4 hours
busy-event sends = 0
quiet-hour sends = 0
buttons/callbacks = 0
reply instructions = 0
unsupported personal claims = 0
same-template repeat within 14 days = 0
duplicate external sends = 0
```

- [ ] Ensure at least one real delivered message from each family. Use a reversible canary preference/window adjustment if natural selection misses a family; do not fabricate user context.

- [ ] Replay one processed user/day/window. Require zero additional Telegram message IDs.

- [ ] Mark V1 PASS only when every condition holds. General rollout remains locked otherwise.

- [ ] Commit and push final evidence.

---

## Future work: context unlocks, one at a time

These are not V1 tasks. Add a separate spec and plan for each:

1. Explicit important-event classification.
2. Event-bound preparation completion receipt.
3. Current-day completed-action receipts.
4. Authorized activity/focus duration.
5. Explicit failure/rejection aftercare.

Each unlock must define source, freshness, transformation, exact legal claim, tests, production readback, and replay-zero. Anicca iOS remains a separate product operated by the mobile-app loop and is not a Life Manager mental-runtime dependency.

## Final verification checklist

- [ ] Telnyx real-call receipt proves `90029` is gone.
- [ ] Railway worker `commitHash` equals merged `main`.
- [ ] Production schema matches the additive migration.
- [ ] V1 has exactly three message families.
- [ ] Every delivered item is plain Telegram text.
- [ ] Seven-day canary has zero unsupported context claims.
- [ ] Cap, spacing, busy suppression, quiet suppression, 14-day dedupe, and replay-zero all pass.
- [ ] No Anicca iOS dependency, feedback UI, or second mental loop was added.
