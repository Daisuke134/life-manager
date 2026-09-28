---
name: rfp-response-evidence-matrix
description: Turn a pasted RFP and pasted company material into a requirement-by-requirement response matrix that distinguishes supported statements from gaps and questions.
---

# RFP Response Evidence Matrix

Turn material supplied in the chat into a traceable response-planning matrix for an RFP, questionnaire, or procurement request. This skill helps a team organize what its supplied material supports before a reviewer drafts or approves a submission. It does not inspect websites, files, prior bids, product systems, pricing systems, or legal terms outside the text provided.

## Input

Ask for:

- The pasted RFP, questionnaire, or list of buyer requirements
- Pasted company, product, security, implementation, pricing, or policy material that may support a response
- Any mandatory response format, word limits, and labels for authoritative source material
- The desired response voice and the owner who will verify gaps

Treat a requirement, capability, certification, metric, commitment, date, price, integration, or approval as unknown unless the supplied text states it. Preserve the user's source labels.

## Method

1. Split the pasted request into individually answerable requirements without adding requirements that are not present.
2. For each requirement, locate only directly relevant supplied statements and quote or closely attribute them in an evidence column.
3. Classify each row as `SUPPORTED`, `PARTIALLY SUPPORTED`, `GAP`, `QUESTION`, or `OUT OF SCOPE` based on the supplied material.
4. Draft a concise response only for supported portions. For partial support, state the supported portion and name the missing fact. For a gap or question, write a verification question instead of a claim.
5. Separate buyer-facing draft wording from the internal verification queue so an unverified statement is not presented as established fact.
6. Run a final traceability pass: every factual draft statement must have a supplied source reference; otherwise remove it or move it to a question.

## Output

Return:

- A requirement-and-evidence matrix with the requirement, supplied evidence, status, draft answer, and owner question
- A red-flag list for unsupported commitments, missing attachments, ambiguous wording, and approval-dependent claims
- A prioritized verification queue that identifies the source or owner needed for each open item
- A submission-readiness summary that counts supported, partial, gap, and question rows without deciding whether to submit

## Boundaries

Use only the text pasted into the chat and general language reasoning. Do not claim certification, compliance, capability, pricing, availability, contract acceptance, integration, security posture, delivery timing, or buyer eligibility unless that claim is explicitly supported by supplied material. Do not submit, send, upload, negotiate, or approve anything. A qualified owner must verify every final response before use.
