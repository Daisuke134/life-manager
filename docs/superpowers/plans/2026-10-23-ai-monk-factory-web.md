# Monk Factory Web 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 公開draft workspaceと、既存Factoryへ接続する同一UIのlocal Web appを公開する。

**Architecture:** UIの正本をLife Managerに置き、Node標準HTTPのlocalhost serverから既存Factory MCP/CLIを呼ぶ。公開productsはimmutable mainから同UIをstageする。有限Codexは利用者の既存model設定を継承する。

**Tech Stack:** Node 20.19+標準API、既存MCP SDK/Zod、plain HTML/CSS/JavaScript、既存Python Factory。

**Spec:** docs/superpowers/specs/2026-10-23-ai-monk-factory-web-design.md

## Global Constraints
- 日次自社投稿・稼働loop・既存effect・credential・容量運用を変更しない。
- 新依存・hosted credential/課金基盤・モデル指定を追加しない。
- 1runのinputを固定し、既存renderer/publisher/fenceの判定を保持する。
- public/localは同一UI、APIはlocalhost same-origin/token限定。
- primaryはspec/plan/UI/統合、workerはserver/MCP/関連testsを所有し、commitはprimaryへ一本化する。

## Review Focus
- project編集/再起動/失敗で既存runの再送や成功偽装が起きない。
- hostile Host/Origin/token/未知field/path/symlinkで別ファイル/CLIへ到達しない。
- plan/render modeからproductionへ到達しない。
- agent文章とCLI/provider receiptを区別し、unknown/null/nonzeroを保持する。
- publicページがlocalhost APIへ接続せず、draft export/importとlocal移行が実際に動く。

### Task 1: server-bound runtime
Files: factory-web/server.mjs, factory-web/agent-mcp.mjs, factory-web/server.test.mjs、既存README。
Interfaces: GET /api/projects -> {projects}; POST /api/projects {project} -> {project}; POST /api/runs {project_id, mode} -> {run}; GET /api/runs -> {runs}; GET /api/runs/<run_id> -> {run}; GET /api/runs/<run_id>/video -> 検証済みasset。全APIは x-factory-token を要求する。HTMLの __FACTORY_TOKEN__ を起動tokenへ置換する。run shapeは run_id/project_id/mode/state/exit_code/created_at/updated_at/tool_results/summary/artifact_url、未確定値はnull。
- [x] 実HTTPのtoken/Host/Origin/body/ID拒否、project永続化とsnapshot不変、mode制限、nonzero/unknown、reload後run復帰、agent argvにmodel指定無しの最小REDを観測する。
- [x] 既存callFactoryTool/runCliを使うserverと固定project MCP、有限agent起動を実装する。
- [x] focused testsをPASSし、外部provider0の実CLI planとHTTP readbackを記録する。

### Task 2: 同一UI
Files: factory-web/index.html, app.css, app.mjs, app.test.mjs。
Interfaces: project v1とTask1 APIを使う。UIはrootが __FACTORY_TOKEN__ を置換した時だけlocal。publicではbrowser draftのみ。実行actionはplan/render/publishの単一run、stateはserver結果を表示する。
- [x] draft validation/export/import/local判定の最小REDを確認する。
- [x] accessible form、保存/実行、run履歴/状態、動画/receiptを実装する。CSPに合わせた外部JS/CSSのみ、innerHTMLによるユーザー文字列挿入を使わない。
- [ ] related testsと実localhostの保存/plan、public draft操作を検証する。publicの実ブラウザ保存/export/importと1360/390幅はPASS、local API接続の最終受入を残す。

### Task 3: 統合と公開
- [ ] fresh read-onlyレビューでTask1/2の実害を反証、必要fix後focused検証、source acceptance/CI/main。
- [ ] main由来固定版のlocalhost起動とprovider0 planをreadbackする。
- [ ] productsの既存buildにUI4filesのimmutable SHA/hash stageを最小追加し、Databaseからリンクする。source/test/CI/main/Netlifyと公開draft/local起動導線を確認する。
- [ ] S11/field-guide現在cursorと本計画へ実結果/残件を記録する。公開を実収益や他者provider成功と取り違えない。

## source検証
新Factory focused21件と既存Factory MCP11件をCI=trueで実行し32 PASS/0 FAIL/0 SKIP。実SDK stdioから既存Python CLI planのprovider_calls0/external_effects[]を確認。PC1360/スマホ390の実browserでdraft保存/export/import、JSerror0/overflow0。最初の29件runでは既存output_limit fixtureがNode cold startより短い200ms timerと競合しtimeoutとなるため、output caseだけ3sの別deadlineへ修正し64byte上限判定を維持する。EOF fixture内assertがouter agent catchで隠れる問題は失敗理由と所有PID状態を残す診断を追加し、isolateと全29件でPASSを確認する。renderer/publisherのproduction sourceやguardは変更しない。fresh read-onlyレビューとCI/main/固定版を次cursorとする。

## Codex設定loadの修正と受入
モデル起動前のread-only reviewer起動はinvalid transport in mcp_servers.code-reviewでexit1となる。通常inventoryがplugin仮想MCP名も返す一方、実行でpluginを無効化すると元transportが消え、enabled=falseだけのoverrideが無効になる。モデル開始/外部provider操作は0。inventoryにも同じfeature無効化を適用し、既存HTTP名factoryとの衝突を避けるrun固有MCP名へ接続する。実user設定のCLI loadで既存6件無効・新run1件だけ有効を確認し、credential無しfixtureのHTTP名factory/生成名衝突もPASSする。approval_policy=neverで承認待ちを防ぎ、model/provider指定は0。fresh read-onlyレビューは修正後の設定で再開する。公開assetは末尾slash有無に依存しない/ai-monk-factory/絶対pathとlocal固定aliasへ揃える。

## fresh review修正cursor
独立read-onlyレビューは変更0で3 blocking/1 nitを再現する。検証済み動画からserver抽出したframe/hashへの固定、予約中shutdownの中断/完了待機、run全体の費用未照合/失敗集約、日本語draftのUTF-8上限統一を最小REDから修正し、関連testsと差分レビュー後にCI/mainへ進む。実provider/日次投稿は操作しない。

3 blocking/1 nitは旧REDを観測して最小修正する。関連4file suiteは36 PASS/0 FAIL/0 SKIP（実SDK stdio、実Python offline plan、実ffmpeg/ffprobe抽出と画像hash、EOF所有子孫回収を含む）。停止予約/費用未照合/偽frame/日本語file往復の回帰を含む。差分fresh reviewを実行中。実Codex plan/local browser受入・CI/main・immutable releaseは次cursorのまま保持する。
