# Browser installation protection

Approved scope: source-only fix for the two default browser installation roots
verified by the retained 2026-10-11T13:51:23Z cleanup receipt. This plan is not
another state/TODO authority; the unified SSOT remains authoritative.

Base: eea5a355722c59af70ce37671b87bc224a8280b3 (origin/main at creation).
Branch: fix/protect-camoufox-installations-20261011.

## Boundaries

- Protect Library/Caches/camoufox and .cache/life-manager/camofox-browser
  beneath the governor's home, including descendants.
- Reuse HostDiskGovernor._protected's existing prefix protection and remove
  these roots from EXACT_CACHE_ROOTS, hence from candidate discovery and
  whole-tree reclamation. Precedent: skills/self/healthcheck-lib.sh keeps the SDK.
- Do not change thresholds, schedules, daemon configuration, other cache policy,
  provider state, credentials, receipts, releases, or worktrees.
- Never run cleanup, delete data, reinstall, launch a browser, or alter processes.
- PR #7623 owns host inventory and its tests; leave those files alone.
  Open PR #3445 touches the same cleanup/test files for release retention but
  does not implement this browser protection. Preserve its independent policy.

## Task 1: regression and minimal fix

1. Replace obsolete browser-deletion expectations with read-only tests using
   real default paths and the pinned commit from camofox-browser/fetch.sh.
2. Run python3 -B skills/self/disk-cleanup/tests/test_browser_installation_protection.py.
   Expected before production edit: the two installation-root checks fail;
   the unrelated runtime-cache check passes.
3. Remove only the two browser roots from the exact-cache allowlist and add
   both to the existing protected-root set.
4. Repeat the command. Expected: three passing checks.
5. Validate the real retained receipt's reclaimed paths against _protected
   and removed allowlist owners; compile changed Python source in memory and
   run git diff --check. Expected: protected paths, absent owners, no errors.

## Task 2: review and handoff

Review the entire diff locally, then obtain one independent read-only Sol review.
Commit and push the named branch and open a draft PR. Verify the remote head.
Keep the worktree/lease for PR fixes; do not merge, deploy, apply, or delete it.

## Rulings and limitations

- User forbids synthetic data, mocks, and cleanup execution. The existing broad
  cleanup suite creates fixtures and deletes them, so do not run it for this task.
  Use standalone real-path checks, the retained receipt, and static/syntax checks.
  Cost: destructive integration behavior is not exercised here.
- User forbids deletion; retain the private verification ledger and all evidence.
- No product-loop contract/entrypoint changes are made. Runtime recovery and the
  cause of the contemporaneous Reddit timeout remain unverified.
