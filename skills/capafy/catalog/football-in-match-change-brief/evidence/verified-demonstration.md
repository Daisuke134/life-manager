# Verified Demonstration — Football In-Match Change Brief

## Concrete input

```text
match_context: Harbor Town vs Eastvale United, stated minute 68. Harbor Town lead 1-0.
current_shape_and_pattern: Harbor are in a 4-3-3. The buyer's notes say Harbor are losing second balls after clearances and Eastvale are restarting attacks quickly through the centre.
decision_question: Should Harbor replace an attacking midfielder with the available defensive midfielder, or keep the current shape?
available_options: One defensive midfielder is available on Harbor's bench. No other bench roles, player fitness, cards, or substitutions are supplied.
evidence_notes: No possession figures, player workload, official lineup change, or later match events are supplied.
audience: 30-second commentary update
```

## Actual output

```markdown
# Football In-Match Change Brief: Harbor Town vs Eastvale United — stated minute 68

## Evidence boundary
- Supplied: Harbor Town lead 1-0 at the stated 68th minute.
- Supplied: Harbor are in a 4-3-3 and are losing second balls after clearances.
- Supplied: Eastvale are restarting attacks quickly through the centre.
- Supplied: Harbor have one defensive midfielder available on the bench.
- [UNVERIFIED]: player fitness, cards, other bench roles, player workload, possession figures, official lineup changes, and later events.

## Decision card
- Question: Should Harbor replace an attacking midfielder with the available defensive midfielder, or keep the current shape?
- Objective: Address the buyer-stated second-ball problem while Harbor protect a one-goal lead.
- Constraints: The only stated alternative is one defensive midfielder; no player-specific availability or workload context is supplied.
- Confidence: medium.

## Conditional paths
1. **If Harbor adds the stated defensive midfielder:** Possible effect: the supplied second-ball problem could receive an extra central screen after clearances. Trade-off: the record does not establish how removing the attacking midfielder affects Harbor's outlet or the replacement's readiness. Reassess if player fitness, the exact role change, or Eastvale's current central pattern differs from the notes.
2. **If Harbor keeps the current 4-3-3:** Possible effect: Harbor retain the stated attacking-midfield option while asking the same structure to manage the central restarts. Trade-off: the supplied notes give no evidence that the existing midfield is resolving the second-ball problem. Reassess if the next supplied phase shows Harbor winning those clearances or Eastvale changing its approach.

## Commentary line
Harbor's choice is conditional: the available defensive midfielder could add a central screen to the stated second-ball issue, but the notes do not establish the effect on Harbor's outlet or the player's readiness.

## Verify before using
- Confirm the players' fitness, cards, and current roles.
- Confirm whether the defensive midfielder can enter and which role would change.
- Confirm the current shape and whether the stated central restart pattern is continuing.

## Capability boundary
This is a text brief from buyer-pasted material; it does not access a match feed or predict a result.
```

## Verification notes

- **Input traceability:** Every team, score, minute, shape, tactical observation, and bench option in the output is present in the concrete input.
- **Unknowns preserved:** Fitness, cards, roles, workload, possession figures, lineup changes, and later events remain `[UNVERIFIED]`; no substitute, event, statistic, or result is invented.
- **Capability boundary:** The deliverable is self-contained text made from the pasted record. It does not access a match feed, retrieve football data, issue a team instruction, or predict an outcome.
- **Distinct catalog job:** The recurring input is one stated football decision moment plus available options; the output is a conditional change card and commentary line. This differs from the catalog's weekly fixture analysis, pre-match scoreline scenarios, set-piece plan, and post-match decision review.
