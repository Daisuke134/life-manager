---
name: mlb-lineup-matchup-brief
description: >
  Turn buyer-pasted single-game MLB lineups, starter notes, and matchup splits into an evidence-bound lineup matchup card and editorial angle list. Use when a baseball writer, podcast producer, or serious fan needs to compare today's supplied game notes without claiming live data.
license: MIT
version: "1.0.0"
tags: [mlb, baseball, lineup, matchup-analysis, sports-writing]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# MLB Lineup Matchup Brief

MLB Lineup Matchup Brief turns the single-game baseball material a buyer already has into a traceable lineup-versus-starter card. It is deliberately narrower than a series preview: the recurring job is deciding which individual batter, handedness, lineup-order, and availability questions deserve coverage for one supplied game.

## When to Use

- A baseball writer has probable lineups, starter notes, and a few supplied splits for one game and needs a focused preview angle.
- A podcast producer needs a reliable pregame rundown that keeps confirmed notes separate from assumptions.
- A fan wants to compare a pasted lineup against the opposing starter without treating missing current information as fact.

## Input Schema

```text
game: string (required) — away team, home team, date, and ballpark if supplied
lineups: string (required) — batting order, handedness, and availability notes as supplied
starters: string (required) — each probable starter plus supplied pitch, workload, or split notes
matchup_evidence: string (optional) — buyer-pasted batter/pitcher splits, park notes, or recent observations
coverage_goal: string (optional) — article, podcast, fan discussion, and any player or angle to prioritize
```

## Workflow

### Step 1: Build an evidence ledger

Extract the supplied game facts, lineup slots, handedness, starter information, and stated availability. Label any absent current lineup, starter, split, weather, or ballpark fact `[UNVERIFIED]`. Do not replace it with assumed roster knowledge.

### Step 2: Create the matchup map

For each supplied lineup, identify up to three evidence-backed batter-versus-starter or handedness questions. Explain the connection using the buyer's supplied notes. A useful card names both the supporting evidence and the limitation; it never invents a split or declares an edge certain.

### Step 3: Separate conditional changes

For every tentative player, probable starter, or incomplete lineup supplied by the buyer, write an `if confirmed` / `if changed` consequence. Keep these as conditional editorial scenarios, not forecasts.

### Step 4: Produce the single-game brief

Return the matchup card, three coverage angles, a verification queue, and a short broadcast-ready rundown. The quality bar is a self-contained text brief in which every current-game statement is traceable to the input or marked `[UNVERIFIED]`.

## Output Schema

```text
output_schema_version: "1.0.0"
game_label: string
evidence_boundary: string[]
lineup_matchup_cards: { lineup_slot: string, supplied_fact: string, matchup_read: string, confidence: "low" | "medium" | "high", limitation: string }[]
coverage_angles: { angle: string, supporting_input: string, caveat: string }[]
conditional_scenarios: { condition: string, implication: string }[]
verification_queue: string[]
pregame_rundown: string
```

## Output Format

```markdown
# MLB Lineup Matchup Brief: [away] at [home] — [date]

## Evidence boundary
- Supplied: [fact]
- [UNVERIFIED]: [missing current fact]

## Lineup matchup cards
| Lineup slot | Supplied matchup fact | Read | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| [player / slot] | [fact] | [evidence-bound interpretation] | [low/medium/high] | [gap] |

## Coverage angles
1. [angle] — Evidence: [supplied material]. Caveat: [limitation].

## If the lineup changes
- If [condition]: [conditional implication].

## Verify before using
- [current fact the buyer should confirm]

## 45-second pregame rundown
[brief, source-bounded spoken summary]
```

## Error Handling

- **No single game supplied:** Ask for one matchup before making cards; do not combine an entire series into this product.
- **No lineup or handedness notes:** Return a starter-focused outline and mark lineup matchup cards `[UNVERIFIED]` rather than filling a batting order.
- **Conflicting supplied information:** Quote both claims in the evidence boundary and ask the buyer which should govern the brief.
- **Request for live scores, odds, or injury status:** Explain that the skill uses only pasted information and ask the buyer to provide the facts they want assessed.
- **Request for a wager or certain outcome:** Decline the certainty framing and provide conditional baseball-analysis questions instead.

## Examples

### Example 1: Handedness-focused preview

**Input:** Away: Harbor Sailors at Summit Foxes. Harbor's first four are R, L, R, L. Summit starts left-hander Lund; buyer notes that Harbor's third hitter has a supplied .910 OPS against left-handed pitching this season. Summit's closer availability is unknown.

**Decision:** Make the third hitter a supported coverage angle, preserve the lineup handedness as supplied, and do not claim the closer is available.

**Output excerpt:** `3rd slot — the supplied .910 OPS versus left-handed pitching makes this the clearest lineup-vs-starter question; confidence medium because the sample size and current lineup confirmation were not supplied.`

### Example 2: Tentative lineup

**Input:** River Athletic at Northbridge. River's leadoff hitter is listed as day-to-day; Northbridge starts a right-hander with a supplied high fastball rate. The buyer supplied no River replacement or weather note.

**Decision:** Produce two conditional lead-off scenarios and put replacement identity and weather in the verification queue.

**Output excerpt:** `If the listed leadoff hitter starts, the supplied high-fastball note is the opening matchup question. If absent, the replacement and batting-order effect are [UNVERIFIED].`

## Flywheel Connections

### Feeds Into

- `mlb-series-preview-brief` (S2-Analysis) — a buyer can roll verified single-game cards into a later series-level record.
- `sports-podcast-run-sheet` (S2-Content) — the pregame rundown can become a host's source-bounded segment.

### Fed By

- Buyer-maintained lineup notes, starter notes, and baseball stat excerpts.
- `mlb-series-preview-brief` (S2-Analysis) — a series brief can identify the game that deserves closer lineup treatment.

### Feedback Loop

Buyers can report which supplied fields made the cards most useful; use that feedback to improve the input checklist without adding claims of access to current baseball data.

```yaml
chain_metadata:
  skill_slug: "mlb-lineup-matchup-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-12"
  suggested_next:
    - "mlb-series-preview-brief"
    - "sports-podcast-run-sheet"
```

## Quality Gate

1. The output identifies exactly one buyer-supplied game.
2. Every current lineup, starter, split, and availability statement is traceable to the pasted input or labeled `[UNVERIFIED]`.
3. Each matchup card gives evidence, an interpretation, a confidence label, and a limitation.
4. Every tentative-player result is conditional, not a prediction.
5. The brief has no odds, wagering instruction, certain game outcome, or live-data claim.
6. The verification queue contains only facts needed to improve the next revision.

## References

- `LISTING.md` — buyer-facing offer, plans, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification record.
