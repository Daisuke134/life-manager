---
name: cricket-innings-turning-point-brief
description: Turn buyer-pasted cricket score context, bowling plans, and batter notes into an evidence-bound innings turning-point brief.
---

# Cricket Innings Turning-Point Brief

Create a reusable cricket analysis brief from the match notes the buyer pastes.
This is a structured reading of supplied information, not live score retrieval,
betting advice, or a prediction service.

## Input

Ask for the format, innings, current or completed score context, wickets, overs,
batting pair, bowling spells or intended matchups, pitch/weather notes if known,
and the buyer's own observations. Mark absent current facts `[UNVERIFIED]`.

## Method

1. Separate supplied facts from assumptions and missing context.
2. Identify the innings phase: powerplay, middle overs, consolidation, or death.
3. Assess the stated run-rate pressure, wicket state, bowling options, batting
   matchup, and fielding or pitch notes.
4. Produce conditional turning-point scenarios only when grounded in supplied
   information.

## Output

Return a phase table, three turning-point conditions, an evidence ledger, and a
short "what would change this" checklist. Never invent a score, player status,
or statistic. Do not advise wagers or present an outcome as certain.
