---
name: launch-readiness-gate-deck
description: Turn buyer-pasted launch criteria, evidence, dependencies, and open decisions into a traceable go/no-go gate deck outline without claiming a launch is ready.
---

# Launch Readiness Gate Deck

Turn launch material pasted into the chat into a concise, decision-ready gate
deck outline. The result is structured text for the buyer to place in their own
presentation tool; it does not make, record, or communicate a launch decision.

## Input

Ask for the launch name and target date; decision-maker and audience; the exact
go/no-go decision requested; supplied release criteria or gate definitions;
evidence for each criterion; dependencies; known risks or blockers; named
owners; and dates. Ask which wording or status labels must remain exact.

Treat an omitted criterion, evidence item, owner, date, dependency, approval,
or status as unknown. A stated target date is not evidence that the launch will
occur on that date.

## Method

1. Make a gate ledger that retains each supplied criterion, its supplied status,
   evidence, owner, and date. Never infer that a gate passes or fails.
2. Separate completed work, planned work, reported risks, and requested
   decisions. Label unsupported claims `[UNVERIFIED]`.
3. Map each supplied dependency to the gate it affects. Keep a dependency with
   no supplied gate link in an open-questions list.
4. Identify only the blockers and decisions that the buyer explicitly supplies;
   do not predict schedule, delivery, approval, or business outcomes.
5. Draft a six-slide gate narrative: decision, launch scope, gate ledger,
   dependencies, blockers and choices, and next review.
6. Run a traceability pass. Every factual statement must point to supplied
   material; replace missing ownership, dates, and evidence with `[TBD]`.

## Output

Return, in this order:

1. A decision brief with the requested decision, target date if supplied, and
   clearly labelled unknowns.
2. A gate ledger with criterion, supplied status, supplied evidence, dependency,
   owner, and date.
3. A six-slide deck outline. Each slide has a title, takeaway, supplied
   evidence, and visual suggestion.
4. A blocker-and-decision register distinguishing a supplied blocker from an
   open question.
5. A next-review agenda containing only supplied milestones and clearly marked
   missing owners or dates.
6. A traceability check listing statements that need accountable-owner
   confirmation before any launch decision.

## Boundaries

Use only the material pasted into the chat and general language reasoning. Do
not inspect systems, release pipelines, test records, calendars, tickets, or
approval records. Do not claim a criterion is satisfied, a dependency is
resolved, a launch is ready, or a launch should proceed unless the buyer has
explicitly supplied that conclusion. Do not create a presentation file, update
a release plan, send a status update, or make the final go/no-go decision.

## Plans

| cycle | price | cap | trial |
|---|---:|---:|---|
| week | $9.99 | 20 | No Free Trial |
| month | $24.99 | 60 | No Free Trial |
