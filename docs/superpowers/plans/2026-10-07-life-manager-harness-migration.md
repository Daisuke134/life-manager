# Life Managerハーネス移行 実行計画

> **実行agent向け:** `superpowers:executing-plans`を読み、以下のtaskを順に実行する。実装は`gpt-6-luna / max`、計画・検証は`gpt-6.1-sol / medium`。独立agentを使う場合だけ適用される委譲手順を読む。各チェックボックスは手順であり、進行状態・順序・cursorの正本は統合SSOTのHM laneに限る。今回は計画作成までで、この実行計画の実装・本番操作は未着手。

**目的:** 自作のagent orchestrationをOpenClawへ段階移行し、商品別agentの24時間運用・復旧・評価・自己改善を既存の金銭/外部作用契約と両立させる。
**構成:** 最初は既存scheduler→薄いoperator bridge→専用OpenClaw profile→業務tool broker。owner単位のsource/effect acceptance後にscheduleもOpenClawへ移し、同一ownerの旧経路を退役する。
**技術:** OpenClaw2026.9.8、対応Node26、native Codex/既存provider、Python adapter、TypeScript業務plugin、既存admission/fence/CFO、SQLite upstream state、OTel、LM-EAB。
**設計:** [移行設計](../specs/2026-10-07-life-manager-harness-migration-design.md)。

## 共通制約

- 最新main由来の専用worktree/leaseで実装する。外部effect、旧gateway/profile/session/credential、他ownerを変えない隔離fixtureから始める。
- 初期OpenClaw=`2026.9.8` / release commit=`fc23bc864e4553c2d215e479eeec47b67a0bf943`。Node25は対応外、専用Node26を使いグローバルNodeを置換しない。pluginのexact version/integrityをHM-01でlockする。
- 初期global model concurrency=2、同一owner/occurrence=1、同一browser identity=1。既存provider/spend上限の小さい方を採る。
- credential SSOTは`~/.local/share/anicca/credentials.json`のみ。gateway bearerはoperatorだけが実行時取得。agent・repo・traceへ複製しない。
- `unknown → reconcile original occurrence`。timeout・transport disconnect・modelの成功申告で再送しない。resumeでexternal effectを再実行しない。
- base/model/providerは業務ownerごとに保持。初回比較でharnessとmodelを同時変更しない。subscription利用の可否・上限・実費は実測し、API-equivalent estimateを実請求にしない。
- scheduler authorityはownerごとに一つ。selectorは既存registryへの参照であり新job/TODO正本ではない。
- 意味のある各task差分はfetch→focused acceptance→commit/push→PR/checks→admin merge。runtime変更は`./bin/lm-loop-contract`もPASS。拒否はexact blockerを記録する。
- source受け入れ後だけmain由来immutable releaseを作る。本番target apply/restartは`launchctl-safe`のowner/GUI preflight後、loaded-idle境界で限定実施。自然run/readbackはsource acceptanceと区別する。
- 各taskに余分なQA体系を作らない。既存テストが契約を表せる場合は再利用する。

## review重点と担当task

1. provider成功→receipt保存の間でcrashし、再開が二重送信する: HM-03/HM-05。
2. HTTP受領IDを失い、新requestで別agentを起動する: HM-02/HM-05。
3. native shell/MCP/browserがbrokerを迂回する: HM-03/HM-06。
4. retry/subagent/compactionのusageが欠落し安く見える: HM-04/HM-05。
5. 新旧schedulerが同じ商品ownerを同時に起こす: HM-08/HM-09。

## 成果単位とファイル所有

A: HM-00〜06で隔離接続・安全契約・比較を実装し、採用可否を判定。B: HM-07〜10で自然read-only→1商品→残ownerを移行。C: HM-11〜14で自己修復・自己改善・実測配分を実証。D: HM-15〜17で不要な自作層の削除・全体readback。これらはそれぞれ単独のPR/acceptanceを持ち、一括PRにしない。

新規`runtime/openclaw/protocol.py`は入出力契約、`transport.py`はoperator HTTP、`bridge.py`は既存CLI互換、`tool_broker.py`は既存policy/fenceへの委譲、`plugin/`はOpenClawへの工具登録とnative経路block、`telemetry.py`はexisting event/costへのprojection、`config/harness-migration.json`はowner selector。pluginのpackageは配布物SDKのexact互換を検証後にlockする。運用stateはprivate `~/.local/state/life-manager/openclaw/`、試験profile/stateはその配下の私有canary領域。

## A — 接続・契約・採用判定

### HM-00: 移行owner一覧とbaselineを固定

Files: 新規`docs/evidence/harness-migration/owner-inventory.json`、`baseline.json`。変更は統合SSOTのHM cursorのみ。
Interfaces: registry/catalog/callerを消費し、`{owner_id, product_group, caller, task_class, provider_route, state_ref, effect_class, cadence, cost_basis, migration_wave}`を出す。

- [ ] registry184件とcatalog15 groupsを最新mainで再集計する。
- [ ] `run_agent.sh`、`agent_runner.py`、Writer wrapperのcallerを`rg`で列挙し、nested runnerをinventoryへ追加する。
- [ ] 対象ownerの直近自然occurrenceをread-only収集し、成功/失敗・queue wait・RSS・usage・actual/unknown cost・公式readbackをbaselineに記録する。失敗原因をharness/host/provider/toolに分ける。
- [ ] 既存OpenClawとbrowserのowner/leaseを確認し、別profile/port/stateの未使用性を記録する。
- [ ] 生credentialや顧客情報を含まないinventory/baselineをcommit/pushする。
DONE: 全runner callerが列挙され、unknownを0へ変換せずbase version/occurrence/cost basisが固定。

### HM-01: 配布版互換と隔離profileを作る

Files: 新規`runtime/openclaw/package.json`・lockfile、`config/openclaw/canary.json`、`docs/evidence/harness-migration/compatibility.md`。production configは変更しない。

- [ ] 公開2026.9.8のpackage integrity・Codex/OTel/plugin SDK互換・Node requirementsを実配布物で確認する。
- [ ] 専用Node26/OpenClaw/private canary profileを非default場所に導入し、channel/cron/autoupdate/技能自動書換を無効にする。既存5agent profileへ接続しない。
- [ ] native provider accountはSSOT経由で利用可否を確認し、default CLI accountのtoken/profileをコピー・refreshしない。leaseが取れない場合はprovider-free fixtureへ進む。
- [ ] canaryの有限fake工具でsession続行、native tool block、schema output、run lookup、usage取得をprobeし、実際のAPI/設定キーをcompatibility文書へ固定する。
- [ ] 対応不能なsurfaceはselectorのeligibleから外し、shimを増殖させず根拠をcommit/pushする。
DONE: 公開配布版の実際の互換APIが記録され、canaryはproductionから独立。未対応ならHM-00へ戻り代案設計を更新する。

### HM-02: 既存runner契約を保つoperator bridge

Files: 新規`runtime/openclaw/{protocol.py,transport.py,bridge.py}`、`runtime/openclaw/tests/test_bridge.py`、`config/harness-migration.json`。変更`runtime/agent-runner/agent_runner.py`。
Interfaces: `dispatch(request: HarnessRequest) -> HarnessResult`、`reconcile(request: HarnessRequest) -> HarnessResult`。設計のfieldsをそのまま使う。

- [ ] `test_bridge.py`に未知owner、schema不一致、受領前timeout、受領後ack喪失、previous session不一致をREDとして追加する。assert: schema invalidはsuccessなし、ack喪失ではPOST count=1/自動再送0。
- [ ] `python3 -m pytest runtime/openclaw/tests/test_bridge.py -q`でREDを確認する。
- [ ] HM-01で固定したtransportへ`dispatch/reconcile`を最小実装する。session keyはowner+occurrence、promptはstdin/body、secretはoperatorだけ。dispatch-startedを送信前にdurable記録する。
- [ ] runnerにeligible owner限定selectorを追加し、既存args、result_path、exit/status/summary契約を保つ。未移行ownerは現行route。
- [ ] 同focused testと既存`runtime/agent-runner/tests/test_runtime_event_boundary.py`をPASSしcommit/pushする。
DONE: 同一occurrenceを二重dispatchせず、既存consumerがJSON/schema/eventを読める。

### HM-03: 外部effectを既存brokerへ限定

Files: 新規`runtime/openclaw/tool_broker.py`、`runtime/openclaw/plugin/index.ts`、`runtime/openclaw/tests/test_tool_broker.py`、pluginのfocused test。既存resource/effect authorityを利用する。
Interfaces: `invoke_tool(owner_id: str, occurrence_id: str, tool_name: str, arguments: dict) -> dict`。plugin→brokerはowner-bound local IPC、authorityはsession文字列だけで認証しない。

- [ ] foreign-owner request、重複occurrence、budgetなし、browser leaseなし、effect_unknown、native tool迂回をREDにする。assert: fake provider write count=0、blocked reasonとnext_actionあり。
- [ ] focused Python/plugin testのREDを確認する。
- [ ] actor authority→既存admission/fence→owner工具という最小経路を実装する。sender/owner bindingはoperator側で固定し、modelから受けたowner_idを信用しない。
- [ ] fake provider成功後の再callは同receiptを返しwrite count=1であることをGREENにする。
- [ ] native shell/MCP/HTTPを通したfake販売writeの迂回が拒否されることをHM-01の実native hooksでも確認し、commit/pushする。
DONE: 全販売writeが既存のauthorityとreceipt経路を通る。隔離workspaceだけで安全と判定しない。

### HM-04: trace・usage・CFOを同一occurrenceへjoin

Files: 新規`runtime/openclaw/telemetry.py`、`runtime/openclaw/tests/test_telemetry.py`。利用`runtime/loop/runtime_event.py`、`runtime/agent-runner/usage_report.py`、financial record contract。
Interface: `project_event(raw: dict, request: HarnessRequest) -> dict`。既存event schemaを優先し、足りない字段だけ契約変更を行う。

- [ ] retry/compaction/subagent usage、null cost、観測export停止、fake secret markerをREDにする。assert: usage二重計上0、unknown cost保持、journal喪失0、secret markerなし。
- [ ] focused REDを確認する。
- [ ] upstream OTel/plugin hooks→existing runtime event/usage ledgerへのprojectionを実装する。実費とAPI-equivalent estimateを分ける。
- [ ] focused GREENと既存usage/runtime-event testsを確認する。
- [ ] source/trace/version/cost basisがjoinされたfixture証拠を保存しcommit/pushする。
DONE: process/trace/費用/公式receiptを同じoccurrenceで辿れる。

### HM-05: 失敗trajectoryと再起動契約の回帰評価

Files: 新規`runtime/openclaw/tests/test_recovery.py`、`fixtures/recovery-cases.json`、`docs/evidence/harness-migration/recovery-results.json`。

- [ ] admission後、dispatch後ack前、工具開始後、provider成功後receipt前、terminal保存後の5 crash位置をfake provider/stateで固定する。
- [ ] RED assertを各caseに追加: 未実行はeffect=0、成功後はwrite count=1、曖昧境界はfence保持・replay0、terminal後は新実行0。
- [ ] REDを確認し、bridge/brokerの不足部分だけ修正する。
- [ ] 同一owner2wake、別owner2wake、gateway停止中schedule、usage欠測も隔離profileで確認する。production processをkillしない。
- [ ] `python3 -m pytest runtime/openclaw/tests -q`をPASSして証拠をcommit/pushする。
DONE: documented restartと販売工具replay-zeroの両方が成立。

### HM-06: 現行harnessとの制作task比較・採用判定

Files: 新規`docs/evidence/harness-migration/task-cases.json`・`comparison.json`。reuse`skills/capafy-autopublish/scripts/`のlisting lintと既存eval。

- [ ] baselineからproduction失敗のprefixを1件、成功prefixを1件、fake商品制作taskを1件選び、データ/seed/model/tools/budgetを固定する。
- [ ] 現行と新harnessを隔離output/worktreeで各caseに実行し、production catalog/marketplaceへのwriteを禁止する。
- [ ] Capafy制作例ではSKILL.md/LISTING.md/icon/evidenceの4成果物と既存listing lintを検証する。公開・新商品販売はこの比較に含めない。
- [ ] task成功、総usage/観測cost、RSS、timeout/recovery、adapter量を比較する。新harness安全caseは全PASS、task成功数はbase以上。予算超過/unknown costは採用判断を保留する。
- [ ] HM-01の互換・HM-05の安全・同task比較が成立すれば採用判定をSSOTに記録しcommit/pushする。不成立なら元ownerは保持し、具体causeを診断して設計を改定する。
DONE: 根拠付きSHIP/HOLD。主観的な便利さや公開benchmark点数だけで採用しない。

## B — 自然実行・owner単位切替

### HM-07: 自然read-only canary

Files: 新規`apps/life-manager/scripts/harness-readonly-canary.py`、`runtime/openclaw/tests/test_canary.py`。変更`config/loop-registry.json`、必要なcatalog参照のみ。

- [ ] read-only入力からschema結果とtraceを出すだけのcanaryをRED/GREENで作る。assert: fake provider writes0、budget cap遵守、自然wakeのrun/occurrence/trace join。
- [ ] canaryに専用owner/profile/stateを設定し、既存model quotaの中に予約する。売上や本番sourceを変える工具を広告しない。
- [ ] `./bin/lm-loop-contract`とfocused acceptance→PR/CI→main統合を完了する。
- [ ] main release→対象canaryだけloaded-idle apply→通常scheduleの自然wakeを確認する。
- [ ] loaded SHA/argv、terminal、schema、trace、usage、providerのno-effect読取り結果を保存する。
DONE: natural run1件がPASS、既存owner・gatewayに影響なし。

### HM-08: 旧scheduleから新cronへの所有権移行

Files: 新規`runtime/openclaw/schedule_transfer.py`、`runtime/openclaw/tests/test_schedule_transfer.py`、`docs/runbooks/openclaw-owner-cutover.md`。変更selectorとcanary registry rowのみ。
Interface: `transfer_owner(owner_id: str, expected_release_sha: str, target: str) -> dict`、target=`legacy|openclaw`。stateは既存owner authorityを使う。

- [ ] old running、unknown effect、foreign lease、新cron作成直後crash、旧disable直後crashのREDを作る。assert:同時scheduler authority<=1、job喪失0、外部write0。
- [ ] frozen wake→drain→new cron disabled登録→旧schedule退役→new enabled→readbackの順を実装する。通常gateway defaultや別ownerは変更しない。
- [ ] rollbackを逆順に実装する。未解決occurrenceは両方でfencedを維持する。
- [ ] fixtureでGREENを確認し、source acceptance→main release後にread-only canaryだけschedule移行する。
- [ ] 次の自然due occurrenceが1件だけterminalになることと、旧label/旧wake不在を確認する。
DONE: 新cronが唯一のowner、source/loaded/natural evidenceあり。

### HM-09: Capafy制作・販売ownerを1件移行

Files: 変更`skills/self/capafy-loop/capafy-loop-daily.sh`、selector、必要な既存Capafy testsのみ。publisher/state/readbackは既存を使う。

- [ ] 現行entrypointのnested runner、CAP_FULL、offline daily claim、pending publish、browser leaseを実測し、対象occurrenceの正当な次の工程を確定する。
- [ ] runner seamのみ新bridgeに接続し、既存cap/JSON/ledgerの回帰をfocused RED/GREENで確認する。
- [ ] acceptance/contract/CI→main→immutable release→owner loaded-idle applyを行う。
- [ ] 旧schedulerを保持したまま新runnerの自然runを1件確認する。既存capが満杯なら正当なoffline成果を確認し、capを迂回して新規submitしない。
- [ ] 次の正当な販売occurrenceで既存publisherを実行し、公式listing/submit receiptとcost/trace joinを確認する。購入を移行gateにせず、売上は別評価する。
- [ ] HM-08でこのownerだけscheduleを移し、旧wakeなし・同一effect1回のreadbackを保存する。
DONE: 1商品ownerの制作/販売契約と単一schedulerが新基盤上で自然成立。制限待ちはoffline部分とpublish未達を別記する。

### HM-10: 残ownerをinventory順に移す

Files: HM-00 inventoryに記録したexact caller/test/selector。全repo一括変更は禁止。各ownerは独立PR/自然acceptanceを持つ。

初期waveは(1) read-only/CFO/market research、(2) Capafy・PromptBase・Writer・ebook・affiliateの商品制作/配信、(3) mobile/agent-economy、(4) paid Coconala/Lancers/CrowdWorks/job-hunter、(5) fundraiser/investment/connector/self-buildの残harness consumers。domain effect riskと受注中leaseで順序を決め、変更理由・旧順・新順・cursorをSSOTへ同じ差分で残す。これは本業TODOのreorderではない。

- [ ] waveの先頭ownerをinventoryから1件選び、exact paths/lease/受注・effect状態をread-only確認する。
- [ ] HM-09と同じrunner接続/既存focused acceptance/main releaseをそのownerだけ完了する。
- [ ] そのownerの自然成果/公式readback/costを確認する。vision/repair/resume互換未達は先にHM-01契約を拡張し、無理に移さない。
- [ ] HM-08のschedule移行と旧wake不在を確認する。
- [ ] inventoryに証拠refを付け、SSOTの該当owner完了を更新してcommit/pushする。
- [ ] 未移行ownerがある間は先頭へ戻り、全15 groupsのnested consumersとsupport jobsまでcoverageを確認する。
DONE: inventoryの全eligible consumersが自然acceptance済み。残legacy理由がある場合は具体ownerと未達契約を記録し、全移行完了とはしない。

## C — 自己修復・自己改善・資源配分

### HM-11: 自己修復の1件を既存Self-Buildで実証

Files: 変更`runtime/loop/recovery-supervisor.mjs`、既存recovery/self-build contract。新規`docs/evidence/harness-migration/self-heal.json`。

- [ ] 実際の失敗traceからno-effect・owner-localの修復1件を選び、失敗prefix回帰をREDにする。
- [ ] 既存supervisor→Self-Build/Symphonyのcandidate経路へupstream run/traceを渡し、新しいcoding harnessを作らない。
- [ ] Life Manager自身のexecutorが最小修正→focused GREEN→PR/CI→main/releaseへ進むようcontract不足だけ修正する。
- [ ] 対象ownerの自然terminal/readbackとreplay-zeroを確認する。
- [ ] before/after occurrence・code diff・release・receiptを同じ修復recordへ保存する。
DONE: issue/restartでなく、Life Manager自身の修正が本番に届き同じ失敗classを解消。

### HM-12: 固定dataset・judgeを既存evalへ接続

Files: 新規`apps/life-manager/eval/harness-migration/{cases.jsonl,run.js,run.test.js}`。reuse economic-autonomy/agent-contract score。
Interface: `evaluateCandidate({baseRef,candidateRef,datasetRef,modelRef,toolRef,budgetRef,seed}) -> {runtime,task,business,costCoverage,evidenceRefs}`。

- [ ] HM-05/06のケースをtrain/holdoutに分けhash固定し、candidateからholdoutへwrite/readして学習できない境界を作る。
- [ ] fake receipt・unknown cost・重複settlement・部分達成をREDにする。assert: business score不合格、unknownを保持。
- [ ] 同task/model/tools/budgetで比較し、経済scoreは既存LM-EABへ委譲する最小runnerを実装する。
- [ ] `node --test apps/life-manager/eval/harness-migration/run.test.js`と既存economic-autonomy関連testをGREENにする。
- [ ] 主観judgeを使う場合だけ既存評価例との一致を確認し、dataset/judge version・coverageを記録する。
DONE: trace・task成果・利益を混同せず再現可能に評価。

### HM-13: skill/prompt改善candidateを1件昇格

Files: 変更`skills/earn/marketing-engine/report/scheduled_runner.py`、必要な既存self-improve testsとcandidate skillのみ。

- [ ] 失敗traceから1候補を隔離branchに作り、workshop/dreamingは参考入力に限定する。
- [ ] HM-12でbase/candidateを比較し、安全全PASS・task成功>=base・既知失敗1件以上改善・観測費用<=baseを確認する。
- [ ] 不合格候補は生産skillを変更せず、失敗理由と次の観測を保存する。合格候補だけsource acceptance→main→immutable releaseへ昇格する。
- [ ] owner限定自然canaryで劣化/未知effect/cost欠測がないかを確認し、劣化時はHM-08 rollback手順を使う。
- [ ] parent/candidate SHA、sealed holdout結果、費用、natural readbackを記録する。
DONE: スキル生成でなく評価で改善した候補が反映。自律policy/credential変更なし。

### HM-14: 実測concurrencyと収益配分

Files: selector/admission configの必要な差分、`docs/evidence/harness-migration/capacity.json`。既存switchboardを利用する。

- [ ] isolated fake工具で同時1/2/4のqueue latency/RSS/provider throttlingを測り、host/provider limitsを確認する。
- [ ] production自然usage/cost/task成功を読み、tool/hostのボトルネックとmodel枠不足を分ける。
- [ ] 上限拡大はmarginがある場合だけ1段階行い、browser/owner/spend上限を維持する。無根拠に8/184へ上げない。
- [ ] switchboardへCFOのsettled net/unknownとtask backlogを渡し、modelが配分案を出しadmissionがcapを執行する。
- [ ] 次の自然occurrenceでqueue/cost/receipt joinを確認し、差分をcommit/pushする。
DONE: agent数の見栄えでなく実測性能と実費で容量を決める。

## D — 自作層の退役・完了readback

### HM-15: 参照のない自作harnessを削る

Files: 移行済み`runtime/agent-runner/`分岐、shared wrapper、旧schedule/health/recoveryの不要部分、README。削除pathはHM-00 inventoryと`rg` caller結果で確定する。

- [ ] 全eligible consumersのloaded/natural acceptanceを確認し、残参照とeffect_unknownを列挙する。
- [ ] gateway/agent役割がupstreamへ移った旧runner/retry/session/cron部分だけ削除する。domain fence/receipt/CFO/admissionを削除しない。
- [ ] 対象focused testsと`./bin/lm-loop-contract`をPASSする。不要旧tests/docsも同じ差分で整理する。
- [ ] main release→対象反映後、旧runner/agent plistの再出現なしと新owner自然runを確認する。
- [ ] retired path/commit/evidenceをSSOTへ記録する。
DONE: 恒久的な二重実装なし、自作層を実際に減らした差分あり。

### HM-16: 全ownerの技術移行を判定

Files: `docs/evidence/harness-migration/final-acceptance.json`、統合SSOT。

- [ ] inventory全行にsource commit/release/loaded owner/scheduler/natural occurrence/tool receipt/cost trace/refをjoinする。
- [ ] missing/unknownは具体owner・境界・次の観測として記録し、健康や0へ変換しない。
- [ ] HM-08 rollback契約・旧wake0・duplicate effect0・credential露出0・self-heal/self-improve証拠を照合する。
- [ ] 全tech criteria成立時のみmigration完了をSSOTに記録し、commit/pushする。
DONE: 全移行済みownerで既製harnessが自然稼働し、旧agent orchestration退役。売上達成とは別。

### HM-17: 販売agentの経済成果を既存CFOへ返す

Files: 既存CFO readback/financial record、必要なowner-local帰属修正のみ。

- [ ] 自然販売の公式sale/order、refund/fee、payout/settlement、actual model/tool costをproduct/occurrenceへjoinする。
- [ ] LM-EABで売上・純利益・欠測を評価し、まだ購入/入金が無いownerはそのままunknown/未達を表示する。
- [ ] 次の収益行動を既存agentが継続し、技術移行の完了を購入待ちで再び止めない。
- [ ] 収益の成果条件が満たされたownerだけCFO証拠refをSSOTへ記録する。
DONE: harnessの健康と経済成果が分離され、収益claimは公式証拠と実費で検証可能。

## 実行時の再開情報

repo=`/Users/anicca/Projects/life-manager-main`、branch/worktreeは各task開始時に最新mainから作成する。設計と計画の絶対パスはrepo配下の同名file。残TODO正本は`docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`のHM lane。初期cursor=HM-00。owner単位でsource→promotion→自然成果を完了し、他laneの処理中effectを中断/重複させない。
