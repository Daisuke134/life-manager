# Verified offline demonstration — Portfolio Tracker — Daily Position Review

## Concrete input

```text
date: 2026-09-30
question: Which evidence should I review first before making my own decision?
positions:
  - symbol: ALPH
    weight: 31%
    supplied_change: -6.2% since yesterday
    thesis: Enterprise renewals should support durable revenue.
    catalyst: Results are scheduled for 2026-10-08.
    invalidation: Renewal growth below the buyer's stated plan.
    concentration_context: Largest position; no peer weights supplied.
    time_horizon: 12 months
  - symbol: BETA
    weight: 18%
    supplied_change: +1.4% since yesterday
    thesis: Margin improvement may continue.
    catalyst: No catalyst supplied.
    invalidation: Margin improvement reverses.
    concentration_context: Second-largest position; no sector weights supplied.
    time_horizon: 6 months
cash: 11%
risk_limits: Maximum single position 35%; target cash 12%.
constraints: Use only this pasted snapshot. Do not retrieve prices or news, and do not tell me what to buy or sell.
```

## Actual output

# Daily Position Review

## Evidence boundary

- Supplied: ALPH is 31% of the portfolio and is down 6.2% since yesterday.
- Supplied: BETA is 18% and is up 1.4% since yesterday.
- Supplied: cash is 11%; the buyer's limits are 35% maximum single position and 12% target cash.
- Supplied: the buyer provided theses, one catalyst for ALPH, invalidation conditions, and time horizons.
- Unknown: current prices, news, sector weights, peer comparisons, portfolio value, and whether either thesis is supported by external evidence. These remain `[UNVERIFIED]`.

## Position table

| Position | Weight | Supplied change | Thesis evidence | Catalyst | Invalidation | Concentration | Time horizon | Missing information |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| ALPH | 31% | -6.2% | Enterprise renewals should support durable revenue; supporting evidence `[UNVERIFIED]` | Results scheduled 2026-10-08 | Renewal growth below the buyer's stated plan | Largest position; peer and sector weights `[UNVERIFIED]` | 12 months | Renewal data, portfolio value, external event details `[UNVERIFIED]` |
| BETA | 18% | +1.4% | Margin improvement may continue; supporting evidence `[UNVERIFIED]` | `[UNVERIFIED]` | Margin improvement reverses | Second-largest position; peer and sector weights `[UNVERIFIED]` | 6 months | Catalyst, margin data, portfolio value `[UNVERIFIED]` |

## Change log

| Position | Numerical move in supplied snapshot | Thesis change | Evidence status |
| --- | --- | --- | --- |
| ALPH | -6.2% since yesterday | No thesis change supplied | Numerical move supplied; cause `[UNVERIFIED]` |
| BETA | +1.4% since yesterday | No thesis change supplied | Numerical move supplied; cause `[UNVERIFIED]` |

## Priority review queue

1. ALPH: identify the buyer-supplied evidence that would test the renewal-growth invalidation before the 2026-10-08 results date.
2. ALPH: compare the 31% weight with the buyer's 35% limit and record whether any other position or sector makes concentration higher than this snapshot shows `[UNVERIFIED]`.
3. BETA: supply the missing catalyst and the evidence supporting the margin-improvement thesis.
4. Cash: compare the supplied 11% cash with the 12% target and record the buyer's own explanation for the difference.

## Limit check

- ALPH at 31% is below the supplied 35% maximum single-position limit by 4 percentage points.
- Cash at 11% is 1 percentage point below the supplied 12% target.
- A full portfolio concentration check is `[UNVERIFIED]` because no other weights or sector totals were supplied.

## Scenario questions

1. What buyer-supplied renewal number would count as evidence for or against the ALPH thesis?
2. What would make the buyer classify the ALPH move as a thesis change rather than a numerical move?
3. Which BETA margin measure and time period should be compared next?
4. What additional position or sector weights are needed to complete the concentration check?

## Boundary note

This is a review of the pasted material, not investment advice or a current-market report. No prices, news, ratings, or events were retrieved.

## Verification notes

- This demonstration was authored and checked offline: no Capafy API, browser, model call, or remote platform action was used.
- Every number and factual statement in the output appears in the concrete input; the two percentage-point comparisons are arithmetic on supplied values.
- Missing external evidence is marked `[UNVERIFIED]`, and the output gives no buy, sell, price, or forecast recommendation.
