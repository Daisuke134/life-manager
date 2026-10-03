# Mobile app metrics and revenue funnel design

## Goal

Give each mobile app a daily, source-separated funnel from store exposure to settled revenue so distribution and product changes can be evaluated without converting missing metrics to zero.

## Source contract

| metric | authoritative source | truth boundary |
|---|---|---|
| first-time downloads, impressions, product-page views | App Store Connect Analytics via Rork `asc` | measured only when the report is complete and app identity matches |
| MRR, active subscriptions, trials, churn, RevenueCat revenue chart | RevenueCat charts API | observed subscription/revenue estimate; not store settlement |
| store proceeds | App Store Connect Sales/Finance reports | settled revenue only when report receipt is available |
| paid customers for install-to-paid rate | product-owned paid-customer cohort | same app, cohort, and report window as ASC downloads; missing join stays unavailable |
| activation and retention | product analytics snapshot | measured only when cohort definition and source receipt exist |
| social distribution | platform-owned daily snapshots | reach evidence; never install attribution without campaign identity |

## Required derived metrics

For each product and same reporting window:

- `impression_to_page_view = unique_product_page_views / unique_impressions`
- `page_view_to_install = first_time_downloads / unique_product_page_views`
- `impression_to_install = first_time_downloads / unique_impressions`
- `install_to_paid = paid_customers / first_time_downloads`

Each rate is `{status: measured|unavailable, value, reason, numerator, denominator, source_refs}`. A zero denominator is `unavailable`, never `0`.

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
- RevenueCat is `available` for the latest six legacy CFO-bound product snapshots for business date 2026-10-02 (observed 2026-10-03 11:54–11:55 UTC). MRR is `20.34` for Anicca and `0` for the other five; daily RevenueCat `Revenue` is `0` for those six. Currency is absent, so the MRR values are currency `UNKNOWN`, are not the same set as the six currently published apps, and are not settled proceeds.
- The latest available Apple Finance Detail report (Apple fiscal month 2026-12; report period 2026-08-30–09-26) contains one settled JPY 4,250 proceeds row with Apple Identifier `6762049696`, SKU `ai.anicca.app.ios.yearly.b`, and title `Anicca Annual`. ASC `subscriptions list --app 6755129214` returns the exact subscription record ID and product ID, state `APPROVED`, period `ONE_YEAR`; therefore this row maps to Anicca through the official subscription record. `6762049696` is not an app ID, so `apps view`/public app lookup returning no app is not evidence of an unmapped sale. The producer source now exists in the mobile-metrics feature branch, but it is not loaded in production and the matched proceeds are not yet in the production CFO projection.

### CFO integration status

- The active CLI path is `loop_pnl.main` → `build_b7_projection` → `collect_b7_records` → `capafy_mobile.adapt_mobile`. The older `mobile_apps_entries()` helper is not the active B7 path and does not prove that the CFO report contains six products.
- The scheduled owner-facing Financial Manager path is separate: `life-manager-cfo-hourly` → `skills/cfo/run.sh` → `apps/life-manager/scripts/cfo-hourly-local.js` → `business-outcomes.jsonl` ingestion and report delivery. Both this path and B7 need the normalized Finance Detail rows.
- The acquisition collector now targets the six officially published apps above; it still reads old persisted pointers immutably and does not overwrite them. The four new Ongoing requests are active, but their `r3`/`r15` report links currently contain no daily instances, so live collection returns `report_pending` until Apple produces them. Existing immutable snapshots for the prior two-product portfolio remain historical evidence, not the six-app daily readback.
- The active B7 path still uses the old six-product RevenueCat binding set, not the six-public-app set. A fresh projection has no settled receipts or verified subscription snapshots: settled coverage is `missing_coverage`, MRR is `unsupported_currency`, and the four additional public apps lack current-project RevenueCat app records. Task 7 reconciles this mapping and freshness before any B7 total is called verified.
- The output now includes `install_to_paid` as explicitly unavailable until a paid-customer cohort is joined to the same app and report window. Campaign attribution, activation, and retention are also unavailable.
- Current production readback: `life-manager-cfo-hourly` is loaded-idle on release `80cccc6f92069b7a8d259af619b87e47bef9861c`; the latest terminal event at `2026-10-03T13:58:17Z` is `pass`/exit 0, but `effect_status=unknown`, `provider_receipt_id=null`, and `official_readback_ref=null`. `last-result.json` claims `sent` with `providerMessageId=102289`, while `last-delivered-snapshot.json` remains at reporting date `2026-09-26` and message `94946`; these are not correlated to the same occurrence. Treat delivery as unverified until the receipt/readback is joined.

### Implementation progress

- Task 6 six-app acquisition coverage is committed and pushed as `3f86d9530f`; focused mobile tests passed 22/22 and `npm test --prefix apps/life-manager` exited 0. Four ASC daily instances remain `report_pending`, not zero.
- Task 8 producer and identity-mapping source are implemented in the mobile-metrics feature branch. Fresh verification passes: ASC producer 31/31, B7 adapter 50/50, active B7 integration 43/43, focused Financial Manager/acquisition Node tests 27/27, `npm test --prefix apps/life-manager` exit 0, and `git diff --check`. The active B7 input path emits exactly one verified JPY 4,250 receipt and no duplicate RevenueCat chart receipt, but B0 keeps the 30-day settled total `unknown` because the final report ends 2026-09-26 and does not cover the 2026-09-30 cutoff. No Finance Detail row has been imported into production business outcomes, and no natural CFO delivery receipt/readback is correlated to the row.

No further Apple agreement or 2FA action is required. The `6762049696` row is now authoritatively mapped to Anicca; the remaining work is to ingest it once, with stable report/row identity, into B7 and Financial Manager.

## Observability

- Each product/source reports its status, reason when unavailable, report window, source/evidence reference, and source observation time.
- Download and engagement totals and derived rates use only intersecting report dates. A mismatch is unavailable, never a mixed-window rate.
- The CFO projection preserves the original source observation time and distinguishes recent-but-usable data from stale data; it must not turn a valid recent read into `stale_readback` only because the projection ran later.
- Unknown currency, missing settlement, missing cohort, and missing report coverage remain visible as gaps; they never become zero-valued verified revenue.

## Acceptance

1. ASC preflight records CLI version and redacted auth/source status; credentials never enter snapshots.
2. Acquisition snapshots expose all four derived rates. The three store-total rates use aligned ASC report dates; `install_to_paid` is measured only from a same-app, same-window paid-customer cohort, otherwise unavailable with a reason.
3. RevenueCat MRR/revenue observations stay separate from ASC settled proceeds and are excluded from settled P&L; the same proceeds are never counted twice.
4. The daily marketing summary shows per-app acquisition metrics and source status for all six apps in the official ASC published inventory. The B7 CFO projection reconciles those published IDs plus historical/prelaunch IDs separately, with covered product identities, observation time, and explicit gaps. It accepts the producer's verified current payload shape without false stale classification and still rejects genuinely stale data.
5. ASC settled rows map by exact raw `Apple Identifier` + SKU to an official subscription/IAP record and its parent app ID. Store the normalized parent app ID separately from the raw child identifier, SKU, catalog record type/ID, and mapping evidence; unmatched rows stay unassigned. Preserve the downloaded report's raw SHA-256 separately from the normalized-content SHA-256. Never compare a subscription ID directly to an app ID.
6. Relevant source suites pass. This slice does not submit apps, change paywalls/prices, publish marketing, or invent campaign attribution.
