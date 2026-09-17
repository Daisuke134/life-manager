# Life Manager Cloud cost・pricing・legacy cleanup design

status: COST TRACK ACTIVE — implemented independently, one atom at a time
owner: Dais / Life Manager Cloud
scope: provider cost control, tenant usage metering, Stripe packaging decision, Cloud daily-runtime cleanup

## 0. Ordering and exclusions

- The remote Cloud product agent owns `CLOUD-01` through `CLOUD-08` in
  `2026-08-28-life-manager-cloud-telegram-product-ux-design.md`. This cost track runs independently
  and does not edit, reorder, or wait for that checklist. If the Cloud agent requests verification,
  this track may inspect its tests and evidence read-only without taking over its implementation.
- Do not use ElizaOS, replace the Life Manager runtime, stop Telegram/Calendar/routing, or modify
  local loops and Alpaca worktrees.
- Do not change Stripe prices before per-tenant production usage is measured. Existing Stripe remains
  the only payment authority.
- A file is not deleted merely because its name says legacy. Require production reference zero,
  registry/owner zero, tests proving the replacement, and provider replay-zero where effects exist.

## 1. Measured incident baseline

Google Cloud billing account `017949-09509F-6A3FB6` reports July 2026 subtotal JPY 28,568 and
August subtotal JPY 78,306: +JPY 49,738, +174.1%, 2.741x. August service totals were Geocoding
JPY 40,095, Gemini API JPY 13,444, Directions JPY 9,549, Routes JPY 7,924, Places JPY 5,054,
and Vertex AI JPY 2,227.

The dominant Maps credential was `lateness-directions`. Monitoring attributed approximately 21,524
Directions 4xx responses and 22,751 Geocoding 4xx responses to it in August. Railway `life-call`
boot logs showed the standalone scheduler owner and all daily loops active. GCP Cloud Run and Cloud
Scheduler were not competing owners. Therefore the incident was repeated paid failure work in the
single active Railway scheduler, not legitimate one-user demand and not a second Cloud deployment.

The billing account now has a non-blocking JPY 35,000 monthly budget with current-spend alerts at
50%, 75%, 90%, and 100%. Provider quotas remain unchanged because a blind cap can remove required
Calendar travel behavior.

## 2. Exact code findings

1. `apps/life-manager/migrations/2026-07-04-lm-route-cache.sql` creates `lm_route_cache`, but the
   production construction in `apps/life-manager/lib/travel.js` supplies only `new Map()` to
   `makeRouteCache`. No production code reads or writes `lm_route_cache`. A process restart loses all
   accepted route cache entries.
2. `apps/life-manager/lib/route-cache.js` stores only non-null results. A provider 4xx, timeout, or
   no-route result returns null and is retried on the next eligible tick. This matches the measured
   paid-failure pattern.
3. The 30-minute travel loop and 60-second Telegram reminder loop both use `directionsRoute`; without
   a durable store they cannot reliably reuse one accepted or failed result across restarts/owners.
4. `scheduler.js` and `inngest/functions.js` are not two independent business implementations:
   Inngest imports the per-user functions from `scheduler.js`, and `maybe-start-loops.js` owns their
   mutual-exclusion predicate. Retain both until one deployment mode is formally retired.
5. `routesDriveMinutes` / `directionsMinutesGoogle` are no longer on the default production fallback,
   consistent with Routes charges disappearing after the free-transit-first release. They remain
   explicit compatibility/test seams; assess deletion only after `CLOUD-02` timing acceptance.

## 3. Pricing decision before Stripe mutation

The launch recommendation is a hybrid subscription, not raw provider-cost pass-through:

| Plan | Monthly price | Included product usage | Overage behavior |
|---|---:|---|---|
| Free | JPY 0 | Calendar connection, settings, cached route display, up to 20 successful managed actions/month, no optional phone | Keep read/settings/cached results available; ask to upgrade for new paid actions |
| Plus | **JPY 4,980** | Core daily Telegram/Calendar automation and 500 successful managed actions/month | Offer prepaid 100-action pack for JPY 980; never count internal retries or provider failures |
| Pro | JPY 9,800 | 2,000 successful managed actions, optional phone allowance, priority/high-cost AI | Additional prepaid packs; explicit warning before high-cost media/agent work |

`successful managed action` is the customer-facing value metric. Internal polling, cache hits,
retries, 4xx/5xx, duplicate suppression, and provider reconciliation cost zero customer credits.
Track actual vendor cost separately for margin control.

JPY 4,980 is provisional until the beta records two to four weeks of normalized per-tenant cost. The
release gate is p95 monthly direct cost at or below JPY 1,000 for Plus (at least 80% gross margin before
support and fixed overhead). If it exceeds that boundary, reduce provider waste or lower included
high-cost actions; do not silently degrade Calendar, Telegram, or cached daily behavior.

## 4. Free operation boundary

Everything cannot be guaranteed free while Life Manager pays commercial LLM, Maps, telephone, hosting,
and payment fees. A sustainable free tier is possible by keeping its marginal paid work bounded:

- use Google Maps monthly free SKU caps only as a shared safety buffer, never as an unlimited promise;
- free transit first, durable accepted-route cache, and bounded negative cache before Google fallback;
- deterministic code before LLM and small models before expensive models;
- no optional phone or video generation in Free;
- cached/read/settings behavior remains available after the action allowance is exhausted;
- referral/sponsor credits can fund extra actions, but never hide provider cost or promise permanent
  unlimited use.

## 5. OSS decision

Reviewed current source from `openmeterio/openmeter`, `BerriAI/litellm`, and `unkeyed/unkey`.

- OpenMeter provides event metering, entitlements, credits, and billing, but its full stack is beta and
  duplicates existing Supabase/Stripe authority. Do not add it for launch.
- LiteLLM provides LLM virtual keys, spend tracking, budgets, and caching, but it cannot meter Maps,
  Telegram, or telephone value consistently. Do not add an AI gateway before the existing call sites
  have one usage contract.
- Unkey provides API-key analytics and durable rate limits, but Life Manager's public product is
  Telegram/tenant based, not a customer API. Do not add it now.
- Reuse the event/entitlement concepts: append a tenant-scoped usage event to the existing Supabase
  ledger and report accepted aggregate usage to Stripe's official usage meter. No new billing engine.

Sources:

- Stripe usage-based billing: https://docs.stripe.com/billing/subscriptions/usage-based
- Google Maps SKU pricing/free caps: https://developers.google.com/maps/billing-and-pricing/pricing
- Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- OpenMeter: https://github.com/openmeterio/openmeter
- LiteLLM: https://github.com/BerriAI/litellm
- Unkey: https://github.com/unkeyed/unkey
- Reclaim pricing: https://reclaim.ai/pricing
- Motion pricing: https://www.usemotion.com/pricing
- Sunsama pricing: https://www.sunsama.com/pricing

## 6. Ordered TODO owned by this track

This track owns these atoms in the exact order below while the remote Cloud product agent separately
owns `CLOUD-01` through `CLOUD-08`. Finish and integrate one cost atom before starting the next.

1. **COST-01 — observe (DONE):** add one tenant/provider/feature usage-event contract and dashboard
   query; record success, cache hit, failure class, provider units, and estimated direct cost without
   secrets. Integrated by PR #4282. Production RPC readback returned HTTP 200 and 17 natural Maps
   usage events for 2026-09-06 UTC: Directions failure 5 / USD 0.025 estimated, Geocoding failure
   5 / USD 0.025, and Geocoding success 7 / USD 0.035. The estimates are provider list-price
   accounting events, not a replacement for the Google Cloud invoice.
2. **COST-02 — stop paid failure replay (DONE):** wire `lm_route_cache` to production, add bounded
   negative cache for deterministic 4xx/no-route and short backoff for timeout/5xx, and prove a later
   valid route can recover. PRs #4291 and #4298 integrated the durable store and the production-observed
   raw-address fallback gap. Focused route/travel tests passed 135/135; a fresh-process test proves zero
   additional provider calls during the 30-minute deterministic-failure TTL and recovery after expiry.
   Production build `342aaf07f` returned HTTP 200, wrote 4 natural success rows and 5 natural
   `google/no_route` negative rows with TTL 1800 seconds, and the next readback kept paid Directions
   failures at 5 (zero increase). Network/5xx uses a 120-second backoff. Raw addresses are represented
   only by opaque SHA-256 cache scopes and are not persisted.
3. **COST-03 — one route fact (DONE):** travel block, Telegram reminder, and optional call reuse one
   event/version-scoped route result. Exact event ID、schedule、endpoints、go/return purpose changes
   invalidate it. PR #4419 merged as `d69b21ee5773f4629a15d226008be7095d68cf02`; focused
   current-main route/travel/reminder/wake verification passed 129/129 and Railway health serves that SHA.
4. **COST-04 — owner and spend guard:** prove exactly one Cloud scheduler owner, add tenant/provider
   daily circuit breakers that preserve cached/read/settings behavior, and alert before rejection.
5. **COST-05 — beta unit economics:** run two to four weeks, calculate p50/p95 direct cost per active
   tenant and per successful managed action, then confirm or revise JPY 4,980 before Stripe mutation.
6. **COST-06 — Stripe meter:** map only successful managed actions to the existing Stripe customer,
   add allowance/credit-pack behavior, test duplicate/replay/refund boundaries, then request the
   separately authorized real payment proof.
7. **CLEAN-01 — compatibility retirement:** after `CLOUD-02`, prove whether old Routes Pro helpers and
   legacy Directions compatibility seams have production callers. Delete only zero-reference seams
   and their now-invalid tests/comments.
8. **CLEAN-02 — runtime retirement:** after the chosen Cloud scheduler mode has natural production
   receipts, retire the unused alternate host adapter/registration surface without deleting shared
   per-user business functions.
9. **CLEAN-03 — final census:** run source reference, deployment entrypoint, loop registry, provider
   traffic, migration, and secret-free receipt checks; record retained owners and deletion evidence.

## 7. Acceptance

- Normal Calendar/Telegram/cached daily behavior remains available at every plan boundary.
- One user action produces at most one accepted billable provider result per event version and purpose.
- Deterministic 4xx/no-route repeats produce zero additional paid calls during the negative-cache TTL.
- Internal failures and retries never consume customer allowance or enter Stripe usage.
- Plus p95 direct monthly cost is at most JPY 1,000 before enabling the JPY 4,980 Stripe price.
- No local loop, Alpaca state/worktree, ElizaOS component, or unrelated production route is modified.

## 8. Friend beta launch and pricing validation

Cloud engineering and operator acceptance are complete. Real friend UAT is the next action. The
public entrypoint is `https://aniccaai.com/life-manager`, and the fastest mobile entrypoint is
`https://t.me/LifeManagerBotbot?start=lp`.

### Product promise

予定のたびにGoogle Calendarと地図・乗換案内を行き来し、出発時刻を逆算する手間をなくす。
Life ManagerはGoogle Calendarの次の予定に合わせて移動時間を確保し、出発前に経路を
Telegramへ送る。「Google Calendarや地図を二度と見なくてよい」とは表現しない。予定の登録・変更、
経路変更の確認は引き続き必要になる場合があるため、「毎回開いて調べなくていい」を正本の表現とする。

### Friend DM

> 今、Life Managerの少人数βを始めてるんだけど、5分だけ試してもらえない？
> Google Calendarをつなぐと、次の予定までの移動時間を自動で予定に入れて、
> 出発前に電車や乗換案内をTelegramで送ってくれる。
> 毎回カレンダーと地図アプリを行き来して、出発時間を逆算しなくてよくなるものです。
> 電話通知は任意で、3日間無料。
> https://t.me/LifeManagerBotbot?start=lp
> 使って詰まったところだけ教えてほしい！

### X launch post

> 次の予定に間に合うために、カレンダーを確認して、乗換案内を検索して、
> 逆算して出発時間を決める。この作業を、毎回やらなくてよくしました。
>
> Life ManagerはGoogle Calendarを読み、移動時間を予定として自動で確保。
> 出発前になると、乗る電車と乗換案内をTelegramへ送ります。
>
> 電話通知は任意。3日間無料で試せます。
> https://t.me/LifeManagerBotbot?start=lp

公開画像には実在の予定名、住所、現在地、個人名を残さない。Telegramの経路通知は、これらを
トリミングまたはぼかした画像だけを使用する。旧投稿の「生活をまるごと管理」「電話で起こす」は、
現在のDAILY機能より広く、電話が必須に見えるため再利用しない。

### Ordered post-release TODO

1. Daisが上記DMを友人へ送り、同じTelegramリンクをXへ投稿する。
2. 友人UATで、開始、Google Calendar接続、home設定、Travel block、Telegram経路通知までを確認する。
3. 本番usage ledgerを2〜4週間集計し、active tenantごとのp50/p95直接原価と成功action単価を確定する。
4. Plusのp95直接原価が月額JPY 1,000以下なら、月額JPY 4,980を確定する。超える場合は、機能を止めずにprovider wasteと含有量を先に調整する。
5. 価格確定後にだけ既存Stripeの価格・allowanceを変更し、test modeでentitlementとwebhook replayを再確認する。

現時点の単一推奨価格は月額JPY 4,980。JPY 10,000 MRRを明確に超えるには有料会員3人が必要で、
MRRはJPY 14,940になる。2人ではJPY 9,960で目標を40円下回る。正常化後の直接原価を
1人月JPY 1,000以下に保てた場合、3人の直接原価上限はJPY 3,000、決済手数料・support・固定費前の
粗利はJPY 11,940、粗利率は約79.9%になる。現在のGoogle Cloudアカウント全体のforecastを
「1人当たり原価」とは扱わない。そこには製品外利用と請求lagが含まれるため、正確なunit economicsは
手順3のtenant別実測で確定する。

## 9. Superseding monetization decision — monthly allowance, one plan

「beta」「3日trial」「onboarding直後の月額プラン確認」は廃止する。Life Managerは正式製品として、
card不要の毎月無料利用枠を全員に付与する。無料枠は毎月resetし、内部API tokenや失敗retryではなく、
ユーザーへ価値が届いた`successful managed action`だけを消費する。Calendar接続、設定変更、cache hit、
内部poll、重複抑止、4xx/5xx、provider retryは無料枠を消費しない。

無料枠の初期値は月30 successful managed actionsとする。80%到達時は完了したactionの後に1回だけ予告し、
100%到達時は進行中・claim済みの通知を完了してから次の新規provider effectを保留する。枠を使い切っても、設定、接続解除、既存情報、
cache済み結果は利用可能に保つ。新しい有料provider effectだけを停止し、Telegramで現在の利用数、次回reset、
継続方法を説明する。途中でStripe情報を要求せず、本人が継続を選んだ時だけStripe Checkoutを開く。

有料planはLife Manager `$29/month`の1つだけとする。月500 successful managed actionsを含み、電話は
明示opt-inかつ月間allowance内で提供する。複数tier、provider別課金、ユーザーに見えるtoken換算、前払いcard、
onboarding paywallは作らない。将来agent economyがtenantのcomputeを実際に賄える場合、検証済み収益を
creditとして本人の請求へ充当できるが、未実現収益を無料化の根拠にはしない。

### 電話の利用枠: provider契約と製品側の現状

Life Managerが発信先・時刻・会話を決め、Telnyxが電話網へ接続する。Telnyxの
[`time_limit_secs`](https://developers.telnyx.com/api-reference/call-commands/dial)は**1回の通話の最長時間**で、
30〜14,400秒を受け付ける。省略時は14,400秒なので、残枠が30秒未満のときに値を省略して発信しない。
月3,600接続秒はTelnyxの要件ではなく、この製品の有料電話向け費用上限である。
電話へ明示opt-inした有料ユーザーには、場所の有無や移動時間に関係なく、時刻のある実予定ごとに
**予定開始10分前と5分前の2回**発信する。2回は別のclaim・allowance identityを持ち、
1回目の成功で2回目を抑止しない。Telegramは補助であり、読むことを電話の前提にしない。
月間電話枠の枯渇がこの約束を止める点は残る商品上の制約として明示し、無音のAI通話を成功と数えない。
公開例では、[Noota](https://telnyx.com/customer-stories/noota)はTelnyxを電話基盤に使い、
[自社の料金表](https://www.noota.io/pricing)に月ごとの含有分数を置く。
[Dialpad](https://telnyx.com/customer-stories/dialpad)もTelnyxを通話基盤に使い、
[AI Agentの料金](https://www.dialpad.com/pricing/)を価値が届いた会話単位で説明する。
これらは月3,600秒を支持する証拠ではなく、通信原価と利用者向け商品ルールを分ける実例である。
[Telnyx公式Node SDK](https://github.com/team-telnyx/telnyx-node/blob/master/src/resources/calls/calls.ts)の実コードは
`call_session_id`を通知の相関ID、`time_limit_secs`を通話上限として扱う。
[公式サンプル](https://github.com/team-telnyx/demo-node-telnyx/blob/master/voicemail-detection/callControl.js)は
webhookへ先に200を返すが、永続的な課金台帳の実装例ではないため、製品側は別にCDR再照合を持つ。

**As-is（確認済み）:** 発信コードは30秒未満を送信前に拒否し、schedulerは30秒未満の予約を
解放して発信を見送る（PR #5295、#5297）。本番の別経路`/test-call`はTelnyxで受理され、
留守番電話への接続・終了と公式APIの3秒の通話時間を確認済み。ただしこれは予定時刻のwake経路ではない。
対象tenantには古い`accepted`が29件あり、予約を含む月間残枠は28秒だった。
29件の`GET /v2/calls/{id}`は`90015`を返したが、Telnyxの
[`detail_records`](https://developers.telnyx.com/api-reference/detail-records/search-detail-records)で
各wakeのsession IDに一意に一致する終了済み・未接続・通話0秒の履歴を29/29件確認した。
既存の所有token付き精算RPCで29件を`0`秒の`succeeded`へ確定し、使用扱いは3,572秒から92秒、
残枠は3,508秒となった。旧予約は削除せず、精算済み行として保持する。
予定wakeの本番E2Eは、発信・終了webhook・秒数精算までは通ったが会話はFAIL。
最初はDais本人の応答をAMDが`machine`と誤判定して3秒で切断した。
AMD OFFの再試行は14秒接続したものの、本人は自分だけが話しAIの声は聞こえなかった。
`gotAudio=true`とWebSocket送信フレーム数はTelnyxでの再生証明ではない。
次の通話前にTelnyxのerror/mark応答、送信音声の長さ・音量、Geminiの入力/出力/割り込みを
内容を記録せずに計測し、AI音声がどこで止まるかを確定する。
AMDの分類はreceiptへ残すが、`machine`だけで通話を切らない。`not_sure`はTelnyxの
[推奨](https://developers.telnyx.com/docs/voice/programmable-voice/answering-machine-detection)どおり
人として扱う。分類が`human`/`not_sure`ならmanaged actionを精算し、それ以外は過大計上しない。
音声入力はTelnyxの`stream_codec=PCMU`を明示し、ブリッジのμ-law復号と一致させる。
main由来本番コミット`96d1586`の制御したT-10 wakeで、Daisは**AIの声が聞こえ、返事もあった**と確認した。
署名済み終了webhook、AMD=`human`、Telnyx公式`GET /v2/calls/{id}`の終了済み10秒、
voice ledgerの`succeeded/10秒`、managed actionの`succeeded`を同一通話で読み戻した。
これは注入したテスト予定であり、実カレンダー取得とT-5の自然発信は未確認。

**To-be:** 時刻のある各実予定の開始10分前と5分前に別々の電話をかける。
同時刻の別予定は別IDで扱い、電話ごとに正確な残枠と通話上限を使う。
電話の結果は、利用者価値を混同しないよう次の3つに分けて保存する。

1. `conversation`: 本人が応答し、AIとの会話が成立した。実接続秒数だけを月3,600秒枠から引く。
2. `no_answer`: Telnyxが発信を受け付けたが、本人の応答を確認できず終了した。予定前に発信した事実として残すが、会話成功とは扱わず、月3,600秒枠は消費しない。
3. `dial_failed`: 発信要求をTelnyxへ届けられなかった、またはproviderの成功を確認できなかった。利用者へ発信済みとは表示しない。

終了後は署名済み[`call.hangup`](https://developers.telnyx.com/docs/voice/programmable-voice/voice-api-webhooks)
と公式通話記録から実接続秒数、`hangup_cause`、provider相関IDを一度だけ精算する。
`no_answer`は「予定前に発信しました（応答なし）」と表示し、携帯に通知が表示されたことや利用者が見たことは断定しない。
パネルでは、通話結果の履歴と「今月の会話残り時間」を別の項目として表示する。

**受け入れ条件:**

- 応答なしの終了通知を受けた通話は、`no_answer`として予定・通話相関IDに紐づき、会話秒数は0になる。
- 応答ありの通話は、公式通話時間だけが月3,600秒枠へ一度だけ加算される。
- ハングアップ時点でAMDが未確定な正の通話時間は月3,600秒枠へ加算せず、後着の`human`/`not_sure`で実秒数を精算する。`machine`は応答なしとして0秒にする。
- stale voice reconciliationも`call_outcome`/AMD証拠を確認し、結果不明のCDRを会話秒数として精算しない。
- 発信失敗またはprovider不明の通話は、`conversation`や`no_answer`として表示されず、再照合可能な状態で残る。
- 同じ終了Webhookを再送しても、履歴・利用秒数・managed actionが二重計上されない。
- パネルには「応答なし」「会話できた」「発信失敗」と月間会話残り時間が別々に表示される。

**ユーザー体験と月3,600秒枠:**

- 月60分は「電話の回数」ではなく、AIと接続して会話した秒数の合計である。
- 応答なし、留守番電話（`machine`）、発信失敗は会話秒数0秒。電話を試みた事実は履歴に残るため、利用者が取れなかった予定でも「予定前に発信しました（応答なし）」として価値を残す。
- 利用者が応答した場合だけ、公式CDRの接続秒数を1回精算する。60分を使い切るまでは、T-10/T-5の電話を通常どおり行う。
- 残りが30秒未満、または月3,600秒を使い切った後は、新しいAI電話を発信しない。Telnyxの`time_limit_secs`最小30秒を満たせず、無制限の原価を作らないためである。
- 月枠が尽きても、Calendar、Telegram、保存済み設定、履歴はそのまま使える。電話枠は次の月次リセットで戻る。
- 「枠を使い切った後も、AI会話なしのring-only発信を残す」案は現在の契約に含めない。採用する場合は、発信回数・Telnyx原価の別上限を先に仕様化する。

**Voice outcome sliceの残りTODO:**

1. **DONE:** 本番projectを`cycgdwndgfgdbnndithc`に確定し、migration、schema/RPC/index readback、Railway health readbackを完了。
2. **DONE:** T-10/T-5自然E2Eで`no_answer`とvoice ledger 0秒を確認。
3. **OPTIONAL PRODUCT DECISION:** 60分後のring-only発信を商品として追加するか判断する。現行実装では追加発信しない。

**2026-09-17実測status:** voice outcome・Webhook精算・Panel表示のfocused suiteは最終コードで247/247 PASS。
Supabase DashboardのOwnerセッションで本番project `Anicca Project Anicca`（ref `cycgdwndgfgdbnndithc`）を確認した。
停止メールの`life-manager-staging-20260808`（ref `ulhsqqkyejzvqgoyjwte`）はstagingであり、本番Railway接続先ではない。
本番SQL Editorで`2026-09-17-lm-wake-call-outcome.sql`を実行し、Successをreadbackした。
SQL readbackは3列、2 constraint、`lm_wake_log_uid_called_outcome_idx`、
`record_lm_wake_telnyx_outcome(p_uid text, p_event_key text, p_claim_token text, p_telnyx_call_control_id text, p_call_outcome text, p_hangup_cause text, p_connected_seconds integer)`を確認した。
Service-role REST readbackは列HTTP 200、Outcome RPC OpenAPI掲載、存在しないwakeへのRPC probe HTTP 200/戻り値0。
Railway production `/health`はmain由来build `0e0758d7f7495af034f28e15bb4bdd3ab9f20b60`でSUCCESS。
検証用の実カレンダー予定（19:20 JST）ではT-10とT-5の両方が自然発火し、各wake rowをTelnyx公式GET（HTTP 200）で照合した。
両方とも`amd_result=machine`、`answered_at=null`、`lm_wake_miss=no_answer/time_limit`、
voice ledger=`succeeded/0秒`となり、応答なし通話を会話時間として請求しないことを本番で確認した。
検証用イベントはComposio delete（HTTP 200）後、`GOOGLECALENDAR_EVENTS_LIST`（HTTP 200）で対象IDが不在であることを確認した。
旧schema fallbackは残し、新Outcome列/RPCが適用済みの場合は新経路を優先する。

**Ordered correction TODO項目3の本番是正:**

1. **DONE:** 残留`accepted`29件をwake sessionとTelnyx CDRで照合し、29件を接続0秒で精算する。
2. **DONE:** CDR再照合を既存wake ownerへ組み込み、本番自然起動で実行を確認する。
3. **DONE (no-answer path):** 実カレンダー予定でT-10とT-5が各1回発火し、Telnyx公式CDR、AMD、`no_answer`、voice ledger 0秒を読み戻した。
   この証跡は応答なし経路の確認であり、会話成立を意味しない。
4. 新規ユーザー向け`wake_policy=all-events`のDB既定値を適用する。既存の明示的な`travel-only`は保持する。
   月3,600秒の硬い上限は「全予定に電話する」という商品約束を止めるため、料金・原価と合わせて解消する。

無料枠到達時の正本copy:

> 今月の無料利用分を使い切りました。Life Managerの設定とこれまでの情報はそのまま残っています。
> 引き続きLife Managerに生活を管理させる場合は、月額$29でこのまま続けられます。
> 次の無料利用分は翌月に戻ります。

`$10K MRR`はUSD 10,000/monthを意味する。$29 planでは345 paying usersでUSD 10,005 MRRになる。
JPYはGoogle Cloud invoiceの照合にだけ併記し、MRR、ARPU、価格、粗利の主通貨はUSDとする。

### Ordered correction TODO

1. **DONE (local/review) — Telegram-native onboarding:** Google consent以外のMini App必須stepを削除する。
   `/start`のprivate-chat actor claim、Telegram言語による日英表示、通常URLのGoogle consent button、
   WebApp非使用、cookie不要のone-time OAuth callback、Calendar ACTIVE同期、Telegram復帰と自宅住所質問を
   branch `feat/lm-telegram-native-start-20260907`で実装。ローカルcontractはPASS済み。
   ローカルcontract 153/153とfresh read-only reviewがPASS。本番反映は項目4でまとめて行う。
2. **DONE (local/review) — optional phone:** 電話の用途、任意性、番号保存とcall opt-inの分離をTelegramで実装する。
   電話skip、番号保存時call OFF、別質問での明示opt-in、日英copy、onboarding paywall削除を実装し、
   関連test 160/160とfresh read-only reviewがPASS。
3. **DONE (local/real PostgreSQL/review) — monthly free allowance:** 3日trial表示とonboarding内の料金CTAを削除済み。
   月30回（paidは500回）のtenant/month/event ledger、15分pending reservation、success確定、月1回の枠到達noticeを追加し、
   Travel blockとTelegram reminderの新規route effect前へ接続。関連test 141/141とTravel wiring 113/113がPASS。
   任意電話のprovider effectと成功receiptも同じevent allowanceへ接続済み。ただしfresh reviewで次のcorrectness gateが
   fix-firstとなったためDONEにしない。(a) reservation tokenを発行し、complete/releaseを予約月と所有tokenで照合する、
   (b) 同一eventの並行workerは1つだけprovider effectを実行する、(c) not-due・未選択・duplicate・no-route・past・
   create/send失敗は自分のpendingだけを解放する、(d) route cache/negative cacheをallowanceより先に読み、枠到達後も
   cached/read/Calendar/Telegram/settingsを維持する、(e) 80%と枯渇noticeをplan-awareなused/limit/reset copyにし、
   exhausted後の80%逆順送信を禁止する、(f) noticeの曖昧配送を永続reconciliation可能にする。
   実DBで並行reserve、誤token拒否、月跨ぎcomplete/release、pending残留0、limit後cache hitのprovider call 0、
   exhausted優先、notice replayを証明。さらに通常通話をpaid-onlyにし、tenant timezoneでresetする月3,600接続秒の
   owner-token ledgerを追加した。並行予約込みで上限を超えず、発信前に`accepted`を永続化し、Telnyx
   `time_limit_secs`へ残秒を渡す。transport/5xx/malformed successはclaimを保持し、署名済み`call.hangup`から
   公式`call_duration`を取得してのみ精算するため、bridge crash、response loss、`LM_AMD=off`でもreplay-safe。
   関連test 236/236、migration二重適用、実PostgreSQLの3,480秒時並行reserve 1/2件、誤token拒否、37秒精算後
   残83秒、stale accepted保持をPASS。fresh read-only reviewはSHA `999755fe0`を`ship`判定。
4. **IN PROGRESS — production:** 1〜3はPR #4524としてmainへmerge済み（merge SHA
   `58347e26f107cd6a8f4a103a5fbc0e48f456748a`）。本番はRailway `life-manager / production /
   life-call`とSupabase project `cycgdwndgfgdbnndithc`。read-only schema probeでmonthly allowance table、
   voice ledger、Telegram OAuth claim RPCがHTTP 404、route-cache新columnがHTTP 400となり、3 migrationが
   未適用と確認した。Supabase dashboardの既存sessionは対象projectを持たない別accountで、対象GitHub accountの
   通常loginは2FAで停止し、GitHub Mobile確認もproviderがidentity確認不能として拒否した。次の一手はDaisが
   GitHub 2FAを1回完了することだけ。その直後に3 migration適用、main由来Railway deploy、health/schema/readbackを行う。
   GitHub Mobile 2FA後、3 migrationは本番へHTTP 201で適用し、allowance/voice/route/OAuth schema readbackは
   4/4 HTTP 200。本番`life-call`はdeploy前からCRASHEDで、最新main deployもrepo-rootの
   `runtime/contracts/common-record.cjs`をapp-root imageが含まないため起動時MODULE_NOT_FOUNDとなった。
   起動時の不要なcontract解決だけを遅延する最小修正とRailway app-root再現testを追加し、関連62/62がPASS。
   次はfresh review、hotfix merge/deploy、health SHA readbackで項目4を閉じる。
5. Telegram Webへ既存sessionまたは通常loginで入り、DaisのTelegram actorと隔離test actorで、新規開始から
   最初のTravel block・乗換案内・Telegram provider receipt・replay追加送信0までE2Eする。
6. E2E receipt後にだけ公開導線を再開し、友人DMとX投稿を行う。

## 10. `$29/month` unit-cost envelope

Planning exchange rate is USD 1 = JPY 150. One normal active user means 60 physical events/month,
one accepted route fact per event/version/purpose, at most 100 short Gemini text actions, and optional
calls averaging one total connected minute per physical event across T-10 and T-5. Free SKU caps are
excluded from the safety calculation even when the actual invoice is lower.

| Component | Unit assumption | Monthly cost without calls | Monthly cost with calls |
|---|---:|---:|---:|
| Google Geocoding | up to 2 × USD 0.005 per physical event | USD 0.60 | USD 0.60 |
| Google Routes/Directions | up to 2 × USD 0.005 per physical event | USD 0.60 | USD 0.60 |
| Gemini short text | 100 bounded Flash actions | USD 0.20–1.00 | USD 0.20–1.00 |
| Calendar / Telegram APIs | no per-message product charge | USD 0 | USD 0 |
| Gemini Live | measured planning rate about USD 0.023/min | USD 0 | USD 1.38 |
| Telnyx voice, streaming, AMD, destination carrier | conservative blended reserve | USD 0 | USD 2.00–4.00 |
| provider error / FX reserve | after cache and replay fences | USD 0.50–1.50 | USD 1.00–2.50 |
| **Direct API total** | | **USD 1.90–3.70** | **USD 5.78–10.08** |

Therefore `$29/month` is sufficient only while phone usage is bounded. The paid plan includes at most
60 connected phone minutes/month; after that, Telegram, Calendar, Travel block, and cached/read/settings
continue, while new phone calls wait for the next monthly reset. This is one plan with a fair-use boundary,
not a second tier. At direct cost USD 10.08, contribution before Stripe, hosting, support, and fixed costs is
USD 18.92 and direct-API margin is 65.2%. At the expected USD 6 cost it is USD 23 and 79.3%.

The free allowance is 30 completed managed events/month, not 30 internal effects. One event may create a
Travel block and one Telegram乗換案内 while consuming one allowance unit. Optional phone is excluded from
the standing free allowance except for one onboarding test call; this caps expected free-user direct API
cost around or below approximately USD 1.50 before shared fixed costs. Usage resets monthly at the tenant billing timezone.

## 10.1 Revenue loop execution status

Life Manager has three cooperating business paths:

1. **Marketing path:** `skills/life-manager/life-manager-daily.sh` generates one bounded creative,
   distributes it through the configured adapter, and records the next improvement. This proves a
   marketing pass, not a paid subscriber.
2. **Self-Build / Product Improvement loop (#11 in `README.md`):**
   `skills/life-manager/self-build-daily.sh` selects one eligible loop-authored fix PR, sends it
   through the protected merge guard, appends a durable day receipt, and reports the result. This
   improves Life Manager; it does not create revenue unless activation or retention improves.
3. **Money/CFO path:** `skills/self/life-manager-loop/loop.sh` reads Stripe active subscriptions,
   verifies `/health`, and chooses the next weakest funnel step. The current measurement run at
   `2026-09-17T14:42:38Z` returned `lm_mrr_usd=NA` and
   `HEAL-NEEDED — STRIPE-KEY-MISSING`; it wrote a self-heal request instead of claiming `$0`.
   A production Supabase billing readback on 2026-09-18 found one `paid=true` row but
   `plan_status`, `current_period_end`, and `stripe_subscription_id` were all null. The entitlement
   flag is therefore not an active-subscription or MRR receipt.

### 2026-09-18 Stripe CLI recovery and production readback

The previous `STRIPE-KEY-MISSING` finding covered the money loop's runtime secret path, not the
Stripe account itself. The operator CLI path was recovered through the existing Stripe owner session:

- `stripe login --complete` returned `Done!` for the existing `anicca` account (`acct_1RT5QgEeDsUAcaLS`).
  The active CLI profile now has a refreshed live credential expiring 2026-12-16. No credential value is
  recorded here.
- `stripe customers list --live --limit 1` returned a live customer list successfully.
- `stripe balance retrieve --live` returned `livemode=true` with available and pending JPY balances of
  zero. This is a current balance readback, not lifetime revenue.
- `stripe subscriptions list --live --status active --limit 100` returned `has_more=false` and
  `page_count=0`. Provider-side active-subscription MRR is therefore USD 0 at this readback; there are
  no subscription rows from which to read a price or period end.
- The browser flow used the existing Google login and Stripe two-factor authentication. Credentials are
  not stored in the repository or this spec.

The product money loop was incomplete at the 2026-09-17 measurement because its private runtime key path
was missing. The implementation below adds a secure CLI-backed read path for the authenticated local
operator and records the provider readbacks in the loop state; no credential value is copied into Git.

**2026-09-18 implementation readback:** `loop.sh` now accepts Stripe restricted live keys and falls back
to the authenticated Stripe CLI when no private runtime key is present. The bounded run returned
`stripe_source=cli`, `lm_mrr_usd=0.0`, `active_subscription_count=0`, no subscription period end,
`refund_count=3`, and `failed_payment_count=91`, with `heal=none`. Fixture coverage is 11/11 PASS.
The private runtime does not retain the invalid CLI config value; the OAuth-backed CLI is the read path.

**2026-09-18 price/link alignment readback:** The live product had an existing `$20/month` price and
Payment Link. A new live `$29/month` price was created under the same `Anicca Life Manager` product with
lookup key `life_manager_monthly_29`; a new Payment Link was created at
`https://buy.stripe.com/cNifZhgcC3h44yYeMK2880X`, verified active with `unit_amount=2900`, USD monthly,
and Managed Payments disabled. The old `$20` Payment Link was disabled after the new link was verified.
Railway production `LM_STRIPE_PAYMENT_LINK` now reads back as the new URL and `/health` remains 200.

**2026-09-18 funnel/self-build readback:** The same money-loop wake now reads Supabase production
funnel counts without persisting personal fields: `funnel_users=315`, stage counts
`calendar=4,done=1,null=310`, Calendar connections `3`, saved phones `3`, call opt-ins `2`,
`paid=1`, and `active_plan=0`. The self-build picker now reads this private state, identifies the
largest measured funnel drop (`calendar` here), and prioritizes a loop-authored PR carrying the matching
`[lm-metric-focus:<stage>]` marker while preserving the existing eligibility and merge guard.
The picker/runtime suites pass 79/79; this proves metric-aware selection, not a growth result.

**Remaining revenue TODO, in order:**

1. **DONE:** Wire the confirmed Stripe live account into the money-loop runtime and record active
   subscriptions, period end, refunds, failed payments, and `lm_mrr_usd` in the loop state.
2. **DONE:** Make `$29/month` canonical across the live Price, Payment Link, Railway runtime, landing
   comments, Telegram copy, and money-path tests. The old `$20` link is disabled.
3. **DONE (measurement path):** Read back the product funnel from Supabase and persist only aggregate
   counts in the bounded money-loop state. Landing visits, renewal, and referral remain unavailable until
   their provider adapters produce a real receipt.
4. **IN PROGRESS (outcome proof):** The self-build loop now selects metric-matched PRs, but each merged
   change still needs a receipt-backed release and a measured movement in activation, retention, cost, or
   MRR.
5. Scale the selected plan to the required active paid count. At `$29/month`, 345 active subscribers
   produce `$10,005` gross MRR.

These are the remaining business gates. Voice outcome migration, no-answer settlement, and the
production health/readback gate are already complete.
