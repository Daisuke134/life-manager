---
name: football-opposition-training-brief
description: >
  Turn buyer-pasted opposition observations and own-squad training constraints into a focused football training brief.
  Use when a coach needs an evidence-bounded microcycle, role messages, and confirmation questions without claiming current match data.
license: MIT
version: "1.0.0"
tags: [football, coaching, opposition-analysis, training, match-preparation]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# Football Opposition Training Brief

Turn a coach's own opposition notes into a short, teachable training microcycle. The workflow separates supplied observations from coaching proposals, then produces a threat ledger, session sequence, role messages, and confirmation queue. It is distinct from a fixture prediction, scoreline scenario, post-match review, or set-piece-only plan.

## Stage

This skill belongs to Stage S2: Analysis.

## When to Use

- An academy coach has three or four buyer-maintained notes about an opponent and needs two focused sessions before a fixture.
- A first-team analyst needs to turn pasted tactical observations and own-squad constraints into coach-facing training priorities.
- A coaching staff wants proposed role messages tied to supplied evidence rather than a generic opponent report.
- A buyer needs unknown personnel, formations, and routines visibly separated from the material they supplied.

## Input Schema

```text
fixture_label: string (required) — buyer's label for the preparation period; teams and date only if supplied
opposition_observations: string (required) — buyer-pasted tactical observations, sequences, or notes
own_squad_constraints: string (required) — buyer-pasted availability, development, time, or tactical constraints
training_window: string (required) — number and duration of available sessions
coaching_objective: string (required) — the outcome the staff wants to rehearse
age_group_or_level: string (optional) — supplied player level, used only to calibrate language and load
evidence_limits: string (optional) — disputed, incomplete, or excluded information
```

## Workflow

### Step 1: Establish the evidence boundary

Extract only the observations, constraints, and objective the buyer provides. Label absent current formations, personnel, fitness, and routine details `[UNVERIFIED]`. Good output does not import a current lineup, statistic, tactic, or opponent fact that the buyer did not paste.

### Step 2: Build a training threat ledger

Separate supplied observations from interpretations. Convert no more than three supplied observations into training-relevant threats, each with a quoted or faithful basis, an intended coaching response, and a limitation. Good output names a pattern only when the buyer supplied it and avoids treating an isolated note as a certainty.

### Step 3: Sequence the microcycle

Use the supplied time window to make a progression from recognition, to rehearsal, to decision-making. Each session includes an objective, constrained practice, coaching cues, and an observable check. Good output keeps every drill a proposed response to a supplied observation rather than claiming it will neutralize an opponent.

### Step 4: Write role messages and contingencies

Give functional role messages rather than ungrounded named-player assignments. Add conditional adjustments for at most three changeable conditions, each tied to an input fact and a confirmation need. Good output treats missing availability and opponent variation as questions to settle, not facts.

### Step 5: Deliver the coach-facing brief

Return the evidence boundary, threat ledger, session plan, role messages, and confirmation queue. If the evidence is sparse, reduce specificity and ask for the most decision-relevant observation rather than inventing a plan.

## Output Schema

```text
output_schema_version: "1.0.0"
fixture_label: string
evidence_boundary: { supplied: string[], unverified: string[] }
training_threats: { threat: string, supplied_basis: string, coaching_response: string, limitation: string }[]
microcycle: { session: string, objective: string, practice: string, coaching_cues: string[], observable_check: string }[]
role_messages: { functional_role: string, message: string, basis: string }[]
contingencies: { condition: string, adjustment: string, supplied_basis: string, confirm_before_use: string }[]
confirmation_queue: string[]
```

## Output Format

```markdown
# Football Opposition Training Brief: [fixture label]

## Evidence boundary
- Supplied: [buyer-pasted observation]
- [UNVERIFIED]: [missing current fact]

## Training threat ledger
| Training threat | Supplied basis | Proposed coaching response | Limitation |
| --- | --- | --- | --- |
| [threat] | [input fact] | [rehearsal focus] | [gap] |

## Session progression
1. **[session]:** [objective]. Practice: [constrained practice]. Cues: [cue]. Check: [observable check].

## Proposed role messages
| Functional role | Message | Basis |
| --- | --- | --- |
| [role] | [short instruction] | [supplied fact] |

## Conditional adjustments
1. **If [condition]:** [adjustment]. Basis: [input]. Confirm: [fact].

## Confirm before use
- [question]
```

## Error Handling

- **No usable opposition observation:** Ask for one buyer-observed sequence or tactical tendency and one own-team constraint; do not substitute general football assumptions.
- **Training window is missing:** Offer a single recognition-and-rehearsal block, label its duration `[ADD: session length]`, and ask the buyer to provide available time.
- **Named-player assignments are incomplete:** Use functional roles and place final assignments in the confirmation queue.
- **Observations conflict:** Preserve both buyer-pasted observations and offer conditional branches instead of selecting an unsupported version.
- **Request for current lineups, results, statistics, or a certain outcome:** Explain that the brief reasons from buyer-pasted material only, then identify what the buyer can confirm from their own record.

## Examples

### Example 1: Wide overload preparation

**Input:** Opposition note: “Vale repeatedly created a wide overload before cutting the ball back from the right.” Own constraint: “Our left-sided defender is returning from a short absence; two 35-minute sessions are available.”

**Decision:** Treat the overload and cutback as supplied observations, use a two-session progression, and avoid claiming Vale will repeat the pattern.

**Output excerpt:** `Rehearse a wide-delay role and a cutback-screen role. The supplied note supports the focus, but Vale's current personnel and repetition of the sequence are [UNVERIFIED].`

### Example 2: Sparse transition notes

**Input:** Opposition note: “They pushed both full-backs high in one buyer-noted sequence.” Own constraint: “The squad needs a low-load session.”

**Decision:** Build a low-load recognition practice and a conditional outlet message; do not call the observation a stable tactic.

**Output excerpt:** `Use a walk-through to recognise space behind the supplied high full-back sequence. Keep the outlet role conditional because one noted sequence does not establish a permanent structure.`

## Flywheel Connections

### Feeds Into

- `football-match-analyst` (S2-Analysis) — buyer-maintained fixture notes can inform a separate broad comparison.
- `football-postmatch-decision-review` (S6-Analytics) — a completed-match review can test which confirmation questions were useful.

### Fed By

- Buyer-maintained opposition observations, training constraints, and coaching objectives.
- `football-postmatch-decision-review` (S6-Analytics) — a source-bounded review may reveal a training question for the next preparation period.

### Feedback Loop

After training or the fixture, buyers can compare their own observations with the confirmation queue and improve the next notes they paste, without turning an unconfirmed pattern into a current fact.

```yaml
chain_metadata:
  skill_slug: "football-opposition-training-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-27"
  suggested_next:
    - "football-match-analyst"
    - "football-postmatch-decision-review"
```

## Quality Gate

1. The output identifies a buyer-supplied training window and coaching objective.
2. Every threat cites supplied material and states a limitation.
3. Every session includes an objective, practice, cue, and observable check.
4. Role messages use functional roles and cite a supplied basis.
5. Every contingency is conditional and states what needs confirmation.
6. Unknown formations, personnel, availability, routines, and statistics are `[UNVERIFIED]` rather than inferred.
7. The output contains no result prediction, wager recommendation, medical judgment, or assertion of current football data.

## References

- `LISTING.md` — buyer-facing offer, pricing, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification record.
