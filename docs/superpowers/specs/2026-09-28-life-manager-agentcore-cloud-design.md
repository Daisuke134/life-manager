# Life Manager Cloud Runtime Design

**Status:** T11 Cloud版のprovider・実行単位・状態所有・無料導線・販売条件の正本

**Decision:** Cloud architectureは確定済みであり、再設計しない。Railway API、Inngest、Supabase PostgreSQL、Stripeをprovider-neutralな制御面として再利用し、仕事がある時だけtenant専用の隔離RuntimeとBrowserを起動する。**v1の最短実測候補はRailway Sandbox＋既存Steel**とし、AWS Bedrock AgentCore Runtime/Browser/Profile/Identityを全部入りの基準実装、Browserbase Contextsをmanaged browser代替、DigitalOcean Managed Agentsを第三候補にする。AWSはCloudFormation、S3、CloudWatch Logs、Cost Explorerの購読が未有効なので待たず、既に認証済みのRailwayでlive canaryを先行する。live isolation、no-ask、browser continuity、teardown、agent parity、公式cost receiptを全部通した構成だけをv1へ採用する。provider選択が変わってもbusiness kernel、job state machine、database、billing、UXは変えない。

**Implementation plan:** `docs/superpowers/plans/2026-09-28-life-manager-agentcore-cloud.md`

**Current cursor:** A24。制御面、same-kernel runtime、dispatcher、browser/identity adapter、no-human policy、cost ledger、Free onboarding、二session isolation/browser canary、agent parity CLI、promotion gate、固定順migration replayはlocal/isolated PostgreSQLで完成している。AWS Account APIは`PENDING_ACTIVATION`を返し、signup画面はFree planの支払方法登録step 3/5で`You have reached your limit of attempts to add a payment method`を返す。Support caseは開設済みであり、解除またはexact safe retry instructionまでカードを再送しない。DigitalOceanはAPI token未取得だが、Railway CLI/accountと既存Steel serviceは利用可能である。Railway Sandbox CLIは利用可能だがexperimentalであり、最初のread-only listはMac Data volume残量575 MiBによる`No space left on device`で未完了である。次は安全にlocal headroomを戻し、Railway Sandbox＋Steelで実provider receiptを取る。local PASSをcloud完了とは数えない。

### 0.1 固定済みの完成architecture

```mermaid
flowchart LR
  U[利用者<br/>Telegram / Web / phone only] --> API[Railway API<br/>tenant auth・goal・status]
  API --> PG[(Supabase PostgreSQL<br/>job・lease・checkpoint・receipt・cost)]
  API --> Q[Inngest<br/>schedule・retry・tenant concurrency 1]
  Q --> D[Cloud dispatcher<br/>release SHA・budget・effect fence]
  D --> R[tenant専用Runtime<br/>v1: Railway Sandbox候補]
  R --> K[既存Life Manager business kernel<br/>local/cloud共通]
  R --> B[隔離Browser<br/>v1: 既存Steel候補]
  B --> BP[tenant/provider別browser state]
  R --> ID[agent-owned identity / secret broker]
  K --> PG
  PG --> BILL[Stripe entitlement + CFO contribution ledger]
```

- backend/control planeは既存Railway API、Inngest、Supabase PostgreSQLで固定する。
- browserはagent-ownedで、tenantごとにwriter 1つ、cookie/local storageを次の有限jobへ継続する。
- Runtimeは利用者ごとの永久VMではなく、active job中だけ専用container/microVMを持つ。
- durable truthはVMのRAMではなくPostgreSQL、browser state、opaque identity ref、公式receiptに置く。
- v1はRailway Sandbox＋Steelを先に実測し、一つの固定構成だけを採用する。AWS、Browserbase、DigitalOceanへ通常jobを同時送信しない。
- 人間credential、approval、resume、CAPTCHA、KYCを通常jobの成功条件にしない。該当jobはterminal `not_applicable`にし、他のeligible jobを継続する。

### 0.2 残りTODO — この順序が正本

1. **Macの実行余地を安全に戻す。** 保護対象とproject stateを触らず、再生成可能cache/logだけを特定して十分な空きを作り、`railway sandbox list --json`を再実行する。
2. **Railway Sandbox provider adapterを最小追加する。** 既存Railway認証、TypeScript SDK/CLI、project private networkを使い、create/exec/checkpoint/destroy/list/cost readbackだけを既存provider contractへ写像する。business kernelを複製しない。
3. **A24 infrastructure canaryをlive実行する。** Railwayで2 tenant sandbox、workspace隔離、既存Steelの同一profile継続、no-ask、人間入力0、両sandbox destroy→active 0、前後usageを公式readbackで確認する。
4. **A24 agent parityをlive実行する。** `HEAD == origin/main == candidate SHA`を満たすreleaseで既存business kernel fixtureを実行し、local/cloudのreceipt hashとevidence hash、replay-zeroを一致させる。
5. **Immutable releaseをpromoteする。** CL00–CL04、provider receipt、cost、old session 0、rollback targetをpromotion gateへ渡し、main由来の1 releaseだけを選ぶ。
6. **Production migrationを固定順で適用する。** runtime base → identity refs → no-human browser → cost reservations → Free onboarding。二回目のschema SHA一致と公式DB readbackを得る。
7. **内部tenantでphone-only end-to-endを完走する。** no-card Free onboarding → goal → cloud job → verified result → Telegram report。human input 0、external spend 0、session leak 0を確認する。
8. **A25で5人のFree cohortを完走する。** cross-tenant leak 0、duplicate effect 0、cost cap breach 0、unbounded session 0と、4 journeyのlatency/costを測る。
9. **A26で最初の$49 Founding Proを販売する。** first verified result後だけcheckoutを提示し、Stripe receipt、entitlement、cancel/refund、1 user contributionを公式readbackする。
10. **A27–A28で25人へ拡大し、eval/self-improvementを回す。** activation、retention、conversion、p50/p75/p95、actual cost、settled contributionを基準にcandidateをcanary/rollbackする。
11. **A29でMuse Connectorを追加する。** Life Manager APIとcloud coreが安定した後のdistribution channelであり、runtimeの代替にはしない。

## 1. このspecが固定すること

これまでのT11は「worker pool + Steel Browser」までしか決めておらず、次が未決定だった。

- 利用者ごとに本当に常時VMを持つのか
- loopを誰が起こし、重複実行をどう防ぐのか
- VM停止後に何を正本として再開するのか
- OAuth/CAPTCHAをスマホだけでどう完了するのか
- 無料利用者のクラウド費をどう制限するのか
- Meta Muse本体のSecure VMから何を学び、Muse Connectorをどう分離するのか

本specでこの曖昧さを終わらせる。以後、provider変更は本specのDecision gateを満たす証拠がある場合だけ行い、会話ごとには変更しない。

### 1.1 No-human-loop invariant

Life Managerは通常のjobで利用者に許可・承認・判断を求めない。`ask`、`approve`、`human_wait`はCloud productの通常stateに存在しない。

- effect fenceは人の承認待ちではない。決定的policy、spend cap、idempotency key、最新state、公式receipt/readbackが自動でallow、deny、reconcileを決める。
- policy内のactionは質問せず実行する。policy外のactionは質問せず`policy_denied`として閉じ、別のeligible jobを続ける。
- 人間のcredential、login、OAuth、CAPTCHA、2FA、3DS、KYC、面接、署名を要求する経路は既定product loopへ入れない。agent-owned identity/APIで完結する代替を選び、無ければ`not_applicable: requires_human_principal`でterminalにして別のeligible jobを続ける。
- shared browserの閲覧、emergency stop、利用者が自発的に始めるbreak-glass controlは観測・復旧面として提供できる。ただしagent writerをleaseで停止して単一ownerにし、Life Managerの完了・収益・成功、credential取得、resume条件には数えない。待機state、接続依頼、approve/resume callbackを通常loopに作らない。

## 2. 単一推奨

### 2.1 答え

Life Managerにはクラウド計算機が必要である。ただし、**利用者ごとに24時間起動し続ける1台のVMは不要**である。v1では既存制御面と同じRailwayのSandboxを有限job用のCloud Computerにする。

各利用者は1つの「論理Cloud Computer」を持つ。仕事がある間だけ、そのtenant専用Railway Sandbox VMを起動する。同じtenantの仕事は同時に1件だけ実行する。停止中の正本はVMのRAMではなく、Supabase PostgreSQL、object evidence、Steel browser profile、server-side secret vaultに置く。次のwakeではcheckpointまたはimmutable templateから新しい隔離VMを安全に再構成する。AWSへ移行してもこの所有境界は変えない。

```mermaid
flowchart LR
  U[利用者: Telegram / Web] --> API[既存Railway API]
  API --> PG[(Supabase PostgreSQL<br/>tenant・goal・job・receipt・cost)]
  API --> Q[既存Inngest<br/>schedule・retry・tenant concurrency=1]
  Q --> D[Cloud dispatcher<br/>lease・budget・release SHA gate]
  D --> R[Railway Sandbox<br/>active jobごとの専用VM]
  R --> G[既存API / MCP tools]
  R --> B[既存Steel Browser<br/>job session]
  B <--> P[tenant/provider別<br/>Browser Profile]
  R --> I[server-side vault<br/>agent-owned API credential]
  R --> E[(object evidence / replay)]
  R --> PG
  PG --> S[Stripe entitlement + CFO P&L]
```

### 2.2 「ユーザーごとにVMか」の正確な答え

- activeな実行中は、各tenant jobが専用Railway Sandbox VMを持つ。
- idle中はmicroVMを保持しない。計算料金を止める。
- tenantごとに同時active runtimeは最大1つ。同じ利用者の複数loopはqueueで直列化する。
- Browserはruntimeとは別の隔離sessionで、ログイン状態だけtenant/provider別Browser Profileへ保存する。
- 長時間の仕事は1つのVMに居座らせない。checkpointをPostgreSQL/object storageへ書き、次の有限wakeへ分割する。
- runtime session ID、browser session ID、profile IDは状態の参照であり、business truthではない。

これはGrok BotやMuseの「自分専用クラウドコンピュータ」と同じ利用者体験を与えながら、永続VMのコストと単一障害点を避ける。

Meta Museは比較対象として公式に、各利用者から独立したpersistent isolated Linux VM、full browser、filesystem、terminal、generated tools、Secure Credentials Store、schedule/event driven background workを持つ。ここでいうpersistentは同じ人格、files、browser、memory、taskが継続する利用者契約であり、idle CPUを24時間占有することまでは意味しない。Life Managerはこの利用者契約を採用し、低層computeはfinite AgentCore sessionと外部durable stateで実装する。

### 2.3 既存loopを作り直さない境界

Cloud版は新しいagentをもう1体作らない。既存Life Managerのloopを、別のhostから呼ぶ。

| 既存のまま再利用するもの | Cloud用に追加する薄い境界 |
|---|---|
| goal、business rule、effect fence、receipt判定、`lm_runtime_jobs` state machine | provider-neutral request/response envelope |
| Inngestのwake/retryとtenant別直列化 | Railway Sandbox runtime adapter |
| PostgreSQLのjob/checkpoint/receipt | tenant→runtime/profile/usageのprovider ID map |
| 既存browser task contract | v1 Steel adapter。Browserbase/AgentCore Browserは同じcontractの代替 |
| Stripe webhook entitlement | `free-v1` / `founding-pro-v1` admission policy |

local版とCloud版の差は「誰が起こすか」「どこで隔離実行するか」「provider IDをどう保存するか」だけにする。business kernelをcopyしない。同じtask capsuleを同じkernel SHAへ渡し、canonical receipt/evidence hashが一致しなければCL01失敗である。

`browser-session-lease`はprovider-neutral contractとしてtenantごとにbrowser ownerを1つへ制限する。既存Stagehand/Steel driverをv1 canaryで使い、実サイト互換性が失敗した場合だけBrowserbase Contexts、AWS解除後だけAgentCore Browserを同じcontractで再評価する。

## 3. 調査した選択肢

### 3.1 一次資料で確認した事実

| 選択肢 | 確認した事実 | 判断 |
|---|---|---|
| [AWS Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html) | 各user sessionは専用microVM。任意framework/model、最大8時間、非同期処理、消費量課金。GAでTokyo対応 | 全部入り基準。account解除後の移行候補 |
| [AgentCore Browser](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-tool.html) / [Browser Profiles](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-profiles.html) | 隔離browser、agent-owned cookie/local storageをprofileへ保存、CloudTrail/recording | 全部入り基準。account解除後の移行候補 |
| [AgentCore Identity](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-overview.html) | inbound identity、outbound OAuth/API keyを一元管理し、credentialをmodel contextへ置かない | 全部入り基準。account解除後の移行候補 |
| [AgentCore pricing](https://aws.amazon.com/bedrock/agentcore/pricing/) | 最低料金・前払いなし。Runtime V2はCPU $0.1276/vCPU-hour、memory $0.0169/GB-hour、BrowserはCPU $0.0895/vCPU-hour、memory $0.00945/GB-hour | 無料枠をhard budgetで実現可能 |
| [Railway Sandboxes](https://railway.com/sandboxes) / [pricing](https://railway.com/pricing) | API/CLI/TypeScript SDKで作る隔離Linux VM。checkpoint、fork、private network、自動破棄、4地域。CPUとmemoryは秒課金で各約$50/month相当、公式例の20分・1GB・平均0.3 vCPUは約$0.03。CLIはexperimental/API変更可能と明記 | **v1最短canary候補**。既存Railway account/control plane/Steelを再利用できるが、production採用はlive gate通過後だけ |
| [Browserbase Contexts](https://docs.browserbase.com/platform/browser/core-features/contexts) / [pricing](https://www.browserbase.com/pricing) | cookie、localStorage、IndexedDB等を暗号化してsession間で永続化。managed browser、recording、proxy、CAPTCHA対応。100時間後は$0.12/browser-hourのplan例 | Steel実サイト互換性が落ちる場合のmanaged browser代替。Runtimeの代替ではない |
| [DigitalOcean Managed Agents](https://docs.digitalocean.com/products/managed-agents/agent-harness-runtime/concepts/architecture/) | 1 session = 1 microVM、pause/resume、Chromium、Action Gateway、tenantごとにsessionを作れる | 第三候補 |
| [DigitalOcean limits](https://docs.digitalocean.com/products/managed-agents/agent-harness-runtime/details/limits/) / [triggers](https://docs.digitalocean.com/products/managed-agents/agent-harness-runtime/how-to/run-agents-with-triggers/) / [environment spec](https://docs.digitalocean.com/products/managed-agents/agent-harness-runtime/reference/environment-spec/) | public preview、最大100 active sessions、pause中もslotを使う。fresh/reuse trigger、VPC/subnet、egress allowlist、明示allow/denyを持つ。triggerで`ask`はcreate時拒否されるが、reuse sessionに残ったruntime promptはauto-approvedされ得るため`ask`を安全策にしてはいけない | AWS activation期限超過後の実測fallback。`allow`＋明示`deny`、HITL reject、remove後list 0、billing recordを必須にする |
| [Google Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale) | managed runtime、sessions、Memory Bank、evaluation、tracing、code/computer-use sandbox、IAMを持つ | 強い全部入り代替。ただしtenant別の永続browser login profile契約と単純なend-to-end原価を確認できずv1不採用 |
| [Microsoft Foundry Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/overview) | hosted container、session state、VM-isolated sandbox、managed identityを持つ | 強い代替。ただしmanaged browser profileとagent-owned outbound identityが一体化していないため不採用 |
| [E2B persistence](https://e2b.dev/docs/sandbox/persistence) / [pricing](https://e2b.dev/pricing) | filesystemとmemoryをpause/resume。Hobbyは20 concurrent、Proは$150/月＋usage、100 concurrent、標準2 vCPU＋4GBは約$0.166/hour | compute部品として優秀だが、tenant別identity/browser profile/auditを別途組むため不採用 |
| [Daytona persistence](https://www.daytona.io/docs/en/persistence/) / [pricing](https://www.daytona.io/pricing) | persistent filesystem、VM memory pause/resume、snapshot/fork。vCPU $0.0504/hour、memory $0.0162/GB-hour、秒課金 | 安いcompute部品だが、browser/identity/receipt統合を自作するため不採用 |
| [Modal Sandboxes](https://modal.com/docs/guide/sandboxes) / [pricing](https://modal.com/pricing) | serverless sandbox、CPU/memory秒課金、Starterに月$30 compute | burst computeに強いが、browser profile/identity/product control planeは別途必要 |
| [Fly Machines suspend/resume](https://fly.io/docs/reference/suspend-resume/) | Firecracker snapshotで高速resume、suspend中はstorage課金だけ。ただしsnapshotは保証されずcold start必須 | 運用責任が大きいため不採用 |
| 自前Kubernetes/Firecracker + Steel | 最大の自由度 | isolation、patch、autoscale、browser、viewer、vault、auditを全部所有するためv1では不採用 |
| [Meta Muse](https://ai.meta.com/muse/) / [security architecture](https://www.meta.com/help/1047255454427887/) | 各userに独立したpersistent isolated Linux VM、full shared browser、storage/CPU/memory、terminal/filesystem、自作tool、Secure Credentials Store、schedule/event background work、activity logを持つ | 直接借りるruntimeではないが、Life Managerのlogical computer、credential broker、shared-browser observabilityの主要benchmark |
| [Meta AI / Muse Connectors](https://dev.meta.ai/products/connectors) | 既存REST APIをMeta AIが呼ぶtoolへ変換するdeveloper preview。Meta Muse本体とは別のdistribution interface | Life Manager API完成後のdistribution channel |

### 3.2 推論と決定理由

AgentCoreが最善なのは「一番強いagent model」だからではない。Life Managerの未解決部分を最少の新規部品で埋めるからである。

1. 専用microVMでtenant実行を隔離できる。
2. Browser Profileでログインを次回jobへ持ち越せる。
3. Browser ProfileとIdentityをagent-owned principalだけに限定し、人間credentialをruntimeへ持ち込まない。
4. Identityでrefresh token/API keyをmodelから隔離できる。
5. CloudTrail/CloudWatch/session replayを既存receipt ledgerと結べる。
6. Tokyo regionがあり、GA、CloudFormation対応である。
7. 既存のNode business kernel、PostgreSQL job protocol、Inngest、Stripeを捨てずに接続できる。

ただし「設計上の最善」と「今すぐ出荷できる最短」は同じではない。現在のAWS accountはroot/IAMと東京AgentCore control planeだけが利用できる一方、Account APIは`PENDING_ACTIVATION`、CloudFormation=`OptInRequired`、S3=`NotSignedUp`、CloudWatch Logs/Cost Explorer=`SubscriptionRequiredException`を返す。signup画面で原因を実測すると、Free planからpaid planへ進む支払方法登録step 3/5がAWS側のattempt limitで一時lockされている。これはLife Managerの審査否決でも、各serviceへ個別に$2を払う問題でもない。AWSはcard verificationで最大$1を3–5日一時保留する場合があるが、現在はその認証を再送できない。Support caseによる解除またはexact safe retry instructionを待ち、同じcard submissionを繰り返さない。S3 evidence、CloudWatch trace、Cost Explorer receiptが無いまま本番に出すと、成功証拠、障害原因、原価を確定できない。そのためAWS解除を待たず、既に認証済みで同じcontrol plane/private networkを使えるRailway Sandbox＋既存Steelを先にcanaryする。

Railway案は以前の「tenantごとに常駐Railway serviceを作る」案ではない。jobごとに隔離Sandboxをcreateし、同一kernel SHAをexecし、checkpoint/evidenceを書き、destroyする。browser login continuityだけを既存Steel profileへ分離する。これによりAWSほど一社完結ではないが、新しいscheduler、database、billing、VM orchestrator、browser stackを作り直さずに済む。

DigitalOcean Managed Agentsは概念的には非常に近く、microVM、pause/resume、Chromium、VPC、egress、credential broker、fresh/reuse triggerを持つ。pauseはcompute課金を止めるがactive-session slotは解放しない。Insightsのtoken/resource値は運用指標であり、正確な支出はbilling recordを正本にする。triggerの`ask`は安全停止ではないため、Life Managerは`ask` 0、`allow`＋明示`deny`、headless HITL rejectだけを許す。AWSの24時間support期限超過とfresh `OptInRequired` / `NotSignedUp` readbackにより、DigitalOcean＋Steel compatibility canaryを開始するが、tenant別login continuity、remove後teardown、session別cost joinが実測PASSするまではproductionへ切り替えない。

DigitalOcean canaryは二段階にする。第一段は`agent: none`の2つのbare microVMを使い、model credentialなしでAのChromium localStorageを同じprofileから再読し、BからAのworkspaceが見えないこと、両sessionのexact remove→list 0、前後prepayment balanceを測る。第二段だけ実際のLife Manager agentとmodel credentialを使い、同じbusiness kernel receiptを検証する。これによりmodel vendor認証をinfrastructure isolationの前提にせず、自己申告ではないbrowser continuityとtenant isolationの証拠を先に得る。live実行は`billing:read`を含むleast-privilege DigitalOcean tokenがSSOTへ保存されてから一度だけ行い、token未取得のlocal testをprovider PASSと数えない。

競合runtimeの詳細な事実、推定、非公開部分、Life Managerへの採否は[`docs/research/cloud-agent-runtime-benchmark.md`](../../research/cloud-agent-runtime-benchmark.md)を正本とする。Meta Muse本体をMuse ConnectorやMuse Codeと混同しない。

## 4. componentの責任

| Component | 唯一の責任 | 正本にしないもの |
|---|---|---|
| Railway API | Telegram/web ingress、auth済みtenant scope、goal/status/result | job進行、receipt判定 |
| Inngest | cron/event wake、再試行、tenant concurrency=1 | effectが成功したかの判断 |
| Supabase PostgreSQL | tenant、goal、`lm_runtime_jobs`、lease、checkpoint、receipt、entitlement、cost ledger | credential値、browser cookie平文 |
| Railway Sandbox | 有限jobを同一business kernel SHAで隔離実行し、checkpoint/destroyする | 永久memory、最終receiptの自己申告 |
| Steel Browser | job中の自律browser automation、provider readback、read-only live observation、emergency stop | 永続的なbusiness state、human resume dependency |
| Browser Profile | tenant/provider別のagent-owned cookieとlocal storage | human credential、複数tenant共有、receipt |
| server-side secret vault | agent-owned OAuth refresh token/API key、agent identity | human credential、user goal、economic ledger |
| object evidence storage | artifact、screenshot、trace、session replay。DBにはhash/refだけ | query可能なjob state |
| Stripe | subscription/paymentの公式状態 | agent jobの成功 |
| CFO ledger | provider receipt + revenue - 全cost | passログや予測利益 |

## 5. 実行フロー

### 5.1 無料onboarding

1. 利用者がTelegramまたはwebで「何を任せたいか」を1文で入れる。
2. APIがtenantを作り、`free` entitlement、月次cost budget、1つのgoalを割り当てる。カードは要求しない。
3. 最初はAPI/read-onlyで完了できる仕事を選び、10分以内に最初のverified resultを返す。
4. 人間principalを要求する候補は選ばず、agent-owned identity/APIで完結する候補へ自動で切り替える。代替が無ければ`not_applicable`で閉じる。
5. 以後はInngestが自動wakeし、通常結果は静かに保存する。通知はmaterial outcomeだけで、credential、許可、承認、再開を求めない。

### 5.2 scheduled wake

1. Inngestが`tenant_id`だけを含むeventを作る。
2. dispatcherがPostgreSQLからtenant、entitlement、cost、次のeligible jobを再読込する。
3. `tenant_id + job_id + attempt + release_sha`でleaseをclaimする。tenantにactive leaseがあれば起動しない。
4. budgetとrelease gateが通った時だけAgentCore Runtimeをinvokeする。
5. runtimeは参照だけのtask capsuleを受け、必要なstateをtenant scopeで読む。
6. jobは有限に終わり、checkpoint、usage、provider receipt ref、evidence hashを返す。
7. control planeが公式readbackを行い、PostgreSQLで`completed|retry|reconcile|not_applicable|policy_denied|blocked`を決定する。どの状態も人のcredential・承認・再開を待たず、他のeligible jobを継続する。
8. microVMを終了する。次のjobは新しいmicroVMでも同じ正本から続く。

### 5.3 browser jobとhuman-free principal selection

1. API toolがあるproviderはGateway/API adapterを優先する。
2. browserしかない場合、tenant/providerに紐づくBrowser Profileで新しいBrowser sessionを開始する。
3. 外部作用直前に最新stateとeffect fenceを再読込し、policy内なら質問せず実行する。
4. providerがhuman login、OAuth、CAPTCHA、2FA、3DS、KYC、面接、署名を要求したら外部作用を開始せず、その候補を`not_applicable: requires_human_principal`で閉じてagent-owned/API候補へ移る。
5. user credential input、approve/resume callbackを通常jobに実装しない。read-only Live Viewとemergency stopは許す。任意break-glass takeoverを提供する場合はagent writerを停止し、手動結果をautomated success/revenueから除外し、終了後も元jobを人間待ちでresumeしない。human principalを要求する入力はprovider call 0で拒否する。
6. 作用後はproviderのreceipt/readbackを取得する。取得できない場合は`effect_unknown`へ隔離し、自動再送しない。
7. session stateをBrowser Profileへ保存してsessionを終了する。

## 6. tenant隔離

次の境界を全部通らなければCloud版を公開しない。

- すべてのjob/state/receipt/cost queryは`tenant_id`を必須にし、PostgreSQL RLSでも二重に強制する。
- `runtime_session_id`、`browser_session_id`、`browser_profile_id`はtenant mapからだけ取得し、client入力を信用しない。
- 同一tenantのactive runtime leaseは最大1つ。別tenantは別microVM、別browser session、別profileを使う。
- credential値はAgentCore Identityまたは既存server-side vaultだけに置き、prompt、job row、trace、Telegramへ出さない。
- Browser ProfileとIdentity refはagent-owned principalだけを許可し、人間credential値またはuser-supplied sessionを拒否する。
- artifactは`tenant/<tenant_id>/...` prefixとKMSで分離し、DBにはrefとSHA-256だけ置く。
- release SHAが承認済みSHAと違うruntimeは、state readやeffect前にfail closedする。
- forged cross-tenant refのtestでは、backing provider callが0回であることを確認する。
- shared browser viewerはtenant-bound opaque session refだけを受け取り、credential/cookie/profile raw dataを返さない。viewer、stop、break-glass writerは同じlease generationを検証し、agentとhumanの同時writerを作らない。

## 7. 無料提供と販売

### 7.1 launch時のplan

| Plan | 利用者体験 | deterministic limit |
|---|---|---|
| Free | カード不要。1 active goal。最初のverified resultまでpaywallなし | 初回activation credit $1、その後は月variable cost hard cap $0.50、1日1 scheduled wake、月10 browser-minutes、外部支出なし |
| Founding Pro | $49/月。3 active goals、1日12 scheduled wakeまで、長いjob、優先queue | 月variable cost target $6 / hard cap $12。上限到達時は自動課金せず停止し、翌月または明示upgradeを案内 |

制限値はversioned entitlementとして保存し、UI文言にprovider単位を露出しない。利用者には「1つの目標が無料で動く」と見せる。無料枠を使い切っただけで既存stateやBrowser Profileを消さない。Freeのactivation creditは最初のverified resultを得るためだけに使い、紹介やbot farmで再発行しない。

### 7.2 収益と利用者の利益を分ける

- Life Manager社の収益はStripe subscription receiptで証明する。
- 利用者のincome loopの成果は、各providerの入金・返金・payoutと実測costをjoinして証明する。
- 「loopが動いた」「応募した」「投稿した」は利益ではない。
- 特定loopで`settled revenue - refund - model/browser/cloud/provider cost > 0`が反復して確認されるまで、「稼げる」と販売文言に書かない。
- AgentCore Payments/x402は初期subscriptionに使わない。自己資金化gateを通った後のagent間支払いだけに限定する。

### 7.3 1 userあたりのunit economics

当社の月次式を次の1本に固定する。

```text
company_contribution_per_user
= subscription_collected
+ attributable_company_owned_settled_revenue
- refunds_and_chargebacks
- Stripe_Payments_fee
- Stripe_Billing_fee
- model_cost
- AgentCore_Runtime_cost
- AgentCore_Browser_cost
- tool_and_search_cost
- allocated_Railway_Inngest_Supabase_S3_CloudWatch_cost
```

ユーザー自身がjob、投資、販売で受け取った金額は`user_outcome`であり、当社売上ではない。初期版でsuccess feeを取らない。会社所有のAffiliate、Apps、Product、x402 loopが受け取った外部入金だけを`attributable_company_owned_settled_revenue`へ入れる。自己送金、含み益、応募、投稿、クリック、未回収請求は0である。

[Stripe Japan pricing](https://stripe.com/jp/pricing)の国内カード3.6%と[Stripe Billing pricing](https://stripe.com/jp/billing/pricing)の0.7%を合わせ、$49 subscriptionの決済費用を4.3% = $2.107として計画する。為替、税、international card surcharge、refund、disputeは別ledger rowにする。

| paid user / month | Subscription | Stripe 4.3% | model + runtime + browser + tools | shared infra allocation | 粗利貢献（人件費・税・広告前） |
|---|---:|---:|---:|---:|---:|
| Best | $49.00 | $2.11 | $3.00 | $1.00 | **$42.89 (87.5%)** |
| Base target | $49.00 | $2.11 | $6.00 | $2.00 | **$38.89 (79.4%)** |
| Cost-cap worst | $49.00 | $2.11 | $12.00 | $2.00 | **$32.89 (67.1%)** |

hard capを越えるjobは開始しないため、1人の暴走がsubscription以上のcomputeを焼かない。refund/chargebackや広告費は上表の外なので、会社全体のnet profitはCFO ledgerで別に差し引く。

Free userは初回$1、以後月$0.50が最大変動原価で、売上は$0である。したがってFree単体は赤字だが、永久VMを持たないので損失上限が明確である。Free portfolioの月次予算は`active_free_users × $0.50 + new_activations × $1`を絶対上限にし、会社全体のFree予算capも重ねる。

AWSの公式例では、10分のRuntime sessionが約$0.006703、10分のBrowser sessionが約$0.012267である。これはLife Manager実測ではないため、CL00/CL06で各jobのAWS Cost and Usage receiptとmodel usageを計測し、上の$3/$6/$12を置き換える。pricing pageの数字だけで利益達成を主張しない。

### 7.4 scale arithmetic（予測ではなく式）

internal revenueを0としても、Base targetの算術は次になる。

| Paid users | Subscription MRR | Stripe fee | variable cost target | shared infra仮配賦 | 粗利貢献 |
|---:|---:|---:|---:|---:|---:|
| 100 | $4,900 | $211 | $600 | $200 | **$3,889/月** |
| 1,000 | $49,000 | $2,107 | $6,000 | $2,000 | **$38,893/月** |
| 100,000 | $4.9M | $210,700 | $600,000 | $200,000 | **$3.889M/月** |
| 204,082 | $10,000,018 | $430,001 | $1,224,492 | $408,164 | **$7,937,361/月** |
| 1,000,000 | $49M | $2.107M | $6M | $2M | **$38.893M/月** |

100,000人・1,000,000人は売上予測ではなく、$49とBase targetを掛けたcapacity/business modelである。顧客獲得、解約、support、人件費、税、広告費を含まない。実際のforecastは、25人cohortのactivation、D7/D30 retention、Free→Paid conversion、cost/userが揃ってから更新する。

内部収益loopは次のように上乗せする。

```text
portfolio_net_profit
= subscription_contribution
+ verified_company_owned_internal_revenue
- payroll - tax - acquisition_cost - unallocated_shared_cost
```

たとえばcompany-owned loopが100,000 paid usersへ帰属可能なsettled revenueを平均$10/user生み、そのための追加costが$3/userなら、追加貢献は$700,000/月である。しかし現状の統合SSOTでは検証済みsettled net MRRはほぼ0なので、この$10をforecastには入れない。receiptが生まれた分だけCFOが加算する。

### 7.5 $10M MRRへ到達する算術とgrowth gate

`$10,000,000 ÷ $49`を切り上げると、必要なactive paid subscriptionsは**204,082人**で、実際のMRRは`204,082 × $49 = $10,000,018`である。Base targetなら人件費・税・広告費前の月次粗利貢献は約**$7,937,361**である。これは売上予測でも達成保証でもなく、priceとcost capから出る必要顧客数・capacityの式である。

Free→Paid conversionをactivated users基準で置くと、204,082 paidへ必要なactivated usersは次のとおりである。

| Measured conversion | 必要activated users | 解釈 |
|---:|---:|---|
| 5% | 4,081,640 | 20人のactivated userから約1人がpaid |
| 10% | 2,040,820 | 10人のactivated userから約1人がpaid |

成長の順序は`1 paid receipt → 100 paid → 1,000 paid → 10,000 paid → 100,000 paid → 204,082 paid`とする。各段階で先へ進む条件は、MRRの見かけではなく、paid retention、月次churn、verified outcome率、Free→Paid conversion、support負荷、p50/p95 cost/userが計測でき、解約分を補充した後もactive paidが純増していることである。必要な月次新規paid数は常に`目標純増 + 当月churn人数`である。

最初から204,082人分のVMを予約しない。active jobだけmicroVM/browserを作るため、capacityは利用者数ではなく同時実行数と実測job minutesに合わせて増やす。company-owned internal revenueはreceipt-backed settled netだけを上乗せし、$10M subscription MRRの必須条件には含めない。

### 7.6 launch cohort

1. internal tenantでread-only canary。
2. 5人のinvite-only Free cohort。
3. cross-tenant leak 0、effect duplicate 0、cost cap breach 0を確認。
4. 25人へ拡大し、activation、D7 retained、verified outcome、cost/userを計測。
5. 最初の価値を受け取った利用者だけへFounding Proを提示する。
6. Stripeで最初の有料subscription receiptをreadbackしてR01完了。

### 7.7 測定可能なjourneyを自律改善する

[Anthropicのclaude.ai高速化事例](https://claude.dev/blog/how-we-made-claude-ai-faster/)は、利用の95%を占める4journeyへ比較可能なstart/end telemetryを置き、lab benchmark、限定deploy、field readback、benchmark ratchet、rollbackを一つのloopにした。二週間で13測定の幾何平均を約3.1倍改善できた核心は、AIへ「改善して」と頼む抽象目標を、改善対象、再現可能な数値、実利用との相関、退行を防ぐratchetへ分解したことにある。

Life Managerは同じ方法を、人間承認へ依存せず次の4journeyへ適用する。

1. `goal accepted -> first verified result`
2. `scheduled wake -> terminal official receipt/readback`
3. `browser session start -> first policy-allowed useful action`
4. `settled revenue/cost change -> CFO ledger + user report`

各journeyはtenant、release SHA、model/tool version、start/end、p50/p75/p95 latency、model/browser/runtime/tool cost、step count、retry count、effect/readback、verified outcomeを同じschemaで記録する。速度またはcostの改善は、verified outcome率、cross-tenant leak 0、duplicate effect 0、credential exposure 0、effect-unknown率、settled net contributionを悪化させない場合だけ採用する。

改善loopは次で固定する。

```text
field trace -> material bottleneck -> one-variable hypothesis -> deterministic proxy benchmark
  -> real outcomeとの相関確認 -> isolated candidate -> held-out/safety/cost evaluation
  -> one-tenant canary -> field readback -> promote + ratchet、またはrollback
```

- proxy metricは、実利用latency、verified outcomeまたはsettled contributionとの相関を実測できなければ廃棄する。測りやすい数字だけを最適化しない。
- candidateは1 bottleneck、1 owner、1 bounded changeを基本とし、別candidateと同じtenant、browser profile、effect ownerを共有しない。
- fieldで改善を確認した後だけbaseline上限を下げる。ratchetは悪化を防ぐ一方向gateであり、候補自身は変更できない。
- high-risk変更はinternal tenantから段階拡大し、失敗時は自動rollbackする。人間approveは通常promotion条件にしない。
- self-improvementはtelemetry、evaluator、receipt定義、identity、permission、spend cap、tenant isolation、rollback権限を変更できない。
- 新しい測定を作ること自体をagentの仕事に含める。ただし新metricはfield outcomeとの相関を証明するまでpromotion gateにしない。

## 8. acceptance gates

| Gate | 完了条件 |
|---|---|
| CL00 Provider proof | TokyoでAgentCore Runtime、Browser、agent-owned Browser Profile、Identityのread-only canaryが実環境PASS。公式resource IDとusage/cost receiptを保存 |
| CL01 Kernel parity | localとAgentCoreが同じ承認済みbusiness-kernel SHA、task capsuleから同じcanonical receipt/evidence hashを作る |
| CL02 Tenant isolation | tenant Aからtenant Bのstate、credential ref、browser profile、session、receipt、artifactへ到達不能。provider call 0 |
| CL03 Lifecycle | tenantごとactive runtime 1、jobごとbrowser session 1。timeout/crash/deploy後もstale leaseをreconcileし、cold startで再開 |
| CL04 Phone-only | Telegram/webでgoal投入後、credential入力・確認・承認・resume 0でagent-owned action、公式readback、session releaseを完走。phoneからread-only live viewとemergency stopが可能。任意break-glass操作はautomated success/revenueに数えず、human principalを要求する候補はprovider call 0で`not_applicable`になり、別jobが継続 |
| CL05 Promotion | main由来immutable releaseだけをdeployし、cloud canary、official readback、replay-zeroを確認 |
| CL06 Cost/Free | Free capで追加computeをfail closedし、既存stateを保持。CFO ledgerでtenant/job単位のmodel/browser/runtime/tool costをjoin |
| CL07 Measured improvement | 4 core journeysのfield baselineをrelease/model/tool別に取得。candidateはproxyとfield outcomeの相関、held-out/safety/cost、one-tenant canaryを通り、verified outcome・effect safety・tenant isolation・settled contributionを悪化させずにp75/p95 latencyまたはcostを改善。失敗candidateは自動rollbackし、成功時だけratchetを下げる |
| R01 Paid | StripeのFounding Pro subscription receiptを1件公式readbackし、entitlement反映とcancel/revokeを確認 |
| R02 Cohort | 25 Free tenantsでcross-tenant leak 0、duplicate effect 0、unbounded session 0、cost cap breach 0 |

local in-memory simulationはunit testであり、CL00〜CL06のcloud完了証拠には数えない。

## 9. provider fallbackと変更条件

provider adapterは`runtime`、`browser`、`identity`の3境界で保つ。ただしv1で複数providerを同時実装しない。

- Browser互換性canaryがAgentCoreで失敗したproviderだけ、既存Steel adapterを限定fallbackとして再評価する。
- AgentCore outageはjobをretry/reconcileへ戻す。即座に別providerへ二重送信しない。
- DigitalOceanへの変更は、必要session数、agent-owned tenant別login continuity、lifecycle readback、決定的allow/deny policy、remove後active session 0、billing recordのtenant/job joinが全部確認できた場合だけ行う。VPC/egressは現行environment specで利用可能だが、canaryで実挙動を確認する。
- provider変更後もPostgreSQLのjob/receipt/effect contractとbusiness-kernel SHAは変えない。

## 10. 非目標

- Meta MuseのSecure VMをLife Manager runtimeとして借りること。Muse本体は主要benchmarkであり、Muse Connectorは別物のdistribution interfaceとしてLife Manager APIを呼ぶ。
- 利用者ごとの永久起動VM。
- Cloud版だけの別business logic。
- previewのAgentCore session storageを唯一の正本にすること。
- v1でKubernetes、Firecracker、独自browser viewer、独自OAuth vaultを作ること。
- 利益を保証すること、またはreceiptなしで「稼いだ」と数えること。

## 11. best / base / worst

- **Best:** Railway Sandbox＋既存Steelがlive gateを全部通り、AWS待ちなしで5人canaryから25人Free cohort、$49 Founding Proへ進む。
- **Base:** Steelの一部実サイト互換性だけ不足し、RuntimeはRailwayのままBrowserbase Contextsへbrowser adapterを差し替える。
- **Worst:** Railway Sandboxのlifecycle/cost readbackが必要contractを満たさない。この場合もbusiness kernel、PostgreSQL job、Inngest、Stripeは残り、AWS解除後のAgentCoreまたはDigitalOceanへruntime adapterだけ差し替える。

棄却案の最強論拠は、AWS AgentCoreならRuntime、Browser Profile、Identity、CloudWatchを一社で揃えられ、長期の部品数が最少になること。ただしこのaccountで標準AWS serviceが未契約のままなので、「解除日不明の待ち時間」がv1の最大コストになる。

**この判断が間違う最有力の筋:** Railway Sandboxの実測memory課金または既存Steelのlogin continuityが、AgentCore/Browserbaseより高価・不安定になること。したがってA24 live canaryで同じfixture、同じ時間、同じreceipt項目を測り、推測でpromoteしない。
