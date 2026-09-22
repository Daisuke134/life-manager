# Life Manager CC03 Phone/Web Continuity Implementation Plan

> **For implementers:** Follow `superpowers:executing-plans`, `superpowers:test-driven-development`, and
> the repository `skills/loop-development/SKILL.md`. Run each RED test before its implementation. Keep
> `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md` current after every
> verified milestone.

**Goal:** Expose the CC02 durable Goal slice through the existing authenticated phone/web Panel, prove
that the same cloud work survives a closed client, and add deterministic source-backed
`lm-loop status --explain` output.

**Architecture:** Reuse the existing Panel session as the only tenant authority and the existing runtime
PostgreSQL connection as the durable state/job authority. Add a strict Gemini JSON adapter behind the
existing Goal Portfolio validator, a small start/read service with no caller-authored goal, one Panel API
endpoint, and one automatically loaded Panel section. Extend the read-only CLI only when `--explain` is
present; default status output remains byte-shape compatible.

**Boundaries:** Do not edit Paid fulfillment code/tests/config/state, `config/loop-registry.json`,
`apps/life-manager/config/product-loop-catalog.json`, or any provider session. Do not apply migrations,
restart loops, publish a release, or claim production availability from this branch.

---

## Task 1: Strict production Goal model adapter

**Files:**

- Create: `apps/life-manager/lib/cloud-goal-generator.js`
- Create: `apps/life-manager/lib/cloud-goal-generator.test.js`
- Modify: `apps/life-manager/package.json`

1. Write failing tests for missing API key, transport failure, non-2xx response, invalid JSON, unknown
   fields, caller/tenant data leakage, unauthorized evidence refs, and one valid strict response.
2. Run the focused test and preserve the RED result in the progress ledger.
3. Implement a single bounded `gemini-2.5-flash:generateContent` call with a 20-second timeout,
   `temperature: 0`, `responseMimeType: application/json`, and a response schema matching only the
   candidate keys accepted by `goal-portfolio.js`.
4. Treat all prompt inputs as references and policy, not executable instructions. Return only
   `{goals:[...]}`; let `synthesizeGoalPortfolio` remain the final authority for tenant/revision/origin and
   authorized-reference validation.
5. Re-run the focused test and `npm run test:goal-policy`.
6. Commit and push before Task 2.

## Task 2: Durable start/read service and closed-client recovery

**Files:**

- Modify: `apps/life-manager/lib/cloud-goal-slice.js`
- Modify: `apps/life-manager/lib/cloud-goal-slice.test.js`
- Modify if required: `apps/life-manager/lib/cloud-goal-store.js`
- Modify if required: `apps/life-manager/lib/cloud-goal-store.test.js`

1. Write failing tests for a read before start, automatic revision-1 empty reference context, first start,
   replay, fresh service/store read, receipt projection, wrong chat/session isolation, and rejection of every
   caller field including `goal`.
2. Add a server-owned initial context builder. It accepts only the resolved tenant ID and creates
   `life-manager.goal-context.v1` revision 1 with four empty reference arrays; J4 is injected by
   `goalSynthesisRefs` and is never caller-controlled.
3. Add a read path that resolves the session, verifies context through the chat-bound store read, loads the
   persisted portfolio, derives the deterministic Goal job ID, and reads the safe projection. It returns the
   exact six-key projection with `created:false`; no context returns exact `status:not_started` and null refs.
4. Keep start success after context, portfolio, and job are durable. Replay returns the same job and does not
   call the model again. Storage collision remains fail-closed; it is not guessed to be a replay.
5. Re-run `npm run test:cloud-goal`.
6. Commit and push before Task 3.

## Task 3: Authenticated Panel Goal API

**Files:**

- Modify: `apps/life-manager/lib/panel-api.js`
- Modify: `apps/life-manager/lib/panel-api.test.js`

1. Write failing HTTP tests for:
   - authenticated `GET /api/panel/goals` current/not-started projection;
   - authenticated `POST /api/panel/goals` with exactly `{}`;
   - JSON, exact body, Origin, and CSRF rejection;
   - unauthenticated rejection;
   - ignored/rejected tenant and job query overrides;
   - model/store failure returning no false success.
2. Add `goals` as one explicit endpoint. GET calls the injected read service; POST calls the injected start
   service. The already resolved Panel scope remains authoritative; endpoint code accepts no tenant, job,
   goal, facts, or evidence from the request.
3. Require an idempotency-shaped header for consistency, but rely on the durable deterministic context,
   portfolio, and job identities rather than a browser receipt for replay safety. This avoids a lost HTTP
   response leaving an otherwise completed Goal permanently hidden behind a pending command receipt.
4. Return only the safe six-key projection and stable error codes.
5. Re-run the focused Panel API tests.
6. Commit and push before Task 4.

## Task 4: Phone-first Panel section with automatic start

**Files:**

- Modify: `apps/life-manager/lib/panel-ui.js`
- Modify: `apps/life-manager/lib/panel-ui.test.js`

1. Write failing rendering tests that require a non-guest Goal section and forbid goal/question/input/local
   storage strings or caller-supplied Goal payloads.
2. Add a compact Goal Portfolio status section to the responsive Panel. It renders only status plus opaque
   goal/job/receipt refs.
3. On initial GET `not_started`, automatically POST `{}` with same-origin credentials, Origin-derived browser
   behavior, CSRF, and a fresh idempotency header, then render the returned durable projection. Do not add a
   start button or ask for a goal.
4. A POST response failure falls back to one GET read before showing unavailable, so a lost response after
   durable enqueue is recoverable.
5. Guest/public Money Printer mode does not start tenant work.
6. Re-run the focused Panel UI tests.
7. Commit and push before Task 5.

## Task 5: Production server wiring without a second runtime

**Files:**

- Modify: `apps/life-manager/server.js`
- Modify/Create focused server option tests under `apps/life-manager/lib/`

1. Write a failing wiring test showing `/api/panel/goals` receives a service built from the existing runtime
   PostgreSQL pool, existing Panel session resolver, strict generator, and existing `enqueueJob`.
2. Create one lazy Goal service beside the existing runtime store. Reuse
   `LM_RUNTIME_DATABASE_URL || LM_FEEDBACK_DATABASE_URL`; do not create a second scheduler or database.
3. Inject the service only for the Goal endpoint. Keep module initialization lazy so unrelated Panel paths
   do not require the runtime database.
4. Re-run the focused server and API tests.
5. Commit and push before Task 6.

## Task 6: Deterministic source-backed `status --explain`

**Files:**

- Modify: `runtime/loop/lm_loop.py`
- Modify: `runtime/loop/tests/test_lm_loop_readonly.py`

1. Write failing tests that assert default `status_rows` has no explanation field and `explain=True` adds an
   exact explanation envelope for:
   - disabled;
   - unloaded;
   - no validated report event;
   - installed/event release mismatch;
   - live admission `effect_unknown` fence;
   - exact runtime blocker/failure;
   - unverified effect;
   - healthy current release.
2. The explanation envelope contains only `reason_code`, `next_action`, `event_id`, `run_id`, `phase`, and
   `evidence_refs`. Event identity and evidence come only from `_last_event`, which already validates the
   runtime event schema. Missing evidence remains an empty list with `insufficient_evidence`.
3. Add argument parsing for `lm-loop status [<loop|all>] [--explain]`. Reject duplicates, unknown flags,
   multiple targets, and `--explain` on mutation/watch commands.
4. Preserve default status output and single-loop bounded collection behavior.
5. Run the focused Python tests and wrapper smoke from outside the repository cwd.
6. Commit and push before Task 7.

## Task 7: PostgreSQL continuity, replay, and isolation proof

**Files:**

- Modify: `apps/life-manager/test/postgres/cloud-goal-postgres.integration.sh`
- Modify: `apps/life-manager/package.json`

1. Extend the disposable PostgreSQL test to apply runtime plus Goal migrations, create two tenant/session
   identities, start one Goal, destroy the initiating service/client fixture, and read the same job from a
   fresh service/store fixture.
2. Assert exact one context, portfolio, and runtime job after replay; assert wrong tenant/chat reads zero
   rows and no raw facts, chats, credentials, or provider payload enter the projection.
3. Add a focused package script that continuously runs model, cloud slice, API/UI, server wiring, and CLI
   explain tests without requiring production credentials.
4. Run the focused gate and PostgreSQL integration.
5. Commit and push before Task 8.

## Task 8: Final verification, spec evidence, and handoff

**Files:**

- Modify: `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md`
- Update ignored ledger: `.superpowers/sdd/2026-09-22-life-manager-cloud-goal-slice/progress.md`

1. Run `npm run test:cloud-goal`, the CC03 focused gate, `npm run test:runtime-job`, and the full
   `npm test` in `apps/life-manager`.
2. Run the focused Python loop tests and `./bin/lm-loop-contract`.
3. Run the protected boundary diff check proving no Paid source/tests/config/state, Paid registry entries,
   product-loop catalog, or provider sessions changed.
4. Run a fresh-diff review against the CC03 contract; repair any finding and repeat affected verification.
5. Update CC03 in the canonical spec with exact commit SHAs and measured results. State explicitly that no
   production migration, main merge, public deployment, or provider effect is claimed.
6. Commit and push all evidence. Send one deduplicated `Codex:::` Telegram milestone with the next cursor
   (CC04). Do not create/merge a PR until the broader spec acceptance permits it.
