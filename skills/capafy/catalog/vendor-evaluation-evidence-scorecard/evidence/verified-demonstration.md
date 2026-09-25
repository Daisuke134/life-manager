# Verified Demonstration — Vendor Evaluation Evidence Scorecard

## Concrete input

```text
Evaluation: Northstar support-platform shortlist
Scoring scale: 0 = absent, 1 = partial or ambiguous, 2 = directly stated.
Weights: SSO = 3; annual subscription under $60,000 = 3; CSV export = 2; signed DPA = 1.
Non-negotiables: SSO and annual subscription under $60,000.

Vendor Beacon proposal excerpt:
- “SAML SSO is included in the standard plan.”
- “Annual subscription: $54,000. Implementation services are scoped separately.”
- “Administrators can export case lists as CSV.”
- No DPA statement was supplied.

Vendor Cascade proposal excerpt:
- “SAML SSO is available in Enterprise.”
- “Enterprise annual subscription: $72,000.”
- “CSV export is available for cases and reports.”
- “We will provide our standard DPA for review.”
```

## Actual output

# Northstar support-platform shortlist — evidence scorecard

## Scoring basis

- Scale: 0 = absent; 1 = partial or ambiguous; 2 = directly stated.
- Weighted score: criterion score × supplied weight.
- The annual-price criterion concerns the supplied annual subscription only. Implementation services are a separate unresolved item for Beacon.

## Comparison

| Criterion | Weight | Beacon evidence and score | Cascade evidence and score |
|---|---:|---|---|
| SSO | 3 | “SAML SSO is included in the standard plan.” Score 2 × 3 = 6. | “SAML SSO is available in Enterprise.” Score 2 × 3 = 6. |
| Annual subscription under $60,000 | 3 | “Annual subscription: $54,000.” Score 2 × 3 = 6. Implementation services are separately scoped. | “Enterprise annual subscription: $72,000.” Score 0 × 3 = 0. |
| CSV export | 2 | “Administrators can export case lists as CSV.” Score 2 × 2 = 4. | “CSV export is available for cases and reports.” Score 2 × 2 = 4. |
| Signed DPA | 1 | `[NOT SUPPLIED]` Score 0 × 1 = 0. | “We will provide our standard DPA for review.” Score 1 × 1 = 1 because a signed DPA was not stated. |
| **Weighted total** |  | **16** | **11** |

## Non-negotiables

| Requirement | Beacon | Cascade | Evidence or gap |
|---|---|---|---|
| SSO | SUPPORTED | SUPPORTED | Both proposals directly state SAML SSO availability. |
| Annual subscription under $60,000 | SUPPORTED for the stated subscription; implementation scope unresolved | CONFLICTS WITH SUPPLIED TEXT | Beacon states $54,000 annual subscription; Cascade states $72,000 Enterprise annual subscription. |

## Evidence-gap ledger

| Vendor | Open item | Why unresolved | Follow-up question |
|---|---|---|---|
| Beacon | Implementation-services cost and scope | The proposal says services are scoped separately but gives no amount or scope. | What implementation work, price, and assumptions apply to Northstar? |
| Beacon | DPA | No DPA statement was supplied. | Can you provide the proposed DPA and identify the signing process? |
| Cascade | DPA status | The proposal offers a DPA for review but does not state it is signed. | What remains before the DPA can be signed, and who owns each step? |

## Conditional options

1. `[CONDITIONAL OPTION]` Keep Beacon as the leading evidence score only if the accountable buyer confirms that its implementation scope and cost fit the approved budget and the DPA process is acceptable.
2. `[CONDITIONAL OPTION]` Keep Cascade in consideration only if the stated $72,000 annual subscription can be reconciled with the under-$60,000 non-negotiable by an accountable buyer; the supplied record currently conflicts with that requirement.

## Review agenda

1. Confirm Beacon’s implementation price and scope because that information is absent from the supplied record and can affect the cost decision.
2. Confirm the DPA process for both vendors before treating either record as complete.
3. Confirm whether the annual-subscription non-negotiable is fixed; Cascade’s stated price conflicts with it.

## Verification notes

- The four criteria, weights, and non-negotiables are copied from the concrete input.
- Each vendor statement in the comparison is quoted from the supplied excerpts; the only arithmetic is shown as score × supplied weight.
- Beacon’s implementation and DPA fields remain unresolved because the input does not provide them.
- Cascade’s DPA receives partial support rather than direct support because the input says it will be provided for review, not that it is signed.
- The output calls Beacon a leading evidence score only conditionally and keeps final budget, contract, and approval decisions with the accountable buyer.
- No vendor system, external record, automatic action, or fact outside the concrete input is represented as used.
