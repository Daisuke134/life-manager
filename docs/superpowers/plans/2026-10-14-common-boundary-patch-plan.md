# 共通実行・監視・結果照合の差分計画

> 実装時は `superpowers:executing-plans`。今回は診断、差分案、spec更新だけ。patchは適用せず、本番の設定・state・release・fence・providerを変更しない。

**目的:** 既存PA01/PA02について、確認した失敗境界、必要な差分、実装する順と条件を確定する。

**正本:** `../specs/2026-09-25-life-manager-unified-ssot.md` の「共通境界のpatch-level診断」。CB01–CB06の順序/status/cursorはspecだけに置く。このplanは手順と差分の参照。

**固定したsource:** `7018416d03a7755766df1e115e019c6f1da5c49a`。local `main`や共有rootのHEADを使わない。適用者は最新origin/mainでpatch checkと関連検証を再実行し、関係する実装が変われば差分案を更新する。別ownerの進行を巻き戻さない。

**構成:** 既存release builder、resource admission、health CLI/observer、provider-owned fence adapterを使う。新scheduler・新cache・provider・model・walletを追加しない。healthの30秒、observerの180秒、fence guardを維持する。

## 確認した入口と最初の失敗

| 対象 | 実際の経路 | 確認した失敗 / 残る不明 |
|---|---|---|
| release採用 | `reconcile-agent-runner-release.sh` → `$CURRENT/bin/cut-loop-release.sh` → current版`disk_admission.release_capacity_bytes` | current5b90は新toolchainからbundle keyを再計算して正しい既存bundleを拒否。main701は同じ入力で必要容量を返す |
| 失敗理由 | `disk_admission.main --release-capacity` → exception handler | ValueErrorの種類を捨てるため、原因が`release_capacity_measurement_failed`に潰れる |
| health取得 | `health_observer.load_health_snapshot` → `lm_loop.main health` → `snapshot/collect_live` | 全191のsnapshot timeoutとprojection timeoutが別の窓で発生。どの自然runで30秒を使うかは未確定 |
| health診断保存 | child stderr → `subprocess.run(capture_output=True)` → observer | rc0/1時にstderrを捨てる。子へ診断を足すだけでは自然runの証拠が残らない |
| 旧effect | admission claim → entrypoint → stdout/runtime binding → official receipt | Coconalaの旧2件はpre-effect terminalなし。Storefront adapterはbinding invalid、reply adapterはofficial receipt unavailable。現時点で解除できる根拠なし |
| recovery | old intent → supervisor/current-release check | `release_sha_mismatch`は正しい拒否。source patchで比較を緩和しない |

容量probeの同一入力は、repo `/Users/anicca/Projects/life-manager-main`、source SHA701、donor `20261013T150253-5b90b21e`、Python3.14.7、node`v25.6.1`、npm`11.9.0`、Darwin/arm64。loaded helperは`dependency bundle unavailable`、main helperは`2,398,003,200 bytes`。live RRCのargvも5b90を確認し、toolchain overrideはplistにない。観測時の空き`1,089,990,656 bytes`は不足する。計算の復旧と容量の回復を混同しない。

反復stderrの正本は `~/.local/state/life-manager/release-reconciler/logs/bounded/launchd-life-manager-release-reconciler.err.log`。read-only検証でcapacity failure327/ValueError323を観測した。別の`launchd.err.log`の件数で代用しない。

## CB01 — main済みbundle修正を採用する

**source再実装は不要。** 修正は`03df6ebe10`等としてmain済み。参照差分は `../patches/2026-10-14-common-boundary/R01-already-merged-bundle-reuse.patch`。`dependency_bundle_is_reusable`は既存のcomplete・read-only・共有root内bundleを検証し、`release_capacity_bytes`は現在のnode/npmから別keyを作って拒否しない。

**既存検証:** `runtime/host/tests/test_disk_admission.py::test_release_capacity_reuses_locked_bundle_for_script_and_toolchain_change`。依存/lock変更・不完全bundle・非immutable donorの拒否は保持する。今回のlive read-only比較は新install0、新bundle0、provider call0。

**反映経路:** currentの旧cutterを繰り返すと同じ失敗になる。既存release ownerが修復済みconstruction toolから一度ALLを作り、以後の自然RRCが新currentのcutterを使う。

1. owner/leaseと稼働中のcut/applyを確認する。lockファイルの存在をlock保持と扱わず、他ownerを止めない。通常のowner lockを取れなければ待機する。
2. construction直前にRRCのpromotion-hold契約を読み戻す。active hold、またはexpiredでterminal promotion ledgerがないholdではactivationしない。holdを消したり期限だけで無視しない。
3. construction候補は `/Users/anicca/loops/releases/20261013T214452-9336980a`。main祖先、mode0555、cutter/disk helperの承認sourceとのhash一致、4 module importを確認する。これはSPARSEで、候補自身をcurrentへ設定したり全jobへapplyしたりしない。
4. 必要容量とfreeを同じfilesystemで再測定する。未PASSなら既存F5/cleanup ownerの安全回収とreceiptを待つ。floor変更・protected store削除・budget overrideをしない。
5. 現在のapproved origin/main SHAを固定し、下の既存cutter入口でALLをinactiveのまま作る。construction中に新しいholdが入る可能性があるため、ここで自動activationしない。
6. 出力は`release -> ABS_PATH (ancestor-of-origin-main; current unchanged)`。そのABS_PATHのdescriptorがapproved SHA/ALL/main祖先/mode0555であることを確認し、`LM_CB_DEST`へ設定する。
7. 実際のguard writerの`--ledger/LM_DEV_GUARD_LEDGER/deps.lockPath`をownerが読み戻し、単一のguard lockへの協調を確認する。既定ledgerは`/Users/anicca/.life-manager/state/dev-guard-runs.jsonl`だが、overrideを調べず既定を当てはめない。異なるlockへのwriterがあればactivationしない。
8. 下のactivation referenceは同じguard lockへ完全なPID/timestamp metadataをatomic linkでpublishし、cut lock→protocol/apply lockの既存順を守る。空のguard lockを先に公開するとlegacy readerが壊れたlockとして回収できるため、その窓も作らない。ageだけで既存lockを回収する`acquireGuardLock`を使わず、存在するlockは保持して待機する。holdがあればownerの解決を待つ。Python activationは30秒上限、自分のPID/inodeのlockだけを解放する。moduleは完成ALLから読む。
9. 成功後にcurrentのexact path/SHAと既存RRCのloaded-idle/self-handoff経路、自然capacity測定/fleet進行/loaded argvを確認する。timeout/例外時はcurrentをread-onlyで照合し、不明な切替を成功/未実行へ置換したりblind rollbackしたりしない。旧effect-unknown/running ownerは保持する。

実行時の既存入口（今回は実行しない）:

```bash
LM_CB_REPO=/Users/anicca/Projects/life-manager-main
LM_CB_BOOTSTRAP=/Users/anicca/loops/releases/20261013T214452-9336980a
LM_CB_SHA=$(git -C "$LM_CB_REPO" rev-parse origin/main)
# 上のowner/hold/immutable/hash/import/capacityがPASSした時だけ実行する。
LIFE_MANAGER_SOURCE_REPO="$LM_CB_REPO" LOOPS_ROOT=/Users/anicca/loops \
  LOOPS_RELEASE_PATHS= LOOPS_ACTIVATE_CURRENT=0 \
  bash "$LM_CB_BOOTSTRAP/bin/cut-loop-release.sh" "$LM_CB_SHA"
```

activationのexact referenceは `../patches/2026-10-14-common-boundary/CB01-activate-verified-release.cjs`。これはone-time operation案であり、今回実行しない。plan/patchをmainへ統合した後の完成ALLに含まれるscriptを使い、worktreeやSPARSEからruntime moduleをimportしない。`LM_CB_DEST`は上の実出力/descriptor、`LM_CB_GUARD_LEDGER`は上のlive writer readbackで確認したpathである。

```bash
# owner/hold/ledger override一致/descriptorを確認後に、宣言して実行する。
node "$LM_CB_DEST/docs/superpowers/patches/2026-10-14-common-boundary/CB01-activate-verified-release.cjs" \
  "$LM_CB_DEST" "$LM_CB_REPO" "$LM_CB_SHA" "$LM_CB_GUARD_LEDGER"
```

wrapperはguard→cut directory→既存`activate_current`のprotocol/apply順。同じguard lockを守る通常writerが対象で、未知の非協調writerまで絶対排他を保証しない。現在のconfigurationが一致しなければ運用preflight未PASSとして保持する。syntax checkと、実FS/execを置換した隔離4ケース（成功、guard busy、hold present、cut busy）を確認した。本番のactivationやlock取得は行っていない。

Doneは容量計算だけでなく、完全release/current/対象loaded argvとRRCの自然進行。全18の利益や全fleet完了とは呼ばない。

## CB02 — 容量エラーの理由を残す

**適用案:** `../patches/2026-10-14-common-boundary/D01-release-measurement-reason.patch`。

**変更箇所:** `runtime/host/disk_admission.py::main`の`--release-capacity`例外処理。既存`reason/error_class/exit1/stdout空`を保持し、known errorから`measurement_reason`だけを追加する。文字列の例外全体は出さない。

| 既知の例外 | 新しい固定値 |
|---|---|
| donor is not a complete immutable runtime | donor_runtime_invalid |
| dependency manifests changed | dependency_manifest_changed |
| dependency bundle unavailable | dependency_bundle_unavailable |
| filesystem allocation unknown | filesystem_allocation_unknown |
| Git export measurement failed | git_export_measurement_failed |
| その他 | unclassified |

**RED/GREEN:** 同じ既存test fileへ`test_release_capacity_error_reports_safe_measurement_reason`。既知bundle失敗と、未分類の秘密に似たfixture文字列の2ケース。後者のraw文字列は出力しない。実装時は `python3 -m pytest runtime/host/tests/test_disk_admission.py -k 'measurement_reason or measurement_failure'`。今回の隔離probeはbaseline0/2、差分案2/2。これは診断の検証で、容量確保ではない。

## CB03 — healthの失敗phaseを子側で残す

**適用案:** `../patches/2026-10-14-common-boundary/M01-health-read-diagnostics.patch`。

**変更箇所:** `runtime/loop/health.py`に固定schemaのsanitizer、`lm_loop.collect_live/snapshot/main`にread-only stage callbackと診断出力。snapshot/collect_liveの新引数は`stage_observer=None`、callback契約は`(stage: str, loop_id: str | None) -> None`。

固定stageは`runtime_snapshot/admission_fences/resolved_receipts/launchd_list/launchd_disabled/runtime_journal/status_projection/storage_snapshot/health_projection`。親だけのtimeoutで子markerがない時は`health_subprocess`を使い、子がどこへ進んだか推測しない。journalsでは現在読んでいるregistry loop IDをmemory内で更新する。stderrへ出すのは外側3phaseの開始と最後のcomplete/timeout/errorで、jobごとに大量のlogを出さない。

診断schemaは`lm-loop.health-read-diagnostic.v1`。保持するフィールドは`schema_version/source/event/stage/loop_id/elapsed_seconds/budget_seconds`だけ。sourceは`health_cli/observer_subprocess`、eventは`start/timeout/complete/error`。stage enum、既知loop IDまたはnull、有限で非負のelapsed、有限で正のbudgetを検証し、bool/raw exception/env/stdout bodyを受け入れない。

snapshot SIGALRM外のstorage readにも開始markerを出し、projectionの残予算切れでもtimeoutを出す。既存stdoutの`lm-loop.health.v1`、summary/facets、30秒deadline、partial projectionの扱いは変えない。timeoutをextendしたりfenceを解放したりしない。

**RED/GREEN:** `test_lm_loop_health.py`へ`test_health_snapshot_timeout_reports_exact_read_stage`と`test_storage_time_consumption_reports_projection_timeout`。前者はruntime_journalで止まったloop ID、後者はstorageが31秒を消費した時のprojection timeoutを確認する。新testはbaselineで失敗、差分案で成功。既存deadline/remaining budget testも通す。

## CB04 — 自然observer経路で診断を保存する

**CB03の後に適用:** `../patches/2026-10-14-common-boundary/M02-observer-diagnostic-forwarding.patch`。

**変更箇所:** `runtime/loop/health_observer.py::load_health_snapshot`と`_forward_health_read_diagnostics`。正常/failed health documentのvalidation後、doc中のjob IDsを許可集合にしてsanitizerを使う。stderrの末尾4096文字を読み、1行1024文字以下、最大4件だけを既存親stderrへ転送する。raw stderrと追加secretフィールドは出さない。親timeout時は転送に加え親の診断1件があり、出力も最大5件に制限される。

`subprocess.TimeoutExpired`でも検証済みの外側開始markerを転送する。markerがなければ固定`health_subprocess/loop_id=null`を記録する。親command timeoutは`source=observer_subprocess`でconfigured budget180と親monotonicの実測elapsedを別々に記録し、子の30秒budgetと混同しない。stdoutがない場合はloop ID=nullのmarkerだけを受ける。元のTimeoutExpiredは再送出し、成功に変換しない。

**RED/GREEN:** `test_health_observer.py`へ`test_snapshot_loader_keeps_only_valid_bounded_read_diagnostics`、`test_snapshot_loader_preserves_stage_when_child_times_out`、`test_parent_timeout_without_marker_is_still_diagnosed`。未知stage/NaN/bool/浮動小数で表せない整数/raw文字列を排除し、4件転送上限、doc不変、親timeoutのstage/実測elapsedを検証する。None/raw-only stderrも独立入力にする。有限で表現できる数値に新しい上限は追加しない。既存read-only CLI入口testを通す。

**実装時検証:** `python3 -m unittest runtime.loop.tests.test_lm_loop_health runtime.loop.tests.test_health_observer`。今回の隔離probeはCB03/04合計5 test methods（6入力ケース）、baseline6 failures/errors0、差分案5 methods PASS、既存安全契約3件PASS。適用可能性は`git apply --check`で確認した。実際のworktree/source/mainに適用した結果や自然runの証明ではない。

## CB05 — 出たphaseから一つだけ性能原因を狭める

性能修復のsource diffは、自然runの診断と同じ入力の再現が揃うまで作らない。現在のread-only profileはsnapshot8.719秒、admission0.167秒、resolved receipts1.324秒、collect_live7.059秒、_last_event6.677秒。99 journalsの合計495,050,333 bytes。これは成功窓であり30秒超過原因の確定ではない。

| 診断stage | 次の限定probe | 修復の開始条件 |
|---|---|---|
| admission_fences | 同じRO SQLの所要時間・BUSY/LOCKED・EXPLAIN QUERY PLAN | 読取/lockのどちらが予算を使うか再現。retryを増やさない |
| resolved_receipts | `_last_adapter_calls`を当該ledgerでprofileし、latest proof集合を固定fixture化 | 重複decode等を再現し、全履歴を捨てず同じclosure判定を保持できること |
| launchd_list/disabled | exact safe preflightと同じread commandのexit/time | owner/Aqua/GUI状態を確定。141/153 retry・基盤restartなし |
| runtime_journal | 記録loopのplist state_root/inode/bytesと`_last_event/_health_event_projection`をprofile | first slow read/decodeを同じwindowで再現。任意のtail切捨てや新cacheを先に入れない |
| status_projection | `_latest_harness_failure/status_rows`の回数・所要時間 | 同一journal再読等の実反例を確認。stale/unknownをhealthyへ変換しない |
| storage_snapshot | `read_storage_snapshot`の実path・read/validation時間 | どのreceipt/ファイルが遅いか確定。free/capacityを0やPASSへ置換しない |
| health_projection | `project_health`の残予算と該当adapter時間 | clock/adapter/全体予算のどの境界か再現。partial情報とstdout契約を保持 |

最初の失敗を再現する最小test→当該functionの最小差分→同じtest/自然診断の順。CB03/04の診断PASSを性能修復PASSとは呼ばない。

## CB06 — 旧effectを正確な証拠で照合する

CB05と独立。現時点でgenericな解除patchは作らない。fence数の増減だけを公式解決と扱わない。

| owner / occurrence | 確認した境界 | 次に必要な証拠 |
|---|---|---|
| hf-gig-apply-direct / 18dadcd76d9c61b0-37711 | RO max_rows1でno_pre_effect_terminal | 同じ提出のofficial application ID/受付結果、または同じclaimed runの完全なno-effect証拠 |
| hf-gig-storefront-direct / 18d8d288748508e8-23902 | 同probeでno_pre_effect_terminal、adapterはstdout_runtime_binding_invalid | 同じruntime bindingと公式listing ID/version/更新結果 |
| hf-gig-reply-detector / 18dde86cdb81d360-30574 | adapterはofficial_provider_receipt_unavailable | 同じ送信のofficial message IDとreadback |
| Mobileの旧publication | adapterはidentity_missing_or_invalid | 同じtenant/product/integration/slotとpost IDのreceipt |

各ownerは既存`lm-loop status JOB --explain`とregistered adapterのreadbackで、過去claim→実行run→provider結果を結ぶ。entrypointのexitだけを未送信証明にしない。provider調査には既存credential SSOT/session/leaseを使い、browser・所有者を奪わない。

no-effectが同一occurrenceで証明された時だけ既存pre-effect resolver、実effectが公式receiptで証明された時だけ既存unknown resolverを使う。proof取得前の解除・再送0を維持する。adapterが既存の正しいproofを誤拒否したと再現できた場合だけ、そのparserの最小REDと差分を追加する。証拠欠落を新adapterの推測で埋めない。

## 成果物と実装前の判定

`docs/evidence/common-boundary-probe-20261014.json`は隔離検証の結果。R01はmainに存在する既存差分でreverse checkがPASS。D01/M01/M02はproposed diffでapply checkがPASS、product sourceへの適用0。差分を作ったsource SHA・function・test・実行条件・自然受入をspecへ残す。

順序はspecのCB表だけ。CB01の必要容量不足、CB05の30秒超過原因、CB06のprovider proofは具体的な残条件であり、実装済み/復旧済み/売上達成にはしない。
