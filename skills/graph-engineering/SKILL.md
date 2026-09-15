---
name: graph-engineering
description: Use when an agent needs to model dependencies, provenance, identity, state transitions, or cross-loop queries without creating a second source of truth.
---

# Graph Engineering

## Overview

A graph is a queryable projection of facts, not the authority that proves an external effect. Start
with the questions the agent must answer, then project the smallest nodes and edges that answer them.
Every edge carries provenance, authority, and observed time so a stale or inferred relationship cannot
silently become permission.

## Master catalog route

Read this skill first. Then consult the pinned **[Awesome Harness Engineering](https://github.com/ai-boost/awesome-harness-engineering)**
snapshot (`692a1a681c464de22a5e9b947bd081808600b0b3`) under Memory & State, Agent Loop, and Reference
Implementations. Use the dedicated [Awesome Graph Engineering](https://github.com/adventurewave-labs/awesome-graph-engineering)
list only as secondary discovery. Read `references/source-notes.md` before borrowing Graphiti or
LangGraph code; the catalog never becomes the graph authority.

## When to use

- Goals, capabilities, artifacts, effects, receipts, or people have real dependencies.
- A loop needs cross-run queries such as “what requirement produced this artifact?” or “which goals
  are blocked by the same missing capability?”
- Identity or temporal facts change and a flat lookup loses history.

## Recipe

1. Write three to five competency questions before choosing a library.
2. Name the append-only fact source and projection revision; the graph never replaces the ledger or
   official readback.
3. Choose stable authoritative IDs and keep unproven provider/local aliases separate.
4. Define a small edge vocabulary (`requires`, `produced_by`, `sent_to`, `proved_by`, `earned`,
   `supersedes`) and reject unknown predicates.
5. Project idempotently with source fact, time, authority, and content hash on every node/edge.
6. Query for planning, then recheck mutable authority before effect/promotion. Diagnose missing nodes,
   identity conflicts, cycles, or stale edges instead of inventing facts.
7. Add a graph database only after a measured traversal/concurrency need.

## Contract

| Element | Required fields |
|---|---|
| Node | `id`, `kind`, `source_fact_id`, `observed_at`, `authority`, `sha256` |
| Edge | `from`, `to`, `predicate`, `source_fact_id`, `observed_at`, `confidence` |
| Identity | Canonical key plus provider/local aliases with an explicit match reason |
| Projection | Input ledger revision, projection revision, deterministic rebuild command |
| Query | Competency question, bounded result, source pointers, stale/unknown markers |
| Authority | Graph output can guide a decision; only the authoritative source can prove an effect |

## Example

```python
def project_effect(fact: dict) -> tuple[dict, dict]:
    """Pure projection: no provider action and no invented receipt."""
    effect_id = fact["effect_key"]
    node = {"id": effect_id, "kind": "effect", "source_fact_id": fact["id"],
            "observed_at": fact["observed_at"], "authority": fact["authority"],
            "sha256": fact["sha256"]}
    edge = {"from": fact["goal_id"], "to": effect_id, "predicate": "sent_to",
            "source_fact_id": fact["id"], "observed_at": fact["observed_at"],
            "confidence": fact.get("confidence", "unknown")}
    return node, edge
```

## Failure modes

| Symptom | Correct move |
|---|---|
| Graph says “sent” but provider readback is missing | Mark unknown; inspect the provider, do not promote the edge |
| Same person has two IDs | Keep aliases and require an explicit identity fact before fusion |
| Projection rebuild changes old relationships | Version the projection and preserve source facts |
| Dependency cycle appears | Return a cycle diagnostic and let the goal planner replan |
| New database proposed for one query | Keep the local append-only index until a second measured query justifies extraction |

## Source map

Read `references/source-notes.md` for pinned code. Local starting points are
`apps/life-manager/lib/context-graph.js`, `scripts/integration-onboarding.py`,
`config/loop-registry.json`, and `skills/registry.json`.
