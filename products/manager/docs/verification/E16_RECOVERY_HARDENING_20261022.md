# E16 recovery hardening — source implementation receipt

2026-10-22 UTC. The user continued the existing goal with “finish it until the end”. This receipt records concrete source/test work after the full-roadmap update, not production completion. Task authority remains `docs/roadmap/tasks.json`:69 done/41 todo/3 skipped; E16 is still the current incomplete technical gate.

## Implemented boundaries

1. **PATCH-01:** drain saved uncertain owned intents before cadence, stop or new-candidate preparation. Bounded ordered batches preserve packet/original parent; unresolved or unscanned work blocks new sends. Scope expiration/revocation and candidate-source changes cannot hide old occurrences. A stale new baseline is NO_ACTION, not permission to overwrite the recovered target.
2. **PATCH-02:** public `dispatch_owned_once` preserves owner lock, pending recovery, stop and current scope/assessment. Its shared locked body performs fresh lookup/admission/reservation/send without returning reusable dispatch permission. The cycle uses that body without a second flock. Existing correct slot-claim semantics are preserved: a recorded tick is not a completed effect.
3. **PATCH-04:** fixed-origin provider pagination and exact immutable seven-file/parent collection reuse the original publisher GET/validator. Commit PRESENT is separate from delivery. Pending PRESENT rows are independently observed before cadence and planning. Lag, timeout, missing files and hash-only mismatch do not trigger resend or rollback. Public mismatch alone never establishes deployment-bound regression. Sandbox rollback additionally requires a fixture-only completed-deployment binding, actual failure of the fixed HTML/CSP rubric, and exact current commit CAS; it remains P0. A sibling target advance blocks rollback. Historical delivery verification is preserved separately from current live state.
4. **Development probe:** `scripts/compare_owned_runtime.py` is a portable offline comparison CLI, not a production workflow engine. `--backend current` needs no DBOS dependency. It uses existing local-Git fixtures, explicit JSON reconstruction, separate child processes, fixed source snapshots, bounded deadlines and durable send-entry counters. It rejects source-tree state. Optional DBOS runs use portable JSON workflow serialization and the audited Git pin below. No core dependency was added.

## Actual runtime comparison

The integrated CLI ran **16/16 cases, failure0**, against the same fixed source content: six crash points plus fresh engine metadata and shortened multi-stage wait, each with current and DBOS. Counts measure send attempts separately from Git target advances. Every crash restart made zero additional sends; the slot-claim case performs its first send only on the next eligible slot. Reservation-before-send stays UNKNOWN with zero sends.

[Condensed result, source hashes and dependencies](E16_RUNTIME_COMPARISON_20261022.json). The local source snapshot is `46fa9cda3b23e373d80a201d14b6b1f9174f3131`; all five changed behavioral source hashes are recorded so later remote commit metadata cannot obscure the tested bytes. Raw private fixture/SQLite/process artifacts are session-local under `/workspace/scratch/e16-reviewed-runtime-comparison-20261022/`.

Audited optional source: `dbos @ git+https://github.com/dbos-inc/dbos-transact-py.git@e63ee714e031287c9b3447a173be835d6eaf1f95`. The actual isolated build resolved **3.4.0a4**, not3.3.0. MIT SDK source and its dependencies were installed only in `/workspace/scratch/e16-dbos-probe-venv`; production dependencies/lockfiles remain unchanged.

Reproduction from `products/manager`, using a fresh state directory outside source:

```sh
python scripts/compare_owned_runtime.py --backend current --case checkpoint_loss --state-dir /tmp/new-manager-current-probe
# With the exact optional DBOS pin installed in an isolated interpreter:
python scripts/compare_owned_runtime.py --backend both --case all --state-dir /tmp/new-manager-runtime-comparison
```

DBOS preserved recorded steps and the absolute wake deadline after a2-second test wait. That demonstrates bounded recovery behavior, not production-duration waiting, availability or lower cost. Both backends still need authority/journal/CAS/readback. The comparison does not demonstrate production recovery-code removal or operating-cost reduction, so **retain the current single-worker; DBOS production adoption remains UNDECIDED**. Reassess if actual multi-stage/long-wait workload and host/backup measurements justify delegation. This is a measured comparison, not proof the current runtime is universally best.

## Verification

- Baseline661 tests OK(skipped=5). One initial invocation used repository root instead of `products/manager`, causing79 import-loader errors; the correct documented cwd passed before edits.
- PATCH-01: RED exposed missing batch API, hidden prior occurrence and an actual second send under a changed candidate; GREEN5 tests, full suite666 OK(skipped=5).
- PATCH-02: RED4 missing-helper failures; slot-crash semantics were already correct and are recorded as preserved behavior. GREEN5 tests, suite671 OK(skipped=5).
- PATCH-04: RED reproduced unwanted lag/missing/hash-only rollback and sibling-target rollback plus missing collector; GREEN6 tests with extra timeout/old-version/exact-delivery fixture coverage, suite677 OK(skipped=5).
- Portable probe CLI: RED2 failures before the script existed; GREEN2. Final local suite **684 tests, OK(skipped=5)**. Optional DBOS actual16-case run is separate from the stdlib-only suite.
- Product boundary and roadmap113 checks pass. Original task ledger byte content, E cursor and completed prefix are unchanged. No new task authority, dependency, provider trial or welfare/revenue result was invented.
- Negative production preflight returned exit2 / `DEPLOYMENT_HOST_REQUIRED`, writes0, deployed=false. This is fail-closed development evidence, not a production dry-run pass or canary.

Using-superpowers, executing-plans, test-driven-development, using-git-worktrees, dispatching-parallel-agents and the repository loop-development guidance were read. Astra Advisor was not exposed; inline implementation plus a fresh read-only final review is used. Skill helper files unavailable through the cloud resource interface were replaced by a plan-scoped ignored execution ledger and actual commands. The canonical worktree/remote were verified and its task lease acquired. The Mac source guard remains exit2 because its canonical host root is absent; it was neither passed nor bypassed. Existing cloud source authorization applies; runtime authority is separate.

## Observed production prerequisites

Fresh authenticated Railway reads show the existing life-manager project with one existing service, no volumes, no variables and no staged changes. Its old SUCCESS deployment is not a Manager E16 worker. Existing service, credentials and infrastructure were preserved. The cloud development environment has no configured runtime secret/outbound identity, which does not negate connector access.

The next production work is PATCH-05/06: versioned main-SHA admission with legacy-v1 read compatibility; a real worker-to-privileged-publisher bridge; dedicated persistent worker/volume and verified backup/restore; secure delivery of a machine credential with the required minimum permissions; an observed hosting cost/stop boundary; then reviewed main promotion and one real scoped canary/readback/replay-zero/restart/rollback. The current research branch must not be added to the live source allowlist. Do not demand Mac host details or recreate a generic scheduler.

Existing authorization for owned digital publication is retained: no new per-run human approval is introduced. What remains unavailable is a verified machine-credential delivery path and an observed hosting spend/stop cap, not user permission to keep implementing source. Never ask for secret values in chat/Git. Real canary, deployed status, human benefit, paid customers, revenue, applications and YC admission all remain unverified.

## Independent review and one fix pass

Fresh-context reviewer (`gpt-6.1-sol`, high) found **2 Blocking /0 Nit /0 Pre-existing**. Both were reproduced and fixed in one pass; no new whole-change review was requested.

- Recovery starvation: persist separate occurrence/delivery scan cursors, cycle through bounded100-record batches, continue delivery reads despite an unrelated UNKNOWN occurrence, and keep every new write/rollback blocked while occurrence uncertainty remains. UNKNOWN rows are never cleared by cursor movement. New102-record and mixed-queue tests failed first, then passed; STOPPED remains read-only.
- Delayed valid packet: reproduce a1-second delay being rejected, then reconstruct immutable bindings with the original creation time while checking fresh scope/assessment and admitting the original lease at the actual current time. Expiry is not renewed. The new delay test failed first, then passed; the original-expiry test preserves an already-correct rejection.

After the fix pass, the full suite ran684 OK(skipped=5) and the actual integrated16-case current/DBOS comparison was rerun against the fixed committed core. Result hashes above identify the fixed tree. **0 unresolved Blocking /0 deferred nits**. Original review findings and exact reproductions are preserved in [review history](E16_RECOVERY_REVIEW_20261022.md).

Rulings: unavailable skill helper automation was replaced with the plan-scoped ledger (bookkeeping risk only); stale baselines return NO_ACTION (one delayed planning wake); the public locked helper and cycle share a private locked body (nested-lock failure avoided); public hash mismatch stays UNKNOWN without deployment-bound rubric failure (possible delay pending evidence); historical delivery is separate from current state; unimplemented live/restore/publication tasks remain incomplete; sandbox API construction does not grant production authority. DBOS remains optional/undecided until it demonstrates useful production simplification. No review nit was deferred.

Remote readback/CI identities are recorded in the PR after publication. Keep this worktree while the draft PR is open. No production deployment, merge, external publication, outreach, job/YC submission, payment or human study occurred in this update.

## 2026-10-25 — local owner-state backup and restore hardening

Added `manager_core/state_recovery.py` and `scripts/backup_owned_cycle.py` for consistent SQLite online backups, an integrity/hash manifest, verification, and restore into a new isolated directory. Backup refuses a busy owner lock and source-tree/live-state overlap. Restore never overwrites an existing directory; it writes `RESTORE_RECONCILIATION_REQUIRED.json`, and both `run_owned_cycle` and the direct dispatch helper now fail closed on restored state. The cycle CLI returns exit 2 for that quarantine. The SHA-256 digest detects accidental changes only; this is not a signed backup format or a production recovery credential.

TDD evidence: `python3 -m unittest discover -s tests -p 'test_owned_state_recovery.py' -v` first failed because dispatch still accepted restored state (`NOT_DUE` instead of `RESTORE_RECONCILIATION_REQUIRED`), then passed all 3 recovery tests after the guard was added. Tests cover active-owner refusal, modified database rejection, source-tree separation, no-overwrite restore, quarantine, and zero sandbox commits from restored state.

This is local recovery plumbing only. No Railway service/volume was created, no existing service changed, and no production restore/restart was run. A production host adapter, immutable source/owner bridge, volume-backed drill, and official external reconcile/marker-release procedure remain required before E16 acceptance. The original task ledger and E16 cursor are unchanged.
