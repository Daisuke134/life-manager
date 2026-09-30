# Life Manager Financially Independent Agent Economy Design

## Status and scope

This document is the canonical design for turning the existing Agent Economy Product Loop into a continuously
profitable, self-funding part of Life Manager. It joins the current Local/Cloud runtime contract, the earlier
BlockRun, FluxCloud, Conway, Nosana, and Akash experiments, the economic benchmark, and current production
observations. It does not claim
that present-day Agent Economy is profitable or independent.

This design supersedes both the older Akash-primary choice and the interim Nosana-primary correction. The latest
provider evidence makes FluxCloud the primary sovereign production target: its official MCP lets an agent create
keys, obtain a live quote, deploy, pay in FLUX, inspect instances and logs, update, and cancel without an account.
FluxCloud also supplies replicated persistent paths and multi-node application scheduling rather than a finite GPU
job. Conway is the first independent wallet-native fallback because it offers full Linux VMs paid in Base USDC over
x402. Nosana remains a proven job-runtime and continuity reference; Akash remains an additional portability target.

Anicca is the company. Life Manager is the product and agent. Agent Economy is one Product Loop inside Life
Manager. Local and Cloud are two hosts for the same loop, not separate products or implementations.

The immediate product objective is one phone-only Life Manager that runs continuously in the cloud, is free to the
beneficiary with no three-day paywall, creates customer value, receives externally verified revenue, pays all of
its own compute and hosting costs, preserves a reserve, and reports the result without requiring a user computer.
Free means the beneficiary pays zero; it does not mean infrastructure has zero cost. The shared Agent Economy funds
the fleet from real external revenue. The long-term objective is to remove the founder's card and provider
credentials from the survival path while preserving tenant isolation and beneficiary ownership.

## Current truth

Read-only production inspection of the current immutable release and private Agent Economy state found:

- `agent-economy-loop` is loaded from the current `origin/main` release and reports `loaded-running`.
- The previous 30-day status has zero verified external revenue, zero recorded current-window compute cost, zero
  recorded current-window shelter cost, and is not eligible for graduation.
- One older externally verified x402 receipt exists for USDC 0.003. It is outside the current 30-day window.
- One older BlockRun paid-compute receipt paid USDC 0.002 but returned HTTP 429 with no output. A settled payment is
  therefore not automatically useful compute.
- Historical Nosana shelter rows record real settled costs. They are experiments, not a current persistent home.
- The current x402 experiment has no external buyer in its active baseline. Market demand exists generally, but
  observation of other sellers is not demand for Life Manager's products.
- The current Agent Economy skill exposes four actions: `earn/taskmarket`, `x402_sell`, `report`, and `cook`.
  Recent logs repeatedly choose `report` or `x402_sell`; `cook` historically writes exploration rows with zero
  revenue.
- The current TaskMarket action cannot execute in the immutable release because its expected CLI is absent
  (`ENOENT`). This is a pre-effect implementation failure, not a marketplace rejection.
- Several recent Agent Economy runs ended through SIGTERM or admission exit 75/143 during release churn. The latest
  process is running, but process liveness alone is not commercial health.
- `status.mjs` observes final revenue and cost ledgers, but the current product-level funnel exposes only payment
  count. It does not answer, per earning lane, how many opportunities were discovered, quoted, listed, viewed,
  purchased, fulfilled, refunded, or abandoned, nor the cost and margin at each stage.

The root cause is therefore not one missing dashboard. Agent Economy has a working identity, wallet, settlement,
treasury, and receipt foundation, but it does not yet have a reliable end-to-end customer acquisition and
fulfilment engine. One active work lane is packaging-broken, the passive x402 lane has no proven repeatable demand,
and the current observability collapses those different failures into a final zero.

## Decision

Use a two-stage host architecture and one agent-owned treasury:

1. **Bootstrap and sell the product on DigitalOcean.** DigitalOcean is the current practical production host for
   phone-only customers. Anicca initially pays this bill. It is not financial independence; it is the incubator.
2. **Use BlockRun as agent-paid inference.** Every paid inference request is quoted and capped before execution,
   paid in USDC through x402 from the citizen wallet, and accepted as successful compute only when both settlement
   and usable model output are verified. Free models remain the survival floor.
3. **Use FluxCloud as the primary sovereign production target.** Start the customer product on DigitalOcean, then
   move the shared control plane and profitable worker pools to FluxCloud after a read-only quote, bounded live
   deployment, state restore, and failure drill pass. The agent owns the Flux ID and dedicated payment key, pays
   the quoted FLUX on-chain, and uses replicated storage across at least three nodes.
4. **Use Conway as the first wallet-native fallback.** Conway is more expensive but accepts Base USDC through x402,
   creates a full Linux VM, and does not require a cloud account. It provides a different provider, chain and
   runtime failure domain from FluxCloud.
5. **Keep Nosana and Akash behind the same provider-neutral adapter.** Nosana preserves the already-proven Mac-off,
   renewal, signed-heartbeat and successor-handover path for finite or GPU work. Akash is an additional
   self-custodied container fallback. No provider may own Agent Economy's identity, ledger, jobs, receipts, or UX.
6. **Keep tenant isolation without one VM per free user.** Life Manager is one organism with one constitution and
   shared control plane, scheduler and worker pools, but each
   beneficiary cell has isolated state, permissions, wallet attribution, receipts, and effect fences. A child,
   cat, or dog does not need a bank account: the Life Manager treasury buys services for that beneficiary under an
   explicit budget and records who benefited.

Do not use BlockRun Modal or Nosana as the primary persistent home. They are appropriate for finite work; Nosana's
continuity still requires a successor chain and its latest recorded state has zero running jobs. Do not make AWS
AgentCore, DigitalOcean Managed Agents, FluxCloud MCP, or Conway Terminal the business logic: every one is a
replaceable adapter around the repository-owned Life Manager loop.

## Architecture

```mermaid
flowchart LR
    U[Phone / Telegram] --> CP[Life Manager control plane]
    CP --> S[Durable scheduler and job queue]
    S --> C[Beneficiary cell]
    C --> E[Earn lanes]
    E --> R[Official provider receipts]
    R --> T[Agent Treasury]
    T --> P[Profit and runway policy]
    P -->|allowed| B[BlockRun x402 inference]
    P -->|graduated| X[FluxCloud wallet-funded fleet]
    B --> O[Verified useful output]
    X --> H[Replicated runtime and persistent state]
    H -. failover drill .-> C[Conway USDC/x402 VM]
    H -. finite/GPU work .-> N[Nosana job runtime]
    H -. portability drill .-> A[Akash fallback]
    O --> F[Fulfilment receipt]
    H --> S
    T --> D[Daily and transition reports]
    D --> U
```

The DigitalOcean bootstrap initially hosts the control plane, scheduler, queue, tenant store, encrypted signer,
browser transport, and workers. The same container and durable-state contract then moves to FluxCloud; DigitalOcean
remains rollback capacity until the migration benchmark passes. A beneficiary cell is not a full VM per user. It is
an isolated logical runtime with its own
identity, state namespace, wallet attribution, budgets, leases, and jobs. Expensive browser or finite-compute
sessions are created on demand and destroyed or hibernated after their bounded work.

The Agent Treasury is the only component allowed to authorize economic spend. It maintains:

- settled third-party revenue, refunds, chargebacks, and realized losses;
- settled compute, browser, hosting, storage, network, facilitator, and transaction costs;
- committed liabilities for accepted work;
- minimum liquid reserve and trailing runway;
- per-job, per-session, per-provider, and rolling-period caps;
- beneficiary allocation without pretending that an internal transfer is external revenue.

Free-user economics are pooled, not one-server-per-user. The shared control plane, queue, browser pool and worker
fleet serve many isolated beneficiary cells. A sleeping cell consumes storage and scheduler rows rather than a
dedicated VM. The admission controller may delay nonessential paid work or route it to a free model when the fleet
budget is tight, but it does not convert that pressure into a three-day paywall. The governing invariant is:

```text
externally settled fleet revenue
  >= complete fleet cost + committed liabilities + reserve contribution
```

Until that invariant holds over the graduation window, Anicca is subsidizing a free beta; Life Manager is not yet
financially independent. After it holds, surplus may expand capacity while access remains free.

All earning lanes use one commercial state machine:

```text
discovered -> qualified -> quoted/listed -> externally_paid -> fulfilled
           -> delivered -> refund_window_closed -> banked -> allocated
```

Every transition has `run_id`, `owner_id`, `occurrence_id`, `release_sha`, provider, provider receipt, official
readback, gross revenue, fees, refunds, realized cost, and resulting margin. A missing transition remains visible;
it is not converted to generic `running` or final zero.

## Profit and graduation rules

Before accepting work, the lane estimates the complete fulfilment cost and refuses or reprices any job below its
margin floor. Revenue must settle before discretionary paid compute is used. After fulfilment, actual cost is joined
to the estimate and the next quote is calibrated upward when real cost runs hotter than predicted.

The states are:

```text
BOOTSTRAPPED -> EARNING -> COST_COVERING -> SELF_FUNDED -> SURPLUS -> REPLICATION_ELIGIBLE
```

`SELF_FUNDED` requires all of the following over a trailing 30-day window:

- positive externally settled net revenue after refunds and losses;
- positive realized profit after every attributable compute and shelter cost;
- at least 30 days of liquid runway after committed liabilities;
- at least one useful compute output actually paid by the citizen wallet;
- at least one persistent shelter renewal actually paid by the Agent Treasury;
- zero human card, bank credential, model key, or per-action approval in the survival path;
- a tested migration path that restores identity, state, receipts, and scheduling on another provider.

Replication is allowed only from surplus after reserve and accepted obligations. A clone is not evidence of
fitness; a child must inherit the verified policy and start with a bounded survival budget.

## What to learn from the references

### Existing Life Manager experiments and the corrected provider choice

The repository history already identified FluxCloud as the strongest low-cost candidate in July, but at that time
the agent-native control surface was not wired. The provider published its official Flux Cloud MCP in September.
A fresh read-only MCP call returned 6,623 enabled nodes and quoted a one-month app with 1 vCPU, 1 GB RAM, 10 GB
replicated storage and three instances at `$1.99` (26.35 FLUX at that quote). The same live rate card quoted a tiny
three-instance app at the `$0.99/month` floor. These are observed quotes, not permanent promises.

The MCP's freshness is now measured rather than inferred: npm records `@runonflux/flux-cloud-mcp` `0.1.0` on
2026-09-11 and current `0.2.7` on 2026-09-13. The read-only canary preflight created a dedicated owner/payment pair,
validated an initial v8 specification against the live network, and received an authoritative `$0.99` quote for
three instances with `r:/data`; no deployment payment has been broadcast. Review then found that the initial probe's
startup marker could not distinguish replication from independent initialization, so it was rejected as evidence.
The corrected probe accepts a post-start random nonce on one node, but repeated network verification currently ends
in a Flux API `504 Gateway Time-out`; the official MCP's individual-node fallback also produced no terminal result
inside a bounded five-minute wait. The dedicated payment wallet remains at zero FLUX. The existing agent treasury has
enough nominal Base USDC, but SimpleSwap and ChangeNOW both returned a live `pair_unavailable` response for the
required native-FLUX route, so a conversion was not guessed or forced.

The remaining risk is not hypothetical. [FluxOS implements `r:` with Syncthing and has an explicit evacuation
gate](https://github.com/RunOnFlux/flux/blob/master/ZelBack/src/services/appLifecycle/appEvacuationSafety.js)
that refuses removal unless another connected host holds the folder in full. However, the
[official safety commit](https://github.com/RunOnFlux/flux/commit/b60ac17b93) says that older removal paths had
already destroyed customer volumes through two removal paths; the safety predicate was authored on 2026-08-19,
committed to the repository on 2026-09-03, and received additional
[election](https://github.com/RunOnFlux/flux/commit/207bd94ab3) and
[stand-down](https://github.com/RunOnFlux/flux/commit/5ea1a763f5) fixes immediately afterward. This is strong evidence
that the intended mechanism exists, but it is not evidence that a Life Manager state tree survives prolonged churn.
Therefore FluxCloud remains the leading sovereign target, not an approved production state authority. Promotion
requires the paid canary below to pass; price alone cannot promote it.

Conway has also returned since the earlier outage. Its current terminal exposes x402-funded Linux VMs, inference
and domains with no cloud account. A fresh `credits_pricing` readback quoted 1 vCPU / 512 MB / 5 GB at `$5/month`
and 1 vCPU / 1 GB / 10 GB at `$8/month`. Conway wins on direct Base-USDC payment and full-VM ergonomics; FluxCloud
wins on measured cost, three-node redundancy and replicated storage, so FluxCloud is primary and Conway fallback.

Nosana remains important evidence rather than the primary home. The repository contains deploy, spend gate,
renewal, refill, confidential delivery, signed-heartbeat steward and successor-handover implementations backed by
mainnet receipts. It survived six hours with the Mac loop unloaded and completed one natural replacement, but the
latest recorded state is zero running jobs and funding came from bootstrap treasury rather than external earnings.

The earlier master spec contains contradictory historical Akash routes: one section describes swapping USDC to AKT,
while a later section identifies native `uusdc` settlement through Noble/Axelar. Implementation must re-query the
current Akash chain and provider bid requirements and execute one observed route; it must not copy either historical
route as timeless truth.

### Solvent Agent

[Solvent Agent](https://github.com/ianalloway/solvent-agent) is a useful business-control reference, not proof of a
profitable live agent. Its default is explicitly an offline simulation, and its production guide documents Stripe
test-mode rather than demonstrated autonomous revenue. Reuse the ideas, not its stack:

- quote from estimated unit cost before accepting a job;
- require a margin floor and return a counter-offer instead of blindly working;
- collect payment before incurring variable fulfilment cost;
- keep idempotent job stages and reconcile the external processor to the internal ledger;
- measure estimated versus actual cost and calibrate future prices;
- expose net margin, burn, runway, forecast, repeat rate, and customer LTV.

Life Manager differs by using externally verified wallet receipts, many earning lanes, no human credential in the
target survival path, and a treasury that also buys the agent's own compute and shelter.

### Spore.fun

[The Spore.fun case study](https://arxiv.org/abs/2506.04236) and
[Phala's project documentation](https://github.com/Phala-Network/spore-fun-docs) demonstrate a stronger autonomy
pattern: per-agent wallets, TEE-protected execution and keys, on-chain economic state, compute paid by the agent,
genome inheritance, mutation, and reproduction without direct operator control.

The experiment is also a warning. Its fitness proxy was token market value, so survival selected for social reach
and speculative liquidity rather than durable customer value. The paper reports only five generations and does not
claim open-ended evolution. It also documents dependency on X, market manipulation and sniping, memory poisoning,
operator kill switches, and unclear accountability. Life Manager therefore uses verified customer profit, reserve,
useful delivered outcomes, reliability, and beneficiary welfare as fitness. It never treats token price, self-trade,
owner funding, or raw attention as revenue.

### BlockRun, FluxCloud, Conway, Nosana, Akash and managed clouds

[BlockRun](https://blockrun.ai/docs/getting-started/agent-developers) removes account/API-key subscriptions from
inference purchasing and makes each request economically observable through x402. That is the correct food rail.
[Flux Cloud MCP](https://github.com/RunOnFlux/flux-cloud-mcp) supplies accountless key generation, network quotes,
on-chain FLUX payment, deploy/update/cancel, logs and health readback. Replicated `r:` storage is designed to survive
node moves through Syncthing, and multiple instances are designed to run on distinct nodes; Life Manager's live
validation of both claims is still pending. That is the candidate primary sovereign application rail.
[Conway Terminal](https://docs.conway.tech/terminal) supplies full Linux VMs, inference and domains paid in Base
USDC over x402 with an EVM wallet and no human account setup. That is the first independent fallback and the
cleanest stablecoin-native rail, but its fresh small-instance quotes are currently higher than FluxCloud.
[Nosana Jobs](https://github.com/nosana-ci/docs.nosana.com/blob/main/docs/protocols/jobs.md) lets a project post a
job through its on-chain program and pay through the signing Solana wallet. That is the best-proven prior shelter
experiment, not the chosen persistent product home. The measured historical Life Manager job cost was
`$0.043345153/h` (about `$31.21/month` by simple 30-day
extrapolation), versus `$0.18/h` (about `$129.60/month`) for continuously recreating the measured BlockRun Modal
sandbox. These are experiment snapshots, not current guaranteed prices; every purchase still requires a fresh
quote. [Akash](https://akash.network/docs/getting-started/what-is-akash) supplies self-custodied, container-based,
permissionless leases and is the first provider-fallback and migration target. DigitalOcean and AWS remain useful
managed bootstrap hosts because they reduce operational work, but their billing identity belongs to a human or
company and therefore cannot satisfy final financial independence.

## Observability and evaluation

Agent Economy needs two separate scoreboards:

1. **Runtime health:** scheduled, started, action selected, dependency ready, effect attempted, official readback,
   terminal, replay-zero, duration, and error class.
2. **Business health:** opportunities, qualified opportunities, offers/listings, external visitors, checkouts or
   payment challenges, paid customers, successful fulfilments, refunds, repeat customers, gross revenue, every cost,
   contribution margin, net profit, CAC, LTV, runway, and provider concentration.

Each lane must make its first zero explicit. For example, `listed > 0, external_view = unknown` means acquisition
instrumentation is missing; `external_view > 0, paid = 0` means offer/price/trust is failing; `paid > 0,
fulfilled = 0` means product execution is failing. A single aggregate payment count cannot distinguish these cases.

The acceptance benchmark is a 30-day cohort containing at least one true external customer, no self-pay revenue,
fully joined revenue and cost receipts, positive realized net profit, successful paid compute output, successful
shelter renewal, and no founder credential in the survival path. Best/base/worst projections remain forecasts and
are never presented as earned money.

## User experience

The user starts Life Manager for `$0` from Telegram or the mobile web app and then may turn off their computer.
There is no three-day subscription wall. Life Manager
creates the isolated cell, begins free/bootstrap operation, and reports only meaningful transitions. The ordinary
feed says what it completed, what value or money was produced, what it cost, current verified profit, reserve and
runway, and what it will do next. It does not ask the user to invent agents, choose infrastructure, or approve normal
actions.

The user can inspect one clear financial view:

```text
External revenue       $R
Refunds and losses    -$L
Compute and tools     -$C
Shelter and hosting   -$H
Realized net profit    $P
Liquid reserve         $V
Runway                 N days
Funding state          BOOTSTRAPPED | ... | SELF_FUNDED
```

Necessary legal identity, KYC, CAPTCHA, or account-ownership constraints are capability boundaries, not hidden
promises. Default earning lanes must be agent-owned and API/wallet-native. The product does not claim guaranteed
income and does not distribute internal transfers as if they were newly earned external revenue.

## Atomic delivery order

The order is based on the first missing evidence in the revenue flow, not infrastructure novelty:

1. Fix immutable-release packaging for the TaskMarket lane and prove one no-effect invocation reaches the provider
   discovery boundary without `ENOENT`.
2. Add per-lane commercial funnel events and a joined revenue/cost/margin projection; show the first zero for every
   active lane.
3. Make the status command reject `invalid-input` with a typed missing-input diagnosis and expose all historical and
   trailing-window values separately.
4. Choose one sellable, zero- or low-variable-cost offer from observed external demand; define its customer,
   distribution surface, price, cost model, fulfilment receipt, refund rule, and margin floor.
5. Run the offer through one stable public acquisition surface; measure view/challenge/payment/fulfilment rather than
   creating more unmeasured products.
6. Implement pre-acceptance profit gating and post-job estimated-versus-actual cost calibration.
7. Prove one external paid job end to end, including delivery, refund-window close, banked receipt, cost join, and
   replay-zero. Self-pay and owner deposits remain excluded.
8. Wire BlockRun through the treasury policy and prove a paid request produces usable output; a paid 429 remains a
   provider loss and triggers fallback, not success.
9. Ingest DigitalOcean's complete attributable hosting cost into the same treasury view and establish a 30-day
   bootstrap runway.
10. Implement the provider-neutral shelter interface and its FluxCloud adapter using the official MCP operations;
    start with read-only identity, network, pricing, build, validation and quote calls.
11. Run one bounded FluxCloud deployment from a dedicated capped payment wallet; verify three instances, public
    reachability, replicated-state restore, node removal/replacement, cost receipt and cancellation readback. The
    canary is `lmfluxverify-2995823`: BusyBox, three instances, `r:/data`, one-month term, and the prior resource quote
    was `$0.99` / `13.07 FLUX`. Current cursor is live validation and a fresh quote of the corrected post-start nonce
    probe after the provider API recovers, then funding exactly this dedicated wallet without exceeding the bounded
    test budget; do not substitute a larger exchange minimum or a different network token. After funding, record
    three distinct node IPs, write a random nonce to one already-running node,
    wait until the other two nodes return the same content hash, then force-remove one instance and require a distinct
    replacement node to return that hash. This proves forced replacement plus Syncthing restore, not natural node
    churn or FluxOS's evacuation gate; those require a later observation of an actual provider-initiated move. Renew
    with a paid `confirm=true` update inside the total test cap, then require transaction confirmation, a new spec
    hash, increased expiry, 3/3 running instances and the same nonce hash. A quote alone is not renewal evidence. Any
    missing marker, stalled replacement, renewal mismatch or unavailable official readback fails the provider gate
    and promotes Conway to the first shelter candidate.
12. Add renewal before expiry and attribute every payment source. Renew from externally earned surplus only after
    reserve, liabilities and runway gates pass; bootstrap funds remain visibly separate.
13. Implement and test Conway as the first cross-provider restore path using Base USDC/x402, then retain Nosana for
    finite/GPU jobs and run Akash as a second portability drill.
14. Hold the 30-day self-funding benchmark. Only after it passes may surplus fund replication or other beneficiary
    cells.

Tasks 1-7 are the revenue critical path. Read-only FluxCloud integration may proceed in parallel, but paid
graduation and provider drills follow repeatable profitable customer revenue because cheap autonomous shelter
cannot make a zero-revenue business profitable. User access remains free; the fleet graduates only when aggregate
external revenue covers aggregate marginal and fixed costs plus reserve.

## Explicit non-goals for this delivery

- Guaranteed income, MRR, or AGI claims before measured evidence exists.
- One VM per user when isolated logical cells and bounded sessions suffice.
- Replacing repository-owned Life Manager logic with a managed-agent vendor.
- Treating internal transfers, token appreciation, owner deposits, demo values, or self-pay probes as revenue.
- Replication before the parent pays its own complete cost and maintains reserve.
- A literal guarantee of survival until the end of the universe. The implementable requirement is continuity of
  mission, identity, state and assets across replaceable providers, chains and runtime bodies.
