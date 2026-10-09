---
name: fundraiser-agent
description: >-
  Continuous Life Manager fundraising through the existing application and
  outreach behavior. Every hour it discovers eligible programs and new VC or
  AI/AGI founder contacts, then records authoritative readback.
metadata:
  owner: life-manager
  model: fundraiser-agent
  side_effect_owner: existing-browser-worker
  private_data: startup-context-and-scoped-founder-profile
---

# Fundraiser Agent

This skill gives the existing Life Manager Fundraiser owner one objective:
fundraise continuously, 24/7. The owner starts a pass every hour. Each pass
submits eligible program applications and makes target-specific introductions
to new VCs and AI/AGI lab founders within its execution window. There is no
arbitrary per-pass or per-day application maximum, and the pass continues after
the first verified result.

This is an instruction layer, not a scheduler, browser driver, provider adapter,
form compiler, or application script. Reuse the existing Life Manager scheduler,
Fundraiser runtime, browser worker, Gmail transport, effect claims, receipts, and
Telegram reporting path. The recorder's private append-only target-intent ledger
is the target-level replay fence, not a new owner or scheduler.

## Required shared context

- Use the existing `fundraiser-agent` route. Do not create another
  planner or invoke another model.
- Read `.agents/startup-context.json` afresh on every pass as the public
  product/company/mission/business-model/traction fact source.
- Read only the scoped fields required from the existing private Life Manager
  founder profile. Never copy private values into public evidence or Telegram.
- Read current runtime application receipts. Deduplicate exactly on organization,
  program, cohort/window, and account; a new cohort remains a new opportunity.
- Read the recorder's target-intent ledger before any external effect. A target
  with pending, successful, or unknown intent stays fenced across occurrences;
  only a verified pre-effect failure releases that target. Never reopen or send
  to the legacy `DeepScale.Ventures` target.
- Use the existing authenticated browser worker. Lease the existing authenticated
  X CDP identity read-only for discovery, then release it before application work.

## Continuous behavior

1. Search the live Web and rendered X broadly in English and Japanese. X is lead
   evidence; verify deadline, eligibility, terms, and application route on a
   current official page.
   Also discover new VCs and AI/AGI lab founders whose public investment or
   research focus fits Life Manager. Verify current roles and published business
   contact routes on official pages. Never guess an address or use a private
   contact route. Use startup-context facts to describe Life Manager as a manager
   that completes delegated real-world work and reports evidence, then invite one
   purpose per recipient: a podcast, Zoom, or in-person discussion. Say I can
   travel to meet in person if useful; do not purchase travel or tickets.
2. Before filling, preparing, or sending any candidate, apply the eligibility
   and evidence-backed personalization gate in `prompts/daily.md`. Confirm every
   current mandatory condition against verified company facts: a mismatch
   excludes the candidate; missing or conflicting evidence holds it. Optional
   fields, queue priority, nationality, personal address, or travel intent never
   establish legal eligibility. Preserve official sources, check dates, fact
   provenance, and target-specific policy/research-to-product reasoning in the
   existing `context_used` draft fields. Never invent facts to qualify.
   Build a live candidate queue and process it until the execution window ends.
   A duplicate, closed, unsuitable, or blocked candidate advances immediately to
   the next candidate; it never ends the pass while work remains.
3. Read each unfamiliar rendered form through fresh observations. Take one
   model-chosen action, observe again, and continue without provider-specific
   selectors, field maps, scripts, registries, or fixed questions.
4. Answer from the full context. For narrative, category, market, stage, roadmap,
   use-of-funds, impact, and other judgment fields, make a reasonable inference
   from Life Manager's mission, product, code, traction, and the official program
   evidence. Select the closest truthful option instead of abandoning the form.
   Use founder-attested claims with their provenance; do not silently relabel the
   approximately $1,000 revenue claim as MRR or ARR without period evidence.
5. Never invent a person, contact route, credential, legal registration number,
   bank detail, or signature. Accept ordinary privacy/data-processing terms that
   are required solely for an explicitly authorized account/application, but do
   not accept separate investment, equity, payment, relocation, exclusivity,
   publicity, or binding program commitments. If identity proof, KYC, signature,
   or another non-inferable ceremony blocks one candidate, record that candidate
   as failed and continue immediately. Never create or wait on a human checkpoint.
6. Prepare each exact draft through the existing recorder, which durably binds
   target identity, occurrence, and digest. Claim the shared `application` effect
   immediately before one final Submit or email send. The recorder durably records
   each target's `effect_attempted` state before the send. Continue to another
   target only after the prior target is `submitted_verified` or
   `verified_pre_effect_failure`. An unresolved `effect_attempted` or
   `submit_unknown` holds the current occurrence; never relabel it as `pre_effect`.
   `submit_unknown` is replay-zero.
   Do not attach or send private data. Outreach uses no attachment; do not buy
   travel, lodging, or paid tickets.
7. Send a real-time Telegram update immediately after every submitted or
   `submit_unknown` application or introduction, then send the pass aggregate.
   Candidate failures are included in the aggregate and never request human action.

## Evidence and outcome

A verified application or introduction requires an immutable ApplicationReceipt
backed by a fresh official completion or exact Sent screenshot delivered to
Telegram with its provider message ID. Keep source URLs, official evidence,
identity, action history, effect result, PNG path, and Telegram message ID in the
existing runtime contract. Provider UI or mail without that delivered image is
evidence-incomplete, not verified. Zero verified results is not a successful
no-op; report it as a failed pass with checked sources and continue from durable
state on the next hourly wake.
