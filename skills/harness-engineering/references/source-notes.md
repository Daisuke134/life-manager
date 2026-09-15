# Harness source notes

Pinned clones are listed in `docs/agent-engineering/REFERENCE-REPOS.md`.

## What to read upstream

- `openai-symphony/elixir/lib/symphony_elixir/orchestrator.ex`: poll ticks, active-state
  reconciliation, worker-down handling, retry scheduling, and terminal cleanup are owned by one
  orchestrator state machine.
- `openai-symphony/elixir/lib/symphony_elixir/agent_runner.ex`: `run/3` creates/reuses one workspace,
  starts one app-server session, continues an active issue, and logs `issue_id`, `issue_identifier`,
  `session_id`, and workspace.
- `openai-symphony/elixir/lib/symphony_elixir/workspace.ex`: `create_for_issue/2`, `workspace_key/1`,
  `validate_workspace_path/2`, and `remove_recorded/2` make workspace identity and cleanup explicit.
- `langchain-deepagents/libs/deepagents/deepagents/graph.py`: the harness composes middleware around
  an agent graph rather than forking a second runner.
- `langchain-deepagents/examples/better-harness/better_harness/core.py`: `RunLayout`,
  `validate_experiment`, `run_experiment`, and trace-reference writers show how a run owns its
  artifacts, split, trace, and result files.
- `OpenHands/OpenHands/AGENTS.md`: runtime, UI, automation, and telemetry ownership are separated;
  one canonical telemetry client prevents duplicate business events.
- `NousResearch/hermes-agent/agent/` and `hermes_state_*.py`: inspect the tool loop and persisted
  session/state boundaries before borrowing any self-restart behavior.

## Life Manager mapping

- `runtime/loop/run-skill.mjs::runSkill` is the existing bounded child-process seam.
- `runtime/loop/run-skill.mjs::resolveSkillPath` resolves a registry-owned repository path; a skill
  must not select an arbitrary home-directory implementation.
- `runtime/loop/index.mjs` owns wake identity, context assembly, tool-call parsing, timeouts, ledger
  fields, failure-layer classification, and retry/reroute state.
- `runtime/loop/prompt.mjs::buildSystemPrompt` and `getToolDefinitions` are the agent-computer
  interface; tool descriptions must expose useful arguments and evidence, not implementation logs.
- `config/loop-registry.json` is the one lifecycle registry. `skills/registry.json` is the capability
  catalog; neither is a replacement for durable effect/readback state.
- `skills/loop-development/SKILL.md` defines immutable release, launchd ownership, and local/cloud
  parity rules. Follow it before changing a production loop.

## Adopted lessons

1. Separate supervisor/owner/adapter responsibilities; a supervisor observes and schedules but does
   not perform a provider effect.
2. Preserve a workspace and workpad across continuation turns; do not rebuild context from the last
   message.
3. Give every retry a durable attempt token and reconcile terminal/unknown state first.
4. Make logs searchable with stable identifiers while keeping payloads bounded and secret-free.
