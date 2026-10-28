---
name: soccer-set-piece-matchup-brief
description: Turn a pasted football match fact pack into a practical set-piece matchup brief with clearly marked assumptions.
---

# Soccer Set-Piece Matchup Brief

Create a decision-ready set-piece plan from the match information the user provides. Do not claim access to live fixtures, team sheets, or statistics. Work only from the supplied fact pack and model knowledge; label every missing fact as `[ADD]` or `[UNVERIFIED]`.

## Input

Ask for or use: teams, competition context, likely formations, available height/role notes, recent set-piece notes, referee tendencies if known, and the user's tactical objective.

## Output

Return these sections:

1. Matchup assumptions and information gaps.
2. Attacking-corner plan: target zones, blockers, delivery choices, and two variants.
3. Defensive-corner plan: marking allocation, first-contact priority, and transition roles.
4. Free-kick and throw-in opportunities.
5. A 10-minute rehearsal checklist and in-match adjustment triggers.

Keep recommendations conditional on the pasted information. Do not invent player availability, statistics, or results.
