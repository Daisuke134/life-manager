# Revenue admission floor — implementation complete

This records the replacement of the original 1 GiB proposal. The current implementation was merged to main in PR #7177, merge commit `1fe7db3b634bb910187b846c7246aa7fe0dcba82`.

## Implemented contract

- `priority=critical_paid` defaults to a 256 MiB disk floor.
- `priority=revenue` defaults to a 512 MiB disk floor.
- Other priorities keep the 2 GiB recovery floor.
- `LIFE_MANAGER_DISK_FLOOR_<PRIORITY>_BYTES` can override the configured floor, capped at the shared 2 GiB maximum.
- The existing pre-enqueue and post-claim disk checks still defer a run below its selected floor.
- Global finite-run cap remains 8; no unbounded concurrency or admission schema change was made.

The earlier proposal for a 1 GiB revenue floor and 512 MiB minimum is superseded by the 2026-10-09 instruction to keep shipping while the cleanup owner handles disk capacity.

## Completion boundary

Source is merged in main. Production completion still requires a main-derived immutable release, natural owner runs, installed-release and admission readback, and actual provider outcomes. Until those receipts exist, this plan does not claim that Connector, Job Hunter, or Fundraiser has resumed or earned revenue.

The canonical ordered remaining TODO is in `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`.
