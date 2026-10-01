---
name: nba-slate-analyst
description: >
  Turns buyer-pasted NBA game-slate notes into a transparent matchup brief with
  availability scenarios and an uncertainty ledger. It uses supplied material
  only; it does not retrieve live scores, odds, standings, or injury reports.
license: MIT
version: "1.0.0"
tags: [nba, basketball, game-slate, matchup-analysis, availability]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# NBA Slate Analyst

NBA Slate Analyst converts the game slate and context the buyer pastes into a
consistent, text-only basketball briefing. It keeps supplied evidence, cautious
inference, and unknowns separate, so the result is useful without pretending to
know the current NBA state.

## When to Use

- A basketball writer is preparing a preview from supplied matchup notes.
- A fan has a slate, availability notes, and recent-game observations to compare.
- A producer needs a repeatable game-brief structure for each new slate.

## Input Schema

```text
slate_date: string (required)
games: string (required) — matchup, home team, away team, and supplied notes for each game
availability_notes: string (required) — confirmed, doubtful, or absent players as supplied
recent_evidence: string (optional) — pasted observations, stats, or schedule context
constraints: string (optional) — coverage angle, teams to prioritize, or language limits
```

## Workflow

### Step 1: Build the supplied-evidence ledger

List each matchup, player-status statement, schedule fact, statistic, and stated
constraint. Label absent information `[UNVERIFIED]`. Do not substitute model
knowledge for a current roster, result, injury, or schedule fact.

### Step 2: Score six analysis axes

For each supplied game, assess: home context, availability, rest or travel,
recent supplied evidence, style matchup, and uncertainty. State the evidence
behind every axis and leave an axis unresolved when the buyer did not provide it.

### Step 3: Write availability scenarios

For every doubtful or missing player supplied by the buyer, give an "if active"
and "if unavailable" reading. These are conditional basketball interpretations,
not predictions or medical reporting.

### Step 4: Package the slate brief

Return a compact slate table, a short matchup brief for each game, a ranked
watch list only when the supplied evidence supports comparison, and the missing
facts the buyer could add next time.

## Output Format

```markdown
# NBA Slate Brief: [slate date]
## Evidence boundary
- Supplied: [fact]
- Unverified: [missing fact]
## Slate table
| Game | Supplied edge | Uncertainty | Evidence |
| --- | --- | --- | --- |
## Matchup briefs
### [Away] at [Home]
- Six-axis read: [evidence-bound analysis]
- If active / if unavailable: [conditional scenarios]
## Watch list
1. [game] — [reason grounded in supplied material]
## Add next time
- [missing input]
```

## Error Handling

- **No game slate:** ask for the date and at least one matchup before analysis.
- **No availability notes:** mark availability `[UNVERIFIED]`; do not infer status.
- **Conflicting supplied facts:** surface both statements and request a correction.
- **Betting request:** explain that the output is an evidence-bound game brief,
  not wagering advice or a certain prediction.

## Quality Gate

1. The slate date, matchups, and availability input are present.
2. Every current basketball fact is traceable to the buyer's pasted material.
3. Each game covers the six fixed axes or marks the absent axis `[UNVERIFIED]`.
4. Every doubtful-player reading is conditional.
5. The output has no live-data, betting, certainty, or performance claim.
6. The final section identifies missing facts rather than inventing them.

## References

- `LISTING.md` — buyer-facing offer and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and checks.
