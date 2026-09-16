# Life Manager Mental Messages V1 Design

**Status:** Revised after context-grounding review
**Owner:** Life Manager cloud runtime
**Primary locale:** Japanese
**Scope:** Affirmation, manifestation, and mindfulness inquiry messages only

## 1. Outcome

Life Manager sends brief Japanese messages that support confidence, intention, self-compassion, and present-moment awareness without asking the user to manage another interface.

V1 is deliberately narrow:

1. affirmation messages;
2. manifestation messages that turn an intention into a controllable action;
3. mindfulness prompts and reflective questions (`問いかけ`).

Messages contain no buttons, no repeated sender prefix, no mandatory reply, and no claim about the user's current activity, emotion, achievement, location, preparation, or physical state unless Life Manager has an authoritative source for that exact claim.

The independent Telnyx `/calls` error `90029` remains the first repair milestone, but it is not part of mental-message semantics.

## 2. Correction to the previous design

The previous version treated future context sources as though they were already available. Current source inspection proves that is unsafe:

- `scheduler.js` marks an event `important` when it has a location or attendees. That does not prove it is a presentation or that the user has prepared.
- An event lasting at least 90 minutes is marked `intense`. That does not prove the user concentrated for 90 minutes.
- Production location may be `unknown`.
- The current mental runtime has no authoritative completed-task count, mood signal, preparation receipt, screen-time duration, hydration state, or posture state.

Therefore these messages are prohibited in V1:

- `必要なものは持ってきてる。あとは話すだけ。`
- `今日はすでに3件終えています。`
- `90分集中していました。`
- `落ち込んでいる今も、立て直そうとしています。`

They may become legal later only when the exact premise has a named, current, authoritative source and a freshness rule.

## 3. Product principles

1. **No invented context.** Unknown never becomes a personalized claim.
2. **Context is first used to avoid interruption.** Calendar busy state, quiet hours, daily cap, and recent-send state decide when to stay silent.
3. **Stable personalization before live personalization.** Locale, tone, values, and explicit goals are safer than inferred emotions or activity.
4. **No interaction debt.** A message does not include buttons and does not require a reply.
5. **A question may be contemplative, not operational.** `問いかけ` may use `？`, but must remain useful when unanswered and must not say `返信して`, `教えて`, or equivalent.
6. **Manifestation is action-oriented.** It may express possibility and intention, but never promise that thought alone changes external reality.
7. **Silence is a valid output.** Missing timezone, unreadable send history, quiet hours, active calendar event, daily cap, or duplicate context suppresses delivery.
8. **No new loop.** Reuse the existing scheduler, Telegram transport, mental runtime, and send ledger.

## 4. What Life Manager actually knows

### 4.1 V1-authorized sources

| Claim class | Authoritative source | Freshness | Allowed use |
|---|---|---|---|
| Local time/day | User timezone or explicit UTC offset | Current tick | Select morning/day/evening family |
| User is in a calendar event | Calendar start/end | Current tick | Suppress delivery only |
| Recent message count/time | `lm_mental_send_log` | Current local day | Cap, spacing, dedupe |
| Quiet hours | Runtime preferences | Current preference | Suppress delivery |
| Locale and tone | Explicit runtime preference | Until changed | Select copy bank |
| Values or goal | Explicit user-authored durable profile entry | Until superseded | Select relevant affirmation/manifestation; never claim progress |
| Bedtime goal | Explicit preference | Current local day | Select evening/release family |

### 4.2 Not known in V1

The following remain `unknown` unless a later milestone adds the stated receipt:

| Proposed fact | Required future evidence |
|---|---|
| `準備できている` | Explicit preparation completion receipt |
| `3件終えた` | Durable completed-action ledger rows with current-day scope |
| `90分集中した` | Authorized activity/focus-session measurement |
| `落ち込んでいる` | User-authored mood input; never inferred from silence |
| `水分不足` | User-authored or authorized sensor evidence |
| `座り続けている` | Authorized device/activity evidence |
| `発表が重要` | Explicit event classification, not attendees/location heuristic |

### 4.3 Truth rule

Every variable in a message template must declare:

```text
source -> timestamp -> freshness limit -> transformation -> rendered claim
```

If any link is absent, stale, ambiguous, or unreadable, that variable is unavailable. The runtime either selects a context-free template or stays silent.

## 5. V1 architecture

```mermaid
flowchart LR
  TZ[Timezone] --> G[Opportunity gate]
  BUSY[Calendar busy only] --> G
  Q[Quiet hours] --> G
  LOG[Send history] --> G
  PREF[Explicit tone, values, goals] --> S[Message selector]
  G -->|suppress| N[No message]
  G -->|open window| S
  S --> A[Affirmation]
  S --> M[Manifestation]
  S --> I[Mindfulness inquiry]
  A --> V[Copy validator]
  M --> V
  I --> V
  V -->|valid| T[Plain Telegram message]
  V -->|invalid| N
  T --> R[Durable send receipt]
```

Current execution path remains:

```text
scheduler.js
  -> mentalDeps(...)
  -> mentalUserOnce(...)
  -> evaluateMentalTrigger(...)
  -> buildMentalMessage(...)
  -> Telegram sendMessage(...)
  -> recordMentalSend(...)
```

## 6. Delivery timing

Without live mental/body context, V1 is not described as perfect just-in-time personalization. It is **right-window delivery**: Life Manager finds a low-interruption opportunity and sends a low-assumption message.

Default opportunity windows in the user's local time:

| Window | Time | Eligible family |
|---|---:|---|
| Morning orientation | 07:30–09:30 | personalized affirmation |
| Midday awareness | 12:00–15:00 | mindfulness or body-awareness inquiry |
| Evening direction | 20:30–22:30 | manifestation, release, or rest |

Rules:

- Default is three message opportunities per local day: morning, midday, and evening.
- Maximum three delivered mental/body messages per local day.
- Minimum three hours between delivered messages.
- Never send during a current calendar event.
- Never send inside quiet hours.
- Use a deterministic per-user/per-day minute inside the selected window so the whole fleet does not fire at one time.
- Do not describe the selected minute as emotionally optimal.
- A user-authored goal may influence message selection, not factual claims.
- If no eligible non-repeated message fits the person, skip that window rather than send filler.

The default UX is therefore usually three messages, but the actual result can be zero to three. Operational receipts from Jobs, CFO, Investment, Calendar, or Care are separate and are not counted as mental/body messages.

## 7. Catalog sources: external reuse only

Life Manager does not use the internal Anicca affirmation catalog. It imports only reviewed external OSS source material with pinned commits and text-level provenance.

### 7.1 Approved source set

| Source | Pin | License | Use |
|---|---|---|---|
| [humancto/antara-remarkable](https://github.com/humancto/antara-remarkable) | `bdaf5a19e6401c771e097e04bc3fcc16d44eb835` | MIT | Primary source for enoughness, rest, boundaries, courage, self-trust, body awareness, imperfection, and starting again |
| [lifeLessCoder/Mental-Buddy](https://github.com/lifeLessCoder/Mental-Buddy) | `05e0522deae5943ac2704826cbe3cdc124d9fedf` | MIT | Secondary source for self-worth, resilience, calm, presence, daily orientation, and evening release; every item is screened |
| [ghall89/journal-prompts](https://github.com/ghall89/journal-prompts) | `6a180a182273f52d317d771e39546373beebac21` | MIT | Source for mindfulness, reflection, values, goals, body-awareness, and manifestation inquiries; only low-burden prompts are used |

Rejected in V1:

| Source | Reason |
|---|---|
| `ContionMig/Mitsuzi-JS` | Mixed third-party quotations, medical claims, relationship predictions, universe claims, and absolute manifestation language |
| `DNSERR/confidencecrew` | Duplicates, destiny/success claims, extreme language, and unclear per-item provenance |

Repository license alone is insufficient when a file aggregates third-party quotations. Each imported item must either be authored by the repository source under its license or have separate text-level provenance.

### 7.2 What is reused

The English source text is stored unchanged. Japanese text is a reviewed translation tied to the exact source item; it is not generated at delivery time.

Examples from the approved sources include:

| Source | Exact English source | Life Manager theme |
|---|---|---|
| Antara | `i am enough as i am right now.` | enoughness, self-worth |
| Antara | `i am allowed to rest before i am exhausted.` | rest, boundaries |
| Antara | `my courage does not need to be loud to be real.` | courage, confidence |
| Antara | `i can take the small step even while afraid.` | courage, action |
| Antara | `i am here, in this body, breathing.` | presence, body awareness |
| Antara | `i can unclench my jaw and mean it.` | body awareness |
| Antara | `my body is not a project, it is a home.` | body respect |
| Antara | `my mistakes are tuition, not verdicts.` | self-compassion |
| Mental Buddy | `I am enough just as I am.` | self-worth |
| Mental Buddy | `I do not have to believe everything I think.` | cognitive distance |
| Mental Buddy | `My breath anchors me to the present.` | mindfulness |
| Mental Buddy | `Small progress is still progress.` | growth |
| Journal Prompts | `If my body could speak, it would tell me to` | body inquiry |
| Journal Prompts | `I can take better care of myself by` | physical intention |
| Journal Prompts | `My top three priorities right now are` | attention inquiry |
| Journal Prompts | `If failure wasn’t an issue, I would` | manifestation inquiry |

Items implying a current emotion, clinical condition, guaranteed result, or observed behavior are excluded unless the sentence remains universally valid without context.

### 7.3 Import manifest

Every imported catalog has a pinned manifest:

```json
{
  "source_id": "antara-remarkable-affirmations",
  "source_repo": "humancto/antara-remarkable",
  "source_commit": "bdaf5a19e6401c771e097e04bc3fcc16d44eb835",
  "source_path": "content/collections/affirmations.json",
  "license": "MIT"
}
```

The importer computes and stores `imported_sha256`. Manifests also store the license URL, author field when available, exact upstream text, reviewed Japanese translation, reviewer version, and rejection reason for excluded items. Unlicensed or ambiguous text never enters the production bank.

## 8. Catalog classification and personalization

Life Manager personalizes by selecting an existing catalog item, not by asking an LLM to rewrite it.

Each approved quote receives Life Manager-owned metadata without changing the source text:

```json
{
  "id": "antara:affirmations:enough-right-now",
  "source_id": "antara-remarkable-affirmations",
  "source_quote_id": "i-am-enough-as-i-am-right-now",
  "family": "affirmation",
  "themes": ["self-worth", "enoughness"],
  "tones": ["gentle", "direct"],
  "windows": ["morning_orientation", "evening_direction"],
  "risk_flags": [],
  "localized_text": {
    "ja": "私は今のままで十分です。",
    "en": "i am enough as i am right now."
  }
}
```

### 8.1 User personalization inputs

Only explicit, durable user facts affect selection. Every profile tag retains source references instead of becoming an unexplained model judgment:

```json
{
  "tag": "self-worth",
  "weight": 1.0,
  "source_refs": ["telegram-message://..."],
  "basis": "explicit_user_statement",
  "observed_at": "RFC3339 timestamp",
  "expires_at": null
}
```

Eligible profile inputs:

```text
preferred locale
preferred tone: gentle / direct / spiritual-neutral
explicit statements such as low confidence, self-hatred, stress, or a wish to be more mindful
explicit values: growth / peace / courage / self-worth / rest / boundaries
explicit goals
explicit themes to avoid
recently delivered quote IDs
current delivery window
```

Calendar titles, silence, response time, notification opens, and inferred mood do not modify the mental profile.

### 8.2 Gradual personalization

Personalization changes with each person, but it earns specificity gradually:

| Stage | Evidence | Behavior |
|---|---|---|
| Bootstrap | Locale, timezone, explicit current conversation, existing durable goals | Select broad matching themes immediately; no inferred mental state |
| First 7 days | Delivery history and calendar availability | Avoid repetition and move delivery within the three safe windows; do not claim effectiveness |
| Days 8–21 | Repeated explicit themes across conversations | Increase weight only when the person directly states the same need more than once; retain source refs |
| Mature profile | Explicit corrections, spontaneous reactions, changed goals, stable routine | Adjust themes, tone, and timing; old themes decay or are superseded |

No button is needed. Learning comes from normal conversation and explicit corrections. In the absence of a real response signal, Life Manager learns only timing and dedupe, not whether the message emotionally worked.

### 8.3 Deterministic selection

For every eligible quote:

```text
score =
  +4 for each explicit-value/theme match
  +3 for an explicit-goal/theme match
  +2 for preferred-tone match
  +1 for delivery-window match
  -1000 if theme is explicitly avoided
  -1000 if quote was delivered within 14 days
  -1000 if any safety/risk flag is present
```

Ties are broken deterministically by `uid + local_day + window + quote_id`. Selection produces the existing localized text byte-for-byte.

### 8.4 Manifestation

Manifestation is a catalog classification, not newly generated prose. Only catalog items about direction, possibility, growth, and controllable action qualify. Items promising inevitable success, attraction of wealth, perfect health, destiny, or intervention by the universe are rejected.

An explicit goal selects a matching quote but is not interpolated into the quote in V1. This avoids awkward or unsupported rewriting.

### 8.5 Mindfulness inquiry (`問いかけ`)

If a catalog contains an approved question, it can be delivered verbatim. When an affirmation is converted into a question, the question must be a separately reviewed catalog variant linked to its source ID:

```json
{
  "id": "life-manager:inquiry:antara-body-breathing:ja:v1",
  "derived_from": "antara:affirmations:i-am-here-in-this-body-breathing",
  "reviewed_text": "いま、身体と呼吸に気づいている？",
  "family": "mindfulness_inquiry"
}
```

Runtime generation or ad-hoc paraphrasing is prohibited. The reviewed inquiry is stored and tested like any other catalog item. It remains useful without an answer and carries no button or reply instruction.

### 8.6 Physical-life management

Physical management has two layers.

**Layer 1 — body awareness without sensors:** the midday message selects reviewed OSS body-awareness text or inquiry. It does not claim what the body is doing.

Examples derived from the approved Antara source set:

- source `i am here, in this body, breathing.` -> reviewed Japanese `私はこの身体にいて、呼吸しています。`
- source `i can unclench my jaw and mean it.` -> reviewed Japanese `顎の力を、いま少しゆるめられる。`
- source `my shoulders are allowed to drop.` -> reviewed Japanese `肩の力を下ろしていい。`
- source `my body is not a project, it is a home.` -> reviewed Japanese `身体は直す対象ではなく、私が暮らす場所です。`
- source `i can drink water and call that care.` -> reviewed Japanese `水を飲むことも、自分を大切にすることです。`

These are invitations, not claims that the person is dehydrated, tense, sitting, or unhealthy.

**Layer 2 — actions backed by records:** existing Life Manager physical and diet organs manage explicit routines and care continuity.

| Area | What Life Manager can use | What it may do |
|---|---|---|
| Sleep | Explicit bedtime/wake goal and calendar | Protect quiet hours, reserve sleep window, send evening release message |
| Meals | Explicit meal preference and calendar gaps | Reserve a meal window; never claim the person ate |
| Exercise | Explicit goal and scheduled/confirmed activity | Reserve recurring activity blocks and follow through |
| Dental/medical/hair care | Verified visit history, explicit cadence, provider receipts | Detect due care, search, book within delegated boundaries, report confirmed appointment |
| Medication or clinical care | Explicit professional plan only | Remind exactly as authorized; never prescribe or modify |
| Live body state | Authorized wearable/sensor integration, added later | Use only the named fresh measurement |

Physical operational receipts are separate from the three daily mental/body messages. A confirmed appointment or urgent care reminder is sent when required, even if the message budget is otherwise full.

## 9. Copy contract

All V1 copy must satisfy:

- 80 Japanese characters or fewer.
- Plain Telegram text only.
- No inline keyboard or callback data.
- No sender signature such as `Life Manager:::`.
- No user name unless explicitly required later.
- No exclamation-heavy encouragement.
- No diagnosis, therapy claim, crisis inference, wealth promise, or guaranteed result.
- No `あなたは今〜している`, `〜を完了した`, or numeric personal fact without an authorized source.
- Affirmation may be a statement.
- Manifestation must preserve agency and avoid magical causation.
- Mindfulness inquiry may use `？` but cannot ask for a reply.

The validator rejects reply-seeking phrases:

```text
返信して / 教えて / 答えて / 押して / 選んで / let me know / reply / tell me
```

## 10. Selection and repetition

V1 uses the imported, classified catalog, not free-form LLM generation.

Selection key:

```text
uid + local_day + window + eligible_quote_ids + explicit_profile_tags
```

- Do not repeat the same template for the same user within 14 days.
- Do not send the same family twice on the same day.
- If no non-repeated eligible template exists, stay silent.
- Delivered text must equal the approved localized catalog text byte-for-byte.
- LLM generation is not part of V1.

No feedback buttons exist. V1 does not claim to learn message preference from silence. Any later adaptation must name a real signal such as explicit conversation, reaction, or settings change.

## 11. Data and privacy

Reuse `lm_mental_send_log`. Extend it only if current columns cannot store:

```text
family
template_id
local_day
window
delivered Telegram message_id
```

Do not add raw calendar titles, inferred mood, message-reply tracking, location coordinates, journal content, or a new mental profile database.

The durable profile may contain only explicit, user-authored values/goals and presentation preferences. A system inference is never written back as a user fact.

## 12. Future context unlocks

Future contextual messages are separate milestones. Each is disabled until its evidence contract passes production readback.

| Unlock | Required contract | Then-legal example |
|---|---|---|
| Important-event support | Explicit event type + current calendar event | `14時の発表まで30分。最初の一文だけ整えればいい。` |
| Preparation confidence | Current preparation receipt tied to event | `必要なものは揃っている。あとは話すだけ。` |
| Small-win reflection | Current-day completed-action receipts | `今日は3件終えている。その事実は残っている。` |
| Physical reset | Authorized current activity measurement | `90分座っている。少し歩く時間です。` |
| Self-compassion after setback | Explicit failure/rejection receipt | `今回の結果と、あなた自身の価値は別です。` |

The receipt authorizes only the matching claim. For example, a calendar event never authorizes `準備済み`, and a task completion never authorizes an inferred mood.

## 13. Failure behavior

| Failure | Behavior |
|---|---|
| Timezone absent or invalid | Suppress |
| Calendar unavailable | Suppress rather than risk interrupting an event |
| Send history unreadable | Suppress rather than exceed cap or repeat |
| No eligible non-repeated template | Suppress |
| Catalog manifest hash differs | Suppress; do not load an unreviewed catalog |
| Source license/provenance missing | Exclude source at build/import time |
| Template uses unavailable variable | Reject before Telegram |
| Telegram failure | Do not record a delivered send |
| Receipt write fails after delivery | Record reconciliation evidence by Telegram message ID; never resend blindly |

## 14. Rollout

### Milestone A — Telnyx repair

Locate the actual producer of `time_limit_secs`, fix the shared provider boundary, deploy from merged `main`, and verify one real call without `90029`.

### Milestone B — Current MENTAL truth audit

Verify Railway deployment `commitHash`, scheduler wiring, send ledger, timezone source, calendar availability, and Dais tenant eligibility.

### Milestone C — Japanese V1 canary

Enable the three V1 opportunities for Dais: morning affirmation, midday mindfulness/body awareness, and evening manifestation/release. Deliver at most three plain messages per local day for seven days. Buttons and unsupported personal claims remain zero.

### Milestone D — General Japanese rollout

Expand after canary acceptance. Context unlocks remain off independently.

### Milestone E — Context unlocks

Add one evidence-backed context class at a time. Each needs source, freshness, test, cloud readback, and replay-zero before its copy is legal.

Anicca assets and Anicca iOS are not part of this runtime or rollout. Anicca iOS remains a separate product created and operated by Life Manager's mobile-app loop.

## 15. Acceptance criteria

- Only `affirmation`, `manifestation`, and `mindfulness_inquiry` are enabled in V1.
- Every production message resolves to a source ID, pinned manifest, quote ID, and approved localized text.
- Only the three pinned external OSS sources listed in section 7 are eligible for V1 import.
- No unlicensed or ambiguous external text is imported.
- Every message is plain text with zero buttons and zero reply instruction.
- Maximum three V1 mental/body messages per user/local day.
- Minimum three hours between messages.
- Zero messages during current calendar events or quiet hours.
- Zero personal activity, achievement, emotion, preparation, or physical-state claims without an authorized source.
- Zero repeated template IDs within 14 days for the same user.
- Every delivered message has a positive Telegram message ID and one durable send receipt.
- Replaying the same user/day/window produces zero duplicate messages.
- Seven-day Dais canary contains at least one delivered message from each family.
- Telnyx acceptance remains independently satisfied.

## 16. Non-goals

- Inferring mood from silence, calendar gaps, response time, or message opens.
- Claiming a person prepared, focused, completed work, exercised, ate, drank, slept, or felt something without evidence.
- Buttons, daily check-ins, required replies, surveys, journaling, or streaks.
- A new mental daemon, database, agent framework, or mobile app.
- Importing Anicca catalogs or integrating Anicca iOS.
- Clinical diagnosis, therapy, emergency automation, or treatment claims.
- Magical manifestation or guaranteed outcomes.
- Runtime LLM rewriting, paraphrasing, translation, or interpolation of catalog prose.

## 17. Decision record

**Chosen:** select verbatim, licensed catalog text using stable preferences and low-interruption opportunity windows.

**Deferred:** event-specific confidence, completed-task reflection, failure aftercare, and sensor-based physical prompts until their exact evidence sources exist and are verified in production.

**Reason:** reuse proven words; personalize the selection, not the truth of the sentence.
