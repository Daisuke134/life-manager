# ローカルLife Managerのハーネス採用価値を判定する原子的計画

> 実行時は `superpowers:executing-plans`。今回の成果は仕様・計画まで。本番変更・有料比較の実行をこの文書作成で許可されたと扱わない。

**Goal:** 現行と同じ業務を保ち、OpenClawに実測便益がある場合だけ移行する。
**Architecture:** Life Manager CLIを維持する。finite engine比較を先に行い、Gateway/cron/session全面移管を現在の採用に含めない。
**Tech Stack:** 現行Python runner、pinned OpenClaw CLI、既存fixture/JSON証拠。
**Spec:** `docs/superpowers/specs/2026-10-07-main-agents-readiness.md`

制約と数値閾値はSpecのGo/No-Goを参照。レビュー重点は欠測の0化、失敗runの除外、別account/model比較、execのOTel誤認、業務receiptと会話stateの混同。

## MV-01 — 比較入力を固定する

- [ ] Create `docs/evidence/harness-migration/local-value-cases.json`。
- schema=`life-manager.harness-value-cases.v1`、10case×repetitions4、order=alternating、read_only_business=true。
- case ids: structured-result、existing-script-read、fixture-file-write、tool-error-recovery、long-context-task、provider-disconnect、deadline-expiry、process-interrupt、retained-state-contention、cleanup-failure。
- 各caseはprompt_sha256、fixture_ref、expected_result_ref、allowed_fixture_effects、forbidden_provider_effects、baseline_command_ref、candidate_command_refを固定。prompt/秘密情報本文をJSONへ入れない。
- account/model/tools/budgetの同一性証拠がないcaseはready=false。production mutationは禁止。fixture書き込みはowner専用private workspaceのみ。
- 完了: 10 unique id、全fixtureと期待結果refが存在し、real spend capとmodel/account同一性が確認できない比較は自動着手しない。

## MV-02 — 同じ入力の実行記録を保存する

- [ ] Create `docs/evidence/harness-migration/local-value-runs.json`。
- 入力: MV-01、既存runnerのattempts/summary、candidateのstdout envelope。active production ownerを止めたり同occurrenceを再送しない。
- 1 record: case_id、pair_id、repetition、engine、source_sha、package_integrity、model_ref、account_ref_hash、tool_contract_sha、budget_ref、started_at、elapsed_ms、result_pass、actual_cost、cost_basis、rss_peak_bytes、completed_jobs、recovery_ms、diagnosis_ms、duplicate_effect_count、missing_effect_count、receipt_join_missing_count、evidence_refs。
- secret/prompt/rawprovider応答を保存しない。不明値=null、失敗も残す。costのestimate/実請求を混ぜて勝者を決めない。
- 完了:40pair/80recordが同じinput/host/budget条件で揃うか、足りない証拠をmissingとして列挙。追加の有料APIやaccount方式への変更は既存spend-cap/認証契約の範囲外へ進めない。

## MV-03 — 判定の計算を固定する

- [ ] Create `scripts/compare-harness-runs.py` に `compare_runs(records: list[dict], limits: dict) -> dict` とJSON file入出力CLIを追加。provider/process起動やstate書き込みをしない。
- 出力はbaseline/candidate別sample counts、success_rate、同cost_basisのtotal_cost、p95_elapsed_ms、throughput、median recovery/diagnosis、全duplicate/missing/receipt gap、net_removed_production_loc、decision=go/no_go/incomplete、reason codes。
- percentileはsorted elapsedのnearest-rank ceil(0.95*n)-1。未知値やpair欠落でincomplete。成功runだけを選ばない。
- Test `scripts/tests/test_compare_harness_runs.py`: missing data→incomplete、same baseline→no_go、benefit20%かつ全nonregression→go、duplicate1→no_go、failure runがsuccess rate/p95/cost集計に含まれること、cost basis mismatch→incomplete。
- 完了: `python3 -m unittest discover -s scripts/tests -p test_compare_harness_runs.py` PASS。例の数値はfixtureで、本番改善値ではない。

## MV-04 — 採用判断を保存する

- [ ] Create `docs/evidence/harness-migration/local-value-decision.json`、統一SSOTの同lane cursorを更新する。
- 入力: MV-03出力、実際の保守code差分、既存15業務の未解決境界。
- Goの場合のみ便益が証明されたowner/taskにMX adapter/canaryを適用する候補として記録。No-Goなら現行継続、互換だけで採用しない。
- OTel観測性を理由にする場合はexecを採用入口にしない。pinned `agent --local`/Gatewayとdiagnostics-otelの別比較が必要で、既存cronを二重有効化しない。
- 完了:改善した要求と改善していない要求を分け、source/readback/費用未確認をPASSへ変換しない。
