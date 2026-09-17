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

One repository does not mean one physical directory. Temporary worktrees and runtime-owned state remain outside the source authority. Only assets actually needed by Life Manager move from other repositories; existing copies are compared before any migration.

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
- `npm run verify:source-boundary` passes from the canonical Life Manager worktree and rejects `/Users/anicca/anicca-project` with a wrong checkout root/origin. It also rejects an independent clone nested under `.worktrees` because its Git common directory is not `/Users/anicca/Projects/life-manager-main/.git`. The check is repository-owned and agent-invoked before edit/push; it is intentionally not a second hook framework.
- The first PR CI run caught that a hardcoded local path in the boundary script violated the repository's OSS self-contained source fence. The script now derives the canonical root from its own repository parent `.git` directory, so source contains no machine-specific absolute path; local shell syntax, boundary PASS/FAIL cases and the full app suite were rerun successfully.

## C-series inventory and classification evidence

- On 2026-09-17, `scripts/worktree-lease.py audit` returned 179 registered worktrees: states `unmanaged=44`, `unmanaged-locked=29`, `expired=90`, `active=16`; 135 were locked and 15 registered paths were missing. A separate status scan found 4 dirty existing worktrees, 4 prunable registrations, 144 paths under `/private/tmp`, and 23 under the canonical repository's `.worktrees`. These are classification counts only; none was removed.
- A read-only repository scan found 38 Git repositories under `/Users/anicca/Projects`: 12 with the canonical `Daisuke134/life-manager.git` remote, one `life-manager-workrooms.git` repository, and the rest external research/reference repositories. The canonical checkout was dirty on `capafy/account-plan-deck-offline-20260912`; the `GH-32` Life Manager workroom checkout was also dirty. They remain untouched.
- `/Users/anicca/anicca-project` is a separate dirty checkout whose `origin` is `Daisuke134/anicca-products.git`. It contains 36M of `aniccaios` and 213M of `mobile-apps`, alongside unrelated apps and generated artifacts. It is an inventory source, not a migration target to edit in place.
- C2 classification: `apps/life-manager/mobile-starter-packs/`, mobile loop runners, and the scoped `apps/landing` files are already in the canonical repository; the real `aniccaios` source referenced by `mobile-products.json` at revision `a9ab8a17c7dee9af8c3f2ad752a902ce26e7d1d3` is a required-missing candidate pending comparison; the private `honne-ai` source at revision `b57928bb13ef1f9a1e774e4bca2467e3059c9eac` is another required-missing candidate; unrelated old Swift apps, screenshots, IPAs, reports and build outputs are historical or runtime data and are not migrated by default. The external pointers remain until C3 proves the canonical replacement.
