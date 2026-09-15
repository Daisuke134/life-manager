# Common loop contracts

These wire contracts are the boundary shared by local JSONL/SQLite and cloud Postgres adapters.
They do not choose a storage engine and do not move an existing database.

- Scheduler declaration: `runtime/loop/loop.schema.json`
- Runtime work item: `runtime/contracts/common-record.schema.json#/$defs/Job`
- Typed run lifecycle: `runtime/contracts/common-record.schema.json#/$defs/RunState`
- Durable retry entry: `runtime/contracts/common-record.schema.json#/$defs/RetryEntry`
- Host/browser pressure snapshot: `runtime/contracts/common-record.schema.json#/$defs/HostPressure`
- Runtime event: `runtime/contracts/common-record.schema.json#/$defs/RuntimeEvent`
- External effect: `#/$defs/Effect`
- Verified receipt: `#/$defs/Receipt`
- Durable notification outbox item: `#/$defs/OutboxItem`
- Financial Manager ledger record: `#/$defs/FinancialRecord`
- Browser target lease: `#/$defs/BrowserTargetLease`
- Launch identity: `runtime/loop/release_identity.py` verifies the immutable release manifest,
  Loop/owner/resource environment, private state boundary, and current release before an effect
  child starts; stale effect-bearing releases fail closed as `release_drift`.

An entrypoint exit proves only a runtime event. An external effect becomes true only through a
provider-backed `Receipt`. Outbox delivery uses `message_key` as its retry identity. Financial
records keep non-negative minor-unit amounts; `direction` carries the sign, while `scope` and
`kind` prevent a personal balance, internal transfer, business revenue, cost, and payout from being
silently aggregated as the same thing. `verification.status=verified` requires evidence references.
Run state keeps lifecycle truth (queued, running, retry, deferred, human wait, terminal) separate
from effect/readback truth (not applicable, planned, started, verified, failed, reconciled, unknown);
`unknown` is never promoted to success. A retry entry carries the next attempt, due time, failure
layer, and idempotency key without copying provider payloads.
`HostPressure` contains only bounded memory, swap, load, wake, browser-process, and endpoint counts;
it is an admission signal, not a provider receipt and never includes PIDs, URLs, or credentials.
Finite wakes also check writable data-volume headroom before starting a child; below the configured
floor they persist a deferred `disk_headroom_low`/`disk_headroom_unavailable` receipt and resume from
the same durable queue position.
Runtime events may also carry `product_loop_id`, `job_id`, `owner_id`, `wake_id`, `attempt`,
`effect_key`, `failure_layer`, `official_readback_ref`, `next_eligible_at`, `entrypoint`,
`resource_class`, and a `state_root_sha256` (hash only). These optional identity fields are emitted
by the current builders so older event rows remain readable while the runtime migrates to the full
join key without exporting a private state path.
Every FinancialRecord identity is deterministic:
`record_id = "financial:" + sha256_utf8(subject_id + "\n" + idempotency_key)`.
The JSON Schema enforces the resulting shape; `projectFinancialRecord` enforces this cross-field
hash invariant before either local or cloud persistence.

`BrowserTargetLease` is the portable record shape, not an authorization validator. The runtime
adapter must also verify that the target ID matches the WebSocket path, timestamps are ordered,
the CDP origin and provider URL are allowed, credentials are absent, and the owner token plus
generation still match current storage before any heartbeat, mutation, close, or release.
Connector's adapter is the first implementation of those operational checks; Gig and Job Hunter
follow only after their live target ownership is read back.

Existing domain rows remain in their current files and databases. ARCH-08 adapters translate them
to these records at read/write boundaries; they must not rewrite historical evidence in place.
An outbox row in `delivery_uncertain` is never blindly returned to `pending`; a provider readback
must reconcile it to delivered or a safe retry decision.
