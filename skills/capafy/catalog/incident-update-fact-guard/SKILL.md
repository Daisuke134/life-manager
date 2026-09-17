---
name: incident-update-fact-guard
description: Use when an operations, support, or incident team must turn pasted incident notes into a status update without turning unconfirmed causes, planned work, or missing facts into claims.
---

# Incident Update Fact Guard

Turn buyer-pasted incident notes into one concise, time-stamped status update that
keeps observed impact, unknown cause, planned work, and the next verification point
separate. The core rule is simple: a claim is either supported by pasted material,
explicitly unknown, or omitted.

## Input

Ask for the intended audience, update timestamp and time zone, incident summary,
observed impact, confirmed scope, known facts, unconfirmed explanations, planned or
completed actions, customer guidance, and the next verified update time. Treat an
omitted cause, scope, resolution, owner, action, or time as unknown.

## Method

1. Make a fact ledger with each supplied statement, its source label, and one status:
   `confirmed`, `reported`, `planned`, `unknown`, or `needs verification`.
2. Keep a reported symptom separate from a confirmed cause. Do not convert a planned
   mitigation into a completed fix.
3. Draft one update in this order: current state, affected experience, what is known,
   what is being done, and next verified update.
4. Remove or label any sentence whose cause, scope, resolution, timing, or customer
   guidance lacks supplied support.
5. Return a short claim ledger and verification queue so a responsible operator can
   check the text before using it.

## Output

Return:

1. A single status update, labeled with the supplied timestamp and audience.
2. A claim ledger showing the source status of each material statement.
3. A verification queue for missing facts and any wording that needs an accountable
   operator to confirm.

## Boundaries

Use only material pasted into the chat and general language reasoning. Do not inspect
systems, logs, tickets, monitoring, customer records, or service status outside that
material. Do not diagnose the root cause, declare an incident resolved, estimate an
unprovided scope, send or post an update, or make commitments on the buyer's behalf.
An accountable incident owner must verify the final text before it is used.
