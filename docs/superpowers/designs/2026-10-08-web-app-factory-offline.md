# Web App Factory: offline product lifecycle

Approved scope: a local, zero-additional-spend first increment for existing web products. This is a design record, not a second task/state SSOT. The unified SSOT remains authoritative. No deployment, scheduler, account registration, marketing submission, payment or inference call is part of this increment.

## Architecture and precedents

A pure CommonJS evaluator and a JSON-stdin CLI produce a bounded task handoff. Reuse `mobile-product-registry.normalizeProduct` to validate pinned imported source and `financial-record-contract.projectFinancialRecord` to consume established CFO records. No new dependency, state store, browser owner, accounting ledger, or independent loop implementation. The existing self-build owner may consume the handoff later; runtime admission and effect leases remain mandatory there.

The report separates source existence, offline QA, production readback, marketing readiness, and economic evidence. A successful test never means a working deployment or revenue. QA must match product and pinned revision. Demand needs a competitor example and an independent problem/demand signal; missing coverage blocks every distribution draft with demand_unverified. Marketing claims must have evidence for this revision, and no unresolved QA failures. Zero-cost distribution is a draft plan restricted to explicitly permitted, individually owned channels; no executable command is emitted.

## Ownership and effects

Input includes an explicit source owner, current worktree lease, owned repository-relative paths, and a coordination inventory. A missing/expired lease or incomplete inventory fences the handoff. Any foreign overlapping path or identical external resource fences it, even if its observation is old: expiry alone is not permission to take over. This evaluator does not acquire locks; its report is never an execution capability. Runtime callers must atomically reacquire the existing leases before acting.

Every report permanently states `external_effects: false` and `additional_spend_minor: 0`. Nonzero budget, paid channels, missing permission, missing cost evidence or account ownership block distribution preparation. Other channels such as paid ads, automated outreach, email/DM, and scraping are outside this increment.

## Evidence and economics

Metric snapshots cover visits, successful uses, paid invoices, revenue, refunds, and costs for one explicitly supplied period/product/currency. Only a supplied snapshot declaring complete live provider readback, with a receipt reference, timestamp and nonnegative safe integer, passes the input contract. Reports explicitly label evidence operator_attested and receipts_authenticated false: this offline evaluator does not authenticate receipts or verify channel cost/permission. Even draft_ready is conditional planning coverage, never execution permission. Missing/stale/test/partial evidence remains `unknown` with null value. Zero is verified only by a complete zero-valued snapshot. Net contribution = revenue minus refunds minus costs only when all three share period and currency; losses stay negative. It is not MRR, profit after taxes, or bank cash. FinancialRecords are separately validated using the shared contract; no write or new refund classification is invented.

## Product evidence and public boundary

Application-specific source, audit findings, ownership records and real operator input belong in the product owner's private handoff. Do not copy application files, repository history, customer data, logs, credentials or private evidence into this MIT Life Manager module. Public examples use fictional products and opaque synthetic receipts.

The generic QA categories are core flow, quota, entitlement, copy and privacy. Each category requires revision-matched evidence; missing or failing evidence blocks distribution preparation. Product-specific investigation and remediation belong to the authorized product owner. The evaluator neither diagnoses a deployed application nor applies changes to it.

Publishable scope is only the evaluator, CLI, tests, synthetic example and generic documentation plus existing MIT dependencies. Any source visibility change is a separate authorized operation. The PR remains draft and integration belongs to the existing orchestrator.
