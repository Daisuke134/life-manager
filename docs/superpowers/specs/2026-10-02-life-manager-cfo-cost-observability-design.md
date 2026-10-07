# Life Manager CFO and Provider Cost Observability Design

Status: current design reference; implementation state, cursor, and ordered TODOs are maintained only in [the unified SSOT](2026-09-25-life-manager-unified-ssot.md)
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

- The official September 2026 Google Cloud Cost Table CSV reports ¥27,889 including tax: ¥25,354 invoice-rounded usage subtotal plus ¥2,535 tax. Its unrounded usage total is ¥25,354.451251 with a -¥0.451251 rounding adjustment. This is billed invoice evidence, not proof that payment settled. Source: [Google Cloud Cost Table](https://docs.cloud.google.com/billing/docs/how-to/cost-table).
- The CSV's rounded service-cost rows are Places API ¥9,420, Geocoding API ¥7,493, Gemini API ¥5,159, Directions API ¥3,271, and Cloud KMS ¥10. These displayed rows total ¥25,353 because row rounding differs by ¥1 from the invoice subtotal; do not present their sum as the invoice amount. A displayed ¥0 row is not proof of zero unrounded cost.
- Read-only `serviceruntime.googleapis.com/api/request_count` Monitoring observations were Geocoding 22,348, Places 6,580, and Directions 15,092 over `2026-08-31T00:00:00Z`–`2026-10-01T00:00:00Z` (31 days). This interval is not the September invoice period, and request counts are not SKU billable quantities or loop attribution. The Google CSV reports 19,403 Geocoding requests and 14,105 Directions requests; the difference is unresolved, not evidence of free errors or overbilling. Source: [Cloud Monitoring time-series API](https://cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.timeSeries/list).
- A Moneytree read returned one MUFG JPY savings balance of ¥504,302, but no upstream sync timestamp; the latest transaction date was 2026-08-25 and a September transaction query returned no rows. Treat the balance as last-known with freshness unknown, not today's confirmed balance or September spending of ¥0.

### Code gaps

- Mainline now has a Moneytree projection in the CFO report source path, but a successful natural report receipt/readback containing a fresh MUFG balance is not yet verified. The last-known balance above cannot satisfy that acceptance.
- The report still lacks a verified join from the official Google invoice's project/SKU/service rows to the specific provider operations, Life Manager loops, and report receipt. Monitoring counts alone cannot fill that join.
- A persistent geocode cache is wired into the production source, but the post-restart natural route/cache-hit/replay-zero acceptance is unverified. Free-provider fallback is a separate route optimization; it does not prove end-to-end cost reduction until its code is integrated and its natural UX/readback is observed.
- Cost visibility and spend policy must keep actual invoice charges, estimates, and unknown attribution separate. A Google invoice total is not yet a measured per-loop cost or a daily CFO report receipt.

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

**A4.2 scope:** this is a behind-the-scenes geocoding fallback for eligible Japanese address/facility lookups, not a new CFO screen and not a replacement for every Google API. An exact, attributable free result can avoid a Google Geocoding request; an ambiguous, invalid, or unavailable result keeps the existing route UX and falls back to Google Geocoding once. It does not replace Google Places, Directions/Routes, or Gemini, and the September bill shows Places—not Geocoding—as the largest individual service. Therefore A4.2 can reduce only its eligible Geocoding share; the remaining Google services need their own usage attribution and optimization.

## 9. Delivery scope by design phase

This section defines phase scope and acceptance intent, not the live TODO order or completion status. The unified SSOT is the sole source for the active cursor and remaining work.

### A0 — Spec and ownership

- approve this design;
- review existing Cost Guard and Finance specs for overlap;
- write the implementation plan only after this spec is accepted;
- record file ownership and excluded files in the plan.

### A1 — Observation envelope (operational; hardening remains)

The production observation path is active; the 2026-10-06 read-only evidence shows no A1-caused outage or confirmed row mutation. A1 is not a current production issue and does not block A2–A10. The advertised REST `PATCH`/`DELETE` methods do not prove that rows were changed; the inspected application path writes with `POST` and reads with `GET`, while production ACL/trigger state remains unverified. Keep that missing readback, the canonical wake/voice/provider-cost join, and crash/stale/`effect_unknown` lifecycle evidence as non-blocking audit hardening in the unified SSOT. Missing `loop_id` and actual billing attribution are cost-coverage gaps owned by A2/A6/A8, not evidence that A1 observation is down. Do not backfill historical rows by inference.

The A1 acceptance contract is schema validation, append-only storage, secret/PII redaction, and evidence for success, timeout, provider failure, crash, stale, and `effect_unknown` outcomes. The remaining production verification status is in the unified SSOT; these acceptance items are not the active cursor.

### A2 — Cost ledger

- extend provider cost rows with provider, SKU, operation, quantity, estimate, actual, billing status, and pricing version;
- keep the existing `lm_api_cost` table: `quantity` and `est_usd` remain nullable columns; provider, SKU, operation, actual amount, billing status, pricing version, and currency go in existing `meta` JSONB. Do not add a table or migration for A2;
- reject missing actual billing as zero;
- make failed ledger writes visible to the owner.

### A3 — Geocode and route reuse

- persist successful geocodes;
- persist route results with tenant/event/time/mode/provider identity;
- prove repeated scheduler ticks create zero duplicate paid calls;
- preserve cache reads in degraded/stopped budget states.

Implementation boundary for A3:

- Keep the existing `lm_route_cache` route-result store and its tenant/provider/mode/timezone/event scope. Do not create a second route cache or change Transit-first → one sequential Google fallback.
- Add a private `lm_geocode_cache` store for successful coordinates. Key by tenant, geocoder provider, and a keyed digest of the NFKC/trim/whitespace-normalized address; persist only `lat`, `lon`, `computed_at`, and TTL, never the raw address, event title, provider response, or API credential.
- Preserve the current 24-hour successful-geocode TTL and process-local transient/negative memo. Persist only provider-success coordinates that are finite and within latitude/longitude bounds; cache-store read/write failure is a miss/fallback and must not change the user's result flow.
- Deduplicate concurrent same-process geocodes by scoped key. Do not claim distributed exactly-once for simultaneous cold misses across independent processes; the scheduled single-owner path and later natural repeated ticks are the acceptance target.
- Retain the current hashed event/anchor/endpoint/purpose dimensions and add timezone, arrival/departure direction, and a routing-policy version to route `event_version`, so the early persistent event lookup cannot bypass the coordinate cache's scope. Keep the route cache's existing provider and mode identity.
- Add the 64-hex opaque `event_version` to route/geocode usage metadata for correlation; never persist the raw Calendar event ID, address, or full route cache key in cost rows or logs.
- Verify a durable success survives a fresh cache/store instance and produces zero additional Google calls for an equivalent normalized address within TTL; verify tenant/provider isolation, TTL expiry, valid-coordinate checks, secret/PII exclusion, route-cache hit before reservation, and unchanged route/fallback UX.
- A3 source acceptance is focused tests plus main deployment and natural readback showing stable same-tenant/same-`event_version` repeated ticks add zero paid provider rows after the first computation. Settled Google invoice reconciliation remains A6; the seven-day cross-loop finance close remains A10.

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

## 10. Status ownership

This document defines the target design and A0–A10 acceptance criteria. The current implementation state, evidence, blockers, and active cursor are maintained only in `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` (CFO section). A source merge alone does not satisfy production acceptance; use the unified SSOT for the current gate.
