# Verified demonstration — Delivery Commitment Evidence Ledger

## Concrete input

```text
Build a delivery-commitment evidence ledger from only these excerpts.

Order Form — 2026-09-01
- Commitment: Acme will provide a daily delivery-status file by 09:00 JST on each business day.
- Acceptance wording: Each file includes order ID, current delivery state, and the report date.
- Owner: Operations lead.

Implementation update — 2026-09-12
- The delivery-status file layout is approved internally.
- The team plans to begin producing the file on 2026-09-15.
- Owner: Kai.

Sample record — 2026-09-16
- Report date: 2026-09-16.
- Order ID: A-104.
- Current delivery state: dispatched.

No other records are supplied. Do not decide whether the order form is enforceable or whether Acme breached it.
```

## Actual output

```text
Commitment ledger
| ID | source | stated commitment | timing | owner | acceptance wording |
|---|---|---|---|---|---|
| C-01 | Order Form — 2026-09-01 | Provide a daily delivery-status file. | By 09:00 JST on each business day. | Operations lead. | Each file includes order ID, current delivery state, and the report date. |

Evidence-status table
| commitment | supplied material | finding | basis |
|---|---|---|---|
| C-01 daily file | Implementation update — 2026-09-12 | NOT EVIDENCE OF COMPLETION | The update says the layout is approved internally and the team plans to begin producing the file; it does not state that a file was delivered by the required time. |
| C-01 acceptance wording | Sample record — 2026-09-16 | PARTIAL | The supplied sample contains a report date, order ID, and current delivery state. The excerpt does not state its delivery time or establish that a file was provided on every business day. |

Gaps and unknowns
- [UNKNOWN DELIVERY TIME] No supplied material shows whether the 2026-09-16 sample was available by 09:00 JST.
- [UNKNOWN DAILY COVERAGE] No supplied material covers the other business days in the period.
- [OWNER QUESTION] The order form names “Operations lead,” while the implementation update names Kai. The supplied excerpts do not state whether Kai is the Operations lead or owns C-01.

Verification queue
1. Operations lead: provide the delivery timestamps for each business-day file in the review period.
2. Operations lead: provide a record or index showing daily coverage, including dates without a sample excerpt.
3. Kai or Operations lead: confirm the accountable owner for C-01.

Delivery-check-in brief
The supplied material supports that the 2026-09-16 sample contains all three named fields. It does not establish the required delivery time, daily coverage, or accountable-owner relationship. No conclusion is made about enforceability, acceptance, or breach.
```

## Verification notes

- The output preserves the exact supplied commitment, timing, owner label, and three supplied acceptance fields.
- It treats the implementation update as a plan rather than proof of completed delivery because the update does not state that a file was provided by the required time.
- It marks the sample as partial support because its three fields are present while timing and recurring coverage are not supplied.
- It leaves the owner relationship, delivery time, and daily coverage as unknown rather than inventing a status.
- Offline duplicate check: the 25-candidate origin/main catalog included RFP response, sustainability-disclosure, decision-record, risk-register, and customer-escalation workflows. None is a post-agreement ledger that separates pasted delivery commitments, acceptance wording, plans, and delivery evidence.
- Offline `sales_selector.select_signal` readback used the 25 local catalog entries with no invented sales fields: `{"ok": true, "signal": "none", "listings": 25, "company_orders": 0}`. The no-signal outcome is why this listing makes no winner or demand claim.
