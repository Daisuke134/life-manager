# CFO A4.1 Free Geocoding Evidence Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task-by-task. The unified CFO spec remains the only TODO/order/status source.

**Goal:** Record reproducible, offline evidence for whether GSI AddressSearch and OpenPOI are safe free candidates before any provider-routing change.

**Architecture:** Store small, date-stamped public response snapshots with source/license metadata and exercise their acceptance boundaries with Node's built-in test runner. This task does not modify runtime geocoding, route UX, production services, or the current CFO TODO order.

**Tech Stack:** Node.js built-in `node:test`, `node:assert/strict`, JSON fixtures.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`, CFO cursor A4.1.

## Global Constraints

- The current order is `A4.1 → A4.2 → A4.3 → A5 → A6 → A3 conditional → A7 → A8 → A9 → A10`.
- Do not call Life Manager production routes, restart/deploy the service, or issue Google billable requests.
- Do not auto-accept ambiguous, unmatched, coarse, or timed-out candidates.
- Preserve OpenPOI result `licenses` and `attributions`; record GSI PDL1.0 attribution.
- Treat missing GSI rate/SLA terms as unknown, never as unlimited.
- Use only public sample place names in fixtures; do not send or persist actual calendar event data in this task. OpenPOI's privacy policy says request content and access-source information are logged.

## Review Focus

- A full GSI address query can return a coarser title that drops the house number; the fixture test must retain that mismatch.
- OpenPOI can return repeated exact names with materially different coordinates; the fixture test must preserve both and classify them ambiguous.
- Broad OpenPOI search can return a result from another locality; the fixture test must not interpret the first result as a geocode.
- Zero-result and timeout cases must contain no accepted coordinates and remain fallback cases.
- Every captured OpenPOI result must keep its complete `licenses` and `attributions` arrays; its request logging must be considered before runtime use.
- Fixture provenance must record source freshness: OpenPOI currently publishes a fixed Overture release and weekly JFF rebuilds, not a live freshness guarantee.

---

### Task 1: Capture free-provider candidate evidence

**Files:**
- Create: `apps/life-manager/lib/fixtures/geocode-free-candidates.json`
- Create: `apps/life-manager/lib/geocode-free-candidates.test.js`
- Do not modify: unified SSOT, `apps/life-manager/lib/travel.js`, `apps/life-manager/lib/geocode-cache.js`, scheduler, Railway config, or any production state.

**Interfaces:**
- Consumes: GSI GeoJSON `properties.title` and `[longitude, latitude]`; OpenPOI `/v1/search` and `/v1/suggest` response fields `count`, `results`/`suggestions`, `name`, `address`, `lat`, `lng`, `level`, `source`, `licenses`, and `attributions`.
- Produces: a dated fixture matrix for A4.2 adapter tests; no runtime API or provider-selection behavior.

- [x] **Step 1: Write `geocode-free-candidates.test.js` first.** Load the named JSON fixture and assert the known-address precision loss, GSI ambiguity, OpenPOI conflicting exact-name coordinates, broad/unmatched result, zero-result/timeout, dataset freshness, and attribution-array invariants using literal expected values.
- [x] **Step 2: Verify RED.** Run `node --test apps/life-manager/lib/geocode-free-candidates.test.js`. The test may map only `ENOENT` to `{schema_version: 0, cases: []}`; other read/parse errors must still throw.
  **Expected:** assertion FAIL on the missing fixture's `schema_version` (0, expected 1), not a test-run error.
- [x] **Step 3: Add the minimal fixture.** Include the 2026-10-07 GSI full-address/ambiguous/no-result samples; OpenPOI broad search, station suggestions, branch no-result, dataset release/cadence, and a clearly labeled synthetic timeout case. Keep each included POI's complete observed license and attribution arrays.
- [x] **Step 4: Verify GREEN.** Run `node --test apps/life-manager/lib/geocode-free-candidates.test.js`.
  **Expected:** all fixture contract tests pass without network access.
- [x] **Step 5: Run the focused regression.** Run `node --test apps/life-manager/lib/geocode-free-candidates.test.js apps/life-manager/lib/geocode-cache.test.js`.
  **Expected:** all fixture and existing geocode-cache tests pass; no production source file changed.
- [x] **Step 6: Review diff and commit Task 1.** Run `git diff --check`; confirm the fixture contains no credentials or personal calendar data; commit the plan, fixture, and test.

### Task 2: Advance the canonical A4.1 cursor

**Files:**
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**
- Consumes: Task 1's `apps/life-manager/lib/fixtures/geocode-free-candidates.json` and its passing offline test.
- Produces: canonical A4.1 findings plus cursor A4.2; preserves the existing mainline order.

- [ ] **Step 1: Confirm SSOT ownership is available.** Fetch `origin`; verify the current cursor is still A4.1 and no other session holds an active SSOT edit lease. If the owner is still completing its current readback, leave this file untouched.
- [ ] **Step 2: Record A4.1 evidence.** State the sample outcomes, attribution and privacy constraints, data freshness, unknown GSI rate/SLA, zero Life Manager production-route requests, and zero Google billable requests. Record old/new order and cursor together; only the cursor advances to A4.2.
- [ ] **Step 3: Verify and commit.** Run `git diff --check`, `bash scripts/verify-source-boundary.sh`, confirm the order/cursor and secret-free diff, then commit and push the SSOT update.
