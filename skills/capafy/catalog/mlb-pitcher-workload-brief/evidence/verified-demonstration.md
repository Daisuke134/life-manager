# Verified Demonstration — MLB Pitcher Workload Brief

## Concrete input

```text
pitcher_and_start: Harbor RHP Reyes; buyer's next-start label is "next Harbor game".
recent_outing_log: Six days ago Reyes threw 96 pitches over 6 innings. One day before
that outing he threw 82 pitches over 5 innings. In the latest supplied log he left
after 5 innings; no reason, pitch count, or date is supplied.
rest_and_plan_notes: The buyer supplies no stated pitch limit, medical note, rotation
decision, or current availability.
editorial_question: Write a 45-second preview of what workload question matters for
Reyes's next start.
supporting_evidence: None.
```

## Actual output

```markdown
# MLB Pitcher Workload Brief: Harbor RHP Reyes — next Harbor game

## Evidence boundary
- Supplied: Reyes threw 96 pitches over 6 innings six days before the named next-start label.
- Supplied: Reyes threw 82 pitches over 5 innings one day before that 96-pitch outing.
- Supplied: the latest supplied log says he left after 5 innings.
- [UNVERIFIED]: the latest outing's date and pitch count, the reason for the early exit, a stated pitch limit, medical status, rotation decision, and current availability.

## Outing ledger
| Supplied outing | Workload | Note | Limitation |
| --- | --- | --- | --- |
| Six days before next-start label | 6 innings, 96 pitches | Buyer-supplied prior outing | No later workload plan is supplied. |
| One day earlier | 5 innings, 82 pitches | Buyer-supplied prior outing | No broader baseline is supplied. |
| Latest supplied log | 5 innings | Buyer says the outing ended after five innings | Date, pitch count, and exit reason are [UNVERIFIED]. |

## Workload read
- Documented signals: the supplied record contains consecutive 82-pitch and 96-pitch outings, followed by a five-inning latest log with no stated reason for the exit.
- Interpretation: The recent pitch totals make workload context worth discussing, but the record does not establish fatigue, a restriction, or a plan for the next start.
- Confidence: medium.
- Limitation: The latest pitch count, rest interval, and exit reason are absent.

## Conditional editorial thresholds
1. **Early workload check:** If the buyer confirms that the five-inning exit had a workload-related reason, an early pitch-count check is a supported preview angle. Caveat: no reason is supplied now. This changes if the buyer supplies a different exit explanation.
2. **Normal-length possibility:** If the buyer confirms a normal rest interval and no stated limit, the prior 96-pitch outing can be described as context rather than a restriction. Caveat: the record gives no current plan. This changes if a stated limit is supplied.

## Coverage narrative
Reyes's supplied record gives the preview a real workload question: it includes 82- and 96-pitch outings before a latest five-inning log. What that last exit means is not in the record, so the responsible framing is to watch for confirmation of the pitch count, rest interval, and team plan—not to report a restriction or an injury.

## Verify before using
- Confirm the latest outing's date, pitch count, and exit reason.
- Confirm the rest interval before the named next start.
- Add any buyer-supplied pitch limit or availability note.
```

## Verification notes

- **Input traceability:** Every inning total, pitch total, sequence statement, and missing-field label in the output is taken from the concrete input.
- **Unknowns preserved:** The exit reason, latest pitch count and date, rest interval, medical status, rotation decision, and availability remain `[UNVERIFIED]`; none is inferred.
- **Capability boundary:** This is self-contained text reasoning from a pasted record. It does not access a game feed, retrieve baseball data, report a current pitching plan, place a wager, or promise an outcome.
- **Distinct catalog job:** Its recurring input is a recent outing log and rest context; its output is a workload ledger and conditional editorial thresholds, rather than a lineup matchup, series preview, postgame turning-point recap, or in-game decision card.
