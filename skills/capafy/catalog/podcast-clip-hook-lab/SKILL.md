---
name: podcast-clip-hook-lab
description: >
  Turn a pasted podcast excerpt and episode context into evidence-bounded short-clip hooks,
  captions, and a text-only first-three-seconds blueprint. Use for podcast social clips, not audio editing, publishing, or performance prediction.
license: MIT
version: "1.0.0"
tags: [podcast, clips, hooks, short-form, social-media]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Content
---

# Podcast Clip Hook Lab

Create a source-bounded opening package for one social clip from a podcast excerpt the user pastes into chat. It distinguishes direct quotes, supported paraphrases, and unknown context so the output improves discoverability without inventing what a guest said or implying it edited the audio.

## Stage

This skill belongs to Stage S2: Content.

## When to Use

- A podcast producer has a transcript excerpt and needs several opening treatments before cutting a clip.
- A host wants an episode quote turned into platform-neutral caption openings and on-screen text.
- A social editor needs a first-three-seconds plan but only has pasted transcript text, not an audio or video file.
- A team needs a clip teaser that preserves a guest's actual position and flags missing episode context.

## Input Schema

```text
clip_goal: string (required) — intended viewer takeaway or next action
audience: string (required) — intended listener or viewer
podcast_context: string (required) — show, episode, speaker, and topic as supplied
transcript_excerpt: string (required) — pasted excerpt selected for the clip
approved_quote: string (optional) — wording that may be quoted verbatim
tone: string (optional) — e.g. thoughtful, energetic, plainspoken
cta: string (optional) — approved call to action
constraints: string (optional) — banned claims, speaker sensitivities, or duration
```

## Workflow

### Step 1: Build an evidence ledger

Extract speaker names, direct wording, context, audience, CTA, and constraints only from the pasted input. Mark absent context as `[ADD: ...]`; do not invent credentials, episode claims, outcomes, or quotations. Quality bar: every factual line in the output maps to a ledger item.

### Step 2: Diagnose the excerpt

Identify the first usable spoken phrase, tension, concrete takeaway, necessary context, and risk of misleading truncation. Label each observation `supplied`, `inference`, or `unknown`. Quality bar: quote fragments retain their supplied meaning and speaker attribution.

### Step 3: Draft five distinct hooks

Write five structures: direct-quote lead, audience question, tension statement, takeaway reveal, and contrarian framing. Each uses an approved quote or a clearly supported paraphrase; replace unsupported specifics with `[ADD: proof]`. Quality bar: no two hooks open with the same claim or structure.

### Step 4: Specify the opening blueprint

Choose the strongest supported hook and map 0.0–1.0s, 1.0–2.0s, and 2.0–3.0s into spoken text, on-screen text, and an editor-facing described beat. This is a text plan, not an instruction to edit or inspect media. Quality bar: the plan neither changes nor fabricates the supplied spoken content.

### Step 5: Return copy and safeguards

Provide three caption openings, a supplied CTA or `[ADD: approved CTA]`, and a context check. Quality bar: explicitly name any missing attribution, approval, or contextual limitation and make no promise about views, listens, or shares.

## Output Schema

```text
output_schema_version: "1.0.0"
evidence_ledger: EvidenceItem[]
excerpt_diagnosis: ExcerptDiagnosis
hook_options: HookOption[5]
recommended_blueprint: ThreeSecondBlueprint
supporting_copy: SupportingCopy
context_and_honesty_check: HonestyCheck
```

## Output Format

```markdown
# Podcast Clip Hook Lab: [episode or topic]

## Evidence boundary
- Supplied: [fact or quote]
- Unknown: [ADD: missing context]

## Excerpt diagnosis
- Usable phrase: "[quote]"
- Tension: [supplied / inference / unknown]

## Five hook options
1. **[structure]** — "[hook]" — Basis: [quote or supported paraphrase]

## Recommended 0–3 second blueprint
| Time | Spoken text | On-screen text | Described beat |
| --- | --- | --- | --- |
| 0.0–1.0s | [supplied quote or narration] | [text] | [editor-facing cue] |

## Supporting copy
- Caption opening: [text]
- CTA: [supplied CTA or ADD marker]

## Context and honesty check
- [attribution, truncation, or missing-proof note]
```

## Error Handling

- **No transcript excerpt:** Request a pasted excerpt and episode context; do not create a quote for a speaker.
- **Unattributed quote:** Label the speaker `[ADD: speaker]` and avoid presenting the wording as a verified quote.
- **Excerpt changes meaning when shortened:** Keep the qualifying phrase or recommend a different hook.
- **Audio/video-only request:** Explain that the skill accepts pasted text and returns a blueprint, not an edited clip.
- **Sensitive claim:** Preserve supplied constraints and flag it for producer or speaker approval.

## Examples

**Example 1: Founder interview**

Input: Audience = early-stage founders; excerpt = “We stopped adding features for two weeks and called ten customers.”

Decision: Use the supplied quote as the lead; do not claim the calls caused growth.

Output excerpt: `“We stopped adding features for two weeks.” — Basis: supplied guest quote.`

**Example 2: Career show**

Input: Audience = new managers; excerpt = “Your first one-on-one is not a status meeting.”; no CTA.

Decision: Use tension framing and preserve the limitation to one-on-ones.

Output excerpt: `“Your first one-on-one is not a status meeting.”` and `CTA: [ADD: approved CTA]`.

## Flywheel Connections

### Feeds Into

- `social-content` (S5-Distribution) — adapts approved clip copy into a posting plan.
- `youtube-script-writer` (S2-Content) — expands a validated excerpt into a longer script treatment.

### Fed By

- Producer-provided episode briefs and transcript excerpts — provide the complete factual basis.
- `product-marketing-context` (S1-Research) — can supply audience and approved messaging context.

### Feedback Loop

Teams can paste their own reviewed clip notes in later sessions to revise the next treatment; no external performance data is assumed.

```yaml
chain_metadata:
  skill_slug: "podcast-clip-hook-lab"
  stage: "S2-Content"
  timestamp: "2026-10-05"
  suggested_next:
    - "social-content"
    - "youtube-script-writer"
```

## Quality Gate

1. Required goal, audience, context, and transcript excerpt are present or explicitly requested.
2. Each factual claim and direct quote maps to the evidence ledger.
3. Five hooks use five named, distinct structures.
4. The blueprint has exactly three one-second intervals from 0.0 to 3.0 seconds.
5. Output describes text and editorial cues only; it does not claim to edit, inspect, render, or publish media.
6. No output promises views, listens, shares, reach, or platform performance.
7. The context check identifies unresolved attribution, approval, or truncation risks.

## References

- `LISTING.md` — buyer-facing listing and price ladder.
- `evidence/verified-demonstration.md` — concrete offline input, output, and checks.
