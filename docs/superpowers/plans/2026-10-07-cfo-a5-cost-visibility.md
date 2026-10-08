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
- Preserve small USD values to at least 8 fractional digits so positive API-price estimates are never rendered as `$0.00`.
- Keep per-event `runtime_trace` fields from the existing `lm_api_cost.meta` rows available for loop/owner attribution; missing trace stays unknown/unattributed.
- Group by loop/owner and preserve trace coverage counts; the latest trace is only an anchor and never represents every event in a mixed-release group.
- Never add a global hard cap, automatic spend cutoff, or silent feature stop.

## Working Order and Ownership

- The canonical CFO cursor is A5; its current global order is A5 → A6 → A8 → A9 → A10. A7 Moneytree and A3/A4 Cloud/geocoding savings are deferred by Dais and are not prerequisites for this work.
- This plan owns branch `feat/cfo-a5-cost-visibility-20261007` and its existing dedicated worktree only. Source work does not apply production migrations or release branches directly.
- Tasks 1–4 deliver the initial cost summary. Tasks 5–7 add loop attribution, reduce CFO FIFO wait, then update and validate the existing PR; none changes the wider SSOT order or adds a spend cap.

## Review Focus

- A missing or unavailable RPC is shown as unknown/unavailable, never an empty verified-zero period.
- An estimate of zero is valid only when its event carries explicit estimated/not-applicable status; null, missing, malformed, or unavailable estimates remain unknown.
- A positive estimate below one cent remains visibly nonzero at the panel boundary.
- Only `billing_status=settled` rows contribute settled actual cost; not-applicable cache hits are not unknown expense.
- Quantities with different units (`request`, `tokens`, `grounded_prompt`, `seconds_proxy`) are never summed into one displayed total.
- Tenant and period filters apply inside SQL, not only in UI projection.
- Provider/SKU/operation labels are bounded and safe; no raw event metadata reaches the browser.
- Partial traces remain explicitly partial. Preserve validated `loop_id`/`owner_id` attribution when present; map missing or invalid loop/owner identity to `unattributed`. Do not present partial or unlinked data as fully verified or zero-cost.
- A `latest_trace` anchor is not proof that every event in its group ran under that release; render distinct release/run/occurrence counts separately.

---

### Task 1: Add bounded period-summary RPC

**Files:**
- Create: `apps/life-manager/migrations/2026-10-07-lm-usage-cost-period-summary.sql`
- Modify: `apps/life-manager/lib/usage-summary-migration.test.js`

**Interfaces:**
- Produces service-role-only RPC `lm_usage_cost_period_summary(p_period_start timestamptz, p_period_end timestamptz, p_tenant_id text)`.
- Returns provider/SKU/operation/unit groups, event/request and cache counts, provider units, nullable estimated and settled USD totals, unknown-estimate and unknown-actual event counts, and not-applicable count.
- `sum(est_usd)` remains NULL when no event has a known estimate; actual is summed only for valid settled rows.

  - [x] Write migration-contract tests for tenant/period predicates, provider/SKU/operation/unit dimensions, estimate/actual/unknown fields, and service-role-only grants.
  - [x] Run the migration tests and confirm they fail on the missing period-summary RPC.
  - [x] Add the additive RPC without changing or dropping the existing `lm_usage_cost_summary` function.
  - [x] Run migration-contract tests and verify the new SQL remains tenant/period bounded, unit-separated, and unknown-safe.

### Task 2: Read and project daily/month-to-date summaries

**Files:**
- Modify: `apps/life-manager/lib/panel-api.js`
- Modify: `apps/life-manager/lib/panel-presentation.js`
- Test: `apps/life-manager/lib/panel-api.test.js`

**Interfaces:**
- The authenticated `ledger(uid, opts)` calls the summary RPC for today and month-to-date using Asia/Tokyo bounds and `p_tenant_id=uid`.
- The panel DTO has separate `daily` and `monthly` period records, each with status, exact period bounds, sanitized provider/SKU/operation/unit groups, and explicit estimate/actual/unknown counts.
- RPC failure returns an unavailable summary state while preserving the existing ledger; it never fabricates zero rows or a zero cost.

  - [x] Write API tests for tenant scoping, day/month boundaries, one summarized group, unavailable RPC, and actual-versus-estimate separation.
  - [x] Run the API test and confirm it fails because the ledger does not call the period-summary RPC.
  - [x] Implement the bounded calls and project only the allowlisted summary fields.
  - [x] In the same panel API contract test, verify presentation for unavailable, verified-empty, estimated, settled, and partial-unknown periods.
  - [x] Run the API contract tests; verify no raw event metadata is returned.

### Task 3: Render the existing Ledger summary

**Files:**
- Modify: `apps/life-manager/lib/panel-ui.js`
- Modify: `apps/life-manager/lib/panel-ui.test.js`

**Interfaces:**
- Extend the exact ledger payload validator for the new `api_cost` summary fields and existing estimate/actual status fields.
- Render separate `今日` and `今月` tables with provider/SKU/operation/unit, request/unit counts, at-least-8-decimal estimated and settled USD cost, `未確認` values, and coverage gaps.
- Show that the warning threshold is not configured pending A6; no threshold state stops travel or Calendar behavior.

  - [x] Add panel contract tests that projected fields pass validation, summaries appear in rendered output, and a positive sub-cent estimate stays visibly nonzero.
  - [x] Run the UI tests and confirm the old validator rejects status/summary fields.
  - [x] Update the exact-key validator and render both periods with unknown values visibly distinct from zero.
  - [x] Run UI tests and the relevant panel privacy harness.

### Task 4: Acceptance and handoff

  - [x] Run `node --test apps/life-manager/lib/usage-summary-migration.test.js apps/life-manager/lib/panel-api.test.js apps/life-manager/lib/panel-ui.test.js`.
  - [x] Run `git diff --check` and inspect the complete diff for tenant isolation, raw data, hard caps, and incorrect zero/settlement claims.
  - [x] Commit and push the initial cost-visibility source on the existing draft PR #6827; latest-main synchronization and additional trace/priority tasks remain in Tasks 5–7.

### Task 5: Attribute provider-cost groups and expose trace anchors

**Files:**
- Modify: `apps/life-manager/migrations/2026-10-07-lm-usage-cost-period-summary.sql`
- Modify: `apps/life-manager/lib/usage-summary-migration.test.js`
- Test: `apps/life-manager/lib/panel-api.test.js`
- Modify: `apps/life-manager/lib/panel-presentation.js`
- Modify: `apps/life-manager/lib/panel-ui.js`
- Test: `apps/life-manager/lib/panel-ui.test.js`

**Interfaces:**
- Extend each SQL group with `loop_id` and `owner_id` alongside the existing provider/SKU/operation/unit dimensions. Missing or invalid loop/owner identity projects as `unattributed`; partial status alone does not discard a validated loop/owner.
- Preserve each row's existing `meta.runtime_trace` identity. The grouped DTO returns `trace_status` (`linked`, `partial`, `unlinked`), linked/partial/unlinked event counts, distinct run/occurrence/release counts, and a nullable `latest_trace` object with `run_id`, `occurrence_id`, and `release_sha`. Grouping remains by loop/owner, not by each run, so totals stay usable. Render the three distinct counts beside, not as a substitute for, the latest trace anchor.
- `panel-api.js` already passes tenant-scoped RPC rows into the existing server projection; keep that pass-through unchanged and assert its tenant/period request arguments in tests.
- The panel renders loop/owner and the latest trace anchor without returning raw `meta` or provider payload. Estimate, settled actual, and unknown semantics remain unchanged.

- [x] Add `COST-03 period summary separates costs by runtime loop and trace` to the migration-contract tests; assert tenant/period filtering, unit separation, attribution groups, trace counts/latest anchor, and the explicit unattributed bucket.
- [x] Run the focused migration/API tests and confirm they fail because the RPC/DTO omits runtime attribution.
- [x] Extend the SQL RPC, API projection, and allowlisted panel DTO to project the trace fields above; reuse the existing usage-event producer, which already writes `runtime_trace`.
- [x] Add `ledger period projection attributes cost groups and exposes only safe latest trace` and `PANEL-A5: browser renders loop/owner grouping and newest trace`; prove partial status stays visible, missing identity maps to `unattributed`, validated loop/owner IDs remain accurate, and IDs are escaped/allowlisted.
- [x] Run migration/API/UI tests and the panel privacy evaluator; verify raw `meta` never reaches the browser.

### Task 6: Raise CFO's scheduling priority without reserving capacity

**Files:**
- Modify: `config/loop-registry.json`
- Test: `runtime/loop/tests/test_macos_loop_registry.py`
- Modify: `runtime/loop/tests/fixtures/macos-loop-jobs.json`

**Interfaces:**
- For `life-manager-cfo-hourly`, set `priority` to `revenue` while retaining `admission_class=borrow` and `resource_class=deterministic`.
- The change only moves CFO ahead of support-priority queue backlog; it does not reserve a revenue slot and does not fix a genuinely full `resource_capacity_busy` host.
- The existing byte-stable production render fixture must reflect this one intentional CFO priority change; no other rendered registry row changes.

- [x] Change `test_life_manager_cfo_hourly_declares_effect_rebind_contract` to expect revenue priority while retaining borrow/deterministic; run it and observe RED.
- [x] Change only the CFO registry priority, then update only its expected priority in the byte-stable rendered-job fixture; verify both the targeted contract and render-fixture tests pass.
- [x] Run the focused registry test and `./bin/lm-loop-contract`; do not add a hard cap or stop any provider feature.

### Task 7: Sync, review, and update the existing A5 PR

**Files:**
- Modify: `apps/life-manager/migrations/2026-10-07-lm-usage-cost-period-summary.sql`
- Modify: `apps/life-manager/lib/usage-summary-migration.test.js`
- Modify: `apps/life-manager/lib/panel-ui.js`
- Modify: `apps/life-manager/lib/panel-ui.test.js`
- Modify: `docs/manifests/oss-merge-1-sources.json`
- Modify: `docs/superpowers/plans/2026-10-07-cfo-a5-cost-visibility.md`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

- [x] Add regression tests for review findings; require explicit estimate status for zero and render distinct run/occurrence/release counts. Preserve validated partial loop/owner attribution; missing loop/owner remains `unattributed`.
- [x] Refresh the absorbed Capafy source inventory for merged main; run `node scripts/verify-oss-self-contained.mjs` and `node --test test/oss-self-contained.test.mjs`.
- [x] After merging latest main `1872befb`, recompute the OSS source inventory from the merged tree and rerun its verifier plus `node --test test/oss-self-contained.test.mjs`.
- [x] Merge latest main through `71a5f878` (including `55546755`, `68b03657`, and `b634a187`); recompute the OSS inventory from the merged tree and rerun verifier plus self-contained tests (12/12 PASS).
- [x] Run the complete A5 focused tests plus `npm run eval:panel-privacy`, the focused registry test, and `./bin/lm-loop-contract`.
- [x] Rerun the A5 focused tests (127/127), privacy evaluator, registry/loop contract, and the first full runtime suite against the merged head. The suite reached 791 tests; only the two `cut-loop-release` pressure tests failed because current commit `3f25077e` exists only locally.
- [ ] After pushing the branch, rerun the two release-pressure tests to satisfy their remote-SHA guard, then require the complete runtime suite to pass.
- [x] After merging latest main `71a5f878`, rerun A5 focused tests (127/127), privacy evaluator, registry fixture/loop contract, OSS verifier/tests, and `git diff --check`.
- [ ] After pushing the `71a5f878`-synced head, rerun the complete runtime suite and require all 791 tests to pass.
- [x] Run `git diff --check` against the merged branch; full branch review still requires a fresh read-only review on the pushed head.
- [x] Update the canonical SSOT's A5 cursor and production evidence from fresh readbacks; distinguish the older-release ENOSPC messages from the current release's in-progress apply and keep unrelated owner failures outside A5 scope.
- [x] Fetch/merge latest `origin/main` (`1872befb`); resolve the registry fixture from merged `config/loop-registry.json`, retaining CFO `priority=revenue` and main's eBook occurrence flag.
- [ ] Fetch/merge latest main `71a5f878` (and any newer tip) before pushing the existing `feat/cfo-a5-cost-visibility-20261007` branch and updating PR #6827; keep it draft until required checks and fresh source review pass.
- [x] On pushed head `be3e03a8b5`, rerun `python3 -m unittest discover -s runtime/loop/tests -p 'test_*.py'` and the loop-adapter registry test; all 791 tests pass after satisfying the remote-SHA guard.
- [ ] After pushing the `71a5f878`-synced branch, rerun the complete 791-test runtime suite; require all 791 to pass on the new remote head.
- [ ] After new-head required CI passes, obtain a fresh read-only whole-branch review, then mark PR #6827 ready and merge.
- [ ] Do not apply the database migration or manually run/restart the production CFO owner from this worktree; production migration/release/natural-report readback follows the canonical SSOT cursor.
