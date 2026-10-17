# Verified demonstration — NFL Game Script Brief

## Concrete input

```text
Game: Harbor Hawks at Summit Stags, Week 7.

Injury report: Harbor's lead receiver is listed questionable after limited practice participation
Thursday and Friday. No Saturday estimate is supplied. Summit has no injury designations in the
buyer's notes.

Personnel notes: Harbor's offense ran a no-huddle package on 18 of its last 60 offensive snaps,
per the buyer's charting. Summit's base personnel is a four-man front with the buyer noting no
depth-chart changes this week.

Situational notes: Summit's secondary allowed a buyer-noted high per-play passing rate in each of
its last two games. No weather, odds, or official inactive list is supplied.

Coverage goal: 45-second podcast pregame segment on the receiver's status and its effect on game
script.
```

## Actual output

```markdown
# NFL Game Script Brief: Harbor Hawks at Summit Stags — Week 7

## Evidence boundary
- Supplied: Harbor's lead receiver is questionable after two limited practices (Thursday, Friday); no Saturday estimate.
- Supplied: Harbor ran no-huddle on 18 of its last 60 offensive snaps.
- Supplied: Summit's secondary allowed a high per-play passing rate in each of its last two games.
- Supplied: Summit has no injury designations and no depth-chart changes in the buyer's notes.
- [UNVERIFIED]: Harbor's Saturday practice estimate, both teams' official inactive lists, weather, and odds.

## Game-script comparison
| Axis | Supplied fact | Read | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| Injury certainty | Harbor's lead receiver is questionable with two limited practices; no final estimate supplied. | The receiver's status stays conditional until a Saturday estimate or inactive list is supplied. | low | Two practice days do not confirm game-day availability. |
| Personnel/pace | Harbor used no-huddle on 18 of 60 recent offensive snaps. | If the receiver plays, the supplied no-huddle rate supports a faster-tempo passing script as a live angle. | medium | One sample of 60 snaps does not establish a season-long tendency. |
| Situational | Summit allowed a high per-play passing rate in its last two games. | The supplied two-game trend supports asking whether Summit's secondary is a pass-script target, independent of Harbor's receiver status. | low | Two games is a small sample and does not name which routes or personnel were involved. |

## Scenario cards
- If the receiver is active: frame the segment around the supplied no-huddle rate and Summit's two-game passing-rate-allowed trend as the clearest pass-script angle.
- If the receiver is inactive or limited: remove the receiver-specific framing and keep the segment to Harbor's general no-huddle tendency versus Summit's secondary trend, noting the sample is thinner without him.

## Coverage angles
1. Tempo versus a leaky secondary — Evidence: Harbor's 18-of-60 no-huddle rate and Summit's two-game passing-rate-allowed note. Caveat: both are limited-game samples.
2. The questionable-receiver swing — Evidence: two limited practices with no final estimate. Caveat: practice participation does not confirm game-day status.

## Verify before using
- Confirm the receiver's final game-day status (official report or inactive list).
- Confirm whether Summit has any late injury or personnel change not in the buyer's notes.

## 45-second pregame rundown
The supplied notes point to a conditional game-script story rather than a settled plan. Harbor's lead receiver is questionable after two limited practices with no final estimate, so his availability is still open. If he plays, Harbor's charted 18-of-60 no-huddle rate and Summit's two-game trend of allowing a high per-play passing rate frame a tempo-driven pass script as the clearest angle; if he sits, that framing loses its sharpest supplied evidence. Confirm his status first, then lean on the no-huddle-versus-secondary angle only if he is active.
```

## Verification notes

- **Input traceability:** Every named team, week, practice-participation detail, snap count, and situational note in the output appears in the concrete input; no additional player names, statistics, or current-week facts were introduced.
- **Unknown handling:** The receiver's final status, both teams' official inactive lists, weather, and odds remain `[UNVERIFIED]`; the output does not supply a replacement fact or assume game-day availability.
- **Capability boundary:** The demonstration is fully self-contained text analysis of pasted notes, produced by walking the skill's own four-step workflow (evidence boundary, game-script comparison, scenario cards, coverage package) against the concrete input above. It makes no claim to browse or retrieve current NFL information, place a wager, or guarantee a lineup or score.
- **Output contract:** The output includes every section required by SKILL.md's Output Format: evidence boundary, game-script comparison table, scenario cards, coverage angles, verification queue, and a 45-second rundown — matching the Output Schema's field set (`game_label`, `evidence_boundary`, `game_script_comparison`, `scenario_cards`, `coverage_angles`, `verification_queue`, `pregame_rundown`).
- **Quality Gate check:** Exactly one game is analyzed (gate 1); every statement traces to supplied input or is `[UNVERIFIED]` (gate 2); each comparison row has fact/read/confidence/limitation (gate 3); the only uncertain designation (the receiver) produces a conditional scenario, not a start/sit call (gate 4); no wagering advice, certain score, or current-information claim appears (gate 5); the verification queue lists only facts that would improve a revision (gate 6).
