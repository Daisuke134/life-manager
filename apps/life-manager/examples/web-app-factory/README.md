# Offline Web App Factory

A zero-dependency, zero-additional-spend **planning module** for existing web products. It is not an autonomous deployed agent. It validates supplied evidence; it cannot authenticate provider receipts or discover active sessions. Nothing is sent, published, purchased, scheduled or changed by this module.

From the Life Manager repository root:

```sh
node apps/life-manager/scripts/web-app-factory-plan.js --now 2026-10-08T09:00:00Z \
  < apps/life-manager/examples/web-app-factory/example.json
node --test apps/life-manager/lib/web-app-factory.test.js \
  apps/life-manager/scripts/web-app-factory-plan.test.js
```

The sample is fictional and deliberately blocked. Missing revenue is `null`, not zero. For current operator input, omit `--now`. The stdin limit is 1 MiB. Invalid input returns exit 1 with a generic error; no input is echoed. Successful planning returns exit 0 even when readiness is blocked: inspect `next_task` and gates.

## Evidence contract

Keep real input and output in an owner-controlled private runtime store outside Git. Never include credentials, customer details, PDF text, payment payloads or user contact data. Evidence references are opaque receipt references without query strings, credentials or fragments. No referenced URI/path is dereferenced. The operator/provider adapter is the trust boundary: labels and receipt identifiers alone do not prove a real event. Every report therefore states `evidence_trust: operator_attested` and `receipts_authenticated: false`. Fields named `verified` mean only that supplied claims satisfy this input contract; they are not independent provider authentication or execution permission.

All evidence contains `product_id`, `ref`, `observed_at`, and `scope` (`offline` or `provider_readback`). QA, factual claims and unit economics also require the exact source `revision`. Evidence older than seven days or from the future does not pass readiness. Use complete live provider exports, not sandbox transactions, dashboards with unknown coverage, local mocks or process exit codes. Scope `provider_readback` must only be supplied after the adapter confirms the actual live provider result.

- `demand`: competitor example plus an independent `problem_signal`, with distinct receipt references. The adapter must also verify semantic independence; different identifiers alone are not proof. This marks evidence coverage, not proven demand or profitability.
- `qa`: one entry per `core_flow`, `quota`, `entitlement`, `copy`, `privacy`; `pass`, `fail` or `unknown`. Offline tests cannot establish production readiness.
- `marketing_claims`: claim IDs and receipt references; actual copy stays with the owner. Include every factual claim that will be used. A report cannot detect claims omitted from its input.
- `unit_economics`: verified `price_minor`, maximum variable `max_variable_cost_minor` per order, explicit matching `price_currency`/`cost_currency` (also matching the reporting currency), and evidence for all included entitlements. The maximum must include provider fees, inference and processing. Unknown or negative contribution blocks distribution preparation. Do not label a free quota zero cost when provider calls are billed.
- `distribution`: draft-only `owned_site`, `owned_social`, or `permitted_community` with operator-attested permission, exact resource ownership and zero channel cost. `cost_minor: 0` and `permission: granted` are claims, not proof of verified free distribution. `draft_ready` requires demand coverage and all other structural gates, but never authenticates these claims or authorizes execution. An authorized adapter must confirm current channel terms, cost and permission before any later action. Never use the legacy marketing dry-run; it can send notifications. No automatic posting or outreach.
- `metrics`: `visits`, `successful_uses`, `invoices_paid`, `revenue_minor`, `refunds_minor`, `costs_minor`. Each snapshot has `status`, nonnegative integer `value`, `complete`, `period_start`, `period_end`, `currency`, and evidence. Counts describe distinct successful events as defined by the provider. Monetary values use the stated currency's minor unit; never exchange currencies implicitly. Aggregate values are not inferred from partial invoice lists.
- `financial_records`: optional existing CFO FinancialRecords, validated by the shared contract and counted only. They do not prove product attribution or snapshot completeness, are not echoed, and are never written. Refunds remain separate supplied snapshots; no unsupported CFO refund kind is invented.

Net contribution covers only revenue minus refunds minus supplied costs for the specified period. It is not MRR, tax-adjusted profit or verified bank cash. All monetary snapshots must have the same period and currency. Negative contribution is preserved. Unknown stays unknown.

## Ownership and lifecycle

`assignment` names a unique owner, exact worktree, repository-relative file paths, external resource IDs, current lease projection, and complete coordination inventory. Use the existing `scripts/worktree-lease.py` interface; this evaluator never acquires or releases a lease. GitHub repository identities normalize name case, trailing slashes and optional `.git`; other hosts require canonical exact repository URLs. Foreign overlapping paths (including case variants and parent directories) or the same resource block readiness. Stale owners must be reconciled; never reclaim by age alone.

`ownership.state: verified` means only the supplied projection passed validation, not that the seven sessions were observed or any atomic lock is held. An inventory without actual owner correspondence must remain incomplete. Recheck source SHA, worktree identity, owner, paths and resources and atomically acquire the existing owner/admission locks at execution time. This report always has `execution_authority: false`, `external_effects: false` and `runtime_registered: false`.

The `lifecycle` handoff targets existing `self-build` vocabulary. No entry is added to loop registries, no job is created and no scheduler is enabled. That owner can later consume the bounded task using the normal worktree → tests → draft PR → review → merge → immutable release → apply → official readback path. Business state continues to live in the unified SSOT and existing owner stores.

## Product evidence and publication boundary

For each product, its owner must confirm source ownership, core-flow QA, quota and entitlement behavior, marketing claims, usage, invoices, refunds and costs. Keep target identities, audit findings and detailed regression cases in that owner's private handoff. Generic QA categories and synthetic examples do not establish production or revenue success.

Application-specific investigation, security review and changes require the product owner's normal review and release process. This planner does not perform those actions or expose private audit conclusions.

Life Manager's root LICENSE is MIT. These newly authored files, synthetic fixtures and existing MIT module dependencies are the reusable public scope. Do not publish private product source/history, operator inputs, runtime logs or customer data. This planning module does not publish content or change repository visibility.
