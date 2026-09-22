# Life Manager CC04 Cloud Policy and Worker Boundary Implementation Plan

> **For implementers:** Follow `superpowers:executing-plans`,
> `superpowers:test-driven-development`, and `skills/loop-development/SKILL.md`. Preserve the exclusive
> Paid boundary. Commit and push each verified task before continuing.

**Goal:** Turn the CC03 non-effectful Goal job into one tenant-isolated Cloud execution path with a
canonical policy authority, signed short-lived grants, bounded tenant admission, and a credential
surrogate that never exposes raw secrets to workers.

**Architecture:** Reuse the existing runtime PostgreSQL queue, job leases, Goal job/adapter, and cloud
secret-provider abstraction. Add one exact execution policy and an HMAC-signed capability grant. Add one
narrow tenant-scoped claim RPC that permits only one active non-effectful job per tenant. Keep plaintext
inside a broker-owned provider callback and return only a validated secret-free result. Do not create a
second queue, scheduler, goal authority, credential store, or business recipe.

**Boundaries:** Do not edit Paid source/tests/config/state, Paid registry rows,
`apps/life-manager/config/product-loop-catalog.json`, provider sessions, browser state, or live runtime
state. Do not apply migrations, restart loops, deploy production, or claim a provider effect from this
branch.

---

## Task 1: Canonical Cloud execution policy

**Files:**

- Create: `apps/life-manager/config/cloud-execution-policy.json`
- Create: `apps/life-manager/lib/cloud-execution-policy.js`
- Create: `apps/life-manager/lib/cloud-execution-policy.test.js`
- Modify: `apps/life-manager/package.json`

1. Write failing tests for unknown fields, another authority, required user goals, effectful work,
   unsupported capabilities, raw credential values, undeclared/malformed secret references, duplicate
   entries, and overbroad claim/lease/grant limits.
2. Define one exact v1 policy subordinate to J4: `general-agent.work`, `effect_class=none`, max attempts 1,
   claim limit 1, a bounded 30–900 second lease, a shorter/equal grant TTL, and only
   `secret://gemini/api-key`.
3. Load, validate, canonicalize, digest, and deep-freeze the policy. Export no mutable policy object and no
   raw secret value.
4. Run the focused test and existing goal-policy tests.
5. Commit and push before Task 2.

## Task 2: Signed policy-bound capability grants

**Files:**

- Create: `apps/life-manager/lib/cloud-work-authority.js`
- Create: `apps/life-manager/lib/cloud-work-authority.test.js`

1. Write failing tests for a valid CC03 Goal job and for tampered signature/payload, expiry, future issue
   time, policy digest drift, foreign tenant/job/attempt/worker, unsupported capability/effect, malformed
   reference, and weak/missing signing key.
2. Issue a compact HMAC-SHA256 grant with exact version, policy digest, tenant/job/attempt/worker,
   capability/effect, authorized secret refs, issued-at, and expires-at fields.
3. Verify every field against an expected execution identity with timing-safe signature comparison. Never
   accept permission or time bounds from an unverified caller.
4. Ensure same inputs produce the same grant and no grant/log/error contains a raw secret.
5. Run focused policy/authority tests, then commit and push.

## Task 3: Durable tenant-scoped exact-one Cloud claim

**Files:**

- Create: `apps/life-manager/migrations/2026-09-22-lm-cloud-work-admission.sql`
- Modify: `apps/life-manager/lib/runtime-job-store.js`
- Modify: `apps/life-manager/lib/runtime-job-store.test.js`
- Create: `apps/life-manager/lib/cloud-worker-admission.js`
- Create: `apps/life-manager/lib/cloud-worker-admission.test.js`

1. Write failing unit tests requiring a new `claimCloudJob` store call to one RPC with exact worker,
   capability list, trusted tenant, and policy lease. Require at most one row and reject a foreign tenant,
   effectful/wrong capability job, invalid attempt, and caller attempts to override policy bounds.
2. Add a SECURITY DEFINER RPC that validates inputs, takes a tenant transaction advisory lock, reuses the
   existing queue row/lease fields, selects only queued or retryable expired `effect_class=none` work, and
   refuses a second non-expired running job for the tenant. Return at most one row.
3. Revoke direct execution from public/anon/authenticated and grant only service role when present.
4. Build a worker admission object with constructor-fixed tenant/worker/policy. Its public `claim()` accepts
   no tenant, capabilities, limit, lease, or goal override. It validates the row and issues the signed grant.
5. Run focused tests and the runtime-job suite, then commit and push.

## Task 4: Credential-surrogate broker

**Files:**

- Create: `apps/life-manager/lib/cloud-credential-broker.js`
- Create: `apps/life-manager/lib/cloud-credential-broker.test.js`

1. Write failing tests proving foreign/tampered/expired grants and mismatched tenant/job/attempt/worker/
   capability/reference/operation are rejected before health/get/provider calls.
2. Accept only an exact reference-only invocation. Verify the signed grant, Cloud vault health, and the one
   policy-declared credential reference before resolving it.
3. Pass plaintext only to a broker-owned provider callback. Validate an exact secret-free result envelope
   with bounded opaque evidence references; reject unknown fields, secret echo, or unbound identity.
4. Make provider, vault, console, grant, request, result, error, and serialized-object assertions explicit.
5. Run focused tests and commit/push.

## Task 5: One bounded non-effectful execution

**Files:**

- Create: `apps/life-manager/lib/cloud-general-agent-worker.js`
- Create: `apps/life-manager/lib/cloud-general-agent-worker.test.js`

1. Write failing tests for claim → grant → broker invocation → existing
   `general-agent-work` receipt → runtime completion, no work, broker failure, lease/identity mismatch,
   replay, and an independent sibling tenant.
2. Compose the existing Goal adapter rather than duplicating its job or receipt contract. The worker sees
   only the job, signed grant, secret reference, and broker result.
3. Complete the exact claimed attempt only after adapter verification. On failure, use the existing
   non-effectful bounded failure path; never guess completion.
4. Run focused tests plus CC03 cloud/runtime tests and commit/push.

## Task 6: PostgreSQL concurrency, isolation, and secret-containment proof

**Files:**

- Create: `apps/life-manager/test/postgres/cloud-worker-boundary.integration.sh`
- Modify: `apps/life-manager/package.json`

1. Start a disposable PostgreSQL cluster and apply runtime, Goal, and Cloud admission migrations.
2. Create two paid test tenants and enqueue two tenant-A Goal jobs plus one tenant-B Goal job. Race two
   tenant-A claims while claiming tenant B independently; assert exactly one active A claim and one B claim.
3. Run the bounded worker with a fake Cloud vault whose plaintext marker is known only to the broker callback.
   Complete one job and read the durable receipt from a fresh process.
4. Assert cross-tenant grant/claim/broker calls fail before vault access; client roles cannot execute the RPC
   or read Cloud state; database rows, output, and logs contain no plaintext marker.
5. Add `test:cc04` and `test:cloud-worker:postgres` scripts and run both twice where concurrency is involved.
6. Commit and push.

## Task 7: Final verification, evidence, and next cursor

**Files:**

- Modify: `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md`
- Update ignored ledger: `.superpowers/sdd/2026-09-22-life-manager-cloud-goal-slice/progress.md`

1. Run focused policy/authority/admission/broker/worker tests, `test:cc04`, the PostgreSQL gate,
   `test:cc03`, `test:runtime-job`, and full `apps/life-manager` tests.
2. Run `./bin/lm-loop-contract`, `git diff --check`, a fresh-diff review, and the exact Paid/config protected
   boundary check.
3. Repair every finding, repeat affected verification, and record exact commit SHAs and measured results.
4. Mark CC04 complete only if all acceptance clauses pass. State explicitly that main merge, production
   migration/deployment, provider mutation, Local credential/session copy, and Paid work are not claimed.
5. Commit/push evidence and send one deduplicated `Codex:::` Telegram milestone. Move the sole cursor to
   CC05; do not create or merge a PR until the broader canonical acceptance permits it.
