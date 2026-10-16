---
name: football-postmatch-decision-review
description: >
  Turn buyer-pasted football match events and staff notes into a source-bounded post-match decision review.
  Use when a coach, analyst, or football writer needs an accountable tactical review after a completed match.
license: MIT
version: "1.0.0"
tags: [football, post-match, tactical-review, coaching, analysis]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S6-Analytics
---

# Football Post-Match Decision Review

Create an accountable post-match review from the event log, tactical notes, and decisions the buyer pastes. The result distinguishes supplied observations from interpretation, connects each finding to a decision point, and keeps missing evidence visible instead of inventing statistics or current facts.

## Stage

S6-Analytics

## When to Use

- A coach has a completed-match timeline and wants three focused training priorities for the next session.
- An analyst needs to turn staff notes into a review that links substitutions, shape changes, and game-state decisions to observed consequences.
- A football writer or video analyst wants a disciplined post-match explainer without claiming access to match feeds or statistics.

## Input Schema

```text
match_context: string (required) — teams, competition, date, final score, and the buyer's role.
event_log: string (required) — timestamped incidents, phases, substitutions, or observations.
staff_notes: string (required) — tactical intent, decisions made, and observations from staff.
review_question: string (optional) — decision or phase to examine first.
evidence_limits: string (optional) — facts that are unavailable or disputed.
```

## Workflow

### Step 1: Establish the evidence boundary

Extract only the match facts the buyer supplied, preserving timestamps and attribution. Mark any absent score detail, player availability, or statistic as `[UNVERIFIED]`; a good review never fills a gap from assumed match knowledge.

### Step 2: Build the decision timeline

Place supplied tactical decisions, substitutions, and visible game-state changes in chronological order. For each, state the stated intent, the supplied observation after it, and whether the link is evidence, inference, or unknown. A good timeline makes causality proportionate to the input.

### Step 3: Identify turning points

Select at most three moments supported by multiple supplied details. Explain what changed, which decision mattered, and a plausible alternative only as a counterfactual—not as a claim that it would have changed the result. A good turning point includes an uncertainty note.

### Step 4: Produce next-action priorities

Convert the review into three concrete next actions: a training focus, a repeat/avoid decision rule, and a verification question for the next review. Each action must name its supporting evidence and owner; do not prescribe medical, gambling, or undisclosed player data decisions.

### Step 5: Perform an honesty pass

Check that every current fact is traceable to buyer input and every inference is labelled. The finished review says it is based on pasted material, does not present a result forecast, and does not imply access to live data, video, or external statistics.

## Output Schema

```json
{
  "output_schema_version": "1.0.0",
  "evidence_boundary": ["string"],
  "decision_timeline": [{"time": "string", "decision": "string", "observed_effect": "string", "confidence": "high|medium|low"}],
  "turning_points": [{"moment": "string", "evidence": "string", "interpretation": "string", "uncertainty": "string"}],
  "next_actions": [{"owner": "string", "action": "string", "support": "string"}],
  "verification_queue": ["string"]
}
```

## Output Format

```markdown
# [Team] post-match decision review — [Match]

## Evidence boundary
- [Supplied fact or [UNVERIFIED] item]

## Decision timeline
| Time | Decision / change | Supplied observation | Confidence |
|---|---|---|---|
| [minute] | [decision] | [effect] | [high/medium/low] |

## Turning points
1. **[moment]** — Evidence: [pasted evidence]. Interpretation: [bounded interpretation]. Uncertainty: [what is not established].

## Next actions
1. **[owner]:** [action] — supported by [evidence].

## Verification queue
- [Question to check from the buyer's own material]
```

## Error Handling

- **No timeline:** Ask for at least three ordered events or state that a chronological review cannot be produced.
- **Outcome without evidence:** Report the score as supplied, but do not infer why it occurred.
- **Causal overreach:** Replace “caused” with “followed” or “may have contributed” unless the pasted evidence directly establishes the connection.
- **Missing tactical intent:** Separate observation from interpretation and add the intended decision as `[UNVERIFIED]`.
- **Request for prediction or wagering:** Decline that portion and keep the output as a retrospective decision review.

## Examples

**Example 1: Late-game shape change**

Input: “Harbor 1–2 Vale. At 62' Harbor changed from 4-3-3 to 4-4-2; staff note says the aim was more box presence. At 68' Vale created a wide overload and scored. At 74' Harbor created two crosses but no shot.”

Decision: Treat the wide overload as an observed consequence, not proof that the shape change caused the goal.

Output excerpt: “62': 4-4-2 change; stated intent: more box presence. At 68' the supplied log records a Vale wide overload and goal. Confidence in a tactical link: medium; the log does not establish individual assignment errors.”

**Example 2: Incomplete match notes**

Input: “We lost control after half-time. A midfielder came off.”

Decision: Do not manufacture a minute, reason, or tactical adjustment.

Output excerpt: “The halftime-control claim and substitution timing are `[UNVERIFIED]` from the supplied material. Verification queue: add the substitution minute, replacement role, and two events before and after the change.”

## Flywheel Connections

### Feeds Into

- `football-match-analyst` (S6-Analytics) — recurring fixture notes can incorporate lessons from prior reviews.
- `football-scoreline-scenario-card` (S6-Analytics) — writers can use verified retrospective lessons as bounded context for a new preview.

### Fed By

- Match event logs, coach observations, and analyst notes supplied by the buyer.

### Feedback Loop

Buyers can compare the next match's supplied observations with the review's verification queue and refine which decision notes they capture.

```yaml
chain_metadata:
  skill_slug: football-postmatch-decision-review
  stage: S6-Analytics
  timestamp: "2026-10-17"
  suggested_next:
    - football-match-analyst
    - football-scoreline-scenario-card
```

## Quality Gate

1. Every claimed match fact appears in the buyer-pasted input.
2. The timeline has a time or is explicitly marked `[UNVERIFIED]`.
3. No more than three turning points are presented.
4. Each turning point has evidence, interpretation, and uncertainty.
5. Each next action names an owner and supporting observation.
6. The output contains no forecast, wager recommendation, or claim of external data access.

## References

- `LISTING.md` — buyer-facing scope, pricing, and sandbox honesty statement.
- `evidence/verified-demonstration.md` — concrete input, output, and verification notes.
