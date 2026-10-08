---
name: mlb-series-preview-brief
description: Turn a buyer-pasted MLB series, probable starters, bullpen usage and lineup notes into a source-bounded pitching and bullpen preview brief.
---

# MLB Series Preview Brief

Produce a series-level baseball analysis from the material the buyer pastes. This
is analysis of supplied notes, not data retrieval and not betting advice.

## Input

Ask for the teams, series dates and ballpark, the probable starter for each game,
recent bullpen usage, lineup and injury notes, and any statistics the buyer wants
used. Mark every absent fact `[UNVERIFIED]`; never fill a starter, statistic,
injury or lineup from assumption.

## Method

For each game in the series, compare four things using only supplied input:
starter against opposing lineup, bullpen rest against likely game length, park and
travel context, and the single factor most likely to swing the game.

## Output

Return, in order:

1. A series table: one row per game, with the supplied starters and a confidence
   label (low, medium, high) with its reason.
2. A pitching-matchup read per game, naming the two or three supplied facts that
   drive it.
3. A bullpen strain check covering each side's supplied usage.
4. A lineup and availability section; every unconfirmed item is `[UNVERIFIED]`.
5. A "what would change this read" list per game.
6. A series-level summary only when the supplied evidence supports comparison.

Never present a prediction as certain, invent a statistic, injury or starter, state
odds, or suggest a wager. State that all inputs came from the buyer's paste.
