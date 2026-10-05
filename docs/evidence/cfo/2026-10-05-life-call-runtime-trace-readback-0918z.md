# A1 production readback: `life-call` provider usage trace

観測時刻: 2026-10-05 18:18 JST（2026-10-05 09:18 UTC）  
範囲: Railway production の `life-call` と、`LM_RUNTIME_TENANT_ID`で指定された1 tenantの読み取り専用cost ledger。会社全体の集計ではない。

## Deployment

- Railwayのactive deploymentはcommit `9f7bf1420ec1416d4c713a218ac7570760992658`（PR #6637）で、2026-10-05 08:17:50 UTCに`SUCCESS`、instanceは`RUNNING`。
- service variable key inventoryには`LIFE_MANAGER_LOOP_ID`、`LIFE_MANAGER_OWNER_ID`、`LIFE_MANAGER_RUN_ID`、`LIFE_MANAGER_OCCURRENCE_ID`、`LIFE_MANAGER_RELEASE_SHA`がない。
- `LIFE_RUN_LOOPS`と`LM_DEPLOYMENT_ROLE`も未設定。現行`maybeStartLoops`規則ではRailway内のwake/travel/ask schedulerが起動する。
- local `config/loop-registry.json`と14-entry Product Loop catalogに`life-call`またはTravel loopの対応IDはない。

## Read-only cost ledger

`financial-report-runtime.readCostLedger`で、2026-10-05 08:17:48 UTC以降の行だけを取得した。

| Provider / feature | Rows | `est_usd`合計 | Outcome |
|---|---:|---:|---|
| `route_cache/travel_route` | 178 | $0.000 | `cache_hit` |
| `google_maps/geocoding` | 5 | $0.025 | `success` |
| `google_maps/directions` | 12 | $0.060 | `failure` |
| **合計** | **195** | **$0.085** | 推定値 |

`$0.085`は1 tenantのprovider usage行に保存された価格推定で、Google invoice・settlement・会社全体の実費ではない。

- 186行は`runtime_trace.status=unlinked`で、`loop_id`、`owner_id`、`run_id`、`occurrence_id`、`release_sha`が欠けていた。
- 9行は`runtime_trace`自体がなく、すべて`route_cache/travel_route`。発生時刻は2026-10-05 08:18:35.963–08:20:36.313 UTC。旧deploymentのin-flight writeか別writerかは未確定。
- 読み取り時点で`linked`行は0件。provider event rowは残り、使用量推定も保存されている。

## A1 cursor

PR #6637のsourceはproductionにdeploy済みだが、Railwayの`life-call`にはlocal loop identityがなく、Google travel費用を14 Product Loopのどれかへ割り当てる根拠もない。loop IDを捏造せず、既存`life-call` travel ownerのrun/occurrence/releaseだけを記録する変更を作業branch `fix/cfo-life-call-travel-trace-20261005`で実装した。`loop_id`は未割当のままpartialとなるため、A1は未完了。新たなprovider call、service variable変更、DB writeは行っていない。
