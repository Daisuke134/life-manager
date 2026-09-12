# Verified demonstration — Decision Record Consistency Auditor

## Concrete input

```text
Create a reconciliation brief from only these records.

Record A — 2026-08-03, Mobile booking design review
- Decision: The booking flow will store itinerary details on the device for use during travel.
- Scope: mobile booking flow.
- Rationale: travelers can lose connectivity.
- Owner: Mina.

Record B — 2026-08-17, Security review notes
- Decision: Booking details must remain online-only and are not stored on a device.
- Scope: mobile booking flow.
- Rationale: not stated.
- Owner: not stated.

Neither record says it replaces the other. Do not choose a final design.
```

## Actual output

```text
Decision ledger
| source | date | scope | decision | owner | rationale | status |
|---|---|---|---|---|---|---|
| Record A — Mobile booking design review | 2026-08-03 | mobile booking flow | Store itinerary details on the device for use during travel. | Mina | Travelers can lose connectivity. | [STATUS NOT SUPPLIED] |
| Record B — Security review notes | 2026-08-17 | mobile booking flow | Booking details remain online-only and are not stored on a device. | [OWNER NOT SUPPLIED] | [RATIONALE NOT SUPPLIED] | [STATUS NOT SUPPLIED] |

Direct conflicts
| shared scope | Record A statement | Record B statement | finding |
|---|---|---|---|
| mobile booking flow | “store itinerary details on the device” | “remain online-only and are not stored on a device” | [CONFLICT] The supplied decisions prescribe incompatible storage choices for the same scope. |

Ambiguities and missing context
- [PRECEDENCE UNRESOLVED] Neither record says it replaces the other. Record B has a later supplied date, but recency alone is not an authority rule.
- [MISSING OWNER] Record B has no supplied owner.
- [MISSING RATIONALE] Record B has no supplied rationale.
- [MISSING DETAIL] The records do not define which itinerary fields, retention period, or connectivity behavior are in scope.

Reconciliation agenda
1. Which record is authoritative for the mobile booking flow, and does it supersede the other?
2. If device storage is permitted, which itinerary fields and retention period are approved?
3. Who owns the security-review decision and its rationale?

Verification checklist
- Confirm source authority and any supersession statement.
- Confirm the exact data fields and retention requirements.
- Assign an owner to Record B before recording a final resolution.
```

## Verification notes

- The output includes both supplied decisions and retains their supplied dates and scopes.
- It marks the incompatible device-storage instructions as a conflict because they cover the same supplied scope.
- It does not convert Record B's later date into an unsupported supersession rule.
- It leaves Record B's owner and rationale visibly unspecified rather than fabricating them.
- Offline duplicate check: the source catalog contained 23 existing candidates, including decision-deck, risk-register, customer-escalation, research, academic-editing, sales, finance, interview, and script workflows. None compares multiple pasted decision records for conflicts and unresolved precedence.
- Offline `sales_selector.select_signal` readback used those 23 local inventory entries with no invented sales fields: `{"ok": true, "signal": "none", "listings": 23, "company_orders": 0}`. The no-signal outcome is why this listing does not claim a winning category or proven demand.
