# Life Manager — 既存runner内の最初のharness切替計画

> 実行workerは`superpowers:executing-plans`を読む。実装=gpt-6-luna/max、計画・検証=gpt-6.1-sol/medium。今回の依頼はreadiness監査までで、以下は未着手。状態正本は統合SSOTのMX lane。

**目的:** 既存収益ownerのschedule/state/publisherを変えず、有限CLI backendを差し替えるための最小adapterを実装する。
**構成:** 既存entrypoint→同agent_runner preflight/lease/budget→legacy CLIまたはOpenClaw agent exec→同caller schema/result_path/summary。
**技術:** Python既存runner、Node24.16、OpenClaw2026.9.8の固定main-derived package bundle、既存jsonschemaとtest framework。
**Spec:** [設計の初回移行縮小](../specs/2026-10-07-life-manager-harness-migration-design.md)、[readiness](../../research/2026-10-07-harness-transition-readiness.md)。

## 共通条件

- scheduler/registry cadence、publisher/readback、credential/browser profile、mutable state、CFO、model/account/backendを変更しない。
- 全candidateはdefault legacy。image/repair/resume/未検証native budget/tool parityはlegacyに固定する。
- sourceに新gateway daemon、再起動supervisor、HTTP/RPC dispatch store、新model semaphoreを作らない。既存run_provider_processの所有process group内で有限childを起動する。
- 同一入力JSON schema、timeout、token budget、selected account/effortを保持。APIキー課金へ黙ってfallbackしない。
- processが始まった後の不確実な失敗はsame-occurrence fallback/replayを禁止。rollbackはfuture wakeのselectorだけ、pending/running/unknownはdrain/readback先行。
- source focused acceptance→PR/CI/main→immutable release→target loaded-idle apply→自然run。試験はfake/private state、production故意kill無し。

## review重点

stdout envelopeをcaller resultと混同、usage欠測を0計上、cleanup不確実なのにsuccess、timeout後の別backend再送、native account/model/budget/toolsの暗黙変更。下記testのassertionで固定する。

### MX-01 — pure envelope decoder

- [ ] Create `runtime/agent-runner/openclaw_exec.py` の `decode_envelope(stdout_text: str, return_code: int) -> dict`。CLIは実測で前置きlogをstdoutへ出すため、json.JSONDecoderでtop-level JSON documentsを走査し、ok/status/final/sessionIdのenvelope構造を満たす候補がちょうど一つであることを確認する。JSON内部のnested objectを別候補と数えない。ok=true/status=ok/return_code=0を要求し、final stringとusage/provider/model/sessionIdだけを返す。payloadsやログ文字列をcaller JSONと扱わない。error/timeout/cleanup failed/JSON欠落はtyped failure、stderr全文を例外へ混ぜない。
  Test `runtime/agent-runner/tests/test_openclaw_exec.py::test_envelope_contract`: final中のstatus=successを得る、outerstatus=okを返さない、exit1+oktrueは拒否、invalidJSON拒否、usagemissing保持、実測の[state/agent-db] prefix+envelopeを受ける、候補envelope2件はambiguous rejection。RED→minimal GREEN。

### MX-02 — existing caller result file

- [ ] 同moduleに `write_caller_result(envelope: dict, schema: dict, result_path: Path) -> Path`を追加。finalだけを既存parse_contract_result/jsonschemaと同じ契約で検証し0600 atomic writeする。mtimeは当該attempt開始後。status/ref/receiptを生成しない。
  Test `test_openclaw_exec.py::test_caller_schema_and_fresh_result`: {status:success,evidence:[]}のcaller schema通過、schema違反/古いresultは選択不可、model文章のreceiptは公式証拠にしない。依存MX-01。

### MX-03 — normalized usage

- [ ] 同moduleに `project_usage(envelope: dict, cost_basis: str) -> dict`を追加。usage.input/output/total/cacheの明示fieldを既存usage dictへ写し、未観測cache/token/costはNone。costUsdは請求receiptでなければapi_equivalent_estimateとして保持し、totalだけから内訳を推定しない。
  Test `test_openclaw_exec.py::test_usage_missing_and_cost_basis`: input12/output5/total17を保持、missingnull、priceestimateと実請求を区別。依存MX-01。

### MX-04 — finite command builder

- [ ] 同moduleに `build_command(node: Path, entry: Path, config_path: Path, workdir: Path, model: str, effort: str, timeout_seconds: int) -> list[str]`を追加。argvは[node, entry, agent, exec, --config, config_path, --message-file, -, --json, --cwd, workdir, --model, model, --thinking, effort, --timeout, seconds]。prompt/keyをargvへ置かず、configはpinned instance config。--auth-env-onlyと--configを混ぜない。Node/entryはimmutable bundle絶対pathでglobalPATHへfallbackしない。
  Test `test_openclaw_exec.py::test_exact_finite_argv`: argv完全一致、secret/prompt文字列なし、relative/executable missing拒否。config/model/backend/accountはMX-09 parityが成立した値だけ使う。依存MX-01。

### MX-05 — owner/task selector, default off

- [ ] 同moduleに `select_engine(owner_id: str | None, task_class: str, config: dict) -> str`を追加。config.openclaw_exec_routes[owner][task_class]はenabled/parity_evidence_ref付き。default/unknown/unsupported/image/resume/repairはlegacy。allowlistは移行対象を限定するdeployment selectorで、skill能力判定ではない。
  Test `test_openclaw_exec.py::test_default_off_and_unsupported`:既存routes全legacy、selected verified diagnosticだけcandidate、unknownowner/未証明parityはlegacy。依存MX-04。

### MX-06 — integrate command generation, preserve process ownership

- [ ] Modify `runtime/agent-runner/agent_runner.py::command_for`。selectorで候補engineを選んだ時だけMX-04へ委譲。既存provider/candidate model/effort/profile_aliasを維持し、既存run_provider_processでchildを実行する。CLI credential/plugin/backend parityが設定に無ければprovider開始前にcandidateを拒否する。legacy branchのargvは不変。
  Test `test_openclaw_exec_route.py::test_process_route_and_legacy_argv`: legacyCodex/Claude argv不変、budget/lease/evidence preflight不変、gateway PIDにclaimを移管しない。依存MX-05。

### MX-07 — normalize result at the existing acceptance boundary

- [ ] Modify `agent_runner.py::run()` のprovider completion→result parsing/usage部分。candidate engineがopenclaw_execの場合だけMX-01/02/03を使い、同summary keysとresult_path/attempts/runtime eventへproject。selected_provider/profile/modelはcaller指定の値を勝手に変更せず、upstream model/provider mismatchはvalidation failure。
  Test `test_openclaw_exec_route.py::test_existing_summary_consumer`: run_agent.shとWriter shared-model-runner.pyの既存JSON consumerが同resultを読む、upstream mismatchでsuccessなし。依存MX-06。

### MX-08 — prohibit unsafe cross-harness fallback

- [ ] Modify `agent_runner.py::run()` のfallback判定だけ。candidate subprocess開始後のtimeout/disconnect/cleanup_failed/JSON欠落はunknown-after-startとして同occurrenceの次candidateへ進まない。明確なprelaunch failureだけ既存policyに沿ってlegacyへ戻せる。CLI errorからeffect=0を推測しない。
  Test `test_openclaw_exec_route.py::test_no_fallback_after_start`: sentinelwrite1後timeout/disconnectでsecondchild0、start前executable_missingはnoeffect proof付き、processgroup childrenをreapできなければfence。依存MX-07。

### MX-09 — same native account/model/budget/tool parity record

- [ ] Create `docs/evidence/harness-migration/native-parity.json`。source provider/profile/model/effort/rollout-budget/featuresと、candidateのpublic config/native runtime readbackを照合する。real credentials値を保存/複製しない。API-key fake probeでnative Codex同account互換をPASSにしない。境界ごとconfirmed/unsupported/unmeasuredを記録し、全required field confirmedのtaskclassだけMX-05へeligible。
  Verificationはsource exact selected candidateとaccount/backend/model/tool/rollout capのreadback。native rollout-budget/image/resumeの非対応はlegacyを保持するので収益ownerを止めない。既存live owner/profileのleaseがある時は取り上げない。依存MX-08。

### MX-10 — isolated task comparison, only supported taskclass

- [ ] Create `docs/evidence/harness-migration/finite-cli-comparison.json`。既存tool-less diagnostic/semantic caseを同model/account/tools/budgetで比較し、schema、task成功、usage、error、runtime cleanupを記録。candidateは同task成功>=base、観測費用<=base、安全case全PASS、hostcapacity内。native/経済費用unmeasuredならactivationHOLD。
  Verify MX-01〜08 focused tests、existing runner tests、loop-contract。fake/provider-free結果と実account結果を別recordsにする。依存MX-09。

### MX-11 — first activation is a tool-less canary only

- [ ] Modify `runtime/agent-runner/config.json` のopenclaw_exec_routesで、MX-09/10全required evidenceがPASSの既存診断/semantic owner/taskclassを一つだけenabledにする。他ownerはlegacy。実際のselectedownerはvalidated比較recordに固定される。paid publisher/browser/task fulfillmentを初回に選ばない。
  source/CI/main後target releaseをloaded-idleでapply。running/pending/fenced occurrenceを移し替えず次の自然wakeで同schema/trace/budgetをreadback。ownerのexact configured/loaded SHAとreceiptが得られない場合activationしない。依存MX-10。

### MX-12 — exact rollback receipt

- [ ] Create `docs/evidence/harness-migration/first-cutover.json`。selector旧/新、source/release、oldrunning/pending、自然occurrence、schema/usage/cleanup、未確定effectを記録。異常時はnewwake停止→対象child/group停止proof→当該selectorだけlegacyへ戻す。state/credential/ledger/reviewed productsは巻戻し・再生成しない。
  Assert futurewakelegacy、unknownoccurrence両backend再送0、他ownerのargv/state/hash不変更。初回成立後にだけ収益owner一件のtool parity/cutoverを追加設計する。依存MX-11。

## 実行可否の境界

MX-01〜08は現在のsourceと公開CLI入出力の契約で実装可能なadapter単位。MX-09〜12は実証recordを作るoperation/verification atomsであり、parity結果を実装前から成功と断定しない。未測定のreal account/tool/rollout budgetがある間、candidateはdefault-offで収益経路を維持する。full migrationや売上維持の保証とfirst-adapter実装可能性を混同しない。
