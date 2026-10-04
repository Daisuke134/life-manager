---
name: podcast-hook-lab
description: >
  Turns a pasted podcast episode brief, transcript excerpt, or guest notes into an
  honest cold-open diagnosis, hook alternatives, host read, and segment roadmap.
  Use for planning a podcast opening; it does not edit audio, publish episodes, or predict downloads.
license: MIT
version: "1.0.0"
tags: [podcast, cold-open, hooks, host-read, audio-planning]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Content
---

# Podcast Hook Lab

Podcast Hook Lab turns the buyer's supplied episode material into a text-only opening
package. It separates supplied facts from editorial framing so a host can choose a
cold open without inventing guest claims, outcomes, quotes, or listener evidence.

## Stage

This skill belongs to Stage S2: Content.

## When to Use

- A host has guest notes and needs a compelling opening before recording.
- A producer has a pasted transcript excerpt and wants a tighter cold open.
- A branded podcast needs multiple accurate episode promises and host-read options.

## Input Schema

```text
episode_goal: string (required)
listener: string (required)
topic_or_guest: string (required)
pasted_material: string (required) — notes, transcript excerpt, or interview brief
approved_facts_or_quotes: string (optional)
tone: string (optional)
cta: string (optional)
constraints: string (optional)
```

## Workflow

### Step 1: Build an evidence ledger

List supplied topic facts, exact quotes, names, listener promise, and constraints.
Mark anything missing `[ADD: ...]`. Quality bar: every factual phrase in the opening
has a supplied source or an explicit missing-proof marker.

### Step 2: Diagnose the supplied opening

Identify the first stated idea, listener relevance, tension, and unanswered question.
When no opening exists, report that it is absent. Quality bar: distinguish `supplied`,
`inference`, and `unknown` rather than describing imagined audio.

### Step 3: Draft five distinct cold-open hooks

Use five structures: question, contrast, moment, myth correction, and stakes. Keep
claims within the supplied material. Quality bar: no repeated premise or unsupported
outcome claim.

### Step 4: Make a 30-second host-read roadmap

Build 0–10, 10–20, and 20–30 second blocks with host words, optional supplied quote,
and a transition into the episode. Quality bar: it is a spoken-text plan, not audio
editing instructions or a claim that audio was inspected.

### Step 5: Critique and package

Return title options, episode-description lead lines, the buyer-supplied CTA, and an
honesty check. Quality bar: flag unattributed quotes, missing proof, and listener
benefits that need approval.

## Output Schema

```text
output_schema_version: "1.0.0"
evidence_ledger: EvidenceItem[]
opening_diagnosis: OpeningDiagnosis
cold_open_options: HookOption[5]
host_read_roadmap: TimedHostRead
supporting_copy: SupportingCopy
honesty_check: HonestyCheck
```

## Output Format

```markdown
# Podcast Hook Lab: [episode]
## Evidence boundary
- Supplied: [fact]
- Unknown: [ADD: fact]
## Five cold-open options
1. **[structure]** — "[host line]" — Evidence: [source]
## Recommended 30-second host read
| Time | Host words | Transition |
| --- | --- | --- |
| 0–10s | [words] | [cue] |
## Supporting copy
- Title: [option]
- Description lead: [line]
## Honesty check
- [unverified claim or approval need]
```

## Error Handling

- **No episode material:** request the listener, topic, and notes before writing a hook.
- **Unsourced guest statement:** label it `[ADD: verify quote]` instead of attributing it.
- **Conflicting brand constraints:** list the conflict and request a governing instruction.
- **Audio-file request:** explain that the output is a text plan from pasted material, not edited audio.

## Examples

**Example 1: Guest interview**

Input: listener = new managers; topic = delegation; supplied fact = guest began delegating recurring reports in weekly blocks.

Decision: Use the moment structure without claiming a productivity result.

Output excerpt: `“The first task she delegated was a recurring report—not because it was easy, but because it happened every week.”`

**Example 2: Solo episode**

Input: topic = project retrospectives; supplied material = three questions: what changed, what surprised us, what to try next.

Decision: Use a contrast hook and mark outcome proof absent.

Output excerpt: `“A retrospective is not a list of what went wrong; it starts with what changed.”`

## Flywheel Connections

### Feeds Into

- `youtube-script-writer` (S2-Content) — adapts an approved episode premise into video script material.
- `social-content` (S5-Distribution) — turns approved copy into promotional text.

### Fed By

- Pasted host notes, guest briefs, and transcript excerpts.
- `product-marketing-context` (S1-Research) — contributes buyer-approved facts.

### Feedback Loop

Hosts can paste their own reviewed listener feedback in a later session; it is treated
as supplied material, never as an externally observed metric.

```yaml
chain_metadata:
  skill_slug: "podcast-hook-lab"
  stage: "S2-Content"
  timestamp: "2026-09-28"
  suggested_next: ["youtube-script-writer", "social-content"]
```

## Quality Gate

1. Required episode goal, listener, topic, and pasted material are present.
2. Each factual hook phrase has evidence or an `[ADD: ...]` marker.
3. Five hooks use five named structures.
4. The host-read roadmap has exactly three ten-second blocks.
5. The output claims text planning only, never audio editing, publishing, or analytics access.
6. It promises no downloads, audience growth, sales, or ranking.
7. The honesty check names every unresolved quote, proof, or approval need.

## References

- `LISTING.md` — buyer-facing offer and capability boundary.
- `evidence/verified-demonstration.md` — offline worked input and output.
