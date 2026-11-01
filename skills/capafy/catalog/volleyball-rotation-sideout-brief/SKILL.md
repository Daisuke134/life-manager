---
name: volleyball-rotation-sideout-brief
description: Turn buyer-pasted volleyball rotation, serve-receive, blocking, and match notes into a source-bounded side-out decision brief. Use for one supplied matchup; it does not supply current match information or betting advice.
license: MIT
metadata:
  author: anicca
  stage: S2-Analysis
---

# Volleyball Rotation & Side-Out Brief

Create a repeatable, text-only analysis brief from the volleyball match packet the buyer pastes. The brief identifies how the supplied rotation, serve-receive, blocking, and setter notes support conditional side-out questions; it never fills in missing current facts.

## When to Use

- A volleyball coach or analyst has one opponent or post-match note packet and needs a rotation-by-rotation discussion guide.
- A volleyball writer or podcast producer needs a concise, evidence-bound segment from their own match notes.
- A buyer wants to organize supplied serve-receive and blocking observations without predicting a result.

## Required Input

```text
match_label: the buyer-supplied matchup or match review label
rotation_notes: the supplied rotation order, setter position, and player-role notes
serve_receive_notes: supplied server targets, passing observations, and side-out outcomes
block_defense_notes: supplied block matchups, defensive positioning, or transition observations
decision_question: the buyer's coaching, preview, review, or editorial question
```

Optional input: buyer-pasted set score, sample counts, substitutions, or quoted observations.

## Workflow

1. Make an evidence boundary. List each supplied fact and label unprovided roster, injury, form, score, and statistics facts `[UNVERIFIED]`.
2. Build a rotation card. For each supplied rotation or matchup, connect the stated serve-receive or block observation to one cautious side-out read, a confidence level, and a limitation.
3. Write conditional decision points. Give two or three `if observed` actions or discussion questions. State the supplied evidence and the fact that would change the conclusion.
4. Deliver a practical text package: rotation card, side-out decision points, one coverage angle, verification queue, and a 45-second rundown.

## Output Format

```markdown
# Volleyball Rotation & Side-Out Brief: [match label]

## Evidence boundary
- Supplied: [fact]
- [UNVERIFIED]: [missing fact]

## Rotation card
| Rotation or matchup | Supplied observation | Side-out read | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| [label] | [fact] | [conditional interpretation] | [low/medium/high] | [gap] |

## Conditional decision points
- If [observable condition]: [action or discussion point]. Evidence: [supplied material]. Reconsider if: [falsifier].

## Coverage angle
[one source-bounded angle and caveat]

## Verify before using
- [fact the buyer can add]

## 45-second rundown
[brief spoken summary bounded to the supplied packet]
```

## Boundaries and Error Handling

- If there is no rotation order or player-role context, ask for it and return only an input checklist; do not infer a lineup.
- If notes conflict, quote both supplied claims and ask which should govern the revision.
- If sample counts are missing, use low confidence and request them in the verification queue.
- For a request for current score, roster, injury, schedule, odds, or certain result, state that the brief uses only buyer-pasted material and ask for the relevant facts.
- Do not give wagering advice or describe an outcome as certain.

## Quality Gate

1. The brief concerns exactly one buyer-supplied volleyball matchup or review.
2. Every named player, rotation, score, and count is traceable to the pasted packet or marked `[UNVERIFIED]`.
3. Each rotation row includes a supplied observation, cautious read, confidence level, and limitation.
4. Every recommended adjustment is conditional and names what would change it.
5. The result contains no claim to current data access, outcome certainty, or wagering advice.

## References

- `LISTING.md` contains the buyer-facing subscription offer and capability boundary.
- `evidence/verified-demonstration.md` records a concrete offline input, output, and verification notes.
