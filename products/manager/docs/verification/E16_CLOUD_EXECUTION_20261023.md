# E16 — cloud実行と残る受入れ（2026-10-23 UTC）

現在の実行先は、既存GitHub Actions ownerと既存Supabase stagingの非公開checkpointです。Mac mini、Railwayの新worker・volume、長期tokenの新規提供は再開条件ではありません。本記録は過去のhost未接続という説明を更新します。Manager原113件の研究台帳は、継続branchの [固定版tasks.json](https://github.com/Daisuke134/life-manager/blob/64c05479d229bdcb95c619f38759fa5e7ad3d9ca/products/manager/docs/roadmap/tasks.json) を参照します。Life Manager全体の統括SSOTを置き換える新台帳は作りません。E16は未完了です。

## 実施して確認したこと

- Gateway: [PR8573](https://github.com/Daisuke134/life-manager/pull/8573)、main `4c565f83e35211dd821f7aac3d532fc11c324f87`。既存 `life-manager-staging-20260808` に専用table/RPCとEdge function `manager-owned-state` v1を適用。匿名POSTと不正tokenは401、GETは405。RLS/FORCE、anon/authenticatedの権限なし、service_roleのINSERT権限なしを実確認しました。既存の他table/serviceは変更していません。
- 共通runtime: [PR8577](https://github.com/Daisuke134/life-manager/pull/8577)、main `d00288f59b3a4ecde2133ecdada8458623c699fe`。既存cycle、selector、publisher、private checkpointをmainの単一workflowに接続。研究branchへのsource allowlist変更はありません。
- 旧writer退役: [PR8576](https://github.com/Daisuke134/life-manager/pull/8576) は既存legacy branchへ統合。自然push [39880994343](https://github.com/Daisuke134/life-manager/actions/runs/39880994343) は成功、publish/verify-liveはSKIPPED。共有writer concurrencyと既存Pages workflow `307239134` を保持しました。
- 初回状態移行: 過去7件の元v1 packet、元の公式job log、commit/parent、公開7ファイルと歴史的P2を照合。新しい送信許可を作らず、PRESENTと過去deliveryだけを非公開SQLiteへ保存。最新Manager commit `d33d251ec0b82bf541a727ead7d1ede39f0a8216` と実配信bytesの一致を再確認しました。90112-byte画像のSHA256は `03ed0d23a8b24f260acb0ae51fe063b6fc6ec2a23a6e6f3e93035f7b9c9971bd`。既存rowがある場合は拒否するatomicな初回INSERT後、row1/revision0/ownerなし/recovery_required=falseを確認しました。画像・packet・private journalはGitや公開artifactに置いていません。
- 初回実main実行: [39882336050](https://github.com/Daisuke134/life-manager/actions/runs/39882336050)、source `2c945b7b3890af40a07f9938cc9830f56403ab4a`、2026-10-23 01:08:59–01:12:29 UTC、verify/publisherともSUCCESS。公式summaryは `authentication=GATEWAY_ACKNOWLEDGED`, `status=NO_ACTION`, `reason=MISSING_TYPED_CANDIDATE`, `writes=0`, `positive_canary=NOT_RUN`, `E16_ACCEPTANCE=INCOMPLETE`。実GitHub OIDCで復元・checkpoint更新・解放を通過しました。実DBのrevision1、90112 bytes、owner/leaseなし、recovery_required=falseも別に読み戻しました。NO_ACTIONは公開変更の実証ではありません。

## 続行中の受入れ

1. 別のfresh runner [39882784491](https://github.com/Daisuke134/life-manager/actions/runs/39882784491) は2026-10-23 01:22:53 UTCにSUCCESS。公式summaryで `GATEWAY_ACKNOWLEDGED / NOT_DUE / writes=0`、実DBでrevision2・同じ90112-byte snapshot hash・owner/leaseなし・recovery_required=falseを確認しました。公開全7ファイルのhashとgh-pages tipが元のd33dから変わっていないことも独立に読み戻しました。これで実OIDCとcross-run restore/replay-zeroの限定受入れは成立。正のcanary・停止/復旧の受入れを続けます。
2. 実在する改善としてfinance/mental各ページの一意なself navigationへ `aria-current="page"` を付与するversioned typed criterionを追加する。旧v1 link/label検証は維持する。これはW3Cに沿う位置情報の付加で、WCAG違反や人への便益を主張しません。
3. private checkpointを跨ぐSTOPと、当該candidateだけを対象にした明示的CAS rollbackを既存journal/publisherへ接続する。lag・timeout・hash mismatchだけではrollbackしません。
4. exact P1と独立served P2を、既存Explorer/shadowへ元の単位と欠測理由で接続する。sandboxのlossや人間の成果へ読み替えません。
5. reviewed mainで限定canary、別テーマのP1/P2、restart/catch-up、STOP/rollback、replay-zero、対象外不変を実観測してからE16を判定し、その後F005→F006→F008→F009を個別に受け入れる。

新しい有料resource・upgradeは作成していません。Actionsの開始時刻は保証されず、既存catch-up-onceを用います。費用の実請求や無制限無料稼働は未認定。人の行動変化・苦痛低減はNOT_MEASUREDです。Mac専用source-boundary guardはcanonical path不在でFAILのままです。所有者の明示的なcloud作業指示に従って専用worktreeで開発しており、このguardをPASSと表示していません。
