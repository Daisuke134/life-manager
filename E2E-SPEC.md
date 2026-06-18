# Life Manager LOCAL — E2E SPEC (the only definition of "done") — Dais 2026-06-17

Lives IN the anicca repo, next to the code. LM-local is ONE self-contained skill under `~/anicca/skills/life/`
— no reach into anicca-products or aniccaai.com. Runs entirely via `node skills/life/...` on the Mac Mini,
scheduled by the OpenClaw gateway (runtime engine only). Promise = the user is NEVER late to ANY schedule.

## Product promise (every line MUST pass its E2E, no-mock)
寝坊・夜更かし・遅刻・連絡漏れから卒業。あらゆる予定（起床・就寝・仕事・瞑想・移動）を完全管理。
1. 名前・電話番号・Googleカレンダー・任意で現在位置の連携で簡単スタート。
2. あらゆる予定に対して、移動時間を自動登録。
3. 場所がわからなければ質問→返信すれば自律的に登録完了。
4. 次の予定（移動含む）の **15/10/5 分前**に電話、行き方をガイド・行動を促す（迫るほど厳しく）。
5. 予定に遅れそうな場合は関係者へ、返信案を承認後に連絡。

## Rules
- **NO mock.** Real gog (real gcal/gmail, account you@example.com), real Telnyx call to Dais's real phone (+<YOUR_E164_NUMBER>), real OpenClaw cron. Test recipients = you@example.com (never a real third party).
- Each test: GOAL · PRECONDITION · STEPS (exact commands) · EXPECTED (pass criteria) · EVIDENCE (what to capture).
- A line is DONE only when its test is green with fresh evidence. Loop fix→run until all green.
- Cleanup: delete test gcal events + auto-deleted --at jobs after each run.

---

### LM-E1 — onboarding (bullet 1)
- GOAL: name + phone + gcal + gmail (+optional location) connected with one simple setup.
- PRECONDITION: `~/.openclaw/.env` has GOG_KEYRING_PASSWORD, GOG_ACCOUNT; gog installed.
- STEPS:
  1. `node ~/anicca/skills/life/setup.js` (NEW) → enter name + phone → it runs gog Google OAuth (gcal+gmail).
  2. `gog calendar events list -j --account you@example.com --from today --to <+1d>`
  3. `gog gmail send --account you@example.com --to you@example.com --subject "LM-E1" --body ok`
- EXPECTED: `skills/life/profile.json` has `{name, phone:"+8180...", gcalAccount, gmailAccount}`; step 2 returns real events (gcal connected); step 3 returns a message id (gmail send works).
- EVIDENCE: profile.json contents + events JSON length>0 + gmail send id.

### LM-E2 — travel auto-register (bullet 2)
- GOAL: every located event gets a `[Travel]` block at (event start − real travel time).
- PRECONDITION: GOOGLE_API_KEY_DIRECTIONS set; HOME_ADDRESS or profile home set.
- STEPS:
  1. Insert a real test event: summary "LM-E2 MUIT", start +3h, location "大崎駅" via `gog calendar create`.
  2. `node ~/anicca/skills/life/travel/travel.js`
  3. `gog calendar events list -j ... --from today` → find the `[Travel] LM-E2 MUIT` block.
- EXPECTED: a `[Travel] LM-E2 MUIT` event exists, its start = event start − (Google Directions transit duration), duration ≈ that travel time. A no-location event (e.g. "LM-E2 Sleep") gets NO travel block (leave = event start).
- EVIDENCE: the inserted [Travel] block JSON (start/end) + the computed duration.

### LM-E3 — ask when location unknown (bullet 3)
- GOAL: location unknown → question mail → reply → event registered, all local (gog), no web call.
- STEPS:
  1. Insert event "LM-E3 meeting" start +4h with NO location.
  2. `node ~/anicca/skills/life/ask/ask.js --action question`  (local gog detection — NOT postNetlify)
  3. Check you@example.com for the question mail. Reply "自宅".
  4. `node ~/anicca/skills/life/ask/ask.js --action reply --body '{"eventId":"<id>","answer":"自宅"}'`
- EXPECTED: step 2 sends a question email (gog gmail send id); after reply, the event has location "自宅" set (or a [Travel] block from home appears on next travel run).
- EVIDENCE: question mail id + the event after-state showing the registered location.

### LM-E4 — the calls: 15/10/5 before, guided, ESCALATING (bullet 4) ★ the heart ★
- GOAL: Dais's real phone rings at −15/−10/−5 of the leave time of EVERY event; Charon names the event + guides + gets harsher each step.
- PRECONDITION: TELNYX_API_KEY + GEMINI_API_KEY set; call runner in-repo (`skills/life/call/`).
- STEPS:
  1. Insert event "LM-E4 test" start ~ now+16min with location "大崎駅".
  2. `node ~/anicca/skills/life/travel/travel.js` → [Travel] block sets leave ≈ now+1min.. (so −15 has passed; use a leave ~now+16min: set event start far enough that −15/−10/−5 are all future). Practically: pick start so leave = now+16min → −15 fires in 1 min.
  3. `node ~/anicca/skills/life/planner.js` → registers the future `--at` jobs.
  4. `openclaw cron list --json` → assert 3 jobs `life-call-<stamp>-LM-E4-test-{15,10,5}` exist with correct `--at` times.
  5. WAIT through the offsets.
- EXPECTED:
  - 3 `--at` jobs registered (T−15/−10/−5), times correct (UTC), `toolsAllow:["exec"]`, delete-after-run.
  - **Dais's real phone RINGS at each of −15, −10, −5.**
  - Charon SPEAKS the specific event: "next event is LM-E4 test at <time>, it's at 大崎駅 — time to leave." Tone ESCALATES: −15 calm heads-up; −10 firmer; −5 urgent/harsh ("leave NOW or you'll be late").
  - After each fires, its job auto-deletes; re-running `planner.js` does NOT re-register fired/past offsets (no double-call).
- EVIDENCE: `openclaw cron list` before (3 jobs) → after (0); Telnyx call-id per call; Gemini-Charon audio present; the spoken transcript per offset showing event name + escalating urgency.

### LM-E5 — late → stakeholder after approval (bullet 5)
- GOAL: predicted-late → approval mail to Dais → "OK" reply → stakeholder notified (test address).
- PRECONDITION: NOTIFY_TRANSPORT=gog; NOTIFY_TEST_STAKEHOLDER=you@example.com (safety).
- STEPS:
  1. Insert event "LM-E5" with a [Travel] block whose start is already in the PAST (running late).
  2. `NOTIFY_TRANSPORT=gog node ~/anicca/skills/life/notify/notify.js scan`
  3. Check you@example.com for the approval mail (draft + token AN-XXXX). Reply "OK".
  4. `NOTIFY_TRANSPORT=gog node ~/anicca/skills/life/notify/notify.js poll`
- EXPECTED: step 2 sends an approval email (draft to stakeholder shown, token present), saves a pending record in `~/.openclaw/state/life-notify-pending.jsonl`; after "OK" reply, step 4 sends the stakeholder mail (to the TEST address) and marks the pending record `sent:true`.
- EVIDENCE: approval mail id + pending jsonl record + the sent stakeholder mail id + record sent:true.

---

## Pass gate
LM-local is DONE only when LM-E1..E5 are ALL green with fresh evidence, AND the whole skill runs from
`~/anicca/skills/life/` with ZERO reach into anicca-products / aniccaai.com (verified by grep: no
ANICCA_PRODUCTS, no aniccaai.com, no postNetlify in skills/life). Then S8 finishing (merge+push).
