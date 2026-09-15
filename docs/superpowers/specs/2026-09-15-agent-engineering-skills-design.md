# Agent Engineering Skills Design

**Goal:** Give every future Life Manager loop a reusable, code-grounded recipe for harness,
context, loop, graph, evaluation, observability, and goal engineering so the system can recover and
improve without a human restarting each step.

**Scope:** Add six new repository-owned skills and refine the existing `skills/loop-engineering/SKILL.md`.
Keep source repositories as durable, shallow/sparse clones outside Git, and record pinned commits,
licenses, source paths, and Life Manager mappings in `docs/agent-engineering/REFERENCE-REPOS.md`.

**Non-goals:** Do not rewrite the Coconala TODO, change a production loop, add a graph database,
replace the current runtime, or claim autonomous self-improvement from process liveness. The other
Codex owns the Coconala-to-meta-loop worktree and `skills/earn/gig/TODO.md` remains read-only here.

## Architecture

The skills are development-time recipes, not a second runtime. They point future agents to the
existing Life Manager seams:

```text
goal -> context capsule -> model decision -> loop transition
  -> capability/effect -> official readback -> append-only facts
  -> graph projection -> eval/observability -> next goal revision
```

Deterministic code owns leases, budgets, state transitions, retries, effect fences, redaction,
hashes, and receipt validation. The model owns semantic interpretation, prioritization, replanning,
and choosing among capabilities. No skill may introduce a keyword/regex classifier for a judgment
that the agent should make.

Each skill has the same shape:

1. concise trigger description and boundary;
2. a six-to-ten step recipe at the right altitude;
3. one concrete Life Manager code example;
4. a contract table (inputs, outputs, owner, evidence, stop condition);
5. failure modes and recovery boundaries;
6. source map to the pinned OSS clones and local files.

Heavy source notes live in `references/` only when they improve reuse. The skills cite code paths and
functions rather than copying upstream implementations, preserving license and updateability.

## Source set

| Engineering area | Primary code references | Why it is selected |
|---|---|---|
| Harness | `openai/symphony`, `langchain-ai/deepagents`, `OpenHands/OpenHands`, `NousResearch/hermes-agent` | Isolated workspaces, long-running agents, tool contracts, context middleware, restartable execution |
| Context | `langchain-ai/deepagents`, `langchain-ai/langgraph`, `getzep/graphiti`, `NousResearch/hermes-agent` | Context budgets, offload/summarization, checkpoints, temporal memory, state compression |
| Loop | `openai/symphony`, LangGraph durable execution, existing `runtime/loop` | Observe/decide/act/verify/persist, reconciliation, backoff, replay-zero |
| Graph | LangGraph, Graphiti, existing `context-graph.js` and `integration-onboarding.py` | State graphs plus provenance-rich temporal projections without a second source of truth |
| Eval | `UKGovernmentBEIS/inspect_ai`, `stanfordnlp/dspy`, `openai/simple-evals` (reference only; deprecated) | Task/solver/scorer logs, held-out experiments, prompt optimization, reproducible baselines |
| Observability | `Arize-ai/phoenix`, Symphony logging/status, existing health and effect ledgers | OpenTelemetry spans, datasets/experiments, structured receipts, privacy-aware runtime health |
| Goal | `Conway-Research/automaton`, `NousResearch/hermes-agent-self-evolution`, Symphony workflow states | Durable goal lifecycle, constitution/stop boundaries, skill evolution, no-human continuation |

The clones live at `/Users/anicca/Projects/life-manager-agent-engineering-references/` and are not
runtime dependencies. A clean machine can use the recorded upstream URL and commit instead.

## Local adoption map

- Harness: `runtime/loop/run-skill.mjs`, `runtime/loop/index.mjs`, `runtime/loop/prompt.mjs`,
  `config/loop-registry.json`, and `skills/loop-development/SKILL.md`.
- Context: `runtime/loop/prompt.mjs`, `apps/life-manager/lib/context-graph.js`,
  `apps/life-manager/lib/event-cache.js`, and the Project Context Capsule contract in
  `skills/earn/gig/TODO.md` (reference only; not edited).
- Loop: `runtime/loop/index.mjs`, `runtime/loop/run-skill.mjs`,
  `apps/life-manager/lib/effect-reconciler.js`, `runtime/loop/harness-health-snapshot.mjs`.
- Graph: `apps/life-manager/lib/context-graph.js`, `scripts/integration-onboarding.py`,
  `config/loop-registry.json`, `skills/registry.json`.
- Eval: `apps/life-manager/eval/`, `skills/self/self-improve/`,
  `skills/earn/self-improve/lib/promote_gate.py`.
- Observability: `runtime/loop/harness-health-snapshot.mjs`,
  `skills/self/self-improve/lib/harness_health.py`, `apps/life-manager/lib/effect-reconciler.js`,
  and the shared ledger/receipt modules.
- Goal: `skills/self/spawn/lib/spawn-decision.js`, `skills/self/spawn/lib/spawn-orchestrator.mjs`,
  `skills/earn/self-improve/lib/promote_gate.py`, and the existing loop registry/TODO contracts.

## Completion criteria

- Six new skills plus the refined Loop skill pass the skill frontmatter/structure validator.
- Every source-map entry resolves to a file in the clone or Life Manager worktree.
- A contract test fails before the skills exist and passes after they are written.
- Each skill names a measurable evidence boundary and a safe stop condition.
- No production runtime, state, browser, launchd job, or Coconala TODO is changed.
- Changes are committed and pushed from the dedicated worktree; the canonical checkout and the other
  Codex worktree remain untouched.
