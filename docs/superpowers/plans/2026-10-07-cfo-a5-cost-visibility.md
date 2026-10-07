# CFO A5 Provider Cost Visibility Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Show tenant-scoped daily and month-to-date provider usage, estimates, settled actuals, and unknown coverage in the existing Life Manager Ledger panel.

**Architecture:** Reuse the append-only `lm_api_cost` ledger and existing authenticated panel. Add one bounded, service-role-only RPC for cost-period aggregates, project its result into a safe panel DTO, and render daily/month-to-date summaries beside the existing ledger. No new CLI or reporting loop is introduced.

**Tech Stack:** PostgreSQL migration, existing Node.js panel API/presentation, existing browser panel, `node:test`.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` (A5); `docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md` (Observability and Daily CFO Report contracts).

## Global Constraints

- A5 shows provider daily/monthly usage, estimate, actual, and unknown; warning thresholds are calibrated only after A6 bill reconciliation.
- Do not add global hard caps, automatic cutoffs, or silent feature stops; do not treat missing values as zero.
- Keep actual settlement separate from API-price estimates and preserve source coverage/unknown counts.
- Scope every summary query to the authenticated tenant and a bounded period; expose no raw prompt, address, coordinate, credential, or provider error payload.
- Reuse the existing panel and append-only ledger; do not add a new CLI, scheduler, loop, or state store.
- Use Asia/Tokyo day and month-to-date boundaries; state explicitly when a summary source is unavailable.

## Working Order and Ownership

- The canonical SSOT cursor remains `A4.1`; its edit lease belongs to a separate worktree and is not changed by this plan.
- A4.2 source/tests are complete but its PR is held by unrelated repository-wide checks. Following the user's instruction to continue past blocked items, A5 source work proceeds independently; this does not claim A4.3 production acceptance or change the canonical cursor/order.
- Keep A4.2 branch/worktree and the CFO SSOT owner's staged changes untouched. This plan owns branch `feat/cfo-a5-cost-visibility-20261007` and its dedicated worktree only.

## Review Focus

- A missing or unavailable RPC is shown as unknown/unavailable, never an empty verified-zero period.
- An estimate of zero is valid only when its event carries explicit estimated/not-applicable status; null, missing, malformed, or unavailable estimates remain unknown.
- Only `billing_status=settled` rows contribute settled actual cost; not-applicable cache hits are not unknown expense.
- Tenant and period filters apply inside SQL, not only in UI projection.
- Provider/SKU/operation labels are bounded and safe; no raw event metadata reaches the browser.

---

### Task 1: Add bounded period-summary RPC

**Files:**
- Create: `apps/life-manager/migrations/2026-10-07-lm-usage-cost-period-summary.sql`
- Modify: `apps/life-manager/lib/usage-summary-migration.test.js`

**Interfaces:**
- Produces service-role-only RPC `lm_usage_cost_period_summary(p_period_start timestamptz, p_period_end timestamptz, p_tenant_id text)`.
- Returns provider/SKU/operation group, event/request and cache counts, provider units, nullable estimated and settled USD totals, unknown-estimate and unknown-actual event counts, and not-applicable count.
- `sum(est_usd)` remains NULL when no event has a known estimate; actual is summed only for valid settled rows.

- [ ] Write migration-contract tests for tenant/period predicates, provider/SKU/operation dimensions, estimate/actual/unknown fields, and service-role-only grants.
- [ ] Run the migration tests and confirm they fail on the missing period-summary RPC.
- [ ] Add the additive RPC without changing or dropping the existing `lm_usage_cost_summary` function.
- [ ] Run migration-contract tests and verify the new SQL remains tenant/period bounded and unknown-safe.

### Task 2: Read and project daily/month-to-date summaries

**Files:**
- Modify: `apps/life-manager/lib/panel-api.js`
- Modify: `apps/life-manager/lib/panel-presentation.js`
- Test: `apps/life-manager/lib/panel-api.test.js`
- Create: `apps/life-manager/lib/panel-presentation.test.js`

**Interfaces:**
- The authenticated `ledger(uid, opts)` calls the summary RPC for today and month-to-date using Asia/Tokyo bounds and `p_tenant_id=uid`.
- The panel DTO has separate `daily` and `monthly` period records, each with status, exact period bounds, sanitized provider/SKU/operation groups, and explicit estimate/actual/unknown counts.
- RPC failure returns an unavailable summary state while preserving the existing ledger; it never fabricates zero rows or a zero cost.

- [ ] Write API tests for tenant scoping, day/month boundaries, one summarized group, unavailable RPC, and actual-versus-estimate separation.
- [ ] Run the API test and confirm it fails because the ledger does not call the period-summary RPC.
- [ ] Implement the bounded calls and project only the allowlisted summary fields.
- [ ] Add presentation tests for unavailable, verified-empty, estimated, settled, and partial-unknown periods.
- [ ] Run API and presentation tests; verify no raw event metadata is returned.

### Task 3: Render the existing Ledger summary

**Files:**
- Modify: `apps/life-manager/lib/panel-ui.js`
- Modify: `apps/life-manager/lib/panel-ui.test.js`

**Interfaces:**
- Extend the exact ledger payload validator for the new `api_cost` summary fields and existing estimate/actual status fields.
- Render separate `今日` and `今月` tables with provider/SKU, request/unit counts, estimated cost, settled actual or `未確認`, and coverage gaps.
- Show that the warning threshold is not configured pending A6; no threshold state stops travel or Calendar behavior.

- [ ] Add panel contract tests that the real projected ledger fields pass validation and appear in rendered output.
- [ ] Run the UI tests and confirm the old validator rejects status/summary fields.
- [ ] Update the exact-key validator and render both periods with unknown values visibly distinct from zero.
- [ ] Run UI tests and the relevant panel privacy harness.

### Task 4: Acceptance and handoff

- [ ] Run `node --test apps/life-manager/lib/usage-summary-migration.test.js apps/life-manager/lib/panel-api.test.js apps/life-manager/lib/panel-presentation.test.js apps/life-manager/lib/panel-ui.test.js`.
- [ ] Run `git diff --check` and inspect the complete diff for tenant isolation, raw data, hard caps, and incorrect zero/settlement claims.
- [ ] Commit and push this worktree's branch. Keep the PR draft until canonical cursor/order and A4.2/A4.3 promotion dependencies are resolved.
