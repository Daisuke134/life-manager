# A1: `life-call` Travel natural readback

観測範囲: Railway production `life-call` とservice設定の1 tenant。会社全体の費用集計ではない。
固定window: 2026-10-05 09:43:58.192–09:54:24.000 UTC

## Deployment / runtime

- PR #6647は09:43:56 UTCにmergeされ、main SHAは`f9e4b2a6d82729b1218c10346e25f8a6685738cf`。Railway `life-call`も同SHAで`SUCCESS`、instanceは`RUNNING`。
- read-only log集計: `loops ON` 1件、Travel loop起動1件、Travel tick error 0件。carrierは09:50:33.367 UTCに接続し、09:51:02.369 UTCに切断した。これは自然run中に観測した1組のイベントであり、確認者は通話を起動していない。通話の請求額はこのledger readbackの対象外。
- `financial-report-runtime.readCostLedger`をGET-onlyで読み取り、1 tenantの`provider_usage`を固定window内で集計した。確認者によるprovider call、DB write、service variable変更は行っていない。自然Travel tickは通常処理でproviderを呼び、既存cost rowを書き込んだ。

## Cost ledger

| Provider / feature / outcome | Trace | Rows | row `est_usd` |
|---|---|---:|---:|
| `route_cache/travel_route/cache_hit` | `partial` | 17 | $0.000 |
| `google_maps/geocoding/success` | `partial` | 5 | $0.025 |
| `google_maps/directions/failure` | `partial` | 12 | $0.060 |
| `route_cache/travel_route/cache_hit` | `unlinked` | 4 | $0.000 |
| **合計** |  | **38** | **$0.085** |

実請求額は分からない。`$0.085`はcost row直下の`est_usd` usage推定値であり、Google invoice、settlement、音声通話料、会社全体の実費はこの照会では確認していない。

同じwindowには上記の38 `provider_usage`以外に7 `composio_call` rowsもある。row `est_usd`は7行とも$0.000で、operationはCalendar list 6回とcreate 1回。これは記録されたtool呼び出しと推定額であり、Calendar側のeffect receiptや実請求が0である証明ではない。全ledger行数は45。音声carrier費用もこのledger集計では確認できない。

- 34件の`partial`はすべてowner=`life-call-travel`で、run ID・owner-prefixed occurrence ID・deploy SHA一致のrelease SHAを持つ。欠落項目は`loop_id`だけ。
- 4件の`unlinked`は09:44:34.329592–09:45:35.520675 UTCに記録され、5つのtrace identity項目を欠く。writer境界は未特定。`provider_usage`の`linked` rowは0件。
- canonical Product Loop catalogにこのTravel ownerのloop IDがないため、`loop_id`は推測していない。

A1は未完了。自然runのtrace contextは記録されたが、Product Loopへの正しい帰属、4 unlinked rowsのwriter境界、他provider経路のtrace/cost coverageは未確認である。
