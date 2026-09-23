Primary Model: Claude Sonnet 4.6 · category: 分析 · tags: AI evaluation, failure triage, evidence brief

## Offline selection notes

The release-owned `sales_selector.py` was used through its pure `select_signal`
function against the current local source catalog only: 28 candidates, each supplied
with zero sales, recent sales, rating, and review count. It returned `signal: none`
and advised against inventing a winner. The current catalog was checked for AI
evaluation, evaluation failure, failure triage, and test-case triage candidates; no
matching candidate exists. This candidate is distinct from the experiment-readout
deck: it turns individual pasted expected-versus-observed cases into an uncertainty-
bounded investigation brief, rather than telling the story of an experiment result.

## Renewal reason

Each evaluation run can introduce different cases, expected behavior, observed
behavior, hypotheses, ownership, and evidence gaps. A prior brief is stale when any
of that supplied material changes.

## Unit economics

This offline candidate uses a paid recurring subscription and bounded message caps.
Every plan explicitly has `No Free Trial`. The platform sandbox fee and hosted-cost
receipt must be obtained and checked for a positive contribution before any later
platform submission; neither is asserted by this source candidate.

| cycle | price | cap | trial |
|---|---:|---:|---|
| week | $7.99 | 20 | No Free Trial |
| month | $27.99 | 60 | No Free Trial |

## Verified demonstration

See `evidence/verified-demonstration.md` for a concrete pasted evaluation record,
the resulting triage brief, and verification notes.

## Title
AI Evaluation Failure Triage Brief

## shortDescription
Turn pasted AI evaluation cases into an evidence-bounded triage brief that separates expected and observed behavior, hypotheses, and missing checks without claiming a root cause or fix.

## welcomeMessage
👋 Paste the evaluation goal, case inputs, expected and observed results, relevant prompt or configuration excerpts, and any run notes. I’ll turn them into a careful failure-triage brief for review.

Example: “Goal: extract invoice totals. Case A expected 1,240.00 but observed 124.00. The prompt says preserve decimals; no model version or scoring record was supplied.”

## detailedDescription
✨ **Turn evaluation evidence into a focused inspection brief**

Paste the cases already available to your team: the evaluation goal, inputs or
excerpts, expected and observed results, relevant prompt or configuration text, run
notes, and any supplied owner or priority. The Agent turns only that material into a
structured triage brief.

⚙️ **How it works**

1. Creates a case record for each pasted expected-versus-observed result.
2. Separates observations, expectations, reported explanations, hypotheses, and unknowns.
3. Preserves supplied priorities, owners, timings, and completed work without adding any.
4. Builds a next-inspection queue for reproducibility, context, configuration, and scoring gaps.
5. Produces an evidence ledger for the brief’s material conclusions.

📦 **You receive**

- A concise triage summary for the supplied evaluation goal
- A case table that makes each mismatch and its evidence status clear
- A hypothesis register that does not turn guesses into causes
- A bounded next-inspection queue and evidence ledger

💡 **What makes it different**

- It is for individual AI evaluation failures, not a generic experiment summary or a decision deck.
- It keeps expected behavior, observed behavior, supplied explanations, and unknowns separate.
- It works from your pasted material and model reasoning only; it does not access systems or run tests.
- It does not claim a root cause, regression, fix, score, or performance improvement.

👤 **Built for**

AI product managers, evaluation leads, ML engineers, QA teams, and technical
reviewers who need a careful shared brief before deciding what to inspect.
