# Maritime 3人pilotのLife Manager接続設計

## 目的と範囲

Life ManagerのTelegram利用者3人に、各自専用のMaritime agentとmicro-VMを割り当て、日々の計画支援を7日間試す。これは1,000 agentを獲得する競争の前段階の技術・利用・費用確認であり、3人pilot自体は勝利条件ではない。

既存のTelegram利用面とslash-command routerを使う。通常のcommute、Calendar、browser-task、onboarding経路は置き換えない。新規Web/PWA、scheduler、loop registry、database migrationは追加しない。

## 確認済みの外部条件

- The First 1,000はKeikiとMaritimeの6週間competition。トップページは「1,000 users」と表現するが、2026-10-14更新のProgram Termsで正式な計数対象は1,000 distinct agentsで、各agentに専用Maritime VMが必要。1 agentを1,000人が使っても1 agentで、subagentは数えない。実利用のlegitimacy reviewはあるが、agentごとの追加retention/activity目標は書かれていない。最初に到達して確認された3 projectがwinner。https://competition.maritime.sh/ https://competition.maritime.sh/terms
- Applications opened 2026-10-13。初期応募者にはその週の終わりまでにconfirmation emailを送る予定。共通の6週間windowで途中参加できるが期間延長なし。closing timeは11:59 p.m. Pacificだが、start/endのcalendar dateは未公表。Apply CTAはSMS `+1 (628) 726-4285`。公開ページに選考rubricや採択条件はない。https://competition.maritime.sh/terms
- Awardはwinner projectあたり最大$20,000分のAI credits。3者全員が$20,000とは限らず、2位・3位のcredit額、free-accessの期間と範囲は未公表。SFは最初の3 winning projects向け3日間体験で、sponsored flightsは米国内旅行に限定。搭乗者数、費用範囲、国際winnerのflight support、日程は未公表。https://competition.maritime.sh/terms
- maritime-sdk 0.9.0はESM、Node >=18。default exportの`Maritime`をCommonJSからdynamic importできる。`agents.provision({ externalId, name, template, instructions })`は`externalId`で冪等。`agents.chat(id, message, { conversationId })`は`{ response, error? }`を返し、delivery failureがthrowされない場合があるため`error`と空responseを確認する。SDK既定の再試行は2回なので`maxRetries: 0`を使う。https://maritime.sh/docs/sdk/agents.md https://registry.npmjs.org/maritime-sdk/-/maritime-sdk-0.9.0.tgz
- API keyは`provision`と`deploy` scopeに限定できる。BYOK env登録には別途`secrets` scopeが必要。https://maritime.sh/docs/sdk/authentication.md
- Free planは3 agent、同時起動1体、$0で期限なし。現行list priceで1,000 machineはScaleの500台$500/月 + 追加500台×$1/月で、host費用は約$1,000/月。model callsは別料金。大会free accessの範囲・期間は未確定。https://maritime.sh/docs/billing.md https://competition.maritime.sh/terms
- Maritime AI-credit model callsはfull prompt/responseを無期限保存。BYOK callsはMaritimeに保存されないが、agentへkeyを登録する必要がある。どちらもこのpilotでは未使用。https://maritime.sh/privacy https://maritime.sh/docs/sdk/agents.md
- MaritimeのOpenClaw frameworkは100+ built-in skills（web browsing、code execution、file management等）を持つautonomous agent。prompt指示だけではこれらを無効化できた証明にならない。制限済みtool policyかchat-only custom imageを確認するまで有効化しない。https://maritime.sh/docs/frameworks/openclaw
- 現行apps/life-managerにMaritime SDK呼び出しやユーザー別継続chat経路はない。Telegram slash-command routerは既存の明示的なuser command境界。
- YC公式profileでMaritimeはFall 2026 companyと確認。創業者への接点があることはYC紹介やWinter 2027採択の保証ではない。https://www.ycombinator.com/companies/maritime

## 選択肢

1. **Telegramの明示command /pilotからだけMaritime agentを呼ぶ。** 既存のtenant UIDを使い、feature-offと3名allowlistを必須にする。通常機能は変更しない。**採用。**
2. 全ユーザーの一般agent backendをMaritimeへ置き換える。アプリ全体のprovider・権限・データ経路を変えるため不採用。
3. 新しいWeb/PWAを作る。既存のTelegram-only user-surface契約に反するため不採用。

## データフローと境界

Telegram webhookが既存のlm_users.uidを解決する。/pilot commandを受けた場合だけ、feature flag、data approval、tool-policy verification、server-side MARITIME_API_KEY、重複なしの最大3 UID allowlistを検証する。どれかが不足・不正ならSDKをimportせず外部callを行わない。`MARITIME_PILOT_TOOL_POLICY_VERIFIED=1`は実際にtool制限を確認した後だけ設定し、OpenClawのprompt指示だけでpassさせない。

有効なpilot userではprovider callより前に、既存の`lm_panel_command_receipts`へ`telegram-maritime-pilot:<update_id>`をclaimする。request hashはLM_UID_SECRETでHMAC化し、メッセージ本文をreceiptへ保存しない。同じupdate_idの再配信はclaim conflictでprovider callも返信も行わずHTTP 200で終える。pending/failed receiptは自動解放しないため、claim後のcrashで依頼が未完了になる場合はあるが、有料provider callの重複を優先して防ぐ。新しいTelegram updateでの明示再依頼は別のreceiptとなる。

有効時は、CommonJS appからmaritime-sdkをdynamic importする。UIDからPIIを含まない安定external IDとconversation IDを導出し、agents.provisionを呼ぶ。agent IDはprovider側externalIdの冪等性で再取得し、Life ManagerのDBに保存しない。agents.chatはresponse.errorを必ず検査し、errorまたは不明応答では成功表示せず、自動再送しない。

pilotはchat-onlyとし、Calendar書込み、メール送信、購入、browser actionは接続しない。prompt、response、email、phone、user name、API keyはLife Managerのログへ記録しない。Telegramへ返す文はHTML escapeし、長さを制限する。

## pilot測定・counting

3つの異なるLife Manager UIDを3つの異なるexternal IDに対応させ、Maritime dashboardで3つのdistinct agent IDと3つの専用VMを確認する。provisionの再試行でagent/VMが増えないことを確認する。subagent、同一agentの利用者数、duplicate accountはagent数に加えない。

7日間、provision成功、初回chat、再利用、利用者が明示したtask完了/未完了、provider error、agentごとの利用量を記録する。prompt/response本文は収集しない。実費はMaritime Billingのprovider readbackで確認し、app側の推定値をactual costにしない。Free tierでは同時起動1体を守る。

## live enablement gate

- 本作業ではMaritime account作成、ToS同意、API key発行、VM作成、実ユーザーの入力送信、paid plan、AI-credit購入、旅行予約を行わない。
- 現行goalの制約では、Maritimeの法的拘束力あるToSとAI-credit利用時の無期限prompt retentionを含むdata handling条件が未承認なのでpilot routeを有効化しない。
- OpenClawのbrowser/code/file capabilitiesを限定するruntime設定は未確認なので、tool-policy verification gateを通すまではpilot routeを有効化しない。
- BYOKはretentionを避ける候補だが、第三者agentへcredentialを登録する追加データ条件が発生するため、本作業では使わない。
- 実pilotの成功条件は、参加者同意の証跡、3 UID→3 external ID→3 agent/VMのofficial readback、3人の実利用、error/retention条件確認、7日利用指標、Billingの実費readback。これらが揃う前に10→100→1,000へ拡大しない。

## 現在の状態

SDKのAPI形状、counting rule、free cap、list-price試算、data retentionは一次資料で確認済み。Life ManagerとのSDK接続、account、key、VM、参加者3人は未作成。source changeはfeature-offで準備できるが、live connectionは現行の法的・データ条件のままでは実行しない。
