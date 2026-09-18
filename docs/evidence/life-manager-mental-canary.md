# Life Manager MENTAL V1 Canary Evidence

Status: `IN_PROGRESS` — production code and schema are live; the seven-day natural canary is not closed.

## Current production readback

- Merged main deployment: `92e9fc01664b65e8a22d37d3969b8379c67cb1fe` (PR #5482 merge).
- Railway `life-call` deployment: `SUCCESS`, instance `RUNNING`; `/health` returned `200` with build `92e9fc01664b65e8a22d37d3969b8379c67cb1fe`.
- Production Supabase tables: `lm_verified_outcomes`, `lm_mental_outcome_send_log`, and `lm_mental_profile_tags` exist with additive columns, checks, unique keys, and RLS enabled.
- `LM_MENTAL_OUTCOME_INGEST_SECRET` is present in production Railway variables.
- `LM_MENTAL_V1_ALLOWED_UIDS` is present and contains only the Dais tenant UID; the value is never written here.
- Production preflight for that allowlisted tenant returned one matching `lm_users` row and one preferences row; Telegram chat, Calendar, Gmail, paid entitlement, timezone, notifications, and daily automation were all present/enabled. Raw identifiers are intentionally omitted.
- `lm_mental_profile_tags` is present with RLS, closed kind/basis/explicit/source-hash checks, expiry/supersession columns, and zero rows until an explicit source-backed profile statement is available.
- Production scheduler logs show `organ:mental-outcome` and `organ:mental` startup/ticks.

## Telnyx authorized test-call receipt

- The post-fix authorized `/test-call` returned HTTP `200` with provider control ID `v3:tobFLiJMYkq_lUpUidoo8WXcofHUuutSy-vcIt__FxA9sHa-BqrQJA`.
- Telnyx `GET /v2/calls/{call_control_id}` returned HTTP `200` and `call_duration=18`; the related signed webhook logged AMD `machine` and the test branch performed no automatic hangup.
- No `90029` or `time_limit_secs` rejection appeared in the provider response/log readback. Duplicate-call replay-zero was not run because the first provider effect was already accepted.

## Signed outcome bridge proof

- A synthetic structured projection was posted to production over HTTPS.
- First response: `200 inserted`.
- Exact replay response: `200 duplicate`.
- Supabase readback: one structured row.
- The synthetic row and its send receipt were deleted by exact `source_outcome_id` filters after verification.
- The synthetic provider message ID was passed to Telegram `deleteMessage` with the exact mapped chat; the provider returned `ok=true`.
- Raw Gmail body, subject, snippet, and prompt text were not transmitted.

The production scheduler also observed the synthetic projection and logged a Telegram provider message ID. The exact synthetic message was deleted after verification, so it is not counted as a confirmed natural canary message.

## Remaining canary gates

- Latest automated readback at `2026-09-18T19:55:42+09:00`: `v1_count=1`, `legacy_count=33`, `daily_counts={2026-09-18: 1}`, `windows.morning_orientation=1`, and structural `pass=true` over the trailing 14-day window. This is one natural morning receipt, not a seven-day canary pass.
- The receipt row has `family=affirmation`, `window=morning_orientation`, and template `antara:courage-quiet:ja`. The provider-native `Cloud Life Manager` dialog contains a same-second inbound MTProto message (`2026-09-17T23:00:50Z`) whose text hash/length exactly matches that approved catalog item; its message has no buttons/reply markup and `out=false`. Bot API receipt ID `1384` and MTProto ID `88742` are different API identifiers, so the cross-API ID mapping is recorded as an observation rather than assumed.
- Repository hardening is now pushed on the dedicated branch: closed decision rows with replay keys, explicit quiet-hours fields, and reply-to-window timing correction are implemented and covered by the full Life Manager test suite. Production has not received this release yet; `LM_MENTAL_DECISION_LOG_REQUIRED=1` is intentionally held until the migration readback.
- A secret-free production schema probe confirms the migration gate is still open: `lm_mental_decision_log` returns `404/PGRST205`, the quiet-hours columns return `400/42703`, and the existing `lm_mental_send_log` family columns return `200`. No production mutation was attempted because the available Railway service environment exposes Supabase REST credentials but no SQL/DB connection or migration executor.
- The merged offline policy scorecard is available for replay, but no policy is promoted from it until natural provider receipts exist; this readback contains no synthetic rows.
- Explicit reply correction intake is live in the same deployment: only a reply to a durable V1 Telegram receipt can create a bounded tone tag; ambiguous/timing corrections remain no-op and no raw text is stored.
- Window-bound scheduler logs now record send family/template/message ID or enum suppression reasons; outside-window heartbeats remain silent.
- [ ] Capture one natural Dais morning affirmation in `morning_orientation`.
- [ ] Capture one natural Dais midday mindfulness/body-awareness line in `midday_awareness`.
- [ ] Capture one natural Dais evening manifestation/release line in `evening_direction`.
- [ ] For seven consecutive local days, record decision, family, template ID, window, Telegram ID, and durable receipt row.
- [ ] Prove daily count <= 3, spacing >= 3 hours, busy/quiet suppression, 14-day template dedupe, and replay-zero.
- [ ] Verify the actual Telegram text has no buttons, callback data, reply instruction, sender signature, or unsupported personal claim.

No production rollout beyond the Dais allowlist is authorized until these rows are closed with provider-native Telegram readback.
