# A1: `life-call` current-release cost ledger readback (13:16 UTC)

範囲: Railway production `life-call`のactive deploymentと、Supabase production `lm_api_cost`をGET-onlyで照会。会社全sourceの費用やGoogle/Composioの請求額ではない。UID、tenant ID、run ID、occurrence ID、call ID、payloadは取得・保存していない。

## Deployment

- Railway service statusは2026-10-05T13:14:48.794–13:14:54.065Zに`status=SUCCESS`、`stopped=false`、active deployment `38b34ef2-4900-4ccc-83b8-f874bf88fac8`、release SHA `9e3fb448b6799e6f5183f087773fa245c8409778`。最新deployment list entryはcommit `f61d2adbf0ede40f4ab5a318fc98e1acf7a69ed2`の`SKIPPED`で、active SHAは維持されている。

## Cost ledger

- Supabase REST GETは`meta.runtime_trace.release_sha`を上記SHAに完全一致させ、`ts >= 2026-10-05T12:34:01.656Z`かつ`ts < 2026-10-05T13:14:24.197Z`で照会。`reported_total=52`、照会時刻は13:14:24.197–13:14:29.723 UTC、row時刻範囲は12:36:13.084567–13:08:11.274908 UTC。
- selectした列はtimestamp、kind、quantity、unit、`est_usd`とprovider/feature/tool/outcome/owner/traceのallowlisted fieldsのみ。全52 rowsでSHA一致。traceは全件`partial`、`loop_id`だけ欠落。

| kind / operation | outcome | rows | row `est_usd`合計 |
|---|---|---:|---:|
| `composio_call` / `GOOGLECALENDAR_EVENTS_LIST` | success | 27 | USD 0.000 |
| `provider_usage` / `route_cache/travel_route` | cache_hit | 8 | USD 0.000 |
| `provider_usage` / `google_maps/geocoding` | success | 5 | USD 0.025 |
| `provider_usage` / `google_maps/directions` | failure | 12 | USD 0.060 |
| **合計** |  | **52** | **USD 0.085** |

USD 0.085はledgerの`est_usd`見積合計のみで、actual spendや請求額ではない。Production PostgREST GETで`actual_usd`、`billing_status`、`pricing_version`、`provider_receipt_id`、`effect`、`readback`の各columnを個別selectしたところ、全てHTTP 400 / PostgreSQL `42703`（column missing）だった。`meta`内のactual amount、billing status、provider receipt、effect、readbackも52件すべて未記録。Composio listのUSD 0見積もりも無料の証拠ではない。

Schema probe: GET-only、2026-10-05T13:16:44.748Z、exact release SHA filter。raw error bodyや行データは保存していない。

## Voice coverage check

- 同一windowのGET-only queryでは、`gemini_live` / `telnyx_call` rowsが0件、`provider_usage`かつfeature=`live_api` rowsも0件。
- これは期間内の該当cost ledger rowを観測しなかった意味だけであり、自然voice occurrenceの不存在、voice費用ゼロ、provider請求なしの証拠ではない。検証者によるprovider call、Calendar call、DB writeは0件。
