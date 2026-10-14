# Verified demonstration — NHL Goalie Matchup Brief

## Concrete input

```text
Game: Harbor Orcas at Summit Owls, Thursday.

Goalie notes: Harbor projects Hale. The buyer's notes say Hale stopped 31 shots two nights ago.
Summit projects Varga after three days off. Neither starter is confirmed in the supplied notes.

Team context: Summit limited opponents to 20 shots in its last game. Harbor allowed 14 slot chances
in its last game. No travel, injury, season save percentage, or expected lineup information is supplied.

Coverage goal: 45-second podcast pregame segment about the goalie situation.
```

## Actual output

```markdown
# NHL Goalie Matchup Brief: Harbor Orcas at Summit Owls — Thursday

## Evidence boundary
- Supplied: Harbor projects Hale; the buyer says he stopped 31 shots two nights ago.
- Supplied: Summit projects Varga after three days off.
- Supplied: Summit allowed 20 shots in its last game; Harbor allowed 14 slot chances in its last game.
- [UNVERIFIED]: confirmed starters, travel, injuries, season save percentages, and expected lineups.

## Goalie comparison
| Axis | Supplied fact | Read | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| Starter certainty | Both goalies are projected, not confirmed. | The pregame goalie comparison remains conditional until confirmation. | low | The supplied notes do not confirm either starter. |
| Rest/workload | Hale faced 31 shots two nights ago; Varga had three days off. | If the projections hold, the supplied rest contrast is the clearest workload-management angle. | medium | One previous workload note does not establish a broader trend. |
| Team context | Summit allowed 20 shots; Harbor allowed 14 slot chances in their respective last games. | The notes support asking whether Varga's environment was calmer while Harbor's defensive context may demand more high-danger work. | low | Each observation covers one game and does not name the shooters or confirmed goalie. |

## Scenario cards
- If both projected starters are confirmed: frame the segment around the supplied rest contrast and the limitation of the single-game team notes.
- If either starter changes: remove the workload comparison and verify the replacement's supplied context before using a goalie angle.

## Coverage angles
1. Rest versus recent workload — Evidence: Hale's 31 shots two nights ago and Varga's three days off. Caveat: neither starter is confirmed.
2. The environment question — Evidence: Summit's 20 allowed shots and Harbor's 14 allowed slot chances. Caveat: both are one-game observations.

## Verify before using
- Confirm both starting goalies.
- Confirm whether travel or an availability note changes either workload scenario.

## 45-second pregame rundown
The supplied notes point to a conditional goalie story rather than a confirmed edge. Harbor projects Hale after a 31-shot outing two nights ago, while Summit projects Varga after three days off. Summit's last-game 20-shot result and Harbor's 14 slot chances give the segment a defensive-context question, but both starter names and the broader sample remain unverified. Confirm the goalies first; if they hold, use rest and workload as the focused pregame angle.
```

## Verification notes

- **Input traceability:** Every named team, goalie, shot count, rest interval, and slot-chance count in the output appears in the concrete input.
- **Unknown handling:** Starter confirmation, travel, injuries, season save percentages, and lineups remain `[UNVERIFIED]`; the output does not supply replacements or inferred facts.
- **Capability boundary:** The demonstration is fully self-contained text analysis of pasted notes. It makes no claim to browse, retrieve hockey information, place wagers, or determine a game result.
- **Output contract:** The output includes the required evidence boundary, comparison table, scenario cards, coverage angles, verification queue, and 45-second rundown.
