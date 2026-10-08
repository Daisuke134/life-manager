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

### 3. [source実装済み・review修正待ち] 既存Codex profile orderでprofile busyをfail-fast

- `runtime/agent-runner/config.json`は`account_profile_order=[acct1,acct2]`で既に候補展開する。3専用task classだけに`fail_fast_provider_lease=true`を追加し、同じ`gpt-6-luna/max/fast`を維持する。
- 現行実装はinvocationごとに異なる`CODEX_HOME`へlockを置くため、同じacctを使う別runのbusyを検出できない。修正ではaccount profileごとの共有leaseを追加し、invocation-home lockも残す。対象taskのprofile-level busyだけ起動前にtypedで返し、既存failoverで次profileへ進める。全profile busyはretryable exit 75、provider起動後のtimeout/errorではfailoverしない。
- `LIFE_MANAGER_CODEX_HOME_BUSY_POLICY`は親環境から常に除去し、対象taskの候補だけrunner内部で有効化する。環境変数の継承で対象外taskへfail-fastを漏らさない。
- `runtime/agent-runner/tests/test_provider_lease.py`と`runtime/agent-runner/tests/test_codex_account_failover.py`は42 passed / 24 subtests passed。
- 同一profileへの異なるinvocation IDは相互排他され、異なるprofileは並行でき、対象外taskは従来どおり待つことをfocused testで確認する。認証値は出力しない。

### 4. Connector/Fundraiser browserをtask-owned contextへ移す; capacity probeはsource branchで完了

- Review correction: Fundraiser wrapperの既定owner `fundraiser` とprompt内helperのowner `ai.anicca.fundraiser` を、registryが選ぶ同一owner keyへ揃える。`cdp_default_tab.py`とcontext leaseでowner・context取得方式を一致させる。
- Connectorはcontext lease取得後にowner単位の`cdp_tab_gc.py`を呼ぶ。このGCはowner ledgerで対象を絞るがcontext IDでは絞らないため、leased context内のreapへ置換するか、この呼出しを除去する。

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
- 既存source snapshot: context/CDP 21 tests、Connector wrapper 2、Fundraiser wrapper 7、Connector controller+contract 10 tests pass。`./bin/lm-loop-contract`、source-boundary、shell syntax、diff checkもpass。
- PR #7072 (`fix/local-revenue-capacity-concurrency-20261008`) は最新main `1872befb`へrebaseし、head `fa60666e`でOPEN。read-only reviewはCriticalなし、Important 2件（Fundraiser owner/context不一致、profile-level provider lease不足）、Minor 1件（継承envで対象外taskにもfail-fastが漏れる）を報告。Connector GCのcontext scopeもsource上で未解決。
- rebase前のheadでは`test_terra_default.py`の3 task-class期待値不一致とOSS manifest不一致でCIがFAIL。manifest更新後のローカルverifierは`ok=true`。現headではCodeRabbitとOSS boundaryはPASS、Loop control・Python syntax/unittest・secret scansは実行中。
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

## 現在cursorと残TODO（完了までの順序）

1. **現在cursor — source修正:** profile-level provider leaseとfail-fast envの漏れを修正し、Fundraiserのowner/contextをregistry keyへ統一する。Connector tab GCをleased context内に限定するか除去する。`test_terra_default.py`の3 task-class fixtureも新設定に合わせる。
2. 既存effect fenceのread-only照合をsource修正と並行する。LAUNCH occurrence `fundraiser:18dc7222f6b5ec78-20440`の同一target official status/application ID付きreceipt、Danaher `R1316263`、DeepScale.Venturesを確認する。証拠不足のtargetはfencedのまま保ち、再送しない。
3. 修正箇所のfocused testsを追加・実行し、関連suite、`./bin/lm-loop-contract`、source-boundary、shell syntax、manifest verifier、`git diff --check`をpassさせる。providerの同一profile排他・別profile並行・対象外taskのwait、browser owner一致・context境界を確認する。
4. 修正とmanifest更新を専用branchへcommit/pushする。fresh read-only reviewでCritical/Important findingを閉じ、PR #7072の全required CIをPASSさせてmainへ統合する。
5. release reconcilerのnatural terminal、shared apply lock、disk/headroom、target admission、unknown fenceをfresh readbackする。latest-main由来immutable releaseを作り、Connector `life-manager-connector-native`、Job Hunter daily/health/inbox、Fundraiserだけをowner単位でapplyし、loaded SHA/argv/envを確認する。active ownerを止めず、applyを重ねない。
6. 3 loopのnatural occurrenceを確認する。ConnectorはLuma registration + Google Calendar + Telegram receipt、Job Hunterは新規適格Workday jobのofficial state/receipt + Telegram、Fundraiserは新規VCとAI/AGI founderへのGmail provider message ID + exact Sent + Telegram receiptを同一occurrenceへ結ぶ。human-required gateを迂回しない。
7. 各occurrenceのreplay-zeroを確認し、過去unknownは同一targetのofficial statusまたはstrict verified-pre-effect proofがある場合だけcloseする。証拠が取れないものはfencedのまま記録し、新規targetの処理とは分ける。
8. 3 loopのproduction readbackとreplay-zeroが揃ったらこのlaneを完了し、統合SSOTの次cursor `MX-01`へ戻る。
