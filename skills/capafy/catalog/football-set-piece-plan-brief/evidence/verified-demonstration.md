# Verified Demonstration — Football Set-Piece Plan Brief

## Demonstration boundary

This is an offline, text-only demonstration. The input is invented solely for testing the skill's input-to-output behavior; it is not a claim about a current football team, lineup, player, match, statistic, or opponent routine. The output below was produced by applying the documented workflow to that exact input, with no web, platform, or file access.

## Concrete input

```text
planning_context: Harbor FC v Vale Athletic — defensive-corner rehearsal for Thursday training
restart_type: corner
plan_side: defend
opponent_notes: Vale use an inswinging right-side corner toward a back-post screen. In two buyer-noted examples, a runner arrived behind the screen for a second contact. The notes do not identify the taker or current target players.
own_squad_constraints: Harbor's tallest centre-back is unavailable. The goalkeeper prefers a clear central lane. The buyer has one strong aerial defender and one quick wide defender available.
training_time: 18 minutes
desired_emphasis: protect the first contact and organise the second ball
evidence_limits: No current lineup, taker, delivery speed, or opponent personnel is supplied.
```

## Actual output

```markdown
# Football Set-Piece Plan Brief: Harbor FC v Vale Athletic — corner defend

## Evidence boundary
- Supplied: the opponent notes describe an inswinging right-side corner toward a back-post screen and two examples of a runner arriving for a second contact.
- Supplied: Harbor's tallest centre-back is unavailable; the goalkeeper prefers a clear central lane; one strong aerial defender and one quick wide defender are available.
- [UNVERIFIED]: current taker, target players, delivery speed, starting lineup, and whether the same routine will be used.

## Preparation signals
| Signal | Supplied basis | Limitation |
| --- | --- | --- |
| Back-post screen risk | Buyer notes describe a back-post screen on an inswinging right-side corner. | The screen's personnel and timing are not supplied. |
| Second-contact risk | A runner arrived behind the screen in two buyer-noted examples. | Two examples do not establish frequency or certainty. |
| Central-lane priority | The goalkeeper prefers a clear central lane. | The final setup still depends on the confirmed delivery and available players. |

## Rehearsal sequence
1. **Walk-through:** Place a central-lane protector and back-post tracker before the delivery. Actions: rehearse the call "lane clear" and identify who tracks the runner behind the screen. Coaching check: the goalkeeper has an unobstructed first step.
2. **First-contact rep:** Deliver an inswinging ball from the described side. Actions: the strong aerial defender contests the stated danger area while the quick wide defender holds second-ball cover. Coaching check: every clearance has a named cover player.
3. **Second-contact branch:** Add a delayed runner behind the screen. Actions: the back-post tracker passes the runner only after calling "runner live." Coaching check: the transition from first contact to second-ball cover is audible and assigned.

## Role checklist
| Proposed role | Responsibility | Call | Basis |
| --- | --- | --- | --- |
| Central-lane protector | Preserve the goalkeeper's stated clear central lane. | "lane clear" | Goalkeeper preference supplied by buyer. |
| Primary aerial defender | Contest the described back-post danger area. | "first ball" | One strong aerial defender is supplied. |
| Back-post tracker | Track the delayed runner behind the supplied screen description. | "runner live" | Two buyer-noted examples mention a runner. |
| Second-ball cover | Protect the clearance zone and wide transition. | "cover out" | Buyer supplies one quick wide defender and a second-contact concern. |

## Conditional branches
1. **If the delivery is outswinging rather than the supplied inswinger:** move the first-contact rehearsal toward the confirmed delivery zone. Basis: the supplied pattern is specifically an inswinger. Confirm: taker foot and delivery type.
2. **If the strong aerial defender is unavailable:** rehearse a zonal first-contact alternative and reduce matchup-specific instructions. Basis: only one strong aerial defender is supplied. Confirm: final available defenders.
3. **If no back-post screen appears:** retain second-ball cover but do not force a screen-tracking assignment. Basis: the screen appears only in the supplied notes. Confirm: the opponent's current routine.

## Confirm before use
- Who is expected to take the corner and from which side?
- Which opponent players are the intended targets or screeners?
- Which Harbor players are available for the final first-contact and back-post assignments?
```

## Verification notes

1. **Traceability:** Every tactical signal is either a direct transformation of the input or identified as a proposed rehearsal role. No current team or opponent fact is asserted.
2. **Uncertainty preservation:** Taker, targets, delivery speed, lineup, and routine repetition remain `[UNVERIFIED]` because they were absent from the input.
3. **Scope check:** The output is a text rehearsal plan. It makes no result prediction, wager suggestion, medical claim, web lookup, platform action, or file-export promise.
4. **Differentiation check:** The input is set-piece notes plus squad constraints; the output is a rehearsal sequence and role checklist. It is not a fixture-wide comparison, scoreline scenario, or retrospective decision timeline.
