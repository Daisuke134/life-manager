# Loop source notes

## What to read upstream

- `openai-symphony/SPEC.md` §§3, 7, 8, 14, and 17: separates policy/config/coordination/execution/
  integration/observability, defines retry/reconciliation states, and requires a test matrix.
- `openai-symphony/elixir/lib/symphony_elixir/orchestrator.ex`: `handle_info/2` tick and worker events,
  `schedule_issue_retry/3`, active-state reconciliation, stalled-run handling, and terminal cleanup.
- `openai-symphony/elixir/lib/symphony_elixir/agent_runner.ex`: continuation prompts re-use the current
  workspace/workpad and refresh tracker state before deciding whether to continue.
- `langchain-langgraph/libs/langgraph/langgraph/pregel/` and checkpoint tests: durable graph execution
  resumes from checkpoint/config identity instead of replaying the whole run.
- `langchain-deepagents/examples/ralph_mode/ralph_mode.py`: bounded repeated work with a stop condition;
  use it as a loop-shape example, not as permission to run forever.
- `conway-automaton/src/heartbeat/` and `src/agent/loop.ts`: heartbeat/waking and ReAct state
  transitions; borrow the lifecycle vocabulary, not the survival economics.

## Life Manager mapping

- `runtime/loop/index.mjs` is the current wake loop: it builds context, parses one tool call, runs the
  registered skill, classifies failures, writes ledger fields, and chooses sleep/reroute state.
- `runtime/loop/run-skill.mjs::runSkill` is the bounded child-process seam; the registry decides the
  repository-relative entrypoint.
- `runtime/loop/harness-health-snapshot.mjs` derives health from ledger records; it does not restart a
  loop or declare business success.
- `apps/life-manager/lib/effect-reconciler.js::reconcileUnknownEffect` enforces the present/absent/
  unknown boundary and dead-letters an unknown effect after the configured consecutive limit.
- `config/loop-registry.json` contains one lifecycle row per owner. `skills/registry.json` describes
  capabilities; neither registry is the provider receipt.

## Adopted lessons

1. A scheduler is only the alarm clock; durable state, verification, recovery, and stop conditions
   are the loop.
2. Keep a finite wake and persist `next_eligible_at`; do not hold one process open for a long wait.
3. Treat an uncertain effect as a different state from a failed pre-effect attempt.
4. Keep local and cloud as host adapters for one loop implementation.
