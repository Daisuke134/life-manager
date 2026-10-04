---
name: youtube-shorts-hook-lab
description: >
  Turn a pasted YouTube Shorts brief, transcript, or rough opening into evidence-bounded
  first-three-second hooks, spoken lines, on-screen text, and a short shot plan. Use it when
  a creator needs a fresh text-only opening package for a specific Short without web or channel access.
license: MIT
version: "1.0.0"
tags: [youtube-shorts, hooks, short-form-video, scripts, content]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Content
---

# YouTube Shorts Hook Lab

Build a text-only opening package for one YouTube Short from material the creator pastes into chat. The workflow makes the first three seconds, spoken line, on-screen text, and opening shot agree while keeping supplied facts separate from editorial framing and unknowns.

## Stage

This skill belongs to Stage S2: Content.

## When to Use

- A creator has a new Shorts topic or rough transcript and needs several first-three-second directions.
- A channel manager needs a concise spoken hook and opening-shot plan from approved product or educational facts.
- An editor wants to improve a weak Short opening without inventing retention, trend, or performance claims.
- A team needs a repeatable text package for each new Short before filming or editing.

## Input Schema

```text
topic_or_transcript: string (required) — pasted topic, transcript excerpt, or rough opening
audience: string (required) — intended viewer and context
goal: string (required) — takeaway or action the Short should support
supplied_facts: string (optional) — approved facts, exact quotes, product details, or examples
duration_seconds: number (optional) — target duration; default 30
cta: string (optional) — approved call to action
tone: string (optional) — e.g. practical, curious, direct
constraints: string (optional) — prohibited claims, required terms, brand rules, or visual limits
```

## Workflow

### Step 1: Establish the evidence boundary

Extract the topic, audience, goal, approved facts, CTA, and constraints into a ledger. Mark missing proof as `[ADD: ...]`; never invent statistics, outcomes, customer quotes, trend information, or channel results. Quality bar: every factual claim in a recommended hook is traceable to supplied material or has an ADD marker.

### Step 2: Diagnose the current opening

Identify the viewer cue, promise, tension, first spoken words, and first visible frame in the pasted material. If no opening is supplied, say `No opening supplied` rather than pretending there was one. Quality bar: label observations as supplied fact, editorial inference, or unknown.

### Step 3: Generate five distinct hook directions

Create five directions using specific contrast, problem interruption, process reveal, objection reversal, and consequence. For each, write a ≤7-word on-screen line, an approximately 12-word spoken line, a concrete opening shot, and the evidence basis. Quality bar: no two options use the same structure or unsupported performance promise.

### Step 4: Build the recommended Shorts opening package

Choose the strongest supported direction and produce a 0–3 second opening, a 3–15 second beat plan, a title option, and the supplied CTA placement. Quality bar: spoken and on-screen lines complement rather than duplicate each other, and every beat fits the stated or default duration.

### Step 5: Self-critique before delivery

Check for unsupported factual claims, unclear audience relevance, tone mismatch, and missing approvals. Quality bar: name at least one limitation and never claim channel access, trend access, posting, analytics, views, retention, subscribers, or revenue.

## Output Schema

```text
output_schema_version: "1.0.0"
evidence_ledger: EvidenceItem[]
opening_diagnosis: OpeningDiagnosis
hook_options: ShortsHookOption[5]
recommended_opening_package: ShortsOpeningPackage
honesty_check: HonestyCheck
```

## Output Format

```markdown
# YouTube Shorts Hook Lab: [topic]

## Evidence boundary
- Supplied: [fact or constraint]
- Unknown: [ADD: missing proof]

## Opening diagnosis
- Viewer cue: [supplied / inference / unknown]
- Opening supplied: [text or No opening supplied]
- Tension: [diagnosis]

## Five hook options
1. **[structure]**
   - On-screen text: [≤7 words]
   - Spoken line: [about 12 words]
   - Opening shot: [specific visual]
   - Evidence: [supplied source or ADD marker]

## Recommended opening package
- 0–3 seconds: [on-screen text + spoken line + shot]
- 3–15 seconds: [beat plan]
- Title option: [text]
- CTA placement: [supplied CTA or ADD marker]

## Honesty check
- [limitation or unsupported claim removed]
```

## Error Handling

- **No usable brief:** Request a topic or transcript, audience, and goal; do not fabricate a Short.
- **Unsupported result claim:** Replace it with `[ADD: proof]` or a process-based statement.
- **Conflicting audience or CTA:** Present both instructions and ask which controls the recommendation.
- **Request to access or publish to YouTube:** Explain that the skill returns text from pasted material and cannot access a channel, analytics, or publishing controls.
- **Regulated or safety-sensitive claim:** Preserve buyer constraints and flag the wording for qualified human review.

## Examples

**Example 1: Tutorial Short**

Input: Audience = new home cooks; topic = a one-pan tomato pasta; supplied fact = it uses one pan; goal = show the first cooking step.

Decision: Use a specific-contrast hook and retain only the supplied one-pan fact.

Output excerpt: `On-screen text: One pan, dinner starts` and `Spoken line: “Start tomato pasta in the same pan you will serve from.”`

**Example 2: Product education Short**

Input: Audience = first-time calendar users; topic = a weekly planning template; supplied fact = it has three sections; no CTA supplied.

Decision: Use process reveal and mark the CTA missing instead of promising saved time.

Output excerpt: `Opening shot: cursor moves through Today, This Week, and Later headings` and `CTA placement: [ADD: buyer-approved CTA]`.

## Flywheel Connections

### Feeds Into

- `youtube-script-writer` (S2-Content) — expands the approved opening into a longer script when needed.
- `social-content` (S5-Distribution) — adapts approved angles into text for other channels.

### Fed By

- `product-marketing-context` (S1-Research) — supplies approved audience and offer facts.
- Buyer-provided Short briefs, transcripts, and constraints — provide the factual basis for the package.

### Feedback Loop

Creators can paste their own editorial feedback or approved revised wording into the next brief; the skill treats it as supplied material and does not infer platform metrics.

```yaml
chain_metadata:
  skill_slug: "youtube-shorts-hook-lab"
  stage: "S2-Content"
  timestamp: "2026-10-01"
  suggested_next:
    - "youtube-script-writer"
    - "social-content"
```

## Quality Gate

1. Required topic/transcript, audience, and goal are present or explicitly requested.
2. Every factual phrase in the recommended package is in the evidence ledger or marked `[ADD: ...]`.
3. Five options use five named, distinct structures.
4. Each option includes on-screen text, a spoken line, an opening shot, and an evidence basis.
5. The recommended spoken and on-screen lines do not merely repeat one another.
6. Output is text only and makes no claim to access YouTube, use trend data, publish a Short, or inspect analytics.
7. The honesty check names unresolved proof, approval, compliance, or performance gaps.

## References

- `LISTING.md` — buyer-facing listing, plan ladder, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification notes.
