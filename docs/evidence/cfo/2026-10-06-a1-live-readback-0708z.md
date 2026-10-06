# CFO A1 live readback — 2026-10-06T07:08Z

Read-only production capture used to classify A1. This is an estimate-ledger snapshot, not a billing receipt. Raw logs, row IDs, tenant/user IDs, calendar data, and credentials are not retained here.

## Runtime observation

- Railway production service `life-call`: deployment `685f6118-f575-45fe-b47c-0c2cfe4f2d60`, source SHA `0ba957af5405bfbea5f1d6e9ce6ca78deb66b421`, status `RUNNING`.
- The 11 most recent `[wake] scan` lines returned for that deployment span `2026-10-06T06:14:45Z`–`07:05:51Z`. All 11 report `calendar_read_failed=0`; 3 report `due_candidates>0`. A due candidate is not proof that a call completed.

## Cost ledger repeat-read

- Fixed window: `2026-10-06T06:06:20.108Z <= ts < 2026-10-06T07:08:37.097Z`.
- Two identical read-only GETs returned the same 315 row IDs (`Content-Range: 0-314/315`). The ID set itself is not persisted.
- Current release SHA `0ba957af5405bfbea5f1d6e9ce6ca78deb66b421`: 275 rows (`provider_usage` 235, `composio_call` 40), row estimate USD `0.130`. All 275 have owner/run/occurrence/release trace; none has `loop_id`, provider receipt, `meta.actual_usd`, or `meta.billing_status`.
- Other rows in the same time window: prior SHA `a9868ad41188e6c0a13b5277accba872460db832`, 28 rows, estimate USD `0.005`; missing release SHA, 12 rows, estimate USD `0.005845`. Those 12 lack the full runtime trace. None of the 315 rows has `loop_id`, provider receipt, `meta.actual_usd`, or `meta.billing_status`.
- Total row estimate: USD `0.140845`. This is neither actual provider billing, an invoice, a Google-only total, nor a monthly total.

## Mutation-boundary readback

- Supabase REST OpenAPI GET returned HTTP `200` and advertised `GET/POST/PATCH/DELETE` for `lm_api_cost`. This describes API methods, not evidence that any row was changed or deleted; it does not prove migration/trigger/ACL state.
- Source inspection: `apps/life-manager/lib/ledger.js` writes cost rows with POST; the inspected readers use GET. No application UPDATE/DELETE writer was found in the inspected path.
- The append-only migration exists in source/main, but no production migration receipt, ACL readback, or trigger readback was available. Production append-only state remains `unverified`.
- An earlier single-read `49→48` discrepancy remains unexplained. This fixed-window repeat-read was stable; the earlier discrepancy alone does not prove current data loss.

## Result

A1 observation is running and no A1-caused production outage or current deletion was observed. A1 is not a blocker to A2–A9. Its append-only proof and canonical wake/voice-cost/lifecycle join remain non-blocking audit hardening. The measured current CFO gap is per-loop and actual-billing attribution: all 315 rows lack `loop_id` and per-row actual/billing metadata. Keep these values estimated/unattributed/unknown; close the cost and source-coverage gaps under A2/A6/A8.
