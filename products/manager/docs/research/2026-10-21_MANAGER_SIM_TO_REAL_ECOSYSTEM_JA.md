# Manager Research — Simulation, Markets, Reality and Causal Blessings
**2026-10-21 JST · version 1 · original source-backed research · no actual interventions executed**

**Question:** Which existing environments, marketplaces, RCT methods and field deployments can Manager reuse to go from offline decision-making to provably positive net-world impact without inventing a simulator, a payment protocol or a marketplace? **Answer:** Reuse different proven pieces, not one universal environment. The missing layer is a robust *controlled sim-to-real contract with independent real outcome/counterfactual*, not another prompt loop. Each example has an evidence boundary.

## 1. Reaffirm the mission and the central falsifiable claim

Manager (Anicca) aims to minimize avoidable harms and improve beneficiaries' objectively measurable welfare across independent domains, without a human in the routine execution loop **only inside verified lawful, revocable, scoped pre-existing rights**. Digital Buddha/AGI is a long-term metaphor, not achieved capability or omniscience. `products/manager/` remains architecturally and operationally independent of Life Manager: different accounts, runtime, data, permissions and SSOT.

```text
PUBLIC SOURCE/RIGHTS -> OBSERVATION (unit/time/missingness)
 -> WORLD STATE -> MULTIPLE CAUSAL HYPOTHESES
 -> ACTIONS + NO_ACTION -> PREDICTION FIT != CAUSAL TREATMENT EFFECT
 -> VERIFIED OWNER RIGHT/SCOPE/BUDGET -> DURABLE INTENT/AT-MOST-ONCE DISPATCH
 -> PROVIDER RECONCILIATION (PRESENT/ABSENT/UNKNOWN)
 -> INDEPENDENT READBACK -> PREREGISTERED COUNTERFACTUAL
 -> NET WELFARE, COST, HARMS, DISPLACEMENT, UNCERTAINTY
 -> LEARNING UNDER HOLDOUT/SHADOW/ROLLBACK -> CHALLENGEABLE BLESSING
```

Use three *separate scorecards*: (A) simulation engineering performance, (B) real externally settled task/financial outcome, and (C) beneficiary causal net effect. Scores cannot be silently summed into one number or upgraded from P0 to P4.

## 2. What has been done in the world: different trajectories, no magical universal market

| Trajectory and original evidence | What is actually achieved/reusable | What is not proven; reuse decision |
|---|---|---|
| [Andon Labs Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2) | Year-long simulated vending-business challenge, supplier negotiation, delayed delivery, complaints, inventory, bankruptcy, profit-and-cost leaderboard. Excellent long-horizon planner stress cases | Simulated cash is not earned money, settled revenue, user benefit or physical production; use test protocol, not model rankings as welfare |
| [ProsusAI vending-bench](https://github.com/ProsusAI/vending-bench) (Apache-2.0) | Inspectable MCP economy (6 machines/3 locations, 30 days + 365-day variant, 22 tools, seeded replays), documented model/tool costs vs in-game balance | Do not copy entire simulator into Manager; run as an **external optional sandbox**, pin version, costs and seed, check its independent license notices |
| [Anthropic/Andon Project Vend 1](https://www.anthropic.com/research/project-vend-1) (2025-06-27) | Actual SF office mini-store managed by Claude, web search, email, price/product choices, physical workers doing restock. Reported poor business performance and red-team susceptibility | Human physical operators are real loop components, original shop was not unattended robot/welfare proof, no causal counterfactual |
| [Project Vend 2](https://www.anthropic.com/research/project-vend-2) (2025-12-18) | Different models, better systems, additional locations, Anthropic-reported operating improvement and continued adversarial weakness | Reporting company profit trajectory is not independently tested P4 social benefit; useful real-world failure modes |
| [OSWorld](https://os-world.github.io/) / [BrowserGym](https://github.com/ServiceNow/BrowserGym) / [TheAgentCompany](https://github.com/TheAgentCompany/TheAgentCompany) | Diverse desktop, browser and fictional enterprise workflows to test agent interactions with stateful tools, permission and timing failures | Mock UI goal completion not autonomous real salary, beneficial labor or official provider approval |
| [SWE-Lancer](https://openai.com/index/swe-lancer/) / [GDPval](https://openai.com/index/gdpval/) | Real economically valued historical freelance tasks vs expert-reviewed occupational deliverables; helps evaluate **quality** before field exposure | Historic bounty valuations are not payouts earned by Manager; human reviewer agreement not verified recipient welfare |
| [Concordia](https://github.com/google-deepmind/concordia), [BEHAVIOR](https://behavior.stanford.edu/), [Isaac Lab](https://isaac-sim.github.io/IsaacLab/), [LeRobot](https://github.com/huggingface/lerobot) | Simulated social decisions, household physics, robotics environments; each permits offline hazard rehearsal | Fictional humans, simulated robots and synthetic sensors not evidence that real-world interventions reduce harm |
| [Fetch.ai Agentverse](https://docs.agentverse.ai/documentation/agent-discovery/setup-guide), [Olas Mech](https://docs.olas.network/) | Existing *agent marketplace* mechanisms for discoverability, service offers, external invocation and machine-to-machine payment | Agent listing/transaction fee/token reward does NOT equal approved customer result, independent net money or welfare; real wallet/scope/terms required |
| [Algora](https://algora.io/pricing/) / [Algora API](https://api.docs.algora.io/) | Existing public GitHub bounty/maintainer acceptance/payout workflow; read-only research can observe issue+PR+published result | Submitted PR ≠ accepted PR ≠ settled payout ≠ welfare gain. Do not submit spam or infer contributor payout rights |
| [Shopify dev stores](https://shopify.dev/docs/apps/build/stores/development-stores) | Owned realistic commerce sandbox with test orders and API tool contracts | Official Shopify docs: cannot run live transactions; use separate actual merchant scope and provider settlement for real proof |
| [OpenAQ measurement API](https://docs.openaq.org/resources/measurements) | Sensors’ dated measurements, hourly/daily aggregates, upstream provider source. Can ground read-only outdoor world state | Requires API key and license checks; “latest” may not reflect complete time series. Outside air != indoor exposure; no physical actuator grant |
| [Hillstrom MineThatData 2008](https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html) original author publication | Real 64,000-customer randomized marketing experiment: men/women email treatment or no-email; 2-week visits/conversions/spend. Offers real treatment-effect *methodology* separate from behavioral imitation | Historical ecommerce—not Manager-caused benefit. Raw historical customer rows should not be mirrored publicly; redistribution/rights need review first |
| [Criteo uplift](https://ailab.criteo.com/criteo-uplift-prediction-dataset/) | Very large randomized-incrementality dataset, 25m rows, anonymized projected features; possible uplift evaluation methods | Publisher warns nonuniform sampling masks true original incrementality; CC BY-NC-SA means **do not assume product/commercial reuse** |
| [DoWhy](https://www.pywhy.org/dowhy/) / [EconML](https://www.pywhy.org/EconML/) | Causal graph, estimand identification, assumption refutation and heterogeneous treatment-effects libraries | A library producing a confidence interval does not provide randomization, guarantee valid assumptions or eliminate selection bias |
| [Behavior Change for Good megastudy](https://www.nature.com/articles/s41586-021-04128-4) | Real prospectively compared different behavior intervention messages with a common control and outcome; strong experimental-design precedent | Evidence for original enrolled populations/treatments only, not universal transferable welfare or Manager interventions |

## 3. Why marketplace ≠ our product (and when to make one)

Existing markets solve **task discovery** (Agentverse/Mech), **worker/bounty acceptance** (Algora), **commerce tooling** (Shopify) and **machine payment** (x402 and other providers). None guarantees independent scientific evaluation of beneficiary outcomes. Manager should be a *permissioned beneficial-intervention protocol* that can operate across existing services, not become a two-sided marketplace immediately.

**Reuse now:** MCP agents/workflows; lawful read-only external catalogs; controlled test merchants; open benchmarks; real third-party verification interfaces. Build only minimal adapters enforcing provenance, real authority, P0..P4 separation, cost/harms, trace and revocation. **Consider a new marketplace only after** multiple independent operators and verifiers need standardized contracts that existing markets cannot satisfy; the opportunity must survive actual willingness-to-pay/beneficiary evidence.

## 4. A credible sim -> shadow -> real pipeline

1. **Theory/causal preregistration:** Define affected unit, outcome, time window, side effects, spillovers, baseline NO_ACTION and credible experimental/randomized or justified control, primary and secondary estimands, sample/power and stop rule *before* seeing outcomes. Include negative impact scenarios.
2. **Simulator competence:** Pin ProsusAI/OSWorld/Concordia versions and seeds; adversarial supplier/provider timeouts, forgeries, replay, reward hacking, hidden worker costs, third-party consent violations, distribution shift and failed tool calls. Track model/API dollar cost separately. Score remains P0.
3. **Empirical causal-science reproduction:** Source-rights review Hillstrom before any locally ephemeral dataset ingestion; predefine randomization contrasts and recompute uncertainty, negative/null findings, unit of randomization; compare to original author. Historical trial never becomes current Manager welfare.
4. **Read-only field shadow:** Actually read public external API snapshots with proper license/API permission and independent observer. Register source URL/hash/time, diagnostics and hypothetical NO_ACTION actions; **do not execute**. Verify provenance and comparator availability first.
5. **Capability/rights admission:** Owner or third-party issuer grants exactly one bounded, revocable scope with budget/time; actual signature/credential custody not inside model context. If rights absent, remain REJECTED/NO_ACTION; founder's blanket research approval does not grant third-party accounts.
6. **Bounded pilot:** Pre-register, isolate a single reversible and low-harm permitted effect, reserve budget/intent durably, verify provider receipt and reconcile UNKNOWN on timeout without blind retry. For physical effect, documented property owner permission and independent sensor required.
7. **Independent outcomes and causal analysis:** Compare with NO_ACTION/cohort under a valid assignment/identification strategy; measure net beneficiary improvement, compute/physical/labor costs, spillover, harm, uncertainty and true denominators; negative or inconclusive must be published as such.
8. **Promotion only after evidence:** Versioned candidate policy in shadow; holdout on unseen time/market/population/region, rollback on degradation. Replicate in truly different domains. Public card has accessible original sources, action record, independent verifier and challenge mechanism.

**Claim hierarchy:** P0 synthetic/offline ; P1 authenticated externally effected receipt ; P2 independent observed field change ; P3 measured beneficiary improvement ; P4 valid causal net improvement ; P5 replication across distinct contexts. Never convert P0 to P4 for passing a software test. **All phases to date have zero Manager-verified P1+ Blessings.**

## 5. First 3 vertical designs

| First wedge | Read-only inputs | First potential action requiring rights | Independent outcome | Counterfactual / harm |
|---|---|---|---|---|
| Bounded own digital business | Public product/market terms, optional owner-authorized aggregate stores | Merchant-owned, explicit limited copy/timing modification only with verified grant | External real orders **settled** with refunds/fees/time, not simulated checkout | Preallocated products/cohorts/time; cannibalization, customer complaints, workload |
| Environmental exposure | Licensed OpenAQ provider measurements (outdoor ambient), weather, public regulatory sources | Facility-owner-approved, low-risk indoor purification/actuator only | Calibrated independent *indoor* PM2.5, power meter, dB, timestamp | Randomized room/time crossover, outdoor/weather adjustment; noise, energy, occupant impact |
| Work/OSS bounties | Published open issues, Algora terms, project docs | Owner-authorized user/maintainer accepted contributor operation | Merged approved artifact + independently confirmed payout; quality/displacement | Randomized or matched assistance conditions, refund/repair, work time and fees |

A fourth cause, charity/benefit access, may deliver high welfare but is **blocked** until external financial/agency rights and ethical recipient evidence. Current F004/F007 must remain blocked.

## 6. Scientific pitfalls and negative evidence

- Confusing (P(Y|X)) from simulation with (E[Y(1)-Y(0)]) from an intervention is a causal fallacy. Requires randomized assignment/identification assumptions, overlap, uncertainty and stability tests.
- Criteo’s public dataset deliberately destroys original true lift through subsampling. An uplift estimator can still benchmark rank, but cannot reconstruct original truth from released rows alone.
- A completed historic SWE-Lancer coding challenge is not cash in the Manager’s bank; a Shopify dev store “order” is not a real receipt; Agentverse listing is not welfare improvement; an OpenAQ ambient reading is not lower indoor PM2.5.
- Published individual respondent rows or health/sensitive profiles should not be copied into Manager Git. Rights and privacy are assessed per source, not by mere public reachability.
- Provider availability, rights/authentication, settlement, experiment-valid effects and independent beneficiaries must all be reported separately; **unavailable ≠ zero**, **unknown ≠ success**, **negative ≠ secretly dropped**.

## 7. Exact canonical task consequences

- `F001` (Phase06): [opportunity matrix](../product/OPPORTUNITIES.md) now lists operators, source rights, efficacy metrics, independent external verification prospects, feasibility and explicit blockers for each finance/environment candidate; no pilot claim without permissions.
- `U001` (Phase08): 7 separate beneficiary/harms mechanisms, public observations, operator permissions, comparison approaches; each comparison includes NO_ACTION and unproven results.
- `F002`, `F003`, `U002`, `U003` and other tasks are **NOT closed** by literature search or writing this note. F002 requires a specific preregistered study. F003 requires independent third-party real public ledger readback, not a fake fixture. U002 requires consented live interviews; U003 its resulting selection. F004 and F007 remain blocked.
- Historical H005 is an explicitly documented scientific **SKIP**. Scientific Gate1 requires a new legitimately reproducible dataset/protocol or original missing fields, never claiming the exact original HeartSteps sample was recovered.

The definitive ordered list/status of 113 tasks remains **ONLY** [tasks.json](../roadmap/tasks.json). Additional research backlog narrative must not duplicate its status authority.
