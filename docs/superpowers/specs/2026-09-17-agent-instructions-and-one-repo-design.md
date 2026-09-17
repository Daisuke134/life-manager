# Life Manager agent instructions and one-repo design

## Goal and priority

The primary outcome is that every Life Manager coding session actually uses the applicable, current Superpowers skills from start through finish. The second outcome is one source repository and one normal developer checkout, so a correct change cannot be stranded in an obsolete folder. This design supplements the ordered product TODO in `2026-09-06-life-manager-one-repo-two-runtimes-design.md`; it does not reorder or replace it.

## As-is: observed on 2026-09-17

- `Daisuke134/life-manager` is the repository SSOT. `life-manager-main` is its canonical local checkout. The repository already defines one product with local and cloud runtimes.
- The root `AGENTS.md` still describes a deleted Felix workspace and does not provide the coding-agent entrypoint. The root `CLAUDE.md` points to it but does not import it. An older `anicca-project/AGENTS.md` contains a Superpowers rule, but it is outside the Life Manager instruction-discovery path.
- The generated global Codex and Claude instructions say that the full Superpowers workflow is not the default. This conflicts with Dais's current requirement to use Superpowers for development.
- The installed Superpowers Codex manifest has `"hooks": {}`. Its skills are available, but that manifest does not inject `using-superpowers` at session start. The separate local Codex hooks do not currently inject it either. Availability is not proof of invocation.
- `life-manager-main` was observed on a dirty feature branch. Git registered 177 linked worktrees, 134 locked and 15 with missing paths. These are audit counts, not deletion eligibility.
- The one-repo/two-runtime spec already defines the source/runtime boundary and worktree lifecycle. This design narrows the missing instruction and enforcement contract.

## To-be: one source and one instruction body

```text
~/Projects/life-manager-main/             # normal development checkout; origin Daisuke134/life-manager
├── AGENTS.md                              # one concise project instruction body for coding agents
├── CLAUDE.md                              # @AGENTS.md plus only Claude-specific loading notes
├── apps/                                  # Life Manager web, mobile and other owned app source
│   └── mobile/                            # canonical mobile app source
│       ├── anicca-ios/                    # Anicca iOS source and Xcode project
│       └── honne-ai/                      # Honne app and small backend
├── skills/                                # product capabilities and provider adapters
├── runtime/                               # local/cloud execution code
├── services/                              # supporting service source
├── config/                                # registry and source configuration
├── docs/superpowers/                      # designs, implementation plans, evidence pointers
└── .worktrees/<task>/                     # temporary isolated development checkout, removed after integration

outside the Git repository:
  ~/.codex/ and ~/.claude/                 # harness-level settings and global instructions
  ~/.local/share/anicca/credentials.json  # private credential SSOT
  ~/.local/state/life-manager/ and ~/loops/releases/ # live state and immutable releases
  browser profiles, logs and receipts     # runtime data, never source authority
```

One repository does not mean one physical directory. Temporary worktrees and runtime-owned state remain outside the source authority. Only assets actually needed by Life Manager move from other repositories; existing copies are compared before any migration. A registry remote/revision retained after migration is provenance, while `canonical_source_rel` identifies the source used for local edits and build preparation.

## Superpowers adherence contract

1. At session start, resolve the actual Git root, `origin`, branch, and loaded instruction files. A session with a different source repository cannot edit Life Manager source.
2. Load `using-superpowers` and read each applicable skill before its step. Use the installed skill as the procedure; do not maintain a competing fixed-stage summary. Ponytail chooses the smallest sufficient implementation within that procedure.
3. Record observable milestones: skill and version/path read, design/plan when applicable, focused test or verification output, source commit, PR/merge result, and worktree disposition. A claim that a skill was used is not evidence that its steps were followed.
4. Inject the bootstrap at session start and after compaction where the harness supports it. Add narrow, deterministic checks at edit, push, and stop boundaries for wrong repository, unintegrated work, and worktree cleanup. Hooks are guardrails, not a complete proof of model reasoning; verify one real task in both Codex and Claude.
5. Keep an open PR's worktree while feedback may still require edits. Once its work is integrated, verify the merged commit and no unique uncommitted files or active owner, then remove that exact worktree and prune its registration. Never infer deletion eligibility from age, directory name, or lock alone.

## Completion conditions

- Fresh Codex and Claude sessions launched in Life Manager report the expected root files and read the current `using-superpowers` before development action.
- A representative small change produces the required design/plan, implementation, verification, integration and cleanup evidence for the skills applicable to that change; a missing step is visible and blocks a false completion claim.
- No active Life Manager source or deployment imports another checkout. Required mobile-app source is in this repository, or is explicitly recorded as not required by the current product contract.
- Old repositories are archived only after source and runtime-reference readback reaches zero. Every removed worktree has an exact-path, owner, dirty-state and integration preflight; all retained worktrees have an owner and reason.

## Order

`instruction truth -> bootstrap/readback -> one real adherence trial -> asset/dependency inventory -> required source migration -> archive -> exact-path worktree cleanup`.

This order fixes the process that will execute the larger consolidation before touching old source folders. It is internal to the existing product TODO and does not interrupt active production effects.

## A-series verification evidence

- Before the project edit, a fresh Codex session in this worktree reported the canonical root, branch and origin but no `using-superpowers` injection. A fresh Claude session launched in the same worktree loaded global `~/.claude/CLAUDE.md` and the project `CLAUDE.md`, but its referenced `AGENTS.md` was not loaded because the file was not imported.
- After the project edit, fresh Codex and Claude sessions reported the same Life Manager worktree, `docs/agent-instructions-consolidation-20260917`, and `https://github.com/Daisuke134/life-manager.git`. Both identified the project instructions as Life Manager rather than Felix. Claude loaded `CLAUDE.md` and its `@AGENTS.md` import; Codex loaded `AGENTS.md`.
- `~/.config/ai/bootstrap.sh --check` passed after syncing the generated Codex, Claude, Gemini and second-account files. The shared source now requires `using-superpowers` for software development and does not require a copied fixed stage list.
- The same post-edit sessions still reported that the `using-superpowers` skill body was not injected at startup. This is an explicit B1/B2 failure to repair, not an A-series pass condition.

## B-series verification evidence

- Claude's first normal session was blocked before plugin loading because `/Users/anicca/.claude/settings.json` used the obsolete boolean `permissions.disableAutoMode: true`. After changing it to the current string value `"disable"`, `claude doctor` reported no installation issues and `claude plugin list --json` reported Superpowers 6.3.0 `enabled: true`.
- A fresh normal interactive Claude session in the Life Manager worktree reported `using-superpowers` injected by the SessionStart hook, `superpowers:brainstorming` available, and both project `CLAUDE.md` and imported `AGENTS.md` loaded. The session made no edits and was exited cleanly.
- Headless `claude -p` does not load user plugins in this installation's Agent SDK path; an explicit `--plugin-dir` read-only session did load the same official hook. This is recorded as a harness limitation, not a project wrapper.
- Superpowers 6.3.0's Codex manifest has an intentional empty `hooks` object and its release notes document native Codex skill discovery. This machine's Codex CLI has no reserved `openai-curated` marketplace snapshot, so a single symlink at `~/.agents/skills/superpowers` now exposes the official cache through Codex's supported USER skill path without copying files or adding a second hook. A fresh Codex CLI session listed the six required Superpowers skills.
- `bash scripts/verify-source-boundary.sh` passes from the canonical Life Manager worktree and rejects `/Users/anicca/anicca-project` with a wrong checkout root/origin. It also rejects an independent clone nested under `.worktrees` because its Git common directory is not `/Users/anicca/Projects/life-manager-main/.git`. The check is repository-owned and agent-invoked before edit/push; it is intentionally not a second hook framework.
- The first PR CI run caught that a hardcoded local path in the boundary script violated the repository's OSS self-contained source fence. The script now derives the canonical root from `$HOME/Projects/life-manager-main`, so source contains no machine-specific absolute path; local shell syntax, canonical PASS, `anicca-project` FAIL, and an independent clone's own-script FAIL were rerun successfully.
- The subsequent Loop control CI failure was traced to the temporary root `package.json` script addition: the release test intentionally archives `origin/main` package files while the donor uses the working tree, so the extra script made their hashes differ. Removing that unnecessary npm alias and invoking the boundary script directly restored the contract; the isolated symlinked-donor test and all 12 `test_cut_loop_release` tests now pass locally. No runtime loop file was changed.

## C-series inventory and classification evidence

- On 2026-09-17, `scripts/worktree-lease.py audit` returned 179 registered worktrees: states `unmanaged=44`, `unmanaged-locked=29`, `expired=90`, `active=16`; 135 were locked and 15 registered paths were missing. A separate status scan found 4 dirty existing worktrees, 4 prunable registrations, 144 paths under `/private/tmp`, and 23 under the canonical repository's `.worktrees`. These are classification counts only; none was removed.
- A read-only repository scan found 38 Git repositories under `/Users/anicca/Projects`: 12 with the canonical `Daisuke134/life-manager.git` remote, one `life-manager-workrooms.git` repository, and the rest external research/reference repositories. The canonical checkout was dirty on `capafy/account-plan-deck-offline-20260912`; the `GH-32` Life Manager workroom checkout was also dirty. They remain untouched.
- `/Users/anicca/anicca-project` is a separate dirty checkout whose `origin` is `Daisuke134/anicca-products.git`. It contains 36M of `aniccaios` and 213M of `mobile-apps`, alongside unrelated apps and generated artifacts. It is an inventory source, not a migration target to edit in place.
- C2 classification: `apps/life-manager/mobile-starter-packs/`, mobile loop runners, and the scoped `apps/landing` files are already in the canonical repository; the real `aniccaios` source referenced by `mobile-products.json` at revision `a9ab8a17c7dee9af8c3f2ad752a902ce26e7d1d3` was a required-missing candidate; the private `honne-ai` source at revision `b57928bb13ef1f9a1e774e4bca2467e3059c9eac` remains another required-missing candidate; unrelated old Swift apps, screenshots, IPAs, reports and build outputs are historical or runtime data and are not migrated by default.
- C3 Anicca iOS result: the source, Xcode project, widget/notification extensions, tests, localizations, runtime resources, Maestro definitions and deployment scripts from the fixed public revision are now under `apps/mobile/anicca-ios/`. Generated screenshots/reports, editor metadata, signing/export files and credential-bearing config values were excluded. The registry keeps the remote/subdirectory/revision as provenance and adds `canonical_source_rel: apps/mobile/anicca-ios`; the focused registry and mobile-command tests assert that path exists. `Configs/*.example` documents the private build inputs.
- C3 Honne result: the private fixed revision was audited through the authenticated GitHub API, and the app source, Xcode project, tests, backend and deployment code are now under `apps/mobile/honne-ai/`. The mobileprovision, export plist, Fastlane report, screenshots and embedded RevenueCat/App Store Connect values were excluded or replaced with private environment/bundle inputs. The registry adds `canonical_source_rel: apps/mobile/honne-ai`; focused tests assert the canonical project path. No private credential value was copied.
- C4 re-scan result: after both migrations, active mobile/build paths resolve to `apps/mobile/anicca-ios` or `apps/mobile/honne-ai`; the two Git remotes remain registry provenance only. The presentation helper no longer defaults to an old checkout and now fails closed unless `PPTX_SKILL_ROOT` is supplied. Remaining legacy-name matches are historical docs, test fixtures, the OSS forbidden-path guard, or the disk governor's intentional host-inventory family. The old `anicca-project` checkout is still dirty and has a live `node_repl` owner, so it is retained pending a later Dais-owned handoff.

## D-series closeout evidence

- The fresh post-migration worktree audit recorded 167 Git registrations: 20 active leases, 77 expired leases, 41 unmanaged, 29 unmanaged-locked, 126 locked entries and 15 missing paths. Twenty-four open PRs were read back separately; an active or dirty/open-PR worktree was never treated as cleanup-eligible.
- Thirteen canonical `.worktrees` were individually verified as clean, ancestors of `origin/main`, without open PRs, active lease, or `lsof` owner, then unlocked and removed without force. Each exact path and Git registration disappeared. A `writer-integrated` candidate changed branch/HEAD during its preflight and was retained. Forty-eight `/private/tmp` candidates matched the clean/full-status + main-ancestor + no-open-PR shape but still need their own lsof/owner pass; 15 missing locked registrations lack content proof and remain retained.
- Retained worktrees have an explicit reason: active lease owner, open PR, dirty/unique branch, locked unmanaged state without integration proof, missing path without content proof, or concurrent branch mutation. The canonical checkout remains dirty on `capafy/account-plan-deck-offline-20260912`. The final D2 audit found no remaining safe cleanup candidate; 15 missing locked registrations remain without content proof. `~/loops/current` points to immutable release `a77c5629e1` with `provenance=ancestor-of-origin-main`, while latest `origin/main` is `4d506060ce`. Read-only launchd inspection found the loaded mobile labels using main-derived immutable releases `37384185…` (Anicca and most routes), `203bbe88…` (Honne EN), and `61036e1e…` (Honne JA); the `37384185…` tree contains both canonical mobile paths. The Postiz/mobile receipt suite remains green, so no immediate cutover is required for the migrated source, but controlled newer-release rollout confirmation remains an owner-controlled D3 task.
- Targeted mobile status then found the shared host-admission fence: each affected publish owner has a private `effect_unknown=1` occurrence, so the next wake is correctly held before provider retry. Existing Postiz receipts are not sufficient to clear a row without an exact occurrence/effect identity and official provider readback. The focused recovery design and atomic plan are in `docs/superpowers/specs/2026-09-18-mobile-postiz-admission-recovery-design.md` and `docs/superpowers/plans/2026-09-18-mobile-postiz-admission-recovery.md`.

## B4/V-series closeout evidence

- The representative Life Manager change was implemented in the dedicated worktree `docs/agent-instructions-consolidation-20260917`, reviewed by a fresh read-only reviewer (`ship`), verified locally with the full app suite and release module, passed all 9 PR checks, and merged as PR #5332 into `origin/main` at `4835540a7f31bc4396b7e7c78c7877bc42718892`.
- The exact worktree was removed without force after merge; a subsequent `git worktree list --porcelain` contained no `agent-instructions-consolidation-20260917` entry. PR #5332 merged at `4835540a7f31bc4396b7e7c78c7877bc42718892`; later concurrent work advanced current `origin/main` to `b271a6702a`. A clean closeout worktree was used for this checklist update.
- Fresh post-merge Codex reported Life Manager root/origin and native `using-superpowers`, `brainstorming`, and finish skills. Fresh post-merge Claude reported SessionStart `using-superpowers` injection, `superpowers:brainstorming` availability, and project `CLAUDE.md` importing `AGENTS.md`. Remaining C3/C4/D tasks are unchanged.
