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

Keep real input and output in an owner-controlled private runtime store outside Git. Never include credentials, customer details, PDF text, payment payloads or user contact data. Evidence references are opaque receipt references without query strings, credentials or fragments. No referenced URI/path is dereferenced. The operator/provider adapter is the trust boundary: labels and receipt identifiers alone do not prove a real event.

All evidence contains `product_id`, `ref`, `observed_at`, and `scope` (`offline` or `provider_readback`). QA, factual claims and unit economics also require the exact source `revision`. Evidence older than seven days or from the future does not pass readiness. Use complete live provider exports, not sandbox transactions, dashboards with unknown coverage, local mocks or process exit codes. Scope `provider_readback` must only be supplied after the adapter confirms the actual live provider result.

- `demand`: competitor example plus an independent `problem_signal`, with distinct receipt references. The adapter must also verify semantic independence; different identifiers alone are not proof. This marks evidence coverage, not proven demand or profitability.
- `qa`: one entry per `core_flow`, `quota`, `entitlement`, `copy`, `privacy`; `pass`, `fail` or `unknown`. Offline tests cannot establish production readiness.
- `marketing_claims`: claim IDs and receipt references; actual copy stays with the owner. Include every factual claim that will be used. A report cannot detect claims omitted from its input.
- `unit_economics`: verified `price_minor`, maximum variable `max_variable_cost_minor` per order, explicit matching `price_currency`/`cost_currency` (also matching the reporting currency), and evidence for all included entitlements. The maximum must include provider fees, inference and processing. Unknown or negative contribution blocks distribution preparation. Do not label a free quota zero cost when provider calls are billed.
- `distribution`: draft-only `owned_site`, `owned_social`, or `permitted_community` with explicit permission, exact resource ownership and verified zero channel cost. Never use the legacy marketing dry-run; it can send notifications. No automatic posting or outreach.
- `metrics`: `visits`, `successful_uses`, `invoices_paid`, `revenue_minor`, `refunds_minor`, `costs_minor`. Each snapshot has `status`, nonnegative integer `value`, `complete`, `period_start`, `period_end`, `currency`, and evidence. Counts describe distinct successful events as defined by the provider. Monetary values use the stated currency's minor unit; never exchange currencies implicitly. Aggregate values are not inferred from partial invoice lists.
- `financial_records`: optional existing CFO FinancialRecords, validated by the shared contract and counted only. They do not prove product attribution or snapshot completeness, are not echoed, and are never written. Refunds remain separate supplied snapshots; no unsupported CFO refund kind is invented.

Net contribution covers only revenue minus refunds minus supplied costs for the specified period. It is not MRR, tax-adjusted profit or verified bank cash. All monetary snapshots must have the same period and currency. Negative contribution is preserved. Unknown stays unknown.

## Ownership and lifecycle

`assignment` names a unique owner, exact worktree, repository-relative file paths, external resource IDs, current lease projection, and complete coordination inventory. Use the existing `scripts/worktree-lease.py` interface; this evaluator never acquires or releases a lease. GitHub repository identities normalize name case, trailing slashes and optional `.git`; other hosts require canonical exact repository URLs. Foreign overlapping paths (including case variants and parent directories) or the same resource block readiness. Stale owners must be reconciled; never reclaim by age alone.

`ownership.state: verified` means only the supplied projection passed validation, not that the seven sessions were observed or any atomic lock is held. An inventory without actual owner correspondence must remain incomplete. Recheck source SHA, worktree identity, owner, paths and resources and atomically acquire the existing owner/admission locks at execution time. This report always has `execution_authority: false`, `external_effects: false` and `runtime_registered: false`.

The `lifecycle` handoff targets existing `self-build` vocabulary. No entry is added to loop registries, no job is created and no scheduler is enabled. That owner can later consume the bounded task using the normal worktree → tests → draft PR → review → merge → immutable release → apply → official readback path. Business state continues to live in the unified SSOT and existing owner stores.

## PDF Insight and publication boundary

PDF Insight is the first real operator target. Public site: https://clear-pdf-converter.com. Its private application source and history are excluded. Actual source-owner mapping, core-flow QA, current live entitlement/quota behavior, marketing claims, usage, invoices, refunds and costs need owner-confirmed evidence. No production or revenue success is claimed.

Pending private-owner regression cases: free lifetime quota, UTC month boundary, environment-aware paid entitlement, repeat/concurrent parse charging, subscription write policies, and precise quota copy. Security migrations belong to the private application review lane and must not be applied by this planner. A source audit is not proof that the live site contains or exploited that behavior.

Life Manager's root LICENSE is MIT. These newly authored files, their synthetic fixtures and their existing MIT module dependencies are the clean reusable boundary. Do not publish private target inputs, PDF source/history, runtime logs or customer data. Publishing or changing repository visibility is a separate operation. This local increment performs neither.
