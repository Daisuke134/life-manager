# Cloud Edition CL01-CL05 Implementation Plan

> **Superseded for remaining work:** Task 1 produced useful provider-neutral parity groundwork in `a78ab3d306`, but this plan's local in-memory “Cloud” simulation and Steel-first runtime cannot prove a sellable Cloud product. Do not continue Tasks 2-3 as the T11 production path. The selected architecture and executable TODO are now `docs/superpowers/specs/2026-09-28-life-manager-agentcore-cloud-design.md` and `docs/superpowers/plans/2026-09-28-life-manager-agentcore-cloud.md`. Existing uncommitted browser/Steel work must be preserved and classified as provider-neutral lease code or conditional fallback; it is not CL03 evidence.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove one repository-owned business kernel runs through local and tenant-isolated Cloud host adapters with identical receipts and evidence, strict tenant boundaries, bounded Steel leases, phone-only handoff, and replay-zero.

**Architecture:** A pure deterministic kernel owns task semantics and receipt hashing; host adapters own storage, secrets, browser-session references, and readback. The Cloud adapter is bound to one authenticated tenant at construction and receives durable stores through narrow interfaces, allowing the acceptance suite to use a local in-memory simulation without creating a paid cloud account. Steel session ownership is a separate lease coordinator injected into the existing driver, so browser lifecycle changes do not fork the business kernel.

**Tech Stack:** Node.js CommonJS, `node:test`, `node:crypto`, existing Steel/Stagehand browser runtime.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` T11 and `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md` J/J1 plus CL01-CL05.

## Global Constraints

- Local and Cloud use one business implementation; only supervisor, durable storage, secret store, and browser transport vary.
- Cloud state, credential references, browser sessions, and receipts are tenant scoped; local credentials or mutable logs are never copied.
- The same approved business-kernel SHA must produce the same capsule hash, receipt, and evidence hash for the same task.
- An uncertain browser effect is never retried; lease cleanup releases only the exact expired or completed Steel session.
- No production `~/loops`, launchd, browser profile, credential value, provider effect, paid cloud service, or billing path is touched.

## Review Focus

- A forged cross-tenant reference must fail before the backing store is called.
- A task whose approved kernel SHA differs from the loaded artifact must fail closed.
- Concurrent Steel owners must create at most one session; an expired lease must release its exact session before takeover.
- A release failure must retain the lease for bounded stale cleanup instead of advertising a free slot.
- Telegram handoff must retain the session until an explicit resume, then read back and release exactly once.

---

### Task 1: Shared Business Kernel and Tenant-Bound Host Adapters

**Files:**
- Create: `apps/life-manager/lib/cloud-edition-kernel.js`
- Create: `apps/life-manager/lib/cloud-edition-host-adapter.js`
- Test: `apps/life-manager/lib/cloud-edition-host-adapter.test.js`

**Interfaces:**
- Produces: `readBusinessKernelArtifact()`, `executeBusinessTask(task, approvedSha)`, `createLocalHostAdapter(options)`, and `createCloudHostAdapter(options)`.
- Store contract: `read(tenantId, key)`, `put(tenantId, key, value)`, and receipt `putIfAbsent(tenantId, key, value)`.

- [ ] **Step 1: Write the CL02 failing tests**

  Add tests proving tenant A cannot read tenant B credential, browser session, state, or receipt references, and that rejected reads make zero backing-store calls.

- [ ] **Step 2: Run the CL02 test and verify RED**

  Run: `node --test lib/cloud-edition-host-adapter.test.js --test-name-pattern='tenant A'`

  Expected: FAIL because the adapter module is absent.

- [ ] **Step 3: Implement tenant-bound resource reads**

  Reference syntax is `lm-resource://<kind>/<tenant>/<key>`. Bind `tenantId` when constructing an adapter; validate kind and tenant before calling the matching store.

- [ ] **Step 4: Run the CL02 test and verify GREEN**

  Run the command from Step 2; expected PASS.

- [ ] **Step 5: Write the CL01/CL05 failing parity tests**

  Assert local and Cloud execute the same literal task with the same approved SHA and yield deeply equal receipts, capsule hashes, and evidence hashes. Assert a second Cloud execution creates no second receipt and reads back the original exact receipt. Assert a mismatched approved SHA fails before persistence.

- [ ] **Step 6: Run the parity tests and verify RED**

  Run: `node --test lib/cloud-edition-host-adapter.test.js`

  Expected: FAIL because the kernel/parity execution is not implemented.

- [ ] **Step 7: Implement the deterministic kernel and host execution boundary**

  Hash canonical JSON with SHA-256. Keep deployment mode outside the canonical receipt. Persist with `putIfAbsent`, read back by exact tenant/task receipt key, and compare the full receipt before reporting verified/replay-zero.

- [ ] **Step 8: Run the focused tests and verify GREEN**

  Run the command from Step 6; expected all PASS.

- [ ] **Step 9: Commit and push**

  Commit only Task 1 files plus this plan.

### Task 2: Shared Steel Session Lease and Phone-Only Handoff

**Files:**
- Create: `apps/life-manager/lib/steel-session-lease.js`
- Test: `apps/life-manager/lib/steel-session-lease.test.js`
- Modify: `apps/life-manager/lib/stagehand-steel-driver.js`
- Modify: `apps/life-manager/lib/stagehand-steel-driver.test.js`
- Modify: `apps/life-manager/lib/generic-browser-task.js`
- Modify: `apps/life-manager/lib/generic-browser-task.test.js`
- Modify: `apps/life-manager/lib/browser-job-runtime.test.js`

**Interfaces:**
- Consumes: existing `openSession`, `releaseSession`, `readHeldReceipt`, and `completeBrowserHandoff` boundaries.
- Produces: `createSteelSessionLeaseCoordinator(store, options)` with `acquire`, `attach`, `release`, and `reapExpired`; the driver receives it as `sessionLease`.

- [ ] **Step 1: Write the CL03 failing tests**

  Prove two driver owners sharing one lease store cannot create a second Steel session, and an expired lease releases the exact stale session once before the next owner acquires it.

- [ ] **Step 2: Run the CL03 tests and verify RED**

  Run: `node --test lib/steel-session-lease.test.js lib/stagehand-steel-driver.test.js --test-name-pattern='shared lease|stale lease'`

  Expected: FAIL because the coordinator and driver integration are absent.

- [ ] **Step 3: Implement the lease coordinator and driver integration**

  Pass `ownerId: job.id` into `openSession`. Acquire before `createRawSession`, attach the exact provider session ID, and clear only after provider release succeeds. On failure, retain the lease until expiry; takeover first releases the stale provider session.

- [ ] **Step 4: Run the CL03 tests and verify GREEN**

  Run the command from Step 2; expected all PASS.

- [ ] **Step 5: Write the CL04 failing integration test**

  Exercise Telegram handoff status, explicit resume, provider readback, receipt completion, and exact lease/session release once, with no credential value in result or trace.

- [ ] **Step 6: Run the CL04 test and verify RED**

  Run: `node --test lib/browser-job-runtime.test.js --test-name-pattern='phone-only'`

  Expected: FAIL until the lease-aware handoff evidence is returned.

- [ ] **Step 7: Implement the minimum handoff evidence change and verify GREEN**

  Keep existing Telegram/runtime semantics; expose only bounded lease release/readback metadata required by the test.

- [ ] **Step 8: Run all browser-focused tests**

  Run: `node --test lib/steel-session-lease.test.js lib/stagehand-steel-driver.test.js lib/generic-browser-task.test.js lib/browser-job-runtime.test.js`

  Expected: all PASS with zero leaked sessions or leases.

- [ ] **Step 9: Commit and push**

  Commit Task 2 files after `git diff --check`.

### Task 3: Acceptance Evidence, T11 Progress, and Integration

**Files:**
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`
- Create: `docs/evidence/cloud-edition-cl01-05.md`

**Interfaces:**
- Consumes: Task 1 parity result and Task 2 lease/handoff result.
- Produces: a local/cloud receipt comparison with commands, SHAs, hashes, and replay-zero result.

- [ ] **Step 1: Run focused acceptance and repository gates**

  Run the Task 1 and Task 2 focused suites, `./bin/lm-loop-contract`, `python3 -m unittest discover -s runtime/loop/tests -p 'test_*.py'`, `node --test apps/life-manager/lib/loop-adapter-registry.test.js`, and `git diff --check`.

- [ ] **Step 2: Record exact evidence and update T11**

  Mark CL01-CL05 complete only when each assertion has direct command output. Record the local and Cloud receipt JSON side by side, business-kernel SHA, capsule/evidence hashes, and replay-zero count; never record secrets.

- [ ] **Step 3: Commit, fetch, rebase if needed, and push**

  Preserve concurrent `origin/main` changes and never force-push.

- [ ] **Step 4: Fresh read-only review**

  Require `ASTRA REVIEW` verdict `ship`; fix and rerun if it returns `fix-first` or `rethink`.

- [ ] **Step 5: Open PR, wait for required checks, and admin merge**

  Verify the PR head and merged `origin/main` SHA. Do not deploy or touch production loops.
