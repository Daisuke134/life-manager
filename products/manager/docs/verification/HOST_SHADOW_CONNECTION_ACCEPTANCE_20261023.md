# Prepared shadow host connection — source acceptance

2026-10-23 UTC. [PR8741](https://github.com/Daisuke134/life-manager/pull/8741) merged normally through `bin/merge-when-green 8741 --squash`; accepted main commit `c0d86ff82ec81dfbd60d3763a208de5970530a40`, reviewed feature head `857fc3fa7b4f296a8c6b262d8280b65acd426eac`. No admin/force merge. Other owners' concurrent main changes were preserved.

## Accepted behavior

The existing host compares its exact prepared candidate after existing recovery/STOP/cadence gates, using the same checkpoint. CLI configuration is inert; saved results/uncertain intent retain replay ordering. Default/scheduled/control/preflight comparison stays OFF. Only explicit dispatch/run-once/true admits the SDK install and cycle-step key; money stays blank unless explicitly configured. Advice cannot change candidate bytes or publisher admission.

The comparison bound only decreases: at most120seconds from CLI entry, with120seconds reserved inside the existing host/scope windows; SDK timeout30seconds. Clients are closed in finally on comparison exits. Only the accepted nested19-key P0 projection is public. The existing owner, publisher, concurrency, scope and checkpoint fences remain authoritative. See [design](../plans/2026-10-23-host-shadow-connection-design.md) and [completed source plan](../plans/2026-10-23-host-shadow-connection.md).

## Verified evidence

- Actual RED→GREEN per task; final focused230/full449 tests,0skips. Three independent task reviews and fresh Astra whole-branch review:0findings, spec/quality approved.
- All16 PR checks terminal:15success,1expected `publish-owned-prefix` skip,0failures. [Security Scan](https://github.com/Daisuke134/life-manager/actions/runs/39978822090), [Manager verification](https://github.com/Daisuke134/life-manager/actions/runs/39978821852) and [checkpoint contract](https://github.com/Daisuke134/life-manager/actions/runs/39978821886) all succeeded. Actual2top-level comments/0inline/0review submissions were read; Codex completed with0findings. CodeRabbit explicitly skipped its review and was not counted as substantive approval.
- Exact accepted main bytes for8source/test/workflow/deployment-doc paths plus2plans were copied into research commit `5018a30938acf9f8cb18daf8cb986ac4fdc26aae`. All8 prior research blobs matched the accepted pre-feature main baseline; research-specific INTIMA, README, legacy maintenance fixture, rights, registry and other lanes were preserved. This is a source copy, not an ancestry claim for a squash merge.
- Research local full1025tests/5skipped passed. Fresh synchronization review:0findings/spec PASS/quality Approved. [Official research run39980993977](https://github.com/Daisuke134/life-manager/actions/runs/39980993977) at exact `5018a30938acf9f8cb18daf8cb986ac4fdc26aae`: full999tests/6skipped,0failures/errors; separate focused6 and21. All1job/10steps succeeded. The reason for the local/official count difference remains unestablished. Official log31506bytes/SHA256 `def0fc39ea8e0ae7cca956242097b40397f1fb9709d79ac996928f47f362dc1b`.
- Changed-diff secret scans, boundary and diff checks passed. Cloud canonical source guard remains actual FAIL/exit2 because `/home/agent/Projects/life-manager-main` is absent; explicit owner authorization covered this cloud work, with canonical origin/common Git verified. No guard was edited or relabeled PASS.
- The exact integrated feature worktree was removed without force after clean-state, own-lease, no active cwd process,11exact owned blobs and retained Board claim/log checks. Only67generated ignored pyc files were disposable. Its registration and active lease were removed; branch/history/private evidence and every other worktree were retained. Whole-tree equality was not asserted because main had advanced with unrelated changes before squash integration.

## Still separate

This source acceptance does not enable scheduled inference, spend a provider budget, establish live SDK behavior or authorize a new behavioral channel. Live dry-run/canary, an appropriate task and explicit money configuration, independent provider/readback/replay-zero evidence, model usefulness and real human outcomes remain separate gates. `V004` is not completed. Registry remains113IDs:80done/23todo/10skipped.
