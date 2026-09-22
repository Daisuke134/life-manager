# Life Manager-Owned Goal Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Life Manager create and maintain a source-backed Goal Portfolio without requiring a person to author, choose, restate, or maintain goals.

**Architecture:** Add one machine-readable goal-policy contract and one model-facing Goal Portfolio boundary. The model judges which goals and priorities follow from authorized facts and boundaries; deterministic code validates identity, provenance, budgets, references, expiry, and idempotent WorkItem creation. Existing integration selection remains a consent/setup ceremony, not a goal-authoring surface.

**Tech Stack:** Node.js CommonJS, `node:test`, JSON contracts, existing runtime-job and hosted-ingress adapters.

**Spec:** `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md` sections J4 and CC01.

## Global Constraints

- Goal authority is Life Manager. A missing user-authored goal never becomes `setup_required`, `blocked`, or an open-ended question.
- Human input is limited to reusable facts, accounts, credentials, consent, boundaries, and exact typed gates required by law, provider policy, safety, identity, or an irreversible action.
- Model judgment selects goals and priorities. Deterministic code owns schema validation, tenant identity, budgets, references, expiry, WorkItem identity, and replay-zero.
- Goal statements and private evidence never enter runtime WorkItems or public receipts; WorkItems carry only an opaque Goal Portfolio reference.
- This plan must not modify any Coconala, CrowdWorks, Lancers, or Upwork Paid implementation, test, registry row, state, occurrence, fence, browser/session, client effect, or the Paid worktree/spec/plan.
- Do not modify `config/loop-registry.json` or `apps/life-manager/config/product-loop-catalog.json` in CC01.
- CC01 is source/contract work only. It performs no provider effect, production apply/restart, release cut, or client delivery.
- Keep `intent-graph.js` backward compatible. Historical `explicit_goal` entries remain readable but are no longer the hosted Life Manager goal authority.

## Review Focus

- A new tenant with zero user-authored goals still receives a valid `origin=life_manager` portfolio and one reference-only WorkItem.
- A user-supplied `goal` field cannot bypass the Life Manager-owned policy or change the selected Goal Portfolio.
- Cross-tenant portfolio references, model-invented evidence references, malformed budgets, and expired goals fail before enqueue.
- A replay loads the saved portfolio and enqueues the same WorkItem identity without a second model call or duplicate job.
- README and onboarding copy explain that integration choices are permissions, never goal selection, without promising that required KYC/OTP ceremonies disappear.

---

### Task 1: Machine-readable goal policy

**Files:**
- Create: `apps/life-manager/config/goal-policy.json`
- Create: `apps/life-manager/lib/goal-policy.js`
- Create: `apps/life-manager/lib/goal-policy.test.js`

**Interfaces:**
- Consumes: repository-local `apps/life-manager/config/goal-policy.json`.
- Produces: `readGoalPolicy(file?) -> Readonly<GoalPolicy>`, `GOAL_SYNTHESIS_INSTRUCTION: string`, and two frozen `GOAL_SYNTHESIS_EXAMPLES`.

- [ ] **Step 1: Write the failing policy tests**

Create `apps/life-manager/lib/goal-policy.test.js` with tests that require the exact contract and reject a second goal authority:

```js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {
  GOAL_SYNTHESIS_EXAMPLES, GOAL_SYNTHESIS_INSTRUCTION, readGoalPolicy,
} = require("./goal-policy.js");

test("Life Manager is the only goal authority and user-authored goals are optional", () => {
  const policy = readGoalPolicy();
  assert.equal(policy.schema_version, "life-manager.goal-policy.v1");
  assert.equal(policy.authority, "life_manager");
  assert.equal(policy.requires_user_authored_goal, false);
  assert.deepEqual(policy.human_inputs, ["facts", "accounts", "credentials", "consent", "boundaries"]);
  assert.deepEqual(policy.objective_order, ["safety", "continuity", "financial_surplus", "marginal_outcome"]);
  assert.match(GOAL_SYNTHESIS_INSTRUCTION, /Never ask the person to invent, choose, or restate a goal/u);
  assert.equal(GOAL_SYNTHESIS_EXAMPLES.length, 2);
  assert.equal(Object.isFrozen(GOAL_SYNTHESIS_EXAMPLES), true);
});

test("unknown policy fields and another authority fail closed", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-goal-policy-"));
  const file = path.join(root, "policy.json");
  fs.writeFileSync(file, JSON.stringify({ ...readGoalPolicy(), authority: "user", extra: true }));
  assert.throws(() => readGoalPolicy(file), /goal policy invalid/u);
  fs.rmSync(root, { recursive: true, force: true });
});
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
node --test apps/life-manager/lib/goal-policy.test.js
```

Expected: FAIL because `goal-policy.js` does not exist.

- [ ] **Step 3: Add the policy manifest and strict reader**

Create `apps/life-manager/config/goal-policy.json`:

```json
{
  "schema_version": "life-manager.goal-policy.v1",
  "authority": "life_manager",
  "requires_user_authored_goal": false,
  "human_inputs": ["facts", "accounts", "credentials", "consent", "boundaries"],
  "objective_order": ["safety", "continuity", "financial_surplus", "marginal_outcome"],
  "human_gates": ["kyc", "otp", "provider_mandated_interview", "personal_medical_decision", "external_wallet_or_bank_spend", "unforeseen_public_or_legal_commitment"]
}
```

Create `apps/life-manager/lib/goal-policy.js`. Use a closed top-level schema, exact constant arrays, `Object.freeze`, and this model-facing instruction:

```js
const GOAL_SYNTHESIS_INSTRUCTION = [
  "Create and prioritize a small Goal Portfolio from the authorized facts, evidence, consent, and boundaries supplied by Life Manager.",
  "Never ask the person to invent, choose, or restate a goal.",
  "Preserve safety, legality, identity, and declared boundaries; then continuity, verified financial surplus, and the highest evidence-backed marginal outcome.",
  "Return goals grounded only in the supplied evidence references. Mark an exact typed human gate only when autonomous continuation is impossible.",
].join(" ");
```

`readGoalPolicy` must reject unknown keys, a non-`life_manager` authority, `requires_user_authored_goal !== false`, reordered/missing canonical inputs or objectives, and an empty/duplicate human gate.
Export two compact canonical examples with different evidence: one tenant with only the J4 policy reference and one tenant with a verified income shortfall plus a no-spend boundary. Each example demonstrates a grounded model output and contains no open-ended question or provider effect. These are model guidance, not deterministic routing rules.

- [ ] **Step 4: Run the policy test and verify GREEN**

Run the Step 2 command. Expected: 2 tests PASS.

- [ ] **Step 5: Commit and push the policy contract**

```bash
git add apps/life-manager/config/goal-policy.json apps/life-manager/lib/goal-policy.js apps/life-manager/lib/goal-policy.test.js
git commit -m "feat(life-manager): define owned goal policy"
git push origin HEAD
```

### Task 2: Model-generated Goal Portfolio contract

**Files:**
- Create: `apps/life-manager/lib/goal-portfolio.js`
- Create: `apps/life-manager/lib/goal-portfolio.test.js`

**Interfaces:**
- Consumes: `readGoalPolicy()`, `GOAL_SYNTHESIS_INSTRUCTION`, authorized `fact_refs`, `evidence_refs`, and `boundary_refs`, plus injected `generate(input)`.
- Produces: `synthesizeGoalPortfolio(input, { generate, policyFile? }) -> Promise<Readonly<GoalPortfolio>>`, `validateGoalPortfolio(value, context)`, `activePortfolioGoal(portfolio, nowMs)`, and `goalReference(goal)`.

- [ ] **Step 1: Write failing synthesis and validation tests**

The happy-path test calls `synthesizeGoalPortfolio` without a user goal and captures the model input:

```js
const generated = await synthesizeGoalPortfolio({
  tenantId: "tenant-a",
  revision: 1,
  generatedAt: "2026-09-22T12:00:00.000Z",
  factRefs: [],
  evidenceRefs: ["policy://life-manager/J4"],
  boundaryRefs: [],
}, { async generate(input) {
  calls.push(input);
  return { goals: [{
    goal_id: "financial-continuity",
    statement: "Increase verified financial surplus within delegated boundaries",
    expected_outcome: "One attributable settled revenue receipt",
    confidence: 0.8,
    evidence_refs: ["policy://life-manager/J4"],
    cost_budget: { currency: "USD", minor_units: "0" },
    risk_budget: "low",
    dependencies: [],
    expires_at: null,
    success_receipt: null,
    status: "active"
  }] };
} });
assert.equal(generated.goals[0].origin, "life_manager");
assert.equal(generated.goals[0].tenant_id, "tenant-a");
assert.equal(generated.goals[0].revision, 1);
assert.equal(calls.length, 1);
assert.equal(Object.hasOwn(calls[0], "user_goal"), false);
```

Add table tests rejecting cross-tenant identity, unknown goal keys, duplicate IDs, evidence refs outside the authorized set, non-integer or negative `minor_units`, confidence outside `(0,1]`, malformed expiry, and zero or more than three goals. Add an expiry test proving `activePortfolioGoal` does not select an expired first goal and selects the next model-ranked active goal.

- [ ] **Step 2: Run the tests and verify RED**

```bash
node --test apps/life-manager/lib/goal-portfolio.test.js
```

Expected: FAIL because `goal-portfolio.js` does not exist.

- [ ] **Step 3: Implement the smallest model boundary**

Implement a closed portfolio shape:

```js
{
  schema_version: "life-manager.goal-portfolio.v1",
  tenant_id: "tenant-a",
  revision: 1,
  generated_at: "2026-09-22T12:00:00.000Z",
  origin: "life_manager",
  goals: [{
    goal_id: "financial-continuity",
    tenant_id: "tenant-a",
    revision: 1,
    origin: "life_manager",
    statement: "...",
    expected_outcome: "...",
    confidence: 0.8,
    evidence_refs: ["policy://life-manager/J4"],
    cost_budget: { currency: "USD", minor_units: "0" },
    risk_budget: "low",
    dependencies: [],
    expires_at: null,
    success_receipt: null,
    status: "active"
  }]
}
```

The harness, not the model, stamps `schema_version`, `tenant_id`, `revision`, `generated_at`, and `origin`. Pass `instruction`, `examples`, `policy`, and the three authorized reference arrays to `generate`. Accept only 1–3 model-ranked goals and deep-freeze the normalized return value. Use parsing/validation only for the fixed machine schema; do not add keyword or regex judgment about which goals are good.

`goalReference(goal)` returns:

```text
goal-portfolio://tenant-a/financial-continuity?revision=1
```

- [ ] **Step 4: Run the synthesis tests and verify GREEN**

Run the Step 2 command. Expected: all Goal Portfolio tests PASS.

- [ ] **Step 5: Commit and push the Goal Portfolio contract**

```bash
git add apps/life-manager/lib/goal-portfolio.js apps/life-manager/lib/goal-portfolio.test.js
git commit -m "feat(life-manager): synthesize goal portfolios"
git push origin HEAD
```

### Task 3: Remove the user-authored goal requirement from hosted work ingress

**Files:**
- Modify: `apps/life-manager/lib/goal-work-item.js`
- Modify: `apps/life-manager/lib/goal-work-item.test.js`
- Modify: `apps/life-manager/lib/general-agent-work-adapter.js`
- Modify: `apps/life-manager/lib/general-agent-work-adapter.test.js`
- Modify: `apps/life-manager/lib/hosted-goal-ingress.js`
- Modify: `apps/life-manager/lib/hosted-goal-ingress.test.js`

**Interfaces:**
- Consumes: `activePortfolioGoal`, `goalReference`, a tenant-scoped saved portfolio, or injected model generation from Task 2.
- Produces: the existing `general-agent.work` RuntimeJob and hosted enqueue receipt with a `goal-portfolio://...` opaque reference.

- [ ] **Step 1: Replace the fixtures before implementation**

Change all three test fixtures from `kind: "explicit_goal"` intent entries to normalized `origin: "life_manager"` portfolio goals. The WorkItem expectation becomes:

```js
{
  job_id: "goal:financial-continuity:r1",
  tenant_id: "tenant-a",
  loop_id: "life-manager.manager",
  capability: "general-agent.work",
  effect_class: "none",
  effect_key: null,
  input_refs: {
    goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1"
  },
  max_attempts: 1
}
```

Add a hosted-ingress test whose input contains only authenticated scope and `nowMs`. Its fixture returns no saved portfolio on the first call, uses `generateGoalPortfolio` once, saves once, and returns the saved portfolio on replay. Assert two ingress calls yield `created: true` then `created: false`, one model call, one saved portfolio, and one job identity.

Add a test that supplies `input.goal` and expects rejection with zero model, save, or enqueue calls. Keep unauthenticated, unpaid, cross-tenant, and unhealthy-vault zero-effect cases.

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
node --test \
  apps/life-manager/lib/goal-work-item.test.js \
  apps/life-manager/lib/general-agent-work-adapter.test.js \
  apps/life-manager/lib/hosted-goal-ingress.test.js
```

Expected: FAIL on the old `explicit_goal` and `intent-entry://` requirements.

- [ ] **Step 3: Update WorkItem and adapter contracts**

`buildGoalWorkItem(goal, nowMs)` validates the portfolio goal, rejects expired/inactive goals, builds `goal:${goal.goal_id}:r${goal.revision}`, and stores only `goalReference(goal)`. `general-agent-work-adapter.js` parses the fixed `goal-portfolio:` URL and verifies its hostname/path/revision match the job tenant and ID; it must not inspect goal prose or perform goal-quality judgment.

- [ ] **Step 4: Update hosted ingress resolution**

Keep the existing authentication, tenant, entitlement, and vault checks before model work. Reject `input.goal`. Resolve the portfolio in this order:

```js
let portfolio = await deps.loadGoalPortfolio(scope.tenantId);
if (!portfolio) {
  portfolio = await synthesizeGoalPortfolio({
    tenantId: scope.tenantId,
    revision: 1,
    generatedAt: new Date(input.nowMs).toISOString(),
    factRefs: tenant.fact_refs || [],
    evidenceRefs: tenant.evidence_refs || ["policy://life-manager/J4"],
    boundaryRefs: tenant.boundary_refs || [],
  }, { generate: deps.generateGoalPortfolio });
  await deps.saveGoalPortfolio(portfolio);
}
const goal = activePortfolioGoal(portfolio, input.nowMs);
const job = buildGoalWorkItem(goal, input.nowMs);
```

Require `loadGoalPortfolio`, `saveGoalPortfolio`, and `generateGoalPortfolio` in the injected dependency contract. A replay must load and validate the persisted portfolio instead of calling the model again.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run the Step 2 command. Expected: all tests PASS and no receipt contains goal prose, tenant chat ID, private evidence, or secret material.

- [ ] **Step 6: Commit and push ingress migration**

```bash
git add \
  apps/life-manager/lib/goal-work-item.js \
  apps/life-manager/lib/goal-work-item.test.js \
  apps/life-manager/lib/general-agent-work-adapter.js \
  apps/life-manager/lib/general-agent-work-adapter.test.js \
  apps/life-manager/lib/hosted-goal-ingress.js \
  apps/life-manager/lib/hosted-goal-ingress.test.js
git commit -m "feat(life-manager): remove user goal requirement"
git push origin HEAD
```

### Task 4: Product copy and executable conformance gate

**Files:**
- Modify: `README.md`
- Modify: `README.ja.md`
- Modify: `apps/oss-onboarding/index.html`
- Modify: `apps/life-manager/package.json`
- Create: `apps/life-manager/test/goal-policy-contract.test.js`

**Interfaces:**
- Consumes: the Goal Policy manifest and public product surfaces.
- Produces: one CI command, `npm run test:goal-policy`, that prevents reintroducing goal-selection onboarding.

- [ ] **Step 1: Write the failing public-contract test**

Create `apps/life-manager/test/goal-policy-contract.test.js` that loads the manifest, English/Japanese README, local onboarding HTML, `goal-work-item.js`, and `hosted-goal-ingress.js`. Assert:

```js
assert.match(english, /Life Manager creates, prioritizes, and maintains your Goal Portfolio/u);
assert.match(japanese, /Life Manager自身がGoal Portfolioを作成・優先順位付け・維持/u);
assert.match(onboarding, /Life Manager chooses goals and next actions/u);
assert.doesNotMatch(onboarding, /What is your goal|Choose your goal|目標を選/u);
assert.match(workItem, /goal-portfolio:\/\//u);
assert.doesNotMatch(hostedIngress, /buildGoalWorkItem\(input\.goal/u);
assert.equal(policy.requires_user_authored_goal, false);
```

This is fixed-copy/schema verification, not semantic goal judgment.

- [ ] **Step 2: Run the contract test and verify RED**

```bash
node --test apps/life-manager/test/goal-policy-contract.test.js
```

Expected: FAIL because the current public copy says goals are supplied or loops are chosen without distinguishing consent from goal authority.

- [ ] **Step 3: Update public copy without removing consent gates**

Use this English contract near the top of `README.md`:

```markdown
Life Manager creates, prioritizes, and maintains your Goal Portfolio from the facts, accounts, consent, and boundaries you provide once. It does not require you to invent or maintain goals. It works continuously, asks only for an exact KYC, OTP, safety, identity, or irreversible-action gate when necessary, and closes outcomes with official receipts.
```

Add the equivalent Japanese contract to `README.ja.md`. Replace the local onboarding lede with:

```html
<p class="lede">Life Manager chooses goals and next actions for your money, body, and mind. Connect only the services you authorize once; integration choices are permissions, not goal selection.</p>
```

Do not remove integration-level connect/uninstall controls or one-time consent fields.

- [ ] **Step 4: Register the focused CI command**

Add this script to `apps/life-manager/package.json`:

```json
"test:goal-policy": "node --test lib/goal-policy.test.js lib/goal-portfolio.test.js lib/goal-work-item.test.js lib/general-agent-work-adapter.test.js lib/hosted-goal-ingress.test.js test/goal-policy-contract.test.js"
```

Append `npm run test:goal-policy` to the existing `test:runtime-job` command so the canonical runtime-job check cannot omit the goal authority contract.

- [ ] **Step 5: Run copy/CI tests and verify GREEN**

```bash
cd apps/life-manager
npm run test:goal-policy
npm run test:runtime-job
```

Expected: both commands PASS.

- [ ] **Step 6: Commit and push the public contract**

```bash
git add README.md README.ja.md apps/oss-onboarding/index.html \
  apps/life-manager/package.json apps/life-manager/test/goal-policy-contract.test.js
git commit -m "docs(life-manager): make goal ownership explicit"
git push origin HEAD
```

### Task 5: CC01 acceptance and spec cursor

**Files:**
- Modify: `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md`

**Interfaces:**
- Consumes: pushed source commits and test evidence from Tasks 1–4.
- Produces: a truthful CC01 completion receipt and advances the written cursor to CC02 without claiming cloud/runtime/provider completion.

- [ ] **Step 1: Run the full CC01 focused acceptance**

```bash
node --test \
  apps/life-manager/lib/goal-policy.test.js \
  apps/life-manager/lib/goal-portfolio.test.js \
  apps/life-manager/lib/goal-work-item.test.js \
  apps/life-manager/lib/general-agent-work-adapter.test.js \
  apps/life-manager/lib/hosted-goal-ingress.test.js \
  apps/life-manager/lib/product-onboarding.test.js \
  apps/life-manager/test/goal-policy-contract.test.js \
  apps/life-manager/test/context-onboarding-discovery-contract.test.js
./bin/lm-loop-contract
git diff --check
```

Expected: all focused tests PASS, the loop contract gate PASS, and no whitespace errors.

- [ ] **Step 2: Verify the protected Paid boundary**

```bash
if git diff origin/main...HEAD --name-only \
  | rg -q '(^|/)(paid_direct|paid_admission|paid_thread_state)\.py$|test_paid_remote_wait\.py$|^config/loop-registry\.json$'; then
  exit 1
fi
```

Expected: no protected Paid file or registry change.

- [ ] **Step 3: Update the spec from measured evidence only**

Change CC01 from `[ ]` to `[x]` and record the exact pushed commit plus test counts. State explicitly:

```text
CC01 proves Life Manager-owned goal policy, model-generated Goal Portfolio validation,
reference-only WorkItems, replay-zero ingress, and public-copy conformance. It does not
claim persistent cloud tenant storage, phone/web availability, provider effects, or Paid fulfillment.
Current cursor: CC02.
```

- [ ] **Step 4: Commit and push the acceptance update**

```bash
git add docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md
git commit -m "docs: close Life Manager goal policy gate"
git push origin HEAD
```

- [ ] **Step 5: Record the milestone**

Send one deduplicated Telegram update beginning with `Codex:::` that names the branch, pushed commit, focused test/contract results, Paid boundary result, and `CC02` as the next cursor. Do not call CC01 a cloud or production completion.
