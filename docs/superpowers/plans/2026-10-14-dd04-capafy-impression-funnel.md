# DD04 Capafy Impressions Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. Steps use checkbox syntax for tracking.

**Goal:** Add trustworthy Capafy listing-exposure observations to the existing traffic funnel without conflating impressions, detail views, or purchases.

**Architecture:** Extend the existing `capafy_hourly_reconcile.py` traffic-source collector with the already-observed `v2/impressions/stats` endpoint. Store impressions in a separate account/agent-scoped sidecar beside existing visits and sales; keep source rows, query bounds, filters, observed time, and canonical response hashes. Preserve the existing visits/sales `status`, summary, money verdict, and scheduled owner.

**Tech Stack:** Python standard library, existing `capafy_hourly_reconcile.py`, existing pytest suite.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`, DD04.

## Global Constraints

- Reuse the existing read-only `_post`, `TRAFFIC_SOURCES_BASE`, UTC-calendar 7d/30d windows, inventory-derived agent IDs, 60-agent cap, and delay.
- Call only `/app/developer/traffic-sources/v2/impressions/stats`; do not add credentials, providers, dependencies, spend, account routes, schedulers, or publishing.
- The new impressions read adds one request per existing scope/window (up to 122 per collector run); preserve the 60-agent cap and per-agent delay. No cadence or paid provider is added.
- Keep exposure counts separate from `pageViewCount`/`detailViewCount`, trials, paid orders, and sales.
- Preserve `sourceType`, `sourceName`, `agentId`, `country`, and `platform`; no country/platform filter is sent by the current query.
- Normalize each impression row to `source_type`, `source_name`, `agent_id`, `country`, `platform`, `exposure_count`, and `user_id_exposure_count`; keep rows separate and compute no source-summed exposure total.
- Use `exposureCount` only as the provider's listing-exposure event count. Preserve `userIdExposureCount` per row; its uniqueness and buyer meaning remain unverified.
- Preserve account and agent scopes separately. Do not sum across source rows or between account and agent scopes.
- Errors, missing tokens, malformed rows, and missing metric values remain unknown/null. A successful empty item list is an empty result only for that exact query scope.
- Keep `traffic_sources.status` and the financial reconcile verdict unchanged; add a separate funnel freshness field.
- Compute `funnel_status` from account-level 7d/30d windows only; report by-agent omissions explicitly and never turn omitted agents into zeros.

## Review Focus

- A provider error or malformed exposure value must produce unknown/null, never a fabricated zero.
- A successful empty `items` response must stay distinguishable from a missing or failed response.
- Rows with the same source name but different type, country, platform, or agent must not be collapsed.
- Account-level and agent-filtered responses must remain separate even when their values differ.
- A missing or semantically uncertain `userIdExposureCount` must not become unique buyers, qualified clicks, or paid outcomes.

---

### Task 1: Add a separately scoped impressions sidecar

**Files:**
- Modify: `skills/earn/capafy-marketing/scripts/capafy_hourly_reconcile.py`
- Test: `skills/earn/capafy-marketing/tests/test_capafy_hourly_reconcile.py`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**
- Add `_impressions_window(web_token: str, start_ms: int, end_ms: int, observed_at: str, agent_id: str | None = None) -> dict` beside `_traffic_window`.
- Extend `_traffic_window(..., observed_at: str)` to retain separate visits/sales status and canonical response hashes without changing its existing totals.
- Extend `build_traffic_sources(..., observed_at: str)` to attach account-level and capped per-agent impressions in `traffic_sources["impressions"]`; retain the existing visits/sales shape and top-level status.
- `traffic_sources["impressions"]` contains `status`, `account.last_7d`, `account.last_30d`, `by_agent[agent_id].last_7d`, `by_agent[agent_id].last_30d`, and `by_agent_coverage={requested,queried,omitted,cap}`. `traffic_sources["funnel_status"]` reflects account-level visits/sales/impressions freshness; legacy `traffic_sources["status"]` keeps its existing visits/sales-only meaning.
- Each impression row is exactly `{source_type, source_name, agent_id, country, platform, exposure_count, user_id_exposure_count}`; empty provider strings map to null, invalid counts map to null, and no cross-row or cross-scope count is generated.
- Every impressions/visits/sales window records `scope`, UTC start/end milliseconds and ISO bounds, Asia/Tokyo display bounds, `filters` (`country` and `platform` both null because no filter is sent), `observed_at`, per-source status, and canonical JSON SHA-256 computed as `sha256(json.dumps(response, sort_keys=True, separators=(",", ":")).encode("utf-8"))`. No raw response payload is retained.

- [x] Add RED test `test_impressions_window_preserves_provider_metrics_and_query_scope`: synthetic rows with `exposureCount`, `userIdExposureCount`, country, and platform stay separate; exact body, window, scope, and hash are asserted.
- [x] Run the focused test before implementation; it failed with the expected missing `_impressions_window` behavior.
- [x] Extend `test_traffic_window_posts_startat_endat_and_optional_agent` to assert separate visits/sales hashes, query scope, UTC/local bounds, filters, and observation time.
- [x] Run the focused test before implementation; it failed because `_traffic_window` did not accept `observed_at` or return source provenance.
- [x] Add RED test `test_impressions_window_keeps_empty_errors_and_malformed_counts_distinct`: transport/API errors, missing `items`, and invalid metric types stay unknown/null; a successful empty list is fresh with zero rows.
- [x] Run the focused test before implementation; it failed with the expected missing `_impressions_window` behavior.
- [x] Extend `test_build_traffic_sources_covers_windows_and_bounded_per_agent` and `test_build_traffic_sources_respects_the_agent_cap` to cover account/agent impressions, cap coverage, and non-aggregation.
- [x] Add RED test `test_impressions_failure_only_degrades_funnel_status`: failed impressions degrades `funnel_status` while legacy visits/sales status, summary, and `build_receipt().verdict` remain unchanged.
- [x] Run six focused tests before implementation; all six failed on the missing function/signature as expected.
- [x] Add two regression tests after fresh review found malformed visits could be reported `fresh` or contaminate valid sales status; confirm both fail before the fix and pass afterward.
- [x] Implement `_traffic_window(..., observed_at: str)` with scope/window/filter metadata and separate canonical hashes for visits and sales.
- [x] Derive visits and sales source status independently from each endpoint's transport and row shape; retain legacy window `status` behavior.
- [x] Implement `_impressions_window` with a whitelist projection of observed row fields and fail-closed unknown states.
- [x] Integrate impressions into the same bounded account/agent windows; keep existing visits/sales request and summary behavior unchanged.
- [x] Run regression tests RED→GREEN (2/2) and full Capafy hourly reconcile suite (48/48).
- [x] Run `bash scripts/verify-source-boundary.sh`, `git diff --check`, and targeted Gitleaks scans (0 findings).
- [x] Update the canonical spec with reviewed source-status behavior, local acceptance, and the current DD04 cursor; remove the duplicate schema-probe paragraph.
- [x] Commit and push the implementation, regression tests, plan, and canonical spec to PR #7976 (`292fc86a90`).
- [x] Obtain fresh read-only review of the correction; reviewer returned SHIP for source commit `292fc86a90`.
- [x] Pass exact-head CI on head `9acbd136888804678775083fe98fcdd72fbc6e60` (run `38484484101`, 11/11 jobs) and merge PR #7976 as `32077478452505a77969ea7ca23bf767ed022792`.
- [x] Attempt the full immutable `origin/main` release cut. The preflight deferred with `disk_headroom_low` (`available_bytes=2225684480`, `required_bytes=2399420416`); current symlink stayed on release `28614ef51d8f5be0aa82c0967d4d8562ba7f14dc`, and target apply was not attempted.
- [ ] Diagnose the unexplained capacity drop using fresh cleanup/inventory and active-writer evidence; preserve open/protected Codex state and Git objects. Retry the full cutter only when measured available bytes meet `2399420416` and the global release-cut lock is free, then cut a complete immutable release from latest main.
- [ ] Recheck the owner is loaded-idle and apply only `capafy-goal-monitor-hourly` through the existing owner-locked `lm-loop apply --loaded-idle-only` path. Do not force-wake it or send a separate report.
- [ ] Read the natural production receipt and verify the new impressions sidecar is present with fresh/unknown semantics, while the legacy financial verdict and provider attribution remain unchanged. Then close DD04 and advance the canonical cursor.
