# A1: `life-call` Composio trace natural readback

範囲: Railway production `life-call`、service設定の1 tenant、固定window 2026-10-05 10:46:45.766–10:50:00 UTC。会社全体の費用ではない。

## Deployment / runtime

- PR #6650は10:46:43 UTCにmainへmergeされ、commitは`d6f3a952e31ffc66e39a2592e775720118f3d32d`。Railway deploymentは10:46:45.766 UTC開始、readback時点で`SUCCESS` / `RUNNING`。
- log集計: `loops ON` 1件、Travel loop起動1件、Travel tick error 0件、carrier connection event 0件。
- `financial-report-runtime.readCostLedger`のGET-only結果を1 tenant分集計。確認者によるprovider/Calendar call、DB write、service variable変更はない。各行は自然schedulerが通常処理で記録したもの。

## Ledger rows

| Release | Kind / operation | Outcome / trace | Rows | row `est_usd` |
|---|---|---|---:|---:|
| `f9e4b2a6` | `provider_usage` / route-cache hit | `partial` | 2 | $0.000 |
| `f9e4b2a6` | `provider_usage` / Directions failure | `partial` | 4 | $0.020 |
| `d6f3a952` | `provider_usage` / route-cache hit | `partial` | 6 | $0.000 |
| `d6f3a952` | `provider_usage` / geocoding success | `partial` | 3 | $0.015 |
| `d6f3a952` | `provider_usage` / Directions failure | `partial` | 1 | $0.005 |
| `d6f3a952` | `composio_call` / Calendar events list | `success` response | 3 | $0.000 |
| **合計** | **ledger rows** |  | **19** | **$0.040** |

`$0.040`はrow `est_usd`推定値で、Google/Composio invoice、settlement、voice tariff、全社費用ではない。旧`f9e4`行と新`d6f3`行が同じwindowに混在しており、原因は特定していない。

- 新release由来の3 `composio_call` rowsはowner=`life-call-calendar`、run ID・owner-prefixed occurrence ID・release SHAあり。欠落は`loop_id`のみ。outcome `success`はComposio responseのbooleanであり、公式Calendar readbackや実請求の確認ではない。
- 新releaseの10 `provider_usage` rowsはowner=`life-call-travel`、run/occurrence/releaseを持ち、`loop_id`のみ欠落。旧releaseの6 rowsもpartialだが、legacy sliceとのrollout overlapの正確な原因は未検証。
- A1は未完了。canonical Product Loop mapping、Composioのactual billing/effect receipt、voice/Gemini/Telnyx cost coverage、過去のunlinked rowsが残る。直前windowの7 Composio rowsはtrace不在のまま保管され、遡及修正・再送はしていない。
