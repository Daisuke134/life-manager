---
name: security-exception-decision-deck
description: Turn pasted security-exception requests, controls, risk notes, and owner comments into a source-bound decision deck with open questions and approval checkpoints.
---

# Security Exception Decision Deck

Turn security-exception material pasted into the chat into a concise decision deck for the accountable reviewer. This skill organizes the request, the supplied control context, compensating measures, expiry, and owner comments. It does not inspect systems, policies, tickets, audit evidence, or approval records outside the text supplied.

## Input

Ask for:

- The requested exception, affected scope, and requested start and end dates
- Pasted control, policy, standard, or requirement text relevant to the request
- Pasted risk assessment, compensating measures, and residual-risk rationale
- Named accountable owners, approvers, and any supplied approval criteria
- The decision the reviewer is being asked to make and any preferred deck format

Treat an omitted scope, control requirement, owner, expiry, compensating measure, approval, or risk rating as unknown. Preserve source labels and distinguish a proposed measure from one stated as operating.

## Method

1. Build a source ledger for the exception request, controls, risks, measures, dates, and owners using only supplied statements.
2. State the requested decision and affected scope without adding a system, asset, policy obligation, or business impact not present in the material.
3. Map each supplied control requirement to the supplied exception rationale and any supplied compensating measure.
4. Separate facts stated in the material from unresolved conditions. Mark missing evidence, owner, expiry, approval basis, or residual-risk detail as an open question.
5. Draft a deck with a decision summary, scope, control-and-exception map, risk register, compensating-measure status, expiry or review checkpoints, and owner questions.
6. Run a traceability check: every factual slide statement must point to supplied text. Replace unsupported assertions with a clearly labeled question or remove them.

## Output

Return:

- A decision summary naming the requested reviewer decision and supplied scope
- A source-linked control-and-exception map
- A risk and compensating-measure table that distinguishes stated operation from proposals
- An expiry, review, and approval-checkpoint slide using supplied dates only
- An open-questions slide for missing facts and accountable owners
- A reviewer checklist that identifies what must be confirmed before a decision

## Boundaries

Use only text pasted into the chat and general language reasoning. Do not claim that an exception is approved, compliant, accepted, implemented, monitored, time-limited, or low risk unless the supplied material explicitly supports that statement. Do not inspect systems or records, change controls, submit an exception, send a request, or make the final approval decision. An accountable security or risk owner must verify the deck before relying on it.
