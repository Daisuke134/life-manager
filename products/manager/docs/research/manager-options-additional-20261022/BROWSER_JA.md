# Manager向け 新規ブラウザ・外部action実行基盤の一次資料調査

調査日: 2026-10-22 UTC。成果物は調査・実装候補であり、接続済み・実操作済み・本番完成の主張ではない。

## 結論

現在のDigital Autonomy v0.1では新しいブラウザagentを実行ownerにしない。既存の`public_observer.fetch_snapshot`、Playwright/axe、`digital_handoff`、`OwnedEffectJournal`、`reconcile_owned`、元のprivileged publisherを接続する。現行対象は所有する6 HTML + manifestの7パスで、form/input/script/iframeを禁止している。ブラウザagent導入は現在のボトルネックを解消しない。

新しく再利用できる候補はある。UIだけに存在する公開情報の観測や、将来明示的に所有・許可されたUI操作が必要になった時、Stagehand v4の`observe`/`extract`、browser-useのアクションregistryとCDP接続、Skyvernのsession generation fence・credential release guard・post-dispatch timeout分類を比較する。まず既存Playwrightを使い、必要性を確認してから薄いadapterを足す。Selector recovery、LLM cache、agent resume、webhook dedupはいずれも「外部操作が一度だけ起き、独立に確認された」証拠ではない。

特に新規性のあるコード上の発見は以下。

- Stagehandのcached action sequenceは途中の操作が成功した後、後続失敗でfull inferenceへfallbackし得る。書込全体のdedupではない。
- browser-useのaction timeoutはモデル向けerrorに`Try again or a different approach`を返す。送信後timeoutをManager側でUNKNOWNとして封じないまま渡すと再操作の入口になる。
- SkyvernはPlaywrightの`scheduled navigation` timeoutをpost-dispatchと扱い、fallback clickを止める。副作用に対する具体的な実装先例である。一方この分岐はclickの受付らしさを示す分類で、外部providerの確定receiptではない。
- Composioのmulti-accountは明示選択がdefault falseで、通常はmost recently connected accountを使う。ManagerとLife Managerのaccount分離には明示account ID固定が必要。

## 調査境界・自分で観測したこと

Canonical checkout: `/workspace/manager-execution`、origin `https://github.com/Daisuke134/life-manager.git`、共通git dir `/workspace/life-manager/.git`、branch `research/manager-e06-cloud-execution-20261022`、開始時HEAD `ae06f4ccfa30b29e427f71d6413eba0858a34cf8`。AGENTS.md、REVIEW.md、現行MANAGER_PRODUCT_SPEC.md、既存research manifests、実ソースを読んだ。`owned_execution.py`/`owned_handoff.py`というファイルは存在せず、実名は`owned_cycle.py`/`digital_handoff.py`。仕様の通常運用はno per-run human approvalであり、upstreamに承認機能があっても人間承認を通常loopへ追加する提案ではない。

実施したのはFirecrawl Manager接続でのsearch→official scrape、developer index、公開GitHub metadata GET、read-only clone、git/rg/sedによる固定commitの静的コード読み。依存関係をinstallしていない。upstreamコード、Managerテスト、ブラウザagent、LLM、ログイン、submit、送信、課金session、deployは実行していない。下記のテスト挙動はテストコードを読んだ事実であり、自分のテスト実行結果ではない。

Noveltyチェックは`products/manager/docs/research`と`docs/research`のmd/json、およびcompletion/strategy/crossfield manifestsを対象に実施。既知はbrowser-use/**rl-env-useという評価repo**と、現行の直接Playwright/axe。今回のbrowser-use本体実行コード、Stagehand/Browserbase、Skyvern、Playwright MCP、Composio、Pipedream、ADK、Agents SDKのexecution比較は検索範囲で未記載。rl-env-useを新規実行基盤として再包装しない。除外指定のOpenHands/Letta/Inspect/LangGraph/Temporal/Railway/Simile/Aaru/Radiantは比較を掘り直していない。

## 広く比較した候補

| 選択肢 | 実際に提供する層 | 認証・回復の要点 | Manager判断 |
|---|---|---|---|
| **既存Playwright + axe** | deterministic browser/test | Manager側で1.56.1 / axe 4.10.2固定、retries 0、1 worker、fresh context | **今使う既知の再利用**。新発見とは数えない |
| **Playwright MCP** | snapshot/targetをtool化するMicrosoft bridge | persistent profile default、isolated + storage state選択可。security boundaryではない | 必要ならread-only観測用tool化候補。現行の直接テストを置換しない |
| **Stagehand v4 / Browserbase** | AI observe/extract/actとbrowser lifecycle | local persistent userDataDir、cloud context persist、cache replay、opt-in selfHeal。browser owner分離をコードで持つ | 後日のUI限定adapter第一候補。observe→host validate→deterministic actionを優先。現在導入不要 |
| **browser-use** | Python agent loop / CDP browser actions | allowed_domains、domain-sensitive data、action registry、stale-page queue guards、per-action timeout | 既存Python側に合うがフルagentは大きい。既存actorで不足が出た時の比較候補 |
| **Skyvern** | browser workflow platform / credentials / session service | runnable generation fence、credential frame/site release checks、post-click timeout分類、agent retry/step policy | platform丸ごと置換は過剰。境界・回復テストの良い先例。AGPL条件と重いlocal/server依存に注意 |
| **OpenAI Agents Python SDK** | agent orchestration + tool approval/run-state | approval per call / sticky decision、RunState serialization、server-side snapshot ownershipはapp責任 | モデルadvisory adapterの候補。external side-effect journalの代替にしない |
| **Google ADK** | event/session runner、tool confirmation、workflow resume | ResumabilityConfig、invocation ID、custom agentはcheckpoint追加が必要。confirmationはexperimental | 既存kernelの置換をしない。Google側model/workflowが必要になった時の比較候補 |
| **Composio** | OAuth/connected account/tool routing | token refresh、project/user/account ID、明示account固定。webhook IDのidempotencyはdelivery dedup | APIがある新規service接続時はbrowserより先に検討。現在のGitHub publisherを置換しない |
| **Pipedream Connect** | managed auth + end-user action/workflow execution | externalUserId、projectEnvironment、account binding。hosted serviceとrepo licenseは別 | 多数API connectorの必要が出た時の候補。rootはSource Available、OSSと思ってcopyしない |

公式repo metadataは8候補とも`archived=false`、2026-10-20〜22にpush観測。これは維持活動のスナップショットであり、SLA・将来保守・品質証明ではない。Pipedream GitHub license APIはNOASSERTIONだったためLICENSE本文を別途読んだ。

## 固定commitの深い読み: browser-use

**pin:** `aa093a843da5edbf323c0b4145c9b6a0db3ecde8`、2026-10-17T11:53:21-07:00、version 0.13.13、MIT。`pyproject.toml`: Python >=3.11,<4、`cdp-use==1.4.5`、`browser-harness==0.1.13`、`browser-use-sdk>=3.10,<4`、`bubus`、Pydantic、OpenAI/Anthropic/Google等。現在版を「Playwrightの薄いwrapper」と説明しない。

- [`AgentSettings`](https://github.com/browser-use/browser-use/blob/aa093a843da5edbf323c0b4145c9b6a0db3ecde8/browser_use/agent/views.py#L59): max_failures=5、max_actions_per_step=5、step_timeout=180、final_response_after_failure=True、judge/planning/loop detectionあり。modelによるsuccess/judgeはManagerのP2へ昇格させない。
- [`Tools.act`](https://github.com/browser-use/browser-use/blob/aa093a843da5edbf323c0b4145c9b6a0db3ecde8/browser_use/tools/service.py#L2178): registry actionをasyncio.wait_forで包みdefault180s。BrowserError/TimeoutError/other ExceptionをActionResult(error=...)へ返す。timeoutは`Try again or a different approach`という文字列になる。事前未実行timeoutか送信後timeoutかをこの一般結果だけでは区別できない。
- [`Agent.multi_act`](https://github.com/browser-use/browser-use/blob/aa093a843da5edbf323c0b4145c9b6a0db3ecde8/browser_use/agent/service.py#L2755): actionを順に実行しdone/errorでbreak。terminates_sequence metadata、URL/focused targetの変化でも残りqueueを中断。partial results保持は良いが外部operation idempotencyではない。
- [`Registry.exclude_action`](https://github.com/browser-use/browser-use/blob/aa093a843da5edbf323c0b4145c9b6a0db3ecde8/browser_use/tools/registry/service.py#L34): action削除と再登録除外を持つ。read-only構成ではclick/input/upload/sendkeys等を出さない形を検討できるが、registry除外だけをnetwork security boundaryと扱わない。
- [`SecurityWatchdog`](https://github.com/browser-use/browser-use/blob/aa093a843da5edbf323c0b4145c9b6a0db3ecde8/browser_use/browser/watchdogs/security_watchdog.py#L177): host/scheme条件とIPチェックがある。allowed_domains未指定は全許可。data/blobとinternal pagesは早期許可。navigation-completeでdisallowed redirectを検出するとabout:blankへ戻す。これはnavigation後の検出を含み、全subresource/全書込の事前遮断を証明しない。
- [`Agent`のsecret警告](https://github.com/browser-use/browser-use/blob/aa093a843da5edbf323c0b4145c9b6a0db3ecde8/browser_use/agent/service.py#L534): sensitive_data使用時allowed_domainsがないとwarning。ドメイン別credentialsも検査。placeholder/redactionは実際のログイン先の所有権やclient権限を自動保証しない。
- [browser profile](https://github.com/browser-use/browser-use/blob/aa093a843da5edbf323c0b4145c9b6a0db3ecde8/browser_use/browser/profile.py#L628): persistent user_data_dir / storage_state / CDP / keep_alive。既存Life ManagerのprofileをManagerへ共有しない。`config.py`はANONYMIZED_TELEMETRY default true、cloud syncもそれをdefaultに参照する。試験時も明示設定が必要。

**採用条件:** 公開UIでHTTP取得では観測できない情報があり、限定action schema、host-owned source binding、deadline/cost reserve、独立readbackの契約が先にある場合。**現在却下:** フルAgent.runをowned releaseのsendに使い、error後の再計画をそのまま許す構成。実サイトログイン持続、provider receipt、API-side idempotencyは未検証。

## 固定commitの深い読み: Stagehand / Browserbase

**pin:** `6aec9d16a8f503d0e81f22b92ff15a01205c4db2`、2026-10-21T19:18:47-07:00、MIT。root packageは4.0.0だが**`packages/sdk-ts/package.json`は4.3.0**。Node>=22.18、SDK dependenciesはBrowserbase SDK/OpenTelemetry/zod。v4はbrowser extension/runtime + SDK/RPC構成。旧v3のnew Stagehand({env})や「Playwright wrapper」を現行APIへ混ぜない。

- [`Stagehand.create`](https://github.com/browserbase/stagehand/blob/6aec9d16a8f503d0e81f22b92ff15a01205c4db2/packages/sdk-ts/src/stagehand.ts#L96)はbrowser handleをclaimし、init failureがambiguousならinvalidate、確定失敗ならrelease。[`act/observe/extract`](https://github.com/browserbase/stagehand/blob/6aec9d16a8f503d0e81f22b92ff15a01205c4db2/packages/sdk-ts/src/stagehand.ts#L245)は明示page又はactive pageにRPCする。このpage defaultを複数tabの所有境界として使わない。
- [`replayCachedActions`](https://github.com/browserbase/stagehand/blob/6aec9d16a8f503d0e81f22b92ff15a01205c4db2/packages/extension/services/actService.ts#L249)はキャッシュ内actionsを順次deterministicに実行し、失敗でthrow。[`withCache`](https://github.com/browserbase/stagehand/blob/6aec9d16a8f503d0e81f22b92ff15a01205c4db2/packages/extension/services/cacheService.ts#L264)はonHit失敗をcatchしfull executeへfallback。したがってsequence前半の副作用が成功した後の失敗で、再推論実行が始まる可能性がある。cacheはLLM再推論を減らす機能でありeffect dedupではない。
- [`takeDeterministicAction/selfHealAction`](https://github.com/browserbase/stagehand/blob/6aec9d16a8f503d0e81f22b92ff15a01205c4db2/packages/extension/services/actService.ts#L330): operation後例外時、TimeoutErrorはthrow、他errorでselfHeal=falseならsuccess:false、trueならsnapshotを取り直してselectorを再推論して同method/argsを実行する。extensionの初期defaultはfalse。自動repairを不可逆writeへ無条件適用しない。
- [`resolveChromeProfile`](https://github.com/browserbase/stagehand/blob/6aec9d16a8f503d0e81f22b92ff15a01205c4db2/packages/sdk-ts/src/browser/localBrowser.ts#L170)は指定userDataDirを0700で作り保存、未指定時tempを作り通常削除。browser lifecycleを自作し直す必要はない。Browserbase session clientはcreate/connect/releaseとextension cleanupを持つ。cloud cookbookはcontext ID + `persist:true`で認証を再利用する。既存ユーザーChromeへ自動接続する提案ではない。
- [`SubmissionGuard.claimSubmit`](https://github.com/browserbase/stagehand/blob/6aec9d16a8f503d0e81f22b92ff15a01205c4db2/packages/examples/cookbooks/approve-form-submission/typescript/src/approval.ts#L17)はbrowser call前にattemptedへ移す。例はfilled values再照合とreceipt fileを持つがguard自体はin-memory。restart/concurrent ownerの永続dedupを証明しない。human approvalはVercel AI `toolApproval`をappが組み合わせたcookbookであり、Stagehand全actionの強制gateではない。

[公式v4 act docs](https://docs.stagehand.dev/v4/basics/act)はBrowserbase cacheがdefault on、localではcache効果なし、locator scopeではserver cache bypass、observe結果Actionはselectorを直接replayすると説明。これらはlive docsの記述であり、上記固定commitとは別の証拠。

**採用案:** 将来の読み取り限定UI-sourceにはobserve/extract候補。実writeが必要になった場合もhostが一つの許可済みdeterministic operationを選び、Manager journalの予約後に一回だけ呼ぶ。irreversible stepではcache:false、selfHeal:false、sequence batchingなし。**今は不要:** cloud browser/account/model利用は未実行、費用・保存地域・trace漏洩・session競合・login durabilityは未検証。

## 固定commitの深い読み: Skyvern

**pin:** `a59e8c4ce423ed38feef994bace51f7a0f996011`、2026-10-22T09:18:14-04:00、version1.0.56、AGPL-3.0。Python>=3.11,<3.15。core SDKとlocal/server optional dependenciesを区別する。`[project.optional-dependencies].local`自体がForge compatibility bridgeと明記され、Playwright、LiteLLM、SQLAlchemy、FastAPI、cloud/vault client等を含む。小さいbrowser-only dependencyだとは言えない。ManagerへAGPLコードを無検討でcopyしない。

- [`BaseTaskBlock`](https://github.com/Skyvern-AI/skyvern/blob/a59e8c4ce423ed38feef994bace51f7a0f996011/skyvern/forge/sdk/workflow/models/block.py#L2000): max_retries=0、max_steps_per_run、complete/terminate criterion、complete_verificationを持つ。executeの失敗分岐ではcurrent_retry<=max_retriesならtaskを再作成・実行し得る。anti-bot failureはretryを止める。max_retries=0は外部side effectのAPI-level dedupを意味しない。
- [`PersistentBrowserSession`](https://github.com/Skyvern-AI/skyvern/blob/a59e8c4ce423ed38feef994bace51f7a0f996011/skyvern/forge/sdk/schemas/persistent_browser_sessions.py#L94)はorganization/runnable/generation、lifetime、upstream CDP/vendor/browser IDsを持つ。[`assert_runnable_owner`](https://github.com/Skyvern-AI/skyvern/blob/a59e8c4ce423ed38feef994bace51f7a0f996011/skyvern/forge/sdk/schemas/persistent_browser_sessions.py#L210)は期待run/generationと相違でownership conflict。`RealBrowserManager`はlease renewとexpected generationをsession取得/cleanupへ渡す。browserを一つのrunnableが所有する先例として有用。
- [`is_post_dispatch_click_timeout`](https://github.com/Skyvern-AI/skyvern/blob/a59e8c4ce423ed38feef994bace51f7a0f996011/skyvern/webeye/utils/dom.py#L101)はこのrunのengine timeoutで`scheduled navigation`を含む場合をpost-clickと分類。[`SkyvernElement.click`](https://github.com/Skyvern-AI/skyvern/blob/a59e8c4ce423ed38feef994bace51f7a0f996011/skyvern/webeye/utils/dom.py#L1392)はその場合fallbackを止めてreturnする。一般click failureではblocking-element/JS等のfallbackが続くので、全文脈なしで「全clickはat-most-once」とは言わない。分類がreturnしただけでofficial external readbackにはならない。
- [`CredentialReleaseGuard.enforce`](https://github.com/Skyvern-AI/skyvern/blob/a59e8c4ce423ed38feef994bace51f7a0f996011/skyvern/forge/sdk/workflow/models/credential_release.py#L185)はsecretをpageへ渡す前に、locatorのowner frame URL又はkeyboardのfocused frame URLを調べsaved siteとのscopeを比較。拒否exceptionはdenied page operation markerを持ちhealable errorとして扱わせない。logにsecret入りURLを出さない工夫もある。レビュー済みcredentialを誤ったiframeへ流さないテストの先例。
- [`HumanInteractionBlock`](https://github.com/Skyvern-AI/skyvern/blob/a59e8c4ce423ed38feef994bace51f7a0f996011/skyvern/forge/sdk/workflow/models/block.py#L15578)はapprove続行/reject終了/no response timeout終了、default2h。任意blockであり全runの必須手順ではない。Managerにこの人間待ちを追加する理由はない。

[公式browser docs](https://www.skyvern.com/docs/browsers.md): 同sessionへのrunは前run完了を待つ、idle sessionも課金、extend再試行は時間をもう一度加算する。期限切れ/closeは410、startup timeoutは504でrun作成前に拒否と説明。[production docs](https://www.skyvern.com/docs/developers/production.md): HMAC(raw-body)でwebhook検証、deliveryとrunは別、terminal statusとoutputを保持、webhook replayとagent retryを区別する。これらはvendor文書の主張であり自分の外部実行確認ではない。

**採用案:** 具体的な障害ケースをManagerの既存テストに追加。**今は却下:** platform全導入、別のcredential store/DB/queue/session ownerの追加。hosted実証・料金・license適合性・general prompt-injection防御は未確認。

## 追加読み: Playwright MCPとSDK/connector

**Playwright MCP pin:** `ab6d67cbf8b619338f096980806fdbe29432cc4d`、0.0.83、Apache-2.0。[package](https://github.com/microsoft/playwright-mcp/blob/ab6d67cbf8b619338f096980806fdbe29432cc4d/package.json)はPlaywright/core1.64.0-alphaを参照。Manager既存1.56.1と同じものとして扱わない。[src/README](https://github.com/microsoft/playwright-mcp/blob/ab6d67cbf8b619338f096980806fdbe29432cc4d/src/README.md)は実装本体をPlaywright monorepoへ移したと明記、index.jsはcoreBundle.tools.createConnectionのexport。click fixtureはsnapshot ref e2→getByRole click→新snapshotの流れ。追加でmonorepo `ca7ca36145b84183cf423c2a099bd7e9cd8b1cb3`の`mcp/program.ts`/`browserFactory.ts`を読み、attached/own、isolated client context、shared lifecycleを確認したが、これはMCP0.0.83内のalpha dependencyと同一commitの証明ではない。

[公式profile docs](https://playwright.dev/mcp/configuration/user-profile): persistent default、同profile同時利用は起動失敗、isolated+storage-state、extensionの3方式。READMEはallowed/blocked originsがsecurity boundaryではなくredirectに効かないと明記し、secretsもconvenienceでsecurity featureではないとする。したがってMCPの起動optionでManagerのsource policy/egress/publisher authorizationを置換しない。

[OpenAI Agents HITL](https://openai.github.io/openai-agents-python/human_in_the_loop/): needs_approvalはopt-in、per-callとstickyを区別。Shell/ApplyPatch stickyはagentを跨いでtype+nameで一致し、別executorへも適用し得る。RunState deserializeはsnapshotや提出者をauthenticateしない。公式docs自体がserver-owned storage、atomic consumption、side-effect reconcile before retryを要求する。Manager既存standing scopeとjournalを維持する方が小さい。通常loopにhuman checkpointを持ち込まない。

[ADK resume](https://adk.dev/runtime/resume/)はPython1.16+のResumabilityConfigとinvocation ID、completed task/eventsの記録、custom agentのcheckpoint実装必要性を説明。[confirmation](https://adk.dev/tools-custom/confirmation/)はPython1.14+等のexperimental機能、boolean/structured確認、人又はsupervising systemを想定。resumeがprovider receiptやexternal dedupを自動供給するという根拠は得ていない。

[Composio connected accounts](https://docs.composio.dev/docs/auth-configuration/connected-accounts)はtoken refresh/credential managementを管理しcredential値はdefault masked、proxy executeを案内。[multiple accounts](https://docs.composio.dev/docs/authentication/managing-multiple-connected-accounts)のrequire_explicit_selection=false、most recently connected active account defaultが重要。user/project/account/toolkit versionをhostで固定する。[connection activated webhook](https://docs.composio.dev/reference/api-reference/webhook-events/composio_connected_account_activated)の安定webhook-idは配送重複排除であり、例えばsend API自体の重複防止契約とは別。

[Pipedream managed auth](https://pipedream.com/docs/connect/managed-auth/quickstart)はserverで短命Connect tokenをexternalUserIdへscope、[workflows](https://pipedream.com/docs/connect/workflows)はprojectEnvironment + end-user accountを選んで実行する。自分のaccountを使う設定とuser authの設定が別にある。root [LICENSE](https://raw.githubusercontent.com/PipedreamHQ/pipedream/master/LICENSE)はPipedream Source Available License1.0、Excluded Purposeにany commercial useを含む記述。MITと仮定せず、hostedAPI利用条件と各componentのlicenseを別確認する。SDKやmanaged serviceの保守・dependenciesは全てを固定commit監査したわけではない。

## Managerの正確な接続点とatomic patch候補

以下は**未実装の提案**。既存境界を拡張する設計であり、fixtureをliveにするflag、毎回の人間承認、任意browser custom engineは追加しない。parentのE06 promotion/worker計画と統合して重複実装を避ける。

### B01: 現在の6ページ全体で既存browser gateを使う（新規依存0）

対象: `products/manager/tests/e2e/environment.spec.cjs`の各page loop、`playwright.config.cjs`。

現状: 各pageにaxe/keyboard/mobile/lang/heading/no-form/no-script/no-iframe/cookies/localStorageチェック、別のnetwork-only testはmental.htmlだけ。retries=0、workers=1。

差分候補: 各page.goto前にcontext requestのURL/methodを観測し、全6pageでowned-origin GET/HEADだけ、同origin以外のrequestなし、service-workerなし等の現在のpublic-static契約を確認する。許可されたpublic page journeyとmutationを区別して現行テストへ追記。失敗時traceへcredentialを入れない。public byte evidenceは`phase06_kernel_release.live_snapshot`を引き続き使う。

受入: 同originPOST、third-party iframe/request、storageを持つprivate fixtureを混ぜた時browser gateが落ち、現行静的bundleはdesktop/mobile全routeで通る。browser resultだけでreceipt/P2にしない。これは新browserを作る作業ではない。

### B02: 既存回復テストを再利用し、将来adapter固有の回復差分だけ追加

対象: `products/manager/tests/test_owned_effect_recovery.py::OwnedRecoveryTests`、`products/manager/tests/test_digital_cycle_acceptance.py::CycleAcceptanceTests`、`manager_core/owned_cycle.py::run_owned_cycle`、`outbox.py::OwnedEffectJournal.reserve`、`reconcile.py::reconcile_owned`。

現状: response-lost、restart、transient not found、concurrent reservation、wrong occurrence、old parent CASは既にテストがある。さらに`test_digital_cycle_acceptance.py::test_lost_send_response_is_unknown_count_then_reconciled_without_resend`はsendがcommit後OSErrorをraiseし、UNKNOWNのwrites=None、次回reconcile、再send 0回を既に検査する。これは完了済みの先例なので新規パッチとして数えない。

差分候補は将来adapter導入時だけ: 上記既存テストをそのまま受入suiteへ使い、adapter固有の「partial browser sequence後failure」「old session generationのlate callback」に差分を絞る。effect-then-errorのcycle検査は重複追加しない。side-effect phase/generation等の新契約を導入した場合だけ対応のfixtureを足し、exact immutable occurrenceがなければUNKNOWN、見つかった後だけPRESENTを確認する。Skyvernのmessage heuristicをManagerのgeneral success判定へcopyしない。現在のGit releaseにbrowser session generationは存在しないため、これを今から新設しない。

受入: classifierやmodelがsuccess/failedを返してもindependent occurrenceなしでfenceが閉じない。停止・再起動後もwrite countが増えない。既存fixture-only type gateを変更しない。

### B03: 将来UI-only public sourceへのread-only adapter契約（条件成立後）

対象: `manager_core/public_observer.py::{PublicSourceSpec,FetchedSnapshot,fetch_snapshot}`、`models/source.py`、`evidence_types.py`、`collaboration.py::PlannerContext`。新設するなら`adapters/browser_observation.py`と対応focused test一つ。

差分候補: HTTP `FetchedSnapshot.body`の意味をrendered DOM/LLM抽出に黙って変えない。ブラウザで得たrendered DOM又はsnapshotは別schema/provenanceとしてraw byte hash、capture time、exact URL、browser/sdk version、read-only action allowlist、host-controlled source rightsを付ける。Stagehand observe/extract又は既存Playwrightをtransportにし、model抽出値はadvisor入力に留める。ソースHTMLをtool権限にしない。既存HTTPS transportをdefaultのまま保つ。

受入: sourceからの`click/publish/send`指示、redirect/private-IP、credential state提供、費用/deadline超過を拒否し、model outputはOwnedReleaseIntent/P1/P2を作れない。UI-onlyに実データ上の必要性がなければ実装しない。

### B04: 将来connector用identity binding（条件成立後）

対象: 追加provider adapterとそのhost設定のみ。`provider_sessions.py`はadvisory側でありlive writeへ転用しない。既存`authority.py::OwnedDigitalScope`、`digital_handoff.prepare_owned_change/admit_release`、`OwnedEffectJournal`へ接続。

Composioならproject/user/connected_account_id/tool slug+version、Pipedreamならproject/environment/externalUserId/accountを固定。モデルにaccount選択を委ねない。webhook-id dedupとeffect-key reservationを別store/別意味に保つ。expired authを「別accountへ自動fallback」「新login」へ変換しない。現行GitHub publisherに必要ないため今追加しない。

受入: 同名tool/別account、最終接続account入替、別project/user、replayed webhook、token refresh失敗、write response lossが無許可dispatchやPRESENTを生まない。

## 残る外部不確実性

公開コード静的監査はlive-site reliabilityを測っていない。Browserbase/Skyvern/browser-useの有償API、長期間login、MFA、profile競合、cloud storage/trace retention、費用上限のprovider請求一致、対象サイトのAPI-side idempotency、未知のpost-dispatch errorは未確認。webhook/approval/run statusのsource statementと、Manager自身の公式外部readbackは別物である。

今回追加したのはscratchの調査md/jsonのみ。canonical repoを編集せず、テスト実行・publish・account mutationをしていない。


---
統合注記: このlaneは読取調査。repoへ収録した統合担当の文書変更と、未実施の実装/外部操作は別。[追加調査の判断](REPORT_JA.md)と[atomic patch plan](../../plans/2026-10-22-manager-e16-atomic-patches.md)を参照。
