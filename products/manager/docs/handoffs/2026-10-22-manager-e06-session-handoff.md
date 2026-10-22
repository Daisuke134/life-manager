# Manager 次セッション引き継ぎ — E06から再開（2026-10-22 JST）

> **資料の位置づけ:** このファイルは**読み取り専用のスナップショット／引き継ぎ説明**であり、第二のタスク台帳・第二のSSOTではない。以後の作業状態とカーソルは必ず `products/manager/docs/roadmap/tasks.json` の `F009.technical_execution_cursor`, `technical_execution_completed`, `technical_execution_receipts` を現在のGitHub HEADで読み直す。日付やここに記載した値よりSSOTと当該コミットのCI結果を優先する。

**ユーザーからの現在の指示:** 「ここで止める。GitHubファイルを更新し、いま何が動いていて、インパクト・評価・ベンチマークがどこまで実証されたかを正確に説明し、次の新しいChatGPTセッション用プロンプトを残す。」この引き継ぎでは**新たな実装・実API推論・ブログ公開・デプロイ・マージはしない**。

## 1. まず確認するリンクと唯一の順番

- 公式GitHubリポジトリ: https://github.com/Daisuke134/life-manager
- Manager製品ディレクトリ: `products/manager/`。Life Manager本体と異なるプロダクトで、DB・秘密情報・実行責任・権限を共有したとは見なさない。
- 実装・引き継ぎブランチ: `research/manager-e01-e16-execution-20261022`。この引き継ぎの最初に確認したHEAD: `17fb8f84cf3a9b3470f826be61a408210cf32e8b`。
- 実際のSSOT: `products/manager/docs/roadmap/tasks.json`。**113 original Manager IDs: done 69 / todo 41 / blocked 0 / skipped 3**。
- Superpowers実装計画: `products/manager/docs/plans/2026-10-22-manager-core-execution-plan.md`。
- 派生の表示専用バックログ: `products/manager/docs/roadmap/ATOMIC_BACKLOG.md`（生成元は `scripts/make_roadmap.py`）。手書きのSSOTにしない。
- 現在のEシリーズ: **E01–E05がSSOTでPASSED、次のタスクはE06、残りE06–E16の11件**。
- **唯一の実装順:** E01→E02→E03→E04→E05→E06→E07→E08→E09→E10→E11→E12→E13→E14→E15→E16。
- **Phase06の受け入れ判定:** F005→F006→F008→F009（Eタスクより先に実装する命令ではない）。F004/F007は元の外部資金管理者・屋内施設依存を外した `skipped`（**未実施であり成功ではない**）。元スコープの履歴は `docs/verification/PHASE06_V1_SCOPE_ARCHIVE_20261022.json`。
- 2026-10-22時点の修正PR: https://github.com/Daisuke134/life-manager/pull/8526 （当初確認では**OPEN / NOT MERGED**。再開時は最新状態をチェックする）。現在のE実装ブランチは研究作業ブランチであり、main/immutable本番releaseへの統合は**未確認・未実施扱い**とする。

## 2. Managerは何を作るのか：非技術者向け説明

Managerは、人や社会が困る原因を理解し、本人の判断を支え、私たちが管理できる環境を改善して、その結果を検証するエージェント製品。

基本ループ:
1. **観測** — 権利・鮮度・出典・実取得バイトを確認し、現在の公開情報や問題の状態を知る。
2. **理解と候補づくり** — 困っている構造と不確実性を整理する。静観（NO_ACTION）、質問、説明、情報整理、アクセス性改善など複数の選択肢を作る。
3. **比較・安全判定** — 予測を実測だと扱わず、費用・負担・別の人への影響・必要な権限を評価する。
4. **限定的に実行** — 私たちが管理する資産への権限内変更などだけ。モデルの文章は実行許可ではない。
5. **独立した読み戻し** — 外部プロバイダーのコミットと実際に公開されているバイトを確認する。
6. **評価・学習** — 技術的な状態変化と人に起きた効果を分け、負の結果・未知・ロールバックも学ぶ。

目標は「人が言うことを聞いた」「会話が気持ちよかった」だけではなく、人にとって意味のある負担・選択肢・生活条件・自律性の改善。ただし**人の苦しみが実際に減ったことは未測定**である。

## 3. 実際に証拠があること

**Ampersand v0.1:** GitHub Actions上で実認証APIによる推論が成功済み。10件の架空シナリオに対し10セッション、同一セッション内のフォローアップ1件、P0監査チェーン10件を保存。証拠: https://github.com/Daisuke134/life-manager/actions/runs/39713799676、`docs/verification/ampersand-20261022/ten_case_raw.json` と `ten_case_receipt.json`。SHA-256固定済み。外部の人の行動や福祉は**測っていない**。

**Ampersandの記述的結果:** 作成者の10件の事前ラベルに7/10一致。ただし指示調整に使っていない7件ではモデル4/7、常にPASS（NO_ACTION）の比較方式も4/7。**優越性・統計的有意差・一般化・人への介入効果は未証明**。7件も外部独立ベンチマークではなく、同じ研究チームが作成した事例。出力形式の失敗と判断の妥当性も別に評価する必要がある。実API料金の確定支払額は `null`（不明、ゼロではない）。

**公開デジタル環境の技術的実世界成果:** `https://daisuke134.github.io/life-manager/manager-support/` に公式支援情報の案内が実際にある。2026-10-22時点でトップ、finance/mental/physicalの公開ページへ読取専用GETを再確認。2026-10-21の元のP2公開は `docs/verification/PHASE06_DIGITAL_SERVICE_EXECUTION_20261021.md`、所有GitHub Pages commit `9160eb265cdd232e534df49b51c2e9a7aa1a2dfb`、CI https://github.com/Daisuke134/life-manager/actions/runs/39617848783。これはP2_ARTIFACT_ONLY：**公開ページの実体がある／変更された証拠**。誰が利用したか、何分節約したか、苦痛が減ったかは未測定。公的窓口の掲載は、受給・治療・実際の支援結果ではない。

**E01–E05 engineering:** 実験原本固定／P0権限隔離／仮想と観測の型分離／厳格JSONと理由・出典形式／SQLiteセッション意図・UNKNOWN照合・writer fence・SDK公式レスポンス読み戻し。SSOTのE05 receiptは `PASSED`: https://github.com/Daisuke134/life-manager/actions/runs/39744857190、既存セッションへの認証済みread-only検証 https://github.com/Daisuke134/life-manager/actions/runs/39744452856。実際のネットワーク切断を意図的に発生させる live chaos trial は `NOT_RUN`。つまり実障害復旧の完全な実地証明は**ない**。E05の合格は、現在のエンジニアリングテストと読み取り専用readbackの範囲。

**最新の全体回帰:** GitHub Actions https://github.com/Daisuke134/life-manager/actions/runs/39747190062 （HEAD `17fb8f84cf3a9b3470f826be61a408210cf32e8b`）で `python -m unittest discover -s tests -q` → `Ran 560 tests ... OK (skipped=5)`。SSOT `python scripts/make_roadmap.py --check` → `PASS 113 tasks`、source boundary check成功。ここから先のcommitについては次セッションで再検証。

**重要:** 本番Managerが継続自律運用、実験の費用・リスク最適化、ユーザーアウトカム計測、実世界の因果推論までできているとの証拠はない。

## 4. 証拠段階（間違えないための表）

| 段階 | 意味 | 現状 |
|---|---|---|
| P0 | 出典・フィクスチャ・模擬会話・予測・型やテストの証拠 | 実際に多数ある。Ampersand実API10ケースもここ |
| P1 | 許可された外部操作のプロバイダー受付・実行receipt | 所有サイト公開に元記録あり |
| P2 | 実際の公開状態が独立に確認された変化 | 所有サイトに技術的実績あり |
| P3 | 実際の受益者が楽になった、負担が減った等の直接観測 | **NOT_MEASURED** |
| P4 | P3変化がManager介入によると比較で支持された因果的純便益 | **NOT_ESTABLISHED** |
| P5 | 別条件・別地域等への実地再現性 | **NOT_ESTABLISHED** |

**人間への実証インパクトがあるとはまだ言えない。** しかし公開情報が届く環境へ技術的に影響したという具体的なP2はある。

## 5. Eval/Benchmarkは全部終わったのか？

**NO。** R&Dの基礎やフィクスチャ検証は進んだが、以下が未完成。
- **E06:** 実APIの予約予算・確定請求額・使用量不明・処理期限・合法的沈黙・キャンセル・UNKNOWNの会計と制御。
- **E07:** 有用な質問と不要な割り込み、形式エラー、プライバシー、安全違反を**別指標**にした採点規則の凍結。
- **E08:** 比較方式（NO_ACTION・ルール・Ampersand）へ同じ入力と予算を提供。シナリオ系列で開発/評価を分離し、複数回測って不確実性を報告。保留7件4/7だけで勝利宣言しない。
- **E09:** 実参照データに対する予測誤差の校正と、分布外時の回答抑制。データがなければ `REFERENCE_DATA_REQUIRED`。
- **E10–E11:** 公式公開ソースへの真正な観測と、変更された現実状態の版管理。
- **E12–E16:** NO_ACTION付き候補生成、実行前検査、所有デジタル媒体への許可済み接続、exact-once/replay-zero、継続実行・独立readback・rollback。
- **S1–S3 / V001–V006:** Persimmon等の利用可能性、人物属性ドリフト、sim-to-real校正、独立ホールドアウト、実際の政策昇格/取り消し、複数実地事例、異なる領域での検証。現実効果を勝手にP4へ昇格させない。

元のManagerタスク台帳も、`69 done / 41 todo / 0 blocked / 3 skipped`。Eシリーズの11件と元の41件は**別粒度**であり、足し算して進捗率を偽らない。

## 6. 次の新セッションで最初に行う作業（E06）

1. 必ずGitHubの現在HEADと `tasks.json/F009.technical_execution_cursor` を読み、**まだE06であること**を確認。すでに他のワーカーがE06を終えた場合はE07以降へ正しく進む。何も読まずE05を再実装しない。
2. `AGENTS.md` と `superpowers:using-superpowers`, `executing-plans`, `test-driven-development`, `verification-before-completion` を読んで、branch/worktree隔離・red→green→全テストを守る。
3. `docs/plans/2026-10-22-manager-core-execution-plan.md` の**E06節**をそのまま実装ブリーフとして使う。新たな実装前に公式Ampersand Agents APIの最新仕様、現在の `manager_core/ampersand_api.py` / `provider_sessions.py` / `scripts/phase_ampersand_lab.py` と既存の予算モジュールを再読する。
4. **E06テストを先に追加（RED確認）**：使用量未取得を0扱いしない、所定予算以上の新リクエストを拒否、タイムアウトでcancel/UNKNOWN照合、正常な沈黙をエラーや成功した行動と混同しない、キャッシュ入力/推論出力を過少計上しない。
5. 最小コードを足し、専用テスト・全ユニットテスト・境界・SSOT生成一致をGitHub Actionsで検証。**実課金のテストは上限と秘密情報と必要な権限の確認があるときだけ**。現場権限や継続実行ホストが未確認ならfail-closed。
6. 正しい合格receiptを保存してから `tasks.json` のE実行カーソルを**E07**へ進め、`ATOMIC_BACKLOG.md` を生成し直す。E06が未完成ならカーソルはE06に残す。次のEへ跳ばない。
7. E07→E16を同じ手順で**順番に**行う。F005/F006/F008/F009は実装工程ではなくEが作った実証の受け入れ判定。E完了がそのまま人間へのP3/P4達成とはならない。
8. 記事・書籍・プレゼン・カルーセル・漫画・`aniccaai.com` 更新の別レーンは `docs/plans/2026-10-22-manager-research-products-plan.md` に沿う。今回の引き継ぎでは公開操作を実施していない。公開の前後を必ず外部読み戻しする。

## 7. 事故・セキュリティ・Git運用メモ

- ユーザーが以前チャットへ書いた認証情報は露出済みとして交換を促す。**APIキー、Googleパスワード、暗号化トークン、実個人プロフィールをGitHub、チャット、CIログ、発表資料へ貼らない**。既存のGitHub Actions `AMPERSAND_API_KEY` シークレットの実値も共有しない。
- 2026-10-22 の `F004/F007` 外部基金・屋内施設ゲートは **skipped/waived**。これは他人の銀行口座、設備、非公開記録を無断操作してよいという意味ではない。
- 一時的なGitHub Actions CIランナーは継続運用用の永続DB/leaseホストではない。E16ではホスト・監視・復旧、権限運営者の確認が必要。
- 既存の `research/manager-ampersand-integration-20261022`、`research/manager-roadmap-refinement-20261022`、`research/manager-phase06-owned-public-good-20261022` と現作業ブランチの履歴を勝手に混ぜたり上書きしない。**SSOTは現在作業ブランチの `tasks.json` が基準**であり、最新 `origin/main` との統合は別のレビュー作業。
- 旧Phase06の54分解や古いスクリーンショット、旧PRが「FをEより先に」と示していても、**現行順はE01–E16**。生成バックログ冒頭が現在カーソルを示す。
- 本書の記載コミットはスナップショット。新セッションで `git status`、GitHub HEAD、保留PR、CIとSSOTを必ず再検証。ソースが進んでいた場合、ここを上書きせず新たな結果を版付きで追記。
- 本引き継ぎは**静的なhandoff書類**。新しいバックグラウンドタスクや定期ジョブを開始しない。

## 8. そのまま新しいセッションへ渡す日本語プロンプト

私は `Daisuke134/life-manager` の独立製品 `products/manager/` を開発しています。Superpowersの `using-superpowers` と `executing-plans`、`test-driven-development`、`verification-before-completion` を読み、**コードを実際に編集してテストしてからGitHubへ証拠を残す**作業を再開してください。

必ず最初にこの引き継ぎファイル `products/manager/docs/handoffs/2026-10-22-manager-e06-session-handoff.md`、`AGENTS.md`、`products/manager/docs/roadmap/tasks.json`、`products/manager/docs/plans/2026-10-22-manager-core-execution-plan.md` と実装ブランチ `research/manager-e01-e16-execution-20261022` の**最新HEADとCI**を確認してください。以前はE01–E05が合格し、次のカーソルはE06でした。しかしこのスナップショットを盲信せず現在のSSOTを再確認してください。

進め方は**E01→E02→…→E16を一件ずつ**。終わったタスクは再実装せず、次の未完了タスクから RED→GREEN→全テスト→GitHubコミット/CI→SSOT receipt 更新→カーソル更新の順で実行してください。E06はAPIコスト・時間制限・合法的沈黙・キャンセル照合。実際のプロバイダーへの通信は公式資料の契約を確認し、守られた秘密情報・上限予算・権限がある場合だけ。失敗/不明をゼロや成功にしないでください。

重要: Model P0、公開サイトの技術的P2、人間へのP3/P4を分けること。既存の10ケースでモデルの保留7ケース一致は4/7でNO_ACTION方式も4/7、優位は未証明。人の苦しみが減ったことは未測定。F004/F007は必須から廃止され未実施。F005→F006→F008→F009はE実装の後の証拠受け入れ判定で、Eより先に行う別の実装順ではない。現行状態は113タスク69 done / 41 todo / 3 skippedだった。更新時は現在の記録で判断してください。

研究・日英記事・書籍・プレゼン・カルーセル・漫画・公式サイトの制作も既存計画で管理しています。ただし製品、原稿、公開済みURLは別です。無断の外部アカウント操作、未承認の資金移動、個人情報収集、権限の自動拡大、証拠なしの「人の幸福改善」主張をしないでください。完了できない項目は具体的理由・対象ファイル・検査方法をSSOTと引き継ぎに残し、できる次の独立作業を進めてください。

回答は日本語で、**実際に完了・テスト済みのもの／未検証のもの／次のAtomic To-do**を分けて報告してください。
