# Manager — 既調査の繰返しを除いた追加選択肢と実装判断

2026-10-22 UTC。baseline `ae06f4ccfa30b29e427f71d6413eba0858a34cf8`。前回の仕様更新を受け、「既知の名前ではなく、新しい一次資料と実コードから選択肢を広げる」という依頼への追加調査。[製品仕様](../../MANAGER_PRODUCT_SPEC.md)と[atomic patch plan](../../plans/2026-10-22-manager-e16-atomic-patches.md)に接続する。

## 何を追加し、何を新規に数えなかったか

5つの独立調査laneとhost比較を並行実施した。Firecrawlのweb/developer検索、公式page取得、paper metadata/body passages/citation探索、別のweb検索系統、公式GitHub metadataとread-only cloneを利用。arXivは正式ID/版を確認した。専用Parallel/Alpha Archive pluginを使ったとは主張しない。無関係なhealth/金融/個人ファイルpluginは呼ばない。

候補名を既存research/landscape/presentations/specと照合した。LangGraph/Temporal/Letta/OpenHands/Simile/Aaru/Radiant/Inspect/Railway、および既存資料にあるAgentSociety/OASIS/AgentTorch/TinyTroupe/TheAgentCompany/τ-bench/τ²-bench、Quarto/Postizは新規発見へ計上しない。AgentSociety 2とττは既知familyの未読論文/別benchmarkと記す。「ローカル資料の検索で未登場」は、ユーザーが過去に一度も見たことがないという主張ではない。

新しい名前を列挙して終わらず、永続実行4実装、個人/業務agent4実装、browser/action3実装、exporter3実装を固定sourceまで読んだ。さらに6本の未読論文と5つの関連公式repoを調べた。これは全repository/全論文の読了、動作試験や独立再現を意味しない。release tagとdefault-branch package versionが違う場合もそのまま残す。

## 新しい選択肢と採否

| 領域 | 今回の追加例 | 一次証拠から分かったこと | 決めたこと |
|---|---|---|---|
| 個人の予定調査・記憶 | OpenClaw / Khoj | 永続schedule、run回復、memory、通知が既にある。OpenClawはrun identity/configRevision、Khojはscheduler/leader lockの実装を持つ | 個人assistantが目的なら直接使うbaseline。Managerに同じagent OSを作らない |
| 定型業務とapp連携 | n8n / Activepieces | scheduler/waitpoint/approval/connectionの既成実装。checkpointの範囲と外部作用の一回性は別 | native workflowをbaselineにする。n8nのSustainable Use License、Activepieces CE/enterprise区分を確認して使う |
| 業務agent SaaS | Gumloop / Relevance AI / Lindy | schedule/MCP/API/approvalを提供。Lindyは今回homepage深度、全backend回復は未監査 | 既に解ける業務はその製品を使う。価格/効果/認証済みという主張はしない |
| Python永続実行 | DBOS / Restate / Inngest / Hatchet | DBOSはSQLiteから比較可能。SDKとserverのlicense、step resultとremote effect、dedup retentionを分離する必要 | DBOSを最初の適合比較に選ぶ。単なるcadence交換で先行移行せず、同条件のfailure matrixで判断 |
| 宣言的workflow | Windmill / Kestra | version guard、retry scopeの既成契約。浅い比較のみ | 汎用workflow/platformが本当に必要になった時の候補。runtime実装を深く監査したとは扱わない |
| browser action | browser-use / Stagehand / Skyvern / Playwright MCP | current version/API/依存が以前の説明と異なる。Stagehand部分replay→fallback、Skyvern送信後timeout/fencing/credential-originが重要 | 現scopeはHTTP＋既存Playwrightで十分。UI-onlyの必要が出た時だけ観測adapterを検討 |
| connector / agent SDK | Composio / Pipedream / Google ADK / OpenAI Agents Python SDK | account binding、SDKのresume/approval範囲、source-available licenseに差がある | accountを自動選択しない。新connector catalogや独自agent SDKを作らない。深度はbrowser laneの表どおり |
| 教材・文書 | Jupyter Book 2 / MyST / Slidev / Remotion | MyST DOCX/JATS、Slidevの画像/編集可能PPTXとfallback、Remotion custom licenseを確認 | 既存原稿とpython-pptx/FFmpegを優先。MySTは必要なexportだけ比較、EPUBは既知Quarto。新CMS/動画runtimeを増やさない |
| 配信 | Ghost / Typefully v2 / Buffer | 現API、token/account、timeout後のrecovery契約を確認。Bufferはcreateのidempotency keyなし | 新接続より既存Postiz/blog bridge。必要なartifact契約・Manager laneだけ追加する |
| 教材→仕事の先例 | Made With ML / Full Stack・askFSDL | 実装→test→教材の対応、録画章→code/図/説明。Made With ML本人のAnyscale参加記事あり | 自分の一つの実装caseを多形式化。収益や採用成功率は推計しない。FSDLは2023archiveと明示 |
| host | Render / Fly / Modal / Cloudflare / Render Workflows | 単一disk/replication/locking/commit/reload/Python runtimeの契約が違う | Railwayを初期選択として維持、最良と証明したとは呼ばない。Renderはfallback、Modal共有volumeやWASMへ現SQLite/flockを無検証移植しない |

直接source例: [OpenClaw runtime](https://docs.openclaw.ai/automation/cron-jobs/how-it-works)・[Khoj automation](https://docs.khoj.dev/features/automations/)・[Gumloop trigger](https://docs.gumloop.com/core-concepts/agent_triggers)・[DBOS database](https://docs.dbos.dev/python/tutorials/database-connection)・[Stagehand source](https://github.com/browserbase/stagehand/tree/6aec9d16a8f503d0e81f22b92ff15a01205c4db2)・[Skyvern source](https://github.com/Skyvern-AI/skyvern/tree/a59e8c4ce423ed38feef994bace51f7a0f996011)・[MyST exports](https://mystmd.org/guide/documents-exports)・[Slidev exports](https://sli.dev/guide/exporting.html)・[Made With ML/Anyscale](https://www.anyscale.com/blog/machine-learning-for-developers)。全source/固定code/限界は下のlane別台帳。

## 論文から実装判断を変える6例

| 論文・版 | 今回読んだ重要部分 | 取り入れる検査・制限 |
|---|---|---|
| [Collective cooperation without individual fidelity, v1](https://arxiv.org/abs/2606.30454v1) | 同protocolでの人との比較、macro/micro/conditionalの乖離 | 集団曲線だけで個人予測や介入を保証しない。単純nullも残す |
| [AgentSociety 2, v2](https://arxiv.org/abs/2607.11895v2) | executable social science、選択methods/失敗/限界＋コード | protocol/データ/seed/実装を別固定。新モデルを作る前に必要な実験基盤を比較 |
| [OccuBench, v2](https://arxiv.org/abs/2604.10866v2) | tool fault、cross-simulator評価、限界 | 環境/採点器の破損をagent失敗と分ける。公開reference実装は論文harnessと同一ではない |
| [DuMateBench, v1](https://arxiv.org/abs/2608.26546v1) | scoringとcode、third-party notices | 論文0.3 partial+0.7 judgeと固定code0.3 complete+0.3 partial+0.4 judgeを混同しない。素材権利未確認は取り込まない |
| [EnterpriseClawBench, v1](https://arxiv.org/abs/2606.23654v1) | human calibration/visual judge、公開contract | LLM同士の一致を人との一致としない。pinしたrepoにcode licenseを確認できず、vendorせず契約を参考にする |
| [ττ-Bench, v1](https://arxiv.org/abs/2609.04611v1) | Appendix Hの9 API故障類型 | post-commit timeout、async completion、projection lag、pagination等をclean fixtureへ。公式code再利用は未確認 |

取得時はarXiv preprintとして扱い、査読採録を確認済みとはしない。原著結果は著者の報告でありManagerでの再現結果ではない。本文の選択節/passagesとコード監査範囲は [SIMULATION_SOURCES.json](SIMULATION_SOURCES.json) に明記。AgentSociety2のcanonical historyとID月の不整合も勝手に補正しない。

## この調査で変わるパッチ

1. **outbox/cycle/reconcile:** 過去UNKNOWNを新candidate・due判定より先に回収する。DBOS等へ渡す場合も `dispatch=True` をcheckpointして送信許可を再生しない。
2. **deliveryと回帰の判別:** 現cycleのbool readback失敗→rollbackを、本番adapterでは使わない。lag/timeout/missingはUNKNOWN。確認済み回帰とexact targetが揃った時だけ限定rollback。
3. **publisherの本当の接続:** 現workflowにはowned intent入力がなく、`admit_owned`が未接続。新hostへ載せるだけで完了しない。固定source/artifactと特権jobをつなぎ、必要なmain移行はversioned契約として扱う。
4. **採点器・素材:** paper/code formulaを版付きで別記録。環境破損・visual judge欠測・再配布不明を分け、既存rubricを上書きしない。
5. **出版:** 既存P01 evidence indexとP06 storyboardを使い、python-pptx/Pillow/FFmpegへ接続。現blog mediaは画像用なので、download artifactを明示契約で追加する。既存6枚/Anicca CTAの投稿laneへ8枚Manager教材をそのまま送らない。

具体的な変更先、提案interface、RED条件、GREEN command、依存・停止条件は [12 atomic patches](../../plans/2026-10-22-manager-e16-atomic-patches.md)。同じ既存テストを再発明せず、新しいfailure deltaだけを追加する。

## 読取台帳と未実施

- [DURABLE_JA.md](DURABLE_JA.md) / [metadata](DURABLE_SOURCES.json): 新runtime6候補、4実コード、14公式文書。
- [AGENT_PRODUCTS_JA.md](AGENT_PRODUCTS_JA.md) / [metadata](AGENT_PRODUCTS_SOURCES.json): 7候補、4実コード、53 source records。
- [BROWSER_JA.md](BROWSER_JA.md) / [metadata](BROWSER_SOURCES.json): 9-way比較、3深読＋wrapper/monorepo追加、固定source fingerprints。
- [SIMULATION_JA.md](SIMULATION_JA.md) / [metadata](SIMULATION_SOURCES.json): 6 exact-version論文、5関連repo、22 selected files。
- [PUBLISHING_JA.md](PUBLISHING_JA.md) / [metadata](PUBLISHING_SOURCES.json): 18 source bundles、3 exporter source snapshotsと追加の教材先例、9既存接続点。
- [HOSTS_JA.md](HOSTS_JA.md) / [metadata](HOSTS_SOURCES.json): 新host/サービス契約、11公式pageとSQLite backup API節。

record/page/repo/論文/versionは異なる単位であり、単純加算して独立研究数や全網羅率にしない。全文取得と全読了を区別し、Lindy homepage・Marp探索・SDK docs-only・wrapper移転先等の深度差を保存した。

未実施: third-party code実行/install、engine比較の実測、provider接続、infra作成、費用/売上照合、記事/動画公開、応募/連絡/研究参加。原113件の状態とE16 cursorは維持。顧客需要、本人の職歴/就労、runtime用credential owner、実hostのlock/restoreはWeb検索だけでは埋まらず、指定patchの実機検査・本人情報・真正なreceiptが必要。

全インターネットや全選択肢を知ったとは宣言しない。今回の不足は、意思決定に関係する別系統の選択肢と実コードを追加し、採否・未検証・次の検査を明示することで修正した。今後は新sourceがどの判断を変えるかを残し、既知候補の再説明を新しい調査と扱わない。
