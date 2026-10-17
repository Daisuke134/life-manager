# Verified Demonstration — Football Scoreline Scenario Card

## Concrete input

```text
Fixture: Northbridge FC host River Athletic in the buyer's supplied league notes.
Goal evidence: Northbridge scored in 8 of their last 10 home matches. River
conceded 7 goals after the 70th minute across their last 10 away matches.
Availability: River's first-choice centre-back is doubtful; no replacement or
confirmation is supplied. Tactical note: the buyer describes Northbridge as
pressing high after halftime. Editorial goal: a 60-second preview segment.
```

## Actual output

```markdown
# Football Scoreline Scenario Card: River Athletic at Northbridge FC

## Evidence boundary
- Supplied: Northbridge scored in 8 of the 10 home matches named in the buyer's notes.
- Supplied: River conceded 7 post-70th-minute goals across the 10 away matches named in the buyer's notes.
- Supplied: River's first-choice centre-back is doubtful, and Northbridge press high after halftime.
- [UNVERIFIED]: confirmed lineups, the centre-back's availability, score context for the goal samples, and the competition date.

## Conditional scenarios
| Scenario | Scoreline range | Supplied basis | Confidence | What would change it |
| --- | --- | --- | --- | --- |
| Northbridge edge | Northbridge by one goal | The supplied home-scoring record plus River's late-concession note fit a narrow home advantage if the doubtful defender is absent. | medium | Confirmed defender availability or a different defensive setup. |
| Late separation | Northbridge by two goals | The buyer's high-press note after halftime and River's supplied late-goal pattern could support a second home goal if the match is level or close late. | low | The supplied notes do not establish how either side performs when leading; confirm game-state evidence. |
| Contained match | Draw or one-goal margin | The input gives no supplied scoring rate for River or confirmed lineup, so a broader low-separation outcome remains possible. | low | Add River's attacking evidence and confirmed selections. |

## Match-shape drivers
1. The supplied late-concession record is the clearest reason to treat the final 20 minutes as a scenario driver.
2. River's doubtful centre-back changes the card only if absence is confirmed; otherwise it remains a conditional assumption.

## Editorial explainer
Northbridge's home-scoring note and River's late-concession pattern make a narrow home edge the best-supported scenario in the supplied material, especially if River's doubtful centre-back does not play. That is not a final-score claim: River's attacking record, confirmed teams, and score-state context are not supplied. The preview should frame late pressure as the question that could widen a close match.

## Verify before using
- Confirm whether River's first-choice centre-back is available.
- Add River's supplied scoring evidence and the match date.
- Confirm the lineups before treating the scenario assumptions as current.
```

## Verification notes

- The output uses one buyer-supplied fixture and does not add a real team,
  current score, lineup, injury report, odds, or statistic.
- Every numerical football fact is copied from the concrete input; missing
  current facts are labeled `[UNVERIFIED]`.
- Every scoreline range is conditional, names its supplied basis, and gives a
  falsifier. The output neither recommends a wager nor presents a result as
  certain.
- The artifact is self-contained text analysis from pasted material; it makes
  no claim to browse or obtain current football information.
