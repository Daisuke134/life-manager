# Coconala Paid profile-lock recovery

## Goal

Keep Paid semantic review from waiting 15 minutes on a busy Codex profile, and release the Coconala browser lease while provider-independent review runs. Preserve the current model and read-only decision contract; leave generic agent routes unchanged.

## Steps

1. Add failing contract tests for a Paid-only review task class with fast-fail account fallback, Paid proof validation against that class, and browser-lease release around `paid-work-decision`.
2. Add `paid-review-agent` using the existing Codex primary/fallback profiles and `fail_fast_provider_lease=true`; route Paid review/decision calls through it without changing `escalation-agent`.
3. Wrap the model-only `paid-work-decision` call in the existing `_yield_registered_browser_lease()` context manager.
4. Run the focused Paid, browser-yield, and agent-runner route tests, plus `git diff --check` and `scripts/verify-source-boundary.sh`.
5. Push the latest-main branch, obtain source review/required CI, then merge. Apply to the Paid owner only after its current natural run releases both locks; verify loaded SHA and the next natural official readback before any buyer-facing action.
