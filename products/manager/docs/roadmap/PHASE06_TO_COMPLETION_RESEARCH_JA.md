# Manager — Canonical remaining task map and priority plan (research view)


> **歴史的な2026-10-21時点の研究分解。現行の実装順ではありません。**
>
> **E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12 → E13 → E14 → E15 → E16** が現行唯一の実装順。現在の技術カーソルはE16（E01–E15は限定実装のreceiptあり）。**F005 → F006 → F008 → F009** は実装後の証拠による受け入れ判定。F004/F007は必須経路から外れ、履歴を保存した `skipped`（未実施）。
>
> 下記の旧F系54分解（旧F004の第1手順など）は**当時の原案の歴史的記録**であり、E01〜E16と同じ名前の現在の作業でも、現行の実装順でもありません。タスク状態・順序・カーソルSSOTは [`tasks.json`](tasks.json)、詳細は [Core実装計画](../plans/2026-10-22-manager-core-execution-plan.md)。

現行の全Phase/残41件は [全工程view](START_TO_END_20261022.md)。この文書の旧54分解と当時のblocked記述は現状態を上書きしない。

**Updated:** 2026-10-21. **Not a new task registry.** Read statuses/dependencies in [`tasks.json`](tasks.json), not this note; it is a cross-phase explanation. Read [evidence map](../research/2026-10-21_MANAGER_SIM_TO_REAL_ECOSYSTEM_JA.md), [F001/U001 opportunity matrix](../product/OPPORTUNITIES.md), and [authority gates](../../pilot/FEASIBILITY_AND_AUTHORITY.md).

## Phase06 — Environment-First Atomic Execution Plan (54 concrete substeps; not a second SSOT)

**As of 2026-10-21 · Working implementation breakdown ONLY; no task statuses changed here.** The only canonical task statuses/dependencies/acceptances remain in [tasks.json](tasks.json) (113 tasks, F001–F003 done, F004/F007 blocked under original finance/physical scope, F005/F006/F008/F009 todo). These `F00x.Eyy` labels are **substeps for execution**, not new tasks or an alternate registry. No redefinition of the task registry was done by this research update. **Scientific Gate1 UNMET, real human welfare NOT_MEASURED.**

**Machine-auditable design labels:** `FRICTION` = a measurable avoidable barrier in the online service journey; `STANDING_AUTHORITY` = owner-scoped, revocable capability with no per-run human approval. Publish **negative or null** results alongside positive results rather than hiding harm or overclaiming success.

**Operating principle:** **Reuse → Connect → Evaluate → Improve**. The intervention target is the **environment people act within** — readable and navigable online public services, accessible task completion, false steps removed, correct information and user agency — not creating a money printer, tracking vulnerable individuals, maximizing persuasion, PM2.5 proxies or fabricating a universal happiness score. The Internet is a real-world environment; interventions are allowed only on owner-controlled assets or genuinely lawful permissionless interfaces and require no person approving every routine action once standing scope is established. The existing Manager production runtime still prohibits live external writes until an actual reviewed separately scoped adapter exists.

**Why this is an ENVIRONMENT intervention rather than a money printer:** Society can be improved by changing the environment in which people make choices: removing friction, inaccessible navigation, dead ends and administrative complexity. See real precedents [GetCalFresh/Code for America](https://codeforamerica.org/news/reflecting-on-10-years-of-getcalfresh/) (their retrospective reports 7M+ users, not a controlled causal estimate), [J-PAL randomized SNAP study](https://www.povertyactionlab.org/evaluation/impact-informational-mailings-snap-enrollment-united-states) (31,888 households, randomized information and application assistance affected *actual enrollment*), [GOV.UK whole-service principles](https://www.gov.uk/service-manual/design/introduction-designing-government-services), [GOV.UK actual task completion definition](https://www.gov.uk/service-manual/measuring-success/measuring-completion-rate), and [W3C WCAG 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/). **Critical transfer limit:** Third-party assisted SNAP RCTs and non-profit service counts do not prove Manager has enrolled one person or reduced suffering; do not copy their agency rights or applicant data.

**Source and code reuse:** [GrowthBook Python SDK 3.2.2](https://github.com/growthbook/growthbook-python) already tested with 512 synthetic assignments, [Playwright + axe](https://playwright.dev/docs/accessibility-testing) for web accessibility, [GOV.UK Service Manual](https://www.gov.uk/service-manual), [Inspect AI](https://inspect.aisi.org.uk/) and [MentalHealthBench](https://openai.com/index/introducing-mentalhealthbench/) for *agent behavior safety*, [DoWhy](https://github.com/py-why/dowhy) and [EconML](https://www.microsoft.com/research/project/econml/) for justified causal comparison, and existing Manager `manager_core/outcome_ladder.py`, `outbox.py`, `learning.py`, `audit.py`. Use official WHO-5/WHODAS/CFPB domain outcomes only with actual valid licenses, consent and independent data. No new marketplace, cryptocurrency, score, A/B allocation engine or bespoke causal package.

**Actual baseline status:** [real public Manager source directory](../../public_goods/RESOURCE_DIRECTORY_JA.md) is externally retrievable with SHA256 and `P2_ARTIFACT_ONLY`; [GitHub Actions proof](https://github.com/Daisuke134/life-manager/actions/runs/39604846226) has 282 passing tests and synthetic GrowthBook assignment. **No deployed human trial, no operator-verified online recipient count, no measured human welfare improvement.**

**Execution contract for every code substep:** add focused failing test, confirm RED, change only the smallest existing Manager-owned file/interface, run focused + full `python3 -m unittest discover -s tests -v`, `python3 scripts/check_boundaries.py`, `python3 scripts/make_roadmap.py --check`; commit on Manager-only research branch; require exact-head GitHub CI GREEN before merge. All external release effects need real owner standing authorization, restart-safe effect intent, public independent readback and safe rollback.

### F004: Authorized DIGITAL intervention surface and rights — originally finance fund scope (still BLOCKED)

| Substep | Exactly one executable action | Reuse the existing wheel | Exact target / file | Pass criterion or fail-closed stop |
|---|---|---|---|---|
| `F004.E01` | Find the real digital environment already owned by Manager: current GitHub public research file plus any genuinely owned public service route; do not assume aniccaai.com deploy credentials | GitHub public Contents API + existing Manager READMEs | docs/product/DIGITAL_ENVIRONMENT_SURFACE_INVENTORY.md | Evidence names actual repo/branch/site owner; unknown live deployment => NO_ACTION |
| `F004.E02` | Map the FINANCIAL structural problem as information friction, not money creation: case note on eligible aid discovery, dead ends and excessive steps | Code for America GetCalFresh + GOV.UK whole-service manual | docs/product/DIGITAL_ENVIRONMENT_SURFACE_INVENTORY.md | Problem, alternative mechanisms, NO_ACTION and actual controllable interface specified |
| `F004.E03` | Inspect current official public resource links for freshness, conditions, 200/redirect/404 and rights, without copying provider application forms | MHLW / FSA source URLs + existing public resource directory | scripts/phase06_source_link_audit.py; tests/test_phase06_source_link_audit.py | Tampered, stale, redirected to untrusted site, unavailable link => mark UNKNOWN; no private data |
| `F004.E04` | Record baseline user environment: complete navigation task, visible links, keyboard access, languages, assistance routes, number of steps; do not assume real users | GOV.UK service mapping + W3C WCAG 2.2 | docs/product/BASELINE_DIGITAL_JOURNEY.md | Repeatable anonymous browser protocol and BEFORE screenshots; if site not deployed flag NOT_AVAILABLE |
| `F004.E05` | Identify one bounded action to change the environment: improve official-resource navigation and accessibility on owned site, not send unsolicited messages | Existing Manager resource directory + GOV.UK patterns | docs/product/FIRST_WEDGE.md | Action is fully reversible, separate from third-party application or payment execution |
| `F004.E06` | Choose source/rights grant from current owned-repository operation, limit exact repo/path/commit, budget, validity and rollback; human authorizes setup only | Existing K007 authority + K008 SQLite outbox | manager_core/authority.py; docs/architecture/PHASE05_KERNEL_IMPLEMENTATION.md | No automatic right to mutate other repositories or Life Manager production; default writes remain denied |
| `F004.E07` | Define an explicit scope amendment proposal for old F004 funds/issuer task: allow owner-controlled digital financial-access environment only after same-SSOT version review | Canonical tasks.json (do not create another registry) | docs/roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md | Original F004 acceptance and BLOCKED status remain intact until actual versioned amendment |
| `F004.E08` | Author tests for wrong publisher repo, forged grant, expired budget, revoked access and external provider UNKNOWN; start RED before changing live executor | Existing test_phase05_adversarial.py / unittest | tests/test_phase06_digital_authority.py | Unauthorized cases all NO_ACTION/REJECTED; no fake token or privileged test backdoor |
| `F004.E09` | Only after owner release channel, actual bounded standing grant and fail-closed CI are verified, record permission packet; otherwise continue with public read-only proof | GitHub public readback + Manager field_readiness.py | pilot/PHASE06_AUTHORITY_READINESS.json | A self-written permission string cannot authorize production; readiness otherwise UNKNOWN |

### F005: Actually change the ONLINE financial-assistance environment — original finance effect remains TODO

| Substep | Exactly one executable action | Reuse the existing wheel | Exact target / file | Pass criterion or fail-closed stop |
|---|---|---|---|---|
| `F005.E01` | Pin maintained GrowthBook SDK/runtime release and license, avoid rewriting randomization algorithm | GrowthBook Python SDK v3.2.2 existing research fixture | requirements-internet-eval.txt; scripts/phase06_growthbook_existing_sdk.py | SDK hash/license/version checked, 512 synthetic stable assignments pass |
| `F005.E02` | Define control experience as unchanged original navigation; define treatment as factual accessible links and reduced friction without hidden persuasion | GOV.UK whole-service design + original directory | pilot/INTERNET_FIRST_TRIAL_DESIGN.md | NO_ACTION available in every plan; no false eligibility or medical/financial advice |
| `F005.E03` | Create RED browser test of missing/incorrect official destinations, broken keyboard navigation, inaccessible headings and focus state | Playwright + axe-core | tests/e2e/manager_public_good_accessibility.spec.ts | Test fails against intentional fixture; no user personal records or provider writes |
| `F005.E04` | Apply only minimal owner-controlled digital navigation/accessibility changes; do not issue a new token, new marketplace or external action | Existing site components + W3C WCAG patterns | owned-site component containing Manager official resource navigation | Code change restricted to confirmed owned route; no random copy of others' pages |
| `F005.E05` | Create smoke test for source-verified service completion path, not just higher outbound click-through | GOV.UK completion-rate definition | tests/e2e/manager_public_good_task_complete.spec.ts | Cannot count a pageview as benefit application, diagnosis or completed financial transfer |
| `F005.E06` | Use existing GrowthBook on owner route with stable opt-in assignment and intentionally unchanged holdout before real rollout | GrowthBook feature flag/experiment SDK | owned-site experiment integration; pilot/INTERNET_FIRST_TRIAL_DESIGN.md | Sample ratio mismatch, assignment missing or invalid consent => stop; test vs actual participant data distinct |
| `F005.E07` | Release to exact owned surface with standing authority and immutable commit; no per-run human approval but hard release cap, rollback and stop | Existing owner release workflow + Manager K008 intent reservation | site release configuration and Manager docs/verification readback | Actual release receipt P1, not inferred from GitHub draft; without release channel stay TEST_ONLY |
| `F005.E08` | Verify HEAD/URL via external public GET, correct links, response code, content hash and NO_ACTION rollback link independently from write log | Existing public_good_readback.py + GitHub Contents API; Playwright | scripts/phase06_public_good_readback.py; tests/test_phase06_internet_public_good.py | Public changed artifact only P2_ARTIFACT_ONLY; wrong path or stale source fails |
| `F005.E09` | Record negative, missing, rejected and unchanged cases as well as success; preserve original baseline, no fake beneficiaries | Existing audit.py/outcome_ladder.py | docs/verification/PHASE06_INTERNET_PUBLIC_ARTIFACT_20261021.md | Evidence labeled P0/P1/P2 only; P3/P4 NOT_MEASURED until valid external welfare data |

### F006: Evaluate net actual FINANCIAL welfare — requires real outcomes, not clicks

| Substep | Exactly one executable action | Reuse the existing wheel | Exact target / file | Pass criterion or fail-closed stop |
|---|---|---|---|---|
| `F006.E01` | Fix FINANCIAL primary endpoint before any human exposure: actual verified retained aid/resources or lower administrative burden, not site sessions | CFPB Financial Well-Being Scale / J-PAL SNAP outcome concept | pilot/INTERNET_FIRST_TRIAL_DESIGN.md | Outcome unit, population, time window and denial/cost consequences frozen |
| `F006.E02` | Define secondary measures of time-to-correct-support, genuine task completion and economic security separately; no composite global score | GOV.UK completion-rate manual + CFPB | pilot/INTERNET_WELFARE_EVIDENCE_CROSSWALK.json | No click/visit elevated to verified money, safety or wellbeing outcome |
| `F006.E03` | Set true eligible unit and safe voluntary participation/consent policy; do not collect private applicant records without rights | NICE RWE + SPIRIT/CONSORT reporting | pilot/INTERNET_FIRST_TRIAL_DESIGN.md | If no verified real cohort, report NOT_MEASURED not fabricated n |
| `F006.E04` | Preregister randomization ratio, fixed sample-size/power, start/end, follow-up, attrition policy and NO_ACTION; freeze timestamp and hash before real exposure | GrowthBook + SPIRIT/CONSORT protocol | pilot/INTERNET_FIRST_TRIAL_DESIGN.md; hash | Experiment not considered field-ready until externally verifiable frozen protocol exists |
| `F006.E05` | Identify independently observable successful outcome: official benefit receipt or participant-volunteered valid measure, not Manager log | Official settlement/program data if available; CFPB scale with valid licensed use | docs/verification/INDEPENDENT_FINANCIAL_OUTCOME_PROTOCOL.md | No external ground truth -> no P3/P4, even if performance improves |
| `F006.E06` | Run existing DoWhy/EconML only on valid real treated/control outcome arrays; include negative effects and source/assignment checks | DoWhy / EconML + existing evaluator.py | scripts/phase06_financial_effect_eval.py; tests/test_phase06_financial_effect_eval.py | Placebo/overlap/confounding and 95% CI checks; if invalid return INCONCLUSIVE |
| `F006.E07` | Account for displaced access, false referrals, time/effort, privacy risk, compute and financial fees | Existing K011 evaluator/economic_scorecard.py | docs/verification/INDEPENDENT_FINANCIAL_OUTCOME_PROTOCOL.md | Costs/harms unknown -> UNKNOWN_HARMS; no count of minted tokens |
| `F006.E08` | Use only original population measures; do not infer poverty relief from a before-after screen or model prediction | Existing outcome_ladder.py + CFPB official scoring | scripts/phase06_welfare_proof_gate.py | P2 technical != P3 beneficiary != P4 causal net effect |
| `F006.E09` | Publish positive, null, negative or inconclusive aggregate results with transparent preregistration and reproducible code; require actual evidence to upgrade F006 | NICE, CONSORT, original Manager audit | docs/verification/PHASE06_FINANCIAL_CAUSAL_RESULT.md | If no observed results keep F006 TODO; no made-up measured effect |

### F007: Second DIGITAL environment / physical task scope proposal — original indoor facility still BLOCKED

| Substep | Exactly one executable action | Reuse the existing wheel | Exact target / file | Pass criterion or fail-closed stop |
|---|---|---|---|---|
| `F007.E01` | Treat original indoor/PM2.5 F007 as OPTIONAL historical physical test; explicitly propose digital environmental second domain in same SSOT, retain original acceptance | Current task registry and docs/roadmap/PRODUCT_COMPLETION_GATES.md | docs/roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md | scope amendment proposal with old verify preserved; never silently label old task done |
| `F007.E02` | Choose a SECOND actual online environment independent of financial navigation: accessible mental/physical public support navigation | Existing MHLW pages and Manager official-links directory | docs/product/SECOND_DIGITAL_ENVIRONMENT.md | Clear separate affected pathway, true owner controls and independent outcome possibility |
| `F007.E03` | Map friction mechanism: information overload, accessibility, inability to find appropriate support, harmful unintended effects | GOV.UK inclusion standards + WHO digital mental environment guidance | docs/product/SECOND_DIGITAL_ENVIRONMENT.md | Counterfactual and alternate reasons recorded, no psychographic targeting |
| `F007.E04` | Select existing behavioral/safety evaluator for content (no therapy claims), and adversarial failure cases | Inspect AI + MentalHealthBench | tests/test_phase06_mental_content_safety.py | No diagnosis, no crisis instruction, no blanket efficacy claim, no secret social-media manipulations |
| `F007.E05` | Adopt W3C WCAG 2.2 and Playwright/axe to measure accessible path and readability, independent of clinical claims | W3C WCAG + Playwright/axe | tests/e2e/manager_mental_physical_accessibility.spec.ts | WCAG technical failures reproducible, but 100% automated scan not certified full access |
| `F007.E06` | Define risk/consent safety boundary: opt-in, no person inference, no platform spamming, reachable official help, safe exit | WHO mental-health implementation and NICE ESF | pilot/SECOND_DIGITAL_ENVIRONMENT_SAFETY.md | High-risk claim/harm -> NO_ACTION and external help option visible |
| `F007.E07` | Define outcome families separately: appropriate voluntary WHO-5 for mental, WHODAS for functioning only with rights and valid context | WHO-5 / WHODAS published validated instruments | pilot/INTERNET_WELFARE_EVIDENCE_CROSSWALK.json | No copying restricted question banks; without human observations status NOT_MEASURED |
| `F007.E08` | Use owned channel standing release authority, cost, revocation and emergency stop independent from first domain; never need per-run approvals | Existing K007/K008, owner site release path | docs/product/SECOND_DIGITAL_ENVIRONMENT.md | Second channel actually controllable or remain proposed/NO_ACTION |
| `F007.E09` | Document why approved public online infrastructure needs no NPO/indoor-owner deal, but also why source URLs alone do not establish welfare | Digital Public Goods Standard + GOV.UK service design | docs/verification/PHASE06_SECOND_DOMAIN_BOUNDARY.md | F007 original blocked until scoped-version amendment or original facility evidence exists |

### F008: Change MENTAL/PHYSICAL access environment — original PM2.5 intervention still TODO

| Substep | Exactly one executable action | Reuse the existing wheel | Exact target / file | Pass criterion or fail-closed stop |
|---|---|---|---|---|
| `F008.E01` | Freeze measurable original navigation task and independent baseline on second domain before change | GOV.UK whole-service journey + Playwright | docs/product/SECOND_DIGITAL_ENVIRONMENT.md | Number of steps and failures from reproducible test, not unobserved real users |
| `F008.E02` | Write failing accessibility/clarity regression that covers small screens, keyboard, focus, accessible links and language | Playwright axe-core | tests/e2e/manager_mental_physical_accessibility.spec.ts | Demonstrate RED under intentionally broken fixture, no staged real patient data |
| `F008.E03` | Implement smallest owned-site link/navigation restructuring from existing official resources rather than an AI therapist | MHLW public links + GOV.UK design patterns | owned-site second-domain component | No AI diagnosing, coercion, personal persuasion or privacy-invasive tracking |
| `F008.E04` | Retain real NO_ACTION baseline variant and stable GrowthBook assignment for any actual consenting experiment | GrowthBook Python/web SDK | second-domain GrowthBook config + tests | Unknown/insufficient sample ⇒ no causal lift verdict |
| `F008.E05` | Verify published second-domain URL from independent read-only browser/GitHub sources; preserve rollback | GitHub REST API and Playwright | scripts/phase06_second_domain_readback.py; tests/test_phase06_second_domain_readback.py | Two real changed *artifacts*, not two beneficiaries nor mental/physical improvement |
| `F008.E06` | If user outcomes can ethically be observed, use correctly licensed WHO-5/WHODAS administered voluntarily; no passive mental-state inference | WHO instruments + NICE evidence | pilot/SECOND_DIGITAL_ENVIRONMENT_SAFETY.md | Genuine consent and follow-up; no outcome records means NOT_MEASURED |
| `F008.E07` | Measure negative exposure and time/effort: distress, misleading referral, delayed official care, accessibility regressions and attrition | WHO digital mental environment + GOV.UK inclusion | docs/verification/PHASE06_SECOND_DOMAIN_OUTCOMES.md | Predefined adverse effect triggers stop/reversion and publication of negative result |
| `F008.E08` | Apply preregistered DoWhy/EconML comparison only if treatment/control and welfare outcome truly observed; no WAI technical metrics promoted to clinical | DoWhy/EconML + existing evaluator.py | scripts/phase06_second_domain_effect_eval.py | 95% CI, harms, missing and no-action; never claim fewer illnesses from web link |
| `F008.E09` | Generate evidence report tagged artifact P2 only until actual valid human well-being/function outcomes are measured | Existing outcome_ladder.py / proof levels | docs/verification/PHASE06_SECOND_DOMAIN_OUTCOMES.md | If original F008 physical PM2.5 acceptance unchanged, keep TODO even with digital accessibility improvement |

### F009: Prove common kernel and cross-domain effects — no synthetic shortcuts

| Substep | Exactly one executable action | Reuse the existing wheel | Exact target / file | Pass criterion or fail-closed stop |
|---|---|---|---|---|
| `F009.E01` | Define one shared source→problem→NO_ACTION→grant→intent→readback→evaluation interface for FINANCIAL and MENTAL/PHYSICAL digital adapters | Existing Phase05 manager_core/kernel.py + source/authority/outbox | docs/architecture/PHASE06_DIGITAL_CROSS_DOMAIN_CONTRACT.md | No domain-specific security bypass or hidden live enablement |
| `F009.E02` | Prove repeated intent submission and provider timeout/unknown do not duplicate publishing or external effects in both domains | Existing K008 tests and identical public readback adapter pattern | tests/test_phase06_multi_domain_execution.py | At-most-once attempts, never 'exactly once' claim; unknown never P2 |
| `F009.E03` | Verify both published online *artifacts* from independent sources before-after with SHA/URL/units and no P3 claim | Existing public_good_readback.py + GitHub API | scripts/phase06_cross_domain_readback.py | Distinct domains P2_ARTIFACT_ONLY with independent public response; no fabricated uses |
| `F009.E04` | Align distinct domain outcome instruments and denominator/units without mixing dollars, WHO-5 or WHODAS | Existing WHO/CFPB source crosswalk | pilot/INTERNET_WELFARE_EVIDENCE_CROSSWALK.json | Different outcomes separate; single invented SufferingScore forbidden |
| `F009.E05` | Build read-only aggregate Proof Explorer on the SAME existing registry/proof ladder, or satisfy U005 dependency before claiming product Gate2 | Existing audit.py/outcome_ladder.py + public original evidence refs | docs/product/PROOF_EXPLORER.md / existing site owned route | External reader can follow original sources and challenge each level |
| `F009.E06` | Run isolated policy alternative on held-out/shadow data, prohibit self-expanded rights, preserve quick revert when outcome degrades | Existing K012 PolicyLearner + heldout tests | tests/test_phase06_policy_shadow_rollback.py | Rollback to validated version, budget/revocation unchanged |
| `F009.E07` | Only when both real populations have comparable authentic outcomes and controls, compute independently reviewed causal estimates with costs/harms | DoWhy/EconML + K011 evaluator | docs/verification/PHASE06_CROSS_DOMAIN_FIELD_CAUSAL.md | P3/P4 granted solely on verified human improvements; otherwise NOT_MEASURED |
| `F009.E08` | Publish transparent negative/null and unresolved outcome report, real CI/commit/URL links and optional reproduction artifacts | Existing audit trail + CONSORT/NICE evidence labels | docs/verification/PHASE06_CROSS_DOMAIN_FIELD_CAUSAL.md | No omitted nonresponse or spoofed case; digital delivery ≠ relieved suffering |
| `F009.E09` | Cross-check F004-F009 actual original acceptance and any approved versioned scope amendment against one tasks.json, regenerate atomic backlog only for genuine DONE | Existing tasks.json + scripts/make_roadmap.py | docs/roadmap/tasks.json; docs/roadmap/ATOMIC_BACKLOG.md | Never mark blocked/unfinished as DONE; CI green plus external scientific proof required |

### Execution order, scientific gates and legacy tasks

**Highest-leverage immediate sequence:** `F004.E01→E05` inventory and journey baseline → `F005.E01→E04` Playwright/axe and GrowthBook contract → `F007.E01→E06` distinct safe second-domain public-service design → `F008.E01→E04` accessibility-first improvement → `F009.E01→E06` common safe kernel, external URL proofs and rollback. `F006`, `F008.E06–E08`, `F009.E07–E09` **cannot** be called DONE without real human outcomes. Avoid over-optimizing pure technical proxies.

**scope amendment proposal (NOT APPLIED):** The earlier F004 funding administrator and F007 indoor facility/PM2.5 plans should be treated as **optional alternative adapters** rather than the sole route to world engineering; a controlled digital FINANCIAL access intervention plus a separately verified digital MENTAL/PHYSICAL access environment is the proposed v2 outcome. Before changing any canonical acceptance, retain `original_change`, `original_verify`, `original_external` and historical `status` for the original F004/F007, retain causal/net welfare strictness of F005/F006/F008/F009, update tasks.json **in-place** with explicit versioned rationale and verified tests. No second SSOT and no retrospective completion. **Current F004/F007 still blocked.**

**NO_ACTION, standing authority and welfare:** The agent can continually perform allowed ordinary digital operations under a bounded asset-owner standing grant without *per-run* human approval, but cannot autonomously issue itself legal rights to third-party money, accounts, facilities, social media identities or confidential data. Delivery should disclose purpose, preserve user autonomy, be opt-in where needed, and must not rely on covert personal psychological targeting. Genuine beneficiary effectiveness often requires **voluntary** follow-up and rights-cleared wellbeing measurement — voluntary beneficiary outcome reporting is not approval of an individual agent operation.

**P0** model/synthetic allocation; **P1** authenticated action receipt; **P2_ARTIFACT_ONLY** independent real internet artifact changed; **P3** genuine observed beneficiary outcome; **P4** credible preregistered causal net benefit with cost/harm; **P5** independent replication if valid. If evidence is missing, return `NOT_MEASURED` or `INCONCLUSIVE`; NEVER upgrade a GitHub file, page click, persuasion score or external ledger observation to proved human welfare.

---

## Internet-first / reuse-only milestone route — Reuse → Connect → Evaluate

**Decision, 2026-10-21:** Internet interactions *are* real-world interactions. Start with open public information and owned online software/assets; partner/NPO and third-party indoor building trials are **optional, not on the critical path to proving online Manager autonomy**. A first practical alternative must satisfy platform terms and beneficiary agency; no person should have to approve each routine run. The scientific proof, however, still requires authentic independent outcomes and often voluntary opt-in responses. An unseen click is not wellbeing.

**First reuse existing tools, in dependency order:** [Inspect AI](https://inspect.aisi.org.uk/) / [MentalHealthBench](https://openai.com/index/introducing-mentalhealthbench/) for agent conversation and safety tasks → [GrowthBook](https://github.com/growthbook/growthbook) or existing [PlanOut](https://facebookarchive.github.io/planout/index.html) for A/B allocation on an *owned* digital surface → [Playwright with axe](https://playwright.dev/docs/accessibility-testing) for accessible browsing and external visible state → [DoWhy](https://github.com/py-why/dowhy), [EconML](https://www.microsoft.com/research/project/econml/) or [Open Bandit Pipeline](https://github.com/st-tech/zr-obp) for justifiable causal estimands → [NICE](https://www.nice.org.uk/corporate/ecd7/chapter/how-to-meet-the-standards), [SPIRIT/CONSORT](https://www.consort-spirit.org/published-statements) for actual study evidence. **No new proprietary benchmark or novel suffering score.** Map existing Manager `V002 OutcomeBench` to upstream metrics without falsifying the registry.

**Welfare outcomes must be actual, not generated labels:**
- **MENTAL:** voluntary WHO-5 wellbeing or NHS-style reliable improvement reporting, honest attrition/adverse experiences; do NOT automatically ship a mental-health treatment based only on MentalHealthBench response scores or WHO Step-by-Step guided trials.
- **PHYSICAL:** WHODAS functioning or rights-cleared PROMIS outcomes, pain/function where directly relevant; an accessible webpage or air-quality time series alone is technical/intermediate P2, not clinical P3/P4.
- **FINANCIAL:** CFPB financial wellbeing, FAO FIES and verified net retained household resources, or World Bank PIP for population baseline; token emissions, site conversions, simulated balance and self-transfer are *not* newly created wealth.

**First operational experiment on existing owned site, not a newly invented marketplace:** choose one existing Manager-controlled web resource where a factual improvement is within published ownership/terms; acquire legitimate standing capability once; record dated source rights, cost and rollback; use public or voluntarily opt-in audiences (no private profiles/unsolicited messaging), randomly retain NO_ACTION control with unchanged experience, deliver transparent sourced nonclinical/noninvestment information, measure accessibility/readback directly and meaningful wellbeing only when consented appropriate data can be collected. If not, mark welfare `NOT_MEASURED`, not success. Autonomy = no per-run human operations; not freedom to seize third-party assets.

**F004–F009 mapping without falsification:** F004 originally demands real finance issuer/funds consent and is blocked for a third-party aid-transfer study. Existing own-budget lawful capabilities can be used to test a new internet-first financial public good, but cannot be retroactively counted as a funded charitable RCT. F007 demands physical facility/indoor sensor consent and remains blocked on that precise scope; do not let this optional physical project stop digital-first research. F005/F006/F008/F009 still require their actual task-specific real field evidence or a clearly versioned amendment to the **same** `tasks.json` before a status change. No false Phase06 full completion.

**Near-term eval release:** assemble a public, versioned *reuse-only evidence bundle* rather than designing new math: each case links population/consent, preregistered instrument, upstream library and version/license, source hash, assignment/no-action, effect confidence intervals, attrition, negative harms, technical receipts, sensitivity, and independent aggregate outcome source. Show P0/P1/P2/P3/P4 as existing Manager types, not a single invented scalar. **Evidence Gate1 and human net welfare UNMET** until independent field outcomes.

Reference: [expanded 87-source reuse inventory](../research/crossfield-20261021/SOURCES.json), [research synthesis](../research/crossfield-20261021/REPORT_JA.md), [autonomy doctrine](../MANAGER_NO_HUMAN_WORLD_ENGINEERING.md).

## Already complete at the scoped task level

- Phase00 P001–P006 **6 done**; Phase01 R001–R008 **8 done**; Phase02 L001–L012 **12 done**.
- Phase03 H001–H004, H006–H010 **9 done**; H005 **1 scientific skipped** (original source data insufficient for exact original analytic cohort). The 2019 RCT replication remains scientifically unresolved and must NEVER be claimed.
- Phase04 S001–S008 **8 done**, specifically narrowed, not a valid original human causal simulation replication.
- Phase05 K001–K014 **14 offline-software done**, same offline kernel across finance/environment, **P0 only**.
- Phase07 C001 **done**; Phase11 Y006 **done** (separate source-backed article), NOT a completed public product impact.

## Step 0: Complete science without redoing completed code

Rethink H005 as an unresolved scientific limitation, not an undone engineering task. Investigate feasible **independent** original randomized data: Hillstrom 64k randomized email, historic energy RCT published aggregate, authentic HeartSteps available data with defensible alternative estimand, or data owners’ additional fields with permissions. Freeze paper version, data license, exact treatment assignment, comparator, held-out groups and uncertainty. Do not upgrade Gate1 until predictive human-conditional tasks and randomized effect error independently hold up. Old Phase04 S005 MiniLM 800 vs SmolLM 320 are not directly comparable.

## Phase06 F001–F009: from offline to observed field evidence

- **F001** — document candidate finance/environment operators, source rights, feasible outcome metrics and unavoidable blocker; never assume user approval is legal permission. See opportunity matrix.
- **F002** — preregister ONE concrete, legal trial in `pilot/PREREGISTRATION.md`: units, comparator, n/power, duration, efficacy window, costs/harms, stop rule and privacy.
- **F003** — implement independent real public finance ledger **read-only** adapter with source hash/time, provider failures and independent comparison. Do not interpret published donation as beneficiary improvement.
- **F004** — BLOCKED: real designated issuer/fund grant/third-party consent and enforceable limits. Never self-authorize.
- **F005** — only once F004 is met: small bounded live intervention and externally corroborated P1/P2.
- **F006** — compare primary real outcome, harms, displacement, uncertainty; report null/negative and inconclusive.
- **F007** — BLOCKED: owner consent for a physical facility, licensed/calibrated indoor sensors and actuation.
- **F008** — permitted PM2.5 actual change plus external ambient comparator, kWh, dB and worker/occupant negative effects.
- **F009** — real independently observed P2+ in **both** finance and environment using the unchanged kernel.

## Phase07

- **C002** — create/originally review English/Japanese article/illustration/slide package based on F006's actual field evidence. Publishing is a separately authorized action; no fabricated P4.

## Phase08 U001–U008: actual beneficiaries and product market fit

- **U001** — 3+ comparative beneficial opportunities with real public-signal/source, harm mechanism, operator, alternative, causal comparator. See matrix.
- **U002** — 5+ genuinely consented interviews across operators, beneficiary groups and supporters, with actual recorded needs.
- **U003** — choose first wedge using evidence from U002 and exact owner/readback/cost limits; record rejected options.
- **U004** — preregister and hash-freeze first experiment design before seeing field results.
- **U005** — public read-only Proof Explorer with original URL verification and P0/P1/P2 boundary.
- **U006** — actual authorized intervention plus externally provable timestamped result.
- **U007** — real net-beneficiary effect, uncertainty and harms; unknown vs zero distinct.
- **U008** — verifiable paid/support commitment or sustained use; zero revenue means report zero.

## Phase09 D001–D016: independent multi-domain evidence

- **Finance D001–D004** — differentiate outside resources from self-funded matching; account for displacement; verify genuine recipient welfare; replicate.
- **Environment D005–D009** — sensor provenance/calibration; controls for time/weather; account for energy/noise; exposure isn't clinical health; reproduce at multiple sites.
- **Work D010–D012** — lawful public job/bounty opportunities; actual delivery/acceptance/payout independently distinguished; net pay less time/fees.
- **Social D013–D015** — public aggregate validated social needs without profiling; ethically permitted data partnership; protect beneficiary rights and abstain on harm.
- **Cross-domain D016** — no false summing of dollars, air quality and mental wellbeing; publish weighting/uncertainty if any shared score is used.

## Phase10 V001–V006: generality and continuous evaluation

- **V001** 3+ adapters without kernel-specific domain branches; **V002** OutcomeBench split descriptive prediction/ATE error/external outcomes/harms; **V003** group, time and geographic out-of-distribution stop; **V004** sandbox→shadow→small real canary with rollback and strict power; **V005** external reproduction of evidence and independent P levels; **V006** portfolio reporting positives, negatives and unknowns, never fabricated cumulative benefits.

## Phase11 Y001–Y008 (Y006 already done): founder and dissemination, separate proof

- **Y001** truthful English problem/beneficiary/evidence narrative; **Y002** working demonstrator video with P0 boundary; **Y003** officially submitted YC W27 application (deadline must be freshly checked on YC official site); **Y004** 10+ public-source researcher map; **Y005** 5 consented appropriate contacts/response status; **Y006 DONE** original research draft; **Y007** audience-appropriate slides with citations; **Y008** permission-checked publication with public URL readback.

## Phase12 G001–G006: legitimate governance and durable operations

- **G001** public-benefit charter, appeal, revocation, permanent audit and independent emergency stop; **G002** outside auditors and incident reporting; **G003** multi-region/demographic replication; **G004** independently permissioned read/write API contract; **G005** sustainable cost model *distinct* from human benefit; **G006** ongoing audit of harms and unmeasured suffering, never claim an absolute end to suffering.

## Priority order and gates

1. Reuse existing simulation market/environment first, build portable **evidence adapters** rather than a new marketplace. Two scored pilot candidates are **read-only** public-data and sandbox tests.
2. Next executable dependency: `F002` prereg if actual first wedge and operator/counterfactual can be specified; `F003` real read-only ledger; `U002` interviews; `D010` OSS opportunity contract and `Y001` truthful pitch can run independently.
3. `F004` and `F007` remain BLOCKED by external rights; no amount of model improvement overrides legitimate property rights/worker consent.
4. `F005` onward demands external evidence, not passing CI. First real P1/P2 then valid P3/P4, then P5 across domains; the mission remains open-ended even after every finite task is DONE.

**Completion conditions:** finite engineering tasks may be done, scientific/field/product/ethics gates may remain UNMET. The project should report this distinction prominently on every outcome page.
