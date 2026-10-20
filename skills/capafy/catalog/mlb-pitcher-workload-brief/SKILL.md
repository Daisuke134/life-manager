---
name: mlb-pitcher-workload-brief
description: >
  Turn a buyer-pasted MLB pitcher's recent outing log, rest notes, and editorial question into an evidence-bounded workload brief. Use when a baseball writer, podcast producer, or serious fan needs a cautious next-start workload discussion without claiming current baseball data.
license: MIT
version: "1.0.0"
tags: [mlb, baseball, pitcher-workload, sports-analysis, sports-writing]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# MLB Pitcher Workload Brief

Turn the pitcher workload record that a buyer supplies into a transparent next-start discussion. This text-only analysis is deliberately separate from a lineup preview, an in-game pitching-change brief, and a postgame recap: it traces the recent outing log, identifies what it can and cannot support, and makes every prospective workload statement conditional.

## Stage

This skill belongs to Stage S2: Analysis.

## When to Use

- A baseball writer has a starter's pasted recent outing log and needs a cautious preview angle for the next scheduled start.
- A podcast producer needs a source-bounded segment on supplied pitch totals, rest intervals, and an incomplete workload context.
- A beat reporter wants to distinguish documented outings from an unsupported claim about injury, restriction, or manager intent.
- A serious fan wants to organize their own pitching notes without treating missing rotation or availability facts as known.

## Input Schema

```text
pitcher_and_start: string (required) — pitcher name or label, team labels, and next-start date/opponent only if supplied
recent_outing_log: string (required) — buyer-pasted dates or order, innings, pitch totals, and any stated exit notes
rest_and_plan_notes: string (required) — supplied rest interval, stated limit, rotation context, or uncertainty
editorial_question: string (required) — preview, podcast, article, or fan-discussion question
supporting_evidence: string (optional) — buyer-pasted prior workload baseline, quotes, or matchup context
desired_length: string (optional) — requested narrative length or segment duration
```

## Workflow

### Step 1: Build the outing ledger

Extract each supplied outing, pitch total, innings note, rest interval, and stated reason for an early exit. Keep dates and sequence exactly as supplied. Good output clearly labels absent pitch counts, exit reasons, injury facts, rotation decisions, and current availability `[UNVERIFIED]`; it never fills them from assumed baseball knowledge.

### Step 2: Separate record from interpretation

List the documented workload signals first, then write a cautious interpretation of what they may make worth discussing. Do not turn pitch totals alone into a report of fatigue, a medical conclusion, or a team plan. A good interpretation names the input fact and its limitation.

### Step 3: Write conditional thresholds

Provide up to three conditional workload thresholds such as an early-check point, a normal-length possibility, or a reason to defer judgment. Each threshold must name its supplied basis, a caveat, and the fact that would change the read. These are editorial framing tools, never forecasts or instructions to a team.

### Step 4: Produce the workload brief

Return the evidence boundary, outing ledger, conditional thresholds, coverage narrative, and verification queue. The result is complete as text even if the record is sparse; uncertainty stays visible rather than being replaced with a current claim.

## Output Schema

```text
output_schema_version: "1.0.0"
pitcher_label: string
evidence_boundary: string[]
outing_ledger: { outing_label: string, supplied_workload: string, note: string, limitation: string }[]
workload_read: { documented_signals: string[], interpretation: string, confidence: "low" | "medium" | "high", limitation: string }
conditional_thresholds: { threshold: string, supplied_basis: string, caveat: string, changes_if: string }[]
coverage_narrative: string
verification_queue: string[]
```

## Output Format

```markdown
# MLB Pitcher Workload Brief: [pitcher] — [supplied next-start label]

## Evidence boundary
- Supplied: [outing or rest fact]
- [UNVERIFIED]: [missing current fact]

## Outing ledger
| Supplied outing | Workload | Note | Limitation |
| --- | --- | --- | --- |
| [outing label] | [innings / pitches as supplied] | [stated note] | [gap] |

## Workload read
- Documented signals: [input-bound facts]
- Interpretation: [cautious analysis]
- Confidence: [low/medium/high]
- Limitation: [what the record cannot establish]

## Conditional editorial thresholds
1. **[threshold]:** [supplied basis]. Caveat: [limitation]. This changes if [fact].

## Coverage narrative
[source-bounded paragraph]

## Verify before using
- [current fact to confirm]
```

## Error Handling

- **No outing log:** Ask for at least one supplied outing or pitch-total note; do not fabricate a workload trend.
- **Sequence without dates:** Preserve the sequence as supplied and mark the actual rest interval `[UNVERIFIED]` rather than calculating one.
- **Early exit without reason:** State only that an early exit was supplied; put its reason and any health implication in the verification queue.
- **Conflicting supplied totals:** Quote both values in the evidence boundary and ask which record should govern the revision.
- **Request for a current rotation, injury update, certain workload, or wager:** Explain that the skill evaluates only pasted material and offer conditional editorial framing instead.

## Examples

### Example 1: Recent high-pitch outing

**Input:** Harbor RHP Reyes threw 96 pitches six days ago, then 82 pitches one day before that. He left the latest start after five innings; no reason is supplied. The buyer wants a 45-second preview.

**Decision:** Preserve all three supplied outing facts, avoid calling the exit an injury, and make the next-start length a conditional question.

**Output excerpt:** `The supplied record establishes a 96-pitch outing followed by an 82-pitch outing; it does not establish why the latest start ended after five innings. Treat an early workload check as a conditional preview angle, not a reported limit.`

### Example 2: Sparse rest information

**Input:** Northbridge LHP Vale worked 74 pitches in the buyer's last log. The buyer says the next start is "later this week" and supplies no prior outing or stated limit.

**Decision:** Use the 74-pitch outing as the only workload fact and mark the rest interval and plan `[UNVERIFIED]`.

**Output excerpt:** `No workload progression can be inferred from one supplied 74-pitch outing. The rest interval and stated plan are [UNVERIFIED], so the segment should ask what the next record confirms rather than assert a restriction.`

## Flywheel Connections

### Feeds Into

- `mlb-lineup-matchup-brief` (S2-Analysis) — a verified workload record can add pitcher context to a buyer's separate lineup card.
- `sports-podcast-run-sheet` (S2-Content) — the coverage narrative can become a source-bounded segment.

### Fed By

- Buyer-maintained outing logs, pitch-count notes, rest notes, and reporting excerpts.
- `mlb-series-preview-brief` (S2-Analysis) — a series record may identify the starter that needs a separate workload discussion.

### Feedback Loop

Buyers can report which fields make the workload narrative most useful; improve the pasted-input checklist without adding a claim of current rotation or health-data access.

```yaml
chain_metadata:
  skill_slug: "mlb-pitcher-workload-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-21"
  suggested_next:
    - "mlb-lineup-matchup-brief"
    - "sports-podcast-run-sheet"
```

## Quality Gate

1. The output identifies one buyer-supplied pitcher and one supplied next-start context.
2. Every outing, pitch total, rest interval, and exit note is traceable to the input or labeled `[UNVERIFIED]`.
3. The workload read separates documented signals from interpretation and names a limitation.
4. Every threshold is conditional and gives a supplied basis, caveat, and change condition.
5. The output does not claim current rotation, injury, availability, pitch count, or game-feed access.
6. The output gives no wager, guaranteed workload, medical conclusion, or certain game outcome.

## References

- `LISTING.md` — buyer-facing offer, plans, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification record.
