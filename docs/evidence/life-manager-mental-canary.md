# Life Manager MENTAL V1 Canary Evidence

Status: `IN_PROGRESS` — production code and schema are live; the seven-day natural canary is not closed.

## Current production readback

- Railway `life-call` deployment: `SUCCESS`, instance `RUNNING`; fresh `/health` readback returned `200` with build `d4659ff4bc7b4e13aa67836243060ad1d4efbb03`.
- Production Supabase tables: `lm_verified_outcomes`, `lm_mental_outcome_send_log`, and `lm_mental_profile_tags` exist with additive columns, checks, unique keys, and RLS enabled.
- `LM_MENTAL_OUTCOME_INGEST_SECRET` is present in production Railway variables.
- `LM_MENTAL_V1_ALLOWED_UIDS` is present and contains only the Dais tenant UID; the value is never written here.
- Production preflight for that allowlisted tenant returned one matching `lm_users` row and one preferences row; Telegram chat, Calendar, Gmail, paid entitlement, timezone, notifications, and daily automation were all present/enabled. Raw identifiers are intentionally omitted.
- `lm_mental_profile_tags` is present with RLS, closed kind/basis/explicit/source-hash checks, expiry/supersession columns, and zero rows until an explicit source-backed profile statement is available.
- Production scheduler logs show `organ:mental-outcome` and `organ:mental` startup/ticks.
- Supabase CLI token was found in the private `/Users/anicca/.openclaw/.env` (value never recorded);
  project listing matched production ref `cycgdwndgfgdbnndithc`. The canonical CLI migration files
  were applied to production at `2026-09-19T00:01:00Z` and `00:02:00Z`; `supabase migration list`
  reports local/remote equality for both versions.
- Post-migration REST readback returned `200` for `lm_mental_decision_log`, the two
  `lm_panel_preferences.mental_quiet_*` columns, and the existing `lm_mental_send_log`.

## Host foundation audit (read-only)

- `/System/Volumes/Data` reported `228 GiB` total, `184 GiB` used, `6.8 GiB` available, and `97%`
  capacity. `vm.swapusage` reported `20 GiB` total and `18.76 GiB` used.
- The host had `703` processes and `165` Chromium processes. Two `Z`/defunct processes were
  observed; their parents were Chromium PID `27633` and ChatGPT PID `52958`, not Life Manager.
- The main repository used `4.8 GiB` (`.worktrees` `2.0 GiB`, `.git` `2.8 GiB`), with `141` Git
  worktrees registered (`106` locked); `git worktree prune --dry-run` returned no prunable entries.
  `/private/tmp` used `4.1 GiB`, `~/.local/state/anicca` `4.7 GiB`, `~/.local/state/life-manager`
  `4.0 GiB`, `.codex/sessions` `3.5 GiB`, and `.openclaw` `4.5 GiB`.
- No large Life Manager deleted-open file was found. These observations support resource pressure
  and missing retention/lease GC as the local foundation risk; they do not establish malware.
- Fresh local verification on 2026-09-19: `npm run test:mental-v1` completed with `103` tests,
  `103` pass, `0` fail. This is repository evidence only; no production mutation was performed.

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

- Latest automated readback at `2026-09-18T22:32:41+09:00`: `v1_count=2`, `legacy_count=32`, `daily_counts={2026-09-18: 2}`, `min_gap_ms=48254748`, `windows.morning_orientation=1`, `windows.evening_direction=1`, and structural `pass=true` over the trailing 14-day window. This is two natural receipts, not a seven-day canary pass. The read-only wall-clock monitor was restarted after its prior process exited; no send or scheduler mutation was performed.
- The receipt row has `family=affirmation`, `window=morning_orientation`, and template `antara:courage-quiet:ja`. The provider-native `Cloud Life Manager` dialog contains a same-second inbound MTProto message (`2026-09-17T23:00:50Z`) whose text hash/length exactly matches that approved catalog item; its message has no buttons/reply markup and `out=false`. Bot API receipt ID `1384` and MTProto ID `88742` are different API identifiers, so the cross-API ID mapping is recorded as an observation rather than assumed.
- The midday opportunity on this local day was correctly suppressed by the shared trailing-24-hour cap; the evening opportunity later delivered one V1 manifestation. The durable row is `id=160`, `family=manifestation`, `window=evening_direction`, `template_id=antara:small-step-afraid:ja`, `telegram_message_id=1395`, `sent_at=2026-09-18T12:25:05.350819Z`. No cap bypass or extra send was authorized. Provider-native body/markup readback for this second receipt remains open.
- Repository hardening is pushed on release branch `fix/lm-mental-production-release-20260919` at
  `8023b98b9d`; focused MENTAL tests and the full Life Manager suite pass. Production has not
  received this code release yet, so `LM_MENTAL_DECISION_LOG_REQUIRED=1` remains intentionally off.
- The remaining release mismatch is code, not schema: production `/health` still reports the older
  build `d4659ff4bc7b4e13aa67836243060ad1d4efbb03`, while the release branch contains the decision
  wiring. No production flag change was attempted before that code release.
- The merged offline policy scorecard is available for replay, but no policy is promoted from it until natural provider receipts exist; this readback contains no synthetic rows.
- Explicit reply correction intake is live in the same deployment: only a reply to a durable V1 Telegram receipt can create a bounded tone tag; ambiguous/timing corrections remain no-op and no raw text is stored.
- Window-bound scheduler logs now record send family/template/message ID or enum suppression reasons; outside-window heartbeats remain silent.
- [x] Capture one natural Dais morning affirmation in `morning_orientation`.
- [ ] Capture one natural Dais midday mindfulness/body-awareness line in `midday_awareness`.
- [x] Capture one natural Dais evening manifestation/release line in `evening_direction` (body/markup readback still open).
- [ ] For seven consecutive local days, record decision, family, template ID, window, Telegram ID, and durable receipt row.
- [x] Apply and read back the decision-log and quiet-hours migrations through Supabase CLI.
- [ ] Deploy the decision-log wiring release and read back its exact production SHA before enabling the flag.
- [ ] Prove daily count <= 3, spacing >= 3 hours, busy/quiet suppression, 14-day template dedupe, and replay-zero.
- [ ] Verify the actual Telegram text has no buttons, callback data, reply instruction, sender signature, or unsupported personal claim.

No production rollout beyond the Dais allowlist is authorized until these rows are closed with provider-native Telegram readback.
