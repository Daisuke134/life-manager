# Agent Engineering Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build seven code-grounded Life Manager agent-engineering skills that future loop work can load on demand.

**Architecture:** Keep the existing Loop Engineering router and add six sibling skills under `skills/`. Each skill is a concise router plus concrete local/OSS source pointers; heavy details live in focused references. The skills guide the existing runtime and never become a second runtime dependency.

**Tech Stack:** Markdown skills, Python/JavaScript source maps, Git sparse clones, existing Life Manager tests and `quick_validate.py`.

**Spec:** `docs/superpowers/specs/2026-09-15-agent-engineering-skills-design.md`

## Global Constraints

- Do not edit `skills/earn/gig/TODO.md`; it is owned by the other Codex worktree.
- Do not edit production loop code, launchd state, browser state, private state, or credentials.
- Use existing Life Manager seams before proposing new abstractions.
- Keep semantic judgment in the model; keep effects, leases, budgets, hashes, receipts, and redaction deterministic.
- Record source URL, pinned commit, license, and exact source paths for every adopted OSS pattern.
- Validate every new or changed skill before moving to the next one.

### Task 1: Create the red contract test before any new skill

**Files:**
- Create: `skills/agent-engineering/tests/test_skill_contract.py`

**Interfaces:**
- Consumes: the seven planned skill paths and `docs/agent-engineering/REFERENCE-REPOS.md`.
- Produces: a deterministic test that checks required frontmatter, trigger wording, core sections, and source-map existence.

- [ ] **Step 1: Write the failing test**

  Assert that these paths exist after implementation: `skills/harness-engineering/SKILL.md`,
  `skills/context-engineering/SKILL.md`, `skills/loop-engineering/SKILL.md`,
  `skills/graph-engineering/SKILL.md`, `skills/eval-engineering/SKILL.md`,
  `skills/observability-engineering/SKILL.md`, and `skills/goal-engineering/SKILL.md`.
  Assert each file starts with YAML `name` and a `description` beginning with `Use when`, and
  contains `## Recipe`, `## Contract`, `## Failure modes`, and `## Source map`.

- [ ] **Step 2: Run the test and verify RED**

  Run `python3 -m pytest skills/agent-engineering/tests/test_skill_contract.py -q`.
  Expected: FAIL because the six new files and the new required sections do not exist yet.

### Task 2: Record the cloned source set

**Files:**
- Create: `docs/agent-engineering/REFERENCE-REPOS.md`
- Create: `docs/agent-engineering/SOURCE-MAP.md`

**Interfaces:**
- Consumes: the nine sparse clones under `/Users/anicca/Projects/life-manager-agent-engineering-references/`.
- Produces: pinned URL/commit/license records and a local function-to-source adoption matrix.

- [ ] **Step 1: Record metadata**

  For each clone, write the URL, commit, license, checkout path, and selected directories. Mark
  `openai/simple-evals` as a historical baseline because its README says it is no longer actively maintained.

- [ ] **Step 2: Record code pointers**

  Map at least one concrete source function/module per topic to its Life Manager counterpart. Do
  not copy upstream code; preserve the source license and link.

- [ ] **Step 3: Verify paths**

  Run `python3 -m pytest skills/agent-engineering/tests/test_skill_contract.py -q`.
  Expected: still FAIL only for missing skill documents, while all recorded source paths resolve.

### Task 3: Write and validate Harness Engineering

**Files:**
- Create: `skills/harness-engineering/SKILL.md`
- Create: `skills/harness-engineering/references/source-notes.md`

**Interfaces:**
- Consumes: Symphony workspace/orchestrator code, Deep Agents middleware, OpenHands runtime/events,
  Hermes state/tool boundaries, and local `runtime/loop` seams.
- Produces: a recipe for augmented-LLM harnesses, owner isolation, tool contracts, recovery, and
  explicit effect/readback boundaries.

- [ ] **Step 1: Write the skill**

  Include one runnable JavaScript example using `runSkill`/`resolveSkillPath`, a contract table, and
  a red-flag list covering duplicate owners, hidden side effects, PID-only success, and hardcoded
  semantic routing.

- [ ] **Step 2: Validate**

  Run `python3 /Users/anicca/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/harness-engineering`.
  Expected: PASS.

### Task 4: Write and validate Context Engineering

**Files:**
- Create: `skills/context-engineering/SKILL.md`
- Create: `skills/context-engineering/references/source-notes.md`

**Interfaces:**
- Consumes: Deep Agents context middleware, LangGraph checkpoint/store APIs, Graphiti episodes/search,
  Hermes compression, local prompt/context graph code, and the Project Context Capsule contract.
- Produces: a context compiler recipe with source tiers, freshness/provenance, budgeted summaries,
  offload pointers, and a no-tail-only rule.

- [ ] **Step 1: Write the skill**

  Include one concrete capsule JSON shape and a JavaScript example that keeps source hashes and
  official receipts while summarizing older turns.

- [ ] **Step 2: Validate**

  Run `python3 /Users/anicca/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/context-engineering`.
  Expected: PASS.

### Task 5: Refine Loop Engineering

**Files:**
- Modify: `skills/loop-engineering/SKILL.md`
- Create: `skills/loop-engineering/references/source-notes.md`

**Interfaces:**
- Consumes: current Loop Engineering router and Loop Development lifecycle contract.
- Produces: an expanded but concise loop recipe for observe → reconstruct → decide → act → verify →
  persist → wake, with state/owner/retry/replay/stop boundaries.

- [ ] **Step 1: Preserve the existing router**

  Keep existing route links and lane ownership rules. Add explicit goal/context/eval/observability
  handoffs and cite Symphony/LangGraph source functions.

- [ ] **Step 2: Validate**

  Run `python3 /Users/anicca/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/loop-engineering`.
  Expected: PASS with no duplicate runtime instructions.

### Task 6: Write and validate Graph Engineering

**Files:**
- Create: `skills/graph-engineering/SKILL.md`
- Create: `skills/graph-engineering/references/source-notes.md`

**Interfaces:**
- Consumes: Graphiti temporal nodes/edges/search, LangGraph state graphs, and local context graph /
  integration graph projections.
- Produces: a minimal projection recipe with competency questions, provenance, identity, edge
  semantics, cycle checks, and a single append-only fact source.

- [ ] **Step 1: Write the skill**

  Include a node/edge table and a JavaScript/Python projection example that never treats a graph
  projection as authoritative effect proof.

- [ ] **Step 2: Validate**

  Run the skill validator for `skills/graph-engineering`.
  Expected: PASS.

### Task 7: Write and validate Eval Engineering

**Files:**
- Create: `skills/eval-engineering/SKILL.md`
- Create: `skills/eval-engineering/references/source-notes.md`

**Interfaces:**
- Consumes: Inspect task/solver/scorer/log patterns, DSPy optimizer modules, simple-evals reference
  baselines, and local `apps/life-manager/eval` plus promotion gates.
- Produces: a recipe for datasets, deterministic checks, model graders, held-out cases, regression
  thresholds, and promotion only after realized evidence.

- [ ] **Step 1: Write the skill**

  Include one eval-case JSONL example and a Python scoring skeleton that separates fixture quality,
  live receipts, and promotion authority.

- [ ] **Step 2: Validate**

  Run the skill validator for `skills/eval-engineering`.
  Expected: PASS.

### Task 8: Write and validate Observability Engineering

**Files:**
- Create: `skills/observability-engineering/SKILL.md`
- Create: `skills/observability-engineering/references/source-notes.md`

**Interfaces:**
- Consumes: Phoenix OpenTelemetry/OpenInference code, Symphony structured logging/status, local
  harness-health and effect-reconciliation modules.
- Produces: a trace/metric/receipt recipe with correlation IDs, privacy redaction, latency/cost/
  retry metrics, and a clear distinction between liveness and business effect.

- [ ] **Step 1: Write the skill**

  Include one span/event schema and a small redaction example. State that logs, PIDs, and Telegram
  messages are not provider-effect truth without official readback.

- [ ] **Step 2: Validate**

  Run the skill validator for `skills/observability-engineering`.
  Expected: PASS.

### Task 9: Write and validate Goal Engineering

**Files:**
- Create: `skills/goal-engineering/SKILL.md`
- Create: `skills/goal-engineering/references/source-notes.md`

**Interfaces:**
- Consumes: Automaton constitution/lifecycle, Hermes self-evolution `evolve`/`SkillModule`, Symphony
  workflow states, and local spawn/promotion gates.
- Produces: a goal contract with owner, horizon, evidence, budget, lifecycle, replanning, and
  bounded recursive-improvement rules.

- [ ] **Step 1: Write the skill**

  Include one goal JSON shape and a state-transition table. Require improvement candidates to beat a
  baseline, pass tripwires, retain provenance, and stop on unresolved external identity or safety.

- [ ] **Step 2: Validate**

  Run the skill validator for `skills/goal-engineering`.
  Expected: PASS.

### Task 10: Run the full contract and repository checks

**Files:**
- Modify: only files listed above.

- [ ] **Step 1: Run all skill validators**

  Run `for d in skills/harness-engineering skills/context-engineering skills/loop-engineering skills/graph-engineering skills/eval-engineering skills/observability-engineering skills/goal-engineering; do python3 /Users/anicca/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$d"; done`.
  Expected: all seven PASS.

- [ ] **Step 2: Run the contract test**

  Run `python3 -m pytest skills/agent-engineering/tests/test_skill_contract.py -q`.
  Expected: PASS for all seven skills and source-map paths.

- [ ] **Step 3: Check documentation and scope**

  Run `git diff --check` and `git status --short`.
  Expected: no whitespace errors, no `skills/earn/gig/TODO.md` change, and only the planned files changed.

- [ ] **Step 4: Commit and push**

  Run `git add docs/agent-engineering docs/superpowers/specs/2026-09-15-agent-engineering-skills-design.md docs/superpowers/plans/2026-09-15-agent-engineering-skills.md skills/agent-engineering skills/harness-engineering skills/context-engineering skills/loop-engineering skills/graph-engineering skills/eval-engineering skills/observability-engineering skills/goal-engineering && git commit -m "docs: add agent engineering skill recipes" && git push -u origin docs/agent-engineering-skills-20260915`.
  Expected: one pushed commit on the dedicated branch; no merge or production release in this task.
