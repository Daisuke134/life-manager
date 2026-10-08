# Web App Factory: offline product lifecycle

Approved scope: a local, zero-additional-spend first increment for an existing web product, PDF Insight. This is a design record, not a second task/state SSOT. The unified SSOT remains authoritative. No deployment, scheduler, account registration, marketing submission, payment or inference call is part of this increment.

## Architecture and precedents

A pure CommonJS evaluator and a JSON-stdin CLI produce a bounded task handoff. Reuse `mobile-product-registry.normalizeProduct` to validate pinned imported source and `financial-record-contract.projectFinancialRecord` to consume established CFO records. No new dependency, state store, browser owner, accounting ledger, or independent loop implementation. The existing self-build owner may consume the handoff later; runtime admission and effect leases remain mandatory there.

The report separates source existence, offline QA, production readback, marketing readiness, and economic evidence. A successful test never means a working deployment or revenue. QA must match product and pinned revision. Demand needs a competitor example and an independent problem/demand signal. Marketing claims must have evidence for this revision, and no unresolved QA failures. Zero-cost distribution is a draft plan restricted to explicitly permitted, individually owned channels; no executable command is emitted.

## Ownership and effects

Input includes an explicit source owner, current worktree lease, owned repository-relative paths, and a coordination inventory. A missing/expired lease or incomplete inventory fences the handoff. Any foreign overlapping path or identical external resource fences it, even if its observation is old: expiry alone is not permission to take over. This evaluator does not acquire locks; its report is never an execution capability. Runtime callers must atomically reacquire the existing leases before acting.

Every report permanently states `external_effects: false` and `additional_spend_minor: 0`. Nonzero budget, paid channels, missing permission, missing cost evidence or account ownership block distribution preparation. Other channels such as paid ads, automated outreach, email/DM, and scraping are outside this increment.

## Evidence and economics

Metric snapshots cover visits, successful uses, paid invoices, revenue, refunds, and costs for one explicitly supplied period/product/currency. Only a complete, live, provider-readback snapshot with a receipt, timestamp and nonnegative safe integer is counted. Missing/stale/test/partial evidence remains `unknown` with null value. Zero is verified only by a complete zero-valued snapshot. Net contribution = revenue minus refunds minus costs only when all three share period and currency; losses stay negative. It is not MRR, profit after taxes, or bank cash. FinancialRecords are separately validated using the shared contract; no write or new refund classification is invented.

## PDF Insight and public boundary

First target: PDF Insight, public URL https://clear-pdf-converter.com. Its application source is private and has no verified redistribution license. Do not copy application files, repository history, customer data, logs, credentials or private evidence into this MIT Life Manager module. Public examples use fictional products and opaque synthetic receipts. Operator-only target input stays outside Git.

Known source-audit concerns for a later isolated private patch: free lifetime quota versus server monthly counting; ambiguous monthly boundary; environment-aware entitlement; repeated parse charging; mutable client subscription policies; clearer summary/parse quota copy. These are source findings, not proof of production exploit or spend. No safe exclusive owner of that separate private source has been established. This increment records QA as unknown/failing and fences distribution; it does not claim those app defects fixed. Security migrations must be reviewed in that private owner lane and must not be applied here.

Publishable boundary is only the new evaluator, CLI, tests, synthetic example and documentation plus existing MIT dependencies. No visibility change is requested or performed. Any later PR must be draft and integration belongs to the existing orchestrator.
