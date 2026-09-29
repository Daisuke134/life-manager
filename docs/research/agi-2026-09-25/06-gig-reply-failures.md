# Gig reply/application failure audit — evidence for eval golden-cases

Scope: read-only. Code read from `origin/main` (local checkout is on an unrelated branch).
Runtime evidence read from `~/gig/*` (live loop state, NOT in git). No provider/browser calls made.
Buyer text below is paraphrased/redacted per instructions; no raw buyer message, name, or ID beyond
Coconala numeric thread IDs (already pseudonymous, not PII) is quoted verbatim.

## 1. Pipeline map (Coconala — the only platform with live reply state, see §2)

Intake → decision → compose → send, all inside `skills/earn/gig/scripts/`:

- **Intake / snapshot**: `coconala_queue_snapshot.py` (talkroom scrape) feeds
  `reply_detector.py`. Entry point `main()` at `reply_detector.py:2470`.
- **Per-thread decision core**: `reply_detector.py:_run_effect_pipeline` (`reply_detector.py:1444-1751`).
  This is the single chokepoint all sends and all suppressions pass through.
  - Semantic gate: `semantic_ready` computed at `reply_detector.py:1500-1512`; if not
    ready or `semantic_failure` is set, thread is parked, not answered
    (`reply_detector.py:1613-1618`, error `semantic_action_not_authorized`).
  - Intentional no-send: `next_action in _TARGETED_INTENTIONAL_NO_SEND` closes the
    action with **no reply sent**, via `_targeted_close_no_send` (`reply_detector.py:1517-1533`).
  - Paid-thread fence: `_paid_fence_open_for_thread` / `_close_paid_handoff`
    (`reply_detector.py:1619-1631`) — a thread already inside a paid-handoff
    fence never gets a normal reply.
  - Estimate branch: routed to `run_requested_estimate` (`requested_estimate.py`,
    called at `reply_detector.py:1683-1691`) instead of a normal composed reply.
- **Model call (composition)**: `reply_lane.py:process_queue` (`reply_lane.py:245`) invokes
  `reply_composer.py`'s `RunnerComposer.__call__` (`reply_composer.py:238-289`), which shells
  out to `runtime/agent-runner/agent_runner.py` with `--task-class composition-agent` and
  schema `skills/earn/gig/schemas/reply_composition.schema.json`. Prompt built in
  `composition_prompt()` (`reply_composer.py:164-193`) — this is where the actual reply text
  the buyer sees is generated; it embeds a large fixed rule list (no unsolicited CTA, no future-tense
  delivery promises, one open question max, hard-decline rules for video editing, etc.).
- **Semantic classification of buyer intent**: `buyer_reaction_classify.py` (schema
  `buyer_reaction.schema.json`) and `reply_detector.py`'s semantic step (schema
  `reply_semantic_judgement.schema.json`, loaded at `reply_detector.py:1787,2492`) — this is
  what decides `next_action` / `semantic_failure` before the compose step ever runs.
- **First-contact decision**: `first_contact.py` (schema `first_contact_decision.schema.json`,
  `first_contact.py:75`) — separate model call gating whether an inbound thread gets a first
  reply at all.
- **Send**: inside `reply_lane.py:process_queue`, dedup via `near_duplicate_reply.is_near_duplicate`
  (`near_duplicate_reply.py:35`), no-contact registry check `no_contact_policy.match_thread`
  (`no_contact_policy.py:66`), then browser send via `coconala_reply_browser.py`, with official
  on-screen readback required before the action is marked `replied` (state machine in
  `connector-outbox.sqlite3`, see §3).
- **Deterministic suppression surfaces** (can block a reply without a model call):
  `project_effect_fence.py` (paid-conversation fence), `operator_brake.py` (global pause),
  `followup_gate.py:decide` (`too_soon`, `draft_violation`), `no_contact_policy.py` (explicit
  stop-contact registry), `silence_liability.py` (closed-enum refusal reasons).

## 2. Runtime evidence stores found (outside git)

| Path | Size | Notes |
|---|---|---|
| `~/gig/` | 13 GB total | loop working tree; NOT a git-tracked area |
| `~/gig/connector-outbox.sqlite3` | 688 KB, mtime 2026-09-13 | **the real reply ledger** — `connector_actions`, `connector_dlq` tables |
| `~/gig/reply-transcripts.jsonl` | 1.4 MB, 1071 lines | every **composed** reply body + buyer's last message + full conversation, Coconala only |
| `~/gig/work-events.jsonl` | 2643 lines | mixed event kinds; only 26 `reply` + 1 `talkroom_reply` rows, all dated 2026-08-06→08-10 (a one-off backfill, not a live feed — do not use for reply metrics) |
| `~/gig/buyer-outcomes.jsonl` | 38 lines | buyer-reaction labels (`positive`/`neutral`/`revision_request`), too small a sample to trend |
| `~/gig/applied-outcomes.jsonl` | 549 lines | **application** outcomes, not reply/buyer-message outcomes |
| `~/gig/evidence/` | 109 MB | per-run evidence dirs (`reply-detector-<run>-<pid>`, `gig-pass-*`); grep for `semantic_action_not_authorized` / `effect_unknown` inside recent dirs returned no hits — reason codes live in the DLQ table, not per-run evidence text |
| `~/gig/freelancer/bid-watch.jsonl` | small | Freelancer bid state only, no talkroom-style reply data |
| `~/.local/share/anicca/gig/` | 0 B | empty — nothing stored here |
| Lancers / CrowdWorks | none found | no `~/gig/lancers`, `~/gig/crowdworks` state dir, no separate sqlite/jsonl. Code (`skills/earn/lancers/scripts/reply_adapter.py:1-2`, `skills/earn/crowdworks/scripts/reply_adapter.py`) says both are "thin adapters for the shared marketplace Reply kernel," but there is **no local runtime evidence of them ever actually running a buyer-reply pass** — see Data gaps. |

## 3. Reconstructed numbers (Coconala, last ~60 days, from `connector-outbox.sqlite3`)

Query: `select state, count(*) from connector_actions where created_at > <60d-ago-epoch> group by state;`

| state | count | meaning |
|---|---|---|
| `replied` | 320 | reply composed, sent, and readback-verified on-screen |
| `pending` | 226 | queued, not yet resolved — includes threads **1200–1400+ hours old (50-58 days)** still open |
| `blocked` | 19 | parked, human/logic block; several threads blocked **860–1620 hours (36-67 days)** |
| `reconcile_pending` | 2 | mid-reconciliation |

So of ~567 non-blocked actionable threads opened in 60 days, **320 got a verified reply (56%)**, and
**226 (40%) are still sitting unresolved**, many for 5-8 weeks. This "pending" backlog is evidence
supporting the owner's report of "does not reply enough" independent of any single bad decision — it
is a throughput/backlog problem, not (only) a quality problem.

DLQ (`connector_dlq`, 241 rows, all within the 60-day window — this is the whole DLQ history) reason
breakdown — this **is** the taxonomy of *why a thread got no reply*:

| reason | count | verdict |
|---|---|---|
| `nothing_to_say:targeted_identity_superseded_seller_last` | 108 | correct suppression — seller already replied last |
| `nothing_to_say:seller_last` | 32 | correct suppression |
| `nothing_to_say:stop_contact` | 22 | correct suppression — buyer asked to stop |
| `consecutive_failures:CollectorUnhealthy:...dm_attachment_message_identity_changed` | 17 | **real failure** — attachment messages break identity tracking, thread silently abandoned |
| `nothing_to_say:observe` | 14 | correct (observe-only phase) |
| `nothing_to_say:semantic_not_estimate` | 10 | ambiguous — needs a golden case to confirm |
| `nothing_to_say:estimate_no_longer_required` | 10 | correct |
| `nothing_to_say:requested_estimate` | 9 | ambiguous |
| `nothing_to_say:officially_unrepliable:submit_rejected_sending_unavailable` | 7 | **real failure** — Coconala UI rejected sending, buyer got nothing |
| `nothing_to_say:officially_unrepliable` | 3 | **real failure** |
| `revision_budget_exhausted` | 1 | **real failure** — ran out of compose retries |
| `nothing_to_say:ignore_policy:operator-owned-*` | 2 | correct (owner manually handling) |
| `nothing_to_say:buyer_message_after_estimate` | 1 | ambiguous |
| `estimate_readback_unresolved` | 1 | **real failure** |
| `consecutive_failures:...reply composer failed rc=N (token budget)` | 1 | **real failure** — token/budget cap suppressed reply |
| `consecutive_failures:...missing_message_input` | 1 | **real failure** |
| `consecutive_failures:...lease_busy` | 1 | infra contention, retryable |
| `consecutive_failures:CollectorUnhealthy:unexpected_title` | 1 | infra |

**~35-40 of 241 DLQ closures (≈15%) are real no-reply failures**, not correct suppression. The rest
(≈85%) are the gate working as designed. This is the opposite skew from what a naive read of "241
threads never got a reply" would suggest — the bigger problem is the **226 still-pending backlog**,
not the DLQ.

Median reply latency, off-target rate: **not directly computable** from available fields —
`connector_actions` has `created_at`/`updated_at` but not a clean "buyer message time → reply sent
time" pair for the full 60-day set; `reply-transcripts.jsonl` has real content but only 340/1071 rows
carry a real (non-test) `sent_at` in the last 60 days, and it records **composed**, not necessarily
**sent**, replies (see §4 example — composing ≠ sending here).

## 4. Concrete failure examples (paraphrased, redacted)

**Thread 10027881 — repeated re-pitch after explicit decline (most severe finding).**
Buyer's last message (paraphrased): "we haven't even finalized anything yet — why is there already a
billing/quote screen? Go find someone else." The connector action for this thread (`action_id 70`)
sat in state `pending` continuously; meanwhile the composer ran **28 separate composition passes on
the same thread in ~26 hours** (`reply-transcripts.jsonl`, `talkroom_id":"10027881"`), each producing
a near-duplicate apology + the *same* unsolicited service re-pitch (scope, price ceiling, delivery
timeline) that the buyer had just rejected. None of the 28 reached "replied" state, so the buyer likely
never saw all 28, but it shows the composer/semantic layer has **no explicit "buyer declined, stop
re-pitching" terminal state** for this path — only a generic retry loop. This is a golden case for a
taxonomy-C+D combination (ignores explicit decline **and** self-repeats).

**Thread 10057948 — inconsistent decline framing.** Buyer message included a soft compliance check
(asked about tool experience + an AI-use restriction). Agent replied with a blunt double decline
("cannot meet the requirement / cannot take this request") in one message, then in a later turn,
after the buyer formally withdrew, replied with an appropriately brief acknowledgement. Two different
policy branches (hard decline vs. polite close) fired on what was functionally one interaction —
worth a golden case to pin down which one is "correct."

**Thread 9967694 / 9967721 / 9993478 / 9995190 / 10003344 — earliest `blocked` actions (action_ids
1,2,4,5,8), oldest in the ledger, still `blocked` 1620h (~67 days) later with zero reconcile attempts
recorded.** No corresponding row in `reply-transcripts.jsonl`, so these never even reached the compose
step — blocked upstream of the model call. Root cause not confirmed from evidence alone (data gap).

**Thread 10110941 / 10107358 — same thread_id opened as a *new* `blocked` action 3-4 separate times**
(`action_id` 413/419/422/428 for 10110941; 472/473/474/475 for 10107358), each superseding the last —
consistent with a retry/re-open loop that never resolves rather than four independent buyer messages.

**Collector-unhealthy attachment failures (17 DLQ rows).** Reason string
`collector_unhealthy:dm_attachment_message_identity_changed` — a buyer sends a message with an
attachment, the collector cannot re-derive a stable identity hash for it, the thread is dropped after
consecutive failures. This is a clean, reproducible taxonomy-A case: **any buyer message with an
attachment is at elevated risk of getting zero reply.**

**"Officially unrepliable" (10 DLQ rows total).** Coconala's own UI refused to let a reply be sent
(`submit_rejected_sending_unavailable`) — buyer asked something, agent had a ready answer, but the
platform blocked sending. Not an agent quality bug, but still a "buyer got no reply" case worth
tracking separately from model failures.

**5 good-reply contrast examples** (from `reply-transcripts.jsonl`, non-10027881 threads): threads
10008720, 10012594, 9942584, 10058344, 10057717 (multi-turn) show the composer correctly (a) answering
a translation-language question directly with a concrete turnaround estimate, (b) giving a polite
no-pressure close when a buyer's request had gone cold, (c) directly stating portfolio availability
without asking the buyer an unnecessary clarifying question, and (d) integrating buyer-supplied
character/story detail into a substantive, non-generic pitch. These read as on-target and are good
default "PASS" anchors for the eval.

## 5. GitHub issues (search: reply/返信/talkroom/buyer, `Daisuke134/life-manager`)

Most relevant, all `OPEN`:
- **#767** "daily-quota SNS reply gigs = structural mismatch distinct from real-time-response skip" —
  names a whole gig category where the agent structurally cannot keep up with reply cadence.
- **#756/#757** "即レス/24時間稼働 requirement = structural auto-skip" — confirms the team already
  treats "must reply instantly/24h" gigs as an explicit skip category (`skip_category` in
  `strategy.json`), i.e. a deliberate, not accidental, "does not reply" path.
- **#728** "45-application accept-rate audit (~2%)" — adjacent (application, not reply), but the same
  audit-methodology pattern requested here.
- **#1038/#1029/#1070/#1069/#1176** — mostly delivery/formal-confirmation and thread-routing lessons,
  not reply-content quality; lower relevance.
- Everything else in the 40-result search is `[gig-lesson]` entries about applications, CDP bugs, or
  unrelated `self-improve` bootstrap-failure noise (2026-06-22 liquidity loop) — not reply-specific.

## 6. Failure-mode taxonomy with counts (Coconala, last 60 days, evidence-backed)

| Code | Description | Count (evidence) |
|---|---|---|
| A | No reply — infra/collector failure (attachment identity break, lease busy, unhealthy tab) | 19 DLQ rows |
| B | No reply — capacity/backlog (queued, never reached in time) | **226 currently pending**, ages up to ~58 days |
| B2 | No reply — stuck `blocked` with zero progress | **19 currently blocked**, ages up to ~67 days |
| C | Reply ignores buyer's stated decision (re-pitches after explicit "no") | 1 confirmed severe case (10027881, 28 composes); prevalence beyond this thread not yet counted — recommend grep across full history for `他の方` / `結構です` / `辞退` phrases co-occurring with repeat compose |
| D | Over-cautious / policy-driven no-send correctly firing (not a bug) | ~205 of 241 DLQ rows (`nothing_to_say:*` minus the officially-unrepliable ones) |
| E | Slow (median latency) | not computable from current fields — data gap |
| F | Reply blocked by platform, not by agent | 10 DLQ rows (`officially_unrepliable*`) |
| G | Reply budget/quota exhausted | 2 DLQ rows (`revision_budget_exhausted`, token-budget composer failure) |
| H | Structural skip by design (real-time-response gigs) | category-level, per gh#756/#757/#767, not counted per-thread here |

## Evidence vs. inference

**Evidence** (directly read, cited above): pipeline file:line map; `connector-outbox.sqlite3` state
and DLQ counts; `reply-transcripts.jsonl` content for thread 10027881 and the 5 good/bad examples;
gh issue list and titles.

**Inference**: which `nothing_to_say:*` DLQ codes are "correct" vs. "ambiguous" is my read of the
reason string semantics, not a verified per-case audit of buyer intent — flagged "ambiguous" above
where I did not check the underlying thread. The claim that thread 10027881's 28 composes reflect a
systemic bug (vs. a one-off) is inference from one thread; I did not scan all 1071 transcript rows
for the same pattern (time-boxed).

## Data gaps (explicit)

1. **Lancers/CrowdWorks have no local runtime evidence at all** — cannot state per-platform reply
   counts/latency/quality for them from `~/gig`. Either they have not run a live reply pass yet, or
   their state lives somewhere not found in this pass (checked `~/gig`, `~/loops/state` [does not
   exist], `~/.local/share/anicca`, `~/Library/Application Support`). Recommend asking the owner or
   checking launchd job logs (`~/gig/launchd-backups`, `~/gig/logs`) directly.
2. **No clean buyer-message-time → reply-sent-time pairing** exists in the tables read, so median
   reply latency is not computed here — would require joining `connector_actions.created_at` against
   the actual buyer message timestamp from the snapshot evidence (not the action's own timestamp),
   which needs a per-thread evidence-dir read not done in this pass.
3. **Off-target rate (ignored question / wrong language / asked for already-given info) is not
   counted systematically** — only spot-checked via a 30-row random sample plus the 10027881 deep
   dive. A full pass would need an LLM-graded read of all 340 recent transcript rows against their
   buyer_last_said, which is exactly the eval this report is feeding, not something to hand-roll here.
4. `~/gig/evidence` per-run dirs did not contain the `semantic_action_not_authorized`/`effect_unknown`
   strings on a shallow grep of directory names/newest dirs — the actual reason codes for those gates
   live in the DLQ table (§3), not in per-run evidence text; a broader `grep -r` over all 109 MB was
   not run (time-boxed).

## Recommended next step

Build the golden-case set from: (a) the 108+32+22=162 `nothing_to_say:*` correct-suppression DLQ rows
as PASS anchors, (b) the ~19 `officially_unrepliable`/`revision_budget_exhausted`/token-budget rows as
"real failure, not agent's fault" anchors, (c) thread 10027881 as the flagship "ignores explicit
decline" FAIL case, and (d) the 17 attachment-identity DLQ rows as the flagship "infra breaks reply"
FAIL case. That is already 15-20 golden cases with hard evidence; expand quality-judgement cases (off-
target replies) only after an LLM-graded pass over `reply-transcripts.jsonl`, per gap #3.
