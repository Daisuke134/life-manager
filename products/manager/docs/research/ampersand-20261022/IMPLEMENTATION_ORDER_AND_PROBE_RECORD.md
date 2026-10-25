# Ampersand × Manager — read-only feasibility evidence, ordered implementation backlog

**2026-10-22 JST | research-only | NOT FOR PUBLICATION**  
This document is intended to be reused in articles and books; no blog publishing workflow is changed or triggered intentionally. The owner explicitly changed the workflow to **save to GitHub, do not deploy articles until later**.

## Current verified status

- Upstream documentation reviewed: https://ampersand.humansand.ai/blog/ , model card, Persimmon release, Guides, API Reference, Pricing, OAPL, Simile, Aaru, Andon Labs.
- Ampersand model: `ampersand-v0.1`; base URL `https://ampersand.humansand.ai/v1`; bearer token; Agents API header `OpenAI-Beta: agents=v1` on session operations.
- Read-only research probe: `ampersand_readonly_probe.py`; unit tests: `test_ampersand_readonly_probe.py`.
- Actual local test run on 2026-10-22:
  ```sh
  cd products/manager/docs/research/ampersand-20261022
  python -m unittest -q test_ampersand_readonly_probe.py
  # Ran 12 tests; OK
  python ampersand_readonly_probe.py --offline
  # OFFLINE_ONLY, P0, authorized_execution=false, causal_support=false
  python ampersand_readonly_probe.py --check-access
  # BLOCKED_NO_API_KEY, exit 2; no network request, charge or actual inference
  ```
- **No AMPERSAND_API_KEY available** in test runtime; **0 authenticated inference calls** and **0 human studies**. The earlier unauthenticated `GET /v1/models` was HTTP 401. A mock shape/access-control test does *not* prove the real model would give accurate or safe recommendations.
- No external API tool was attached to the smoke payload; `environment.type=none`. A billable smoke is guarded by explicit `AMPERSAND_ALLOW_BILLABLE_PROBE=1` **and** a valid key. Do not store the key in GitHub or documentation.
- Real production integration into Manager is **not yet done**. This research probe is deliberately isolated from `manager_core.kernel` and cannot dispatch an intervention.
- Current original roadmap: `products/manager/docs/roadmap/tasks.json` **113 records: 69 done, 41 todo, 2 blocked, 1 skipped**. This list intentionally adds technical sequencing tasks without changing their status.

## Priority order: engineering that does not depend on real-world participants

### P0 — model-independent observation and trustworthy evidence
1. **Manager-OBS-01**: Implement a scheduled read-only observer for an allowlisted public source list, with fetch time, source URL, HTTP failure, content digest, license/privacy metadata; initial target owned pages + official public program information. Acceptance: repeated scrape yields no phantom changes; data is immutable and searchable. Existing components to reuse: `models/source.py`, `models/problem.py` and audit.
2. **Manager-OBS-02**: Normalize observations to typed `Problem` with units, timestamps, stale/missing reasons, versioned source hashes. Acceptance: duplicate, future-dated, stale (48h rule) and contradictory inputs fail closed; provenance never invented.
3. **Manager-OBS-03**: Record outcome and intended comparator BEFORE any proposal; separate page-content correctness from effects on beneficiaries. Acceptance: source hash and pre-registered outcome both available; never turn a page fix into a P3/P4 welfare claim.

### P1 — candidates and decision policy
4. **Manager-PLAN-01**: Add a deterministic no-effects baseline planner (PASS/ASK/PROPOSE/NO_ACTION) for a small public-page-maintenance fixture corpus. Acceptance: exact repeatability, traceable reason, mandatory NO_ACTION in `InterventionPlan`.
5. **Manager-PLAN-02**: Define a provider-neutral **advisory-only** interface accepting minimum context and returning typed candidate plan + source IDs + measured prompt/response cost; preserve existing `ManagerKernel` behavior. Acceptance: no tools/secret/operation authority in model adapter.
6. **Manager-PLAN-03**: Attach Ampersand as OPTIONAL adapter by official Agents API; keys from secret store at runtime, never code; create/retrieve sessions, parse saved result, handle `waiting`, `requires_action`, `failed`, silent output, timeouts, compaction and duplicate/unknown results. Acceptance: offline contract suite first, then one authenticated read-only smoke with a real tenant, explicit cost guard, and receipt.
7. **Manager-PLAN-04**: Strict host side validation and filtering: `source_ids` allowlist, external prompt injection barriers, JSON/type enforcement, context minimization, user-specific consent, redacted logging, fallback to deterministic/NO_ACTION. Acceptance: untrusted text cannot modify grant, budget, tools, prompt, rules or execution policies.
8. **Manager-PLAN-05**: Compare Ampersand / deterministic planner / existing alternative model using identical cases including changed goals, group privacy, interventions at wrong times, useful silence and contradictory sources. Acceptance: blinded held-out scoring with source factuality, error, undue advice, abstention precision, latency, API cost and security regressions. No provider promotion based solely on its benchmark.

### P2 — effects within currently authorized digital scope
9. **Manager-ACT-01**: Connect chosen *validated* proposals only to the existing owned-scope digital release planner, not arbitrary shell/bank/calendar actions. Acceptance: explicit grant/scope, risk/cost budget, prevention of duplicate effects, unknown provider status blocks further effects.
10. **Manager-VERIFY-01**: Link independent live readback to the canonical audit and `RunResult` record, with parent/child commit, source bytes/hash, run-id. Acceptance: real readback matches source, no silent success if missing.
11. **Manager-VERIFY-02**: Build immutable evidence history and a read-only Explorer for multiple runs with corrected/failed/missing entries and source rights. Acceptance: user can follow observation → proposal → authorization → execution → readback → analysis. Track public reliability separately from human benefit.
12. **Manager-LEARN-01**: Bridge independently observed outcomes (not model self-reports) to `PolicyLearner` shadow/holdout, with disjoint groups, OOD checks and kill-switch. Acceptance: objective regression rolls back; no model can change authority or expand exposure.
13. **Manager-STOP-01**: Test injection, reward hacking, nondeterministic duplicate calls, silence, fatigue/over-coaching, source staleness, model outage, input token/budget limit, rollback, denied consent. Acceptance: audit shows NO_ACTION or reject, not invented progress.

### P3 — validated human-outcome science and field activity (external gates)
14. **FIRST-WEDGE** (U002–U004): Obtain 5 consented stakeholder interviews; choose the beneficiary + operator + measured outcome with public data if possible; preregister outcome, sample, control, harm and withdrawal/stop conditions.
15. **FIELD-AUTHORITY** (F004/F007; blocked): Acquire **actual owner/operator permission**, funding and/or sensor-site access. No model's desire overrides human authority. This is a separate external gate; do not claim completion without evidence.
16. **FIELD-PILOT** (F005/F008/U006): Run *one* authorized, bounded experiment and independently read back P1 (execution) and P2 (change of state). Do not claim welfare causal improvement from mere action.
17. **OUTCOME-CAUSALITY** (F006/F009/U007; D001-D016): Pre-registered comparator and confidence intervals, null/negative evidence, displacement (not taking funding from another cause), time/energy/noise/cost, health vs exposure proxies, income actually settled vs merely quoted, mental health support with ethical review. Replicate where allowed.
18. **OUTCOME-BENCH** (V001–V006): Same kernel for three adapters; measure calibration MAE/TVD, treatment effect error, field readback and harms separately; country/time/population holdout, stage model promotion, publish only rights-cleared reproducible aggregate evidence, accumulate positive/negative/unknown outcomes.
19. **GOVERNANCE** (G001–G006): Ratify charter, human override, incident and appeal mechanism, consent revocation, external audit, least-privilege APIs, sustainably measured cost and beneficiary utility. Do not assert that all human suffering has ended.

### P4 — research, book, communications without automatic publishing
20. **CONTENT-LIBRARY** (C002/Y008): Keep source-linked English/Japanese book chapters, diagrams and failure logs in GitHub. Add provenance and errata. **No blog/social publishing; no auto-posting** absent a subsequent explicit request.
21. **OPTIONAL OUTREACH** (Y003/Y005/U008): YC application, research/stakeholder contacts or funding commitments require actual persons, submissions, and their informed authorization; proposal/notes may be prepared without claiming completion.

## Ampersand API reality, risks and pricing (source: 2026-10-22)

Endpoints/headers:
```text
GET  https://ampersand.humansand.ai/v1/models
POST https://ampersand.humansand.ai/v1/agents/sessions
Authorization: Bearer <SECRET>
OpenAI-Beta: agents=v1  # agent/session routes; /models exempt
environment: {"type":"none"}
agent.model: "ampersand-v0.1"
```
A session keeps history; model *weights* are not changed by each conversation. Tools run only in the host and must be permission checked. Tool-result events support Idempotency-Key, session creation does not. On uncertain writes, reconcile in durable outbox before any retry. The public text model does not offer hosted browser/MCP/auto-execution or hard-constrained JSON final output. Silent completion is an intentional state, not an error.

Public token pricing (Oct 2026, USD per 1M): uncached input $1, cached input $0.20, output including reasoning $5.20, plus any host-tool costs. A teaching budget for 12k uncached input + 3k output is $0.0276. Actual run price depends on generated reasoning/output, context and tool continuations.

## Evidence classes and publication discipline

- **P0**: source observations, plans, mock/test outputs and simulation — NO beneficiary change claim.
- **P1**: external evidence that an authorized action happened.
- **P2**: independent evidence that the target's state changed.
- **P3/P4**: credible comparator, net benefit and replicability, as the product's defined proof contract requires.
- **Never equate** more coherent synthetic humans (Persimmon), improved synthetic reward (Ampersand), calibrated surveys (Simile/Aaru), successful business operations (Andon), or compiled code (Manager) with evidence that a human's life improved.

## Sources

- https://ampersand.humansand.ai/blog/
- https://ampersand.humansand.ai/blog/model-card.html
- https://ampersand.humansand.ai/docs/GUIDES.html
- https://ampersand.humansand.ai/docs/API_REFERENCE.html
- https://ampersand.humansand.ai/docs/PRICING.html
- https://persimmon.humansand.ai/blog/persimmon.html
- https://arxiv.org/abs/2602.19362
- https://www.simile.com/blog/confidence
- https://aaru.com/publications/population-simulation-at-the-replication-floor-research
- https://andonlabs.com/publications
- https://andonlabs.com/blog/why-we-built-pion
- https://github.com/Daisuke134/life-manager/blob/research/manager-product-r006-20261020/products/manager/docs/roadmap/tasks.json

**Status semantics**: having code and a passing mock test is a software implementation step, not externally verified model ability. Explicit separate proof is required for every claimed source, operation and actual human benefit.
