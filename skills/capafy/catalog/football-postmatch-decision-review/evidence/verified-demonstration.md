# Verified demonstration — Football Post-Match Decision Review

## Concrete input

```text
Match: Harbor FC 1–2 Vale United, regional cup quarter-final.
Buyer role: assistant coach.

Event log:
- 18': Harbor score after a central turnover.
- 55': Vale equalize after a cutback from Harbor's right side.
- 62': Harbor change from 4-3-3 to 4-4-2; staff intent: add a second striker and more box presence.
- 68': Vale score after a wide overload on Harbor's right; the log records a cutback but no individual assignment detail.
- 74' and 81': Harbor deliver two crosses; no shot is recorded.

Staff notes: The right-sided midfielder was asked to press the opposing full-back after 62'. We did not record player tracking, pass counts, or video tags.
Review question: Did the 62' change create a useful attacking trade-off, and what should the next session address?
```

## Actual output

```markdown
# Harbor FC post-match decision review — Harbor 1–2 Vale

## Evidence boundary
- Score, event minutes, formation change, stated intent, and staff instruction are buyer-supplied.
- Player tracking, pass counts, video tags, and individual defensive assignments are [UNVERIFIED].

## Decision timeline
| Time | Decision / change | Supplied observation | Confidence |
|---|---|---|---|
| 62' | Change from 4-3-3 to 4-4-2 to add box presence | The staff note states the intent; two later crosses produced no recorded shot. | medium |
| 62' | Right-sided midfielder presses opposing full-back | At 68' Vale score from a recorded wide overload and cutback on Harbor's right. | medium |

## Turning points
1. **62' shape and role change** — Evidence: the stated attacking intent, right-side press instruction, and the 68' wide-overload goal. Interpretation: the change may have increased the space-management demand on Harbor's right while seeking more box presence. Uncertainty: the log does not establish the individual assignment, the starting positions, or whether the overload was caused by the change.
2. **74'–81' crossing sequence** — Evidence: two supplied crosses and no recorded shot. Interpretation: the intended extra box presence did not produce a recorded final action in these two events. Uncertainty: the log does not show cross quality, target runs, or any other attacks.

## Next actions
1. **Defensive coach:** rehearse the right-side cover rule when the wide midfielder presses — supported by the 68' supplied overload and the missing assignment detail.
2. **Attacking coach:** define a second-striker box-entry cue for wide deliveries — supported by two supplied crosses without a recorded shot.
3. **Analyst:** add starting positions and assignment notes to the next event log — supported by the `[UNVERIFIED]` defensive linkage.

## Verification queue
- Who covered the right channel after the 62' instruction?
- Were the 74' and 81' crosses aimed at a runner in the box?
- What match event preceded the 68' overload?
```

## Verification notes

- Every score, time, tactical change, and observation in the output appears in the concrete input above.
- The output explicitly labels unavailable tracking, pass, video, and assignment information as `[UNVERIFIED]`.
- It uses bounded language (“may have”) rather than asserting that the formation change caused the goal.
- The deliverable is text-only and does not claim external data access, live information, video analysis, file export, wagering, or a guaranteed result.
