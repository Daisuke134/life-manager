# Mobile Postiz Admission Fence Recovery Design

## Goal

Restore the mobile publishing cadence without losing the one-to-one mapping between a Life Manager occurrence, a Postiz integration, a provider post ID and the published media. An uncertain publish attempt must be reconciled from the provider before that owner can wake again.

## As-is: observed on the current host

- `config/loop-registry.json` contains 18 mobile/Honne loop IDs. Seventeen labels are loaded; `life-manager-anicca-obou-instagram` is intentionally held out as the ebook account and has no installed plist.
- The latest targeted status for the loaded mobile labels reports `host_admission_deferred:resource_effect_unknown` for the publish owners. The loop enters `execute`, then records `effect_status=unknown` and exits without retrying the provider.
- The private admission ledger has one `effect_unknown=1` occurrence for each of the affected mobile/Honne owners: 17 total, 14 released and 3 still claimed. Examples are `life-manager-anicca-main-tiktok:18d611856c9b1058-90754` and `life-manager-honne-ja:18d60ef303ea4b58-65481`. The ledger also has unrelated unknown occurrences; this is a shared host fence, not a Postiz account-map change.
- An earlier readback observed immutable main-derived release `a77c5629…`. A fresh 2026-09-18 readback sees `~/loops/current/RELEASE.json` at immutable release `47b010350d9487e6c16f039c7b91dbbcb93f9ba3`, which contains both canonical mobile trees. Loaded mobile labels still use immutable main-derived releases (`37384185…` for Anicca and most routes, `203bbe88…` for Honne EN, `61036e1e…` for Honne JA).
- Existing video and native-carousel distribution receipts contain account, integration, media/caption hashes, provider ID and `provider_reconciled=true`. Those receipts are useful evidence, but a receipt is not linked to an unknown occurrence unless its effect identity is exact.
- The release reconciler is healthy for its own deterministic lifecycle work, but its `lm-loop reconcile` path swaps immutable release argv; it does not perform provider readback or clear a publish effect fence.

## To-be

1. Every publish occurrence carries or can deterministically recover its exact `effect_key`, `job_id`, product, platform, account, Postiz integration reference and media/caption hashes.
2. Mobile publish owners declare an occurrence-scoped effect contract. An old unknown occurrence remains visible and fenced, but it does not stop a different scheduled occurrence whose inner job has a different exact effect identity.
3. Replaying the same unknown occurrence remains forbidden. A released unknown occurrence can be cleared only by `runtime.host.resource_admission.resolve_unknown_occurrence()` after a provider-owned executor performs fresh official readback with an exact owner, occurrence and provider receipt match.
4. The occurrence-scoped contract is granted only to the canonical `apps/life-manager/scripts/mobile-app` entrypoint with `effect_class=publish`. Merely being a publish or revenue loop never grants it.
5. A failed Mobile occurrence is isolated from later slots, while its exact inner publication job remains protected by the local job/effect key, durable receipt and provider readback contracts.
6. Recovery rolls out one owner at a time, beginning with one naturally due canary. The result distinguishes process exit, runtime terminal status, provider receipt and replay-zero before the next owner is admitted.
7. `config/marketing-destinations.json`, mobile loop IDs, cadence slots, Postiz integration IDs, Paid owner configuration and the OBOU hold remain unchanged by this recovery.
8. Production launchd changes use the existing `lm-loop apply` path against one pushed immutable main-derived release and preserve rollback evidence.

## Invariants

- No direct SQL update, `clear_no_effect_unknown()` call, manual JSON edit or deletion of an effect-bearing fence.
- No historical unknown is relabeled as no-effect merely to unblock an owner.
- No new provider post is created outside a naturally due Mobile slot.
- No cross-family route is accepted: the provider account, integration reference, product, locale, format and content hashes must match the canonical destination contract.
- A provider post ID is authoritative only when the provider adapter's official readback confirms the exact account/integration and content identity.
- Owner-scoped effect loops remain fail-closed; occurrence isolation is not inferred from `effect_class`, priority, domain or owner-name prefixes.
- OBOU remains `ebook-ja` Instagram and stays outside the active mobile daily target set.

## Data flow

```text
unknown occurrence
  -> retain as observable quarantine
  -> enqueue a different natural occurrence under the Mobile occurrence contract
  -> exact inner job/effect identity before provider call
  -> provider-owned official readback
  -> terminal runtime event + provider receipt + replay-zero

historical occurrence
  -> exact proof if it becomes available
  -> resolve_unknown_occurrence (released rows only)
```

## Completion evidence

- The existing 17 historical Mobile/Honne unknown occurrences remain present and unchanged unless exact provider proof later resolves one.
- A unit gate proves that default owners still block, a Mobile occurrence-scoped owner can claim a different occurrence, and the same unknown occurrence cannot be replayed.
- One natural canary produces a terminal event and exact provider receipt. A replay of its exact inner publication job produces provider execution delta zero.
- Targeted `lm-loop status` no longer reports `resource_effect_unknown` for the canary's new occurrence and still reports immutable main-derived release argv. The destination and mobile mapping contract tests remain green.

## Inventory evidence

The first read-only inventory is recorded at `docs/superpowers/evidence/mobile-postiz-admission/mobile-fence-inventory.json`. It contains 17 mobile/Honne unknown occurrences, with 0 exact identities recovered, 14 released rows and 3 claimed rows held. The identity bridge and provider executor now cover future runs; the historical rows remain inconclusive because their exact occurrence identity is absent.

## Implementation evidence

The identity bridge is now in `runtime/loop/lm_loop_run.py`, `runtime/loop/runtime_event.py`, `apps/life-manager/lib/marketing-effect-identity.js`, and the existing video/native-carousel adapters. It records the exact occurrence, runtime run, job/effect key, destination integration, account and content hashes before a provider call, then preserves only validated nonzero-effect sidecars outside scratch. PR #5423 merged at `c947b72dbc7f`; 109 focused Python tests and 37 mobile publication tests pass. The read-only proof gate is in `apps/life-manager/scripts/mobile-postiz-effect-reconcile.py`; PR #5431 merged at `b325a34d5b8e3ca9eaecc396311026d58d0ce399`, with seven reconciler tests passing. The provider-owned executor is `apps/life-manager/scripts/mobile-postiz-provider-reconcile.py`; PR #5453 merged at `23afec79cd640f343e5ac152a4950f90faac4b4d`, with nine executor tests, 106 admission tests and 24 Postiz adapter tests passing. It performs official Postiz post/integration GET readback, separates provider content from local media evidence, and can resolve only an authoritative released row after a fresh proof. It was not run against the live provider; the 17 historical fences remain unchanged.

The occurrence-isolation source gate is pushed at `a82085698e`. Shared admission persists an explicit `effect_scope` with the safe `owner` default; only the canonical Mobile publish entrypoint requests `occurrence`. Tests prove that a different occurrence can reserve and claim while the old unknown remains, the same occurrence stays blocked, and a non-Mobile publish loop keeps owner-wide fencing. Verification passes: 182 shared admission/runner tests, 67 Mobile publication/mapping tests, the complete Life Manager Node suite, 716 runtime tests plus 501 subtests, and the loop contract (`14` catalog loops, `166` registry jobs, `96` mapped jobs, `0` errors). Fresh read-only review finds no material safety or regression issue.

PR #5765 merged at `ac2d9b26d1d808a5f5cca40791c8b15a9e2d8df1`. Latest-main immutable release `87aa9d11fbd8b6eff6cf4bed119635471e037aa8` contains the source gate. The first targeted canary apply correctly made no launchd or provider change: one attempt serialized behind the Paid owner's shared control lock, and the next exposed a remaining deploy-plane mismatch, `admission rebind refused: effect_unknown`. The rebind path still assumed owner-wide effects even though the runner was occurrence-scoped. The follow-up keeps every historical unknown row intact, changes only the canonical Mobile publish queue's persisted `effect_scope`, and leaves claimed non-unknown work plus every default owner fail-closed. A regression test migrates a pre-fix queue with an old unknown and proves that only its different queued occurrence can subsequently claim.

## Current diagnosis and release gate

- Read-only SQLite still finds exactly 17 Mobile/Honne `effect_unknown=1` occurrences: 14 `released` and 3 `claimed`. Their exact identity sidecars do not exist, so none can be truthfully cleared.
- All 17 loaded owners stop before provider execution with `host_admission_deferred:resource_effect_unknown`; OBOU remains intentionally unloaded.
- The failure is the outer host admission granularity, not a current Postiz API or generation failure: one historical occurrence fences every future slot for that owner.
- Mobile's inner runtime already derives slot/content-bound job and effect identities, stores receipts, and refuses a terminal job without a receipt. The outer runtime must preserve those old unknowns while allowing only a distinct occurrence to enter that inner safety boundary.
- Source changes are developed on a latest-main Mobile-only branch. No production state, provider session, Paid fulfillment file, Paid owner, registry entry or OBOU state changes before the focused gates pass.
- The runner source gate is on main and the 17-row readback remains unchanged. The current source cursor is the Mobile-only deploy-rebind follow-up; after its PR/main gate, acceptance returns to the latest-main immutable release, one naturally due non-OBou canary, its exact official provider receipt, and replay-zero before staged rollout.

## Non-goals

- Enabling the held OBOU ebook account.
- Replacing Postiz, changing account IDs, changing cadence, or moving runtime state into the repository.
- Treating all 66 system-wide unknown occurrences as mobile work. Each owner remains separately scoped.
