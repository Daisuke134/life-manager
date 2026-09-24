---
name: vendor-evaluation-evidence-scorecard
description: >
  Turn pasted vendor proposals and evaluation criteria into a traceable comparison scorecard with evidence, gaps, and conditional decision options.
  Use when a procurement, operations, or product team must compare supplied vendor material without inventing facts.
license: MIT
version: "1.0.0"
tags: [vendor-evaluation, procurement, scorecard, evidence, decision-support]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: "affitor"
  version: "1.0"
  stage: "S4-Landing"
---

# Vendor Evaluation Evidence Scorecard

Convert supplied vendor proposals, notes, and scoring criteria into a comparison that preserves the distinction between directly stated evidence, partial support, unknowns, and proposed follow-up. It is a drafting and review aid, not a source of vendor facts, contractual advice, or an automatic purchasing decision.

## Stage

This skill belongs to Stage S4: Landing.

## When to Use

- You have two or more pasted vendor proposals and must prepare a selection meeting.
- A procurement team has criteria but needs a consistent way to distinguish claims from missing answers.
- An operations lead needs a decision brief from supplier notes without treating unstated items as confirmed.
- A buyer needs a follow-up question list before recommending a vendor.

## Input Schema

```text
vendors: array<{name: string, supplied_material: string}> (required)
criteria: array<{criterion: string, weight?: number, requirement?: string}> (required)
scoring_scale: {labels: string, permitted_values: number[]} (optional; default: 0 absent, 1 partial, 2 directly stated)
decision_context: string (optional)
non_negotiables: string[] (optional)
known_constraints: string[] (optional)
```

## Workflow

### Step 1: Normalize the supplied record

**Action:** List vendors, criteria, non-negotiables, and supplied statements separately.
**Approach:** Keep a short quoted or faithfully paraphrased evidence note for each vendor statement; label an absent field `[NOT SUPPLIED]`.
**Quality bar:** Every comparison row identifies the supplied text it relies on or explicitly says no supporting text was supplied.

### Step 2: Define the scoring basis

**Action:** Preserve the user's scale or declare the default editorial scale.
**Approach:** Apply a score only when the supplied material supports the matching level: 0 = absent, 1 = partial or ambiguous, 2 = directly stated. Apply weights only when supplied.
**Quality bar:** A score is never presented as a fact about vendor performance; the score and its reason appear together.

### Step 3: Build the evidence scorecard

**Action:** Compare every vendor against every criterion.
**Approach:** Record evidence, score, weighted score when applicable, confidence label, and an exact gap or follow-up question. Do not infer a feature, price, compliance status, implementation scope, or contract term from silence.
**Quality bar:** Each row can be checked against the pasted material without needing a system, file, or outside source.

### Step 4: Separate non-negotiables from preference scores

**Action:** Test each supplied non-negotiable independently of the total score.
**Approach:** Mark it `SUPPORTED`, `PARTIAL`, `NOT SUPPLIED`, or `CONFLICTS WITH SUPPLIED TEXT`; do not let a high score cancel a stated requirement.
**Quality bar:** The output makes a blocking gap visible even if the vendor has the highest weighted total.

### Step 5: Draft conditional decision options

**Action:** Offer at most three next-step options tied to the evidence record.
**Approach:** Phrase recommendations conditionally, such as `[CONDITIONAL OPTION] Select Vendor A only if the owner confirms the open pricing item.` Keep final approval with the accountable buyer.
**Quality bar:** No option claims that a vendor is objectively best, approved, compliant, or contractually suitable.

### Step 6: Produce the review packet

**Action:** Return a scorecard, an evidence-gap ledger, and a short meeting agenda.
**Approach:** Rank questions by stated non-negotiables first, then by weighted impact, then by missing ownership or dates.
**Quality bar:** The packet is self-contained and states the scoring scale, calculation method, and unresolved fields.

## Output Schema

```json
{
  "output_schema_version": "1.0.0",
  "scoring_basis": {"scale": "string", "weights_used": "boolean"},
  "vendor_scorecards": [{"vendor": "string", "criteria": "array", "weighted_total": "number|null"}],
  "non_negotiable_status": [{"requirement": "string", "status_by_vendor": "object"}],
  "evidence_gap_ledger": [{"vendor": "string", "criterion": "string", "status": "string", "follow_up": "string"}],
  "conditional_options": ["string"],
  "review_agenda": ["string"]
}
```

## Output Format

```markdown
# [Evaluation name] — evidence scorecard

## Scoring basis
- Scale: [0 / 1 / 2 definition]
- Weights: [supplied weights or "none supplied"]

## Comparison
| Criterion | Weight | [Vendor A] evidence | [Vendor A] score | [Vendor B] evidence | [Vendor B] score |
|---|---:|---|---:|---|---:|
| [criterion] | [weight] | [supplied evidence or NOT SUPPLIED] | [score] | [supplied evidence or NOT SUPPLIED] | [score] |

## Non-negotiables
| Requirement | [Vendor A] | [Vendor B] | Evidence or gap |
|---|---|---|---|
| [requirement] | [SUPPORTED/PARTIAL/NOT SUPPLIED] | [status] | [evidence] |

## Evidence-gap ledger
| Vendor | Open item | Why unresolved | Follow-up question |
|---|---|---|---|
| [vendor] | [item] | [reason] | [question] |

## Conditional options
1. [CONDITIONAL OPTION] [option tied to supplied evidence]

## Review agenda
1. [highest-priority confirmation]
```

## Error Handling

- **No criteria supplied:** Ask for the decision criteria; do not create a total score from generic assumptions.
- **One vendor only:** Produce a single-vendor evidence checklist and state that it is not a comparison.
- **Incompatible scoring scales:** Keep each supplied scale separate and ask the buyer to choose one before calculating totals.
- **Price or contract claim is ambiguous:** Quote the ambiguity, mark it partial, and add a confirmation question rather than normalizing it.
- **Requested legal, security, or financial approval:** Identify the relevant supplied clause or gap and direct the user to an accountable reviewer; do not issue approval.

## Examples

**Example 1: SaaS shortlist**
Input: Two pasted proposals, with SSO weighted 3 and annual price weighted 3.
Decision: A stated SSO feature earns direct-support credit; an implementation price marked TBD remains an open item.
Output excerpt: `Vendor Beacon: 14 weighted points; implementation fee [NOT SUPPLIED].`

**Example 2: Facilities supplier review**
Input: Three supplier summaries and a non-negotiable requirement for weekend coverage.
Decision: A supplier with no weekend statement is marked `NOT SUPPLIED`, even if it has the highest preference score.
Output excerpt: `Do not treat the total as clearance of the weekend-coverage requirement.`

## Flywheel Connections

### Feeds Into

- `decision-record-consistency-auditor` (S4) — can check that a later decision record preserves the scorecard's stated evidence and gaps.
- `rfp-response-evidence-matrix` (S4) — can organize a vendor's response material before it is evaluated.

### Fed By

- Procurement notes, proposal excerpts, and stakeholder criteria supplied in chat.
- `rfp-response-evidence-matrix` (S4) — may provide a structured record for one vendor response.

### Feedback Loop

After a buyer confirms outcomes, add only the buyer-confirmed criteria definitions and follow-up prompts to future inputs; do not retroactively convert unresolved claims into evidence.

```yaml
chain_metadata:
  skill_slug: vendor-evaluation-evidence-scorecard
  stage: S4-Landing
  timestamp: "2026-09-25"
  suggested_next:
    - decision-record-consistency-auditor
    - rfp-response-evidence-matrix
```

## Quality Gate

1. Every vendor/criterion cell has supplied evidence, a partial label, or `[NOT SUPPLIED]`.
2. Every numeric score names the declared scale and shows its criterion-level reason.
3. Every supplied non-negotiable has a per-vendor status independent of totals.
4. No unstated feature, price, owner, date, approval, or contract term is treated as confirmed.
5. Each conditional option names the evidence or gap that limits it.
6. The output includes at least one actionable follow-up for every blocking or partial non-negotiable.
7. The output contains no claim of access to vendor systems, files, or information beyond the supplied text.

## References

- `LISTING.md` — buyer-facing listing and paid plan details.
- `evidence/verified-demonstration.md` — concrete input, rendered output, and traceability checks.

## Plans

| cycle | price | cap | trial |
|---|---:|---:|---|
| week | $9.99 | 20 | No Free Trial |
| month | $24.99 | 60 | No Free Trial |
