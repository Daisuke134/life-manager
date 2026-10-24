# Verified Demonstration — Rugby Contact-Area Brief

## Selection and scope notes

- The local C6 opportunity state was read offline. Its highest-total-sales uncovered item is Analysis: 3,201 observed sales, led by Ocup Football Analysis (3,120), MLB Baseball Analysts (39), and Otata Baseball Analysis (29), observed 2026-10-22.
- The release-owned `sales_selector.py` was invoked only through `select_signal` with 54 current local catalog entries and zero supplied sales fields. It returned `{"ok": true, "signal": "none", "listings": 54, "company_orders": 0}`. No network-fetching selector path, Capafy API, or Capafy UI was called.
- A duplicate scan over the current catalog found no rugby, contact-area, breakdown, or ruck candidate. The catalog does contain association-football, MLB, NBA, NHL, and NFL analysis candidates, so this candidate uses a distinct sport, input packet, output format, and buyer task.

## Concrete input

```text
Match: Estuary RFC v Highland RFC, October 25. The buyer's supplied team-sheet
notes list Estuary's scrum-half as tentative and Highland's openside flanker as
starting. The buyer's match notes say Highland's openside made five breakdown
turnovers in the cited prior report. Estuary lost two lineouts in the buyer's
notes. No phase counts, referee, weather, final team sheets, or current injury
status are supplied.
Coverage goal: a 45-second pre-match podcast introduction.
```

## Actual output

```markdown
# Rugby Contact-Area Brief: Estuary RFC v Highland RFC — October 25

## Evidence boundary
- Supplied: Estuary's scrum-half is tentative; Highland's openside flanker is listed to start.
- Supplied: Highland's openside made five breakdown turnovers in the buyer's cited prior report.
- Supplied: Estuary lost two lineouts in the buyer's notes.
- [UNVERIFIED]: final team sheets, phase counts, referee, weather, current injury status, and the causes of Estuary's lineout losses.

## Contact-area cards
| Area | Supplied evidence | Analysis question | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| Ruck | Highland openside made five listed breakdown turnovers | Can Estuary protect its early possession against the supplied turnover threat? | medium | The report supplies no phase count or comparable Estuary ruck figure. |
| Set piece | Estuary lost two supplied lineouts | Is lineout retention the first platform question for Estuary? | low | Throwing cause, opposition pressure, and final callers are not supplied. |

## Coverage angles
1. Highland's listed turnover work makes early-ball security the lead contact-area question. Caveat: five listed turnovers do not establish a current rate.
2. Estuary's two supplied lineout losses make set-piece retention a qualified second angle. Caveat: cause and present selection are [UNVERIFIED].

## Conditional scenarios
- If Estuary's tentative scrum-half starts: retain the ruck-speed question but do not infer a performance level.
- If the scrum-half changes: confirm the replacement's role before using a tempo angle.

## Verify before using
- Confirm both final team sheets.
- Add phase counts or a supplied Estuary ruck observation.
- Confirm the context of Estuary's two lineout losses.

## 45-second pre-match rundown
The clearest supplied contact-area question is Highland's openside flanker, who the buyer's cited report credits with five breakdown turnovers. That makes Estuary's early-ball security worth watching, although phase counts and a comparable Estuary ruck figure are not supplied. Estuary also has two listed lineout losses to resolve, but the causes and final callers remain unverified. The team sheet matters here: Estuary's scrum-half is tentative, so any tempo angle should stay conditional until the buyer confirms the final selection.
```

## Verification notes

- The output uses exactly one buyer-supplied rugby fixture and adds no current team, score, referee, weather, odds, or injury claim.
- Every match-specific fact is either copied from the input or marked `[UNVERIFIED]`.
- The tentative scrum-half creates conditional scenarios rather than an assumed selection.
- The result is text-only analysis, contains no wagering instruction, and does not promise a match result.
