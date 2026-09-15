# Agent-engineering source map

| Topic | OSS source pointers | Life Manager destination/analogue | Preserve |
|---|---|---|---|
| Harness | Symphony `elixir/lib/symphony_elixir/orchestrator.ex` and `agent_runner.ex`; Deep Agents `libs/deepagents/deepagents/graph.py` and `examples/better-harness/better_harness/core.py`; OpenHands `AGENTS.md` and `src/`; Hermes `agent/` and `hermes_state_*.py` | `runtime/loop/run-skill.mjs`, `runtime/loop/index.mjs`, `runtime/loop/prompt.mjs`, `config/loop-registry.json` | one owner/workspace, typed tool contract, bounded process, resume from durable state |
| Context | Deep Agents context middleware and `examples/llm-wiki/`; LangGraph `libs/langgraph/langgraph/pregel/`; Graphiti `graphiti_core/graphiti.py`, `search/`, `telemetry/`; Hermes `hermes_state_compression.py` | `runtime/loop/prompt.mjs`, `apps/life-manager/lib/context-graph.js`, `apps/life-manager/lib/event-cache.js`, Project Context Capsule in `skills/earn/gig/TODO.md` | source hashes, freshness, budgeted summaries, no tail-only context |
| Loop | Symphony `orchestrator.ex` retry/reconciliation handlers; LangGraph Pregel/checkpoint tests; Automaton `src/heartbeat/` and loop modules | `runtime/loop/index.mjs`, `runtime/loop/run-skill.mjs`, `apps/life-manager/lib/effect-reconciler.js`, `runtime/loop/harness-health-snapshot.mjs` | observe → decide → act → verify → persist → wake; retry only before proven effect |
| Graph | LangGraph `StateGraph`/Pregel state; Graphiti `Graphiti.add_episode`, node/edge models and search; local `context-graph.js` and `scripts/integration-onboarding.py` | append-only ledger plus projection/index; `config/loop-registry.json` and `skills/registry.json` | graph is a query projection, not effect authority; every edge has provenance |
| Eval | Inspect `src/inspect_ai/task/`, `solver/`, `scorer/`, `log/`; DSPy `dspy/teleprompt/`; simple-evals runners | `apps/life-manager/eval/`, `skills/self/self-improve/`, `skills/earn/self-improve/lib/promote_gate.py` | dataset/solver/scorer separation, held-out cases, explicit promotion gate |
| Observability | Phoenix `packages/phoenix-otel/src/phoenix/otel/otel.py`; OpenInference semantic conventions; Symphony `docs/logging.md` and status presenter | `runtime/loop/harness-health-snapshot.mjs`, `skills/self/self-improve/lib/harness_health.py`, effect/receipt ledgers | correlation IDs, redaction, structured events, liveness separate from provider effect |
| Goal | Automaton `constitution.md` and heartbeat lifecycle; Hermes self-evolution `evolution/skills/evolve_skill.py` and `skill_module.py`; Symphony workflow states | `skills/self/spawn/lib/spawn-decision.js`, `spawn-orchestrator.mjs`, `skills/earn/self-improve/lib/promote_gate.py`, loop TODO contracts | owner, horizon, budget, evidence, stop/cancel states, baseline/tripwire before promotion |

## License boundary

The skills quote no large upstream code. They cite URLs, commits, and file/function names, then show
small Life Manager-shaped examples. Phoenix's ELv2 license is recorded explicitly; its implementation
is a study reference, while Apache-2.0 OpenInference semantics are the portable observability source.
