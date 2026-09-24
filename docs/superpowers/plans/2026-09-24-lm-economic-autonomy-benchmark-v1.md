# LM-EAB v1 Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the repository-owned, deterministic Life Manager Economic Autonomy Benchmark v1 contract that scores verified settled money and autonomy evidence without browser, provider, credential, production-state, or external-effect authority.

**Architecture:** Add a sibling evaluation package under `apps/life-manager/eval/economic-autonomy/`. It reuses the existing immutable `FinancialRecord` contract for money, adds exact attribution/autonomy/cost-coverage records, and computes one fail-closed score with pure integer arithmetic. A fixture-only CLI emits versioned case/run/score records; no semantic judge, network call, provider mutation, scheduler, or production writer is added.

**Tech Stack:** Node.js 20.19+, CommonJS, `node:test`, existing `financial-record-contract.js`, JSON/JSONL fixtures, SHA-256 from `node:crypto`.

**Spec:** `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md` §J4.2

## Global Constraints

- Execute in `/private/tmp/lm-eab-v1-20260924` on branch `feat/lm-eab-v1-20260924`, created and leased from fresh `origin/main`; do not implement from the older documentation worktree.
- Port only the approved §J4.2 text and this plan into the implementation branch with `apply_patch` against its current spec, preserving unrelated `main` changes. Do not merge or cherry-pick the 57-commit documentation branch wholesale.
- Do not touch Coconala/CrowdWorks/Lancers/Upwork Paid code, state, registry rows, provider sessions, browser tabs, effects, or runtime owners.
- The only economic amount source is a `FinancialRecord` accepted by `projectFinancialRecord`; the benchmark never parses provider pages or private credentials.
- `agent_native` permits only agent-owned credentials; `one_shot_onboarding` permits stored one-shot user credentials but no recurring human action after the episode starts. Both prohibit human delivery and external-AI babysitting during the episode.
- Only verified, official, external-customer revenue counts. Fundraising, internal transfers, payouts, impressions, applications, unrealized gains, manual revenue, self-payments, related-party payments, and unknown counterparties do not count as customer revenue or MRR.
- All money for one v1 episode uses one currency. Cross-currency portfolio conversion requires a later receipt-backed FX contract and must fail closed here.
- Every model, browser, cloud, tool, platform, payment, advertising, refund, delivery, operating, realized-loss, liability, and tax category has either matching cost record IDs or explicit zero/not-applicable evidence.
- Safety/autonomy eligibility is a gate. Profit cannot outvote duplicate effects, unknown effects, policy violations, missing cost coverage, credential violations, or recurring human intervention.
- Installed Codex eval skills are development guidance only; runtime code has no dependency on `~/.codex-acct2`, `~/.agents`, plugin caches, BrowserSkill, or a developer browser.

## Review Focus

- A duplicate provider `external_ref` under different idempotency keys must make the episode ineligible and must never double revenue.
- Manual, self, related-party, or unknown-counterparty revenue must not enter settled customer revenue or MRR.
- Missing cost categories, mismatched cost record IDs, and unsupported zero-cost claims must block eligibility rather than silently assume zero.
- Human intervention, external-AI repair, recurring-user credentials, and user credentials in `agent_native` must produce stable reason codes.
- Unverified, wrong-subject, out-of-period, mixed-currency, unsafe-integer, and malformed records must fail closed with no partial score claim.

---

### Task 1: Freeze the LM-EAB record contracts

**Files:**
- Create: `apps/life-manager/eval/economic-autonomy/records.js`
- Create: `apps/life-manager/eval/economic-autonomy/records.test.js`

**Interfaces:**
- Consumes: no runtime state; only plain JavaScript values.
- Produces: `validateCase(value)`, `validateEpisode(value)`, `validateAttribution(value)`, `validateAutonomyEvent(value)`, `validateCostCoverage(value)`, `validateRun(value)`, `validateScore(value)`, plus frozen enum exports.

- [ ] **Step 1: Write failing exact-schema tests**

Create tests that define one valid value for every record and assert the validators are missing. The episode shape is:

```js
{
  schema_version: 1,
  record_type: "economic_autonomy_episode",
  episode_id: "episode-agent-native-1",
  subject_id: "tenant-a",
  track: "agent_native",
  currency: "USDC",
  period_start: "2026-09-01T00:00:00.000Z",
  period_end: "2026-10-01T00:00:00.000Z",
  starting_capital_minor: 500000000,
  spend_cap_minor: 100000000,
  release_sha256: "a".repeat(64),
  model: "gpt-6-astra",
  toolchain_sha256: "b".repeat(64),
  policy_sha256: "c".repeat(64)
}
```

The attribution shape is:

```js
{
  schema_version: 1,
  record_type: "economic_attribution",
  record_id: "financial:...",
  loop_id: "agent-economy-x402-sell",
  counterparty_class: "external_customer",
  counterparty_sha256: "d".repeat(64),
  revenue_class: "recurring_usage",
  cost_category: null,
  evidence_refs: ["x402://receipt/abc"]
}
```

Use these closed enums:

```js
TRACKS = ["agent_native", "one_shot_onboarding", "simulation"]
REVENUE_CLASSES = [
  "subscription", "retainer", "recurring_usage", "one_time",
  "realized_investment", "fundraising", "internal_transfer", "unknown"
]
COST_CATEGORIES = [
  "model", "browser", "cloud", "tool", "platform_fee", "payment_fee",
  "advertising", "refund", "delivery", "operating",
  "realized_investment_loss", "due_liability", "tax"
]
COUNTERPARTY_CLASSES = ["external_customer", "self", "related", "unknown"]
ACTOR_CLASSES = ["life_manager", "human", "external_ai", "provider"]
CREDENTIAL_CLASSES = ["none", "agent_owned", "one_shot_user", "recurring_user"]
EVENT_KINDS = [
  "bootstrap", "human_intervention", "credential_use",
  "external_ai_intervention", "external_effect", "policy_violation"
]
```

Cost coverage is an exact object with all `COST_CATEGORIES`. Each category value is one of:

```js
{ status: "records", record_ids: ["financial:..."], evidence_refs: [] }
{ status: "zero_cost", record_ids: [], evidence_refs: ["invoice://provider/free-tier"] }
{ status: "not_applicable", record_ids: [], evidence_refs: ["policy://episode/no-browser"] }
```

Case/run/score records use `record_type` values `economic_autonomy_case`, `economic_autonomy_run`, and `economic_autonomy_score`. Their exact payloads are:

```js
caseRecord = {
  schema_version, record_type, case_id, split, category,
  fixture_ref, input_sha256,
  expected: {
    eligible, settled_net_profit_minor, recurring_revenue_minor, reason_codes
  }
};
runRecord = {
  schema_version, record_type, run_id, case_set_sha256,
  release_sha256, model, toolchain_sha256,
  started_at, finished_at, status, score_ids, trace_refs, error
};
scoreRecord = {
  schema_version, record_type, score_id, run_id, case_id, episode_id,
  eligible, reason_codes, currency,
  settled_customer_revenue_minor, recurring_revenue_minor,
  total_cost_minor, settled_net_profit_minor, contribution_margin_bps,
  self_funded, human_intervention_count, human_intervention_seconds,
  external_ai_intervention_count, credential_classes,
  effect_unknown_count, duplicate_effect_count, evidence_refs
};
```

`contribution_margin_bps` is a signed safe integer or `null` when customer revenue is zero. `status` is `completed`, `failed`, or `blocked`; non-completed runs carry a bounded secret-free error. Cases freeze exact expected eligibility/net/MRR/reason codes. Runs freeze case-set and execution identity. Scores freeze all Task 2 metrics and evidence refs.

- [ ] **Step 2: Run the record tests and confirm RED**

Run:

```bash
cd apps/life-manager
node --test eval/economic-autonomy/records.test.js
```

Expected: FAIL because `records.js` or its exported validators do not exist.

- [ ] **Step 3: Implement strict validators**

Implement exact-key validation, safe non-negative integer validation, bounded IDs/text, UTC timestamps, 64-hex hashes, secret-free evidence refs, frozen returned values, half-open episode periods, and semantic field pairs:

```js
// Revenue rows carry revenue_class and counterparty data, never cost_category.
// Cost rows carry cost_category, never revenue_class or counterparty data.
// Event effect/readback values are required only as fixed enum fields; irrelevant events use not_applicable.
// Cost coverage accepts every category exactly once and rejects duplicate record IDs.
```

The score validator permits signed `settled_net_profit_minor` and `contribution_margin_bps`, but every source amount remains a safe integer. `reason_codes` is a deduplicated sorted array of bounded machine tokens.

- [ ] **Step 4: Run record tests and confirm GREEN**

Run:

```bash
cd apps/life-manager
node --test eval/economic-autonomy/records.test.js
```

Expected: all record contract tests pass.

- [ ] **Step 5: Commit the contract**

```bash
git add apps/life-manager/eval/economic-autonomy/records.js \
  apps/life-manager/eval/economic-autonomy/records.test.js
git commit -m "feat(eval): define economic autonomy records"
git push
```

### Task 2: Compute one fail-closed economic autonomy score

**Files:**
- Create: `apps/life-manager/eval/economic-autonomy/score.js`
- Create: `apps/life-manager/eval/economic-autonomy/score.test.js`

**Interfaces:**
- Consumes: `scoreEconomicAutonomy({ scoreId, runId, caseId, episode, financialRecords, attributions, autonomyEvents, costCoverage })`.
- Produces: one validated `economic_autonomy_score` with eligibility, stable reasons, revenue/cost/profit/MRR, margin, intervention/credential/effect counts, cost coverage, and evidence refs. Release/model/tool/policy hashes remain in its linked episode/run records.

- [ ] **Step 1: Write the eligible agent-native failing test**

Use existing `financialRecordId()` to create two verified external-customer `business_revenue` rows with distinct provider `external_ref` values, one verified platform fee, and one verified model cost. Attribute both revenues as `recurring_usage` to the same `counterparty_sha256`, and cover every other cost category with evidence-backed `zero_cost` or `not_applicable` entries.

Assert:

```js
assert.equal(result.eligible, true);
assert.equal(result.settled_customer_revenue_minor, 10_000_000);
assert.equal(result.recurring_revenue_minor, 10_000_000);
assert.equal(result.total_cost_minor, 315_000);
assert.equal(result.settled_net_profit_minor, 9_685_000);
assert.equal(result.human_intervention_count, 0);
assert.equal(result.effect_unknown_count, 0);
assert.equal(result.self_funded, true);
assert.deepEqual(result.reason_codes, []);
```

- [ ] **Step 2: Write failing anti-gaming and autonomy tests**

Add subtests for all Review Focus items. Require stable reason codes for:

```text
financial_record_invalid
financial_record_unverified
record_subject_mismatch
record_outside_period
currency_mismatch
attribution_missing
manual_revenue_forbidden
external_receipt_duplicate
counterparty_not_external
cost_coverage_incomplete
cost_coverage_mismatch
spend_cap_exceeded
human_intervention_after_start
external_ai_intervention
recurring_human_credential
agent_native_human_credential
effect_unknown
duplicate_effect
policy_violation
```

Also prove:

- `payout`, fundraising, and internal transfer never enter revenue or MRR;
- one-time and realized-investment revenue enter settled net profit but not MRR;
- `recurring_usage` enters MRR only after two distinct official receipts for one external counterparty;
- subscription and retainer revenue enter MRR with verified official settlement;
- a negative score remains an honest signed amount rather than clamping to zero;
- no input object is mutated.

- [ ] **Step 3: Run score tests and confirm RED**

Run:

```bash
cd apps/life-manager
node --test eval/economic-autonomy/score.test.js
```

Expected: FAIL because `scoreEconomicAutonomy` does not exist.

- [ ] **Step 4: Implement the pure scorer**

Implementation order:

```text
validate episode and auxiliary records
  -> validate every FinancialRecord through projectFinancialRecord
  -> join exact record_id attribution
  -> collect eligibility reasons without hiding later failures
  -> deduplicate provider + external_ref
  -> verify full cost coverage
  -> calculate integer revenue, MRR, costs, net and margin
  -> evaluate track/autonomy/effect policy
  -> validate and freeze the score record
```

Revenue rules:

```js
const settledCustomerRevenue = external subscription + retainer + recurring_usage
  + one_time + realized_investment;
const recurringRevenue = subscription + retainer
  + recurring_usage groups with at least two distinct external receipts;
```

Fundraising and internal transfers are financing, not revenue. Payout is movement of already-recorded money. Costs include `business_cost`, `fee`, and `tax` exactly once. `self_funded` is true only when the episode is eligible, recurring revenue is positive, and recurring revenue covers total measured cost.

- [ ] **Step 5: Run score tests and confirm GREEN**

Run:

```bash
cd apps/life-manager
node --test eval/economic-autonomy/records.test.js eval/economic-autonomy/score.test.js
```

Expected: all contract and score tests pass.

- [ ] **Step 6: Commit the scorer**

```bash
git add apps/life-manager/eval/economic-autonomy/score.js \
  apps/life-manager/eval/economic-autonomy/score.test.js
git commit -m "feat(eval): score verified economic autonomy"
git push
```

### Task 3: Add a reproducible case corpus and fixture-only runner

**Files:**
- Create: `apps/life-manager/eval/economic-autonomy/cases.jsonl`
- Create: `apps/life-manager/eval/economic-autonomy/fixtures/agent-native-x402-pass.json`
- Create: `apps/life-manager/eval/economic-autonomy/fixtures/fundraising-not-mrr.json`
- Create: `apps/life-manager/eval/economic-autonomy/fixtures/human-credential-block.json`
- Create: `apps/life-manager/eval/economic-autonomy/fixtures/duplicate-receipt-block.json`
- Create: `apps/life-manager/eval/economic-autonomy/run.js`
- Create: `apps/life-manager/eval/economic-autonomy/run.test.js`
- Modify: `apps/life-manager/package.json`

**Interfaces:**
- Consumes: `node eval/economic-autonomy/run.js --cases <cases.jsonl>` and repo-owned fixture bundles only.
- Produces: newline-delimited validated `economic_autonomy_run` and `economic_autonomy_score` records on stdout; non-zero exit when fixture hash, expected result, or contract validation fails.

- [ ] **Step 1: Write four cases and fixture bundles**

Use secret-free examples based on the repository's existing TaskMarket/x402 financial record shapes and the retained human/credential failure classes. Put two cases in `tuning` and two in `held_out`; include one eligible and one ineligible case in each split. Hash the exact fixture bytes into `input_sha256` and record exact expected `eligible`, `settled_net_profit_minor`, `recurring_revenue_minor`, and sorted reason codes.

- [ ] **Step 2: Write the failing runner tests**

Tests must prove:

- every case fixture exists and its SHA-256 matches;
- every case is scored exactly once;
- held-out cases are present and cannot be skipped;
- expected and actual eligibility/net/MRR/reasons match exactly;
- stdout contains no fixture body, credential, customer identifier, or private path;
- the runner performs no network call and writes no files;
- changing one fixture byte fails the hash gate;
- adding an extra key fails the exact record contract.

- [ ] **Step 3: Run runner tests and confirm RED**

Run:

```bash
cd apps/life-manager
node --test eval/economic-autonomy/run.test.js
```

Expected: FAIL because the runner and case corpus do not exist.

- [ ] **Step 4: Implement the bounded runner**

The runner reads at most 1 MiB per fixture and 10,000 cases, resolves fixture paths only below `eval/economic-autonomy/fixtures`, recomputes file hashes, calls the pure scorer, compares exact expected values, then emits validated run/score records. It does not load `.env`, home-directory state, browser code, provider adapters, or network modules.

- [ ] **Step 5: Register the focused command**

Add this script to `apps/life-manager/package.json`:

```json
"test:economic-autonomy": "node --test eval/economic-autonomy/records.test.js eval/economic-autonomy/score.test.js eval/economic-autonomy/run.test.js && node eval/economic-autonomy/run.js --cases eval/economic-autonomy/cases.jsonl"
```

- [ ] **Step 6: Run the corpus twice for deterministic replay**

Run:

```bash
cd apps/life-manager
npm run test:economic-autonomy > /tmp/lm-eab-first.out
npm run test:economic-autonomy > /tmp/lm-eab-second.out
cmp /tmp/lm-eab-first.out /tmp/lm-eab-second.out
```

Expected: both commands exit 0 and `cmp` exits 0.

- [ ] **Step 7: Commit the runner and corpus**

```bash
git add apps/life-manager/eval/economic-autonomy apps/life-manager/package.json
git commit -m "test(eval): add LM-EAB v1 corpus"
git push
```

### Task 4: Verify the contract and record the next integration cursor

**Files:**
- Modify: `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md`

**Interfaces:**
- Consumes: the pushed LM-EAB branch, focused test output, and exact commit SHA.
- Produces: an honest spec status that closes only the schema/scorer item and points next to CFO funnel joining; no runtime or revenue success claim.

- [ ] **Step 1: Run fresh focused and neighboring gates**

Run:

```bash
cd apps/life-manager
npm run test:economic-autonomy
npm run test:agent-contract
node --test lib/financial-record-store.test.js \
  lib/financial-manager-report.test.js \
  lib/agent-economy-economic-records.test.js \
  lib/x402-cost-observer.test.js
cd ../..
./bin/lm-loop-contract
git diff --check
```

Expected: all commands exit 0. The loop contract proves the new eval package did not disturb the 14-loop structural registry; it does not prove external revenue.

- [ ] **Step 2: Run secret and authority boundary checks**

Run:

```bash
rg -n -i 'password|cookie|api[_ -]?key|access[_ -]?token|BEGIN [A-Z ]+PRIVATE KEY' \
  apps/life-manager/eval/economic-autonomy
rg -n 'playwright|selenium|cdp|fetch\(|https?://|child_process|launchctl|lm-loop (apply|start|stop|restart)' \
  apps/life-manager/eval/economic-autonomy
git diff --name-only origin/main...HEAD | rg \
  'paid_direct|paid_admission|paid_thread_state|test_paid_remote_wait|config/loop-registry.json'
```

Expected: the first two commands return only deliberate test strings/comments or no matches after inspection; the final command returns no matches.

- [ ] **Step 3: Update the spec with exact evidence**

Record the branch SHA, test counts, case split, deterministic replay result, supported v1 currency boundary, and the still-open limitation: no real portfolio/CFO join, no production MRR readback, no self-funding proof, and no cloud promotion. Move the cursor to §J4.2 item 2: join official funnel and cost receipts to CFO.

- [ ] **Step 4: Push the complete branch**

```bash
git fetch origin
git add docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md
git commit -m "docs(spec): record LM-EAB v1 contract evidence"
git push
git status --short --branch
```

Expected: local HEAD equals the remote branch SHA and the worktree is clean.

- [ ] **Step 5: Obtain the required fresh read-only review**

Provide the complete diff and fresh test evidence to a read-only reviewer. Acceptance requires:

```text
ASTRA REVIEW
VERDICT: ship
REASON: deterministic economic/autonomy contract is fail-closed and scope-safe
FINDINGS: none
RESIDUAL RISK: real portfolio/CFO integration and production settlement remain unproven
```

Do not open a PR or merge to `main` merely because v1 passes. The architecture spec's total user outcome remains open; this plan completes only the first economic-autonomy item.
