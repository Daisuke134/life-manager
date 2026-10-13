---
name: nhl-goalie-matchup-brief
description: >
  Turn buyer-pasted NHL game notes, projected goalies, workload, and chance-quality observations into a source-bounded goalie matchup brief and coverage rundown. Use when a hockey writer, podcast producer, or serious fan needs a disciplined pregame goalie comparison without claiming access to current hockey information.
license: MIT
version: "1.0.0"
tags: [nhl, hockey, goalie, matchup-analysis, sports-writing]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# NHL Goalie Matchup Brief

NHL Goalie Matchup Brief turns the game notes a buyer already has into a traceable pregame comparison of the two supplied goaltending situations. It keeps the recurring sports-analysis job focused: explain how named starter status, rest, workload, team chance quality, and tactical context may shape coverage, while treating missing facts as unknown rather than filling them in.

## Stage

This skill belongs to Stage S2: Analysis.

## When to Use

- A hockey writer has one upcoming game's projected starters, rest notes, and team context and needs a qualified preview angle.
- A podcast producer needs a short goalie-focused rundown that distinguishes supplied facts from conditional scenarios.
- A serious fan wants to organize pasted save, workload, or chance-quality notes without treating unstated injury or starter information as confirmed.

## Input Schema

```text
game: string (required) — away team, home team, and date or game label
goalie_notes: string (required) — projected or confirmed starters, handedness if relevant, workload, rest, and availability notes supplied by the buyer
team_context: string (required) — supplied defensive, chance-quality, special-team, travel, or opponent-shot-profile observations
evidence_notes: string (optional) — buyer-pasted save percentages, shot totals, previous-game observations, or quoted reports
coverage_goal: string (optional) — article, podcast, fan discussion, and any angle to prioritize
```

## Workflow

### Step 1: Set the evidence boundary

Extract the named game, supplied goalie status, stated workload/rest facts, and team-context observations into a compact ledger. Mark every missing starter confirmation, injury detail, statistic, or schedule fact `[UNVERIFIED]`. The quality bar is that a reader can identify which facts came from the buyer without relying on assumed roster knowledge.

### Step 2: Build the goalie comparison

Compare the supplied inputs across starter certainty, rest/workload, defensive environment, opponent chance profile, and evidence strength. For each axis, name the input that supports the interpretation and one limitation. The quality bar is a conditional matchup read, not a prediction or a claim that either goalie will start.

### Step 3: Write scenario cards

For each tentative starter, availability issue, or incomplete note, produce an `if confirmed` / `if changed` card. State only the editorial implication of the supplied change. The quality bar is that uncertain facts remain conditional and never become a forecast.

### Step 4: Deliver the coverage package

Return a comparison table, two or three evidence-bound story angles, a verification queue, and a 45-second pregame rundown. The quality bar is a self-contained text package that a writer or host can adapt without confusing model knowledge with supplied current-game facts.

## Output Schema

```text
output_schema_version: "1.0.0"
game_label: string
evidence_boundary: string[]
goalie_comparison: { axis: string, supplied_fact: string, matchup_read: string, confidence: "low" | "medium" | "high", limitation: string }[]
scenario_cards: { condition: string, coverage_implication: string }[]
coverage_angles: { angle: string, supporting_input: string, caveat: string }[]
verification_queue: string[]
pregame_rundown: string
```

## Output Format

```markdown
# NHL Goalie Matchup Brief: [away] at [home] — [date]

## Evidence boundary
- Supplied: [fact]
- [UNVERIFIED]: [missing current fact]

## Goalie comparison
| Axis | Supplied fact | Read | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| [starter certainty/rest/defense/chance profile] | [fact] | [evidence-bound interpretation] | [low/medium/high] | [gap] |

## Scenario cards
- If [condition]: [coverage implication].

## Coverage angles
1. [angle] — Evidence: [supplied material]. Caveat: [limitation].

## Verify before using
- [current fact the buyer should confirm]

## 45-second pregame rundown
[brief, source-bounded spoken summary]
```

## Error Handling

- **No individual game supplied:** Ask for one matchup before making a goalie comparison; do not convert a whole week's schedule into this product.
- **No goalie status or workload notes:** Build only a team-context outline and mark starter-related rows `[UNVERIFIED]`; never nominate a starter.
- **Conflicting supplied goalie information:** Quote both claims in the evidence boundary and ask which note should control the revision.
- **Request for current scores, odds, standings, or injury status:** Explain that the skill assesses only the material pasted by the buyer and request the facts they want analyzed.
- **Request for a wager or certain result:** Decline certainty framing and provide conditional coverage questions instead.

## Examples

### Example 1: Rest and defensive-context preview

**Input:** Harbor Orcas at Summit Owls. Harbor projects Hale, who stopped 31 shots two nights ago; Summit projects Varga after three days off. Buyer notes that Summit limited opponents to 20 shots in its last game, while Harbor allowed 14 slot chances. Confirmed starter status is not supplied.

**Decision:** Compare the stated rest and defensive-context notes, mark both starters unconfirmed, and avoid turning the slot-chance note into an outcome claim.

**Output excerpt:** `Starter certainty is low: Hale and Varga are projections in the supplied notes. If confirmed, Varga's stated three-day rest and Summit's 20-shot defensive result make workload management a supported coverage angle; the one-game defensive note is a limitation.`

### Example 2: Tentative starter change

**Input:** River Blades at Northbridge Forge. River's usual starter is questionable; the possible replacement faced 18 shots in a relief appearance. Northbridge's buyer-pasted notes say its first unit generated six slot attempts last game. No travel or save percentage information is supplied.

**Decision:** Write a conditional replacement scenario and put travel and longer-run performance evidence in the verification queue.

**Output excerpt:** `If the replacement starts, the supplied relief appearance and six recent slot attempts frame an opportunity-versus-evidence question, not a projected result. Verify: starter confirmation, travel context, and a comparable workload sample.`

## Flywheel Connections

### Feeds Into

- `sports-podcast-run-sheet` (S2-Content) — the pregame rundown can become a source-bounded host segment.
- `football-match-analyst` (S2-Analysis) — buyers who use structured event analysis can reuse the evidence-bound comparison discipline for another sport.

### Fed By

- Buyer-maintained NHL game notes, goalie reports, and hockey-stat excerpts.
- A buyer's editorial calendar identifying the individual game that needs a goalie-focused preview.

### Feedback Loop

Buyers can report which supplied goalie, workload, and chance-context fields made the brief useful; use that feedback to refine the input checklist without adding claims of access to current hockey information.

```yaml
chain_metadata:
  skill_slug: "nhl-goalie-matchup-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-14"
  suggested_next:
    - "sports-podcast-run-sheet"
    - "football-match-analyst"
```

## Quality Gate

1. The output identifies exactly one buyer-supplied NHL game.
2. Every starter, workload, availability, and statistic statement is traceable to the pasted input or labeled `[UNVERIFIED]`.
3. Each comparison row gives a supplied fact, interpretation, confidence label, and limitation.
4. Every tentative starter produces a conditional scenario rather than a prediction.
5. The brief contains no wagering advice, certain game result, or claim of access to current hockey information.
6. The verification queue contains only facts that would improve the next revision.

## References

- `LISTING.md` — buyer-facing offer, plans, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification record.
