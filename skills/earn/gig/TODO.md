# Gig revenue program — current execution SSOT

This file contains only current truth and remaining work. Completed incident detail is preserved in Git
history through commit `e2b30b8e10`; it must not be copied back into the active TODO. Evidence lives in
durable runtime ledgers and receipts, not in duplicated historical checklists.

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
- Ryu `18211957` already has the requested ordinary reply and attachment in official readback. Do not resend;
  wait for a genuinely new buyer event. Formal delivery remains off without the required buyer state.
- Chii is outside this program cursor. Completed excluded work must not be reopened.

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

- PR `#5184`, main SHA `b8de9bf2d230514587bb455f59a3e866ec27f658`, fixes scheduled resource
  admission. Busy wakes attempt once, retain no ticket, write effect-zero deferred state and exit `75`.
- Idle rollout succeeded cumulatively for 96 label installs with zero reconcile failures. The latest
  convergence pass updated 11 deterministic and 12 shared-agent-runner labels; old-release running owners
  were skipped, not restarted, and continue draining naturally.
- Legacy root cause is proved: blocking waiters retained one process and ticket per wake; a waiter could hold
  the global control lock while an unbounded `/bin/ps ... lstart=` identity probe stalled every resource
  class. The new release bounds that probe to two seconds and fails conservatively as live.
- Coconala Reply is installed on `b8de9bf2`. Two natural wakes independently ended exit `75`,
  `host_admission_deferred`, loaded-idle, with no retained new-release ticket. Contention safety passes;
  later natural resume and official business readback remain open.
- Latest legacy queue count is `20`, with one live owner immediately after the latest idle convergence pass.
  Current memory admission itself passes at
  `free_percent=31` against `minimum_free_percent=15`; the remaining backlog is legacy process/ticket drain,
  not evidence of current physical-memory rejection. Coconala Paid PID `6856`, Apply PID `42143` and
  Storefront PID `60168` remain on older releases and must end naturally before target-only loaded-idle
  reconciliation.
- Disk availability recovered from `1.1 GiB` to `4.0 GiB`. Only clean, unused, regenerable external clones,
  main-contained temporary clones, three completed merged worktrees/branches/owned leases, and one missing-worktree
  registration were removed. Codex/cloud sessions, credentials, browser profiles, memory, state, ledgers,
  receipts, active evidence and other agents' worktrees were untouched.

### Coconala

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
- Coconala is not revenue-complete until Apply, Reply, Paid, Storefront and payout attribution all have fresh
  official effect/readback and replay-zero receipts.

## Remaining execution order

Platform/client owners remain concurrent. This list selects the engineering cursor; it does not serialize
independent production effects.

### 1. Shared runtime production convergence — current cursor

- [x] Recover safe disk headroom and remove proved-obsolete artifacts.
- [x] Deploy nonblocking admission release to idle fleet.
- [x] Prove repeated safe contention deferral on Coconala Reply.
- [ ] Let legacy Paid, Apply and Storefront owners finish naturally.
- [ ] Reconcile each newly idle owner to `b8de9bf2` without restarting siblings.
- [ ] Prove each lane defers under contention without a retained ticket or external effect.
- [ ] Prove pressure recovery: a later natural wake acquires, resumes durable progress and writes terminal
  business receipt plus official readback.
- [ ] Prove queue drains to zero, fleet-wide starvation does not recur, and no duplicate external effect occurs.
- [ ] Keep producing terminal receipts for at least 24 hours without human restart or babysitting.

### 2. Coconala vertical revenue proof

- [ ] Reconcile all 54 uncertain application intents against official applied history.
- [ ] Restore authenticated discovery for both `single:new` and `retainer:new`.
- [ ] Submit every eligible high-fit one-off and continuous application; verify each officially; replay zero.
- [ ] Create Calendar events and five-minute Telegram reminders for every accepted meeting.
- [ ] Keep Reply processing every talkroom independently with cumulative context and attachment recovery.
- [ ] Recover and verify Kokoro's 15 retained files without another buyer request.
- [ ] Complete every funded Paid work item, deliver exactly once and verify official room state.
- [ ] Keep Storefront published where supported and measure official demand.
- [ ] Attribute accepted payout and bank receipt to its originating application and contract.

### 3. Existing CrowdWorks funded liabilities

- [ ] Close the three active contracts through independent per-client workers.
- [ ] Prove exact delivery readback, payout attribution and replay-zero for each.

### 4. Lancers vertical proof

- [x] Phone verification.
- [ ] Restore durable browser availability and persistent authentication.
- [ ] Prove Apply -> Reply -> contract -> Paid -> payout; Storefront only if officially supported.

### 5. CrowdWorks platform proof

- [ ] Keep Apply and Reply healthy, finish Paid and payout, and mark Storefront `not_applicable` unless an
  official listing surface is observed.

### 6. Mercor vertical proof

- [ ] Stop repeated login by retaining and observing authenticated state.
- [ ] Prove Apply -> Reply -> interview handoff -> contract -> Paid -> payout.
- [ ] Storefront is `not_applicable`.

### 7. Freelancer.com and Upwork

- [ ] Recover official account/policy state and prove Apply -> Reply -> Paid -> payout on each.
- [ ] Implement Storefront only where an official provider surface supports it.

### 8. New-platform meta loop

- [ ] Search Web/X daily, qualify policy/automation/expected net value and select profitable platforms.
- [ ] Generate thin adapters against the shared conformance contract.
- [ ] Canary, verify official effect/readback/replay-zero and promote only passing adapters.
- [ ] Feed failures to self-heal and successful patterns to shared skills/evals.

### 9. Recursive self-healing and self-improvement

- [ ] Detect missed replies/deliveries, auth expiry, browser faults, resource starvation and revenue regressions
  from events, metrics and receipts.
- [ ] Reproduce the failure, patch in an isolated worktree, run regression/fault-injection evals, canary,
  promote or roll back, and preserve a terminal repair receipt without Dais or Codex babysitting.
- [ ] Rank improvements by verified revenue impact and safely improve existing loops as well as build new ones.

### 10. Phone-only hosted Life Manager

- [ ] Run the same kernel in tenant-isolated cloud browser/computer sessions.
- [ ] Use Telegram as the only required initial UI; local computers are unnecessary.
- [ ] Use managed agent sessions/sandboxes/handoffs where they reduce custom orchestration, while keeping
  identity, authorization, revocation and audit inside the service boundary.
- [ ] Start subscription billing and prove tenant isolation, reliability and unit economics.

### 11. Revenue and YC gate

- [ ] Count only attributable accepted contracts, payouts and bank receipts.
- [ ] Reach verified USD 10K MRR by cloning profitable end-to-end lifecycles and selling the hosted product.
- [ ] Publish accurate traction, retention, margin and automation metrics in README and the product site.
- [ ] Apply to YC Winter 2027 as a solo founder with measured evidence, not projections.

## Completion gate

This program is complete only when every applicable platform has a continuously operating profitable
lifecycle, unsupported lanes are explicitly proved `not_applicable`, the meta/self-heal/self-improve loops
operate without babysitting, the hosted phone-only product works, and attributable receipts prove USD 10K
MRR. Larger revenue ambitions remain direction, never a substitute for this measured gate.
