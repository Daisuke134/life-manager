# Phase 06 Scope Amendment — Owner-controlled, voluntary digital public goods (v2)

**Date:** 2026-10-22 (JST)
**Source authority:** `products/manager/docs/roadmap/tasks.json` (one registry)
**Original source:** immutable Git revision `de8656444c132fe2c51b7ed79f007724ce152d2a`.
**User decision:** Stop treating money-holder approvals and indoor facility access as prerequisites to building Manager; replace this dependency with a permission-independent first wedge that can genuinely be built and measured.
**Boundary:** Historical acceptance is versioned, never retroactively claimed as satisfied. Superseding scope is not evidence that an earlier finance/physical experiment occurred.

**Execution-order SSOT:** `../roadmap/tasks.json` / F009 `technical_execution_sequence` and `technical_execution_cursor` fixes **E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12 → E13 → E14 → E15 → E16** as the sole sequential engineering track. **F005 → F006 → F008 → F009** are evidence acceptance checks after E implementation, not a second earlier queue. F004/F007 skipped but not done. [Superpowers core plan](../plans/2026-10-22-manager-core-execution-plan.md) has atomic file/test steps.

## What changes

**Old F004** — requires outside financial administrator, budget and approval for third-party transfers — is **retired/waived**. No funds are needed to develop Manager's public-information intervention. Historical `original_*` fields preserve the old status and original acceptance. Owner authorization for edits to Anicca's own properties remains a real, separately checked capability.

**Old F007** — requires a physical facility operator, indoor sensors and permission to actuate equipment — is **retired/waived**. A useful Manager need not install instruments or control facilities. Human-facing informational and accessibility improvements to owned pages count as environmental changes **only at the observed technical artifact level**, not verified relief of suffering.

**F005** (new technical track): Demonstrate bounded first-party public-information release with actual provider commit, immutable content comparison, independently fetched live bytes, no unintended change outside `manager-support/` and NO_ACTION/replay-zero. A verified technical publication is P1/P2, not welfare.

**F006** (new reporting track): Preregister and report the digital state outcome and null/negative/unknown evidence, with a control/no-action reference if available. Explicitly mark empirical users, conversions, mental/physical/financial benefits and causal effects **NOT_MEASURED**. Deterministic exact-byte criteria are not population confidence intervals; CI only when a sample-based endpoint exists.

**F008** (new second-surface track): Verify a **different public informational barrier or topic page** on the already controlled publication channel, using the same bounded pipeline. Record separate target URLs, original content hashes, independent readbacks, rollback/no-action and harm limitations. Do not assert independence of human participants or two field studies merely from two HTML pages.

**F009** (new integration track): Verify a single common Manager technical kernel and publisher for at least two distinct owned public assets with independent P2 readbacks and traceable receipts, without granting new money, private access or facility capabilities. Its result is `PHASE06_DIGITAL_TECHNICAL_P2`; beneficiary effects remain unmeasured.

## Non-negotiable distinctions

1. **Talking, publishing accurate information, making optional recommendations, and modifying the owner's own website do not require third-party facility grants.** These actions may still require the usual platform's valid owner credentials and respect private/regulated rights.
2. This amendment does **not** authorize touching other people's equipment, accounts, money, health records, identities, inboxes or personal profiles without applicable permissions. It eliminates those activities from Phase06's critical path; it does not abolish consent for third-party operations.
3. Never replace `skipped/waived` with `done`; historical F004/F007 were not completed. Waiver means no longer required.
4. Only mark the revised F005/F006/F008/F009 done with verified actual occurrence evidence, tests, same-commit/immutable source and an independent external readback. A mock, fixture, planned act, PR alone or success banner is not enough.
5. The original Phase09 finance/air quality chapters are now optional **separate research**, not required for Phase06 technical release. Their original acceptance conditions are unchanged. The product's much larger aspiration — reducing human suffering — remains unverified and must not be conflated with an accessible website.
6. No new customer recruitment, unsolicited message, collection of identifiable personal data or randomized human experiment is part of this amendment.

## Approved paths and invariants

- Existing official guide: `manager_core/digital_environment.py` builds the six `manager-support` HTML pages and manifest, with only public, nonpersonal official links and accessible layout.
- Publisher: `.github/workflows/manager-phase06-service.yml` and `scripts/phase06_kernel_release.py` with separate GitHub Actions admission. Only existing `gh-pages:manager-support/` seven-file allowlist may change.
- Proof: `scripts/phase06_kernel_release.py prove` checks exact provider commit, parent bundles, changed files and actual HTTP GET of independently served artifacts. No private contact forms, trackers or financial transfers.
- Control: `NO_ACTION` if candidate unchanged, source unverified, grant absent, live result unknown or target advanced. Financial budget remains zero.
- Quality: compare before/after bytes and accessibility without pretending clickthrough or suffering relief was measured.

## One-registry status migration

The old F004/F007 become `skipped`, each with `waiver_scope`, `waiver_reason`, `original_status=blocked`, `original_change`, `original_verify`, `original_external`, `original_depends`, and `scope_amendment`. This is a transparent owner-requested waiver, not hidden deletion. F005/F006/F008/F009 receive new purpose, dependencies and versioned `original_*` fields. Initially remain `todo` until verified acceptance. `H005` retains its scientific waiver unchanged. Original 113-task ID set and past done records remain stable.

## Test acceptance

- `scripts/make_roadmap.py --check` agrees with the registry; neither F004 nor F007 is a blocking dependency; no marked-done task depends on a skipped/blocked task.
- New `tests/test_phase06_owned_scope.py` checks scope version, history, own-assets-only and P0/P2/P3 separation.
- Legacy finance/indoor adapters remain inert. Historical tests may be updated to expect a **retired original track** while continuing to assert that self-attested external privileges cannot enable any operations.
- The exact live bundle is verified anew before marking a technical effect.
- Versioned `docs/verification/PHASE06_DIGITAL_V2_RESULT_20261022.json` distinguishes public tech evidence and human unknown.

## Explicit exclusion

No attempt will be made to obtain a room key, indoor sensor, grant for someone else's money or personal medical data merely to satisfy Phase06. Those can be separately pursued in future, if truly needed and authorized. Buddhism/compassion inform the mission; none of these engineering measures claims to replicate the historical Buddha's achievements or create a literally omniscient being.
