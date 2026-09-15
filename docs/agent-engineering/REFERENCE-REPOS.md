# Agent-engineering reference repositories

These are pinned code references for the repository-owned skills. They are study material, not
Life Manager runtime dependencies. The local clones use shallow/sparse checkout so the code paths
remain available without importing another project's dependency tree.

Local root: `/Users/anicca/Projects/life-manager-agent-engineering-references/`

| Repository | Pinned commit | License | Local clone | Used for |
|---|---|---|---|---|
| [openai/symphony](https://github.com/openai/symphony) | `e0ccc83720a42a600a53b61c5f8d3e518bebe1db` | Apache-2.0 | `openai-symphony` | harness, loop, workspaces, retries, observability |
| [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | `1d3232c0852c47af09119edea10eeec887e4f0da` | MIT | `langchain-deepagents` | harness, context offload, skills, subagents |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | `230927fb3a9ac9b2893a30322b4dfea7cdea9a8f` | MIT | `langchain-langgraph` | state graph, checkpoints, durable execution |
| [getzep/graphiti](https://github.com/getzep/graphiti) | `c035afb7990b6077331a81e98b04efcfd9bf8184` | Apache-2.0 | `getzep-graphiti` | temporal graph, provenance, search, telemetry |
| [UKGovernmentBEIS/inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) | `8ba398c10683b68d93546c2da2e00ba6ae7d5af5` | MIT | `uk-inspect-ai` | eval tasks, solvers, scorers, logs, retries |
| [Arize-ai/phoenix](https://github.com/Arize-ai/phoenix) | `06a21cd04bcf533066b22e7b032ff4346996ed37` | Elastic License 2.0 | `arize-phoenix` | tracing/eval implementation reference; do not host as a derivative service without license review |
| [Arize-ai/openinference](https://github.com/Arize-ai/openinference) | `812f6877d5e3e353be4ecceaf9b51896347569a0` | Apache-2.0 | `arize-openinference` | OpenTelemetry/OpenInference span semantics |
| [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | `110baa095bc7135a0624557a9cc35df0f98ece0f` | MIT | `nous-hermes-agent` | persistent state, compression, tools, heartbeat |
| [NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) | `0a929e3aa20e15cf04dc7c28492a7d41a5139125` | repository README/metadata | `nous-hermes-self-evolution` | skill evolution, candidate evaluation, promotion loop |
| [Conway-Research/automaton](https://github.com/Conway-Research/automaton) | `d8f816881fd24b6f5e3d616e59edec387a447667` | MIT | `conway-automaton` | constitution, heartbeat lifecycle, survival/goal boundaries |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | `23ca81c9ff6e638546f966d7f0e11a7682666179` | MIT | `openhands` | agent/runtime event model, workspace and telemetry boundaries |
| [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | `4368715bfb9dd275e0ffc286c7c7198d2798b859` | MIT | `stanford-dspy` | typed signatures, prompt optimization, optimizer/eval separation |
| [openai/simple-evals](https://github.com/openai/simple-evals) | `652c89d0ca9df547706735883097e9537d40dc47` | MIT | `openai-simple-evals` | small transparent baseline evals; repository is deprecated for new benchmarks |

## Reading rule

Read the exact pinned file/function named by the relevant skill before borrowing a pattern. Copy the
decision boundary and evidence contract, not a framework or an entire runner. Re-check upstream
commits when a dependency or API is proposed; the pinned clone is a reproducible reference, not a
claim that the current branch is still the best version.
