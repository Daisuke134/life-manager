---
name: nfl-game-script-brief
description: >
  Turn buyer-pasted NFL injury-report designations, personnel-package notes, and situational tendencies into a source-bounded pregame game-script brief. Use when an NFL beat writer, fantasy football analyst, or podcast producer needs a disciplined pregame read of how a single supplied matchup is likely to be schemed and played, without claiming access to current injury, inactive, or odds information.
license: MIT
version: "1.0.0"
tags: [nfl, football, game-script, injury-report, fantasy-football, sports-writing]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# NFL Game Script Brief

NFL Game Script Brief turns the injury-report, personnel, and tendency notes a buyer already has into a traceable pregame read of how one supplied NFL matchup is likely to be played: which personnel packages and tempo each side leans on, how a questionable or doubtful designation could change the plan, and which situational tendencies (third down, red zone, two-minute) the supplied material supports. It keeps the recurring sports-analysis job focused on the buyer's own material and treats missing facts as unknown rather than filling them in from assumed roster or odds knowledge.

## Stage

This skill belongs to Stage S2: Analysis.

## When to Use

- An NFL beat writer has one upcoming week's injury report and personnel notes for a single matchup and needs a qualified pregame game-script angle.
- A fantasy football analyst wants a disciplined read of how supplied snap-count and personnel-package notes could affect usage, without being told it is a lineup guarantee.
- A podcast producer needs a short game-script rundown that separates supplied facts from conditional scenarios for a questionable or doubtful player.

## Input Schema

```text
game: string (required) — away team, home team, week number, and date/time if known
injury_report: string (required) — buyer-pasted designations (questionable, doubtful, out), practice participation notes, and any confirmed absences for either team
personnel_notes: string (required) — supplied personnel-package tendencies, snap-count splits, or depth-chart notes for either team
situational_notes: string (optional) — buyer-pasted pace, third-down, red-zone, or two-minute tendency notes
coverage_goal: string (optional) — article, podcast, fantasy-lineup memo, and desired length
```

## Workflow

### Step 1: Set the evidence boundary

Extract the named game, supplied injury designations, personnel/snap-count notes, and situational notes into a compact ledger. Mark every missing official-inactive confirmation, weather note, odds line, or practice-participation detail `[UNVERIFIED]`. The quality bar is that a reader can identify which facts came from the buyer without relying on assumed roster or injury knowledge.

### Step 2: Build the game-script read

Compare the supplied inputs across injury-designation certainty, personnel-package tendency, pace/tempo, situational efficiency, and evidence strength. For each axis, name the input that supports the interpretation and one limitation. The quality bar is a conditional game-script read, not a snap-count guarantee, a lineup promise, or a score prediction.

### Step 3: Write scenario cards

For each questionable or doubtful player, or each personnel note with an open question, produce an `if active` / `if inactive or limited` card stating only the supplied-evidence implication. The quality bar is that uncertain facts remain conditional and never become a start/sit or betting instruction.

### Step 4: Deliver the coverage package

Return a game-script comparison table, two or three evidence-bound coverage angles (article, podcast, or fantasy-usage framing), a verification queue, and a 45-second pregame rundown. The quality bar is a self-contained text package a writer, host, or fantasy analyst can adapt without confusing model knowledge with supplied current-week facts.

## Output Schema

```text
output_schema_version: "1.0.0"
game_label: string
evidence_boundary: string[]
game_script_comparison: { axis: string, supplied_fact: string, script_read: string, confidence: "low" | "medium" | "high", limitation: string }[]
scenario_cards: { condition: string, coverage_implication: string }[]
coverage_angles: { angle: string, supporting_input: string, caveat: string }[]
verification_queue: string[]
pregame_rundown: string
```

## Output Format

```markdown
# NFL Game Script Brief: [away] at [home] — Week [n]

## Evidence boundary
- Supplied: [fact]
- [UNVERIFIED]: [missing current fact]

## Game-script comparison
| Axis | Supplied fact | Read | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| [injury certainty/personnel/pace/situational] | [fact] | [evidence-bound interpretation] | [low/medium/high] | [gap] |

## Scenario cards
- If [condition]: [coverage implication].

## Coverage angles
1. [angle] — Evidence: [supplied material]. Caveat: [limitation].

## Verify before using
- [current fact to confirm]

## 45-second pregame rundown
[brief, source-bounded spoken summary]
```

## Error Handling

- **No individual game supplied:** Ask for one matchup before building a game-script read; do not convert a full week's slate into this product.
- **No injury report or personnel notes:** Build only a situational-tendency outline and mark injury/personnel rows `[UNVERIFIED]`; never name an active or inactive player.
- **Conflicting supplied injury designations:** Quote both claims in the evidence boundary and ask which note should control the revision.
- **Request for current inactives, weather, odds, or confirmed depth charts:** Explain that the skill assesses only the material pasted by the buyer and request the facts they want analyzed.
- **Request for a start/sit call, a betting pick, or a certain score:** Decline certainty framing and provide conditional coverage questions instead.

## Examples

### Example 1: Questionable receiver and pace note

**Input:** Harbor Hawks at Summit Stags, Week 7. Harbor's lead receiver is listed questionable after limited practice participation Thursday and Friday; no Saturday estimate is supplied. Summit's secondary has allowed a buyer-noted high per-play passing rate the last two games. Harbor's offense ran a buyer-noted no-huddle package on 18 of its last 60 offensive snaps. No official inactive list, weather, or odds are supplied.

**Decision:** Compare the supplied practice-participation trend and pace note, keep the receiver's status conditional, and avoid turning the secondary note into a guaranteed target share.

**Output excerpt:** `Injury certainty is low: the receiver is questionable with two limited practices and no final estimate. If active, the supplied no-huddle rate and Summit's per-play passing allowance make a pass-pace script the clearest angle; the two-game secondary sample is a limitation.`

### Example 2: Backup personnel usage

**Input:** River Rapids at Northbridge Stallions. River's starting running back is doubtful; the backup logged a buyer-noted 14 snaps in relief last week. Northbridge's run defense allowed a buyer-noted 4.8 yards per carry in its last game. No practice-report detail beyond the doubtful tag, weather, or depth-chart confirmation is supplied.

**Decision:** Write a conditional backup-usage scenario and place broader sample size and official confirmation in the verification queue.

**Output excerpt:** `If the doubtful tag becomes an inactive, the supplied 14-snap relief sample and Northbridge's 4.8 yards-per-carry allowance frame an opportunity-versus-evidence question, not a projected workload. Verify: final inactive list and a larger carry sample.`

## Flywheel Connections

### Feeds Into

- `sports-podcast-run-sheet` (S2-Content) — the pregame rundown can become a source-bounded host segment.
- `nhl-goalie-matchup-brief` (S2-Analysis) — buyers who use this evidence-bound comparison discipline for one sport can reuse the same structure for another.

### Fed By

- Buyer-maintained NFL injury reports, personnel/snap-count charts, and situational-tendency notes.
- A buyer's editorial or fantasy-content calendar identifying the individual game that needs a game-script preview.

### Feedback Loop

Buyers can report which supplied injury, personnel, and situational fields made the brief useful; use that feedback to refine the input checklist without adding claims of access to current NFL information.

```yaml
chain_metadata:
  skill_slug: "nfl-game-script-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-18"
  suggested_next:
    - "sports-podcast-run-sheet"
    - "nhl-goalie-matchup-brief"
```

## Quality Gate

1. The output identifies exactly one buyer-supplied NFL game.
2. Every injury, personnel, snap-count, and situational statement is traceable to the pasted input or labeled `[UNVERIFIED]`.
3. Each comparison row gives a supplied fact, interpretation, confidence label, and limitation.
4. Every questionable or doubtful designation produces a conditional scenario rather than a start/sit call.
5. The brief contains no wagering advice, certain score, lineup guarantee, or claim of access to current NFL information.
6. The verification queue contains only facts that would improve the next revision.

## References

- `LISTING.md` — buyer-facing offer, plans, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification record.
