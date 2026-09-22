# Life Manager CC02 Durable Cloud Goal Slice Implementation Plan

> **Execution:** Use `superpowers:executing-plans` task by task. Use TDD for every behavior change and `superpowers:verification-before-completion` before closing CC02.

**Goal:** Close CC02 with one authenticated, tenant-scoped, durable, non-effectful path from an existing Panel session and one-time reference context to a Life Manager-generated Goal Portfolio, one `effect_class=none` RuntimeJob, and a safe state/receipt projection.

**Architecture:** Reuse `panel-auth.js` as the only sign-in authority and `runtime-job-store.js` as the only durable work queue. Add a strict reference-only goal-context contract and two versioned Postgres records: context and portfolio. A small orchestration service resolves the session, creates or reads context, calls the existing hosted goal ingress, and reads an opaque projection from the persisted RuntimeJob/receipt. No HTTP route, provider adapter, browser, credential copy, or external effect belongs to CC02.

**Tech stack:** Node.js 20 CommonJS, `node:test`, PostgreSQL/Supabase service-role SQL, existing Panel session helpers, existing goal policy/portfolio/ingress/runtime job modules.

**Spec:** `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md`, J4/J5 “CC02 concrete contract”.

**Protected boundary:** Do not modify the Paid worktree/branch/specs, any Coconala/CrowdWorks/Lancers/Upwork Paid module/test/state/owner, `config/loop-registry.json`, or `apps/life-manager/config/product-loop-catalog.json`.

---

## Task 1: Define the reference-only goal context contract

**Files:**
- Create: `apps/life-manager/lib/goal-context.js`
- Create: `apps/life-manager/lib/goal-context.test.js`

**Interfaces:**
- `validateGoalContext(value, expectedTenantId)` returns a deeply frozen exact-shape context.
- `goalContextReference(value)` returns `goal-context://<tenant>?revision=<n>`.
- `goalSynthesisRefs(value)` returns frozen `{ factRefs, evidenceRefs, boundaryRefs }`, with the J4 policy reference plus account and consent references in `evidenceRefs`.

- [ ] **Step 1: Write failing contract tests**

Use this canonical fixture:

```js
{
  schema_version: "life-manager.goal-context.v1",
  tenant_id: "tenant-a",
  revision: 1,
  fact_refs: ["fact://tenant-a/income"],
  account_refs: ["account://tenant-a/calendar"],
  consent_refs: ["consent://tenant-a/calendar-read"],
  boundary_refs: ["boundary://tenant-a/no-owner-spend"]
}
```

Assert exact keys, 1–100 positive revision, deep freeze, canonical reference, and synthesis refs. Assert rejection of raw values, extra keys, duplicate refs, the wrong URI scheme, cross-tenant hosts, whitespace, credentials/secrets, and more than 100 refs per list. Empty lists remain valid because the standing policy is sufficient to synthesize a continuity goal without asking the person to invent one.

- [ ] **Step 2: Verify RED**

```bash
node --test apps/life-manager/lib/goal-context.test.js
```

Expected: FAIL because `goal-context.js` does not exist.

- [ ] **Step 3: Implement the smallest closed validator**

Keep all judgment out of this module. It validates shape, identity, revision, URI kind, tenant binding, uniqueness, and size only. It never reads raw source values.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: all context tests PASS.

- [ ] **Step 5: Commit and push**

```bash
git add apps/life-manager/lib/goal-context.js apps/life-manager/lib/goal-context.test.js
git commit -m "feat(life-manager): define tenant goal context"
git push origin HEAD
```

## Task 2: Persist versioned context and Goal Portfolios

**Files:**
- Create: `apps/life-manager/migrations/2026-09-22-lm-goal-context-portfolios.sql`
- Create: `apps/life-manager/lib/cloud-goal-store.js`
- Create: `apps/life-manager/lib/cloud-goal-store.test.js`

**Interfaces:**
- `createCloudGoalStore({ query })`
- `store.putContext(scope, context)` → `{ created, context }`
- `store.loadContext(scope)` → latest context or `null`
- `store.loadTenant(scope)` → authenticated tenant projection with goal synthesis refs and entitlement
- `store.loadGoalPortfolio(tenantId)` → latest validated portfolio or `null`
- `store.saveGoalPortfolio(portfolio)` → `{ created, portfolio }`
- `store.readProjection({ tenantId, jobId })` → safe opaque state or `null`

- [ ] **Step 1: Write failing store tests against an in-memory query double**

Cover:

1. A matching `{ uid, chatId }` stores revision 1 once; exact replay returns `created:false`.
2. Same tenant+revision with different bytes is a collision and does not overwrite.
3. Revision 2 may coexist and becomes the latest context.
4. Wrong chat or tenant writes/reads zero rows.
5. A validated portfolio stores once, survives a fresh store instance, and rejects cross-tenant or same-revision drift.
6. A durable queued RuntimeJob projects only `tenant_id`, `goal_ref`, `job_ref`, `status`, and nullable `receipt_ref`.
7. A later `general_agent_work` runtime receipt changes only safe status/receipt reference; goal prose, context refs, chat ID, receipt payload, and provider data never leave the projection.

- [ ] **Step 2: Verify RED**

```bash
node --test apps/life-manager/lib/cloud-goal-store.test.js
```

Expected: FAIL because the store is absent.

- [ ] **Step 3: Add the service-role-only migration**

Create versioned `public.lm_goal_contexts` and `public.lm_goal_portfolios` tables with composite `(tenant_id, revision)` keys, `lm_users(uid)` ownership, bounded JSON objects, canonical SHA-256 columns, timestamps, RLS enabled, and no `anon`/`authenticated` table grants. Add narrow security-definer put functions that:

- bind context writes to the existing `lm_users.uid + telegram_chat_id` pair;
- take a tenant advisory lock;
- insert once or return exact replay;
- reject a different hash at the same revision;
- require a matching context revision before storing a portfolio; and
- grant execution only to `service_role`.

Add an expression index for `(tenant_id, input_refs->>'goal_ref')` on the existing runtime job table only if absent; do not alter RuntimeJob semantics.

- [ ] **Step 4: Implement the store**

Use the injected query boundary. Revalidate every database JSON value with `validateGoalContext` or `validateGoalPortfolio`; never trust stored JSON. Compute canonical hashes in JS and compare RPC/readback results. `readProjection` uses tenant+job identity and an exact `goal-portfolio://` reference; it never calls `readCommonReceipt`, because CC02 jobs have `effect_class=none` and are not external provider receipts.

- [ ] **Step 5: Verify GREEN and neighboring contracts**

```bash
node --test \
  apps/life-manager/lib/goal-context.test.js \
  apps/life-manager/lib/cloud-goal-store.test.js \
  apps/life-manager/lib/goal-portfolio.test.js \
  apps/life-manager/lib/runtime-job-store.test.js
```

Expected: all tests PASS.

- [ ] **Step 6: Commit and push**

```bash
git add \
  apps/life-manager/migrations/2026-09-22-lm-goal-context-portfolios.sql \
  apps/life-manager/lib/cloud-goal-store.js \
  apps/life-manager/lib/cloud-goal-store.test.js
git commit -m "feat(life-manager): persist cloud goal state"
git push origin HEAD
```

## Task 3: Close the authenticated non-effectful vertical slice

**Files:**
- Create: `apps/life-manager/lib/cloud-goal-slice.js`
- Create: `apps/life-manager/lib/cloud-goal-slice.test.js`

**Interfaces:**
- `runCloudGoalSlice(input, dependencies)`
- Input: `{ session, nowMs, context? }`; a `goal` field is always rejected.
- Dependencies: `resolveSession`, `store`, `generateGoalPortfolio`, `enqueueJob`.
- Output exact keys: `{ created, tenant_id, goal_ref, job_ref, status, receipt_ref }`.

- [ ] **Step 1: Write failing end-to-end service tests**

Use the real goal context/portfolio/ingress modules with memory stores at external boundaries. Assert:

1. A valid existing Panel session plus first-use context generates once, persists context+portfolio, and enqueues one effect-free job.
2. A second call may omit context, loads durable state, calls the model zero additional times, returns `created:false`, and keeps the same goal/job identity.
3. Constructing a fresh service/store instance over the same database still returns the saved state.
4. Missing/invalid session, session/tenant mismatch, unentitled tenant, malformed context, explicit `input.goal`, and cross-tenant projection perform zero model/save/enqueue work.
5. Results and receipts contain no raw goal statement, fact/account/consent/boundary refs, chat ID, credential, or provider payload.
6. No dependency exposes or calls a provider adapter.

- [ ] **Step 2: Verify RED**

```bash
node --test apps/life-manager/lib/cloud-goal-slice.test.js
```

Expected: FAIL because the slice does not exist.

- [ ] **Step 3: Implement the orchestration**

Order is security-significant:

1. Reject `input.goal` and malformed observation time.
2. Resolve the existing Panel session; derive tenant scope only from its `uid/chatId`.
3. Load context. If absent, require and store the validated one-time context; if present, an exact supplied replay is allowed and drift at the same revision is rejected.
4. Adapt `store.loadTenant(scope)`, portfolio load/save, model generation, and RuntimeJob enqueue into `enqueueHostedGoal`.
5. Read the persisted projection by the returned tenant/job identity and return only the exact public keys.

Do not add an HTTP endpoint; that is CC03.

- [ ] **Step 4: Verify GREEN and the entire goal path**

```bash
node --test \
  apps/life-manager/lib/goal-policy.test.js \
  apps/life-manager/lib/goal-context.test.js \
  apps/life-manager/lib/goal-portfolio.test.js \
  apps/life-manager/lib/goal-work-item.test.js \
  apps/life-manager/lib/general-agent-work-adapter.test.js \
  apps/life-manager/lib/hosted-goal-ingress.test.js \
  apps/life-manager/lib/cloud-goal-store.test.js \
  apps/life-manager/lib/cloud-goal-slice.test.js
```

Expected: all tests PASS.

- [ ] **Step 5: Commit and push**

```bash
git add apps/life-manager/lib/cloud-goal-slice.js apps/life-manager/lib/cloud-goal-slice.test.js
git commit -m "feat(life-manager): add authenticated cloud goal slice"
git push origin HEAD
```

## Task 4: Register the CC02 continuous gate

**Files:**
- Modify: `apps/life-manager/package.json`

- [ ] **Step 1: Verify the command is absent**

```bash
cd apps/life-manager
npm run test:cloud-goal
```

Expected: FAIL with missing script.

- [ ] **Step 2: Add the behavior-only command**

Add:

```json
"test:cloud-goal": "node --test lib/goal-policy.test.js lib/goal-context.test.js lib/goal-portfolio.test.js lib/goal-work-item.test.js lib/general-agent-work-adapter.test.js lib/hosted-goal-ingress.test.js lib/cloud-goal-store.test.js lib/cloud-goal-slice.test.js"
```

Append `npm run test:cloud-goal` to `test:runtime-job`. Do not add source-text or copy grep tests.

- [ ] **Step 3: Verify focused and full Life Manager suites**

```bash
cd apps/life-manager
npm run test:cloud-goal
npm run test:runtime-job
npm test
```

Expected: all commands PASS.

- [ ] **Step 4: Commit and push**

```bash
git add apps/life-manager/package.json
git commit -m "test(life-manager): gate cloud goal persistence"
git push origin HEAD
```

## Task 5: Accept CC02 and advance the spec cursor

**Files:**
- Modify: `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md`

- [ ] **Step 1: Run the full CC02 acceptance**

```bash
cd apps/life-manager
npm run test:cloud-goal
cd ../..
./bin/lm-loop-contract
git diff --check
```

- [ ] **Step 2: Recheck the protected boundary**

```bash
if git diff origin/main...HEAD --name-only \
  | rg -q '(^|/)(paid_direct|paid_admission|paid_thread_state)\.py$|test_paid_remote_wait\.py$|^config/loop-registry\.json$|^apps/life-manager/config/product-loop-catalog\.json$'; then
  exit 1
fi
```

Expected: no protected path.

- [ ] **Step 3: Update measured evidence only**

Mark CC02 `[x]`, record exact pushed commits/test counts, and advance the cursor to CC03. State explicitly:

```text
CC02 proves an existing authenticated tenant can persist reference-only context and a validated
Goal Portfolio, enqueue one replay-safe non-effectful job, and read a tenant-scoped safe projection.
It does not claim a public phone/web endpoint, closed-client continuity, provider effects, copied
credentials, production migration/application, or Paid fulfillment. Current cursor: CC03.
```

- [ ] **Step 4: Commit, push, and report**

```bash
git add docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md
git commit -m "docs: close CC02 durable cloud goal gate"
git push origin HEAD
```

Send one deduplicated Telegram milestone beginning `Codex:::` with branch, commit, exact test/contract results, Paid boundary result, and `CC03` as the next cursor.
