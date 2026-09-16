# Fair Always-Running Loop Recovery Implementation Plan

> Superseded for execution by [Foundation Local Integration Atomics](2026-09-16-foundation-local-integration-atomics.md). This earlier design proposed changes already present in the foundation candidate and treated queue-age targets as guarantees without proving host capacity. Do not execute its tasks independently.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore every registered money-making loop to continuous scheduled progress without unbounded parallel processes, `borrow` starvation, or launchd-only runtime failures.

**Architecture:** Keep the existing independent launchd owners and bounded host admission runtime. Use priority-aware durable queues per resource class: paid/contract fulfillment starts first, revenue acquisition and publication follow, and support work remains lower priority. Add aging so an older lower-priority job is promoted after a bounded wait; priority changes order, never permanent eligibility. When a finite run exits, it releases its claim and dispatches the highest effective-priority compatible waiter. There is no external business deadline: correctness is measured by cadence continuity, bounded queue age, terminal receipts, and provider readback.

**Tech Stack:** Python 3.14, SQLite, launchd, Node.js, shell entrypoints, immutable Life Manager releases.

**Spec:** `skills/earn/gig/TODO.md` section `Fundamental scalability repair`; this plan retains paid-work priority while replacing permanent `borrow` eligibility with priority plus bounded aging.

## Global Constraints

- Every registered earning loop remains enabled. Capacity pressure delays work but never drops a scheduled occurrence.
- “24/7” means every owner repeatedly performs bounded durable transitions; it does not mean keeping every heavy process alive simultaneously.
- There is no business deadline field. Use registry cadence plus observed `queued_at`, `started_at`, and terminal timestamps.
- Paid and accepted-contract work has the highest base priority. No class may jump an older waiter indefinitely.
- Initial operational wait bounds are 5 minutes for paid/contract work, 30 minutes for acquisition/publication (including Connector and Mobile), and 2 hours for support/metrics. These are starvation safety bounds, not external business deadlines.
- A completed, failed, or timed-out run releases its exact claim before the next waiter is dispatched.
- Keep memory, browser, agent, and disk limits. Do not restore unbounded fan-out.
- Serialize only the same exact provider/browser/effect resource; unrelated owners remain parallel.
- Credentials remain only in private state. Tests and receipts expose key presence, never values.
- Production changes come only from pushed `main` via an immutable release and target-only `lm-loop apply`.

## Existing TODO Alignment

The existing TODO is aligned on independent owners, bounded runs, durable state, immutable releases, provider readback, and paid-work priority. It is not aligned where `borrow` can mean indefinite non-admission:

```text
maintenance may borrow unused capacity only
```

Replace them with:

```text
Every finite owner remains durably eligible in its declared resource class.
Paid and accepted-contract fulfillment has the highest base priority; acquisition
and publication is next; support and metrics is last. Waiting jobs age toward the
front, so base priority can reorder work but can never starve Connector, Mobile,
metrics, or maintenance indefinitely. Light deterministic work uses a separate
measured capacity and does not consume a browser/model slot. When a claim is
released, the highest effective-priority compatible waiter is reserved and
dispatched immediately. Continuous success requires bounded queue age for every
registered earning loop.
```

Do not treat `1–30 minute cadence` as a universal business deadline. Each registry cadence remains the desired recurrence. Runtime evidence records how late each occurrence actually starts; sustained lateness is a capacity defect to repair, not a reason to discard the occurrence.

---

### Task 1: Freeze the exact earning-loop inventory and baseline

**Files:**
- Modify: `skills/earn/gig/TODO.md`
- Read: `config/loop-registry.json`
- Read: `~/.local/state/life-manager/events.jsonl`

**Interfaces:**
- Consumes: registry loop rows and current runtime events.
- Produces: an authoritative table containing `loop_id`, cadence, resource class, loaded release SHA, last terminal result, last verified provider effect, and current queue age.

- [ ] **Step 1: Enumerate the exact scope from the registry**

Run:

```bash
jq -r '.loops | to_entries[] | [.key, (.value.cadence|tojson), (.value.resource_class // "default"), .value.effect_class] | @tsv' config/loop-registry.json
```

Record all Mobile App publication owners, Connector, Instagram metrics, and TikTok metrics. Do not stop at a remembered count of fourteen; the registry is authoritative.

- [ ] **Step 2: Capture the live baseline**

For each scoped loop, record the latest start and terminal events, loaded `ProgramArguments`, release SHA, and official provider receipt. Label missing evidence explicitly.

- [ ] **Step 3: Update the TODO contract**

Insert the replacement fairness text from `Existing TODO Alignment` and the baseline table. Preserve paid-work priority; remove only the assertion that lower-priority work may remain indefinitely ineligible.

- [ ] **Step 4: Commit the documentation contract**

```bash
git add skills/earn/gig/TODO.md docs/superpowers/plans/2026-09-16-fair-always-running-loop-recovery.md
git commit -m "docs(runtime): require fair continuous loop progress"
```

### Task 2: Reproduce starvation before changing admission

**Files:**
- Modify: `runtime/host/tests/test_resource_admission.py`
- Modify: `runtime/loop/tests/test_lm_loop_run_bounds.py`

**Interfaces:**
- Consumes: current durable admission SQLite schema.
- Produces: regression tests proving paid work starts first, older lower-priority work is promoted within its wait bound, and released capacity dispatches the next waiter.

- [ ] **Step 1: Write the continuous-arrival regression**

Create a test that enqueues Mobile, Connector, and paid marketplace owners, continuously adds newer paid work, then repeatedly claims and releases one slot. Assert the first paid item claims first, while Mobile and Connector claim after aging despite continuous paid arrivals.

```python
assert claimed_owner_ids[0] == "paid-a"
assert claimed_owner_ids.index("mobile-a") < claimed_owner_ids.index("paid-newest")
assert claimed_owner_ids.index("connector") < claimed_owner_ids.index("paid-newest")
assert set(claimed_owner_ids) == set(enqueued_owner_ids)
```

- [ ] **Step 2: Write the release-to-next-dispatch regression**

Create a live claim, release it, and assert the oldest compatible waiter receives one reservation without waiting for a new launchd cadence.

- [ ] **Step 3: Write crash recovery coverage**

Expire a claimed owner identity and assert the waiter returns to the durable queue exactly once. Assert no scheduled row disappears.

- [ ] **Step 4: Run RED tests**

```bash
python3 -m unittest runtime.host.tests.test_resource_admission runtime.loop.tests.test_lm_loop_run_bounds
```

Expected: the class-priority starvation fixture fails before implementation.

### Task 3: Replace permanent borrow eligibility with priority plus aging

**Files:**
- Modify: `runtime/host/resource_admission.py`
- Modify: `runtime/host/tests/test_resource_admission.py`

**Interfaces:**
- Consumes: `queue(sequence, owner_id, resource_class)` and live owner identity.
- Produces: `enqueue_durable`, `claim_durable`, `release_and_reserve`, and `reserve_available` with paid-first, starvation-free semantics.

- [ ] **Step 1: Store base priority and queue age inputs**

Use three explicit base priorities:

```text
0 critical_paid   paid delivery, accepted-contract fulfillment, urgent buyer reply
1 revenue         application, Connector, Mobile publication
2 support         metrics, reports, maintenance
```

Store `queued_at` durably. Derive effective priority at claim time; never rewrite queue history.

- [ ] **Step 2: Add bounded aging**

Promote a waiter to effective priority `0` when its operational wait bound is reached:

```text
critical_paid: 5 minutes
revenue:       30 minutes
support:        2 hours
```

Within the same effective priority, select the lowest sequence. Delete `_revenue_floor` and permanent `borrow` exclusion; retain bounded total and resource-class capacity.

- [ ] **Step 3: Preserve schema compatibility during rollout**

Continue reading legacy `priorities` rows while mixed releases exist. Map legacy `revenue` rows to the correct explicit priority and legacy `borrow` rows to `revenue` or `support` from the registry. Do not delete the table until every loaded finite owner runs the compatible release and queued/reserved rows are drained.

- [ ] **Step 4: Dispatch immediately on release**

Ensure `release_and_reserve` selects the highest effective-priority compatible waiter and returns one dispatch target after the releasing owner has durably relinquished its claim.

- [ ] **Step 5: Run GREEN tests**

```bash
python3 -m unittest runtime.host.tests.test_resource_admission runtime.loop.tests.test_lm_loop_run_bounds
```

Expected: paid-first, aging, starvation, handoff, crash-recovery, and capacity tests pass.

### Task 4: Measure and raise capacity by resource class

**Files:**
- Modify: `config/loop-registry.json`
- Modify: `runtime/host/resource_admission.py`
- Modify: `runtime/loop/tests/test_macos_loop_registry.py`

**Interfaces:**
- Consumes: registry `resource_class`.
- Produces: separate bounded capacity for `agent`, `browser`, and `deterministic` work, allowing the total to exceed five when measured headroom supports it.

- [ ] **Step 1: Add only missing resource classifications**

Classify Mobile publication and Connector browser/model work by what they physically consume. Metrics and ledger-only work must not consume a browser/model slot.

- [ ] **Step 2: Reject unknown resource classes**

Extend registry validation with the exact accepted set and a failing fixture for an unknown class.

- [ ] **Step 3: Prove cross-class progress**

Add a test where all browser slots are occupied while a deterministic metrics job still claims its own slot.

- [ ] **Step 4: Roll capacity upward from evidence**

Start from the proven-safe current limit, then canary higher total capacity in steps (`5 -> 7 -> 10`). Advance only when peak RSS, memory-free percentage, swap growth, browser health, terminal latency, and stale-owner count remain within the existing host safety thresholds. A total of ten is acceptable if the measured mix is safe; ten simultaneous heavy Chromium/Codex jobs is not assumed safe.

- [ ] **Step 5: Run focused tests**

```bash
python3 -m unittest runtime.host.tests.test_resource_admission runtime.loop.tests.test_macos_loop_registry
```

### Task 5: Pin Mobile and metrics runtimes in generated launchd plists

**Files:**
- Modify: `runtime/loop/lm_loop_apply.py`
- Modify: `runtime/loop/tests/test_lm_loop_apply.py`

**Interfaces:**
- Consumes: host-resolved executable paths during apply.
- Produces: plist environment keys `LIFE_MANAGER_NODE`, `NODE_BIN`, `LIFE_MANAGER_PYTHON`, and `PYTHON_BIN`.

- [ ] **Step 1: Write the failing minimal-PATH plist test**

Assert all Mobile entrypoints and both metrics entrypoints receive absolute executable paths when launchd provides no Homebrew PATH.

- [ ] **Step 2: Resolve executables at apply time**

Use `shutil.which` during plan generation, require absolute executable files, and fail apply before mutation if either runtime is unavailable.

- [ ] **Step 3: Import/version smoke the generated command**

Execute bounded `node --version` and `python3 -c 'import sys'` checks before installing the plist.

- [ ] **Step 4: Run focused tests**

```bash
python3 -m unittest runtime.loop.tests.test_lm_loop_apply
```

### Task 6: Give all Postiz consumers one explicit private env contract

**Files:**
- Modify: `runtime/loop/lm_loop_apply.py`
- Modify: `apps/life-manager/scripts/mobile-app`
- Modify: `apps/life-manager/scripts/instagram-metrics-production-boot.sh`
- Modify: `apps/life-manager/scripts/tiktok-metrics-production-boot.sh`
- Modify: `apps/life-manager/scripts/load-env-file.test.js`

**Interfaces:**
- Consumes: `LIFE_MANAGER_MARKETING_ENV_FILE`.
- Produces: Mobile and metrics processes with the same mode-600 private env source.

- [ ] **Step 1: Write the failing env-parity test**

Assert all three launchers load `LIFE_MANAGER_MARKETING_ENV_FILE`, defaulting to `~/.local/state/life-manager/private/marketing.env`, and never print credential values.

- [ ] **Step 2: Unify the launchers**

Load the same env file before runtime preparation in Mobile, Instagram metrics, and TikTok metrics.

- [ ] **Step 3: Add secret-free preflight**

Require presence of `LM_POSTIZ_API_KEY` and `LM_DATA_DIR`; report only missing key names.

- [ ] **Step 4: Run Node tests**

```bash
node --test apps/life-manager/scripts/load-env-file.test.js apps/life-manager/scripts/portable-runtime.test.js
```

### Task 7: Verify slot demand fits the host

**Files:**
- Modify: `skills/earn/gig/TODO.md`
- Read: runtime events and host-admission SQLite state.

**Interfaces:**
- Consumes: available recent production start/terminal timestamps and bounded load-test traces; no fresh 24-hour wait.
- Produces: observed arrivals, average runtime, p95 runtime, slot-hours/day, maximum queue age, and orphan-owner count by resource class.

- [ ] **Step 1: Calculate actual demand**

For each resource class calculate:

```text
slot_hours_per_day = sum(run_duration_seconds) / 3600
utilization = slot_hours_per_day / (capacity * 24)
```

- [ ] **Step 2: Remove duplicate/no-op demand before raising capacity**

If utilization exceeds capacity, first coalesce duplicate scheduled occurrences for the same loop, make no-op checks exit immediately, and confirm every terminated child releases its owner claim.

- [ ] **Step 3: Increase a capacity only from measured headroom**

Change a class limit only when memory, swap, browser count, and disk headroom show the additional worker is safe.

### Task 8: Merge, release, and target-apply without sibling restart

**Files:**
- Verify: all modified source and tests.

**Interfaces:**
- Consumes: reviewed main commit.
- Produces: one immutable release loaded by the scoped labels.

- [ ] **Step 1: Run required verification**

```bash
python3 -m unittest runtime.host.tests.test_resource_admission
python3 -m unittest discover -s runtime/loop/tests -p 'test_*.py'
node --test apps/life-manager/scripts/load-env-file.test.js apps/life-manager/scripts/portable-runtime.test.js
git diff --check
~/loops/current/bin/lm-loop doctor
```

- [ ] **Step 2: Commit, push, review, and merge once**

Fetch current `origin/main`, preserve concurrent commits, push the focused branch, obtain a fresh read-only review, and merge only after required checks pass.

- [ ] **Step 3: Cut an immutable main-derived release**

```bash
bin/cut-loop-release.sh origin/main
```

- [ ] **Step 4: Apply only scoped idle labels**

Use `lm-loop apply <loop-id>` one label at a time. Never restart a running sibling or broad-apply the fleet.

### Task 9: Prove continuous natural operation

**Files:**
- Modify: `skills/earn/gig/TODO.md`
- Read: provider receipts, runtime events, loaded plists, and queue state.

**Interfaces:**
- Consumes: natural scheduled wakes from the installed SHA.
- Produces: acceptance evidence for every scoped loop.

- [ ] **Step 1: Verify lifecycle evidence**

For every scoped loop require `queued -> claimed -> running -> terminal -> released`, followed by dispatch of the next compatible waiter.

- [ ] **Step 2: Verify external effects separately**

For Mobile require Postiz receipt and intended account/content provider readback. For Connector require provider registration/readback or a truthful no-candidate terminal receipt. For replay, require zero duplicate effects.

- [ ] **Step 3: Run the observation window**

Observe a targeted natural wake for every changed owner/adapter, while other owners are evaluated in parallel. Run bounded saturation, crash, restart and uncertain-effect regressions against the shared lifecycle; record maximum queue age and assert every business item either completes or remains durably discoverable. Existing multi-day telemetry informs capacity but is not an elapsed-time acceptance gate. Require official provider readback for attempted effects; a no-work wake proves lifecycle readiness only. Keep automatic cadence/receipt monitoring active after promotion.

- [ ] **Step 4: Close the TODO only from receipts**

Loaded status, PID, exit zero, or historical posts are insufficient. Close only after current-SHA natural wakes, provider evidence, claim release, next-waiter dispatch, and replay-zero are all observed.

## Completion Conditions

- Paid and accepted-contract work claims before newer lower-priority work.
- No final runtime decision uses `borrow` as permanent non-eligibility.
- Every compatible waiter claims before its operational maximum queue age.
- A released slot immediately advances the highest effective-priority compatible waiter.
- Mobile and metrics run under launchd with absolute Node/Python paths and the private marketing env.
- Every scoped loop produces current-release natural terminal evidence within its observed cadence cycle.
- Mobile and Connector external effects have official readback and replay-zero.
- Twenty-four hours show zero vanished occurrences, zero starvation, zero stale owners, and bounded queue age for every resource class.
