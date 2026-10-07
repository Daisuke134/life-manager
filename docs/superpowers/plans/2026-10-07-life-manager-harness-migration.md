# Life Managerハーネス移行 — ファイル・関数単位の実行計画

> 実行agentは`superpowers:executing-plans`を読む。コード実装は`gpt-6-luna / max`、計画・検証は`gpt-6.1-sol / medium`。各atomは一つの関数・設定箇所・受け入れrecordを変更する。code atomは記載testをRED→最小実装→GREENとして同じ契約で完了する。source-only commit/push/PRは関連atomのまとまりで行い、技術受け入れ後にだけpromotion atomへ進む。

**目的:** OpenClawへagent executionを段階移行するため、実装者がファイル・API・contract・assertionを決め直さず着手できる作業へ分解する。
**構成:** 公式GatewayClient、既存Python admission/fence、owner-bound plugin、既存runner互換。初期cronはdisabled。単一ownerの自然実行後にscheduleを移行する。
**技術:** openclaw2026.9.8、gateway-client/protocol2026.8.1、Node24.16以上の対応LTS、Python既存runtime。
**設計:** [移行設計](../specs/2026-10-07-life-manager-harness-migration-design.md)。**状態正本:** 統合SSOTのHA lane。

## 前版の訂正と実行範囲

旧HM-00〜17はroadmapだった。『互換APIを決める』『適切なtoolsを接続する』『残ownerを移す』の中に未確定の仕事があり、90checkboxという数だけでatomicと呼べない。本版はその実行手順を置換し、設計末尾にtype・RPC・key・status契約を固定した。旧HM IDはtraceability用の成果区分として残し、HA IDが実行atomとなる。

今は計画作成のみ。全atom未着手、最初の実装atomはHA-001。OSS/cloud配布atomは`条件付き`であり、仮定が採用されるまで実装cursorへ入れない。実装開始、本番切替、公開、hosted service開始、資金支出は本依頼に含まない。

互換/fail-closedの外部実装を実測前に成功と断定しない。HA-012/026は具体入力・assertion付きの実行可能な契約テストで、FAIL時は後続activation禁止。未知APIを実装者へ選ばせるtaskではない。全販売toolが既にportableだという意味でもない。

## 全atomの共通制約

- 最新main専用worktree/lease、他owner/state/profileへwriteなし。既存OpenClaw2026.6.1をupgradeしない。
- source secretsなし、credentialは唯一のSSOT。作成runtime configのtoken/keyはSecretRefのみ。
- model/providerをharness移行と同時に変更しない。unsupported image/repair/resumeは事前にeligiblefalse。
- scheduler<=1、model claimは同global authority、caller死亡/TTLだけでcapacity再利用なし、effect unknownから再送なし。
- fake acceptanceはprivate state/providerで実施。本番故意killなし。
- verification commandはrepo rootから実行。Nodecode testsは`node --test runtime/openclaw/tests/<記載名>`、Python testsは`python3 -m pytest runtime/openclaw/tests/<記載名> -q`。既存test/acceptanceは各atom記載pathを使う。
- source acceptanceと自然run/公式receipt/経済成果を分離。未測定costはunknown、採用は同task総費用<=base、task>=base、安全全PASS、RSS host許容内。

## ファイル・関数単位のTODO

以下のcheckboxは手順、進行状態はSSOTだけに置く。`変更`に複数の独立APIを混ぜない。関数が同じfileにあっても別atomにする。

### HA-001 — dependencies

- [ ] **対象:** `runtime/openclaw/package.json`
  **変更:** 新規private ESM packageを作る。openclaw=2026.9.8、@openclaw/gateway-client=2026.8.1、@openclaw/gateway-protocol=2026.8.1、engines.node=>=24.16.0 <25 || >=26.1.0。scripts.test=node --test tests/*.test.mjs。
  **検証・完了:** JSONの3version完全一致を検証。npm install --package-lock-only --ignore-scripts、npm ci --ignore-scriptsを専用dirで実行。package-lock.jsonを同差分に追加。
  **依存:** なし。

### HA-002 — resolveHarnessPaths(env, homedir) -> HarnessPaths

- [ ] **対象:** `runtime/openclaw/paths.mjs`
  **変更:** 既存apps/life-manager/lib/runtime-paths.jsのresolveDataRootを呼ぶ。stateRoot=<dataRoot>/openclaw、configPath=<stateRoot>/config.json、dispatchRoot=<stateRoot>/dispatch、workspaceRoot=<stateRoot>/workspaces。相対LM_DATA_DIRは拒否。credentialFile=env.LM_CREDENTIALS_FILEまたは<homedir>/.local/share/anicca/credentials.json。
  **検証・完了:** tests/paths.test.mjs: /home/alice、/Users/bob、/srv/lmの3rootでDais絶対pathなし、相対rootでthrow。
  **依存:** HA-001。

### HA-003 — validateRunRequest(value) -> frozen RunRequest

- [ ] **対象:** `runtime/openclaw/protocol.mjs`
  **変更:** 設計末尾RunRequestのexact fields/types、40hex release、128字ID、16字prompt、positive timeout、absolute workdir、effect_modeの2enumをvalidate。unknown fieldはreject。
  **検証・完了:** tests/protocol.test.mjs: valid fixture通過、空prompt/bool timeout/../owner/unknown keyを拒否、入力を変更しない。
  **依存:** HA-002。

### HA-004 — buildRunIdentity(request, agentId) -> {sessionKey,idempotencyKey}

- [ ] **対象:** `runtime/openclaw/protocol.mjs`
  **変更:** hash入力はNodeのJSON.stringify配列をUTF-8化する。sessionKey=agent:<agentId>:lm:<sha256([owner_id,occurrence_id])>、idempotencyKey=sha256([release_sha,owner_id,occurrence_id,task_class])。コロン区切りの文字列連結は使わない。
  **検証・完了:** tests/protocol.test.mjs:同入力同key、prompt変更だけではkey不変、owner/occurrence変更は別key。owner=a:b/occurrence=c と owner=a/occurrence=b:c は別session/idempotency。
  **依存:** HA-003。

### HA-005 — load_dispatch(root: Path, owner_id: str, occurrence_id: str) -> dict | None

- [ ] **対象:** `runtime/openclaw/dispatch_store.py`
  **変更:** DispatchRecordのpathはsha256(json.dumps([owner_id,occurrence_id],ensure_ascii=False,separators=(",",":")))のUTF-8を使い、NodeのHA-004と一致させる。<root>/<hash>.jsonのexact fields/phaseをvalidate。不在None、corrupt ValueError、foreign identity拒否。
  **検証・完了:** tests/test_dispatch_store.py:コロン境界2fixtureは別path、Node/Python hash一致、欠落None、foreign/corrupt拒否。
  **依存:** HA-004。

### HA-006 — save_dispatch(root: Path, record: dict) -> Path

- [ ] **対象:** `runtime/openclaw/dispatch_store.py`
  **変更:** 同一recordファイルのlock下で比較しphase遷移を検証。temporary write→fsync→atomic replace。prepared→sent→accepted→terminal、sent/accepted→unknown、unknownはreconcile経路のみ。chmod0600。
  **検証・完了:** tests/test_dispatch_store.py:2process同occurrenceでsent admission1件、terminal→sent拒否、mode0600。
  **依存:** HA-005。

### HA-007 — connectGateway({url,token,onEvent}, Client=GatewayClient) -> Promise<Client>

- [ ] **対象:** `runtime/openclaw/gateway-client.mjs`
  **変更:** 公開SDKのstartを呼びonHelloOkまでresolveしない。minProtocol=maxProtocol=4。connect error/5秒timeoutでstopAndWaitしreject。tokenをstdout/例外へ入れない。
  **検証・完了:** tests/gateway-client.test.mjs: hello前request0、startup unavailable再接続はSDKに委譲、bad token表示にtoken文字列なし。
  **依存:** HA-001, HA-004。

### HA-008 — submitRun(client, request, identity, agentId) -> Promise<{runId}>

- [ ] **対象:** `runtime/openclaw/gateway-client.mjs`
  **変更:** agent RPCにmessage/agentId/sessionKey/idempotencyKey/deliver:false/timeoutのみ渡す。expectFinal:false。未受領timeoutはdispatch_unknown。自身でagentを再callしない。
  **検証・完了:** tests/gateway-client.test.mjs: params完全一致、ack喪失でagent request count=1。
  **依存:** HA-007。

### HA-009 — waitRun(client, runId) -> Promise<object>

- [ ] **対象:** `runtime/openclaw/gateway-client.mjs`
  **変更:** agent.waitへ{runId,timeoutMs:1000}を渡す。RPC未知field/未知statusはprovider_status_unknown。terminal判定はpinした配布contractのstatusだけを使う。
  **検証・完了:** tests/gateway-client.test.mjs:同runIdを照合、timeoutをsuccess扱いしない、foreign runId拒否。
  **依存:** HA-008。

### HA-010 — abortRun(client, {runId,sessionKey,agentId}) -> Promise<object>

- [ ] **対象:** `runtime/openclaw/gateway-client.mjs`
  **変更:** sessions.abortへ{key:sessionKey,runId,agentId}だけ渡す。ACKを返すが停止proofを生成しない。
  **検証・完了:** tests/gateway-client.test.mjs:別session取消0、abort ACKだけでterminal/claim release0。
  **依存:** HA-009。

### HA-011 — readSession(client, {sessionKey,agentId}) -> Promise<object>

- [ ] **対象:** `runtime/openclaw/gateway-client.mjs`
  **変更:** sessions.listのexact session結果を取得してagent/session identityとhasActiveRun/activeRunIdsを照合。read-only RPCだけ。OpenClaw内部DBを開かない。
  **検証・完了:** tests/gateway-client.test.mjs:foreign session拒否、active=trueは未停止、未知active情報はunknown。
  **依存:** HA-010。

### HA-012 — testPinnedGatewayContract()

- [ ] **対象:** `runtime/openclaw/tests/release-contract.test.mjs`
  **変更:** SDKとgateway配布版のagent/agent.wait/sessions.abort/terminal payloadをprivate fake-model serverで記録し、既存fixtures/rpc-contract.jsonを作る。gateway-only instance、fake credential、model cost0、native tools disabled。
  **検証・完了:** node --test runtime/openclaw/tests/release-contract.test.mjs。handshake v4、1dispatch、1terminal、abort後active0、secret marker出力0。status shape不一致ならconsumerを直すtaskへ進まずcontract差分を確定。
  **依存:** HA-011。

### HA-013 — buildGatewayEnv(env, paths, secretValues) -> object

- [ ] **対象:** `runtime/openclaw/environment.mjs`
  **変更:** copy envをやめallowlistを使う。PATH/HOME/TMPDIRと明示LM変数だけ。STATE_DIR/CONFIG_PATHをinstance pathへ、NO_RESPAWN=1、DISABLE_BONJOUR=1、EXEC_SHELL_SNAPSHOT=0、SKIP_CHANNELS=1。operator token/provider credentialsはruntime envのみ。
  **検証・完了:** tests/environment.test.mjs:fixture arbitrary AWS_SECRET/X private変数なし、旧OPENCLAW_STATE_DIR不継承、4preset完全一致。
  **依存:** HA-002, HA-012。

### HA-014 — buildGatewayConfig({paths,port,agentId,modelRoute,effectMode}) -> object

- [ ] **対象:** `runtime/openclaw/profile.mjs`
  **変更:** gateway local loopback/token、agents.entries.<agentId>.workspace=専用dir、global maxConcurrent=2、cron.enabled=false。tools allow=lm_read/lm_artifact/lm_effectのうちeffectModeが許すものだけ。shell/browser/message/sessions_spawn/native MCPとfallbackは初版disabled。credentialsはSecretRef。 lm_artifactはprivate workspace出力のみで、read_onlyでも利用可能。remote writeはlm_effectだけ。
  **検証・完了:** tests/profile.test.mjs:read_onlyではlm_effectなし、cronfalse、ambient account/credential valueなし。公開CLI config validateで通過。
  **依存:** HA-013。

### HA-015 — startGateway({nodeExecutable,paths,env,config}, deps) -> Promise<GatewayHandle>

- [ ] **対象:** `runtime/openclaw/supervisor.mjs`
  **変更:** import.meta.resolve(openclaw)からpackage executableを解決し、指定Nodeでgatewayをspawn。stdioを即consume、exit78はtyped config_error、無限doctor/updateなし。readinessはHA-007を使う。
  **検証・完了:** tests/supervisor.test.mjs:PATH上global openclawを起動しない、timeout cleanup1回、exit78再起動0。
  **依存:** HA-007, HA-014。

### HA-016 — stopGateway(handle, {drainTimeoutMs:5000}) -> Promise<StopProof>

- [ ] **対象:** `runtime/openclaw/supervisor.mjs`
  **変更:** 対象instanceのclient停止・child graceful shutdown・owned child exitを確認。foreign PID/既存gatewayへsignalしない。期限後は未停止typed outcomeで返し容量を解放しない。
  **検証・完了:** tests/supervisor.test.mjs:foreign signal0、child不明ならstopped=false、単なるWS closeはproofにならない。
  **依存:** HA-015。

### HA-017 — claim_model(owner_id: str, occurrence_id: str, inherited_claim: Path | None) -> dict

- [ ] **対象:** `runtime/openclaw/admission.py`
  **変更:** 既存resource_admission.enqueue_durable/claim_durableをresource_class=agentで使う。継承claimは同owner/occurrenceを照合して二重claimしない。authoritative値はhost envから。
  **検証・完了:** tests/test_admission.py: nested broker claim count1、foreign claim拒否、capacity busyでmodel starts0。
  **依存:** HA-006。

### HA-018 — bind_execution(claim_ref: Path, gateway_pid: int) -> None

- [ ] **対象:** `runtime/openclaw/admission.py`
  **変更:** 既存transfer_durableとprocess_startで実gateway PIDへbind。caller PIDだけをheartbeat対象にしない。durable recordへidentity保存。
  **検証・完了:** tests/test_admission.py:別PID/start identityを拒否、transfer後caller終了でもclaim継続。
  **依存:** HA-017, HA-015。

### HA-019 — heartbeat_model(claim_ref: Path) -> bool

- [ ] **対象:** `runtime/openclaw/admission.py`
  **変更:** 既存heartbeat_durableを呼ぶ。false/exceptionでstopping→upstream cancel/readbackへ進めるtyped resultを返す。staleだから即releaseしない。
  **検証・完了:** tests/test_admission.py:heartbeat failureでclaim保持、retry無制限なし。
  **依存:** HA-018。

### HA-020 — release_model(claim_ref: Path, stop_proof: dict, effect_state: str) -> dict

- [ ] **対象:** `runtime/openclaw/admission.py`
  **変更:** terminal/owned children停止proofとeffect fenceを照合。未停止はresource_effect_unknownを保持。停止確認後だけ既存release_and_reserveで一度release。
  **検証・完了:** tests/test_admission.py:abort ACKのみrelease0、stop確認後release1、repeat release二重更新0。
  **依存:** HA-019, HA-016。

### HA-021 — _run_admitted() の finally release分岐

- [ ] **対象:** `runtime/loop/lm_loop_run.py`
  **変更:** 新routeがdispatch recordでgatewayへclaimを引き継いだ場合のみ、子wrapper終了を理由とする旧releaseを行わずHA-020のterminal proofを要求する。既存routeのfinallyは変更しない。LIFE_MANAGER_LOOP_ID/CLAIM_REFをこのrouteへ常時渡す。
  **検証・完了:** runtime/loop/tests/test_openclaw_resource_lifetime.py: caller死亡後gateway activeでcapacity再利用0、legacy route同結果。
  **依存:** HA-020。

### HA-022 — manifest.tools

- [ ] **対象:** `runtime/openclaw/plugin/openclaw.plugin.json`
  **変更:** lm_read/lm_artifact/lm_effectをmanifestへ宣言。owner binding endpointとinstance idのconfigSchemaをclosed schemaにする。secret文字列/任意commandはconfigSchemaへ持たない。
  **検証・完了:** tests/plugin.test.mjs:tool宣言と実登録一致、unknown config field拒否。
  **依存:** HA-014。

### HA-023 — default plugin register(api)

- [ ] **対象:** `runtime/openclaw/plugin/index.mjs`
  **変更:** definePluginEntryで3toolをcontextVersion:2で登録する。create(ctx)はctx.agentId/sessionKeyに一致するoperator BindingRecordだけをlookupし、固定Python/runtime/openclaw/tool_broker.py --invoke-stdinへ{binding_ref,tool_name,arguments}をstdinで渡す。shell:false、source-owned絶対script、callerからcommand/owner/credentialを受けない。assertInvocationCurrentを各call前に確認し、subprocess envへgateway/provider secretsを継承しない。
  **検証・完了:** tests/plugin.test.mjs:偽owner paramsはauthority変更なし、stale invocationのprovider call0。
  **依存:** HA-022。

### HA-024 — invoke_read(binding: dict, tool_name: str, arguments: dict) -> dict

- [ ] **対象:** `runtime/openclaw/tool_broker.py`
  **変更:** bindingのownerが持つread-only handlerを呼ぶ。初版handlerはinventory fixture readだけ。read-only経路でpublisher/submission/moneyコードを呼ばない。
  **検証・完了:** tests/test_tool_broker.py:read許可、write tool要求でprovider write0、foreign owner拒否。
  **依存:** HA-023, HA-017。

### HA-025 — invoke_effect(binding: dict, tool_name: str, arguments: dict) -> dict

- [ ] **対象:** `runtime/openclaw/tool_broker.py`
  **変更:** effect_mode=brokered、既存owner policy/admission/browser lease/effect fenceが揃うhandlerだけ呼ぶ。初版実provider handlerは未登録でtyped adapter_missing。fake provider handlerでreceipt/idempotencyを検証。
  **検証・完了:** tests/test_tool_broker.py:unknown/fenceなし/leaseなしwrite0、same occurrence fakewrite1・same receipt。
  **依存:** HA-024。

### HA-026 — write_artifact(binding: dict, relative_path: str, content: str) -> dict

- [ ] **対象:** `runtime/openclaw/tool_broker.py`
  **変更:** trusted binding.workspace配下のrelative pathだけへUTF-8成果物を書く。absolute/..、symlink parent、.git、credential/config/state領域を拒否。最大1MiB。temp write/fsync/replaceし{artifact_ref,sha256,bytes}を返す。canonical catalog/production sourceを直接書かない。
  **検証・完了:** tests/test_tool_broker.py:4成果物SKILL.md/LISTING.md/icon.svg/evidence/verified-demonstration.mdをprivateworkspaceに作れる。../、symlink、1MiB超過はwrite0。
  **依存:** HA-024。

### HA-027 — main(argv: list[str], stdin: TextIO) -> int

- [ ] **対象:** `runtime/openclaw/tool_broker.py`
  **変更:** --invoke-stdinだけ受付。packetは{binding_ref,tool_name,arguments} closed schema。operator dispatchRoot内のBindingRecordをmode/owner/claim/actual parent PID・start identityと照合し、lm_read→invoke_read、lm_artifact→write_artifact、lm_effect→invoke_effectへdispatchする。model supplied owner/claimを採用しない。stdoutはsanitized JSON、unknown/errorはtyped resultと非zero。
  **検証・完了:** tests/test_tool_broker.py:foreign binding/parent mismatch/unknown tool/secret markerでeffect0、固定invoke packetが通る。shell command文字列は受けない。
  **依存:** HA-025, HA-026。

### HA-028 — testModelAndToolAdmissionFailClosed()

- [ ] **対象:** `runtime/openclaw/tests/native-boundary.test.mjs`
  **変更:** 配布版でplugin missing/timeout、native shell/MCP/HTTP、cron/direct RPC、subagentの5迂回をfake provider相手にprobeする。一般prompt hookだけで強制保証しない。
  **検証・完了:** node --test runtime/openclaw/tests/native-boundary.test.mjs。claimなしmodel call0、broker外write0。どちらか失敗ならeffect_modeはread_onlyのまま、HA-059以後は未着手。
  **依存:** HA-025, HA-012, HA-021, HA-027。

### HA-029 — validate_result(instance: object, schema: dict) -> dict

- [ ] **対象:** `runtime/openclaw/schema_validate.py`
  **変更:** 既存jsonschema==4.26.0のvalidators.validator_for(schema)でschemaをcheck_schemaし結果をvalidate。stdinは{instance,schema}、stdoutは{valid:true}または{valid:false,error_class:schema_invalid|result_invalid}だけ。値やschema全文をstderrへ出さない。
  **検証・完了:** tests/test_schema_validate.py:additionalProperties:false拒否、required不足拒否、draft選択、fake secret markerを出力しない。
  **依存:** HA-003。

### HA-030 — normalizeOutcome(raw, request) -> RunOutcome

- [ ] **対象:** `runtime/openclaw/result.mjs`
  **変更:** HA-012で固定したpayloadのfinal JSONを取得し、release-ownedPythonのschema_validate.pyへstdinでinstance/schemaを渡す。valid=falseならfailed。usage/cost欠測はnull。tool receiptはbroker証拠のみからjoinし、LLM textを公式receiptへ変換しない。
  **検証・完了:** tests/result.test.mjs:invalid JSON/schemaはfailed、fake final receiptを採用しない、token欠測null。
  **依存:** HA-012, HA-025, HA-029。

### HA-031 — project_usage(raw: dict, identity: dict) -> dict

- [ ] **対象:** `runtime/openclaw/telemetry.py`
  **変更:** existing agent-usage fieldsへinput/output/cached/retry/subagent tokensをproject。cost_basisはprovider_reported/api_equivalent_estimate/unknownを分離。runId重複を二重計上しない。
  **検証・完了:** tests/test_telemetry.py:retry usage含む、欠測null、同run二重charge0、fake secret marker非露出。
  **依存:** HA-030。

### HA-032 — project_runtime_event(outcome: dict, identity: dict) -> dict

- [ ] **対象:** `runtime/openclaw/telemetry.py`
  **変更:** 既存runtime_event.build_runtime_event/validate_runtime_eventを利用しrun/owner/occurrence/releaseをjoin。error_class/retryable/next_action/receipt/readbackを保持。
  **検証・完了:** tests/test_telemetry.py:既存validator通過、release欠落でsuccess不可、unknown effect維持。
  **依存:** HA-031。

### HA-033 — main(argv, stdin, deps) -> Promise<number>

- [ ] **対象:** `runtime/openclaw/cli.mjs`
  **変更:** --request-stdinまたは--request-file、--outcome-fileを解析。validate→durable prepared→claim→sent→agent ACK保存→wait→schema結果→event/receipt保存→stop proof→releaseの順で実行。exit success0/failed1/input2/pending75。 dispatch送信前にBindingRecordを0600でatomic保存する。fields={owner_id,occurrence_id,session_key,workspace,claim_ref,gateway_pid,gateway_start,allowed_tools}。pathはdispatchRoot/<identityhash>.binding.json、workspaceはrequest.workdir、allowed_toolsはeffect_modeからoperatorが固定。
  **検証・完了:** tests/cli.test.mjs:正常fixture各呼出順、ack喪失でsent1/dispatch0追加、timeoutでunknown。
  **依存:** HA-003, HA-004, HA-006, HA-008, HA-009, HA-010, HA-011, HA-020, HA-030, HA-032, HA-028。

### HA-034 — run_openclaw(parsed, prompt: str, schema: dict, config: dict) -> int

- [ ] **対象:** `runtime/openclaw/runner_adapter.py`
  **変更:** 既存runner argsをRunRequestへ写しnode cliをstdin JSONで呼ぶ。outcomeをexisting summaryのversion/status/route/attempt_count/result_path/selected_*へproject。image/codex-resumeは初版unsupportedでprovider開始前に明示失敗。
  **検証・完了:** tests/test_runner_adapter.py:既存run_agent consumerがsummaryを読める、unknown75、unsupported image dispatch0。
  **依存:** HA-033。

### HA-035 — run() の parsed入力validate後・candidate起動前

- [ ] **対象:** `runtime/agent-runner/agent_runner.py`
  **変更:** config.harness_routes[trusted owner].engine=openclawでenabled=trueの時だけHA-034へ委譲。ownerはLIFE_MANAGER_LOOP_ID、short --loopをauthorityにしない。disable/defaultは現行候補chain。
  **検証・完了:** runtime/agent-runner/tests/test_openclaw_route.py:default legacy、eligible ownerだけnew、env owner欠落時newに入らない。
  **依存:** HA-034, HA-021。

### HA-036 — test_ack_loss_preserves_claim()

- [ ] **対象:** `runtime/openclaw/tests/test_recovery.py`
  **変更:** 送信→ACK前crash fixture。sent recordが残り、同occurrence再開はreconcileのみ、新RPC agent0・claim保持をassert。
  **検証・完了:** python3 -m pytest runtime/openclaw/tests/test_recovery.py::test_ack_loss_preserves_claim -q。
  **依存:** HA-035。

### HA-037 — test_provider_success_receipt_gap()

- [ ] **対象:** `runtime/openclaw/tests/test_recovery.py`
  **変更:** fake provider成功→receipt保存前crash fixture。readbackで同receipt復元、provider write1、retry追加0をassert。
  **検証・完了:** python3 -m pytest runtime/openclaw/tests/test_recovery.py::test_provider_success_receipt_gap -q。
  **依存:** HA-036。

### HA-038 — test_terminal_replay_zero()

- [ ] **対象:** `runtime/openclaw/tests/test_recovery.py`
  **変更:** terminal保存済みoccurrenceを再投入。existing result/refを返しmodel/provider/toolの追加call0をassert。
  **検証・完了:** python3 -m pytest runtime/openclaw/tests/test_recovery.py::test_terminal_replay_zero -q。
  **依存:** HA-037。

### HA-039 — 固定canary request

- [ ] **対象:** `runtime/openclaw/fixtures/read-only-request.json`
  **変更:** owner_id=harness-readonly-canary、occurrence_id=fixture-001、effect_mode=read_only、task_class=repeatable-agent、timeout_seconds=60、schema={type:object,required:[status,count],properties:{status:{const:success},count:{const:1}},additionalProperties:false}。model/providerはprivate fixture configに渡しsourceへcredentialを入れない。
  **検証・完了:** tests/canary.test.mjs:validateRunRequest通過、fake modelの返答{status:success,count:1}、effect0。
  **依存:** HA-038。

### HA-040 — main(argv) -> int

- [ ] **対象:** `apps/life-manager/scripts/harness-readonly-canary.py`
  **変更:** release-rootのNode cliへHA-039を入力。workdir/evidence-dirはprivatecanaryroot、release SHAはloaded env。production source/catalogをwriteしない。
  **検証・完了:** runtime/openclaw/tests/test_canary.py:caller pathsrelease相対、effect0、event same occurrence。
  **依存:** HA-039。

### HA-041 — loops.harness-readonly-canary

- [ ] **対象:** `config/loop-registry.json`
  **変更:** entrypoint=apps/life-manager/scripts/harness-readonly-canary.py、adapter=python、domain=system、effect_class=none、provider_route=deterministic、resource_class=agent、admission_class=borrow、priority=support、cadence.start_interval_seconds=300、private state/logroot、system_role=controlを追加。
  **検証・完了:** ./bin/lm-loop-contractでPASS。public installerのdefault enabled対象に入れない。
  **依存:** HA-040。

### HA-042 — source acceptance receipt

- [ ] **対象:** `docs/evidence/harness-migration/first-source-acceptance.json`
  **変更:** HA-001〜038のfocused node/Pythonテストとloop-contract結果、source SHA、SDK/gateway/Nodeの版を記録する。mock成功をproduction成功と書かない。
  **検証・完了:** node --test runtime/openclaw/tests/*.test.mjs; python3 -m pytest runtime/openclaw/tests runtime/agent-runner/tests/test_openclaw_route.py runtime/loop/tests/test_openclaw_resource_lifetime.py -q; ./bin/lm-loop-contract。
  **依存:** HA-041。

### HA-043 — read-only自然occurrence receipt

- [ ] **対象:** `docs/evidence/harness-migration/readonly-natural.json`
  **変更:** HA-042のPR/main/release後、harness-readonly-canaryだけloaded-idle applyする。自然due1件のloaded argv/SHA、terminal、trace/cost、external writes0を記録する。他gateway/ownerはapplyしない。
  **検証・完了:** bin/lm-loop status --explain harness-readonly-canaryのowner/version/terminalとsame-occurrence evidence照合。GUI preflight不可時はmutationせずそのpreconditionを記録。
  **依存:** HA-042。

### HA-044 — main() の mode/role/engine対応

- [ ] **対象:** `skills/writer-agent/runtime/shared-model-runner.py`
  **変更:** legacy image/repair/resumeのunsupportedをnewengineで先に拒否し、通常agent/judgeだけ既存RUNNER経由で同schemaを維持。直接新CLIを呼ぶ第二実装を作らない。
  **検証・完了:** runtime/openclaw/tests/test_writer_route.py:agent/judgeの既存format維持、vision/repair/resumeはsource eligibility=false。
  **依存:** HA-035。

### HA-045 — 3固定task cases

- [ ] **対象:** `apps/life-manager/eval/harness-migration/cases.jsonl`
  **変更:** read-only inventory、Capafy offline 4artifacts、ack-loss prefixの3ケースを固定seed/hashで保存。実platform/canonical catalogへのwriteはない。
  **検証・完了:** tests/eval.test.mjs:case ID唯一、3casesちょうど、run budgetとmodel固定、holdout write不可。
  **依存:** HA-042。

### HA-046 — evaluateHarnessPair({base,candidate,cases,budget,seed}) -> report

- [ ] **対象:** `apps/life-manager/eval/harness-migration/run.js`
  **変更:** 同3cases/model/tool/budgetを2harnessで実行し安全、task成功数、総observed cost、RSSを比較する。既存LM-EAB economic scorerへfinancial inputだけ委譲。採用はcost<=base、task>=base、safety allPASS、RSS host capacity内。
  **検証・完了:** run.test.js:cost増/欠測、receipt偽造、同task不一致でHOLD、全条件でSHIP。
  **依存:** HA-045, HA-044。

### HA-047 — 採用判定

- [ ] **対象:** `docs/evidence/harness-migration/adoption.json`
  **変更:** HA-046の実reportにbase/model/tools/cost basis/evidence refsを保存する。未知費用ならHOLD。SHIPの場合だけ後続enabled selectorへ進む。
  **検証・完了:** 同3casesのreceipt・費用をreportと再照合。公開benchmark点数は入力に使わない。
  **依存:** HA-046, HA-043。

### HA-048 — validate_owner_route(owner_id: str, route: dict, registry: dict) -> dict

- [ ] **対象:** `runtime/openclaw/owner_routes.py`
  **変更:** owner存在、source callerがrunner seamを通ること、taskclass/image/repair/resume/effect adapterの実装coverage、model/provider保持、HA-047 SHIPを検証。どれか未確認ならactivationを拒否する。
  **検証・完了:** tests/test_owner_routes.py:caller未対応/env owner欠落/coverageunknown/leaseactiveでenabled拒否。
  **依存:** HA-047。

### HA-049 — capafy_readback(binding, arguments) -> dict

- [ ] **対象:** `runtime/openclaw/tool_broker.py`
  **変更:** bindingのownerをcapafy-loop-dailyへ固定。handler引数は{}または{agent_id:string}のみ。既存vendor/capafy-publisher/packager.pyを固定cwdでpublish-list、指定IDならpublish-remote-status --agent-id <ID>として呼ぶ。reconcile_ledger.main()はledgerへwriteするのでread-only handlerから呼ばない。
  **検証・完了:** tests/test_capafy_handler.py:fake公式readbackをjoin、401と検索エラーを混同しない、foreign ownercall0。
  **依存:** HA-048, HA-024。

### HA-050 — capafy_publish(binding, arguments) -> dict

- [ ] **対象:** `runtime/openclaw/tool_broker.py`
  **変更:** 初版はCP1完了済みagentだけを対象にする。引数={agent_id,skill_name,listing_path,agent_version_id}をclosed schemaで検証しlisting_pathはowner workspace内に限定。既存scripts/publish_finish.shの4positional argsへ委譲し、CP1未確認/CAP_FULL/unknownでは起動0。新しいdraft作成やCP1の別実装はこのhandlerに混ぜない。
  **検証・完了:** tests/test_capafy_handler.py:cap full0、unknown0、sameoccurrence1receipt、provider success前後crash回帰。
  **依存:** HA-049, HA-025。

### HA-051 — harness_routes.capafy-loop-daily

- [ ] **対象:** `runtime/agent-runner/config.json`
  **変更:** HA-048 validationとHA-050が成立してからengine=openclaw、enabled=true、allowed_task_classes=[repeatable-agent,application-lane-agent]を設定。許可される販売行為はCP1完了済みagentのfinishだけ。新規draft/CP1作成を要求する既存promptはcoverage falseのままlegacyへ残す。
  **検証・完了:** test_openclaw_route.py:capafy-loop-dailyだけnew、同model/provider保持、defaultdisabled。
  **依存:** HA-050。

### HA-052 — RUN_AGENT呼出env

- [ ] **対象:** `skills/self/capafy-loop/capafy-loop-daily.sh`
  **変更:** shared RUN_AGENTを維持し、trusted entrypoint envのLIFE_MANAGER_LOOP_ID=capafy-loop-dailyをnewrouteの呼出時に明示。CAP_FULL/offline cadence/ledger/bodyは変更しない。
  **検証・完了:** runtime/openclaw/tests/test_capafy_caller.py:全RUN_AGENT呼出のowner一致、cap/cadence/source artifactsの既存focused regression。
  **依存:** HA-051。

### HA-053 — Capafy自然成果receipt

- [ ] **対象:** `docs/evidence/harness-migration/capafy-natural.json`
  **変更:** HA-052 source acceptance→main/release→owner限定apply。自然offline4成果物と、既存CP1完了済みagentの正当なfinishについて公式receipt/費用/trace/duplicate0を保存。新規draft/CP1のcoverageは未達と表示しCapafy全業務移行完了にはしない。cap満杯ならpublish未達を保持。
  **検証・完了:** bin/lm-loop status --explain capafy-loop-daily、既存公式readback、sameoccurrence cost/refをjoin。buyer購入は技術移行gateにしない。
  **依存:** HA-052, HA-043。

### HA-054 — prepare_transfer(owner_id: str, target: str, expected_sha: str) -> dict

- [ ] **対象:** `runtime/openclaw/schedule_transfer.py`
  **変更:** owner/release/lease/running/unknownを確認。target enumlegacy/openclaw。旧wakeを凍結してdrain後、新cronをdisabledで登録しreceiptを保存する。公開配布でcron強制admission未検証ならtargetopenclaw拒否。
  **検証・完了:** tests/test_schedule_transfer.py:active/unknown/foreignleaseで旧owner変更0、prepared途中crashで二重enabled0。
  **依存:** HA-053, HA-048。

### HA-055 — commit_transfer(prepared: dict) -> dict

- [ ] **対象:** `runtime/openclaw/schedule_transfer.py`
  **変更:** receiptのexpected owner/sha/epoch一致を確認し旧schedule退役→newenabled→readback。retryで二重作成しない。model-start claim/heartbeat/cleanupが強制されることはHA-028を再実行し必要条件にする。
  **検証・完了:** tests/test_schedule_transfer.py:old-disabled直後crash、新enabled直後crashの両方でauthority<=1・job喪失0。
  **依存:** HA-054。

### HA-056 — rollback_transfer(receipt: dict) -> dict

- [ ] **対象:** `runtime/openclaw/schedule_transfer.py`
  **変更:** new wakeを止めrunをdrain、unknownを保持、旧main由来release/scheduleだけrestore。credential/session/ledgerの巻戻しなし。
  **検証・完了:** tests/test_schedule_transfer.py:unknownoccurrence再送0、旧owner再開1、foreignservice untouched。
  **依存:** HA-055。

### HA-057 — 唯一のscheduler receipt

- [ ] **対象:** `docs/evidence/harness-migration/capafy-schedule.json`
  **変更:** HA-054〜053source/main/release後にcapafy-loop-daily1件の転送を実行し、新cronの次due自然occurrence1件と旧wake0を記録する。
  **検証・完了:** source SHA/loaded/oldretired/newenabled/next occurrenceが一致。HA-028不合格なら実行せずHOLD。
  **依存:** HA-056。

### HA-058 — build_owner_inventory(registry_path: Path, catalog_path: Path, tracked_files: list[str]) -> list[dict]

- [ ] **対象:** `runtime/openclaw/owner_inventory.py`
  **変更:** registry ownerとcataloggroup、shared runnerのsource literal caller、nested wrappersをjoinする。全184をagent消費者と推定しない。各rowにcaller_path/symbol/taskclass/handlercoverage/eligibility/evidenceを入れる。
  **検証・完了:** tests/test_owner_inventory.py:deterministic nested capafy/promptbase検出、read-only supportのfalsepositiveなし、caller未確認eligibilityfalse。
  **依存:** HA-048。

### HA-059 — _claude(prompt, system) の subprocess env

- [ ] **対象:** `skills/earn/promptbase/scripts/gen_examples.py`
  **変更:** MODEL_RUNNERは既存Writer model-runner.shを維持。subprocess envへLIFE_MANAGER_LOOP_ID=promptbase-loop-dailyを明示し、SYSTEM INSTRUCTIONS/BUYER PROMPT区分と{text:string} output schemaを保つ。publish.py/ledgerは変更しない。
  **検証・完了:** tests/test_promptbase_caller.py: owner一致、2prompt section保持、textのJSON unwrap不変、example generationでplatform write0。
  **依存:** HA-058, HA-044。

### HA-060 — harness_routes.promptbase-loop-daily

- [ ] **対象:** `runtime/agent-runner/config.json`
  **変更:** PromptBase工具coverageがHA-048でverifiedになった時だけownerrouteをenabled。未実装publisher handlerではenabledfalseを固定。
  **検証・完了:** test_owner_routes.py:handler未登録でenable拒否、owner一致のverifiedcoverageだけ許可。
  **依存:** HA-059。

### HA-061 — trusted ownerの伝播

- [ ] **対象:** `skills/writer-agent/runtime/shared-model-runner.py`
  **変更:** ARTICLE_MODEL_ROLEからownerを作らずLIFE_MANAGER_LOOP_IDをrunnerへ保持。agent/judgeだけeligible、repair/vision/codexresumeはHA-044の明示unsupported。
  **検証・完了:** tests/test_writer_route.py:article-daily/agentjudgeのactor保持、別ownerへ上書き不可。
  **依存:** HA-044, HA-058。

### HA-062 — harness_routes.article-daily

- [ ] **対象:** `runtime/agent-runner/config.json`
  **変更:** HA-048でWriterpublish/readbackのcoverageがverifiedの時だけagent/judgeをenabled。read-only judge成功をWriter公開成功へ転写しない。
  **検証・完了:** test_owner_routes.py:publication adapter欠落でenable拒否、vision/resumeはlegacy route保持。
  **依存:** HA-061。

### HA-063 — judgeCandidate({baseReport,candidateReport,holdoutHash}) -> {verdict,reasons}

- [ ] **対象:** `apps/life-manager/eval/harness-migration/gate.js`
  **変更:** safety全件PASS、task成功>=base、knownfailure1件改善、cost<=base、holdout hash不変をAND判定。unknown costはHOLD。既存agent-contract/economic-autonomyのgateを再利用。
  **検証・完了:** gate.test.js:同dataset汚染・costnull・receipt偽造・課題変更でHOLD、全条件SHIP。
  **依存:** HA-046。

### HA-064 — record_canary_application() の候補gate

- [ ] **対象:** `skills/writer-agent/scripts/writer_learning_worker.py`
  **変更:** 既存canary適用recordへHA-063 report SHA/parent/holdout hashを照合する分岐を追加する。既存offline/close-canary/promotionを維持しSHIPだけ既存候補受付へ渡す。marketing scheduled_runnerは実際にwritebackをquarantineしているので別の直接昇格分岐を捏造して変更しない。
  **検証・完了:** runtime/openclaw/tests/test_learning_gate.py:既存record_canary_applicationをimportしreport missing/HOLD/parent mismatchは受付0、SHIP一致1。
  **依存:** HA-063。

### HA-065 — repair evidence envelope

- [ ] **対象:** `runtime/loop/recovery-supervisor.mjs`
  **変更:** OpenClaw upstream run/session/trace refsをexisting repair intent evidenceへ追加する。Self-Build/Symphony既存executorを維持し別codingharnessを作らない。
  **検証・完了:** 既存recovery-supervisor関連test:before/after occurrenceと修正commit/readback欠落ならrepairedfalse。
  **依存:** HA-032, HA-057。

### HA-066 — 自然コード修復1件のreceipt

- [ ] **対象:** `docs/evidence/harness-migration/self-heal.json`
  **変更:** noeffect/ownerlocal実障害1件を既存Self-Buildで修正し、修正commit/main/release/after自然run/公式readbackを保存する。restart/issueだけでは未達。
  **検証・完了:** 同failure prefixの回帰PASSとbefore/after別occurrence、duplicate0。
  **依存:** HA-065。

### HA-067 — 評価済候補1件のreceipt

- [ ] **対象:** `docs/evidence/harness-migration/self-improve.json`
  **変更:** HA-063/061でSHIPの1skillをmain/releaseし、owner自然runのtask/cost/receiptをparentと比較する。劣化時はHA-056rollbackを実行。
  **検証・完了:** fixed holdout改善、knownfailure改善、costbasis同一、naturalreadback欠測なし。
  **依存:** HA-064, HA-066。

### HA-068 — 未参照legacy routeの削除

- [ ] **対象:** `runtime/agent-runner/agent_runner.py`
  **変更:** HA-058 inventoryでsourcecaller0かつloaded/natural移行済みのlegacy provider分岐だけ削る。未対応vision/repair/resumeとdomainfence/CFO/admissionは保持。
  **検証・完了:** 既存runnerfocused testsとloop-contract、削除symbolへのrg参照0。残legacyがある場合full migration完了にしない。
  **依存:** HA-067, HA-062, HA-060。

### HA-069 — 全owner受け入れ照合

- [ ] **対象:** `docs/evidence/harness-migration/final-acceptance.json`
  **変更:** HA-058全eligible rowにsource commit/release/loaded/scheduler/natural/toolreceipt/costをjoin。欠けたrowはmissing対象と次probeを残す。全owner技術migrationと商品収益の判定を分ける。
  **検証・完了:** source/loaded一致、duplicateeffect0、旧agentwake0、全eligible rowのrequired evidenceあり。
  **依存:** HA-068。

### HA-070 — inspectHost({platform,env,which}) -> CapabilityReport（条件付き配布）

- [ ] **対象:** `runtime/openclaw/doctor.mjs`
  **変更:** Nodeversion、python3/bash、dockerを検出。mac/linuxnativeはsupported、win32native販売toolはunsupported_host、WSL2/DockerはLinuxadapterへ。model/platform credentialは設定名の有無だけ返し値は返さない。
  **検証・完了:** tests/doctor.test.mjs:mac/linux/win32/WSL fixture、iOS/Androidはcontrolleronly、未設定機能はmissing理由。
  **依存:** HA-002。

### HA-071 — resolveSecretRef(ref, credentialFile) -> string（条件付き配布）

- [ ] **対象:** `runtime/openclaw/credentials.mjs`
  **変更:** 一意SSOTのservice/keyをruntimeだけで読む。symlink/ownership/mode不正を拒否。OpenClaw configにはSecretRefだけ、値をconfig/log/返答へ保存しない。
  **検証・完了:** tests/credentials.test.mjs:fake keyはsecret-free config、repo内source不読、別tenant mount拒否。
  **依存:** HA-070, HA-014。

### HA-072 — frozen dependencies section（条件付き配布）

- [ ] **対象:** `install.sh`
  **変更:** LIFE_MANAGER_INSTALL_HARNESS=1の場合のみruntime/openclawでnpm ciを実行しdoctorでhost能力を表示する。default0で現行install動作維持。global npm/openclaw/Nodeのupgradeなし。
  **検証・完了:** test/install-isolation.test.mjs:HAinstall0でextra calls0、1で専用pathのみ、existing user config不変更。
  **依存:** HA-071, HA-001。

### HA-073 — single-tenant Linux runtime image（条件付き配布）

- [ ] **対象:** `runtime/openclaw/Dockerfile`
  **変更:** Node24.16系Linuxbase、Python3/bashとlocked runtime dependencies、runtime/openclaw npm ci。同一repo sourceをcopy、non-root実行、外部LM_DATA_DIR volume、credentialはsecret mount。Dais HOME/browser/accountをcopyしない。
  **検証・完了:** docker buildのsource/lock確認、fake credential mountでcanary1run、image layersにfake secret markerなし。
  **依存:** HA-072, HA-042。

### HA-074 — lm instance service（条件付き配布）

- [ ] **対象:** `runtime/openclaw/compose.yaml`
  **変更:** private network、loopback-only publicport、data volume、read-onlycredential secret、healthcheckはreadiness RPCのみ、restart policyはprocess failureに限定。固定Daispathsやregistry全ownerのautoenableなし。
  **検証・完了:** docker compose config通過、stop/startでsame session/readback、reboot recoveryfixtureでsend1回。
  **依存:** HA-073。

### HA-075 — portable acceptance matrix（条件付き配布）

- [ ] **対象:** `.github/workflows/harness-portability.yml`
  **変更:** ubuntu-latest/macos-latestでpaths/protocol/result/client fake testsとNode24.16。Windowsはcorefake testsだけ、販売tool supportはWSL2/Linuxcontainerのみと明示。secretsやliveproviderを使わない。
  **検証・完了:** matrix3platform allPASS、cloudsingletenantcontainerfixturePASS、live effects0。
  **依存:** HA-074。

### HA-076 — ACTIVE_ROOTSに含まれるruntime/openclawの検査（条件付き配布）

- [ ] **対象:** `scripts/verify-oss-self-contained.mjs`
  **変更:** 既存runtime rootのscannerを利用し新packageのlock/relativeentrypoints/外部HOME依存をcoverageへ加える。大量baseline例外を追加しない。
  **検証・完了:** node --test test/oss-self-contained.test.mjs; npm run verify:oss。新Daispath/ambientprofile依存でFAIL。
  **依存:** HA-075。

### HA-077 — OpenClaw/client/protocol notices（条件付き配布）

- [ ] **対象:** `THIRD_PARTY_NOTICES.md`
  **変更:** 固定packageversionとMITlicense noticeを追加。OpenClawは正常npm依存で再配布しdistfiles選択vendorをしない。Mastra ee codeやhostedLangSmithを必要dependencyとしない。
  **検証・完了:** pinversionとlicense本文/NOTICEの照合。
  **依存:** HA-076。

### HA-078 — portable installation/capability table（条件付き配布）

- [ ] **対象:** `README.md`
  **変更:** nativeMac/Linux、WindowsWSL2/Docker、cloudsingletenant、スマホcontrollerを区別。本人のprovider/platformsetup必要、freecompute/全商品自動有効の約束なし。Docker/CLIのexact commandをHA-072〜071から記載。
  **検証・完了:** 新READMEの各commandがfreshfixtureで実行済、対応表とdoctor result一致。
  **依存:** HA-077。

### HA-079 — 同じ配布境界の日本語手順（条件付き配布）

- [ ] **対象:** `README.ja.md`
  **変更:** HA-078と同じversion/command/能力表を日本語で記す。actualsecret/既存Daisbrowser移行を手順に含めない。
  **検証・完了:** 対応OS/credential/volume/defaultdisabledが英語READMEと一致。
  **依存:** HA-078。

### HA-080 — clean-user/cloudsource acceptance（条件付き配布）

- [ ] **対象:** `docs/evidence/harness-migration/portable-acceptance.json`
  **変更:** 異なるfakeHOME2個とLinuxcontainer2cellで、owner同名でもstate/session/credential非共有を実測。iOS/Androidで実行できるとは記さない。source packaging成立だけ記録し公開/deploy/支払はしない。
  **検証・完了:** same-owner crosscell leakage0、credential/tracefake marker露出0、one effectfakewrite percell、fresh install/restart結果。
  **依存:** HA-079。

## 全ownerの切替を一つのTODOにしない

[owner activation map](../../research/harness-owner-activation-map.json)は現行shared-agent-runner routeの各entrypointを列挙する。ただしregistryのrouteだけではcaller内部が共有runnerへ到達する証明ではないため、全行`route_enabled=false`で固定する。HA-058がnested callerを含む実sourcecoverageを作る。

残ownerに対して必要なのは、特定entrypoint内の特定caller、使用taskclass、呼ぶpublisher/readback handlerを名指した追加atomである。まだ読んでいないcallerを『既存handlerを接続』という万能TODOにして実行可能と偽らない。初版でsourceを確認したcallerはCapafy、PromptBase、Writer。Capafy公開handlerはCP1完了済みfinishに限定し、各商品の未実装工具coverageはfalseにする。残り全商品の切替仕様はcoverage一覧の未確認箇所が確定してから該当関数ごとに追加する。ここは**全移行のsource設計未完部分**であり、HA-069の全移行完了を現時点で保証しない。

## 初回にそのまま実行する順序

HA-001→002→003→004→005→006→007→008→009→010→011→012。最初のPR成果はpinされたpackageとpath/protocol/dispatch/RPC契約。次はHA-013からsupervisor/admissionへ進む。互換testで外部contractが不成立ならfail原因を同じsource/evidenceへ記録し、activated ownerを作らない。

計画は実装内容の指定であり、実装済み・配布済み・本番安全の証明ではない。
