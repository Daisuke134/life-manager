# Mobile App Metrics Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make mobile app revenue and distribution metrics source-separated, daily, and conversion-ready without claiming unavailable data as zero.

**Architecture:** Extend the existing ASC acquisition snapshot with denominator-safe funnel rates, preserve RevenueCat as an observed subscription/revenue source, and expose ASC proceeds separately as settled store revenue. Keep campaign attribution unavailable until a campaign identity is actually attached.

**Tech Stack:** Node.js CommonJS, Python `skills/cfo/loop_pnl.py`, existing JSONL daily snapshots, `node:test`, Python unittest.

**Spec:** `docs/superpowers/specs/2026-10-03-mobile-app-metrics-funnel-design.md`

## Tasks

### Task 1: Denominator-safe ASC funnel rates

**Status:** complete (`56faf5cdaa`); focused tests pass.

**Files:** `apps/life-manager/scripts/marketing-asc-acquisition.js`, `apps/life-manager/scripts/marketing-asc-acquisition.test.js`

- [x] Add failing tests for measured rates, zero denominators, missing metrics, and unavailable source.
- [x] Implement a pure rate helper returning measured/unavailable contracts with numerator/denominator.
- [x] Include `impression_to_page_view`, `page_view_to_install`, and `impression_to_install` in every product snapshot.
- [x] Run focused tests and commit.

### Task 2: Separate ASC proceeds from RevenueCat observations

**Status:** complete in local adapters (`b61347e50a`); live ASC source remains blocked by the App Store Connect agreement.

**Files:** `skills/cfo/loop_pnl.py`, `skills/cfo/test_loop_pnl.py`, `apps/life-manager/lib/financial-record-mobile-apps.js`, `apps/life-manager/lib/financial-record-mobile-apps.test.js`

- [x] Add failing fixtures for ASC settled proceeds plus RevenueCat chart revenue and assert no double count.
- [x] Count ASC proceeds only as settled external revenue when the source is available and currency is explicit.
- [x] Keep RevenueCat chart revenue labeled as observed/estimated and exclude it from settled totals when ASC proceeds are present.
- [x] Run focused CFO/Node tests and commit.

### Task 3: Surface mobile funnel status in the owner/CFO summary

**Status:** complete for daily summary output (`b61347e50a`); current rates remain unavailable when ASC is unavailable.

**Files:** `apps/life-manager/scripts/marketing-product-summary.js`, related tests, `docs/evidence/cfo/`

- [x] Add failing tests for source status, rates, attribution unavailable, and per-product separation.
- [x] Render the funnel with explicit `取得不可`/`UNKNOWN` states and source refs.
- [x] Record current ASC agreement failure and missing analytics as gaps, not zeros.
- [x] Run full mobile/CFO suites and commit.

### Task 4: ASC CLI and distribution handoff

**Status:** CLI update complete; provider permission/Agreement gate remains external.

- [x] Use Rork `asc` 5.9.2 after checksum verification.
- [x] Run read-only auth/analytics preflight; do not submit builds or alter pricing.
- [x] Hand off the required production credential/permission fix to the registered release owner.
- [ ] Re-run one daily snapshot after ASC readback becomes available.

## Verification

```bash
node --test apps/life-manager/scripts/marketing-asc-acquisition.test.js
python3 -m unittest skills/cfo/test_loop_pnl.py
npm test --prefix apps/life-manager
```
