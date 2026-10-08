# Coconala Paid decision profile-lock recovery

## Goal

Keep the `paid-work-decision` stage from waiting 15 minutes on a busy Codex profile, release the Coconala browser lease while that provider-independent decision runs, and reuse exact legacy cached decisions so a route change cannot reopen completed remote work. Preserve the current model and read-only decision contract; leave other review and generic agent routes unchanged.

## Steps

1. Add failing tests for a `paid-decision-agent` fast-fail route, reuse of a hash-bound legacy `escalation-agent` decision cache, fresh-run proof requiring the new task class, and browser-lease yield around `paid-work-decision`.
2. Route only `paid-work-decision` through the new Codex class with `fail_fast_provider_lease=true`; keep other Paid review tasks on `escalation-agent`.
3. Preserve the existing path-specific cache contract: standard cache requires prompt/schema/compiled-context/source-input/policy digests; stable cache may ignore compiled-context churn but revalidates schema/source-input/policy, current requirements/identities, summary/result hashes, and the decision output. Permit the legacy class only in cache reads; fresh runs require the new class.
4. Wrap the model-only decision call in `_yield_registered_browser_lease()`.
5. Run the focused Paid, browser-yield, and agent-runner route tests, plus `git diff --check` and `scripts/verify-source-boundary.sh`.
6. Push the latest-main branch, obtain source review/required CI, then merge. Apply to the Paid owner only after its current natural run releases the project lock; verify loaded SHA and the next natural official readback before any buyer-facing action.
