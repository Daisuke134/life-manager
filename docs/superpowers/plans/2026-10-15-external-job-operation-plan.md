# 外部の実運用方式を既存Life Managerへ適用する差分計画

> 実装担当はsuperpowers:executing-plansを使う。今回の成果は調査・仕様・差分手順。順序/status/cursorは統合specだけに置く。

> 実行開始: → spec「R1の実行範囲」。下の文書作成時のno-action記録を実装停止の条件へ使わない。

**Goal:** 永続キュー・空き実行枠・仕事単位の復旧を使い、現在の停止境界を閉じて次の収益仕事へ進む。連続成功回数で完了を待たない。
**Architecture:** nativeのqueue/lease/heartbeat/finite child/中央cleanupを再利用し、外部の負荷制御と再送設計へ対応付ける。CloudのInngestは既存の役割を保ち、Mac18業務の移植をこの修復の前提にしない。
**Tech Stack:** 既存Python/Bash/Nodeと既存test。新server、model API、scheduler、会計ledgerを増やさない。
**Spec:** ../specs/2026-09-25-life-manager-unified-ssot.md「外部の実運用方式へ揃える」。source605177d47acdb77ded7c130f3d5d1cdeb46576b2。実装時は最新mainの同関数を比較する。

## Global Constraints

- 連続N回と全F合格待ちを撤回。未完の個別故障を完了扱いにはしない。
- 既存owner/lease/operation identityを保つ。結果不明の再送やreceiptの推測はしない。
- 既済sourceを作り直さない。関連回帰で足りる時は新testを追加しない。
- RAM/diskのソフト予算をOS強制quotaと称さず、枠管理外のwriterを別に観測する。
- 今回は文書だけで、runtime/provider/install/auth/applyは実行しない。

## Review Focus

1. 枠待ちのjobがworkerを占有する — queue/claimの区別をTask Bで確認。
2. 終了済みjobのunknownが他ownerを止める — resource返却とeffect保持をTask Bで確認。
3. 子processまたは自分の一時物が残る — 所有範囲の終了/清掃をTask Cで確認。
4. providerが再送のidempotencyを保証しない — 公式結果を先に読むTask D。
5. DB読取失敗を空の正常状態へ置換する — 既存typed errorをTask A/Bで維持。

## 根拠の対応

- Google SRE: https://sre.google/sre-book/handling-overload/
- Temporal Task Queues: https://docs.temporal.io/task-queue
- Inngest concurrency: https://www.inngest.com/docs/durable-execution/flow-control/concurrency
- Amazon idempotent APIs: https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/

ここで採用するのは各一次資料に説明された運用方式。新しいdaemonの導入済み、Mac上のhard quota、すべての外部操作のexactly-onceは主張しない。

### Task A — 回数と全体停止の条件を文書から外す

**Files:** 統合specのF4/F5・共有再開条件・最新cursor、既存ordered/common-boundary/readme-meta plan。
**Interface:** 選択laneの現在の停止境界→該当修復→仕事の進行。全Fのstatusを一括判定へ使わない。

- [ ] activeな「連続N回」「全F PASSまで全業務待機」を撤回する。過去の観測は履歴として区別する。
- [ ] 旧順/新順/理由/current cursorを同じspec差分へ書く。
- [ ] 根拠URL、scope、source SHA、実装未着手を照合し、専用branchへ保存する。

### Task B — 現在止まる仕事をキュー・実行枠・外部待ちへ分ける

**Read/conditional modify:** runtime/host/resource_admission.py::enqueue_durable/claim_durable/heartbeat_durable/release_and_reserve、runtime/loop/lm_loop.py::_read_admission_rows。
**Interface:** owner_id/occurrence_id/resource_class/admission_class→queued/claim/release、既存effect_unknownは独立保持。
**Tests:** runtime/host/tests/test_resource_admission.py、runtime/loop/tests/test_lm_loop_readonly.py（既存の状態読取・admission error回帰）。

- [ ] 最初に共有制御/cleanup/releaseの対象status/loaded SHA/runを読み、現在のclaim・pending・unknown・直近terminalを分ける。
- [ ] worker停止/実待機なら実行枠を返す既存経路を確認する。provider結果を待つだけの状態とlive childを混同しない。
- [ ] 既存 `test_successful_release_does_not_clear_unknown_without_readback` を再利用。別ownerが進めない反例がある時だけ `test_released_unknown_does_not_consume_other_owner_slot` を同moduleへ追加し、RED後に最初の不成立関数だけ直す。
- [ ] Assert: 終了済みclaimの枠返却、元occurrenceのunknown保持、他の適格ownerのclaim成功、同effectの再送0。DB busyはtyped errorで、空のfleetではない。
- [ ] sourceが既に満たす場合はpatchなし。既存ownerの採用または対象のreadbackへ進む。

### Task C — 実writerの保存・終了・清掃だけを直す

**Read/conditional modify:** runtime/host/disk_admission.py::_producer_gate、runtime/loop/lm_loop_run.py::_run_entrypoint、runtime/loop/central_cleanup.py::scratch_gcと実測したproducer。
**Tests:** runtime/loop/tests/test_lm_loop_run_bounds.py、test_loop_scratch.py、test_loop_cleanup.py、runtime/host/tests/test_disk_admission.py。
**Interface:** owner/PID/run/path/bytes＋既存runtime limit→所有する子終了、正式出力とreceiptを保持し、回収可能な自分の一時物だけcleanup。

- [ ] writerと出力先を同じwindowで結び、枠管理外の子、無制限保存、正式出力/scratch混在のどれが実在するかを調べる。
- [ ] 再現した境界の既存testを使う。必要なREDだけ追加し、producerまたは共通入口の一箇所を直す。
- [ ] Assert: 自分の子を回収、別session/借用browserは保持、partial/active/unknownの証拠保持、正式商品とreceipt保持。未帰属のrootを推測で削除しない。
- [ ] 該当故障の修復と仕事の進行が確認できたら次へ進む。何回連続という待機はしない。既存監視は稼働後の異常を次の個別修復へ戻す。

### Task D — 対象jobの外部結果を閉じ、次の収益仕事へ進む

**Read/conditional modify:** 対象registryのeffect_reconcile、Capafy factory/distribution adapter、Gig application/reply/paid adapter。
**Interface:** 同occurrence/intent/hash/provider ID→official resultまたは未確認。リトライ可否はproviderの保証と既存fenceで決める。

- [ ] providerがidempotency keyを受ける場合だけ、同じoperation IDと同じpayloadで再送できる契約を使う。
- [ ] 未対応の公開/応募/納品は、公式結果を照合してから次actionへ。原因未確定の比較緩和はしない。
- [ ] 業務の進行・購入・入金・利益を別に記録する。故障が閉じた後に連続成功を集め直さず、共有修復が閉じた後、Capafy/Gigの次の仕事へ進む。

最小focused command例（実装修復時に対象caseだけ選ぶ）:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest runtime/host/tests/test_resource_admission.py -k successful_release_does_not_clear_unknown_without_readback
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest runtime/loop/tests/test_lm_loop_run_bounds.py -k 'timeout or cancel'
```

source変更時の通常のfocused検証/CI/main/対象反映は保持する。連続回数や無関係なlaneの完了を追加条件にしない。進行中の別owner・外部effectは保持する。
