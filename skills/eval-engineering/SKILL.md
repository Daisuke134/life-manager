---
name: eval-engineering
description: Use when measuring an agent, loop, tool, prompt, or self-improvement candidate, including dataset design, trajectory scoring, regression checks, or promotion decisions.
---

# Eval Engineering

## Overview

An eval is a reproducible decision instrument, not a number attached to a demo. Separate the task
dataset, agent/solver, tool environment, scorer, and promotion policy. Measure both the behavior in a
controlled fixture and the real-world evidence that the fixture cannot provide.

## When to use

- A loop change needs a baseline, regression gate, or held-out test.
- A model/prompt/tool choice is being compared or optimized.
- A self-improvement candidate claims to be better, safer, cheaper, or more profitable.

## Recipe

1. State the behavior, failure classes, and pass condition before running.
2. Build a versioned dataset with canonical, boundary, adversarial, and prior-failure cases; separate
   tuning from held-out data.
3. Run the same solver and tool fixtures while recording model, prompt/code hashes, seed, calls,
   latency, cost, and outcome IDs.
4. Score deterministic invariants first; use a model grader only for irreducibly semantic criteria.
5. Report per-case variance and preserve failed trajectories.
6. Compare with a frozen baseline and held-out set. Regressions in safety, cost, latency, or live
   evidence block promotion; the evaluator never mutates production.

## Contract

| Component | Required fields |
|---|---|
| Case | stable ID, input/context hashes, expected evidence, split (`train`/`held_out`) |
| Run | candidate/baseline version, model, prompt hash, tool fixture, seed, started/finished time |
| Score | per-criterion values, scorer version, errors, trace/receipt pointers |
| Gate | baseline comparison, safety tripwire, live-realism check, promotion decision/reason |
| Artifact | immutable result file; no overwrite of prior runs |

## Example

```jsonl
{"id":"reply-unknown-effect","split":"held_out","goal":"reply once","input_hash":"…","must":"official readback or owned retry","must_not":"blind resend"}
```

```python
def gate(candidate, baseline, live_receipts):
    if candidate.schema_failures or candidate.safety_tripwire:
        return {"promote": False, "reason": "deterministic gate failed"}
    if candidate.held_out_score <= baseline.held_out_score:
        return {"promote": False, "reason": "no held-out improvement"}
    if live_receipts.unresolved_identity or live_receipts.negative_trend:
        return {"promote": False, "reason": "realized evidence blocks promotion"}
    return {"promote": True, "reason": "baseline and live gates clear"}
```

## Failure modes

| Symptom | Correct move |
|---|---|
| Test passes only on happy paths | Add boundary/adversarial/previous-failure cases |
| Model grader says “looks good” without evidence | Require structured criteria and source pointers |
| Candidate beats a fixture but live revenue worsens | Keep baseline; mark realism-gap/trend blocker |
| Eval retries mutate a provider | Use isolated fixtures; provider effects require a separate authorized acceptance |
| One aggregate hides a bad class | Report per-case/per-class scores and variance |

## Source map

Read `references/source-notes.md` for pinned code. Local starting points are `apps/life-manager/eval/`,
`skills/self/self-improve/`, and `skills/earn/self-improve/lib/promote_gate.py`.
