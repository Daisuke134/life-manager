# Life Manager Mental Messages V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Follow the tasks in order and preserve checkbox state.

**Goal:** Repair Telnyx call-limit rejection, ship natural Japanese-first mental messages, then connect verified Gmail/Calendar outcomes so Life Manager can report what matters and offer the right words at a receptive moment.

**Architecture:** The Telnyx repair ships independently through the actual observed `/calls` producer. Mental V1 reuses `scheduler.js -> mentalUserOnce -> evaluateMentalTrigger -> buildMentalMessage -> Telegram -> lm_mental_send_log`. The next slice consumes verified Job Hunter Gmail outcomes and Calendar busy state, rather than creating a second mail poller. Its factual outcome report is distinct from an optional, native-language mental intervention.

**Tech Stack:** Node.js CommonJS, `node:test`, Supabase/Postgres REST, Telegram Bot API, Telnyx Call Control, Railway.

**Spec:** `docs/superpowers/specs/2026-09-16-life-manager-mental-physical-design.md`

## Global constraints

- Reuse the existing scheduler, Telegram transport, send ledger, runtime preferences, and Railway deployment path.
- Do not add a daemon, scheduler, database, queue, feedback UI, inline keyboard, or LLM framework.
- V1 enables only `affirmation`, `manifestation`, and `mindfulness_inquiry`.
- Messages are plain Telegram text with zero buttons, zero callback data, and zero reply instruction.
- Default three opportunities per local day, maximum three delivered messages, and minimum three hours between them.
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
| `apps/life-manager/content/mental/sources.json` | Pinned external OSS provenance manifests |
| `apps/life-manager/content/mental/catalog/{en,ja}.json` | Reviewed external source text and Japanese translations |
| `apps/life-manager/content/mental/metadata.json` | Quote family, themes, tones, windows, and risk flags |
| `apps/life-manager/scripts/import-mental-catalog.js` | Deterministic catalog importer and hash checker |
| `apps/life-manager/scripts/import-mental-catalog.test.js` | License, ID parity, hash, and rejection tests |
| `apps/life-manager/lib/mental-catalog.js` | Load and score eligible existing quotes |
| `apps/life-manager/lib/mental-catalog.test.js` | Deterministic personalized selection tests |
| `apps/life-manager/lib/mental-profile.js` | Closed source-backed personalization tags and gradual weighting |
| `apps/life-manager/lib/mental-profile.test.js` | Explicit-statement, correction, decay, and privacy tests |
| `apps/life-manager/lib/mental-copy.js` | Verbatim catalog output and reviewed inquiry validation |
| `apps/life-manager/lib/mental-copy.test.js` | Exact-source copy and forbidden-claim tests |
| `apps/life-manager/lib/mental-runtime.js` | Select, send, and record one plain message |
| `apps/life-manager/lib/mental-runtime.test.js` | Delivery, failure, and no-button contracts |
| `apps/life-manager/lib/mental-send-log.js` | Cap, spacing, 14-day template dedupe, receipt |
| `apps/life-manager/lib/mental-send-log.test.js` | Strict history and replay tests |
| `apps/life-manager/scheduler.js` | Timezone, busy-state, quiet-hours, explicit preferences |
| `apps/life-manager/lib/mental-wiring.test.js` | Scheduler wiring and sibling isolation |
| `apps/life-manager/migrations/2026-09-16-lm-mental-message-family.sql` | Family/template/local-day/window fields |
| `apps/life-manager/migrations/2026-09-16-lm-mental-profile-tags.sql` | Private tag, weight, basis, hashed source ref, decay, and supersession |
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

- [ ] Add RED suppression tests for invalid timezone, calendar unavailable, current event, quiet hours, three-message cap, three-hour gap, family already used, and no eligible catalog item.

- [ ] Add RED send cases:

```text
07:30–09:30 -> personalized affirmation
12:00–15:00 -> mindfulness or body-awareness inquiry
20:30–22:30 -> manifestation, release, or rest
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

## Milestone 4: Import and personalize existing catalogs

### Task 5: Import licensed catalogs and select existing words

**Files:**
- Create: `apps/life-manager/content/mental/sources.json`
- Create: `apps/life-manager/content/mental/catalog/en.json`
- Create: `apps/life-manager/content/mental/catalog/ja.json`
- Create: `apps/life-manager/content/mental/catalog/es.json`
- Create: `apps/life-manager/content/mental/metadata.json`
- Create: `apps/life-manager/scripts/import-mental-catalog.js`
- Create: `apps/life-manager/scripts/import-mental-catalog.test.js`
- Create: `apps/life-manager/lib/mental-catalog.js`
- Create: `apps/life-manager/lib/mental-catalog.test.js`
- Modify: `apps/life-manager/lib/mental-copy.js`
- Modify: `apps/life-manager/lib/mental-copy.test.js`

**Interfaces:**

```js
loadMentalCatalog(locale)
selectMentalQuote({ uid, localDay, window, family, profile, recentQuoteIds })
// -> { id, sourceId, sourceQuoteId, family, text, themes }

buildMentalMessage({ quote })
// -> { text: quote.text, templateId: quote.id, sourceId: quote.sourceId }
```

- [ ] Add RED provenance tests requiring every source manifest to contain repository, 40-character commit, path, license classification, SHA-256, and item count.

- [ ] Add `humancto/antara-remarkable` as the primary source pinned to `bdaf5a19e6401c771e097e04bc3fcc16d44eb835`, path `content/collections/affirmations.json`, license `MIT`, preserving its author field.

- [ ] Add `lifeLessCoder/Mental-Buddy` as the secondary source pinned to `05e0522deae5943ac2704826cbe3cdc124d9fedf`, path `assets/data/affirmations.json`, license `MIT`. Its items stay excluded until each passes safety classification.

- [ ] Add `ghall89/journal-prompts` as the inquiry source pinned to `6a180a182273f52d317d771e39546373beebac21`, path `src/data/prompts.json`, license `MIT`. Import only low-burden mindfulness, body-awareness, values, goals, and manifestation prompts.

- [ ] Add a RED test proving no source ID, path, repository, or generated snapshot refers to Anicca or `anicca-products`.

- [ ] Add RED tests proving `ContionMig/Mitsuzi-JS` and `DNSERR/confidencecrew` are not imported in V1 because their inspected catalogs mix duplicate, attributed, medical, destiny, or guaranteed-success language.

- [ ] Add RED rejection cases for:

```text
perfect health or recovery from illness
inevitable success or limitless outcomes
wealth or opportunities attracted by thought
universe or divine intervention presented as fact
current emotion, safety, achievement, or activity not established by context
third-party quotation without text-level provenance
```

- [ ] Create metadata without editing source text. At minimum tag the approved source examples in spec section 7.2 with `family`, `themes`, `tones`, and `windows`.

- [ ] Add RED personalized-selection tests using this explicit profile:

```js
const profile = {
  locale: "ja",
  tones: ["gentle"],
  values: ["self-worth", "mindfulness", "body-awareness"],
  goals: [],
  avoidThemes: ["spiritual"],
};
```

Assert theme matches outrank generic items, avoided themes never win, a quote delivered within 14 days never wins, and identical inputs return the same quote ID.

- [ ] Implement the exact scoring contract from spec section 8.3. Add no embeddings, model calls, vector database, or learning service.

- [ ] Add exact-source tests:

```js
assert.equal(selectById("antara:affirmations:enough-right-now", "en").text, "i am enough as i am right now.");
assert.equal(selectById("antara:affirmations:body-home", "en").text, "my body is not a project, it is a home.");
assert.equal(buildMentalMessage({ quote }).text, quote.text);
```

- [ ] Store mindfulness questions only as reviewed derived catalog entries with `derived_from`. Prove runtime cannot create or paraphrase a question.

- [ ] Prove `？` is legal only for reviewed `mindfulness_inquiry` entries; `返信して`, `教えて`, `答えて`, `押して`, and `選んで` remain illegal.

- [ ] Run RED:

```bash
cd apps/life-manager
node --test \
  scripts/import-mental-catalog.test.js \
  lib/mental-catalog.test.js \
  lib/mental-copy.test.js
```

- [ ] Implement `sources.json`, normalized catalog snapshots, metadata, deterministic scoring, and verbatim output. The importer fails nonzero on ID drift, hash drift, missing provenance, or rejected text.

- [ ] Run GREEN and commit:

```bash
node --test \
  scripts/import-mental-catalog.test.js \
  lib/mental-catalog.test.js \
  lib/mental-copy.test.js
git add content/mental scripts/import-mental-catalog.js scripts/import-mental-catalog.test.js \
  lib/mental-catalog.js lib/mental-catalog.test.js lib/mental-copy.js lib/mental-copy.test.js
git commit -m "feat(life-manager): personalize licensed mental catalogs"
git push
```

### Task 5A: Build a gradual source-backed mental profile

**Files:**
- Create: `apps/life-manager/migrations/2026-09-16-lm-mental-profile-tags.sql`
- Create: `apps/life-manager/lib/mental-profile.js`
- Create: `apps/life-manager/lib/mental-profile.test.js`

**Closed tags:**

```js
const MENTAL_TAGS = Object.freeze([
  "self-worth", "confidence", "self-compassion", "mindfulness",
  "calm", "rest", "boundaries", "courage", "growth",
  "body-awareness", "discipline", "future-direction",
]);
```

**Stored row:**

```js
{
  uid,
  tag,
  weight,
  basis: "explicit_user_statement|explicit_goal|explicit_correction",
  sourceRefHash,
  observedAt,
  expiresAt,
  supersededBy,
}
```

- [ ] Add RED tests proving raw Telegram text, chat ID, name, diagnosis, free-form model label, and inferred mood cannot be stored.

- [ ] Add RED tests for explicit statements:

```text
"自分を嫌いになる" -> self-worth + self-compassion
"自信がない" -> confidence
"もっと今に集中したい" -> mindfulness
"休むことに罪悪感がある" -> rest + self-compassion
```

Each accepted tag retains an HMAC source reference to the user-authored message and `basis=explicit_user_statement`; it does not store the raw text.

- [ ] Add RED tests rejecting inference from silence, calendar title, missed message, late reply, notification non-response, job rejection, or financial loss.

- [ ] Add RED tests for gradual weighting:

```text
first explicit statement -> weight 1.0
second explicit statement on another day -> weight 1.5
explicit correction "that is not my issue" -> old tag superseded and excluded
90 days without fresh evidence -> weight decays but history is retained
```

- [ ] Implement a closed classifier contract. A model may map explicit user text to the closed tags, but the output is accepted only when it cites the exact source message, marks `explicit=true`, uses an allowed tag, and passes schema validation. The model never generates message copy.

- [ ] Add read projection `readMentalProfile(uid)` returning only active tags, weights, explicit tone/locale, goals, avoid themes, and source counts.

- [ ] Run and commit:

```bash
cd apps/life-manager
node --test lib/mental-profile.test.js lib/mental-catalog.test.js
git add migrations/2026-09-16-lm-mental-profile-tags.sql \
  lib/mental-profile.js lib/mental-profile.test.js
git commit -m "feat(life-manager): ground gradual mental personalization"
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

- [ ] Add RED store tests for strict unreadable-history failure, three-message cap, three-hour gap, same-family/day lookup, 14-day template lookup, duplicate Telegram message ID, and replay of the same user/day/window.

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

- [ ] Add RED wiring tests proving scheduler provides current `nowMs`, user timezone, event start/end only, quiet hours, `readMentalProfile(uid)`, and strict send history.

- [ ] Prove scheduler does not map `location` or `attendees` to `important`, does not map duration to `focused`, and does not supply completed count, mood, hydration, or posture.

- [ ] Required runtime order:

```text
read strict send history
read active source-backed profile tags
evaluate opportunity gate
select non-repeated approved catalog quote by tag weights, tone, avoid themes, and window
validate source manifest, quote metadata, and verbatim localized text
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

- [ ] Enable the three V1 opportunities for the Dais tenant only: morning affirmation, midday mindfulness/body awareness, and evening manifestation/release. Cap three/day and gap three hours.

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
messages per day <= 3
gap >= 3 hours
busy-event sends = 0
quiet-hour sends = 0
buttons/callbacks = 0
reply instructions = 0
unsupported personal claims = 0
same-template repeat within 14 days = 0
duplicate external sends = 0
```

- [ ] Ensure at least one real delivered message from morning affirmation, midday mindfulness/body awareness, and evening manifestation/release. Use a reversible window adjustment if natural selection misses a family; do not fabricate user context.

- [ ] Replay one processed user/day/window. Require zero additional Telegram message IDs.

- [ ] Mark V1 PASS only when every condition holds. General rollout remains locked otherwise.

- [ ] Commit and push final evidence.

---

## Next slice: Gmail/Calendar-grounded mental UX

This slice follows the plain-message canary. It is not a new Gmail poller or a blanket auto-reply loop. The existing Job Hunter inbox owner is the first producer; MENTAL consumes its verified outcome. Keep the two effects separate: the owner reports the result, and MENTAL may send one supportive line later or stay silent.

### Task 10: Expose a bounded Job Hunter outcome to MENTAL

**Files to inspect and modify only where the current contract requires:**
- `apps/job-search-loop/job_search_loop/inbox.py`
- `apps/job-search-loop/job_search_loop/ledger.py`
- `apps/job-search-loop/job_search_loop/application_reporting.py`
- `apps/life-manager/lib/mental-runtime.js`
- Focused tests alongside the changed modules.

**Output contract:** `{uid, outcome_kind, application_ref, gmail_message_id, received_at, verified_at, evidence_ref, confidence_state}`. `outcome_kind` is one of `interview`, `offer`, `rejection`, `unknown`; `unknown` cannot trigger contextual mental copy. The producer must not copy raw mail body into the mental ledger.

- [ ] Read the current 15-minute Job Hunter inbox projection and existing outcome/Telegram receipts before defining the bridge. Reuse the immutable Gmail message ID, exact application identity, and owning ledger.
- [ ] Test that a verified rejection/offer/interview emits one projection; spoofed, stale, ambiguous, duplicate, and unmatched mail emits no contextual projection.
- [ ] Test that the normal Job Hunter result report is unchanged, and MENTAL cannot send a second result report or reply to the email.
- [ ] Add the smallest projection/adapter needed; no parallel Gmail scan in MENTAL.
- [ ] Run focused tests and one natural inbox wake. Read back the owner receipt and MENTAL's decision, including silence; require replay-zero.

### Task 11: Decide whether/when a contextual line helps

**Files:**
- `apps/life-manager/lib/mental-trigger.js`
- `apps/life-manager/lib/mental-runtime.js`
- `apps/life-manager/scheduler.js`
- Their focused tests.

- [ ] Feed the verified outcome projection, current Calendar busy intervals, local quiet hours, recent operational notices, and user's source-backed tone/theme profile into one decision.
- [ ] Test the cases: verified rejection during a meeting -> factual owner report then hold mental line; verified rejection in free time -> one gentle line or silence; verified offer -> no rejection copy; unknown outcome -> no contextual line; two results in one day -> no notification pile-up.
- [ ] Keep the 0–3 daily mental/body cap. An event-driven line replaces a routine slot and never creates a fourth mental message.
- [ ] Record `source outcome ID -> decision -> text version -> Telegram message ID` or a silence reason. A 30/60-minute evaluation is not a 30/60-minute send.

### Task 12: Approve native Japanese and English copy independently

**Files:**
- `apps/life-manager/content/mental/catalog/ja.json`
- `apps/life-manager/content/mental/catalog/en.json`
- `apps/life-manager/content/mental/metadata.json`
- `apps/life-manager/lib/mental-copy.test.js`

- [ ] Start from licensed OSS themes, not literal translations. Create locale-native editorial candidates for: general self-worth, rest, mindfulness inquiry, manifestation as action, verified rejection, verified offer, confirmed upcoming event.
- [ ] For every variant store locale, source inspiration, exact allowed context, reviewer/version, and forbidden assumptions. English copy is independently written/reviewed, not translated from Japanese final text.
- [ ] Test that Japanese lines read naturally aloud, avoid translated-slogan cadence and unsupported feelings, and that the English lines read natively. A mismatched locale or unreviewed variant is not eligible.
- [ ] Use the seven scenario pairs in spec §9.5 as acceptance examples, not automatic production copy. A native reviewer/user readback is needed before broad rollout.

### Task 13: Keep general mail autonomy separate

Do not route YC/general Gmail directly into MENTAL until an owning mail workflow verifies program identity, decision, deadlines, and exact message ID. That workflow also owns any reply and sent-mail readback. Its separate plan defines which mail classes are ignored, answered, escalated, or reported. The outcome projection from Task 10 is the interface to reuse; do not add a second mental-mail framework.

### Task 13A: Improve timing and wording from real corrections

**Files to inspect before choosing a patch:**
- `apps/life-manager/lib/mental-send-log.js`
- `apps/life-manager/lib/mental-profile.js`
- `apps/life-manager/lib/mental-catalog.js`
- Existing Telegram message intake and tests.

- [ ] Store each decision as `send` or `silence` with reason, source outcome ID, Calendar busy version, chosen text version, and eventual Telegram ID. Do not store a full Gmail body or infer emotion from message-open state.
- [ ] Treat an explicit user correction such as `この言い方は嫌`, `この時間は邪魔`, or `こういう時は短く` as source-backed feedback for that user; update tone/avoid tags or a delivery window only after the correction is tied to an exact prior message.
- [ ] Compare a changed policy with its prior version on verified cases: useful explicit reactions, intrusive corrections, false personal claims, duplicate sends, and missed material outcome reports. Keep the new policy only if it improves the intended signal without worsening the safety counters.
- [ ] Test replay of the same correction and the same Gmail outcome. Both must have one durable update/effect at most.
- [ ] Do not claim emotional benefit from silence, read receipts, or a delivered Telegram ID.

### Task 14: Crisis-response safety boundary

Before claiming any self-harm support, verify the existing safety route and its actual owner. Explicit imminent self-harm language stops ordinary affirmation selection and offers location-appropriate human/crisis support. Do not infer crisis from rejection, silence, or Calendar gaps; do not claim suicide prevention, emergency dispatch, continuous monitoring, or treatment without independently proven capability. Test crisis text versus ordinary disappointment and read back the actual handoff route.

### Task 15: Optional Anicca iOS copy improvement

Anicca iOS is a separate product under the mobile-app loop, not a Life Manager channel. After Life Manager Japanese/English copy has native-language acceptance, the mobile-app owner may independently review its own affirmation bank. No Life Manager runtime dependency or shared send ledger is added to the app.

## Final verification checklist

- [ ] Telnyx real-call receipt proves `90029` is gone.
- [ ] Railway worker `commitHash` equals merged `main`.
- [ ] Production schema matches the additive migration.
- [ ] V1 has exactly three message families.
- [ ] Every delivered item is plain Telegram text.
- [ ] Seven-day canary has zero unsupported context claims.
- [ ] Cap, spacing, busy suppression, quiet suppression, 14-day dedupe, and replay-zero all pass.
- [ ] No Anicca source, Anicca iOS dependency, feedback UI, or second mental loop was added.
