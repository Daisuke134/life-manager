# Mobile metrics readback — 2026-10-03

Status: `partial` / fail-closed.

## Tooling and source status

- Rork `asc` installed after checksum verification: `5.9.2`.
- `asc auth status --validate`: credentials resolve, but App Store Connect API access is blocked by `required agreement missing or expired`.
- `asc apps list`: same account-wide agreement blocker; no app acquisition report is claimed from this run.
- RevenueCat daily snapshots are available in `~/.local/state/life-manager/marketing-metrics-daily/state/business-outcomes.jsonl`.
- Latest local rows are for `2026-10-02`, observed `2026-10-03`.

## Latest RevenueCat observations

| product | MRR | active | new customers | 7-day paid conversion | daily revenue |
|---|---:|---:|---:|---:|---:|
| anicca-ios | USD 20.34 | 5 | 1 | 0% | USD 0 |
| honne-ai | USD 0 | 0 | 1 | 0% | USD 0 |

These are RevenueCat observations, not App Store settled proceeds. ASC acquisition/proceeds and campaign attribution remain unavailable until the Account Holder accepts the required App Store Connect agreement and the readback is rerun.
