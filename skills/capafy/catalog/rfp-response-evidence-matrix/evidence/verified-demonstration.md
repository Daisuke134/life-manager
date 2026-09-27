# Verified demonstration — RFP Response Evidence Matrix

## Concrete input

```text
Create a response-planning matrix from only the text below. Do not add facts.

Buyer requirements
1. Confirm that the platform supports SAML SSO.
2. Confirm a 99.9% monthly service commitment.
3. State whether the implementation can finish in 30 days.
4. Describe how customer data is exported at contract end.

Company product brief
- SAML 2.0 single sign-on is available on the Enterprise plan.
- The Enterprise plan includes an administrator-controlled CSV export for workspace records.

Implementation note
- A typical Enterprise implementation takes four to six weeks after the required customer contacts are available.

No supplied material states a service commitment. No supplied material defines which data is included in an export at contract end.
```

## Actual output

```text
Requirement-and-evidence matrix
| # | buyer requirement | supplied evidence | status | cautious draft response | owner question |
|---|---|---|---|---|---|
| 1 | Confirm SAML SSO. | Product brief: “SAML 2.0 single sign-on is available on the Enterprise plan.” | SUPPORTED | SAML 2.0 single sign-on is available on the Enterprise plan. | Confirm that the proposed plan is Enterprise. |
| 2 | Confirm a 99.9% monthly service commitment. | No supplied statement. | GAP | [NO DRAFT CLAIM] | Is there an approved service commitment, and which document states it? |
| 3 | State whether implementation can finish in 30 days. | Implementation note: “A typical Enterprise implementation takes four to six weeks after the required customer contacts are available.” | PARTIALLY SUPPORTED | The supplied implementation note describes a typical four-to-six-week Enterprise implementation after required customer contacts are available. It does not confirm a 30-day completion. | Can the accountable implementation owner approve a 30-day commitment for this buyer and scope? |
| 4 | Describe data export at contract end. | Product brief: “administrator-controlled CSV export for workspace records.” | PARTIALLY SUPPORTED | The Enterprise plan includes an administrator-controlled CSV export for workspace records. The supplied material does not define the contract-end process or the complete export contents. | Which records are included, and is there an approved contract-end export process? |

Red flags
- Do not state a 99.9% service commitment: no supplied evidence supports it.
- Do not promise a 30-day implementation: the supplied timing is typical, not a commitment.
- Do not describe a full contract-end export process or data set: only an administrator-controlled CSV export for workspace records is supplied.

Prioritized verification queue
1. Service owner: provide the approved service-commitment wording or confirm that none may be stated.
2. Implementation owner: approve, revise, or reject a 30-day commitment for this scope.
3. Product or legal owner: identify the records and approved process for export at contract end.
4. Sales owner: confirm that the buyer will receive the Enterprise plan before using the SAML statement.

Readiness summary
- Supported: 1
- Partially supported: 2
- Gap: 1
- Question: 0
- The matrix organizes supplied evidence and open questions; it does not decide whether to submit a response.
```

## Verification notes

- The SAML row repeats the supplied Enterprise-plan statement and asks the sales owner to verify the plan before use.
- The service-commitment row contains no claim because the input explicitly supplies none.
- The timeline row preserves the supplied four-to-six-week qualification and does not recast it as a 30-day promise.
- The export row limits its statement to the supplied CSV-export detail and leaves contract-end specifics open.
- Offline duplicate check: the source catalog contained 24 candidates spanning academic editing, decision reconciliation, research and board decks, sales plans and objections, interviews, finance, football, and scripts. None maps a pasted RFP requirement to pasted evidence, cautious buyer wording, and an internal verification queue.
- Offline `sales_selector.select_signal` policy was applied without calling its networked fetch path: local inventory had 24 entries and no supplied sales fields, yielding the selector's documented no-signal outcome: `{"ok": true, "signal": "none", "listings": 24, "company_orders": 0}`. The listing therefore makes no winner or proven-demand claim.
