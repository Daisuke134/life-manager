# Mobile app metrics and revenue funnel design

## Goal

Give each mobile app a daily, source-separated funnel from store exposure to settled revenue so distribution and product changes can be evaluated without converting missing metrics to zero.

## Scope boundary

This spec covers mobile-app acquisition, subscription observations, and App Store settlement. It is not the company-wide or personal CFO ledger: MUFG/Moneytree balances, non-mobile revenue, all-company expenses/subscriptions, and Google Cloud/API invoice attribution require separate source contracts and are not claimed complete here.

## Source contract

| metric | authoritative source | truth boundary |
|---|---|---|
| first-time downloads, impressions, product-page views | App Store Connect Analytics via Rork `asc` | measured only when the report is complete and app identity matches |
| MRR, active subscriptions, trials, churn, RevenueCat revenue chart | RevenueCat charts API | observed subscription/revenue estimate; not store settlement |
| store proceeds | App Store Connect Sales/Finance reports | settled revenue only when report receipt is available |
| paid customers for install-to-paid rate | Apple-documented Download-to-Paid D7 metric, currently readable only through Rork `asc web analytics cohorts`' experimental/private ASC web endpoint; denominator from the matching ASC `r3` first-time-download report | This is not a supported public ASC API. Mark the metric experimental; only measure the same app and exact mature cohort date with a nonzero official denominator, zero redownloads, and a rate that uniquely reconstructs an integer payer count at provider precision. Otherwise unavailable; never substitute RevenueCat cohorts or summed purchase rows. |
| activation and retention | product analytics snapshot | measured only when cohort definition and source receipt exist |
| social distribution | platform-owned daily snapshots | reach evidence; never install attribution without campaign identity |

## Required derived metrics

For each product and same reporting window:

- `impression_to_page_view = unique_product_page_views / unique_impressions`
- `page_view_to_install = first_time_downloads / unique_product_page_views`
- `impression_to_install = first_time_downloads / unique_impressions`
- `install_to_paid = D7_paid_customers / first_time_downloads` for one exact, mature ASC download cohort; include `cohort_date` and `cohort_window_days=7` in the source record.

Each rate includes `{status: measured|unavailable, value, reason, numerator, denominator, source_refs}`. The install-to-paid rate also records its cohort date and seven-day window. A zero denominator is `unavailable`, never `0`.

## Current verified state

### Provider observations

- Rork `asc` 5.9.2 is installed and checksum-verified. The Account Holder agreement is active (`pending=false`, accepted 2026-10-03T10:14:32Z); ASC has 24 app records. The official `asc apps published` audit reports six seller-owned apps published in 175 territories each; the current branch uses these IDs as the acquisition target set:

| active public app | ASC app ID | bundle ID | acquisition request |
|---|---:|---|---|
| Anicca | `6755129214` | `ai.anicca.app.ios` | `04c74879-547f-4e35-b231-1fafd485801d` |
| Honne | `6759667221` | `app.rork.hon-ne-honyaku-ai` | `c7c05836-181e-49cc-ae71-b57b7a0b466e` |
| Dhamma Quotes | `6757726663` | `com.dailydhamma.app` | `25b5906d-025b-4b9d-8226-dc1ea25bd13f` |
| For Better Sleep - Sleep Reset | `6762143790` | `app.rork.vcinrjbl3ke00f07gtlzf` | `f4f4e486-d5cd-4b16-9d06-a1850fc9a477` |
| STUDIO CHERIE | `6766485903` | `app.rork.xhozd938ie79zdqd5plem` | `b1c18c4e-77f3-4b63-bee4-259353531c3d` |
| Thankful - Gratitude Journal | `6759514159` | `app.rork.thankful-gratitude-app` | `a1149f87-b22a-42cb-85a8-324eb54d2f1a` |

- Fresh acquisition read intersects download and engagement dates before calculating rates. Anicca's latest common window is 2026-10-01: 0 first-time downloads, 5 unique impressions, 0 unique page views; page-view→install is unavailable (`denominator_zero`), and `install_to_paid` is unavailable (`paid_customer_cohort_unavailable`). Honne has no overlapping report date (`report_window_mismatch`). The four new ongoing requests are active, but ASC has not produced daily report instances yet; current status is `report_pending`, not zero.
- The old CFO binding set contains Anicca/Honne plus four nonpublished app records: `BreathCalm Test` (`6760253231`), `SleepRitual` (`6759916261`), `Desk Stretch Timer` (`6760048397`), and `Micro-Mood` (`6759877003`). The ASC published audit excludes these four. Keep them separate as prelaunch/unpublished records; do not use them as the live acquisition denominator.
- The configured RevenueCat project has eight app records: Anicca and Honne, those same four unpublished app records, one RC Billing app, and one Test Store. The four additional published apps above have no app record in this configured project; their RevenueCat metrics must remain unavailable until an authoritative source/project binding is found.
- A fresh RevenueCat v2 account read found one project (`anicca`) with eight app records. The project product endpoint returns 21 product IDs across six app IDs (Anicca, Honne, SleepRitual, Desk Stretch Timer, Micro Mood, and Test Store); the BreathReset and Anicca Web Billing app records have no listed products. None of the four additional published ASC apps is present in the project app inventory. Similar names are not sufficient product bindings.
- The persisted RevenueCat snapshots for the six legacy CFO-bound products (business date 2026-10-02) still omit currency, so those stored values remain `UNKNOWN`. A fresh RevenueCat v2 MRR chart read for complete period 2026-10-02 returns `yaxis_currency=USD`: Anicca is `$20.34`; Honne, BreathReset, SleepRitual, Desk Stretch Timer, and Micro Mood are `$0`. These are provider-observed MRR estimates, not settled proceeds; Test Store is excluded.
- Anicca's stored RevenueCat `conversion_to_paying` chart has `New Customers=1`, `Paying Customers (7 days)=0`, and `Conversion Rate (7 days)=0` for its latest complete cohort. RevenueCat cohorts customers by first-seen/first purchase, not App Store first-time download; its product filter does not scope the `New Customers` denominator. Do not use this as `install_to_paid`.
- Apple documents `Download to Paid` as conversion from a download cohort within D1/D7/etc. The read-only Rork `asc web analytics cohorts` command returned D7 `0%` for the Anicca and Honne `2026-09-26` cohorts; matching official ASC `r3` first-time-download denominators are 4 and 1, each with zero redownloads. These exact historical cohorts therefore have observed 0/4 and 0/1 conversions, but are too small to indicate a stable trend. The four other published apps have no matching official daily denominator, so any private endpoint zero is unavailable, not zero conversion. ASC exposes no public cohort API schema; the Rork web-session endpoint is experimental/private and not a production-grade contract. Keep its status and sample size visible, fail closed on any mismatch, and never fall back to summing purchase rows. [Apple cohort definition](https://developer.apple.com/help/app-store-connect-analytics/monetization/cohorts/), [Apple Purchases report fields](https://developer.apple.com/documentation/analytics-reports/app-store-purchase)
- Campaign/activation/retention readiness is incomplete: Honne has a configured campaign token but the checked `2026-10-02` report contained no matching campaign row (not a measured zero); Anicca has no configured campaign token. Anicca's available Mixpanel export contains app-open/onboarding/paywall events but no purchase event; Honne has no verified funnel source, and the PostHog project read credential is missing. Keep attribution, activation, and retention unavailable until source identity, event definitions, and report windows are verified.
- The latest available Apple Finance Detail report (Apple fiscal month 2026-12; report period 2026-08-30–09-26) contains one settled JPY 4,250 proceeds row with Apple Identifier `6762049696`, SKU `ai.anicca.app.ios.yearly.b`, and title `Anicca Annual`. ASC `subscriptions list --app 6755129214` returns the exact subscription record ID and product ID, state `APPROVED`, period `ONE_YEAR`; therefore this row maps to Anicca through the official subscription record. `6762049696` is not an app ID, so `apps view`/public app lookup returning no app is not evidence of an unmapped sale. The producer source now exists in the mobile-metrics feature branch, but it is not loaded in production and the matched proceeds are not yet in the production CFO projection.

### CFO integration status

- The active CLI path is `loop_pnl.main` → `build_b7_projection` → `collect_b7_records` → `capafy_mobile.adapt_mobile`. The older `mobile_apps_entries()` helper is not the active B7 path and does not prove that the CFO report contains six products.
- The scheduled owner-facing Financial Manager path is separate: `life-manager-cfo-hourly` → `skills/cfo/run.sh` → `apps/life-manager/scripts/cfo-hourly-local.js` → `business-outcomes.jsonl` ingestion and report delivery. Both this path and B7 need the normalized Finance Detail rows.
- The acquisition collector now targets the six officially published apps above; it still reads old persisted pointers immutably and does not overwrite them. The four new Ongoing requests are active, but their `r3`/`r15` report links currently contain no daily instances, so live collection returns `report_pending` until Apple produces them. Existing immutable snapshots for the prior two-product portfolio remain historical evidence, not the six-app daily readback.
- The loaded active B7 path still uses the old six-product RevenueCat binding set, not the six-public-app set. A fresh production projection has no settled receipts or verified subscription snapshots: settled coverage is `missing_coverage`, MRR is `unsupported_currency`, and the four additional public apps lack current-project RevenueCat app records. The feature branch now includes the six-published/four-prelaunch roster, chart-currency capture, mobile-only freshness tolerance, and per-app RevenueCat gap rows. Production remains on immutable releases outside this branch until the combined acceptance/promotion gate.
- The output currently keeps `install_to_paid` unavailable: the D7 source has read-only feasibility evidence for two tiny historical cohorts, but no collector integration or supported public API contract yet. If integrated, it must remain visibly experimental and fail closed under the source contract above. Campaign attribution, activation, and retention are unavailable for the source gaps listed above.
- Current production readback (rechecked 2026-10-04): `marketing-metrics-daily` is loaded-idle on release `9c03543e5dc51f7bc54f8e132a264964a0e40f6d`; latest run `18db16696e9c8a10-9960` passed at `2026-10-03T17:53:18Z`. The production `business-outcomes.jsonl` mtime is `2026-10-04T02:53:15+09:00`, latest business date `2026-10-03`, and still contains only the six legacy CFO-bound mobile products. Anicca and Honne ASC reads are available, but App Store sales are `provider_query_failed`; all six persisted RevenueCat rows lack currency; the four additional published apps are absent. There is no production `app_store_financial` row. CFO is loaded-idle on `c0db5d489d96738bcbd69229ad04c97eb05b2193`; its latest occurrence `life-manager-cfo-hourly:18db16b0c6340428-28078` at `2026-10-03T17:57:05Z` was deferred with `host_admission_deferred:resource_capacity_busy` (exit 75), with no receipt/readback. The durable delivered snapshot still reports `2026-09-26` (`provider_message_id=94946`), while `last-result.json` claims a send for `2026-10-04` (`providerMessageId=102384`); these are not correlated, so the current delivery remains unverified. Do not manually trigger either owner or claim a fresh CFO report was delivered.

### Implementation progress

- Task 6 six-app acquisition coverage is committed and pushed as `3f86d9530f`; focused mobile tests passed 22/22 and `npm test --prefix apps/life-manager` exited 0. Four ASC daily instances remain `report_pending`, not zero.
- The independent source review returned `fix-first` on four Task 7/8 defects. All four now have focused RED→GREEN regressions: Financial Manager rejects missing/altered report hashes and evidence; transient producer failures preserve last-good Finance Detail and its original source observation time while exposing the latest attempt; one-day freshness tolerance is mobile-only; and each unbound public app has an individual B7 coverage row. Latest source verification: Financial Manager mobile 17/17, producer 36/36, full CFO unittest discovery 275/275, full `npm test --prefix apps/life-manager` exit 0, and `git diff --check` clean. These are source-only results, not production proof. No Finance Detail row has been imported into production and no natural CFO receipt/readback is correlated to the row.

### Source-correctness contract

- Financial Manager must validate the canonical normalized-content hash and report/evidence identity for the complete Finance Detail payload before marking any proceeds row `verified`. Missing or mismatched hashes, missing evidence, or a row altered independently of its report must fail closed; the raw downloaded-report SHA-256 remains distinct from the normalized-content SHA-256.
- A transient `provider_query_failed` attempt must not overwrite a previously successful `app_store_financial` row with unavailable data. Preserve the last-good row and its original `observed_at`, while making the latest failed attempt/status visible; a failed refresh must never make old data look fresh.
- The one-day staggered-observation allowance applies only to the mobile RevenueCat subscription snapshots that need it. Other B0 product loops retain their existing freshness semantics.
- Each of the four published apps without a RevenueCat binding—Dhamma Quotes (`6757726663`), Sleep Reset (`6762143790`), STUDIO CHERIE (`6766485903`), and Thankful (`6759514159`)—must have an individually identifiable `app_not_in_project`/unavailable coverage record in B7. A loop-level aggregate gap must not hide which app is missing or let stale coverage mask it.

No further Apple agreement or 2FA action is required. The `6762049696` row is authoritatively mapped to Anicca. Task 7/8 source-correctness fixes pass their regression suites; production import remains last, after Task 9/10 source disposition, then must be read through B7 and Financial Manager and correlated to a natural CFO receipt/readback.

## Observability

- Each product/source reports its status, reason when unavailable, report window, source/evidence reference, and source observation time.
- Any ASC D7 cohort value reports `cohort_date`, `period_days=7`, matching first-time-download denominator, redownload count, provider percentage/precision, reconstructed paid count (only when unique), sample size, source path, and experimental status. Missing, immature, zero-denominator, privacy-suppressed, or inconsistent data stays unavailable.
- Download and engagement totals and derived rates use only intersecting report dates. A mismatch is unavailable, never a mixed-window rate.
- The CFO projection preserves the original source observation time and distinguishes recent-but-usable data from stale data; it must not turn a valid recent read into `stale_readback` only because the projection ran later.
- For mobile RevenueCat subscription snapshots only, B0 accepts staggered `observed_at` values up to one day before the projection snapshot; older snapshots stay stale/unavailable. This allowance does not change other product loops' freshness semantics. Any app-level source gap still makes portfolio MRR `unknown` while preserving valid per-app snapshots and individually identifying each gap.
- Unknown currency, missing settlement, missing cohort, and missing report coverage remain visible as gaps; they never become zero-valued verified revenue.

## Acceptance

1. ASC preflight records CLI version and redacted auth/source status; credentials never enter snapshots.
2. Acquisition snapshots expose all four derived rates. The three store-total rates use aligned ASC report dates. `install_to_paid` stays unavailable unless the exact D7 contract passes; any value obtained from the experimental private endpoint is labeled experimental with cohort date, denominator, sample size, and source status, and is never treated as settled revenue.
3. RevenueCat MRR/revenue observations stay separate from ASC settled proceeds and are excluded from settled P&L; the same proceeds are never counted twice.
4. The daily marketing summary shows per-app acquisition metrics and source status for all six apps in the official ASC published inventory. The B7 CFO projection reconciles those published IDs plus historical/prelaunch IDs separately, with covered product identities, observation time, and product-level gaps. Each unbound published app stays individually visible; aggregate coverage cannot hide a missing app. Mobile-only freshness tolerance does not alter other loops' rules.
5. ASC settled rows map by exact raw `Apple Identifier` + SKU to an official subscription/IAP record and its parent app ID. Store the normalized parent app ID separately from the raw child identifier, SKU, catalog record type/ID, and mapping evidence; unmatched rows stay unassigned. Preserve the downloaded report's raw SHA-256 separately from the normalized-content SHA-256. Financial Manager validates the complete canonical payload and evidence before marking a row verified; missing, altered, or mismatched hashes fail closed. Never compare a subscription ID directly to an app ID.
6. A transient provider-read failure cannot erase a last-good settled row or refresh its original `observed_at`; the latest attempt status remains visible separately.
7. Relevant source suites pass, including regression coverage for all four review findings. This slice does not submit apps, change paywalls/prices, publish marketing, or invent campaign attribution.
