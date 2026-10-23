# Monk Factory Web 実装計画

**Goal:** 公開draft workspaceと、既存Factoryへ接続する同一UIのlocal Web appを公開する。

**Architecture:** Life ManagerのUIを正本にし、Node標準HTTPのlocalhost serverから既存Factory MCP/CLIを呼ぶ。productsはmain SHAと4filesのSHA256を固定して同UIをstageする。有限Codexは利用者のmodel/provider/auth設定を継承する。

**Tech Stack:** Node 24.16+/npm 11、既存MCP SDK/Zod、Python、native ffmpeg/ffprobe、plain HTML/CSS/JavaScript。

**Spec:** docs/superpowers/specs/2026-10-23-ai-monk-factory-web-design.md

## 担当・境界
- 日次自社投稿はGrok Botが所有する。自社Postiz/HeyGen、稼働loop、未完effect、容量復旧を操作しない。
- 新依存、hosted credential/課金基盤、model/provider指定を追加しない。
- 1runの入力を固定し、既存renderer/publisher/receipt/fenceを保持する。取得済みCLI receiptはframe抽出前に1回保存する。
- 公開Webはdraft編集、制作実行はlocalhost。公開HTTPSからlocalhost APIへfetchしない。
- primaryは仕様・UI・統合・完了判定、workerはruntimeと指定testsを所有する。

## Task 1: server-bound runtime
- [x] exact Host/Origin/token、body/ID/未知field/path/symlink拒否を実装する。
- [x] project/run永続化、入力snapshot、mode権限、予約段階からのshutdown中断・完了待機を実装する。
- [x] 既存callFactoryTool/runCli、run固有MCP名、同じplugin-offでのinventory、approval_policy=never、有限Codexを接続する。
- [x] 実動画receiptからserverが3frameを抽出し、asset/frame hash・AI reviewer・notesを固定する。任意画像を受理しない。
- [x] 全tool履歴の費用未照合・CLI失敗を保持し、後続statusで隠さない。抽出中断でも元receiptを失わず、二重計上しない。

## Task 2: 同一UI
- [x] 12fieldsのproject v1、draft保存、shared validator、UTF-8 65536byteのexport/importを実装する。
- [x] project/brief/商品/チャンネル、plan/render/publish、履歴・実exit・動画/receiptを表示する。
- [x] 公開URLで35,473byteの日本語draftを実downloadし、同じfileのimport・保存・reloadを確認する。
- [x] localhostで空scriptから実Codexが165文字の台本を作り、実MCP→Python CLIでplanned/exit0となる。
- [x] 公開/localhost双方で1360/390幅、JSerror0、横overflow0、履歴復帰を確認する。

## Task 3: 統合と公開
- [x] 関連37件PASS、独立レビュー最終blocking0、Security Scan39964362189全成功を確認する。
- [x] LM PR8721をmain eb78a805c4f79cd807852c27f52f9e4207a1ba61へ統合する。
- [x] 専用LOOPS_ROOT/LM_DATA_DIRにmain由来immutable app releaseを作る。既存current/loopを切り替えず、protected memoryをexportしない。11関連fileのmain bytes一致・書込不可を確認する。
- [x] products PR602/main fcbe8ec027bcc78825f5e50e0d83d0926a036525、Netlify39967298318成功を確認する。
- [x] https://aniccaai.com/ai-monk-factory/ とslash無し入口、4fileのmain hash、Databaseリンク、73cards/69候補注記の保持を確認する。
- [x] S11と本計画へ受入結果と未達を記録する。

## 検証と最小修正
37件はHTTP/永続化/mode、実SDK stdio、実Python offline plan、実ffmpeg/ffprobe、所有process group回収を含む。独立レビューで見つかった偽frame・shutdown競合・費用履歴の隠蔽・日本語file上限・抽出中receipt欠落はRED→GREENで修正する。実user設定のCLI loadも既存MCP無効/新run1件有効を確認する。CIは既存repoのNode24.16/npm11へ揃え、依存版/lockを変更しない。

## 根拠
- docs/evidence/ai-monk-factory-web-source-20261023.json
- docs/evidence/ai-monk-factory-web-local-20261023.json
- docs/evidence/ai-monk-factory-web-production-20261023.json

## 現在cursor・未達
この公開workspace/local plan受入は完了する。無料plugin ZIP v0.1.1も公開するが、ChatGPT/Codex公式directory掲載、Museサービス特定、実生成/投稿/native確認、売上/他者無人収益/USD10K MRRは未達として扱う。次は直接install可能な配布導線。公式掲載の通常Google SSOは既存persistent contextで通過し、OpenAI MFA passkeyに留まる。指定cua-driver skill不在でnative UIは未操作とし、掲載済みと呼ばない。API成功や生成fixtureを実収益の証拠に置換しない。
