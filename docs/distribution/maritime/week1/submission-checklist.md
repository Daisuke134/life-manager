# Maritime 初週の現状と残TODO

## As-Is

- Team application: accepted.
- Official competition goal: six weeks、1,000 distinct people with real usage。最初の3 verified projectsがwinner。利益額を順位にする条件は公開されていない。
- Kickoff email: Week 1後はtop 30のみadvance、real usersはbonus。正確なcutoff/timezone/rubricは未記載。
- Existing entry: #competition-submissionsへLife Manager entryを1件投稿しreadback済み。channelは投稿がrequired formを置き換えないと明記。formal submission receiptは未確認。
- Product: Railway life-callとworkerはSUCCESS。最新成功deploymentは06:23 UTC、loaded SHAの最後のexact readbackは982875d62eaa03f8e924b990c4bc80f521d8dcce。pilot pageは稼働するが、hosted work/report/stop cycleとexternal userは未確認。Runtime PG last readback 08:00:19 UTC: identity=1、enrollment/execution/participant/job/external work/users=0。
- Revenue: 09:38 UTC live Stripe readbackでLife Manager月額price ($29と$20)それぞれのactive subscription=0、subscription MRR=$0。ローカルworkflow収益はDais申告だがsettlement receipt未結合。hosted user earningsとdistribution revenueは未確認。
- Distribution: SEO article sourceと56件目のpublication packageはfeature worktreeにあり、未commit/unpublished。article URLはHTTP 404。GSCは0 clicks / 7 impressions through 2026-10-18。Postiz connectorはgroups=0 / integrations=0 / posts空。Life Manager X postなし。新規accountやInstagramは作らない。

## Ordered atomic TODO

### 1. 既存ブログで最初のSEO記事を公開

- Source: docs/research/manager/articles/2026-10-21-ai-assistant-vs-agent-next-task-en.md。
- Package: docs/research/manager/publication/2026-10-19/en/manager-ai-assistant-vs-agent-next-task-en.md と docs/research/manager/publication/2026-10-19/manifest.json。
- Daisuke134/anicca-productsの既存Manager bridgeを使い、新CMSを作らない。
- 記事とpilot pageに、hosted work/report cycle未検証、必要なwork dataをMaritimeへ送信、AI-credit callの無期限保持条件、収益非保証を明記。実行・収益claimはprovider receiptがあるものだけ。
- title/description/slug/word_count/series_order=56とsource/package SHA256を記録。Life Manager branchをpushし、exact-head review/required CI後に既存bridgeを更新しbuild。
- DONE: production canonical URLがHTTP 200で、title/canonical/bodyがsource packageと一致。記事公開だけを獲得/売上の証拠とはしない。

### 2. owner consent後にhosted work cycleを完了

- Current cursor: docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md のT22.1e.2 / b.6-28。
- 正しいowner mailbox sessionから既存Maritime email PKCEを完了し、AI-credit retention noticeへの明示同意を記録する。linkを再送したり同意を推定したりしない。
- その後identity/enrollmentを読み、既存agentを一度だけbind。既存factoryのreversible taskを一件実行し、Maritime execution/result・外部provider receipt・artifact/hash・daily report receipt・stop readbackを保存。
- DONE: user/tenant/jobを全receiptで同じIDへ結合。local successやpageviewは完了扱いしない。

### 3. 既存entryを重複させず正式提出を完了

- 正本: docs/distribution/maritime/week1/requirements.json、packet: docs/distribution/maritime/week1/submission.json。
- 公式home/Terms、announcements、既存organizer threadでform/cutoff/timezone/required field/rubricを確認する。推測のformを作らず、既存Slack entryを再投稿しない。
- official routeが出たら実測値と理由付きnullだけでpacketを作り、1回submit。
- DONE: confirmation pageまたはofficial receipt IDをreadbackし正本へ保存。現状はentry-shared/formal-submission-unconfirmed。

### 4. 既存X identityを確認して一投稿

- 現Postiz connectorはgroups=0 / integrations=0。
- 新規Instagram/X accountを作らず、既存広域X profileのowner/integrationを再読取する。確認後、一意のbuild-in-public投稿を1件だけ公開しUTMとPUBLISHED receipt/permalinkを保存。
- identity readbackがない間は投稿しない。家族/友人DMはDaisが保持条件を確認して送る。

### 5. 実利用・収益を別々に計測

- Article/X UTM → visit → verified signup → activation → completed external work → return → settled user earnings/net。
- 別軸: Life Manager paid subscriptions/settled company revenue、およびsource-attributed distribution paid receipts/fees/cost。
- competition userはKeiki/Maritime project usageで確認できるdistinct real usageだけ。views/signup/agents/VM/team/test identitiesは数えない。
- 成果が確認できたsourceだけ拡大。未確認収益/costはunknownのままにする。
