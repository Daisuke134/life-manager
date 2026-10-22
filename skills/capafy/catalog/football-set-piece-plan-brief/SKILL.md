---
name: football-set-piece-plan-brief
description: >
  Turn buyer-pasted football set-piece notes and squad constraints into an evidence-bounded rehearsal plan, role checklist, and confirmation queue. Use when a coach or set-piece analyst needs a text-only dead-ball preparation brief without claiming current football data.
license: MIT
version: "1.0.0"
tags: [football, set-pieces, coaching, opposition-analysis, match-preparation]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# Football Set-Piece Plan Brief

Turn a coach's or analyst's own dead-ball notes into a disciplined rehearsal brief. It is deliberately narrower than a fixture preview, scoreline scenario, or post-match review: it turns a supplied restart pattern and squad constraints into roles, communication calls, contingencies, and questions to settle before training.

## Stage

This skill belongs to Stage S2: Analysis.

## When to Use

- A coach has pasted notes about an opponent's corner routine and needs a defensive rehearsal sequence for the next training session.
- A set-piece analyst needs to convert their own free-kick observations and availability constraints into an attack or defence role checklist.
- An academy coach wants to make unknown takers, personnel, and intended assignments explicit rather than treating them as established facts.
- A video analyst needs a text brief from notes they already maintain, without asserting access to a match feed, roster, or statistics.

## Input Schema

```text
planning_context: string (required) — fixture label, team labels, and coaching objective only when supplied
restart_type: "corner" | "wide free kick" | "central free kick" | "throw-in" | "penalty" | "mixed" (required)
opponent_notes: string (required) — buyer-pasted pattern notes, observed movements, delivery notes, or stated uncertainty
own_squad_constraints: string (required) — buyer-pasted available roles, absences, goalkeeper preferences, height/speed notes, or tactical limits
plan_side: "defend" | "attack" | "both" (required)
training_time: string (optional) — supplied session duration or drill limit
desired_emphasis: string (optional) — e.g. first contact, second ball, communication, or transition
evidence_limits: string (optional) — disputed, incomplete, or deliberately excluded information
```

## Workflow

### Step 1: Establish the evidence boundary

Extract only the restart pattern, personnel constraints, stated preferences, and tactical objective that the buyer supplies. Preserve uncertainty about takers, formation, roles, and personnel as `[UNVERIFIED]`. Good output never imports a current lineup, opponent routine, statistic, or availability fact that was not pasted.

### Step 2: Build the set-piece evidence ledger

Separate supplied opponent pattern notes from supplied own-team constraints and from interpretation. Identify up to three preparation-relevant signals, such as delivery zone, blocker/screen description, preferred target area, or goalkeeper lane preference. Good output attaches each signal to a quoted or faithfully paraphrased input fact and names the limitation where evidence is incomplete.

### Step 3: Design roles and a rehearsal sequence

Translate the supplied facts into a short rehearsal sequence with named functional roles (for example, central-lane protector, primary tracker, second-ball cover, or outlet). Provide a trigger, responsibility, and communication call for each role. Good output treats roles as proposed coaching options based on the supplied record, not as facts about named players or a certainty about what will happen.

### Step 4: Add contingencies and confirmation questions

Create at most three conditional branches tied to a changeable supplied condition, such as a different delivery type, missing aerial player, or disrupted first contact. For every branch, say what input supports it and what needs confirmation. Good output places uncertain takers, personnel, and routine variations in a confirmation queue instead of guessing.

### Step 5: Produce the preparation brief

Return an evidence boundary, preparation signals, rehearsal plan, role checklist, contingencies, and confirmation queue. The plan must remain useful as text when the record is sparse: reduce specificity and state the limitation rather than inventing a routine, lineup, or result.

## Output Schema

```text
output_schema_version: "1.0.0"
planning_label: string
restart_type: string
plan_side: "defend" | "attack" | "both"
evidence_boundary: { supplied: string[], unverified: string[] }
preparation_signals: { signal: string, supplied_basis: string, limitation: string }[]
rehearsal_sequence: { phase: string, objective: string, actions: string[], coaching_check: string }[]
role_checklist: { role: string, responsibility: string, communication_call: string, basis: string }[]
contingencies: { condition: string, adjustment: string, supplied_basis: string, confirm_before_use: string }[]
confirmation_queue: string[]
```

## Output Format

```markdown
# Football Set-Piece Plan Brief: [team] — [restart type] [defend/attack]

## Evidence boundary
- Supplied: [buyer-pasted fact]
- [UNVERIFIED]: [missing fact]

## Preparation signals
| Signal | Supplied basis | Limitation |
| --- | --- | --- |
| [signal] | [input fact] | [gap] |

## Rehearsal sequence
1. **[phase]:** [objective]. Actions: [actions]. Coaching check: [observable check].

## Role checklist
| Proposed role | Responsibility | Call | Basis |
| --- | --- | --- | --- |
| [role] | [task] | "[call]" | [supplied fact] |

## Conditional branches
1. **If [condition]:** [adjustment]. Basis: [input]. Confirm: [fact].

## Confirm before use
- [question]
```

## Error Handling

- **No opponent or own-team notes:** Ask for at least one supplied routine observation and one squad constraint; do not fabricate a tactic.
- **Restart type is unclear:** Offer a generic preparation checklist and ask the buyer to choose corner, free kick, throw-in, penalty, or mixed work before assigning roles.
- **Named player facts are incomplete:** Use functional roles rather than asserting who starts, takes a restart, or marks a target; add the assignment to the confirmation queue.
- **Conflicting observations:** Preserve both buyer-pasted observations, label the conflict, and write alternative rehearsal branches rather than selecting an unsupported version.
- **Request for current lineups, opponent statistics, or a certain result:** Explain that the brief works from pasted material only, then offer conditional questions the buyer can settle from their own record.

## Examples

### Example 1: Defensive corner preparation

**Input:** Restart type: corner. Plan side: defend. Opponent note: “Vale use an inswinging right-corner toward a back-post screen.” Own constraint: “Our tallest centre-back is unavailable; goalkeeper prefers a clear central lane.”

**Decision:** Retain the described delivery and screen as supplied, propose a back-post tracker and central-lane protection, and leave the current taker and target personnel `[UNVERIFIED]`.

**Output excerpt:** `Rehearse a protected central lane plus a designated back-post tracker. The supplied screen note supports that rehearsal, but the current taker and intended target are [UNVERIFIED]; confirm both before assigning a final matchup.`

### Example 2: Sparse attacking free-kick note

**Input:** Restart type: wide free kick. Plan side: attack. Opponent note: “They left one player high after a cleared cross in our notes.” Own constraint: “Two regular aerial targets may be absent.”

**Decision:** Do not claim a stable opponent transition pattern; build a conditional second-ball rehearsal and mark the target availability as unresolved.

**Output excerpt:** `The record supports practising a second-ball cover role after a cleared delivery, not claiming that the opponent will always leave a player high. If both aerial targets are absent, rehearse a shorter delivery option after confirming the available roles.`

## Flywheel Connections

### Feeds Into

- `football-match-analyst` (S2-Analysis) — a buyer can add verified set-piece preparation notes to a separate fixture-wide brief.
- `football-postmatch-decision-review` (S6-Analytics) — completed-match observations can test the confirmation questions and improve the next rehearsal record.

### Fed By

- Buyer-maintained opponent observations, set-piece clips transcribed into notes, and squad-availability notes.
- `football-postmatch-decision-review` (S6-Analytics) — a source-bounded review may identify a set-piece problem worth preparing for.

### Feedback Loop

After a session or match, buyers can compare their own observations with the confirmation queue and improve which note fields they paste next time, without turning absence of evidence into a claim of current data.

```yaml
chain_metadata:
  skill_slug: "football-set-piece-plan-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-23"
  suggested_next:
    - "football-match-analyst"
    - "football-postmatch-decision-review"
```

## Quality Gate

1. The output identifies a buyer-supplied restart type and plan side.
2. Every preparation signal cites a supplied fact and a limitation.
3. Every role lists a responsibility, communication call, and input-bound basis.
4. Each contingency is conditional and states what needs confirmation before use.
5. Unknown takers, lineups, personnel, routines, and statistics are `[UNVERIFIED]` rather than inferred.
6. The output contains no score prediction, wager recommendation, medical judgment, or assertion of current football data.

## References

- `LISTING.md` — buyer-facing offer, pricing, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification record.
