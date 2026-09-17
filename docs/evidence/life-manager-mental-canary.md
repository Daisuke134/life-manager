# Life Manager MENTAL V1 Canary Evidence

Status: `IN_PROGRESS` — production code and schema are live; the seven-day natural canary is not closed.

## Current production readback

- Merged main deployment: `b325a34d5b8e3ca9eaecc396311026d58d0ce399`.
- Railway `life-call` deployment: `SUCCESS`; `/health` returned `200` with the same build SHA.
- Production Supabase tables: `lm_verified_outcomes`, `lm_mental_outcome_send_log`, and `lm_mental_profile_tags` exist with additive columns, checks, unique keys, and RLS enabled.
- `LM_MENTAL_OUTCOME_INGEST_SECRET` is present in production Railway variables.
- `LM_MENTAL_V1_ALLOWED_UIDS` is present and contains only the Dais tenant UID; the value is never written here.
- `lm_mental_profile_tags` is present with RLS, closed kind/basis/explicit/source-hash checks, expiry/supersession columns, and zero rows until an explicit source-backed profile statement is available.
- Production scheduler logs show `organ:mental-outcome` and `organ:mental` startup/ticks.

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

- [ ] Capture one natural Dais morning affirmation in `morning_orientation`.
- [ ] Capture one natural Dais midday mindfulness/body-awareness line in `midday_awareness`.
- [ ] Capture one natural Dais evening manifestation/release line in `evening_direction`.
- [ ] For seven consecutive local days, record decision, family, template ID, window, Telegram ID, and durable receipt row.
- [ ] Prove daily count <= 3, spacing >= 3 hours, busy/quiet suppression, 14-day template dedupe, and replay-zero.
- [ ] Verify the actual Telegram text has no buttons, callback data, reply instruction, sender signature, or unsupported personal claim.

No production rollout beyond the Dais allowlist is authorized until these rows are closed with provider-native Telegram readback.
