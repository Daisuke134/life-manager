# Life Manager project instructions

This repository is the source authority for Life Manager. The canonical remote is
`https://github.com/Daisuke134/life-manager.git`; the normal local checkout is
`/Users/anicca/Projects/life-manager-main`.

## ★ Baked-in operating facts (Dais 2026-09-29 — read before any Life Manager work) ★

1. **One SSOT.** TODO / order / state live only in `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`. Every other spec and `skills/earn/gig/TODO.md` is reference only. Never create another "SSOT".
2. **Copy successful people first.** Every decision (price, model, plans, product idea, marketing format, app, investment) starts from what the top sellers on that platform do, never from our own listings or failures. Capafy market data: `POST /agent/agents/search` with JSON body `{"query":..,"page":1,"pageSize":30}` (1,025-agent sweep in `~/.local/state/life-manager/state/capafy-market-agents-*.json`). Keep this data refreshed continuously.
3. **Charge more, spend less.** Default hosted model = cheap (DeepSeek V4.1 Flash). Price at the successful sellers' band (weekly $9.99-19.99, monthly $19.99-29.99, always a yearly plan). No product may lose money per order.
4. **We are logged in forever. Never log in again.** Browser-to-platform mapping: `~/.config/ai/registry/browsers.toml` (lease with `skills/browser/browser-guard.sh acquire <identity>`). Logins are banked in `~/.cloak/vault/<profile>/auth-state.json` via `skills/browser/scripts/session_vault.py` (`SESSION_VAULT_PORT`, `SESSION_VAULT_DIR`). Read the mapping first. Capafy seller console = identity `coconala:kosuke` (gig-daily-driver). Never touch Dais's Chrome (`interactive:dais`).
5. **Life Manager agents and Claude/Codex are browser-using agents.** If the UI can fix it now (e.g. stop a money leak), look at the real screen and act; do not over-engineer a pipeline for a 2-second fix.
6. **Read the existing loop before describing it.** Writer earns by selling articles (note paywall, Substack paid, aniccaai.com preview+paid); Ebook = monk factory to "The Anicca Reset" via Stripe (Amazon KDP not yet connected); Capafy, apps, PromptBase already exist. Check `skills/<loop>/SKILL.md` and `skills/earn/marketing-engine/registry/products/*.json` first.
7. **Reply to Dais in Japanese only.**

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
- Development and production are separate planes. The worktree owns source edits, focused tests and private fixtures; production owns immutable releases, launchd, admission, browser profiles, credentials and provider effects. Promote only through PR/checks → merged `origin/main` → complete immutable release → targeted loaded-idle apply → natural terminal → official readback → replay-zero. See `docs/agent-engineering/WORKTREE-PROMOTION-CONTRACT.md`.

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
