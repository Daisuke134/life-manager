---
name: context-engineering
description: Use when an agent must assemble, trim, persist, or refresh context for a long-running task, including memory, summaries, prompt budgets, provenance, or cross-session resume.
---

# Context Engineering

## Overview

Context is a compiled view of durable facts, not a transcript dump. Build the smallest context that
lets the model make the next correct decision while preserving the evidence and commitments that
cannot be reconstructed cheaply. Summaries are derived data; source records and official receipts
remain authoritative.

## When to use

- A prompt is too large, a session is compacted, or tool output is flooding the model.
- A resumed owner forgets a promise, winning artifact, effect key, or unresolved blocker.
- Multiple loops need shared facts without sharing mutable conversation context.

## Recipe

1. State the current goal, owner, decision boundary, and next action before history.
2. Gather authoritative provider state, durable facts, accepted artifacts, permissions, and the latest
   verified receipt.
3. Add task-local constraints, decisions, failures, and questions; link each to a source ID/hash and
   observed time.
4. Add historical summaries only when they change the next decision. “Last N messages” is never the
   contract context for an effect-bearing task.
5. Keep identifiers, commitments, and evidence; offload long logs/artifacts to hashed files with
   bounded excerpts.
6. Recheck freshness before effects, persist capsule/source hashes, and append revisions on resume.

## Contract

| Field | Required contract |
|---|---|
| Capsule | `goal`, `owner`, `sources[]`, `decisions[]`, `open_questions[]`, `budget`, `hash` |
| Source | ID, type, observed time, authority, content hash, and bounded locator |
| Summary | Explicitly marked derived; points to all omitted source records |
| Freshness | Recheck mutable provider/effect sources immediately before action |
| Privacy | Never include secrets, credentials, raw PII, or unbounded external payloads |
| Resume | Same owner and effect namespace; append a revision, never silently reset |

## Example

```js
export function compileCapsule({ goal, owner, facts, decisions, budget }) {
  const sources = facts.map(({ id, authority, observedAt, sha256 }) =>
    ({ id, authority, observedAt, sha256 }))
  return {
    goal, owner, sources, decisions,
    open_questions: facts.filter((fact) => fact.status === 'unknown').map((fact) => fact.id),
    budget: { maxTokens: budget, omitted: 'large logs/artifacts -> content store' },
  }
}
```

## Failure modes

| Symptom | Correct move |
|---|---|
| Context exceeds budget | Offload low-signal payloads; keep hashes and decision/effect facts |
| Old and new provider state disagree | Mark stale, refresh authoritative state, and replan |
| Summary has no provenance | Reject it; rebuild from source records |
| Two owners share a conversation transcript | Keep separate capsules; share only approved facts |
| Model wants to act on an old artifact | Bind the decision to the last accepted artifact hash |

## Source map

Read `references/source-notes.md` for pinned code pointers. Local starting points are
`runtime/loop/prompt.mjs`, `apps/life-manager/lib/context-graph.js`, `apps/life-manager/lib/event-cache.js`,
and the Project Context Capsule contract in `skills/earn/gig/TODO.md` (reference only; do not edit in
this skill workstream).
