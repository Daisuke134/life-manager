# Verified demonstration — Sustainability Disclosure Evidence Deck

## Concrete input

```text
Create a six-slide internal evidence deck from only the material below.

Reporting scope: Tokyo office, FY2025. Audience: reporting steering group.

Criterion A — Energy use
The review checklist asks for annual electricity use, the reporting boundary,
the unit, and a source label.

Evidence A1 — Facilities meter summary
Tokyo office electricity use in FY2025: 120 MWh.
Source: Facilities meter summary, 2026-01-12.
Calculation method: not supplied.
Owner: Reina, Facilities.

Criterion B — Supplier screening
The review checklist asks for evidence that in-scope suppliers were screened.

Evidence B1
No supplier-screening material is attached.
Owner: not supplied.

Do not state that either criterion satisfies a law, standard, or assurance process.
Do not invent a supplier count, calculation method, or reporting conclusion.
```

## Actual output

```text
Slide 1 — Review purpose and supplied scope
- Purpose: review coverage of two supplied sustainability-reporting criteria.
- Reporting boundary: Tokyo office.
- Reporting period: FY2025.
- Audience: reporting steering group.
- Boundary note: This deck evaluates only the pasted material; it makes no compliance or assurance conclusion.

Slide 2 — Criterion-to-evidence matrix
| criterion | supplied evidence | coverage | source / owner |
|---|---|---|---|
| A — Energy use | Tokyo office electricity use: 120 MWh in FY2025. | Partial | Facilities meter summary, 2026-01-12 / Reina, Facilities |
| B — Supplier screening | No material supplied. | Missing | Owner not supplied |

Slide 3 — Energy-use evidence review
- Supported: the supplied energy-use value is 120 MWh for the Tokyo office in FY2025.
- Supported: the source label is “Facilities meter summary, 2026-01-12.”
- Open item: the calculation method was not supplied.
- Reviewer question: Does the stated Tokyo-office boundary match the boundary required by Criterion A?

Slide 4 — Supplier-screening evidence review
- Missing: no supplier-screening evidence was supplied for Criterion B.
- Missing: no owner was supplied for the evidence request.
- Evidence request: assign an owner and provide the in-scope supplier definition and the screening record, if available.

Slide 5 — Decisions and ownership
| decision or request | supplied owner | status |
|---|---|---|
| Confirm the calculation method for the 120 MWh value. | Reina, Facilities | Open |
| Confirm boundary fit for Criterion A. | No owner supplied | Open |
| Supply screening evidence and an owner for Criterion B. | No owner supplied | Open |

Slide 6 — Verification checklist
- Confirm that FY2025 and the Tokyo-office boundary are the intended reporting scope.
- Verify the source record and calculation method for 120 MWh.
- Assign an accountable owner for Criterion B.
- Have accountable reporting and legal reviewers determine whether the final report meets any applicable requirements.
```

## Verification notes

- The output preserves the supplied value (`120 MWh`), period (`FY2025`), boundary (`Tokyo office`), source label, and supplied owner.
- It labels Criterion A as partial because the requested calculation method was not supplied; it does not infer one.
- It labels Criterion B as missing because no evidence or owner was supplied, and it converts that absence into an evidence request.
- It does not assert compliance, assurance, legal applicability, or access to information beyond the pasted input.
- Offline duplicate check: the current source catalog has 26 candidates spanning academic editing, sales, RFP response, decision reconciliation, interview synthesis, portfolio review, football analysis, and several decision-deck workflows. None maps pasted sustainability disclosure criteria to internal evidence and an evidence-review deck; the closest RFP matrix is a buyer-response workflow, while this candidate is an internal reporting-evidence workflow.
- Offline inventory readback: local state recorded 45 observed listings and 40 listed listings at `2026-09-20T15:30:22Z`. No platform endpoint or UI was called in this pass.
- Offline selector readback: the release-owned `sales_selector.select_signal` was invoked only through its pure function with 45 local inventory slots (no Agent sales values) and the locally cached official seller record. It returned `{"ok": true, "signal": "sales", "listings": 45, "company_orders": 10, "attribution_status": "official_seller_ranking", "winner": {"agent_id": "8828622062", "name": "Slide Maker — Any Content Into a Styled Deck", "revenue_kind": "subscription", "sales_usd": "9.99", "sku_type": "subscription_week", "source": "official_publisher_console"}}`. The candidate follows the successful deck format without claiming direct demand for sustainability disclosure work or treating one subscription sale as MRR proof.
