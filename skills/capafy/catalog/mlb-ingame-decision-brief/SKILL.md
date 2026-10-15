---
name: mlb-ingame-decision-brief
description: >
  Turn a buyer-pasted MLB game state, bullpen availability notes, and decision context into an evidence-bounded in-game decision brief. Use when a baseball broadcaster, beat writer, or serious fan needs to frame the next decision without claiming access to a current game feed.
license: MIT
version: "1.0.0"
tags: [mlb, baseball, in-game-analysis, bullpen, sports-writing]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# MLB In-Game Decision Brief

Turn the game state that the buyer supplies into a disciplined decision brief for one moment in one baseball game. This is neither a pregame lineup preview, a multi-game series preview, nor a completed-game recap: its job is to distinguish documented game state from conditional decision paths while the buyer is preparing commentary or notes.

## When to Use

- A broadcaster or producer has a manually captured inning, score, base/out state, and bullpen notes and needs a concise decision segment.
- A beat writer wants to describe the options around a supplied pitching change, pinch-hitting choice, or intentional-walk question without inventing current facts.
- A serious fan wants a structured way to compare the supplied decision paths, limitations, and questions still to confirm.

## Input Schema

```text
game: string (required) — teams, date, and ballpark if the buyer supplies them
game_state: string (required) — inning, score, outs, runners, batter/pitcher, and current count if known
decision_context: string (required) — the manager choice or tactical question to assess
availability_notes: string (required) — buyer-pasted bullpen, bench, workload, handedness, or substitution notes
supporting_evidence: string (optional) — buyer-pasted splits, pitch counts, prior events, or stated constraints
coverage_goal: string (optional) — broadcast, article, podcast, or fan-discussion use
```

## Workflow

### Step 1: Set the evidence boundary

Extract the supplied score, inning, base/out state, personnel, and decision question. Quote conflicting supplied claims side by side. Mark a missing count, pitch total, availability fact, lineup spot, or rule detail `[UNVERIFIED]`; never supply one from assumed current knowledge.

### Step 2: Define the decision frame

State the decision the supplied context actually supports. Separate the documented constraints (for example, a reliever's recent usage) from an interpretation (for example, a possible workload concern). Do not turn a plausible interpretation into a report of the manager's intent.

### Step 3: Compare conditional paths

For up to three supplied options, describe a conditional upside, trade-off, and the fact that would change the read. These are analysis paths, not win probabilities, predictions, or wagering advice.

### Step 4: Deliver the moment brief

Return an evidence ledger, decision card, conditional paths, coverage wording, and verification queue. The brief must remain useful even when the buyer's record is incomplete: missing facts stay visible rather than being filled in.

## Output Schema

```text
output_schema_version: "1.0.0"
game_label: string
moment: string
evidence_boundary: string[]
decision_card: { question: string, documented_constraints: string[], interpretation: string, confidence: "low" | "medium" | "high", limitation: string }
conditional_paths: { path: string, potential_value: string, trade_off: string, changes_if: string }[]
coverage_lines: string[]
verification_queue: string[]
```

## Output Format

```markdown
# MLB In-Game Decision Brief: [away] at [home] — [moment]

## Evidence boundary
- Supplied: [fact]
- [UNVERIFIED]: [missing current fact]

## Decision card
- Question: [supplied choice]
- Documented constraints: [supplied facts]
- Read: [cautious interpretation]
- Confidence: [low/medium/high]
- Limitation: [what the input cannot establish]

## Conditional paths
1. **If [path]:** [potential value]. Trade-off: [trade-off]. This changes if [fact].

## Coverage line
[one source-bounded sentence for the buyer's broadcast or notes]

## Verify before using
- [fact to confirm]
```

## Error Handling

- **No moment or decision supplied:** Ask for one game state and one decision question; do not infer either from a team name.
- **No availability notes:** Describe only the stated decision and mark bullpen or bench implications `[UNVERIFIED]`.
- **Conflicting score or inning information:** Preserve both supplied versions in the evidence boundary and ask which record governs the revision.
- **Request for a current feed, score, odds, or roster update:** Explain that this skill evaluates only buyer-pasted material and ask the buyer to paste the record they want assessed.
- **Request for a certain outcome or wager:** Decline the certainty framing and offer conditional baseball questions instead.

## Examples

### Example: late-inning pitching choice

**Input:** Harbor leads Summit 4–3 in the eighth, one out, runner on first. The buyer says Summit's left-handed batter is due. Harbor's right-handed reliever has thrown 22 pitches over the past two days; its left-hander has not pitched in three days. The buyer asks whether the left-hander should enter now. No platoon split or current pitch count is supplied.

**Decision:** Treat workload and handedness as documented context, make the switch a conditional option, and leave current pitch count and splits in the verification queue.

**Output excerpt:** `If Harbor uses the left-hander now, the supplied three-day rest aligns with the stated left-handed matchup. Trade-off: no supplied split or current pitch count establishes that the move is preferred. Verify the current pitcher and bench options before using this as commentary.`

## Flywheel Connections

### Feeds Into

- `mlb-postgame-turning-point-brief` (S2-Analysis) — a buyer can use verified in-game notes as a later recap record.
- `sports-podcast-run-sheet` (S2-Content) — coverage lines can become a source-bounded segment prompt.

### Fed By

- Buyer-maintained score notes, inning logs, bullpen availability notes, and baseball-stat excerpts.

### Feedback Loop

Buyers can report which manually supplied fields make a decision card clearer; improve the input checklist without adding a claim of access to a current game feed.

```yaml
chain_metadata:
  skill_slug: "mlb-ingame-decision-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-16"
  suggested_next:
    - "mlb-postgame-turning-point-brief"
    - "sports-podcast-run-sheet"
```

## Quality Gate

1. The output identifies exactly one buyer-supplied game moment and decision question.
2. Every stated current-game fact is traceable to the input or labeled `[UNVERIFIED]`.
3. Each decision card names documented constraints, a cautious interpretation, a confidence label, and a limitation.
4. Every recommended path is conditional; the skill does not produce a probability, certain outcome, or wager.
5. The output has no claim of access to game feeds, scores, odds, lineups, or availability beyond what the buyer pastes.
6. The verification queue contains only facts that would materially change the next revision.

## References

- `LISTING.md` — buyer-facing offer, plans, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification record.
