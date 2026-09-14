# Gig revenue program — current execution SSOT

This file contains only current truth and remaining work. Completed incident detail is preserved in Git
history through commit `e2b30b8e10`; it must not be copied back into the active TODO. Evidence lives in
durable runtime ledgers and receipts, not in duplicated historical checklists.

## Account 1 restart cursor

This is the only restart cursor for the next Codex session. Re-check every value against Git and official
runtime/provider readback before acting; conversation claims are not completion evidence.

- Repository: `/Users/anicca/Projects/life-manager-main`, remote `Daisuke134/life-manager`.
- Runtime implementation worktree: `/private/tmp/lm-runtime-admission-reservations-20260914`, branch
  `fix/runtime-admission-reservations-20260914`, upstream of the same name. Pushed clean HEAD is
  `4ac009092fdebcec225d5516a9de444e6a15f5f7`; PR `#5193` is merged at main
  `3fbe75546d720add1bfa465731ddc94353b662b5`. Preserve this worktree until production activation and natural
  proof finish; do not delete or reuse it for another task.
- Phase 2 replaces the v2 JSON scan with stdlib SQLite, adds durable FIFO reservations, child-PID claim
  handoff, same-owner/crash recovery, exact loaded-idle dispatch, retired/missing-owner cancellation, a
  default-v1 mixed-release gate and `lm-loop admission-v2-enable`. Final evidence is 500 sequential enqueues in
  1.872 seconds, 39/39 simultaneous enqueues persisted, 69 host tests, 464 loop tests plus 470 subtests, 67
  registry tests plus 100 subtests, exact stdlib CI discovery 434 tests, fresh read-only `ship`, and GitHub CI
  8/8 PASS. Earlier JSON 500-enqueue evidence was 35.93 seconds.
- Spec worktree: `/private/tmp/lm-coconala-retained-attachments`, branch
  `docs/coconala-current-cursor-20260914`. This file is the current remaining-work SSOT. Its eventual canonical
  name/location must be derived from repository conventions and references, then migrated once without
  creating a second live TODO.
- Ryu and Coconala are not complete. No current official readback proves that the newest Ryu buyer event is
  covered by a later seller submission. Never report completion from a historical message or local state.
- Account migration is open: identify the account 1 Codex auth/provider profile through the credential SSOT,
  prove one bounded invocation, then roll only the intended Life Manager Codex routes forward. Preserve all
  Codex/cloud sessions and unrelated providers.
- First safe action: keep admission protocol at `1`, observe old-release finite owners ending naturally, and
  repeatedly reconcile only newly loaded-idle labels to immutable release
  `/Users/anicca/loops/releases/20260915T025232-3fbe7554`. Never restart a running sibling. Enable protocol `2`
  only when every finite label has exact current loaded argv and legacy owners/tickets plus SQLite work are
  idle; then prove natural fairness/recovery before Coconala browser effects.

## Outcome

Life Manager autonomously earns attributable revenue across Coconala, Lancers, CrowdWorks, Mercor,
Freelancer.com, Upwork and newly discovered platforms. Every supported lifecycle runs 24/7 without Dais or
Codex babysitting, shares one runtime and marketplace kernel, resumes from durable state, verifies official
effects, prevents duplicates, heals failures and improves itself. The first measured revenue gate is USD
10K MRR; applications, health checks and projected value do not count as revenue.

## Non-negotiable contracts

- Scheduler registration and a PID are not health. Every wake ends with a bounded terminal receipt.
- Each client is an independent work item. Clients, lanes and platforms run concurrently.
- Every external mutation uses prepare -> effect fence -> official readback -> terminal receipt -> replay-zero.
- Uncertain effects are reconciled officially before retry. Never guess and never duplicate.
- Buyer conversation, files, requirements and decisions are cumulative durable context.
- Shared runtime, browser leasing, Telegram, Calendar, receipts, evals and marketplace lifecycle are reused.
  Providers implement only thin official-surface adapters.
- KYC, interviews and person-bound media may use typed minimal-human Telegram handoffs. Everything else is
  autonomous. Meetings are added to Google Calendar with the join URL and a five-minute reminder.
- Never fake applications, messages, delivery, spreadsheets, revenue or readback.
- Do not apply for work whose required numerical outcome cannot be delivered within the paid scope. Prefer
  concrete artifacts and services whose completion is controllable.
- A historical seller message is never proof that a talkroom is currently handled. Completion requires the
  newest official buyer event to be covered by a later seller effect and official readback. If durable
  `next_action` conflicts with a newer buyer-event digest, the buyer event wins and the item returns to work.
- Chii remains an active paid contract until the official room and the truthful DM-result ledger prove the
  contracted outcome. Never invent recipients, sends or spreadsheet rows.

## Shared architecture

```text
config/
runtime/
  scheduler/ admission/ queue/ workers/ effects/ browser/
  receipts/ observability/ self_healing/ self_improvement/
domains/
  marketplace/{apply,reply,paid,storefront}/
providers/
  {coconala,lancers,crowdworks,mercor,freelancer,upwork}/
loops/
  {revenue,platform_discovery,loop_builder,self_heal,self_improve}/
evals/
  {conformance,replay,fault_injection,revenue}/
skills/
docs/
```

## Current measured state

### Shared host/runtime

- PR `#5193`, main SHA `3fbe75546d720add1bfa465731ddc94353b662b5`, is merged and published as
  immutable release `/Users/anicca/loops/releases/20260915T025232-3fbe7554`. The safe two-stage rollout keeps
  protocol `1` until every finite label is exact-loaded from this capability-2 release. Initial loaded-idle
  reconciliation completed with failures 0: deterministic had 53 eligible results, 44 changes and nine
  snapshot-race running skips; shared-agent-runner changed 33 labels. A later targeted pass moved Coconala
  Apply, Reply, Paid and Storefront to the new release after each old wake ended naturally. Repeated current-SHA
  natural wakes now write bounded effect-zero `host_admission_deferred:resource_control_busy` terminal events;
  they do not yet prove business recovery or official provider readback. Fleet convergence reduced finite
  installed mismatches from 51 to 38. Current admission readback is protocol `1`, owners `3`, legacy tickets
  `4`; v2 activation, natural fairness, recovery, replay-zero and 24-hour proof remain open.
- PR `#5192`, main SHA `6a901db5011da29a05ef91422c7ee745c8fa6e51`, is the compatibility-first
  admission rollout. It preserves future-version durable tickets during mixed-release convergence and records
  the exact bounded admission reason instead of collapsing every deferral to `host_admission_deferred`.
  Its exact head passed 31 focused tests, 493 runtime tests plus 470 subtests, all CI and fresh read-only review.
- The first targeted Paid wake on `6a901db5` started normally and terminated without an external effect at
  `2026-09-14T14:02:40.631497+00:00` with
  `host_admission_deferred:memory_headroom_unavailable`. It did not observe or reply to Ryu. This proves precise
  classification, not recovery or client completion.
- Durable fairness implementation is merged, but production activation and natural proof are still open. The
  lock-protected path is `queued -> dispatch_reserved -> claimed -> running -> released`, with monotonic
  sequence, reservation lease recovery, child-PID ownership and out-of-lock target kickstart. Protocol `1`
  remains the correct production mode during mixed-release convergence.

- PR `#5184`, main SHA `b8de9bf2d230514587bb455f59a3e866ec27f658`, fixes scheduled resource
  admission. Busy wakes attempt once, retain no ticket, write effect-zero deferred state and exit `75`.
- PR `#5186`, main SHA `3e7b77714d92e179806970d353f7c9db2f8dfed6`, removes every external
  process-identity probe from the shared admission critical section. It snapshots all identities once outside
  the lock, fails closed on snapshot failure and preserves rows created during the snapshot. Race tests,
  100-ticket scale coverage, 47 host tests, all CI and a fresh read-only review pass.
- PR `#5187`, main SHA `59bd6cddaf2768a98da6373480043672db657713`, makes explicit-loop
  reconciliation read only the requested launchd labels instead of enumerating the full fleet. Production
  read-only latency fell from about 37 seconds to 1.4--2.4 seconds; 70 tests plus 30 subtests, all CI and a
  fresh read-only review pass.
- PR `#5188`, main SHA `d80e7359127a9bc591463ee4b6b3ea2528f8639a`, removes synchronous evidence
  garbage collection from Apply's revenue-critical path. The observed old run spent about 28 minutes scanning
  412 MiB and reclaimed zero bytes because it was below the 400 MiB high watermark. GC now has an independent
  six-hour deterministic owner, and active evidence is protected by a PID plus process-start-identity pin.
- PR `#5189`, merge SHA `0a7b8c8b75899137bf28236e3c2e47fe1a3a0a91`, removes recursive run-tree
  cleanup from every business wake. Per-run scratch is created through state-root-anchored directory FDs;
  terminal evidence is protected before business execution; only exact PID plus process-start identities are
  reclaimed by the central owner. Ancestor symlink, run replacement, terminal-write failure and no-clobber
  races are covered. Targeted 45 tests, the 425-test runtime suite, all CI and fresh Terra architecture review
  pass.
- Immutable release `/Users/anicca/loops/releases/20260914T211512-0a7b8c8b` is current. The preceding
  `3e7b7771` loaded-idle rollout reconciled 57 deterministic and 40 shared-agent-runner labels with zero
  failures; target-only convergence to `59bd6cdd` has begun and running owners are skipped, not restarted.
- Idle rollout succeeded cumulatively for 96 label installs with zero reconcile failures. The latest
  convergence pass updated 11 deterministic and 12 shared-agent-runner labels; old-release running owners
  were skipped, not restarted, and continue draining naturally.
- Legacy root cause is proved: blocking waiters retained one process and ticket per wake; a waiter could hold
  the global control lock while an unbounded `/bin/ps ... lstart=` identity probe stalled every resource
  class. The new release bounds that probe to two seconds and fails conservatively as live.
- Read-only process sampling confirmed that the legacy drain, rather than the new release, caused the long
  wait: Paid PID `6856` and Apply PID `42143` spent every sampled stack in blocking `flock` on the shared
  `control.lock`. Paid then exited naturally, reconciled to `3e7b7771`, and its first natural new-release wake
  ended with bounded `host_admission_deferred`. Apply PID `42143` subsequently acquired the agent resource and
  now runs its real `application_direct.py --all-eligible` child; it is no longer blocked on `flock` but remains
  on old release `d74258a8` until that business run ends naturally.
- Coconala Reply and Paid are installed on current `d80e7359` and are executing natural wakes. Their previous
  wakes independently ended exit `75`,
  `host_admission_deferred`, loaded-idle, with no retained new-release ticket. Contention safety passes;
  later natural resume and official business readback remain open.
- Coconala Storefront is installed on current `59bd6cdd`. Its first natural current-release wake
  `18d526f7b56f7b80-33558` emitted started and bounded terminal `host_admission_deferred` receipts in 16.6
  seconds with no external effect. Target reconciliation applied exactly this idle label with zero failures;
  later natural resource acquisition, official listing readback and replay-zero remain open.
- The legacy queue is draining rather than growing: read-only polls measured `19`, `18`, `11`, then `10`
  retained tickets. Current memory admission itself passes at
  `free_percent=31` against `minimum_free_percent=15`; the remaining backlog is legacy process/ticket drain,
  not evidence of current physical-memory rejection. Coconala Storefront PID `60168` ended naturally and
  the lane is installed on `b8de9bf2`; two new-release wakes ended with bounded terminal deferral and retained
  no legacy ticket or owner. Paid is now reconciled; Apply PID `42143` remains live on an older release and
  must end naturally before target-only loaded-idle reconciliation.
- Disk availability recovered from `1.1 GiB` to `4.0 GiB`. Only clean, unused, regenerable external clones,
  main-contained temporary clones, three completed merged worktrees/branches/owned leases, and one missing-worktree
  registration were removed. Codex/cloud sessions, credentials, browser profiles, memory, state, ledgers,
  receipts, active evidence and other agents' worktrees were untouched. The retained legacy ticket count later
  fell to `7`; zero remains the completion gate.
- The dedicated `hf-gig-apply-evidence-gc` owner is installed on `d80e7359`, loaded-idle with exit `0` and a
  six-hour cadence. Apply PID `42143` remains on `d74258a8` and continues its pre-deployment business run; it
  is not interrupted. Storefront likewise remains running on `59bd6cdd` until its wake ends naturally.
- Target rollout of `0a7b8c8b` succeeded for Paid, Reply, Apply-evidence-GC and disk-cleanup without restarting
  a running owner. Paid then started from launchd without a kick and wrote a start receipt followed 16.3 seconds
  later by an effect-zero `host_admission_deferred` terminal receipt. It retained no admission ticket.
- A second shared startup bottleneck is now measured rather than inferred: Paid took about 149.7 seconds from
  launch to its start receipt while a one-second stack sample remained in Python import/compile. Immutable
  releases cannot write adjacent bytecode, so every wake recompiles shared runtime modules under host pressure.
  Disk-cleanup separately exited `78` before its start receipt because `process_start()` could not obtain the
  owner identity. These are the next shared-runtime cursor; neither is a Coconala-specific selector problem.
- PR `#5191` is merged at main `3a21ba280931757fbfd9adb4f3695ec36ab48b47` and release
  `20260914T220710-3a21ba28` is current. It builds checked-hash bytecode before sealing each immutable release,
  records and pins the exact runtime Python, verifies its cache tag during apply, obtains Darwin process-start
  identity through native `proc_pidinfo`, and removes fleet-wide `ps` enumeration from every admission wake.
  Fresh Astra review returned `ship`; the exact head passed 492 tests plus 470 subtests and every required CI
  check. Reply and disk-cleanup reconciled while idle; Apply, Paid and Storefront were observed running and were
  deliberately left on their installed releases to drain naturally.
- Reply's first observed natural wake on `3a21ba28` launched successfully but terminated at
  `2026-09-14T13:11:39.278302+00:00` with `host_admission_deferred`, exit `75`, and external effect zero.
  Therefore release startup identity/bytecode is shipped, but natural pressure recovery is not yet proved and
  the 15 nonterminal talkrooms have not advanced on this wake.

### Coconala

#### Current active-client inventory

This is the retained official-state candidate set, not a claim that every newest message has been handled.
The next admitted Paid/Reply observation must refresh each row from the official talkroom before any completion
claim. One buyer may own multiple independent contracts.

| Buyer | Talkroom | Retained official state | Current unresolved condition |
|---|---:|---|---|
| Ryu0820119 | `18211957` | `取引中` | A newer buyer message is reported after the historical confirmed seller effect. The current state is internally inconsistent: `next_action=await_buyer_feedback` while `buyer_feedback_pending_artifact=true`. Re-observe the newest message, perform the requested ordinary submission, then verify a later seller effect. Formal delivery stays off unless the buyer authorizes that state. |
| こころ支援 NPO法人まくとぅー | `18223833` | `取引中` | The retained ledger says the prior seller effect was confirmed and is awaiting buyer feedback. Refresh the official head and retained attachments; do not ask again for files already retained. |
| こころ支援 NPO法人まくとぅー | `18250352` | `取引中` | Separate active contract. The retained ledger says the prior effect was confirmed and awaits feedback; refresh independently and preserve this room's own context. |
| Chii【CK protect】 | `18180857` | `取引中` | Buyer feedback is pending while the lane says `await_buyer_feedback`. Establish the truthful completed/target DM count from official/account evidence, continue only permitted real sends, update the real result ledger, and reply from that evidence. |
| あつぎ | `18171850` | `取引中`, formal delivery confirmed | Buyer feedback is pending after delivery. Observe the newest feedback, revise/reply if requested, and verify the later seller effect; otherwise remain at buyer acceptance. |

`逃げ因子` talkroom `18211838` is excluded because retained official state is `取引完了`. Historical
projects with `unknown` state are not promoted into the active set; an authenticated orders observation must
do that.

- Apply one-off `single:new` and continuous `retainer:new` are implemented through the same lifecycle.
- Shared browser acquisition is already repaired by merged PR `#5175` (`833b55b6`) and PR `#5177`
  (`6a9f3aa4`): slow CDP I/O stays outside the ledger lock and unrelated owners acquire under distinct
  task locks. The current `b8de9bf2` release contains that exact main implementation. Latest read-only
  health is `/json/version` in `0.025s`, `/json/list` in `0.017s`, and one lease against capacity `16`.
- Latest discovery failed before observation at the shared CDP lease boundary; this is not proof of empty
  inventory, logout or selector failure. Its 160-second timeout occurred on release `6a9f3aa4`; current
  health does not prove recovery until a later natural Apply wake completes official readback.
- Exactly 54 application intents are `prepared_unconfirmed`. Frozen source result:
  `gig-apply-direct-1789367873154753000-28060`; sorted IDs `5207298` through `5267876`; newline-list SHA-256
  `cd0610bb8daaf78c11ffd143a4688fad30edeff34188725aaa6867d935b8b2e5`. Reconcile every member
  against the official applied state before retry. Retained official readbacks match zero of these 54 IDs,
  so none can be confirmed or safely retired without one fresh authenticated official-history scan.
- PR `#5183`, main SHA `d74258a8ce25a834e1fff31b7e3dc01ac0b816ba`, makes Paid fail closed as
  `buyer_attachment_recovery_pending` instead of asking a buyer to re-upload when official attachment
  references exist but verified bytes are missing. Kokoro resumes only after all 15 files are verified.
- Latest durable Reply snapshot observed 179 talkrooms: 164 have official replay-zero/closed/no-reply
  readback, while 15 remain nonterminal (`pending=5`, `failed=10`). The ten failures are predominantly
  historical CDP context-creation timeouts; a fresh admitted Reply wake must reconcile them independently.
  A historical Ryu seller effect exists, but a newer buyer event is reported and is not covered by a later
  officially verified seller effect. Reconcile the newest digest before deciding whether to send; never resend
  a confirmed effect and never suppress a genuinely newer request.
- Coconala is not revenue-complete until Apply, Reply, Paid, Storefront and payout attribution all have fresh
  official effect/readback and replay-zero receipts.

## Remaining execution order

Platform/client owners remain concurrent. This list selects the engineering cursor; it does not serialize
independent production effects.

### 1. Shared runtime production convergence and account 1 cutover — current cursor

- [x] Recover safe disk headroom and remove proved-obsolete artifacts.
- [x] Deploy nonblocking admission release to idle fleet.
- [x] Prove repeated safe contention deferral on Coconala Reply.
- [x] Merge and deploy PR `#5189`; prove one natural Paid wake reaches a bounded terminal receipt without
  pre-admission recursive cleanup.
- [x] Remove per-wake Python source recompilation from immutable releases with release-built checked-hash
  bytecode, a pinned interpreter and apply-time cache attestation (PR `#5191`).
- [x] Replace per-wake fleet process enumeration with native Darwin process-start identity while preserving the
  legacy `ps lstart` format and PID-reuse discrimination (PR `#5191`).
- [ ] Prove on natural production wakes that launch-to-start remains bounded under pressure and disk-cleanup no
  longer loses its recovery wake before the start receipt.
- [ ] Let the legacy global-lock queue drain naturally. Paid drained; Apply PID `42143` acquired the agent
  resource and is executing its business child. Storefront has a terminal receipt but its process is still
  finishing naturally.
- [ ] Reconcile each newly idle owner to current `3a21ba28` without restarting siblings. Reply and disk-cleanup
  are installed current. Apply remains on `d74258a8`; Paid on `0a7b8c8b`; Storefront on `59bd6cdd` until their
  observed running wakes finish. Target checks remain bounded and running owners are never interrupted.
- [ ] Prove each lane defers under contention without a retained ticket or external effect.
  Reply, Storefront and Paid pass; Apply remains.
- [ ] Prove pressure recovery: a later natural wake acquires, resumes durable progress and writes terminal
  business receipt plus official readback.
- [ ] Prove queue drains to zero, fleet-wide starvation does not recur, and no duplicate external effect occurs.
- [ ] Keep producing terminal receipts for at least 24 hours without human restart or babysitting.
- [x] Verify mixed-release compatibility and land the first durable reservation/dispatcher contract as pushed
  commits `479435f804`, `3181bbd03c`, and `9e275ed0a9` on the dedicated Phase 2 branch.
- [x] Finish the SQLite replacement, including retired/missing-owner cancellation, bounded 500-waiter evidence
  and 39 simultaneous durable enqueues.
- [x] Inspect the entire Phase 2 diff, run host/loop/registry and stdlib CI suites, obtain fresh read-only
  `ship` on exact commit `4ac009092f`, then commit and push without losing the original dirty work.
- [x] Merge PR `#5193`, build immutable main-derived release `20260915T025232-3fbe7554`, and reconcile only
  loaded-idle targets with failures 0; running siblings were skipped and not restarted.
- [ ] Prove with natural production wakes that a sleeping queue head does not idle capacity, a crashed
  dispatcher is reclaimed, retired/missing owners cannot block the queue, one resource class cannot starve
  another, and an uncertain external effect is never replayed.
- [ ] Switch only the intended Life Manager Codex provider routes from account 2 to account 1 after resolving
  their current owner and credential profile. Prove one bounded account 1 invocation and receipt before the
  targeted rollout; do not delete or overwrite either account's sessions.

### 2. Coconala vertical revenue proof

- [ ] Finish the currently running Paid wake and persist its terminal receipt; process start alone is not a
  client effect.
- [ ] Obtain one authenticated `orders-only` observation and replace the retained candidate set above with the
  exact official active-order set.
- [ ] For every active order, obtain a `selected-talkroom-only` head readback and store newest buyer-event and
  newest seller-effect digests independently.
- [ ] Fix the shared queue reducer so a newer unhandled buyer digest always overrides stale
  `await_buyer_feedback`; retain one regression fixture covering the Ryu-shaped contradiction.
- [ ] Route each active talkroom to an independent work item and effect fence; one blocked room must not block
  any sibling room.
- [ ] Ryu `18211957`: observe the newest buyer request, generate the requested ordinary submission from retained
  context/artifacts, send once, and prove a later seller effect in official readback. Do not toggle formal
  delivery without buyer authorization.
- [ ] Kokoro `18223833`: refresh the official head and all retained attachment references; recover missing bytes
  locally and continue without asking the buyer to resend known files.
- [ ] Kokoro `18250352`: refresh and process independently from `18223833`; prove its own terminal receipt and
  official effect.
- [ ] Chii `18180857`: read the truthful sent-count ledger, identify the remaining eligible real TikTok targets,
  execute only permitted real DMs at provider-safe cadence, persist each official result, and report the real
  total. Never fabricate work.
- [ ] Atsugi `18171850`: reconcile the newest post-delivery feedback, perform any required revision/reply once,
  and return to verified buyer-acceptance wait.
- [ ] Re-run all five active work items and prove newest-buyer-digest coverage, official readback and replay-zero
  independently for each.
- [ ] Reconcile all 54 uncertain application intents against official applied history.
- [ ] Restore authenticated discovery for both `single:new` and `retainer:new`.
- [ ] Submit every eligible high-fit one-off and continuous application; verify each officially; replay zero.
- [ ] Create Calendar events and five-minute Telegram reminders for every accepted meeting.
- [ ] Keep Reply processing every talkroom independently with cumulative context and attachment recovery.
- [ ] Recover and verify Kokoro's 15 retained files without another buyer request.
- [ ] Complete every funded Paid work item, deliver exactly once and verify official room state.
- [ ] Keep Storefront published where supported and measure official demand.
- [ ] Attribute accepted payout and bank receipt to its originating application and contract.

### 3. CrowdWorks vertical proof

- [ ] Close the three existing active contracts first through independent per-client workers.
- [ ] Prove exact delivery readback, payout attribution and replay-zero for each existing contract.
- [ ] Keep Apply and Reply healthy, finish Paid and payout, and mark Storefront `not_applicable` unless an
  official listing surface is observed.

### 4. Lancers vertical proof

- [x] Phone verification.
- [ ] Restore durable browser availability and persistent authentication.
- [ ] Prove Apply -> Reply -> contract -> Paid -> payout; Storefront only if officially supported.

### 5. Mercor vertical proof

- [ ] Stop repeated login by retaining and observing authenticated state.
- [ ] Prove Apply -> Reply -> interview handoff -> contract -> Paid -> payout.
- [ ] Storefront is `not_applicable`.

### 6. Freelancer.com and Upwork

- [ ] Recover official account/policy state and prove Apply -> Reply -> Paid -> payout on each.
- [ ] Implement Storefront only where an official provider surface supports it.

### 7. New-platform meta loop

- [ ] Search Web/X daily, qualify policy/automation/expected net value and select profitable platforms.
- [ ] Generate thin adapters against the shared conformance contract.
- [ ] Canary, verify official effect/readback/replay-zero and promote only passing adapters.
- [ ] Feed failures to self-heal and successful patterns to shared skills/evals.

### 8. Recursive self-healing and self-improvement

- [ ] Detect missed replies/deliveries, auth expiry, browser faults, resource starvation and revenue regressions
  from events, metrics and receipts.
- [ ] Reproduce the failure, patch in an isolated worktree, run regression/fault-injection evals, canary,
  promote or roll back, and preserve a terminal repair receipt without Dais or Codex babysitting.
- [ ] Rank improvements by verified revenue impact and safely improve existing loops as well as build new ones.

### 9. Phone-only hosted Life Manager

- [ ] Run the same kernel in tenant-isolated cloud browser/computer sessions.
- [ ] Use Telegram as the only required initial UI; local computers are unnecessary.
- [ ] Use managed agent sessions/sandboxes/handoffs where they reduce custom orchestration, while keeping
  identity, authorization, revocation and audit inside the service boundary.
- [ ] Start subscription billing and prove tenant isolation, reliability and unit economics.

### 10. Revenue and YC gate

- [ ] Count only attributable accepted contracts, payouts and bank receipts.
- [ ] Reach verified USD 10K MRR by cloning profitable end-to-end lifecycles and selling the hosted product.
- [ ] Publish accurate traction, retention, margin and automation metrics in README and the product site.
- [ ] Apply to YC Winter 2027 as a solo founder with measured evidence, not projections.

### 11. Documentation and obsolete-artifact convergence

- [ ] Derive the canonical program-spec name and location from current repository conventions and inbound
  references; migrate this SSOT once and replace every old live pointer with one reference to it.
- [ ] Delete only proved-obsolete duplicate specs, completed temporary artifacts, unused clean clones and
  regenerable caches after exact reference/owner checks. Preserve Codex/cloud sessions, credentials, browser
  profiles, durable memory/state/ledgers/receipts, active evidence, and other owners' worktrees.
- [ ] Prove the surviving tree has one execution SSOT, no broken references, a clean owning branch, and remote
  recovery evidence before removing any local handover path.

## Completion gate

This program is complete only when every applicable platform has a continuously operating profitable
lifecycle, unsupported lanes are explicitly proved `not_applicable`, the meta/self-heal/self-improve loops
operate without babysitting, the hosted phone-only product works, and attributable receipts prove USD 10K
MRR. Larger revenue ambitions remain direction, never a substitute for this measured gate.
