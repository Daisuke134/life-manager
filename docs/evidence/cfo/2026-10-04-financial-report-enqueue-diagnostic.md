# Financial Report enqueue diagnostic — 2026-10-04

Status: the same-occurrence readback proves an entrypoint failure before enqueue/provider effect. The precise cause is a missing report tenant UID argument; the separate lack of a local PostgreSQL URL is a downstream boundary, not this occurrence's cause. No message was sent by this occurrence.

## Same-occurrence readback

- `life-manager-financial-report` occurrence `life-manager-financial-report:18db38bf3ffccbe8-44180` ran at 2026-10-04 13:21:16 JST on release `1a7a8e2faf1eb34931f05287d846fc036bc9eec0`.
- `lm-loop status --explain` reports `exit_code=1`, `failure_layer=entrypoint`, `error_class=entrypoint_exit_1`, effect class `none`, effect status `not_applicable`, no provider receipt, and next action `reconcile_owner`. The same-occurrence structured event's `error_detail` matches the adapter's required-UID error, not a database connection error.
- No report delivery or external effect is recorded for this occurrence.

## Root cause trace

- `apps/life-manager/lib/runtime-job-store.js` creates its Postgres client from `opts.connectionString`, `LM_RUNTIME_DATABASE_URL`, or `LM_FEEDBACK_DATABASE_URL`; if all are empty it throws `runtime job store unavailable` before the database insert.
- Neither accepted URL key is present in the private Life Manager `.env` or in the loaded financial-report LaunchAgent environment key list. The `.env` has Supabase REST URL/service-role configuration, but this runtime-job store does not consume those names. The current `financial-report-boot.sh` only prepares Node/Python runtime and does not load `.env`; the loaded LaunchAgent environment also contains no database URL. This remains a separate downstream failure if a valid UID lets the command reach Postgres; it did not cause this same occurrence's exit.
- A value-redacted credential SSOT inspection found no record with a recognized database URL/DSN field. No connection URL or credential value is copied here.
- The last 64 KiB of the private stderr log contained 259 enqueue-error lines, all reducing to the same sanitized `runtime job store unavailable` message, but those lines lack a same-occurrence correlation and cannot be attributed to this run. Focused `node --test apps/life-manager/lib/runtime-job-store.test.js apps/life-manager/lib/report-job-adapter.test.js` passes 33/33. These contract tests do not prove that the installed LaunchAgent has the production connection string.

## Same-occurrence tenant-argument trace — 2026-10-04

- The installed LaunchAgent points to `lm-loop-run` with loop ID `life-manager-financial-report` and immutable release `20261004T102016-1a7a8e2f`. The release's `config/loop-registry.json` sets `financial-report-boot.sh` as the entrypoint with zero command arguments.
- The same-occurrence event `loaded_argv_sha256` exactly matches the argv recomputed from that release registry. The boot script invokes `report-job-adapter.js enqueue "$@"`; with zero configured arguments, the adapter receives no `--uid` value. `parseEnqueueArgs` requires `--uid <tenant>`, and the structured event confirms that validation error. No UID value was logged or copied into evidence.
- The pushed candidate branch at HEAD `5befe4538e3f14e140cab375c0a2f79eb9ef9327` also has the same `financial-report-boot.sh` entrypoint and zero registry command arguments. Its Task 1–7 completion markers therefore do not fix this earlier UID-argument failure.
- Therefore the first fix boundary after Issue #6549 approval is to resolve the correct tenant identity/binding and provide it explicitly to the existing report command. Only after that boundary is fixed can the local missing-DB-URL boundary be exercised; the already verified Railway SSH worker is the candidate enqueue runtime.

## Configured tenant binding follow-up — 2026-10-04

- The private local environment contains an `LM_TENANT_UID` key. A read-only Supabase lookup using that configured value as a filter resolved exactly one user row with a syntactically valid email and nonempty wallet and Telegram bindings. The UID, email, wallet, chat ID, and row contents were not logged or copied here.
- A read-only query of `lm_financial_report_receipts` scoped by the same private UID returned five rows, all `sent`; the newest stored daily period is 2026-09-09. Only status, report kind, period, and send timestamp were summarized; no recipient, message ID, hash, or report body was read into the output. These historical receipts are not evidence of a 2026-10-04 delivery.
- The active Financial Report LaunchAgent/loop registry does not pass this configured UID to `financial-report-boot.sh`; the binding lookup therefore does not prove that the same tenant was targeted by the failed occurrence or by any completed queue job. No report setting or delivery was changed.

## Configured tenant FinancialRecord coverage — aggregate only

- A read-only aggregate of `public.lm_financial_records` in the Railway runtime database, filtered by the private configured tenant UID, found `business_cost` rows from provider `api-cost` with verification `unverified` and `personal asset_balance` rows from provider `base-usdc` with verification `verified`.
- No `business_revenue` or `moneytree` personal-bank records exist in this FinancialRecord store for that configured tenant. This is a ledger-coverage result, not evidence of zero business revenue or full settlement/cost coverage.
- No amounts, record IDs, source refs, wallet values, or payloads were copied here; the query performed SELECT aggregation only.

## Same-period queue identity check — read-only

- The installed LaunchAgent interval is 300 seconds. In the deployed `buildFinancialReportJob`, `financialReportRef` includes the exact `nowMs` timestamp, and the job/effect identity hashes that reference.
- A pure in-memory builder check with a synthetic tenant showed identical inputs return the same job ID, but an input five minutes later returns a different job ID and effect key while remaining in the same UTC hour. No UID, database, job queue, or provider was accessed by this check.
- Therefore, after the missing UID is fixed, repeated 5-minute wakes could create distinct queue jobs within one report period. The report receipt may dedupe delivery, but does not dedupe those queue inserts/worker executions. Current UID failure means this potential repeated enqueue was not observed in the failed occurrence.
- Before enabling the owner, require a stable per-period occurrence/idempotency key or a proven one-enqueue-per-period gate; verify scheduler replay-zero and one official receipt for the configured period.

## PostgREST route confirmation — 2026-10-04 14:13 JST

- With the existing service-role configuration, a read-only `GET /rest/v1/lm_runtime_jobs?select=job_id&limit=0` returned HTTP 404 / `PGRST205`; no rows were read or written. `OPTIONS` returned HTTP 200 but does not prove that the table route is present in PostgREST's schema cache.
- At 2026-10-04 14:16 JST, a read-only GET of the live PostgREST OpenAPI document returned HTTP 200 with 122 paths. Filtering path names for `runtime|job|enqueue` found only `/rpc/lm_enqueue_late_telegram_receipt`, which is not a runtime-job enqueue route. No table rows or mutation endpoints were invoked.
- `20260729_runtime_jobs.sql` defines claim/heartbeat/complete/fail/reconcile functions but no generic initial enqueue RPC. `complete_lm_runtime_job_and_enqueue` in `2026-09-11-lm-cloud-citizens.sql` only queues a next job after completing an existing job; it is not an initial enqueue substitute.
- These checks establish that the inspected Supabase REST surface does not expose the generic initial-enqueue route; they do not inspect or disprove the separate Railway Postgres runtime queue. The earlier inference that a new Supabase RPC/schema publication was needed is superseded by the topology follow-up below.

## Runtime queue topology follow-up — 2026-10-04

- An independent read-only architecture review traced the deployed canonical `life-call` and `money-printer-worker` services to source SHA `655b2cf2001ad54ce70cb975910f363091052651`. The worker uses the private Railway Postgres runtime queue and has the `report.financial.telegram` capability. The service named `API` is a separate legacy `anicca-products/apps/api` deployment; it is not evidence of a financial enqueue route in `life-call`.
- At that SHA, `apps/life-manager/lib/runtime-job-store.js` accepts `LM_RUNTIME_DATABASE_URL`, `LM_FEEDBACK_DATABASE_URL`, or an injected query; it does not consume `DATABASE_URL`. `apps/life-manager/scripts/runtime-up.js` exposes `/health` over HTTP and claims/executes jobs through its worker/database path. `financial-report-boot.sh` calls the local adapter, which directly enqueues to Postgres. Its job identity includes `Date.now()`, so a later retry can create a different job ID.
- The least-invasive candidate is a finite Railway SSH remote command pinned to the project/environment/service and run inside the existing worker, keeping the private DB URL off the Mac and avoiding a new public endpoint. Follow-up read-only probes reached the active production instance, returned cwd `/app`, found the adapter at `/app/apps/life-manager/lib/report-job-adapter.js`, observed `LM_RUNTIME_DATABASE_URL` present without reading its value, and ran `SELECT 1` successfully from `/app/apps/life-manager`. A first module-resolution attempt from `/app` failed before SQL; no database request was issued by that attempt.
- A read-only aggregate over `public.lm_runtime_jobs` returned six `completed` and one `dead_letter` job for capability `report.financial.telegram`; aggregate receipt outcomes were four `completed`, three `failed`, and two `reconciled_present`. Tenant IDs, job IDs, provider IDs, and receipt bodies were not read, so these rows cannot be attributed to Dais or called her delivered report. No enqueue or message send occurred.
- The adapter entrypoint is `lib/report-job-adapter.js` (the boot script resolves it as `../lib/report-job-adapter.js`); do not invoke it to test help because its CLI path enqueues. It requires `--uid <tenant>` and uses current time by default. SSH/cwd/path/DB access are now verified; tenant binding, replay contract for the target occurrence, enqueue, natural worker completion, and Telegram receipt remain unverified.
- Before any source/config change or enqueue, satisfy Issue #6549's explicit approval gate. Do not manually enqueue an unbound or unidentified tenant; continue with read-only tenant/receipt correlation and preserve the scheduler/effect fence.

## Safe next boundary

No source change, production config mutation, manual enqueue, or manual send was made because Issue #6549 remains open without the requested approval reaction. A later natural hourly result-report occurrence is documented in the 2026-10-04 follow-up below. The configured tenant is now read-only correlated to Dais's Telegram dialog; the earlier identity uncertainty is resolved. The failed cloud Financial Report occurrence still had no UID, so it cannot be retroactively attributed. Preserve the registered scheduler/effect fence until approval and exact retry identity are established.

## 2026-10-04 recipient and natural report follow-up

- A read-only query of the configured private tenant resolved exactly one `lm_users` row. Its Telegram chat binding matches Dais's existing MTProto dialog; its email and agent-wallet bindings are nonempty. No UID, email, chat ID, or wallet was emitted or stored.
- The `life-manager-cfo-hourly` LaunchAgent's UID and Telegram destination hashes match this tenant. Successful natural occurrence `life-manager-cfo-hourly:18db3e094c4fa948-95818` reached report phase at 2026-10-04 14:58:39 JST with exit 0. The same occurrence's report state is `sent`, period `2026-10-04:05`, channel Telegram, with a valid message hash; the shared Telegram outbox row is `delivered` and matches that state.
- A read-only MTProto fetch of the bot dialog found exactly one full-body match for the stored 1,205-character report at 14:58:34 JST, 23 seconds after the local send timestamp. It reported historical/trailing revenue, cost-complete net/cost, MRR, runway, and bank deposit as `未確認`; it did not provide actual financial totals.
- The Bot API provider ID stored by the outbox differs from the MTProto history message ID by 2,588. The full body, destination hash, and adjacent timestamps correlate the delivery, but the cross-API ID mapping is not established. The owner event's `provider_receipt_id` is null despite the local outbox receipt, so receipt propagation into loop telemetry remains incomplete.
- The local result-report configuration is Telegram with hourly default cadence because `LM_CFO_REPORT_CADENCE` is unset; the matching `lm_users` preference row says email/hourly. These are separate settings/paths, not proof of a unified daily CFO report. The separate `life-manager-financial-report` LaunchAgent still has no UID argument or tenant env; its receipt table has five sent rows, latest daily period 2026-09-09 and latest weekly period end 2026-07-27. `lm_cfo_result_receipts` has one sent email row for period `2026-10-02:09`.
- The next natural `life-manager-cfo-hourly` attempt `life-manager-cfo-hourly:18db41414afe61e8-9360` at 15:57 JST exited 75 at `resource_capacity_busy` before provider effect, with no receipt. No manual wake, enqueue, or resend was performed. Issue #6549 remains OPEN with zero comments/reactions, so source/config changes remain gated.
