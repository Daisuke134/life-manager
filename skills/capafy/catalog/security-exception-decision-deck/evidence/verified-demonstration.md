# Verified demonstration — Security Exception Decision Deck

## Concrete input

```text
Build a decision deck from only the supplied material. Do not decide whether to approve the exception.

Exception request
- Research Engineering requests an exception to the endpoint-encryption standard for two lab laptops used with a device driver that the team says fails when full-disk encryption is enabled.
- Requested period: 2026-10-01 through 2026-12-30.
- Scope: two lab laptops in Lab North. Asset identifiers are not supplied.

Endpoint-encryption standard
- All company-managed endpoints must use full-disk encryption.
- An exception may be considered when a documented technical incompatibility exists and an accountable risk owner records an expiry and review date.

Team risk note
- The driver failure was observed during a lab test on 2026-09-12.
- The note does not include test logs, affected operating-system version, or a risk rating.

Proposed compensating measures
- Keep the two laptops in a locked Lab North cabinet when not in use.
- Perform a weekly inventory check.
- Restrict use to the Lab North network.

Owner comments
- Priya is the Research Engineering owner.
- No accountable risk owner, reviewer, approval record, or review date is supplied.
```

## Actual output

```text
Slide 1 — Decision summary
Requested reviewer decision: consider a temporary exception to the endpoint-encryption standard for two Research Engineering lab laptops in Lab North from 2026-10-01 through 2026-12-30.

The supplied request says full-disk encryption causes a device-driver failure. The supplied material does not include asset identifiers, test logs, an operating-system version, a risk rating, an accountable risk owner, a reviewer, an approval record, or a review date.

Slide 2 — Control and exception map
| supplied control requirement | supplied exception rationale | supplied status | reviewer question |
|---|---|---|---|
| All company-managed endpoints must use full-disk encryption. | Research Engineering says a device driver fails when full-disk encryption is enabled. | Technical incompatibility is asserted; the request does not include logs or the operating-system version. | Does the documented technical incompatibility meet the exception standard, and where is the supporting evidence? |
| An exception may be considered when a documented technical incompatibility exists and an accountable risk owner records an expiry and review date. | Requested period is 2026-10-01 through 2026-12-30. | An expiry is supplied. No accountable risk owner or review date is supplied. | Who is the accountable risk owner, and what review date will be recorded? |

Slide 3 — Risk and compensating-measure status
| item | supplied statement | status |
|---|---|---|
| Driver failure | Observed during a lab test on 2026-09-12. | Stated; no test logs or operating-system version supplied. |
| Risk rating | No rating supplied. | Open question. |
| Locked storage | Keep the laptops in a locked Lab North cabinet when not in use. | Proposed measure; operating evidence is not supplied. |
| Weekly inventory | Perform a weekly inventory check. | Proposed measure; owner and record are not supplied. |
| Network restriction | Restrict use to the Lab North network. | Proposed measure; enforcement detail is not supplied. |

Slide 4 — Dates and approval checkpoints
- Requested start: 2026-10-01.
- Requested expiry: 2026-12-30.
- Review date: not supplied.
- Research Engineering owner: Priya.
- Accountable risk owner, reviewer, and approval record: not supplied.

Before a reviewer records a decision, confirm the incompatibility evidence, the two asset identifiers, the accountable risk owner, the review date, the risk rating, and whether each proposed measure will operate as described.

Slide 5 — Open questions
1. Which two asset identifiers are in scope?
2. What test logs and operating-system version document the driver incompatibility?
3. Who is the accountable risk owner required by the standard?
4. What review date will accompany the supplied expiry?
5. What risk rating applies, and who assigned it?
6. Who owns the weekly inventory check, and where will it be recorded?
7. How will the Lab North network restriction be enforced?

Reviewer checklist
- Verify the supplied driver-failure evidence before treating the incompatibility as documented.
- Confirm the specific assets and whether they are company-managed endpoints.
- Confirm an accountable risk owner, review date, and any approval record.
- Confirm the feasibility and ownership of each proposed compensating measure.
- Record the final decision outside this deck only after the accountable reviewer verifies the missing information.
```

## Verification notes

- The output preserves the supplied request period, scope, driver-failure observation date, standard language, and named engineering owner.
- It labels storage, inventory, and network restrictions as proposed because the input supplies proposals rather than evidence that they operate.
- It does not claim the exception is approved, compliant, low risk, or implemented; the missing risk owner, review date, evidence, and approval record remain explicit questions.
- Offline duplicate check: the current source catalog contains academic-editing, research, sales, portfolio, football, interview, decision-record, RFP, and several deck workflows. None turns a pasted security-control exception into a source-linked decision deck that separately tracks technical evidence, compensating-measure status, expiry, and accountable approval questions.
- Offline selector readback: `sales_selector.select_signal` was run against the 25 pre-existing catalog entries with no invented sales values; it returned `signal: "none"` and advised against fabricating a winner. The local cached output previously produced by `sales_selector.py` names “Slide Maker — Any Content Into a Styled Deck” as the official seller winner and advises building the next skill in the same customer-job category/style. This candidate therefore uses a deck format, while making no direct-demand or sales claim for security-exception work.
