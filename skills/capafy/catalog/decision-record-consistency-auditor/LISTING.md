Primary Model: Claude Sonnet 4.6 · category: 生産性 · tags: decision records, architecture decisions, project governance

R1 recurring input : Teams revise decisions through meeting notes, ADRs, project briefs, and operating documents.
R2 recurring output: Each review produces a new traceable conflict and ambiguity report for the supplied records.
day-8 answer       : A prior report cannot reconcile a later decision record, revised scope, or newly supplied source text.
demand evidence    : Offline inventory selection reported no observable local sales signal. This differentiated candidate makes no winner or demand claim.

| cycle | price | cap | trial |
|---|---:|---:|---|
| week | $9.99 | 20 | No Free Trial |
| month | $24.99 | 60 | No Free Trial |

## Title
Decision Record Consistency Auditor

## shortDescription
Compare pasted decision records and meeting notes to identify conflicting choices, missing context, and unresolved questions while retaining a traceable source ledger.

## welcomeMessage
👋 Paste the decision records or meeting notes you want compared, including dates, owners, scope, and source precedence if you have it. I’ll make a source-linked ledger, identify only supported conflicts, and leave unknowns visible.

Example: “Record A says the mobile app uses offline caching for travel bookings. Record B says booking data stays online-only. Both cover the booking flow, but neither says which record is newer. Build a reconciliation brief.”

## detailedDescription
✨ **Reconcile the decisions already in your documents**

Paste ADRs, meeting notes, project briefs, or operating decisions. The Agent organizes the decisions you provide into a ledger, compares overlapping scope, and separates direct conflicts from missing context.

⚙️ **How it works**

1. Extracts decision, source, date, owner, scope, rationale, and status from your text.
2. Compares records only where their stated scope overlaps.
3. Shows conflicting supplied statements side by side.
4. Marks unclear precedence, missing ownership, and absent rationale as open items.
5. Produces questions for a reconciliation meeting instead of choosing a result without evidence.

📦 **Each consistency report includes**

- A source-linked decision ledger
- A conflict table with the shared scope and exact supplied statements
- An ambiguity and missing-context table
- A reconciliation agenda of unresolved questions
- A verification checklist for the decision owner

💡 **What makes it different**

- **Decision-specific:** it compares the commitments in several records instead of merely summarizing them.
- **Evidence-bound:** it separates direct contradictions from incomplete information.
- **Traceable:** it keeps each finding tied to the text you supplied.

👤 **Built for**

Product, engineering, operations, and program teams reconciling decisions that have accumulated across their own documents. It uses only pasted material and does not inspect repositories, tickets, calendars, approvals, or implementation state. Confirm every final resolution with the accountable decision owner.
