# Sales Account Plan Deck — verified demonstration

## Offline selection notes

No Capafy API or UI was called. The local sales-selector cache records the official
seller winner as `Slide Maker — Any Content Into a Styled Deck`, with a $9.99
weekly subscription and `signal: sales`. The current local candidate-inventory cache
lists deck candidates for experiments, customer escalations, research, and talent
reviews, and a sales-objection reply writer; it does not list a sales account-plan
deck. The candidate therefore follows the measured deck format for a distinct,
input-only sales account-planning job.

## Concrete input

```text
Account: Northstar Logistics
Opportunity: Operations-workflow pilot discussion.

Buyer roles and discovery:
- Priya, Operations Director: said the team spends time reconciling handoff notes.
- Marco, Security Lead: asked whether customer data can remain in the buyer's existing environment.
- No economic buyer or decision process was supplied.

Supplied proof and constraints:
- Buyer-provided baseline: 18 handoffs per week across two teams.
- Our case-study note: another customer reduced its handoff-review time by 25% after a process change.
- No evidence says Northstar will see the same result.
- Security documentation has not yet been supplied.

Risk and next meeting:
- Known objection: Marco needs the security material before a pilot discussion.
- Next meeting: Tuesday, 2026-09-22, with Priya and Marco.
- Requested internal decision: decide whether to propose a pilot agenda or first return with security evidence.
- Owner supplied: Elena for the meeting preparation. No due date supplied.
```

## Actual output

```text
ACCOUNT-PLAN BRIEF
Account: Northstar Logistics.
Decision required: decide whether to propose a pilot agenda or first return with
security evidence. Supplied opportunity context is an operations-workflow pilot
discussion. Unknowns: economic buyer, decision process, Northstar-specific outcome,
security documentation, and a due date for Elena.

EVIDENCE LEDGER
| Statement | Status | Supplied basis |
| Priya says the team spends time reconciling handoff notes. | BUYER-REPORTED | Priya discovery note |
| Northstar has 18 handoffs per week across two teams. | SUPPLIED | Buyer-provided baseline |
| Marco needs security material before a pilot discussion. | BUYER-REPORTED | Known objection |
| Another customer reduced handoff-review time by 25%. | SUPPLIED | Case-study note |
| Northstar will reduce handoff-review time by 25%. | [UNVERIFIED] | No Northstar result supplied |
| Security evidence should be returned before a pilot agenda. | HYPOTHESIS | Decision option based on the stated objection |

SEVEN-SLIDE OUTLINE
1. Account decision — “What must Northstar see before a pilot discussion?”
   Takeaway: The next-step choice is security evidence versus a pilot agenda.
   Evidence: requested internal decision and Marco's stated question.
   Visual: two-path decision card.
2. Account context — operations-workflow pilot discussion.
   Takeaway: The supplied baseline is 18 handoffs per week across two teams.
   Evidence: buyer-provided baseline. Visual: two-team workflow sketch.
3. Buyer goals — Priya reports time spent reconciling handoff notes.
   Takeaway: This is a buyer-reported problem, not a measured time total.
   Evidence: Priya discovery note. Visual: statement-and-evidence card.
4. Stakeholders — Priya and Marco have supplied priorities; economic buyer is [UNVERIFIED].
   Takeaway: Security material is an explicit dependency for Marco.
   Evidence: discovery notes. Visual: stakeholder matrix.
5. Proof and limits — the case-study note describes another customer, not Northstar.
   Takeaway: Do not transfer the 25% result to this account.
   Evidence: case-study note and missing Northstar result. Visual: proof-versus-gap split.
6. Options — first return with security evidence, or propose a pilot agenda while
   marking security as unresolved. Takeaway: Elena chooses the acceptable dependency risk.
   Evidence: Marco's objection and requested decision. Visual: two-row option matrix.
7. Next-meeting plan — Tuesday, 2026-09-22, with Priya and Marco.
   Takeaway: Elena owns preparation; due date is [TBD].
   Evidence: supplied meeting and owner. Visual: meeting-preparation checklist.

STAKEHOLDER-AND-EVIDENCE MATRIX
| Role | Supplied priority | Evidence | Unknown |
| Priya, Operations Director | Reduce time spent reconciling handoff notes | Buyer-reported discovery note | Decision authority |
| Marco, Security Lead | Review whether customer data can remain in the buyer's environment | Buyer-reported question | Required security criteria |

ACTION REGISTER
| Action | Status | Owner / date |
| Decide whether security evidence precedes a pilot agenda. | decision required | Elena / [TBD] |
| Obtain or prepare security documentation. | [UNVERIFIED] dependency | [TBD] / [TBD] |
| Prepare Tuesday meeting material for Priya and Marco. | supplied next meeting | Elena / 2026-09-22 |
```

## Verification notes

1. Every account name, role, date, number, meeting fact, owner, and requested decision in the output appears in the concrete input.
2. The 25% case-study result remains attributed to another customer; the output marks a Northstar result `[UNVERIFIED]`.
3. The output labels Priya's and Marco's statements as buyer-reported and does not infer buyer intent, authority, a commitment, a forecast, or a deal outcome.
4. Missing security material, economic buyer, decision process, and Elena's due date remain unknown or `[TBD]`.
5. The result is structured text only. It does not create, export, send, or update a presentation, CRM, account, or external system.
