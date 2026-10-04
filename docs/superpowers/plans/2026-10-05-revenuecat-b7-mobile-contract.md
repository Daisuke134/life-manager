# RevenueCat-to-B7 Mobile MRR Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** B7 consumes the latest verified RevenueCat MRR snapshot for the six configured mobile apps from the existing shared `business-outcomes.jsonl`, with currency, metric period, and evidence intact, while keeping MRR separate from settled revenue.

**Architecture:** Keep the current RevenueCat collector and JSONL source. It records the API's explicit `yaxis_currency`, exact MRR definition, and a normalized ISO period while retaining its data-only evidence hash. The B7 adapter filters the shared file to the six mobile products, verifies that source contract, and accepts only non-future observations within 24 hours and provider periods no more than one day behind the report date.

**Tech Stack:** Python, `unittest`, RevenueCat Charts API v2 readback fixtures, existing B7 adapter.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` §87-J item 5 and §87-AT/§87-AU.

## Global Constraints

- Missing, malformed, future, or stale source data remains unknown/partial, never zero.
- RevenueCat MRR remains a stock metric, not settled Apple proceeds, bank cash, or B7 revenue receipts.
- Preserve the API's explicit currency; do not infer from a symbol or convert currencies.
- Do not call providers or write live state during tests; use full-shape fixtures for the external response.
- Modify only the canonical source and tests named below; do not edit the separate mobile worktree or production owner.
- Do not create a CLI, alter launchd, or change reporting cadence.

## Review Focus

- Shared JSONL contains unrelated products and legacy aliases; only the six canonical mobile IDs may affect this adapter.
- RevenueCat MRR must preserve API `yaxis_currency`, the exact definition, and a normalized ISO UTC period; missing or incomplete values fail closed.
- The producer hashes `data`; the adapter verifies that same payload hash.
- A source observation is fresh only when it is not future-dated and is no older than 24 hours; one-day provider-period lag is allowed and the true period remains visible.
- MRR stays a subscription snapshot and never becomes settled revenue or bank proceeds.

---

### Task 1: Repair the existing RevenueCat-to-B7 mobile MRR path

**Files:**
- Modify: `skills/earn/marketing-engine/measure/business_outcomes.py`
- Test: `skills/earn/marketing-engine/measure/test_business_outcomes.py`
- Modify: `skills/cfo/adapters/capafy_mobile.py`
- Test: `skills/cfo/test_capafy_mobile_attribution.py`

**Interfaces:**
- Producer emits `sources.revenuecat.data` with `app_id`, `currency`, `revenue_definition`, `charts.mrr.latest_complete.MRR`, and `evidence_sha256 = sha256(data)`.
- Consumer returns one `subscription_snapshot` per mobile product and explicit `revenuecat-mrr` coverage; it does not create settled revenue receipts from MRR.

- [ ] **Step 1: Write failing producer tests.** `test_collect_revenuecat_emits_currency_definition_and_iso_mrr_period` feeds `yaxis_currency=USD` and MRR timestamp `1790985600`; assert `currency == "USD"`, the exact definition object, and `period == "2026-10-03"`. `test_collect_revenuecat_without_yaxis_currency_fails_closed` confirms missing currency cannot default from the `$` label. `test_collect_snapshot_jsonl_roundtrip_keeps_revenuecat_contract` checks `collect_snapshot` → `upsert_snapshots` → JSONL readback.
- [ ] **Step 2: Run producer tests and confirm the expected failures.** Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s skills/earn/marketing-engine/measure -p 'test_business_outcomes.py'`. Expected: the new assertions fail on missing currency/definition or numeric epoch period, not test setup/import errors.
- [ ] **Step 3: Write failing B7 adapter tests.** `test_mobile_adapter_filters_shared_jsonl_to_mobile_products` adds eBook and legacy rows and asserts only six mobile snapshots are returned. `test_mobile_adapter_accepts_one_day_period_lag_and_data_hash` uses `business_date=2026-10-04`, provider period `2026-10-03`, producer data-only hash, and `observed_at=2026-10-04T22:00:00Z` with `snapshot_at=2026-10-04T22:17:00Z`; assert six MRR subscription snapshots, no settled RevenueCat receipt, and `revenuecat-mrr` coverage `evidence_ref` ends with the actual provider period `2026-10-03`. `test_mobile_adapter_rejects_future_or_over_two_day_period` asserts provider periods `2026-10-05` and `2026-10-02` both yield incomplete `revenuecat-mrr` coverage for the `2026-10-04` report date. `test_mobile_adapter_observation_freshness_boundary` uses `snapshot_at=2026-10-04T22:17:00Z`: `observed_at=2026-10-03T22:17:00Z` is fresh at exactly 24 hours; `2026-10-03T22:16:59Z` is stale at 24 hours + 1 second; `2026-10-04T22:17:01Z` is stale because it is future-dated.
- [ ] **Step 4: Run B7 tests and confirm the expected failures.** Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest skills.cfo.test_capafy_mobile_attribution`. Expected: new cases fail on shared-file extras, producer hash scope, provider-period lag, and exact timestamp equality.
- [ ] **Step 5: Implement the smallest producer and consumer changes** in the two source files: carry `yaxis_currency`, exact MRR definition, normalize epoch period to ISO UTC, verify the existing data-only hash, filter to six mobile IDs, and apply the documented period/observation-age bounds. Keep MRR separate from settled receipt arithmetic.
- [ ] **Step 6: Run both focused test commands and `git diff --check`;** also run the pure adapter against a copied in-memory representation of the current JSONL shape and confirm six MRR snapshots only when every required field is valid.
- [ ] **Step 7: Commit and push this task branch.** Do not merge or change production; those remain gated by the complete §87-J acceptance.
