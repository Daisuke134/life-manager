---
name: observability-engineering
description: Use when instrumenting or diagnosing an agent/loop, defining traces or metrics, debugging retries and stalls, or proving the difference between process health and an external business effect.
---

# Observability Engineering

## Overview

Observability makes a loop explainable across wakes without turning logs into a second source of
truth. Emit stable, privacy-safe lifecycle events and traces for the model, tools, state transitions,
effects, and readbacks. Keep business receipts in the durable ledger; use traces to find why a result
happened.

## Master catalog route

Read this skill first. Then consult the pinned **[Awesome Harness Engineering](https://github.com/ai-boost/awesome-harness-engineering)**
snapshot (`692a1a681c464de22a5e9b947bd081808600b0b3`) under Observability & Tracing, Debugging &
Developer Experience, and Verification & CI. The specialized [Awesome Agent Observability](https://github.com/danielt69/awesome-agent-observability)
list is secondary discovery. Read `references/source-notes.md` for OpenInference/Phoenix pointers;
telemetry remains diagnostic and never replaces a ledger or provider readback.

## When to use

- A loop stalls, retries, times out, or appears healthy while making no progress.
- You need latency, cost, tool-use, failure-class, or replay metrics.
- A new provider/effect requires a trace that can be joined to its official readback.

## Recipe

1. Define stable events/spans: `wake.started`, `decision.made`, `tool.started`, `tool.finished`,
   `effect.requested`, `readback.observed`, `wake.finished`.
2. Carry bounded IDs (`loop_id`, `owner_id`, `wake_id`, `goal_revision`, `effect_key`) and hash/scoped
   provider identifiers.
3. Record duration, attempt, status, failure class, model/tool version, and trace pointers.
4. Redact secrets, PII, full prompts, attachments, and unbounded output before persistence/export.
5. Send diagnostics to OTel/OpenInference or the existing logger; append authoritative effects/readbacks
   to the ledger, never to a dashboard-only store.
6. Derive bounded metrics and alert on durable actionable states, then link traces/receipts to evals.

## Contract

| Signal | Required fields |
|---|---|
| Event | schema version, kind, IDs, timestamp, status, bounded reason |
| Span | parent/child relation, component, duration, outcome, redacted attributes |
| Metric | name, unit, bounded dimensions, aggregation window, source |
| Receipt | effect key, provider readback, authoritative ID/hash, replay result |
| Privacy | redaction decision and payload-size limit; no raw secret/PII export |
| Health | owner/liveness separate from business success and revenue |

## Example

```js
export function toolEvent({ wakeId, ownerId, slot, attempt, status, durationMs, traceId }) {
  return {
    schema_version: 1, kind: 'tool.finished', wake_id: wakeId, owner_id: ownerId,
    slot, attempt, status, duration_ms: durationMs, trace_id: traceId,
  }
}
```

## Failure modes

| Symptom | Correct move |
|---|---|
| Logs contain raw prompt/credential/PII | Stop export, redact at the boundary, rotate only if exposure is proven |
| PID is alive but no effect receipt exists | Mark business state unknown/blocked; inspect the provider |
| One high-cardinality label makes metrics unusable | Hash or remove raw IDs; keep stable scoped dimensions |
| Trace exporter is down | Keep the loop's durable receipt path; record observability degradation separately |
| Health watchdog restarts on any error | Classify failure layer and use the owning recovery contract |

## Source map

Read `references/source-notes.md` for pinned code. Local starting points are
`runtime/loop/harness-health-snapshot.mjs`, `skills/self/self-improve/lib/harness_health.py`,
`apps/life-manager/lib/effect-reconciler.js`, and the shared ledger/receipt modules.
