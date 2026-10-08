# A5 Task 1 Report

## Status

PASS. Added the service-role-only `lm_usage_cost_period_summary(p_period_start timestamptz, p_period_end timestamptz, p_tenant_id text)` RPC, grouped by provider, SKU, and operation. The query uses a required tenant and the half-open period `[p_period_start, p_period_end)`. Estimated USD remains `NULL` when no known estimate exists; settled USD sums only non-negative JSON numeric amounts with `billing_status = 'settled'`. Unknown estimate, unknown actual, and valid not-applicable events are reported separately. Existing COST-01 remains unchanged.

## Commits

- Implementation: `e39635e141` (`feat(life-manager): add bounded period cost summary`)

## Test result

- RED before SQL: `node --test lib/usage-summary-migration.test.js` exited 1; existing COST-01 passed and all 4 new COST-02 tests failed with the expected missing-migration assertion.
- GREEN after SQL: `node --test lib/usage-summary-migration.test.js` exited 0; 5 tests passed, 0 failed.
- `git diff --check` passed.

## Concerns

- The migration was not applied to a database, and no production database or deployment was touched. PostgreSQL execution is therefore not covered by this static migration-contract test.

## Fix round 1 — preserve provider unit

- Ruling: include `unit` in the returned and grouped dimensions because real producers emit request, token, grounded-prompt, and seconds-proxy quantities. Without it, `provider_units` can add unlike units. Cost if wrong: the dashboard would display semantically invalid usage totals.
- RED: the updated `COST-02 groups provider, SKU, operation, and unit...` contract test failed because the RPC result columns lacked `unit`.
- GREEN: `node --test apps/life-manager/lib/usage-summary-migration.test.js` — 5 passed, 0 failed.
- `git diff --check` passed. No PostgreSQL apply, provider call, or deployment occurred.
