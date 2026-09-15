# Life Manager Agent Architecture Refinement

状態: IN PROGRESS（未完了） — this document defines the next architecture boundary; it does not
claim that the target control plane, marketplace effects, or cloud deployment are complete.

## Implementation status (current evidence)

このspecの受入状態は、次のとおりです。`PROD-01`が全体の正本cursorであり、provider固有の
応募・送信・公式receiptはMarketplace ownerが管理します。Architecture ownerは別worktreeで
共通契約、skill、fixture、read-only診断だけを進めます。両者を同じファイルや稼働browserで
同時に変更しません。

完了済みの共通基盤:

- Product Loop/job identity、runtime state/event、context capsule（FND-02〜FND-10）
- graph projection/query（GRAPH-01〜GRAPH-03）
- eval case/run/score/gate（EVAL-01〜EVAL-03）
- typed human gate（HUMAN-01〜HUMAN-02）
- browser session contractとlocal headless read-only canary（BROWSER-01〜BROWSER-02）
- Responses APIの同期adapterとread-only background start/poll（API-01の基礎部分）
- Lancers共有9227/profileのbrowser session lease実装と競合時の再試行分類（コード/テスト済み、main未統合）

未完了の受入:

- `PROD-01`: Lancersのpending消化とNegotiate/Storefront/Paidの公式receipt・replay-zero
- `BROWSER-03`: Application canaryは合格。残りのeffect/readback laneは未完了
- `ADMISSION-01`: protocol v2のmain由来release反映と有効化は実測済み。current releaseと各ownerの自然terminal確認は継続中
- `BROWSER-04` / `ADMISSION-02`: branch実装・テスト済み。main由来release反映と自然wake canaryは未完了
- `CONTROL-01`: registry外Browser provisionerの所有者分類とhandoff
- Responses APIの通常Loopへの昇格、Agents API maintenance pilot
- 14 Loopのlocal completion gate
- tenant分離したcloud、cloud canary、phone-only経路、本番昇格

証拠はplan `docs/superpowers/plans/2026-09-15-life-manager-local-to-cloud.md`と専用branch
`docs/agent-engineering-skills-20260915`のcommitへ記録します。テストgreenだけではprovider
成功や収益を意味せず、公式receiptがない状態は未完了です。

### Foundation scope（platform作業との境界）

このspecでいうfoundationは、Lancers/CrowdWorks/Coconala/Mercorの案件を処理することではなく、
どのProduct Loopでも同じ安全な実行契約を使えるようにすることです。platform ownerはサイト固有の
DOM・アカウント・応募・契約・納品・報酬receiptを担当し、foundation ownerは共有kernelと受入契約を
担当します。platformの公式receiptはfoundationが実環境で機能したことを確認する受入証拠ですが、
platform adapterの実装そのものをfoundationへ複製しません。

| foundation領域 | 現在 | 残り |
|---|---|---|
| FND（goal/wake/context/admission/effect/readback） | 共通契約とcandidate testsあり | 14 loopすべてを同じcontractへ接続し、local completion manifestを埋める |
| GRAPH | projection/queryの部品あり | 全loopのissue・receipt・resource・human gateを一つのcontrol planeで再構築する |
| EVAL | case/run/score/gateの部品あり | held-out・safety・cost・live canary・promotion/rollbackを実運用へ接続する |
| OBSERVABILITY | runtime event・metrics・Telegram境界を定義 | 内部control room、通知抑制、失敗からの自動issue生成を全loopへ接続する |
| SELF-HEAL / SELF-IMPROVE | timeout・stale回収・冪等化の候補修正あり | supervisor、retry、candidate生成、評価、昇格、rollbackを無人で連結する |
| LOCAL / CLOUD | 同じcontractにする設計あり | local gate、tenant分離、cloud worker/browser、phone-only canary、本番昇格 |

### 今回の判定（2026-09-16）

**この仕事は完了していません。** スキルの調査・読み込みと候補branchのテストgreenは、
Life Managerの実際の応募・契約・納品・報酬・cloud運用が動いたことを意味しません。現在の
origin/mainは `0aba1191a4`（PR #5257）まで進みましたが、本番selectorはまだ
`20260916T060446-f80de2ef` のままで、ownerのinstalled/event SHAも混在しています。統合候補
`fix/lm-fundamental-runtime-20260916`（HEAD `b783051fd5`）は最新mainを取り込みpush済みで、
本番へはまだ統合していません。
したがって、次の作業は「さらにスキルを読む」ではなく、候補をmain由来immutable releaseへ
昇格し、ownerごとの自然wakeで公式効果を確認することです。

### 残りTODO（実行順の短い正本）

**前提0（最優先）:** gig workの外部effectを実行するCodexを一つに固定し、もう一方は同じ
provider/state/browserを触らない。handoff receiptができるまで、未統合candidateの再実行も行わない。

| 順番 | atomic task | いま残っている理由 | 完了条件 |
|---:|---|---|---|
| 1 | `CAND-01` 候補 `b783051fd5` の共有kernel修正を固定する | 修正はcandidateに限定され、本番ownerへは未配布 | **完了（candidate gate PASS）**: 最新main同期後にLancers 402 tests + 17 subtests、Job Hunter 462、runtime/loop 481 + 483 subtests、runtime/host 88、sparse/admission 61、completion manifest 12 tests、agent-runner 71 + 93 subtestsがPASS。main/本番にはまだ配布しない |
| 2 | `CAND-02` candidateのread-only自然wake/canaryを閉じる | `66 passed`はfixture/内部read-only canaryであり、本番ownerの自然wakeではない | **内部canary PASS**: lease競合、CDP stale GC、admission v2/legacy並行を確認。live ownerのterminal・公式readbackはmain/release反映後に再確認 |
| 3 | `PROD-01-F` Lancers pendingを1 sliceずつ消化 | pending 101件が残り、Application以外の収益receiptが0 | 101件が公式receipt付きで処理済み、または理由付きterminal。effect key重複0、replay-zero |
| 4 | `PROD-02` Lancers Negotiate/Storefront/Paidを閉じる | Paidは契約候補0・effect/readback 0で、収益成功ではない。Reply/Storefrontも公式readback未完 | laneごとに公式receipt、または明示的not-applicableと再試行境界 |
| 5 | `MARKET-02` CrowdWorksを閉じる | 4 ownerが旧release、直近に30秒 `Page.goto` timeout、account/profile failure | 候補受入後に作る新releaseの自然terminal、公式応募/契約receiptまたはtruthful not-applicable、重複0 |
| 6 | `MARKET-03` Mercorを閉じる | logged_out / CDP handshake timeout履歴、human gate・payment receipt未確認 | stale lease再発なし、Application/Reply/Paidがtyped terminal、必要なhuman gate再開、公式receipt |
| 7 | `MARKET-04` Coconalaを別ownerから受け取る | 他workstreamがbrowser/account/TODOを所有中 | 4 laneごとの公式応募・購入・納品receipt、buyer readback、replay-zero |
| 8 | `CONTROL-01` registry外Browser provisionerを分類する | `lm-loop doctor` が unmanaged provisionerを1件報告 | 所有者・release・state・readbackを登録し、doctorのunmanaged 0（稼働中profileは止めない） |
| 9 | `LOCAL-01/02` 14 Product Loopのcompletion manifestを埋める | manifest契約はcandidateに実装済みだが、各loopの実測evidence接続が未完 | unknown 0、未対応はtyped state、成功は公式receiptだけ、内部ログとTelegramを分離 |
| 10 | `CLOUD-01..04` local→cloud昇格 | tenant分離・cloud Browser・phone-only canary未実装/未実測 | local gate全PASS後、同じcontractでcloud canary、公式readback、replay-zero |
| 11 | `INT-99` 全受入後に一度だけmain統合・immutable release化 | 候補は未統合で、本番selectorは `f80de2ef` のまま | rows 1〜10が全PASS、mainへ一度だけPR/merge、13 ownerを同じSHAへ反映、production readback |

**進行ルール:** 前の行の完了条件を満たすまで次の外部effectを実行しません。`exit 0`、
Telegram報告、テストgreen、ブラウザ画面表示だけでは完了にしません。候補branchを本番ownerへ
先に配布しません。全体のlocal/cloud受入が揃った最後に、main統合とimmutable release作成を
一度だけ行います。

**現在のfoundation cursor:** `CAND-01`と`CAND-02`の内部canaryは完了しています。`LOCAL-01/02`
ではcompletion manifestの契約をcandidate `b783051fd5`へ実装済みです。次は各loopのevidenceを
このmanifestへ接続する作業であり、platformの外部effectを私が実行する項目ではありません。

### 理想フロー（1回のwake）

Life Managerは、常駐する一つの巨大agentではなく、短いwakeを何度も安全に積み重ねます。
利用可能な観測データ、保存済みの方針・制約、現在状態から、各wakeで次の安全な行動を
自律的に決めます。

```mermaid
flowchart LR
  A[保存済みの目標・方針・現在状態] --> B[queue / resource admission]
  B --> C[新鮮で小さいcontext capsule]
  C --> D[modelが次のskillを選ぶ]
  D --> E[owner lease付きのprovider操作]
  E --> F[公式画面/APIのreadback]
  F --> G[receipt・ledger・graph・eval]
  G --> H[次のwake / retry / typed human gate]
  H --> A
  G --> I[内部control room]
  I -.重要な時だけ.-> J[短いTelegram通知]
```

ブラウザ、memory、認証、外部effectは共有kernelが安全に管理し、各platform adapterはサイト固有の
URL・DOM・receiptだけを担当します。成功は「プロセスが動いた」ではなく、公式readbackと
replay-zeroが揃った時だけです。人間が必要なのは、Mercorの面接や購入者確認のような
`human_gate`だけで、通常のwake・失敗回復・評価は自動で続きます。

### 引き継ぎ判定（gig work）

**推奨は、ここからgig workの実行ownerを他Codex一つに固定することです。** 直接の同じファイル
競合は今回のread-only確認では検出していませんが、未統合branch・候補release・共有browser/stateが
複数あるため、二つのCodexが同じgig workを進める運用は危険です。以後の境界を次で固定します。

- 他Codex：`skills/earn/gig/TODO.md`、Coconala/Lancers/CrowdWorks/Mercorのprovider effect、
  browser/account/state、公式receipt、production owner。ここをgig workの単独ownerとする。
- 私の候補：`fix/lm-fundamental-runtime-20260916` は handoff用のruntime候補証拠として凍結する。
  `bf8ab51b34`を部分的に本番へ入れず、単独ownerが受入した後に一度だけrelease化する。
- 私のdocs：このspecだけをread-onlyで更新し、gigのTODO/provider/state/browserを再編集しない。

handoffの完了条件は、単独owner、対象branch、候補SHA、未完了receipt、次の一件を一つのhandoff
receiptに記録することです。handoff receiptがない間は、どちらのCodexも同じ外部effectを再実行しません。

### TODO.mdとの関係

`skills/earn/gig/TODO.md`は、Gigの案件・契約・納品・報酬を進めるplatform workstreamの実行SSOTです。
このspecは、14 Product Loopが共通で使うfoundationのSSOTです。両方を一つの長いTODOへコピーして
統合しません。Gig ownerはTODOからprovider effectを進め、foundation ownerはこのspecのcontractを
更新します。TODOの各platform項目は、必要なfoundation gateをこのspecのIDへリンクします。

### Current operational cursor and remaining atomic TODO

次の状態は、意図やPIDではなく、最新のread-only `lm-loop status`、immutable release manifest、
runtime event、provider ledgerを突き合わせた現在cursorです。後続のwakeで変わり得るため、
履歴として残し、成功判定には再利用しません。

| 対象 | 実測状態 | 判定 |
|---|---|---|
| source | `origin/main=0aba1191a451a0ad72540f48397623f93cab3d8e`（PR #5257まで）; 統合候補branch `fix/lm-fundamental-runtime-20260916`（HEAD `b783051fd5`）はpush済み・未統合 | mainにはCodex account failoverとTODO更新が追加済み。候補にはLancers shared browser session lease、stale claim解放の冪等化、CrowdWorks/Mercor finite lane timeout、Mercor stale provisioning auto-GC、sparse releaseのadmission capability自動同梱、14-loop completion manifest契約/CLI、canonical job mapping、7つのagent-engineering skillを追加。主要suite・effectなしcanary（66 tests）・manifest tests（12 tests）・agent-engineering static checkがPASS |
| release selector | `~/loops/current`は`20260916T060446-f80de2ef`（SHA `f80de2ef`）を指す。ownerのinstalled/event SHAは混在 | current自体はorigin/mainと一致するが、Lancers/CrowdWorks/Mercorのowner drift gateはFAIL。protocol v2は有効、候補branchは未反映、全体gateは未完 |
| Lancers Application | 以前のe789/current wakeでproposal 20件を公式ledgerへ記録（pendingは134→101）。直近current ownerは`entrypoint_exit_124`でblocked | 20件のApplication公式receiptは保持するが、現在の自然wakeは成功扱いにしない。pending 101件と再現可能なterminalが残る |
| Lancers Browser | `loaded-running`、9227 CDPはlisten中だがinstalled SHA `2ff93374`、event SHA `437b5696`でcurrent `f80de2ef`と不一致 | 9227 healthだけではrelease gate PASSにならない。候補反映後に同時接続とlease releaseを確認 |
| Lancers Negotiate/Storefront/work-sync/report | Negotiate/Telegram-report/Work-syncは`resource_control_busy`/FIFO blocked、Storefrontは`entrypoint_exit_1`。installed/eventは2ff | current自然wakeを成功扱いせず、候補反映後にownerごとのterminalと公式readbackを確認 |
| Lancers Paid | installed/eventは2ff、直近は`resource_capacity_busy` blocked | timeout canaryは候補でPASSしたが、現行Paidの`effect=0`・`readback=0`・公式paid receipt 0。契約が存在する場合の正式納品は別の認可・契約仕様が必要 |
| Lancers ledger | 最新はsequence 167（proposal 27922237）。148〜167は`application_verified`のみで、paid/delivery receiptは0 | Application 20件は成功として記録。収益・納品の成功は0件として扱う |
| CrowdWorks | 9228/profileは既存の`provider-browser.lock`でlane間を直列化。4 ownerは旧release `2a53ce25`で、直近はApplication/Paidが`resource_capacity_busy`、Reply/Reportが`resource_control_busy` | timeout修正は候補 `b783051fd5`。main/current反映後、4 laneの自然terminalと公式receiptを確認 |
| Mercor | 9222/daily-driverはCDP context leaseを使用。期限切れ`job-search-daily`行はGC済み。Application installed 2ff/event e789、Paid/Reply installed/event 2ffで、Paid/Replyはresource blocked | timeoutとstale provisioning auto-GCは候補 `b783051fd5`。main/current反映後、Application/Paid/Replyの自然terminal・human gate・公式receiptを確認 |

履歴として、PR #5250（commit `2ff93374f7`）までのmainでは次を実施しました。PR #5233で本番の
`application-owner`から`--exhaustive`を外し、仕様どおり通常の回転検索を使うことです。
PR #5234では、confirmation遷移失敗後の診断用`page.evaluate`を呼ばず、URLだけを記録して
必ず戻るようにしました。PR #5235では、通常経路も候補40件になるまで検索せず、1 wakeにつき
回転中の1 query sliceだけを処理します。新releaseの自然wakeで約1分終了を確認しましたが、
旧releaseでは候補・公式応募receiptがありませんでした。現在はPR #5236で停止時にrun専用Playwright clientを
2秒でterminateするwatchdogを追加し、PR #5237でpending-cursorの回帰fixtureを現行readerへ
合わせ、HOL 36件をgreenにしました。共有admission枠はCoconala収益agent・Affiliate・Lancers
Negotiateなどが占有し、Application/Paidの新wakeが`resource_capacity_busy`になっています。これは
memory crashを避けるfail-closed動作ですが、PR #5238でCrowdWorks/Mercorをagent/revenue admission
へ明示し、admission handoff lockを0.5秒でfail-closedにしました。PR #5241で現行Lancers DOMの
proposal読取fallbackを追加し、PR #5242でPaidの後処理にもbounded cleanupを適用しました。
e789のApplication自然wakeで公式proposal receipt（ledger sequence 148〜162）を15件確認済みです。
一方、protocol v2は`protocol.json={"version":2}`として有効化され、`verified_finite_labels=139`を
readbackしました。queueにはborrow owner、revenue claimにはLancers/Application等が現れ、優先順を
実測しています。自動reconciler自身は旧releaseで全fleet走査が長時間化していましたが、PR #5245で
1 wake最大1 ownerへ、PR #5248で対象snapshotを最大64件へ制限しました。PR #5249でLancersの有限laneに
300秒のruntime timeoutを追加し、当時のrelease `20260916T041632-437b5696`へ反映済みです。当時のmain `2ff93374f7`は
当時のcurrent `20260916T044820-2ff93374`へ反映され、Lancers 7 ownerのinstalled/loaded argvもその時点では一致していました。Paidのtimeout
canaryは`entrypoint_exit_143`で終端しましたが、provider効果は未確認です。関連suiteは206 tests + 130
subtests PASS、Lancers timeout suiteは163 tests + 30 subtests PASSです。
未load plistの検証に加え、release reconcilerがprotocol未作成時に自動でv2有効化を試みます。
その後、PR #5252〜#5256で収益枠の予約改善・legacy revenue ownerの並行許可・現在の
admission release記録がmainへ入りました。`~/loops/current`はPR #5255由来のreleaseを指し、
PR #5256はまだrelease化されていません。ownerのinstalled/event SHAも混在しているため、
release drift gateは未完了です。
また、`lm-loop doctor`はregistry外の稼働中label
`ai.anicca.provision-browser.colors-hachioji.owner-18211957`を1件報告しています。
これは別のBrowser provisionerがprofileを使用中のため、停止・削除せず、所有者登録または
安全なhandoffを完了するまでlocal gateを閉じます。

順序変更記録: 旧順序ではpending処理（`PROD-01-F`）をrelease統一（`PROD-01-H`）より先に置いて
いましたが、Browser競合を増やさず全ownerを同一immutable SHAへ揃える方が安全で、後続wakeの再現性も
上がるため、`PROD-01-H`を先に実行しました。新しいcursorは`PROD-01-F`です。公式effectの順序は
変えず、各laneを一つずつ検証します。

このcursorからの実行順序を固定する。前の項目の公式証拠がない限り、次のplatformへ進めない。

| 順番 | atomic task | 変更範囲 | 完了条件 |
|---:|---|---|---|
| 1 | `PROD-01-A` Lancers Paidを現行releaseへreconcileし、timeout canaryを確認 | Lancers Paid ownerのみ | **基盤gate PASS**: installed/loaded argvとinstall eventはSHA `437b5696`、旧runは`entrypoint_exit_143`。provider効果は別gate |
| 2 | `PROD-01-B` wrapper修正を含む`6e95...` releaseを作成し、Applicationをidle境界で反映 | Application owner + immutable release | **完了**: loaded argvは`--exhaustive`なし、installed/event SHAは`6e95...` |
| 3 | `PROD-01-C` Lancers Applicationを新wrapperの自然wakeで1回検証 | Application owner、planner/safety evidence | **基盤gate完了**: bounded discoveryが約1〜5分で終端。公式効果は`BROWSER-03`で別判定 |
| 4 | `PROD-01-D` `ba19...` releaseを作成し、Application/Paid/Browserを反映 | immutable release + 3 Lancers owners | **履歴gate・置換済み**: ba19の反映確認後、現行の収益admission/DOM修正を含むe789へ移行 |
| 5 | `PROD-01-E` 収益枠を予約できるadmissionへ修正・検証 | shared resource admission + marketplace revenue owners | **コード/テスト/release作成完了**: 148 tests + 100 subtests PASS。e789を7 ownerへ反映済み、自然wakeの効果確認は別gate |
| 6 | `PROD-01-F` pending 101件を順番に再確認し、fresh sliceを枯らさない | Application state/reconciliation only | 観測cursorではpendingが134→101（33件減）。20件の公式verified ledgerを確認済み。transient failureは次wakeへ送り、state invalidはfail-closed。101件の解消または理由付きterminalが必要 |
| 7 | `PROD-01-G` proposal確認遷移の残故障を1件で再現・修正 | Lancers provider adapterと回帰テスト | **完了**: 現行DOM fallback（PR #5241）をe789で実行し、proposal 27922413/27921564の公式readbackをledgerへ記録 |
| 8 | `PROD-01-H` Lancers全7 ownerのrelease driftを解消 | Lancers ownerだけ | **旧currentではPASSしたが再オープン**: currentが`f80de2ef`へ進み、7 ownerのinstalled/event SHAが混在。新releaseでbounded reconcileを再実行する必要がある |
| 9 | `BROWSER-03` Lancers応募canaryを1件だけ実行 | provider effect owner | **Application部分PASS**: ledger sequence 148〜167の公式 `application_verified` 20件、重複0。直近Applicationは`entrypoint_exit_124`で、残りeffect laneのcanaryは未完 |
| 10 | `ADMISSION-01` 未load v2対応plistを許容する修正をmain由来releaseへ反映し、protocol v2を有効化 | shared runtime + installed finite owners | **v2基盤はmainで有効 / runtime反映未完**: current `060446-f80de2ef`、`protocol.json` version 2。ownerのinstalled/event driftと自然terminalを再確認する必要がある |
| 11 | `BROWSER-04` shared Lancers browser session leaseをmain由来releaseへ反映 | Lancers browser boundary + all Lancers owners | **統合候補 `b783051fd5` code/tests/live contention/Paid canary PASS**: lease保持中の別processは`browser_session_busy`で拒否し、解放後のread-only inventoryとbranch版Paid ownerは順番に成功。runtime停止完了まで保持する解放回帰テスト済み。main統合後、Application/Paid/Reply/Storefrontの2 natural wakeで競合0を確認 |
| 12 | `ADMISSION-02` stale claim解放を冪等化し、再予約を壊さない | shared runtime admission | **統合候補 `b783051fd5` code/tests PASS**: stale sweepがclaimを先に削除しても`release_and_reserve`が警告・例外を出さず、必要な予約を継続。runtime testsを含むcandidate suite PASS。main統合後、自然wakeで`resource release deferred`が0になることを確認 |
| 13 | `CROWD-01` CrowdWorks finite laneを5分runtime boundへ揃える | CrowdWorks registry + owner | **統合候補 `b783051fd5` code/tests PASS**: Application/Reply/Paid/Reportへ300秒上限、registry fixtureとCrowdWorks tests PASS。main統合後、4 laneのtimeout/公式receiptを確認 |
| 14 | `MERCOR-01` Mercor finite laneを5分runtime boundへ揃える | Mercor registry + owner | **統合候補 `b783051fd5` code/tests PASS**: Application/Paid/Replyへ300秒上限、Mercor tests PASS。main統合後、CDP/human-gateの自然terminalと公式receiptを確認 |
| 15 | `MERCOR-02` 別taskの期限切れprovisioningをacquire時にbounded GC | CDP context lease | **統合候補 `b783051fd5` code/tests/live recovery PASS**: 期限切れ`job-search-daily`を対象1件reaped、Mercor parked contextは保持。main統合後、handshake timeoutとstale row再発を監視 |
| 16 | `PROD-02` Lancers Negotiate/Storefront/Paidを個別に閉じる | 各provider adapter | laneごとの公式receiptまたは明示的not-applicable、重複0 |
| 17 | `MARKET-02` CrowdWorksを同じshared kernelで検証 | CrowdWorks adapter/owner | 応募・契約の公式receiptまたはtruthful not-applicable |
| 18 | `MARKET-03` Mercorをhuman gate付きで検証 | Mercor adapter/owner | typed gate再開、公式application/contract/payment receipt |
| 19 | `MARKET-04` Coconalaを別workstream完了後に検証 | Coconala owner | 既存の4 laneごとの公式receipt、buyer readback、replay-zero |
| 20 | `CONTROL-01` registry外Browser provisionerの所有者分類とhandoff | control plane + provisioner owner | active profileを止めずにdoctorのunmanaged 0、owner/release/state/readbackを登録 |
| 21 | `LOCAL-01/02` 14 Product Loopのlocal completion manifest | shared control plane + 各owner | unknown 0、未対応は明示状態、外部成功はreceipt限定 |
| 22 | `CLOUD-01/02/03` tenant分離・cloud Browser・phone-only経路 | cloud adapter | localと同じcontract、cloud canary、静かな通知、公式readback |
| 23 | `CLOUD-04` production昇格 | primary release owner | local gate、cloud gate、公式効果、replay-zeroの全PASS |

routine report、PID、exit 0、Telegram送信、テストgreenだけでは各項目を完了にしない。各項目の
最後に公式証拠がなければ、その項目は同じcursorに留まり、次のplatformを起動しない。

### Shared components and provider adapters

現在の構成は、完全な共有でも完全な分離でもありません。共有kernelとprovider専用adapterの
境界は次のように固定します。

| 層 | 共有するもの | platformごとに変えるもの |
|---|---|---|
| 目標・wake | goal revision、owner、wake、retry、停止条件 | 仕事の目的と入力データ |
| 資源 | resource admission、memory/disk pressure、queue、deferred state | provider/accountごとの上限値 |
| model | agent-runner、Responses API、context capsule、tool-call schema | 使用するskillとJSON schema |
| browser | owner lease、CDP health、headless、timeout、release | profile、CDP port、provider URL/DOM |
| effect | effect key、attempt、official readback、replay-zero | 応募・返信・掲載・納品のprovider操作 |
| 記録 | runtime event、graph、eval、内部control room | provider固有のreceipt parser |
| 通知 | 共通outbox、dedupe、human gate | 人間が必要な時の文面・リンク |

Lancersの現在の故障は、この境界が実装にも反映されていない例です。Apply/Reply/Storefront/
Paidは同じhost admissionを使いますが、Lancersの4収益laneが`borrow`のままだったため、
Coconala/Affiliateのownerがdeterministic枠を占有すると、Lancersはproviderへ到達する前に
`resource_capacity_busy`になりました。ApplyはさらにLancers専用browser接続のretry cleanupと
safety verifier timeoutを持っていませんでした。したがって、各laneを個別に再起動することが
解決策ではなく、共有kernelの資源分類と、Lancers adapterの接続境界を順に直す必要があります。

```mermaid
flowchart TD
  K[共有kernel\nqueue / admission / runner / browser lease / receipts] --> L[Lancers adapters\nApply / Reply / Storefront / Paid]
  K --> C[Coconala adapters\nApply / Reply / Storefront / Paid]
  K --> M[Mercor adapters]
  L --> LR[Lancers公式receipt]
  C --> CR[Coconala公式receipt]
  M --> MR[Mercor公式receipt]
  K --> G[graph / eval / internal report]
```

修正順序は、(1)共有kernelがownerを正しく分類・保留・再開する、(2)各provider adapterが同じ
browser/effect/readback契約を使う、(3)公式receiptとreplay-zeroを受けてから次のlaneへ進む、
とする。一つのproviderを直しただけで他のproviderが直ったとは扱わない。

### Platform differences and current read-only state

「共通部品を使う」とは、同じブラウザや同じログインを使い回すことではありません。各サイトは
専用のadapter、URL、DOM、アカウント、profile、公式receiptを持ち、共有kernelには typed な
状態と証拠だけを渡します。次の表は今回のread-only確認で固定した境界です。`未確認`は失敗の
証拠でも成功の証拠でもなく、公式readbackを取るまで未完了として扱います。

| platform | サイト固有の仕事と境界 | 共有kernelから使う部品 | 今回の状態（公式receipt基準） | 次の合格条件 |
|---|---|---|---|---|
| Coconala | 公開依頼→応募、購入前talkroom返信、自分のサービス掲載、購入済み納品。`coconala.com`のrequest/message/service/order route、専用profile | goal/wake、admission、context、browser lease、effect key、readback、通知outbox | 別workstreamが1案件を処理中。architecture workstreamはbrowser/account/TODOを変更しない。今回のcanaryで応募成功は主張しない | 案件ごとの公式応募/購入/納品receipt、buyer readback、replay-zero |
| Lancers | 公開案件→proposal、購入前会話、menu掲載、契約/納品。`www.lancers.jp`のwork/proposal/menu/myplan route、専用9227 CDP、safety verifier | Coconalaと同じtyped lifecycle・admission・effect/readback契約 | mainはPR #5257（0aba1191）まで統合済み。proposal 20件を公式ledger sequence 148〜167へ記録（重複0）。current `060446-f80de2ef`とowner installed/event SHAは不一致。Application直近は`entrypoint_exit_124`、Negotiate/Paid/Report/Work-syncはresource blocked、Storefrontは`entrypoint_exit_1`。統合候補 `b783051fd5`（lease + stale claim冪等化 + CrowdWorks/Mercor timeout + sparse release互換 + completion manifest/CLI）は未統合。pending 101件、paid/delivery receipt 0。protocol v2はversion 2で有効 | 候補受入→main統合後にownerを同一SHAへ揃える→同時接続0/stale warning 0→pendingを1 sliceずつ処理→各lane公式receipt/readback→replay-zero |
| CrowdWorks | 公開案件→応募→契約→納品。応募・契約のprovider語彙は専用adapterで保持し、Coconala/Lancersの掲載laneを仮定しない | goal/context、admission、provider-browser.lock、effect fence、human gate、receipt/eval | 9228/profileのprovider-browser.lockは存在するが、4 ownerは旧release `2a53ce25`。直近はApplication/Paidが`resource_capacity_busy`、Reply/Reportが`resource_control_busy`。公式応募・契約・収益receiptは未確認。timeout修正は候補 `bf8ab51b34` | 候補受入→main統合後に4 laneの自然terminal→公式応募/契約receiptまたはtruthful not-applicable→重複なし |
| Mercor | 応募→本人確認/面接/録画などのhuman gate→契約・報酬。identity/interview/mediaの外部状態を専用adapterで扱う | agent-runner、context capsule、human gate、通知outbox、effect/readback、revenue/cost graph | Application installed 2ff/event e789、Paid/Reply installed/event 2ff。Paid/Replyはresource blocked、過去Application/ReplyにはCDP handshake timeout・logged_out。期限切れprovisioningは対象1件GC済み。3 finite laneのtimeoutとauto-GCは候補 `bf8ab51b34`、公式application/contract/payment receiptは未確認。architecture workstreamはMercorの認証・面接を操作しない | 候補受入→main統合後にCDP/human gate自然terminal→公式application/contract/payment receipt→費用上限内・replay-zero |

したがって、前回のLancers失敗は「各サイトの処理内容が同じだから」ではありません。共通kernelの
入口で (a) 収益laneが`borrow`のまま容量を奪われ、(b) launchdが旧releaseを指し、(c) 失敗した
Playwright/CDP接続の後始末とsafety verifierの時間上限が不足し、providerの応募画面まで到達
できなかったことが原因です。`browser_unavailable`、`account_unavailable`、`safety_check_failed`
というTelegram文面だけでは、外部応募の成功/失敗を確定できません。必ず同じwakeのofficial
receipt、readback、effect keyの再実行0件を揃えます。

```mermaid
flowchart LR
  K[共有kernel\n状態・容量・再試行・記録] --> C[Coconala adapter\n依頼/DM/掲載/納品]
  K --> L[Lancers adapter\n案件/proposal/menu/契約]
  K --> W[CrowdWorks adapter\n案件/応募/契約/納品]
  K --> M[Mercor adapter\n応募/本人確認/面接/報酬]
  C --> CR[サイト公式receipt]
  L --> LR[サイト公式receipt]
  W --> WR[サイト公式receipt]
  M --> MR[サイト公式receipt + human gate]
  CR & LR & WR & MR --> E[readback + replay-zero\n→ 初めて成功扱い]
```

## 1. Overview (What & Why)

Life Manager presents fourteen user-facing Product Loops, while
`config/loop-registry.json` currently contains 165 lifecycle and support jobs. The current registry
snapshot contains 26 keep-alive jobs, 39 five-minute jobs, and six browser-owner jobs. The count is
not itself the failure: the failure is treating a growing job inventory as an unbounded set of
independent workers.

The current runtime already has a useful finite wake shape:

```text
observe -> assemble context -> model decision -> bounded skill -> persist -> sleep
```

It also has partial graph projections (`context-graph.js`, `intent-graph.js`) and deterministic
domain evals under `apps/life-manager/eval/`. They do not yet form one cross-loop control plane that
can answer which goal is blocked, what evidence proves an effect, which human gate is due, or whether
a candidate release is better than its baseline.

The Coconala TODO records the operational consequence: browser and ledger critical sections have
serialized unrelated work, and host load/swap saturation has admitted work despite a percentage-only
memory signal. Repeatedly starting or restarting loops cannot repair this class of failure and can
destroy authenticated browser ownership.

The target is one owner-aware Life Manager control plane that runs finite wakes through bounded
resource admission, compiles small provenance-bound context capsules, projects an auditable graph,
evaluates behavior against frozen baselines, represents human work as resumable typed gates, and
feeds verified outcomes into bounded self-improvement. Local and cloud remain host adapters for the
same product recipes and evidence contracts.

## 2. Acceptance Criteria

### A. Product loops and lifecycle jobs have separate identities

Every registry entry has a stable `product_loop_id`, `job_id`, `owner_id`, `resource_class`,
`effect_class`, and `cadence`. Product-loop reporting groups jobs without merging their ownership,
state, or receipts. Existing registry IDs remain addressable during migration.

### B. Admission is bounded and durable

One repository-owned admission boundary limits active work by resource class, provider/account,
browser profile, model transport, and host capacity. A deferred job writes a durable
`resource_admission_deferred` state with reason, owner, and `next_eligible_at`; it is resumed by a
later wake. Admission never holds the global ledger/vault lock across CDP, network, model, or context
disposal I/O. No feature uses `start all` as a production acceptance shortcut.

### C. Every wake has an evidence contract

Each finite wake persists `wake_id`, owner, goal revision, context hash, selected capability, attempt,
effect key, status, failure layer, official readback pointer, and next eligible time. A process PID,
exit code, Telegram message, or dashboard row never closes a business goal without authoritative
readback.

### D. Context is a bounded capsule, not a transcript

The wake context contains `goal`, `owner`, `sources[]`, `decisions[]`, `open_questions[]`, explicit
budget, freshness, and a content hash. Large logs/artifacts are stored by hash with bounded excerpts.
Mutable provider state is refreshed immediately before an effect. Separate owners share approved facts,
never mutable transcripts, browser sessions, or credentials.

### E. Graph is a rebuildable projection of the ledger

An append-only fact source remains authoritative. A versioned, idempotent projection exposes at least
the node kinds `goal`, `capability`, `opportunity`, `artifact`, `effect`, `receipt`, `human_gate`,
`revenue`, and `resource`. Edges use a closed vocabulary (`requires`, `produced_by`, `sent_to`,
`proved_by`, `earned`, `blocked_by`, `supersedes`) and carry source fact, authority, observed time,
confidence, and content hash. Graph queries are bounded and return source pointers plus stale/unknown
markers. Graph output cannot authorize an effect.

### F. Evals gate behavior and promotion

Every shared recipe and provider adapter has versioned JSONL cases for canonical, boundary,
adversarial, and previous-failure behavior. Runs record candidate/baseline hashes, model, prompt,
tool fixture, seed, latency, cost, per-case score, trace pointers, and errors. Tuning and held-out
cases are separate. Deterministic safety/replay/schema checks run before semantic grading. A candidate
cannot promote when held-out behavior, safety, cost, latency, or required live evidence regresses;
the evaluator never mutates production.

### G. Human work is a typed gate, not a side channel

Provider capabilities declare one of `autonomous`, `human_required`, or `prohibited` for the current
owner and account policy. A human-required transition writes one stable `human_gate_id` containing
exact action, work-item identity, evidence, deadline, owner, and Telegram delivery/outbox ID. The
worker completes all preceding reversible work, sends the gate once, enters `waiting_human`, and
resumes the same owner/effect namespace after the answer. Missing, expired, or contradictory answers
remain typed blockers; no guessed identity, interview, recording, KYC, or approval is fabricated.

### H. Observability separates health from business truth

The runtime emits versioned lifecycle events/spans for wake, decision, tool, effect, readback, wait,
and finish with bounded IDs and redacted attributes. Metrics cover admission depth, active resources,
memory/load/swap pressure, context bytes, model cost/latency, retries, human-gate age, and
effect/readback/replay counts. Durable ledgers and official provider receipts remain the business
authority; telemetry degradation is observable but non-destructive.

### I. Recursive self-improvement is bounded and reversible

Every candidate skill/prompt/model/tool change records a hypothesis, frozen baseline, changed hashes,
train/held-out split, safety tripwires, promotion decision, and rollback pointer. The loop may propose
changes to recipes and skills, but cannot rewrite constitution, identity, credentials, permissions,
effect/readback rules, or evaluator gates. Promotion is a separate owner action after all gates pass.

### J. Local and cloud are one implementation

Both hosts use the same product loop ID, recipe, capability/effect contract, graph vocabulary,
evaluation contract, receipt schema, and human-gate semantics. Only supervisor, storage, secret, and
browser transport adapters differ. A second local/cloud business implementation is a contract failure.

### J1. Two Deployment Modes and local-first promotion

Life Manager exposes two deployment modes for the same implementation:

1. **Local mode:** a single owner runs the control plane, private state, and host adapters on a local
   Mac or Linux machine. It is the development, self-hosted, and recovery mode. Autonomous browser work
   uses headless sessions; the user's screen is reserved for debugging and human gates.
2. **Cloud mode:** the hosted control plane, tenant-scoped durable store, worker pool, and Steel Browser
   sessions run continuously in the cloud. A phone and Telegram/app are sufficient for the user. Cloud
   is the production expansion mode, not a fork of the business code.

The **local completion gate** MUST pass before cloud promotion: every advertised Product Loop has one
canonical owner and release, no stale/duplicate scheduler, bounded resource admission, a context and
receipt contract, private internal reporting, and either a verified official effect or an explicit
`setup_required`/`not_applicable` capability state. No enabled owner may remain `unknown`, silently
failing, or dependent on a visible desktop window. Cloud promotion copies the immutable source and
contracts, creates fresh tenant-scoped state, runs one cloud canary, and proves the same official
readback/replay-zero behavior. It never copies local credentials, browser sessions, or mutable logs.

Local and cloud remain available as user choices after promotion. `phone-only` use is the default cloud
experience; local mode remains a self-hosted option and a recovery path. Both modes use the same
implementation, and only their host adapters differ. Ordinary wakes do not require the user to restate
a goal. User involvement is limited to an explicit typed human gate or a deliberate
policy/permission change; ordinary wakes continue without conversation.

The rule is: **no cloud promotion before local acceptance**.

### J2. Parallel Workstream Boundary

The active marketplace owner exclusively edits `skills/earn/gig/TODO.md` and provider-owned files
while its vertical acceptance is in progress. Architecture work proceeds in a separate worktree on
skills, specifications, contract fixtures, and read-only diagnostics. A shared-file overlap check is
required before changing `config/loop-registry.json`, `runtime/loop`, `skills/browser`,
`skills/_shared/marketplace-core`, or production state. No workstream edits the active TODO or
provider-owned files concurrently, and no workstream changes a live browser/account/ledger owner
owned by another workstream.

### J3. Fourteen-Loop Remediation Matrix

Every Product Loop uses the same shared kernel for goal, context, admission, effect fencing, official
readback, receipts, internal reporting, evaluation, and recovery. Only the provider/product adapter
owns its external vocabulary and mutation. The matrix assigns one workstream owner and one completion
condition per Product Loop; the completion condition is explicit and an old receipt never closes a current owner.

| # | Product Loop | First repair focus | Shared-kernel use | Completion condition | Workstream owner |
|---:|---|---|---|---|---|
| 1 | Coconala | source/form health, browser ownership, four-lane cursor | Apply/Reply/Storefront/Paid, effect fence, readback | official application or funded work receipt plus replay-zero | marketplace TODO owner |
| 2 | Lancers | account/session, CDP health, proposal form | same Apply/Reply/Paid/Storefront contracts | official proposal/contract receipt plus replay-zero | marketplace TODO owner |
| 3 | CrowdWorks | profile/dependency completeness, browser lock | shared application and contract lifecycle | official proposal or truthful not-applicable receipt | marketplace TODO owner |
| 4 | Writer | opportunity, authoring, publisher, payment lineage | goal/artifact/publish/settlement receipts | publisher confirmation and attributable payment receipt | Writer owner |
| 5 | Affiliate | source freshness, attribution, publish readback | opportunity/effect/link/revenue ledger | official publication and attributed conversion evidence | Affiliate owner |
| 6 | Investment | mode separation, risk budget, order reconciliation | goal/effect/payment readback and kill boundary | explicit paper/shadow/live mode and broker receipt | Investment owner |
| 7 | Agent Economy | isolated identity, wallet, compute cost, reserve | treasury/effect/revenue/cost graph | verified net-positive or explicit setup state | economy owner |
| 8 | Job Hunter | provider discovery, profile/resume, Gmail confirmation | application receipt, human gate, inbox reconciliation | official application confirmation or typed human wait | Job Hunter owner |
| 9 | Fundraiser | eligibility, deadline, form and submission receipt | opportunity/application/artifact/readback chain | official intake receipt or explicit ineligible state | Fundraiser owner |
| 10 | Connector | event source, Calendar conflict, registration readback | event goal, calendar, effect, ticket receipt | official registration/ticket or truthful no-op receipt | Connector owner |
| 11 | Self-Build | feedback→test→patch→evaluation→release | issue/goal/candidate/promotion/rollback graph | reviewed immutable release and regression PASS | self-build owner |
| 12 | Mobile Apps | product manifest, build/sign, store and marketing receipts | artifact/release/publication/revenue chain | store/provider receipt or explicit setup state | mobile-app owner |
| 13 | Capafy | product/sales/outcome/audience resource separation | goal/effect/attribution/Telegram contract | official business outcome or explicit setup state | Capafy owner |
| 14 | CFO | source reconciliation, payout matching, report noise | revenue/cost/balance/evidence graph | verified financial snapshot; unknown never becomes zero | CFO owner |

The marketplace TODO workstream owns rows 1–3 and the existing `skills/earn/gig/TODO.md`; other
owners continue their rows independently. The architecture workstream owns only the shared contracts,
skills, specifications, fixtures, and read-only diagnostics until a shared-file overlap check approves
runtime changes.

### K. User Communication Contract

Every wake, retry, evaluation, health signal, and diagnostic remains in the private ledger/control room
by default. Telegram receives only a human action, urgent safety/credential issue, material verified
outcome, or persistent blocker after bounded recovery. A routine wake or healthy no-op produces zero
Telegram messages. Human-gate messages are idempotent by stable event key; identical blocker messages
are suppressed until state changes or the 24-hour reminder boundary. User messages contain only the
short reason, exact action, deadline, and link/evidence needed to act—never raw logs, prompts, secrets,
or unnecessary personal data.

The allowed Telegram event kinds are `human_action_required`, `urgent_safety`, `material_outcome`,
and `persistent_blocker`; every other lifecycle event remains internal.

### L. Model Runtime Boundary

There are three distinct OpenAI layers:

1. **Responses API:** the low-level model request. The application owns the loop, tool dispatch, and
   state.
2. **Agents SDK:** a local Python runtime that can own turns, tools, guardrails, handoffs, sessions,
   and tracing around Responses API calls.
3. **Agents API:** OpenAI's hosted **Codex harness** and infrastructure. It can create a cloud agent,
   attach tools and a hosted sandbox, compact long sessions, search tools on demand, and run bounded
   subagents. The [official Agents API announcement](https://openai.com/ja-JP/index/introducing-the-agents-api/)
   describes these managed capabilities and the choice of OpenAI-hosted or partner environments.

The core Life Manager model transport uses the Responses API through the existing brain adapter because
Life Manager owns the loop, tool dispatch, leases, context capsule, ledger, and provider readback. The
official [Agents SDK/Responses API guidance](https://openai.github.io/openai-agents-python/) says the
Responses API is appropriate when the application owns loop/tool/state handling, while the Agents SDK
is appropriate when its runtime should manage turns, tools, guardrails, handoffs, or sessions.

Agents SDK may be used only inside an isolated evaluator or repair worker behind the same owner,
context, budget, and evidence contracts. Agents API is used in a separate cloud maintenance pilot for
read-only diagnosis, evaluation, skill drafting, and architecture research. Its hosted sandbox receives
only a **read-only release**, approved skills, bounded fixtures, and a private output directory. It
never receives provider credentials, browser sessions, payment keys, or permission to perform a
marketplace effect. It must not create a second scheduler, provider-effect owner, or authoritative
memory store. If SDK or Agents API tracing is enabled, sensitive capture is disabled or routed to a
private exporter with `trace_include_sensitive_data=False`; the official [tracing guidance](https://openai.github.io/openai-agents-python/tracing/)
warns that generation and function spans can contain sensitive inputs/outputs.

Long analysis may use Responses `background=true` with a persisted response ID and next-wake polling or
webhook. A background response may not hold a browser/effect lease or perform a provider mutation. The
official [Responses create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
defines background execution, context management, tool-call limits, and response storage controls;
privacy-sensitive work uses the repository-owned capsule and explicit storage policy instead of
implicitly retaining an unbounded conversation.

### M. No-babysitting Operation

Each failure creates one durable issue with owner, repair class, retry budget, next eligible time,
last-good receipt, and escalation boundary. A supervisor resumes queued issues after process exit and
applies only the repair class permitted by the evidence. It continues independent work while one issue
waits for a human or external provider. A human is contacted only for an explicit human gate; all
other supported work, recovery, evaluation, and candidate promotion proceed without manual restarts.

### N. Agents API sandbox boundary

The hosted Agents API maintenance pilot is bounded by a signed task manifest containing owner, goal
revision, release hash, allowed skills, fixture hashes, maximum subagent count, time/token budget, and
output path. It returns a result ID, artifact hashes, trace pointers, and a promotion recommendation;
the Life Manager control plane performs all validation, graph projection, evaluation gates, and release
decisions. A hosted agent cannot modify the canonical repository, private state, credentials, browser
session, scheduler, or provider system directly.

### O. Browser Execution and Deployment

Browser automation runs headless by default so the user's screen is not occupied, but headless does
not mean zero memory: Chrome still creates browser/renderer processes and page JavaScript, DOM,
cookies, and storage consume resources. The [Chrome headless documentation](https://developer.chrome.com/docs/automation-and-testing/headless)
states that modern headless shares the Chrome implementation; capacity is therefore controlled by
session count, page count, timeouts, and measured memory rather than by the display flag alone.

The selected browser abstraction is [Steel Browser](https://github.com/steel-dev/steel-browser), used
through its session API and CDP connection. It manages browser processes, session state, cookies,
local/session storage, cleanup, and a viewer while remaining compatible with the existing Playwright/
Puppeteer adapters. Local and cloud use the same `BrowserSession` contract; only the endpoint,
secret store, and session storage adapter differ.

```text
local Mac today                 cloud target
----------------                ------------------------------
Life Manager queue              Life Manager control plane
        |                       tenant/owner work queue
Steel self-hosted Docker        Steel Cloud or self-hosted Steel
headless sessions               headless sessions on worker nodes
        |                       |
provider adapter via CDP        provider adapter via CDP
```

On the local Mac, retain one controlled browser service during migration and move non-human work to
headless Steel sessions; headed windows remain only for debugging or an explicit human gate. In the
cloud, create a tenant- and provider-scoped session on demand, park or release it after the finite
wake, persist only the declared authentication state, and attach a viewer to that same session when
human action is required. Never create a second session for the handoff. The session memory is scoped to
the owner and provider, not shared across users or unrelated loops.

Admission uses a measured concurrency limit (`concurrency_limit`) and per-session CPU, memory, page, wall-clock, and
inactivity budgets. It queues work when capacity is full and records a durable deferral; it does not
promise that a virtual computer eliminates memory crashes. A full `virtual computer`/desktop is not
the default for autonomous work because its guest OS and display stack add overhead. Use a remote
desktop such as Kasm only when a person must see or operate the same browser session.

[Firecracker](https://github.com/firecracker-microvm/firecracker) is the isolation reference for
untrusted repair/evaluation code, with a separate microVM and explicit resource limits; it is not a
one-VM-per-browser design. [Lightpanda](https://github.com/lightpanda-io/browser) is a low-memory,
headless discovery experiment whose Web API and Playwright compatibility remains partial/WIP; it
cannot perform a provider effect until a provider-specific read-only and official-readback suite
passes. Browserless is a comparison reference for queue/timeout ideas, not a deployment choice under
its SSPL/commercial licensing.

## 3. As-Is / To-Be

| Concern | As-Is (measured) | To-Be contract |
|---|---|---|
| Topology | 14 Product Loops backed by 165 registry jobs; 26 keep-alives and frequent interval jobs | Product loop is a logical goal stream; jobs are queued lifecycle work owned by one scheduler |
| Capacity | Memory/load pressure can admit work; browser/ledger I/O has caused cross-owner stalls | Resource-class admission, durable deferral, per-owner leases, and host-pressure telemetry |
| Wake | `runtime/loop/index.mjs` has finite wake/retry/sleep behavior, but context is still recent-ledger oriented | One wake contract with goal/context/effect/readback evidence and explicit next eligibility |
| Context | `runtime/loop/context.mjs` passes bounded fields and the last 20 ledger lines | Hash-bound source capsules with freshness and artifact offload |
| Browser | Visible Chromium and persistent owners consume host resources; browser choice is mixed across lanes | Headless Steel sessions with per-owner state, measured concurrency, timeout/cleanup, and same-session viewer handoff |
| Deployment | Local browser processes compete with the user's Mac and are hard to scale | Local Steel service during migration; cloud Steel sessions behind the same CDP/provider contract |
| Graph | Intent and calendar/context projections exist; no unified economic/effect dependency projection | Rebuildable cross-loop projection for planning and provenance; ledger/provider remain authoritative |
| Eval | Domain-specific deterministic eval files exist | Shared case/run/score/gate schema plus held-out and live-evidence promotion gates |
| Human loop | Mercor and marketplace gates exist in lane-specific work | Provider-neutral typed `human_gate` lifecycle and Telegram outbox idempotency |
| Learning | Self-eval and promotion helpers exist in separate areas | One candidate → baseline → eval → tripwire → promotion/rollback contract |
| Hosts | Local and cloud share a target architecture but portability is incomplete | Same recipes/contracts; host adapters own only infrastructure differences |

## 4. Target Architecture

```mermaid
flowchart TD
    G[Durable goals and revisions] --> P[Graph projection and competency queries]
    P --> Q[Owner-aware work queue]
    Q --> A[Resource admission<br/>memory/load/browser/model budgets]
    A --> W[Finite wake worker]
    W --> C[Bounded context capsule]
    C --> M[Model chooses capability]
    M --> X[Leased provider effect]
    X --> R[Official readback + replay check]
    R --> L[Append-only ledger / receipt facts]
    L --> P
    L --> O[Observability events and metrics]
    L --> E[Eval dataset and promotion gate]
    W --> H[Typed human gate -> Telegram outbox]
    H --> W
    E --> N[New goal/skill candidate]
    N --> G
```

The scheduler is an alarm clock, not a second agent brain. The model chooses semantic work from the
loaded skill and available capabilities. Deterministic code owns admission, leases, schemas, effect
keys, retries, redaction, hashing, bookkeeping, and readback checks. The graph answers dependency and
provenance questions; it never substitutes for provider truth.

## 5. Test Matrix

| # | To-Be requirement | Test name | Cover |
|---:|---|---|---|
| 1 | Product-loop/job identity separation | `test_registry_product_and_job_identity` | OK: grouping preserves job ownership and receipts |
| 2 | Resource admission and durable deferral | `test_admission_defers_and_resumes_without_stampede` | OK: pressure/deadline/owner limits; sibling progress |
| 3 | Wake evidence contract | `test_wake_requires_effect_readback_or_typed_wait` | OK: PID/exit-only result rejected |
| 4 | Hash-bound context capsule | `test_context_capsule_budget_freshness_and_resume` | OK: offload, hashes, stale refresh, privacy |
| 5 | Rebuildable graph projection | `test_agent_graph_projection_is_idempotent_and_provenanced` | OK: replay, version, unknown/stale markers |
| 6 | Competency queries | `test_agent_graph_answers_blocker_receipt_and_gate_queries` | OK: bounded source-backed results |
| 7 | Eval and promotion gate | `test_candidate_gate_requires_heldout_safety_and_live_evidence` | OK: regression, tripwire, realism gap |
| 8 | Human gate lifecycle | `test_human_gate_delivery_resume_and_replay_zero` | OK: one Telegram outbox, same owner/effect |
| 9 | Observability schema/privacy | `test_runtime_events_redact_and_join_by_stable_ids` | OK: bounded attributes; health/effect separation |
| 10 | Recursive improvement boundary | `test_candidate_cannot_change_constitution_or_evidence_rules` | OK: rollback and immutable policy |
| 11 | Local/cloud parity | `test_host_adapters_share_loop_and_receipt_contract` | OK: infrastructure-only variation |
| 12 | Internal-first user communication | `test_routine_wakes_are_private_and_human_gates_are_idempotent` | OK: notification budget, stable keys, redaction |
| 13 | Responses API boundary | `test_model_adapter_persists_capsule_and_resumes_background_response` | OK: response ID, polling, no effect lease in background |
| 14 | Agents SDK isolation | `test_sdk_worker_cannot_create_scheduler_or_authoritative_state` | OK: bounded evaluator/repair-only use |
| 15 | No-babysitting supervisor | `test_issue_queue_recovers_or_escalates_without_manual_restart` | OK: retry budget, independent progress, typed escalation |
| 16 | Agents API sandbox boundary | `test_agents_api_task_manifest_and_readonly_release` | OK: bounded subagents, no credentials/effects, hashed outputs |
| 17 | Browser session mode and capacity | `test_browser_session_mode_capacity_and_handoff` | OK: headless default, session state, limits, viewer handoff, no duplicate session |
| 18 | Two deployment modes | `test_local_and_cloud_use_the_same_implementation_contract` | OK: host-only variation, tenant isolation, phone-only cloud path |
| 19 | Local-first promotion | `test_cloud_promotion_requires_local_completion_gate_and_canary` | OK: no unknown/stale owner, immutable source, official readback/replay-zero |

All tests are deterministic fixtures or read-only contract checks. External marketplace acceptance
remains a separate owner-scoped operation that requires the existing immutable-release,
official-readback, and replay-zero rules.

## 6. Boundaries

- Do not add a graph database before a measured traversal/concurrency need; begin with a local
  projection rebuilt from the existing append-only facts.
- Do not replace `config/loop-registry.json`, the shared runtime, provider adapters, or the existing
  effect reconciler with a parallel framework.
- Do not run or restart all 165 jobs to prove the design; use deterministic contention fixtures and
  targeted owner-scoped acceptance.
- Do not copy credentials, browser sessions, raw PII, full prompts, or unbounded provider payloads
  into graph, eval, telemetry, Git, or Telegram.
- Do not count applications, process health, eval scores, unrealized positions, or model claims as
  revenue; only attributable provider/payment receipts count.
- Do not let self-improvement modify identity, permissions, safety/evidence boundaries, or promotion
  gates.
- Do not create a fifth marketplace lane when Apply, Reply, Storefront, and Paid already own the
  lifecycle; add only a thin provider adapter and shared receipt mapping.
- Do not edit another worktree's active Coconala TODO while implementing this architecture.
- Do not send routine wake, retry, evaluation, health, or diagnostic reports to Telegram; retain them
  in the private control room and send only the contracted user-facing events.
- Do not replace the existing control plane with an Agents SDK scheduler or a second memory/session
  authority. Use the Responses API adapter for the core loop and isolate any SDK worker.
- Do not allow a background model response, webhook, or trace callback to hold a browser/effect lease
  or perform a provider mutation.
- Do not give an Agents API hosted sandbox provider credentials, browser sessions, canonical write
  access, scheduler control, or direct marketplace-effect tools. Use it only with a read-only release
  and bounded fixtures in the maintenance pilot.
- Do not equate headless mode, a virtual computer, or a remote browser with unlimited concurrency or
  zero memory use. Every session needs a measured limit, timeout, cleanup, and durable owner.
- Do not switch a provider's effect path to Lightpanda or a new browser service without read-only
  compatibility, authentication persistence, official readback, and replay-zero acceptance.
- Do not create a second browser session for a human handoff; attach the viewer to the existing leased
  session and resume the same owner.
- Do not promote cloud before the local completion gate passes; do not copy local mutable state,
  credentials, browser sessions, or logs into cloud.
- Do not maintain separate local and cloud business implementations. Only host adapters may differ.

## 7. Execution Steps

1. Add registry identity/resource-class fixtures and measure the current 165-job inventory without
   changing production state.
2. Add the bounded admission contract to the existing runtime control path; prove deferred/resumed
   owners and sibling progress under synthetic memory, load, browser, and ledger contention.
3. Replace recent-ledger-only wake assembly with the hash-bound context capsule while preserving the
   existing redaction and effect-reconciliation seams.
4. Add the pure cross-loop graph projector and competency queries; rebuild it from ledger fixtures and
   keep provider readback as the authority boundary.
5. Add the shared eval case/run/score/gate schema and migrate one marketplace recipe plus one
   non-marketplace loop before expanding coverage.
6. Route Mercor-style identity/interview/media actions through the provider-neutral human-gate
   contract and prove one notification, resumable wake, and replay-zero fixture.
7. Extend lifecycle telemetry/resource metrics and connect traces, receipts, graph facts, and eval
   runs by stable hashes and IDs.
8. Enable bounded skill/prompt candidate promotion only after baseline, held-out, safety, and live
   evidence gates pass; record rollback and the generalized lesson.
9. Re-run focused runtime, graph, eval, human-gate, and host-parity tests, then perform targeted
   immutable-release acceptance for one owner at a time. Update the active TODO only from measured
   receipts.
10. Add the private control-room projection and notification policy; prove routine wakes stay private,
    human gates are delivered once, and persistent blockers are rate-limited.
11. Add the Responses API brain adapter with explicit capsule/hash, tool-call, background, polling,
    storage, timeout, and cost contracts; preserve the existing provider effect owner.
12. If an evaluator or repair worker needs Agents SDK, wrap it behind a bounded adapter with isolated
    session/evidence and disabled sensitive trace capture; prove it cannot schedule or mutate a provider.
13. Run the Agents API maintenance pilot against a read-only release and bounded fixture, verify the
    task manifest, result/artifact hashes, no credential/effect access, and import only its recommendation.
14. Run the no-babysitting supervisor fixture, then targeted immutable-release acceptance and update
    the active TODO only from official receipts.
15. Implement the provider-neutral browser-session interface against Steel, preserving the current
    CDP/Playwright adapter contract and explicit session ownership.
16. Run headless compatibility and measured memory/concurrency acceptance for one read-only provider,
    then one effectful provider with official readback and replay-zero; keep a headed/remote-view path
    only for human gates and debugging.
17. Use Firecracker only for untrusted repair/evaluation execution and run Lightpanda only as a
    read-only discovery experiment; record the license and compatibility decision before any promotion.
18. Complete the local completion gate for every advertised Product Loop, including owner/release
    readback, resource admission, private reporting, official effect/readback or explicit capability
    state, and replay-zero where an effect exists.
19. Promote the identical immutable source to cloud, provision tenant-scoped state and Steel sessions,
    run one canary per supported resource class, prove official readback/replay-zero, and expose the
    phone-only notification/control path before enabling broader cloud capacity.

## E2E Judgment

| Item | Value |
|---|---|
| UI変更 | なし |
| 結論 | Maestro: 不要 — this specification changes runtime contracts and worker control, not iOS UI |
