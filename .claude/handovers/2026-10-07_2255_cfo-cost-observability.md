# CFO引継ぎ — 2026-10-07 23:11 JST更新

メール・Telegramは送らない。新session用Goalは隣の`2026-10-07_2255_cfo-cost-observability-goal.txt`。送信前に必ずfresh readbackする。

## 正本とcursor

- repo: `/Users/anicca/Projects/life-manager-main`。
- 今回の編集対象spec: `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-cost-observability-evidence-20261007/docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md`。
- remaining-TODOの唯一の正本: `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-cost-observability-evidence-20261007/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` の「2026-10-07 JST — CFO cursor更新」内「Atomic remaining TODO — active order」。main上の最新記録のcursorは`A4.1`、記録された旧順序は`A4.1→A4.2→A4.3→A5→A6→A3 conditional→A7→A8→A9→A10`。
- Daisの新しい明示指示による優先順は`A5→A6→A7（既存Moneytree接続を一度bounded read-only確認。失敗/古い場合はunknownで続行）→A8→A9→A10→A4.1→A4.2→A4.3→A3.4 conditional`。理由は無料geocoding最適化より先に会社の実売上・実費とCFO報告を成立させること。Moneytreeの再認証に固執せず、個人財務coverageはpartial/unknownを明示して事業CFOを進める。
- この優先順はdesign specに記録済みだが、leased SSOTにはまだ未反映。SSOTを持つ別worktreeのactive lease中はcursor・TODOを編集しない。lease解放後にownerが順序/cursorを正本へ同期するまで、SSOTが既に変わったとは主張しない。

## 今回の確認済み事実

- 公式Google Cloud Cost Tableの2026-09 invoice-month画面は税込み合計¥27,889、未丸め合計¥27,889.451251（税抜利用額¥25,354.451251＋税¥2,535）を表示。service別はPlaces ¥9,419.856821、Geocoding ¥7,493.014626、Directions ¥3,271.171127、Gemini ¥5,160.873099、KMS ¥9.530434、Storage ¥0.005144、Run ¥0。個別丸め行合計は¥25,355で、invoice丸め税抜小計より1円高い。これは公式画面readbackで、支払settlement証拠ではない。CSV artifactは未取得で、旧保存値のGemini ¥5,159との差をA6で照合する。
- 6つの見えるGoogle Cloud projectのAPI Keys metadataは24件、うち20件がGeminiを許可、23件はAPI restrictionあり、1件はAPI restrictionなし、全24件にapplication restrictionなし。Console警告は悪用の証拠ではなく、keyとproduction callerの対応は未確定。key文字列は取得・変更していない。caller mapping前にkey変更・rotationをしない。
- BigQuery readはcurrent identityに見えるdatasetが4 projectで0件、他2 projectはAPI未有効。IAMで一覧に見えない可能性があり、全体でdataset/exportが無いとは断定できない。API有効化・export作成はしていない。
- MoneytreeのMUFG表示残高¥504,302はfreshness timestampなし。取得行の最新日は2026-08-24/25、2026-09直接windowは0 rows。これを新鮮な残高、全支出、ゼロ支出とは扱わない。最新company reportは広いcoverage gapを持ち、唯一の確認済みloop MRR USD20.34はmobile-appsのsubscription MRRで、settled revenue/netではない。
- 仕様差分の独立read-only reviewは算術とBigQuery/API-key解釈に重大指摘なし。ただしreviewer自身はCost Table UI/API-key実測を独立再取得していない。

## Git・worktree・外部状態

- spec worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-cost-observability-evidence-20261007`。
- branch/push先: `docs/cfo-a6-bq-availability-20261007` / `origin/docs/cfo-a6-bq-availability-20261007`。
- specと最新main取込の確認済みbaseline: `f1566f3396893e922c044cfc6eeed20e0fdf830d`。handover/goal更新はその後に作成するため、resume時に必ずlocal/remote HEAD・upstream・dirty stateを読み直す。
- PR #6915はDraft。最新main `3519bd4f23`を取り込んだため、更新をpush後に新headのCIを再確認する。CI/reviewを迂回してmergeしない。
- A4 owner worktree `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-a4-1-geocode-20261007`、branch `docs/cfo-a4-1-geocode-20261007`、HEAD `e09a8bcb996b1fdeb24caf7abd5c09f02f0c7867`、active lease owner `codex-cfo-a4-1`。PR #6803はDraftでOSS self-contained boundaryとgitleaksがfailure。A4.1/A4.2実装・fixture/test証拠はこのownerの範囲。ユーザー新指示によりA4 laneはCFOのA5–A10の後へ延期。既存worktreeを壊さず、触らない。
- A5 owner worktree `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-a5-cost-visibility-20261007`、branch `feat/cfo-a5-cost-visibility-20261007`、HEAD `980fe86791247fac29b614a0d5da0957e901e087`、active lease owner `codex-cfo-a5`。触らない。
- B7 evidence worktree `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-b7-evidence-persist-20261007`、branch `fix/cfo-b7-evidence-persist-20261007`、HEAD `3138dce2c78c2751096023986842a9e339e1b90f`、active lease owner `lm-cfo-observability-1002`。触らない。
- SSOT writer worktree `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-mobile-evidence-ssot-20261007`、branch `docs/cfo-mobile-evidence-ssot-20261007`、HEAD `528746f20f8a84f6949d02344b99839cd6061e80`、active lease owner `lm-cfo-observability-1002`。触らない。
- 今回の確認では本番設定/API key/DB stateを変更せず、Google API billable call、route、release、Moneytree資金移動、email、Telegram送信も0件。
- AGMSG identity lookupは複数候補だったため、そのskillの要件に従い送信者を推測せずowner宛メッセージは送っていない。Telegram/email通知もしていない。

## 最初の安全な再開

handoverとGoal、両specを読み、fresh fetch後に現在のSSOT cursor、全関連lease、PR #6915/#6803、branchのdirty stateと公式Cost Table/CSV状態をreadbackする。まずA5→A6を進め、A7は既存接続を一度だけread-only確認する。Moneytreeが未接続/古い場合はunknownを記録してA8/A9/A10へ続行する。A4/A5/SSOT writerのactive lease中は各worktreeを編集しない。A6は公式CSVを取得できる経路を確認し、Cost Table UI・Monitoring・SKU/期間・税/creditを照合して旧Gemini額の差を解消する。Google keyはproduction callerとrestrictionを対応付けるまで変更しない。SSOT order/cursorはlease解放後にowner境界を守ってCFO-first順へ同期する。
