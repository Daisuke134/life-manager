# A1: `life-call` cumulative production cost readback (13:52 UTC)

範囲: Railway production `life-call`のactive deploymentとproduction Supabaseの既存CFO/voice関連read-only tables。会社全sourceの請求額ではない。UID、tenant ID、run/occurrence/event key、call ID、電話番号、calendar event details、payloadは取得・保存していない。

## Deployment

- 2026-10-05T13:52:04–13:52:08ZのRailway service statusは`status=SUCCESS`、`stopped=false`、active deployment `38b34ef2-4900-4ccc-83b8-f874bf88fac8`。SHAは`9e3fb448b6799e6f5183f087773fa245c8409778`。同時刻のdeployment listでは最新entry `3c9518ce-2f33-4298-ba7d-6b067aba2053`（main SHA `3f8371b0`）が`SKIPPED`で、active deploymentは維持されていた。

## Cost ledger

- Supabase REST GETはexact `meta.runtime_trace.release_sha`と`ts >= 2026-10-05T12:34:01.656Z`、`ts < 2026-10-05T13:52:04.283Z`で照会。`reported_total=91`、row範囲は`2026-10-05T12:36:13.084567+00:00`–`2026-10-05T13:51:11.840524+00:00`。SHA mismatchは0。
- 91件すべてtrace=`partial`、missingは`loop_id`のみ。個人・tenant・occurrence識別子とpayloadはselectしていない。

| kind / operation | outcome | rows | row `est_usd`合計 |
|---|---|---:|---:|
| `composio_call` / `GOOGLECALENDAR_EVENTS_LIST` | success | 54 | USD 0.000 |
| `provider_usage` / `route_cache/travel_route` | cache_hit | 8 | USD 0.000 |
| `provider_usage` / `google_maps/geocoding` | success | 5 | USD 0.025 |
| `provider_usage` / `google_maps/directions` | failure | 24 | USD 0.120 |
| **合計** |  | **91** | **USD 0.145** |

USD 0.145は見積額のみ。actual amount、billing status、receipt/effect/readbackは確認できない。Production schema probe（13:16:44.748Z）は`actual_usd`、`billing_status`、`pricing_version`、`provider_receipt_id`、`effect`、`readback`を全てSQLSTATE `42703`（missing column）と確認済み。見積0は無料の証明ではない。

## Voice / wake occurrence

- 同じrelease windowの`gemini_live` / `telnyx_call` rowsは0、`provider_usage` feature=`live_api` rowsも0。
- `lm_wake_log`の`called_at`（2026-10-05T11:24:42Z–13:50:03.776Z）は0件。`lm_wake_miss`の`occurred_at`同windowも0件。selectは時刻・outcome/reason・durationだけで、UID/event key/call ID/detailは含めない。
- 13:44:55.352Zのproduction `HEAD count=exact`では、`paid=true`、E.164 phoneあり、supported calendar provider、`call_enabled=true`、`daily_automation_enabled=true`に合うaccount数は1。response body/UID/phoneは読んでいない。この数だけではどのaccountか、wake対象eventがあったかは分からない。
- Railway logs（deployment `38b34ef2-4900-4ccc-83b8-f874bf88fac8`、deployment開始–13:49:21.289Z）の安全なtext-filter集計: scheduler started 1、wake started 1、voice reconciliation checked 16、wake placement/dial failure/missed wake/carrier connectionはいずれも0。log本文は保存していない。
- したがって自然voice occurrenceは未観測。これはvoice費用ゼロや請求なしの証明ではない。確認者は発信・Calendar call・DB writeをしていない。
