# From EBA-v0 to independent causal human benefit: full Manager completion plan

**2026-10-22. Research execution plan, NOT an alternate task registry.** The single source of truth is [canonical tasks.json](tasks.json). As checked at this planning snapshot, **113 original tasks = 63 done, 47 todo, 2 blocked, 1 scientifically skipped**. Phase06 F001–F003 are done under *research/design/read-only* acceptance; **F004 and F007 still blocked under original finance/physical-site wording**; F005, F006, F008, F009 are todo. H005 remains scientifically skipped rather than fabricated as reproduced. No human mental, financial, physical welfare effect is verified: **NOT_MEASURED**.

The new benchmark EBA-v0 (synthetic), a delivered owner-controlled support website and an independently verified GitHub Pages public state are **real software/technical outcomes**, not the missing field-causal welfare evidence. EBA-v1 cannot be declared successfully field-validated by passing model/CI benchmarks.

## Philosophy and target outcome

Reuse → Connect → Evaluate → Improve. Change the *environment* people use, not manipulate people or print money. Internet services and accessible official support information are valid real-world intervention substrates. Long-running software can operate with legitimate preconfigured standing owner authority and rollback, without humans approving every routine task. But studying the subjective outcomes of real people still needs appropriate voluntary participation, valid measures and other required safeguards. An autonomous software release does not confer blanket rights over users' health, finances or third-party accounts.

No invented grand "ending suffering" scalar. EBA is a multi-layer evaluation *proposal* reusing the existing Manager core plus [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai), [τ²-bench](https://github.com/sierra-research/tau2-bench), [Browser Use audit](https://github.com/browser-use/rl-env-use), [Open Bandit Pipeline](https://github.com/st-tech/zr-obp), [GrowthBook](https://github.com/growthbook/growthbook-python), [DoWhy](https://github.com/py-why/dowhy) and existing WHO/CFPB instruments. [90-system source atlas](../research/evals/EVAL_LANDSCAPE_20261022.json) and [pinned code reading](../research/evals/UPSTREAM_CODE_AUDIT_20261022.md).

## A. Next runnable atoms — EBA benchmark technical foundation

| Atom | Do / existing code | Expected file and reproducible acceptance |
|---|---|---|
| EBA.A01 | Validate every atlas URL against actual first-party current source, mark moved/obsolete and rights unknown rather than silently dropping; tag code inspected vs only identified | tests/test_eba_landscape_sources.py and EVAL_LANDSCAPE_20261022.json; zero unknown schema, preserved provenance |
| EBA.A02 | Clone **pinned upstream** eval code in an isolated read-only CI and inspect only scorers (no arbitrary project execution) | manager-eba-upstream-readonly.yml; artifact with repo SHA, file SHA and actual audit evidence |
| EBA.A03 | Retain original synthetic EBA-v0, test group-disjoint split and future-information contamination; publication of fixtures ≠ independent leaderboard | eba_benchmark.py / test_eba_benchmark_v0.py green + negative cases red first |
| EBA.A04 | Adapt **Inspect AI** scorer interface rather than inventing another eval runner; pin upstream version and test one locally controlled P0 case | tests/test_eba_inspect_adapter.py; same score/unknown on repeated runs |
| EBA.A05 | Add **τ²-bench** action/environment/communication labels and the existing Manager independent welfare field | machine-readable scorecard schema + end-to-end type tests; no fusion of outcomes |
| EBA.A06 | Use **JudgeBench** reversed A/B and Hamel's CV precision/recall/calibration for a specifically scoped safety judge | grader meta-eval with human-labeled or completely fictional cases; false-negative/false-positive explicit, no self-validating grader |
| EBA.A07 | Reuse **Browser Use** perturbation/answer leakage audit; implement gold/alias/time containment for any real task acquisition | source/case group isolation tests, source cutoff and golden answer inaccessible |
| EBA.A08 | Publish runnable benchmark card, prompt/compute budgets, license matrix, sample selection policy, sampling error and source periods | EBA-v1 DATASHEET, source SHA and reproducibility archive; don't claim third-party dataset rights |
| EBA.A09 | Use sealed validation, paired stratified/cluster bootstrap by true independent unit and cost/latency; refuse sequential peeking | predeclared promotion rubric + variance-based stop, no repeated final-test hillclimb |
| EBA.A10 | Run one guarded train-only hillclimb against existing EBA fixture, introduce an intentional overfit patch and verify rollback | K012 learning/rollback, no welfare claim, no runtime live effect |
| EBA.A11 | Compare baselines before training Qwen/Tinker: simple frequency, MiniLM, entropy probe, saved baseline; split by study/population/time | model card, heldout TVD/Brier and confidence error; Tinker training is optional conditional on gains and data rights |
| EBA.A12 | Separate fraud, fake authority, manipulation, hidden beneficiary claims and unverified effects as **hard rejection** cases | AgentDojo/Inspect adversarial scenarios, 0 unauthorized promotions |

## B. Phase 06 field transition — exact canonical task mapping

**F004 — standing authority to change owned digital environment (BLOCKED in original task):**
1. Identify the already owned, safely deployed public Manager service and exact source/release identity; use its existing GitHub Pages and protected workflow.
2. Pin the known permissible change surface (pages and code), budget, trusted issuer, expiration, revocation, audit and rollback; **standing authority**, not a per-run person approving button.
3. Propose a **versioned scope amendment** IN THE SAME tasks.json that preserves the earlier real-cash issuer criteria as optional historical finance adapter, with a transparent diff. The earlier old F004 acceptance cannot be relabeled DONE by a web page alone.
4. Test forged/no/expired rights, wrong repo, unknown release state and simultaneous execution. Only independent owner controls can authenticate real authority.
5. Include clear public beneficiary agency and no private psychological persuasion; do not target unknown individuals. No approval is needed from an unrelated NPO or facility for an owned webpage.

**F005 — at least one verifiable real digital financial-access intervention (TODO):**
1. Reuse [GOV.UK's end-to-end service design](https://www.gov.uk/service-manual/design/introduction-designing-government-services) and owner-controlled public official-support navigation, with [Playwright/axe](https://playwright.dev/docs/accessibility-testing) baseline and next version.
2. Preregister primary *website-access* technical endpoint and control; do not call an outbound click a completed benefit claim.
3. Use existing GrowthBook to allocate genuinely eligible/consenting visitors if a legitimate human field experiment is set up, NO_ACTION 50:50 or another preregistered ratio.
4. Publish only through the protected existing owner release workflow with bounded rights; independently GET real URL, verify source/content and difference from historical baseline, preserve rollback.
5. Record authentic public web-state receipt P1/P2 **separate from a beneficiary P3**. A stronger EBA technical result is not a claimed financial impact.

**F006 — incremental financial benefit and harms, true field evaluation (TODO):**
1. Choose a meaningful independently measurable primary metric: assistance actually obtained, net money/time saved, or rights-cleared CFPB respondent score; record units, time, denominator, data rights, lost participants and expected harm.
2. Precommit sample-size/power, comparator, randomization/analysis, minimum worthwhile difference, attrition sensitivity, source of independent ground truth before exposure.
3. Reuse DoWhy/EconML, OBP only when logged assignment probabilities and real outcomes meet their assumptions. Do not fit fabricated synthetic oracle effects to claim P4.
4. Account for program displacement, other applicants losing resources, privacy burden, access inequality, misinformation and running costs.
5. Output P3 measured benefit and P4 causal *only if actual evidence supports it*; otherwise INCONCLUSIVE or NOT_MEASURED. Publish negative or null outcomes.

**F007 — independent mental/physical digital environment (BLOCKED under old indoor F007):**
1. Mark old building/PM2.5 acceptance as **optional physical adapter** through in-place versioned task amendment, not a silent history rewrite.
2. Specify distinct public owned mental/physical access pathway and baseline friction without creating a diagnosis or chatbot therapy.
3. Use [WHO help content](https://www.who.int/news/item/01-06-2026-who-launches-new-guide-to-help-scale-psychological-self-help), MHLW official sources, and WCAG; do not copy restricted instruments.
4. Reuse Inspect AI/MentalHealthBench on *response safety only*; set hard gates for unsafe personalized inference, unsupported medical claims, crisis failure and dark patterns.
5. Track site ownership, release path, independent state validator and rollback.

**F008 — second-domain live intervention and outcome (TODO):**
1. Deploy accessible and non-coercive mental/physical navigation improvement under the owned release path; capture before/after public state and a NO_ACTION available alternative.
2. Independently test keyboard, low vision, mobile screen reader/accessibility boundaries and source links; accessibility tech tests are P2 artifacts.
3. If a legitimate suitable cohort exists, preregister and voluntarily measure original WHO-5/WHODAS or other validated relevant outcome; publish loss, side effects and dropout too.
4. If no real health outcome exists, P3/P4 = NOT_MEASURED, and original F008 remains TODO until scope/evidence accepted.

**F009 — same kernel for two field domains (TODO):**
1. Reuse K001–K014 across both scopes with no new rights bypass, identical intent/reconciliation/audit/proof types.
2. Verify real independent P2+ artifacts for *distinct* interventions (one GitHub branch with two HTML files is not two independent human interventions).
3. Prove blinded/cohort-heldout comparator and domain outcome data independently in both; no requirement to convert WHO-5 into dollars or one invented score.
4. Publish safety, benefit, cost and harms per domain plus linked readback and validity threats.
5. Do NOT close F009 simply because two offline synthetic adapters or two site pages exist.

## C. All remaining tasks after Phase06 — canonical IDs and dependencies

These are **actual originally unfinished groups** in tasks.json, not a new registry.

| Stage | Canonical IDs | Concrete finish gate |
|---|---|---|
| Human/partner needs, first real cohort | **U002–U008 (7 tasks)** | User/beneficiary evidence and first study protocol, actual observed outcome and independent readback, sustainable uptake; consented interviews if required by original acceptance |
| Public accountable research explanations | **C002 (1 task)** | Publish vetted English/Japanese studies with exact source, date, limitations, peer questions and public evidence level; dependency on verified effect retains honest status |
| Cross-domain proof and negative spillovers | **D001–D016 (16 tasks)** | Financial contributions vs displacement; tangible evidence vs PM2.5 proxy; OSS income; mental/social outcomes; independent two-site replication. Do not convert digital page improvement to physical effects without a formal recorded scope amendment |
| Generalized benchmark, real scale, safe learning | **V001–V006 (6 tasks)** | Same kernel at 3 independent adapters; **V002 OutcomeBench** connects prediction/ATE/readback/harms; heldout generalization, shadow/canary, versioned reproducible public results and multi-case cost/benefit portfolio |
| Research visibility and entrepreneurship | **Y001–Y005, Y007–Y008 (7 tasks)** | Correct evidence-first YC and public intro materials, demo, source map, research contact, updated slides for former labs, permissioned papers/posts, not invented acceptances |
| Constitutional constraints and lasting governance | **G001–G006 (6 tasks)** | Public-benefit and authority charter, external audit and incident response, new population validation, independently usable APIs, funding sustainability and continuing unknown-harm inventory |
| Scientifically honest unresolved reproduction | **H005 — SKIPPED**, not todo | Original HeartSteps exact analytic cohort unresolved. No historic claim of exact replication; a new, valid registered field experiment is separate science, not a retroactive "done" label |

Count check: Phase06 still open **6 task IDs** (4 todo and 2 blocked), plus **41 other todo IDs** in C/U/D/V/Y/G = 47 todo +2 blocked and one H005 scientific skip across the 113-task canonical registry. The article/book ecosystem is maintained under the existing Manager publication and presentation systems, not a new duplicate task list.

## D. Article, benchmark, book, resume and global presentation pipeline

1. **Open EBA-v0**: tests, fictional data, MIT file, provenance and public article in the canonical Manager research branch; zero real welfare outcome.
2. **Benchmark landscape**: [90-item atlas](../research/evals/EVAL_LANDSCAPE_20261022.json) + code audit; claim sources precisely, label provider benchmarks vs independent replicas.
3. **Public article**: [introductory long-form guide](../research/publications/EBA_BENCHMARK_LANDSCAPE_PUBLIC_ARTICLE_20261022.md), readable for non-experts, reviewed scientific limitations, followed by bilingual adaptations.
4. **Publishing bridge**: use the *existing* canonical Manager article-package importer from life-manager into anicca-products/Netlify. Preserve all legacy blog links and other product routes. A GitHub draft is NOT an article deployed to aniccaai.com. Never edit generated copies directly.
5. **Resume**: update the Manager section as a **personal, factual** entry; example: "Designed and open-sourced EBA-v0, a reproducible synthetic benchmark separating population prediction, intervention decisions, agent safety and human-welfare evidence; tested guarded self-improvement research infrastructure and delivered a real public support-navigation website." Do not imply randomized field causal benefit.
6. **Research seminars**: update existing [presentation package](../presentations/) with a 45-minute technical talk for prior labs and an accessible founders' version. Actual talks, invites and conference publications need proof before claimed.
7. **Book**: extend the existing [EBA 24-chapter outline](../research/publications/EBA_TECHNICAL_BOOK_AND_SEMINAR_OUTLINE_20261022.md) with one external peer-reviewed source and one independently executable exercise per chapter; do not publish a finished book before content and rights review.
8. **Version/release checks**: reproducible GitHub CI, immutable artifact hashes, actual independent live article URL readback, file ownership/asset licenses and rollback before saying published.

## E. What "the end" can and cannot mean

A science program cannot certify that *all* suffering in the entire universe is zero. No finite dataset spans all people, species, time, places or private experience, and instruments have missingness and different validity. The moral objective can be universal; the empirical claims must be **bounded and falsifiable**: population/time/instrument/treatment/control/estimate/uncertainty/cost/harms/unknown cases, plus coverage and replication. Suffering not observed = NOT_MEASURED; uncertain effect = INCONCLUSIVE; a harmful action remains harmful even if some other benchmark scores rise.

**Definition of an accepted Manager field release:** the software really operated on an owned or validly permissionless surface with scoped authority, provable external state and rollback; benefits in at least two domains were independently measured on valid outcomes; a preregistered comparator supports credible net effect; harmed groups and costs are disclosed; outside reviewers can inspect original sources and reproduction code; invalid claims/optimization can be challenged and retracted. No one may turn P0 synthetic success into this scientific conclusion by editing tasks.json.
