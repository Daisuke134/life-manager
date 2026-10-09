# Life Manager共通storage・cleanup再発防止 実装計画

> 実装はSuperpowers executing-plansで原子順に進める。状態/順序の正本は統一SSOT。

**Goal:** 今日の仕事と翌日の仕事を、管理下のログ/再生成物の増大・実書込み失敗で欠落/重複させず、同じ仕組みをOpenClaw移行後も使う。
**Architecture:** 既存host inventory、cleanup governor、5分pass、watchdog、15日dispatcher、admission/recovery/domain fenceを再利用する。管理下stdio/再生成物に保存量契約を追加し、cleanup実行成功と容量回復を分離する。agent/session/cronの新frameworkは作らない。
**Tech Stack:** Python標準ライブラリ(logging.handlers/subprocess/os/socket)、既存Python/Node runtime、既存OS supervisor、既存jsonschema。
**Spec:** docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md のstorage先行section。

## 確認したbaseline

- source baseline: 844e8efaf63552fd8c213fea9dda67519e4aab57。最新mainの15日cleanup dispatcherを再利用。既存OpenClaw残計画は233atom。
- 前回のlive readback: Data空き約0.57GiB。cleanup rc0/errors0/protected0でもcapacity_recovery=unmet。古いhealth healthy snapshotは同receiptの評価ではない。
- 現行stderr修正は終了後のreplay/tailだけをboundedにし、実書込は無制限。raw provider stdout/stderrにも直接file captureがある。
- writerと増加速度の全体帰属は未完。大きいrootが原因だと断定せず、DS03でmetadata観測を実装する。

## 共通条件

- 個人Codex/OpenClaw store、credentials/browser identity、memory、state JSONL、active/loaded release、既存商品/注文/receipt、Simulatorは削除/移動しない。未知/open pathは保持。
- producerの固定free-space floor・全loop stopは復活させない。actual ENOSPC/EDQUOTとoperator stop、保存量契約を区別する。cleanupの2GiBは診断値でありadmission条件ではない。
- 管理下stdio relayは有限runの所有process。EOFまで生存し、親終了/timeoutでログreaderだけを先に殺して孫processへSIGPIPEを起こさない。個人/既存daemonのFDを遡って変更しない。
- terminal/event/resultは正本で、diagnostic raw logはbounded copy。schema/result/usageを確定する前にraw stdoutを捨てない。
- readonly snapshotはmetadataのみ。private run rootは0700、file0600、nofollow/owner/start identity検証。source/fixtureはworktree、本番state/ログをコピーしない。
- effect_unknownは公式readbackへ。capacity回復やprocess終了を外部効果の未実行証拠にしない。
- DS01–14はsource/隔離fixture。DS15–17だけが本番promotion/自然証拠。現在の依頼は計画更新であり、本番操作はまだ実施しない。

## Review Focus

1. 親が終了しても孫がstderrへ書き、reader先終了でSIGPIPEになるケース → DS06/07。
2. result/usageがraw stdoutのrotationで失われるケース → DS08。
3. 誤ったowner/open path/未知effect成果物を回収するケース → DS05/09。
4. effect後のENOSPCをpre-effectと誤認して再送するケース → DS10/11。
5. 旧receipt・partial inventory・健康snapshotの時間違いを回復完了へ変換するケース → DS01/02/03/16。

## 新規interfaceの固定shape

- StoragePolicy: version=1、owner_id、diagnostic_segment_bytes=1048576、diagnostic_backup_count=1、chunk_bytes=4096、head_bytes=32768、metadata_max_bytes=4096、structured_record_max_bytes=16777216、owner_diagnostic_retained_bytes=16777216、host_diagnostic_retained_bytes=536870912。boolはintegerとして受理しない。byte contractは管理下の診断出力だけに適用し、自由容量のadmission floorではない。
- OwnerBinding: owner_id/run_id/occurrence_id/release_sha/private_root。この値は既存runner/registryから渡し、child/modelの申告をauthorityにしない。
- RelayHandle: pid/process_start/owner_binding/stdin_write_fd/control_socket。親はentrypoint stderrにstdin_write_fdだけを渡す。helperは別process group、全writer EOFまでdrain。
- RelayReceipt: owner/run/occurrence/release、pid/start、observed_at、retained_bytes、written_bytes、dropped_bytes、tail_b64（末尾2048bytes）、storage_error=null|ENOSPC|EDQUOT、eof bool。control socketの不在/満杯でhelperを終了しない。
- StorageSnapshot: owner attribution付きroot別size_bytes/delta_bytes/elapsed_seconds/bytes_per_second、coverage、unattributed。nullを0へ変換せず古いsnapshotから回復完了を推測しない。
- StorageFailure: owner/run/occurrence/release/phase、errno、effect_started、retryable、next_action、evidence_refs。effect開始が不確かな場合はpre-effectに変換しない。

## 全原子

### Task 1: DS01 — host_cleanup_readback(returncode, stdout) -> tuple[bool, dict]

**Files:** runtime/loop/central_cleanup.py  
**Test:** runtime/loop/tests/test_loop_cleanup.py  
**Depends:** なし  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`host_cleanup_readback(returncode, stdout) -> tuple[bool, dict]`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: rc0/errors0/protected0/free_after600MiBではexecution_ok=trueかつcapacity=unmet。unknown容量はunknown、別runのreceiptは採用しない。
- [ ] Step 2: `python3 -m pytest runtime/loop/tests/test_loop_cleanup.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `runtime/loop/central_cleanup.py` の `host_cleanup_readback(returncode, stdout) -> tuple[bool, dict]` を変更: cleanup実行成功と容量回復を別の値として返す。okの既存意味は維持。trusted runnerからowner/run/occurrence/releaseをreceiptへ付け、capacity_recovery.status=met|unmet|unknownを失わない。低容量だけを理由にcleanupを失敗・全producer停止にしない。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS01行で更新する。

**Done:** rc0/errors0/protected0/free_after600MiBではexecution_ok=trueかつcapacity=unmet。unknown容量はunknown、別runのreceiptは採用しない。

### Task 2: DS02 — project_health(rows, *, scope, storage_snapshot=None) -> dict

**Files:** runtime/loop/health.py; runtime/loop/health.schema.json; runtime/loop/health_observer.py; runtime/loop/lm_loop.py  
**Test:** runtime/loop/tests/test_health_observer.py; runtime/loop/tests/test_lm_loop_health.py  
**Depends:** DS01  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`project_health(rows, *, scope, storage_snapshot=None) -> dict`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: 正常cleanup+unmetをhealthy/回復完了に統合しない。old/foreign receiptはunknown。実CLI health/status fixtureがsnapshotを受け渡す。全既存health schema tests PASS、Telegram等の新規送信0。
- [ ] Step 2: `python3 -m pytest runtime/loop/tests/test_health_observer.py runtime/loop/tests/test_lm_loop_health.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `runtime/loop/health.py; runtime/loop/health.schema.json; runtime/loop/health_observer.py; runtime/loop/lm_loop.py` の `project_health(rows, *, scope, storage_snapshot=None) -> dict` を変更: host_storageを閉じた任意top-level項目としてschema生成元へ追加し、生成JSONを同期する。executionとcapacityをCLIで別表示。lm_loop.py::mainのhealth/status callerがvalidated storage_snapshotをproject_healthへ渡す。run/occurrence/release一致とsnapshot時間を確認し、古いreceiptを現在の回復証拠にしない。容量変化の通知は既存local alert経路だけ。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS02行で更新する。

**Done:** 正常cleanup+unmetをhealthy/回復完了に統合しない。old/foreign receiptはunknown。実CLI health/status fixtureがsnapshotを受け渡す。全既存health schema tests PASS、Telegram等の新規送信0。

### Task 3: DS03 — project_storage_growth(previous, current, registry_roots) -> dict

**Files:** skills/self/disk-cleanup/host_inventory.py  
**Test:** skills/self/disk-cleanup/tests/test_host_inventory.py  
**Depends:** なし  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`project_storage_growth(previous, current, registry_roots) -> dict`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: 2snapshotの100MiB増/60秒を検証。新規root・時計逆行・partial sizeはrate=null。symlink/permission gapはunknownで、ownerを名前だけから推測しない。
- [ ] Step 2: `python3 -m pytest skills/self/disk-cleanup/tests/test_host_inventory.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `skills/self/disk-cleanup/host_inventory.py` の `project_storage_growth(previous, current, registry_roots) -> dict` を変更: 既存collect_host_inventoryのbounded metadata snapshotから、同じrootのbytes差分・elapsed_seconds・bytes_per_second・owner/ref・coverageを出す。registry外はunattributed。content読取・lsof強制・未知path削除なし。既存full/fast budgetを再利用。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS03行で更新する。

**Done:** 2snapshotの100MiB増/60秒を検証。新規root・時計逆行・partial sizeはrate=null。symlink/permission gapはunknownで、ownerを名前だけから推測しない。

### Task 4: DS04 — load_storage_policy(path, owner_id) -> StoragePolicy

**Files:** config/storage-policy.json; runtime/host/storage_policy.py  
**Test:** runtime/host/tests/test_storage_policy.py  
**Depends:** なし  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`load_storage_policy(path, owner_id) -> StoragePolicy`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: bool/negative/unknown field/foreign ownerを拒否。未定義ownerは既存処理を勝手に変更しない。HOME/data rootを変えたclean fixtureで個人絶対path依存0。
- [ ] Step 2: `python3 -m pytest runtime/host/tests/test_storage_policy.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `config/storage-policy.json; runtime/host/storage_policy.py` の `load_storage_policy(path, owner_id) -> StoragePolicy` を変更: operator所有のclosed policyを定義。diagnostic segment=1MiB、backup=1、chunk=4096、diagnostic total<=2MiB+40KiB。closed diagnostic retentionはowner16MiB/host512MiBの初期値でoperator変更可（business result/receiptへこの削除budgetは適用しない）。structured text result上限の初期値16MiBはownerで明示変更可能。保持対象はhostが印を付けた再生成可能診断だけ。個人session・credentials・memory・state JSONL・未知effect成果物は対象外。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS04行で更新する。

**Done:** bool/negative/unknown field/foreign ownerを拒否。未定義ownerは既存処理を勝手に変更しない。HOME/data rootを変えたclean fixtureで個人絶対path依存0。

### Task 5: DS05 — cleanup_run_root(...); gc_releases(...)

**Files:** runtime/loop/loop_cleanup.py  
**Test:** runtime/loop/tests/test_loop_cleanup.py  
**Depends:** DS04  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`cleanup_run_root(...); gc_releases(...)`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: 数は少ないがbyte量が大きいclosed fixtureだけ回収。active writer/loaded release/receipt未保存/memory/state JSONL/symlink保持、protected_deletions=0。
- [ ] Step 2: `python3 -m pytest runtime/loop/tests/test_loop_cleanup.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `runtime/loop/loop_cleanup.py` の `cleanup_run_root(...); gc_releases(...)` を変更: 既存age/count retentionへmanaged_bytesを追加。host .lm-regenerable、terminal receipt、closed PID/start identityを満たす候補だけ古い順で回収。active/loaded/current/protected/unknownは必ず保持し、unrecoverable_bytesを別報告する。worktree削除は既存owner退役手順に限定。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS05行で更新する。

**Done:** 数は少ないがbyte量が大きいclosed fixtureだけ回収。active writer/loaded release/receipt未保存/memory/state JSONL/symlink保持、protected_deletions=0。

### Task 6: DS06 — start_stderr_relay(private_root, policy, binding) -> RelayHandle; relay_stderr(read_fd, control_fd, private_root, policy, binding) -> RelayReceipt

**Files:** runtime/host/bounded_output.py  
**Test:** runtime/host/tests/test_bounded_output.py  
**Depends:** DS04  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`start_stderr_relay(private_root, policy, binding) -> RelayHandle; relay_stderr(read_fd, control_fd, private_root, policy, binding) -> RelayReceipt`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: 32MiBの改行なし/binary stderrでもretained<=2MiB+40KiB、RAM buffer bounded。親exit後にdetached childが書いてもEPIPE/SIGPIPE0。foreign metadata・symlink拒否、保存不能でもdrain継続。
- [ ] Step 2: `python3 -m pytest runtime/host/tests/test_bounded_output.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `runtime/host/bounded_output.py` の `start_stderr_relay(private_root, policy, binding) -> RelayHandle; relay_stderr(read_fd, control_fd, private_root, policy, binding) -> RelayReceipt` を変更: 新しいagent frameworkや常駐daemonを作らず、有限runに属するstdio relayを作る。stdlib RotatingFileHandler、latin-1 byte roundtrip、formatter messageのみ、terminator空、segment/backup/chunkをDS04で固定。最初32KiBのheadをhost-owned .headへ一度保存し、後続rotationでも最初の診断を失わない。writerはpipeを持ち、relayは全writerのEOFまで読み続ける。自身をentrypointのkill groupへ入れない。起動はimmutable release内の固定script/Pythonだけ。helperに渡すFDはread/controlのみ（provider/model/admission lease FDは継承しない）、envはPATH/LANG/TMPDIRだけの最小集合でprovider secretsは継承しない。PID/startとownerをprivate metadataに保存。ENOSPC時も読み捨てdrainを続け、bounded tailとstorage_errorをnonblocking UNIX datagram socketpairへ返す（最大4KiB/frame）。親側close/queue満杯は通知をdropするだけでinput drainを止めない。親用read_relay_snapshot(handle)でlatest frameを取得。handlerのerrorを握り潰さない。helperだけumask077。stderr captureの既存小さいbyte列はそのままroundtripする。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS06行で更新する。

**Done:** 32MiBの改行なし/binary stderrでもretained<=2MiB+40KiB、RAM buffer bounded。親exit後にdetached childが書いてもEPIPE/SIGPIPE0。foreign metadata・symlink拒否、保存不能でもdrain継続。

### Task 7: DS07 — _run_entrypoint_with_stderr_capture(...); scratch_gc(...)

**Files:** runtime/loop/lm_loop_run.py; runtime/loop/central_cleanup.py  
**Test:** runtime/loop/tests/test_lm_loop_run_bounds.py; runtime/loop/tests/test_loop_cleanup.py  
**Depends:** DS05, DS06  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`_run_entrypoint_with_stderr_capture(...); scratch_gc(...)`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: 短いstderrのbyte互換、large stderr bounded、親後に書くchild生存、active relay root回収0、他owner停止0。既存FDへのtruncate/RLIMIT_FSIZE/force closeなし。
- [ ] Step 2: `python3 -m pytest runtime/loop/tests/test_lm_loop_run_bounds.py runtime/loop/tests/test_loop_cleanup.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `runtime/loop/lm_loop_run.py; runtime/loop/central_cleanup.py` の `_run_entrypoint_with_stderr_capture(...); scratch_gc(...)` を変更: DS06を有限entrypointのstderr境界へ接続。stdout/exit/timeout/cancel/業務receiptは不変更。親終了だけでrelayを殺さず、last2048 bytesを既存diagnosticへ返す。scratch GCはlive relay PID/startがあるrootを保持し、EOF後だけ回収。既存browser/daemonのFDは遡って変更しない。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS07行で更新する。

**Done:** 短いstderrのbyte互換、large stderr bounded、親後に書くchild生存、active relay root回収0、他owner停止0。既存FDへのtruncate/RLIMIT_FSIZE/force closeなし。

### Task 8: DS08 — run_provider_process(...); extract_provider_usage(provider, stdout_text, model=None)

**Files:** runtime/agent-runner/agent_runner.py  
**Test:** runtime/agent-runner/tests/test_bounded_provider_output.py  
**Depends:** DS06, DS04  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`run_provider_process(...); extract_provider_usage(provider, stdout_text, model=None)`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: 32MiB diagnostic出力でも上限内、最終JSONとusageが非rotation baseline一致。record oversizeはsuccess0、画像/result/resume互換、親後childのSIGPIPE0。
- [ ] Step 2: `python3 -m pytest runtime/agent-runner/tests/test_bounded_provider_output.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `runtime/agent-runner/agent_runner.py` の `run_provider_process(...); extract_provider_usage(provider, stdout_text, model=None)` を変更: stderrへDS06を適用。stdoutは構造化eventをstreamで消費してresult/usageを確定してからdiagnosticをbounded保存する。Codexの既存result_pathが正本。16MiB上限を超える単一structured recordはtyped result_oversizedにし、切れたJSONを成功にしない。model/account/route/resume/token-budget/provider lease契約は変更しない。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS08行で更新する。

**Done:** 32MiB diagnostic出力でも上限内、最終JSONとusageが非rotation baseline一致。record oversizeはsuccess0、画像/result/resume互換、親後childのSIGPIPE0。

### Task 9: DS09 — HostDiskGovernor.run_once(); host_cleanup_readback(...)

**Files:** skills/self/disk-cleanup/disk_cleanup.py; runtime/loop/central_cleanup.py  
**Test:** skills/self/disk-cleanup/tests/test_disk_cleanup.py; runtime/loop/tests/test_loop_cleanup.py  
**Depends:** DS01, DS03, DS05  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`HostDiskGovernor.run_once(); host_cleanup_readback(...)`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: cursor budget切れでも次passへ公平に進む。候補無し/全protectedならunmetを正直に返す。busy lockで二重sweep0、15日dispatcherの既存tests PASS。
- [ ] Step 2: `python3 -m pytest skills/self/disk-cleanup/tests/test_disk_cleanup.py runtime/loop/tests/test_loop_cleanup.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `skills/self/disk-cleanup/disk_cleanup.py; runtime/loop/central_cleanup.py` の `HostDiskGovernor.run_once(); host_cleanup_readback(...)` を変更: 既存5分pass・watchdog・15日dispatcher・singleton・candidate cursor・receipt reserveを再利用する。DS03/05をreceiptへ結合し、reclaimed/remaining/protected/unattributed/coverageを分ける。閉じたallowlist candidate以外へcleanup範囲を拡大しない。回復未達でも理由と次の処理対象を具体的に残す。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS09行で更新する。

**Done:** cursor budget切れでも次passへ公平に進む。候補無し/全protectedならunmetを正直に返す。busy lockで二重sweep0、15日dispatcherの既存tests PASS。

### Task 10: DS10 — classify_storage_failure(error, phase, binding, effect_started) -> dict

**Files:** runtime/host/storage_failure.py; runtime/loop/runtime_event.py; runtime/loop/lm_loop_run.py; runtime/agent-runner/agent_runner.py  
**Test:** runtime/loop/tests/test_storage_failure.py; runtime/loop/tests/test_runtime_event.py; runtime/agent-runner/tests/test_storage_failure.py  
**Depends:** DS07, DS08, DS09  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`classify_storage_failure(error, phase, binding, effect_started) -> dict`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: prepare/result/terminal各write failureを注入。pre-effect RPC0、effect後再送0、same owner/occurrence/run/release/phase/errno/ref保持。診断保存自体失敗しても成功receipt偽造0。
- [ ] Step 2: `python3 -m pytest runtime/loop/tests/test_storage_failure.py runtime/loop/tests/test_runtime_event.py runtime/agent-runner/tests/test_storage_failure.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `runtime/host/storage_failure.py; runtime/loop/runtime_event.py; runtime/loop/lm_loop_run.py; runtime/agent-runner/agent_runner.py` の `classify_storage_failure(error, phase, binding, effect_started) -> dict` を変更: shared runtime/host/storage_failure.pyに分類関数を一度定義し、runner二経路は同じ関数を呼ぶ。runtime_eventへclosed optional storage_failure(errno/operation/effect_started/proof_ref)を追加してvalidator/serializerを同期する。実際のENOSPC/EDQUOTだけをtyped storage errorとして境界記録する。既存terminal-unrecorded/receipt reserveの処理を再利用し、未保存を保存済みとしない。effect前はpre_effect_failure、effect後はeffect_unknownを維持。free-space数値やcleanup unmetだけでは全loopをdeferしない。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS10行で更新する。

**Done:** prepare/result/terminal各write failureを注入。pre-effect RPC0、effect後再送0、same owner/occurrence/run/release/phase/errno/ref保持。診断保存自体失敗しても成功receipt偽造0。

### Task 11: DS11 — _enqueue_recovery_intent(...); buildRecoveryIntent(input); buildRecoveryIntentRecord(...); buildRecoveryApplyPlan(...); executeRecoveryPlan(...)

**Files:** runtime/loop/lm_loop_run.py; runtime/loop/recovery-intent.mjs; runtime/loop/recovery-intent-record.mjs; runtime/loop/recovery-apply-plan.mjs; runtime/loop/recovery-executor.mjs  
**Test:** runtime/loop/__tests__/recovery-intent.test.mjs; runtime/loop/__tests__/recovery-intent-record.test.mjs; runtime/loop/__tests__/recovery-apply-plan.test.mjs; runtime/loop/__tests__/recovery-executor.test.mjs; runtime/loop/tests/test_lm_loop_run_bounds.py  
**Depends:** DS10  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`_enqueue_recovery_intent(...); buildRecoveryIntent(input); buildRecoveryIntentRecord(...); buildRecoveryApplyPlan(...); executeRecoveryPlan(...)`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: 容量復旧後の同仕事処理1回、receipt確認済み仕事再送0。未知effect/foreign owner/古いcleanupはhold。supervisor→buildRecoveryApplyPlan→executorのcaller-level fixtureまで通す。新action未定義による拒否0。retry backoff有限、他owner動作不変更。
- [ ] Step 2: `python3 -m pytest runtime/loop/tests/test_lm_loop_run_bounds.py` と `node --test runtime/loop/__tests__/recovery-intent.test.mjs runtime/loop/__tests__/recovery-intent-record.test.mjs runtime/loop/__tests__/recovery-apply-plan.test.mjs runtime/loop/__tests__/recovery-executor.test.mjs` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `runtime/loop/lm_loop_run.py; runtime/loop/recovery-intent.mjs; runtime/loop/recovery-intent-record.mjs; runtime/loop/recovery-apply-plan.mjs; runtime/loop/recovery-executor.mjs` の `_enqueue_recovery_intent(...); buildRecoveryIntent(input); buildRecoveryIntentRecord(...); buildRecoveryApplyPlan(...); executeRecoveryPlan(...)` を変更: _enqueue_recovery_intentとbuildRecoveryIntentRecordでDS10のtrusted storage_failure/proof_refを落とさず渡す。新actionを追加せず、確定pre-effectは既存action=reconcile_owner、reason=storage_write_failed_pre_effectで既存queue/cursorに接続する。next_action=retry_after_cleanupは診断値だけ。buildRecoveryApplyPlan/executeRecoveryPlanで同owner/occurrence/release/proofとfailure後のfresh cleanupを確認し、実operationのwrite確認が通る時だけ既存reconcileを一度実行する（2GiB unmetだけを禁止理由にしない）。cleanup lock取得・readback後、同一occurrenceの次wakeを再開。effect_unknownは既存official readback reconciliationへ渡し、自動fence解除/再submitはしない。新しいqueue/cronを作らない。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS11行で更新する。

**Done:** 容量復旧後の同仕事処理1回、receipt確認済み仕事再送0。未知effect/foreign owner/古いcleanupはhold。supervisor→buildRecoveryApplyPlan→executorのcaller-level fixtureまで通す。新action未定義による拒否0。retry backoff有限、他owner動作不変更。

### Task 12: DS12 — test_same_work_survives_storage_pressure_and_recovers()

**Files:** runtime/host/tests/test_storage_recurrence.py  
**Test:** runtime/host/tests/test_storage_recurrence.py  
**Depends:** DS07, DS08, DS09, DS11  
**Interfaces:** Consumes=既存contractと上記依存の出力。Produces=`test_same_work_survives_storage_pressure_and_recovers()`。receiptへ最低限owner_id/run_id/occurrence_id/release_sha/phase/error_class/retryable/next_action/evidence_refsを保持（DS03 metadata値のみはnull許可）。

- [ ] Step 1: 指名testに次のassertionを追加: retained bytes上限維持、protected_deletions0、accepted仕事欠落0、同effect重複0、result/usage互換。外部/保護データが増えた場合はunknown/unmetとし、回復したことにしない。
- [ ] Step 2: `python3 -m pytest runtime/host/tests/test_storage_recurrence.py` を実行し、未実装の振る舞いでREDを確認する。
- [ ] Step 3: `runtime/host/tests/test_storage_recurrence.py` の `test_same_work_survives_storage_pressure_and_recovers()` を変更: 隔離fixtureでログburst、同時writer、GC、実書込み失敗注入、次wake、detach writerを組み合わせる。host diskを埋める検証や本番processの停止は行わない。共有storage helperを新旧harnessのadapter fixture双方から呼ぶ。
- [ ] Step 4: 同commandでGREENと既存focused testsの互換を確認する。
- [ ] Step 5: source境界/diffを確認し、担当filesだけcommit/push。状態は統一SSOTのDS12行で更新する。

**Done:** retained bytes上限維持、protected_deletions0、accepted仕事欠落0、同effect重複0、result/usage互換。外部/保護データが増えた場合はunknown/unmetとし、回復したことにしない。

### Task 13: DS13 — shared storage integration contract

**Files:** skills/self/disk-cleanup/SKILL.md; docs/superpowers/plans/2026-10-09-openclaw-remaining.md; docs/research/openclaw-remaining-atoms.json  
**Test:** 既存DS tests + remaining dependency graph validator  
**Depends:** DS12  
**Interfaces:** 消費=依存atomの検証証拠。生成=対象JSON/文書（source/main/release/owner coverage/window/verdict/evidence_refs/remainingを記録）。新規実装関数ではない。

- [ ] Step 1: skill/remaining plan/manifestのsource-contract記述を同じ差分で更新する。
- [ ] Step 2: 全DS/OC IDs・先行DS17・依存参照・循環なし・catalog coverageをJSONで検証する。
- [ ] Step 3: runtimeコードを変更していないこと、未実装を実装済みと書いていないことをdiffで確認する。
- [ ] Step 4: docsだけcommit/push。

**Done:** OpenClaw残233atomとsource型/field/dependency一致。storage workを先頭に置いても循環0、全catalog coverage維持。


### Task 14: DS14 — source/PR/main acceptanceを記録する

**Files:** docs/evidence/storage-foundation/source-acceptance.json  
**Test:** 関連DS suite、既存loop contract、source/OSS、必要CI  
**Depends:** DS13  
**Interfaces:** 消費=依存atomの検証証拠。生成=対象JSON/文書（source/main/release/owner coverage/window/verdict/evidence_refs/remainingを記録）。新規実装関数ではない。

- [ ] Step 1: `python3 -m pytest runtime/loop/tests/test_loop_cleanup.py runtime/loop/tests/test_lm_loop_run_bounds.py runtime/loop/tests/test_lm_loop_health.py runtime/loop/tests/test_health_observer.py runtime/host/tests/test_storage_policy.py runtime/host/tests/test_bounded_output.py runtime/host/tests/test_storage_recurrence.py runtime/loop/tests/test_storage_failure.py runtime/agent-runner/tests/test_storage_failure.py runtime/agent-runner/tests/test_bounded_provider_output.py skills/self/disk-cleanup/tests/test_host_inventory.py skills/self/disk-cleanup/tests/test_disk_cleanup.py` を実行し全PASS。
- [ ] Step 2: `./bin/lm-loop-contract`、`bash scripts/verify-source-boundary.sh`、`node scripts/verify-oss-self-contained.mjs`、diff checkをPASS。
- [ ] Step 3: read-only reviewの重要指摘を最小RED→GREENで修正し、branch push/PR exact-head CIをPASS。
- [ ] Step 4: main統合のSHA/source acceptanceをsource-acceptance.jsonへ保存。本番release作成はまだ実行しない。

**Done:** source/integration/CIのexact SHA一致、担当外diff0、未達source taskをPASSにしない。


### Task 15: DS15 — immutable releaseとowner限定反映を記録する

**Files:** docs/evidence/storage-foundation/owner-apply.json  
**Test:** 隔離apply-lock/loaded-idle regression +自然readback  
**Depends:** DS14  
**Interfaces:** 消費=依存atomの検証証拠。生成=対象JSON/文書（source/main/release/owner coverage/window/verdict/evidence_refs/remainingを記録）。新規実装関数ではない。

- [ ] Step 1: mainの固定SHAを指定し、既存bin/cut-loop-release.shで完全immutable releaseを作る。これは事前GC/通常current切替を含む本番promotionとして宣言して実施し、保護/owner契約を確認する。source fixtureのreleaseはLOOPS_ROOT=<private fixture>へ作り本番を変更しない。manifest/SHAをreadbackする。
- [ ] Step 2: id/Directory Services/Aqua/manager UID/PID・GUI readbackを確認する。どれか不成立ならgui probe/mutationは発行しない。
- [ ] Step 3: `owner_deploy_lock(owner_id)`を保持し、effect readbackとloaded-idle/queue/reservation/未知effectを照合する。busy対象は不変更で次ownerへ。
- [ ] Step 4: 対象を宣言し、`LIFE_MANAGER_APPLY_TARGET=<owner_id> LIFE_MANAGER_RELEASE_ROOT=<verified immutable release> <verified immutable release>/bin/lm-loop apply --loaded-idle-only`を既存launchctl-safe経由で実行する。raw launchctl/基盤restart/稼働jobの停止はしない。
- [ ] Step 5: 対象のloaded argv/SHAと次の自然runを確認しowner-apply.jsonへ保存。他ownerは変更しない。

**Done:** 対象loaded argv/SHA、run中断0、other owner不変更、保護削除0。全該当ownerの新wake経路が適用済みになるまでfleet完了としない。


### Task 16: DS16 — 自然24hの翌日継続性を記録する

**Files:** docs/evidence/storage-foundation/next-day-acceptance.json  
**Test:** 自然cleanup receipt/owner runtime/公式成果readback  
**Depends:** DS15  
**Interfaces:** 消費=依存atomの検証証拠。生成=対象JSON/文書（source/main/release/owner coverage/window/verdict/evidence_refs/remainingを記録）。新規実装関数ではない。

- [ ] Step 1: DS15後の24h windowを固定し、自然cleanup/growth snapshot/予定された仕事のowner+occurrence+releaseを照合する。
- [ ] Step 2: 投稿・納品等の実際の公式結果とreplay-zeroを確認する。読取以外の再送で証拠を作らない。
- [ ] Step 3: management budget超過/ENOSPC/予定仕事の欠落があれば失敗境界へ戻す。容量理由pendingの仕事を翌日成功に数えない。
- [ ] Step 4: 確認window、結果、未測定領域をnext-day-acceptance.jsonへ記録する。

**Done:** 管理下出力はpolicy内、回復未達に診断と次action、scheduled仕事は完了または理由付きpending、欠落/重複0。未測定外部writerを安定化済みとしない。


### Task 17: DS17 — 全成果を照合してDS完了を記録する

**Files:** docs/evidence/storage-foundation/final.json  
**Test:** DS01–16証拠照合 + OpenClaw実行cursor確認  
**Depends:** DS16  
**Interfaces:** 消費=依存atomの検証証拠。生成=対象JSON/文書（source/main/release/owner coverage/window/verdict/evidence_refs/remainingを記録）。新規実装関数ではない。

- [ ] Step 1: DS01–16のsource/main/release/owner coverage/自然公式結果/protected dataを照合する。
- [ ] Step 2: 予定仕事が容量理由で止まる再発や回復未達に安全な次手がない場合は、具体的root/bytes/rateと未完taskを記録しDSを閉じない。
- [ ] Step 3: 全DS達成時だけfinal.jsonと統一SSOTを更新し、OpenClaw内cursor OC012を再開する。

**Done:** 全DS成果一致、既存仕事中断0、既存業務の公式結果保持。自然再発が残るならDSを閉じない。

## 実行順の変更

旧=OC012→OpenClaw残233atom。新=DS01→DS02→DS03→DS04→DS05→DS06→DS07→DS08→DS09→DS10→DS11→DS12→DS13→DS14→DS15→DS16→DS17→OC012→既存233atom。理由=liveで回復未達を確認し、userが共通storage予防を先行するよう指定したため。既存業務effectを中断/重複させず、進行中の仕事は旧releaseのまま完走させる。

## 自己レビュー

17atomのfile/symbol/test/dependencyを明示。既存5分/15日dispatcher/queue/sessionを重複作成しない。active/protectedの削除・固定容量による全停止・個人store変更を含めない。容量増加が管理外または保持必須データによる場合を未解決として残す。自然24hは翌日の継続性という要求の証拠であり、永久無障害の保証にしない。

## 計画reviewで訂正した点

- 実在するtest_loop_cleanup/test_lm_loop_health/test_lm_loop_run_boundsを再利用。DS02の実CLI callerも変更対象に追加。
- DS13–17は文書/検証/運用手順で、疑似RED/GREENやJSON内の仮想関数を実装しない。
- shared storage error分類は一箇所。recovery chainは既存reconcile_owner actionへ接続し、proof/errno/operationをrunnerから落とさない。
- release cutは事前GCとcurrent切替を持つため、本番promotionへ分類。applyの正しいtargetは位置引数ではなくLIFE_MANAGER_APPLY_TARGET。
- control socket閉鎖でrelay inputを閉じず、先頭32KiBと末尾2048bytesを保持する。
