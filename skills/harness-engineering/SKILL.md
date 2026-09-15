---
name: harness-engineering
description: Use when designing or changing the runtime around an LLM agent, including tool contracts, workspaces, ownership, process lifecycle, recovery, or local/cloud host adapters.
---

# Harness Engineering

## Overview

A harness is the deterministic environment that lets an augmented LLM observe, choose, act, and
resume. Keep the model responsible for semantic choices; keep the harness responsible for resource
ownership, tool execution, isolation, evidence, and lifecycle. The harness is complete only when a
finite run can resume from durable state without a human replaying the prompt.

## When to use

- Adding a tool, agent runner, host adapter, or new loop owner.
- Splitting local and cloud execution, or replacing a process supervisor.
- A run works once but loses state, crosses workspaces, retries an uncertain effect, or reports only
  a PID/exit code.

## Recipe

1. Name the logical agent, loop, resource owner, and durable state root.
2. Define the agent-computer interface: typed input, purpose, bounded output, timeout, and error
   shape. Return useful next-decision context, not raw logs.
3. Separate model policy, deterministic execution, and verification.
4. Allocate one workspace, effect namespace, browser/session lease, and receipt stream per owner.
5. Run one finite attempt; persist the decision, result, failure, and next eligible time.
6. On restart reconcile observed state, resume the owner, and retry only proven pre-effect failures.
   An uncertain effect enters reconciliation, never a blind retry.

## Contract

| Field | Required contract |
|---|---|
| Owner | One `loop_id + owner_id + resource_scope`; siblings cannot claim it |
| Input | Goal/context capsule hash plus typed tool arguments |
| Output | Bounded result with status, evidence pointers, and next action/state |
| Side effects | Effect key, lease, timeout, and official readback; no model-only success |
| Recovery | Durable cursor and reconciliation path; no process-wide restart |
| Stop | Verified terminal receipt, explicit wait, or a typed blocker with next eligible time |

## Example

```js
import { runSkill, resolveSkillPath } from './runtime/loop/run-skill.mjs'

const owner = { loopId: 'apply', ownerId: 'request-123', effectNamespace: 'coconala:acct-1' }
const slot = 'earn/gig'
const skill = resolveSkillPath(slot, config)
const result = await runSkill(slot, { owner, goalId: 'goal-7' }, wakeId, config)
// The caller records result.status/evidence and decides whether the next wake is eligible.
```

## Failure modes

| Symptom | Correct move |
|---|---|
| Two workers target one account/room | Stop the later claim; reconcile the owner lease |
| Tool timeout before effect proof | Persist `unknown` and inspect official state; do not resend |
| Model asks for an unavailable capability | Return a typed capability failure; let the model replan |
| Local/cloud implementations drift | Keep one recipe/core and vary only host adapters |
| “Success” is only PID, exit 0, or a Telegram message | Keep the goal open until authoritative readback |

## Source map

Read `references/source-notes.md` for pinned upstream file/function pointers. In Life Manager, start
with `runtime/loop/run-skill.mjs`, `runtime/loop/index.mjs`, `runtime/loop/prompt.mjs`,
`config/loop-registry.json`, and `skills/loop-development/SKILL.md`. Primary upstream examples are
Symphony's `orchestrator.ex`/`agent_runner.ex`, Deep Agents' `graph.py` and `better-harness`,
OpenHands' `AGENTS.md`/`src`, and Hermes' state/tool modules.
