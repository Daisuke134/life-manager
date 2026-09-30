# Life Manager DigitalOcean Cloud Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the existing Life Manager as a phone-only, no-human-loop cloud product on DigitalOcean Managed Agents without requiring a user computer or Mac Mini.

**Architecture:** Keep Railway API, Inngest, Supabase PostgreSQL, Stripe, the existing job/receipt state machine, and the existing business kernel. Add one thin DigitalOcean provider adapter that creates or resumes one tenant-owned Harness Runtime session, runs the immutable main-derived kernel, uses the session Chromium and Action Gateway/server-side secret refs, persists durable state outside VM RAM, and pauses or removes the session after official readback.

**Tech Stack:** Node.js 20 CommonJS, DigitalOcean `doctl harness-runtime`, DigitalOcean Chromium/Action Gateway, Railway, Inngest 4, PostgreSQL/Supabase, Stripe, object evidence storage, `node:test`.

**Spec:** `docs/superpowers/specs/2026-09-28-life-manager-agentcore-cloud-design.md`

## Global Constraints

- No human approval, credential entry, CAPTCHA, KYC, resume callback, or takeover is a normal success dependency.
- Reuse the existing Life Manager business kernel; do not create a DigitalOcean-only copy of business rules.
- One tenant has at most one active runtime lease and one browser writer lease.
- Only official provider readback settles effect, lifecycle, usage, cost, or revenue.
- A provider timeout after a possible effect enters `reconcile`; it never causes a blind replay.
- PAT/model/Action Gateway secrets stay in private SSOT or provider secret storage and never enter repository, prompt, job row, trace, or Telegram.
- Production promotion requires a main-derived immutable release, two-tenant isolation, replay-zero, teardown readback, and a rollback target.

## Review Focus

- Prepayment says eligible but blocked: no create/resume/exec call occurs and the job remains safely retryable.
- A foreign tenant supplies a valid-looking session/checkpoint ref: reject before any provider call.
- The process crashes after an external effect but before persistence: reconcile by official receipt and do not repeat the effect.
- A session pauses from idle or low balance: distinguish the reason and resume only when policy and budget allow.
- Chromium state is restored for the same tenant but never visible to another tenant.
- Official session IDs use UUID/ULID-like values rather than the old local `sess_*` fixture: accept only the provider's bounded documented shape and bind it to the tenant map.

---

### Task 1: Resolve and encode the DigitalOcean billing gate

**Files:**
- Modify: `apps/life-manager/lib/digitalocean-runtime-client.js`
- Modify: `apps/life-manager/lib/digitalocean-runtime-client.test.js`
- Create: `docs/evidence/cloud/digitalocean-billing-gate.json`

**Interfaces:**
- Consumes: `doctl harness-runtime balance -o json` and private PAT injection.
- Produces: `readAdmission(): Promise<{eligible:boolean, blocked:boolean, balanceMicros:number, autoPrepay:boolean, receipt:object}>`.

- [ ] Add failing tests for `eligible=true/blocked=true`, malformed money, missing billing scope, and positive unblocked balance.
- [ ] Implement integer-micros parsing and fail-closed `readAdmission()` without logging credentials.
- [ ] Run `node --test apps/life-manager/lib/digitalocean-runtime-client.test.js`; require zero failures.
- [ ] Perform a fresh official balance readback and store only sanitized configuration/status evidence.
- [ ] Pass when a new spend-cap-bounded session can be created, shown, removed, and absent from final list; otherwise record the exact provider blocker and continue only non-spending work.

### Task 2: Complete the production runtime lifecycle adapter

**Files:**
- Modify: `apps/life-manager/lib/digitalocean-runtime-client.js`
- Modify: `apps/life-manager/lib/digitalocean-runtime-client.test.js`
- Modify: `apps/life-manager/lib/cloud-runtime-dispatcher.js`
- Modify: `apps/life-manager/lib/cloud-runtime-dispatcher.test.js`

**Interfaces:**
- Consumes: tenant/job/release IDs, budget reservation, server-owned session ref.
- Produces: `create|show|exec|checkpoint|pause|resume|remove|list|logs` methods and canonical lifecycle receipts.

- [ ] Add failing tests for exact session binding, foreign refs, pause reasons, resume budget checks, checkpoint ownership, lingering removal, and ambiguous provider errors.
- [ ] Replace the stale `^sess_` validator with the bounded official DigitalOcean session-ID shape proven by live readback; keep malicious whitespace, control characters, flags, and foreign IDs rejected.
- [ ] Implement the missing lifecycle methods using argv arrays and JSON readback; never construct a shell command string.
- [ ] Add dispatcher selection `provider=digitalocean-managed-agents` while retaining the AWS code only as dormant compatibility code.
- [ ] Require admission, release SHA, tenant lease, and budget reservation before every create/resume/exec.
- [ ] Run the two focused test files; require zero failures and zero provider calls on rejected inputs.

### Task 3: Bind tenant-owned Chromium and agent-owned secrets

**Files:**
- Create: `apps/life-manager/lib/digitalocean-browser-driver.js`
- Create: `apps/life-manager/lib/digitalocean-browser-driver.test.js`
- Modify: `apps/life-manager/lib/browser-session-lease.js`
- Modify: `apps/life-manager/lib/browser-session-lease.test.js`
- Create: `apps/life-manager/agentcore/digitalocean-production.yaml`

**Interfaces:**
- Consumes: tenant lease, provider session ref, opaque checkpoint ref, Action Gateway/vault secret refs.
- Produces: `startBrowserJob()`, `saveBrowserCheckpoint()`, `stopBrowserJob()` and a provider-neutral browser receipt.

- [ ] Add failing tests proving one writer, same-tenant restore, cross-tenant rejection before provider call, secret-value rejection, and no `ask` permission.
- [ ] Implement the driver around session Chromium and server-owned checkpoint refs; never accept cookies or credentials from the client.
- [ ] Define production egress, strict deny rules, finite timeout, no keep-warm, and headless HITL rejection in the manifest.
- [ ] Run focused browser/lease tests and parse the manifest; require zero failures and no `ask|approve|human_wait` state.

### Task 4: Run the real two-tenant infrastructure canary

**Files:**
- Modify: `apps/life-manager/lib/digitalocean-infrastructure-canary.js`
- Modify: `apps/life-manager/lib/digitalocean-infrastructure-canary.test.js`
- Modify: `apps/life-manager/scripts/digitalocean-infrastructure-canary.js`
- Create: `docs/evidence/cloud/digitalocean-cl00.json`

**Interfaces:**
- Consumes: approved release SHA and production manifest.
- Produces: signed/sanitized CL00 receipt containing both session refs, isolation checks, browser continuity, lifecycle, teardown, usage, and cost evidence refs.

- [ ] Add failing tests for workspace leakage, browser-state leakage, missing pause/resume, lingering session, and missing cost receipt.
- [ ] Run two real tenant sessions and prove A cannot read B workspace/browser marker while A restores its own marker.
- [ ] Prove no human prompt, pause/resume semantics, exact remove, and final active session count zero.
- [ ] Join the before/after billing readback to both job IDs and persist sanitized evidence.

### Task 5: Prove same-kernel cloud parity and failure recovery

**Files:**
- Modify: `apps/life-manager/lib/digitalocean-agent-parity.js`
- Modify: `apps/life-manager/lib/digitalocean-agent-parity.test.js`
- Modify: `apps/life-manager/scripts/digitalocean-agent-parity-canary.js`
- Modify: `apps/life-manager/lib/cloud-runtime-dispatcher.test.js`
- Create: `docs/evidence/cloud/digitalocean-cl01-cl04.json`

**Interfaces:**
- Consumes: immutable main-derived SHA and canonical task capsule.
- Produces: matching local/cloud receipt and evidence hashes plus crash/reconcile/replay-zero proof.

- [ ] Add failing tests for wrong SHA, changed capsule, missing provider receipt, crash-before-effect, crash-after-effect, and redelivery.
- [ ] Run the exact local fixture and DigitalOcean fixture; require identical canonical hashes.
- [ ] Kill one run after claim and one after synthetic accepted effect; require recovery without duplicate effect.
- [ ] Confirm human input count zero, `effect_unknown` is reconciled, and all sessions are terminal/removed.

### Task 6: Promote and migrate production

**Files:**
- Modify: `apps/life-manager/scripts/cloud-promotion-gate.js`
- Modify: `apps/life-manager/scripts/cloud-promotion-gate.test.js`
- Create: `apps/life-manager/lib/cloud-production-config.js`
- Create: `apps/life-manager/lib/cloud-production-config.test.js`
- Create: `docs/evidence/cloud/digitalocean-production-promotion.json`

**Interfaces:**
- Consumes: CL00–CL04 evidence, approved SHA, provider config hash, cost receipt, rollback target.
- Produces: one immutable production provider config with `digitalocean-managed-agents` selected.

- [ ] Add failing gates for non-main SHA, incomplete evidence, stale active sessions, cost cap breach, missing rollback, and AWS accidentally selected.
- [ ] Promote only after `HEAD == origin/main == candidate SHA` and all DigitalOcean evidence passes.
- [ ] Apply migrations in fixed order: runtime base → identity refs → no-human browser → cost reservations → Free onboarding.
- [ ] Replay migrations and require identical schema SHA plus official PostgreSQL readback.

### Task 7: Complete phone-only product and revenue validation

**Files:**
- Modify: `apps/life-manager/lib/hosted-goal-ingress.js`
- Modify: `apps/life-manager/lib/hosted-goal-ingress.test.js`
- Modify: `apps/life-manager/lib/cloud-cost-ledger.js`
- Modify: `apps/life-manager/lib/cloud-cost-ledger.test.js`
- Create: `docs/evidence/cloud/phone-only-internal.json`
- Create: `docs/evidence/cloud/free-cohort-5.json`

**Interfaces:**
- Consumes: Telegram/web goal, Free/Pro entitlement, cloud receipts, Stripe receipts.
- Produces: verified-result timeline, net-outcome report, cohort metrics, and promotion/rollback decision.

- [ ] Run internal no-card onboarding → goal → scheduled cloud job → verified result → Telegram report with Mac Mini runtime disabled from the journey.
- [ ] Require credential/approval/resume prompts zero, external spend zero for the fixture, session leak zero, and official cost join.
- [ ] Run five Free tenants; require cross-tenant leak, duplicate effect, unbounded session, and cost-cap breach all zero.
- [ ] Sell the first $49 Founding Pro only after a verified result; read back Stripe receipt, entitlement, cancel/refund behavior, and contribution.
- [ ] Expand to 25 users and replace assumed cost/retention/conversion with p50/p75/p95 measured values before changing price or scaling beyond the preview limit.

## Atomic execution order

1. Billing gate readback and one bounded session lifecycle.
2. Runtime lifecycle adapter.
3. Chromium/secret boundary.
4. Two-tenant live infrastructure canary.
5. Same-kernel parity and recovery.
6. Immutable promotion and ordered migrations.
7. Internal phone-only E2E.
8. Five Free users.
9. First $49 receipt.
10. Twenty-five-user cohort and scale decision.
