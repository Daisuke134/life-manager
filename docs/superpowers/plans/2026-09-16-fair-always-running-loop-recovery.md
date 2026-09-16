# Fair Always-Running Loop Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore every registered money-making loop to continuous scheduled progress without unbounded parallel processes, `borrow` starvation, or launchd-only runtime failures.

**Architecture:** Keep the existing independent launchd owners and the existing bounded host admission runtime. Replace class-based `borrow`/`revenue` selection with one durable, starvation-free FIFO queue per resource class; when a finite run exits, it releases its claim and dispatches the oldest compatible waiter. There is no external business deadline: correctness is measured by cadence continuity, bounded queue age, terminal receipts, and provider readback.

**Tech Stack:** Python 3.14, SQLite, launchd, Node.js, shell entrypoints, immutable Life Manager releases.

**Spec:** `skills/earn/gig/TODO.md` section `Fundamental scalability repair`; this plan intentionally replaces its remaining `maintenance may borrow` and `revenue-priority` language with the uniform fairness contract below.

## Global Constraints

- Every registered earning loop remains enabled. Capacity pressure delays work but never drops a scheduled occurrence.
- “24/7” means every owner repeatedly performs bounded durable transitions; it does not mean keeping every heavy process alive simultaneously.
- There is no business deadline field. Use registry cadence plus observed `queued_at`, `started_at`, and terminal timestamps.
- All compatible waiters use insertion order. No class may jump the queue indefinitely.
- A completed, failed, or timed-out run releases its exact claim before the next waiter is dispatched.
- Keep memory, browser, agent, and disk limits. Do not restore unbounded fan-out.
- Serialize only the same exact provider/browser/effect resource; unrelated owners remain parallel.
- Credentials remain only in private state. Tests and receipts expose key presence, never values.
- Production changes come only from pushed `main` via an immutable release and target-only `lm-loop apply`.

## Existing TODO Alignment

The existing TODO is directionally aligned on independent owners, bounded runs, durable state, immutable releases, and provider readback. It is not aligned on these two statements:

```text
maintenance may borrow unused capacity only
Apply, Reply, Paid and Storefront must all be revenue-priority owners
```

Replace them with:

```text
Every finite owner joins the same durable FIFO for its declared resource class.
No admission class may bypass an older compatible waiter. Light deterministic
work uses its own measured resource class and therefore does not consume a
browser/model slot. When a claim is released, the oldest compatible waiter is
reserved and dispatched immediately. Continuous success is proved by bounded
queue age across every registered earning loop, not by a priority label.
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

Insert the replacement fairness text from `Existing TODO Alignment` and the baseline table. Remove assertions that `borrow` or `revenue-priority` is the desired final architecture.

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
- Produces: regression tests proving all compatible waiters advance in insertion order and released capacity dispatches the next waiter.

- [ ] **Step 1: Write the continuous-arrival regression**

Create a test that enqueues Mobile, Connector, and marketplace owners, continuously adds newer marketplace work, then repeatedly claims and releases one slot. Assert that the original Mobile and Connector sequence numbers are claimed before later arrivals.

```python
assert claimed_owner_ids[:3] == ["mobile-a", "connector", "marketplace-a"]
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

### Task 3: Replace class priority with simple compatible FIFO

**Files:**
- Modify: `runtime/host/resource_admission.py`
- Modify: `runtime/host/tests/test_resource_admission.py`

**Interfaces:**
- Consumes: `queue(sequence, owner_id, resource_class)` and live owner identity.
- Produces: `enqueue_durable`, `claim_durable`, `release_and_reserve`, and `reserve_available` with uniform FIFO semantics.

- [ ] **Step 1: Remove priority from queue ordering**

Change head selection to:

```sql
SELECT owner_id
FROM queue
WHERE resource_class = ?
ORDER BY sequence
LIMIT 1
```

Do not order by `admission_class`.

- [ ] **Step 2: Remove the borrow/revenue capacity floor**

Delete `_revenue_floor`, `_legacy_owner_present`, and admission-class-specific bypasses. Capacity remains bounded by total and resource-class limits.

- [ ] **Step 3: Preserve schema compatibility during rollout**

Continue reading legacy `priorities` rows while mixed releases exist, but ignore them for ordering. Do not delete the table until every loaded finite owner runs the compatible release and queued/reserved rows are drained.

- [ ] **Step 4: Dispatch immediately on release**

Ensure `release_and_reserve` selects the oldest compatible waiter and returns one dispatch target after the releasing owner has durably relinquished its claim.

- [ ] **Step 5: Run GREEN tests**

```bash
python3 -m unittest runtime.host.tests.test_resource_admission runtime.loop.tests.test_lm_loop_run_bounds
```

Expected: all starvation, handoff, crash-recovery, and capacity tests pass.

### Task 4: Measure capacity by resource class without adding priorities

**Files:**
- Modify: `config/loop-registry.json`
- Modify: `runtime/host/resource_admission.py`
- Modify: `runtime/loop/tests/test_macos_loop_registry.py`

**Interfaces:**
- Consumes: registry `resource_class`.
- Produces: separate bounded capacity for `agent`, `browser`, and `deterministic` work.

- [ ] **Step 1: Add only missing resource classifications**

Classify Mobile publication and Connector browser/model work by what they physically consume. Metrics and ledger-only work must not consume a browser/model slot.

- [ ] **Step 2: Reject unknown resource classes**

Extend registry validation with the exact accepted set and a failing fixture for an unknown class.

- [ ] **Step 3: Prove cross-class progress**

Add a test where all browser slots are occupied while a deterministic metrics job still claims its own slot.

- [ ] **Step 4: Run focused tests**

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
- Consumes: per-run start/terminal timestamps over 24 hours.
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

Observe at least one full cadence for every scoped loop and a 24-hour fleet window. Record maximum queue age and assert every scheduled occurrence either completes or remains durably queued; none disappear.

- [ ] **Step 4: Close the TODO only from receipts**

Loaded status, PID, exit zero, or historical posts are insufficient. Close only after current-SHA natural wakes, provider evidence, claim release, next-waiter dispatch, and replay-zero are all observed.

## Completion Conditions

- No final runtime decision depends on `borrow`, `revenue`, or a revenue floor.
- Every compatible waiter eventually claims in durable insertion order.
- A released slot immediately advances the next compatible waiter.
- Mobile and metrics run under launchd with absolute Node/Python paths and the private marketing env.
- Every scoped loop produces current-release natural terminal evidence within its observed cadence cycle.
- Mobile and Connector external effects have official readback and replay-zero.
- Twenty-four hours show zero vanished occurrences, zero starvation, zero stale owners, and bounded queue age for every resource class.
