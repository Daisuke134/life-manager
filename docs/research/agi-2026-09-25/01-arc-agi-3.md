# ARC-AGI-3 / ARC Prize — Briefing for competitive planning

Compiled 2026-09-25. Sources: crwl crawls of arcprize.org / docs.arcprize.org, `gh` CLI repo metadata, shallow clones under `/Users/anicca/Projects/agi-research/repos/`. DuckDuckGo HTML search (`html.duckduckgo.com`) returned bot-challenge pages after ~2 queries even via `lite.duckduckgo.com`; official-site crawling substituted as primary source and is sufficient — all key facts below are sourced to arcprize.org/docs.arcprize.org/github.com directly, with verbatim quotes. Where a claim could not be pinned to a fetched page it is marked **UNVERIFIED**.

---

## 1. What ARC-AGI-3 is

**Format.** Interactive, turn-based game benchmark (not static grid puzzles like ARC-AGI-1/2).
Source: https://arcprize.org/arc-agi/3 — "ARC-AGI-3 is an interactive reasoning benchmark which challenges AI agents to explore novel environments, acquire goals on the fly, build adaptable world models, and learn continuously... Instead of solving static puzzles, agents must learn from experience inside each environment—perceiving what matters, selecting actions, and adapting their strategy without relying on natural-language instructions."

**Scale / launch.** Full (non-preview) release 25 Mar 2026, alongside ARC Prize 2026.
Source: https://arcprize.org/blog/arc-agi-3-launch — "Today we're excited to announce the release of ARC-AGI-3, a series of hundreds of interactive environments and thousands of game-style levels... Humans score 100%. Frontier AI scores 0.51%." (published 25 Mar 2026 by Greg Kamradt)
A technical paper exists: https://arcprize.org/media/ARC_AGI_3_Technical_Report.pdf, referenced elsewhere as arXiv 2603.24621 (per the Astra post footnote linking `arxiv.org/pdf/2603.24621`). **UNVERIFIED**: did not independently open the PDF/arXiv page to confirm the abstract, only the outbound link text.

**Number of games.** Preview had 3 public games; full ARC-AGI-3 is "hundreds of original turn-based environments" (see launch quote above) — an exact game count was not found; the 2026 competition page uses "game environments" without a fixed number. Human leaderboard shows a "GamesDone" cap of 25 for 100%-scorers, suggesting the *scored* set (at least at that leaderboard's snapshot) = 25 games / 183 levels.
Source: https://arcprize.org/arc-agi/3/leaderboard — table shows top human scorers all at `GamesDone 25 | LevelsDone 183 | Score 100.00`.

**Action space.** Discrete actions: `RESET`, `ACTION1`–`ACTION6` per docs; changelog in the official agent repo later adds `ACTION7`.
Source: https://docs.arcprize.org/llm_agents — "LLM agents are expected to return exactly one of the valid action names (`RESET`, `ACTION1` – `ACTION6`)."
Source: `/Users/anicca/Projects/agi-research/repos/arcprize_ARC-AGI-3-Agents/README.md` changelog `[0.9.2] - 2025-08-19` — "Added `available_actions` to `FrameData`" and "`ACTION7` as possible `GameAction`". Grid is 64×64 cells, 16 colors per the Blind Squirrel agent README (`wd13ca_ARC-AGI-3-Agents/README.md`): "Each game environment consists of a 64x64 grid, where each cell in the grid is filled with one of 16 different colours."

**Scoring — action efficiency vs. humans.** Core metric is *action efficiency*: how many actions an agent needs to finish a level, normalized against a human baseline (median actions of real testers), not just pass/fail.
Source: https://arcprize.org/blog/arc-agi-3-preview-30-day-learnings — "Score agents by their per-level action efficiency (as compared to humans), normalized per game, across all games... 'Normalized per game' - Each level will be scored in isolation. Each individual game will get a score between 0%-100%... 'Across all games' - Total score will be the sum of individual game scores divided by the total number of games."
Human baseline methodology: ~500 general-public participants (not selected for puzzle skill), median action count per level used as baseline.
Source: https://arcprize.org/blog/astra — "Before launching ARC-AGI-3, we tested approximately 500 members of the general public to establish a human baseline for action efficiency... For each level, we defined the 'human baseline' using the median action count among players who completed it."

**Public/preview vs. private/semi-private sets.** Two evaluation harnesses exist for model runs: "Standard harness" (model manages its own notes) and "Provider Adapter harness" (uses opaque provider reasoning-state + compaction). Games are split into Public, Semi-Private (used for current SOTA claims) and (implicitly) a fully Private set for the Kaggle competition, mirroring ARC-AGI-1/2's public/private-eval convention.
Source: https://arcprize.org/blog/astra — "OpenAI's Astra (max) scores 62.7% on ARC-AGI-3 Semi-Private ... for $26K" and "Provider Adapter harness ... preserves opaque reasoning state between requests and uses compaction for longer conversations."
Preview-era: 3 public games + 3 private holdout games used for the Preview Agent Competition.
Source: https://arcprize.org/blog/arc-agi-3-preview-30-day-learnings — "The three private games used as a hidden holdout set for the ARC-AGI-3 Preview Agent Competition will be released in the coming weeks."

**Current SOTA (as of 3 Sep 2026).** OpenAI GPT-6 Astra: 62.7% ($26,098) with Standard harness (max reasoning), and **99.9%** ($18,817) with Provider Adapter harness (high reasoning) — near-saturating the benchmark under the provider-adapter condition.
Source: https://arcprize.org/blog/astra — table: "max | 62.7%, $26,098 | 98.6%, $17,332" ... "high | 54.8%, $40,705 | 99.9%, $18,817" (Standard | Provider Adapter columns). Text: "GPT-6 Astra achieves state-of-the-art scores on ARC-AGI-3 with both the Standard and Provider Adapter harnesses."
Astra also beats the human action-efficiency baseline: "Astra (max) used fewer actions than the human baseline on 96.0% of levels and used 51.7% fewer actions per level on average."
At full ARC-AGI-3 launch (25 Mar 2026), frontier AI scored only 0.51% vs. humans' 100% — i.e., SOTA moved from ~0.5% to ~99.9% (Provider Adapter, best model/harness) in about 5 months. **UNVERIFIED for "best open/competition agent" score on the *full* ARC-AGI-3** — the only public open competition-agent numbers found are from the Preview format (3 games only, before full launch); see §3.

**Human baseline.** 100% by design/construction — games are calibrated to be 100% human-solvable.
Source: https://arcprize.org/arc-agi/3 — "A 100% score means AI agents can beat every game as efficiently as humans." / "100% human-solvable environments."

---

## 2. ARC Prize 2026 competition (current cycle)

**Tracks (3 total), total prize pool $2,000,000.**
Source: https://arcprize.org/competitions/2026 — "$2M in prizes. 3 tracks." Tracks: ARC-AGI-3 (interactive), ARC-AGI-2 (static), Paper Prize.

**Key dates:**
- March 25, 2026 — Competition starts
- June 30, 2026 — ARC-AGI-3 Milestone #1
- September 30, 2026 — ARC-AGI-3 Milestone #2 (5 days from today, 2026-09-25)
- November 2, 2026 — Submissions due
- November 8, 2026 — Papers due
- December 4, 2026 — Results announced
Source: https://arcprize.org/competitions/2026 (Key Dates list, verbatim above).

**ARC-AGI-3 track prizes — $850K total:**
- Grand Prize (100% score): $700K — "Awarded to the first eligible agent that scores 100% on the ARC-AGI-3 evaluation. If not won, the Grand Prize will continue during the next annual competition."
- Top Score Award: $75K guaranteed (1st $40K / 2nd $15K / 3rd $10K / 4th $5K / 5th $5K)
- Milestone Prizes: $75K guaranteed, split across two dated milestones (Jun 30 & Sep 30 2026), each with 1st $25K/2nd $10K/3rd $2.5K, for open-sourcing by the milestone deadline.
Source: https://arcprize.org/competitions/2026/arc-agi-3 (verbatim, see full page capture in research log).

**ARC-AGI-2 track prizes — $700K total:** Progress Prizes $275K (8 places, $75K→$15K), Grand Prize $275K (writeup-judged, 6 criteria 0-5 each), Bonus Prize $150K (first to ≥85% on private eval; rolls to 2027 if unmet).
Source: https://arcprize.org/competitions/2026/arc-agi-2.
Objective: "Reach 85% accuracy on the ARC-AGI-2 private evaluation dataset within the Kaggle efficiency limits." Scoring: predict exactly 2 outputs per test input; correct if either matches.

**Compute / submission constraints (both tracks):**
- Submissions via the designated **Kaggle** competition (Kaggle notebook for ARC-AGI-2 explicitly stated).
- **No internet access during evaluation** — "no API-based systems like GPT/Claude/etc." is called out explicitly for the general rules.
- "Hardware and compute limits will be announced with the competition launch" (stated on both track pages as of this crawl — i.e. not finalized/published yet as of 2026-09-25). **Numeric compute/hardware limits: UNVERIFIED / not yet published per official pages.**
Source: https://arcprize.org/competitions/2026 — "Internet access is not available during Kaggle evaluation (no API-based systems like GPT/Claude/etc.)."
Source: https://arcprize.org/competitions/2026/arc-agi-3 — "Submissions must be made through the designated Kaggle competition. No internet access during evaluation. All code and methods must be open sourced to be eligible for prizes. Hardware and compute limits will be announced with the competition launch."

**Open-source requirement (both tracks, mandatory for any prize):** All submitter-authored code/methods must be under a permissive public-domain-equivalent license (CC0 or MIT-0); third-party code must be at least a permissive-share license (Apache-2.0, GPLv3, etc.). Must open-source **before** receiving official private evaluation scores.
Source: https://arcprize.org/competitions/2026 — "In order for a submission to be eligible, all code and methods authored by the submitter must be made open source under a permissive public domain license (eg. CC0 or MIT-0)... Participants must open source their solutions before receiving official private evaluation scores. This applies across all three competition tracks."

**SDK / API / agent template repo:**
- `pip install arc-agi` (or `uv add arc-agi`) — the ARC-AGI Toolkit, official Python client/environment interface. Repo: https://github.com/arcprize/arc-agi (251 KB).
  Source: https://docs.arcprize.org/ — "Install the ARC-AGI Toolkit ... uv add arc-agi / pip install arc-agi" and sample code using `import arc_agi; from arcengine import GameAction`.
- Agent template/starter repo: `arcprize/ARC-AGI-3-Agents` (GitHub, 632 KB) — includes `random`, `llm`, `fastllm`, `reasoningllm` (o4-mini), `guidedllm` (o3) templates plus LangGraph/smolagents/multimodal/openclaw templates.
  Source: `arcprize_ARC-AGI-3-Agents/README.md` (cloned) and https://docs.arcprize.org/llm_agents (agent template descriptions, quoted in §1).
- `ARC_API_KEY` env var required (or falls back to anonymous key with limited public-game access); register via https://three.arcprize.org (preview) or https://arcprize.org/platform (per agent-repo README).
- Benchmarking tooling (beta) for reproducible scorecards/replays: `arcprize/arc-agi-3-benchmarking` (7.9 MB on GitHub, cloned).

**How to submit:** Kaggle notebook submission to "the designated Kaggle competition" per track (exact Kaggle competition slug/URL for the 2026 ARC-AGI-3 track was not located in this crawl — the 2025 static-track Kaggle URL was found: https://www.kaggle.com/competitions/arc-prize-2025/. **The live 2026 Kaggle competition URL is UNVERIFIED** — likely not yet published or not surfaced by crawl of the pages visited).

---

## 3. Top approaches — winners and methods

### ARC-AGI-3 Preview Agent Competition (2025, 30-day, 3 public + 3 private games; sponsored with Hugging Face; 12 submissions, 8 scored against private games)

Source: https://arcprize.org/blog/arc-agi-3-preview-30-day-learnings

| Place | Team / Dev | Method | Score | Levels completed | Actions |
|---|---|---|---|---|---|
| 1st | **StochasticGoose @ Tufa Labs** (Dries Smit, adviser Jack Cole) | CNN-based action-learning RL agent — predicts which actions cause frame changes, for smarter exploration than random | 12.58% | 18 | 255,964 |
| 2nd | **Blind Squirrel** (Will Dick) | Explore-and-learn agent: builds a state graph from frames, prunes loop/no-op actions, back-labels distances on score improvement, retrains a small ResNet18 value model to rank (state,action) pairs toward next milestone | 6.71% | 13 | 109,108 |
| Honorable mention | Dhana Abhiraj — "Play Zero Agent" | Random + LLM Video | 4.37% | 5 | 7,226 |
| Honorable mention | Evgenii Rudakov — "Explore It Till You Solve It" | Smart-random / frame-graph exploration | 3.64% | 12 | 278,158 |
| Honorable mention | Ujjwal Chadha et al. — "Fluxonian" | DSL + LLM | 8.04% | 5 | 11,890 |

Quotes: "1st Place: StochasticGoose @ Tufa Labs: Score: 12.58%, Levels Completed: 18. Convolutional Neural Network Action-learning agent. It uses a simple reinforcement learning approach to predict which actions will cause frame changes, enabling more efficient exploration than random selection." / "2nd Place: Blind Squirrel: Score: 6.71%, Levels Completed: 13. Explore-and-learn agent that builds a state graph from frames. It prunes actions that create loops or don't change state. Whenever the score improves, it back-labels that level with distances and retrains a small ResNet18-based value model..."

Note: no graph-search / world-model-learning / pure-LLM-agent approach won — the winning approaches were RL/frame-diff exploration, not LLM agents. Pure-LLM approaches scored worst (e.g. Cristian Valdivia's LLM agent: 3.70%, "Limited Results, Crashed Often", only 1 level, 79 actions).

### ARC-AGI-2 / ARC Prize 2025 (Kaggle static track, results announced 5 Dec 2025)

Source: https://arcprize.org/blog/arc-prize-2025-results-analysis — "1,455 teams submitted 15,154 entries for ARC Prize 2025... The top Kaggle score winner reached a new SOTA on the ARC-AGI-2 private dataset of 24% for $0.20/task."

**High Score winners (ARC-AGI-2 private eval):**
| Place | Team | Score | Prize | Method summary (from official interview blurbs) |
|---|---|---|---|---|
| 1st | **NVARC** | 24.03% (24.0% on the public results page) | $25K | "A synthetic-data-driven ensemble of an improved Architects-style test-time-trained model and TRM-based components" |
| 2nd | **the ARChitects** | 16.53% (16.5%) | $10K | "A 2D-aware masked-diffusion LLM with recursive self-refinement and perspective-based scoring... improving substantially over the team's 2024 autoregressive system" |
| 3rd | **MindsAI** | 12.64% (12.6%) | $5K | "A heavily engineered test-time-training pipeline that combines TTFT, augmentation ensembles, tokenizer dropout, and some new pretraining tricks" — reported elsewhere in same post as 15.42% in a longer description; **discrepancy 12.64% vs 15.42% is as-published, UNVERIFIED which is the official contest number** (12.64%/12.6% appears in the results table, 15.42% appears in prose) |
| 4th | Lonnie | 6.67% | $5K | — |
| 5th | G. Barbadillo | 6.53% | $5K | search+learn combination (per honorable-mention paper title) |

**Paper Award winners** (methods, not leaderboard scores):
- 1st ($50K): Alexia Jolicoeur-Martineau — **Tiny Recursive Model (TRM)**: "~7M-parameter, single-network recursive model with separate answer and latent states that, via deep supervised refinement, attains ~45% on ARC-AGI-1 and ~8% on ARC-AGI-2." Paper: https://arxiv.org/abs/2510.04871. Official repo (cloned): https://github.com/SamsungSAILMontreal/TinyRecursiveModels (now **archived/read-only** per repo README: "we have to temporaliy archive (make read-only) this and several other repos").
- 2nd ($20K): J. Pourcel et al. — **SOAR**, self-improving evolutionary program synthesis, fine-tunes an LLM on its own search traces; "boosting open-source ARC-AGI-1 solution performance up to 52%."
- 3rd ($5K): I. Liao & A. Gu — **CompressARC**: MDL/VAE-based, no pretraining, no dataset (trains per-task from random init), ~20-34% ARC-AGI-1 / ~4% ARC-AGI-2, "processing each puzzle in roughly 20 minutes on 1 RTX 4070."

**Commercial/refinement systems (not competition entries, verified on the general leaderboard):**
- Best verified commercial model on ARC-AGI-2: Claude Opus 4.5 (Thinking, 64k) — 37.6% for $2.20/task.
- Best verified "model refinement" solution: Poetiq (built on Gemini 3 Pro) — 54% for $30/task, up from a 31%/$0.81 baseline; similar gains reported on Claude Opus 4.5 at ~2x cost (~$60/task). Repo cloned: https://github.com/poetiq-ai/poetiq-arc-agi-solver.
Source: https://arcprize.org/blog/arc-prize-2025-results-analysis — "the top verified commercial model, Opus 4.5 (Thinking, 64k), scores 37.6% for $2.20/task. The top verified refinement solution, built on Gemini 3 Pro and authored by Poetiq, scores 54% for $30/task."

**Named 2024 ARChitects repo** (predecessor system, method basis for 2025 2nd place): `da-fr/arc-prize-2024` (cloned, 5.3 MB) — "test-time-trained model" lineage referenced directly in the 2025 results post: "the top score in ARC Prize 2024 (ARChitects) and 2025 (NVARC)."

---

## 4. Cloned repos (`/Users/anicca/Projects/agi-research/repos/`), total ~48 MB added, well under the 1.5 GB cap

Note: this repos/ directory already contained ~1.0 GB of unrelated prior research clones (BARC, lilo, memo, stitch, vjepa2, dreamerv3, HRM, axiom, Gen.jl, marc, arc_agi, arc_draw_more_samples_pub, and a bare `TinyRecursiveModels`) from an earlier, different task — left untouched, not part of this task's output.

| Path | Repo | Size | How it works / how an agent plugs in |
|---|---|---|---|
| `arcprize_ARC-AGI-3-Agents/` | arcprize/ARC-AGI-3-Agents | 1.0 MB | Official starter kit. `main.py --agent=<name> --game=<id>` runs any agent in `agents/templates/` (random, llm, fastllm, reasoningllm, guidedllm, langgraph, smolagents, multimodal, openclaw) against a game via the hosted API or local engine. Plug in a new agent by subclassing the base `Agent` class in `agents/agent.py` and registering it in `AVAILABLE_AGENTS`; action space is `RESET`/`ACTION1-6` (later `ACTION7`). Needs `ARC_API_KEY`. |
| `arcprize_arc-agi/` | arcprize/arc-agi | 848 KB | The official SDK (`pip install arc-agi`). Exposes `arc_agi.Arcade()` → `arc.make(game_id, render_mode=...)` → Gym-like `env.step(GameAction.ACTIONn)` loop, plus `arc.get_scorecard()`. This is the underlying engine the agent-template repo now wraps (per changelog note "Updated to use the new ARC-AGI tool ... Allows local execution of environments"). |
| `arcprize_arc-agi-3-benchmarking/` | arcprize/arc-agi-3-benchmarking | 1.6 MB | Official (beta) benchmarking harness for producing repeatable scorecards/replays across prompts/model versions/agent architectures — the tool referenced for the "Standard" vs "Provider Adapter" harness comparisons used in leaderboard posts (e.g. the Astra post). |
| `arcprize_ARC-AGI-2/` | arcprize/ARC-AGI-2 | 8.8 MB | Official ARC-AGI-2 static-task dataset/repo (train/eval JSON task grids), the direct successor format to ARC-AGI-1, used for the 2026 ARC-AGI-2 Kaggle track. |
| `DriesSmit_ARC3-solution/` | DriesSmit/ARC3-solution | 212 KB | **1st place, ARC-AGI-3 Preview Agent Competition.** CNN-based RL agent: learns to predict which actions cause a frame/state change (novelty/interestingness signal), biasing exploration away from no-op actions instead of uniform random search. Plugs in as a standalone agent script against the preview API. |
| `wd13ca_ARC-AGI-3-Agents/` | wd13ca/ARC-AGI-3-Agents (branch `blindsquirrel`) | 1.8 MB | **2nd place, Preview Competition ("Blind Squirrel").** Builds an explicit state graph from observed frames; prunes actions that loop or don't change state; on any score improvement it back-labels the traversed path with distance-to-goal and retrains a small ResNet18 value network to rank (state, action) pairs; repeats until win or action cap. Confirms game format: 64×64 grid, 16 colors. Plug-in point: `--agent=blindsquirrel` via the same `main.py` harness as the official template repo (it's a fork). |
| `dolphin-in-a-coma_arc-agi-3-just-explore/` | dolphin-in-a-coma/arc-agi-3-just-explore | 2.3 MB | Honorable mention ("Explore It Till You Solve It", Evgenii Rudakov). Smart-random / frame-graph exploration strategy; includes a written report draft (`Report_Draft.pdf`) analyzing exploration-only strategies as a strong preview-era baseline. |
| `da-fr_arc-prize-2024/` | da-fr/arc-prize-2024 | 5.3 MB | The original **ARChitects** ARC Prize 2024 winning solution (test-time-trained/fine-tuned autoregressive LLM + augmentation), the direct methodological ancestor of the team's 2025 2nd-place (masked-diffusion) entry and one of the two lineages (with TRM) that fed into 2025's 1st-place NVARC ensemble. |
| `poetiq-ai_poetiq-arc-agi-solver/` | poetiq-ai/poetiq-arc-agi-solver | 14 MB | Reproduction repo for **Poetiq's** model-refinement layer on top of frontier models (Gemini 3 Pro / Claude Opus 4.5) — the current best verified "refinement" approach (54% ARC-AGI-2 @ $30/task). Plug-in model: wraps an existing frontier LLM via API keys (`.env` with Gemini/OpenAI keys) and applies an iterative refine/verify loop rather than training a new model — i.e. an application-layer harness, not a Kaggle-eligible offline solution (uses API calls, disallowed under "no internet" Kaggle rules; positioned as a leaderboard-only comparison point). |
| `SamsungSAILMontreal_TinyRecursiveModels/` | SamsungSAILMontreal/TinyRecursiveModels | 12 MB | Official **TRM** (Tiny Recursive Model) repo, 2025 Paper Award 1st place. 7M-parameter net that iteratively refines a latent state `z` and answer `y` via a small recursive update loop (no pretraining reliance, no pretrained LLM backbone); trained per-dataset (ARC-AGI-1/2, Sudoku-Extreme, etc.) via `dataset.build_arc_dataset`. **Now archived/read-only by the author** due to spam issues — treat as reference-only, not a base to fork/PR against. |

---

## 5. Biggest open uncertainties for a startup planning to compete

1. **Kaggle compute/hardware limits for 2026 are not yet published.** Both track pages explicitly say "Hardware and compute limits will be announced with the competition launch" — as of this crawl (2026-09-25, i.e. 6 months after the stated 25 Mar 2026 "Competition starts" date) no numeric limit was found on the crawled pages. This is the single most important gap for infra planning (GPU budget, model size ceiling) and should be re-checked directly on Kaggle before committing engineering resources.
2. **No internet access during Kaggle evaluation rules out API-based frontier models entirely** ("no API-based systems like GPT/Claude/etc.") — meaning the extremely strong Astra 99.9% result (which used a hosted-API harness) is **not achievable inside the actual Kaggle prize track**; competitive solutions must be self-contained offline models/agents. This is a major strategic fork: the "leaderboard SOTA" (Astra) and the "Kaggle-prize-eligible SOTA" are different competitions with different constraints — plan for the latter.
3. **Exact number of ARC-AGI-3 games and public/private split for the full (non-preview) benchmark** was not confirmed by page text; only the preview's 3+3 split and the human-leaderboard's 25-game/183-level snapshot were found. Recommend checking `docs.arcprize.org` game-list endpoint or `arcprize.org/tasks?v=3` directly.
4. **Live Kaggle competition URL/slug for ARC Prize 2026 (both tracks)** was not located during this crawl — needs direct Kaggle-site verification.
5. **MindsAI's 3rd-place ARC-AGI-2 2025 score is internally inconsistent in the source post** (12.64%/12.6% in the results table vs. "15.42%" in the winner-interview prose) — needs disambiguation from the Kaggle leaderboard directly before citing externally.
6. DuckDuckGo HTML search access from this environment is unreliable (bot-challenge after ~2 queries even via `lite.duckduckgo.com`); if further web research is needed beyond arcprize.org/github.com, expect to need a different search path or longer cooldowns between queries.
