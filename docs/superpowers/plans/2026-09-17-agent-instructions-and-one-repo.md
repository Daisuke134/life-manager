# Agent Instructions and One-Repo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task by task. Read each applicable current Superpowers skill before acting. Steps use checkbox syntax for tracking.

**Goal:** Make Superpowers adherence observable and keep Life Manager source and project instructions in one repository.

**Architecture:** The root `AGENTS.md` owns project rules; root `CLAUDE.md` imports it. Harness startup loads `using-superpowers`, and narrow checks guard the source and integration boundaries. Source consolidation follows only after this entrypoint works.

**Tech Stack:** Git, Codex and Claude instruction files/hooks, existing Life Manager source and runtime registry.

**Spec:** `docs/superpowers/specs/2026-09-17-agent-instructions-and-one-repo-design.md`

## Global constraints

- Use `Daisuke134/life-manager` `main` as the integration authority and a dedicated worktree for each change.
- Preserve existing uncommitted work, active leases, runtime state, credentials and immutable releases.
- Follow the current installed Superpowers skill text, including its actual applicability and completion rules. Do not duplicate a fixed stage list.
- Do not archive a repository or remove a worktree based only on its name, age, or lock state.
- Keep the product order in `2026-09-06-life-manager-one-repo-two-runtimes-design.md` intact.

## Atomic TODO

### A. Establish instruction truth

- [ ] A1. From a clean worktree of current `origin/main`, capture the existing root/global `AGENTS.md`, `CLAUDE.md`, overrides, Codex fallback names and plugin versions; record which files fresh Codex and Claude sessions actually load.
- [ ] A2. Replace the deleted-Felix root `AGENTS.md` with a concise Life Manager coding contract: exact repository check, `using-superpowers` first, current applicable skills, observable completion evidence, and post-merge worktree removal. Preserve only still-valid project safety rules.
- [ ] A3. Make root `CLAUDE.md` import `@AGENTS.md` and retain only Claude-specific guidance. Confirm Claude reports that imported file in its loaded context.
- [ ] A4. Edit the generated global-rule source under `~/.config/ai/` to remove the opposing Superpowers-default language, run its existing sync command, and verify both generated harness files agree. Do not edit only one generated copy.
- [ ] A5. Start fresh Codex and Claude sessions in `life-manager-main`; ask each to report Git root, origin and loaded instruction sources. Fail this task if either reads an obsolete project rule or does not identify the canonical repository.

### B. Prove the Superpowers entrypoint

- [ ] B1. Inspect the installed Superpowers bootstrap and current harness hook schemas. Add the smallest supported Codex session-start/compact injection, and verify its output includes the installed `using-superpowers` content once.
- [ ] B2. Verify Claude's installed Superpowers startup hook actually injects the current bootstrap on startup and compaction; repair only the missing hook/configuration if readback fails.
- [ ] B3. Add deterministic source-boundary checks at the supported edit/push boundary: Git root and origin must match Life Manager. Give a clear failure message and verify both allowed and denied cases.
- [ ] B4. Run one small, real Life Manager development change through the applicable Superpowers skills. Capture skill-read, relevant design/plan, focused verification, merge and worktree cleanup receipts. Fix any observed gap in the entrypoint; do not count a verbal claim as a pass.

### C. Consolidate only required source

- [ ] C1. Inventory other local repositories and linked worktrees by exact path, Git common directory, remote, branch, dirty state, lock, owner, open PR, active process and source/runtime references. Mark unknowns explicitly.
- [ ] C2. Compare candidate mobile-app and other Life Manager assets against tracked source in `origin/main`. Classify each as already present, required missing, historical only, or runtime data; record the evidence and target path.
- [ ] C3. For each required missing asset, use a dedicated worktree and a small migration PR: copy source, update imports/build/deployment references, run focused verification, merge, and confirm the canonical path is used. Repeat only for verified required assets.
- [ ] C4. Re-scan active source and deployment references for old checkout paths/remotes. Archive an old repository only when the exact dependency count is zero and its required unmerged work is accounted for.

### D. Close worktrees without losing work

- [ ] D1. Re-audit registered worktrees immediately before cleanup; separate open-PR, dirty, locked, active-runtime and integrated candidates. Existing counts are not eligibility proof.
- [ ] D2. For each integrated candidate, verify exact merged commit, no unique uncommitted content, no process/open-file owner, and no active lease; then remove that exact worktree without force and confirm Git no longer registers it.
- [ ] D3. Report retained worktrees with owner and reason. Confirm the normal development checkout and current production releases still point to the intended source/release after cleanup.

## Verification and finish

- [ ] V1. Review the spec and this plan for stale Felix instructions, conflicting skill rules, missing dependencies, and claims unsupported by readback.
- [ ] V2. For each implementation PR, run its focused checks and `verification-before-completion` on the actual tree being integrated.
- [ ] V3. After integration, verify `origin/main`, loaded instructions in fresh Codex and Claude sessions, canonical source references, and exact worktree removal receipts. Update this checklist with evidence, not estimates.
