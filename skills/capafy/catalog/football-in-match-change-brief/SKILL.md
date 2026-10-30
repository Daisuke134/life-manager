---
name: football-in-match-change-brief
description: >
  Turn a buyer-pasted football match state, bench options, and stated tactical question into a conditional change brief for commentary or staff discussion. Use when a football analyst needs to explain a possible shape or personnel change without claiming access to a match feed.
license: MIT
version: "1.0.0"
tags: [football, match-analysis, tactical-brief, commentary, sports-writing]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# Football In-Match Change Brief

Turn one buyer-supplied football decision moment into a bounded change brief. Unlike a fixture preview, scoreline scenario card, set-piece plan, or post-match review, this skill works from the stated minute, score, shape, available personnel, and question to compare conditional options. It is analysis of pasted material for commentary or discussion, not a match feed, instruction to a team, or outcome prediction.

## Stage

This skill belongs to Stage S2: Analysis.

## When to Use

- A commentator has a buyer-pasted match state and needs a short, evidence-bounded explanation of a possible personnel or shape change.
- A football analyst wants to compare two stated change options without inventing a lineup, current score, or player availability.
- A coaching staff discussion needs a structured record of trade-offs from its own supplied observations, not a prescriptive answer.
- A writer needs a conditional match note that separates known facts from information that still needs confirmation.

## Input Schema

```text
match_context: string (required) — teams, competition if relevant, stated minute and score.
current_shape_and_pattern: string (required) — buyer-pasted shape, observed problem, and relevant phase of play.
decision_question: string (required) — one personnel, role, or shape-change question to compare.
available_options: string (required) — named or role-based bench/field options and any stated limitations.
evidence_notes: string (optional) — supplied workload, cards, matchup, event, or tactical observations.
audience: string (optional) — commentary, analyst notes, or staff discussion; defaults to analyst notes.
```

## Workflow

### Step 1: Establish the evidence boundary

Extract only the teams, minute, score, shape, observed problem, named options, and constraints that the buyer actually supplied. Label each missing current fact `[UNVERIFIED]`. Quality bar: every factual statement in the brief is traceable to the pasted record.

### Step 2: Restate one decision moment

Write the decision question in one neutral sentence and identify the stated objective (for example, protect a lead or improve access to wide areas). Do not turn an ambiguous prompt into a recommendation. Quality bar: the brief addresses exactly one buyer-supplied decision rather than expanding into a generic match preview.

### Step 3: Build two or three conditional paths

For each supplied option, state the possible tactical effect, the stated trade-off, and the fact that could change the reading. Use `If ...` wording where the input cannot establish a preferred move. Quality bar: each path names a consequence and a limitation; no path promises a result.

### Step 4: Produce an audience-ready change card

Return the evidence boundary, decision card, conditional paths, a concise commentary line, and a verification queue. Adapt wording to the requested audience while keeping the same evidence labels. Quality bar: a reader can use the text without treating an assumption as a current fact.

### Step 5: Run the honesty check

Remove invented current events, player qualities, statistics, substitutions, scores, and results. Confirm that the output says it is based on pasted input and does not frame analysis as a command or forecast. Quality bar: unknowns remain visible and the deliverable is self-contained text.

## Output Schema

```text
output_schema_version: "1.0.0"
match_label: string
evidence_boundary: { supplied: string[], unverified: string[] }
decision_card: { question: string, stated_objective: string, documented_constraints: string[], confidence: "low" | "medium" | "high" }
conditional_paths: { option: string, possible_effect: string, trade_off: string, changes_if: string }[]
commentary_line: string
verification_queue: string[]
capability_boundary: string
```

## Output Format

```markdown
# Football In-Match Change Brief: [team A] vs [team B] — [stated minute]

## Evidence boundary
- Supplied: [fact from pasted record]
- [UNVERIFIED]: [missing current fact]

## Decision card
- Question: [one stated question]
- Objective: [stated objective]
- Constraints: [supplied constraints]
- Confidence: [low | medium | high]

## Conditional paths
1. **If [option]:** Possible effect: [effect]. Trade-off: [trade-off]. Reassess if [fact].
2. **If [option]:** Possible effect: [effect]. Trade-off: [trade-off]. Reassess if [fact].

## Commentary line
[one conditional, audience-ready line]

## Verify before using
- [missing fact]

## Capability boundary
This is a text brief from buyer-pasted material; it does not access a match feed or predict a result.
```

## Error Handling

- **No stated minute or score:** Ask for the last known match state; do not assume the match is level or in a particular phase.
- **No decision question:** Ask the buyer to choose one personnel, role, or shape question before comparing options.
- **Options are unnamed or unavailable:** Use role labels only and mark the bench, fitness, and availability context `[UNVERIFIED]`.
- **Request for a certain result:** Reframe as conditional tactical effects and explain that the supplied record cannot establish an outcome.
- **Conflicting supplied notes:** Preserve both claims, identify the conflict, and lower confidence rather than resolve it from model knowledge.

## Examples

**Example 1: Protecting a narrow lead**

Input: At 68 minutes, Harbor Town lead Eastvale 1–0. Harbor's 4-3-3 is losing second balls after clearances. The buyer says a defensive midfielder is on the bench and asks whether to replace an attacking midfielder.

Decision: Compare the stated midfielder change with keeping the current shape; do not assume fitness, cards, or the opponent's bench.

Output excerpt: `If Harbor replaces the attacking midfielder with the stated defensive midfielder, the supplied second-ball problem could receive an extra central screen. Trade-off: the record does not establish how the new midfield balance affects Harbor's outlet.`

**Example 2: Chasing width**

Input: At 74 minutes, River Athletic trail Northbridge 0–1. River's supplied notes say the right side is congested and a wide player is available. The question is whether to change from a narrow front two to a wider shape.

Decision: Describe the width option and the continuity option as conditional paths; mark player roles beyond the notes `[UNVERIFIED]`.

Output excerpt: `If River adds the stated wide option, the supplied congestion note supports testing a wider starting position. Trade-off: no supplied defensive-transition evidence shows whether this leaves the opposite side exposed.`

## Flywheel Connections

### Feeds Into

- `football-postmatch-decision-review` (S2-Analysis) — the buyer can turn a completed, verified event log into a later review.
- `football-scoreline-scenario-card` (S2-Analysis) — verified state notes can support conditional scenario writing.

### Fed By

- `football-match-analyst` (S2-Analysis) — a pre-match brief can provide only buyer-verified context, not asserted current facts.
- Buyer-pasted match notes — the source of every current claim.

### Feedback Loop

Track which missing facts repeatedly block useful change cards, then improve the intake prompt to request those buyer-supplied facts earlier.

```yaml
chain_metadata:
  skill_slug: "football-in-match-change-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-31"
  suggested_next:
    - "football-postmatch-decision-review"
    - "football-scoreline-scenario-card"
```

## Quality Gate

1. The output identifies one supplied match state and one decision question.
2. Every current fact appears in the pasted input or carries `[UNVERIFIED]`.
3. The output compares at least two conditional paths when two options are supplied.
4. Every path includes a possible effect, a trade-off, and a reassessment trigger.
5. No outcome, score, availability, statistic, or player attribute is invented.
6. The commentary line is conditional and contains no command to a team.
7. The capability boundary says the deliverable is text from buyer-pasted material.

## References

- `evidence/verified-demonstration.md` — concrete input, actual output, and verification notes.
