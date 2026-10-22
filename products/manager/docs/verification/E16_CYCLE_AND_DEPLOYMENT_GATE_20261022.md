# E16 — reference cycle verified; production deployment blocked

**Stage remains E16 / DEPLOYMENT_HOST_REQUIRED. Digital Autonomy v0.1 is not deployed.**

The deterministic reference implementation uses existing seven-path release admission/guard, E13 candidate verification, E14 source/scope bindings and E15 journal. The sole supported cycle adapter is explicitly local Git without any remote. Independent served files are separate from the candidate and commit checkout. Every resulting record remains P0/SANDBOX/NOT_MEASURED. The production script is a fail-closed preflight; it cannot install a scheduler, publish, create a host identity or issue a grant.

RED: missing cycle module. GREEN: 9 focused tests cover one scoped commit and independent file readback; next-slot and lost-checkpoint replay-zero; served-byte regression stops new work and restores exact seven old files; unrelated.html survives; missed schedule catches up once; an active flock owner denies another worker; a lost send response keeps write count unknown and reconciles next slot without resending. Remote-bearing Git repositories are rejected as sandboxes. UNKNOWN shadow records retain null values and never promote a policy. The full Python and browser CI results are linked from the E16 attempt in tasks.json.

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
