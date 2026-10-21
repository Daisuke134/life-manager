# Behavior × AGI — Living lab seminar V3 (39-slide, English, editable)

**Date reviewed:** 2026-10-21 (JST)  
**Purpose:** beginner-to-research-proposal seminar: the foundations of human-behavior prediction, social simulation, counterfactuals, intervention experiments, scientific validity, active companies, and Manager's proposed independent-benefit loop.  
**Research truth:** no independently proven Manager beneficiary gains. A model's simulation, tool success, source matching or internally reported benchmark is not a completed real-world intervention.

## Saved user-owned deliverables

- Main editable deck: ChatGPT Library `/Manager/Research/Manager_Behavior_AGI_EndToEnd_Lab_Seminar_v3_2026-10-21.pptx`.
- Original reproducible Python source: `/Manager/Research/build_manager_behavior_research_seminar_v3.py`.
- Original generated cover art: `/Manager/Research/Manager_Research_Hero_2026-10-21.png`.
- Full-slide contact-sheet preview: `/Manager/Research/Manager_Behavior_AGI_EndToEnd_v3_preview.png`.
- PPTX SHA-256: `8dbc6795248604db5a8c2f9d21f1f24374a7e7ba57091f2015a748710fb20447`. 39 slides; visual rendering and contact-sheet inspection performed. This is the **condensed v3 alternative to the existing 44-slide v2 lab deck**, not an overwrite of historical v2, C001 evidence, or an academic peer-review claim.
- PDF was not newly produced as a deliverable in this revision; the earlier 44-slide v2 PDF remains separate.

## Presentation sequence

| Slide range (1-indexed) | Narrative | Reader should leave understanding |
|---|---|---|
| 1–3 | Mission, central research question, five evidence layers | Manager's aim is to *verify* societal benefit, not merely generate plausible people |
| 4–7 | Population and probabilistic behavior; conditional distributions, TVD/Brier/calibration | Representativeness, response prediction and causal validity require different benchmarks |
| 8–10 | Counterfactuals, DAGs, micro-randomization | `P(Y\|X)` is not the same as `P(Y\|do(T))` |
| 11–14 | Research history, Generative Agents, Concordia | Memory/reflection/agent interaction and environment adjudication |
| 15–18 | Centaur/Psych-101; SocSci210; EDSL; AgentTorch/OASIS/AgentSociety | Neural cognitive modeling vs social-science fine-tuning vs simulation frameworks |
| 19–26 | Company and method comparison, Simile, Aaru, Artificial Societies/Radiant, validation tests | Accurate attribution of vendor-reported human comparisons and separate group-network evidence |
| 27–30 | Manager evidence readbacks: HeartSteps mismatch, public UCI holdout, synthetic causal counterexample | What the project has actually verified and what it has not |
| 31–35 | Proposed general kernel, public Blessing receipts, falsifiable hypotheses and three candidate experiments | Source → lawful action → independent readback → credible net benefit |
| 36–39 | Mission, primary links, closing | Specific sources, limitations and the scientific research thesis |

## Primary-source claim / method / limits

| Slide(s) | Claim | Source, category and method | Boundary |
|---|---|---|---|
| 13–14 | Generative Agents, memory/reflection/planning; Concordia Game Master | Park et al. 2023 [paper](https://arxiv.org/abs/2304.03442) / [Google DeepMind code](https://github.com/google-deepmind/concordia) | Believability is not a field impact result |
| 15 | Centaur on 160 experiments, 60,092 participants, 10,681,650 choices | [Nature original 2025](https://www.nature.com/articles/s41586-025-09215-4), original observational cognition benchmark | Not general-purpose welfare intervention |
| 16 | SocSci210 210 studies, 170/40 study-ID mapping, ~2.9M records | [Socrates paper](https://arxiv.org/abs/2509.05830), original study and source metadata | Manager only verified study metadata; 40-study respondent metric remains unmeasured |
| 17–18 | EDSL instruments, Concordia alternative simulation frameworks | [Expected Parrot](https://github.com/expectedparrot/edsl), [AgentTorch](https://github.com/AgentTorch/AgentTorch), [OASIS](https://github.com/camel-ai/oasis), [AgentSociety](https://github.com/tsinghua-fib-lab/AgentSociety) | Package capabilities not proof of human fidelity |
| 20 | Simile predicts responses to scenarios; reports uncertainty validation | [Company technical source](https://www.simile.com/blog/confidence), vendor-evaluated product | No claim Simile fails to test against real observations |
| 21 | Aaru reports 2,993-question survey evaluation (TVD 7.62 unadjusted) and transaction panel analysis | [Aaru primary corporate research](https://aaru.com/publications/population-simulation-at-the-replication-floor-research), company-authored methods/results | Not head-to-head with Radiant or Manager on identical tasks |
| 22–23 | Radiant society graph, surveys/interviews/focus groups; Persona Genesis→Society Assembly→simulation | [Product](https://societies.ai/radiant), [method](https://societies.ai/knowledge/the-science-behind-artificial-societies), publicly described vendor architecture | Internal persona-generation/model weights not audited |
| 24–25 | Internal/construct/external validity, 11 tests; company reports 0.08 TVD vs 0.31 and 68,280 test answers | [Chidichimo et al. preprint](https://arxiv.org/abs/2609.30030), [AS benchmark](https://societies.ai/as-benchmark) | Preprint/company evaluation, not independent Manager replication or causal beneficiary effect |
| 28 | HeartSteps original counts vs alternate public sample | [RCT](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/) + project's pinned public-CSV diagnostic and [real-data CI](https://github.com/Daisuke134/life-manager/actions/runs/39526839889) | Exact historical selection not replicated; H005 skipped |
| 29 | Public daily bike demand: 2011 365 train vs 2012 366 holdout; MAE 2489 vs 2304 | [UCI original dataset](https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset), [Manager independent execution](https://github.com/Daisuke134/life-manager/actions/runs/39545601251) | Observational aggregate forecasting, no randomized causal effect or proven welfare |
| 30 | Example marginal TVD=0 but constructed causal effect error=0.4 | Manager [synthetic analytic tests](https://github.com/Daisuke134/life-manager/tree/research/manager-product-r006-20261020/products/manager) | Artificial math counterexample, no empirical human effect |
| 31–36 | Manager's proposed kernel and Transparent Blessing | Internal Manager design hypothesis, not a third-party scientific result | NO verified real-world beneficiary improvements; legitimate authorization and independent audit remain necessary |

## Scientific and communication quality requirements

- Distinguish original peer-reviewed / company preprint / company-claimed benchmark / Manager-run observational benchmark / synthetic construction / unimplemented proposal.
- *Never* compare unlike TVD numbers as if models were evaluated on the same study split.
- Do not equate network homophily (33,299 chatbots, He et al., [British Journal of Psychology](https://doi.org/10.1111/bjop.12764)) with the predictive validation of the commercial Radiant survey platform.
- Radiant official pages differ on minimum society size: some say 12, some 20. The deck intentionally does not declare an exact stable minimum.
- The sample internal architecture is an ambition to **End suffering**, not verified global optimizer, omniscience or superintelligence.
- Reuse this guide when the living presentation is revised; preserve source URL/version and slide mapping for every material number.
- No original third-party participant records, journal PDFs or copyrighted images were included. Cover image is project-generated.

## Deployment / publication status

- **Research seminar v3 file:** saved to ChatGPT Library, not posted as a new public page.
- **Radiant in 26-organization ecosystem map:** already preserved under `docs/landscape/2026-10-20-behavior-intervention-entities.{json,md}` with a separate, detailed original technical review in `docs/research/societies/RADIANT_2026-10-21_JA.md`. No duplicate company record.
- **Daily newsletter:** the independently configured Behavior × AGI Daily scheduled task is enabled, starting October 22 at approximately 08:00 JST. Actual future editions/notification delivery must be verified per run; its creation is not evidence of publication on the site or X.
- **Social posts / blog:** require actual provider receipts and live canonical URL readback. No phantom tweets or published slides.

## Scientific program next

1. Choose rights-cleared experimental human data and measure calibrated study-heldout predictions and treatment-effect fidelity separately.
2. Evaluate networked agent behavior against heldout observed human social-influence experiments rather than visual plausibility.
3. Build first small, consent/authority-scoped intervention and public outcome ledger with independent readback, comparison, costs, distributional harms and rollback.
