# Manager — E16本番配備ゲートから再開

唯一の状態正本は [tasks.json](../roadmap/tasks.json) のF009。技術順は既存E01→E16、次のカーソルはE16。E01–E15をやり直さない。原113件の69 done /41 todo /3 skippedは別の受入状態で、Eの実装件数を加算しない。

**後続source実装:** 過去intent先行回収、checkpointで再利用できない送信境界、commitとdeliveryの分離、lag/hash-onlyでrollbackしない処理を追加した。[実装・684テスト・16ケース実測の記録](../verification/E16_RECOVERY_HARDENING_20261022.md)。本番host adapter/privileged bridge/volume/実canaryは未成立で、E16の状態は変わらない。

## 実装済みの範囲

- E06: 同期providerの絶対期限、cancel/正確なturn読戻し、予算の未知状態保持。新しいlive推論なし。
- E07–E08: 凍結した多軸rubric、20開発/40評価ケース、NO_ACTION/単純ルール基準。モデル比較はNOT_RUN、優位性未証明。
- E09: 実際のUCI公開集計データによる、その領域限定の誤差校正。subgroup riskでpromotion拒否。人/所有デジタルへの転用はABSTAIN。
- E10–E11: HTTPS公開情報の実取得、版管理、永続SQLite、古い引用の拒否。観測は実行権限にならない。
- E12–E14: 単位を混ぜない候補、NO_ACTION、公式リンク/ラベルの限定差分検証、所有者scopeと元のprivileged publisherへの不活性handoff。
- E15: 永続intent予約、Git親commit CAS、正確なoccurrence照合、UNKNOWN隔離。fixture executorのlive禁止は維持。
- E16部分: ローカルGit専用の参照サイクル、独立した配信ファイル、replay-zero、停止/正確な7ファイル復元、single-host flock、catch-up一回、shadow記録。**本番アダプターは未実装、常駐ホストへの配備も未実施。**

証跡は `docs/verification/E06_*`〜`E16_*` とSSOTの各source commit/CI。現行ブランチは `research/manager-e01-e16-execution-20261022`、PRは [#8527](https://github.com/Daisuke134/life-manager/pull/8527)、baseは `research/manager-phase06-owned-public-good-20261022`。draft/unmergedの研究PRで、本番mainではない。クラウドでMac専用source guardは未合格、代替合格とは扱わない。

**2026-10-25訂正:** 上記source-guard記述は初回cloud worktreeの履歴です。正規origin clone配下の許可された`.worktrees`へ移動し、`bash scripts/verify-source-boundary.sh`はPASSしました。Mac Miniには接続されていません（Remote Desktop Commander上Offline）し、Railwayで進めるE16にMac接続は不要です。最新のローカルstate backup/restore実装と687件の検証結果は[recovery receipt](../verification/E16_RECOVERY_HARDENING_20261022.md)に追記しました。

## 2026-10-22 cloud-first選定更新

実行先はRailwayの専用Python worker＋永続volumeに決定。既存life-manager projectへのread accessを確認した。Macのホスト情報待ちを再開条件にしない。既存production serviceの用途/ownerを調べて保全し、専用isolated stagingから始める。新worker/volume、本番adapter、費用/停止設定、main/immutable-release promotionと実機証拠は未完了なのでE16はBLOCKEDのまま。新しいfounder/収益/出版/採用/W27の依存付き作業は [実行マップ](../plans/2026-10-22-manager-founder-execution-map.md) を参照。

## ここからの順番

1. [E16の本番要件と未実装パッチ](../verification/E16_CYCLE_AND_DEPLOYMENT_GATE_20261022.md) を読み、選定したRailwayの既存service用途/ownerと、Manager専用のloaded immutable release・owner・永続volumeを実際に確認。registryだけで稼働を推定しない。新規/競合schedulerを作らない。
2. そのhost契約に合わせ、本番cycle adapterを既存ownerへ接続。元の `phase06_kernel_release.admit_owned` / publisher / official collectorを再利用し、元SOURCE_REFを今回研究branchへ書換えて権限チェックを迂回しない。private stateはsource/releaseの外。
3. 通常のレビュー→main→immutable release→owner apply経路で、1回の7ファイルcanary→公式commit/parent/全body照合→別経路の公開GET→replay-zero→実hostの再起動/catch-up/限定rollbackを記録。その証跡が揃うまでE16はBLOCKED。
4. E16後もF005→F006→F008→F009の受入は別判定。人への便益、持続効果、需要/顧客、モデル優位、YCや記事公開は、対応する実証なしにdoneにしない。

## 開発確認

`products/manager` で `python -m unittest discover -s tests -q`、`python scripts/check_boundaries.py`、`python scripts/make_roadmap.py --check`。ブラウザは既存catalogから `output/service/site` をrenderして `npm --prefix tests/e2e test`。read-only CIは当該研究branch向けで、production promotion gateの代替ではない。

`python scripts/run_owned_digital_cycle.py --state-store <private-state>` の現状の正しい結果はexit 2 / DEPLOYMENT_HOST_REQUIRED。本番writeは行わない。この状態を隠すためにフラグを変えない。既存公開siteは別の旧sourceから配信されており、今回のE16配備と混同しない。
