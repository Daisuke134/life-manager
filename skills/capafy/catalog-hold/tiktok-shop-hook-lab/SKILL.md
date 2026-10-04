---
name: tiktok-shop-hook-lab
description: >
  Turn a pasted TikTok Shop product brief or rough opening into a text-only product-discovery
  diagnosis, evidence-bounded hook rewrites, caption variants, and shot-list blueprint.
  Use for TikTok Shop opening development, not video editing, publishing, or sales prediction.
license: MIT
version: "1.0.0"
tags: [tiktok-shop, product-hooks, short-form-video, copywriting, social-media]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Content
---

# TikTok Shop Hook Lab

Create an evidence-bounded product-opening package for one TikTok Shop video from
material the seller pastes into chat. The skill improves the words, product framing,
and described visual beats without claiming to inspect media, edit video, access shop
data, publish a post, or predict sales.

## Stage

This skill belongs to Stage S2: Content.

## When to Use

- A TikTok Shop seller has a rough product opening and needs distinct text hooks before filming.
- A creator partner has approved product facts but needs a first-three-seconds discovery blueprint.
- A social manager has a pasted product transcript or video description and wants an opening diagnosis without uploading media.
- A product marketer needs caption and product-title variants that keep every factual claim grounded in supplied material.

## Input Schema

```text
video_goal: string (required) — desired buyer action or product lesson
buyer: string (required) — intended product viewer
brief_or_transcript: string (required) — pasted script, rough opening, or video description
product: string (required) — product or product message
approved_product_facts: string (optional) — facts, constraints, price, materials, or features safe to state
tone: string (optional) — e.g. direct, playful, demonstrative
cta: string (optional) — seller-supplied call to action
constraints: string (optional) — banned claims, duration, compliance, brand notes
```

## Workflow

### Step 1: Establish the evidence boundary

Extract only supplied product facts, buyer, goal, CTA, and constraints. Mark every
missing fact as `[ADD: ...]`; do not invent price, inventory, reviews, outcomes,
product capabilities, or buyer testimonials. Quality bar: each factual hook claim has
a source phrase in the evidence ledger.

### Step 2: Diagnose the supplied product opening

Identify the first spoken line, first described visual beat, buyer cue, product
discovery, proof, friction, and unanswered question. If no opening is supplied, say
`No opening supplied` rather than imagining footage. Quality bar: label each diagnosis
as `supplied`, `inference`, or `unknown`.

### Step 3: Choose differentiated hook angles

Create five hooks using distinct structures: buyer interruption, product contrast,
feature reveal, objection reversal, and use-moment consequence. Preserve the supplied
buyer and product; replace unsupported detail with `[ADD: proof]`. Quality bar: no two
hooks share the same opening claim or rhetorical structure.

### Step 4: Turn one hook into a first-three-seconds blueprint

For the strongest supported hook, specify the spoken line, on-screen text, and a
described visual beat at 0.0–1.0s, 1.0–2.0s, and 2.0–3.0s. This is a production
blueprint, not an edited video. Quality bar: every visual direction is feasible from
the seller's description and does not assert access to media.

### Step 5: Produce supporting copy and a self-critique

Return three caption openings, three product-title text options, an optional supplied
CTA, and a risk check for vague claims, missing proof, or a mismatched buyer. Quality
bar: the critique names at least one limitation and does not promise sales, views,
conversion, or platform performance.

## Output Schema

```text
output_schema_version: "1.0.0"
evidence_ledger: EvidenceItem[]
product_opening_diagnosis: OpeningDiagnosis
hook_options: HookOption[5]
recommended_blueprint: ThreeSecondBlueprint
supporting_copy: SupportingCopy
honesty_check: HonestyCheck
```

## Output Format

```markdown
# TikTok Shop Hook Lab: [product]

## Evidence boundary
- Supplied: [fact or constraint]
- Unknown: [ADD: missing fact]

## Product-opening diagnosis
- First line: [supplied line or No opening supplied]
- Buyer cue: [supplied / inference / unknown]
- Product discovery: [diagnosis]

## Five hook options
1. **[structure]** — "[hook]" — Evidence: [supplied source or ADD marker]

## Recommended 0–3 second blueprint
| Time | Spoken line | On-screen text | Described visual beat |
| --- | --- | --- | --- |
| 0.0–1.0s | [line] | [text] | [description] |

## Supporting copy
- Caption opening: [text]
- Product-title text: [text]
- CTA: [supplied CTA or ADD marker]

## Honesty check
- [unsupported claim removed or missing proof]
```

## Error Handling

- **No usable brief:** Ask for the buyer, goal, product, and pasted opening or product topic; do not fabricate a product video.
- **Unsupported product claim:** Replace it with `[ADD: proof]` or a process-based line.
- **Conflicting buyer or CTA:** Show both supplied instructions and ask which one governs the recommendation.
- **Media-only request:** Explain that the skill uses pasted text or a description and returns a blueprint, not edited video.
- **Regulated or sensitive product:** Preserve seller-provided constraints and flag claims requiring human review.

## Examples

**Example 1: Commuter tumbler**

Input: Buyer = commuters; product = insulated tumbler; approved fact = the lid twists
closed; rough opening = “This is my new tumbler.”

Decision: The generic opening does not identify the buyer or supported feature. Use a
feature-reveal hook and avoid claims about temperature retention.

Output excerpt: `“Commuters: this tumbler lid twists closed before it goes in your bag.”`

**Example 2: Desk cable organizer**

Input: Buyer = people with charging cables on a desk; product = cable organizer;
proof = holds three cables; no CTA supplied.

Decision: Use a buyer-interruption hook; do not claim it eliminates clutter.

Output excerpt: `“Three charging cables, one place on your desk.”` and `CTA: [ADD: seller-approved CTA]`.

## Flywheel Connections

### Feeds Into

- `youtube-script-writer` (S2-Content) — expands an approved hook into a fuller script.
- `social-content` (S5-Distribution) — adapts approved text into a posting plan.

### Fed By

- `product-marketing-context` (S1-Research) — supplies approved product facts and buyer notes.
- Seller-provided product briefs and transcripts — supply the only factual basis for claims.

### Feedback Loop

Sellers can paste their own post-review notes in a later session; the skill uses only
those notes to revise the next brief and never treats an unsupplied shop metric as observed.

```yaml
chain_metadata:
  skill_slug: "tiktok-shop-hook-lab"
  stage: "S2-Content"
  timestamp: "2026-10-04"
  suggested_next:
    - "youtube-script-writer"
    - "social-content"
```

## Quality Gate

1. Required goal, buyer, brief, and product are present or the missing fields are requested.
2. Every factual claim in a hook appears in the supplied evidence ledger or is marked `[ADD: ...]`.
3. Five hooks use five named, distinct structures.
4. The recommended blueprint includes exactly three one-second intervals from 0.0 to 3.0 seconds.
5. Output describes text and visual beats only; it does not claim to edit, render, inspect, or publish media.
6. No output promises views, reach, sales, conversion, or platform performance.
7. The honesty check names all unresolved proof, approval, or compliance gaps.

## References

- `LISTING.md` — buyer-facing listing, price ladder, and honest capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input and output verification.
