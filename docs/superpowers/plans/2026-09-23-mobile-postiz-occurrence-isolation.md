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
4. Run focused admission and runner tests, then the existing Mobile publication and mapping tests.
5. Run the full Life Manager suite and protected-scope diff checks.
6. Commit and push the source result. Merge only after the scoped source acceptance is green.
7. Build/apply one immutable main-derived release to one naturally due non-OBou Mobile owner, then verify terminal event, exact provider receipt and replay-zero before staged rollout.

## Failure policy

- Never clear historical rows without exact official proof.
- Never treat a process exit or local ledger row as a provider receipt.
- If the canary creates an unknown new effect, keep that occurrence fenced, stop its rollout, and diagnose from its new exact identity without blocking unrelated Mobile owners.

## Current progress

- Complete: explicit occurrence-scoped admission, Mobile-only runner wiring, same-occurrence refusal, reservation/requeue/stale-claim preservation, focused/full tests, loop contract and fresh read-only review.
- Unchanged: 17 historical unknown occurrences (14 released, 3 claimed), Paid scope, registry/catalog, provider sessions and OBOU hold.
- Current cursor: PR/main integration, then one immutable-release natural canary, exact official receipt and replay-zero.
