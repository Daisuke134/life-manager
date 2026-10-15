# Verified Demonstration — MLB In-Game Decision Brief

## Concrete input

```text
game: Harbor Sailors at Summit Foxes, 2026-10-16
game_state: Harbor leads 4-3 in the bottom of the eighth. One out, runner on first. Summit's next listed batter is left-handed. The current count is not supplied.
decision_context: Should Harbor replace its right-handed reliever with the left-handed reliever before this batter?
availability_notes: Harbor's right-handed reliever has thrown 22 pitches across the prior two days. Harbor's left-handed reliever has not pitched in three days. No other bullpen availability is supplied.
supporting_evidence: No batter-versus-pitcher split, current pitch count, bench options, or confirmed lineup change is supplied.
coverage_goal: 30-second radio update
```

## Actual output

```markdown
# MLB In-Game Decision Brief: Harbor Sailors at Summit Foxes — bottom 8th

## Evidence boundary
- Supplied: Harbor leads 4-3 with one out and a runner on first in the bottom of the eighth.
- Supplied: Summit's next listed batter is left-handed.
- Supplied: Harbor's right-handed reliever has thrown 22 pitches across the prior two days; its left-handed reliever has had three days off.
- [UNVERIFIED]: current count, current-game pitch count, batter-versus-pitcher split, other reliever availability, bench options, and any lineup change.

## Decision card
- Question: Should Harbor replace its right-handed reliever with the rested left-hander before the next listed batter?
- Documented constraints: the stated left-handed matchup; the right-hander's supplied recent workload; the left-hander's supplied three days of rest.
- Read: The rested left-hander is a reasonable conditional option because the supplied matchup and rest point in the same direction. The record does not establish that a switch is preferred.
- Confidence: medium.
- Limitation: No current pitch count, split, or alternate bullpen option was provided.

## Conditional paths
1. **If Harbor uses the left-hander now:** The supplied three days of rest align with the stated left-handed matchup. Trade-off: the supplied record gives no split or current pitch count to show that this improves the moment. This changes if the current pitcher, batter, or available relief options differ from the notes.
2. **If Harbor leaves the right-hander in:** Continuity may preserve the current matchup, but the supplied two-day workload is relevant context. Trade-off: workload alone does not show fatigue or dictate a change. This changes if the current-game pitch count or recent recovery information is supplied.

## Coverage line
Harbor's choice is a conditional matchup question: the notes support a rested left-handed option, but the current count, pitch total, and available alternatives still need confirmation.

## Verify before using
- Confirm the current pitcher, batter, count, and pitch count.
- Confirm the remaining bullpen and bench availability.
- Confirm whether the listed batter is still due to hit.
```

## Verification notes

- **Input traceability:** Every team, inning, score, runner, handedness, and workload statement in the output appears in the concrete input.
- **Unknowns preserved:** The current count, current-game pitch count, splits, bench, and wider bullpen facts remain `[UNVERIFIED]`; none is inferred.
- **Capability boundary:** The output is self-contained text created from the pasted record. It does not access a game feed, retrieve baseball data, report a current score, place a wager, or promise an outcome.
- **Distinct catalog job:** The input is a single in-game decision moment; the output is a decision card and conditional coverage line. This differs from the catalog's MLB lineup matchup card, series preview, and postgame turning-point brief.
