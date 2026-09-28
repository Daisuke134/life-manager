---
name: ai-evaluation-failure-triage-brief
description: Use when a team needs to turn pasted AI evaluation cases, expected results, observed results, and notes into an evidence-bounded failure-triage brief without inventing root causes, metrics, or fixes.
---

# AI Evaluation Failure Triage Brief

Turn pasted AI evaluation material into a compact triage brief that keeps observed
behavior, expected behavior, hypotheses, and missing evidence separate. It helps a
team decide what to inspect next; it does not diagnose a model, run an evaluation,
or change a system.

## Input

Ask for the evaluation goal, cases or excerpts, expected result, observed result,
severity or priority if supplied, relevant prompt or configuration excerpts, run
notes, and any owner or next review. Treat omitted metrics, versions, datasets,
causes, dates, owners, and outcomes as unknown.

## Method

1. Build an evidence ledger from the pasted material. Label each material item as
   `observed`, `expected`, `reported`, `hypothesis`, `planned`, `completed`,
   `unknown`, or `needs verification`.
2. Make one case record per supplied evaluation case. Preserve quoted expected and
   observed behavior without repairing, normalizing, or extending either one.
3. Identify the stated mismatch for each case. Keep a proposed explanation as a
   hypothesis unless the input supplies confirmed causal evidence.
4. Group missing information into reproducibility, input/context, configuration,
   scoring, and decision-owner questions. Do not imply that a missing field caused
   the failure.
5. Return a triage brief containing the supplied evidence, explicitly bounded
   hypotheses, and a next-inspection queue. Include only supplied priorities,
   owners, timings, and completed work.

## Output

Return, in order:

1. A triage summary stating the supplied goal and the number of supplied cases.
2. A case table with expected behavior, observed behavior, stated mismatch, and
   evidence status.
3. A hypothesis register that separates supplied explanations from unknown causes.
4. A next-inspection queue for missing reproducibility and review information.
5. An evidence ledger for every material conclusion.

## Boundaries

Use only material pasted into the chat and general language reasoning. Do not run
code, access repositories, inspect logs or dashboards, query an evaluation service,
alter prompts or configuration, contact anyone, calculate an unsupplied metric, or
claim a root cause, regression, fix, or performance improvement. A responsible
technical owner must verify the brief before acting on it.
