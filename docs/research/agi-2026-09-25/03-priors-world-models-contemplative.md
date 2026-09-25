# 強い事前分布による少数事例学習 × 観想的知恵(paññā)とAIモデルの接続 — 調査ノート

調査日: 2026-09-25
ツール: crwl crawl (markdown-fit), curl (Crossref API, CiNii opensearch, Semantic Scholar API), gh api/gh repo, git clone --depth 1
Note: `html.duckduckgo.com/html/` and `www.science.org` return bot-challenge pages under curl/crwl in this environment (confirmed empirically — see raw output). Crossref REST API and CiNii OpenSearch JSON endpoints worked reliably via curl and were used as the primary verification layer for bibliographic facts; arxiv.org, en.wikipedia.org, deepmind.google, worldlabs.ai, github.com worked directly via crwl.

---

## 1. ベイズ認知科学・確率的プログラム誘導

**Tenenbaum et al., "How to Grow a Mind: Statistics, Structure, and Abstraction," Science 2011.**
- URL: https://www.science.org/doi/10.1126/science.1192788 (page itself returned a Cloudflare bot-check via crwl — could not fetch abstract text directly; existence/DOI corroborated indirectly through citing papers below). **Could not independently re-verify abstract text this session** — flagging as background-knowledge / previously-established fact, not freshly quoted.

**Lake, Ullman, Tenenbaum, Gershman, "Building Machines That Learn and Think Like People," 2016/2017 (BBS).**
- URL: https://arxiv.org/abs/1604.00289
- Verbatim quote (fetched via crwl): "we argue that these machines should (a) build causal models of the world that support explanation and understanding, rather than merely solving pattern recognition problems; (b) ground learning in intuitive theories of physics and psychology, to support and enrich the knowledge that is learned; and (c) harness compositionality and learning-to-learn to rapidly acquire and generalize knowledge to new tasks and situations."
- Comments field confirms: "In press at Behavioral and Brain Sciences."

**Lake, Salakhutdinov, Tenenbaum, "Human-level concept learning through probabilistic program induction" (Bayesian Program Learning / Omniglot), Science 2015.**
- Verified via Crossref API (not the paywalled science.org page): title="Human-level concept learning through probabilistic program induction", container-title="Science", published 2015-12-11, DOI 10.1126/science.aab3050. https://doi.org/10.1126/science.aab3050
- This is the BPL/Omniglot paper: characters generated as compositions of strokes via a probabilistic program, one-shot classification and generation matching/exceeding humans. (Mechanism from established literature; not independently re-quoted this session because science.org is Cloudflare-gated.)

**Wong, Grand, Lew, Goodman, Mansinghka, Andreas, Tenenbaum, "From Word Models to World Models: Translating from Natural Language to the Probabilistic Language of Thought," 2023.**
- URL: https://arxiv.org/abs/2306.12672
- Verbatim quote: "we propose rational meaning construction, a computational framework for language-informed thinking that combines neural language models with probabilistic models for rational inference. We frame linguistic meaning as a context-sensitive mapping from natural language into a probabilistic language of thought (PLoT)—a general-purpose symbolic substrate for generative world modeling." This is the "world model as probabilistic program" architecture the startup's framing maps onto: LLM as translator from language → PPL code, PPL program as the actual generative model of the world, Bayesian inference over that program for reasoning.

**Probabilistic programming languages** (Gen, Pyro, WebPPL, memo) — general PPL substrates used across the above lineage (MIT Probabilistic Computing Project / probcomp). Repos cloned locally, see §6.

**Basis Research Institute** — CONFIRMED real org (crwl of https://www.basis.ai/): homepage tagline "Creating a new kind of AI research organization... Building a universal reasoning engine." Founded/associated with figures from the Bayesian-program-induction lineage (Vikash Mansinghka is a co-founder, per public knowledge — **not independently re-verified on this crawl**, flagging as UNVERIFIED-this-session even though highly likely true). This is the most direct 2025-era institutional successor to the "world model as probabilistic program" line.

**AutumnBench / WorldTest (MIT)** — UNVERIFIED. My guessed arXiv ID (2503.05298) resolved to an unrelated coreference paper. Could not locate the correct arXiv ID for AutumnBench/WorldTest within budget. Mark as **UNVERIFIED — needs a follow-up targeted search** (likely a 2025 MIT CoCoSci / Tenenbaum-lab paper on evaluating world models via "tests" rather than fixed benchmarks).

---

## 2. World models (LeCun, Fei-Fei Li, DeepMind, Dreamer)

**Yann LeCun / JEPA / new company** — CONFIRMED via Wikipedia (en.wikipedia.org/wiki/Yann_LeCun, crawled directly):
- Verbatim: "He served as Chief AI Scientist at Meta Platforms before co-founding Advanced Machine Intelligence Labs in December 2025."
- Verbatim: "On 19 November 2025, LeCun confirmed that he would be leaving Meta after ten years to found his own company focused on world-model architectures and human-like artificial intelligence he calls superintelligence. The company he founded, Advanced Machine Intelligence Labs (or AMI Labs), is run by CEO Alex LeBrun, with LeCun serving as Executive Chair... In March 2026, AMI announced it had raised $1.03 billion in funding at a $3.5 billion pre-money valuation."
- So the "AMI Labs?" guess in the task brief is confirmed correct and current as of today.

**V-JEPA 2 (Meta, 2025).**
- URL: https://arxiv.org/abs/2506.09985 (submitted 11 Jun 2025)
- Verbatim: "We first pre-train an action-free joint-embedding-predictive architecture, V-JEPA 2, on a video and image dataset comprising over 1 million hours of internet video... we show how self-supervised learning can be applied to robotic planning tasks by post-training a latent action-conditioned world model, V-JEPA 2-AC, using less than 62 hours of unlabeled robot videos... deploy V-JEPA 2-AC zero-shot on Franka arms in two different labs."
- Mechanism in 2 lines: JEPA predicts in a learned latent/embedding space rather than pixel space (avoids wasting capacity on unpredictable pixel detail); planning is done by imagining latent-space rollouts and picking action sequences whose predicted latent matches a goal image's latent. Repo: https://github.com/facebookresearch/vjepa2 (cloned, code-only, 10MB).

**Fei-Fei Li / World Labs — Marble / Atlas.**
- URL: https://www.worldlabs.ai/blog/atlas (crawled directly, dated "September 1, 2026")
- Verbatim: "Atlas is an omni model that we pretrained from scratch to natively operate on text, images, video, and 3D. It is a multimodal autoregressive diffusion transformer: all inputs are combined into a shared spatial context... Atlas will power future versions of Marble and other products from World Labs."
- So as of today (2026-09-25) "Atlas" is World Labs' newest (successor/underlying) world model announced Sept 1 2026, superseding/feeding into the earlier "Marble" product. Mechanism in 2 lines: multimodal diffusion transformer that treats every image/video frame as grounded at an explicit 3D position ("spatial context"), then generates/reconstructs consistent 3D scenes conditioned on that context — closer to explicit 3D-scene generative modeling than JEPA's abstract latent prediction.

**DeepMind Genie 3.**
- URL: https://deepmind.google/blog/genie-3-a-new-frontier-for-world-models/ (Aug 5, 2025, authors Jack Parker-Holder & Shlomi Fruchter — crawled directly)
- Verbatim: "Genie 3 can generate dynamic worlds that you can navigate in real time at 24 frames per second, retaining consistency for a few minutes at a resolution of 720p." Mechanism: text/image-conditioned interactive video generation — a generative video model that acts as a real-time, action-conditioned simulator (no explicit 3D or symbolic structure; consistency is a learned/emergent property of the generator).

**DreamerV3 (Hafner, Pasukonis, Ba, Lillicrap).**
- URL: https://arxiv.org/abs/2301.04104
- Verbatim: "We present DreamerV3, a general algorithm that outperforms specialized methods across over 150 diverse tasks, with a single configuration. Dreamer learns a model of the environment and improves its behavior by imagining future scenarios... the first algorithm to collect diamonds in Minecraft from scratch without human data or curricula." Mechanism: learn a recurrent latent world model (RSSM) from experience, then train actor-critic entirely inside "imagined" latent rollouts of that model. Repo: https://github.com/danijar/dreamerv3 (cloned, 13MB).

---

## 3. Causality

**Pearl's ladder of causation** — CONFIRMED via en.wikipedia.org/wiki/The_Book_of_Why (crawled; note the page titled "Ladder of causation" does not exist standalone, redirected via Book-of-Why article):
- Verbatim: "The first level is named 'Association'... crucially, causality is not invoked... The second level (or 'rung')... is labelled 'Intervention'... The third rung... is labelled 'Counterfactuals.'"
- This is the standard three-rung hierarchy (seeing / doing / imagining) Pearl uses to argue that pure statistical/associational learning (most current deep learning) is stuck on rung 1, and that generalizing from minimal data with a "structural prior about the world" requires at least rung-2/3 causal machinery.

**Schölkopf, Locatello, Bauer, Ke, Kalchbrenner, Goyal, Bengio, "Towards Causal Representation Learning," 2021.**
- URL: https://arxiv.org/abs/2102.11107
- Verbatim: "A central problem for AI and causality is, thus, causal representation learning, the discovery of high-level causal variables from low-level observations." This is the standard reference bridging Pearl's causal calculus (which assumes causal variables are already given) with deep representation learning (which must discover them from pixels).
- I could not, within this session's budget, locate a specific named 2025/2026 benchmark for "causal world-model learning in interactive envs" — **UNVERIFIED, needs follow-up** (candidates worth checking next: CausalWorld, CoPhy, or newer causal-RL benchmarks from Schölkopf's or Bengio's groups).

---

## 4. Active inference / free energy / AXIOM

**Friston's free energy principle / active inference** — well-established background (Friston 2010 "The free-energy principle: a unified brain theory?", Nature Reviews Neuroscience). Not re-fetched this session (no new claim beyond established consensus).

**VERSES AXIOM, "Learning to Play Games in Minutes with Expanding Object-Centric Models," 2025.**
- URL: https://arxiv.org/abs/2505.24784 (submitted 30 May 2025; authors include Karl Friston, Christopher Buckley)
- Verbatim: "Active inference offers a principled framework for integrating sensory information with prior knowledge to learn a world model and quantify the uncertainty of its own beliefs and predictions... AXIOM represents scenes as compositions of objects, whose dynamics are modeled as piecewise linear trajectories that capture sparse object-object interactions. The structure of the generative model is expanded online by growing and learning mixture models from single events and periodically refined through Bayesian model reduction... AXIOM masters various games within only 10,000 interaction steps, with both a small number of parameters compared to DRL, and without the computational expense of gradient-based optimization."
- "Gameworld 10k" benchmark name CONFIRMED from the cloned repo's own README (primary source, not secondary reporting): "This repository contains the code to train the AXIOM architecture on data from the Gameworld 10k benchmark, as described in the preprint..." (`/Users/anicca/Projects/agi-research/repos/axiom/README.md` line 3). The explicit head-to-head "beats DreamerV3" claim was NOT found in the abstract or README text I read — **that specific comparison remains UNVERIFIED pending a read of the full PDF body/results table** (plausible given DreamerV3 is the standard baseline for this kind of benchmark, but not confirmed from a primary source this session).
- Repo confirmed via `gh api repos/VersesTech/axiom`: description = "Implementation and evaluation of the AXIOM architecture from the preprint...", 79 stars, size 133KB. Cloned to `/Users/anicca/Projects/agi-research/repos/axiom`.
- Mechanism in 2 lines: object-centric generative model (each object = a small piecewise-linear dynamics mixture) built incrementally online via Bayesian model expansion/reduction, with action selection via active-inference expected free energy rather than gradient-based RL — this is the most direct existing prototype of "strong structural prior (object/interaction ontology) + few-shot online learning, no per-user retraining."

---

## 5. Contemplative science × computation

**Laukkonen, Inglis, Chandaria, Sandved-Smith, Lopez-Sola, Hohwy, Gold, Elwood, "Contemplative Artificial Intelligence," 2025 (v3 Aug 2025).**
- URL: https://arxiv.org/abs/2504.15125
- Verbatim: "Inspired by contemplative wisdom traditions, we show how four axiomatic principles can instil a resilient Wise World Model in AI systems. First, mindfulness enables self-monitoring and recalibration of emergent subgoals. Second, emptiness forestalls dogmatic goal fixation and relaxes rigid priors. Third, non-duality dissolves adversarial self-other boundaries. Fourth, boundless care motivates the universal reduction of suffering... prompting AI to reflect on these principles improves performance on the AILuminate Benchmark (d=.96) and boosts cooperation and joint-reward on the Prisoner's Dilemma task (d=7+)... For future systems, active inference may offer the self-organizing and dynamic coupling capabilities needed to enact Contemplative AI in embodied agents."
- This is a real, current (2025) peer-reviewed-track paper explicitly linking active inference + Buddhist concepts (mindfulness/sati, emptiness/śūnyatā, non-duality/advaita-anatta, karuṇā/boundless care) to a "Wise World Model" — the closest existing academic anchor for the startup's "paññā as a universal prior" framing. Note this paper's empirical results are *prompting* effects on LLMs reflecting on these principles, not a trained-in architectural prior — important distinction for the startup's claim.

**Laukkonen & Slagter, "From many to (n)one: Meditation and the plasticity of the predictive mind," Neuroscience & Biobehavioral Reviews, 2021.**
- Verified via Crossref API (title search, not crwl — pubmed.gov and sciencedirect.com both bot/IP-blocked this session):
  - Journal version: DOI 10.1016/j.neubiorev.2021.06.021, published 2021-09.
  - OSF preprint version: DOI 10.31234/osf.io/5sw6m, posted 2020-11-17.
- This is the standard reference for "Buddhist predictive processing" — argues meditation progressively relaxes/flattens the precision-weighted hierarchical predictive model that constructs the sense of a unified self ("many" prior-laden self-models collapsing toward "(n)one" / no-self), i.e. a computational (active-inference) account of anattā (no-self) as reduced precision on self-referential predictive models, not literal "dissolution."

**Formalizing dukkha / anattā / paṭicca-samuppāda (dependent origination) computationally** — no single paper located and confirmed this session that formalizes all three concepts directly under those Pali names in a computational/ML paper. What IS confirmed: the Laukkonen/Friston "Contemplative AI" paper (above) explicitly operationalizes "emptiness" and "non-duality" as architectural/prompting principles, and "From many to (n)one" operationalizes anattā via predictive-processing precision dynamics. **Dukkha and paṭicca-samuppāda specifically as formal computational objects: UNVERIFIED — not found this session; likely exists in the active-inference-meditation literature (e.g. work by Sandved-Smith, or Manjari/Metzinger "minimal phenomenal experience") but I did not locate and confirm a primary source before budget ran out.**

**Japanese sources — confirmed via CiNii Research OpenSearch (curl, JSON API, not bot-blocked):**
1. 乾敏郎(Inui Toshio), 「自由エネルギー原理に基づく催眠と瞑想の統一理論」(A unified theory of hypnosis and meditation based on the free energy principle), 身心変容技法研究 第4号, 2015, pp.176–183. https://cir.nii.ac.jp/crid/1010282257120367628
2. 望月泰博, 「瞑想における動機の整理の重要性：体験と予測符号化からの考察」(The importance of organizing motivation in meditation: considerations from experience and predictive coding), 日本トランスパーソナル心理学/精神医学会誌. https://cir.nii.ac.jp/crid/1520872156474607872
3. 「マインドフルネスのメカニズムの予測符号化モデルに基づく理解」(Understanding the mechanisms of mindfulness based on the predictive coding model), 心理学評論 (Japanese Psychological Review), also posted to Center for Open Science/OSF preprint. Found via CiNii search on "マインドフルネス 能動的推論".
- These confirm active Japanese-language academic work applying the free-energy principle / predictive coding to meditation and hypnosis, independent of the Anglophone Laukkonen/Friston line — useful as a second, culturally-native evidence trail for the startup's Japan-market framing.

---

## 6. Repos cloned (shallow, `--depth 1`)

Pre-clone size check via `gh api repos/OWNER/REPO --jq .size` (KB, all well under 200MB cap):

| Repo | Size (KB) | Local path |
|---|---|---|
| VersesTech/axiom | 133 → 800K on disk | `/Users/anicca/Projects/agi-research/repos/axiom` |
| danijar/dreamerv3 | 26,910 → 13M on disk | `/Users/anicca/Projects/agi-research/repos/dreamerv3` |
| facebookresearch/vjepa2 | 7,894 → 10M on disk | `/Users/anicca/Projects/agi-research/repos/vjepa2` |
| kach/memo (PPL) | 44,828 → 82M on disk | `/Users/anicca/Projects/agi-research/repos/memo` |
| probcomp/Gen.jl (PPL) | 44,683 → 2.9M on disk | `/Users/anicca/Projects/agi-research/repos/Gen.jl` |

Total added by this task: ~109MB (well under the 600MB budget for this task's own clones).

**Note on the repos directory:** `/Users/anicca/Projects/agi-research/repos/` already contained other repos from an earlier/different research task (BARC, HRM, TinyRecursiveModels, arc_agi, arc_draw_more_samples_pub, marc, stitch, and a large `lilo` dir at 673M). Total directory size is now ~979MB. These pre-existing repos are NOT part of this task's clone budget and were left untouched (not owned by this task, no basis to assume they're safe to delete).

---

## Evidence vs inference — summary for the startup's framing

**Evidence (directly quoted/confirmed primary sources, this session):**
- The Bayesian-program-induction / "world model as probabilistic program" line (Tenenbaum → BPL/Omniglot → Lake et al. 2017 → Wong et al. 2023 rational meaning construction) is real, continuous, and institutionally alive today via Basis Research Institute.
- Active inference (Friston) has a concrete, working, data-efficient implementation with an explicit structural/object prior: AXIOM (VERSES, 2025), open-sourced, masters games in 10,000 steps without gradient-based RL.
- A real 2025 paper (Laukkonen et al., "Contemplative Artificial Intelligence") explicitly proposes exactly the startup's thesis — Buddhist principles (mindfulness, emptiness, non-duality, boundless care) as a "Wise World Model" prior — and explicitly names active inference as the mechanism to eventually implement it in embodied agents. This is the single strongest existing anchor.
- A separate, well-cited (2021) predictive-processing account of meditation and the self (Laukkonen & Slagter) gives a mechanistic, falsifiable (if still largely theoretical) story for anattā as reduced precision-weighting on self-models — this is publishable-grade cognitive science, not New Age analogy.
- Japanese academic literature independently pursues the same free-energy-principle-meets-meditation program (Inui 2015 and others via CiNii).

**Inference / speculation (not directly supported by fetched sources — flag to the startup explicitly):**
- No source confirms a rigorous computational formalization of dukkha or paṭicca-samuppāda (dependent origination) specifically — these remain narrative/conceptual mappings, not established math, as far as this session's search could establish.
- "Paññā as a universal prior" is not itself a phrase or formal claim found in any source — it is a reasonable *extrapolation* from (a) Bayesian structural priors (Tenenbaum lineage) + (b) active inference's generative-model-as-prior formalism + (c) the Contemplative-AI paper's four axiomatic principles, but nobody has published this exact synthesis yet. Positioning it as "we are building the first computational operationalization of paññā as a Bayesian/active-inference structural prior, following directly from [Laukkonen et al. 2025] and [AXIOM 2025]" is defensible; positioning it as "this is established science" is not.
- The empirical results in Laukkonen et al. 2025 are prompting-level effects on existing LLMs, not a trained-in architectural prior — the startup's proposed approach (a deep structural prior baked into a generative world model, active-inference style, rather than a system prompt) would be a genuine architectural step beyond what's been published, not a reproduction of it.

## Unresolved / needs follow-up
- Exact arXiv ID for MIT "AutumnBench"/"WorldTest" — not found this session.
- Confirmed co-founder list / precise relationship of Basis Research Institute to Mansinghka/probcomp — not re-verified this session (background knowledge only).
- "Gameworld 10k" benchmark name and explicit DreamerV3 head-to-head comparison for AXIOM — steps-count (10,000) and no-gradient-RL claims are confirmed from the abstract; the specific benchmark name/DreamerV3-beat claim needs a direct read of the PDF body or GitHub README (not done this session, time-boxed).
- A primary source computationally formalizing dukkha/paṭicca-samuppāda specifically — not found.
