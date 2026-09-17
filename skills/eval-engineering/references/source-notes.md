# Eval source notes

## What to read upstream

- `uk-inspect-ai/src/inspect_ai/_eval/task/` and `solver/_solver.py`: task/sample/solver boundaries;
  `scorer/` separates criteria and metrics; `_eval/eval.py` and `evalset.py` handle runs, retries,
  cancellation, and reproducible task sets.
- `uk-inspect-ai/src/inspect_ai/_eval/task/log.py` and `log/_log.py`: `TaskLogger`, sample events,
  config, and finish records preserve a trajectory instead of only a final score.
- `uk-inspect-ai/examples/tool_use.py`, `examples/structured.py`, and `examples/reasoning.py`: small
  task definitions show how tool use and structured outcomes become eval inputs.
- `stanford-dspy/dspy/evaluate/evaluate.py` and `dspy/teleprompt/`: evaluator/optimizer separation;
  inspect `BootstrapFewShot`, `MIPROv2`, and signature-based modules before changing prompts.
- `openai-simple-evals`: transparent baseline runners for factual/benchmark cases. Its README marks
  the repository deprecated for new benchmarks, so use it only for simple reference patterns.

## Life Manager mapping

- `apps/life-manager/eval/` contains deterministic calendar, intent, context, privacy, connector, and
  event-goal eval runners. Add a case to the owning file rather than creating a parallel harness.
- `skills/self/self-improve/lib/harness_health.py` computes health from already-parsed records and
  keeps escalation pure; it is an evaluator, not a repair action.
- `skills/earn/self-improve/lib/promote_gate.py::assess_candidate` runs scope, stage, and tripwire
  gates before any costly fresh review; `decide_promotion` requires an exact PASS and can block on
  unresolved realized identity, negative trend, or realism gap.
- `skills/self/self-improve/*/evaluator.py` and `weekly_compare.py` show per-loop evaluation and
  historical comparison; preserve the distinction between fixture score and realized ledger facts.

## Adopted lessons

1. Define the expected evidence before the agent runs.
2. Keep deterministic policy/permission/replay checks outside a semantic grader.
3. Freeze a baseline and held-out split; never tune and judge on the same cases.
4. Make promotion a pure gate over measured outputs, then let a separate owner perform deployment.
