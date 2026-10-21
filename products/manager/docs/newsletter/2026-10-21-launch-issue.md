# Behavior × AGI Daily — Research Brief #0
*21 October 2026 · Launch issue / research baseline, not a claim that every item was published today.*

## Lead: Radiant makes simulated audiences behave like interconnected societies

**What changed:** Artificial Societies' Radiant product presents a combined society graph, mass surveys, persona interviews, group discussions and research assistant. The company's October 1 benchmark reports population-level TVD **0.08** versus **0.31** for the best of nine tested generic LLMs, across seven human survey sources, 2,796 represented respondents and 68,280 simulated answers.

**Why experts should care:** This shifts the marketing comparison away from “is the persona believable?” toward whether the generated answers preserve **population distributions, subgroup differences, response-process biases and intervention contrasts**. Radiant's published 11-test framework is worth close inspection; its product evaluations are company claims and need independent replication.

**Manager relevance:** Build a study-disjoint, rights-cleared benchmark with an explicit subgroup error table and randomized-effect error. Never treat distribution fit as net welfare impact.

- Product https://societies.ai/radiant
- Corporate metrics https://societies.ai/as-benchmark (published 1 October 2026)
- Scientific framework https://arxiv.org/html/2609.30030 (v2 dated 1 October 2026)

## Science: Eleven validity tests should become standard practice

**Primary source:** Chidichimo, Jung, Wallis, He (2026), [Artificial Societies Benchmark](https://arxiv.org/html/2609.30030).

Their 11 proposed tests span repeated questions / survey perturbations (internal), relationships among psychological traits (construct), and overall distributions / individuals / groups / treatment effects (external). A model can match an average but misrepresent **who** believes it, **why** connected answers vary, and **what** changes after a treatment.

**Status:** Author-affiliated research preprint—not a universal independent certification. We should separate any replications by dataset, rights, group, effect and uncertainty.

## Technical context: Simile predicts its prediction error

**Prior milestone, not breaking news:** Simile's 2026 [confidence-method article](https://www.simile.com/blog/confidence) describes roughly 8,600 held-out questions, and a confidence model trained to predict expected distributional error (TVD) from model representations. The company reports a 0.73 AUROC from a simple hidden-state probe on its evaluation setting. Its [What-If Machine](https://www.simile.com/blog/what-if-machine) spans hypothetical prices, products, messages and policies.

**Relevance:** For Manager, an action should be withheld when expected error exceeds an explicit limit; uncertainty score does not itself establish causal welfare benefit.

## Evidence caution: Homo Silicus is not the whole society

An earlier Artificial Societies team paper in [British Journal of Psychology](https://doi.org/10.1111/bjop.12764) used 33,299 AI chatbots to observe language/content homophily. This matters for the network layer. It is not proof of simulated finance, healthcare or political actions in the real world.

## Three research actions for Manager

1. Add Radiant to the canonical company map without double counting Artificial Societies, and retain distinct dates and evidence types.
2. Compare **frequency → LLM persona → network-structured simulation** on a rights-cleared empirical experiment with TVD, subgroup error and intervention-effect error. Retain the S002 rights ledger and anonymization restrictions.
3. Define a public “Blessing Receipt” schema separating model prediction, authorized action, independent external readback, costs, harms and causal assessment.

## X post draft (English, not posted)

> The future of human simulation isn't “1,000 AI personas said yes.” It's asking whether the same model reproduces human answer distributions, subgroup differences, measurement effects—and real treatment effects. Radiant's 2026 work makes that gap harder to ignore. We still need independent outcome proof.

## Editorial follow-through

**Long article:** “Radiant: What Happens When a Synthetic Audience Becomes a Society?”  
**Living lab deck:** Behavior models → synthetic populations → societal simulations → 11 validity tests → interventions → Manager's research proposal.  
**Book chapter:** “From Simulated Opinion to Measured Welfare,” including honest failure cases.  
**Service hypothesis:** Free daily signal + permanent cited archive; optional paid reproducibility notes, annotated datasets, editable lecture slides and independent benchmark notebooks. Paid demand, permissioned distribution and measured subscription conversion are not yet established.

**Editorial rule:** Date every item accurately. Distinguish recent publications, background research, company claims and findings that Manager reproduced. No fabricated beneficiary counts, publication receipts, or X posts.
