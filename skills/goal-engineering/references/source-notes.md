# Goal source notes

## What to read upstream

- `conway-automaton/constitution.md`: immutable policy is separated from mutable runtime goals;
  borrow the separation and auditability, not the survival/spend policy.
- `conway-automaton/src/heartbeat/daemon.ts`, `scheduler.ts`, and `tick-context.ts`: heartbeat wakes
  are bounded triggers that inspect state and schedule work; they do not replace goal evidence.
- `conway-automaton/src/agent/loop.ts`, `src/orchestration/planner.ts`, and `task-graph.ts`: ReAct
  execution and planning state are explicit and testable.
- `conway-automaton/src/replication/lifecycle.ts`, `lineage.ts`, and `self-mod/audit-log.ts`: child
  lifecycle, lineage, and self-modification audit records are separate from the agent's mutable plan.
- `nous-hermes-self-evolution/evolution/skills/evolve_skill.py`: `evolve` freezes a baseline, builds
  train/val/holdout data, validates constraints, optimizes a candidate, then evaluates before output.
- `nous-hermes-self-evolution/evolution/skills/skill_module.py`: `load_skill`, `find_skill`, and
  `reassemble_skill` preserve frontmatter and replace only the skill body.

## Life Manager mapping

- `skills/self/spawn/lib/spawn-decision.js::decideSpawn` is the pure spawn eligibility boundary;
  `spawn-orchestrator.mjs::executeSpawnAttempt` performs the effectful child lifecycle and records
  failures/registry state.
- `skills/earn/self-improve/lib/promote_gate.py::assess_candidate` and `decide_promotion` enforce
  scope, baseline, tripwire, realized-identity, trend, realism, and exact adversary PASS gates.
- `skills/self/self-improve/lib/harness_health.py::should_escalate` is a pure threshold decision;
  escalation/recovery remains outside the evaluator.
- `config/loop-registry.json` supplies durable loop ownership. `skills/earn/gig/TODO.md` describes
  the current economic goal streams and meta-loop order; it is another Codex worktree's file and is
  intentionally not edited here.

## Adopted lessons

1. Keep immutable policy/identity separate from mutable goals and candidate skills.
2. Make every goal transition durable, typed, owned, and tied to evidence.
3. Self-improvement is baseline → bounded hypothesis → eval → tripwire → promotion/rollback.
4. Spawning and retries are resource-bounded effects, never proof that the parent goal is successful.
