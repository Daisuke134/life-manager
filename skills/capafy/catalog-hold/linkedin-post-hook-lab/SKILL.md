---
name: linkedin-post-hook-lab
description: >
  Turn a pasted LinkedIn post brief, draft opener, and approved proof into evidence-bounded
  two-line hooks, a “see more” bridge, and a post-opening package. Use for LinkedIn post openings,
  not posting, audience analytics, or performance prediction.
license: MIT
version: "1.0.0"
tags: [linkedin, post-hooks, thought-leadership, b2b-writing, social-media]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Content
---

# LinkedIn Post Hook Lab

LinkedIn Post Hook Lab turns one buyer-supplied post brief into a text-only opening
package for a LinkedIn post. It keeps approved proof, editorial framing, and unknowns
separate so a stronger first two lines do not become a stronger unsupported claim.

## Stage

This skill belongs to Stage S2: Content.

## When to Use

- A B2B founder has a draft LinkedIn post whose first two lines do not clearly earn the reader's attention.
- A subject-matter expert has an approved insight, example, or customer-safe proof point and needs several opening angles.
- A content lead needs a “see more” bridge and first-paragraph structure without turning a short brief into invented evidence.
- A team needs a repeatable text-only opening package for a new LinkedIn post each week.

## Input Schema

```text
post_goal: string (required) — the reader action, lesson, or discussion the post should support
audience: string (required) — intended LinkedIn reader
topic_or_offer: string (required) — subject, product, lesson, or point of view
draft_or_source_material: string (required) — pasted rough opener, notes, or source text
approved_proof: string (optional) — buyer-approved facts, examples, quotations, or constraints
tone: string (optional) — e.g. direct, reflective, technical, conversational
cta: string (optional) — buyer-approved closing invitation
constraints: string (optional) — banned wording, compliance rules, length, or brand requirements
```

## Workflow

### Step 1: Establish the evidence boundary

Extract supplied facts, quotations, audience, topic, CTA, and constraints into an
evidence ledger. Mark a missing fact `[ADD: ...]`; do not invent customer results,
metrics, prices, employer facts, or product capabilities. Quality bar: every factual
phrase proposed for a hook has a source phrase or an explicit `[ADD: ...]` marker.

### Step 2: Diagnose the supplied opening

Identify the first two lines, reader cue, stated tension, promised value, and the
point at which a reader would need more context. If no draft is supplied, report
`No draft opening supplied`. Quality bar: each diagnosis is labelled `supplied`,
`inference`, or `unknown` rather than presented as a platform observation.

### Step 3: Create distinct opening angles

Write five two-line hooks using distinct structures: specific observation, contrast,
question, process moment, and misconception. Keep the supplied audience and topic;
when an angle needs unsupplied proof, retain it only with `[ADD: proof]`. Quality bar:
no two options rely on the same first claim or rhetorical structure.

### Step 4: Build the recommended post opening

Choose the strongest supported hook and expand it into a first paragraph, a “see
more” bridge, and a second-paragraph handoff. This is text for review, not a posted
LinkedIn update. Quality bar: the bridge introduces only the supplied lesson or a
clearly marked question; it does not imply views, engagement, or authority.

### Step 5: Add supporting copy and a claim check

Return three post titles or internal labels, the supplied CTA (or `[ADD: CTA]`), and
a self-critique for vague framing, unsupported proof, audience mismatch, or compliance
review. Quality bar: the critique lists at least one limitation and makes no claim of
post reach, leads, replies, or conversion.

## Output Schema

```text
output_schema_version: "1.0.0"
evidence_ledger: EvidenceItem[]
opening_diagnosis: OpeningDiagnosis
hook_options: LinkedInHookOption[5]
recommended_opening: LinkedInOpeningPackage
supporting_copy: SupportingCopy
honesty_check: HonestyCheck
```

## Output Format

```markdown
# LinkedIn Post Hook Lab: [topic]

## Evidence boundary
- Supplied: [fact or constraint]
- Unknown: [ADD: missing fact]

## Opening diagnosis
- First two lines: [supplied lines or No draft opening supplied]
- Reader cue: [supplied / inference / unknown]
- Tension: [diagnosis]

## Five hook options
1. **[structure]**
   [first line]
   [second line]
   Evidence: [supplied source or ADD marker]

## Recommended opening package
- First two lines: [text]
- First paragraph: [text]
- “See more” bridge: [text]
- Second-paragraph handoff: [text]

## Supporting copy
- Internal label: [text]
- CTA: [supplied CTA or ADD marker]

## Honesty check
- [unsupported claim removed or missing proof]
```

## Error Handling

- **No usable source material:** Ask for the audience, post goal, topic, and pasted notes or rough opener; do not fabricate an expert point of view.
- **Unsupported outcome claim:** Replace it with `[ADD: approved proof]` or a process-based statement.
- **Conflicting audience or CTA:** Preserve both supplied directions and ask which instruction governs the recommendation.
- **Request to post or inspect results:** Explain that the skill produces text for review from pasted material; it does not publish, access LinkedIn, or measure engagement.
- **Regulated, employment, or financial subject:** Preserve buyer constraints and flag claims needing human or compliance review.

## Examples

**Example 1: Product-operations post**

Input: Audience = product managers; topic = release-note checklist; approved fact = the checklist has seven questions; rough opener = “We made a release-note checklist.”

Decision: The opening is low-specificity. Use a specific-observation angle without claiming the checklist prevents mistakes.

Output excerpt: `Before you publish release notes, ask these seven questions. The checklist is not the update; it is the final pass before the update.`

**Example 2: Founder process post**

Input: Audience = B2B founders; topic = sales-call review; supplied note = two calls used the same objection log; no result or CTA supplied.

Decision: Use a process-moment angle and mark any performance implication as missing proof.

Output excerpt: `We reviewed two sales calls with the same objection log. The useful part was not the count—it was seeing which questions kept repeating.` with `CTA: [ADD: buyer-approved CTA]`.

## Flywheel Connections

### Feeds Into

- `marketing-strategist` (S1-Research) — turns an approved opening into a broader campaign decision.
- `social-content` (S5-Distribution) — adapts approved copy into a channel plan.

### Fed By

- `product-marketing-context` (S1-Research) — supplies approved offer facts and audience notes.
- Buyer-provided subject-matter notes — provide the sole factual basis for post claims.

### Feedback Loop

Writers can paste their own review notes from a prior post into the next brief. The
skill uses only those supplied notes for revision and never treats an unsupplied
engagement metric as observed.

```yaml
chain_metadata:
  skill_slug: "linkedin-post-hook-lab"
  stage: "S2-Content"
  timestamp: "2026-10-03"
  suggested_next:
    - "marketing-strategist"
    - "social-content"
```

## Quality Gate

1. Required goal, audience, topic, and source material are present or the missing fields are requested.
2. Every factual claim in a hook has a supplied source or an `[ADD: ...]` marker.
3. Five hooks use five named, distinct structures.
4. The recommended opening includes two opening lines, a first paragraph, a “see more” bridge, and a second-paragraph handoff.
5. Output is text for review only and does not claim to access LinkedIn, publish a post, or inspect analytics.
6. No output promises views, reach, leads, replies, sales, conversion, or platform performance.
7. The honesty check names every unresolved proof, approval, or compliance gap.

## References

- `LISTING.md` — buyer-facing listing, price ladder, and honest capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input and output verification.
