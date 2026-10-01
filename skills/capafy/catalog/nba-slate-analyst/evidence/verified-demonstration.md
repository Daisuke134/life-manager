# Verified offline demonstration — NBA Slate Analyst

## Concrete input

```text
slate_date: 2026-10-06
games: Harbor at Summit. Harbor's lead guard is doubtful. Summit played last night.
availability_notes: Harbor lead guard: doubtful. No other player status is supplied.
recent_evidence: Harbor allowed 56 paint points in its last game.
constraints: Compare availability and rest scenarios. Do not predict a winner or discuss betting.
```

## Actual output

# NBA Slate Brief: 2026-10-06

## Evidence boundary

- Supplied: Harbor plays at Summit.
- Supplied: Harbor's lead guard is doubtful.
- Supplied: Summit played last night.
- Supplied: Harbor allowed 56 paint points in its last game.
- Unverified: lineups, current standings, travel distance, other injuries, and any betting market.

## Slate table

| Game | Supplied edge to examine | Uncertainty | Evidence |
| --- | --- | --- | --- |
| Harbor at Summit | Harbor's ball handling and interior defense | Whether the lead guard plays; Summit's recovery context | doubtful guard, back-to-back note, 56 supplied paint points |

## Matchup briefs

### Harbor at Summit

- **Home context:** Summit is the home team from the supplied matchup; no home-performance data was provided.
- **Availability:** Harbor's lead guard is doubtful. Other player availability is `[UNVERIFIED]`.
- **Rest or travel:** Summit played last night. Travel details and Harbor's rest are `[UNVERIFIED]`.
- **Recent evidence:** Harbor allowed 56 paint points in its last supplied game. This supports watching interior pressure; it does not establish a trend.
- **Style matchup:** Interior pressure is a question to examine from the supplied paint-points note. Summit's personnel and style are `[UNVERIFIED]`.
- **Uncertainty:** The doubtful guard and missing lineup information are the largest limits on this brief.
- **If active / if unavailable:** If Harbor's lead guard is active, the supplied notes still do not establish their workload or effectiveness. If unavailable, Harbor's replacement ball handling is `[UNVERIFIED]`; no outcome is implied.

## Watch list

1. Harbor at Summit — it contains both a supplied doubtful-player scenario and a supplied back-to-back note.

## Add next time

- Confirmed player availability and expected lineups.
- Harbor's rest and travel information.
- Supplied matchup-specific evidence for Summit's interior offense.

## Verification notes

- This demonstration was produced offline from the concrete input above; no Capafy API, UI, browser, model endpoint, or remote platform action was used.
- Every current-game statement is either copied from the input or explicitly marked `[UNVERIFIED]`.
- The output applies all six documented axes, includes conditional availability scenarios, and makes no live-data, wagering, certainty, or performance claim.
- The listing promises the same text-only, buyer-pasted-input workflow demonstrated here.
