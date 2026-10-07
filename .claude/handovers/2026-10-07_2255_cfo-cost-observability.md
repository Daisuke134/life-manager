# CFO引継ぎ — 2026-10-07 22:55 JST

メール・Telegramは送らない。新session用Goalは隣の`2026-10-07_2255_cfo-cost-observability-goal.txt`。送信前に必ずfresh readbackする。

## 正本とcursor

- repo: `/Users/anicca/Projects/life-manager-main`。
- 今回の編集対象spec: `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-cost-observability-evidence-20261007/docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md`。
- remaining-TODOの唯一の正本: `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-cost-observability-evidence-20261007/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` の「2026-10-07 JST — CFO cursor更新」内「Atomic remaining TODO — active order」。main上の最新記録ではcursor=`A4.1`、順序=`A4.1→A4.2→A4.3→A5→A6→A3 conditional→A7→A8→A9→A10`。
- SSOTを持つ別worktreeはlease中。cursorや完了状態をこのspec-only branchから勝手に変更しない。

## 今回の確認済み事実

- 公式Google Cloud Cost Tableの2026-09 invoice-month画面は税込み合計¥27,889、未丸め合計¥27,889.451251（税抜利用額¥25,354.451251＋税¥2,535）を表示。service別はPlaces ¥9,419.856821、Geocoding ¥7,493.014626、Directions ¥3,271.171127、Gemini ¥5,160.873099、KMS ¥9.530434、Storage ¥0.005144、Run ¥0。個別丸め行合計は¥25,355で、invoice丸め税抜小計より1円高い。これは公式画面readbackで、支払settlement証拠ではない。CSV artifactは未取得で、旧保存値のGemini ¥5,159との差をA6で照合する。
- 6つの見えるGoogle Cloud projectのAPI Keys metadataは24件、うち20件がGeminiを許可、23件はAPI restrictionあり、1件はAPI restrictionなし、全24件にapplication restrictionなし。Console警告は悪用の証拠ではなく、keyとproduction callerの対応は未確定。key文字列は取得・変更していない。caller mapping前にkey変更・rotationをしない。
- BigQuery readはcurrent identityに見えるdatasetが4 projectで0件、他2 projectはAPI未有効。IAMで一覧に見えない可能性があり、全体でdataset/exportが無いとは断定できない。API有効化・export作成はしていない。
- MoneytreeのMUFG表示残高¥504,302はfreshness timestampなし。取得行の最新日は2026-08-24/25、2026-09直接windowは0 rows。これを新鮮な残高、全支出、ゼロ支出とは扱わない。最新company reportは広いcoverage gapを持ち、唯一の確認済みloop MRR USD20.34はmobile-appsのsubscription MRRで、settled revenue/netではない。
- 仕様差分の独立read-only reviewは算術とBigQuery/API-key解釈に重大指摘なし。ただしreviewer自身はCost Table UI/API-key実測を独立再取得していない。

## Git・worktree・外部状態

- spec worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-cost-observability-evidence-20261007`。
- branch/push先: `docs/cfo-a6-bq-availability-20261007` / `origin/docs/cfo-a6-bq-availability-20261007`。
- specと最新main取込の確認済みbaseline: `cb2ad05b1f1a9724113c36b33b7e3133f21919ac`。handover/goal追加commitはその後に作成するため、resume時に必ずlocal/remote HEAD・upstream・dirty stateを読み直す。
- PR #6915はDraft。新headでCI再実行中。最新stateはresume時にGitHubから確認し、CI/reviewを迂回してmergeしない。
- A4 owner worktree `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-a4-1-geocode-20261007`、branch `docs/cfo-a4-1-geocode-20261007`、HEAD `e09a8bcb996b1fdeb24caf7abd5c09f02f0c7867`、active lease owner `codex-cfo-a4-1`。PR #6803はDraftでOSS self-contained boundaryとgitleaksがfailure。A4.1/A4.2実装・fixture/test証拠はこのownerの範囲。SSOTのcursor/evidence更新はSSOT lease解放後に行う。触らない。
- A5 owner worktree `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-a5-cost-visibility-20261007`、branch `feat/cfo-a5-cost-visibility-20261007`、HEAD `980fe86791247fac29b614a0d5da0957e901e087`、active lease owner `codex-cfo-a5`。触らない。
- B7 evidence worktree `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-b7-evidence-persist-20261007`、branch `fix/cfo-b7-evidence-persist-20261007`、HEAD `3138dce2c78c2751096023986842a9e339e1b90f`、active lease owner `lm-cfo-observability-1002`。触らない。
- SSOT writer worktree `/Users/anicca/Projects/life-manager-main/.worktrees/cfo-mobile-evidence-ssot-20261007`、branch `docs/cfo-mobile-evidence-ssot-20261007`、HEAD `528746f20f8a84f6949d02344b99839cd6061e80`、active lease owner `lm-cfo-observability-1002`。触らない。
- 今回の確認では本番設定/API key/DB stateを変更せず、Google API billable call、route、release、Moneytree資金移動、email、Telegram送信も0件。

## 最初の安全な再開

handoverとGoal、両specを読み、fresh fetch後に現在のSSOT cursor、全関連lease、PR #6915/#6803、branchのdirty stateと公式Cost Table/CSV状態をreadbackする。A4/A5/SSOT writerのactive lease中は各worktreeを編集しない。A6は公式CSVを保存してCost Table UI・Monitoring・SKU/期間・税/creditを照合し、旧Gemini額の差を解消する。Google keyはproduction callerとrestrictionを対応付けるまで変更しない。CSVが取れない場合もA7など独立TODOは止めず、未取得を明示する。

