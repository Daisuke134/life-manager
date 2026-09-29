---
name: earnings-call-brief
description: Turn a pasted earnings-call transcript, shareholder letter, and buyer-supplied figures into an evidence-bounded earnings brief with changes, open questions, and an uncertainty ledger.
license: MIT
version: "1.0.0"
tags: [earnings, investor-relations, financial-analysis, transcript-summary, research-workflow]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  stage: S2-Content
---

# Earnings Call Brief

Turn material the buyer pastes for one reporting period into a structured, source-bounded
earnings brief. This is a reading and synthesis workflow, not a market-data feed, financial
advice service, or earnings prediction tool.

## When to Use

- An investor or analyst has a pasted earnings-call transcript and wants the changes surfaced consistently.
- An IR, finance, or research team has a shareholder letter and supplied figures that need a reusable internal brief.
- A reader needs management statements separated from reported figures, inferred implications, and unanswered questions.

## Input Schema

```text
company_or_subject: string (required)
reporting_period: string (required)
transcript_or_letter: string (required) — pasted excerpt, transcript, or shareholder letter
supplied_figures: string (optional) — buyer-provided revenue, margins, guidance, KPI values, or comparisons
prior_period_context: string (optional) — buyer-provided earlier-period notes for comparison
reader_goal: string (required) — e.g. prepare internal discussion questions
constraints: string (optional) — terminology, word limit, prohibited claims, or review needs
```

## Workflow

### Step 1: Establish the evidence boundary

List the company, period, figures, dates, statements, and comparisons explicitly supplied by
the buyer. Label each item `Supplied`, `Inference`, or `[UNVERIFIED]`. Do not supply a price,
consensus estimate, subsequent event, market reaction, or missing prior-period fact.

### Step 2: Build the reported-facts ledger

Make a table that preserves the buyer's units and period labels. Separate:

- reported figures and buyer-supplied comparisons;
- management statements or intentions;
- absent figures, definitions, and dates.

If a number cannot be reconciled from the pasted material, retain its wording and flag it rather
than calculating a replacement.

### Step 3: Identify changes and drivers

For each supplied comparison, name the stated change, the stated driver, and the evidence phrase.
If the transcript does not state a driver, write `Driver: [UNVERIFIED]`. Never turn a management
statement into a verified outcome.

### Step 4: Produce the brief and question set

Return an executive readout, fact ledger, stated changes, management claims, risks/unknowns, and
five review questions. A review question must point to a missing definition, comparison, timing,
or condition in the pasted record.

### Step 5: Run the financial-boundary check

State that the brief is based only on pasted material and model reasoning. Remove buy/sell/hold
language, price targets, certainty claims, and unsupplied current information.

## Output Format

```markdown
# Earnings Call Brief: [company] — [period]

## Evidence boundary
- Supplied: [fact]
- Management statement: [statement]
- Unknown: [UNVERIFIED]

## Executive readout
- Reported: [supported change]
- Stated driver: [supported wording or UNVERIFIED]
- Open point: [missing item]

## Fact ledger
| Topic | Pasted evidence | Classification | Caveat |
| --- | --- | --- | --- |

## Changes and stated drivers
| Topic | Change | Stated driver | Evidence status |
| --- | --- | --- | --- |

## Questions for the next review
1. [question tied to a missing or conditional item]

## Boundary note
This is a summary of pasted material, not investment advice or current market information.
```

## Error Handling

- **No period or subject:** Ask for both; do not infer a reporting period from a company name.
- **Narrative without figures:** Summarize stated themes and list the missing numerical evidence as `[UNVERIFIED]`.
- **Figures without source context:** Preserve them as buyer-supplied figures; do not present them as independently verified.
- **Request for a recommendation:** Provide a neutral question list and explain that the skill does not issue investment recommendations.
- **Conflicting figures:** Quote both supplied values, identify the conflict, and request the authoritative source.

## Quality Gate

1. The output names the supplied company/subject and reporting period.
2. Every reported figure or comparison has a traceable pasted source.
3. Management statements remain distinct from reported facts.
4. At least five questions identify a real missing, conditional, or undefined item.
5. No output claims current prices, news, consensus, market reaction, browsing, or financial advice.
6. Every unknown is marked `[UNVERIFIED]` or `[ADD: ...]`.

## References

- `LISTING.md` — buyer-facing description and subscription configuration.
- `evidence/verified-demonstration.md` — concrete offline input, output, and verification notes.
