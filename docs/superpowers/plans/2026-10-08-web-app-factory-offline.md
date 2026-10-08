# Web App Factory offline implementation plan

> Execute inline with superpowers:executing-plans. User preapproved this scoped implementation; no additional design approval is needed.

**Goal:** Give the existing product owner a truthful, zero-spend local factory report for PDF Insight without effects or session collisions.
**Architecture:** Pure evaluator, shared source/financial validators, JSON stdin CLI and synthetic fixture. No dependency installation.
**Stack:** Node built-ins/CommonJS, node:test.
**Spec:** docs/superpowers/designs/2026-10-08-web-app-factory-offline.md

## Global Constraints

- Own only new `web-app-factory*` files, `examples/web-app-factory/` and the two design/plan documents.
- No WebTravel, active-session edits, shared registry/SSOT changes, paid APIs, posting, deploy or production migrations.
- Reuse canonical worktree lease; observations are not atomic execution authority.
- No private PDF source or data in public commits. Actual model/effort unexposed; no routing claim.

## Review Focus

Inspect fail-open evidence gates: unknown revenue, cross-product/currency/period evidence, future timestamps, stale QA, incomplete account inventory, case-insensitive parent/child path overlap, expired foreign ownership, unsafe CLI fields or error echoes, and shared-validator side effects. Check that an all-green fixture cannot enable external effects or turn offline QA into production success.

### Task 1: Evidence and ownership evaluator

Files: new `apps/life-manager/lib/web-app-factory.js` and `.test.js`.
Interfaces: `evaluateWebAppFactory(input, {now})` returns schema, source, ownership, demand, QA, claims, distribution, metrics, contribution, next_task, lifecycle handoff; consumes the existing imported-source and FinancialRecord validators.
1. Write node:test cases first: missing evidence stays unknown; verified zero distinct; net loss; incomplete/cross-product/time/period/currency reports rejected; source/lease/file/resource conflicts fence; offline vs provider QA; claim proof; paid or unowned channels; budget and unsafe input rejected; existing FinancialRecord projection.
2. Run `node --test apps/life-manager/lib/web-app-factory.test.js`. Expected: RED, module missing.
3. Implement smallest evaluator, strict structured allowlists and no mutation/effect surface.
4. Run same command. Expected: all tests PASS. Commit owned files only.

### Task 2: Local CLI and operator boundary

Files: new `apps/life-manager/scripts/web-app-factory-plan.js` and `.test.js`; new `apps/life-manager/examples/web-app-factory/{README.md,example.json}`.
Interfaces: reads only bounded JSON stdin and optional `--now ISO`; invokes Task 1; emits one JSON report. Never reads env secrets, files named by input, spawns tools, calls network or writes state.
1. Write CLI tests: valid input yields setup/blocked report; malformed/oversize input fails without echo; no files change; paid budget fails; deterministic clock.
2. Run `node --test apps/life-manager/scripts/web-app-factory-plan.test.js`. Expected: RED, entrypoint missing.
3. Implement CLI and synthetic example. Write usage and private PDF follow-up boundary.
4. Run both test files plus existing `mobile-product-registry.test.js` and `financial-record-contract.test.js`. Expected: PASS. Commit.

### Task 3: Review and handoff

1. Fresh independent read-only review using the skill reviewer, with no app or production operations.
2. Address Important/Critical findings with RED→GREEN regression evidence, one pass.
3. Run focused suite, source boundary, `git diff --check` and CLI synthetic sample. Expected: all PASS; production/readback/revenue unknown.
4. Commit final evidence and preserve worktree for review. No publication or remote write required for this local phase. Report exact commit, base, ownership, checks and unresolved private source ownership.

## Local verification record — 2026-10-08

- Fork point: `origin/main` at `f9d94048ba0522bad881de2a1266f92011610dec`; canonical origin `https://github.com/Daisuke134/life-manager.git`.
- Exclusive development worktree/lease owner: `codex-web-factory-offline-1008`; own only the new files in this plan. This does not claim ownership of the separate PDF application.
- Skills read: installed Superpowers using-superpowers, brainstorming, writing-plans, using-git-worktrees, test-driven-development plus writing-good-tests reference, executing-plans, verification-before-completion, requesting-code-review and finishing-a-development-branch; Astra orchestration and repository loop-development. User authorized inline implementation without another routine approval. No model-based implementation worker was started.
- RED: missing evaluator and CLI failed first. GREEN: evaluator 26 tests, complete focused suite 34 tests. Independent read-only review found three Important issues: GitHub repository aliases, currency-less unit economics and duplicate demand receipts. New regression tests reproduced all three incorrect readiness results (26 pass/3 fail); fixes produced **37 pass/0 fail** across evaluator, CLI, existing imported-product registry and FinancialRecord contract.
- Independent reviewer dispatch selection: `gpt-6.1-sol/high`; this is dispatch metadata, not an actual runtime model readback. Executor runtime model/reasoning not exposed by the checked environment. No claim of Astra runtime routing or cost receipt.
- `git diff --check` and `scripts/verify-source-boundary.sh` passed. The synthetic CLI input emits `resolve_ownership`, `external_effects: false`, unknown metrics and no runtime registration.
- No private source/history, real provider data, secrets, customer data, runtime state or app credentials are in this branch. PDF-specific operator input/report live outside Git. No dependency installed; no paid/provider API invoked by implementation/tests.
- No private PDF patch/security migration applied or claimed. No scheduler, marketing submission, deployment, publication, remote push, PR or merge. Worktree is retained for integration owner review.

### Decisions and limits

1. Private PDF fixes stay in a private owner lane until exclusive source ownership and licensing are established. Cost: those product fixes are still pending.
2. Verification covers the complete new module suite and both directly reused contracts; the service's provider-dependent whole-repository suite was not run. Cost: unrelated integration failures remain unobserved.
3. Actual receipt authenticity, active-session/lease observation, private source rights, production QA/revenue and release effects are outside this offline evaluator. Cost: a caller supplying fabricated evidence could mislabel readiness; the report therefore grants no execution authority and requires atomic owner/admission checks before any later execution.
4. Preserve the local branch and worktree without publication/integration during this expressly offline phase. Cost: production integration waits for the orchestrator.

No deferred Minor review findings. The module is an offline factory slice, not proof of a functioning autonomous revenue loop.
