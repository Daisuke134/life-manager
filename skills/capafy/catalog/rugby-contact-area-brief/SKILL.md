---
name: rugby-contact-area-brief
description: >
  Turn buyer-pasted rugby team sheets, breakdown notes, and set-piece observations into a source-bounded contact-area brief. Use when a rugby analyst, coach, or podcast producer needs a disciplined match preview without claiming current data access.
license: MIT
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Analysis
---

# Rugby Contact-Area Brief

Rugby Contact-Area Brief converts one buyer-supplied rugby match packet into a traceable preview of ruck, maul, discipline, and set-piece questions. It is for the recurring pre-match job of deciding which supplied contact-area evidence deserves attention while keeping all missing team information explicit.

## Stage

This skill belongs to Stage S2: Analysis.

## When to Use

- A rugby writer has team sheets and match notes for one fixture and needs qualified coverage angles.
- A coach or analyst wants to organize supplied ruck, maul, penalty, and lineout observations before a review meeting.
- A podcast producer needs a short pre-match segment that distinguishes confirmed notes from unknowns.

## Input Schema

```text
match: string (required) — two teams, competition, date, and venue when supplied
team_sheets: string (required) — buyer-pasted starters, bench, availability, and role notes
contact_evidence: string (required) — supplied ruck, maul, tackle, penalty, or turnover observations
set_piece_notes: string (optional) — supplied scrum, lineout, restart, or kicking notes
coverage_goal: string (optional) — preview article, coaching discussion, or podcast segment
```

## Workflow

### Step 1: Set the evidence boundary

Extract only the supplied teams, roles, availability, and match observations. Label absent player status, referee, weather, score history, or current statistics `[UNVERIFIED]`. The quality bar is that a reader can identify every match-specific fact's source in the buyer packet.

### Step 2: Map the contact-area contest

Turn the supplied notes into up to four ruck, maul, tackle, turnover, or discipline questions. For each question, pair a cited observation with a limitation. The quality bar is a question-led analysis, not an invented performance claim.

### Step 3: Test conditional scenarios

Where a starter, role, or tactical note is tentative, write an `if confirmed` and `if changed` consequence. The quality bar is that uncertainty changes the brief visibly rather than being hidden in a generic disclaimer.

### Step 4: Assemble the match brief

Return a contact-area card, three coverage angles, a verification queue, and a 45-second spoken rundown. The quality bar is a self-contained text output that a buyer can adapt without treating it as a prediction or a current-data report.

## Output Schema

```text
output_schema_version: "1.0.0"
match_label: string
evidence_boundary: string[]
contact_area_cards: { area: string, supplied_evidence: string, analysis_question: string, confidence: "low" | "medium" | "high", limitation: string }[]
coverage_angles: { angle: string, supporting_input: string, caveat: string }[]
conditional_scenarios: { condition: string, implication: string }[]
verification_queue: string[]
pregame_rundown: string
```

## Output Format

```markdown
# Rugby Contact-Area Brief: [team A] v [team B] — [date]

## Evidence boundary
- Supplied: [fact]
- [UNVERIFIED]: [missing current fact]

## Contact-area cards
| Area | Supplied evidence | Analysis question | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| [ruck / maul / discipline / set piece] | [pasted note] | [qualified question] | [low/medium/high] | [gap] |

## Coverage angles
1. [angle] — Evidence: [supplied material]. Caveat: [limitation].

## Conditional scenarios
- If [condition]: [implication].

## Verify before using
- [fact to confirm]

## 45-second pre-match rundown
[source-bounded spoken summary]
```

## Error Handling

- **No single fixture:** Ask for one match packet; do not merge several fixtures into one brief.
- **No team sheets:** Produce a contact-area question list only and mark player-role implications `[UNVERIFIED]`.
- **Conflicting buyer notes:** Preserve both claims in the evidence boundary and ask which note controls the revision.
- **Request for current scores, squad news, odds, or weather:** Explain that the skill assesses pasted information only and ask the buyer to supply the facts they want considered.
- **Request for a certain result or wagering recommendation:** Decline the certainty framing and provide conditional rugby-analysis questions instead.

## Examples

### Example 1: Ruck-speed preview

**Input:** Estuary RFC v Highland RFC. The buyer's notes say Estuary used a fast first-receiver pattern in their last supplied match report; Highland's openside made five listed breakdown turnovers. Estuary's starting scrum-half is tentative.

**Decision:** Make Highland's supplied turnover note a medium-confidence ruck question, and write two scrum-half scenarios rather than selecting a starter.

**Output excerpt:** `Ruck: Highland's listed five breakdown turnovers make early-ball security the leading supplied question. Confidence medium; the report does not provide phase counts or confirm Estuary's scrum-half.`

### Example 2: Lineout and discipline review

**Input:** Northport v Valley. The buyer supplied three Northport lineout losses and Valley's eight listed penalties conceded in the previous notes. No referee or weather information is supplied.

**Decision:** Separate the lineout reliability question from the discipline question and place referee and weather in the verification queue.

**Output excerpt:** `Set piece: Northport's three supplied losses make lineout retention a coverage angle, but throwing causes and current selection are [UNVERIFIED].`

## Flywheel Connections

### Feeds Into

- `sports-podcast-run-sheet` (S2-Content) — the spoken rundown can seed a rugby segment.
- `football-postmatch-decision-review` (S2-Analysis) — both preserve a source-bounded review pattern without sharing sport-specific claims.

### Fed By

- Buyer-maintained team sheets, analyst notes, and match reports.
- A buyer's prior rugby review notes, when pasted into the next fixture packet.

### Feedback Loop

Buyers can report which supplied contact-area fields produced the clearest cards; use that feedback to refine the input checklist without asserting access to current rugby information.

```yaml
chain_metadata:
  skill_slug: "rugby-contact-area-brief"
  stage: "S2-Analysis"
  timestamp: "2026-10-25"
  suggested_next:
    - "sports-podcast-run-sheet"
    - "football-postmatch-decision-review"
```

## Quality Gate

1. The output covers exactly one buyer-supplied rugby fixture.
2. Every match-specific fact is traceable to the packet or labeled `[UNVERIFIED]`.
3. Each contact-area card contains evidence, a question, confidence, and a limitation.
4. Tentative selection or role information produces conditional scenarios.
5. The output contains no score prediction, wagering instruction, or claimed current-data access.
6. The verification queue lists only information that would improve the buyer's next revision.

## References

- `LISTING.md` — buyer-facing offer, plans, and capability boundary.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification record.
