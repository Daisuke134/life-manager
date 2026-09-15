---
name: goal-engineering
description: Use when defining, decomposing, resuming, measuring, or closing an agent goal, including self-improvement, spawning, budgets, deadlines, and typed blockers.
---

# Goal Engineering

## Overview

A goal is a durable contract between intent and evidence. It names who owns the next transition,
what result counts, what resources are allowed, and when the loop must stop. Recursive improvement
means proposing and measuring bounded changes to a goal or skill—not allowing the agent to rewrite
its constitution, permissions, identity, or evidence rules.

## When to use

- A loop has an aspiration but no measurable finish line or owner.
- Work is split into subgoals, waits for an external event, or resumes after a failure.
- An agent proposes changing its prompt, skill, model, tool, policy, or spawn configuration.

## Recipe

1. Write one goal ID, owner/resource scope, intent, horizon, budget, deadline, and observable success
   condition.
2. Choose the smallest evidence-producing subgoal with one owner and next transition.
3. Use typed states (`proposed`, `active`, `waiting_external`, `blocked`, `evaluating`, `completed`,
   `cancelled`) and persist each cause/source fact.
4. At each wake load the latest revision and authority; let the model act, replan, wait, or close.
5. Enforce deterministic budgets, leases, permissions, and effect/readback gates; never silently extend
   limits.
6. For self-improvement record hypothesis, frozen baseline, changed hashes, eval split, tripwires, and
   rollback before running. Promote only after held-out and required live gates; append the lesson.

## Contract

| Field | Required contract |
|---|---|
| Identity | stable `goal_id`, owner, parent (optional), resource/effect scope |
| Intent | human intent, success predicate, non-goals, priority, horizon |
| Resources | budget, deadline, concurrency, permissions, stop/cancel authority |
| State | typed lifecycle state, revision, transition cause, next eligible time |
| Evidence | source facts, eval/live receipts, baseline/candidate hashes, rollback pointer |
| Learning | failure class, lesson, proposed skill change, promotion decision/reason |

## Example

```json
{
  "goal_id": "gig-meta-001",
  "owner": "meta-loop",
  "success": "one new provider adapter has an official application receipt and replay-zero",
  "state": "evaluating",
  "budget": {"max_attempts": 3, "max_cost_usd": 2},
  "baseline_sha256": "…",
  "candidate_sha256": "…",
  "evidence": ["eval-run-42", "receipt-17"],
  "next_eligible_at": "2026-09-15T12:00:00Z"
}
```

## Failure modes

| Symptom | Correct move |
|---|---|
| Goal has no observable success predicate | Keep it `proposed`; refine it from available facts |
| Subgoal waits forever | Persist `waiting_external` with owner, reason, and recheck time |
| Candidate wins only on fixtures | Keep baseline; require held-out and realized evidence |
| Agent changes its own safety/identity boundary | Reject and record a policy violation; never promote |
| Spawn/retry increases without progress | Enforce budget/concurrency and return a typed blocker |

## Source map

Read `references/source-notes.md` for pinned code. Local starting points are
`skills/self/spawn/lib/spawn-decision.js`, `skills/self/spawn/lib/spawn-orchestrator.mjs`,
`skills/earn/self-improve/lib/promote_gate.py`, and the loop registry/TODO contracts.
