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
