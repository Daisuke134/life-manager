---
name: mlb-postgame-turning-point-brief
description: >
  Turn buyer-pasted completed MLB game notes, inning events, and manager decisions into an evidence-bounded postgame turning-point brief. Use when a baseball writer, podcast host, or serious fan needs a disciplined recap without claiming access to current scores or video.
license: MIT
version: "1.0.0"
tags: [mlb, baseball, postgame-analysis, turning-points, sports-writing]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# MLB Postgame Turning-Point Brief

MLB Postgame Turning-Point Brief turns a completed game's buyer-pasted event log and notes into a traceable explanation of how the game changed. It is deliberately a postgame product: unlike the catalog's MLB lineup matchup and series preview skills, it begins after the final out and produces a recap structure, turning-point analysis, and follow-up questions rather than a preview.

## Stage

This skill belongs to Stage S2: Analysis.

## When to Use

- A beat writer has a completed game's inning notes and needs a defensible recap angle before drafting a story.
- A podcast host needs a concise postgame rundown that separates supplied events from interpretation.
- A fan-site editor wants to identify which supplied sequence changed momentum without inventing a box-score fact.
- A baseball creator has manager-decision and leverage notes and needs follow-up questions for a postgame discussion.

## Input Schema

```text
game: string (required) — teams, date or game label, and final score if supplied
inning_log: string (required) — buyer-pasted scoring plays, outs, pitching changes, and major defensive events
game_notes: string (required) — supplied context such as manager decisions, player availability, or quoted observations
statistics: string (optional) — buyer-pasted totals, splits, leverage notes, or box-score excerpts
editorial_goal: string (optional) — recap, podcast, fan discussion, desired angle, or word limit
```

## Workflow

### Step 1: Set an evidence boundary

Extract only the completed-game facts supplied by the buyer: score, event order, named players, decisions, and statistics. Mark a missing inning, score state, rationale, statistic, quote, or official ruling `[UNVERIFIED]`. The quality bar is that every current-game statement can be located in the pasted record.

### Step 2: Build the game-change timeline

Order material events chronologically and record the supplied before/after situation when available. Identify up to three candidate turning points only where the input provides an event and a plausible game-state change. The quality bar is a timeline that never fills missing plays or assumes a manager's intent.

### Step 3: Analyze turning points conditionally

For each candidate, state the supplied evidence, why it may have changed the game's shape, one limitation, and a question that would strengthen or challenge the read. Distinguish a documented event from an editorial interpretation. The quality bar is useful analysis without declaring a single cause of the result.

### Step 4: Package the postgame brief

Return a recap lead, event timeline, two or three turning-point cards, a manager-decision section, and a verification queue. Adapt the tone to the stated editorial goal. The quality bar is a self-contained text brief that a buyer can verify against their own record before publication.

## Output Schema

```text
output_schema_version: "1.0.0"
game_label: string
evidence_boundary: string[]
recap_lead: string
event_timeline: { sequence: number, supplied_event: string, stated_game_state: string, evidence_status: "supplied" | "unverified" }[]
turning_point_cards: { event: string, supplied_basis: string, interpretation: string, limitation: string, verification_question: string }[]
manager_decision_read: { supplied_decision: string, context: string, bounded_read: string, unknowns: string[] }[]
podcast_rundown: string
verification_queue: string[]
```

## Output Format

```markdown
# MLB Postgame Turning-Point Brief: [away] at [home] — [date]

## Evidence boundary
- Supplied: [fact]
- [UNVERIFIED]: [missing detail]

## Recap lead
[two-to-three sentence, evidence-bound recap]

## Game-change timeline
| Sequence | Supplied event | Stated game state | Status |
| --- | --- | --- | --- |
| [number] | [event] | [before/after state or not supplied] | [supplied/unverified] |

## Turning-point cards
### [event label]
- Supplied basis: [input]
- Read: [bounded interpretation]
- Limitation: [gap]
- Verify: [question]

## Manager-decision read
- [decision] — [what the supplied record supports]; unknown: [gap].

## 45-second postgame rundown
[spoken recap]

## Verify before publishing
- [item]
```

## Error Handling

- **No completed game record:** Ask for a final score or event sequence; do not turn a future fixture into a postgame recap.
- **Only a final score is supplied:** Return a minimal recap shell and mark turning points `[UNVERIFIED]`; never invent the decisive play.
- **Conflicting event order:** Preserve both supplied versions, flag the conflict, and ask which record governs before ranking an event.
- **Requested video, live score, or box-score lookup:** Explain that the skill analyzes only buyer-pasted material and ask the buyer to paste the relevant facts.
- **Request for a certain cause or wager:** Reframe the answer as an evidence-bounded interpretation and identify the missing confirmation.

## Examples

### Example 1: Late-inning comeback

**Input:** `Harbor 4, Summit 3. Harbor trailed 3–1 entering the eighth. In the eighth, Summit's reliever walked the first two hitters; a double tied the game. Harbor scored the go-ahead run on a sacrifice fly in the ninth. Buyer notes say Summit's closer had pitched the prior two days; no pitch counts or postgame quotes supplied.`

**Decision:** Treat the two walks and tying double as a supported turning-point sequence, but do not state why the reliever struggled or why the closer was unavailable.

**Output excerpt:** `The eighth-inning walk-double sequence is the clearest supplied inflection point: it erased a two-run deficit. The closer's recent usage is context, not proof of a decision rationale; verify availability and pitch counts before attributing the choice.`

### Example 2: Early manager decision

**Input:** `River 6, Northbridge 2. River removed its starter after four innings and 78 pitches with a 2–1 lead. The buyer's log records a two-run fifth after the first reliever entered. No injury note, matchup split, or manager quote is supplied.`

**Decision:** Place the pitching change on the timeline and make its consequence conditional rather than calling it a mistake.

**Output excerpt:** `The supplied record shows the lead changed after the early pitching change, but it does not establish why the starter exited or whether the change caused the fifth-inning sequence. Verify the manager's explanation and the inning's baserunner detail.`

## Flywheel Connections

### Feeds Into

- `sports-podcast-run-sheet` (S2-Content) — the verified recap can become a postgame segment.
- `social-post-writer` (S5-Distribution) — the recap lead and supplied turning point can inform a buyer-reviewed post.

### Fed By

- Buyer-maintained scorebooks, inning logs, press notes, and box-score excerpts.
- The buyer's published-game editorial assignment and verification record.

### Feedback Loop

Buyers can report which supplied fields made a turning point clear or left it uncertain; use that feedback to refine the input checklist without adding claims of score, video, or statistical access.

```yaml
chain_metadata:
  skill_slug: "mlb-postgame-turning-point-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-15"
  suggested_next:
    - "sports-podcast-run-sheet"
    - "social-post-writer"
```

## Quality Gate

1. The input describes a completed game, not an upcoming fixture.
2. Every event, score state, player, and statistic in the brief is supplied or marked `[UNVERIFIED]`.
3. The output contains no more than three turning-point cards, each with a limitation and verification question.
4. A manager decision is described only from supplied context; unstated rationale remains unknown.
5. The recap lead, timeline, and rundown are text-only and do not claim access to video, live scores, or box scores.
6. No outcome, causal conclusion, or wagering claim is presented as certain.

## References

- `LISTING.md` — buyer-facing offer, pricing, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification notes.
