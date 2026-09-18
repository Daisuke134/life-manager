# Agent Worktree Promotion Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Life Manager coding agent keep source changes isolated in its own worktree and promote them to production only through main, immutable release, targeted load and official readback.

**Architecture:** The worktree is the development plane: source edits, focused tests, local fixtures and owner-scoped temporary state. Main and immutable releases are the promotion plane: PR review/checks, complete release, targeted owner load, natural terminal and official effect/readback. Shared runtime, admission, browser profiles and production state remain outside a loop owner's worktree.

**Tech Stack:** Git worktrees, GitHub Flow/PR checks, immutable Life Manager releases, `lm-loop`, Markdown contract docs.

**Spec:** `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md`

## Global Constraints

- One independent workstream owns one worktree, branch, lease and mutable test state.
- Production uses only a pushed `origin/main` ancestor in an immutable release.
- A worktree test or exit 0 never proves a provider effect.
- Shared `runtime/`, admission, release control, registry, browser profile and credential state stay with their owners.
- Official provider readback, Calendar exact-one and replay-zero are required for external success.

### Task 1: Add the repository contract

**Files:**
- Create: `docs/agent-engineering/WORKTREE-PROMOTION-CONTRACT.md`
- Test: `git diff --check` and required-section grep

- [x] Write the contract with development plane, promotion plane, ownership, no-self-blocking and completion evidence.
- [x] Include the exact promotion sequence: focused test → push branch → PR/checks → merge main → complete immutable release → targeted loaded-idle apply → natural terminal → official readback → replay-zero.
- [x] Include the forbidden shortcut: never run unfinished worktree code against production profiles/state and never merge incomplete provider code just to remove a local blocker.

### Task 2: Wire the contract into agent instructions

**Files:**
- Modify: `AGENTS.md`
- Modify: `skills/loop-development/SKILL.md`
- Test: `git diff --check` and section/reference grep

- [x] Add a short AGENTS reference to the contract without changing the existing ownership boundaries.
- [x] Add the same development/promotion distinction to the repository loop skill so every loop change reads it before editing.
- [x] Preserve existing source-of-truth and no-sibling-mutation rules.

### Task 3: Verify and publish the docs-only change

**Files:**
- Test: `git diff --check`
- Test: `rg` contract invariants

- [x] Confirm only the three intended docs/instruction files plus this plan changed.
- [x] Commit with a docs-only message.
- [x] Push the dedicated branch and record the PR URL.
- [x] Do not merge to main until the repository's normal PR checks and the user outcome gate permit promotion.
