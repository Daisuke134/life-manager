# Manager — E16本番配備ゲートから再開

唯一の状態正本は [tasks.json](../roadmap/tasks.json) のF009。技術順は既存E01→E16、次のカーソルはE16。E01–E15をやり直さない。原113件の69 done /41 todo /3 skippedは別の受入状態で、Eの実装件数を加算しない。

**当初スナップショット時点の後続source実装:** 過去intent先行回収、checkpointで再利用できない送信境界、commitとdeliveryの分離、lag/hash-onlyでrollbackしない処理を追加した。[初期実装・684テスト・16ケース実測の記録](../verification/E16_RECOVERY_HARDENING_20261022.md)。本番host adapter/privileged bridge/volume/実canaryは未成立で、E16の状態は変わらない。

## 実装済みの範囲

- E06: 同期providerの絶対期限、cancel/正確なturn読戻し、予算の未知状態保持。新しいlive推論なし。
- E07–E08: 凍結した多軸rubric、20開発/40評価ケース、NO_ACTION/単純ルール基準。モデル比較はNOT_RUN、優位性未証明。
- E09: 実際のUCI公開集計データによる、その領域限定の誤差校正。subgroup riskでpromotion拒否。人/所有デジタルへの転用はABSTAIN。
- E10–E11: HTTPS公開情報の実取得、版管理、永続SQLite、古い引用の拒否。観測は実行権限にならない。
- E12–E14: 単位を混ぜない候補、NO_ACTION、公式リンク/ラベルの限定差分検証、所有者scopeと元のprivileged publisherへの不活性handoff。
- E15: 永続intent予約、Git親commit CAS、正確なoccurrence照合、UNKNOWN隔離。fixture executorのlive禁止は維持。
- E16部分: ローカルGit専用の参照サイクル、独立した配信ファイル、replay-zero、停止/正確な7ファイル復元、single-host flock、catch-up一回、shadow記録。**2026-10-25に本番接続用adapter/bridgeのsourceは追加済み。専用ホストへの配備・実workflow・公開readback・復旧receiptはまだなく、E16受入は未完了。**

証跡は `docs/verification/E06_*`〜`E16_*` とSSOTの各source commit/CI。現行ブランチは `research/manager-e01-e16-execution-20261022`、PRは [#8527](https://github.com/Daisuke134/life-manager/pull/8527)、baseは `research/manager-phase06-owned-public-good-20261022`。draft/unmergedの研究PRで、本番mainではない。初回cloud workspaceではsource guardに通らなかったが、許可されたcanonical clone配下のworktreeへ移動後はguardがPASSしている。

**2026-10-25 source-boundaryと検証履歴:** 正規origin clone配下の許可された`.worktrees`で `bash scripts/verify-source-boundary.sh` がPASS。前段state backup/restore後は687件、初期bridge後は723件（5 skip）、最終review修正後のlocal全suiteは730件成功（5 skip）。最後の730件はこのworktreeでの結果で、未push・未GitHub CI。Mac Miniへの接続は確認しておらず、Railwayで進めるE16の前提ではない。初期state recoveryは[recovery receipt](../verification/E16_RECOVERY_HARDENING_20261022.md)、最終修正は[atomic patch plan](../plans/2026-10-22-manager-e16-atomic-patches.md)を参照。

## 2026-10-25 PATCH-05 implementation checkpoint

`manager_core/owned_platform_host.py` に固定schemaのowner workflow request、owner/packet/target parentの再照合、Railway runtime identity preflightを追加した。最終review修正前の初期request digestはlease時刻を含まなかったが、request v2で元の`created_at`/`expires_at`をrequest IDとdigestに固定し、再構築時も元の6時間leaseをpublisherまで保持する。preflightはRailway project/environment/service/volumeの期待ID、`Daisuke134/life-manager` の `main` とimmutable SHA、独立した永続state mountを要求する。書込modeではowner enablement、上限付きinterval、dispatch credentialの存在も要求し、credential値は結果に返さない。owner無効またはcredential不在のread-only recovery modeではREADY requestをrevokeして保存済みeffect/deliveryだけ照合し、外部API、dispatch、新規planningは行わない。main source admissionはversioned v2として追加し、既存v1を維持する。既存workflowはmainの`workflow_dispatch`でだけrequestを受け取り、保護されたowner ID、同一SHAのverified artifact、正確な`gh-pages`親commitを再検査して既存7-file guardを通す。source checkout credential persistenceは無効のまま。SQLiteはmain requestを永続予約してから一度だけ送信claimし、期限切れrequestは送信せず`EXPIRED`として保持する。GitHub run lookupはrequest ID/title、branch、event、source SHAを照合する。Railway cycleは固定support catalogから候補を生成し、稼働SHAがmainと一致すること、committed `gh-pages` bundleが独立取得した公開bytesと一致することを確認し、due時だけrequestを予約する。過去effectのoccurrenceとdeliveryを先に照合し、未知の履歴を越えて新しいeffectを送らない。実際の公開writeは引き続き保護されたGitHub workflowだけが担当する。

初期bridge時点で723件のPython test（5 skip）、Playwright/axeのdesktop/mobile 16ケース、境界・roadmap・source-boundary checksが通過した。その後のfinal reviewで見つかった3件（公開readback receiptの引数衝突、期限切れrequest再送、owner無効時のread-only回収停止）を修正し、local全Python suiteは730件成功（5 skip）。修正後のGitHub CIは未実行。この証拠はsourceとfake transportの範囲で、本番E2Eではない。専用Railway staging service/volume・credential、通常のmain promotion、実workflow、公式commit/parent/public-byte照合、restart/replay-zero evidenceはまだない。旧`research/manager-product-r006-20261020` publisher pathは変更していない。残りはreview修正のGitHub CI、通常のreview/main promotion、分離staging worker/settings、read-only preflight、レビュー済み1回canary、provider/publicの独立readbackの順。旧source-ref allowlistは拡張しない。

## 2026-10-22 cloud-first選定更新

実行先はRailwayの専用Python worker＋永続volumeに決定。既存life-manager projectへのread accessを確認した。Macのホスト情報待ちを再開条件にしない。既存production serviceの用途/ownerを調べて保全し、専用isolated stagingから始める。新worker/volume、本番adapter、費用/停止設定、main/immutable-release promotionと実機証拠は未完了なのでE16はBLOCKEDのまま。新しいfounder/収益/出版/採用/W27の依存付き作業は [実行マップ](../plans/2026-10-22-manager-founder-execution-map.md) を参照。

## ここからの順番

1. final source reviewで直した3件をcommit/pushし、修正後のCIで730 Python tests（5 skip）、16 browser tests、boundary・roadmap・source-boundary checksを確認してPR #8527に記録する。研究branchをproduction mainと誤認せず、旧`SOURCE_REF` allowlistも拡張しない。
2. 通常のreviewとmerge/promotionを通じて、versioned bridgeをapproved `main` releaseへ載せる。draft research PRの状態だけではRailway workerを起動できない。
3. Railwayで既存serviceを維持したまま、owner管理の期待IDを持つManager専用staging service/volumeを作成する。`rootDirectory=products/manager`、`deploy/owned-digital/Dockerfile`、one replica、`/data/manager` mount、hourly cron、owner enablementとintervalを設定。Railway側のdispatch tokenとGitHub側のprotected `MANAGER_OWNER_ID` / `MANAGER_RELEASE_ENABLED`を別々に登録する。
4. 実ホストでread-only preflight、single-owner lock、SIGTERM、volume permission、backup/isolated restore/quarantine、停止・health・費用記録を確認した後、レビュー済みcanaryを1回だけ実行する。exact workflow run、request ID、gh-pages commit/parent/7 files、独立served bytesを別経路で照合する。UNKNOWNなら停止して照合し、再送しない。
5. 再起動、restore、1-slot catch-up、replay-zero、rollback境界を実service上のreceiptで記録してreviewする。証拠が揃った場合だけproduction promotionとE16受入を別途判断する。人への便益や持続効果は別の評価・実験なしにverifiedとしない。
6. E16受入後にF005→F006→F008→F009の順で別々に判定する。これらが通ったあと、顧客・収益・応募・記事・書籍の実績を証拠に基づいて進める。

## 開発確認

`products/manager` で `python -m unittest discover -s tests -q`、`python scripts/check_boundaries.py`、`python scripts/make_roadmap.py --check`。ブラウザは既存catalogから `output/service/site` をrenderして `npm --prefix tests/e2e test`。read-only CIは当該研究branch向けで、production promotion gateの代替ではない。

`python scripts/run_owned_digital_cycle.py --state-store <private-state>` の現状の正しい結果はexit 2 / DEPLOYMENT_HOST_REQUIRED。本番writeは行わない。この状態を隠すためにフラグを変えない。既存公開siteは別の旧sourceから配信されており、今回のE16配備と混同しない。
