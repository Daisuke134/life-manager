# Life Manager Provider Cost Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve Life Manager's calendar/location UX while making Japan POI/transit calls free-first, bounding every paid fallback, and producing source-backed CFO cost evidence.

**Architecture:** Keep the existing OpenPOI and Transit adapters as the free primary lane, fix the route entry gate so coordinate-ready Japan transit does not require a Google key, and keep Google as a sequential budget-authorized fallback. Benchmark geocoding and driving/transit OSS candidates offline/read-only before any production switch; evaluate local LLM routing separately without inventing a second model adapter.

**Tech Stack:** Node.js CommonJS, `node:test`, existing Supabase route/geocode caches, existing provider-cost ledger and budget governor, read-only HTTP probes, deterministic JSON benchmark fixtures, Python `skills/cfo/loop_pnl.py` receipts, and existing CFO daily report delivery.

**Spec:** `docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md` (Section 12)

**Execution status (2026-10-04):** Tasks 1–6 are implemented on the dedicated branch, not merged/deployed. Task 7 is partial: the September Cost Table is reconciled; tenant cost estimates total USD 4.596581116667 for 2026-10-01 00:00 through 2026-10-04 08:44 JST, while the lane RPC returns `PGRST202` and event metadata lacks loop/actual-billing status. Seven natural periods, fresh Moneytree data, October settlement, source settlement coverage, and production parity remain open. Moneytree My Account login succeeds and OpenAI read authorization is active, but the portal has no bank-sync control; the 09:23 JST plugin reread still ends at 2026-08-25. Issue #6549 remains open with no maintainer response; source/migration edits wait for approval. CFO admission is also mismatched: the registry marks it deterministic/borrow/support, and the 09:38 JST read found 8/8 finite-run slots occupied by revenue owners. Candidate fix after approval: reserve one existing slot for CFO (revenue cap 7, CFO priority critical_paid) without stopping owners. Full detail is in `docs/evidence/cfo/2026-10-04-cfo-capacity-admission-readback.md`. At pre-refresh HEAD `1178c99091`, the cost branch was pushed against `origin/main` `b7fb1dfa5a` (merge-base `bc0d1fa7`; 63 main-only / 82 branch-only commits). The earlier sync attempt targeted `5fc226d9`, conflicted in six paths, and was aborted cleanly. This refresh changes documentation/evidence only. Review fixes are in `930abbb6b4`; refreshed files are the CFO, Moneytree, provider-cost, B7, and mobile readbacks dated 2026-10-04.

## Global Constraints

- Unknown, stale, failed, and `effect_unknown` remain explicit; none may be rendered as zero.
- Free-provider success must produce zero paid fallback calls; fallback is sequential, budget-authorized, and observable.
- OpenPOI `licenses`/`attributions` are retained with every stored/displayed result; raw provider payloads and secrets are not persisted.
- Public Nominatim and Photon demo servers are not production dependencies; self-host candidates require measured resource and refresh evidence.
- Google Maps fallback caps are per tenant and expressed in both estimated USD and provider units; missing billing remains `unknown`, not zero.
- Gemini is not replaced by a new direct API adapter in this plan; any local-model switch requires a recorded quality/latency/privacy/cost evaluation.
- No production provider mutation, scheduler cutover, release apply, or cloud deployment occurs in benchmark tasks.
- Existing marketplace, Moneytree, Stripe, and release owners retain their state and external-effect boundaries.

## Review Focus

- **Missing Google key with a coordinate-ready Japan route:** Transit must still run; the request must not silently fail before the free provider is tried. Covered by Task 1.
- **Transit timeout or malformed route:** exactly one budget-authorized Google fallback is permitted, with a typed failure/readback and no parallel retry storm. Covered by Task 1 and Task 5.
- **POI result with incomplete attribution:** the venue may not be promoted to a source-backed result without `licenses`/`attributions` and the OpenPOI attribution URL. Covered by Task 2.
- **Geocoder candidate that is cheap but inaccurate or license-incompatible:** the benchmark must reject it before production selection. Covered by Task 3.
- **Local LLM that is cheap but degrades location/online decisions:** the evaluation must keep Gemini and produce a non-promotion verdict. Covered by Task 6.

---

### Task 1: Remove the free-transit Google-key gate and preserve sequential fallback

**Status:** complete (`6951527ef1`, with scheduler/authorizer hardening in `930abbb6b4`); focused 28/28 and full npm 188/188 pass.

**Files:**
- Modify: `apps/life-manager/lib/travel.js:472-545`
- Modify: `apps/life-manager/lib/transit.js`
- Test: `apps/life-manager/lib/travel-transit-wire.test.js`
- Test: `apps/life-manager/lib/travel.test.js`

**Interfaces:**
- Preserve `directionsRoute(src, dst, mapsKey, anchorAtMs, nowMs, departureMode, opts) -> route|null`.
- Add a pure internal gate `canAttemptFreeTransit(srcGeo, dstGeo) -> boolean` that depends only on coordinate validity and Japan bounds.
- A missing `mapsKey` may block address geocoding and Google fallback, but must not block Transit when both endpoints are already coordinates inside Japan.

- [x] **Step 1: Write failing tests.** Inject coordinate endpoints, no Google key, a successful Transit response, and a Google fallback spy. Assert Transit succeeds and Google calls equal zero. Add a malformed/timeout Transit fixture that asserts exactly one budget-authorized Google attempt when a key is present.
- [x] **Step 2: Run focused tests to verify RED.** Run `node --test lib/travel-transit-wire.test.js lib/travel.test.js`; expected failure is the current early `!mapsKey` return.
- [x] **Step 3: Implement the gate.** Move the key check after coordinate parsing; preserve the existing cache lookup, event anchor, tenant scope, and `provider_unconfigured` failure observation for requests that cannot geocode or fallback.
- [x] **Step 4: Run focused tests to verify GREEN.** Re-run the commands from Step 2 and assert no duplicate provider calls on cache replay.
- [x] **Step 5: Commit.** `git add apps/life-manager/lib/travel.js apps/life-manager/lib/transit.js apps/life-manager/lib/travel-transit-wire.test.js apps/life-manager/lib/travel.test.js && git commit -m "fix(life-manager): allow free transit without maps key"`.

### Task 2: Make OpenPOI attribution and location UX source-backed

**Status:** complete (`be5de8004e`, hardened in `930abbb6b4`); focused 7/7 and full npm 188/188 pass.

**Files:**
- Modify: `apps/life-manager/lib/place-search-openpoi.js`
- Modify: `apps/life-manager/lib/ask.js`
- Modify: `apps/life-manager/lib/places-memory.js`
- Test: `apps/life-manager/lib/place-search-openpoi.test.js`
- Test: `apps/life-manager/lib/ask-openpoi.test.js`

**Interfaces:**
- Extend `searchOpenPoi(query, options) -> { status, candidates, attributions, attributionUrl, observedAt }` with fixed `attributionUrl: "https://openpoiapi.com/attribution.html"` on successful or empty responses.
- Extend successful `agentResolveLocation()` results with `provider: "openpoi"|"google"|"memory"` and `attributionUrl` when the provider is OpenPOI.
- Preserve current user behavior: a known candidate fills the calendar; an unresolved candidate reaches the existing user question path.

- [x] **Step 1: Write failing tests.** Assert live-shaped OpenPOI success carries licenses/attributions/URL into the resolver result, an empty result is not a Google success, and a remembered place returns without any provider call.
- [x] **Step 2: Run focused tests to verify RED.** Run `node --test lib/place-search-openpoi.test.js lib/ask-openpoi.test.js`; expected failure is the missing attribution URL/provider fields.
- [x] **Step 3: Implement normalized source metadata.** Keep only allowlisted attribution metadata, preserve current candidate mapping, and do not add a new search provider or second memory store.
- [x] **Step 4: Run focused tests and the existing location resolver suite.** Verify OpenPOI success calls Google zero times and Google fallback remains budget-gated.
- [x] **Step 5: Commit.** `git add apps/life-manager/lib/place-search-openpoi.js apps/life-manager/lib/ask.js apps/life-manager/lib/places-memory.js apps/life-manager/lib/place-search-openpoi.test.js apps/life-manager/lib/ask-openpoi.test.js && git commit -m "feat(life-manager): carry OpenPOI attribution"`.

### Task 3: Build a bounded geocoder comparison artifact

**Status:** complete (`0cff346fea`, hardened in `930abbb6b4`); runner 3/3 and full npm 188/188 pass. No provider winner was promoted.

**Files:**
- Create: `apps/life-manager/scripts/provider-benchmark-geocoder.js`
- Create: `apps/life-manager/scripts/provider-benchmark-geocoder.test.js`
- Create: `apps/life-manager/fixtures/provider-benchmarks/japan-geocoder-cases.json`
- Create: `docs/evidence/cfo/2026-10-03-geocoder-provider-benchmark.md`

**Interfaces:**
- `runGeocoderBenchmark({ cases, providers, fetchImpl, now }) -> { schemaVersion, digest, rows, summary }`.
- Each row contains only `caseId`, provider, status, coordinate precision, latencyMs, attribution/licence refs, errorClass, observedAt, and releaseSha; no private address or credential.
- Providers under comparison: current Google Geocoding, Geoapify free plan, and one self-host candidate selected from Photon/Pelias after resource preflight. Public Nominatim/Photon demos are excluded by policy.

- [x] **Step 1: Write pure fixture tests.** Cover exact coordinate, city-level coordinate, no-result, timeout, quota response, missing attribution, and unsupported license cases; assert deterministic digest and fail-closed winner selection.
- [x] **Step 2: Run tests to verify RED.** Run `node --test scripts/provider-benchmark-geocoder.test.js`; expected failure is missing runner/schema.
- [x] **Step 3: Implement bounded benchmark runner.** Use a fixed non-private Japanese corpus, one request per provider/case, bounded timeout, no retries, and explicit provider terms/attribution metadata. Read credentials only from approved environment/SSOT; never write them to evidence.
- [x] **Step 4: Run read-only provider probes.** Save the evidence digest and source links; do not switch production routing from the result alone.
- [x] **Step 5: Commit the runner and fixture, not secrets or transient responses.** `git add apps/life-manager/scripts apps/life-manager/fixtures/provider-benchmarks docs/evidence/cfo/2026-10-03-geocoder-provider-benchmark.md && git commit -m "feat(cfo): benchmark geocoder providers"`.

### Task 4: Benchmark self-hosted driving and transit candidates

**Status:** complete (`ba24a8d7a7`); runner 4/4 and full npm 188/188 pass. Transit/OSRM evidence remains benchmark evidence, not a production cutover.

**Files:**
- Create: `apps/life-manager/scripts/provider-benchmark-routing.js`
- Create: `apps/life-manager/scripts/provider-benchmark-routing.test.js`
- Create: `apps/life-manager/fixtures/provider-benchmarks/japan-route-cases.json`
- Create: `docs/evidence/cfo/2026-10-03-routing-provider-benchmark.md`

**Interfaces:**
- `runRoutingBenchmark({ cases, providers, now }) -> { schemaVersion, digest, rows, summary }`.
- Provider rows record `provider`, `mode`, `routeStatus`, `durationSeconds`, `legCount`, `farePresent`, `latencyMs`, `dataUpdatedAt`, `resourceCost`, `licenseRefs`, and `errorClass`.
- Candidate order: current Transit API, OTP with explicit GTFS/OSM feed versions, OSRM for driving, then Valhalla only if OSRM lacks required route facts.

- [x] **Step 1: Write pure parser/contract tests.** Cover accepted route, no route, stale feed, timeout, unsupported mode, and fare/leg preservation.
- [x] **Step 2: Run tests to verify RED.** Run `node --test scripts/provider-benchmark-routing.test.js`.
- [x] **Step 3: Implement a read-only bounded runner.** Require an explicit endpoint/feed version for each candidate, cap calls and concurrency at one, and calculate operating cost from measured CPU/RAM/storage rather than treating self-hosting as zero.
- [x] **Step 4: Run the benchmark only against owned/local or documented public read-only endpoints.** No production scheduler or browser state is changed; save only normalized rows and source links.
- [x] **Step 5: Commit evidence and runner.** `git add apps/life-manager/scripts apps/life-manager/fixtures/provider-benchmarks docs/evidence/cfo/2026-10-03-routing-provider-benchmark.md && git commit -m "feat(cfo): benchmark routing providers"`.

### Task 5: Enforce explicit per-provider caps and fallback telemetry

**Status:** complete (`fbdc67a099`, hardened in `930abbb6b4`); focused 35/35 and full npm 188/188 pass.

**Files:**
- Modify: `apps/life-manager/lib/provider-budget.js`
- Modify: `apps/life-manager/lib/usage-event.js`
- Modify: `apps/life-manager/lib/travel.js`
- Modify: `apps/life-manager/lib/ask.js`
- Modify: `apps/life-manager/lib/financial-manager-report.js`
- Test: `apps/life-manager/lib/provider-budget.test.js`
- Test: `apps/life-manager/lib/usage-event.test.js`
- Test: `apps/life-manager/lib/travel-usage.test.js`

**Interfaces:**
- Add `defaultProviderCaps() -> { "google_maps:places_search": { dailyUsd: 0.50, monthlyUsd: 5, monthlyUnits: 100 }, "google_maps:route": { dailyUsd: 0.50, monthlyUsd: 5, monthlyUnits: 100 }, "google_maps:geocode": { dailyUsd: 0.50, monthlyUsd: 5, monthlyUnits: 200 }, "gemini:nonessential": { monthlyUsd: 5 } }`.
- Extend `evaluateProviderBudget({ measuredUsd, estimatedUsd, unknownCount, units, caps })` without breaking the existing `thresholds` argument; return `cap_exceeded` in `reasons` and `stopped` when a hard cap is exceeded.
- Every fallback deny/hit/success emits provider, operation, cap state, units, estimate, actual status, and `next_action` without secrets.

- [x] **Step 1: Write failing cap tests.** Pin daily/monthly currency caps, unit caps, unknown-cost degradation, essential cache reads, per-tenant isolation, and exact reason strings.
- [x] **Step 2: Run focused tests to verify RED.** Run `node --test lib/provider-budget.test.js lib/usage-event.test.js lib/travel-usage.test.js`.
- [x] **Step 3: Implement caps as additive policy.** Keep existing generic budget behavior, make the listed caps the default for nonessential Google work, and preserve cache reads at `stopped`.
- [x] **Step 4: Wire fallback calls and render cap state.** Google calls must be denied before network when the cap is exceeded; the CFO report must show fallback units, cache hits, estimated cost, settled cost, unknowns, and next action.
- [x] **Step 5: Run focused tests plus the current CFO/Node suites.** Confirm a fallback cap cannot be bypassed by a second scheduler tick.
- [x] **Step 6: Commit.** `git add apps/life-manager/lib && git commit -m "feat(cfo): cap paid provider fallbacks"`.

### Task 6: Evaluate local LLM routing without a blind production switch

**Status:** complete (`f91cafffaf`, hardened in `930abbb6b4`); runner 3/3 and full npm 188/188 pass. Recommendation remains `keep_current`.

**Files:**
- Create: `apps/life-manager/scripts/provider-benchmark-llm.js`
- Create: `apps/life-manager/scripts/provider-benchmark-llm.test.js`
- Create: `apps/life-manager/fixtures/provider-benchmarks/location-decision-cases.jsonl`
- Create: `docs/evidence/cfo/2026-10-03-llm-provider-benchmark.md`

**Interfaces:**
- `runLlmProviderBenchmark({ cases, candidates, runner, now }) -> { schemaVersion, digest, scores, recommendation }`.
- Each candidate must use an existing Life Manager model-routing boundary; the benchmark may compare Gemini with the existing local/Codex lane but must not add a direct Ollama/vLLM API adapter.
- Score exact location grounding, online/no-travel classification, ask-user precision, latency, estimated cost, privacy status, and receipt completeness.

- [x] **Step 1: Write evaluator tests.** Assert a cheaper but lower-quality candidate returns `keep_current`, missing receipts fail closed, and a non-inferior candidate returns `eligible_for_shadow` only.
- [x] **Step 2: Run tests to verify RED.** Run `node --test scripts/provider-benchmark-llm.test.js`.
- [x] **Step 3: Implement fixture runner and scorecard.** Keep prompts/cases scrubbed, use bounded calls, and record only normalized verdicts and cost/latency metadata.
- [x] **Step 4: Run shadow evaluation.** No user-facing routing change; save the scorecard and recommendation for review.
- [x] **Step 5: Commit evidence and runner.** `git add apps/life-manager/scripts apps/life-manager/fixtures/provider-benchmarks docs/evidence/cfo/2026-10-03-llm-provider-benchmark.md && git commit -m "feat(cfo): evaluate local LLM cost lane"`.

### Task 7: Close provider-cost acceptance with CFO readback

**Status:** partial (`a82e94ce33` plus current provider-lane plumbing). Synthetic acceptance, variance, durable observation state, official Moneytree readback, and usage-summary lane propagation are complete; live seven-period observation, October settlement, fresh Moneytree data, full B7 settlements, and production parity remain open. The 2026-10-04 Moneytree retry confirms all 183 returned rows stop at 2026-08-25 and the balance has no bank freshness cursor. The tenant ledger total reconciles, but lane-specific RPC lookup returns `PGRST202`; all usage amounts remain estimates and no loop/actual-billing attribution is present. A fresh project-level Monitoring read is in `docs/evidence/cfo/2026-10-04-google-monitoring-readback.md`; it finds 804 Directions 404s and no active Gemini GenerateContent metric descriptor, so official October Google spend remains unknown.

**Files:**
- Modify: `docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md`
- Create: `docs/evidence/cfo/2026-10-03-provider-cost-selection.md`
- Create: `apps/life-manager/lib/provider-lane-readback.js`
- Test: `apps/life-manager/lib/provider-lane-readback.test.js`
- Create: `apps/life-manager/migrations/2026-10-03-lm-provider-lane-summary.sql`
- Test: `apps/life-manager/lib/usage-summary-migration.test.js`
- Modify: `apps/life-manager/lib/financial-manager-ingest.js`
- Modify: `apps/life-manager/lib/financial-manager-runtime.js`
- Modify: `apps/life-manager/lib/financial-manager-report.js`
- Modify: `apps/life-manager/scripts/cfo-hourly-local.js`
- Test: `apps/life-manager/lib/financial-manager-ingest.test.js`
- Test: `apps/life-manager/lib/financial-manager-runtime.test.js`
- Test: `apps/life-manager/lib/financial-manager-report.test.js`
- Test: `apps/life-manager/scripts/cfo-hourly-local.test.js`
- Modify: `apps/life-manager/lib/ask.js`
- Test: `apps/life-manager/lib/ask-openpoi.test.js`
- Modify: `apps/life-manager/lib/provider-budget.js`
- Test: `apps/life-manager/lib/provider-budget.test.js`
- Modify: `apps/life-manager/scheduler.js`
- Test: `apps/life-manager/test/scheduler.test.js`
- Modify: `apps/life-manager/scripts/provider-benchmark-llm.js`
- Test: `apps/life-manager/scripts/provider-benchmark-llm.test.js`
- Modify: `apps/life-manager/scripts/cfo-natural-run.test.js`
- Test: `skills/cfo/test_loop_pnl.py`

**Interfaces:**
- The selection evidence contains candidate digests, provider terms/licence refs, benchmark release SHA, measured request counts, cache hit rate, fallback counts, budget transitions, settled Google CSV receipt, and a decision of `keep`, `shadow`, or `promote` for each capability.
- The natural-run harness adds provider lane states without changing B7 arithmetic or turning benchmark estimates into settled costs.

- [x] **Step 1: Write acceptance tests.** Cover a seven-period run with free-primary success, bounded fallback, stale benchmark evidence, and an official Cost Table variance; assert only fresh/settled rows close the gate.
- [x] **Step 2: Run the CFO and Life Manager focused suites.** Run `python3 -m unittest discover -s skills/cfo -p 'test_*.py'`, the provider benchmark tests, and `npm test` from `apps/life-manager`.
- [ ] **Step 3: Execute seven natural daily closes.** Record provider health, cache hits, paid fallback units, budget state, source freshness, official receipts, and replay-zero; do not change external marketplace or bank state.
- [ ] **Step 4: Read back the October Google Cost Table.** Reconcile estimates versus settled rows and keep any discrepancy as an explicit CFO gap.
- [x] **Step 5: Update the spec cursor and evidence.** Mark each candidate `proved`, `partial`, or `rejected` and retain the ordered financial TODOs from Section 11. The cursor remains partial until the external gates close.
- [x] **Step 6: Commit and push.** `git add docs/superpowers/specs docs/evidence/cfo apps/life-manager/scripts && git commit -m "docs(cfo): close provider cost selection"`.

## Verification Commands

```bash
cd apps/life-manager
node --test lib/travel-transit-wire.test.js lib/travel.test.js lib/place-search-openpoi.test.js lib/ask-openpoi.test.js
node --test scripts/provider-benchmark-geocoder.test.js scripts/provider-benchmark-routing.test.js scripts/provider-benchmark-llm.test.js
node --test lib/provider-budget.test.js lib/usage-event.test.js lib/travel-usage.test.js
python3 -m unittest discover -s skills/cfo -p 'test_*.py'
npm test
git diff --check
```
