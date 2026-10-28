---
name: npb-game-flow-scenario-brief
description: Turn buyer-pasted NPB game notes into a conditional first-five and late-inning game-flow brief for baseball coverage; do not use it for live data, wagers, or certain results.
license: MIT
metadata:
  author: anicca
  stage: S2-Analysis
---

# NPB Game-Flow Scenario Brief

Use this skill when a Japanese-baseball writer, podcast producer, or serious fan has
their own upcoming-game notes and needs a disciplined preview of plausible game
flows. It is a text-only analysis of the material supplied in the conversation.

## Required input

Ask for one upcoming NPB game and the buyer's available evidence:

- teams, venue, and game date or label;
- probable starters and the buyer's notes on pitch mix, workload, or recent outings;
- expected lineup or matchup notes;
- bullpen and availability notes;
- park, weather, or tactical context, if the buyer has it; and
- the intended coverage use (article, broadcast, or fan discussion).

Mark every missing current fact `[UNVERIFIED]`. Do not fill gaps with roster
knowledge, a statistic, a result, an injury update, or a betting line.

## Method

1. Make an evidence ledger separating supplied facts, interpretations, and gaps.
2. Identify up to three supplied factors that could shape the first five innings,
   such as a starter workload note, lineup handedness, or a park condition.
3. Build two or three conditional game-flow scenarios. Each must state its
   supporting input, a counter-condition, and a confidence level. These are
   editorial possibilities, never forecasts or probabilities.
4. Add a late-inning branch only when the buyer supplied bullpen or availability
   context. Otherwise label that branch `[UNVERIFIED]`.
5. Finish with a coverage lead, a 45-second spoken rundown, and a short list of
   facts to confirm before publication.

## Output format

```markdown
# NPB Game-Flow Scenario Brief: [away] at [home]

## Evidence boundary
- Supplied: ...
- [UNVERIFIED]: ...

## First-five factors
| Supplied factor | Possible effect | Confidence | Limitation |
| --- | --- | --- | --- |

## Conditional game flows
### [Scenario label]
- Supported by: ...
- If this holds: ...
- What would change it: ...
- Confidence: low / medium / high

## Late-inning branch
[Use supplied bullpen context, or state what is unverified.]

## Coverage lead
[One qualified paragraph.]

## 45-second rundown
[Source-bounded spoken summary.]

## Confirm before using
- ...
```

## Boundaries

- Work only from buyer-pasted material and general baseball reasoning.
- Do not retrieve current scores, lineups, standings, weather, injury reports,
  odds, or other external information.
- Do not recommend a wager, assign a win probability, predict a final score, or
  present any scenario as a result.
- If the buyer asks for current information, ask them to paste the facts they
  want assessed.

## Quality checks

Before returning, confirm that the output:

1. Covers exactly one buyer-supplied upcoming NPB game.
2. Traces every current-game statement to supplied material or marks it
   `[UNVERIFIED]`.
3. Makes every scenario conditional and names what could change it.
4. Includes neither wagering advice nor a certain result.

See `evidence/verified-demonstration.md` for a concrete input, output, and
verification record.
