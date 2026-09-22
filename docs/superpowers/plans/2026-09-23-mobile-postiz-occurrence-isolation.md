# Mobile Postiz Occurrence Isolation Plan

## Outcome

Restore naturally scheduled Mobile/Postiz publishing without deleting or guessing the 17 historical unknown effects. A failed slot remains inspectable, a different slot can continue, and the same unknown occurrence cannot be replayed.

## Scope

- Change shared host admission and its runner wiring only as required for the canonical Mobile entrypoint.
- Update the Mobile recovery spec and focused tests.
- Do not modify Paid fulfillment, Paid state, Paid owners, `config/loop-registry.json`, `apps/life-manager/config/product-loop-catalog.json`, destination mappings, cadence, provider sessions or OBOU.

## Implementation

1. Add failing admission tests for an explicit `occurrence` effect scope:
   - default owner remains blocked by any old unknown;
   - a different occurrence can queue, reserve and claim while the old unknown remains;
   - the same unknown occurrence remains blocked;
   - reservation dispatch preserves the scope.
2. Persist `effect_scope` in the durable priority/claim contract with a safe `owner` default and migration.
3. Thread `effect_scope=occurrence` from `lm_loop_run` only when the validated registry entry is `effect_class=publish` and its exact entrypoint is `apps/life-manager/scripts/mobile-app`.
4. Migrate the same explicit scope through deploy-time queue rebind so a retained historical unknown cannot block installation of the occurrence-scoped runner. Never alter the unknown row, and keep owner-scoped or claimed non-unknown work fail-closed.
5. Run focused admission and runner tests, then the existing Mobile publication and mapping tests.
6. Run the full Life Manager suite and protected-scope diff checks.
7. Commit and push the source result. Merge only after the scoped source acceptance is green.
8. Build/apply one immutable main-derived release to one naturally due non-OBou Mobile owner, then verify terminal event, exact provider receipt and replay-zero before staged rollout.

## Failure policy

- Never clear historical rows without exact official proof.
- Never treat a process exit or local ledger row as a provider receipt.
- If the canary creates an unknown new effect, keep that occurrence fenced, stop its rollout, and diagnose from its new exact identity without blocking unrelated Mobile owners.

## Current progress

- Complete: initial occurrence-scoped admission, Mobile-only runner wiring, same-occurrence refusal, reservation/requeue/stale-claim preservation, focused/full tests, loop contract, fresh read-only review and PR #5765/main merge `ac2d9b26d1…`.
- Unchanged: 17 historical unknown occurrences (14 released, 3 claimed), Paid scope, registry/catalog, provider sessions and OBOU hold.
- Observed canary gate: latest-main release `87aa9d11…` contains the runner fix; the targeted apply changed nothing and reported `admission rebind refused: effect_unknown`, proving deploy rebind still used owner scope.
- Complete: deploy-rebind regression, 826 runtime tests plus 598 subtests, fresh `ship` review, PR #5767/main merge `3bf95b47…`, exact immutable release and targeted apply event `55cad11137bcadb03f92b5d6` for `life-manager-anicca-jp1-tiktok`. Only this Mobile plist uses the new release; its launchd run count is zero after apply.
- Verified unchanged after apply: all 17 historical Mobile/Honne unknown occurrences, jp1's old unknown, Paid scope, registry/catalog, provider sessions and every other Mobile loaded release.
- Current cursor: wait for the jp1 natural 06:30 JST wake, then require an exact terminal event, official provider receipt and replay-zero before a second Mobile owner is promoted.
