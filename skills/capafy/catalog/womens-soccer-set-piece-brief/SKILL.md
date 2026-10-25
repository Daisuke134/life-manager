---
name: womens-soccer-set-piece-brief
description: >
  Turn buyer-supplied women's soccer set-piece notes for one upcoming match into
  an evidence-bound matchup brief, coverage angles, and a verification queue.
license: MIT
version: "1.0.0"
tags: [women-soccer, football, set-pieces, matchup-analysis, sports-writing]
compatibility: "Capafy run_online"
metadata:
  author: life-manager
  stage: analysis
  tools_needed: []
---

# Women's Soccer Set-Piece Brief

This skill converts a buyer's pasted set-piece evidence for one upcoming women's soccer match into a clear, source-bounded text brief. It separates supplied facts from interpretation and marks missing confirmation instead of filling gaps with invented match information.

## When to Use

- A women's soccer writer needs a pre-match set-piece angle from notes already gathered.
- A podcast producer wants a concise corner and free-kick matchup rundown.
- A fan-site editor has team-news and set-piece observations but needs them organized for one match.

## Input Schema

```text
match: string (required) — the two teams and match context
attacking_set_piece_notes: string (required) — supplied corner, free-kick, or throw-in observations
defensive_set_piece_notes: string (required) — supplied defending observations
availability_or_roles: string (optional) — confirmed or tentative takers, targets, markers, goalkeeper notes
editorial_priority: string (optional) — article, podcast, or fan-discussion focus
```

## Workflow

### 1. Extract only supplied evidence

List each note by team and label it as a fact, a stated uncertainty, or an interpretation request. Do not add results, lineups, standings, statistics, or injuries not present in the input.

### 2. Build the set-piece matchup card

Compare attacking delivery, target or runner notes, defensive assignment notes, goalkeeper context, and restarts only when the buyer supplied relevant evidence. State the strongest supported matchup question and its confidence.

### 3. Write conditional scenarios

For every tentative taker, target, marker, or goalkeeper, write an explicit if/then scenario. Keep a supplied uncertainty unresolved rather than assuming confirmation.

### 4. Produce coverage-ready output

Return the matchup card, two or three qualified coverage angles, a short spoken rundown, and a verification queue. The quality bar is that each conclusion traces to a pasted note and each unknown is visible.

## Output Schema

```text
output_schema_version: "1.0.0"
set_piece_matchup_card: string
confidence: "low" | "medium" | "high"
coverage_angles: string[]
spoken_rundown: string
conditional_scenarios: string[]
verification_queue: string[]
```

## Output Format

```markdown
## [Team A] vs [Team B] — Set-Piece Brief

### Supplied matchup card
- [attack versus defense comparison]
- [taker/target/marker or goalkeeper context]
- Confidence: [low|medium|high] — [why]

### Coverage angles
1. [evidence-bound angle]
2. [evidence-bound angle]

### Conditional scenarios
- If [unconfirmed role], then [limited implication].

### Spoken rundown
[two or three sentences]

### Verify before use
- [missing fact]
```

## Error Handling

- **No opponent identified:** Ask for both teams before comparing a matchup.
- **Only one side has notes:** Produce a one-team observation card and label the comparison incomplete.
- **Tentative roles presented as facts:** Move them into conditional scenarios and the verification queue.
- **Request for a prediction or wager:** Decline the certainty claim and provide only evidence-bound matchup questions.

## Examples

**Example 1: Corner matchup**

Input: Harbor Women use inswinging corners to a near-post runner; Summit Women have conceded two supplied near-post headers in their last three noted matches; Harbor's usual taker is doubtful.

Output excerpt: "The near-post run is the clearest supplied matchup question, but confidence is medium because Harbor's normal taker is doubtful. If the taker is unavailable, verify the replacement delivery profile."

**Example 2: Free-kick context**

Input: North City Women list a left-footed direct free-kick taker; River Women use a four-player wall in the supplied notes; River's goalkeeper status is unconfirmed.

Output excerpt: "The supplied left-footed delivery and four-player wall create a direct-free-kick angle, not a goal expectation. Verify the goalkeeper and final taker before publication."

## Quality Gate

1. Names both teams and the one supplied match.
2. Contains no unprovided score, schedule, lineup, odds, injury, or statistic.
3. Separates supplied facts, interpretations, and unknowns.
4. Includes at least one conditional scenario when a role is tentative.
5. Includes a verification queue.
6. Does not promise a result or place a wager.
