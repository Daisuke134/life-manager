# Maritime 初週の現状と残TODO

> Historical snapshot from 2026-10-21. Its dated counts, URLs, and statuses are not the current readback. Current status and cursor: [integrated SSOT](../../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md); current evidence: [2026-10-24 readback](../../../evidence/maritime/live-readback-20261024-1110Z.json).


**更新:** 2026-10-21 11:29 UTC。競技home/Terms、Railway status/API readback、英日pilot page、Stripe、Postiz、Gmail、Life Manager/Anicca Products PRをreadback。

## As-Is

- 申請はaccepted。競技公式条件は6週間で実利用のある別人1,000人、最初に到達して検証された3 projectがwinner。利益額は公開順位条件にない。Kickoffメールは初週後Top 30のみ次週へ進出とするが、cutoff/timezone/rubric/最低ユーザー数は公表されていない。
- 提出: #competition-submissionsにはentry 1件を投稿/readback済み。channel説明はrequired formを代替しないと明記。公式home/Termsを11:10Zに再確認してもWeek 1の別form/cutoff/rubricなし。Gmailの10/20以降検索はMaritimeのWelcome/Verify通知のみで、競技案内なし。正式submission receiptとTop 30 statusは未確認。旅行条件は11:14ZにMaria宛て既存スレッドで質問し、送信済み/readback済み、返信待ち。投稿を重複させない。
- Product: goal/budget入力なしでManager自身が仕事を選ぶ設計。copy修正PR #8492のsource SHAはb5ecef6、current mainはcab43203e2d80c3600ed53754377565920df6845だが、その間にPR #8493で`skills/writer-agent/runtime/shared-model-runner.py`のsource変更あり。production life-call e9ebfb62-e8c3-46eb-a198-d9203f574899とworker 9dc09440-42ed-4349-83c2-e437b1fc5017は06:23ZのSUCCESS deployment、exact SHA 982875d62eaa03f8e924b990c4bc80f521d8dcce。英日pilot pageは11:10ZにHTTP 200だが、日次メールを現在機能として示し、hosted cycle未検証の説明を欠く。worker email flagは09:50Zのlast exact readback=0、11:12Z variables values redacted。
- Product usage: 10:49Z Supabase aggregate-only readbackでlive participants/enrollments/executions/completed-work/report-sentはすべて0。これは内部DB集計で、Keiki/Maritimeの公式user countではない。owner PKCE、Maritime AI-credit保持への明示同意、hosted work→external result→daily report→stopは未完。個人業務データは同意前に送らない。
- Revenue: 11:05Z Stripe live readbackでLife Managerの$29/月と$20/月priceはactive subscription各0、MRR=$0。paid invoice/checkout line itemは両priceとも0。$29 payment linkはactiveだがcompleted session=0、$20 linkなし。Account-wide invoice/PI/refund/balance rowsはLife Managerへ未帰属。T31.1b evidence: docs/evidence/maritime/stripe-revenue-attribution-readback-20261021.json。Daisのlocal earnings申告、hosted user income/net、distribution revenueは未確認。
- Distribution: article source/package/manifestはPR #8492でmainへmerge済み（56 entries、SHA一致）。Anicca Products PR #537はdraft、Landing CI/CodeRabbit PASS。候補URLは11:10Z HTTP 404。GSC settled through 2026-10-18は0 clicks/7 impressions。Postiz connector groups/integrationsは10:49Zに0。Life Manager X post、verified signup、source-attributed paid receiptは未確認。Instagram新規accountなし。
- Railway: 11:10Z official statusはMajor Outage（Dashboard/API停止、新規buildは全region停止）。11:12Z Railway readbackでは既存life-call/workerは06:23ZのSUCCESSのままSHA 982875d。10/17からinvestment resource/flagの無関係な3変更がstagedのまま。Maritime変更と混ぜてacceptしない。

- Demo: `demo-script.md`に`GET /maritime`、`POST /maritime/activate`、`maritime_manager_cycle` receipt、`GET /maritime/artifacts/...`、`maritime.manager.report`/Resend receipt、`POST /maritime/stop`を明記。動画素材/公開投稿は未確認。source cycle receiptにはexternal provider refsを結合できず、T17.5が未完。

## Ordered atomic TODO

1. **T23.3 — 正式な提出経路を監視し、出たら一度だけsubmit。**
   - Official home/Terms、announcements、既存organizer threadの新着を確認する。11:10Z時点でpublic form/締切/rubricは未公表。11:14ZにSF国際旅行条件をMariaへ質問済み、返信待ち。
   - 旅行問い合わせはmessage `1a15e2beef607bc0`として既存スレッドへ送信/readback済み。2026-10-23T11:14:59Zまでに回答がなければ同じthreadで一度だけfollow-upする。旅行条件の回答を待って初週提出を遅らせない。
   - 公開formが出たら、実測値と理由付きnullのみで既存draftを更新し、指定のformal formだけを一度submitする。Slack entryを重複投稿しない。
   - **DONE:** confirmation/受付IDと提出本文・時刻・release SHAを保存。現状はformal submission unconfirmed。

2. **T26.5b — Railway復旧後に英日pilot説明を本番反映。**
   - 公式Railway statusが正常へ戻った後に、life-call/workerがその時点の`origin/main` exact SHAを使うdeploymentをreadbackする。b5ecef6だけでは不足し、PR #8493の後続source changeも含める。
   - English/Japanese /maritime をGETし、日次メールを未検証cycleの設計意図として表示し、goal/budget optional、Telegram optional、Maritime保持条件、収益非保証を照合する。
   - **DONE:** 両localeのproduction pageが正しいcopyを返し、deployment SHAを記録。現状は旧表示でblocked by Railway outage。

3. **T22.1e.2 — owner PKCE/明示同意後に一件のCloud Manager cycleを完了。**
   - Ownerが既存email PKCEを本人手続きで完了し、無期限retention noticeを読んで明示同意する。本人同意を推定・代行しない。
   - Identity/enrollmentをaggregate-safeに照合し、既存factoryの一件を実行する。Maritime execution/result、外部provider receipt、artifact/hash、日次報告の送信と受信、pause/stop readbackを同一user/jobへ結合する。
   - **DONE:** 自律選択→実仕事→外部結果→日報→stopの一周期を証明。local successやpageviewは数えない。

4. **T27.2 — 既存blog記事を公開し、計測入口を開く。**
   - Existing source/package/manifestはmainへmerge済み。PR #537はdraft head 42aac79aa29012ab018a138fe295943269967210、Landing CI/CodeRabbit PASS。
   - T26.5b後にfresh exact-head reviewを行い、PRをready/merge/deployする。Canonical URL HTTP 200、title/canonical/body/source hashをreadbackする。
   - Existing Writer/Manager blogをSEO主軸とする。Search demandは未計測であり、SEOだけで初週usersが来ると仮定しない。

5. **T27.3-4 — 既存XとDaisの個別紹介を使って実ユーザーを増やす。**
   - Postiz identity/integration readbackが0の間はpostしない。新規Instagram/X accountを作らない。接続済みの広い既存X identityが確認できたら1件だけpublishしてUTM/permalink/receiptを保存する。
   - Live pageのcopyが直った後、T30.5で初回preview emailの訂正版をDaisへ一度返信する。準備済みのfamily/friend DMはDaisが使う。送信・既読をsignupやuser countにしない。T22の完全cycleは待たず、early-pilot/未検証範囲/保持条件/収益非保証を明記する。
   - **DONE:** source→visit→verified signup→activation→completed work→returnをcohort別に読める。

6. **T28/T29/T31 — 利用者増と収益を証拠で改善する。**
   - Competition countはKeiki/Maritime project usageで検証されたdistinct real peopleだけ。社員/test/VM/agent/view/signupを公式usersに数えない。
   - 1,000人/約6週間は平均約24人/日というplanning arithmetic。初週cutoff/必要数が公式にあるとは言わない。
   - Life Manager subscription MRR、利用者businessのsettled cash/net、distribution別paid receipts/fees/costを分けて計測する。0ではなくunknownの項目はunknownのままにする。