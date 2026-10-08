# 3つのlocal revenue loopを並行可能にする実装計画

## Goal

Connector、Job Hunter、Fundraiserの既存loopを、現行`lm-loop`上で安全に動かし、同時実行をCodex homeとbrowser profileの不要な長時間lockで塞がない。対象はSQLite admission hot path、3 task classのprovider profile pool、Connector/Fundraiserのowner-isolated browser context、使い捨てChromiumを起動するbrowser capacity probeに限定する。

## Invariants

- 3 task classは`gpt-6-luna` / `max` / `fast`を維持する。
- `acct1`と`acct2`は既存profileだけを使う。各`CODEX_HOME`のexclusive provider lockは残す。
- provider lock busy以外のtimeout/未知失敗を別profileへ再送しない。busyはprovider起動前のtyped errorとしてのみ即時failoverする。
- browserは登録済みCloakBrowser daily-driverと既存session vaultだけを使う。contextごとにownerを固定し、別ownerのcontext/targetを変更しない。認証contextを確認するまでConnector/Fundraiserのprofile lockを短縮しない。
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

### 3. [完了: source branch] 既存Codex profile orderでhome busyをfail-fast

- `runtime/agent-runner/config.json`は`account_profile_order=[acct1,acct2]`で既に候補展開する。3専用task classだけに`fail_fast_provider_lease=true`を追加し、同じ`gpt-6-luna/max/fast`を維持する。
- `runtime/agent-runner/agent_runner.py::run_provider_process`は対象taskのCodex home lock busyを既存nonblocking lease helperで起動前に返す。`codex_failover_action`はこのtyped busyだけ次profileへ進め、全profile busyはretryable exit 75にする。provider起動後のtimeout/errorではfailoverしない。通常task classの同home直列待ちは維持する。
- `runtime/agent-runner/tests/test_provider_lease.py`と`runtime/agent-runner/tests/test_codex_account_failover.py`は42 passed / 24 subtests passed。
- 実装前に既存profileの`codex login status`をread-only・sanitizedで再確認する。認証値を出力しない。

### 4. Connector/Fundraiser browserをtask-owned contextへ移す; capacity probeはsource branchで完了

- `skills/connector/discover.js`、`apps/life-manager/lib/connector-browser-target-controller.js`、`apps/life-manager/lib/connector-browser-target-controller.test.js`、`skills/connector/test/discover.test.js`を確認・更新する。Connector controllerはdefault contextを仮定せず、leaseのcontext IDに属するtargetだけを作成/検出/終了する。
- `skills/browser/browser-context-lease.sh`はregistered endpoint、owner、domain cookie allowlist、seeded context ID/target IDを一元化する。`skills/connector/run.sh`と`skills/fundraiser-agent/runtime/run.sh`はprofile busyならresolverでread-only endpointを取り、task contextをseedする。profile guardはcontext準備中だけ保持し、その後解放する。
- Connector `apps/life-manager/lib/connector-browser-target-controller.js`はleased contextにtargetを作成し、probe/closeも同contextのexact targetに限定する。Fundraiser `skills/browser/scripts/cdp.py`はcontext IDに合わないtargetのoperationを拒否する。
- Vault内に`luma.com`および`x.com`/`twitter.com` domain cookiesがあることを確認した。cookie値は読まず、lease helperはseed count=0を拒否する。
- `runtime/browser/capacity_probe.py`と`runtime/browser/tests/test_capacity_probe.py`はsource branchで完了。登録identity resolver経由でdaily-driverの`/json/version`と`cdp_context_lease.py audit`のcontext countをread-onlyで観測する。Chromium processを起動・終了しない。focused testは3/3 pass。
- durable admission ownerの`resource_class`は変更しない。

### 5. Source acceptance

- 変更ごとに対象focused testをpassさせる。主な対象: `runtime/host/tests/test_resource_admission.py`、`runtime/agent-runner/tests/test_provider_lease.py`、`runtime/agent-runner/tests/test_codex_account_failover.py`、`runtime/browser/tests/test_capacity_probe.py`、Connector/Fundraiserの上記test。
- `bash scripts/verify-source-boundary.sh`、`./bin/lm-loop-contract`、`git diff --check`をpassさせる。
- 対象source acceptance、fresh read-only review、required CIをpassしてPRをmainへ統合する。
- 2026-10-08 15:57 JST source snapshot: context/CDP 21 tests、Connector wrapper 2、Fundraiser wrapper 7、Connector controller+contract 10 tests pass。`./bin/lm-loop-contract`、source-boundary、shell syntax、diff checkもpass。fresh read-only review、required CI、mergeは未完。

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
