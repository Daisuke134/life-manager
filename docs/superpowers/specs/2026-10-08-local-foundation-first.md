# 現行Life Managerの容量基盤を先に安定させる

目的:ハーネス移行の前に現行workerの不要なdisk/RAM増幅を減らし、既存業務を維持する。推論はChatGPT account接続Codexのまま。OpenClaw/Temporalの追加service設置や全owner restartは先に行わない。

実行順:
1. FD-01 `runtime/loop/lm_loop_run.py::_run_entrypoint_with_stderr_capture` の終了時全量read/replayをbounded化する。子stderrはregular fileのまま、pipeへ変えない。
2. FD-02 既存cleanup/retentionとowner別scratch/evidence増加量を基にproducerのdisk予算を必要箇所へ適用する。memory/state JSONL/credentials/browser/referenced releaseを削除しない。disk gateの閾値低下で解決扱いしない。
3. FD-03 whole job slotの長時間占有を短いmodel/browser/readback/build phaseへ分け、外部待機をcheckpoint化する。model終了確認まではclaimを解放しない。domain effect fenceは保持。
4. FD-04 軽い公式readbackをmodel waitingと別容量で進められるようにする。quota/browser identityの排他を維持し、単なるglobal8増加を最初の修正にしない。
5. FD-05 同じ既存業務の自然結果・queue wait・disk増加・重複/欠落・費用を確認する。実行数を売上へ置換しない。
6. FD-06 安定した基盤から既存OpenClaw移行を進める。長期workflowに必要ならTemporalの標準wait/activityを補完するが、今のsource修正へ新frameworkを抱き合わせない。

## FD-01 source acceptance

現在のhelperはchild stderrをreal fileへ保存し、終了時`read_bytes`で全量RAM化、同じ全量をlaunchd stderrへ再出力する。large stderrで無駄なRAMと二重log出力が増える。

変更は終了時のみ:通常64KiB以下は従来どおり全文replay。大きい場合は先頭32KiB＋固定truncation marker＋末尾32KiBだけreplay。diagnostic tailは末尾2048bytesを正確に保持。whole read_bytesを使わずseek/readのbounded I/O。child stderr fdはregular fileを維持し、detached childにSIGPIPE/EPIPEを起こすpipe、RLIMIT_FSIZE、signal、in-place truncateを追加しない。stdout/schema/exit/timeout/cancel/on_started/domain fence/元のworkerを変えない。

所有ファイルはruntime/loop/lm_loop_run.pyとruntime/loop/tests/test_lm_loop_run_bounds.py。既存testへsmall/large/bounded read/regular fd/exitと最終tail保持の最小回帰を追加しRED→GREEN。source/diff/必要既存contractsを確認し専用branch commit/push/PR/main。production反映はidle ownerとmain-derived release境界で実施し、稼働仕事を途中で止めない。

この一手は長い子process実行中のreal file増加やdetached子が保持するfd全体を解決するものではない。その対策を成功扱いせずFD-02へ残す。完了報告はsource proofとrelease/natural readbackを分ける。

## FD-01現在の確認

source/独立review/CI/main統合PASS、PR #7038。main SHA d1d5850630946bdb04818e62849f22af0e669379。main由来不変releaseをcurrent不変更で作成し、idle/pending無しのhealth observer一件だけ反映。自然run 18dc7136883a17c0-13707のreport pass/exit0を同SHAで確認。売買/応募owner変更0、manual provider action0。全owner展開と実行中captureの増加対策は未完。次のcursorはFD-02。[receipt](../../evidence/foundation-stderr/acceptance.json)。
