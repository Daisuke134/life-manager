# Life Manager AgentCore Cloud Product Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the existing Life Manager as a real multi-tenant cloud product that needs only a phone, runs the same business kernel locally and in AWS AgentCore, gives every tenant a logically persistent cloud computer, enforces bounded cost, offers a natural no-card Free plan, and collects one verified $49 Founding Pro subscription.

**Architecture:** Keep the existing Railway ingress, Inngest scheduler, Supabase PostgreSQL job/receipt protocol, and Stripe billing. Add AWS Bedrock AgentCore Runtime V2 for active-job microVM isolation, AgentCore Browser Profiles for agent-owned browser continuity, AgentCore Identity for agent-owned outbound credentials, and S3/CloudWatch for evidence. A tenant has at most one active runtime lease; compute is created only for finite jobs and all durable truth remains outside VM RAM. Human credentials, approvals, takeover, and resume are not product dependencies. A tenant-bound shared-browser view and emergency stop are observability controls; any optional break-glass writer is single-owner and excluded from automated success and revenue. Four user journeys emit comparable field telemetry; bounded self-improvement may lower latency/cost ratchets only after verified outcome, effect safety, tenant isolation, and settled contribution remain healthy.

**Tech Stack:** Node.js 20 CommonJS business kernel, TypeScript AgentCore entrypoint, `@aws/agentcore@0.30.0` pinned, AWS SDK v3, AgentCore Runtime/Browser/Identity, Inngest 4, PostgreSQL/Supabase, Stripe, S3, CloudWatch, `node:test`.

**Spec:** `docs/superpowers/specs/2026-09-28-life-manager-agentcore-cloud-design.md`

## Global constraints

- No human in loop: normal jobs never emit `ask`, `approve`, or `human_wait`; deterministic policy and provider readback decide execution.
- Human credentials, login, OAuth, CAPTCHA, 2FA, 3DS, KYC, interviews, signatures, browser takeover, and resume callbacks are never required by the default product path. Select an agent-owned/API alternative or close the candidate as `not_applicable: requires_human_principal` and continue.
- Existing `handoff_required` browser rows are migrated explicitly in Task 6 to terminal `not_applicable` records; do not silently reinterpret or resume stored production rows.
- Meta Muse is an architecture benchmark with a persistent isolated Linux VM, shared full browser, credential store, generated tools, and background goals. Muse Connector is a separate future distribution interface; never treat it as Life Manager compute.

## Current state and scope

- `a78ab3d306` contains the first local/cloud host-adapter parity slice. It is unit evidence, not a real cloud proof.
- `5be0ff8551` classifies the pending browser work: `browser-session-lease` is the provider-neutral ownership contract, while Stagehand/Steel remains a conditional compatibility fallback. Its 79 focused tests are local evidence, not CL03 completion or an AgentCore implementation.
- `lm_runtime_jobs`, tenant-scoped job leases, browser jobs, Inngest per-user functions, Stripe webhook entitlement, and PostgreSQL adapters already exist and must be reused.
- Do not build a second Life Manager repository or copy business rules into the AgentCore wrapper.
- Do not migrate Railway/Inngest/Supabase/Stripe in this plan. Replatforming the working control plane is outside the critical path.
- Do not mark any CL gate complete from mocks, local simulation, or a provider dashboard screenshot. Each cloud gate requires resource IDs, official readback, usage/cost evidence, and replay-zero.

## Definition of done

1. A user can onboard with only Telegram/web on a phone, no card, and receive one verified result.
2. The same immutable business-kernel SHA runs locally and in AgentCore.
3. Each active tenant run has a dedicated AgentCore microVM; idle tenants consume no runtime VM.
4. Agent-owned browser login survives across jobs through a tenant/provider Browser Profile; no human credential is imported.
5. Actions complete with zero credential requests, confirmations, approvals, required browser takeover, or resume steps. A user can observe and emergency-stop a browser from a phone. Optional break-glass control never counts as automated completion or revenue; human-principal-only opportunities are excluded without stopping other work.
6. Cross-tenant access, duplicate execution, uncertain-effect replay, unbounded session, and budget overrun all fail closed.
7. Free costs cannot exceed their deterministic caps; every paid user has a complete revenue/cost contribution row.
8. Five-user and then 25-user cohorts pass operational gates.
9. Stripe records and the application reads back one real $49 Founding Pro subscription.

---

### Task 1: Freeze the provider decision and protect the existing kernel

**Files:**
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`
- Modify: `docs/superpowers/plans/2026-09-28-cloud-edition-cl01-05.md`
- Test: `apps/life-manager/lib/cloud-edition-host-adapter.test.js`

**Produces:** one live Cloud plan, one provider decision, and explicit evidence that current parity code is only CL01 unit groundwork.

- [x] **Step 1: Record the supersession**

  Point T11 and the old CL01-CL05 plan to the AgentCore design and this plan. Preserve historical completed work; do not label the local simulation a cloud canary.

- [x] **Step 2: Re-run the existing parity unit test**

  Run from `apps/life-manager`:

  ```bash
  node --test lib/cloud-edition-host-adapter.test.js
  ```

  Expected: PASS. Record the business-kernel SHA and note that no AWS call occurred.

- [x] **Step 3: Classify the pending Steel changes**

  Inspect only the six existing dirty browser/Steel files. Reusable provider-neutral lease behavior stays as an adapter contract; Steel-specific code is deferred behind a compatibility canary. Do not count it as AgentCore implementation.

- [x] **Step 4: Commit the documentation decision separately**

  Stage only the spec/plan files. Preserve all pre-existing code changes. Task 1 closes with the documentation commit containing this checkbox; the next cursor is Task 2 Step 1.

---

### Task 2: Prove AgentCore in Tokyo before building the product around it (CL00)

**Files:**
- Modify: `apps/life-manager/package.json`
- Modify: `apps/life-manager/package-lock.json`
- Create: `apps/life-manager/agentcore/agentcore.json`
- Create: `apps/life-manager/agentcore/app/cloud-canary/main.ts`
- Create: `apps/life-manager/agentcore/app/cloud-canary/package.json`
- Create: `apps/life-manager/scripts/agentcore-cloud-canary.js`
- Test: `apps/life-manager/scripts/agentcore-cloud-canary.test.js`
- Create: `docs/evidence/cloud/agentcore-cl00.md`

**Produces:** a disposable read-only runtime/browser/agent-owned-profile/identity canary in `ap-northeast-1`, deployed from a pinned official CLI configuration.

- [x] **Step 1: Write the canary contract test**

  Test that the script rejects missing region, non-Tokyo resource ARN, mutable/unpinned release SHA, missing runtime session ID, missing browser/profile ID, missing official usage record, or any effect other than `none`.

  ```js
  assert.equal(result.region, "ap-northeast-1");
  assert.equal(result.effect, "none");
  assert.match(result.release_sha, /^[a-f0-9]{40}$/);
  assert.ok(result.runtime_session_id);
  assert.ok(result.browser_profile_id);
  assert.ok(result.usage_receipt_ref);
  ```

- [x] **Step 2: Verify RED**

  ```bash
  node --test scripts/agentcore-cloud-canary.test.js
  ```

  Expected: FAIL because the canary parser/runner is absent.

- [x] **Step 3: Pin the official CLI**

  Add exact dev dependency `@aws/agentcore: 0.30.0`; do not use the legacy Python starter toolkit. Generate declarative `agentcore.json` and CDK assets under `apps/life-manager/agentcore/`. Commit generated infrastructure only after review; never commit `.env.local`, account IDs, tokens, or signed URLs.

- [x] **Step 4: Implement a read-only runtime**

  The runtime accepts `{ tenant_id, job_id, release_sha, probe: "read_only" }`, emits its isolated filesystem/session identifiers, and exits without network effects. It does not import a second business implementation.

- [x] **Step 5: Validate and package locally**

  ```bash
  npx agentcore validate --directory . --json
  node scripts/agentcore-cloud-canary-package.js
  ```

  The pinned CLI `package` command delegates to Ink without terminating in a non-interactive shell. The repository wrapper calls the same exported `ConfigIO`, `resolveCodeLocation`, `validateAgentExists`, and `packCodeZipSync` APIs and exits deterministically. Expected: valid pinned config and reproducible package contents; archive bytes may differ because the upstream ZIP writer embeds timestamps. No AWS mutation yet.

- [ ] **Step 6: Deploy the CL00 canary**

  This changes cloud state; announce it immediately before running. Deploy only the canary resources in Tokyo, invoke one runtime session, create one agent-owned Browser Profile, open one browser session to an inert read-only page, request one non-secret Identity health result, then stop every session. Do not supply a human credential or interactive takeover.

- [ ] **Step 7: Read back provider state and cost**

  Require runtime/browser terminal state, CloudTrail/CloudWatch trace, S3 evidence hash if recording is enabled, and AWS usage/cost reference. Verify no active canary sessions remain.

- [ ] **Step 8: Write CL00 evidence and decide**

  Pass only if Runtime, Browser/Profile, and Identity work without human input. If Browser fails the agent-owned path, stop AgentCore expansion and evaluate the existing Steel adapter against the exact failed contract; do not silently combine both providers.

---

### Task 3: Add durable tenant, entitlement, runtime, browser-profile, and cost contracts

**Files:**
- Create: `apps/life-manager/migrations/20260928_agentcore_cloud_runtime.sql`
- Create: `apps/life-manager/lib/cloud-runtime-store.js`
- Create: `apps/life-manager/lib/cloud-runtime-store.test.js`
- Create: `apps/life-manager/lib/cloud-entitlement.js`
- Create: `apps/life-manager/lib/cloud-entitlement.test.js`
- Modify: `apps/life-manager/lib/runtime-job-store.js`
- Test: `apps/life-manager/test/postgres/agentcore-cloud-runtime.integration.sh`

**Produces:** one durable mapping and budget ledger, while keeping `lm_runtime_jobs` as the only job queue/state machine.

- [x] **Step 1: Write RED schema/contract tests**

  Require these tenant-scoped records:

  ```text
  lm_cloud_tenants(tenant_id, region, release_sha, status, plan_version)
  lm_cloud_runtime_leases(tenant_id PK, job_id, attempt, runtime_session_id,
                          lease_owner, lease_expires_at, generation)
  lm_cloud_browser_profiles(tenant_id, provider, profile_id, updated_at)
  lm_cloud_usage_ledger(tenant_id, job_id, provider, resource, quantity,
                        unit, cost_usd_micros, provider_receipt_id)
  lm_plan_entitlements(plan_version, plan, limits_json, effective_at)
  ```

  Test composite foreign keys, RLS/tenant predicates, one active runtime per tenant, immutable usage rows, and idempotent provider receipt IDs.

- [x] **Step 2: Verify RED**

  ```bash
  node --test lib/cloud-runtime-store.test.js lib/cloud-entitlement.test.js
  bash test/postgres/agentcore-cloud-runtime.integration.sh
  ```

- [x] **Step 3: Implement the minimum migration/store**

  Reuse `lm_runtime_jobs`; do not create a second queue. Store provider IDs only after validating their tenant/job binding. Use integer USD micros, never floating-point money.

- [x] **Step 4: Seed versioned launch entitlements**

  Seed `free-v1` and `founding-pro-v1` from the design spec. The pure decision function returns one of `allow`, `budget_exhausted`, `plan_inactive`, or `manual_hold`; it never charges money.

- [x] **Step 5: Verify GREEN and migration rollback fixture**

  Run the commands from Step 2. Also prove a failed migration transaction leaves the old runtime job protocol intact.

---

### Task 4: Package the same Life Manager kernel for AgentCore Runtime (CL01)

**Files:**
- Create: `apps/life-manager/lib/agentcore-runtime-envelope.js`
- Create: `apps/life-manager/lib/agentcore-runtime-envelope.test.js`
- Create: `apps/life-manager/agentcore/app/life-manager/main.ts`
- Create: `apps/life-manager/agentcore/app/life-manager/main.test.ts`
- Modify: `apps/life-manager/lib/cloud-edition-host-adapter.js`
- Test: `apps/life-manager/lib/cloud-edition-host-adapter.test.js`

**Produces:** an AgentCore transport wrapper that validates identity/release/budget, calls the existing CommonJS kernel, and returns a bounded result envelope.

- [x] **Step 1: Write RED envelope tests**

  Reject missing tenant/job/attempt/wake/release IDs, payloads over the limit, inline credentials, unapproved SHA, and result envelopes without receipt/evidence/cost fields.

- [x] **Step 2: Verify RED**

  ```bash
  node --test lib/agentcore-runtime-envelope.test.js lib/cloud-edition-host-adapter.test.js
  ```

- [x] **Step 3: Implement the wrapper, not a second agent**

  `main.ts` performs protocol translation only. Business execution remains `executeBusinessTask()` and existing loop adapters. The wrapper receives reference-only input and emits:

  ```json
  {
    "tenant_id": "...",
    "job_id": "...",
    "attempt": 1,
    "release_sha": "...",
    "status": "completed|retry|reconcile|not_applicable|policy_denied|blocked",
    "receipt_ref": "...",
    "evidence_sha256": "...",
    "usage": []
  }
  ```

- [x] **Step 4: Run local transport parity**

  Invoke the wrapper locally with the literal CL01 fixture and compare the full canonical receipt/evidence hash to the local host adapter.

- [ ] **Step 5: Run real AgentCore parity**

  Deploy the immutable candidate, invoke the same fixture in Tokyo, read the official result, and require exact parity. A different session ID is expected; a different business receipt is failure.

---

### Task 5: Connect Inngest to AgentCore with one tenant writer

**Files:**
- Create: `apps/life-manager/lib/agentcore-runtime-client.js`
- Create: `apps/life-manager/lib/agentcore-runtime-client.test.js`
- Create: `apps/life-manager/lib/cloud-runtime-dispatcher.js`
- Create: `apps/life-manager/lib/cloud-runtime-dispatcher.test.js`
- Modify: `apps/life-manager/inngest/functions.js`
- Modify: `apps/life-manager/test/inngest.test.js`

**Produces:** existing Inngest schedules claim existing PostgreSQL jobs and invoke at most one AgentCore runtime per tenant.

- [ ] **Step 1: Write RED dispatcher tests**

  Prove: refetch tenant/job at execution time, budget check before AWS call, release SHA gate, atomic lease claim, tenant concurrency=1, bounded timeout, stable idempotency token, and zero invoke on duplicate/stale events.

- [ ] **Step 2: Verify RED**

  ```bash
  node --test lib/agentcore-runtime-client.test.js lib/cloud-runtime-dispatcher.test.js test/inngest.test.js
  ```

- [ ] **Step 3: Implement AgentCore client**

  Keep the AWS SDK behind an injected client. Never log payloads or signed endpoints. Map AWS transient failures to bounded retry; map ambiguous post-invoke failures to reconcile, not a blind second invocation.

- [ ] **Step 4: Add one Inngest function**

  Add `lm/cloud.job` with `concurrency.key = event.data.tenant_id` and limit 1. Events contain only tenant/job identifiers. The handler refetches state and calls the dispatcher.

- [ ] **Step 5: Prove crash/cold-start recovery**

  Kill the local fake worker after claim, expire its lease, and show the next attempt restores from PostgreSQL checkpoint without duplicating an effect. Then repeat one read-only case against AgentCore.

---

### Task 6: Replace the primary Steel path with human-free AgentCore Browser Profiles (CL03/CL04)

**Files:**
- Create: `apps/life-manager/lib/agentcore-browser-driver.js`
- Create: `apps/life-manager/lib/agentcore-browser-driver.test.js`
- Create: `apps/life-manager/lib/browser-principal-policy.js`
- Create: `apps/life-manager/lib/browser-principal-policy.test.js`
- Modify: `apps/life-manager/lib/generic-browser-task.js`
- Modify: `apps/life-manager/lib/browser-job-runtime.js`
- Test: `apps/life-manager/lib/browser-job-runtime.test.js`

**Produces:** job-scoped browser sessions, agent-owned tenant/provider profiles, zero-human execution, tenant-bound live observation/emergency stop, and terminal exclusion of human-principal-only opportunities.

- [ ] **Step 1: Write RED browser/profile tests**

  Assert profile lookup is tenant/provider scoped and agent-owned, concurrent owners cannot start a second session, profile save happens only after verified completion, and failed release retains reconciliation data.

- [ ] **Step 2: Write RED no-human principal tests**

  Assert policy-allowed agent-owned actions expose no credential request, ask, approve, takeover, or resume state. Human credential/profile input and sites requiring human login, OAuth, CAPTCHA, 2FA, 3DS, KYC, interview, or signature return `not_applicable: requires_human_principal`, make no external effect, and do not stop another eligible job.

- [ ] **Step 2a: Write RED shared-browser observability tests**

  Require a tenant-bound opaque viewer ref, read-only activity stream, and emergency stop. Cross-tenant viewer refs fail before provider calls. If optional break-glass writing is enabled, it must first stop the agent writer under the same lease generation, record `manual_external`, exclude the result from automated success/revenue, and never create a resume callback.

- [ ] **Step 3: Implement the AgentCore driver**

  Map the existing provider-neutral browser contract onto StartBrowserSession, automation WebSocket, SaveBrowserSessionProfile, and StopBrowserSession. Accept only server-owned profile refs and agent-owned principals; never expose AWS credentials or raw profile data.

- [ ] **Step 3a: Implement shared-browser observation without a completion dependency**

  Expose phone/web read-only live view and emergency stop through server-owned opaque refs. Do not expose cookies, credentials, raw Browser Profile data, AWS URLs, or a second writer. Keep full browser recording in the evidence timeline.

- [ ] **Step 4: Migrate legacy handoff rows without resuming them**

  Convert existing `handoff_required` rows to terminal `not_applicable` receipts with reason `requires_human_principal`. Do not replay their effect, ask for credentials, send an approval link, or create a resume callback.

- [ ] **Step 5: Run focused tests**

  ```bash
  node --test lib/agentcore-browser-driver.test.js lib/browser-principal-policy.test.js lib/browser-job-runtime.test.js
  ```

- [ ] **Step 6: Run real no-human canary**

  On a dedicated test tenant, prove one agent-owned read-only browser action completes with human inputs 0 and read back the same tenant/profile binding. Observe it through the phone/web viewer and exercise emergency stop on a separate inert run without credential exposure or a second writer. Probe one synthetic human-principal requirement and require provider effect 0, terminal `not_applicable`, another queued job completed, and active sessions=0 afterward.

---

### Task 7: Move outbound credentials to AgentCore Identity

**Files:**
- Create: `apps/life-manager/lib/agentcore-identity-provider.js`
- Create: `apps/life-manager/lib/agentcore-identity-provider.test.js`
- Modify: `apps/life-manager/lib/hosted-goal-ingress.js`
- Modify: `apps/life-manager/lib/browser-auth-session-store.js`
- Test: `apps/life-manager/lib/browser-auth-session-store.test.js`

**Produces:** agent-owned cloud connections store OAuth/API credentials in AgentCore Identity; human-owned credentials are rejected and never migrated.

- [ ] **Step 1: Write RED secret-boundary tests**

  Prove job rows, prompts, runtime envelopes, traces, and Telegram payloads contain opaque refs only. Cross-tenant or human-principal ref use must fail before AgentCore Identity is called.

- [ ] **Step 2: Implement the provider interface**

  Keep `health`, `authorize`, `resolveRef`, and `revoke` behind the existing secret-provider boundary. Do not make AgentCore Identity business truth.

- [ ] **Step 3: Add migration-on-use**

  For an existing agent-owned supported credential, verify ownership, create the Identity credential, store the opaque ref, verify a read-only call, and only then retire the old cloud credential copy. Never migrate local Mac or human credentials.

- [ ] **Step 4: Verify revoke and tenant deletion**

  Revocation removes provider access and pauses dependent jobs without deleting receipts/evidence.

---

### Task 8: Prove adversarial tenant isolation and uncertain-effect recovery (CL02/CL03)

**Files:**
- Create: `apps/life-manager/test/cloud/agentcore-tenant-isolation.test.js`
- Create: `apps/life-manager/test/cloud/agentcore-effect-recovery.test.js`
- Modify: `apps/life-manager/test/tenant-isolation.test.js`
- Create: `docs/evidence/cloud/agentcore-cl01-cl04.md`

**Produces:** direct evidence that the cloud product cannot cross tenant boundaries or duplicate an uncertain effect.

- [ ] **Step 1: Add forged-reference cases**

  Cover state ref, receipt ref, runtime session, browser session, browser profile, Identity ref, S3 key, human credential input, approval callback, and resume callback. For every rejection, assert provider call count is zero.

- [ ] **Step 2: Add lifecycle failure cases**

  Cover process crash before effect, crash after effect before receipt, AWS timeout after accepted invoke, browser disconnect, stale lease, deploy with old release, and Inngest redelivery.

- [ ] **Step 3: Verify locally**

  ```bash
  node --test test/cloud/agentcore-tenant-isolation.test.js test/cloud/agentcore-effect-recovery.test.js test/tenant-isolation.test.js
  ```

- [ ] **Step 4: Verify bounded real-cloud cases**

  Run read-only and synthetic-receipt canaries only. Require `effect_unknown` quarantine when acceptance is ambiguous and replay-zero after reconciliation.

---

### Task 9: Enforce cost accounting and the natural Free plan (CL06)

**Files:**
- Create: `apps/life-manager/lib/cloud-cost-ledger.js`
- Create: `apps/life-manager/lib/cloud-cost-ledger.test.js`
- Create: `apps/life-manager/lib/cloud-plan-policy.js`
- Create: `apps/life-manager/lib/cloud-plan-policy.test.js`
- Modify: `apps/life-manager/lib/financial-record-store.js`
- Modify: `apps/life-manager/lib/telegram-onboard.js`
- Modify: `apps/life-manager/lib/hosted-goal-ingress.js`
- Test: `apps/life-manager/lib/telegram-onboard.test.js`

**Produces:** every job has actual model/runtime/browser/tool cost, and no Free or paid tenant can exceed its hard limit.

- [ ] **Step 1: Write RED money tests**

  Use integer micros. Prove provider receipt dedupe, monthly boundary, activation credit one-time use, Free $0.50 cap, Pro $12 cap, and fail-closed behavior when cost is unknown.

- [ ] **Step 2: Implement usage ingestion**

  Join AgentCore runtime/browser usage, model tokens, Gateway/search/tool cost, Railway/Inngest/Supabase shared allocation, and Stripe fees. Estimated cost can reserve budget before a job; only provider readback settles it.

- [ ] **Step 3: Implement no-card onboarding**

  New tenants receive `free-v1`, one goal, and $1 activation credit. Choose the cheapest useful read-only first task. Do not show a checkout link before the first verified result.

- [ ] **Step 4: Add deterministic admission**

  Before claim/invoke, reserve the estimated maximum. After readback, settle actual cost and release the remainder. If actual cost is unavailable, keep the reservation and reconcile; never assume zero.

- [ ] **Step 5: Add unit economics report**

  Per tenant/month output subscription collected, internal company revenue, refunds, Stripe fees, each variable cost, allocated shared cost, and contribution. Keep user income in a separate column/ledger.

---

### Task 10: Promote the immutable release and run five real Free tenants (CL05)

**Files:**
- Modify: `apps/life-manager/scripts/cloud-promotion-gate.js`
- Modify: `apps/life-manager/scripts/cloud-promotion-gate.test.js`
- Create: `docs/evidence/cloud/agentcore-cl05-five-tenant.md`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Produces:** one main-derived immutable AgentCore release, five phone-only tenants, and official replay/cost evidence.

- [ ] **Step 1: Write RED promotion tests**

  Gate on merged main SHA, complete local manifest, CL00-CL04 evidence, migration version, AgentCore config hash, no active old release sessions, cost caps, and rollback target.

- [ ] **Step 2: Deploy candidate and canary tenant**

  Deploy one immutable version, bind only the internal canary tenant, complete an agent-owned read-only task with human inputs 0, official readback, and replay-zero.

- [ ] **Step 3: Expand to five invited Free tenants**

  Each tenant completes onboarding and one verified result. Measure activation time, actual cost, session cleanup, human-input count, human-principal exclusions, and errors. For `goal->first verified result`, `wake->official receipt`, `browser start->first useful action`, and `settled change->CFO/report`, record release/model/tool versions, p50/p75/p95 latency, cost, steps, retries, effect/readback, and verified outcome. Free policy permits no external spend, so no spending action is admitted or asked about.

- [ ] **Step 4: Evaluate gates**

  Require cross-tenant leak 0, duplicate effect 0, cost cap breach 0, unbounded active session 0, and every failure either recovered or typed/fenced with next action. Establish field baselines for the four core journeys; do not create a ratchet from fewer than the five cohort tenants or from a proxy metric without field correlation.

- [ ] **Step 5: Roll back or promote**

  Any invariant failure rolls the tenant mapping back to the last release and stops expansion. Passing evidence promotes the version to Free cohort default.

---

### Task 11: Collect the first $49 subscription and prove per-user profit (R01)

**Files:**
- Create: `apps/life-manager/migrations/20260928_cloud_plan_economics.sql`
- Create: `apps/life-manager/lib/cloud-subscription-offer.js`
- Create: `apps/life-manager/lib/cloud-subscription-offer.test.js`
- Modify: `apps/life-manager/lib/billing.js`
- Modify: `apps/life-manager/lib/billing.test.js`
- Modify: `apps/life-manager/lib/slash-command.js`
- Modify: `apps/life-manager/lib/slash-command.test.js`
- Create: `docs/evidence/cloud/founding-pro-r01.md`

**Produces:** a post-value $49 offer, Stripe receipt, entitlement transition, cancellation behavior, and a settled contribution row.

- [ ] **Step 1: Write RED offer tests**

  Offer only after a verified result. Preserve Free state when declined. Bind checkout to tenant. Require price/plan version and reject stale/foreign checkout callbacks.

- [ ] **Step 2: Extend existing Stripe lifecycle**

  Keep Stripe webhook as the only entitlement writer. Map `active/trialing/past_due` through existing deterministic status logic; add `plan_version` and collected amount/currency without trusting client input.

- [ ] **Step 3: Verify test-mode lifecycle**

  Cover checkout, active, out-of-order event, duplicate event, past_due, cancel, refund, and entitlement downgrade.

- [ ] **Step 4: Enable one live Founding Pro checkout**

  This changes billing state; announce immediately before enabling. Present it only to an activated cohort user. Do not self-purchase and do not count a test receipt.

- [ ] **Step 5: Read back the first live receipt**

  Require Stripe payment/subscription IDs, settled currency/amount, tenant entitlement, and no duplicate webhook application. Produce the tenant/month contribution statement with actual cost, not the $6 estimate.

---

### Task 12: Expand to 25 Free tenants, then add Muse Connector as distribution (R02)

**Files:**
- Create: `apps/life-manager/lib/cloud-cohort-gate.js`
- Create: `apps/life-manager/lib/cloud-cohort-gate.test.js`
- Create: `docs/evidence/cloud/free-cohort-r02.md`
- Create after Meta access: `apps/life-manager/connectors/meta-ai/openapi.yaml`
- Create after Meta access: `apps/life-manager/connectors/meta-ai/README.md`

**Produces:** measured cohort economics and, only after the API is stable and Meta allows publishing, a Muse Connector that invokes Life Manager rather than replacing it. Meta Muse itself remains a competing personal cloud agent and architecture benchmark, not the runtime used by this plan.

- [ ] **Step 1: Define cohort gates in code**

  Track activation, first verified result, D7/D30 retention, Free→Paid conversion, cost/active user, human-input count, human-principal exclusions, duplicate effects, and tenant isolation incidents.

- [ ] **Step 2: Expand 5 → 25**

  Invite users in bounded batches. Pause new invitations automatically if cost/user exceeds $0.50 after activation credit, any isolation/effect invariant fails, or active sessions leak.

- [ ] **Step 3: Replace unit-economics assumptions**

  Update the CFO report with measured p50/p95 cost and contribution. Do not alter the $49 price from one anecdote; use the 25-user cohort and paid conversion evidence.

- [ ] **Step 3a: Activate bounded journey hill-climbing**

  Select the first material bottleneck from the four core journeys. Create one isolated, one-variable candidate and a deterministic proxy benchmark. Require correlation with a real field outcome, held-out/safety/cost evaluation, and one-tenant canary. Promote and lower the ratchet only when verified outcome, effect safety, tenant isolation, effect-unknown rate, and settled contribution do not regress; otherwise roll back automatically. The candidate may not edit its evaluator, receipt definition, identity, permissions, spend caps, tenant boundary, or rollback mechanism.

- [ ] **Step 4: Register Muse Connector only when publishable**

  Expose narrow REST/MCP actions such as create goal, read status, pause/resume, and retrieve verified result. Muse receives opaque Life Manager tenant authorization and never receives AWS/Supabase/Stripe credentials or direct browser control.

- [ ] **Step 5: Final review and integration**

  Run focused tests, PostgreSQL integration tests, AgentCore canaries, `git diff --check`, and a fresh read-only architecture/security review. Open one PR, wait for required checks, admin merge, deploy main-derived immutable release, read back provider state, and confirm replay-zero.

## TODO order — do not reorder without measured evidence

1. **CL00 real AgentCore provider proof** — decides whether the chosen runtime/browser actually works.
2. **Durable tenant/session/budget schema** — makes every later call tenant-safe and cost-bounded.
3. **Same-kernel AgentCore packaging (CL01)** — prevents a second product implementation.
4. **Inngest dispatcher + one tenant writer** — makes loops genuinely run in cloud.
5. **Agent-owned Browser Profile (CL03/CL04)** — removes the Mac without introducing human login or takeover.
6. **Agent-owned Identity boundary** — enables authenticated real work without human credentials or exposed secrets.
7. **Isolation + uncertain-effect recovery (CL02)** — makes multi-tenant selling safe.
8. **Cost ledger + Free admission (CL06)** — bounds loss before onboarding strangers.
9. **Immutable promotion + 5 Free users (CL05)** — proves the real product path.
10. **First $49 Stripe receipt (R01)** — proves company revenue and one-user contribution.
11. **25-user cohort (R02)** — replaces assumptions with measured unit economics.
12. **Muse Connector** — distribution after the Life Manager API is stable and Meta publishing exists.

Do not move billing ahead of real-cloud cost measurement, and do not move Muse ahead of the product API. Those two reorderings make revenue or distribution claims without a working Life Manager cloud core.

## Atomic execution ledger — current cursor and start-to-finish order

Each row has one bounded output and one observable completion condition. Do not mark a cloud row complete from a mock.

**Current cursor:** AWS identity authentication and the Tokyo AgentCore control-plane list APIs work, but the account is not service-active: CloudFormation returns `OptInRequired`, S3 returns `NotSignedUp`, the Free Tier plan API returns missing account data, and the console still identifies signup as incomplete. Therefore A06 and A13 are externally blocked, not done, and no deployment retry is allowed before an official AWS response. A11 and A12 are complete; immediate order is `A14 -> A15 -> A16` while the existing activation case remains inside its stated response window, then `A06 -> A07 -> A13` as soon as provider readback proves CloudFormation and S3 active. If AWS gives no response by the stated window or its exact one-time retry still leaves either API inactive, run the existing provider-neutral contract as a bounded DigitalOcean Managed Agents plus Steel compatibility canary; adopt it only if Runtime isolation, agent-owned browser continuity, deterministic no-ask policy, lifecycle readback, and teardown/cost receipts all pass. Control-plane reachability or console login alone is never a cloud pass.

| ID | Status | Atomic output | Completion evidence |
|---|---|---|---|
| A00 | done | Provider decision and one live spec/plan | `7eb28dc7a6`; old plan points here |
| A01 | done | Same-kernel local/cloud host-adapter groundwork | `a78ab3d306`; parity unit test 3/3, AWS calls 0 |
| A02 | done | Provider-neutral browser lease; Steel adapter integration | `5be0ff8551`; focused tests 79/79 |
| A03 | done | CL00 canary contract test | RED for missing/foreign resource IDs, mutable SHA, effect other than `none`, or missing usage receipt |
| A04 | done | Pinned AgentCore CLI/config | exact dependency + validated `agentcore.json` |
| A05 | done | Read-only canary runtime package | Runtime 3/3, canary/package 10/10, CDK 1/1, content manifest 178/178 identical, production dependency audits 0; no AWS mutation |
| A06 | external-blocked | Tokyo Runtime/Browser/agent-owned Profile/Identity canary | official resource IDs; human credential/input 0; CloudFormation and S3 must first return active official readback |
| A07 | todo | CL00 teardown and cost readback | terminal sessions, active sessions 0, usage/cost receipt, evidence doc |
| A08 | done | Tenant/runtime/profile/usage schema tests | RED: missing store/entitlement modules and migration; contracts cover cross-tenant refs, duplicate receipts, second active runtime, integer micros, RLS, and immutable usage |
| A09 | done | Migration and durable stores | store 5/5; PostgreSQL migration replay, tenant/job FK, single lease, receipt dedupe, immutable usage, RLS, role boundary, and failed-transaction rollback PASS |
| A10 | done | Versioned `free-v1` and `founding-pro-v1` policy | pure admission 3/3; Task 3 unit 8/8 and PostgreSQL seeded-policy readback PASS |
| A11 | done | AgentCore envelope contract | 7/7 focused tests; inline secrets, foreign tenant refs, wrong SHA, oversized input, incomplete receipt/evidence/usage, fractional micros, and extra output all rejected |
| A12 | done | Thin AgentCore wrapper over existing kernel | wrapper 2/2 plus envelope/host 7/7; persisted canonical receipt and evidence hash exactly match local host |
| A13 | external-blocked | Real AgentCore kernel parity | same approved SHA and canonical receipt/evidence hash after AWS service activation |
| A14 | **next** | Runtime SDK client and dispatcher tests | budget/release/lease checks occur before provider call |
| A15 | todo | One Inngest cloud-job function | tenant concurrency 1; event carries IDs only |
| A16 | todo | Crash/cold-start recovery | checkpoint resume with duplicate effect 0 |
| A17 | todo | AgentCore Browser Profile adapter | agent-owned tenant/provider profile and exact session release |
| A18 | todo | No-human browser policy, shared-browser observation, and legacy-state migration | human credential/callback/provider effect 0; phone/web live view + emergency stop; cross-tenant view 0; optional break-glass excluded from automated success/revenue; stored `handoff_required` closes `not_applicable` without replay |
| A19 | todo | Real no-human browser canary | agent-owned action completes; human-only probe closes; another job continues; active sessions 0 |
| A20 | todo | AgentCore Identity provider and migration-on-use | agent-owned opaque refs only; human refs rejected; revoke closes dependent jobs without asking |
| A21 | todo | Adversarial tenant/effect recovery suite | cross-tenant access 0, duplicate effect 0, ambiguous effects quarantined |
| A22 | todo | Cost ledger and reservation/admission | integer micros, provider dedupe, Free $0.50 and Pro $12 fail-closed caps |
| A23 | todo | Natural no-card Free onboarding | one goal and first verified result before checkout offer |
| A24 | todo | Immutable main-derived promotion | existing promotion gate PASS plus official readback/replay-zero |
| A25 | todo | Internal + five-user phone-only cohort | isolation/effect/session/cost invariant breaches 0 |
| A26 | todo | First live $49 Founding Pro receipt | Stripe readback, entitlement transition, actual tenant contribution row |
| A27 | todo | 25-user cohort and four-journey field baseline | measured activation, D7/D30, conversion, p50/p75/p95 latency and cost replace assumptions |
| A28 | todo | Bounded journey hill-climbing and repeatable growth toward 204,082 active paid | proxy-to-field correlation; isolated candidate; automated canary/rollback; successful ratchet; each scale gate shows retained paid net growth after churn replacement |
| A29 | todo | Muse Connector distribution | only after stable Life Manager API and publishable Meta access |
