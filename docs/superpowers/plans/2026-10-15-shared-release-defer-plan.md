# 共有releaseの延期分類 — 差分契約

TODO・順序・状態 → docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md「共有releaseの安全な延期を未完・再試行として保存する」。

目的は、control.lock競合とcurrent置換を安全な未完のtickとして扱い、実適用失敗を隠さず、延期ownerを次回確認へ残すこと。既存controllerの仕組みを使い、新queue、daemon、retry engine、frameworkを作らない。

## 差分対象

`bin/reconcile-agent-runner-release.sh::run_fleet_apply`:

1. 前回stateのcontrol_busy_continueをbooleanとして読む。新SHAのcoalescingは既存budget/supersededと同様に、その延期期限だけを尊重する。
2. rc1かつexact JSON `{"ok":false,"error":"admission rebind refused: control_busy"}` に限定してownerをskipする。元rc1をowner logへ残し、reasonはadmission-control-busy。文字列一致や余分なfieldを許容しない。他ownerへ進む。
3. busy ownerが残るtickをpartialにする。errors0、timeoutなしの場合だけcontrol_busy_continue=true、既存LIFE_MANAGER_FLEET_APPLY_CONTINUE_SECONDSを再確認期限に使い、last_ok_epochを更新しない。budget partialにもこの条件を適用する。実エラーとの混在はcontinue=false/非0を保つ。
4. partialの終了判定は、正常budget、正常busy、別の妥当な40桁SHAを観測したsupersededに限り0。errors>0、timeout、欠測/不正currentは非0。supersededでも残りの旧SHA ownerは開始しない。
5. 親がこの関数を`||`で呼ぶため、errexitを失敗伝播に使わない。必須のoutput/plan/tempfile生成、owner journalとstateのPython writer、owner出力保存へ明示`|| return 1`を付ける。registryの欠測/不正を空台帳へ置換せず、plan生成失敗として伝える。書込失敗の後に延期成功判定へ抜けない。新しい保存方式やrollbackを作らない。

`runtime/loop/tests/test_reconcile_agent_runner_release_fleet_apply.py`:

- 既存fake applyにbusy/類似/compound/混在の入力を足す。既存temporary bare repo、fake CLIを再利用し、本番admission/launchd/providerに触れない。
- busyの最初のtickはpartial/skip/retry、次回正常applyでokになることを確認する。新SHAにも保存済み短いretry期限が使われることを確認する。
- lookalike/compound/混在は失敗を保つ。
- stateのatomic一時path/owner journal pathをfixture内のdirectoryにして書込失敗を再現し、非0を要求する。current-skip journalとplan生成失敗も、owner開始や適用済み記録へ進まないことを確認する。
- 既存superseded 2件のexpected tick exitを0に変更し、state partial/旧owner未開始/次current適用のassertionを保つ。実エラーが先行する場合とcurrent SHAが不正の場合は非0を確認する。

## 保持する境界

control.lock取得失敗ではrebind transactionが始まらない。lock、queued occurrence、FIFO identity、effect fenceを変更・解除しない。既存loaded-idle/current guardを変えない。parent reconcile、provision、self-handoff、timeout runnerの失敗は全体の非0を維持する。

対象fleet suiteとbash syntax/diffを確認し、独立fresh read-only検証を行う。CI/main後は完全immutable releaseと対象RRCの既存self-handoffを使う。自然実行が該当境界を越えた結果を記録し、収益成功や全18完了へ読み替えない。
