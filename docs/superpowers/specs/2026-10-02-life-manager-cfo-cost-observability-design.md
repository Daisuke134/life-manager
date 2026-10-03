# Life Manager CFO and Provider Cost Observability Design

Status: implementation slice shipped; acceptance partial
Owner: `lm-cfo-observability-1002`
Scope: Dais personal CFO, Life Manager business CFO, provider cost control, and daily source-backed reporting

## 1. Outcome

Life Manager gives Dais one daily CFO report containing:

1. personal cash and asset balances, including MUFG;
2. settled revenue from every connected revenue rail;
3. settled expenses from every connected bank/card/subscription rail;
4. Life Manager's own provider and cloud cost by tenant, loop, task, and provider;
5. actual, estimate, stale, and unknown states kept separate;
6. a source receipt for every displayed number.

The report is not complete when a local calculation succeeds. It is complete only after the source provider was read and the resulting receipt is durable.

## 2. Current evidence and gaps

### Evidence

- The September 2026 Google Cloud invoice was ¥27,889 including tax (¥25,354 before tax).
- Read-only Cloud Monitoring counts for the linked projects were 25,526 Geocoding calls, 15,092 Directions calls, 6,510 Places Text Search calls, and 21,796 Gemini GenerateContent calls.
- Token and current public pricing produced a pre-tax estimate close to ¥25,354. This is a diagnostic estimate, not the settled SKU receipt; the Google Cloud Cost table CSV remains the settlement authority.
- Moneytree Web readback showed one MUFG ordinary JPY account with last-known balance ¥504,302. Its last successful aggregation was 2026-08-26 and its connection state is `auth.creds.invalid` since 2026-08-28. The balance is stale and must not be reported as today's fresh balance.
- `origin/main` already contains a Moneytree MCP adapter and immutable observation store. A read-only MCP run returned one account and zero transactions on 2026-10-02; the zero-transaction result has no independent completeness/freshness proof and must not be rendered as zero spending.
- Acceptance readback on 2026-10-02 returned one MUFG-linked account at JPY 504,302 and zero transactions, both explicitly `partial`; details and payload receipts are in `docs/evidence/cfo/2026-10-02-cfo-cost-observability-acceptance.md`.
- A wider official Moneytree readback returned 187 transactions through 2026-08-25; after transfer/card-repayment exclusion, last-known income was JPY 806,201 and spending JPY 205,500. These remain stale because source freshness and transaction completeness are unproven.
- Latest sanitized Moneytree MCP readback (2026-10-04 07:37–07:39 JST) again returned one MUFG account with displayed balance JPY 504,302, but the account payload had no `source_updated_at` or transaction-completeness cursor. The 2026-07-04..2026-10-04 transaction range returned 183 rows (11 positive / 172 negative), all through 2026-08-25; a separate 2026-08-26..2026-10-04 query returned zero. Categorized inflow is JPY 806,201 after excluding JPY 18,455 of transfers. Categorized spending is JPY 205,500 for July/August only after excluding JPY 425,456 in transfers and JPY 34,164 in card repayments. Details: `docs/evidence/cfo/2026-10-04-moneytree-mcp-readback.md`. Keep these values `stale/partial`, not today's fresh balance/flows or company revenue.
- Live B7 `loop_pnl.py` readback now uses runtime-time snapshots. The latest canonical run records 129 historical gaps and 124 trailing gaps. Stripe's official read-only API path now produces source-backed trailing receipts, the official Google Cost Table is joined to B7 infra cost, Lancers' official empty-settlement artifact is retained but is coverage-stale and cannot be promoted to a current ¥0, and one CrowdWorks contract receipt is connected as partial coverage; PartnerStack is an official empty report; Alpaca account cash is verified while order P&L remains missing. No settled revenue/net is invented for unresolved rails.
- The canonical source-specific artifact path did verify Capafy last-7-day revenue of USD 19.94; this is not promoted to portfolio-wide settled MRR while strict B7 coverage remains unknown.

### Code gaps

- `origin/main` contains a Financial Manager and Moneytree ingestion path, but the default local result report still has a separate `skills/cfo/loop_pnl.py` path and does not combine personal Moneytree records with every business source in one canonical daily snapshot.
- Moneytree observations now retain a three-month last-known flow snapshot and exclude internal transfers/card repayments, but still mark the account and transaction cursor partial until provider freshness/completeness is proven.
- The current provider-cost ledger stores estimated usage but does not join a settled Google invoice or store actual-vs-estimated billing status on each cost event.
- The existing geocode memo is process-local; successful results are not persisted across restarts, allowing repeated paid requests.
- The existing provider-cost-guard plan defines persistent caches, cost events, budgets, and a seven-day observation gate, but its implementation tasks are not complete on `main`.

## 3. Accounting ownership

Every financial row has exactly one `owner`:

| owner | Meaning | Examples |
|---|---|---|
| `dais_personal` | Dais's personal financial position | MUFG, personal card, securities, cash |
| `life_manager` | Life Manager business economics | Stripe revenue, Google API, Telnyx, Railway, Supabase |
| `transfer` | Movement between owned accounts | MUFG → card payment, wallet → bank |
| `unknown` | Source or classification is unavailable | stale account, failed provider read, unmatched charge |

Internal transfers, owner deposits, fundraising, and unrealized gains are never revenue. Unknown is never zero.

## 4. System architecture

```mermaid
flowchart TD
  PERSONAL["Personal sources<br/>Moneytree / bank / card / broker"] --> ADAPTERS["Read-only source adapters"]
  REVENUE["Revenue sources<br/>Stripe / affiliate / marketplace / wallet"] --> ADAPTERS
  OPS["Operating sources<br/>Google / Gemini / Telnyx / Railway / Supabase"] --> ADAPTERS

  ADAPTERS --> RECEIPTS["Immutable source receipts<br/>provider id + observed_at + release_sha"]
  RECEIPTS --> LEDGER["Owner-separated financial ledger"]
  LEDGER --> PROJECTION["Deterministic projection"]

  PROJECTION --> PERSONAL_CFO["Personal CFO<br/>balance / spending / subscriptions / net worth"]
  PROJECTION --> BUSINESS_CFO["Life Manager CFO<br/>revenue / COGS / margin / runway"]
  PROJECTION --> UNIT["Unit economics<br/>tenant / loop / task / success"]

  BUDGET["Provider budget governor"] --> OPS
  PROJECTION --> REPORT["Daily / weekly Telegram + panel"]
  REPORT --> EVIDENCE["Source links + freshness + unknowns"]
```

The deterministic projection owns arithmetic. Agents may classify or explain, but they cannot invent balances, settle estimates, or replace a missing receipt with zero.

## 5. Observability contract

Every provider operation emits one structured observation. Cost observations are never sampled.

### Identity

`run_id`, `owner_id`, `tenant_id`, `occurrence_id`, `release_sha`, `phase`, `request_id`, `idempotency_key`.

### Operation

`provider`, `product`, `sku`, `operation`, allowlisted command name, cache hit/miss, and latency.

Raw prompt, bank number, API key, password, cookie, address, and secret values are excluded. Allowlisted environment names may be recorded with a hash only.

### Financial measurement

`quantity`, `unit`, `currency`, `estimated_amount`, `actual_amount`, `billing_status`, `pricing_version`, and `cost_owner`.

`billing_status` is one of:

- `estimated`
- `settled`
- `unknown`
- `not_applicable`

### Effect and failure

`effect`, `readback`, `provider_receipt_id`, `evidence_refs`, `exit_code`, `error_class`, `retryable`, and `next_action`.

`effect_unknown` is a hard safety state. It blocks duplicate external actions until official readback resolves it.

### Freshness

Each source row has `observed_at`, `source_updated_at`, `freshness_status`, and `stale_after`. A stale value can be shown as last-known, but never as current.

## 6. Daily CFO report contract

The daily report is a deterministic snapshot with these sections:

### Cash

- account and institution;
- current balance, original currency, and JPY projection only when FX provenance exists;
- `fresh`, `stale`, `failed`, or `unknown`;
- last successful provider observation;
- source receipt link.

### Revenue

- today, month-to-date, and trailing 12-month settled revenue;
- source-by-source rows;
- refunds and processor fees separately;
- pending, estimated, or unattributed amounts excluded from settled revenue and shown as unknown/pending.

### Expenses

- today, month-to-date, and trailing 12-month settled expenses;
- merchant/category/subscription;
- personal versus Life Manager owner;
- actual provider charges separate from estimates;
- stale or unavailable bank/card sources explicitly listed.

### Life Manager unit economics

- revenue, actual cost, estimated cost, unknown cost;
- net contribution and margin;
- cost per active tenant, loop, task, and successful outcome;
- cache hit rate and paid-fallback count;
- budget state and next action.

### Report stop rules

The report is `partial` when any required source is stale, failed, or unknown. It is `complete` only when the configured source set has fresh readback or a documented source-unavailable receipt.

## 7. Cost targets

These are design targets, not current achievements:

| scope | target |
|---|---:|
| Local routine API spend | $0–$5/month |
| Local paid fallback | Explicit daily budget only |
| Cloud fixed infrastructure | ≤$50/month initially |
| Cloud variable infrastructure | ≤$0.50/active user-month |
| Direct COGS at $10k MRR | ≤$500/month (5%) |
| Routine Japan POI/transit calls | $0 marginal provider cost |

Telephony, paid model calls, and user-requested external actions remain separately budgeted and are never hidden inside a generic “cloud” number.

## 8. Provider strategy

1. Persist geocodes and route results before changing providers.
2. Use OpenPOI as the Japan facility-search primary; preserve licenses and attributions.
3. Use a Japan address geocoder only for address-to-coordinate work; validate its coordinate precision before accepting it for departure safety.
4. Keep the existing Japan transit provider primary with cache, bounded timeout, fallback, and a visible unofficial-data warning.
5. Evaluate OSRM/Valhalla self-hosting for driving routes and OpenTripPlanner self-hosting for scheduled transit only after the current route cache and budget gates are measured.
6. Keep Google as an explicit, budget-authorized fallback rather than the scheduler default.

## 9. Ordered atomic delivery

### A0 — Spec and ownership

- approve this design;
- review existing Cost Guard and Finance specs for overlap;
- write the implementation plan only after this spec is accepted;
- record file ownership and excluded files in the plan.

### A1 — Observation envelope

- add schema and validation tests;
- add append-only storage/migration;
- redact secrets and PII;
- prove success, timeout, provider failure, crash, stale, and `effect_unknown` rows.

### A2 — Cost ledger

- extend provider cost rows with provider, SKU, operation, quantity, estimate, actual, billing status, and pricing version;
- reject missing actual billing as zero;
- make failed ledger writes visible to the owner.

### A3 — Geocode and route reuse

- persist successful geocodes;
- persist route results with tenant/event/time/mode/provider identity;
- prove repeated scheduler ticks create zero duplicate paid calls;
- preserve cache reads in degraded/stopped budget states.

### A4 — Free-provider lane

- add OpenPOI adapter and attribution persistence;
- add Japan address-geocoder adapter and precision tests;
- make Japan transit-first and Google fallback sequential;
- add provider health and fallback counters.

### A5 — Budget governor

- implement pure daily/monthly budget states;
- gate nonessential provider work;
- preserve essential cached reads;
- emit budget transition observations and Telegram warnings.

### A6 — Official Google billing reconciliation

- collect intramonth Monitoring usage estimates;
- import Cost table CSV settlement rows;
- join SKU/project/service rows to provider cost events;
- show estimate-versus-settled variance.

### A7 — Personal CFO rail

- restore Moneytree MUFG authorization;
- read accounts, transactions, and refresh timestamps read-only;
- normalize JPY/original currency/FX provenance;
- reject stale balances as current;
- read back the same balance and transaction cursor independently.

### A8 — Revenue and expense coverage

- connect every settled revenue rail;
- connect every personal bank/card rail;
- detect subscriptions and merchant categories;
- reconcile internal transfers;
- compute 1/3/12-month totals.

### A9 — Report surfaces

- build the deterministic daily/weekly snapshot;
- send Telegram report with freshness and receipts;
- render the same snapshot in the panel;
- test that Telegram and panel totals are identical.

### A10 — Natural-run acceptance

- run one local daily close;
- run one cloud canary;
- observe seven consecutive days;
- verify official Moneytree, Google billing, revenue, and expense readbacks;
- close only when all required numbers are either fresh and sourced or explicitly partial with an owner-visible blocker.

## 10. Current gate

Implementation is shipped on the dedicated branch through Tasks 1–7: truthful Moneytree freshness, canonical local daily path, B7 readback coverage, provider settlement ledger/Google CSV reconciliation, persistent geocode/OpenPOI lane, budget governor, and receipt-backed delivery. The Stripe B7 lane now uses complete official API pagination, cross-currency settlement reconciliation, explicit account classification, and period-scoped coverage; the official Google CSV is joined to B7 infra cost; recent official PartnerStack, CrowdWorks, Lancers, and Alpaca readbacks are bounded by a 24-hour freshness window where available, while the Lancers empty artifact remains coverage-stale and cannot close the current-period zero claim. Alpaca live account reads are enabled in the CFO environment. Task 8 acceptance is partial: the local fixture closes and replays zero, the September Google Cost Table now has an official CSV receipt and service/SKU reconciliation, B7 exposes grouped actionable source gaps, the canonical cloud owner binding plus current-worker send/replay-zero are proved, and a fail-closed seven-period gate is implemented; PartnerStack empty commission, CrowdWorks partial history, Alpaca order P&L, Coconala and other non-Stripe B7 source receipts, the historical Stripe adjustment, branch-to-production parity, and seven elapsed periods remain owner-visible blockers. Moneytree plugin access is available, but the 2026-10-04 read still ends at 2026-08-25 with no freshness/completeness receipt; JPY 504,302 remains last-known/stale, and freshness upgrade is open.

## 11. CFO-only ownership and current cursor

This spec is the CFO workstream's single ownership boundary. `lm-cfo-observability-1002` owns source-backed financial reads, settlement normalization, provider-cost attribution, fail-closed coverage, and the daily report contract. Marketplace publishing, Capafy/Coconala execution, affiliate production, and release/apply work remain with their registered loop owners; this workstream consumes their official receipts and does not mutate their live state.

### Repository approval and integration gate (2026-10-04)

- Issue [#6549](https://github.com/Daisuke134/life-manager/issues/6549) tracks this CFO/cost workstream; it is open with no maintainer response, and no PR exists. Per `CONTRIBUTING.md`, follow-up source edits wait for maintainer 👍.
- Existing branch `docs/lm-cfo-cost-observability-spec-20261002` is pushed at `afd448a554`; latest `origin/main` is `5fc226d9`, and the merge base is `bc0d1fa7`. A local latest-main merge attempt found conflicts in the CFO design spec, Stripe adapter, B7 collector, and three CFO test files; the merge was aborted without retaining source changes, and the worktree is clean. The branch is not ready for promotion; after approval, sync main, resolve conflicts, rerun acceptance, and obtain a fresh whole-branch review.

### Verified state

- The September Google Cost Table CSV is the settled authority: ¥27,889 including tax, ¥25,354.450951 pre-tax, 41 service/SKU rows, receipt `google-billing://sha256/c5157075fe3e8331fa2a72d3b33fc98bbacb8b84a0ee2cfc945051ee87f66c64`.
- Google cost attribution is now joined into B7 as 35 official-cost lines. OpenPOI's live read-only probe succeeds, persistent cache and Google fallback budget gates are present, but a seven-period reduction measurement is not yet proved.
- Moneytree is installed and readable, but MUFG's last-known balance is ¥504,302 and the 187-row flow snapshot is stale (latest source transaction 2026-08-25); the plugin's zero-transaction result has no completeness proof and is never rendered as zero.
- Latest Moneytree readback is the 2026-10-04 entry in `docs/evidence/cfo/2026-10-04-moneytree-mcp-readback.md`: one account, displayed balance ¥504,302, 183 transactions for 2026-07-04..2026-10-04, latest transaction 2026-08-25, categorized inflow ¥806,201, categorized spending ¥205,500 for July/August only. The displayed balance equals the last transaction balance and no independent freshness/completeness receipt exists; do not report it as today's CFO truth. The 2026-10-03 readback remains in its dated evidence file as historical context.
- Stripe trailing settlement, PartnerStack's official empty report, Lancers' coverage-stale empty-settlement artifact, the partial CrowdWorks contract receipt, and the Alpaca account cash readback are connected. Unknown, stale, pending, and missing settlement are excluded from settled revenue and shown as gaps.
- The latest sanitized B7 read-only run on 2026-10-03 has 137 historical gaps and 137 trailing gaps, with status `unknown` and no currency totals. Gap reasons are `missing_category=126`, `source_unconnected=5`, `read_failed=5`, and `stale_readback=1`; unknown revenue/cost/net remains excluded rather than converted to zero. The current whole-repository Node suite is 188/188 PASS and the CFO Python suite is 249/249 PASS; these tests do not close external-provider gaps.

### Ordered remaining atomic TODO

1. **Fresh personal cash:** Moneytree is readable, but the latest range stops at 2026-08-25 and the account payload has no source update timestamp or complete cursor. Refresh/restore the provider connection or obtain an independent bank readback, then record the fresh balance and transaction cursor; until then show JPY 504,302 and July/August flow totals as `stale/partial`, never current or zero.
2. **Complete external settlement:** obtain a fresh/current-period Lancers receipt plus official receipts for Coconala orders, PartnerStack commission/payout settlement after tax setup, CrowdWorks history beyond the one contract, Alpaca order/realized P&L, and the historical Stripe adjustment. The CFO adapter will consume receipts; each live marketplace/account mutation stays with its owner.
3. **Close the CFO snapshot:** rerun B7 with the fresh receipts, preserve every remaining gap as an owner-visible `missing_coverage`/`source_unconnected`/`stale_readback` state, and verify personal and business totals never convert unknown to zero.
4. **Production parity:** promote only the tested CFO release through the registered release owner, verify cloud tenant/email-wallet binding and official report delivery, and replay the same run with zero duplicate effects.
5. **Natural-run gate:** observe seven consecutive daily closes with Google settlement, Moneytree, revenue, expense, and delivery readbacks. Only then mark the CFO report complete and compare measured COGS with the ¥0–¥5 local routine target and the ≤5% direct-COGS target at ¥10k MRR.

### October Google cost estimate (not a settled invoice)

No October invoice has been issued yet. The last recorded Cloud Monitoring readback for 2026-10-01 through its observation cutoff shows 2,136 successful Gemini requests, 187 Places requests (186 successful and one 4xx), 86 successful Geocoding requests, and 378 Directions 4xx requests. Applying September's settled effective rates (Gemini ¥0.259/request, Places ¥1.604/backend request, Geocoding ¥0.386/request, Directions ¥0.232/request, plus about ¥10 monthly KMS) gives an October month-to-date estimate of about **¥984 (round to ¥1,000)** and a same-pace 30–31 day projection of about **¥9,800–¥10,200**. This is an inference from the prior monitoring snapshot and September receipt, not an official October charge; token/SKU mix and monitoring delay can move it. No newer 2026-10-04 Monitoring count readback was obtained in this pass: the installed gcloud 561.0.0 has no `monitoring time-series` command, and its beta/alpha groups are not installed. The MTD and projection are therefore not a fresh 10/04 actual. A conservative no-change baseline remains the September invoice of ¥27,889. The report must show both figures separately and never label the estimate as settled.

## 12. External provider research and selected cost-reduction design

This section records the provider decision after a source review on 2026-10-03. It narrows the next implementation slice; it does not claim that every candidate below is production-ready or that an estimate is a settled charge.

### Research matrix

| capability | candidates reviewed | evidence-bound finding | decision |
|---|---|---|---|
| Japan POI search | OpenPOI, Overture direct, Mapbox Search, Geoapify | [OpenPOI](https://docs.openpoiapi.com/) is keyless, free, commercial-use allowed, Japan-wide, returns coordinates plus `licenses`/`attributions`, and has a documented API rate limit. Overture is a data distribution/query source, not a ready-to-use application API ([docs](https://docs.overturemaps.org/), [GitHub](https://github.com/OvertureMaps/data)). | Keep OpenPOI as primary for the current Japan venue UX; preserve attribution and keep Google Places only as a budgeted fallback. |
| Japan address geocoding | Geoapify, Nominatim, Photon, Pelias, Google | Geoapify's free plan is commercial-use eligible but quota/attribution bound ([pricing](https://www.geoapify.com/pricing)). The public Nominatim service is capped at 1 request/second, forbids autocomplete, requires identification/caching, and recommends self-hosting for larger use ([policy](https://operations.osmfoundation.org/policies/nominatim/)). Photon public service is fair-use/no-SLA and its self-host documentation reports roughly 95 GB disk and 64 GB RAM for planet data ([GitHub](https://github.com/komoot/photon)). Pelias is open source but requires Elasticsearch and multiple import services ([GitHub](https://github.com/pelias/api)). | Benchmark Geoapify against a bounded self-host candidate; do not call public Nominatim/Photon from production. Keep cached Google Geocoding as fail-closed fallback until an accuracy/licence/freshness winner is proved. |
| Japan public transit | Transit API, OpenTripPlanner, Google Directions | [Transit terms](https://transit.ls8h.com/terms) state that the API is free/read-only/no-auth but unofficial, mutable, and without SLA. [OpenTripPlanner](https://www.opentripplanner.org/) combines OSM and GTFS but requires maintained feeds and a hosted Java service. | Keep Transit API primary with timeout/cache/official-data warning; benchmark OTP only when seven-period route demand justifies operating a feed/service. |
| Driving/non-Japan routing | OSRM, Valhalla, GraphHopper, Mapbox, Google Routes | [OSRM](https://github.com/Project-OSRM/osrm-backend) is a BSD-2-Clause C++ engine with Docker/OSM extracts for driving/bike/walk. [Valhalla](https://github.com/valhalla/valhalla) is MIT, tiled, and supports multimodal/time-based features but is heavier. GraphHopper's free plan is explicitly non-commercial and paid plans start at a recurring fee ([pricing](https://www.graphhopper.com/pricing/)). Mapbox is pay-as-you-go with commercial/licensing terms ([pricing](https://www.mapbox.com/pricing/)). | Keep Google as explicit fallback now. Benchmark OSRM first for driving only; benchmark Valhalla/OTP only if OSRM cannot meet route facts or coverage. |
| LLM reasoning/voice | Gemini, Ollama, llama.cpp, vLLM | Gemini has a free tier but production paid usage is token/tool-metered ([pricing](https://ai.google.dev/gemini-api/docs/pricing)). [Ollama](https://github.com/ollama/ollama) and [llama.cpp](https://github.com/ggml-org/llama.cpp) enable local inference; [vLLM](https://github.com/vllm-project/vllm) targets hosted throughput. None is a drop-in proof that preserves current Life Manager quality, voice latency, cloud access, or receipt semantics. | Do not switch Gemini blindly. Evaluate the existing local-model lane on recorded CFO/calendar tasks; keep Gemini for voice/high-risk paths until quality, latency, and cost gates pass. |

### Selected architecture

```mermaid
flowchart LR
  REQUEST["Calendar / travel request"] --> CACHE["Tenant + event cache"]
  CACHE --> POLICY["Provider policy + budget gate"]
  POLICY --> POI["Japan POI: OpenPOI"]
  POI --> POIFB["Google Places fallback"]
  POLICY --> JPTRANSIT["Japan transit: Transit API"]
  JPTRANSIT --> TRANSITFB["Google Directions fallback"]
  POLICY --> GEO["Address geocode: cache / benchmark winner"]
  GEO --> GEOFB["Google Geocoding fallback"]
  POLICY --> LLM["Gemini now; local-LM evaluation lane"]
  POIFB --> OBS["usage + attribution + receipt"]
  TRANSITFB --> OBS
  GEOFB --> OBS
  LLM --> OBS
  OBS --> CFO["CFO actual / estimate / unknown report"]
```

The user-facing contract stays unchanged: a known venue is filled automatically, a route is inserted when a trustworthy route is available, and an unresolved/unsafe result asks or remains visibly partial. A successful OpenPOI/Transit result must emit zero Google fallback calls. A provider outage must not trigger parallel Google calls or an unbounded retry storm.

The implementation now allows coordinate-ready Japan Transit to run without a `mapsKey`; address geocoding and Google fallback remain explicitly configured and budget-authorized. The location resolver currently uses OpenPOI `/v1/search` rather than an autocomplete surface. If a future UI adds an address search box, use OpenPOI `/v1/suggest`; do not emulate autocomplete against public Nominatim.

### Cost model and target

The September settled Google service totals are the comparison baseline: Places ¥9,419.856821, Geocoding ¥7,493.014626, Directions ¥3,271.171127, Gemini ¥5,160.873099, and KMS/Storage/Run approximately ¥9.54 pre-tax. The following is a **planning budget**, not a settled invoice:

| layer | current baseline | target budget after this design | gate |
|---|---:|---:|---|
| OpenPOI POI primary | Places cost is currently Google-backed | ¥0 provider fee | attribution and health receipt |
| Japan Transit primary | Directions cost is currently Google-backed | ¥0 provider fee | timeout + cache + unofficial warning |
| Google Places fallback | part of September Places total | ≤¥500/month per tenant | 100 fallback requests/month or lower, whichever trips first |
| Google route fallback | part of September Directions total | ≤¥300/month per tenant | 100 fallback requests/month or lower, whichever trips first |
| Google Geocoding fallback | September ¥7,493.01 | ¥100–¥800/month after cache | 200 uncached addresses/month until benchmark winner |
| Gemini | September ¥5,160.87 account-level baseline | ¥5,000–¥6,000 while current path remains | nonessential calls budgeted; voice/high-risk separate |
| fixed Google services | about ¥10 | about ¥10 | settled CSV |
| total Google target | ¥27,889 tax-included September invoice | roughly ¥5,500–¥7,500 pre-tax / ¥6,000–¥8,300 tax-included | seven natural periods + official CSV |

Best case is a cache hit and successful free primary on nearly every Japan request. Base case retains small fallback/geocode spend and the current Gemini cost. Worst case is provider outage or traffic growth returning the account to the September baseline; budget gates must stop nonessential Google calls before that happens. Google Maps pricing remains SKU/free-cap/volume-tier based, so these caps are safety budgets, not promises of free usage ([official pricing](https://developers.google.com/maps/billing-and-pricing/pricing)).

### Ordered provider-cost TODO

1. **[x] Routing policy seam:** coordinate-ready Japan Transit runs without a Google key; non-Japan/address-only requests return typed `provider_unconfigured` rather than silently failing.
2. **[x] UX and attribution:** OpenPOI licenses/attributions and provenance are retained; incomplete attribution is rejected. Add `/v1/suggest` only when an actual input-completion surface exists.
3. **[x] Geocoder benchmark artifact:** the fixed Japan corpus and provider-level accuracy/resource scoring run fail-closed; the current result is `no_winner`, so Google is not replaced.
4. **[x] Route benchmark artifact:** Transit/OTP/OSRM/Valhalla rows and operating-cost fields are recorded; no production cutover is claimed from benchmark evidence alone.
5. **[x] Explicit budget policy:** per-tenant daily/monthly caps and typed fallback telemetry are enforced; durable authorizer read failure denies non-cache paid work.
6. **[x] LLM cost gate:** the existing local-model shadow scorecard is fail-closed; current recommendation is `keep_current` until a receipt-backed, non-inferior candidate exists.
7. **[ ] CFO acceptance:** rerun the B7 report with fresh provider receipts, observe seven consecutive daily closes, reconcile the October Cost Table, and only then update the target from estimate to measured actual.

This provider-cost sequence is additive to Section 11's personal-MUFG and external-settlement TODOs. Those financial source gaps remain required for a complete CFO report even if provider API cost reaches the target.

## 13. Provider-cost implementation cursor

The first six provider-cost tasks are now implemented on the dedicated branch: the production scheduler reaches coordinate-ready Japan Transit without a Google key; a Supabase-backed daily/monthly provider authorizer denies paid work when usage readback fails, is malformed, or caps are exceeded; Transit timeout/malformed states emit typed observations before one fallback; OpenPOI incomplete attribution is rejected, complete provenance is durably retained, and free-primary usage is recorded; geocoder and routing benchmark runners measure corpus-level accuracy/resource evidence; provider caps and fallback telemetry are enforced; the Financial Manager reads the tenant-bound `lm_provider_lane_summary` RPC into bounded `poi`/`transit`/`geocoder` lane evidence; scheduler ask paths carry the usage writer; and the local-LLM scorecard treats missing cost as unknown and refuses an unconfigured, slower, privacy-unknown, lower-quality, or receipt-incomplete candidate. The migration must be applied before the production lane gate can become fresh. Focused tests and the existing Life Manager suite remain green (the current suite is 188/188 PASS; the CFO Python suite is 249/249 PASS).

The current acceptance cursor is:

1. **[x]** rerun all provider benchmark and CFO suites after the variance/gate changes;
2. **[x]** wire provider-lane usage readback and OpenPOI free-primary usage into the report; retain the geocoder `no_winner` and LLM `keep_current` evidence until an approved read-only endpoint or existing model-routing shadow produces receipts;
3. observe seven real daily closes with fresh source rows, settled Google billing, provider-lane cap receipts, and replay-zero;
4. only then promote a benchmark winner or claim the ¥5,500–¥7,500 pre-tax planning target as measured actual; and
5. separately close Section 11's MUFG and external settlement gaps before marking the CFO report complete.

The latest evidence bundle is `docs/evidence/cfo/2026-10-03-provider-cost-selection.md`. Synthetic seven-day rows prove gate behavior only; they are not elapsed production observation.
