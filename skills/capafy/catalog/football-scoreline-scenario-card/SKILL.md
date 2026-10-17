---
name: football-scoreline-scenario-card
description: Turn buyer-pasted football match evidence into conditional scoreline scenarios, assumptions, and an editorial-ready match explainer. Use for one upcoming match when current facts are supplied; not for live-data retrieval, wagering, or certain predictions.
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# Football Scoreline Scenario Card

Turn a buyer's supplied one-match evidence into a transparent scoreline-scenario
card. This is a text-only reasoning workflow: it helps a football writer or
podcast producer explain which supplied conditions support different match
shapes. It does not know current facts unless the buyer supplies them.

## Use when

- A football writer has one upcoming fixture plus their own recent goal notes,
  availability notes, and tactical observations.
- A podcast producer needs an evidence-bound scoreline discussion segment.
- A buyer wants assumptions and missing facts made explicit instead of a
  confident-sounding result claim.

## Input

Ask for one match only:

```text
fixture: away team, home team, competition, and date if known
goal_evidence: buyer-pasted scoring/conceding notes, split data, or match observations
availability: supplied absences, returns, or uncertainty
tactical_notes: supplied style, matchup, or game-state notes
editorial_goal: article, podcast, fan discussion, and desired length
```

If the buyer gives fewer facts, proceed with a smaller card and mark the
missing fields `[UNVERIFIED]`. Never fill current team, injury, score, schedule,
or statistic gaps from assumed knowledge.

## Workflow

1. Build an evidence ledger that separates supplied facts, interpretations,
   and missing facts.
2. Identify the supplied scoring, conceding, availability, and tactical factors
   that could change the match shape.
3. Write up to three conditional scenarios. Each scenario names a plausible
   scoreline range, the supplied assumptions it depends on, a confidence label,
   and a falsifier.
4. Produce an editorial-ready explainer and a verification queue. A scenario is
   never a promise, a probability, or a wagering instruction.

## Output format

```markdown
# Football Scoreline Scenario Card: [away] at [home]

## Evidence boundary
- Supplied: [fact]
- [UNVERIFIED]: [missing fact]

## Conditional scenarios
| Scenario | Scoreline range | Supplied basis | Confidence | What would change it |
| --- | --- | --- | --- | --- |
| [label] | [for example, home by one goal] | [input fact] | [low/medium] | [missing or changed fact] |

## Match-shape drivers
1. [evidence-bound driver]

## Editorial explainer
[short source-bounded paragraph]

## Verify before using
- [current fact to confirm]
```

## Guardrails

- Reason only from buyer-pasted material and general football concepts.
- Do not browse, retrieve, or assert live scores, lineups, odds, statistics, or
  injuries.
- Do not recommend a wager, state an outcome as certain, or invent numerical
  probabilities.
- Use scoreline ranges only as conditional editorial scenarios tied to supplied
  assumptions; mark unsupported facts `[UNVERIFIED]`.

## Quality check

Before returning the card, confirm that it contains one fixture, an evidence
boundary, at least one stated assumption per scenario, a falsifier for each
scenario, and no current fact that cannot be traced to the buyer's input.
