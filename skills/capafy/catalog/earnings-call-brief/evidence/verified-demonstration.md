# Verified offline demonstration — Earnings Call Brief

## Concrete input

```text
company_or_subject: Northstar Systems
reporting_period: Q2 FY2026
transcript_or_letter: "We reported second-quarter revenue of $42 million, compared with $38 million in Q2 FY2025. Gross margin was 61%. We are seeing renewal timing move some enterprise deals into Q3. We continue to invest in implementation staffing."
supplied_figures: "Revenue: $42m in Q2 FY2026; $38m in Q2 FY2025. Gross margin: 61%. No cash flow, customer count, guidance range, or value of delayed renewals supplied."
prior_period_context: "None supplied beyond the prior-year revenue comparison."
reader_goal: Prepare neutral internal questions before the team discusses the quarter.
constraints: Do not give a recommendation, estimate a share price, add market information, or treat management comments as verified outcomes.
```

## Actual output

# Earnings Call Brief: Northstar Systems — Q2 FY2026

## Evidence boundary

- Supplied: Q2 FY2026 revenue was $42 million; the pasted comparison gives Q2 FY2025 revenue as $38 million.
- Supplied: Gross margin was 61%.
- Management statement: renewal timing moved some enterprise deals into Q3.
- Management statement: the company continues to invest in implementation staffing.
- Unknown: cash flow, customer count, guidance range, the value of the renewals, and the timing within Q3 are `[UNVERIFIED]`.

## Executive readout

- Reported: the pasted revenue comparison changes from $38 million in Q2 FY2025 to $42 million in Q2 FY2026.
- Reported: the supplied gross-margin figure is 61%; no prior margin comparison was supplied.
- Stated driver: management attributed movement of some enterprise deals to renewal timing; this is a management statement, not a verified outcome.
- Open point: the pasted record does not quantify how much revenue moved into Q3 or provide a guidance range.

## Fact ledger

| Topic | Pasted evidence | Classification | Caveat |
| --- | --- | --- | --- |
| Revenue | "$42 million" in Q2 FY2026 versus "$38 million" in Q2 FY2025 | Supplied reported figure | No segment, currency policy, or reconciled bridge supplied |
| Gross margin | "61%" | Supplied reported figure | No prior-period margin supplied |
| Enterprise renewals | "some enterprise deals into Q3" | Management statement | Amount, customers, and Q3 timing are `[UNVERIFIED]` |
| Staffing | "invest in implementation staffing" | Management statement | Spend, headcount, and intended effect are `[UNVERIFIED]` |

## Changes and stated drivers

| Topic | Change | Stated driver | Evidence status |
| --- | --- | --- | --- |
| Revenue | $42m versus $38m in the pasted prior-year comparison | No driver stated for the reported revenue comparison | Reported comparison supplied; driver `[UNVERIFIED]` |
| Enterprise renewals | Some deals described as moving into Q3 | Renewal timing | Management statement; value and outcome `[UNVERIFIED]` |
| Implementation staffing | Continued investment stated | No operating rationale stated | Management statement; amount `[UNVERIFIED]` |

## Questions for the next review

1. What revenue value, customer count, or contract timing is included in “some enterprise deals”?
2. Does the company define the $42 million revenue figure as reported, constant-currency, or another measure?
3. What was gross margin in the comparable period, and what factors explain any change?
4. What portion of implementation staffing is current spend versus planned hiring?
5. Is there a supplied Q3 guidance range or condition that would let the renewal-timing statement be assessed later?

## Boundary note

This is a summary of the pasted material, not investment advice or current market information.

## Verification notes

- This demonstration was authored and checked offline: no Capafy API, UI, model call, browser, or remote platform action was used.
- Every number and management statement in the output appears in the concrete input. The calculated difference is deliberately not presented as an independently verified performance conclusion.
- The output distinguishes supplied reported figures from management statements and labels every absent fact `[UNVERIFIED]`.
- It gives no recommendation, price, forecast, current-news claim, or claim that it accessed filings or market data.
