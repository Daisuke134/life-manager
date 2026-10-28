# Verified Demonstration — NPB Game-Flow Scenario Brief

## Selection record

This offline candidate uses the C6 opportunity file dated 2026-10-29. Its
highest-total-sales uncovered shelf is `Analysis` (3,217), with top winners
Ocup Football Analysis (3,134 sold), MLB Baseball Analysts (40), and Otata
Baseball Analysis (30). The locally cached winner records show that those
buyers seek an upcoming-game analysis for outcome, scoreline, game flow, and
key matchup factors. This candidate copies that recurring buyer workflow while
being deliberately narrower and honest: one buyer-pasted NPB matchup pack
becomes conditional editorial scenarios, not a live-data result or probability.

The release-owned `sales_selector.py` was used only through its pure
`select_signal` function with the local cached seller-ranking record. Its
readback was `signal: sales`, with `Hook Lab — Win the First 3 Seconds` as an
official seller winner. That is a catalog-level sales signal, not evidence of
demand or sales for this offline candidate; the C6 Analysis shelf controlled
the present candidate selection.

## Concrete input

```text
Game: Harbor Swallows at Summit Bears, April 14.
Harbor starts right-hander Mori after six days' rest. The buyer's notes say
Mori used his splitter often in his last start, but give no pitch count or
current health information. Summit expects three left-handed hitters in its top
five. Harbor's setup reliever worked on each of the previous two days. The
buyer supplied no confirmed lineups, weather, park factor, or Summit bullpen
notes.
Coverage goal: a 45-second pregame podcast introduction.
```

## Actual output

```markdown
# NPB Game-Flow Scenario Brief: Harbor Swallows at Summit Bears

## Evidence boundary
- Supplied: Harbor right-hander Mori has six days' rest and used his splitter often in his last stated outing.
- Supplied: Summit expects three left-handed hitters in its top five; Harbor's setup reliever worked on two previous days.
- [UNVERIFIED]: pitch count, current health, confirmed lineups, weather, park factor, and Summit bullpen status.

## First-five factors
| Supplied factor | Possible effect | Confidence | Limitation |
| --- | --- | --- | --- |
| Mori's six days' rest and stated splitter use | The opener can examine whether the supplied splitter note remains central against Summit's expected left-handed core. | low | No pitch count, result, or current health information was supplied. |
| Three expected left-handed hitters in Summit's top five | The stated batting-order shape makes early matchup construction a coverage question. | medium | The lineup is not confirmed and no performance split was supplied. |

## Conditional game flows
### Left-handed-core early test
- Supported by: Summit is expected to use three left-handed hitters in its top five; Mori is a supplied right-handed starter.
- If this holds: frame the first five innings around how the supplied batting-order shape meets Mori's stated splitter usage.
- What would change it: a different confirmed lineup or a different supplied pitch plan.
- Confidence: low.

### Late-inning bridge question
- Supported by: Harbor's setup reliever worked on each of the prior two days.
- If this holds: treat Harbor's bridge to the final innings as a conditional discussion point.
- What would change it: a supplied availability decision or additional bullpen notes.
- Confidence: low.

## Late-inning branch
Harbor's supplied workload note supports a question about the setup role, not a claim that the reliever is unavailable. Summit's late-inning options are [UNVERIFIED].

## Coverage lead
Harbor's supplied starter-rest note and Summit's expected left-handed core make the first five innings the clearest preview lens, while Harbor's recent setup-reliever workload leaves a qualified late-inning question. The available notes do not establish a lineup, health status, or bullpen availability.

## 45-second rundown
Harbor brings right-hander Mori after six days' rest, and the buyer's notes say his splitter featured in his last outing. Summit expects three left-handed hitters in its top five, so the opening matchup is worth watching if that order is confirmed. Later, Harbor's setup reliever worked on the previous two days, which makes the bridge innings a question rather than a conclusion. Confirm the lineup and bullpen status before using either angle as a firm claim.

## Confirm before using
- Confirm both starting lineups.
- Add Mori's supplied pitch count or current status if it is relevant.
- Confirm Harbor's setup-reliever availability and Summit's bullpen options.
```

## Verification notes

- The output covers exactly one buyer-supplied NPB game.
- Each current-game assertion is copied from the input or explicitly marked
  `[UNVERIFIED]`; it adds no roster, score, weather, injury, standings, odds,
  or external statistic.
- Both game-flow sections are conditional and say what information would change
  the read.
- The result is text-only analysis: it gives neither wagering advice nor a
  predicted winner, score, or probability.
- No Capafy API, UI, or remote platform state was called or changed for this
  demonstration.
