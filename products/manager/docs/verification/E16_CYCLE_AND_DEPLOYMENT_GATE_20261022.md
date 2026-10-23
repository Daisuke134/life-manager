# E16 — historical reference-cycle and deployment-gate record

**2026-10-23 current-state pointer:** The deployment-host blocker below describes the saved 2026-10-22 reference implementation. The actual main runtime now uses the existing Actions owner and Supabase checkpoint. Finance/mental provider commits, independent public-byte readbacks, durable STOP and resume have been observed. The initial scoped rollback was blocked with zero writes; PR8632 repaired the path boundary. A later rollback restored the exact finance bytes, fresh owner resume reported zero writes, and a subsequent new release has public P2. Its first response remains UNKNOWN. Fresh run39909274852 reconciled the saved occurrence and reported NOT_DUE / writes=0 / current_proof_exported=true. The bounded aggregate E16 acceptance is now PASSED; F005/F006/F008/F009 subsequently passed separate technical-P2 acceptance. The broader Manager work remains. See E16_DEPLOYED_ACCEPTANCE_20261023.md. Read [the current execution receipt](E16_CLOUD_EXECUTION_20261023.md) and `../roadmap/tasks.json` before resuming. Do not create a Railway or Mac owner to satisfy this historical gate.

## Saved 2026-10-22 baseline

**Stage remains E16 / DEPLOYMENT_HOST_REQUIRED. Digital Autonomy v0.1 is not deployed.**

The deterministic reference implementation uses existing seven-path release admission/guard, E13 candidate verification, E14 source/scope bindings and E15 journal. The sole supported cycle adapter is explicitly local Git without any remote. Independent served files are separate from the candidate and commit checkout. Every resulting record remains P0/SANDBOX/NOT_MEASURED. The production script is a fail-closed preflight; it cannot install a scheduler, publish, create a host identity or issue a grant.

RED: missing cycle module. GREEN: 10 focused tests cover one scoped commit and independent file readback; next-slot and lost-checkpoint replay-zero; served-byte regression stops new work and restores exact seven old files; unrelated.html survives; missed schedule catches up once; an active flock owner denies another worker; a lost send response keeps write count unknown and reconciles next slot without resending. Remote-bearing Git repositories are rejected as sandboxes. UNKNOWN shadow records retain null values and never promote a policy. The full Python and browser CI results are linked from the E16 attempt in tasks.json.

Single-host flock is held for the whole cycle; no expiry takeover can admit an old in-flight worker. Git expected-parent CAS is still required. This is not a distributed-lock guarantee. Private state must outlive process/release replacement. Sandbox observation records reuse PolicyLearner storage separately from scalar losses; technical verdicts do not create welfare scores or authority. The existing live public collector is unchanged and remains mandatory before public P1/P2 proof; the new sandbox path cannot claim it ran that collector.

## Actual preflight evidence

Managed cloud environment spec revision 8 was read again: running/connected, unrestricted network; capabilities=[], secrets=[], runtime_variables=[], outbound_identities=[]. This establishes source/test connectivity, not a verified persistent production owner/volume or publisher identity. The repository registry contains other existing Life Manager loops; a name/registry row is not loaded runtime identity. No production loop/registry/cadence was modified. The Mac source-boundary guard could not run successfully in this cloud worktree; it was not bypassed.

`python scripts/run_owned_digital_cycle.py --state-store <private-state>` returns exit 2 and DEPLOYMENT_HOST_REQUIRED, deployed=false, proof=P0, human_outcome=NOT_MEASURED. This fail-closed result was actually run. GitHub CI is intentionally not a replacement persistent scheduler.

## Remaining deployment patches and evidence, in order

1. On the canonical owner host, identify the existing loaded immutable release, loop ID, state volume, owner lock and promotion contract. Verify there is no competing active owner. Supply owner-approved standing scope through host configuration, never model output. Do not guess a launchd label or create a duplicate loop.
2. Integrate a production cycle adapter into that existing owner using the original platform publisher and official read-only collector. The current cycle only supports a local sandbox; a production adapter is **not yet implemented**, since its host/identity/persistent-state contract is not available. Preserve original repository/ref/workflow/artifact checks; do not widen SOURCE_REF to this research branch to bypass promotion. Register any actual owner change through the existing registry/loop-contract gate.
3. Through normal PR/main/immutable-release promotion, run browser + fresh source gates, persist the exact intent before send, and allow one seven-path target-CAS canary. Reconcile the official immutable commit/parent and all bodies, independently GET served bytes, and perform replay-zero. Preserve the exact previous bundle and unrelated paths. A fixture verdict cannot fulfill these steps.
4. Verify normal scheduled wake/restart/catch-up on the actual persistent volume. Verify scoped rollback and record exact runtime/source/occurrence/readback evidence. Only then mark E16 PASSED and call Digital Autonomy v0.1 deployed. Keep human outcomes NOT_MEASURED until separately designed field evidence exists.

No paid inference, third-party intervention, production publication, YC submission or human-benefit claim was made in this engineering run.


Additional dispatch-boundary regression: mutating/re-hashing the candidate after assessment originally created a sandbox commit and only failed at reconciliation. The test reproduced that failure. Candidate and rollback baseline bundles are now checked against the **reserved** packet manifests immediately before staging; the regression now commits nothing. The real platform path already validates its exact packet candidate separately.

A read-only check of the existing public service at 11:30 UTC retrieved its manifest and six pages with matching hashes: source `de8656444c132fe2c51b7ed79f007724ce152d2a`, manifest digest `d13b823071723dc2b20b4b6dfb6730bbe99aa9be035b7fee4386676a93dab4bb`. Raw summary: [existing baseline](E16_EXISTING_PUBLIC_BASELINE_20261022.json). This is the pre-existing service, not this branch's E16 deployment; no new commit occurrence or runtime owner is established by that read.


## Later same-day selection update

The user selected cloud execution; authenticated Railway plugin access to the existing life-manager project is now verified. That access is separate from this task environment's direct cloud identity bindings. A fresh inventory still shows one existing service and no volumes; its SUCCESS deployment is not identified as Manager E16. Adopt a dedicated single Python worker and volume, preserving existing services. Actual owner/volume/runtime adapter/deployment proof remain absent, so DEPLOYMENT_HOST_REQUIRED stays correct for the acceptance gate. Mac access is no longer a requested prerequisite. See the [founder execution map](../plans/2026-10-22-manager-founder-execution-map.md) for the current order and extra pending-intent/crash-point tests. The earlier rev8 observation above remains historical, not proof that no connector can access cloud platforms.
