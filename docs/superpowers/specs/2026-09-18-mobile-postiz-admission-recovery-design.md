# Mobile Postiz Admission Fence Recovery Design

## Goal

Restore the mobile publishing cadence without losing the one-to-one mapping between a Life Manager occurrence, a Postiz integration, a provider post ID and the published media. An uncertain publish attempt must be reconciled from the provider before that owner can wake again.

## As-is: observed on the current host

- `config/loop-registry.json` contains 18 mobile/Honne loop IDs. Seventeen labels are loaded; `life-manager-anicca-obou-instagram` is intentionally held out as the ebook account and has no installed plist.
- The latest targeted status for the loaded mobile labels reports `host_admission_deferred:resource_effect_unknown` for the publish owners. The loop enters `execute`, then records `effect_status=unknown` and exits without retrying the provider.
- The private admission ledger has one `effect_unknown=1` occurrence for each of the affected mobile/Honne owners: 17 total, 14 released and 3 still claimed. Examples are `life-manager-anicca-main-tiktok:18d611856c9b1058-90754` and `life-manager-honne-ja:18d60ef303ea4b58-65481`. The ledger also has unrelated unknown occurrences; this is a shared host fence, not a Postiz account-map change.
- The current release is immutable and main-derived (`a77c5629…`). Loaded mobile labels use immutable main-derived releases (`37384185…` for Anicca and most routes, `203bbe88…` for Honne EN, `61036e1e…` for Honne JA). The migrated canonical mobile trees exist in the `37384185…` release.
- Existing video and native-carousel distribution receipts contain account, integration, media/caption hashes, provider ID and `provider_reconciled=true`. Those receipts are useful evidence, but a receipt is not linked to an unknown occurrence unless its effect identity is exact.
- The release reconciler is healthy for its own deterministic lifecycle work, but its `lm-loop reconcile` path swaps immutable release argv; it does not perform provider readback or clear a publish effect fence.

## To-be

1. Every publish occurrence carries or can deterministically recover its exact `effect_key`, `job_id`, product, platform, account, Postiz integration reference and media/caption hashes.
2. A released unknown occurrence is eventually cleared only by `runtime.host.resource_admission.resolve_unknown_occurrence()` after a provider-owned executor performs fresh official readback with a proof whose `owner_id` and `occurrence_id` match and whose provider receipt is exact and reconciled. The checked-in proof gate never clears state.
3. A claimed unknown occurrence stays fenced. Missing local summaries, a provider dashboard draft, a planned job, a browser URL, or a non-exact receipt never authorizes a retry.
4. Reconciliation runs one owner at a time, then allows one natural scheduled wake. The result must distinguish process exit, runtime terminal status, provider receipt and replay-zero.
5. `config/marketing-destinations.json`, mobile loop IDs, cadence slots, Postiz integration IDs and the OBOU hold remain unchanged by this recovery.
6. Production launchd changes, if required after fence recovery, use the existing `lm-loop apply` path against one pushed immutable release and preserve rollback evidence.

## Invariants

- No direct SQL update, `clear_no_effect_unknown()` call, manual JSON edit or deletion of an effect-bearing fence.
- No new provider post is created merely to test recovery.
- No cross-family route is accepted: the provider account, integration reference, product, locale, format and content hashes must match the canonical destination contract.
- A provider post ID is authoritative only when the provider adapter's official readback confirms the exact account/integration and content identity.
- OBOU remains `ebook-ja` Instagram and stays outside the active mobile daily target set.

## Data flow

```text
unknown occurrence
  -> exact run/effect identity
  -> provider-owned official readback
  -> exact proof (or held/inconclusive)
  -> resolve_unknown_occurrence (released rows only)
  -> one natural wake
  -> terminal runtime event + provider receipt + replay-zero
```

## Completion evidence

- A redacted reconciliation ledger lists every mobile/Honne unknown occurrence and one of `ready`, `inconclusive` or `claimed-held`, with no guessed mapping. `ready` is a precondition for a fresh provider-owned readback, not a state mutation.
- Verified rows have the exact provider receipt ID and official account/integration/content readback; the admission ledger shows `effect_unknown=0` only for those rows.
- One natural wake per verified owner produces a terminal event. If the effect already exists, provider execution delta is zero; if it does not, the single new execution has an official receipt. Duplicate executions are zero.
- Targeted `lm-loop status` shows no `resource_effect_unknown` for the reconciled owner and still reports the immutable release argv. The destination and mobile mapping contract tests remain green.

## Inventory evidence

The first read-only inventory is recorded at `docs/superpowers/evidence/mobile-postiz-admission/mobile-fence-inventory.json`. It contains 17 mobile/Honne unknown occurrences, with 0 exact identities recovered, 14 released rows and 3 claimed rows held. The current runtime event format does not carry the occurrence's `effect_key`/`job_id` or the provider account identity, so every row remains inconclusive until the identity bridge and official readback are implemented.

## Implementation evidence

The identity bridge is now in `runtime/loop/lm_loop_run.py`, `runtime/loop/runtime_event.py`, `apps/life-manager/lib/marketing-effect-identity.js`, and the existing video/native-carousel adapters. It records the exact occurrence, runtime run, job/effect key, destination integration, account and content hashes before a provider call, then preserves only validated nonzero-effect sidecars outside scratch. PR #5423 merged at `c947b72dbc7f`; 109 relevant Python tests and 37 mobile publication tests pass. The read-only proof gate is in `apps/life-manager/scripts/mobile-postiz-effect-reconcile.py` (PR #5431 pending). This changes future evidence quality only; it does not clear the 17 historical fences.

## Non-goals

- Enabling the held OBOU ebook account.
- Replacing Postiz, changing account IDs, changing cadence, or moving runtime state into the repository.
- Treating all 66 system-wide unknown occurrences as mobile work. Each owner remains separately scoped.
