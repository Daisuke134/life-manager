---
name: delivery-commitment-evidence-ledger
description: Turn pasted delivery commitments, acceptance criteria, and project evidence into a traceable ledger of support, gaps, and owner questions.
---

# Delivery Commitment Evidence Ledger

Turn buyer-pasted statements of work, order forms, project updates, acceptance notes, and delivery artifacts into a traceable delivery-commitment ledger.
This is a document-reconciliation workflow for a team’s own review.
It does not determine legal obligations, interpret enforceability, inspect systems, or certify that a delivery was completed.

## Input

Ask for the pasted commitment text, its source label, delivery period, named owner, acceptance wording, and any material offered as delivery evidence.
Ask the buyer to distinguish a planned activity from a completed one when their source material does so.
Treat an omitted owner, date, acceptance criterion, delivery evidence, or source precedence as unknown.

## Method

1. Extract each supplied commitment into a ledger with the source, promised item, stated timing, owner, acceptance wording, and exact supporting text.
2. Keep a commitment separate from a project update, draft, or claimed completion unless the supplied material explicitly links them.
3. Compare each supplied evidence item only with the commitment or acceptance wording it explicitly addresses.
4. Mark an item `SUPPORTED` only when the pasted material directly supports the stated commitment or criterion.
5. Mark `PARTIAL`, `MISSING`, `UNCLEAR`, or `NOT EVIDENCE OF COMPLETION` when the supplied material does not establish the whole item.
6. List owner questions and verification steps without inventing completion, acceptance, breach, priority, remedies, or legal conclusions.

## Output

Return:

- A commitment ledger with source-linked wording
- An evidence-status table that distinguishes delivery evidence from plans and drafts
- A gap and unknowns register
- A verification queue with the accountable owner or an explicit owner question
- A concise review brief for the team’s next delivery check-in

## Boundaries

Use only text pasted into the chat and general language reasoning.
Do not claim access to contracts outside the supplied excerpts, project-management tools, file stores, customer communications, delivery systems, approvals, or acceptance records.
Do not give legal advice, determine enforceability, declare a breach, certify completion, send a notice, or make commitments for the buyer.
Keep each final conclusion tied to supplied text and require the responsible owner to verify it before operational or legal use.
