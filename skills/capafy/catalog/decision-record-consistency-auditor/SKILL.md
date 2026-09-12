---
name: decision-record-consistency-auditor
description: Compare pasted decision records and meeting notes to surface conflicting decisions, missing context, and unresolved implementation questions.
---

# Decision Record Consistency Auditor

Turn a set of pasted architecture, product, operations, or project decisions into a reviewable consistency report. This is for reconciling documents a team already has; it does not inspect repositories, tickets, calendars, or other systems.

## Input

Ask for the decision records, meeting notes, dates, owners, affected scope, stated rationale, constraints, and any requested output format. Ask the user to identify source precedence if one record is authoritative. Treat an omitted date, owner, scope, or decision status as unknown.

## Method

1. Extract each supplied decision into a ledger: decision, source, date, owner, scope, rationale, status, and exact supporting text.
2. Compare only decisions that address the same stated scope or dependency.
3. Flag a conflict when supplied records prescribe incompatible choices for the same scope. Quote the conflicting supplied statements.
4. Flag a supersession only when a supplied record explicitly states that it replaces another record, or when the user supplies an authoritative precedence rule. Otherwise label the relationship as unresolved.
5. List missing decision fields and implementation questions as open items. Do not infer approval, recency, ownership, or technical feasibility.
6. Produce a reconciliation brief that preserves source traceability and separates conflicts from ambiguities.

## Output

Return:

- A decision ledger keyed to the supplied source material
- A conflict table with both source statements and the shared scope
- An ambiguity and missing-context table
- A proposed reconciliation agenda containing questions, not invented resolutions
- A verification checklist for the decision owner

## Boundaries

Use only material pasted into the chat and general language reasoning. Do not claim access to repositories, tickets, calendars, approvals, implementation state, or organizational policy. Do not invent a final decision, source authority, owner, date, dependency, or technical conclusion.
