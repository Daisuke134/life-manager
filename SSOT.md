# Life Manager LOCAL — SINGLE SOURCE OF TRUTH (prepared 2026-06-17)

ONE file. New-session patches are CANONICAL. Old `patches/life-*` are reference-only; do NOT merge
outdated logic in. The ONLY thing reused from old = the life-call **connectivity** fixes (separate, clearly
labeled). Discard old life-ask/notify/travel logic — superseded by the new requirements below.
Done = every subsystem: real diff → /vcsdd-adversary PASS (5-dim) → TDD GREEN → no-mock E2E green.

## §0 Product promise + corrected design
寝坊・夜更かし・遅刻・連絡漏れから卒業。あらゆる予定を完全管理。
1 簡単スタート(名前/電話/gcal/任意位置) · 2 全予定に移動時間自動登録 · 3 場所不明→質問→返信で登録
· 4 次予定(移動含む)の15/10/5分前に電話・行き方ガイド・迫るほど厳しく · 5 遅刻時 関係者へ承認後連絡
Design: ALL events (no filter); offsets 15/10/5 ESCALATING (calm→firm→harsh); schedule-based via
`openclaw cron add --at` (no polling); SEARCH→ASK spine for unknown locations (never hallucinate);
self-contained in ~/anicca/skills/life (zero reach to anicca-products/aniccaai.com).

## §1 AS-IS (real bugs, verified file:line — assume nothing works)
- travel.js = DEAD (live = ~/.openclaw/skills/anicca-travel-fill/scripts/travel_fill.py). Live one is good
  (prev-origin :274, home-skip :50, real Directions :170) BUT `directions_minutes(...) or 45` :302 silent
  guess; unknown location → skipped :284 (not asked).
- call = generic: placeCall({}) passes no event/urgency (call.js:65); runner doesn't forward --event
  (life-call-telnyx.mjs:138); bridge defaults to hardcoded "dentist" (call-bridge.cjs:177);
  buildCallPrompt has no urgency (call-logic.js:367). ALSO not connected: TELNYX_API_KEY absent; D60 gate;
  media.track echo (call-bridge.cjs:72) ; carrier-truth status missing (life-call-telnyx.mjs:159).
- ask = split-brain: question via Gmail (ask.js:140) but reply expected via AgentMail webhook → loop never
  closes. postNetlify to aniccaai.com (ask.js:91). markError non-fatal (ask.js:154).
- locate/planner = NO cron (calls never fire). offsets 15,14,13,5 (locate.js:53, wrong). no tone escalation.
- notify = late = travel-start-passed w/ NO motion check (notify.js:131) → false alarms. extractApproval
  only ok/はい (notify.js:235). dead AgentMail branch.

## §2 FINAL literal diffs (canonical = new-session work)
### 2a CALL — connectivity (reuse ONLY this from old `patches/life-call.patch.md`)
Apply life-call.patch.md hunks D1 (provision TELNYX_API_KEY via camofox), D2 (balance preflight +
carrier-truth status/recording), D3 (honor Telnyx media.track → stop self-echo), + the D60 number-verify.
These make the call CONNECT. Source of truth for this section = `docs/superpowers/specs/anicca/patches/life-call.patch.md` (already adversary-PASS). NOT merged with 2b.
### 2b CALL — content/escalation (canonical = `call/PATCH-call-escalation.diff.md`, reviewed+fixed)
6 hunks: call.js placeCall+CLI forward --event/--urgency; life-call-telnyx.mjs forward to bridge;
call-bridge.cjs parse --urgency + KILL dentist default + geminiSetupForEvent(event,urgency,model);
call-logic.js buildCallPrompt(event,urgency) tone calm/firm/harsh; locate.js offsets 15,10,5 +
dialOnce/runScheduleLoop/runLiveLocationLoop pass event+urgency + parseArgs --event.
### 2c TRAVEL — search→ask (canonical = new)
Adopt travel_fill.py into ~/anicca/skills/life/travel/, repoint cron, delete dead travel.js. Fixes:
`travel_min = directions_minutes(...)`; if None → `enqueue_ask(curr,"no_route"); continue` (NOT or-45).
unknown location :284 → `enqueue_ask(curr,"unknown_location")` (NOT silent skip). Add a web-geocode try
before asking. enqueue_ask writes ~/.openclaw/state/life-ask-queue.jsonl.
### 2d ASK — Gmail loop (canonical = new)
ask.js: drop postNetlify/aniccaai.com; detect from life-ask-queue.jsonl + local gog gcal scan; send
question via gog gmail; NEW runReplyPoll() mirrors notify.js runPoll (gog gmail search reply → parse
Event ID + answer → gog calendar patch). markError fatal (:154). NEW cron anicca-life-ask-poll (*/10).
### 2e PLANNER — schedule-based calls (canonical = `docs/.../plans/step1-lm-local-literal-patches.md`)
NEW skills/life/planner.js: gcal → every event × [15,10,5] future offset → `openclaw cron add --at <iso>
--delete-after-run --tools exec --message "node call.js --event <json> --urgency <tone>"`. idempotent by
leave-instant job name. travel.js exports listEvents. NEW cron anicca-life-plan (*/10, full verified shape).
### 2f NOTIFY — motion gate (canonical = new)
notify.js: isLateRisk (:131) add `&& !locate.hasMoved(prev,live) && now>travelStart+GRACE`. extractApproval
(:235) add yes/go/承知. delete dead AgentMail branch.
### 2g CONSOLIDATE
Move apps/landing/scripts/{life-call-telnyx.mjs,life-call.mjs,call-bridge.cjs}+_lib/call-logic.js →
skills/life/call/lib/; rewire call.js (drop ANICCA_PRODUCTS). telegram location producer → skills/life/locate/.
Verify grep "ANICCA_PRODUCTS|aniccaai.com|postNetlify" skills/life = 0.

## §3 E2E (no-mock, the only "done") — LM-E1..E5
E1 onboarding (profile/gcal/gmail) · E2 travel block real calc from prev loc, home-skip · E3 unknown→Web
search→else question mail→reply→registered · E4 phone rings -15/-10/-5 naming the event + escalating
(Telnyx call-id+audio) · E5 late(real motion)→approval mail→OK→stakeholder sent. (full steps: see below)
Pass gate = E1..E5 all green + grep-0 self-contained.

## §4 PROCESS — superpowers + VCSDD per subsystem (order: travel→ask→call-connect→call-content→planner→notify→consolidate)
For EACH: /vcsdd-init <sub> → /vcsdd-spec (this SSOT section) → /vcsdd-tdd (RED) → apply literal diff
(GREEN) → /vcsdd-adversary (fresh-context, binary PASS/FAIL + evidence, 5-dim: spec fidelity/edge/correctness/
structure/verification) → fix until PASS → no-mock E2E (real gcal/phone/mail) → /vcsdd-converge → /vcsdd-commit.
Then §3 integration E2E LM-E1..E5 → merge+push = LM-local DONE.

## §5 Source files folded here (kept for now, this SSOT is the index)
new: call/PATCH-call-escalation.diff.md · PATCHES-AND-AUDIT.md · E2E-SPEC.md · (anicca-project) plans/step1-lm-local-literal-patches.md
old (reference, connectivity only): (anicca-project) specs/anicca/patches/life-call.patch.md
discard (superseded): old patches/life-ask.patch.md, life-notify.patch.md, life-travel.patch.md
