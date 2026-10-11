# Verified Demonstration — MLB Lineup Matchup Brief

## Concrete input

```text
Game: Harbor Sailors at Summit Foxes, October 12. The buyer's supplied probable
starters are Harbor RHP Reyes and Summit LHP Lund. Harbor lineup order and
handedness: 1 R, 2 L, 3 R, 4 L. The buyer's notes say Harbor's third hitter has
a .910 OPS against left-handed pitching this season. Summit's closer pitched in
three of the last four days; current availability is not supplied. No weather,
confirmed lineup, or sample size is supplied.
Coverage goal: write a 45-second pregame podcast introduction.
```

## Actual output

```markdown
# MLB Lineup Matchup Brief: Harbor Sailors at Summit Foxes — October 12

## Evidence boundary
- Supplied: Summit probable starter Lund is left-handed; Harbor's first four handedness slots are R/L/R/L.
- Supplied: Harbor's third hitter has a .910 OPS against left-handed pitching in the buyer's notes.
- [UNVERIFIED]: confirmed starting lineups, the OPS sample size, weather, and Summit's closer availability.

## Lineup matchup cards
| Lineup slot | Supplied matchup fact | Read | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| Harbor 3rd, R | .910 OPS vs LHP against supplied LHP starter | This is the clearest supplied lineup-versus-starter question for the introduction. | medium | Sample size and confirmed lineup are not supplied. |
| Harbor 2nd and 4th, L | L-handed slots face supplied LHP starter | The lineup creates two handedness matchups worth checking, but no performance split was supplied. | low | No split, pitch mix, or confirmed lineup was supplied. |

## Coverage angles
1. The third hitter's supplied split against a left-handed starter is the lead angle. Caveat: the note does not establish a sample size or current lineup confirmation.
2. Summit's late-inning plan is a question, not a conclusion: the supplied workload note says the closer pitched three times in four days, while present availability is [UNVERIFIED].

## If the lineup changes
- If Harbor's third hitter is not in the confirmed order, remove the supplied split from the lead angle and elevate lineup confirmation to the opening question.

## Verify before using
- Confirm both starting lineups.
- Confirm whether Summit's closer is available.
- Add the sample size for the supplied .910 OPS note if it will be cited.

## 45-second pregame rundown
Harbor's clearest supplied matchup question is its third lineup slot against Summit left-hander Lund: the buyer's notes list a .910 OPS against left-handed pitching, though the sample size and final lineup still need confirmation. Harbor's R/L/R/L opening also puts handedness in focus, but no additional splits were supplied. Late innings are an open question because Summit's closer worked three times in four days; availability has not been confirmed.
```

## Verification notes

- The output uses exactly one supplied game and does not add a current roster, score, lineup, injury, odds, or weather claim.
- Every concrete baseball fact in the output is either copied from the input or labeled `[UNVERIFIED]`.
- The tentative closer is treated as a verification item, not an availability conclusion.
- The result is a text-only analysis and gives no wagering instruction or certain outcome.
