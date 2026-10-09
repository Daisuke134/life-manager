# OpenClaw残実装の全実行TODO

> Superpowers: executing-plans。状態・実行順の正本は統一SSOT。この文書はfile/function/contract/testの全展開。

**Goal:** 現行仕事を中断・重複させず、local Life ManagerのharnessをOpenClawへ移す。
**Architecture:** CLIと業務worker/domain guardを維持し、OpenClawがsession/cron/recovery/trace、既存ChatGPT-account native Codexが推論を担当する。
**Tech Stack:** locked OpenClaw2026.9.8、gateway-client/gateway-protocol2026.8.1、Codex/OTel plugin2026.9.8、Node24.16.0、既存Python/Node。
**Spec:** docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md のOpenClaw source section。

## 共通条件

- isolated_source項目は専用worktree/private fixtureで実装・RED→GREEN。routeはdisabled。稼働runner/認証/注文/個人session/旧global OpenClawを操作しない。
- production項目はmain-derived immutable release、owner deploy lock、active/queued/reserved/unknown無しの確認が必要。進行中仕事を止めず、別ownerを変更しない。未知effectは公式readbackまで再送0。
- engineとschedulerは別handoff。engineの次の自然仕事を確認してから旧future wakeを停止→新cronを有効にする。schedulerは常に一つ。
- 同一Gatewayの別run生存を終了証拠にしない。cancel ACK/exit0/model finalを停止・販売・入金の証拠にしない。
- installer/notices/CLI docsのsourceとisolated検証は本番移管前へ移す。旧順=V全完了→F全項目、新順=F01/02/03/05/06のsource→A/S/V→F04退役/F07最終。理由=安全に実装可能なものを先に終え、現在の本番を維持する。cursor=OC012。

## 検証コマンド

各atomの既存testまたは指名された最小testを先にRED、実装後GREEN。Nodeは `node --test runtime/openclaw/tests/<test>.test.mjs`、Pythonは `python3 -m unittest discover -s runtime/openclaw/tests -p '<test>.py'`。共通suiteは `npm test --prefix runtime/openclaw` と `python3 -m unittest discover -s runtime/openclaw/tests -p 'test_*.py'`。変更した既存callerは同callerの既存focused testsを実行。source境界/OSS/必要CI PASS後commit/push/PR統合。production evidenceは自然仕事/公式readbackのみ。

## 全atom

baseline: 18分類 / 113jobs / finite 95 / continuous 18。残233atom。旧223設計との差分は追加2jobとOC008画像/continuation follow-up、engine自然確認をscheduler移管前の18atomへ明示。これは完了率ではない。

### OC-012 — testPinnedGatewayContract()

- 対象: `runtime/openclaw/tests/release-contract.test.mjs`
- 境界: `isolated_source`
- 変更: SDKとgateway配布版のagent/agent.wait/sessions.abort/terminal payloadをprivate fake-model serverで記録し、既存fixtures/rpc-contract.jsonを作る。gateway-only instance、fake credential、model cost0、native tools disabled。
- 検証/完了: node --test runtime/openclaw/tests/release-contract.test.mjs。handshake v4、1dispatch、1terminal、abort後active0、secret marker出力0。status shape不一致ならconsumerを直すtaskへ進まずcontract差分を確定。
- 依存: OC-001, OC-007, OC-008, OC-009, OC-010

### OC-011 — readSession(client, {sessionKey,agentId}) -> Promise<object>

- 対象: `runtime/openclaw/gateway-client.mjs`
- 境界: `isolated_source`
- 変更: exact session readは実装済み。固定版の公開lifecycle/terminal receiptへ対応し、当該runが停止し当該tool childrenがsettleしたStopProofを作る。公開rowにないactiveRunIdsを仮定しない。unknownならclaim解放0。
- 検証/完了: foreign run/session、stale snapshot、abort ACKのみではStopProofなし。実固定Gateway fixtureで終了を確認。
- 依存: OC-012

### OC-017 — claim_model(owner_id: str, occurrence_id: str, inherited_claim: Path | None, registry_entry: dict) -> dict

- 対象: `runtime/openclaw/admission.py`
- 境界: `isolated_source`
- 変更: registry_entryはimmutable registryのtrusted owner row。継承claimは同owner/occurrenceかつresource_class=agentの場合だけ再利用する。deterministic/browser claimをmodel枠として借りない。この場合はresource_owner_id=m:<sha256(JSON配列[owner_id])>としてagent専用claimをenqueue_durable/claim_durableで追加し、admission_class/priorityは元rowを保持する。parent claimは変更しない。返却ModelClaimに元owner_idとresource_owner_id/refを含める。
- 検証/完了: tests/test_admission.py:agent継承はclaim1、deterministic/browser継承は追加agent枠1、same-owner queueの別resource衝突なし、元priority保持、foreign claim拒否、capacitybusyでmodel starts0。
- 依存: OC-006

### OC-029 — validate_result(instance: object, schema: dict) -> dict

- 対象: `runtime/openclaw/schema_validate.py`
- 境界: `isolated_source`
- 変更: 既存jsonschema==4.26.0のvalidators.validator_for(schema)でschemaをcheck_schemaし結果をvalidate。stdinは{instance,schema}、stdoutは{valid:true}または{valid:false,error_class:schema_invalid|result_invalid}だけ。値やschema全文をstderrへ出さない。
- 検証/完了: tests/test_schema_validate.py:additionalProperties:false拒否、required不足拒否、draft選択、fake secret markerを出力しない。
- 依存: OC-003

### NC-01 — validate_codex_only_config(config) -> Config

- 対象: `runtime/openclaw/profile.mjs`
- 境界: `isolated_source`
- 変更: 全推論routeでagentRuntime.id=codex、fallbacks空、codex plugin enabledを検証。openclaw built-in runtime、OpenAI API-key profile、Claude/Gemini text route、API-key envのmodel利用を拒否。embedding等に別API課金を追加しない。
- 検証/完了: profile.test.mjs:missing Codex/auth→fail closed、Codex不在でAPI request0、approved native modelだけ。
- 依存: OC-001

### NC-04 — resolveNativeCodexEndpoint(config, readback) -> EndpointPlan

- 対象: `runtime/openclaw/codex-endpoint.mjs`
- 境界: `isolated_source`
- 変更: 既存Codex user-home Unix endpointとaccount ownerを公式機構で検出し、存在すればattach-only。無い場合だけ既存OS supervisorへLM-owned native app-server argvを渡す。native account再loginなし、既存daemon/IDE stop0。command/binary/config/canonical socket/versionは同native accountの確認値で固定、hardcoded個人pathなし。
- 検証/完了: endpoint.test.mjs:existing endpointではspawn/stop0、不明owner拒否、LM-owned endpointのみ新規、account/key fallback変更0。
- 依存: NC-01, OC-002

### OC-014 — buildGatewayConfig({paths,artifactWorkspace,port,agentId,modelRoute,effectMode}) -> object

- 対象: `runtime/openclaw/profile.mjs`
- 境界: `isolated_source`
- 変更: buildGatewayConfigは専用instanceと全owner/task profileを初回に用意。ambient/global profileを使わない。初期cronは全disabled、channelsなし。既存Codexモデル/account routeを維持、skillsはrepoの既存methodを参照。OTelはdiagnostics-otel、content capture無効、local OTLP endpointのみ。read_onlyとbrokeredのnative tool policyを明示し、未証明native paths/非承認subagentはdisabled。 推論agentRuntime.idはcodexで固定、plugins.allowにcodex、entries.codex.enabled=true。built-in openclaw runtime/API-key fallback/Claude/Gemini textを禁止。sessionCatalog.enabled=false。appServer.homeScope=userで既存native CodexのChatGPT accountを利用し、OpenClawへrefresh tokenを複製しない。 appServer.transport=unix、urlはNC-04の同native accountの確認済endpointのみ。OpenClaw管理OAuth profileへimportしない。
- 検証/完了: tests/profile.test.mjs:read_onlyではlm_effectなし、cronfalse、ambient account/credential valueなし。公開CLI config validateで通過。
- 依存: OC-013, NC-01, NC-04

### OC-015 — gatewayCommand(paths, profile) -> list[str]

- 対象: `runtime/openclaw/supervisor.mjs`
- 境界: `isolated_source`
- 変更: official openclaw executableのgateway argv/envを返す薄いbuilderだけ。常駐/再起動は既存LM registry+OS supervisorへ委譲。OPENCLAW_NO_RESPAWN=1、既存global gateway/configに変更なし。自作再起動daemonを増やさない。
- 検証/完了: supervisor.test.mjs:private config/node/packageのみ、global signal/install0、OS owner唯一。
- 依存: OC-007, OC-014

### OC-016 — stopGateway(handle, {drainTimeoutMs:5000}) -> Promise<StopProof>

- 対象: `runtime/openclaw/supervisor.mjs`
- 境界: `isolated_source`
- 変更: 全対象sessionがdrainした時だけ専用instanceを既存OS supervisor経由で止める。個別runのtimeoutではGateway全体を止めない。他ownerのactive runがあればinstance stopをdefer。
- 検証/完了: supervisor.test.mjs:run A timeoutでrun BとGateway保持、foreign PID signal0、instance stop前drain必須。
- 依存: OC-015

### OC-018 — bind_execution(claim_ref: Path, gateway_pid: int) -> None

- 対象: `runtime/openclaw/admission.py`
- 境界: `isolated_source`
- 変更: 既存transfer_durableでgateway PID/start identityへclaimをbindし、追加でupstream_run_id/task_id/session_keyへ結合。同gatewayの別runの生存を当該run完了証拠へ流用しない。
- 検証/完了: tests/test_admission.py:別PID/start identityを拒否、transfer後caller終了でもclaim継続。
- 依存: OC-017, OC-015

### OC-019 — heartbeat_model(claim_ref: Path) -> bool

- 対象: `runtime/openclaw/admission.py`
- 境界: `isolated_source`
- 変更: 既存heartbeat_durableを呼ぶ。false/exceptionでstopping→upstream cancel/readbackへ進めるtyped resultを返す。staleだから即releaseしない。
- 検証/完了: tests/test_admission.py:heartbeat failureでclaim保持、retry無制限なし。
- 依存: OC-018

### OC-020 — release_model(claim_ref: Path, stop_proof: dict, effect_state: str) -> dict

- 対象: `runtime/openclaw/admission.py`
- 境界: `isolated_source`
- 変更: 当該upstream run terminal、当該sessionのactiveRunIdsに当該runなし、当該runのowned tool children settlementを照合して既存releaseを一度だけ呼ぶ。Gateway全体の終了を要求しない。cancel ACK/WS close/親wrapper終了だけでは解放しない。不明effectは既存fenceを保持。
- 検証/完了: test_admission.py:run A解放後run B/Gateway生存、ACKのみrelease0、task違い拒否、effect unknown fence保持。
- 依存: OC-019, OC-016, OC-011

### OC-021 — _run_admitted() の finally release分岐

- 対象: `runtime/loop/lm_loop_run.py`
- 境界: `isolated_source`
- 変更: 新routeがdispatch recordでgatewayへclaimを引き継いだ場合のみ、子wrapper終了を理由とする旧releaseを行わずHA-020のterminal proofを要求する。既存routeのfinallyは変更しない。LIFE_MANAGER_LOOP_ID/CLAIM_REFをこのrouteへ常時渡す。
- 検証/完了: runtime/loop/tests/test_openclaw_resource_lifetime.py: caller死亡後gateway activeでcapacity再利用0、legacy route同結果。
- 依存: OC-020

### OC-022 — manifest.tools

- 対象: `runtime/openclaw/plugin/openclaw.plugin.json`
- 境界: `isolated_source`
- 変更: official plugin manifestでlm_read/lm_artifact/lm_effectを宣言。configSchemaはprivate instance/binding rootのみclosed schema。一般shell/browser/scheduler adminへのmodel直接アクセスは未証明なら拒否。
- 検証/完了: tests/plugin.test.mjs:tool宣言と実登録一致、unknown config field拒否。
- 依存: OC-014

### OC-023 — default plugin register(api)

- 対象: `runtime/openclaw/plugin/index.mjs`
- 境界: `isolated_source`
- 変更: definePluginEntryで3toolをcontextVersion:2で登録する。create(ctx)はctx.agentId/sessionKeyに一致するoperator BindingRecordだけをlookupし、固定Python/runtime/openclaw/tool_broker.py --invoke-stdinへ{binding_ref,tool_name,arguments}をstdinで渡す。shell:false、source-owned絶対script、callerからcommand/owner/credentialを受けない。assertInvocationCurrentを各call前に確認し、subprocess envへgateway/provider secretsを継承しない。
- 検証/完了: tests/plugin.test.mjs:偽owner paramsはauthority変更なし、stale invocationのprovider call0。
- 依存: OC-022

### OC-024 — invoke_read(binding: dict, tool_name: str, arguments: dict) -> dict

- 対象: `runtime/openclaw/tool_broker.py`
- 境界: `isolated_source`
- 変更: bindingのownerが持つread-only handlerを呼ぶ。初版handlerはinventory fixture readだけ。read-only経路でpublisher/submission/moneyコードを呼ばない。
- 検証/完了: tests/test_tool_broker.py:read許可、write tool要求でprovider write0、foreign owner拒否。
- 依存: OC-023, OC-017

### OC-025 — invoke_effect(binding: dict, tool_name: str, arguments: dict) -> dict

- 対象: `runtime/openclaw/tool_broker.py`
- 境界: `isolated_source`
- 変更: bindingと既存tool catalogで固定したowner domain adapterへ委譲。既存intent/marketplace ledger/outbox/official readbackを再利用し、effect開始前記録を守る。unknown状態はreconcileのみ。model finalやOpenClawのsuccessをreceiptにしない。CapafyはFROZEN published agentsを更新せず既存new-product policyを維持。
- 検証/完了: tests/test_tool_broker.py:unknown/fenceなし/leaseなしwrite0、same occurrence fakewrite1・same receipt。
- 依存: OC-024

### OC-026 — write_artifact(binding: dict, relative_path: str, content: str) -> dict

- 対象: `runtime/openclaw/tool_broker.py`
- 境界: `isolated_source`
- 変更: trusted binding.workspace配下のrelative pathだけへUTF-8成果物を書く。absolute/..、symlink parent、.git、credential/config/state領域を拒否。最大1MiB。temp write/fsync/replaceし{artifact_ref,sha256,bytes}を返す。canonical catalog/production sourceを直接書かない。 relative_path=caller-result.jsonの場合はbindingのcaller schemaをvalidateし、全JSONを同task private workspaceへatomic保存してSHA/owner/occurrence/task/upstream runのartifact receiptを返す。modelのreceipt文章を公式provider proofにしない。
- 検証/完了: tests/test_tool_broker.py:4成果物SKILL.md/LISTING.md/icon.svg/evidence/verified-demonstration.mdをprivateworkspaceに作れる。../、symlink、1MiB超過はwrite0。
- 依存: OC-024

### OC-027 — main(argv: list[str], stdin: TextIO) -> int

- 対象: `runtime/openclaw/tool_broker.py`
- 境界: `isolated_source`
- 変更: --invoke-stdinだけ受付。packetは{binding_ref,tool_name,arguments} closed schema。operator dispatchRoot内のBindingRecordをmode/owner/claim/actual parent PID・start identityと照合し、lm_read→invoke_read、lm_artifact→write_artifact、lm_effect→invoke_effectへdispatchする前にtool_name∈binding.allowed_toolsとeffect_modeとの整合を検証する。read_onlyのlm_effectはprovider開始前に拒否する。model supplied owner/claimを採用しない。stdoutはsanitized JSON、unknown/errorはtyped resultと非zero。
- 検証/完了: tests/test_tool_broker.py:foreign binding/parent mismatch/unknown tool/secret markerでeffect0、固定invoke packetが通る。shell command文字列は受けない。 read_only bindingへのlm_effect packetはprovider開始0。
- 依存: OC-025, OC-026

### OC-028 — testModelAndToolAdmissionFailClosed()

- 対象: `runtime/openclaw/tests/native-boundary.test.mjs`
- 境界: `isolated_source`
- 変更: 配布版でplugin missing/timeout、native shell/MCP/HTTP、cron/direct RPC、subagentの5迂回をfake provider相手にprobeする。一般prompt hookだけで強制保証しない。
- 検証/完了: native-boundary.test.mjs:before-model hook例外/timeout、native Codex tools、shell/browser/skills経由の迂回、subagent model startをfixtureで試す。host claimなしmodel start0、effect fence外provider mutation0。不成立routeはlegacy維持。
- 依存: OC-025, OC-012, OC-021, OC-027

### OC-030 — normalizeOutcome(raw, request) -> RunOutcome

- 対象: `runtime/openclaw/result.mjs`
- 境界: `isolated_source`
- 変更: normalizeOutcomeは当該binding/taskのfresh caller-result.json+host artifact receiptを優先してschema検証する。無ければpinned terminalReplyの完全なvisible textだけを検証。terminalReplyは4096文字capであり、truncation/JSON不正/別task/古いfileはfailedまたはpendingにする。モデルに必要なlm_artifactの結果保存契約をhost promptへ追加。result_path/summaryは既存形へ戻し、domain tool effectのverifiedは公式readbackだけ。
- 検証/完了: result.test.mjs:10000文字JSONはfull artifactから通る、4096文字に切れたterminalReplyのみは拒否、old/foreign task artifact拒否、小さいJSONは既存schema通過、broker公式receipt以外でeffect verified0。
- 依存: OC-012, OC-025, OC-029

### OC-031 — project_usage(raw: dict, identity: dict) -> dict

- 対象: `runtime/openclaw/telemetry.py`
- 境界: `isolated_source`
- 変更: existing agent-usage fieldsへinput/output/cached/retry/subagent tokensをproject。cost_basisはprovider_reported/api_equivalent_estimate/unknownを分離。runId重複を二重計上しない。
- 検証/完了: tests/test_telemetry.py:retry usage含む、欠測null、同run二重charge0、fake secret marker非露出。
- 依存: OC-030

### OC-032 — project_runtime_event(outcome: dict, identity: dict) -> dict

- 対象: `runtime/openclaw/telemetry.py`
- 境界: `isolated_source`
- 変更: 既存runtime_event.build_runtime_event/validate_runtime_eventを利用しrun/owner/occurrence/releaseをjoin。error_class/retryable/next_action/receipt/readbackを保持。
- 検証/完了: tests/test_telemetry.py:既存validator通過、release欠落でsuccess不可、unknown effect維持。
- 依存: OC-031

### OC-042 — attach_trace_identity(envelope, binding) -> dict

- 対象: `runtime/openclaw/telemetry.py`
- 境界: `isolated_source`
- 変更: official model/tool spansのrun/sessionをtrusted LM owner/product/occurrence/task/releaseへ結合。content/authを記録せず欠測はnull。実請求とestimateを区別。
- 検証/完了: test_telemetry.py: foreign run拒否、missing0化なし、secret field除去、同run相関。
- 依存: OC-031, OC-032

### OC-053 — decideCandidatePromotion(input) harness contract evidence

- 対象: `apps/life-manager/eval/agent-contract/gate.js`
- 境界: `isolated_source`
- 変更: 既存decideCandidatePromotion/decidePromotionGateが要求する同task/baseline/live evidenceにschema/trace/tool/receipt/recovery refsを加える。新judge/benchmark frameworkを作らず、Codex-onlyを同じgateで評価する。
- 検証/完了: gate.test.js:欠測/自己申告fail、fake/real receiptの区別、旧cases PASS。
- 依存: OC-028, OC-042

### NC-02 — readNativeCodexAccount(instance) -> AccountProof

- 対象: `runtime/openclaw/auth_readback.mjs`
- 境界: `isolated_source`
- 変更: existing ChatGPT accountを使うnative Codex Unix endpointへ公式pluginで接続。appServer.transport=unix/homeScope=user、sessionCatalog=false、owner-only LM thread。account/login/logout/importを呼ばずnative account statusを読みkind/account hashを検証。他native sessionを変更せずtokensをOpenClaw DB/configへ複製しない。既存endpointを探し、無ければNC-04でLM-owned native daemonだけを用意。existing managed Codex binary/versionを使用し、bundled/global CLIを自動upgradeしない。
- 検証/完了: auth_readback.test.mjs:account ChatGPT確認、API-key account拒否、token export0、personal thread discovery/manage0。
- 依存: NC-01, NC-04

### F-01 — local OpenClaw package/profile setup

- 対象: `install.sh`
- 境界: `isolated_source`
- 変更: isolated clean-homeでlocked runtimeとprivate profileを初期化するinstallerを実装。現在の端末にはapplyしない。global OpenClaw/auth/browser/stateの複製・上書き0。実install採用はowner切替時のみ。
- 検証/完了: clean-home fixtureでsecret0、同install再実行で既存state保持。
- 依存: OC-014, OC-015, NC-02

### F-02 — OpenClaw artifact boundary

- 対象: `scripts/verify-oss-self-contained.mjs`
- 境界: `isolated_source`
- 変更: runtime/openclawとlocked pluginのOSS notices/integrityを既存boundary検査へ接続。runtime state/secret/transcriptをrepoへ入れない。
- 検証/完了: source-boundary、gitleaks、PII検査PASS。
- 依存: F-01

### F-03 — OpenClaw/SDK/OTel notices

- 対象: `THIRD_PARTY_NOTICES.md`
- 境界: `isolated_source`
- 変更: 実際にbundleしたversion/license/provenanceを記録。未install依存を配布済と書かない。
- 検証/完了: package-lockとのversion一致。
- 依存: F-01

### NC-03 — testNativeCodexRestrictedToolAuthority()

- 対象: `runtime/openclaw/tests/codex-restricted-tools.test.mjs`
- 境界: `isolated_source`
- 変更: finite tools.allowがCodex restricted turnを作りnative Code Mode/environment/native MCP/hook relayを無効化・attestする公開機構を実体fixtureで確認。LM approved dynamic toolだけを許可。hook timeoutを安全保証としない。
- 検証/完了: native Codex→model response→allowed toolの経路、直shell/browser/unauthorized MCP/provider mutation0、別owner/thread不変更。
- 依存: NC-02, OC-028

### OC-033 — main(argv, stdin, deps) -> Promise<number>

- 対象: `runtime/openclaw/cli.mjs`
- 境界: `isolated_source`
- 変更: request v2を読みprepare→host claim→trusted binding→RPC submit→ACK保存→wait→result/schema/domain receipt→terminal proof→release。stable sessionを使っても前task contextをeffect authorityにしない。exit0/1/2/75を現callerへ返す。
- 検証/完了: tests/cli.test.mjs:正常fixture各呼出順、ack喪失でsent1/dispatch0追加、timeoutでunknown。 request.workdirがREPO_ROOTでもartifactWorkspaceはその外のprivate path、source write0。
- 依存: OC-003, OC-004, OC-006, OC-008, OC-009, OC-010, OC-011, OC-020, OC-030, OC-032, OC-028, NC-02, NC-03

### OC-050 — validate_subagent_policy(policy, parentBinding)

- 対象: `runtime/openclaw/profile.mjs`
- 境界: `isolated_source`
- 変更: official subagent機能を利用する条件を固定。childも別host claim/budget、独立workspace/fresh reviewer、同じtool fence。既存hookがfail-openになる経路はenabled falseのまま。
- 検証/完了: native-boundary.test.mjs:child model claimなしstart0、親停止時child settlementまで保持。
- 依存: OC-028, OC-042, NC-03

### OC-051 — resolve_skills_paths(releaseRoot, route)

- 対象: `runtime/openclaw/profile.mjs`
- 境界: `isolated_source`
- 変更: 既存skillsをofficial skills loaderへ参照させる。新しいskill managerを作らない。modelが書いたskillを無審査でproductionへロードしない。
- 検証/完了: profile.test.mjs: release内approved skillのみ、Dais profile/secret snapshot複製0。
- 依存: OC-014, OC-050

### OC-052 — life-manager-openclaw-gateway service

- 対象: `config/loop-registry.json`
- 境界: `isolated_source`
- 変更: 専用Gatewayのcontinuous serviceだけを既存supervisorへ登録。daemon二重所有なし、global OpenClaw upgradeなし。source build中は未install。 source段階はdisabled/default-off契約で、release reconcilerによる暗黙startを既存registry testsで拒否する。現在のGUI/launchdへinstall/startしない。
- 検証/完了: test_lm_loop_apply.py:immutable package/node/profile argv、既存110 owner cadence変更0。
- 依存: OC-015, OC-051

### OC-054 — record_canary_application() harness evidence

- 対象: `skills/writer-agent/scripts/writer_learning_worker.py`
- 境界: `isolated_source`
- 変更: 既存candidate/eval/canary記録へnative Codex account、harness version、同task trace/evidenceを結合。OpenClaw既製skills/subagentを利用し、production skill/codeを無審査で昇格しない。self-improve-evolve等他ownerへの適用はPの実call閉包を先に確認。
- 検証/完了: 既存writer learning/candidate gate testでmissing evidence拒否、baseline候補不変、failed candidate本番enable0。
- 依存: OC-050, OC-051, OC-053

### MI-01 — encode_owned_images(paths, binding) -> list[GatewayAttachment]

- 対象: `runtime/openclaw/images.py`
- 境界: `isolated_source`
- 変更: 画像pathを同owner private artifact/証明済み入力rootで検証しMIME/SHAを保持。公式agent RPC attachmentsからnative Codex image inputへ渡す。Type.Unknownを無検証で渡さずpinned serverの受理schemaに合わせる。symlink/外部URL/credential fileを拒否。画像bufferはWS送信のメモリだけ、stdout/traceにはbytesを出さない。 GatewayAttachmentのwire fieldsは{type:"image",mimeType:<verified MIME>,fileName:<basename>,content:<base64 string>}。公開chat-attachments.tsのnormalizeAttachmentで受理される形に固定する。RunRequest保存時はpath/digestのみで、このwire objectはRPC送信時だけ生成。
- 検証/完了: test_images.py＋native-image.test.mjs: candidates-sheet PNGがCodex画像inputに届く、image無し旧task不変、foreign path拒否、視覚fixtureの期待結果通過。
- 依存: OC-003, OC-012, NC-03

### MI-02 — forkOwnedContinuation(binding, legacyThreadRef) -> ResumeProof

- 対象: `runtime/openclaw/resume_bridge.mjs`
- 境界: `isolated_source`
- 変更: 既存resume refのLM owner/occurrence・task・leaseを証明して公式codex_threads forkを使いLM OpenClaw sessionへ結ぶ。旧threadを別app-serverから同時resume/writeしない。personal thread list/import/stopなし。既存domain checkpoint/receiptを保持し、historyでeffect権限を与えない。
- 検証/完了: resume.test.mjs:owned forkだけ、旧thread不変更、foreign ref拒否、Writer continuation context保持、同業務effect再送0。
- 依存: OC-004, NC-02

### OC-034 — run_openclaw(parsed, prompt: str, schema: dict, config: dict, budget_context: dict) -> int

- 対象: `runtime/openclaw/runner_adapter.py`
- 境界: `isolated_source`
- 変更: run_openclawは既存parsed.imageとcodex_resume_session_idをMI-01/02のapproved referenceへ変換してRunRequest v2へ渡す。usage/schema/result_path/lease/token budget契約を維持。対応が未証明の時だけsource-controlled legacyを選び、全移行完了にしない。画像やresumeを永久unsupportedのまま終わらせない。
- 検証/完了: tests/test_runner_adapter.py:summary result_path互換、pass/daily limit blockedでRPC0、same occurrence二重reserve0、usage unknownでreservation保持、未証明・不正imageでdispatch0。
- 依存: OC-033, MI-01, MI-02

### OC-035 — run() の evidence/lease/token-budget preflight後・candidate for-loop前

- 対象: `runtime/agent-runner/agent_runner.py`
- 境界: `isolated_source`
- 変更: agent_runnerの入口は移行中だけowner/task selectorで旧またはOpenClawへ分ける。RPC開始後の旧経路fallbackなし。全対象移行後はOpenClawだけにしprovider candidate for-loop/旧runtime dispatchをF-04で削除。
- 検証/完了: runtime/agent-runner/tests/test_openclaw_route.py:defaultlegacy、eligibleownerだけnew、空ownernew0、token/evidence/provider-lease preflightを迂回しない、未停止でlease release0。
- 依存: OC-034, OC-021

### OC-036 — test_ack_loss_preserves_claim()

- 対象: `runtime/openclaw/tests/test_recovery.py`
- 境界: `isolated_source`
- 変更: 送信→ACK前crash fixture。sent recordが残り、同occurrence再開はreconcileのみ、新RPC agent0・claim保持をassert。
- 検証/完了: python3 -m pytest runtime/openclaw/tests/test_recovery.py::test_ack_loss_preserves_claim -q。
- 依存: OC-035

### OC-037 — test_provider_success_receipt_gap()

- 対象: `runtime/openclaw/tests/test_recovery.py`
- 境界: `isolated_source`
- 変更: fake provider成功→receipt保存前crash fixture。readbackで同receipt復元、provider write1、retry追加0をassert。
- 検証/完了: python3 -m pytest runtime/openclaw/tests/test_recovery.py::test_provider_success_receipt_gap -q。
- 依存: OC-036

### OC-038 — test_terminal_replay_zero()

- 対象: `runtime/openclaw/tests/test_recovery.py`
- 境界: `isolated_source`
- 変更: terminal保存済みoccurrenceを再投入。existing result/refを返しmodel/provider/toolの追加call0をassert。
- 検証/完了: python3 -m pytest runtime/openclaw/tests/test_recovery.py::test_terminal_replay_zero -q。
- 依存: OC-037

### OC-039 — 固定canary request

- 対象: `runtime/openclaw/fixtures/read-only-request.json`
- 境界: `isolated_source`
- 変更: owner_id=harness-readonly-canary、occurrence_id=fixture-001、effect_mode=read_only、task_class=repeatable-agent、timeout_seconds=60、schema={type:object,required:[status,count],properties:{status:{const:success},count:{const:1}},additionalProperties:false}。model/providerはprivate fixture configに渡しsourceへcredentialを入れない。
- 検証/完了: tests/canary.test.mjs:validateRunRequest通過、fake modelの返答{status:success,count:1}、effect0。
- 依存: OC-038

### OC-040 — main(argv) -> int

- 対象: `apps/life-manager/scripts/harness-readonly-canary.py`
- 境界: `isolated_source`
- 変更: harness-readonly-canary.pyはprivate request/fixtureだけを読み既存operator bridgeへ渡す。production追加owner/scheduleを自動作成しない。source acceptanceと自然業務receiptを区別。
- 検証/完了: runtime/openclaw/tests/test_canary.py:caller pathsrelease相対、effect0、event same occurrence。
- 依存: OC-039

### OC-041 — owners

- 対象: `config/openclaw-routes.json`
- 境界: `isolated_source`
- 変更: catalog全ownerの初期recordをengine=legacy,scheduler=legacy,enabled=false、source coverage refsなしで作る。continuousはnative_service。business cadenceは保持し、推論はCodex-only policyへ統一。
- 検証/完了: test_routes.py: unknown/default/disabledがlegacy、coverage refなしenable拒否。
- 依存: OC-035

### OC-043 — build_owner_inventory(registry, catalog, sources) -> dict

- 対象: `runtime/openclaw/owner_inventory.py`
- 境界: `isolated_source`
- 変更: product bindingをregistry/catalogからcompileするbuild helperを実装。既に記録した全model entrypoint/shared/direct/image/resume callの定義を読み、route/schema/tool/ownerを検証する。未定義ならbuild error。探索や新旧選択を実行TODOにしない。
- 検証/完了: test_inventory.py: nested deterministic modelとdirect APIをfixtureで検出、無モデルjobにmodel追加なし。
- 依存: OC-041

### OC-044 — build_command_job(owner, release, cadence, epoch) -> dict

- 対象: `runtime/openclaw/schedule_transfer.py`
- 境界: `isolated_source`
- 変更: official cron command payloadを作りexisting bin/lm-loop-runを実行する。AI不要の処理へmodelを追加しない。cadence/anchor/timezoneとimmutable argvを保持。最初はenabled=false、delivery none。
- 検証/完了: test_schedule_transfer.py: exact argv/cadence、continuous拒否、client adminのみcron編集。
- 依存: OC-012, OC-043

### OC-045 — prepare_transfer(owner_id, expected_sha) -> dict

- 対象: `runtime/openclaw/schedule_transfer.py`
- 境界: `isolated_source`
- 変更: owner deploy leaseを取得。active model/process/予約/queued occurrence/unknown effectを再観測し、残ればdefer。旧plist/cadence/release/new cron disabled状態をreceiptへ保存。
- 検証/完了: test_schedule_transfer.py: active/pending/fencedは変更0、foreign owner不変更。
- 依存: OC-044

### OC-046 — commit_transfer(prepared) -> dict

- 対象: `runtime/openclaw/schedule_transfer.py`
- 境界: `isolated_source`
- 変更: 既存launchctl-safeで旧ownerの新wakeだけ停止→旧future scheduler停止readback→official cron enable。唯一schedulerをreadback、失敗時に新cronをdisabledとして旧scheduleだけ復元。稼働仕事を移送/再送しない。
- 検証/完了: test_schedule_transfer.py: fault各境界scheduler<=1、同effect重複0、途中receiptから復旧。
- 依存: OC-045

### OC-047 — rollback_transfer(receipt) -> dict

- 対象: `runtime/openclaw/schedule_transfer.py`
- 境界: `isolated_source`
- 変更: 新wake pause→当該run drain/settlement確認→新cron disabled→旧source scheduleを復元。ledger/auth/workspace/provider effectを巻戻さない。Gateway全体stop禁止。
- 検証/完了: test_schedule_transfer.py: 別owner継続、unknownはreconcileへ、effect resend0。
- 依存: OC-046

### OC-048 — _dispatch_reserved(loop_ids, ...) scheduler dispatch

- 対象: `runtime/loop/lm_loop_run.py`
- 境界: `isolated_source`
- 変更: 既存reservation/priority policyは保持。owner authorityがlegacyなら現行kick、OpenClawなら公式cron runへ同owner wakeをdispatch。controllerからmodel/publishを直実行しない。
- 検証/完了: test_openclaw_scheduler_authority.py:legacy不変、reservation duplicate0、authority mismatch拒否。
- 依存: OC-046

### OC-049 — health/status/lifecycle OpenClaw projection

- 対象: `runtime/loop/lm_loop.py`
- 境界: `isolated_source`
- 変更: 既存CLI引数を維持。official health/session/cron状態とLM financial/effect状態を合成。stopはownerの新wake停止、run cancel/drainを対象限定。OS browser ownerは既存処理。
- 検証/完了: test_openclaw_cli.py:同じCLI互換、stop AでB継続、process pass≠business verified。
- 依存: OC-042, OC-048

### C-01 — think

- 対象: `runtime/loop/brain.mjs`
- 境界: `isolated_source`
- 変更: brain.mjs::thinkの推論をnative Codex Gatewayに一本化。claude-p/proxyは新routeのfallbackに使わずwallet/compute toolは別所有を維持。旧実行の途中では切り替えない。
- 検証/完了: 当該既存focused tests＋Gateway fake adapterで同input/output/schema、foreign owner mutation0、未確定generation再送0、baseline route不変。actual provider/model/accountが不明ならsource routeを有効化しない。
- 依存: OC-034, OC-041, OC-028

### C-02 — runAdversaryReview

- 対象: `apps/life-manager/scripts/dev-adversary-review.js`
- 境界: `isolated_source`
- 変更: runAdversaryReviewの直接ClaudeをChatGPT accountのnative Codex fresh_task reviewerへ変更。diff screening/minimal env/独立review threadを保持。builderの会話を継承しない。
- 検証/完了: 当該既存focused tests＋Gateway fake adapterで同input/output/schema、foreign owner mutation0、未確定generation再送0、baseline route不変。actual provider/model/accountが不明ならsource routeを有効化しない。
- 依存: OC-034, OC-041, OC-028

### C-03 — skillopt.model openai_chat invocation

- 対象: `skills/writer-agent/scripts/craft-train.sh`
- 境界: `isolated_source`
- 変更: craft-train.shからdirect openai_chat課金生成を呼ばず、native Codexのskill-improvement経路へ接続。評価dataset/objectiveとquarantineは維持し、OpenClaw既製skill機構を使う。Codexに適合しないoptimizer入口はtyped setup_requiredで新route未完、API-keyで迂回しない。
- 検証/完了: 当該既存focused tests＋Gateway fake adapterで同input/output/schema、foreign owner mutation0、未確定generation再送0、baseline route不変。actual provider/model/accountが不明ならsource routeを有効化しない。
- 依存: OC-034, OC-041, OC-028

### C-04 — fetchGeminiText

- 対象: `apps/life-manager/lib/marketing-slide-pack-text.js`
- 境界: `isolated_source`
- 変更: fetchGeminiTextのtext推論をChatGPT account接続のnative Codex Gatewayへ変更。既存caption/hook schema、approved claim/source facts、caller output shapeを維持。Gemini image/FAL等の既存制作toolをこのtext変更へ混ぜない。
- 検証/完了: 当該既存focused tests＋Gateway fake adapterで同input/output/schema、foreign owner mutation0、未確定generation再送0、baseline route不変。actual provider/model/accountが不明ならsource routeを有効化しない。
- 依存: OC-034, OC-041, OC-028

### C-05 — _run_agent

- 対象: `skills/earn/line-sticker/line_sticker_planner.py`
- 境界: `isolated_source`
- 変更: plan/selectorをtrusted logical task_id付きshared adapterへ。JSON schemaとartifact pathを保持。
- 検証/完了: 当該既存focused tests＋Gateway fake adapterで同input/output/schema、foreign owner mutation0、未確定generation再送0、baseline route不変。actual provider/model/accountが不明ならsource routeを有効化しない。
- 依存: OC-034, OC-041, OC-028, MI-01

### C-06 — character_image

- 対象: `skills/earn/line-sticker/line_sticker_planner.py`
- 境界: `isolated_source`
- 変更: 直接Gemini image生成を既存specialized toolとして登録。既存provider fee/credential/image checkを保持。LLMで画像を代用しない。
- 検証/完了: 当該既存focused tests＋Gateway fake adapterで同input/output/schema、foreign owner mutation0、未確定generation再送0、baseline route不変。actual provider/model/accountが不明ならsource routeを有効化しない。
- 依存: OC-034, OC-041, OC-028

### C-07 — clips

- 対象: `skills/earn/line-sticker/seedance_set.py`
- 境界: `isolated_source`
- 変更: FAL job IDを同じgeneration tool receiptへ結びpending時はpollだけ、再submitしない。画像動画モデルを同時変更しない。
- 検証/完了: 当該既存focused tests＋Gateway fake adapterで同input/output/schema、foreign owner mutation0、未確定generation再送0、baseline route不変。actual provider/model/accountが不明ならsource routeを有効化しない。
- 依存: OC-034, OC-041, OC-028

### C-08 — catalog of existing recipe tools

- 対象: `runtime/openclaw/tool_catalog.json`
- 境界: `isolated_source`
- 変更: products/*.jsonの既存worker/tool bindingを束ねるcatalogを作成。canonical source、schema、owner scope、domain guard/readbackを固定。OpenClawから既存業務workerを実行し、任意argv/function/pathをmodelに決めさせない。
- 検証/完了: 当該既存focused tests＋Gateway fake adapterで同input/output/schema、foreign owner mutation0、未確定generation再送0、baseline route不変。actual provider/model/accountが不明ならsource routeを有効化しない。
- 依存: OC-034, OC-041, OC-028

### F-05 — local install/control/architecture

- 対象: `README.md`
- 境界: `isolated_source`
- 変更: local CLI/install/control/復旧/rollbackとOpenClaw/native Codex構成を実装された範囲で記載。分類/job数はcatalogから検証し固定値にしない。Cloud Web画面は範囲外。
- 検証/完了: catalogとREADMEの機能・CLI一致、isolated smoke、未実装を利用可能としない。
- 依存: OC-049, F-01

### F-06 — 日本語ローカル操作契約

- 対象: `README.ja.md`
- 境界: `isolated_source`
- 変更: 同じ導入/停止/結果確認/復旧/rollbackを日本語で記載。全商品ワンクリック済の誤記なし。
- 検証/完了: README.mdと同じcommand/features。
- 依存: F-05

### C-09 — _claude(prompt, system)

- 対象: `skills/earn/promptbase/scripts/gen_examples.py`
- 境界: `isolated_source`
- 変更: 既存functionの外部signatureとexample/schema/output artifactを保持し、内部モデル呼出をnative Codex OpenClaw bridgeへ置き換える。Claude/API-key/別model fallbackなし。listing/sale/financial readerの処理を変更しない。
- 検証/完了: 既存example generation testsとGateway fakeでsystem/user sections、schema、artifact paths、real example requirement維持。
- 依存: OC-034, NC-03

### OC-008-IMAGE — submitRun approved attachments

- 対象: `runtime/openclaw/gateway-client.mjs`
- 境界: `isolated_source`
- 変更: MI01で検証した画像wireをRPCへ渡し、現在のinput_binding_not_ready拒否を検証済み画像だけ解除。MI02のowned fork sessionへcontinuationを結合する。
- 検証/完了: approved image/resume fixture通過、foreign input dispatch0、bytes/path log0、ACK喪失request1。
- 依存: MI-01, MI-02

### P-gig-coconala — register existing product worker/tools

- 対象: `runtime/openclaw/products/gig-coconala.json`
- 境界: `isolated_source`
- 変更: product_id=gig-coconala、job_ids=["hf-gig-apply-direct", "hf-gig-apply-evidence-gc", "hf-gig-browser", "hf-gig-daily-report", "hf-gig-paid-direct", "hf-gig-reply-detector", "hf-gig-storefront-direct"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-gig-lancers — register existing product worker/tools

- 対象: `runtime/openclaw/products/gig-lancers.json`
- 境界: `isolated_source`
- 変更: product_id=gig-lancers、job_ids=["lancers-revenue-application", "lancers-revenue-browser", "lancers-revenue-negotiate", "lancers-revenue-paid", "lancers-revenue-storefront", "lancers-revenue-telegram-report", "lancers-revenue-work-sync"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-gig-crowdworks — register existing product worker/tools

- 対象: `runtime/openclaw/products/gig-crowdworks.json`
- 境界: `isolated_source`
- 変更: product_id=gig-crowdworks、job_ids=["crowdworks-revenue-application", "crowdworks-revenue-browser", "crowdworks-revenue-paid", "crowdworks-revenue-reply", "crowdworks-revenue-report"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-gig-mercor — register existing product worker/tools

- 対象: `runtime/openclaw/products/gig-mercor.json`
- 境界: `isolated_source`
- 変更: product_id=gig-mercor、job_ids=["mercor-revenue-application", "mercor-revenue-paid", "mercor-revenue-reply"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-promptbase — register existing product worker/tools

- 対象: `runtime/openclaw/products/promptbase.json`
- 境界: `isolated_source`
- 変更: product_id=promptbase、job_ids=["promptbase-loop-daily"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08, C-09

### P-writer — register existing product worker/tools

- 対象: `runtime/openclaw/products/writer.json`
- 境界: `isolated_source`
- 変更: product_id=writer、job_ids=["writer-claim-loop", "writer-craft-train", "writer-money-sync", "writer-opportunity-discovery", "writer-opportunity-response", "writer-report", "writer-sales-measure"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-03, C-08

### P-affiliate — register existing product worker/tools

- 対象: `runtime/openclaw/products/affiliate.json`
- 境界: `isolated_source`
- 変更: product_id=affiliate、job_ids=["affiliate-browser", "affiliate-composition", "affiliate-impact-browser", "affiliate-loop", "affiliate-source-refresh", "affiliate-x-browser"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-investment — register existing product worker/tools

- 対象: `runtime/openclaw/products/investment.json`
- 境界: `isolated_source`
- 変更: product_id=investment、job_ids=["alpaca-investment-paper", "alpaca-investment-live", "investment-cross-venue-report", "investment-strategy-validation"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-agent-economy — register existing product worker/tools

- 対象: `runtime/openclaw/products/agent-economy.json`
- 境界: `isolated_source`
- 変更: product_id=agent-economy、job_ids=["agent-economy-loop", "citizen-refill", "life-manager-x402-ledger", "sol-funding", "the402-provider", "the402-worker", "x402-acquisition-controller", "x402-claude-p", "x402-experiment-franklin1", "x402-franklin1", "x402-franklin2", "x402-inflow-watch", "x402-inflow-watch-claude-p", "x402-inflow-watch-franklin1", "x402-inflow-watch-franklin2", "x402-research-serve", "x402-sale-observer", "x402-seller-8404", "x402-settlement-recorder"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-01, C-08

### P-job-hunter — register existing product worker/tools

- 対象: `runtime/openclaw/products/job-hunter.json`
- 境界: `isolated_source`
- 変更: product_id=job-hunter、job_ids=["job-search-daily", "job-search-health", "job-search-inbox", "job-search-learning"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-fundraiser — register existing product worker/tools

- 対象: `runtime/openclaw/products/fundraiser.json`
- 境界: `isolated_source`
- 変更: product_id=fundraiser、job_ids=["fundraiser"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-connector — register existing product worker/tools

- 対象: `runtime/openclaw/products/connector.json`
- 境界: `isolated_source`
- 変更: product_id=connector、job_ids=["life-manager-connector-native"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-self-build — register existing product worker/tools

- 対象: `runtime/openclaw/products/self-build.json`
- 境界: `isolated_source`
- 変更: product_id=self-build、job_ids=["life-manager-dev", "life-manager-recovery-supervisor", "life-manager-selfbuild", "self-improve-evolve"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-02, C-08

### P-mobile-apps — register existing product worker/tools

- 対象: `runtime/openclaw/products/mobile-apps.json`
- 境界: `isolated_source`
- 変更: product_id=mobile-apps、job_ids=["life-manager-anicca-affirmation-youtube", "life-manager-anicca-ai-youtube", "life-manager-anicca-buddha-tiktok", "life-manager-anicca-en-affirmation-instagram", "life-manager-anicca-en-affirmation-tiktok", "life-manager-anicca-en-card-instagram", "life-manager-anicca-en-slideshow-tiktok", "life-manager-anicca-en-widget-instagram", "life-manager-anicca-en2-affirmation-tiktok", "life-manager-anicca-he", "life-manager-anicca-ja-widget-instagram", "life-manager-anicca-jp1-tiktok", "life-manager-anicca-jp4", "life-manager-anicca-larry-ja-instagram", "life-manager-anicca-main-instagram", "life-manager-anicca-main-tiktok", "life-manager-daily", "life-manager-daily-driver", "life-manager-honne-en", "life-manager-honne-ja", "life-manager-instagram-metrics", "life-manager-tiktok-metrics", "tiktok-browser"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-04, C-08

### P-ebook — register existing product worker/tools

- 対象: `runtime/openclaw/products/ebook.json`
- 境界: `isolated_source`
- 変更: product_id=ebook、job_ids=["ebook-en-instagram-daily", "ebook-en-tiktok-daily", "ebook-ja-instagram-daily", "ebook-ja-tiktok-daily"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-capafy — register existing product worker/tools

- 対象: `runtime/openclaw/products/capafy.json`
- 境界: `isolated_source`
- 変更: product_id=capafy、job_ids=["capafy-browser", "capafy-distribute-daily", "capafy-goal-monitor", "capafy-goal-monitor-daily-close", "capafy-goal-monitor-hourly", "capafy-ig-account-manager", "capafy-ig-marketing-daily", "capafy-loop-daily", "capafy-loop-healthcheck", "capafy-outcome-monitor", "life-manager-capafy-ig"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### P-line-sticker — register existing product worker/tools

- 対象: `runtime/openclaw/products/line-sticker.json`
- 境界: `isolated_source`
- 変更: product_id=line-sticker、job_ids=["line-creators-browser", "line-sticker-factory-hourly", "line-sticker-readback-hourly"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-05, C-06, C-07, C-08

### P-cfo — register existing product worker/tools

- 対象: `runtime/openclaw/products/cfo.json`
- 境界: `isolated_source`
- 変更: product_id=cfo、job_ids=["life-manager-cfo-hourly", "life-manager-financial-report", "life-manager-payout"]。registry固定entrypoint/cadence/effect/schema/既存domain guard/readbackをbindingへ登録。既存業務body/auth/商品dataは保持。
- 検証/完了: binding schema closed、job集合がcatalog一致、旧workerと同input/output、同account/model/task、domain effect/readbackが同じ、native tool迂回0。失敗時は修正してGREENにし、旧経路を最終構成として完了にしない。
- 依存: OC-043, OC-053, C-08

### A-gig-coconala — enable_idle_owner(gig-coconala)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-gig-coconalaと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-gig-coconala, OC-049, OC-052

### A-gig-lancers — enable_idle_owner(gig-lancers)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-gig-lancersと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-gig-lancers, OC-049, OC-052

### A-gig-crowdworks — enable_idle_owner(gig-crowdworks)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-gig-crowdworksと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-gig-crowdworks, OC-049, OC-052

### A-gig-mercor — enable_idle_owner(gig-mercor)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-gig-mercorと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-gig-mercor, OC-049, OC-052

### A-promptbase — enable_idle_owner(promptbase)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-promptbaseと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-promptbase, OC-049, OC-052

### A-writer — enable_idle_owner(writer)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-writerと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-writer, OC-049, OC-052

### A-affiliate — enable_idle_owner(affiliate)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-affiliateと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-affiliate, OC-049, OC-052

### A-investment — enable_idle_owner(investment)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-investmentと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-investment, OC-049, OC-052

### A-agent-economy — enable_idle_owner(agent-economy)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-agent-economyと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-agent-economy, OC-049, OC-052

### A-job-hunter — enable_idle_owner(job-hunter)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-job-hunterと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-job-hunter, OC-049, OC-052

### A-fundraiser — enable_idle_owner(fundraiser)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-fundraiserと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-fundraiser, OC-049, OC-052

### A-connector — enable_idle_owner(connector)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-connectorと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-connector, OC-049, OC-052

### A-self-build — enable_idle_owner(self-build)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-self-buildと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-self-build, OC-049, OC-052

### A-mobile-apps — enable_idle_owner(mobile-apps)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-mobile-appsと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-mobile-apps, OC-049, OC-052

### A-ebook — enable_idle_owner(ebook)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-ebookと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-ebook, OC-049, OC-052

### A-capafy — enable_idle_owner(capafy)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-capafyと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-capafy, OC-049, OC-052

### A-line-sticker — enable_idle_owner(line-sticker)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-line-stickerと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-line-sticker, OC-049, OC-052

### A-cfo — enable_idle_owner(cfo)

- 対象: `config/openclaw-routes.json`
- 境界: `production`
- 変更: P-cfoと共通/native/tool acceptance PASS後、当該productの各model callerをowner deploy lock下で一件ずつ移管。active/queued/reserved/unknownがあればdefer。旧cadence維持、旧仕事は終了まで旧route、次の仕事だけ新route。deterministic jobにmodel追加0、continuous driver停止0。
- 検証/完了: idle対象のみ反映、同task再送0、他owner変更0、RPC開始後fallback0、main immutable releaseのloaded argv確認。
- 依存: P-cfo, OC-049, OC-052

### E-gig-coconala — verify_engine_natural(gig-coconala)

- 対象: `docs/evidence/openclaw-cutover/engines/gig-coconala-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-gig-coconala

### S-hf-gig-apply-direct — commit_transfer(hf-gig-apply-direct)

- 対象: `docs/evidence/openclaw-cutover/schedulers/hf-gig-apply-direct.json`
- 境界: `production`
- 変更: owner=hf-gig-apply-direct、entrypoint=runtime/loop/entry_dispatch.py、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-coconala, OC-046

### S-hf-gig-apply-evidence-gc — commit_transfer(hf-gig-apply-evidence-gc)

- 対象: `docs/evidence/openclaw-cutover/schedulers/hf-gig-apply-evidence-gc.json`
- 境界: `production`
- 変更: owner=hf-gig-apply-evidence-gc、entrypoint=skills/earn/gig/scripts/evidence_gc.py、cadence={"start_interval_seconds": 21600}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-coconala, OC-046

### S-hf-gig-daily-report — commit_transfer(hf-gig-daily-report)

- 対象: `docs/evidence/openclaw-cutover/schedulers/hf-gig-daily-report.json`
- 境界: `production`
- 変更: owner=hf-gig-daily-report、entrypoint=skills/earn/gig/gig_daily_report.sh、cadence={"calendar_interval": {"Hour": 9, "Minute": 7}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-coconala, OC-046

### S-hf-gig-paid-direct — commit_transfer(hf-gig-paid-direct)

- 対象: `docs/evidence/openclaw-cutover/schedulers/hf-gig-paid-direct.json`
- 境界: `production`
- 変更: owner=hf-gig-paid-direct、entrypoint=skills/earn/gig/scripts/paid-direct-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-coconala, OC-046

### S-hf-gig-reply-detector — commit_transfer(hf-gig-reply-detector)

- 対象: `docs/evidence/openclaw-cutover/schedulers/hf-gig-reply-detector.json`
- 境界: `production`
- 変更: owner=hf-gig-reply-detector、entrypoint=skills/earn/gig/scripts/coconala-reply-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-coconala, OC-046

### S-hf-gig-storefront-direct — commit_transfer(hf-gig-storefront-direct)

- 対象: `docs/evidence/openclaw-cutover/schedulers/hf-gig-storefront-direct.json`
- 境界: `production`
- 変更: owner=hf-gig-storefront-direct、entrypoint=runtime/loop/entry_dispatch.py、cadence={"start_interval_seconds": 60}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-coconala, OC-046

### V-gig-coconala — verify_natural(gig-coconala)

- 対象: `docs/evidence/openclaw-cutover/products/gig-coconala-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-gig-coconala, S-hf-gig-apply-direct, S-hf-gig-apply-evidence-gc, S-hf-gig-daily-report, S-hf-gig-paid-direct, S-hf-gig-reply-detector, S-hf-gig-storefront-direct

### E-gig-lancers — verify_engine_natural(gig-lancers)

- 対象: `docs/evidence/openclaw-cutover/engines/gig-lancers-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-gig-lancers

### S-lancers-revenue-application — commit_transfer(lancers-revenue-application)

- 対象: `docs/evidence/openclaw-cutover/schedulers/lancers-revenue-application.json`
- 境界: `production`
- 変更: owner=lancers-revenue-application、entrypoint=skills/earn/lancers/scripts/application-owner、cadence={"start_interval_seconds": 60}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-lancers, OC-046

### S-lancers-revenue-negotiate — commit_transfer(lancers-revenue-negotiate)

- 対象: `docs/evidence/openclaw-cutover/schedulers/lancers-revenue-negotiate.json`
- 境界: `production`
- 変更: owner=lancers-revenue-negotiate、entrypoint=skills/earn/lancers/scripts/negotiate-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-lancers, OC-046

### S-lancers-revenue-paid — commit_transfer(lancers-revenue-paid)

- 対象: `docs/evidence/openclaw-cutover/schedulers/lancers-revenue-paid.json`
- 境界: `production`
- 変更: owner=lancers-revenue-paid、entrypoint=skills/earn/lancers/scripts/paid-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-lancers, OC-046

### S-lancers-revenue-storefront — commit_transfer(lancers-revenue-storefront)

- 対象: `docs/evidence/openclaw-cutover/schedulers/lancers-revenue-storefront.json`
- 境界: `production`
- 変更: owner=lancers-revenue-storefront、entrypoint=skills/earn/lancers/scripts/storefront-owner、cadence={"start_interval_seconds": 1800}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-lancers, OC-046

### S-lancers-revenue-telegram-report — commit_transfer(lancers-revenue-telegram-report)

- 対象: `docs/evidence/openclaw-cutover/schedulers/lancers-revenue-telegram-report.json`
- 境界: `production`
- 変更: owner=lancers-revenue-telegram-report、entrypoint=skills/earn/lancers/scripts/telegram-report-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-lancers, OC-046

### S-lancers-revenue-work-sync — commit_transfer(lancers-revenue-work-sync)

- 対象: `docs/evidence/openclaw-cutover/schedulers/lancers-revenue-work-sync.json`
- 境界: `production`
- 変更: owner=lancers-revenue-work-sync、entrypoint=skills/earn/lancers/scripts/work-sync-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-lancers, OC-046

### V-gig-lancers — verify_natural(gig-lancers)

- 対象: `docs/evidence/openclaw-cutover/products/gig-lancers-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-gig-lancers, S-lancers-revenue-application, S-lancers-revenue-negotiate, S-lancers-revenue-paid, S-lancers-revenue-storefront, S-lancers-revenue-telegram-report, S-lancers-revenue-work-sync

### E-gig-crowdworks — verify_engine_natural(gig-crowdworks)

- 対象: `docs/evidence/openclaw-cutover/engines/gig-crowdworks-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-gig-crowdworks

### S-crowdworks-revenue-application — commit_transfer(crowdworks-revenue-application)

- 対象: `docs/evidence/openclaw-cutover/schedulers/crowdworks-revenue-application.json`
- 境界: `production`
- 変更: owner=crowdworks-revenue-application、entrypoint=skills/earn/crowdworks/scripts/application-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-crowdworks, OC-046

### S-crowdworks-revenue-paid — commit_transfer(crowdworks-revenue-paid)

- 対象: `docs/evidence/openclaw-cutover/schedulers/crowdworks-revenue-paid.json`
- 境界: `production`
- 変更: owner=crowdworks-revenue-paid、entrypoint=skills/earn/crowdworks/scripts/paid-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-crowdworks, OC-046

### S-crowdworks-revenue-reply — commit_transfer(crowdworks-revenue-reply)

- 対象: `docs/evidence/openclaw-cutover/schedulers/crowdworks-revenue-reply.json`
- 境界: `production`
- 変更: owner=crowdworks-revenue-reply、entrypoint=skills/earn/crowdworks/scripts/reply-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-crowdworks, OC-046

### S-crowdworks-revenue-report — commit_transfer(crowdworks-revenue-report)

- 対象: `docs/evidence/openclaw-cutover/schedulers/crowdworks-revenue-report.json`
- 境界: `production`
- 変更: owner=crowdworks-revenue-report、entrypoint=skills/earn/crowdworks/scripts/report-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-crowdworks, OC-046

### V-gig-crowdworks — verify_natural(gig-crowdworks)

- 対象: `docs/evidence/openclaw-cutover/products/gig-crowdworks-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-gig-crowdworks, S-crowdworks-revenue-application, S-crowdworks-revenue-paid, S-crowdworks-revenue-reply, S-crowdworks-revenue-report

### E-gig-mercor — verify_engine_natural(gig-mercor)

- 対象: `docs/evidence/openclaw-cutover/engines/gig-mercor-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-gig-mercor

### S-mercor-revenue-application — commit_transfer(mercor-revenue-application)

- 対象: `docs/evidence/openclaw-cutover/schedulers/mercor-revenue-application.json`
- 境界: `production`
- 変更: owner=mercor-revenue-application、entrypoint=skills/earn/mercor/scripts/application-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-mercor, OC-046

### S-mercor-revenue-paid — commit_transfer(mercor-revenue-paid)

- 対象: `docs/evidence/openclaw-cutover/schedulers/mercor-revenue-paid.json`
- 境界: `production`
- 変更: owner=mercor-revenue-paid、entrypoint=skills/earn/mercor/scripts/paid-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-mercor, OC-046

### S-mercor-revenue-reply — commit_transfer(mercor-revenue-reply)

- 対象: `docs/evidence/openclaw-cutover/schedulers/mercor-revenue-reply.json`
- 境界: `production`
- 変更: owner=mercor-revenue-reply、entrypoint=skills/earn/mercor/scripts/reply-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-gig-mercor, OC-046

### V-gig-mercor — verify_natural(gig-mercor)

- 対象: `docs/evidence/openclaw-cutover/products/gig-mercor-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-gig-mercor, S-mercor-revenue-application, S-mercor-revenue-paid, S-mercor-revenue-reply

### E-promptbase — verify_engine_natural(promptbase)

- 対象: `docs/evidence/openclaw-cutover/engines/promptbase-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-promptbase

### S-promptbase-loop-daily — commit_transfer(promptbase-loop-daily)

- 対象: `docs/evidence/openclaw-cutover/schedulers/promptbase-loop-daily.json`
- 境界: `production`
- 変更: owner=promptbase-loop-daily、entrypoint=skills/earn/promptbase/daily.sh、cadence={"calendar_interval": {"Hour": 4, "Minute": 20}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-promptbase, OC-046

### V-promptbase — verify_natural(promptbase)

- 対象: `docs/evidence/openclaw-cutover/products/promptbase-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-promptbase, S-promptbase-loop-daily

### E-writer — verify_engine_natural(writer)

- 対象: `docs/evidence/openclaw-cutover/engines/writer-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-writer

### S-writer-claim-loop — commit_transfer(writer-claim-loop)

- 対象: `docs/evidence/openclaw-cutover/schedulers/writer-claim-loop.json`
- 境界: `production`
- 変更: owner=writer-claim-loop、entrypoint=skills/writer-agent/scripts/claim-loop-owner、cadence={"start_interval_seconds": 900}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-writer, OC-046

### S-writer-craft-train — commit_transfer(writer-craft-train)

- 対象: `docs/evidence/openclaw-cutover/schedulers/writer-craft-train.json`
- 境界: `production`
- 変更: owner=writer-craft-train、entrypoint=skills/writer-agent/scripts/craft-train-owner、cadence={"calendar_interval": {"Hour": 23, "Minute": 10}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-writer, OC-046

### S-writer-money-sync — commit_transfer(writer-money-sync)

- 対象: `docs/evidence/openclaw-cutover/schedulers/writer-money-sync.json`
- 境界: `production`
- 変更: owner=writer-money-sync、entrypoint=skills/writer-agent/scripts/money-sync-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-writer, OC-046

### S-writer-opportunity-discovery — commit_transfer(writer-opportunity-discovery)

- 対象: `docs/evidence/openclaw-cutover/schedulers/writer-opportunity-discovery.json`
- 境界: `production`
- 変更: owner=writer-opportunity-discovery、entrypoint=skills/writer-agent/scripts/opportunity-discovery-owner、cadence={"start_interval_seconds": 86400}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-writer, OC-046

### S-writer-opportunity-response — commit_transfer(writer-opportunity-response)

- 対象: `docs/evidence/openclaw-cutover/schedulers/writer-opportunity-response.json`
- 境界: `production`
- 変更: owner=writer-opportunity-response、entrypoint=skills/writer-agent/scripts/opportunity-response-owner、cadence={"start_interval_seconds": 900}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-writer, OC-046

### S-writer-report — commit_transfer(writer-report)

- 対象: `docs/evidence/openclaw-cutover/schedulers/writer-report.json`
- 境界: `production`
- 変更: owner=writer-report、entrypoint=skills/writer-agent/scripts/writer-report-owner、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-writer, OC-046

### S-writer-sales-measure — commit_transfer(writer-sales-measure)

- 対象: `docs/evidence/openclaw-cutover/schedulers/writer-sales-measure.json`
- 境界: `production`
- 変更: owner=writer-sales-measure、entrypoint=skills/writer-agent/scripts/writer-sales-measure-worker.sh、cadence={"start_interval_seconds": 3600}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-writer, OC-046

### V-writer — verify_natural(writer)

- 対象: `docs/evidence/openclaw-cutover/products/writer-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-writer, S-writer-claim-loop, S-writer-craft-train, S-writer-money-sync, S-writer-opportunity-discovery, S-writer-opportunity-response, S-writer-report, S-writer-sales-measure

### E-affiliate — verify_engine_natural(affiliate)

- 対象: `docs/evidence/openclaw-cutover/engines/affiliate-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-affiliate

### S-affiliate-composition — commit_transfer(affiliate-composition)

- 対象: `docs/evidence/openclaw-cutover/schedulers/affiliate-composition.json`
- 境界: `production`
- 変更: owner=affiliate-composition、entrypoint=skills/affiliate/affiliate、cadence={"start_interval_seconds": 600}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-affiliate, OC-046

### S-affiliate-loop — commit_transfer(affiliate-loop)

- 対象: `docs/evidence/openclaw-cutover/schedulers/affiliate-loop.json`
- 境界: `production`
- 変更: owner=affiliate-loop、entrypoint=skills/affiliate/affiliate、cadence={"start_interval_seconds": 600}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-affiliate, OC-046

### S-affiliate-source-refresh — commit_transfer(affiliate-source-refresh)

- 対象: `docs/evidence/openclaw-cutover/schedulers/affiliate-source-refresh.json`
- 境界: `production`
- 変更: owner=affiliate-source-refresh、entrypoint=skills/affiliate/affiliate、cadence={"start_interval_seconds": 600}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-affiliate, OC-046

### V-affiliate — verify_natural(affiliate)

- 対象: `docs/evidence/openclaw-cutover/products/affiliate-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-affiliate, S-affiliate-composition, S-affiliate-loop, S-affiliate-source-refresh

### E-investment — verify_engine_natural(investment)

- 対象: `docs/evidence/openclaw-cutover/engines/investment-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-investment

### S-alpaca-investment-paper — commit_transfer(alpaca-investment-paper)

- 対象: `docs/evidence/openclaw-cutover/schedulers/alpaca-investment-paper.json`
- 境界: `production`
- 変更: owner=alpaca-investment-paper、entrypoint=skills/alpaca-investment/run.py、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-investment, OC-046

### S-alpaca-investment-live — commit_transfer(alpaca-investment-live)

- 対象: `docs/evidence/openclaw-cutover/schedulers/alpaca-investment-live.json`
- 境界: `production`
- 変更: owner=alpaca-investment-live、entrypoint=skills/alpaca-investment/run.py、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-investment, OC-046

### S-investment-cross-venue-report — commit_transfer(investment-cross-venue-report)

- 対象: `docs/evidence/openclaw-cutover/schedulers/investment-cross-venue-report.json`
- 境界: `production`
- 変更: owner=investment-cross-venue-report、entrypoint=apps/life-manager/investment-core/cross_venue_run.py、cadence={"start_interval_seconds": 86400}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-investment, OC-046

### S-investment-strategy-validation — commit_transfer(investment-strategy-validation)

- 対象: `docs/evidence/openclaw-cutover/schedulers/investment-strategy-validation.json`
- 境界: `production`
- 変更: owner=investment-strategy-validation、entrypoint=skills/alpaca-investment/validation_runner.py、cadence={"calendar_interval": {"Weekday": 2, "Hour": 14, "Minute": 30}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-investment, OC-046

### V-investment — verify_natural(investment)

- 対象: `docs/evidence/openclaw-cutover/products/investment-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-investment, S-alpaca-investment-paper, S-alpaca-investment-live, S-investment-cross-venue-report, S-investment-strategy-validation

### E-agent-economy — verify_engine_natural(agent-economy)

- 対象: `docs/evidence/openclaw-cutover/engines/agent-economy-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-agent-economy

### S-citizen-refill — commit_transfer(citizen-refill)

- 対象: `docs/evidence/openclaw-cutover/schedulers/citizen-refill.json`
- 境界: `production`
- 変更: owner=citizen-refill、entrypoint=bin/citizen-refill-launchd、cadence={"start_interval_seconds": 3600}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### S-life-manager-x402-ledger — commit_transfer(life-manager-x402-ledger)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-x402-ledger.json`
- 境界: `production`
- 変更: owner=life-manager-x402-ledger、entrypoint=apps/life-manager/scripts/x402-sale-ledger-boot.sh、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### S-sol-funding — commit_transfer(sol-funding)

- 対象: `docs/evidence/openclaw-cutover/schedulers/sol-funding.json`
- 境界: `production`
- 変更: owner=sol-funding、entrypoint=skills/earn/sol-funding-owner、cadence={"start_interval_seconds": 60}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### S-x402-acquisition-controller — commit_transfer(x402-acquisition-controller)

- 対象: `docs/evidence/openclaw-cutover/schedulers/x402-acquisition-controller.json`
- 境界: `production`
- 変更: owner=x402-acquisition-controller、entrypoint=skills/earn/x402-sell/acquisition-controller-boot.sh、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### S-x402-experiment-franklin1 — commit_transfer(x402-experiment-franklin1)

- 対象: `docs/evidence/openclaw-cutover/schedulers/x402-experiment-franklin1.json`
- 境界: `production`
- 変更: owner=x402-experiment-franklin1、entrypoint=skills/earn/x402-sell/experiment-tick.mjs、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### S-x402-inflow-watch — commit_transfer(x402-inflow-watch)

- 対象: `docs/evidence/openclaw-cutover/schedulers/x402-inflow-watch.json`
- 境界: `production`
- 変更: owner=x402-inflow-watch、entrypoint=skills/earn/x402-sell/watch-inflow.sh、cadence={"calendar_interval": [{"Minute": 5}, {"Minute": 35}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### S-x402-inflow-watch-claude-p — commit_transfer(x402-inflow-watch-claude-p)

- 対象: `docs/evidence/openclaw-cutover/schedulers/x402-inflow-watch-claude-p.json`
- 境界: `production`
- 変更: owner=x402-inflow-watch-claude-p、entrypoint=skills/earn/x402-sell/watch-inflow.sh、cadence={"calendar_interval": [{"Minute": 5}, {"Minute": 35}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### S-x402-inflow-watch-franklin1 — commit_transfer(x402-inflow-watch-franklin1)

- 対象: `docs/evidence/openclaw-cutover/schedulers/x402-inflow-watch-franklin1.json`
- 境界: `production`
- 変更: owner=x402-inflow-watch-franklin1、entrypoint=skills/earn/x402-sell/watch-inflow.sh、cadence={"calendar_interval": [{"Minute": 5}, {"Minute": 35}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### S-x402-inflow-watch-franklin2 — commit_transfer(x402-inflow-watch-franklin2)

- 対象: `docs/evidence/openclaw-cutover/schedulers/x402-inflow-watch-franklin2.json`
- 境界: `production`
- 変更: owner=x402-inflow-watch-franklin2、entrypoint=skills/earn/x402-sell/watch-inflow.sh、cadence={"calendar_interval": [{"Minute": 5}, {"Minute": 35}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### S-x402-sale-observer — commit_transfer(x402-sale-observer)

- 対象: `docs/evidence/openclaw-cutover/schedulers/x402-sale-observer.json`
- 境界: `production`
- 変更: owner=x402-sale-observer、entrypoint=skills/earn/x402-sell/sale-observer-boot.sh、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### S-x402-settlement-recorder — commit_transfer(x402-settlement-recorder)

- 対象: `docs/evidence/openclaw-cutover/schedulers/x402-settlement-recorder.json`
- 境界: `production`
- 変更: owner=x402-settlement-recorder、entrypoint=skills/earn/x402-sell/settlement-recorder-boot.sh、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-agent-economy, OC-046

### V-agent-economy — verify_natural(agent-economy)

- 対象: `docs/evidence/openclaw-cutover/products/agent-economy-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-agent-economy, S-citizen-refill, S-life-manager-x402-ledger, S-sol-funding, S-x402-acquisition-controller, S-x402-experiment-franklin1, S-x402-inflow-watch, S-x402-inflow-watch-claude-p, S-x402-inflow-watch-franklin1, S-x402-inflow-watch-franklin2, S-x402-sale-observer, S-x402-settlement-recorder

### E-job-hunter — verify_engine_natural(job-hunter)

- 対象: `docs/evidence/openclaw-cutover/engines/job-hunter-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-job-hunter

### S-job-search-daily — commit_transfer(job-search-daily)

- 対象: `docs/evidence/openclaw-cutover/schedulers/job-search-daily.json`
- 境界: `production`
- 変更: owner=job-search-daily、entrypoint=apps/job-search-loop/scripts/run-daily.sh、cadence={"start_interval_seconds": 1800}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-job-hunter, OC-046

### S-job-search-health — commit_transfer(job-search-health)

- 対象: `docs/evidence/openclaw-cutover/schedulers/job-search-health.json`
- 境界: `production`
- 変更: owner=job-search-health、entrypoint=apps/job-search-loop/scripts/run-health.sh、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-job-hunter, OC-046

### S-job-search-inbox — commit_transfer(job-search-inbox)

- 対象: `docs/evidence/openclaw-cutover/schedulers/job-search-inbox.json`
- 境界: `production`
- 変更: owner=job-search-inbox、entrypoint=apps/job-search-loop/scripts/run-inbox.sh、cadence={"start_interval_seconds": 900}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-job-hunter, OC-046

### S-job-search-learning — commit_transfer(job-search-learning)

- 対象: `docs/evidence/openclaw-cutover/schedulers/job-search-learning.json`
- 境界: `production`
- 変更: owner=job-search-learning、entrypoint=apps/job-search-loop/scripts/run-learning.sh、cadence={"calendar_interval": {"Hour": 9, "Minute": 15}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-job-hunter, OC-046

### V-job-hunter — verify_natural(job-hunter)

- 対象: `docs/evidence/openclaw-cutover/products/job-hunter-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-job-hunter, S-job-search-daily, S-job-search-health, S-job-search-inbox, S-job-search-learning

### E-fundraiser — verify_engine_natural(fundraiser)

- 対象: `docs/evidence/openclaw-cutover/engines/fundraiser-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-fundraiser

### S-fundraiser — commit_transfer(fundraiser)

- 対象: `docs/evidence/openclaw-cutover/schedulers/fundraiser.json`
- 境界: `production`
- 変更: owner=fundraiser、entrypoint=skills/fundraiser-agent/runtime/run.sh、cadence={"start_interval_seconds": 3600}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-fundraiser, OC-046

### V-fundraiser — verify_natural(fundraiser)

- 対象: `docs/evidence/openclaw-cutover/products/fundraiser-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-fundraiser, S-fundraiser

### E-connector — verify_engine_natural(connector)

- 対象: `docs/evidence/openclaw-cutover/engines/connector-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-connector

### S-life-manager-connector-native — commit_transfer(life-manager-connector-native)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-connector-native.json`
- 境界: `production`
- 変更: owner=life-manager-connector-native、entrypoint=skills/connector/run.sh、cadence={"start_interval_seconds": 1800}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-connector, OC-046

### V-connector — verify_natural(connector)

- 対象: `docs/evidence/openclaw-cutover/products/connector-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-connector, S-life-manager-connector-native

### E-self-build — verify_engine_natural(self-build)

- 対象: `docs/evidence/openclaw-cutover/engines/self-build-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-self-build

### S-life-manager-dev — commit_transfer(life-manager-dev)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-dev.json`
- 境界: `production`
- 変更: owner=life-manager-dev、entrypoint=apps/life-manager/scripts/life-manager-dev-daily.js、cadence={"calendar_interval": {"Hour": 4, "Minute": 10}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-self-build, OC-046

### S-life-manager-recovery-supervisor — commit_transfer(life-manager-recovery-supervisor)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-recovery-supervisor.json`
- 境界: `production`
- 変更: owner=life-manager-recovery-supervisor、entrypoint=runtime/loop/recovery-supervisor-cli.mjs、cadence={"start_interval_seconds": 60}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-self-build, OC-046

### S-life-manager-selfbuild — commit_transfer(life-manager-selfbuild)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-selfbuild.json`
- 境界: `production`
- 変更: owner=life-manager-selfbuild、entrypoint=skills/life-manager/self-build-daily.sh、cadence={"calendar_interval": {"Hour": 4, "Minute": 10}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-self-build, OC-046

### S-self-improve-evolve — commit_transfer(self-improve-evolve)

- 対象: `docs/evidence/openclaw-cutover/schedulers/self-improve-evolve.json`
- 境界: `production`
- 変更: owner=self-improve-evolve、entrypoint=skills/earn/marketing-engine/report/scheduled_runner.py、cadence={"start_interval_seconds": 21600}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-self-build, OC-046

### V-self-build — verify_natural(self-build)

- 対象: `docs/evidence/openclaw-cutover/products/self-build-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-self-build, S-life-manager-dev, S-life-manager-recovery-supervisor, S-life-manager-selfbuild, S-self-improve-evolve

### E-mobile-apps — verify_engine_natural(mobile-apps)

- 対象: `docs/evidence/openclaw-cutover/engines/mobile-apps-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-mobile-apps

### S-life-manager-anicca-affirmation-youtube — commit_transfer(life-manager-anicca-affirmation-youtube)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-affirmation-youtube.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-affirmation-youtube、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 8, "Minute": 15}, {"Hour": 14, "Minute": 15}, {"Hour": 20, "Minute": 15}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-ai-youtube — commit_transfer(life-manager-anicca-ai-youtube)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-ai-youtube.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-ai-youtube、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 7, "Minute": 45}, {"Hour": 13, "Minute": 15}, {"Hour": 19, "Minute": 45}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-buddha-tiktok — commit_transfer(life-manager-anicca-buddha-tiktok)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-buddha-tiktok.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-buddha-tiktok、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 7, "Minute": 0}, {"Hour": 13, "Minute": 0}, {"Hour": 20, "Minute": 0}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-en-affirmation-instagram — commit_transfer(life-manager-anicca-en-affirmation-instagram)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-en-affirmation-instagram.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-en-affirmation-instagram、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 10, "Minute": 0}, {"Hour": 15, "Minute": 0}, {"Hour": 20, "Minute": 0}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-en-affirmation-tiktok — commit_transfer(life-manager-anicca-en-affirmation-tiktok)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-en-affirmation-tiktok.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-en-affirmation-tiktok、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 9, "Minute": 15}, {"Hour": 14, "Minute": 15}, {"Hour": 20, "Minute": 15}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-en-card-instagram — commit_transfer(life-manager-anicca-en-card-instagram)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-en-card-instagram.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-en-card-instagram、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 8, "Minute": 45}, {"Hour": 12, "Minute": 45}, {"Hour": 21, "Minute": 30}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-en-slideshow-tiktok — commit_transfer(life-manager-anicca-en-slideshow-tiktok)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-en-slideshow-tiktok.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-en-slideshow-tiktok、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 9, "Minute": 0}, {"Hour": 15, "Minute": 0}, {"Hour": 21, "Minute": 0}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-en-widget-instagram — commit_transfer(life-manager-anicca-en-widget-instagram)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-en-widget-instagram.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-en-widget-instagram、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 7, "Minute": 30}, {"Hour": 9, "Minute": 30}, {"Hour": 19, "Minute": 0}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-en2-affirmation-tiktok — commit_transfer(life-manager-anicca-en2-affirmation-tiktok)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-en2-affirmation-tiktok.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-en2-affirmation-tiktok、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 9, "Minute": 30}, {"Hour": 14, "Minute": 30}, {"Hour": 20, "Minute": 30}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-he — commit_transfer(life-manager-anicca-he)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-he.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-he、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 7, "Minute": 15}, {"Hour": 13, "Minute": 45}, {"Hour": 18, "Minute": 15}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-ja-widget-instagram — commit_transfer(life-manager-anicca-ja-widget-instagram)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-ja-widget-instagram.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-ja-widget-instagram、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 8, "Minute": 5}, {"Hour": 13, "Minute": 5}, {"Hour": 18, "Minute": 20}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-jp1-tiktok — commit_transfer(life-manager-anicca-jp1-tiktok)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-jp1-tiktok.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-jp1-tiktok、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 6, "Minute": 30}, {"Hour": 12, "Minute": 0}, {"Hour": 18, "Minute": 0}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-jp4 — commit_transfer(life-manager-anicca-jp4)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-jp4.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-jp4、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 9, "Minute": 15}, {"Hour": 15, "Minute": 15}, {"Hour": 20, "Minute": 45}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-larry-ja-instagram — commit_transfer(life-manager-anicca-larry-ja-instagram)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-larry-ja-instagram.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-larry-ja-instagram、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 10, "Minute": 30}, {"Hour": 16, "Minute": 30}, {"Hour": 22, "Minute": 30}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-main-instagram — commit_transfer(life-manager-anicca-main-instagram)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-main-instagram.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-main-instagram、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 8, "Minute": 10}, {"Hour": 13, "Minute": 10}, {"Hour": 19, "Minute": 10}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-anicca-main-tiktok — commit_transfer(life-manager-anicca-main-tiktok)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-anicca-main-tiktok.json`
- 境界: `production`
- 変更: owner=life-manager-anicca-main-tiktok、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 8, "Minute": 0}, {"Hour": 16, "Minute": 0}, {"Hour": 22, "Minute": 37}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-daily — commit_transfer(life-manager-daily)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-daily.json`
- 境界: `production`
- 変更: owner=life-manager-daily、entrypoint=skills/life-manager/life-manager-daily.sh、cadence={"calendar_interval": {"Hour": 10, "Minute": 15}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-honne-en — commit_transfer(life-manager-honne-en)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-honne-en.json`
- 境界: `production`
- 変更: owner=life-manager-honne-en、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 7, "Minute": 0}, {"Hour": 11, "Minute": 0}, {"Hour": 20, "Minute": 30}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-honne-ja — commit_transfer(life-manager-honne-ja)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-honne-ja.json`
- 境界: `production`
- 変更: owner=life-manager-honne-ja、entrypoint=apps/life-manager/scripts/mobile-app、cadence={"calendar_interval": [{"Hour": 8, "Minute": 30}, {"Hour": 12, "Minute": 30}, {"Hour": 21, "Minute": 30}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-instagram-metrics — commit_transfer(life-manager-instagram-metrics)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-instagram-metrics.json`
- 境界: `production`
- 変更: owner=life-manager-instagram-metrics、entrypoint=apps/life-manager/scripts/instagram-metrics-production-boot.sh、cadence={"start_interval_seconds": 1800}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### S-life-manager-tiktok-metrics — commit_transfer(life-manager-tiktok-metrics)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-tiktok-metrics.json`
- 境界: `production`
- 変更: owner=life-manager-tiktok-metrics、entrypoint=apps/life-manager/scripts/tiktok-metrics-production-boot.sh、cadence={"start_interval_seconds": 1800}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-mobile-apps, OC-046

### V-mobile-apps — verify_natural(mobile-apps)

- 対象: `docs/evidence/openclaw-cutover/products/mobile-apps-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-mobile-apps, S-life-manager-anicca-affirmation-youtube, S-life-manager-anicca-ai-youtube, S-life-manager-anicca-buddha-tiktok, S-life-manager-anicca-en-affirmation-instagram, S-life-manager-anicca-en-affirmation-tiktok, S-life-manager-anicca-en-card-instagram, S-life-manager-anicca-en-slideshow-tiktok, S-life-manager-anicca-en-widget-instagram, S-life-manager-anicca-en2-affirmation-tiktok, S-life-manager-anicca-he, S-life-manager-anicca-ja-widget-instagram, S-life-manager-anicca-jp1-tiktok, S-life-manager-anicca-jp4, S-life-manager-anicca-larry-ja-instagram, S-life-manager-anicca-main-instagram, S-life-manager-anicca-main-tiktok, S-life-manager-daily, S-life-manager-honne-en, S-life-manager-honne-ja, S-life-manager-instagram-metrics, S-life-manager-tiktok-metrics

### E-ebook — verify_engine_natural(ebook)

- 対象: `docs/evidence/openclaw-cutover/engines/ebook-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-ebook

### S-ebook-en-instagram-daily — commit_transfer(ebook-en-instagram-daily)

- 対象: `docs/evidence/openclaw-cutover/schedulers/ebook-en-instagram-daily.json`
- 境界: `production`
- 変更: owner=ebook-en-instagram-daily、entrypoint=apps/life-manager/scripts/ebook-distribute-daily.sh、cadence={"calendar_interval": [{"Hour": 8, "Minute": 0}, {"Hour": 14, "Minute": 0}, {"Hour": 21, "Minute": 0}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-ebook, OC-046

### S-ebook-en-tiktok-daily — commit_transfer(ebook-en-tiktok-daily)

- 対象: `docs/evidence/openclaw-cutover/schedulers/ebook-en-tiktok-daily.json`
- 境界: `production`
- 変更: owner=ebook-en-tiktok-daily、entrypoint=apps/life-manager/scripts/ebook-distribute-daily.sh、cadence={"calendar_interval": [{"Hour": 8, "Minute": 0}, {"Hour": 14, "Minute": 0}, {"Hour": 21, "Minute": 0}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-ebook, OC-046

### S-ebook-ja-instagram-daily — commit_transfer(ebook-ja-instagram-daily)

- 対象: `docs/evidence/openclaw-cutover/schedulers/ebook-ja-instagram-daily.json`
- 境界: `production`
- 変更: owner=ebook-ja-instagram-daily、entrypoint=apps/life-manager/scripts/ebook-distribute-daily.sh、cadence={"calendar_interval": [{"Hour": 7, "Minute": 0}, {"Hour": 12, "Minute": 30}, {"Hour": 20, "Minute": 0}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-ebook, OC-046

### S-ebook-ja-tiktok-daily — commit_transfer(ebook-ja-tiktok-daily)

- 対象: `docs/evidence/openclaw-cutover/schedulers/ebook-ja-tiktok-daily.json`
- 境界: `production`
- 変更: owner=ebook-ja-tiktok-daily、entrypoint=apps/life-manager/scripts/ebook-distribute-daily.sh、cadence={"calendar_interval": [{"Hour": 7, "Minute": 0}, {"Hour": 12, "Minute": 30}, {"Hour": 20, "Minute": 0}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-ebook, OC-046

### V-ebook — verify_natural(ebook)

- 対象: `docs/evidence/openclaw-cutover/products/ebook-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-ebook, S-ebook-en-instagram-daily, S-ebook-en-tiktok-daily, S-ebook-ja-instagram-daily, S-ebook-ja-tiktok-daily

### E-capafy — verify_engine_natural(capafy)

- 対象: `docs/evidence/openclaw-cutover/engines/capafy-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-capafy

### S-capafy-distribute-daily — commit_transfer(capafy-distribute-daily)

- 対象: `docs/evidence/openclaw-cutover/schedulers/capafy-distribute-daily.json`
- 境界: `production`
- 変更: owner=capafy-distribute-daily、entrypoint=skills/earn/capafy-marketing/capafy-distribute-daily.sh、cadence={"calendar_interval": [{"Hour": 1, "Minute": 15}, {"Hour": 4, "Minute": 15}, {"Hour": 7, "Minute": 15}, {"Hour": 10, "Minute": 15}, {"Hour": 13, "Minute": 15}, {"Hour": 16, "Minute": 15}, {"Hour": 19, "Minute": 15}, {"Hour": 22, "Minute": 15}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-capafy, OC-046

### S-capafy-goal-monitor — commit_transfer(capafy-goal-monitor)

- 対象: `docs/evidence/openclaw-cutover/schedulers/capafy-goal-monitor.json`
- 境界: `production`
- 変更: owner=capafy-goal-monitor、entrypoint=skills/earn/capafy-marketing/capafy-goal-monitor.sh、cadence={"calendar_interval": {"Hour": 9, "Minute": 30}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-capafy, OC-046

### S-capafy-goal-monitor-daily-close — commit_transfer(capafy-goal-monitor-daily-close)

- 対象: `docs/evidence/openclaw-cutover/schedulers/capafy-goal-monitor-daily-close.json`
- 境界: `production`
- 変更: owner=capafy-goal-monitor-daily-close、entrypoint=skills/earn/capafy-marketing/capafy-goal-monitor.sh、cadence={"calendar_interval": {"Hour": 23, "Minute": 50}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-capafy, OC-046

### S-capafy-goal-monitor-hourly — commit_transfer(capafy-goal-monitor-hourly)

- 対象: `docs/evidence/openclaw-cutover/schedulers/capafy-goal-monitor-hourly.json`
- 境界: `production`
- 変更: owner=capafy-goal-monitor-hourly、entrypoint=skills/earn/capafy-marketing/capafy-goal-monitor.sh、cadence={"calendar_interval": {"Minute": 7}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-capafy, OC-046

### S-capafy-ig-account-manager — commit_transfer(capafy-ig-account-manager)

- 対象: `docs/evidence/openclaw-cutover/schedulers/capafy-ig-account-manager.json`
- 境界: `production`
- 変更: owner=capafy-ig-account-manager、entrypoint=skills/earn/capafy-marketing/capafy-ig-account-manager.sh、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-capafy, OC-046

### S-capafy-ig-marketing-daily — commit_transfer(capafy-ig-marketing-daily)

- 対象: `docs/evidence/openclaw-cutover/schedulers/capafy-ig-marketing-daily.json`
- 境界: `production`
- 変更: owner=capafy-ig-marketing-daily、entrypoint=skills/earn/capafy-marketing/capafy-ig-marketing-daily.sh、cadence={"start_interval_seconds": 3600}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-capafy, OC-046

### S-capafy-loop-daily — commit_transfer(capafy-loop-daily)

- 対象: `docs/evidence/openclaw-cutover/schedulers/capafy-loop-daily.json`
- 境界: `production`
- 変更: owner=capafy-loop-daily、entrypoint=skills/self/capafy-loop/capafy-loop-daily.sh、cadence={"start_interval_seconds": 900}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-capafy, OC-046

### S-capafy-loop-healthcheck — commit_transfer(capafy-loop-healthcheck)

- 対象: `docs/evidence/openclaw-cutover/schedulers/capafy-loop-healthcheck.json`
- 境界: `production`
- 変更: owner=capafy-loop-healthcheck、entrypoint=skills/self/capafy-loop/capafy-loop-healthcheck.sh、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-capafy, OC-046

### S-capafy-outcome-monitor — commit_transfer(capafy-outcome-monitor)

- 対象: `docs/evidence/openclaw-cutover/schedulers/capafy-outcome-monitor.json`
- 境界: `production`
- 変更: owner=capafy-outcome-monitor、entrypoint=skills/earn/capafy-marketing/capafy-outcome-monitor.sh、cadence={"start_interval_seconds": 60}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-capafy, OC-046

### S-life-manager-capafy-ig — commit_transfer(life-manager-capafy-ig)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-capafy-ig.json`
- 境界: `production`
- 変更: owner=life-manager-capafy-ig、entrypoint=apps/life-manager/scripts/capafy-ig-reel、cadence={"calendar_interval": [{"Hour": 9, "Minute": 0}, {"Hour": 14, "Minute": 0}, {"Hour": 20, "Minute": 0}]}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-capafy, OC-046

### V-capafy — verify_natural(capafy)

- 対象: `docs/evidence/openclaw-cutover/products/capafy-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-capafy, S-capafy-distribute-daily, S-capafy-goal-monitor, S-capafy-goal-monitor-daily-close, S-capafy-goal-monitor-hourly, S-capafy-ig-account-manager, S-capafy-ig-marketing-daily, S-capafy-loop-daily, S-capafy-loop-healthcheck, S-capafy-outcome-monitor, S-life-manager-capafy-ig

### E-line-sticker — verify_engine_natural(line-sticker)

- 対象: `docs/evidence/openclaw-cutover/engines/line-sticker-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-line-sticker

### S-line-sticker-factory-hourly — commit_transfer(line-sticker-factory-hourly)

- 対象: `docs/evidence/openclaw-cutover/schedulers/line-sticker-factory-hourly.json`
- 境界: `production`
- 変更: owner=line-sticker-factory-hourly、entrypoint=skills/earn/line-sticker/line-sticker-factory.sh、cadence={"start_interval_seconds": 900}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-line-sticker, OC-046

### S-line-sticker-readback-hourly — commit_transfer(line-sticker-readback-hourly)

- 対象: `docs/evidence/openclaw-cutover/schedulers/line-sticker-readback-hourly.json`
- 境界: `production`
- 変更: owner=line-sticker-readback-hourly、entrypoint=skills/earn/line-sticker/line-sticker-readback.sh、cadence={"calendar_interval": {"Minute": 23}}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-line-sticker, OC-046

### V-line-sticker — verify_natural(line-sticker)

- 対象: `docs/evidence/openclaw-cutover/products/line-sticker-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-line-sticker, S-line-sticker-factory-hourly, S-line-sticker-readback-hourly

### E-cfo — verify_engine_natural(cfo)

- 対象: `docs/evidence/openclaw-cutover/engines/cfo-natural.json`
- 境界: `production`
- 変更: 旧cadenceのまま、新engineで当該ownerの次の自然仕事を確認する。release/owner/occurrence/task/session/traceを元の業務contract/公式receiptとjoin。確認前にschedulerを移さない。
- 検証/完了: 対象model経路native Codexのみ、同業務receipt、replay-zero、未知effectなら未完。running ownerの中断/再送0。
- 依存: A-cfo

### S-life-manager-cfo-hourly — commit_transfer(life-manager-cfo-hourly)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-cfo-hourly.json`
- 境界: `production`
- 変更: owner=life-manager-cfo-hourly、entrypoint=skills/cfo/run.sh、cadence={"start_interval_seconds": 3600}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-cfo, OC-046

### S-life-manager-financial-report — commit_transfer(life-manager-financial-report)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-financial-report.json`
- 境界: `production`
- 変更: owner=life-manager-financial-report、entrypoint=apps/life-manager/scripts/financial-report-boot.sh、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-cfo, OC-046

### S-life-manager-payout — commit_transfer(life-manager-payout)

- 対象: `docs/evidence/openclaw-cutover/schedulers/life-manager-payout.json`
- 境界: `production`
- 変更: owner=life-manager-payout、entrypoint=apps/life-manager/scripts/payout-boot.sh、cadence={"start_interval_seconds": 300}。OC045/046を使い新cron disabled作成→idle/予約/queue/未知effect解消→旧future wake停止readback→新cron enabled→唯一scheduler確認。失敗時はOC047で当該ownerだけ復元。
- 検証/完了: 新cron1/旧future wake0、進行中run中断0、外部効果再送0、auth/ledger保持、epoch/argv/自然occurrence/rollback receipt保存。
- 依存: E-cfo, OC-046

### V-cfo — verify_natural(cfo)

- 対象: `docs/evidence/openclaw-cutover/products/cfo-natural.json`
- 境界: `production`
- 変更: catalogの各jobについて次の自然仕事のrelease/owner/occurrence/run/task/session/traceを業務contractとjoin。publish/application/delivery/settlementは公式readbackを使用。unknownは0やsuccessへ変換しない。
- 検証/完了: 全job coverage、旧成果契約維持、replay-zero、既存order/receipt/cost保持。test/モデルfinal/exit0だけではPASS不可。
- 依存: A-cfo, S-life-manager-cfo-hourly, S-life-manager-financial-report, S-life-manager-payout

### F-04 — remove only unreferenced legacy routing

- 対象: `runtime/agent-runner/agent_runner.py`
- 境界: `retirement`
- 変更: 全V自然確認後、旧model runtime dispatch/provider fallback/旧job scheduling分岐の参照を0にして削除。bin/lm-loopはOpenClaw操作への互換facadeへ変更。native Codex binary、OS browser driver、商品worker、domain budget/effect/readback/finance/dataは保持する。
- 検証/完了: 全caller closure参照0、既存source acceptance＋natural records一致。
- 依存: V-gig-coconala, V-gig-lancers, V-gig-crowdworks, V-gig-mercor, V-promptbase, V-writer, V-affiliate, V-investment, V-agent-economy, V-job-hunter, V-fundraiser, V-connector, V-self-build, V-mobile-apps, V-ebook, V-capafy, V-line-sticker, V-cfo, F-01, F-02, F-03

### F-07 — final product/job reconciliation

- 対象: `docs/evidence/openclaw-cutover/final.json`
- 境界: `production`
- 変更: 全catalog business jobsの新engine管理、全finiteのOpenClaw cron、continuousの同OS/browser driver、source/main/release/session/trace/domain成果、旧harness参照0、rollbackの一時退避以外旧job authority0を照合して保存。旧harnessを残したまま全移行完了とはしない。
- 検証/完了: 最新catalog全job coverage、全finite cron移管、continuous owner維持、未確認effect0、旧harness参照0、自然成果readback。性能改善は実測のみ。
- 依存: F-04, F-05, F-06
