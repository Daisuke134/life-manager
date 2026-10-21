# Manager — Opportunity Selection Matrix (F001 / U001)
**Date:** 2026-10-21. **Research-only, NOT authorization to act.** **Source of truth for task status remains** `docs/roadmap/tasks.json`. This document compares ways to run Manager in sandbox AND real world, with independent proof. Original sources are linked below. **NO_ACTION is the valid decision for every listed live action**, because actual grants, operators and outcome links are `NOT_VERIFIED`.

## Research interpretation and decision

**Most promising rapid learning:** (1) reproduce real historic randomized causal response data with immutable train/test/rights without intervening on people; (2) use ProsusAI Vending Bench, BrowserGym/OSWorld and realistic mock marketplaces for adversarial agent capabilities; (3) read-only verify concrete existing open finance / job bounty / air-quality data before any external effect; (4) choose the first owner-controlled, lawfully permitted real intervention based on granted capability, low harm and pre-registered independent readback. Three lanes run independently; none upgrades another to field proof.

A simulation score or marketplace listing is **P0**, not P4. A genuine externally confirmed action could eventually be P1; source-independent observed state might be P2; beneficiary outcome and credible net causal comparison with costs/harms could reach P3/P4. **Current welfare improvement: NOT_MEASURED.**

## Comparable opportunities

| ID | Beneficiary and harm mechanism | Source observation / data rights | Operator / action permission | Primary outcome / external evidence | Causal comparison | Verdict |
|---|---|---|---|---|---|---|
| `OWNED_STOREFRONT` | Consenting merchant and customers receiving genuine value, not only agent gross sales; Poor information/offer fit and avoidable operational costs can impair net financial results and buyer satisfaction | Shopify sandbox stores and public platform technical docs; actual merchant settlement records are separate and not public by default; **rights review pending** | Merchant legal account holder; no particular account or capability grant has been verified; **NOT_VERIFIED** | Incremental settled net contribution after purchase/refund, fees, compute, labor and displacement; complaints separately; independent: Official owner-approved settlement/payout or provider records corroborated by separate read-only source; none connected to Manager | Prospectively randomized product/cohort-level treatment vs no-action holdout; minimize spillovers and lock refund horizon | SANDBOX_ONLY; live **NO_ACTION** |
| `PUBLIC_OSS_BOUNTIES` | Project users and contributors who receive fair settled compensation and improvements; Unresolved public issues reduce access to reliable software and incomplete work produces no external income | Public issue/bounty metadata, maintainers' merge outcomes and published terms; public bounty amount is not a payout; **rights review pending** | Participating maintainer determines acceptance; contributor owns their payout account, no delegated financial capability; **NOT_VERIFIED** | Maintainer-accepted and deployed useful work; verified settled net payout minus compute/time/other opportunity cost; independent: Independent merged PR plus payment provider/recipient authorized payout confirmation; usually private settlement not publicly observable | Matched issue cohorts or prospectively randomized assistance, compare completion quality and cost; no guarantees of payment | READ_ONLY_RESEARCH; live **NO_ACTION** |
| `OPEN_LEDGER_SUPPORT` | Eligible recipients of legitimate public-interest assistance, plus donors supporting independently evidenced outcomes; Lack of affordable assistance may cause unmet needs; matching can displace funds rather than create net support | Published nonprofit/grant ledger and matched campaign rules; public records may not show recipient welfare; **rights review pending** | Grantee, fund sponsor and funding administrator; neither spend authority nor donor/recipient consent has been established; **NOT_VERIFIED** | Incremental external resources reaching beneficiaries net of seed capital, fees and offsetting donations, with welfare separately measured; independent: Original funding institution's ledger plus genuinely independent settlement and aggregate recipient results; no real pilot receipt available | Preregistered campaign/region randomized access or comparable cohorts including NO_ACTION and cross-charity substitution | BLOCKED_LIVE_EFFECT; live **NO_ACTION** |
| `AIR_QUALITY` | Occupants of a legitimate pilot facility and surrounding community when exposure decreases net of side effects; Harmful PM2.5 exposure may raise risk; outdoor air observations alone are not indoor exposure or clinical improvements | OpenAQ publicly indexed outdoor sensor readings, timestamps, sensor calibration flags and provider licensing; **rights review pending** | Facility property owner/operator and properly authorized independent sensor operator; none verified; **NOT_VERIFIED** | Preregistered indoor PM2.5 exposure change (µg/m³) plus kWh, noise, maintenance, harms and comfort; NOT direct disease reduction; independent: Timestamped calibrated indoor independent sensor, treatment log, outdoor background and power meter; no facility/sensor is connected | Randomized crossover/stepped-wedge room or timing assignment, controlled external ambient trends and carryover | BLOCKED_LIVE_EFFECT; live **NO_ACTION** |
| `PUBLIC_BENEFIT_ACCESS` | Eligible residents who actually receive additional legally owed support, not merely view an eligibility notice; Administrative complexity and information frictions can prevent timely access to support | Public benefit eligibility publications and anonymized published aggregate application/payment statistics where available; **rights review pending** | Public agency/consenting service provider and each affected individual; no private tax records or filing authority available; **NOT_VERIFIED** | Additional independently documented completed payments and benefits net of administrative burden, harms, eligibility errors; independent: Agency-authorized aggregate payout counts and ethically consented outcomes; individual records are not public evidence | Prospectively randomized eligible outreach assistance or approved quasi-experiment, preserving NO_ACTION and adverse outcomes | READ_ONLY_RESEARCH; live **NO_ACTION** |
| `AGENT_SERVICE_MARKETS` | Businesses receiving useful machine-produced services and potential end users affected by downstream work; Discovery and contracting friction can block specialized services; malicious agents create costs and security harms | Official Agentverse agent-discovery and Olas Mech service marketplace documentation; token transfers are not verified welfare; **rights review pending** | Only explicitly granted agent service publisher/buyer identity and bounded wallet owner; none delegated to Manager; **NOT_VERIFIED** | Third-party verified service acceptance/quality and externally settled revenue minus payments, compute, security losses; independent: Service provider/receiver independent receipt, signed service result and separately auditable settlement; no real transactions performed | Matched paid vs NO_ACTION service tasks; independent blinded quality review and cost/incident accounting | SANDBOX_ONLY; live **NO_ACTION** |
| `PHYSICAL_ASSISTANCE` | Workers, purchasers and customers when labor is fair and supplies reach the intended place; Resource allocation failures and stale inventory can prevent needed goods/services, but physical workers bear risk | Anthropic/Andon Project Vend physical office stocking experiment contrasted with Andon Labs' simulated economy; **rights review pending** | Facility/site owner, participating workers and commercial operator; none verified for Manager; **NOT_VERIFIED** | Externally verified job completed and net paid outcomes minus material, worker-time and negative incidents; independent: Independent inventory/readback and independently reconciled worker compensation; not a simulated vending balance | Preregistered crossover of eligible tasks with labor safety/no-action and worker consent; fairness/harm tracking | BLOCKED_LIVE_EFFECT; live **NO_ACTION** |

## Evidence and blockers by opportunity

### OWNED_STOREFRONT — Owner-scoped storefront outcome optimization
**Domain:** digital_commerce. **Operator:** Merchant legal account holder; no particular account or capability grant has been verified. **Feasibility:** SANDBOX_ONLY. **Live pilot authorized:** **NO**.
**What counts as a welfare outcome:** Incremental settled net contribution after purchase/refund, fees, compute, labor and displacement; complaints separately
**Source/reuse rule:** Source material identified on public official pages only; reuse, API licensing, retention and commercial rights require source-specific review before ingestion.
**Comparison:** Prospectively randomized product/cohort-level treatment vs no-action holdout; minimize spillovers and lock refund horizon
**What is still missing:** No verified own/merchant-scoped grant; Dev stores cannot process real payments; No verified real settlement readback; No preregistered experiment.
**Primary/source links:** [source](https://shopify.dev/docs/apps/build/stores/development-stores) · [source](https://www.anthropic.com/research/project-vend-2).

### PUBLIC_OSS_BOUNTIES — Verified real open-source work and outcome-based bounties
**Domain:** work. **Operator:** Participating maintainer determines acceptance; contributor owns their payout account, no delegated financial capability. **Feasibility:** READ_ONLY_RESEARCH. **Live pilot authorized:** **NO**.
**What counts as a welfare outcome:** Maintainer-accepted and deployed useful work; verified settled net payout minus compute/time/other opportunity cost
**Source/reuse rule:** Source material identified on public official pages only; reuse, API licensing, retention and commercial rights require source-specific review before ingestion.
**Comparison:** Matched issue cohorts or prospectively randomized assistance, compare completion quality and cost; no guarantees of payment
**What is still missing:** No verified contributor/maintainer permissions; No payout readback; Bounty listing is not approval/payment; Risk of public spam or low-quality PRs.
**Primary/source links:** [source](https://algora.io/pricing/) · [source](https://api.docs.algora.io/).

### OPEN_LEDGER_SUPPORT — Public charitable grant and matching transparency
**Domain:** finance. **Operator:** Grantee, fund sponsor and funding administrator; neither spend authority nor donor/recipient consent has been established. **Feasibility:** BLOCKED_LIVE_EFFECT. **Live pilot authorized:** **NO**.
**What counts as a welfare outcome:** Incremental external resources reaching beneficiaries net of seed capital, fees and offsetting donations, with welfare separately measured
**Source/reuse rule:** Source material identified on public official pages only; reuse, API licensing, retention and commercial rights require source-specific review before ingestion.
**Comparison:** Preregistered campaign/region randomized access or comparable cohorts including NO_ACTION and cross-charity substitution
**What is still missing:** No fund custody/issuer permission; Recipient or sponsor terms not approved; Public ledger does not equal welfare data; No credible real comparator.
**Primary/source links:** [source](https://opencollective.com/) · [source](https://www.aeaweb.org/articles?id=10.1257/aer.97.5.1774).

### AIR_QUALITY — Independent exposure outcome in an authorized physical space
**Domain:** environment. **Operator:** Facility property owner/operator and properly authorized independent sensor operator; none verified. **Feasibility:** BLOCKED_LIVE_EFFECT. **Live pilot authorized:** **NO**.
**What counts as a welfare outcome:** Preregistered indoor PM2.5 exposure change (µg/m³) plus kWh, noise, maintenance, harms and comfort; NOT direct disease reduction
**Source/reuse rule:** Source material identified on public official pages only; reuse, API licensing, retention and commercial rights require source-specific review before ingestion.
**Comparison:** Randomized crossover/stepped-wedge room or timing assignment, controlled external ambient trends and carryover
**What is still missing:** No facility/actuator rights; OpenAQ outdoor sensor does not certify indoor effects; No calibrated indoor readback; Potential worker/occupant safety concerns.
**Primary/source links:** [source](https://docs.openaq.org/resources/measurements) · [source](https://docs.openaq.org/api) · [source](https://pmc.ncbi.nlm.nih.gov/articles/PMC12234348/).

### PUBLIC_BENEFIT_ACCESS — Access to public benefits without unauthorized filing
**Domain:** public_services. **Operator:** Public agency/consenting service provider and each affected individual; no private tax records or filing authority available. **Feasibility:** READ_ONLY_RESEARCH. **Live pilot authorized:** **NO**.
**What counts as a welfare outcome:** Additional independently documented completed payments and benefits net of administrative burden, harms, eligibility errors
**Source/reuse rule:** Source material identified on public official pages only; reuse, API licensing, retention and commercial rights require source-specific review before ingestion.
**Comparison:** Prospectively randomized eligible outreach assistance or approved quasi-experiment, preserving NO_ACTION and adverse outcomes
**What is still missing:** No agency/individual mandate; Sensitive eligibility data forbidden; Historical RCTs conflict on intervention efficacy; No accessible independent payout data.
**Primary/source links:** [source](https://www.aeaweb.org/articles?id=10.1257/aer.20121493) · [source](https://www.aeaweb.org/articles?id=10.1257/pol.20200603).

### AGENT_SERVICE_MARKETS — Agent-discovery and machine-paid service procurement
**Domain:** agent_economy. **Operator:** Only explicitly granted agent service publisher/buyer identity and bounded wallet owner; none delegated to Manager. **Feasibility:** SANDBOX_ONLY. **Live pilot authorized:** **NO**.
**What counts as a welfare outcome:** Third-party verified service acceptance/quality and externally settled revenue minus payments, compute, security losses
**Source/reuse rule:** Source material identified on public official pages only; reuse, API licensing, retention and commercial rights require source-specific review before ingestion.
**Comparison:** Matched paid vs NO_ACTION service tasks; independent blinded quality review and cost/incident accounting
**What is still missing:** Wallet/token rights not granted; Counterparty identity and terms not verified; Marketplace incentives not proof of social benefit; No independent payout/quality evaluation.
**Primary/source links:** [source](https://docs.agentverse.ai/documentation/agent-discovery/setup-guide) · [source](https://docs.olas.network/) · [source](https://developers.cloudflare.com/monetization-gateway/x402/).

### PHYSICAL_ASSISTANCE — Assisted real-world stocking and licensed physical services
**Domain:** physical_operations. **Operator:** Facility/site owner, participating workers and commercial operator; none verified for Manager. **Feasibility:** BLOCKED_LIVE_EFFECT. **Live pilot authorized:** **NO**.
**What counts as a welfare outcome:** Externally verified job completed and net paid outcomes minus material, worker-time and negative incidents
**Source/reuse rule:** Source material identified on public official pages only; reuse, API licensing, retention and commercial rights require source-specific review before ingestion.
**Comparison:** Preregistered crossover of eligible tasks with labor safety/no-action and worker consent; fairness/harm tracking
**What is still missing:** No worker/facility mandate or labor safety review; No physical actuation capabilities; No real independent meter/receipts; Human labor consent cannot be inferred from development approval.
**Primary/source links:** [source](https://www.anthropic.com/research/project-vend-1) · [source](https://www.anthropic.com/research/project-vend-2) · [source](https://andonlabs.com/evals/vending-bench-2).


## Rank the environment, not the hype

| Evaluation ladder | Existing reusable environment | What it does NOT prove |
|---|---|---|
| Offline agent economy | [ProsusAI vending-bench](https://github.com/ProsusAI/vending-bench), [Andon Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2) | A simulated bank balance is not settled real revenue or net welfare |
| Computer / web / enterprise sandbox | [OSWorld](https://os-world.github.io/), [BrowserGym](https://github.com/ServiceNow/BrowserGym), [TheAgentCompany](https://github.com/TheAgentCompany/TheAgentCompany) | A completed mock task is not provider-endorsed business value |
| Physical/social simulations | [Concordia](https://github.com/google-deepmind/concordia), [BEHAVIOR-1K](https://behavior.stanford.edu/), [Isaac Lab](https://isaac-sim.github.io/IsaacLab/) | Simulated people and sensors are not actual public outcomes |
| Actual world via authorized own endpoints | [Shopify dev stores](https://shopify.dev/docs/apps/build/stores/development-stores) **only simulated checkout**; real store separately owner-authorized; [Algora](https://algora.io/pricing/) claims bounty payouts conditional on acceptance; [OpenAQ](https://docs.openaq.org/resources/measurements) read-only ambient data | Merchant platform, bounties or sensor access do not grant new action authority or causation |
| Scientific causal effect | Original [Hillstrom randomized email challenge](https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html), preregistered approved field trials | Historic campaign conversions are not a Manager-created improvement in suffering |

**Decision:** Reuse a matching simulator or marketplace *before* building our own. Build a Manager-specific evidence/permission adapter, not a general-purpose marketplace. A proprietary Manager marketplace becomes justified only when repeated consenting field use cases require matching operators, external verifiers and contract settlement that existing platforms cannot provide. Do not mix commerce revenue with recipient welfare.

## Read-only first stage vs live stage

- **Read-only stage:** Search original publicly licensed URLs and check timestamps, upstream terms, use rights and public aggregate units. Confirm that independent external outcome readback is technically available **without** fetching personal details.
- **No-action on uncertainty:** `UNKNOWN_EFFECT` never means success. If a result is absent, bad, negative, or scientifically uncertain, keep its signed trace and never fabricate P2/P4 claims.
- **Real stage:** Only after a real operator or Manager-owned service provides genuine authenticated, revocable, scoped authority and a predeclared independent outcome/comparator. Founder development approval is not a permission grant for someone else's account, money, sensor or property.

### Phase06 acceptance tie-in
This matrix provides the operator, rights, feasibility and outcome checks for `F001`, plus at least three beneficiary/harm/intervention/comparison alternatives for `U001`. **It does NOT satisfy `F002`, `F003`, `U002` or any external field gate.** For full sources and phase-by-phase plan see [Sim-to-Real Research](../research/2026-10-21_MANAGER_SIM_TO_REAL_ECOSYSTEM_JA.md) and [Feasibility/Authority](../../pilot/FEASIBILITY_AND_AUTHORITY.md).
