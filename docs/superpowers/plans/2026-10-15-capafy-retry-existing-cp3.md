# Capafy retry_existing partial-effect recovery 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 各stepはcheckbox形式で進捗を記録する。

**Goal:** Capafyのretry_existing draftを同一Agent/versionのままCP3へ進め、部分effectをoccurrence-boundな公式receiptで照合する。

**Architecture:** 登録済みCapafy adapterはsame-version updated_atだけをclosure proofにしない。parent event、選択されたretry_existing ID、child summary、開始snapshot、公式readbackが一致した時だけ、platform_status=0のpackage-upload済み状態をeffectedとして閉じる。daily_loopのretry_existing_stub_finish()は同じmanifest/versionがremoteと一致しCP1/model confirmedの場合にpublish_finishを一度だけ呼び、既存daily_loop log contract（Agent/version行とSUBMITTED終端）を再利用する。既存child summary/parent eventがrun・occurrence・releaseを結ぶため、新しいreceipt formatは追加しない。失敗時はそのwakeを終了して重複submitを避ける。

**Tech Stack:** Bash、Python標準ライブラリ、既存pytest suite、Capafy publisher CLI。

**Spec:** docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md のCapafy current cursor。

## Global Constraints

- 最新origin/main由来worktree、専用branch、codex-root leaseを維持する。
- Agent ID/versionはinventory item、local publish manifest、official latest versionで完全一致させる。
- same-version updated_at単独ではeffectを帰属させず、証拠不一致はHELDにする。
- provider retry、draft削除、新Agent作成、counter reset、手動wakeは禁止する。
- CP3は既存publish_finish.shを使って一回だけ試し、失敗時に同じwakeで別経路へfallbackしない。
- effect_unknownはofficial Capafy API readbackとregistered adapterだけで解消し、no-effectへ偽装しない。

## Review Focus

- versionがsnapshot、manifest、official latest status間で変わる場合はsubmitしない。
- updated_atがoccurrence window外、欠落、複数same-version候補ならfenceを閉じない。
- child summaryのparent occurrence/run/releaseが一致しない場合はfenceを閉じない。
- pre-dispatch snapshotと現在のpublish-listのAgent ID集合、重複なし、agent_countが完全一致しなければpartial receiptを返さない。
- official statusがplatform_status=0でもCP1/config/uploadが全てconfirmedでない場合は決定的finishしない。
- publish_finishが非zero終了した後、同じwakeでCP3を再送しない。

---

### Task 1: 部分effectのoccurrence-bound reconciliation

**Files:**

- Modify: skills/self/capafy-loop/capafy_factory_fence_reconcile.py
- Test: skills/self/capafy-loop/test_capafy_factory_fence_reconcile.py

**Interfaces:**

- Add read_occurrence_bound_partial_effect_receipt(occurrence_id, queued_at, window_end, snapshot, agents, evidence_root=None, publisher_log=None, event_log=None) -> dict | None. It accepts exactly one failed parent terminal, one child summary bound to that parent/release, one daily_loop retry_existing action_key for the selected Agent ID, and a child result tied to the same run. It returns the selected Agent ID/version only when snapshot and official publish-list have the exact same Agent ID set/count/versions and the selected update timestamp is inside the run window.
- Reuse existing `read_occurrence_bound_cp3_receipt` for status=1 success. `daily_loop.sh` logs one `AGENT_ID=`, `AGENT_VERSION_ID=`, CP3 attempt output, and the existing SUBMITTED terminal; child summary and parent event bind that block to the run/occurrence/release.
- Extend read_remote_status(agent_id) to retain platform_status, agent_version_id, audit_status, is_confirmed_skills, is_confirmed_config_keys, and package_uploaded.
- reconcile calls the partial receipt path only when find_hit reports same_version_updated_after_queued_at. It then requires official remote status to match the returned Agent/version and show platform_status=0 plus both confirmation flags and package_uploaded=true. Timestamp alone must continue returning ambiguous_provider_readback.

- [x] RED: test_same_version_update_without_bound_retry_evidence_stays_held。snapshotとlive listが同versionでも、parent/child/action bindingがないとresolve_unknownを呼ばずHELDになることを確認する。
- [x] RED: test_occurrence_bound_partial_retry_upload_closes_as_effected。failed parent event、同occurrence child summary、daily_loopのretry_existing action、同version snapshot、official platform_status=0/両confirmation/package_uploaded=trueが揃う場合だけ、provider_receipt_idにAgent ID/version/status=0/package_uploaded=1を含めeffectedで閉じる。
- [x] RED: partial negative cases prove mismatched child occurrence, snapshot occurrence, missing snapshot Agent in the current list, or mismatched official latest version cannot close.
- [x] Existing CP3 receipt parser is reused; exact Agent/version lines and the existing terminal are emitted for retry_existing success.
- [x] Implement the smallest occurrence-bound receipt parser and status-field propagation in the adapter. Exact snapshot owner/occurrence/captured_at is also required; existing successful CP3 receipt path stays unchanged.
- [x] Run the focused adapter tests; 33 passed after the snapshot-set regression.

### Task 2: retry_existingの決定的finish

**Files:**

- Modify: skills/capafy-autopublish/scripts/daily_loop.sh
- Test: skills/capafy-autopublish/test/test_daily_loop_terminal.py

**Interfaces:**

- Reuse the existing RESUME manifest path and publish_finish.sh; do not create a second publisher implementation.
- retry_existing may use that path only when the exact local manifest matches the selected Agent ID and official latest version and CP1 is confirmed. Readback failures/mismatches stop before publish_finish. A nonzero publish_finish result terminates that wake; it never falls through to a second agentic CP3 attempt.
- On successful publish_finish, retry_existing_stub_finish() logs the selected `AGENT_ID=` and `AGENT_VERSION_ID=` once and retains the existing SUBMITTED terminal shape. The existing child summary and parent event bind the block to run/occurrence/release, and `read_occurrence_bound_cp3_receipt` verifies official status=1.

- [x] RED: test_retry_existing_finishes_the_exact_existing_agent_version passes the same ID/version once to publish_finish and touches the healthy marker only on zero exit.
- [x] RED: add manifest/version-mismatch, official version/CP1/model mismatch, and publish_finish-failure tests. None invokes a second agentic submit or touches the marker.
- [x] Implement the exact-version retry_existing condition and emit Agent/version identifiers plus the established SUBMITTED terminal shape into daily_loop logs for occurrence reconciliation.
- [x] Run the focused shell-wrapper tests (16 passed) and bash -n on daily_loop.sh.

### Task 3: Acceptance

- [x] Run both focused pytest files; run `scripts/verify-source-boundary.sh` and `node scripts/verify-oss-self-contained.mjs --json` after syncing the Capafy inventory digest and sparse roots.
- [x] Run git diff --check; review that no counter reset, provider retry, or new Agent path was added.
- [x] Run the full Capafy autopublish/loop suites: 421 passed, 1 skipped (Playwright Chromium unavailable), 6 subtests passed.
- [x] Fresh read-only review: snapshot-set gap reproduced as RED, fixed, and independently confirmed; existing CP3 log contract was confirmed and the plan now matches it.
- [ ] Push the feature branch, pass exact-head CI, and merge through the normal PR path.
- [ ] Cut a latest-main immutable release. Use the registered reconciler to close the exact partial-effect occurrence only after its official receipt is ready; then apply the Capafy owner while loaded-idle.
- [ ] Let one natural scheduled run exercise the deterministic retry_existing path. Require the same Agent/version, platform_status=1, both confirmation flags, official receipt, and replay-zero before calling the listing submitted.
