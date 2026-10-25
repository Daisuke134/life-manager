---
name: tennis-match-tactics-brief
description: >
  Turn buyer-pasted tennis matchup notes, surface context, and point-pattern observations into an evidence-bound tactics brief with conditional adjustments. Use when a coach, tennis writer, or serious fan needs a disciplined single-match analysis without claiming access to current tennis information.
license: MIT
version: "1.0.0"
tags: [tennis, match-analysis, tactics, sports-writing]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# Tennis Match Tactics Brief

Tennis Match Tactics Brief turns the notes a buyer already has into a traceable, single-match tactics package. It explains how supplied surface context, serve and return patterns, rally observations, and stated tendencies may shape choices, while treating absent current facts as unknown rather than inventing them.

## Stage

This skill belongs to Stage S2: Analysis.

## When to Use

- A tennis coach has one matchup's practice or match notes and needs a conditional point-pattern plan.
- A writer or podcast producer needs a short tennis rundown that separates supplied observations from interpretation.
- A serious fan wants to organize pasted serve, return, and rally notes without treating unstated form, fitness, or draw information as confirmed.

## Input Schema

```text
match: string (required) — the two players and match label supplied by the buyer
surface_context: string (required) — surface, conditions, or court-speed notes supplied by the buyer
player_notes: string (required) — supplied serve, return, rally, movement, and stated-tendency observations for both players
evidence_notes: string (optional) — buyer-pasted point counts, practice observations, or quoted notes
tactical_goal: string (optional) — coaching plan, preview, podcast, or discussion angle to prioritize
```

## Workflow

### Step 1: Set the evidence boundary

Extract the named match, supplied surface context, player observations, and numerical point notes into a compact ledger. Mark every missing fitness detail, ranking, draw fact, score context, weather condition, or current statistic `[UNVERIFIED]`. The reader must be able to identify which facts came from the buyer.

### Step 2: Build the point-pattern card

Compare the supplied inputs across first serve, second serve, return position, rally direction, movement, and surface fit. For every row, name the supplied input that supports the read and one limitation. The quality bar is a cautious matchup analysis, not a result prediction.

### Step 3: Write conditional adjustments

Produce two or three `if observed` / `if changed` adjustments based only on the notes. State the tactical implication and the fact that would change the recommendation. The quality bar is that incomplete information stays conditional.

### Step 4: Deliver the tactics package

Return an evidence boundary, point-pattern card, conditional adjustments, coverage angles, a verification queue, and a 45-second match rundown. The quality bar is a self-contained text package a buyer can adapt without confusing model knowledge with current-match facts.

## Output Schema

```text
output_schema_version: "1.0.0"
match_label: string
evidence_boundary: string[]
point_pattern_card: { axis: string, supplied_fact: string, matchup_read: string, confidence: "low" | "medium" | "high", limitation: string }[]
conditional_adjustments: { condition: string, adjustment: string, evidence: string, falsifier: string }[]
coverage_angles: { angle: string, supporting_input: string, caveat: string }[]
verification_queue: string[]
match_rundown: string
```

## Output Format

```markdown
# Tennis Match Tactics Brief: [player] vs [player] — [surface/label]

## Evidence boundary
- Supplied: [fact]
- [UNVERIFIED]: [missing current fact]

## Point-pattern card
| Axis | Supplied fact | Read | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| [serve/return/rally/movement/surface] | [fact] | [evidence-bound interpretation] | [low/medium/high] | [gap] |

## Conditional adjustments
- If [condition]: [adjustment]. Evidence: [supplied material]. Reconsider if: [falsifier].

## Coverage angles
1. [angle] — Evidence: [supplied material]. Caveat: [limitation].

## Verify before using
- [current fact the buyer should confirm]

## 45-second match rundown
[brief, source-bounded spoken summary]
```

## Error Handling

- **No individual matchup supplied:** Ask for one matchup before making a tactics card; do not turn a tournament draw into this product.
- **No surface or point-pattern notes:** Build only an input checklist and mark matchup rows `[UNVERIFIED]`; do not infer a surface preference.
- **Conflicting supplied observations:** Quote both claims in the evidence boundary and ask which note should control the revision.
- **Request for current scores, rankings, draw information, weather, or injury status:** Explain that the skill assesses only buyer-pasted material and request the facts to analyze.
- **Request for a wager or certain result:** Decline certainty framing and provide conditional tactical questions instead.

## Examples

### Example 1: Clay-court serve and return pattern

**Input:** Clay court: Player A won 9 of 12 first-serve points but gave up 6 short returns. Player B attacked second serves and missed 5 backhands under crosscourt pressure. Fitness status is not supplied.

**Decision:** Separate the small supplied samples from a recommendation, and condition any second-serve adjustment on the pattern recurring.

**Output excerpt:** `If the supplied pattern continues, Player A can protect second serves with deeper placement before using crosscourt pressure. Confidence: medium. The notes do not establish fitness, score pressure, or whether the samples cover a full match.`

### Example 2: Incomplete movement note

**Input:** Hard court: Player C's notes say they recovered two wide forehands but give no length of match or recovery information. Player D served wide on three deciding points. No return-position note is supplied.

**Decision:** Keep movement and wide-serve conclusions conditional, and place sample size and return position in the verification queue.

**Output excerpt:** `The supplied deciding-point serves justify a wide-serve question, not a settled pattern. Verify the return position and a larger sample before turning it into a match plan.`

## Flywheel Connections

### Feeds Into

- `sports-podcast-run-sheet` (S2-Content) — the match rundown can become a source-bounded host segment.
- `football-match-analyst` (S2-Analysis) — buyers who use structured sport analysis can reuse the evidence-bound discipline for another sport.

### Fed By

- Buyer-maintained tennis match notes, practice observations, and point-pattern excerpts.
- A buyer's editorial calendar identifying the individual match that needs discussion.

### Feedback Loop

Buyers can report which supplied serve, return, and rally fields made the brief useful; use that feedback to refine the input checklist without adding claims of access to current tennis information.

```yaml
chain_metadata:
  skill_slug: "tennis-match-tactics-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-26"
  suggested_next:
    - "sports-podcast-run-sheet"
    - "football-match-analyst"
```

## Quality Gate

1. The output identifies exactly one buyer-supplied tennis matchup.
2. Every surface, player, point count, and stated tendency is traceable to the pasted input or labeled `[UNVERIFIED]`.
3. Each point-pattern row gives a supplied fact, interpretation, confidence label, and limitation.
4. Every incomplete observation produces a conditional adjustment rather than a prediction.
5. The brief contains no wagering advice, certain match result, or claim of access to current tennis information.
6. The verification queue contains only facts that would improve the next revision.

## References

- `LISTING.md` — buyer-facing offer, plans, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification record.
