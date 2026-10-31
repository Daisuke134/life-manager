# Capafy icon source contract repair

目的: Security Scan run 41182890170 の唯一のOSS境界違反を修復する。
範囲: football-in-match-change-brief の既存画像に、他の商品と同じ asset-manifest.json を追加する。画像・検証器・公開商品は変更しない。
完了条件: 修正前FAIL再現、修正後OSS境界と既存テストPASS、PR/main統合後Security Scan成功。Dots応募重複チェックは別の実行経路と結果で検証する。
根拠: https://github.com/Daisuke134/life-manager/actions/runs/41182890170

原因: icon.png の実バイトのdigestが追跡JSONで宣言されていない。
比較先: skills/capafy/catalog/football-scoreline-scenario-card/asset-manifest.json。
修正前実測: node scripts/verify-oss-self-contained.mjs は generated_artifact 1件、exit 1。

環境: 最新main 8df675eec4c0352fd6482e1fa1b57dbafd9ffc5b を取得した専用linked worktree。既存canonical Git metadataはsandbox書込範囲外なので本workspaceの専用bare repositoryを使用。verify-source-boundary.sh の固定root要件は満たさない。既存checkout/owner/releaseは変更しない。

検証結果: manifest追加後のOSS検証PASS、既存OSSテスト12/12 PASS、git diff --check成功。scripts/test_ledger_check.py は6/6 PASS。追跡main由来台帳で既存キーlancers:5620321はBUSY(exit1)、存在しない確認用キーはFREE(exit0)。claim作成・応募送信は行わない。

PR: https://github.com/Daisuke134/life-manager/pull/9068 。PR CIのOSS境界は成功。全CIとmain統合結果はGitHub PR/checksを正本にする。

残る外部条件: Dots自身の実行環境での再検証は未確認。同ルームはteam/COMMS.mdからSlack #agents-hqと特定したが、Slack/Reasonのsendはいずれもapproval policy neverで拒否。未送信報告は作業workspaceのteam-outbox/AGENTS-HQ-REPORT.mdに保存する。CIのソース修復とこれらの外部条件は別々に判定する。
