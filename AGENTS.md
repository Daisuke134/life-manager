# Life Manager project instructions

This repository is the source authority for Life Manager. The canonical remote is
`https://github.com/Daisuke134/life-manager.git`; the normal local checkout is
`/Users/anicca/Projects/life-manager-main`.

## Before any development action

- Confirm the Git root, current branch, common Git directory and `origin` before reading or editing source. If the root or remote is not Life Manager, stop and report the mismatch.
- Run `bash scripts/verify-source-boundary.sh` before editing or pushing. It accepts only this canonical checkout or one of its temporary `.worktrees` and the canonical Life Manager `origin`.
- Read the current `superpowers:using-superpowers` skill first. If the harness exposes native skill names, the equivalent entry is `using-superpowers` backed by the linked Superpowers source in `~/.agents/skills/superpowers`. Then read and follow every Superpowers skill that applies to the task before its step. Use the installed skill text as the procedure; do not rely on a copied or stale stage list.
- For substantial software work, use Astra Advisor orchestration when the harness exposes it; if it is unavailable, record that mismatch and continue with the applicable Superpowers path.
- Use Ponytail as the minimal-solution check inside that workflow: reuse existing code, native tools and installed dependencies before adding anything.
- For Life Manager loop, launchd, release, runtime-event, provider-routing or cleanup changes, read `skills/loop-development/SKILL.md` before acting.
- Preserve unrelated edits, active worktrees, runtime state, credentials and immutable releases. Do not edit another checkout to make a Life Manager change.

## Development and evidence

- Use a dedicated worktree and branch for repository changes, based on current `origin/main`. Work in the normal checkout only when a documented runtime store requires it.
- Follow the applicable Superpowers path: design or clarification, implementation plan when required, test-first implementation for behavior changes, focused verification, review when the skill requires it, and branch finishing.
- Record observable evidence for the steps that matter: the skill path read, tests or checks run, the commit and remote, integration result, and worktree disposition. A prose claim that a skill was used is not evidence.
- Do not claim completion from a plan, a draft, a process exit code, or a local mock when the requested result requires an external readback.

## Repository and runtime boundaries

- `Daisuke134/life-manager` is the only active Life Manager source repository. Required app, mobile, capability, workflow and deployment source belongs under this repository.
- Runtime state, credentials, browser profiles, logs, receipts, ledgers, and immutable releases stay outside Git in their existing owner-controlled stores. They are not alternate source repositories.
- Local and cloud are host adapters for one implementation. Do not create a second loop implementation in another checkout or home-directory skill tree.

## Finish and cleanup

- Before integrating, verify the tests on the tree being integrated and confirm the base branch. Push the named branch and use the repository's normal PR or merge path.
- Keep a worktree while an open PR may still receive fixes. After its work is integrated, verify the merged commit, no unique uncommitted files, no active process or lease, and remove that exact worktree without force. Prune its Git registration and read it back.
- Never delete a worktree, branch, repository, or runtime directory based only on age, name or lock state. Classify its owner, dirty state, integration state and runtime use first.

## Safety

- Never expose credentials or private data in source, logs, commits or chat.
- In a remote session, do not issue launchd commands that reach `gui/$UID`; identify the exact call path first. For an allowed macOS launchd mutation by the normal owner, use the repository's `bin/launchctl-safe`; if its preflight fails, stop and follow the documented recovery runbook. Do not use Terminal or AppleScript as a bypass.
- Do not restart, replace or create a competing production owner while another owner is active. Inspect the loaded immutable release and state before changing an operational path.
