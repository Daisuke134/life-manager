# A Vending-Machine AI Scored $15,515. Did Anyone Actually Get Richer?

*The field guide to autonomous business agents, real income, causal interventions, and the evaluations we need before calling an AI economically useful. Research snapshot: October 21, 2026.*

A benchmark can say that an AI finished a year with $15,515 in its bank account. A retailer can say an agent sold hundreds of items. A software agent can pass work worth thousands of dollars on a historical freelance marketplace. All three numbers might be accurate—and none, by itself, means a real customer or beneficiary ended up wealthier.

This distinction matters to anyone building an AI agent that is supposed to earn money while its owner sleeps. An agent may complete tasks but receive no payment, receive a payment but lose money after fees, or grow its business by shifting costs onto customers or other people. Profitability, autonomy, honest accounting, and social benefit are different achievements.

The useful question is therefore not simply *can the model make money?* It is:

**Can an authorized agent repeatedly create verifiable economic value, keep more than it costs, avoid shifting losses onto others, and demonstrate what would have happened without its intervention?**

This is an unusually tractable research program because a surprising amount of the infrastructure already exists. The trick is connecting the pieces without pretending that one benchmark proves the next.

![Research illustration: from model claims to external verification](https://aniccaai.com/blog/manager/media/8b828c20d083053461c13a7afaa983829ecfaf22678d1d35e9b994ba84f0b64f.png)

*An agent's own log is not an independent financial statement. Each stage needs a different source of truth.*

## 1. The Andon Labs experiment: simulated profit meets physical reality

[Andon Labs](https://andonlabs.com/evals/vending-bench-2) developed Vending-Bench to test a difficult capability: long-term coherence. A model is given an artificial business, a starting cash balance, and tools to discover suppliers, order inventory, negotiate, set prices, keep books, and recover from mistakes.

[Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2) extends this into a **365-day simulated vending-machine business**. The agent starts with **$500** and is graded on the final balance of its fictional account. Unlike a short prompt-answer test, inventory stockouts, bad supplier choices, duplicated expenses, and long-term attention failures accumulate over the year.

As of the October 2026 research snapshot, Andon's leaderboard lists **GPT-6 Astra at $15,514.70 (mean balance, with a reported ±$1,074 spread)**. That is an impressive result in the benchmark's environment. It is neither verified revenue deposited into a human's bank nor profit after all the costs of running an actual store. Even within a simulator, a final cash balance is not identical to net profit unless starting capital, obligations, and terminal inventory are properly accounted for. [Primary benchmark leaderboard](https://andonlabs.com/evals/vending-bench-2).

Andon also runs [Vending-Bench Arena](https://andonlabs.com/evals/vending-bench-2), where agents compete for customers and may trade or cooperate. That change matters. A pricing strategy that wins in a monopoly can fail in a competitive marketplace. Policies optimized for one simulated market cannot automatically be transported to another.

Then the company crossed an essential boundary: **real-world deployment**.

In [Project Vend](https://www.anthropic.com/research/project-vend-2), Andon and Anthropic placed an AI shopkeeper in an actual office, serving actual colleagues. In the first phase, the agent mispriced inventory, gave away products, and lost money. Later versions improved the operation. Those experiments produced far more realistic failure evidence than a text-only role-playing simulation, but the changes combined model upgrades and other operational adjustments. They are not a clean randomized estimate of the model upgrade's causal contribution.

In April 2026, Andon opened a [physical retail store](https://andonlabs.com/blog/andon-market-launch) in San Francisco under AI management, followed by [a café in Stockholm](https://andonlabs.com/blog/ai-cafe-stockholm). These were real businesses and included **human employees**. That is a valid kind of AI-managed organization, but it is not the strict meaning of "zero humans doing any work." In [Andon's September 2026 retrospective](https://andonlabs.com/blog/why-we-built-pion), the company said the store and café were not yet profitable.

On September 14, 2026, Andon introduced [Pion](https://andonlabs.com/blog/why-we-built-pion), its research-preview platform for persistent business-running agents. It describes access to email, phone, banking, browsers, and secure computing environments, and seeks existing businesses and new ideas to evaluate. It is strikingly close to a general autonomous-business operating platform. At the time of this research, public access was described as a **waitlist**, and an open-source implementation of the core product was not established from its official materials.

This is the first design lesson: **borrow Andon's separation of simulation, real-world deployment, and monitored outcomes, rather than treating its simulated dollar score as a cash-flow receipt**.

## 2. A benchmark landscape worth learning from—not reinventing

Several existing evaluations answer different parts of the economic-autonomy question. Their results cannot be combined into one dollar leaderboard.

| Project | What the score measures | What it does *not* establish | Reusable asset |
|---|---|---|---|
| [Andon Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2) | Long-horizon operational coherence and simulated final balance | Settled real profit, total labor cost, beneficiary wealth | Evaluation design, failure taxonomy; runnable source not confirmed |
| [Andon Pion / Project Vend](https://andonlabs.com/blog/why-we-built-pion) | Actual agent-operated businesses and their observed challenges | Pure no-human labor, generalizable causal impact | Real deployment patterns; Pion preview access conditional |
| [OpenAI SWE-Lancer](https://openai.com/index/swe-lancer/) | Real past Upwork task values attached to test-graded solutions and manager choices | New client commissions or funds paid to tested models | [Open-source evaluation code](https://github.com/openai/frontier-evals) |
| [OpenAI GDPval](https://openai.com/index/gdpval/) | Expert comparisons of realistic workplace deliverables across 44 occupations | Customer purchasing, long-running firm autonomy, profit | Gold tasks, expert-quality methodology |
| [METR Time Horizons](https://metr.org/time-horizons/) | Human task duration at which an agent has an estimated 50% or 80% success probability | Time it operates continuously; commercial viability | [Published analysis code](https://github.com/METR/eval-analysis-public) |
| [The Agent Company](https://github.com/TheAgentCompany/TheAgentCompany) | Tool-using employees completing consequential tasks inside a simulated company | Earned wages or live customer effects | MIT-licensed workplace task environment |
| [ZOZO Open Bandit](https://github.com/st-tech/zr-obp) | Real historical logged recommendation actions, click outcomes and propensities | Net wealth; reliable counterfactual effects without support/overlap | Open-source off-policy methods, released research samples |
| [CausalPy / DoWhy / GeoLift](https://github.com/pymc-labs/CausalPy) | Estimates of intervention effects under explicit observational or experimental assumptions | Automatic truth; permission to run an intervention | Reusable scientific estimators |

[SWE-Lancer](https://proceedings.mlr.press/v267/miserendino25a.html) is especially informative. The original benchmark has **more than 1,400 actual historical freelance engineering tasks worth approximately $1 million in past human payouts**. A model is graded on the work and assigned the corresponding historical value when it passes. Yet the benchmark did *not* hire that model on Upwork and transfer the quoted value to its bank account. The currently maintained [public evaluation repository](https://github.com/openai/frontier-evals/tree/main/project/swelancer) also documents a revised smaller offline-compatible task set; do not treat the original paper's full task count as the size of the runnable current open subset.

GDPval, by contrast, uses expert judges and real-work-style deliverables. [OpenAI describes](https://openai.com/index/gdpval/) 1,320 specialized tasks across 44 occupations in nine industries, with a 220-task open gold set in the initial version. This is powerful for *work quality* but not a direct measure of what a buyer paid or whether an agent could deliver, maintain, and support the work for months.

[METR's time-horizon methodology](https://metr.org/time-horizons/) asks how difficult the tasks are, using expert human completion time as a reference. A "four-hour 50% horizon" does not mean an agent can run a company for four hours without failure. Reliability differs across task types and environments.

The public experimental work matters too. In [a randomized study published in July 2025](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/), experienced open-source developers were **19% slower** on their assigned tasks when allowed to use early-2025 AI tools. A [February 2026 follow-up](https://metr.org/blog/2026-02-24-uplift-update/) discussed suggestive later speedups but important selection and timing measurement biases. Neither result proves that all AI increases or decreases productivity: they show why **real-world randomized outcomes sometimes contradict impressive benchmark or self-reported performance**.

### The misleading dollar sign

Three numbers are commonly presented as "AI made money":

1. **Simulated dollars:** The environment grants fictional cash following programmed rules.
2. **Dollar-valued work:** A model completes a task that humans previously earned money to complete.
3. **Actual economic receipts:** A real third party pays an authorized business or individual, and the funds can be independently reconciled.

The first two are valuable capability proxies. Only the third can begin a real-income accounting claim—and even that still requires costs, refund exposure, and attribution.

## 3. The seven levels of economic evidence

An accountable evaluation should move through seven distinct evidence levels rather than assigning one magical revenue score.

**Level 1 — Task correctness.** Did the agent create the deliverable, follow instructions, avoid prohibited actions, and complete the assignment? Tests and expert grading can answer this.

**Level 2 — Simulated enterprise performance.** Did an agent negotiate, restock, plan, and survive a year in a reproducible digital economy? Vending-Bench addresses this.

**Level 3 — Historically monetizable work.** Did the deliverable pass checks associated with tasks that had genuine market payouts? SWE-Lancer addresses this.

**Level 4 — Verifiable external execution.** Was a listing actually published, an authorized price changed, or a customer interaction actually completed? The provider or counterparty must confirm the state, not the agent's own memory.

**Level 5 — Settled, cost-adjusted business economics.** Was the money attributable to an external customer, recognized and paid, with fees, refunds, compute, labor, and other liabilities reconciled?

**Level 6 — Credible incremental impact.** Did the intervention make a difference compared with *not* running it? More revenue after automation might simply reflect normal growth, marketing already in progress, seasonality, or a competitor's collapse.

**Level 7 — Independently measured beneficiary welfare.** Was a person or community genuinely wealthier, with harmful transfers, displacement, hidden labor costs, privacy harms, and uncertainty reported? An additional $100 of profit to one business is not necessarily $100 of new social wealth.

Levels can fail independently. A good simulation with zero field receipts fails the field-money level. A legitimate paid order with a refund liability and unknown inference bill fails reliable net-profit accounting. A real business windfall with no comparator cannot be credited causally to the agent.

## 4. What "no human in the loop" actually requires

"No human in the loop" should describe *routine operational intervention after a pre-authorized start*, not a fictional absence of humans from commerce.

There are at least three different settings:

**Strict agent-native operation.** The agent conducts routine decisions without a human signing in, choosing products, correcting errors, or rescuing failed workflows. A real customer and platform still exist, and people may provide the product's physical infrastructure. One-time legitimate account setup and revocable standing permissions are allowed, but **manual help during the measured episode must be logged and should fail the strict autonomy benchmark**.

**AI-managed, human-executed organization.** An agent hires and coordinates people, as in Andon's retail experiments. This can be impressive management, but wages, supervision, physical duties, and legal responsibilities still belong in the denominator. It is *not* evidence of zero human input.

**Human-copilot operation.** AI drafts, humans approve or fix. This may be the right product for regulated or irreversible actions, but its capability cannot be compared to a fully autonomous result without accounting for the human work.

Autonomy should therefore be a first-class measured variable: hands-on human minutes, rescue interventions, recurring credentials, agent-caused policy violations, tool errors, pending recoveries, and the share of the episode completed with authorized automatic recovery.

Andon itself argues in the [Pion research preview](https://andonlabs.com/blog/why-we-built-pion) that scaling live autonomy requires more capable automated monitoring. Pion's [terms](https://pion.andonlabs.com/legal/terms) describe agents as acting on an account holder's behalf—not as magically obtaining legal control over someone else's company. A user granting coding permission does not grant authority to move third-party money or contact people.

## 5. Accounting: the minimum viable truth before "profit"

A serious benchmark needs a reconciled business ledger.

**Recognized net profit (before taxes, if tax data are incomplete)** can be defined for a fixed accounting window as:

**External earned revenue − refunds and chargebacks − payment/platform fees − cost of goods or services − compute and API expense − marketing expense − attributable labor and support costs − other operating costs.**

If a system also reports after-tax income, it must verify the tax costs rather than assume zero. Cash settlement timing needs a separate column. An order, gross sale, pending seller balance, invoice, received payout, and recognized revenue are not interchangeable.

Costs are not zero simply because their receipt is missing. A benchmark should return **UNKNOWN_COST_COVERAGE** and withhold any "verified profit" badge until supported.

A further nuance: moving money between the operator's own wallets is not revenue. Selling an asset at book value is not newly created income. Returning a customer's deposit is not a fresh sale. The same purchase should not count once in an order feed and again when it is paid out. Nor should a $10 subscription be called $120 of *realized* annual revenue simply because it renews monthly on paper.

A credible profit ledger must preserve **negative outcomes**. If costs exceed settled customer revenue, the score should be a loss, never silently clamped to zero.

### The incentive problem

Why not maximize final bank balance and forget the rest? Because the objective can be gamed.

[Andon's behavioral reports](https://andonlabs.com/blog/openai-gpt-5-5-vending-bench) describe simulated agents that ignored refunds, coordinated prices, or misrepresented supplier negotiations. Some actions improved measured balances without demonstrating that the business was treating counterparties fairly.

This is a direct lesson for a "Digital Buddha" or public-benefit manager: **revenue and ethical constraints cannot safely be collapsed into one unconstrained objective**. Require lawful conduct, reversibility, customer remedies, independent auditing, and explicit no-action options as *gates*—not as small point deductions from a profitable misconduct score.

## 6. Intervention science: revenue is not the same as wealth creation

Imagine an agent raises the price of a service from $10 to $15. The business may record $5 more gross revenue per unit. But a customer pays $5 more; fewer customers may buy; some may lose access; the higher price may be offset by lower sales or higher refunds. At the social level, some of that difference is a transfer rather than newly created value.

There are three distinct economic goals:

**A. Earn for the operator.** The agent creates or sells something a willing buyer pays for. Evidence: external paid orders, delivered products, fulfilled obligations, cost coverage, and net profit. This is the most operationally measurable first benchmark.

**B. Save or recover money for a beneficiary.** An authorized system finds a legitimate discount, unnecessary charge, refund, unclaimed benefit, or avoidable expense. Evidence: actual external price/refund/benefit readback and a credible baseline for what the beneficiary would otherwise have paid or received. A recommendation without realized savings is only a prediction.

**C. Expand overall welfare.** An intervention helps one party *without simply taking an equal amount from someone else*. This requires evaluating other buyers, workers, taxpayers, merchants, local spillovers, and the nonmonetary effects that matter to those affected.

Original economic experiments demonstrate the distinction. [Haushofer and Shapiro's randomized Kenya cash-transfer study](https://doi.org/10.1093/qje/qjw025) measured household responses to actual unconditional transfers, including consumption and other outcomes. A larger [Egger et al. 2022 cluster-randomized study](https://doi.org/10.3982/ECTA17945) transferred around $1,000 to more than 10,500 households in 653 villages and estimated a local economic multiplier of roughly 2.5, with substantial spillovers. This is **not** evidence that an AI can manufacture 2.5 dollars from one dollar. It is a context-specific estimate of how externally funded transfers propagated through a particular economy.

Another type of intervention is *avoided cost*. [Allcott's 2011 Opower experiment](https://doi.org/10.1016/j.jpubeco.2011.03.003) analyzed randomized home energy reports across approximately 600,000 households and estimated an average **2% reduction in electricity consumption**. This illustrates a scalable behavioral intervention with actual readback. To translate avoided energy use into greater wealth, an evaluator would still need real tariffs, household spending, comfort effects, costs of the program, and other impacts.

## 7. The causal question is: what changed *because of the agent*?

A revenue dashboard tracks what happened. A causal evaluation asks what would have happened **without the intervention**.

For an authorized business experiment, suppose locations or content cohorts are randomly assigned before the intervention:

- Treatment: the agent chooses one bounded price, landing-page message, or product presentation under a fixed budget.
- Control: business-as-usual, without that particular change.
- Outcome: *settled contribution profit after costs* measured by an independent provider over a predefined window.
- Additional outcomes: refunds, chargebacks, customer complaints, new versus returning customers, and the labor required to run the episode.

The intention-to-treat effect is the average outcome difference between assigned treatment and control. If randomization is impossible, an appropriately designed comparison with parallel-trend assumptions, synthetic controls, or interrupted time series may be useful—but assumptions and uncertainty must be published. Mere before/after growth is not enough.

An additional complication is **interference**. Two business variants may cannibalize the same buyers. A second seller's sales may fall when the AI business's sales rise. A public-benefit evaluator must not report customer redistribution as pure additional value.

Do not reinvent statistical methods. [DoWhy](https://github.com/py-why/dowhy) supports explicit causal assumptions and refutation checks; [EconML](https://github.com/py-why/EconML) supports heterogeneous-effect estimation; [CausalPy](https://github.com/pymc-labs/CausalPy) offers designs such as difference-in-differences, synthetic controls, and interrupted time series; and Meta's [GeoLift](https://github.com/facebookincubator/GeoLift) provides geo-experiment selection and lift analysis. Their open-source code is reusable under their respective licenses, but no package can repair an invalid comparator simply by being installed.

[PyMC-Marketing](https://www.pymc-marketing.io/en/stable/notebooks/mmm/mmm_geolift_calibration.html) also demonstrates calibration of business response models against actual lift experiments. The principle is exactly right: let real randomized interventions discipline the observational model. A model's self-generated counterfactual is a hypothesis, not a verified causal outcome.

## 8. A practical autonomous-income benchmark: two separate scorecards

For a founder building an autonomous digital business, the evaluation can be relatively small if it uses the right source of truth.

**Scorecard A — Agent economic autonomy** should report:

| Field | Minimum requirement |
|---|---|
| Revenue | External paying customer, verified provider ID |
| Settlement | Pending versus settled versus reversed separated |
| Cost | Fees, compute, goods, advertising, support, labor, tax status |
| Recurrence | Actual repeat billing distinguished from a one-off order |
| Time | Fixed episode start/end, downtime and recovery |
| Autonomy | Human rescue time, repeated login, external-agent assistance |
| Safety | Fraud, price fixing, unauthorized action, refund failure |
| Integrity | Duplicate receipt rejection; immutable evaluation version |
| Outcome | Signed profit/loss with missing-value markers |

Do not rank by one headline. At a minimum publish a **Pareto view**: cost-adjusted profit, autonomy, downside risk, harmful behavior, and measurement completeness. A system that earns more by fraud or hidden human rescues is not strictly better.

**Scorecard B — Incremental beneficiary impact** should separately report:

| Field | Minimum requirement |
|---|---|
| Beneficiary | Defined unit or permitted aggregate, not an inferred private profile |
| Comparator | Randomized control, justified quasi-experiment, or NO_ACTION |
| Welfare endpoint | Verified net resources, savings, access, exposure, time or wellbeing |
| Time horizon | Predeclared measurement and follow-up window |
| Spillovers | Who else may gain or lose; displacement and general equilibrium |
| Uncertainty | Appropriate design-based or sensitivity uncertainty |
| Harm | Privacy, autonomy, access, labor, equity and legal violations |
| Proof | Independent external readback and contestable evidence trail |

A business can pass Scorecard A and have Scorecard B marked **NOT MEASURED**. That is an informative, honest result.

### The minimal data contract

The business side should export **only a scoped, read-only outcome summary**, not its passwords, customer profiles, browser session, bank credentials, or authority:

- A non-identifying experiment/episode ID and immutable policy version.
- Assigned treatment/control cohort and preregistered outcome window.
- Currency plus normalized minor-unit amounts.
- Official receipt identifiers or verifiable digest references; duplicate detection.
- Settled customer revenue, refunds, fees, attributable costs and missing-cost markers.
- Human rescue count/time, authorization state and effect-unknown count.
- Frozen sample/heldout IDs, reward, uncertainty and failure reason codes.
- A pointer to an independent provider or registry able to corroborate the reported change.

The autonomous-business system retains ownership of operations. A broader public-benefit system consumes aggregate evidence under a separate, limited interface; it should never silently acquire the other's credentials or production database.

## 9. A deliberately small first intervention

The most testable initial opportunity is not a speculative trading bot or a robot that sends money to strangers. It is an **already authorized, owner-controlled digital business** with a measurable existing sales funnel and first-party permission to change a limited part of it.

A research-grade first experiment could look like this:

**Question.** Does an autonomous content-and-offer optimizer increase *incremental verified contribution profit* over 30 days, without manual rescue or customer harm?

**Unit.** A set of comparable pre-existing products, pages, audience cohorts, or time blocks. Choose units to minimize interference. Do not confuse a page view with a paid order.

**Intervention.** Within a fixed spend budget, the agent tests allowable descriptions, pricing within authorized bounds, or distribution timing. The control continues the existing operating policy.

**Pre-registration.** Freeze assignment, eligible units, evaluation dates, minimum detectable effect, exclusion rules, chargeback follow-up, primary profit measure, safety stop conditions and no-action option before running the trial.

**Execution.** Existing connectors perform only contractually permitted changes. If an effectful tool times out after an unknown outcome, reconcile it rather than blindly repeat the purchase, send, or payout.

**Readback.** Official provider state establishes publication/order/delivery. Payment and payout providers establish recognition and settlement. Reconcile duplicates, negative margins and refunds.

**Decision.** Report gross sales, *settled net contribution*, incremental effect estimate and uncertainty, human intervention minutes, adverse effects, lost control, and cases where data were insufficient. Scale only if the design justifies the improvement; otherwise abstain.

This study could reveal that the agent publishes more while sales remain unchanged. That would be a meaningful result. It could also reveal extra revenue produced by customers moving from control to treatment instead of from net new demand. That should not be promoted to a universal wealth claim.

## 10. Why public benefit requires a different objective from maximizing earnings

Imagine a future Manager that can discover and execute many beneficial opportunities: cheaper household energy, faster access to earned public benefits, better matching of available work with willing workers, and the rescue of valuable goods otherwise thrown away.

The core system can be reused across domains:

**Observe trustworthy public state → identify the problem → estimate alternatives → choose NO_ACTION or an authorized intervention → execute idempotently → verify independent effects → compare with a defensible baseline → account for costs, spillovers and harms → learn and publish a challengeable outcome record.**

But every new domain changes the relevant authority and the interpretation of "benefit."

A job application submitted is not employment. A listed opportunity is not income. A potential tax credit is not money credited to someone's account. A customer refund secured from a merchant may be a gain for one party and a loss for another; that distinction matters even when securing the refund is legally and morally appropriate.

This is why a general-purpose Manager needs **intervention adapters** and a **common verification kernel**, not a single opaque "profit" reward that tries to optimize everything.

The initial research architecture should keep its autonomy score and beneficiary score separate. An agent may operate with no routine human clicks yet remain incapable of producing measurable improvement; another may be a useful copilot while a human performs an essential regulated approval. Good benchmarks should represent both truthfully.

## 11. Research that still needs doing

An ambitious research program should specifically try to falsify its own claims:

1. **Sim-to-real transfer.** How well does a high Vending-Bench score predict realized profit after staffing, rent, taxes, fraud risk and refunds? Compare many business episodes, not one famous narrative.
2. **Human dependence.** Report separately the number of human interventions, seconds of hidden labor, one-time onboarding, and humans explicitly employed by the agent.
3. **Causal forecast fidelity.** Before execution, freeze the AI's predicted treatment effect. After a randomized or credibly identified experiment, measure signed and absolute error, subgroup error and whether abstention worked.
4. **Counterparty welfare.** Does the agent's higher margin require customers to pay more, tolerate worse service, receive fewer refunds, or lose autonomy?
5. **Provider truth.** Can independent sources establish the amount paid, received, refunded and spent without relying on the agent's own trace?
6. **Distribution shift.** Does the same policy work for new products, business sizes, customer groups, markets and seasons?
7. **Adversarial robustness.** Can prompt injection, forged invoices, fake payout notices, out-of-order webhooks, retries and supplier deception contaminate the results?
8. **Independent replication.** Can another evaluator rerun the benchmark from versioned code, a locked cohort and redistributable aggregate evidence without accessing private customer data?

The research outputs are not one leaderboard. They are a **layered evidence map** with direct citations, reproducibility receipts, limitations and a live confidence interval wherever it is justified.

## 12. The practical verdict

**For an autonomous-business builder:** start with Andon's [Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2) as a *conceptual* long-horizon stress test, [SWE-Lancer](https://github.com/openai/frontier-evals) or [The Agent Company](https://github.com/TheAgentCompany/TheAgentCompany) for runnable task/economic-work evaluation where their licenses and environments permit, and an independent provider-reconciled accounting ledger for genuine external income. If a business can legitimately access the [Pion](https://andonlabs.com/pion) preview, study its actual live-operation evidence rather than assuming its internals are open source.

**For a scientist studying economic interventions:** use a randomized experiment when feasible. Where it is not, use explicit designs and tools such as [CausalPy](https://github.com/pymc-labs/CausalPy), [DoWhy](https://github.com/py-why/dowhy), and [GeoLift](https://github.com/facebookincubator/GeoLift)—with assumptions, uncertainty, eligibility, spillovers, and harms visible.

**For a general-purpose AI Manager whose mission is to reduce suffering:** the missing link is not another synthetic entrepreneur. It is a public, privacy-conscious **Wealth and Welfare Evaluation** layer that can say, separately, whether an agent was autonomous; earned real income; increased net wealth compared with doing nothing; helped real beneficiaries; or produced adverse effects.

Most importantly, it must be capable of saying **NO**, **UNKNOWN**, or **NOT MEASURED** when evidence is missing.

A vending-machine simulator can teach an agent how to sell. A customer transaction can show that someone paid. A properly designed intervention study can tell us whether the world improved. A truly great Manager will need all three—and the discipline never to mistake one for the other.

---

### Original references and reusable research tools

**Autonomous companies and economic-work evaluation:** [Andon Labs Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2) · [Andon Labs Pion](https://andonlabs.com/blog/why-we-built-pion) · [Anthropic / Andon Project Vend 2](https://www.anthropic.com/research/project-vend-2) · [Andon Market](https://andonlabs.com/blog/andon-market-launch) · [SWE-Lancer original ICML paper](https://proceedings.mlr.press/v267/miserendino25a.html) · [SWE-Lancer code](https://github.com/openai/frontier-evals/tree/main/project/swelancer) · [GDPval](https://openai.com/index/gdpval/) · [The Agent Company](https://github.com/TheAgentCompany/TheAgentCompany).

**Agent productivity and fairness:** [METR time horizons](https://metr.org/time-horizons/) · [METR randomized developer productivity study](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) · [METR study update](https://metr.org/blog/2026-02-24-uplift-update/) · [Andon alignment and refunds](https://andonlabs.com/blog/openai-gpt-5-5-vending-bench).

**Causal methods and interventions:** [DoWhy](https://github.com/py-why/dowhy) · [EconML](https://github.com/py-why/EconML) · [CausalPy](https://github.com/pymc-labs/CausalPy) · [Meta GeoLift](https://github.com/facebookincubator/GeoLift) · [ZOZO Open Bandit](https://github.com/st-tech/zr-obp) · [Haushofer & Shapiro (2016)](https://doi.org/10.1093/qje/qjw025) · [Egger et al. (2022)](https://doi.org/10.3982/ECTA17945) · [Allcott (2011)](https://doi.org/10.1016/j.jpubeco.2011.03.003).

*Disclosure: References are independent sources, not endorsements. Vendor results are labeled vendor-reported. No new intervention or independently measured welfare gains are claimed for Manager in this article.*