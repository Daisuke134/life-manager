---
name: annual-report-risk-change-brief
description: >
  Compare buyer-pasted current and prior annual-report risk disclosures into an evidence-bound change brief.
  Use when you need to identify wording changes, disclosure gaps, and follow-up questions without claiming information outside the pasted text.
license: MIT
version: "1.0.0"
tags: [finance, annual-report, risk-disclosure, comparison, analysis]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: life-manager
  version: "1.0"
  stage: S1-Research
---

# Annual Report Risk Change Brief

Turn two buyer-pasted annual-report risk-disclosure excerpts into a concise, auditable change brief. The skill keeps the evidence boundary explicit: it compares supplied wording, never fills gaps with invented filing details, and labels missing support as `[UNVERIFIED]`.

## Stage

This skill belongs to Stage S1: Research.

## When to Use

- You have current and prior risk-factor excerpts and need to see what language was added, removed, or materially reframed.
- You are preparing an investor, governance, or internal reading note from text someone already supplied.
- You need a repeatable first-pass comparison before a human reviews the full reports.
- You want research questions tied to exact wording rather than an investment recommendation.

## Input Schema

```text
current_period: string (required) — e.g., "FY2026"
current_excerpt: string (required) — pasted risk-disclosure text for the current period
prior_period: string (required) — e.g., "FY2025"
prior_excerpt: string (required) — pasted risk-disclosure text for the comparison period
context: string (optional) — buyer-supplied company, section, or review purpose
materiality_rule: string (optional) — what the buyer considers a material wording change
```

## Workflow

### Step 1: Establish the evidence boundary

State the two periods and list only the excerpts and context actually supplied. Do not infer that either excerpt is complete. A good boundary names the missing source portions that could alter the comparison.

### Step 2: Normalize the supplied claims

Break each excerpt into atomic claims with a short topic label, actor, risk mechanism, condition, and stated consequence. Preserve qualifiers such as “may,” “could,” and “material.” A good ledger has enough quoted or closely paraphrased wording that a reader can trace every row to one paste.

### Step 3: Classify the change

Match claims by topic, then classify each as `added`, `removed`, `reframed`, `narrowed`, `broadened`, or `unchanged`. Treat a changed consequence or qualifier as a reframing, not proof that the underlying business condition changed. A good classification identifies both periods' wording.

### Step 4: Write evidence-bound implications

For each meaningful change, explain only what the wording supports: for example, a newly named delivery-delay consequence. Convert unsupported causal or financial conclusions into review questions. A good implication never presents a prediction, valuation view, or unprovided fact as established.

### Step 5: Prioritize follow-up questions

Create three to five questions ordered by possible decision relevance and evidence gap. Mark every question whose answer is absent from the paste `[UNVERIFIED]`. A good question is answerable by a reader who can inspect the source material or ask management; it is not a vague request for “more detail.”

### Step 6: Perform the quality check

Verify that every change row names current and prior support, each missing fact is marked, and the brief contains no investment advice. If the excerpts are too short or only one period is present, return the input gap instead of fabricating a comparison.

## Output Schema

```text
output_schema_version: "1.0.0"
evidence_boundary: {current_period: string, prior_period: string, limitations: string[]}
change_ledger: [{topic: string, classification: string, current_support: string, prior_support: string}]
supported_implications: [{topic: string, implication: string, support: string}]
review_questions: [{priority: integer, question: string, status: "supported" | "[UNVERIFIED]"}]
summary: string
```

## Output Format

```markdown
# Risk Change Brief: [current_period] vs [prior_period]

## Evidence boundary
- Current excerpt supplied: [yes/no and scope]
- Prior excerpt supplied: [yes/no and scope]
- Limits: [what the pasted text cannot establish]

## Change ledger
| Topic | Classification | Current support | Prior support |
|---|---|---|---|
| [topic] | [added/removed/reframed/narrowed/broadened/unchanged] | [current wording] | [prior wording] |

## Supported implications
- **[topic]:** [what the wording supports, without prediction]

## Review questions
1. [question] — [supported or [UNVERIFIED]]

## Summary
[two to four evidence-bound sentences]
```

## Error Handling

- **Only one period supplied:** Request the missing period; provide no change classification.
- **Unlabeled periods:** Ask the buyer to identify which excerpt is current and which is prior before comparing.
- **Topic mismatch:** Keep unmatched topics as added or removed and say that a direct comparison is not supported.
- **Excerpt too short:** Identify the missing sections needed for a defensible comparison and limit output to a gap note.
- **Request for prediction or investment advice:** Decline that conclusion and provide disclosure-based review questions instead.

## Examples

**Example 1: Consequence reframed**

Input: current FY2026 excerpt says, “Supplier concentration may delay deliveries.” Prior FY2025 excerpt says, “Supplier concentration may increase costs.”

Decision: classify the shared supplier-concentration topic as `reframed`, because the stated consequence changes.

Output excerpt: `Supplier concentration — reframed. Current support: delay deliveries. Prior support: increase costs. Review whether the current report quantifies supplier exposure [UNVERIFIED].`

**Example 2: New topic**

Input: the current excerpt adds, “Data-center power constraints may delay expansion.” The prior excerpt contains no power-related language.

Decision: classify as `added`, not as proof that a constraint began in the current year.

Output excerpt: `Power constraints — added disclosure topic. The supplied current wording identifies possible expansion delay; the pasted comparison does not establish timing, severity, or occurrence [UNVERIFIED].`

## Flywheel Connections

### Feeds Into

- `earnings-call-brief` (S1-Research) — pairs disclosure changes with a buyer-pasted reporting-period results record.
- `decision-record-consistency-auditor` (S8-Meta) — can assess whether a decision note preserves the evidence boundary.

### Fed By

- Buyer-pasted annual-report excerpts and prior-period excerpts.
- `transcript-key-points-skimmer` (S1-Research) — can condense long buyer-supplied passages before comparison.

### Feedback Loop

Readers can compare the ledger against the pasted sections, flag false matches, and refine their materiality rule for the next reporting period.

```yaml
chain_metadata:
  skill_slug: annual-report-risk-change-brief
  stage: S1-Research
  timestamp: "2026-10-09"
  suggested_next:
    - earnings-call-brief
    - decision-record-consistency-auditor
```

## Quality Gate

1. Both current and prior excerpts are present and period-labeled.
2. Every ledger row contains support from the appropriate pasted period or explicitly says it is absent.
3. Every classification is one of the six defined labels.
4. No row converts a wording change into a fact about business performance.
5. Every missing material detail is marked `[UNVERIFIED]`.
6. The output includes at least three specific review questions when the input supports them.
7. The output contains no investment recommendation, target, or prediction.

## References

- `LISTING.md` — buyer-facing scope, pricing, and example.
- `evidence/verified-demonstration.md` — concrete offline demonstration.
