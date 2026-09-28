---
name: newsletter-hook-lab
description: >
  Turn a pasted newsletter brief, draft opening, and approved proof into subject-line options,
  preview text, and an evidence-bounded opening sequence. Use it to improve a newsletter issue's
  opening without claiming inbox access, delivery, or reader-performance prediction.
license: MIT
version: "1.0.0"
tags: [newsletter, subject-lines, hooks, email-copy, content]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Content
---

# Newsletter Hook Lab

Create an evidence-bounded opening package for one newsletter issue from material
the writer pastes into chat. It makes the subject line, preview text, and first
paragraph work together while separating supplied facts from editorial inference.

## Stage

This skill belongs to Stage S2: Content.

## When to Use

- A writer has a rough newsletter opening and needs several supported subject-line directions.
- A founder has an approved announcement but needs a clear first paragraph without adding claims.
- An editor wants to compare opening angles for a recurring issue from a pasted brief.
- A creator needs preview text and a reader-facing opening that preserve supplied compliance constraints.

## Input Schema

```text
issue_goal: string (required) — the desired reader action or takeaway
audience: string (required) — the intended subscribers and their context
brief_or_draft: string (required) — pasted issue brief, rough opening, or draft
topic_or_offer: string (required) — the subject, announcement, or idea
supplied_proof: string (optional) — approved facts, examples, quotes, or constraints safe to state
cta: string (optional) — buyer-approved call to action
tone: string (optional) — e.g. direct, analytical, warm
constraints: string (optional) — banned wording, legal review notes, length, or brand rules
```

## Workflow

### Step 1: Establish the evidence boundary

Extract the supplied audience, goal, topic, CTA, proof, and constraints into an
evidence ledger. Mark anything needed but absent as `[ADD: ...]`; do not invent
results, testimonials, statistics, dates, or product capabilities. Quality bar:
every factual phrase in the recommended opening maps to supplied text or an ADD marker.

### Step 2: Diagnose the pasted opening

Identify the first sentence, reader cue, promise, specificity, tension, and open
question. If the buyer gives no opening, state `No opening supplied` rather than
diagnosing an imagined draft. Quality bar: distinguish supplied material, inference,
and unknowns.

### Step 3: Generate distinct hook directions

Write five opening directions using named structures: specific contrast, problem
interruption, process reveal, objection reversal, and consequence. Give each a
subject line, preview text, and first paragraph. Quality bar: no two options begin
with the same claim or use the same rhetorical structure.

### Step 4: Build the recommended opening sequence

Choose the strongest supported direction and produce a subject line, preview text,
first paragraph, bridge sentence, and CTA placement note. Quality bar: the preview
text complements rather than repeats the subject line, and the first paragraph
explains why the issue matters to the supplied audience.

### Step 5: Self-critique before delivery

Check each option for unsupported claims, ambiguous promises, tone mismatch, and
missing approvals. Quality bar: name at least one limitation and never predict opens,
clicks, replies, sales, or delivery.

## Output Schema

```text
output_schema_version: "1.0.0"
evidence_ledger: EvidenceItem[]
opening_diagnosis: OpeningDiagnosis
hook_options: NewsletterHookOption[5]
recommended_sequence: NewsletterOpeningSequence
honesty_check: HonestyCheck
```

## Output Format

```markdown
# Newsletter Hook Lab: [issue topic]

## Evidence boundary
- Supplied: [fact or constraint]
- Unknown: [ADD: missing fact]

## Opening diagnosis
- First sentence: [supplied sentence or No opening supplied]
- Reader cue: [supplied / inference / unknown]
- Promise: [diagnosis]

## Five hook options
1. **[structure]**
   - Subject line: [text]
   - Preview text: [text]
   - First paragraph: [text]
   - Evidence: [supplied source or ADD marker]

## Recommended opening sequence
- Subject line: [text]
- Preview text: [text]
- First paragraph: [text]
- Bridge sentence: [text]
- CTA placement: [supplied CTA or ADD marker]

## Honesty check
- [unsupported claim removed or missing proof]
```

## Error Handling

- **No usable brief:** Request the audience, issue goal, and a pasted draft or topic; do not fabricate an issue.
- **Unsupported outcome claim:** Replace it with `[ADD: proof]` or a process-based statement.
- **Conflicting audience or CTA:** Present both instructions and ask which one controls the recommendation.
- **Delivery or account request:** Explain that the skill returns copy from pasted material and cannot access, send, or manage a newsletter account.
- **Regulated claim:** Preserve the buyer's constraints and flag the wording for qualified human review.

## Examples

**Example 1: Founder announcement**

Input: Audience = product managers; topic = a release-note checklist; supplied fact = it has seven questions; rough opening = “We made a release-note checklist.”

Decision: The generic opening lacks a reader cue. Use a specific-contrast hook and keep the seven-question fact.

Output excerpt: `Subject line: Before you publish release notes, ask these seven questions` and `Preview text: A checklist for product managers who want a clearer final pass.`

**Example 2: Creator issue**

Input: Audience = independent consultants; topic = post-project debrief; supplied proof = it uses three prompts; no CTA supplied.

Decision: Use a process-reveal hook and mark the CTA missing instead of claiming a client outcome.

Output excerpt: `First paragraph: “A project can end without becoming reusable judgment. My debrief starts with three prompts.”` and `CTA placement: [ADD: buyer-approved CTA]`.

## Flywheel Connections

### Feeds Into

- `email-sequence` (S5-Distribution) — develops approved issue language into a sequence.
- `social-content` (S5-Distribution) — adapts the approved angle for other channels.

### Fed By

- `product-marketing-context` (S1-Research) — supplies approved audience and offer facts.
- Buyer-provided newsletter briefs and drafts — supply the factual basis for every claim.

### Feedback Loop

Writers may paste their own reader replies or editorial notes into a later brief; the
skill treats them as supplied material and does not infer unprovided metrics.

```yaml
chain_metadata:
  skill_slug: "newsletter-hook-lab"
  stage: "S2-Content"
  timestamp: "2026-09-29"
  suggested_next:
    - "email-sequence"
    - "social-content"
```

## Quality Gate

1. Required goal, audience, brief, and topic are present or explicitly requested.
2. Every factual phrase in a recommended hook is in the evidence ledger or marked `[ADD: ...]`.
3. Five options use five named, distinct structures.
4. Each option includes a subject line, preview text, and first paragraph.
5. The recommended preview text complements the subject line instead of restating it.
6. Output is text only and makes no claim to access accounts, send a newsletter, or inspect subscriber behavior.
7. The honesty check names unresolved proof, approval, compliance, or delivery gaps.

## References

- `LISTING.md` — buyer-facing listing, price ladder, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification notes.
