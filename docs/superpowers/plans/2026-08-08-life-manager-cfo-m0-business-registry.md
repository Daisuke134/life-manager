# Life Manager CFO M0 Business Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strict nine-unit financial registry and a read-only live Mac inventory receipt that closes CFO-0c without changing any running loop.

**Architecture:** A Git-tracked JSON registry defines stable economic identity. Pure CommonJS modules validate and classify injected launchd observations. A thin CLI is the only process/filesystem boundary and atomically appends receipts below the Life Manager state root.

**Tech Stack:** Node.js 20+, CommonJS, `node:test`, Node standard library only, JSON, launchctl read-only commands.

## Global Constraints

- Parent design: `docs/superpowers/specs/2026-08-08-life-manager-cfo-m0-business-registry-design.md`.
- No dependency additions, database migrations, network requests, Telegram sends, or launchctl mutation.
- Production code must follow RED → observed failure → minimal GREEN for every task.
- The registry contains identity only: no balances, amounts, account numbers, secrets, PIDs, or copied ledger payloads.
- Runtime globs support exact strings or one terminal `*`; overlapping matches are errors.
- Missing revenue evidence means `unverified`, never zero and never healthy.
- Only the current task's files are staged. Preserve unrelated worktree changes.
- Every task ends with fresh targeted tests, `git diff --check`, commit, and push before the next task.

## File Map and Size Targets

| File | Responsibility | Soft target |
|---|---|---:|
| `apps/life-call/lib/cfo-registry.js` | Strict schema, canonical JSON, SHA-256, runtime matcher | 95 production LOC |
| `apps/life-call/lib/cfo-registry.test.js` | Validator and mapping contract | 95 test LOC |
| `apps/life-call/config/cfo-financial-units.json` | Nine declarative units, nine ledger sources, and exclusions | 125 data LOC; not split because one atomic registry SSOT is safer than cross-file identity |
| `apps/life-call/lib/cfo-inventory.js` | Deterministic observations and receipt construction | 90 production LOC |
| `apps/life-call/lib/cfo-inventory.test.js` | Classification, ambiguity, determinism | 95 test LOC |
| `apps/life-call/scripts/cfo-business-inventory.js` | Read-only launchctl adapter and atomic receipt writer | 85 production LOC |
| `apps/life-call/scripts/cfo-business-inventory.test.js` | CLI effect boundary and immutability | 90 test LOC |
| Parent/child specs | State and evidence update only | 15 documentation LOC |

---

### Task 1: Strict registry validator and matcher

**Files:**
- Create: `apps/life-call/lib/cfo-registry.js`
- Create: `apps/life-call/lib/cfo-registry.test.js`

**Interfaces:**
- Consumes: plain parsed JSON objects only.
- Produces:
  - `validateRegistry(input): Readonly<object>`; throws `Error("cfo_registry_invalid:<reason>")`.
  - `canonicalJson(value): string`; recursively sorted object keys, array order preserved, no whitespace.
  - `sha256Canonical(value): string`; 64 lowercase hexadecimal characters.
  - `matchesLabel(matcher, label): boolean`; exact or terminal-star prefix only.
  - `classifyLabel(registry, label): { kind: "financial_unit"|"exclusion"|"unmapped"|"ambiguous", targetIds: string[] }`.

- [x] **Step 1: Write the failing contract tests**

Create tests using `node:test` and `node:assert/strict`. The minimum fixture has one `business` unit, one channel,
one ledger source, one evidence reference, one relevant prefix, and one exclusion. Assert:

```js
function validFixture() {
  return {
    schema_version: 1,
    registry_id: "life_manager_cfo_financial_units",
    relevant_runtime_prefixes: ["ai.anicca.writer-", "ai.anicca.cfo-"],
    financial_units: [{
      financial_unit_id: "writer_agent", unit_kind: "business", display_order: 1,
      display_name: { en: "Writer Agent", ja: "Writer Agent" }, owner_ref: "human:dais",
      cost_center_refs: [], lifecycle: "active", runtime_matchers: ["ai.anicca.writer-*"],
      revenue_channel_ids: ["publisher_writer"], ledger_source_ids: ["writer_receipts"],
      evidence_refs: ["docs/writer-agent/WRITER-AGENT-SSOT.md"],
    }],
    runtime_exclusions: [{
      exclusion_id: "cfo_controller", runtime_matchers: ["ai.anicca.cfo-*"],
      classification: "controller", cost_treatment: "shared_overhead",
      evidence_refs: ["docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md"],
    }],
  };
}

test("valid registry is frozen and exact/terminal-star labels classify once", () => {
  const registry = validateRegistry(validFixture());
  assert.equal(Object.isFrozen(registry), true);
  assert.deepEqual(classifyLabel(registry, "ai.anicca.writer-report"), {
    kind: "financial_unit", targetIds: ["writer_agent"],
  });
  assert.equal(matchesLabel("ai.anicca.writer-*", "ai.anicca.writer-report"), true);
  assert.equal(matchesLabel("ai.*.writer-*", "ai.anicca.writer-report"), false);
});

test("duplicates, unknown keys, money, secret-like keys, unsafe paths, and overlap fail", () => {
  for (const mutate of invalidMutations()) {
    assert.throws(() => validateRegistry(mutate(validFixture())), /^Error: cfo_registry_invalid:/);
  }
});

test("canonical hash ignores object insertion order but preserves array order", () => {
  assert.equal(sha256Canonical({ b: 2, a: 1 }), sha256Canonical({ a: 1, b: 2 }));
  assert.notEqual(sha256Canonical({ a: [1, 2] }), sha256Canonical({ a: [2, 1] }));
});
```

Define `invalidMutations()` as an array of functions that each clone and change exactly one field. It must cover:
unknown root key, unknown unit key, duplicate unit ID, duplicate channel ID,
invalid `unit_kind`, invalid `lifecycle`, empty `evidence_refs`, `monthly_revenue`, `api_secret`, `/Users/name/state`,
and an internal-star matcher. The final overlap case belongs to Task 3 because syntactically valid matchers can
become ambiguous only when applied to an observed label.

- [x] **Step 2: Run RED**

Run:

```bash
cd apps/life-call
node --test lib/cfo-registry.test.js
```

Expected: FAIL because `./cfo-registry.js` does not exist.

- [x] **Step 3: Implement the minimal strict validator**

Use constant key sets and enums; do not add a schema dependency:

```js
const ROOT_KEYS = new Set(["schema_version", "registry_id", "relevant_runtime_prefixes", "financial_units", "runtime_exclusions"]);
const UNIT_KEYS = new Set(["financial_unit_id", "unit_kind", "display_order", "display_name", "owner_ref", "cost_center_refs", "lifecycle", "runtime_matchers", "revenue_channel_ids", "ledger_source_ids", "evidence_refs"]);
const EXCLUSION_KEYS = new Set(["exclusion_id", "runtime_matchers", "classification", "cost_treatment", "evidence_refs"]);
const UNIT_KINDS = new Set(["business", "personal_income"]);
const LIFECYCLES = new Set(["active", "building", "planned", "retired"]);
const ID = /^[a-z][a-z0-9_]*$/;
const OWNER_REF = /^human:[a-z][a-z0-9_]*$/;
const COST_CENTER_REF = /^agent:[a-z][a-z0-9_]*$/;

function matchesLabel(matcher, label) {
  if (typeof matcher !== "string" || typeof label !== "string") return false;
  const star = matcher.indexOf("*");
  if (star < 0) return matcher === label;
  return star === matcher.length - 1 && matcher.indexOf("*", star + 1) < 0 && label.startsWith(matcher.slice(0, -1));
}
```

Validation must first accept only the exact schema keys in the constant sets above; those permitted keys take
precedence over the secret/money-name scan (so `revenue_channel_ids` remains valid). For every non-schema key,
reject names matching
`/(?:amount|balance|revenue|profit|secret|token|api.?key|account.?number|private.?key|seed)/i`, string values starting
with `/Users/` or `/home/`, non-exact keys, and duplicate IDs. Deep-freeze a
cloned value so caller mutation cannot alter validated state. Apply `ID` to registry/unit/channel/ledger/exclusion IDs,
`OWNER_REF` only to `owner_ref`, and `COST_CENTER_REF` only to `cost_center_refs`; typed references are not generic IDs.
Add invalid owner/cost-centre reference mutations. `classifyLabel` returns sorted target IDs.

- [x] **Step 4: Run GREEN and diff check**

```bash
cd apps/life-call
node --test lib/cfo-registry.test.js
cd ../..
git diff --check
```

Expected: all Task 1 tests pass; diff check exits zero.

- [x] **Step 5: Commit and push Task 1**

```bash
git add apps/life-call/lib/cfo-registry.js apps/life-call/lib/cfo-registry.test.js
git commit -m "feat(cfo): validate financial unit registry"
git push
```

Completion evidence: commits `b1063e627`, `5622b0312`, and `f7b67187b`; focused tests 7/7 PASS; fix rounds 1-2 review clean.

- [x] **Downstream correction: accept strict typed owner and cost-centre references**

Task 2 preflight exposed that the exact `agent:franklin1` values cannot pass a generic `ID` regex. Add the typed
reference contract above, targeted tests, fresh review, state commit, and push before Task 2 resumes.

---

### Task 2: Canonical nine-unit registry

**Files:**
- Create: `apps/life-call/config/cfo-financial-units.json`
- Modify: `apps/life-call/lib/cfo-registry.test.js`

**Interfaces:**
- Consumes: `validateRegistry` and `classifyLabel` from Task 1.
- Produces: the sole registry file with ordered IDs:
  `life_manager_saas`, `anicca_ios`, `writer_agent`, `affiliate_agent`, `gig_work`, `x402_services`, `job_income`,
  `capafy_marketplace`, `proprietary_investing`.

- [x] **Step 1: Add failing canonical-registry tests**

```js
test("canonical registry exposes exactly nine ordered financial units", () => {
  const raw = JSON.parse(fs.readFileSync(path.join(__dirname, "../config/cfo-financial-units.json"), "utf8"));
  const registry = validateRegistry(raw);
  assert.deepEqual(registry.financial_units.map(x => x.financial_unit_id), [
    "life_manager_saas", "anicca_ios", "writer_agent", "affiliate_agent",
    "gig_work", "x402_services", "job_income", "capafy_marketplace", "proprietary_investing",
  ]);
  assert.equal(registry.financial_units.find(x => x.financial_unit_id === "job_income").unit_kind, "personal_income");
  assert.ok(registry.financial_units.filter(x => x.financial_unit_id !== "job_income").every(x => x.unit_kind === "business"));
});
```

Also assert representative mappings for every runtime namespace, `cfo`/`fleet` exclusions, and Franklin exclusions.

- [x] **Step 2: Run RED**

```bash
cd apps/life-call
node --test lib/cfo-registry.test.js
```

Expected: FAIL with `ENOENT` for `config/cfo-financial-units.json`.

- [x] **Step 3: Create the complete registry**

Use these exact values:

| ID | Kind | Lifecycle | Runtime matchers | Channel IDs | Ledger IDs | Cost centres |
|---|---|---|---|---|---|---|
| `life_manager_saas` | `business` | `active` | `ai.anicca.life-manager-*` | `stripe_life_manager`, `taskmarket_life_manager`, `ugig_life_manager` | `lm_agent_earnings` | none |
| `anicca_ios` | `business` | `active` | none | `apple_app_store_anicca` | `revenuecat_subscription_events` | none |
| `writer_agent` | `business` | `active` | `ai.anicca.writer-*` | `note_writer`, `substack_writer`, `publisher_writer` | `writer_receipts` | none |
| `affiliate_agent` | `business` | `building` | `ai.anicca.affiliate-*` | `amazon_associates`, `rakuten_affiliate`, `affiliate_networks` | `affiliate_commission_receipts` | none |
| `gig_work` | `business` | `active` | `ai.anicca.hf-gig-*`, `ai.anicca.gig-outcome-watch` | `gig_marketplaces`, `direct_gig_clients` | `gig_payment_receipts` | none |
| `x402_services` | `business` | `active` | `ai.anicca.x402-*` | `x402_onchain` | `x402_settlement_receipts` | `agent:franklin1`, `agent:franklin2` |
| `job_income` | `personal_income` | `active` | `ai.anicca.job-search-*` | `payroll_bank` | `payroll_bank_receipts` | none |
| `capafy_marketplace` | `business` | `building` | `ai.anicca.capafy-*`, Capafy provisioner | `capafy_sales` | `capafy_sales_receipts` | none |
| `proprietary_investing` | `business` | `planned` | `ai.anicca.autohedge`, `ai.anicca.pm-*`, `ai.anicca.reinvest` | `proprietary_investing` | `proprietary_investing_receipts` | none |

Every row uses `owner_ref: "human:dais"` and its table order as `display_order`. Use these exact identity fields:

| ID | Exact `display_name` | Exact `evidence_refs` |
|---|---|---|
| `life_manager_saas` | `{"en":"Life Manager","ja":"ライフマネージャー"}` | `["docs/superpowers/specs/2026-06-21-life-manager-LAUNCH-ORDER.md"]` |
| `anicca_ios` | `{"en":"Anicca iOS","ja":"アニッチャ iOS"}` | `["AGENTS.md"]` |
| `writer_agent` | `{"en":"Writer Agent","ja":"ライターエージェント"}` | `["docs/writer-agent/WRITER-AGENT-SSOT.md"]` |
| `affiliate_agent` | `{"en":"Affiliate Agent","ja":"アフィリエイトエージェント"}` | `["docs/affiliate-agent/AFFILIATE-AGENT-SSOT.md"]` |
| `gig_work` | `{"en":"Gig Work","ja":"ギグワーク"}` | `["docs/loop-engineering/26-gig-loop-asis-tobe-plan.md"]` |
| `x402_services` | `{"en":"x402 Services","ja":"x402サービス"}` | `["apps/x402-agents/package.json"]` |
| `job_income` | `{"en":"Employment Income","ja":"給与所得"}` | `["launchd:ai.anicca.job-search-*"]` |

Set `relevant_runtime_prefixes` to the literal prefixes covered above plus `ai.anicca.cfo-`, `ai.anicca.fleet-`,
`ai.anicca.franklin`, `ai.anicca.self-fix-`, and `ai.anicca.connector-healer-`.

Create exclusions:

```json
[
  {"exclusion_id":"cfo_controller","runtime_matchers":["ai.anicca.cfo-*"],"classification":"controller","cost_treatment":"shared_overhead","evidence_refs":["docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md"]},
  {"exclusion_id":"fleet_observer","runtime_matchers":["ai.anicca.fleet-*"],"classification":"observer","cost_treatment":"shared_overhead","evidence_refs":["docs/superpowers/specs/2026-08-04-fleet-and-remote-stability-design.md"]},
  {"exclusion_id":"repair_infrastructure","runtime_matchers":["ai.anicca.self-fix-*","ai.anicca.connector-healer-*"],"classification":"repair_infrastructure","cost_treatment":"shared_overhead","evidence_refs":["docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md"]},
  {"exclusion_id":"franklin_cost_centres","runtime_matchers":["ai.anicca.franklin-loop","ai.anicca.franklin2-loop"],"classification":"agent_cost_centre","cost_treatment":"x402_services","evidence_refs":["docs/superpowers/specs/2026-08-08-life-manager-cfo-m0-business-registry-design.md"]}
]
```

- [x] **Step 4: Run GREEN and diff check**

```bash
cd apps/life-call
node --test lib/cfo-registry.test.js
cd ../..
git diff --check
```

- [x] **Step 5: Commit and push Task 2**

```bash
git add apps/life-call/config/cfo-financial-units.json apps/life-call/lib/cfo-registry.test.js
git commit -m "feat(cfo): register canonical financial units"
git push
```

Completion evidence: commit `51cf20fa3`; focused tests 9/9 PASS; task review approved with no findings.

---

### Task 3: Deterministic inventory core

**Files:**
- Create: `apps/life-call/lib/cfo-inventory.js`
- Create: `apps/life-call/lib/cfo-inventory.test.js`

**Interfaces:**
- Consumes: validated registry and injected observations shaped as
  `{ label: string, state: "running"|"not_running"|"unknown", last_exit_code: number|null }`.
- Produces:
  - `normalizeLaunchctlList(stdout): Array<{ label: string, state: "running"|"not_running"|"unknown", last_exit_code: number|null }>`.
  - `collectSourceObservations(registry, exists): Array<{ evidence_ref: string, availability: "present"|"unavailable"|"not_applicable" }>`.
  - `buildInventory({ registry, runtimeObservations, sourceObservations, generatedAt, inventoryId }): object`.
  - `observationHash(receiptCore): string`.

- [x] **Step 1: Write failing inventory tests**

```js
test("inventory maps known labels and is deterministic across input order", () => {
  const first = buildInventory(makeInput(["ai.anicca.writer-report", "ai.anicca.x402-monitor"]));
  const second = buildInventory(makeInput(["ai.anicca.x402-monitor", "ai.anicca.writer-report"]));
  assert.equal(first.observation_hash, second.observation_hash);
  assert.equal(first.result, "pass");
});

test("unmapped relevant and ambiguous labels fail closed", () => {
  const unmapped = buildInventory(makeInput(["ai.anicca.franklin3-loop"]));
  assert.deepEqual(unmapped.unmapped_relevant_labels, ["ai.anicca.franklin3-loop"]);
  const ambiguous = buildInventory(makeInput(["ai.anicca.writer-report"], registryWithSecondWriterMatcher()));
  assert.deepEqual(ambiguous.ambiguous_labels.map(x => x.label), ["ai.anicca.writer-report"]);
  assert.equal(unmapped.result, "fail");
  assert.equal(ambiguous.result, "fail");
});
```

`makeInput(labels, registry = canonicalRegistry)` maps each label to state `unknown` and `last_exit_code: null`,
uses empty source observations, fixed `generatedAt: "2026-08-08T00:00:00.000Z"`, and fixed UUID
`00000000-0000-4000-8000-000000000001`. `registryWithSecondWriterMatcher()` deep-clones the canonical registry
and appends this syntactically valid exclusion before validation:

```js
{
  exclusion_id: "synthetic_writer_overlap",
  runtime_matchers: ["ai.anicca.writer-report"],
  classification: "controller",
  cost_treatment: "shared_overhead",
  evidence_refs: ["docs/superpowers/specs/2026-08-08-life-manager-cfo-m0-business-registry-design.md"],
}
```

Also test irrelevant labels are ignored, missing-runtime units are `unverified`, positive/negative exit codes are
observations rather than financial health, repo-relative evidence refs use the injected `exists` function, URI-like
refs are `not_applicable`, and receipt output contains no raw source payload.

- [x] **Step 2: Run RED**

```bash
cd apps/life-call
node --test lib/cfo-inventory.test.js
```

Expected: FAIL because `./cfo-inventory.js` does not exist.

- [x] **Step 3: Implement normalized classification and receipt construction**

Sort labels, units, findings, and source observations before hashing. Exclude `inventory_id`, `generated_at`, and
the final `observation_hash` from the hash input. Derive unit evidence status as `observed` when any runtime or
source is observed, otherwise `unverified`. Never emit `healthy`, `revenue`, or numeric money fields.

Use these exact minimal item shapes:

```js
financial_units: [{
  financial_unit_id, unit_kind, display_order, display_name, lifecycle,
  runtime_labels: [], source_evidence_refs: [], evidence_status: "observed" | "unverified",
}],
runtime_observations: [{
  label, state, last_exit_code, classification: "financial_unit" | "exclusion" | "unmapped" | "ambiguous",
  target_ids: [],
}],
source_observations: [{ evidence_ref, availability: "present" | "unavailable" | "not_applicable" }],
ambiguous_labels: [{ label, target_ids: [] }]
```

`source_observations` is the unique sorted union of unit and exclusion `evidence_refs`. A repo-relative ref calls
the injected `exists(ref)` and becomes `present` or `unavailable`; a URI-like ref becomes `not_applicable` without
calling `exists`. A unit's `source_evidence_refs` contains only its own present refs. `evidence_status` is inventory
evidence only: it is `observed` when `runtime_labels` or `source_evidence_refs` is non-empty, and never implies
revenue or health. Include every relevant runtime label, drop irrelevant labels, and sort all `target_ids`.

Set `registry_sha256 = sha256Canonical(registry)`. Hash exactly
`{registry_sha256, financial_units, runtime_observations, source_observations, unmapped_relevant_labels,
ambiguous_labels, result}`. `result` is `fail` only when an unmapped or ambiguous relevant label exists; missing
units and any exit code remain evidence, not failure.

```js
function observationHash(core) {
  return sha256Canonical(core);
}

function normalizeLaunchctlList(stdout) {
  return String(stdout).split(/\r?\n/).slice(1).map(line => line.trim().split(/\s+/)).filter(parts => parts.length >= 3)
    .map(([pid, status, label]) => ({
      label,
      state: /^\d+$/.test(pid) ? "running" : pid === "-" ? "not_running" : "unknown",
      last_exit_code: /^-?\d+$/.test(status) ? Number(status) : null,
    })).filter(item => /^ai\.anicca\./.test(item.label)).sort((a, b) => a.label.localeCompare(b.label));
}
```

- [x] **Step 4: Run GREEN and diff check**

```bash
cd apps/life-call
node --test lib/cfo-registry.test.js lib/cfo-inventory.test.js
cd ../..
git diff --check
```

- [x] **Step 5: Commit and push Task 3**

```bash
git add apps/life-call/lib/cfo-inventory.js apps/life-call/lib/cfo-inventory.test.js
git commit -m "feat(cfo): build deterministic business inventory"
git push
```

Completion evidence: commits `d0f27282e` and `29a9062dc`; focused tests 17/17 PASS; fix round 1 review clean.

---

### Task 4: Read-only CLI and immutable receipt

**Files:**
- Create: `apps/life-call/scripts/cfo-business-inventory.js`
- Create: `apps/life-call/scripts/cfo-business-inventory.test.js`
- Modify: `apps/life-call/package.json`

**Interfaces:**
- Consumes environment `LIFE_MANAGER_STATE_HOME`, defaulting to `~/.local/state/life-manager`.
- Produces receipt path
  `$LIFE_MANAGER_STATE_HOME/cfo/business-inventory/<generated-at-safe>--<inventory-id>.json` and one redacted JSON
  summary on stdout: `{ result, receipt_path, registry_sha256, observation_hash, unit_count, unmapped_count, ambiguous_count }`.
- Produces `main({ env, now, randomUUID, launchctlList, stdout }): { exitCode: number, summary: object }`; the
  executable entry supplies real defaults, while tests inject deterministic values.

- [x] **Step 1: Write failing CLI tests**

Call exported `main` in a temporary state root with injected `now`, `randomUUID`, and launchctl fixture containing
representative unit and exclusion labels. Assert exit zero, one receipt, mode `0600`, JSON re-read, hash match, and
no mutation commands. Run again with an unmapped relevant label and assert exit one plus an immutable failure
receipt. Pre-create the deterministic final receipt path and assert the CLI refuses overwrite.

```js
const output = [];
const result = main({
  env: { LIFE_MANAGER_STATE_HOME: stateRoot },
  now: () => new Date("2026-08-08T00:00:00.000Z"),
  randomUUID: () => "00000000-0000-4000-8000-000000000001",
  launchctlList: () => fixtureText,
  stdout: line => output.push(line),
});
assert.equal(result.exitCode, 0);
assert.equal(fs.readdirSync(receiptDir).length, 1);
assert.equal(fs.statSync(receiptPath).mode & 0o777, 0o600);
```

- [x] **Step 2: Run RED**

```bash
cd apps/life-call
node --test scripts/cfo-business-inventory.test.js
```

Expected: FAIL because the CLI does not exist.

- [x] **Step 3: Implement the minimal boundary**

Use `execFileSync("launchctl", ["list"], { encoding: "utf8", timeout: 10000 })` only in the executable default.
Do not call `launchctl print`, kickstart, stop, unload, network, database, or Telegram commands. Read the registry,
validate it, collect repo-relative evidence availability with `fs.existsSync`, build the receipt, create directories
with `0700`, open a unique temporary file using `wx` and mode
`0600`, write + `fsyncSync`, close, atomically publish with `linkSync(temporary, final)` so an existing final path
raises `EEXIST`, then unlink only the temporary name. On any error, clean up only that unique temporary file.

Add package script:

```json
"cfo:inventory": "node scripts/cfo-business-inventory.js"
```

- [x] **Step 4: Run GREEN, full targeted suite, and purity scan**

```bash
cd apps/life-call
node --test lib/cfo-registry.test.js lib/cfo-inventory.test.js scripts/cfo-business-inventory.test.js
! rg -n "kickstart|bootout|unload|stop|sendMessage|fetch\(|SUPABASE|TELEGRAM" scripts/cfo-business-inventory.js
cd ../..
git diff --check
```

- [x] **Step 5: Commit and push Task 4**

```bash
git add apps/life-call/scripts/cfo-business-inventory.js apps/life-call/scripts/cfo-business-inventory.test.js apps/life-call/package.json
git commit -m "feat(cfo): write immutable live inventory receipts"
git push
```

Completion evidence: commit `19ad38c86`; targeted tests 21/21 PASS; purity/diff checks PASS; task review approved.

---

### Task 5: Live Mac E2E and CFO-0c state closure

**Files:**
- Modify: `docs/superpowers/specs/2026-08-08-life-manager-cfo-m0-business-registry-design.md`
- Modify: `docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md`
- Modify: `docs/superpowers/plans/2026-08-08-life-manager-cfo-m0-business-registry.md`

**Interfaces:**
- Consumes: Tasks 1–4 and live read-only launchctl.
- Produces: one real receipt, its verified hashes, and `CFO-0c` checked complete. `CFO-0d` remains unchecked and
  becomes the only active financial item.

- [x] **Step 1: Run all targeted tests fresh**

```bash
cd apps/life-call
node --test lib/cfo-registry.test.js lib/cfo-inventory.test.js scripts/cfo-business-inventory.test.js
```

Expected: zero failures.

- [x] **Step 2: Run the real read-only inventory**

```bash
cd apps/life-call
npm run cfo:inventory
```

Expected summary: `result="pass"`, `unit_count=9`, `unmapped_count=0`, `ambiguous_count=0`; the receipt contains one
redacted ledger observation for each of the nine catalogue entries.

If the result fails, change only registry mappings justified by observed labels, add a failing regression test,
then repeat RED → GREEN and rerun live inventory. Do not mutate a launchd job to make the test pass.

- [x] **Step 3: Verify the receipt independently**

Use a one-shot Node command to parse the emitted receipt, reload the registry, recompute `registry_sha256`, rebuild
the hash input with volatile fields removed, and assert both hashes plus `result === "pass"`. The command must print
only `{result, unit_count, unmapped_count, ambiguous_count, hashes_verified}` and no raw paths or observations.

- [x] **Step 4: Run the existing Life Manager test suite**

```bash
cd apps/life-call
npm test
```

Expected: zero failures. A pre-existing unrelated failure is not waived; record exact evidence and repair only when
caused by this slice.

- [x] **Step 5: Close state without embedding private receipt data**

Mark `CFO-0c` checked in the parent. Change child status to `IMPLEMENTED — LIVE E2E PASS` and record only the commit,
test command, nine-unit count, zero finding counts, ledger status counts, and receipt SHA-256 references. Do not commit the local receipt
or expanded state path. Check every plan checkbox completed.

- [x] **Step 6: Final verification, commit, and push**

```bash
rg -n "CFO-0c|CFO-0d|IMPLEMENTED — LIVE E2E PASS" docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md docs/superpowers/specs/2026-08-08-life-manager-cfo-m0-business-registry-design.md
git diff --check
git status --short
git add docs/superpowers/specs/2026-08-06-life-manager-cfo-design.md docs/superpowers/specs/2026-08-08-life-manager-cfo-m0-business-registry-design.md docs/superpowers/plans/2026-08-08-life-manager-cfo-m0-business-registry.md
git commit -m "docs(cfo): close financial unit inventory"
git push
```

## Plan Self-Review Coverage

| Spec requirement | Implemented by |
|---|---|
| Strict identity/schema/privacy | Tasks 1–2 |
| Nine units and explicit exclusions | Task 2 |
| One/zero/multiple runtime mapping | Tasks 1 and 3 |
| Deterministic immutable receipt | Tasks 3–4 |
| Read-only effect boundary | Task 4 |
| Live nine-unit, zero-finding E2E | Task 5 |
| SSOT state transition | Task 5 |

---

## Final-review correction wave

The first live receipt was internally valid but fail-open: it filtered 139 live `ai.anicca.*` labels down to 45
before classification, so `unmapped_count=0` did not describe the complete Mac. Final review also found that ledger
source IDs were declared but never inventoried, privacy validation allowed repo escape and sensitive values,
`receipt_version` was outside the observation hash, locale-dependent sorting weakened cross-host determinism, and
the CFO tests were absent from the normal `npm test` path. CFO-0c is reopened until all four slices below close.

### F1 — Complete runtime census

**Goal:** classify all 139 observed `ai.anicca.*` labels exactly once and fail any future unknown label.

**Files / soft targets:**
- `apps/life-call/config/cfo-financial-units.json`: +150 data LOC
- `apps/life-call/lib/cfo-registry.test.js`: +70 test LOC
- `apps/life-call/lib/cfo-inventory.test.js`: +45 test LOC

The data file exceeds 100 LOC because it records the explicit business/exclusion ownership boundary; no service or
new abstraction is permitted. Add two verified units: `capafy_marketplace` for six Capafy sales runtimes and
`proprietary_investing` for AutoHedge, Polymarket, and reinvest. Map 33 ignored labels to existing units and 51 to
explicit shared/controller/observer/repair exclusions. `relevant_runtime_prefixes` becomes exactly
`["ai.anicca."]`; an unknown label is unmapped and fails.

### F2 — Canonical ledger-source inventory

**Goal:** resolve every unit ledger ID through one closed catalogue and emit availability only, never money or raw
rows.

**Files / soft targets:**
- `apps/life-call/config/cfo-financial-units.json`: +80 data LOC
- `apps/life-call/lib/cfo-registry.js`: +35 production LOC
- `apps/life-call/lib/cfo-registry.test.js`: +55 test LOC
- `apps/life-call/lib/cfo-inventory.js`: +30 production LOC
- `apps/life-call/lib/cfo-inventory.test.js`: +55 test LOC
- `apps/life-call/scripts/cfo-business-inventory.js`: +35 production LOC
- `apps/life-call/scripts/cfo-business-inventory.test.js`: +45 test LOC

This slice crosses files because one schema must be validated, inventoried, executed, and regression-tested as one
vertical boundary. The catalogue uses opaque, non-secret locators and closed statuses
`available|present_empty|stale_alias|planned|unavailable`. It records source availability/shape only. It does not
read balances, aggregate amounts, copy rows, or write any ledger. Missing/planned sources remain visible and can
never become revenue evidence.

Canonical corrections: replace stale `lm_financial_ledger` with `lm_agent_earnings`; bind RevenueCat to the
`subscription_events` audit source rather than Apple payout truth; retain the real Writer SQLite, Gig JSONL, and
x402 settlement sources; keep Affiliate and payroll adapters planned; add Capafy and proprietary-investing source
identities without inventing receipts.

### F3 — Privacy, immutable hash, and normal CI

**Goal:** close the three independent everlasting-safety gaps without expanding product behavior.

**Files / soft targets:**
- `apps/life-call/lib/cfo-registry.js`: +25 production LOC
- `apps/life-call/lib/cfo-registry.test.js`: +45 test LOC
- `apps/life-call/lib/cfo-inventory.js`: +8 production LOC
- `apps/life-call/lib/cfo-inventory.test.js`: +25 test LOC
- `apps/life-call/package.json`: +3 LOC

Reject absolute paths, `..` traversal, credentialed/query-bearing refs, secret-shaped values, and long account-like
digit runs. Resolve repo evidence only after proving the path stays below `REPO_ROOT`. Include `receipt_version` in
the observation hash and use locale-independent bytewise ordering. Add one `test:cfo` script and invoke it from the
normal `npm test` chain.

### F4 — Live repair verification and honest closure

**Goal:** replace the invalid 7/0/0 evidence with a complete live receipt and close documentation truth.

**Files / soft targets:**
- the parent spec, child spec, and this plan: +45 documentation LOC total

Run RED → GREEN for every correction; run the complete `npm test`; run the real read-only inventory; independently
recompute both hashes; assert the receipt observed all live `ai.anicca.*` labels, nine units, zero unmapped, zero
ambiguous, and one ledger observation per catalogue entry. Check every acceptance item, record exact commit hashes,
then mark CFO-0c complete and CFO-0d active. Do not commit a receipt, raw label list, expanded private path, secret,
balance, amount, transaction, or customer data.

### Final correction closure (2026-08-08)

- [x] F1 complete runtime census — `be53043ce` — 139 live labels classified as 84 financial units and 55 explicit
      exclusions; unknown labels fail closed.
- [x] F2 canonical ledger-source inventory — `7f56f93fb` — nine catalogue entries and nine redacted observations;
      status counts `planned=3`, `unavailable=6`.
- [x] F3 privacy, immutable hash, and normal CI — `86afe492d` — focused CFO tests are on the normal test chain.
- [x] F4 live repair verification and honest closure — documentation commit `ce2c99239`
      (`docs(cfo): close complete runtime inventory`); live counts are `unit_count=9`, `unmapped_count=0`, and
      `ambiguous_count=0`.
- Focused verification: `npm run test:cfo` passed 35/35. Full verification: fresh `npm test` exited 0 after
  `npm ci --no-audit --no-fund` restored the worktree's missing `ws` dependency.
- Independently verified hashes: `registry_sha256=32c3d67f09d3e72b6fdc8a4a8f5d95d38f14a9edd33e8d913238bf65b0868375`;
  `observation_hash=f459730c8505cf22b9f58d45287a6d382b10971b64e0199cf637bad92279046c`.
- Safety checks: receipt mode `0600`, containing directory mode `0700`, receipt not tracked, and no launchd/ledger/
  database/network-write/Telegram mutation.

#### Measured LOC versus cumulative soft targets

Measured with `wc -l` after F3. Test-file overages retain privacy, hash, catalogue, and live-census regression coverage;
the soft targets are not a reason to remove safety tests.

| File | Measured lines | Cumulative soft target | Difference |
|---|---:|---:|---:|
| `config/cfo-financial-units.json` | 245 | 355 | -110 |
| `lib/cfo-registry.js` | 221 | 155 | +66 |
| `lib/cfo-registry.test.js` | 460 | 265 | +195 |
| `lib/cfo-inventory.js` | 151 | 128 | +23 |
| `lib/cfo-inventory.test.js` | 251 | 220 | +31 |
| `scripts/cfo-business-inventory.js` | 130 | 120 | +10 |
| `scripts/cfo-business-inventory.test.js` | 206 | 135 | +71 |

The three F4 documents measured `+176/-57` with `git diff --numstat` against base, versus the `+45` documentation
soft target. The `+131` added-line overage records the expanded nine-source catalogue, redacted receipt contract,
acceptance evidence, and replacement of the invalid seven-unit evidence; it does not expand runtime scope.
