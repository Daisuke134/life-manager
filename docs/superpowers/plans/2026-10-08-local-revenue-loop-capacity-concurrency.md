# 3つのlocal revenue loopを並行可能にする実装計画

## Goal

Connector、Job Hunter、Fundraiserの既存loopを、現行`lm-loop`上で安全に動かし、同時実行をCodex homeとbrowser profileの不要な長時間lockで塞がない。対象はSQLite admission hot path、3 task classのprovider profile pool、Connector/Fundraiserのowner-isolated browser context、使い捨てChromiumを起動するbrowser capacity probeに限定する。

## Architecture review — decision for this repair

- Keep `lm-loop`, its durable admission queue, effect fences, immutable releases, and provider receipts. The observed failures are in local boundaries: SQLite's existing-schema read path takes a writer lock, Codex locking is scoped to unique invocation homes, Fundraiser's wrapper and prompt use different browser owners, and Connector tab GC is not context-scoped.
- OpenClaw's agent queue, Hatchet's worker slots, or Temporal's worker slots do not repair those account/browser identity boundaries. Moving the scheduler now adds migration work while leaving the observed lock and context defects in place. Keep this repair on the current control plane and fix those boundaries directly.
- Keep the global finite-run cap at 8. After the three loops run naturally on the repaired release, collect fresh admission occupancy, queue age, per-class contention, and host load before proposing any cap or lane-limit change. The broader LR-08 revenue-owner classification and fairness design remains a separate SSOT item.

## Invariants

- 3 task classは`gpt-6-luna` / `max` / `fast`を維持する。
- `acct1`と`acct2`は既存profileだけを使う。invocationごとの`CODEX_HOME` lockに加え、同じaccount profileを共有するprofile-level leaseを持つ。3対象taskだけbusyをfail-fastし、他taskのwait動作は維持する。
- provider lock busy以外のtimeout/未知失敗を別profileへ再送しない。busyはprovider起動前のtyped errorとしてのみ即時failoverする。
- browserは登録済みCloakBrowser daily-driverと既存session vaultだけを使う。registryのowner keyを全helperで共有し、contextごとにownerを固定する。別ownerまたは別contextのtargetを変更しない。認証contextを確認するまでConnector/Fundraiserのprofile lockを短縮しない。
- SQLiteの既存`control.lock`、耐久性、effect fence、append-only receiptを維持する。混在release移行計画なしにWALへ変更しない。
- Global finite-run cap 8は維持し、fresh測定なしに上げない。Hatchet/Temporalへschedulerを移行しない。
- provider effect、申請、メール送信、再送、fence解放はsource testやspec更新では発生させない。

## 順序付き作業

### 1. 未確定provider effectを読み取り専用で照合

- LAUNCH Accelerator occurrence `fundraiser:18dc7222f6b5ec78-20440`は、target receiptの`verified_pre_effect_failure`だけでaggregate `effect_unknown`を閉じない。LAUNCHの同一target provider statusまたはapplication ID付きreceiptを確認する。
- Danaher `R1316263`とDeepScale.Venturesの既存targetもofficial readbackまたはstrict verified-pre-effect evidenceで照合する。
- 証拠が足りないtargetはfencedのまま保持し、再送しない。この読み取りはsource修正と並行して進める。

### 2. [完了: source branch] Admission SQLiteのhot pathから不要なwriterを外す

- `runtime/host/resource_admission.py::_database`と全callerを確認する。
- `runtime/host/tests/test_resource_admission.py`へ、既存schemaのopen/readで`BEGIN IMMEDIATE`やmigration DDLを実行しないfocused regressionを追加し、現行コードでfailすることを確認する。
- 既存schemaの接続はread/open pathだけで返し、legacy schema migrationとindex/schema作成は必要な初期化時に一度だけ行う最小変更にする。
- `control.lock`、`synchronous=FULL`、current DELETE journal contract、migration rollback、effect-unknown rowsを保持する。
- RED/GREEN: 実writer lock下で旧`BEGIN IMMEDIATE`が失敗し、修正後にpass。全`runtime/host/tests/test_resource_admission.py`は137/137 pass。main/release/productionへの反映は未完。

### 3. [source修正済み・focused acceptance PASS] 既存Codex profile orderでprofile busyをfail-fast

- `runtime/agent-runner/config.json`は`account_profile_order=[acct1,acct2]`で既に候補展開する。3専用task classだけに`fail_fast_provider_lease=true`を追加し、同じ`gpt-6-luna/max/fast`を維持する。
- Codexの全候補を`automation_home`配下のaccount-profile leaseで直列化し、invocation-home lockも維持する。同一acctの別invocationは同じprofile lockを共有し、別acctは並行できる。`fail_fast_provider_lease=true`の3 loopだけbusyで即時に次acctへ進み、他taskはrun deadlineまで待つ。
- fail-fastは候補configからboolで渡し、親環境の`LIFE_MANAGER_CODEX_HOME_BUSY_POLICY`は判定に使わず子provider envから除去する。unmarked taskのbusyはaccount fallbackを起こさない。profile lease FDはprovider子processへ渡し、runner終了後もprovider終了まで保持する。
- `runtime/agent-runner/tests`は95 passed / 129 subtests passed。profile排他・別acct並行・unmarked wait・runner kill後のlease保持を含む。

### 4. Connector/Fundraiser browserをtask-owned contextへ移す; capacity probeはsource branchで完了

- Fundraiser wrapperのownerはloop label `ai.anicca.fundraiser`を既定とし、promptは同じ環境値`CLOAK_BROWSER_OWNER`を全helperへ渡す。preflightは`context-only` leaseをseedし、`cdp_default_tab.py`の`create_target=False`と同じcontext取得モードを再利用する。`AI_BROWSER_HOLDER_PID`を後続helperへexportして同ownerのlease holderを保つ。
- Connectorのcontext lease後に行っていたowner-wide `cdp_tab_gc.py`呼出しを除去する。Connector controllerのleased-context reaperとcontext releaseを使い、GCが別context targetを閉じないようにする。

- `skills/connector/discover.js`、`apps/life-manager/lib/connector-browser-target-controller.js`、`apps/life-manager/lib/connector-browser-target-controller.test.js`、`skills/connector/test/discover.test.js`を確認・更新する。Connector controllerはdefault contextを仮定せず、leaseのcontext IDに属するtargetだけを作成/検出/終了する。
- `skills/browser/browser-context-lease.sh`はregistered endpoint、owner、domain cookie allowlist、seeded context ID/target IDを一元化する。`skills/connector/run.sh`と`skills/fundraiser-agent/runtime/run.sh`はprofile busyならresolverでread-only endpointを取り、task contextをseedする。profile guardはcontext準備中だけ保持し、その後解放する。
- Connector `apps/life-manager/lib/connector-browser-target-controller.js`はleased contextにtargetを作成し、probe/closeも同contextのexact targetに限定する。Fundraiser `skills/browser/scripts/cdp.py`はcontext IDに合わないtargetのoperationを拒否する。
- Vault内に`luma.com`および`x.com`/`twitter.com` domain cookiesがあることを確認した。cookie値は読まず、lease helperはseed count=0を拒否する。
- `runtime/browser/capacity_probe.py`と`runtime/browser/tests/test_capacity_probe.py`はsource branchで完了。登録identity resolver経由でdaily-driverの`/json/version`と`cdp_context_lease.py audit`のcontext countをread-onlyで観測する。Chromium processを起動・終了しない。focused testは3/3 pass。
- durable admission ownerの`resource_class`は変更しない。
- `skills/browser/scripts/test_browser_context_handoff.py`、Fundraiser runtime control-plane tests、Connector context-wrapper tests、CDP target ownership tests、`test_cdp_context_lease_acquire_lock.py`は41 passed。

### 5. Source acceptance

- 変更ごとに対象focused testをpassさせる。主な対象: `runtime/host/tests/test_resource_admission.py`、`runtime/agent-runner/tests/test_provider_lease.py`、`runtime/agent-runner/tests/test_codex_account_failover.py`、`runtime/browser/tests/test_capacity_probe.py`、Connector/Fundraiserの上記test。
- `bash scripts/verify-source-boundary.sh`、`./bin/lm-loop-contract`、`git diff --check`をpassさせる。
- 対象source acceptance、fresh read-only review、required CIをpassしてPRをmainへ統合する。
- 既存source snapshot: context/CDP 21 tests、Connector wrapper 2、Fundraiser wrapper 7、Connector controller+contract 10 tests pass。`./bin/lm-loop-contract`、source-boundary、shell syntax、diff checkもpass。
- Additional acceptance: `runtime/host/tests/test_resource_admission.py` 137 passed; `runtime/browser/tests/test_capacity_probe.py` 3 passed; Connector production contract 1 passed. `./bin/lm-loop-contract` reports catalog 18 / registry 187 / errors 0. Source boundary, shell syntax, Python compile, diff check and OSS self-contained verifier pass.
- **GREEN source candidate after main sync:** `origin/main` advanced from `64db1c2e` to `da12ba88` with SSOT and LINE Sticker changes only; no overlapping source code changes were present. The source was rebased cleanly and focused acceptance rerun: agent-runner 95 tests / 129 subtests, browser/loop handoff 41 tests, host admission 137 tests, capacity probe 3 tests, Connector contract 1 test; loop contract and manifest verifier pass. The previous independent review and required CI passed before this docs/LINE-only main advancement; push the new rebase and rerun review/CI before merge.
- TDD RED on source head `7201c8d4`: focused regressions reported 8 failures, 1 pass, and 23 passing subtests. The failures reproduce missing profile-level lock API, inherited fail-fast policy affecting unrelated tasks, Fundraiser owner/context-mode mismatch, and Connector's owner-wide tab GC call. `test_terra_default.py` now passes. No production owner or provider was changed by these fixture tests.
- Additional runner-call-site RED on head `5f015b68`: the two profile-policy subtests fail because `run()` passes neither the stable account lock path nor an explicit task-scoped fail-fast boolean to `run_provider_process`.
- The unmarked-task wait and provider-retained-lease-on-runner-kill regressions also fail before implementation, confirming that the shared profile lease must cover all Codex candidates and its file descriptor must survive the runner process.
- Failover policy RED: an unmarked Codex candidate currently receives `retry_next_account` for `codex_home_busy`; only candidates with explicit `fail_fast_provider_lease` may switch profiles on a busy lease.
- Browser lease RED: the helper assigns `AI_BROWSER_HOLDER_PID` only to the initial acquire subprocess; it does not export the owner PID to later `cdp_default_tab.py` calls, so same-owner context reuse is not yet proven.

### 6. Immutable releaseとtarget owner apply

- 変更を含むlatest-main immutable releaseを作る。現行`life-manager-release-reconciler` occurrenceがnatural terminalし、shared apply lockがfreeであることを先にreadbackする。active ownerをstop/restartせず、applyを重ねない。
- Host disk/headroom、target admission rows、unknown effect fencesをfresh readbackする。
- Connector `life-manager-connector-native`、Job Hunter `job-search-daily` / health / inbox、Fundraiserをowner単位で適用し、loaded release SHA・argv/envとadmissionを確認する。
- Global `lm-loop doctor`のCapafy / handoff owner問題は対象外ownerなので変更しない。target-specific applyの安全性を証明できない場合、その正確な外部owner blockerを保持する。

### 7. Natural occurrenceとofficial provider readback

- Connector: 自然runからLuma registration、Google Calendar event、Telegram receiptを同じoccurrenceへ結ぶ。
- Job Hunter: 自然runで新しい適格Workday jobを処理し、公式application state/receiptとTelegram outcomeを同じoccurrenceへ結ぶ。human-required stepを迂回しない。
- Fundraiser: 自然runで新規VCとAI/AGI founderを発見し、適格な公開業務連絡先へLife Managerのmanager conceptを伝える。Gmail provider message ID、exact Sent、Telegram receiptを同じoccurrenceへ結ぶ。Podcast/Zoom/対面提案を含めるが、旅行/有料ticketは購入しない。
- 既存fenced targetは候補から除外する。新しい別targetの処理を妨げる場合は、sourceのfence scope/callerを再診断してtarget単位に修正する。unknownを解消済みに書き換えない。

### 8. 完了判定と次cursor

- 3 loopの各natural occurrenceがprovider receipt/readbackを持ち、対応するTelegram reportが送達済みである。
- 対象occurrenceでduplicate/replayが0である。過去unknown targetはofficial statusかstrict verified-pre-effect proofがある場合だけ閉じる。
- production gatesが揃った後にこのlaneを完了し、統合SSOTの次cursor `MX-01`へ戻る。

## 履歴: PR #7072 acceptance cursor（現在はsuperseded）

1. **現在cursor — latest-main acceptance:** force-with-lease push the rebase onto `da12ba88`, request a fresh read-only review, and pass every required check on the new PR head before merging PR #7072 through the repository's `--admin` first flow.
2. LAUNCH occurrence `fundraiser:18dc7222f6b5ec78-20440`、Danaher `R1316263`、DeepScale.Venturesの既存effectをread-onlyで照合する。これはCIと並行し、Gmail検索は3 queryで0件だったがno-effect proofではない。同一targetのofficial portal/Workday statusまたはstrict verified-pre-effect proofがないものはfencedのまま保ち、再送しない。
3. release reconcilerのnatural terminal、shared apply lock、disk/headroom、target admission、unknown fenceをfresh readbackする。latest-main由来immutable releaseを作り、Connector `life-manager-connector-native`、Job Hunter daily/health/inbox、Fundraiserだけをowner単位でapplyし、loaded SHA/argv/envを確認する。active ownerを止めず、applyを重ねない。
4. 3 loopのnatural occurrenceを確認する。ConnectorはLuma registration + Google Calendar + Telegram receipt、Job Hunterは新規適格Workday jobのofficial state/receipt + Telegram、Fundraiserは新規VCとAI/AGI founderへのGmail provider message ID + exact Sent + Telegram receiptを同一occurrenceへ結ぶ。human-required gateを迂回しない。
5. 各occurrenceのreplay-zeroを確認し、過去unknownは同一targetのofficial statusまたはstrict verified-pre-effect proofがある場合だけcloseする。証拠が取れないものはfencedのまま記録し、新規targetの処理とは分ける。
6. 3 loopのproduction readbackとreplay-zeroが揃ったらこのlaneを完了し、統合SSOTの次cursor `MX-01`へ戻る。

## 現在cursor（2026-10-08）

- PR #7072（`fix/local-revenue-capacity-concurrency-20261008`、head `663577b3ed96938d1c6e9c48acdadb46dad80099`）はmerged。Admission SQLite、Codex profile lease、browser context isolation、capacity probeのsource修正はmainへ統合済み。上のPR #7072 acceptance cursorは完了済みの履歴。
- 現在の実行順序と最新のproduction blockersは [`2026-09-25-life-manager-unified-ssot.md`](../specs/2026-09-25-life-manager-unified-ssot.md) の `2026-10-08 21:30 JST — retired provision-browser guard identity corrected` を正本とする。現cursorはguard PR exact-head CI/fresh review → merge → immutable release/natural handoff → fixed-release cleanup receipt/admission → guarded Capafy retirement/doctor → target effects → owner natural outcomes → same-window capacity/economics。
