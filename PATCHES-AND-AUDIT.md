# Life Manager LOCAL — AUDIT (AS-IS) + PATCHES (TO-BE + literal diffs) — 2026-06-17

Ruthless audit (assume nothing works). Goal: consolidate ALL of Life Manager into ONE repo
(`~/anicca/skills/life/`), self-contained, and make every product bullet ACTUALLY work, proven by
real E2E (see `E2E-SPEC.md`). Nothing is "done" because a cron exists — only because its E2E passes.

## TOP-LEVEL TRUTH (the scatter + what's actually live)
| area | files (3 places) | what actually runs | verdict |
|---|---|---|---|
| travel | `skills/life/travel/travel.js` (OSS, **DEAD**) · `~/.openclaw/skills/anicca-travel-fill/scripts/travel_fill.py` (**LIVE**) · `apps/landing/.../travel-logic.js` (web) | cron `anicca-travel-fill` → **travel_fill.py** | live one is prev→curr + home-skip + real Directions; but `or 45` silent fallback + skips unknown instead of asking. travel.js is dead + buggy. |
| ask | `skills/life/ask/ask.js` + web `life-ask.js`/`ask-logic.js` | cron 21:00 sends question via **Gmail**; reply expected via **AgentMail webhook** | **LOOP NEVER CLOSES** (Gmail reply ≠ AgentMail webhook). |
| notify | `skills/life/notify/notify.js` + web twins | cron scan(*/10)+poll(*/5), `NOTIFY_TRANSPORT=gog` | runs, but "late" = travel-block-start-passed with NO motion check → false alarms. |
| call | `skills/life/call/call.js` → `apps/landing/scripts/{life-call-telnyx.mjs,call-bridge.cjs}` + `_lib/call-logic.js` | **NO cron** | call chain real, but event/urgency severed → generic "dentist" call; never triggered. |
| locate | `skills/life/locate/locate.js` | **NO cron** | unreachable; offsets 15/14/13/5 (wrong); no tone escalation; calls placeCall({}) generic. |

**Decision (recommend): adopt the LIVE `travel_fill.py` as canonical travel** (move into `skills/life/travel/`, delete dead `travel.js`, repoint the cron), because it already does the hard part correctly. Fix its 2 gaps. Consolidate call runners + locate producer into `skills/life/`. Make ask reply-ingestion local+Gmail. Wire call/locate cron. Thread event+urgency for escalation.

═══════════════════════════════════════════════════════════════════════════
## P1 — TRAVEL (bullet 2): adopt travel_fill.py + fix "ask when unknown" + no silent fallback
- AS-IS: `travel.js` DEAD (origin=HOME hardcode L206, 20-min fallback L31/166/182, home events only skipped if empty-location L151). LIVE `travel_fill.py`: correct prev→curr (L274), home-routine skip (L50/93), real Directions (L170), BUT `travel_min = directions_minutes(...) or 45` (L302) silently guesses 45; unknown-location pair → `skipped_unknown` (L284) silently, never asks.
- TO-BE: one canonical travel under `skills/life/travel/`. Origin = prev event loc / live loc / home. Real Directions. Home-routine skip. **On unknown location OR no route → enqueue an ASK (email the user), do NOT guess and do NOT silently skip.**
- DIFF:
  - DELETE `skills/life/travel/travel.js` (dead). MOVE `travel_fill.py` → `skills/life/travel/travel_fill.py`; repoint cron `anicca-travel-fill` run.sh to the new path.
  - `travel_fill.py:302`:
    ```diff
    -        travel_min = directions_minutes(prev_addr, curr_addr) or 45
    +        travel_min = directions_minutes(prev_addr, curr_addr)
    +        if travel_min is None:
    +            enqueue_ask(curr, reason="no_route")   # email Dais, do not guess
    +            continue
    ```
  - `travel_fill.py:284`:
    ```diff
    -        if not (prev_addr and curr_addr) or kind == "unknown":
    -            summary["skipped_unknown"] += 1
    +        if not (prev_addr and curr_addr) or kind == "unknown":
    +            enqueue_ask(curr, reason="unknown_location")  # ask instead of silently skipping
    +            summary["asked"] += 1
            continue
    ```
  - NEW `enqueue_ask(event, reason)` in travel_fill.py → writes a row to `~/.openclaw/state/life-ask-queue.jsonl` that `ask.js` reads (shared queue), so travel + ask are one loop.

## P2 — ASK (bullet 3): close the reply loop LOCALLY via Gmail (send-channel == read-channel)
- AS-IS: `ask.js` detection is on the WEB (`postNetlify` → aniccaai.com, L91/53). Question sent via `gog gmail send` (Gmail, L140). Reply expected via **AgentMail webhook** → loop never closes. `markError` non-fatal (L154).
- TO-BE: detect locally (read `life-ask-queue.jsonl` from P1 + local gcal scan), send question via gog Gmail, and **poll Gmail for the reply** (mirror `notify.js runPoll`), parse `Event ID:` + answer, register via gog calendar patch. No AgentMail, no aniccaai.com.
- DIFF:
  - REMOVE `postNetlify`/`SITE_URL` (ask.js L53,91-109). Replace `--action question` detection with local: read `life-ask-queue.jsonl` + gog event scan.
  - NEW `runReplyPoll()` (mirror notify.js:497): `gog gmail search 'from:DAIS subject:"[Ask]" newer_than:2d' -j` → body → `/Event ID:\s*(\S+)/` + parse location → `gog calendar` patch the event location → travel re-runs next cycle.
  - NEW cron `anicca-life-ask-poll` (*/10) → `node skills/life/ask/ask.js --action poll`.
  - L154: `if (asked.some(x=>x.error||x.markError)) process.exit(1);`

## P3 — CALL CHAIN (bullet 4): thread event + urgency so Charon names the event + escalates
- AS-IS: `placeCall` (call.js:65-73) only passes `provider/to/dryRun` — **no event, no urgency**. Runner `life-call-telnyx.mjs` (L38-41) parses only `--to/--dry-run`, spawns bridge without `--event` (L138). `call-bridge.cjs` DOES support `--event` (L159) but defaults to hardcoded dentist (L177-181). `buildCallPrompt(event)` (call-logic.js:367) has NO urgency param, one calm tone.
- TO-BE: `placeCall({event,urgency})` → runner forwards `--event`/`--urgency` → bridge → `buildCallPrompt(event,urgency)` selects calm/firm/harsh + includes leave-time/route. Delete dentist default.
- DIFF (literal):
  - `call.js` placeCall (after L67 `if (opts.to)...`):
    ```diff
     if (opts.to) args.push(`--to=${opts.to}`);
    +if (opts.event) args.push(`--event=${JSON.stringify(opts.event)}`);
    +if (opts.urgency) args.push(`--urgency=${opts.urgency}`);
     if (opts.dryRun) args.push("--dry-run");
    ```
    + parse `--event=`/`--urgency=` in the CLI block (L81-86).
  - `life-call-telnyx.mjs` L38-42: parse `--event=`/`--urgency=`; bridge spawn (L138) append `...(EVENT?["--event",JSON.stringify(EVENT)]:[]), ...(URGENCY?["--urgency",URGENCY]:[])`.
  - `call-bridge.cjs` parseArgs (L149-163): add `--urgency`; remove dentist default (L177-181) → if no event, exit (no fake call).
  - `call-logic.js buildCallPrompt(event)` → `buildCallPrompt(event, urgency)` (L367):
    ```diff
    -    "Tell them it's time to leave now so they arrive on time, then ask if they need directions or anything else.",
    +    urgency === "harsh" ? "Be urgent and firm: they must leave RIGHT NOW or they will be late. Push them." :
    +    urgency === "firm"  ? "Be firm: it is really time to go now." :
    +                          "Gently remind them it's about time to head out.",
    ```
    + include `e.leaveBy`/`e.travelMinutes`/`e.route` in the spoken guidance.

## P4 — LOCATE/SCHEDULER (bullet 4): offsets 15/10/5, escalation, wire a cron, pass the event
- AS-IS: NO cron (unreachable). offsets `"15,14,13,5"` (L53, wrong). `dialOnce` (L187-194) `placeCall({})` generic, ignores `emergency`. No tone mapping.
- TO-BE: offsets `15,10,5`; map offset→tone (15 calm/10 firm/5 harsh); pass the specific event; a planner registers `openclaw cron add --at` one-shots per event×offset (schedule-based; see step1 v3 planner pattern, but pass `--event`+`--urgency`).
- DIFF:
  - `locate.js:53` `"15,14,13,5"` → `"15,10,5"`.
  - `dialOnce` (L187-194): `return placeCall({ event: opts.event, urgency: opts.urgency });`
  - schedule consumers (L255 / runScheduleLoop): `dial({ event, urgency: toneFor(d.offsetMin), ... })` where `toneFor=o=>o>=15?"calm":o>=10?"firm":"harsh"`.
  - NEW `skills/life/planner.js` (from step1 v3, corrected): for each event×[15,10,5] future offset → `openclaw cron add --at <iso> --delete-after-run --tools exec --message "node skills/life/call/call.js --event '<json>' --urgency <tone>"`. NEW cron `anicca-life-plan` (*/10).

## P5 — NOTIFY (bullet 5): gate "late" on real motion, broaden approval, one transport
- AS-IS: `isLateRisk` (L131-133) flags late the instant travel-block-start passes — NO motion check → false alarms. `extractApproval` (L231-240) accepts only ok/はい → "yes"/"go" silently dropped. Dead AgentMail branch (L412-443).
- TO-BE: late = (travel start passed + GRACE) AND `!hasMoved(origin, live)`. Broaden approval vocab or require explicit token. Delete dead AgentMail path.
- DIFF:
  - `isLateRisk` (L131-133): add `&& !locate.hasMoved(origin, live) && nowMs > travelStartMs + GRACE_MS`.
  - `extractApproval` (L235): add `|yes|go|送って|承知|おk`.
  - Delete AgentMail scan/webhook (L336-348, 412-443, 452-493).

## P0 — CONSOLIDATION (Dais: one repo, run inside anicca)
- MOVE into `~/anicca/skills/life/`: `apps/landing/scripts/{life-call-telnyx.mjs,life-call.mjs,call-bridge.cjs}` + `_lib/call-logic.js` → `skills/life/call/lib/`; `travel_fill.py` → `skills/life/travel/`; telegram location producer → `skills/life/locate/`.
- REWIRE `call.js productsRoot()` (L39-46) → in-repo `skills/life/call/lib/`.
- VERIFY: `grep -rn "ANICCA_PRODUCTS\|aniccaai.com\|postNetlify" skills/life` = 0.
- Web (STEP 2) later imports from anicca or is rebuilt; not STEP-1's concern.

## Done = E2E-SPEC.md LM-E1..E5 all green (real gcal/phone/mail) + grep-0 self-contained. No pretending.
