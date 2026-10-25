# Manager

Managerは、**行動変容を通じて、苦しみを終わらせることを目指す**一つのAIエンティティです。
特定の宗教への帰属を前提にせず、行動科学・統計・AI・既存の実践から学びます。
通常の活動と価値に専用app/chatや人の毎回の操作を必須にしません。Digital Buddhaは
任意の構想上の呼称で、意識・AGI・すべての苦しみの終結を実証したという意味ではありません。
モデル系列・規模・量子化・runtime・学習方法は、根拠と実測から柔軟に選び直します。

このディレクトリには、公開研究を検査・評価するコードと、既存の所有サイトで
限定された変更を実行・照合・復旧する共通kernelを置きます。
サイトの公開成功と、人間の行動変化・便益の実証を区別します。

## 公開研究を再利用する

- [公開研究の再利用計画](../../docs/research/manager/2026-10-22-open-behavior-reuse-plan.md)
- `scripts/inspect_external_behavior_benchmark.py`: 固定された公開Source Dataのhash、
  構造、研究・条件・効果の単位を検査します。
- `scripts/evaluate_external_behavior_benchmark.py`: 公開済み効果予測を研究単位で分割し、
  無効果baseline・元の予測・訓練研究だけで較正した予測を比較します。
  専用の任意依存は `requirements-external-behavior-eval.txt` に固定しています。

過去の公開予測の再採点は、新しいモデル推論や、Manager自身の新しい介入の効果を
証明するものではありません。原データや個人行をGitへ保存しません。

## 有限private SFTのoffline source

[用途限定scope](docs/specs/2026-10-23-finite-private-sft-research-start.md)と
[導入・検証計画](docs/plans/2026-10-23-helpsteer2-private-sft.md)に、固定された
元候補を使う研究専用のnative PEFT/TRL entryを置きます。既存dev8評価の
権利・protocolは維持します。CIはsynthetic fixtureだけで検証し、原corpus・
weights・private adapter/configはGitへ保存しません。

sourceのimport・main統合は学習/評価の実行許可や本番model採用を意味しません。
固定adapter比較の研究entryは[評価source導入計画](docs/plans/2026-10-23-helpsteer2-fixed-adapter-eval.md)
を参照します。同じ固定元候補の比較sourceで、結果・実行権限・model採用は別に確認します。
進捗・順序は下記の単一SSOTを参照します。

## 一つの実行経路

既存の [Manager workflow](../../.github/workflows/manager-phase06-service.yml) は、
mainの定期実行・明示dispatchだけで所有範囲の変更を実行します。
`scripts/run_owned_digital_cycle.py` が一度だけ共通cycleを呼びます。

1. 短命なGitHub OIDCで [private checkpoint gateway](deploy/owned-digital/README.md) を認証し、
   保存済みSQLiteをprivateな一時領域へ復元する。
2. 保存済みの実行・配信結果を先に照合し、停止状態と実行間隔を確認する。
3. 正当な改善候補がある場合だけ、固定された出典・権利・差分・ブラウザ検査を行う。
4. 送信予約をprivate storeへ確実に保存してから、既存の権限検査とGit CASで
   `manager-support/` の7ファイルだけを更新する。
5. 既存Pages workflow `307239134` で公開し、元の実行に結びつくprovider receiptと
   公開されたbytesを独立に確認する。

不明な送信結果を「未送信」とみなして再実行しません。状態欠落時に空のDBを作って
続行するfallbackもありません。初回の状態移行は、旧writerの停止と過去の実行結果の
照合を終えた上で行う、独立したoperator作業です。

引数なし、または `preflight` は読み取り専用です。

```sh
cd products/manager
python scripts/run_owned_digital_cycle.py preflight
python -B -m unittest discover -s tests -v
python scripts/check_boundaries.py
```

ブラウザ検査は `tests/e2e/package-lock.json` を使います。
実環境の `run-once` は、既存のmain workflowだけが所有します。
認証・状態復元・公開・復元後の重複送信0件という実際の記録が揃うまで、
ローカルテストの成功だけでE16を完了にしません。

mainの明示的なworkflow dispatchでは、`operation`から`run-once`、`stop`、
`rollback`、`resume`を選べます。定期実行は`run-once`です。STOPは非公開状態に
保存され、別runnerでも維持します。rollbackは保存済みv2の現在の変更と元の
7ファイルだけに限定し、Git CASで照合します。`resume`は現在の公開内容を
改めて確認してから停止を解除します。配信待ちや不明な結果だけで復元しません。

公式commitと独立した配信確認から得た技術観測は、既存SQLiteへ元の単位で
記録します。人の結果は`NOT_MEASURED`、欠測はnullのままです。Explorerの
集計表示はローカル描画機能で、公開サイトへの接続・実観測の受入れは別に確認します。

## EBA source catalog

EBA v1のcatalogは既存90件のsource inventoryを固定hashで参照します。各候補は
rights・version・評価dimensionの対応が確認されるまで未検証のまま保持し、7 dimensionの
scoreは実行するまで`null`です。このcatalogはbenchmarkの実行結果、共通leaderboard、
人の行動・便益の証拠ではありません。

既存のEBA v0.1 synthetic developer harnessは`eba/`に保存し、共通の
`manager_core.evaluation`のTVD/Brier実装を使います。こちらは公開goldを使うP0の形式・
安全性demoで、実モデルの比較でも人への効果評価でもありません。90件catalogの評価結果
とも別物です。

```sh
cd products/manager
python -B -m manager_core.eba_manifest --check
python -B -m unittest tests.test_eba_manifest -v
python -B -m eba
python -B -m unittest tests.test_eba_benchmark -v
```

90件を個別に採用するには、上流source/version、license、population、unit、label、holdout、
metricを先に確認します。分からない値はunknownのままにし、dimensionへ未レビューの候補を
割り当てません。

## 進捗の正本

このREADMEは実装の入口であり、新しいTODO一覧ではありません。
順序・状態の正本は [Life Manager統合SSOT](../../docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md)
です。研究・出版・応募・売上の記録を、人間への便益や持続的な効果の証明に
読み替えません。

実運用の現在地は [2026-10-23 cloud実行receipt](docs/verification/E16_CLOUD_EXECUTION_20261023.md) を参照してください。gateway/main runtime、初回非公開状態移行、実OIDC復元・更新・解放を確認済みです。初回NO_ACTIONと別fresh runnerのNOT_DUE／重複公開0件を実証しました。正のcanary・停止/復旧・native観測の受入れは継続中です。
