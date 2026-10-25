# Verified Demonstration — Tennis Match Tactics Brief

## Concrete input

```text
Match: Player A vs Player B, buyer's clay-court notes.

Surface context: Clay court. No weather, court-speed rating, or start time is supplied.

Player notes: Player A won 9 of 12 first-serve points but gave up 6 short returns.
Player B attacked second serves and missed 5 backhands after crosscourt pressure.
Neither player's fitness status, ranking, draw position, or recent match record is supplied.

Tactical goal: A 45-second podcast preview about the point patterns to watch.
```

## Actual output

```markdown
# Tennis Match Tactics Brief: Player A vs Player B — clay-court notes

## Evidence boundary
- Supplied: Player A won 9 of 12 first-serve points and gave up 6 short returns.
- Supplied: Player B attacked second serves and missed 5 backhands after crosscourt pressure.
- Supplied: the buyer identifies the court as clay.
- [UNVERIFIED]: fitness, weather, court speed, ranking, draw position, score context, and recent match record.

## Point-pattern card
| Axis | Supplied fact | Read | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| First serve | Player A won 9 of 12 first-serve points. | The supplied sample supports treating first serve as Player A's clearest starting pattern. | medium | Twelve points do not establish a full-match serve trend. |
| Second-serve return | Player B attacked second serves. | Player A should treat second-serve depth as a tactical question if the supplied pressure continues. | medium | The notes give no second-serve point total or return position. |
| Rally direction | Player B missed 5 backhands after crosscourt pressure. | Crosscourt pressure is an evidence-bound pattern to test, not a confirmed weakness. | low | Five misses lack rally length, score state, and error-context detail. |

## Conditional adjustments
- If Player B continues to attack second serves: Player A can prioritize deeper second-serve placement before opening the crosscourt pattern. Evidence: the supplied second-serve attacks and five backhand misses. Reconsider if: added point notes show Player B winning those exchanges.
- If short returns continue from Player A: Player B can use the supplied shorter-ball pattern as a question for early court position. Evidence: six short returns in the buyer's notes. Reconsider if: return depth changes across a larger sample.

## Coverage angles
1. First-serve protection versus second-serve pressure — Evidence: Player A's 9-of-12 first-serve result and Player B's supplied second-serve attacks. Caveat: no second-serve point total is supplied.
2. Crosscourt pressure as a test, not a verdict — Evidence: five Player B backhand misses after crosscourt pressure. Caveat: the input does not show rally length or score pressure.

## Verify before using
- Add the sample size and score context for Player B's second-serve attacks.
- Confirm whether fitness, weather, or court-speed context changes either player's movement or serve plan.
- Add a larger return-depth sample before presenting the short-return pattern as stable.

## 45-second match rundown
The supplied clay-court notes point to two conditional questions rather than a predicted winner. Player A's 9 of 12 first-serve points are the strongest stated pattern, while Player B's second-serve attacks make depth the adjustment to watch. The five backhand misses after crosscourt pressure justify testing that direction, but they do not prove a settled weakness. Fitness, conditions, score context, and larger samples are unverified, so the useful preview is about whether these point patterns repeat.
```

## Verification notes

- **Input traceability:** Every named player, surface, point count, short-return count, and backhand-miss count in the output appears in the concrete input.
- **Unknown handling:** Fitness, weather, court speed, ranking, draw position, score context, and recent records remain `[UNVERIFIED]`; the output does not supply them.
- **Capability boundary:** The demonstration is self-contained text analysis of pasted notes. It makes no claim to browse, retrieve tennis information, place wagers, or determine a match result.
- **Output contract:** The output includes the required evidence boundary, point-pattern card, conditional adjustments, coverage angles, verification queue, and 45-second rundown.
