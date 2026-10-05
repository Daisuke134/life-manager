# Verified demonstration — Customer Renewal Evidence Brief

## Offline selection record

The release-owned `sales_selector.py` was used without its network-fetching entry
point. Its pure `select_signal` function received the current local source catalog:
26 rows, one for each catalog candidate, all with `sales: 0`, `recentSales: 0`,
`rating: 0`, and `reviewCount: 0`; `company_orders` was `0`. It returned:

```json
{"advice":"No company or Agent-level sales signal is observable. Do not fabricate a winner; use marketplace research for the next differentiated candidate.","company_orders":0,"listings":26,"ok":true,"signal":"none"}
```

No Capafy API, UI, or platform state was called or modified. The source and release
catalogs were searched for `renewal risk`, `renewal brief`, `customer renewal`, and
`retention risk`. The only related result was a boundary in the existing Customer
Escalation Decision Deck that says it does not forecast renewal risk; no renewal
evidence-brief candidate was present.

## Concrete input

```text
Account: Northstar Health
Renewal date: 2026-09-30
Period covered: last 14 days
Next customer touchpoint: 2026-09-18 QBR follow-up

Account notes:
- Active seats changed from 25 to 17 during the period.
- Three support tickets reported export errors.
- The executive sponsor said that budget approval is pending.
- The customer cancelled the scheduled QBR.
- The customer requested a revised administrator guide.
- Support expects a patch on Wednesday, but no completion has been confirmed.
- Mia is the account owner.

No contract terms, cause of the seat change, patch date, meeting reason, renewal
intent, or completed action was supplied.
```

## Actual output

### Renewal-preparation summary

**Northstar Health** has a supplied renewal date of **2026-09-30**. The next supplied
touchpoint is a **2026-09-18 QBR follow-up**. The record contains an activity change,
three customer-support reports, a pending-budget statement, a cancelled QBR, and an
administrator-guide request. It does not establish the reason for the activity
change, renewal intent, contract terms, or a completed patch.

### Signal table

| Area | Supplied signal | Status | What remains unknown |
|---|---|---|---|
| Adoption | Active seats changed from 25 to 17 in 14 days. | observed | Reason for the change and whether it will continue. |
| Support | Three tickets reported export errors. | observed | Cause, affected scope, and whether any issue is resolved. |
| Stakeholder | Executive sponsor said budget approval is pending. | customer-reported | Approval outcome and timing. |
| Engagement | The customer cancelled the scheduled QBR. | observed | Reason for cancellation and a replacement meeting time. |
| Request | Customer requested a revised administrator guide. | customer-reported | Owner, delivery date, and whether it has been delivered. |
| Planned work | Support expects a patch on Wednesday. | planned | Patch date, completion, and customer effect. |

### Action register

| Action | Status | Owner | Date |
|---|---|---|---|
| Prepare a revised administrator guide. | requested; completion not supplied | [TBD] | [TBD] |
| Patch export errors. | expected, not confirmed | [TBD] | Wednesday; exact date not supplied |
| Conduct QBR follow-up. | next touchpoint | Mia | 2026-09-18 |

### Conversation agenda and verification queue

1. Confirm what changed in the active-seat count and whether the customer expects it to change again.
2. Ask whether budget approval has an owner, a decision date, and any requested information.
3. Confirm the status, scope, and customer impact of the export-error patch before describing it as complete.
4. Agree a replacement QBR time and ask what the customer wants covered.
5. Confirm who owns the administrator guide and its requested delivery date.
6. Do not state a renewal forecast or account-health conclusion: the supplied record does not establish either.

### Evidence ledger

| Material statement | Classification | Supplied basis |
|---|---|---|
| Active seats changed from 25 to 17. | observed | Account notes |
| Three tickets reported export errors. | observed | Account notes |
| Budget approval is pending. | customer-reported | Executive sponsor statement |
| A patch will resolve the errors. | needs verification | No confirmed outcome supplied |
| The customer will renew. | unknown | No renewal intent supplied |

## Verification notes

1. Every named account fact, count, person, date, and request in the output is present in the concrete input.
2. The seat change and cancelled QBR are retained as observations; the output does not infer their cause or a renewal outcome.
3. The budget comment is labeled `customer-reported`, and the patch is labeled `planned`, not completed.
4. Missing owners, dates, contract terms, resolution status, renewal intent, and account health remain unknown or `[TBD]`.
5. The result is text only. It does not inspect systems, contact a customer, create a forecast, or make an external change.
