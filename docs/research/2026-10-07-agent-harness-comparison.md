# Life Manager用エージェントハーネス比較

## 結論と証拠の限界

**現在の判断: 本番移行No-Go、OpenClawの価値比較はGo。** 対象はローカルLife Manager主要15エージェント。Life Manager CLI、商品/業務、state/effect/receiptを保つ。初回finite execは低影響の比較入口であり、耐久性・拡張性・観測性の向上を証明しない。実測改善が無ければ移行しない。

下の比較表とGateway常駐案は候補能力と過去設計の調査記録。常駐/scheduler/session全面移行を現在の確定推奨として扱わない。現行の正本判断は[ローカル仕様](../superpowers/specs/2026-10-07-main-agents-readiness.md)と[価値比較](../superpowers/plans/2026-10-07-local-harness-value.md)。`agent exec`はOTelをexportしないことを公開tagで確認。CLI互換13fakecasesを品質/耐久性/費用改善の証拠にしない。

## 調査方法

GitHubは`gh search repos`、`gh api`、浅いclone。Web発見はDuckDuckGo HTMLを`scrapy fetch`で取得し、結論の根拠は公式資料へ戻した。LangGraph資料は`crwl crawl`でも取得。Context7 CLIでOpenAI Agents JS、Deep Agents JS、Hermes、OpenClaw、LangGraph JS、Mastra、Temporalをlibrary resolve→docsの順で確認した。Context7の検索benchmark scoreはエージェント性能指標として使わない。全ソースは実行せず、依存もインストールしない。

12個の調査用cloneのremoteとHEADは[harness-source-inventory.json](harness-source-inventory.json)に記録。Symphonyは公式READMEを直接取得。OpenClaw展開はENOSPCで一部欠落し、資料と対象コードの読み取り・release API確認に切り替えた。取得済みHEADを保存後、今回のcloneのGit objectと大型メディアのみ整理した。完全なclone/build検証と主張しない。

「DeepSea harness」は同名検索で候補が複数あり、特定できない。`denis21314151-ui/Deepsea-Harness`はsize=0・license未設定、`Yogeshknaik/deepseak-harness`はMITの別repo、update artifactsのみの候補もある。Deep Agentsと同一だと断定しない。正式URLが不明なため名称未特定のまま記録し、有力なDeep Agentsを別候補として比較する。

## 現行Life Managerから導いた要件

確認したbaseは`0a0ad42514067a59408a2705f1a08945f76fa3cc`。

| 観測事実 | 参照 | 含意 |
|---|---|---|
| registryは184 jobs、routeはdeterministic 119 / shared-agent-runner 65 | `config/loop-registry.json` | 184個のLLMを常駐させない。route分類だけでは内部の推論有無も決まらない |
| 商品・業務catalogは15 groups | `apps/life-manager/config/product-loop-catalog.json` | 旧14分類にebookが加わる。名称をagentsにしても既存IDを一括変更しない |
| Capafy/promptbaseのentrypointはdeterministic routeでも内側にrunnerがある | `skills/self/capafy-loop/capafy-loop-daily.sh`、`skills/earn/promptbase/daily.sh` | registryのrouteだけで移行対象を抽出すると漏れる |
| 共通shell→Python runner→CLI provider、Writerにもwrapperがある | `skills/earn/marketing-engine/run_agent.sh`、`runtime/agent-runner/agent_runner.py`、`skills/writer-agent/runtime/shared-model-runner.py` | 新SDKを追加するだけでは既存経路を置換できない |
| admission、occurrence、immutable release、heartbeat、effect-unknownが既にある | `runtime/loop/lm_loop_run.py`、`runtime/host/resource_admission.py` | 既存の安全契約を消してschedulerを二重化しない |
| Mastra dependencyは存在するがruntime READMEはgraphs未実装と記す | `runtime/package.json`、`runtime/README.md` | 文書や依存だけで稼働harnessを判断しない |
| Symphony専用entrypointとworkroom workflowがある | `runtime/loop/entry_dispatch.py`、`ops/symphony/WORKFLOW.money-printer.md` | self-buildの既製資産を保持する |
| LM-EABのeconomic scorerとagent-contract gateがある | `apps/life-manager/eval/economic-autonomy/`、`apps/life-manager/eval/agent-contract/` | 商品・金銭の評価を新製品で再実装しない |

ホストread-only観測では`~/loops/current`は`20261007T073840-cd9626fa`を指す。これは全ジョブのloaded release一致や健康の証拠ではない。既存OpenClawは`2026.6.1`、default configには5 agent entries、名前がOpenClawを含むprocessが1件ある。process countはgateway健康・所有権の証明ではない。Nodeは`v25.6.1`、Codex CLIは`0.160.0`。公開OpenClaw2026.9.8のnpm enginesは`>=24.16.0 <25 || >=26.1.0`で、Node25は対応外。既存環境を変更せず、専用Node26で検証する。

## 候補比較

「組込」はそのソースに機能がある意味。運用成功・Life Managerへの適合を実測済みという意味ではない。

| 候補 | 再利用できるもの | 耐久性・24時間運用 | 評価・改善・観測 | Life Managerへの判断 |
|---|---|---|---|---|
| **OpenClaw** | gateway、multi-agent、skills、native Codex、cron、session、tool/plugin | SQLiteのschedule/run receipts、owner判定、復旧・catch-up、concurrency制御。一般tool作用のexactly-onceは保証しない | diagnostics-otel、mock personal-agent benchmark、skill-workshop、dreaming。販売評価・自律コード昇格は別 | **比較候補**。常駐機構を実際に削除できるかは未証明。既存gateway/profileを奪わない |
| **Deep Agents JS + LangGraph** | planning、filesystem、隔離subagent、skills、summarization、backend | 永続checkpointerを渡す。MemorySaverのみではprocess crashを越えない。scheduler/worker運用は別途必要 | LangSmith統合。trace/evalサービスの利用条件・費用はOSS libraryと別 | 長い制作の最有力対案。全社常駐基盤としてはschedulerを別に作る/運用する負担が残る |
| **Hermes** | 常駐gateway、cron、SQLite sessions、memory、skills、terminal backend、複数provider | profile別cron、並列pool、tick lock、pending occurrenceとexecution ledgerを持つ。全tool作用のexactly-once証明ではない | skill学習。OTelはplugin経路。別self-evolution repoはGEPAでskill改善を実装、tool/prompt/code/continuousはREADMEではplanned | 第二の常駐候補。skills改善が主目的なら強い。現在のCLI境界・domain契約を移す適合作業は残る |
| **OpenAI Agents JS** | agent loop、handoffs、guardrails、MCP、tracing、RunState、session interface | 状態serialize/resumeはあるがfleet scheduler/daemonを内包しない。JS内蔵sessionはMemory/OpenAI Conversations、SQLite自動組込と呼ばない | OpenAI tracingとcustom processors。tracesはtask成功や自己改善の証明ではない | 最小SDKとして有力。全fleet置換には周辺実装が増える |
| **OpenAI JS + Temporal** | 前項＋durable workflows/Activities | Temporal service/DB/workerが必要。Activity retryと外部作用のidempotencyは別 | workflow history＋SDK traces。TemporalのOpenAI integrationはexperimental | 長期契約のdurable lifecycleに強いが、今のMac fleetに一括導入すると運用層が増える |
| **Mastra** | TS agents、model routing、memory、evals、observability、durable agents/workflows | storageと`recovery.durableAgents: auto`が必要。default off。復旧でtool/subagent全体が再実行され得る | scorer・traceがframework内にある | TS内製app中心なら最有力。今回の「インストールして常駐基盤を借りる」目的ではOpenClawを優先 |
| **Pi** | 軽量CLI/SDK、provider、tools、拡張、sessions | 新しいpi-durableにはintent/checkpoint/replay-safe tools。ただしREADMEはExperimental/API変動を明記 | telemetry packagesあり。fleet/business evalは別 | turn engineには良い。durable/fleetを組み立てる負担を今回は避ける |
| **Microsoft Agent Framework** | Python/.NETのagent、multi-agent、checkpoint、OTel、Labs | durable extension/hostとの組合せを別に検証する必要 | observability・experimental benchmark/RL packages | OSS有力だが既存TS/Python/CLIのfleet移行に新しいhost契約を増やす |
| **CrewAI** | Python Crews/Flows、role協調、memory | Flows persistenceとfleet常駐の成立は別 | framework telemetry、商用AMP control planeはOSSと別 | 商品ownerとrole対話を混同しやすく、今回の運用問題を小さく解かない |
| **Symphony** | issue→隔離workroom→coding agent→PR | engineering preview。既存Life Managerにもsource wiringあり | CI/PR証拠。商品販売の完了判定ではない | self-build/repairの部品として維持。販売fleet全体の代替にしない |

## 一次資料と確認した実装

- OpenClaw公開版: [release](https://github.com/openclaw/openclaw/releases/tag/v2026.9.8)。以下のCodex/cron/benchmark/OTel資料の公開tag存在をAPIで確認し、Codex/cron/benchmark本文も取得した。
- [Codex runtime](https://github.com/openclaw/openclaw/blob/v2026.9.8/docs/plugins/codex-harness-runtime.md)、[native tools対応](https://github.com/openclaw/openclaw/blob/45228e1aeed6c31adbeb6383512609c3dd1dfdf3/docs/plugins/codex-harness-runtime/v1-support-contract.md)、[multi-agent](https://github.com/openclaw/openclaw/blob/45228e1aeed6c31adbeb6383512609c3dd1dfdf3/docs/concepts/multi-agent.md)。Workspaceはsandboxではない。native hooksでblock可能だがargument rewrite/compaction制御には限界がある。
- [cron復旧](https://github.com/openclaw/openclaw/blob/v2026.9.8/docs/automation/cron-jobs/how-it-works.md)、確認sourceは`src/cron/service/ops-run-preparation.ts`、`run-recovery.ts`、`run-receipts.ts`。一般command/tool外部作用はexactly-onceにならないという明記を採用する。
- [OTel](https://github.com/openclaw/openclaw/blob/v2026.9.8/docs/plugins/reference/diagnostics-otel.md)、[benchmark](https://github.com/openclaw/openclaw/blob/v2026.9.8/docs/concepts/personal-agent-benchmark-pack.md)。後者は10個のmock personal workflowケースで、売上benchmarkではない。
- [OpenResponses入口](https://github.com/openclaw/openclaw/blob/45228e1aeed6c31adbeb6383512609c3dd1dfdf3/docs/gateway/openresponses-http-api.md)。`POST /v1/responses`はdefault disabled。explicit session keyを指定しないrequestはstateless。bearer入口はfull operatorなのでagentプロセスへgateway tokenを渡さない。
- [skill-workshop](https://github.com/openclaw/openclaw/blob/45228e1aeed6c31adbeb6383512609c3dd1dfdf3/docs/tools/skill-workshop/how-it-works.md)、[dreaming](https://github.com/openclaw/openclaw/blob/45228e1aeed6c31adbeb6383512609c3dd1dfdf3/docs/concepts/dreaming.md)。候補抽出・記憶改善と、実業務held-out評価・安全昇格を分ける。
- [Deep Agents JS](https://github.com/langchain-ai/deepagentsjs/blob/b448f220866bbb5d41924dfdbb1e0079c3b11838/README.md)、`libs/deepagents/src/agent.ts`、`middleware/subagents.ts`、`backends/filesystem.ts`。`checkpointer`はoptional、既定recursionLimit=10000、filesystem virtualMode=false。いずれも運用予算/隔離を設定せずそのまま使わない。
- [LangGraph persistence](https://docs.langchain.com/oss/javascript/langgraph/persistence)、[functional idempotency](https://docs.langchain.com/oss/javascript/langgraph/functional-api)。未完taskはresumeで再実行され得る。
- [Hermes cron](https://github.com/NousResearch/hermes-agent/blob/59a3866ea5a07290afd9a1d137d52d679b77f3ab/cron/AGENTS.md)、`cron/scheduler.py`、`cron/occurrences.py`、[provider](https://github.com/NousResearch/hermes-agent/blob/59a3866ea5a07290afd9a1d137d52d679b77f3ab/website/docs/integrations/providers.md)。subscription対応の存在を確認したが、このアカウントの利用可能性や料金は未検証。
- [Hermes self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution/blob/0a929e3aa20e15cf04dc7c28492a7d41a5139125/README.md)。Phase1 skillのみImplemented、continuous/codeなどはPlanned。READMEの費用概算を実測費用としない。
- [OpenAI JS sessions](https://github.com/openai/openai-agents-js/blob/d8fa6c35b51deb5b0b4761fd1c6dda45879d52df/docs/src/content/docs/guides/sessions.mdx)、[tracing](https://github.com/openai/openai-agents-js/blob/d8fa6c35b51deb5b0b4761fd1c6dda45879d52df/docs/src/content/docs/guides/tracing.mdx)、`packages/agents-core/src/runState.ts`。データexportとsensitive data設定は別に確認する。
- [Temporal integration](https://github.com/temporalio/sdk-typescript/blob/5a02cb820d1f77aa991fe8ad746077ac56884797/contrib/openai-agents/README.md)。integrationはexperimental、SDK自体と区別する。
- [Mastra durable agents](https://github.com/mastra-ai/mastra/blob/49b9bc8dd8838f7759cddcab4201c14f97db82d0/docs/src/content/en/docs/harness/durable-agents.mdx)、`packages/core/src/workflows/default.ts`、[license](https://github.com/mastra-ai/mastra/blob/49b9bc8dd8838f7759cddcab4201c14f97db82d0/LICENSE.md)。core多数はApache-2.0、ee/はenterprise。installed dependencyをproduction proofにしない。
- [Pi durable](https://github.com/badlogic/pi-mono/blob/eb326d265ae0b88489a6d10319307780df827cdf/packages/durable/README.md)、[MAF](https://github.com/microsoft/agent-framework/blob/279d97f75cb2e7eee885dcdc2c741ef7361ee903/README.md)、[CrewAI](https://github.com/crewAIInc/crewAI/blob/e836a191cfe524feb519c6952a458c9f1e1ff0ef/README.md)、[Symphony](https://github.com/openai/symphony)。

OpenClaw、Deep Agents、LangGraph、Hermes core、OpenAI JS、Pi、MAF、CrewAI、Temporal TS SDKのGitHub license metadataはMIT。Mastraは上記mixed license、SymphonyはApache-2.0。Hermes self-evolutionのAPI license metadataはnull、READMEはMITと記すが専用LICENSEを確認できないため、コード取り込みは保留し設計の参考に限る。商用hosted platformやpluginのlicense・費用をcoreへ転写しない。

## 判断の比較と反証条件

1. **OpenClawへ段階移行（過去候補、現在未採用）:** 常駐・session・scheduler・tracesを既製品へ寄せる。販売者としては担当商品とworkspaceが長期に維持され、待ち時間には推論費用を使わず、復旧で同じ注文を二重処理しないのが利点。最大の負担は既存CLI schema/event/admissionと新gatewayを結ぶ薄いadapter。
2. **Deep Agents JSをrunner内に埋め込む:** domain/control planeをほぼ保持でき、長期制作は強い。棄却案の最強論拠は、既存の証拠境界を最小差分で保ちつつ良いturn engineだけ借りられること。今回は自作の常駐・coordination負担をより減らす目的を優先する。
3. **OpenAI JS + Temporalを全社基盤にする:** 数日・数週の契約lifecycleと多host queueには適する。今は新service/DB/workerとexperimental integrationを同時導入する負担が大きい。

| scenario | 期待・対応 |
|---|---|
| best | native providerとtool契約がそのまま適合し、薄いadapterでself-build・制作・販売を移行。既存cost/receipt joinが維持できる |
| base | 制作agentとread-only collectorを先に移行し、販売・金銭ownerは既存wrapperを使う。安全契約を保ちながら不要なrunner/cronを徐々に削る |
| worst | native toolsからfenceを迂回できる、provider sessionが互換でない、同taskの総費用がbaseを上回る、またはRSSが既存host admissionの許容capacityを超える。この場合はcanaryを止め、外部effectは現行ownerに保持し、Deep Agents JSの局所導入へ設計を改定する |

**自分が間違うとしたら最有力の筋:** OpenClawがLife Managerのstrict occurrence/schema/admissionを保持するために必要なadapter量と常駐メモリが、Deep Agents JSの局所導入より大きくなること。隔離canaryでコード量・RSS・task成功・費用を測って反証する。

## 独立検証と文書acceptance

fresh contextの`gpt-6.1-sol / medium`によるread-only敵対的検証は、初回HOLD（HIGH: 新cron/HTTPのmodel claim lifetime未定義、MEDIUM: 費用採用条件の不一致）だった。commit `8812de3f2ee886e353113118c12e9e16a08982e7`で共通admission/claim transfer/停止proof後releaseと、同task総費用<=base/RSS host許容内を設計・計画・SSOTへ統一。再検証はこの2件の文書修正についてPASS。実装・本番・収益のPASSではない。

local relative links、HM-00〜17の18 taskとSSOT対応、90 checkbox手順、12 source SHA、source-boundary、diff whitespaceを確認した。今回のruntime/provider/browser/business mutationは未実施。Gitの文書commit/push/PR統合だけを実施する。

## 条件付きOSS/端末/cloudとatomic計画の再評価

Daisは配布を仮定として追加した。公開の決定ではない。**OSS配布の候補としてOpenClawを保持するが、実測便益がない限り採用しない。** MIT、公式embedding、public GatewayClient、Docker/self-host対応があり、他社SDKへ変えることだけがportabilityではない。pure SDKとしてagent loopだけを組み込む目的ではDeep Agents JSが有力対案だが、今回のscheduler/session/復旧も含む要求を優先する。Mastraも対案として保持する。

追加一次資料: [embedding](https://github.com/openclaw/openclaw/blob/v2026.9.8/docs/gateway/embedding.md)、[Gateway client](https://github.com/openclaw/openclaw/blob/v2026.9.8/docs/gateway/clients.md)、[Docker](https://github.com/openclaw/openclaw/blob/v2026.9.8/docs/install/docker.md)、[tenant cells](https://github.com/openclaw/openclaw/blob/v2026.9.8/docs/gateway/multi-tenant-hosting.md)。npm metadataでroot2026.9.8、client/protocol2026.8.1の公開とentrypointを確認。wire v4はpackage versionと別で、組合せを実測前に互換と断定しない。

公開tagのpackages/gateway-protocol/src/schema/agent.ts、schema/sessions.ts、packages/gateway-client/src/client.tsを読み、RPC agent/agent.wait/sessions.abort、idempotencyKey、client.request optionsを固定。現行sourceのruntime/loop/lm_loop_run.py::_run_admitted、PromptBase scripts/gen_examples.py::_claude、Writer shared-model-runner.py::main、writer_learning_worker.py::record_canary_applicationも確認し、計画の対象symbolを訂正した。

「誰でも」は本人のaccounts/credentialsを設定して実行できる意味。macOS/Linux native、Windowsは初版WSL2/Docker、スマホはcontroller、cloudはsingle-tenant cell。OpenClaw nativeWindows対応とLife Manager全商品のtool対応は別。複数userを一つのgateway/sessionIDで隔離したとは扱わない。

前版18task/90checkboxはphase内部に未確定API/handler判断を残しており、全移行を実装できるatomic計画とは呼べなかった。[改訂plan](../superpowers/plans/2026-10-07-life-manager-harness-migration.md)と[80 atom manifest](harness-atomic-tasks.json)はファイル/関数/引数/結果/assertionを持つ。最初の共通接続sliceは具体化、未確認owner/tool coverageはfalseで[個別entrypoint一覧](harness-owner-activation-map.json)へ残す。全販売機能の移行source設計はまだ未完であり、80という数を全実装可能性の証明にしない。

best=同package/cellを端末とcloudへ配布し既製常駐資産を再利用。base=対応OS/機能を明示しuser個別credentialのself-host cellで運用。worst=互換/native/tool/admissionや費用条件が成立せずactivation禁止、pure SDK対案を比較し直す。最大の反証筋は、商品内部SDKとしてのembed負担がOpenClawのsidecar/IPCよりDeep Agents JSで小さくなること。実務比較は未実施。

改訂計画はfresh read-only `gpt-6.1-sol / medium`で初期RPC/既存targetを再検証した。確認API・対象symbolはsourceと一致。1件のhash境界衝突（a:b/cとa/b:c）をHOLD findingとして受け、commit0a008ea16cでNode JSON.stringify配列とPythonの同じcompact JSON/UTF8へ統一。独立probeで両tupleの不一致とJS/Python一致を確認し、当該修正だけPASS。全80atomの実装や本番成功の判定ではない。manifest/render一致・80依存DAG・SSOT対応・local links・source-boundary・diff whitespaceも確認した。

追加interface検証では、artifact workspaceへREPO_ROOTを流用する矛盾とBindingRecordのeffect_mode不足を指摘され、b9fd71d8f5でprivate artifact root/mode/membership assertionへ修正した。独立再検証はこの2件についてPASS。さらにsource rowのCapafy=deterministic/PromptBase=browserをmodel claimとして借りないことをHA-017へ明記し、別bookkeeping ownerのagent枠・priority保持・queue非上書きを検証条件にした。
