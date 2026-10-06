# Anicca eBook Revenue Loop — Design

> この設計文書は商品・配布間の契約を定めます。全体の実行順と現在cursorの正本は Life Manager unified SSOT です。

## 成果

1. eBookを既存の自社アカウントで配信し、最初の自然な有料Stripe注文と正しいlocaleのPDF納品を同一campaignに結び付ける。
2. Letter/Tegamiの有料subscriptionだけをMRRに数える。trialやeBook一回購入はMRRではない。
3. その最初のeBook注文・PDF receipt後に、Capafy Instagram marketingだけを開始する。Capafyの商品、listing、account lifecycleの開発は別担当の所有範囲に置く。
4. eBookの14日間readbackはCapafy開始後も継続し、後続の収益作業を止めない。

## 範囲と担当

- eBook checkout/webhook/PDF fulfillmentは anicca-products の既存Stripe・Netlify・Supabase・Resend経路を使う。
- eBookとCapafyのcreative・投稿ownerはLife Managerの既存Marketing Engine、account registry、publication adapterへ接続する。旧OpenClaw schedulerは再有効化しない。
- eBook marketingは既存の本人所有Instagram/TikTok accountだけを使う。registryとprovider readbackでidentity・good-standingを確認できないaccountは使わず、代替accountも作らない。
- Capafyは既存の life-manager-capafy-ig Postiz laneを唯一のpublish ownerにする。Capafy product code・価格・listing・account lifecycleは変更しない。
- eBook向けsystem-generated baseline creativeは、ユーザーが委任したeBook marketingのstanding policy内で配信する。対象product、locale、既存account、approved claims、CTA/token、renderer、media formatを決定的に検査し、Daisが直接編集したcopyは明示確認なしに変更・公開しない。

### Rendererと配信契約

- English `ebook-en-anicca-monk`は既存のHeyGen CLIを使い、Marketing Engineのapproved baseline scriptをAvatar IVで映像化する。HeyGenのfreeform script writerに商品claimを作らせない。avatar/voice IDは既存のAnicca monk素材を使い、API render receiptと費用readbackを保存する。
- Japanese `ebook-ja-watercolor`はWatercolor Monk Factoryの既存Kling scene 02–10/12/13を使い、Life Manager所有のversioned asset rootへ一度コピーしてSHA-256で検証する。distribution実行時に旧factory checkoutやOpenClaw sourceへアクセスしない。コピーした映像へMarketing Engineの日本語baseline scriptを既存のローカル音声・caption rendererで合わせる。FFmpegにlibass subtitles filterがないhostでは、Pillowで日本語caption overlayを作り、FFmpegの`overlay` filterで焼き付ける。両rendererは同じMarketing Engineのscript・product/slot receipt・campaign token契約を使う。
- 各localeはpackのAsia/Tokyo slotsで毎日3本を生成する。1 product/slotにつきrenderは1回とし、同じ動画をそのslotに属する全active Postiz targetへ配る。owner occurrenceごとの投稿effectは最大1件。
- Japanese Instagram/TikTokはactive targetとして登録済み。English packは既存TikTok integrationを参照するが、現在は`provider_disabled` hold中でactive targetではない。English Instagramはdedicated account未登録のため追加・流用しない。投稿前にPostiz integrationのidentity/enabled readbackを行い、disabledまたは不一致ならeffectを発生させない。
- HeyGenはrender前後のwallet readbackを各render receiptへ記録する。walletを読めないrunはcreate前に止める。create後にcost/deltaが確定できないrunはreceiptをreconciliation holdに置き、次のrenderを始めない。既存のHeyGen auto-reload設定を変更しない。

## 現状（2026-10-06 14:05 JST refresh）

### eBook商品・売上経路

- anicca-products PR #419 はmain commit 6c52d4cc13へ統合済み。EN /monk $10.99、JA /achan ¥1,580のone-time checkout、/go token、checkout metadataの接続がある。/letter $9.99/月と/tegami ¥980/月は別のsubscription商品で14日trial後に請求する。
- PR #420はOPEN、head `85116e29aceb3d951e65f125fb3473fcb17d2b99`。signed webhook receipt、PDF retry fence、subscription generation/readback、legacy mapping、trial/paid-MRR分離、normalized-email shared RPC、verified sender、canonical base64url token checkを含む。Focused eBook/Writer/lead-magnet tests 31/31とwriter-entitlement 6/6、PostgreSQL 18.6 fixture、syntax/diff checksはPASS。Landing check `37356856068`はこのheadでSUCCESS。
- PR #420では同一normalized emailのlead-magnet signupとStripe reservationを共通RPCへ直列化し、existing Stripe mappingを優先する。既存行の`signed_up_at`を更新しないため、signup retryでduplicate-emailの選択対象を入れ替えない。PostgreSQL fixtureで、email UNIQUEなしの並行writerでもsubscriber rowが1件、duplicate legacy rowsでも既存subscription mappingを維持することを確認済み。
- Production provider metadata workflow `37353322073`はPASS。`buyers`/`subscribers`のOpenAPI columns/typesはmigrationと整合。email data scanは9 subscriber rows、9 normalized emails、duplicate groups 0、empty rows 0。`pg_indexes`とebook tables/RPCsはPostgRESTで非公開（PGRST205）。PR #420のsourceはemail unique indexの有無に依存せずshared RPCを使うため、email index追加はしない。Supabase CLIはproject ref未link、GitHub/Netlify環境にDB URLやSupabase management tokenはなく、SQL migrationは未適用。main pushは自動deployするため、DDL migrationとpost-migration table/RPC/schema-cache readbackまでPRをmergeしない。
- `RESEND_FROM_EMAIL`はproductionで設定済み、sender domainは`aniccaai.com`。このrunのResend API keyは`GET /domains`に401 `restricted_api_key`を返したため、domain statusはAPIで再確認できていない。過去のdashboard readbackではVerified。購入者へのemailはまだ送っていない。
- PR #420のsourceではlead-magnet.jsがshared normalized-email RPCを呼び、DB write成功後にだけ`RESEND_FROM_EMAIL`からDay-0 emailを送る。missing config/write/send failureをsuccessにせず、provider response bodyをcallerへ返さない。このsourceはまだproductionへdeployされていない。
- 同一occurrenceに結び付いた自然なpaid sessionと正しいPDF delivery receiptはまだ確認できていない。売上とsettlementはunknownであり、ゼロとは扱わない。

### eBook marketing

- PR #6729は全required checks PASSでmainへmerge済み。2026-10-06 15:19 JSTのreadbackではmain commit `0ba957af5405bfbea5f1d6e9ce6ca78deb66b421`のimmutable release `20261006T150708-0ba957af`が`current`を指し、`release_paths=ALL`、`provenance=ancestor-of-origin-main`、read-onlyであった。releaseにはEN HeyGen TikTok、JA Watercolor TikTok、JA Watercolor Instagramの3 ownerと各localeの3 daily slotがあるが、3 ownerとも`launchd_state=unloaded`・`installed_release_sha=null`でまだ稼働していなかった。provider receipt/public URLはなく、eBook public postは未実施。
- 日本語`watercolor-monk` sourceはFactoryのscene 02–10/12/13をLife Manager外部asset rootへ一度コピーし、11個のSHA-256を検証する。local preview `ebook-run.8fb24a21e077a2a9c210ac0f`は720×1280、H.264/AAC、11.933秒で完成し、実際の水彩sceneと字幕を確認した。これはlocal previewであり投稿ではない。
- HeyGen sourceはAvatar IV createごとにwalletを前後readbackし、USD差額とauto-reload状態をeffect receiptへ保存する。wallet readbackなし・threshold以下・未解決の先行effectでは新規createを止める。CLI v0.5.0の過去readbackはwallet USD 12.30、auto-reload USD 10、threshold USD 5、enabled。live EN renderはまだなく、実動画単価は未測定。
- Watercolorのlocal previewはrun `ebook-run.8fb24a21e077a2a9c210ac0f`（20:00 JST pack slot）で完成した。asset pack `watercolor-mark-factory-v1`、manifest SHA `b68216830c5be7b4969caaec095f8376d03af06cc4b90494c71f10aea0b1d06e`、H.264/AAC 720×1280、11.933秒、caption renderer `pillow-overlay`、output SHA `56b25dc8d052326fabcbb4b1f588917146374a0dbb9619ce20e66695daa795ab`。Receiptは`external_effects=[]`、Postiz callは0。実フレーム確認で既存の水彩Kling sceneと日本語captionを確認した。これはdirty worktreeからのlocal previewで、公開投稿やproduction releaseではない。
- 標準`/opt/homebrew/bin/ffmpeg`は`subtitles` filterがなく`overlay`はある。`ffmpeg-full 9.0.1`は`libx265.216`を要求するがhostには`.217`のみあり起動しないため、production pathでは標準FFmpeg+Pillow overlayを使う。libassのないhostでもPillow/日本語font/overlayが揃わない場合は`setup_required`でfail-closedする。
- Postiz integration snapshot (2026-10-06 14:02 JST; superseded by the current refresh below) returned 31 integrations: 30 enabled / 1 disabled. English `Monk Anicca` TikTok `cmo5rwq2p00twn10yrsdglng3` was disabled; Japanese `obou` Instagram `cmooplxmu04tpmd0y4h3cpk33` and TikTok `cmo5s4edx00vgn10ygnu34a0n` were enabled; English Instagram was unregistered. A refresh attempt at 14:49 JST returned HTTP 401 because this shell has no Postiz API key. BrowserGuard later verified daily-driver `interactive:dais` at `localhost:9222` as reachable, but its active browser lease is held by another process; do not attach or steal it. The authenticated 16:18 JST API readback below supersedes this snapshot. Keep English held until its exact integration reads `disabled=false` and a no-cost slot is verified.
- Fresh Checkout/PDF readback (2026-10-06 15:47 JST): manual workflow `37425532984` on Product PR #420 head `85116e29aceb3d951e65f125fb3473fcb17d2b99` passed. `buyers`/`subscribers` are exposed; `ebook_webhook_receipts`/`ebook_subscription_states` and eBook RPCs are absent; receipt-table and `pg_indexes` probes return `404/PGRST205`; subscriber scan reports 9 rows, duplicate normalized groups 0, empty rows 0. Production Netlify variable names include `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`, but no DDL-capable database URL or management token; CLI reports no linked project ref and credential SSOT has no Supabase access token. PR #420 remains OPEN. The live `/monk` and `/achan` pages show purchase CTAs/PDF promises, not a delivery receipt. The latest main deploy `37398436701` failed while fetching Google Fonts in `app/comedy/ja/page.tsx`. Do not publish either locale until production fulfillment is verified.
- Historical 15:51 JST production doctor readback (superseded by the current release readback below): doctor returned `ok=false`, `registry_entries=184`, and unmanaged label `ai.anicca.provision-browser.upwork.dais`. BrowserGuard maps it to registered identity `upwork:dais` / owner `upwork-revenue-browser`, reachable on its owned profile; the label is generated by `skills/browser/ensure_provision_browser.sh`. The label and process are active. The source branch classifies this one on-demand provisioner as an explicit external label; it leaves the browser and account untouched. At this historical snapshot the doctor was false; PR #6739 and release `78c55432` below now make it green.
- HeyGen CLI `v0.5.0` is available. Latest `user me get` readback is USD 12.30 with auto-reload USD 10 at USD 5 threshold, enabled. No HeyGen video or eBook social post has been created; actual per-video cost remains unmeasured.
- Historical 15:51 JST capacity readback (superseded below): the scheduled cleanup owner remained disabled; two bounded one-shot runs of the canonical cleanup implementation reclaimed `2,390,737,049` bytes and `106,945,538` bytes with `errors=0`, `protected_deletions=0`; each preserved 5 open candidates. The full/fast inventory recorded 14/21 gaps. The latest `/System/Volumes/Data` readback was 3.2 GiB available, below the 11 GiB preventive cleanup threshold; `disk-pressure.block` was clear. The scheduled cleanup LaunchAgent was not restarted. The earlier interpretation of this threshold as a rendering gate is superseded by the 16:30 source inspection below.
- Cross-repo source contractはgolden vector `creative.contract.1`で固定した: EN `ee_hcp4v5pifa2ovj47rsir`、JA `ej_cs6k5hu42kvx65x66imw`。Life Managerの`stage_intents`からProduct `/go`, `utm_campaign`, Checkout metadata、webhook durable receipt、locale PDF payloadまで同じJP tokenを使うlocal integration probeがPASS（provider callsはfake、production effect 0）。PR #6704のLife Manager testはmainへmerge済み。Productの対応testsはPR #420 head `85116e29`にあり、PRはOPEN。
- 既存account registryでは`instagram.obou_anicca`のPostiz routeが`route_ready=true`と読み戻されている（02:15 JST）。これはroute設定の証拠であり、現アカウントの本人所有・good-standing・Instagram側の投稿receiptの証拠ではない。EN packはTikTokのみ、JA packはTikTokとInstagram integrationを登録している。pack登録だけではprovider login/statusを証明しない。
- 2026-10-06 JSTの旧factory readback: `~/.openclaw/cron/jobs.json`にあるmonk/watercolor/eBook関連cron 10件はすべてdisabled。OpenClaw GatewayのLaunchAgentは未導入で、`127.0.0.1:18789`はconnection refused。旧factory source/stateはprotected・dirtyなので変更しない。旧価格（$17/¥1,980）と`/jp` routeは現行販売契約として流用しない。
- 現行eBook social routeの状態: JA TikTok `tiktok.obou_anicca` とInstagram `instagram.obou_anicca` はregistry上approved_activeだが、公式account/good-standing readbackは未取得。Shared mobile destination contractは両integrationをmobile scope外としてholdしているため、eBook専用targetを明示的に登録してから使う。EN TikTok `tiktok.monk_anicca` は`disabled_verified`、EN Instagramはsetup-required。新規accountは作らない。
- `effect_unknown` recovery contract: identity sidecarからofficial Postiz lookupへ到達でき、local published rowが無くても回復できる。integration・exact caption hash・slot window・published public URLが全て一致する候補が一件だけの場合に限り、provider receiptを`distribution.jsonl`へdurableに記録してからeffect fenceを解決する。候補なし・複数候補・不一致ではfenceを保持する。同一slotのreplayは保存済みreceiptを再利用し、provider publish callを追加しない。

### 運用cursor

- 実行順・現在状態・容量/readback evidenceの正本は `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`。

#### 2026-10-06 16:23 JST — live distribution refresh

- Dais reconfirmed the intended pipeline and cadence: English uses HeyGen Avatar IV and its existing TikTok route; Japanese uses Watercolor Monk Factory and its existing TikTok+Instagram routes. The three daily slots per locale remain unchanged: EN 08:00/14:00/21:00 JST, JA 07:00/12:30/20:00 JST.
- PR #6739 is merged at `78c55432421dbe821773a96f7a7deb9646ee7599`. The selected main-derived immutable release is `/Users/anicca/loops/releases/20261006T160404-78c55432`; `lm-loop doctor` returns `ok=true`, 184 registry entries, and no missing, retired, or unmanaged labels. The active `upwork:dais` browser remains reachable under its dedicated owner.
- The three eBook launchd jobs are enabled and `loaded-idle` at installed SHA `0ba957af5405bfbea5f1d6e9ce6ca78deb66b421`. All have null occurrence IDs and no provider receipts or public URLs. Their calendar schedules are loaded, but `LM_EBOOK_PUBLISHING_ENABLED` and `LM_POSTIZ_API_KEY` are unset in the launchd environment. The source checks the publish flag before rendering; the next due occurrence should stop before render or Postiz. This is an inference from source and environment, not a natural-run result.
- Authenticated Postiz `GET /public/v1/integrations` readback at 16:18 JST returned 31 integrations: 30 enabled, 1 disabled. The EN `Monk Anicca` TikTok integration exists but is disabled; JA `obou` Instagram and the Japanese TikTok integration are enabled. English Instagram is unregistered. Postiz integration state does not prove native account identity/good-standing or an available channel slot.
- The protected credential SSOT has a Postiz API key, but the selected production release child-process path does not inject it into the three eBook jobs. The key remains in `~/.local/share/anicca/credentials.json`; the only use in this refresh was in-memory for the official API GET. The local branch now implements this mapping in the central loop runtime and withholds the key while publishing is disabled. Focused tests pass 121/121 and the loop contract passes. A no-effect SSOT smoke reports the key present only for an enabled eBook child and absent for a flag-off run or sibling owner; the source change is not merged or loaded, so the selected production release still lacks the mapping.
- Product PR #420 remains OPEN. Production metadata workflow `37425532984` confirms the webhook/subscription tables and eBook RPCs are absent (`404/PGRST205`); `supabase projects list` finds no linked project reference, and the credential SSOT has no Supabase management credential. No authorized DDL path, deployed Checkout/PDF proof, natural paid order, or matching PDF receipt is currently confirmed.
- A bounded owner cleanup at 16:01 JST reclaimed 712,142,339 bytes with zero errors/protected deletions; it preserved five open candidates and recorded 14 inventory gaps. Free space at 16:18 JST was 3.2 GiB, below the 11 GiB preventive cleanup threshold, not an eBook renderer floor. The scheduled cleanup owner remains disabled. HeyGen wallet readback remains USD 12.30 with USD 10 auto-reload at USD 5 threshold enabled; no live video has been generated and no eBook video has been posted.

#### 2026-10-06 16:30 JST — latest owner and provider state

- Three creative slots per locale remain the target: EN 08:00/14:00/21:00 JST, JA 07:00/12:30/20:00 JST. EN produces three TikTok posts/day after its existing route is enabled. JA shares each of its three Watercolor renders with TikTok and Instagram, for six platform posts/day.
- Authenticated Postiz integration readback returns 31 rows (30 enabled, one disabled): JA `obou` Instagram and TikTok are enabled; EN `Monk Anicca` TikTok exists but is disabled; EN Instagram is absent. This does not verify native account good-standing or available Postiz capacity.
- PR #6744 is open at source head `4a85b0866e`; the fresh read-only reviewer found no Critical/Important issues and every required CI check passes. The spec update will create a new head and rerun CI before merge. The key-wiring change is not merged or loaded; current launchd owners still have publishing disabled, no provider receipt, and no public URL.
- Product PR #420 remains open at `85116e29aceb3d951e65f125fb3473fcb17d2b99`. Production webhook/subscription tables and eBook RPCs remain absent; no production Checkout/PDF fulfillment receipt exists.
- The 16:30 JST canonical cleanup pass reclaimed 56,844,145 bytes with zero errors and protected deletions, preserved six open candidates, and recorded 21 inventory gaps. Free space is 1.7 GiB; both disk policy markers are absent. The 11 GiB level is a preventive cleanup tier, not a publishing gate.

#### 2026-10-06 16:39 JST — live Checkout diagnosis

- Public `/monk` and `/achan` pages show the existing one-time eBook offers and CTAs. Both direct locale PDF URLs return `200 application/pdf` by HEAD readback.
- Live GET `/.netlify/functions/checkout` returns a Netlify runtime stack trace: `ReferenceError: module is not defined in ES module scope` from `checkout.js`. The app package sets `type=module`; the checkout file uses CommonJS `require`/`exports` and an ESM dynamic import. A GET to `/.netlify/functions/webhook` returns `no sig`, proving that the webhook handler loads and rejects requests without Stripe signature.
- Latest successful main deploy is `90e03fcc0f5cf2a11c66c3af92d27303c78f5cc0` (run `37362288819`). Main has no later `apps/landing` source changes; newer deploy run `37398436701` failed in Build before deployment. Product PR #420 does not modify `checkout.js`, so its DDL migration cannot fix this runtime error.
- Current one-time eBook source flow creates locale-priced Stripe Checkout Sessions with `ee_`/`ej_` attribution metadata and emails the public locale PDF link through the existing webhook. PR #420 adds durable webhook/subscription receipts and subscriber-state RPCs. The new schema is separate hardening; live checkout module loading is the immediate campaign blocker.

#### 2026-10-06 16:52 JST — checkout fix in flight

- Product PR #422 is based on latest Product main `7ca532244`; head `21293ac4` moves the shared locale-token validator into CJS and keeps the checkout entrypoint out of mixed CJS/ESM mode. Focused checkout tests pass 17/17; the `Landing PR build` CI is pending.
- The current production Checkout endpoint still returns 502; the post-deploy money-path smoke now expects a GET to reach the handler and return its no-effect 405 method response. No Postiz publication is enabled yet.
- Life Manager PR #6744 head `b5265bf743` is independently waiting on loop-contract and security scans. Its child-only Postiz key injection remains behind `LM_EBOOK_PUBLISHING_ENABLED`.

### Capafy Instagram marketing

- 03:42 JST `lm-loop status all --json`: old `capafy-ig-marketing-daily` is managed/loaded-idle at SHA `d091b3bd58aa5f27dbee19c2eab12311b3b0597e`; occurrence `capafy-ig-marketing-daily:18dbb45758667058-79255` is exit 75 / `host_admission_deferred:resource_effect_unknown`, with no provider receipt/readback. Active fence `18db7caff1178a88-68028` remains `no_pre_effect_terminal`; health is `safely_fenced`.
- New `life-manager-capafy-ig` is now returned as managed/loaded-idle at old SHA `4eb6bbbaeb9a8368895e6391e34e8c895908b0ec`; latest occurrence `life-manager-capafy-ig:18dbb4981f9573c8-86990` is exit 1 / `entrypoint_exit_1` / effect unknown / no receipt / `official_readback_required`. `pre-effect-reconcile --dry-run` returns `no_pre_effect_terminal`. The 02:20 `unmanaged_label` snapshot is superseded; neither owner has official readback, so do not repost from either lane.
- **04:06 JST refresh supersedes the 03:42 occurrence IDs above:** old `capafy-ig-marketing-daily` remains loaded-idle; current snapshot SHA is `a09d0ad40b4eddfcaa65ca03b9804604ba692557`, while latest scheduled occurrence `capafy-ig-marketing-daily:18dbb79dd35998c8-25553` used event SHA `d091b3bd58aa5f27dbee19c2eab12311b3b0597e` and exited 75 with `host_admission_deferred:resource_effect_unknown`. Its active fence `18db7caff1178a88-68028` is still unresolved; the adapter reports `active_ig_handle_unresolvable`, not a verified post. New `life-manager-capafy-ig` remains loaded-idle at SHA `4eb6bbbaeb9a8368895e6391e34e8c895908b0ec`; latest occurrence `life-manager-capafy-ig:18dbb7007d247380-97286` failed with `capafy ig reel loop requires node`, provider adapter state `adapter_not_run_yet`, no provider receipt/readback, and an active `effect_unknown` fence.
- The Node/Python launchd lookup repair is already in Life Manager main at commit `9e3fb448b6` (PR #6663), but the installed new-owner release is still `4eb6bbba`; a current immutable release has not been applied to that owner. The source comment also says `@capafy.hooklab` is not connected to Postiz and the integration ID is unset; verify the actual account and Postiz integration through official readback before planning a canary. These runtime errors do not establish that a CAPTCHA exists. No authenticated challenge screen was inspected during this readback.
- 現行sourceのowner pathは`config/loop-registry.json`の`life-manager-capafy-ig` → `apps/life-manager/scripts/capafy-ig-reel` → Postizで、effect reconcilerもPostiz post listingを公式receiptとして読む。entrypointは`LM_POSTIZ_API_KEY`と`CAPAFY_IG_POSTIZ_INTEGRATION_ID`を要求し、source commentは`@capafy.hooklab`がPostiz未接続としている。旧`capafy-ig-marketing-daily`は`instagrapi`経路。`capafy-marketing/SKILL.md`のB4 browser-direct推奨はそのskill directory内で未実装の設計メモであり、この現行Life Manager ownerのrouteではない。新laneのaccount/credential/post statusはprovider readbackで未確認なので、Postizとbrowser-direct/instagrapiを併用せず、D5で一つに収束させる。
- D5の既存正本は docs/superpowers/plans/2026-10-04-capafy-10k-mrr-recipe.md。「eBook first receipt後に開始」「両laneのeffectをreadback」「ownerを一つにする」「1日1回以下のcanary」「14日測定」を既に定義している。このspecではD5のTODOを複製しない。
- 2026-10-06 02:20 JSTのGitHub repository searchでは、最新のlocal/free-code候補は[fiptcha](https://github.com/figranium/fiptcha)（Apache-2.0、2026-10-05 16:42Z更新）。既存のactive Playwright-compatible `page`を受け取りbrowserを起動しない。reCAPTCHA v2 / hCaptcha / Turnstileに対応するが、dynamic 3x3 gridは不安定でdirect-CDP compatibilityは未検証。既存owner helper `skills/fundraiser-agent/runtime/solve-recaptcha-v2.py`は標準reCAPTCHA v2専用で、registered pageのtarget-id、widget site key/response textarea/callbackを必要とする。[Captcha Solver API Python SDK](https://github.com/captcha-solver-api/python-sdk)はrepository licenseがMITのSDKだが、外部API serviceの無料枠/価格はこの調査では確認していないため「無料solver」とは判定しない。Capafy runtime errorはCAPTCHAの証拠ではなく、このturnでは認証済みbrowser画面を未確認。実challengeが現れた場合だけchallenge typeを確認し、既存helperまたはregistered CDP sessionで互換確認できた手段を使う。identity/appeal/suspensionはsolverで回避しない。
- Capafyの既存landing redirectはInstagram bio clickを記録し、seller analyticsは注文・収益を集計する。1投稿ごとの注文IDが得られない期間の投稿→売上対応はcandidate attributionとして表示し、因果と断定しない。

## 現状のarchitecture

~~~mermaid
flowchart LR
  CONTENT["ebook source + verified claims"] --> ENGINE["Marketing Engine render receipt"]
  ENGINE --> PREVIEW["JA local Watercolor preview; 11 pinned scenes; external effects 0"]
  ENGINE --> SOURCE["three account-scoped publisher owners from main release 0ba957af"]
  SOURCE --> RELEASE["selected main-derived release 78c55432; doctor ok=true"]
  RELEASE --> OWNER["three scheduled owners loaded-idle at old SHA 0ba957af; no occurrence/receipt/URL"]
  OWNER -. "LM_EBOOK_PUBLISHING_ENABLED unset" .-> NORUNTIME["pre-render and pre-Postiz hold"]
  KEY["postiz.api_key in protected credential SSOT"] --> WIRING["PR #6744 injects only into the three eBook children when flag=true"]
  WIRING -. "open; CI pending; not in main" .-> ENV["selected release still lacks child key"]
  DISK["cleanup pass complete; 1.7 GiB free; no pressure marker; not a publish gate"]
  SOURCE --> EN["EN HeyGen Avatar IV → existing TikTok integration"]
  SOURCE --> JA["JA Watercolor → existing TikTok + Instagram integrations"]
  EN -. "Postiz TikTok disabled=true; Instagram absent" .-> ENHOLD["EN effect-free hold"]
  JA -. "Postiz TikTok+Instagram enabled; native status and Checkout/PDF proof absent" .-> JAHOLD["JA effect-free hold"]
  TOKEN["ee_/ej_ campaign token"] --> GO["/go click receipt"]
  GO --> CHECKOUT["main checkout.js with locale price + campaign metadata"]
  CHECKOUT -. "live module error: module is not defined in ES module scope" .-> CHECKOUTHOLD["checkout runtime fix required"]
  CHECKOUTFIX["Product PR #422: CJS-safe shared attribution + GET/405 smoke"] -. "CI pending; not deployed" .-> CHECKOUTHOLD
  WH["current signed webhook: existing one-time PDF email path"] -. "PR #420 durable receipt tables/RPCs absent" .-> NOORDER["no verified natural paid + PDF receipt"]
  PDF["EN and JA direct PDF URLs: HEAD 200"]
  OLD["Capafy old owner: active effect_unknown fence"] --> HOLD["no retry; provider readback missing"]
  NEW["Capafy new owner: managed, active effect_unknown, old installed SHA"] --> HOLD
~~~

## To-Be architecture

~~~mermaid
flowchart LR
  subgraph E["1. eBookを先に完走"]
    ENBASE["EN baseline + approved claims"] --> ENLOCK["EN product/slot lock"]
    ENLOCK --> WALLET1["HeyGen wallet pre-read"]
    WALLET1 --> HEYGEN["HeyGen CLI Avatar IV"]
    JABASE["JA baseline + approved claims"] --> JALOCK["JA product/slot lock"]
    JALOCK --> ASSET["11 existing Factory Kling scenes; copied once to LM asset root + SHA-256 verified"]
    ASSET --> WATERCOLOR["local Japanese voice + Watercolor render; Pillow overlay fallback when libass is absent"]
    HEYGEN --> WALLET2["HeyGen wallet post-read + exact delta"]
    WALLET2 --> ENRENDER["EN render receipt; hold if cost unknown"]
    WATERCOLOR --> JARENDER["JA render receipt"]
    ENRENDER --> ENPOST["ebook-en-tiktok-daily: 08:00 / 14:00 / 21:00 JST"]
    JARENDER --> JAPOST["ebook-ja TikTok + Instagram: 07:00 / 12:30 / 20:00 JST"]
    ENPOST -. "Postiz integration disabled; no channel slot confirmed" .-> ENHOLD["EN effect-free hold"]
    ENPOST --> ENRECEIPT["Postiz receipt + public URL"]
    JAPOST --> JARECEIPT["Postiz receipts + public URLs"]
    ENRECEIPT --> GO["/go/<ee_/ej_ token> click receipt"]
    JARECEIPT --> GO
    GO --> PAGE["/monk または /achan"]
    PAGE --> CHECKOUT["Stripe one-time Checkout + attribution metadata"]
    CHECKOUT --> HOOK["署名検証 + durable webhook receipt"]
    HOOK --> BUYER["buyer/session receipt"]
    BUYER --> PDF["正しいlocaleのPDFをverified senderから納品"]
    MIG["PR #420 migration + RPC/ACL/schema-cache readback"] --> DEPLOY["merge + auto-deploy + deployed SHA/health readback"]
    DEPLOY --> CHECKOUT
    PDF --> OPTIONAL["任意のLetter/Tegami CTA"]
    OPTIONAL --> SUBCHECKOUT["本人が選択したsubscription Checkout"]
    SUBCHECKOUT --> TRIAL["14日trial / access state"]
    TRIAL --> PAID["invoice.paid + Stripe active readback"]
    PAID --> MRR["paid MRR receipt"]
  end
  subgraph C["2. 初回eBook paid + PDF receiptの後だけCapafy IG"]
    DEV["別担当が承認した公開listing"] --> DEMO["実物のlistingに沿う独自Reel"]
    DEMO --> CAPOWNER["life-manager-capafy-igの単一owner"]
    ACCOUNT["本人所有・公式statusとPostiz integration確認済みCapafy IG"] --> CAPOWNER
    FENCES["旧・新ownerのeffect_unknownを公式readbackで解消"] --> CAPOWNER
    RELEASE["Node/Python修正を含むmain由来immutable release"] --> CAPOWNER
    CAPOWNER --> CAPPOST["Postiz/Instagram receipt + public Reel URL"]
    CAPPOST --> CTA["Capafy listingへct campaign link"]
    CTA --> ORDERS["Capafy order/fee/refund/payout readback"]
  end
  MRR --> CFO["既存CFO: period・currency・cost・settlementを照合"]
  ORDERS --> CFO
  GATE["account identity + enabled Postiz route + effect_unknown解消 + live checkout/PDF"] --> ENPOST
  GATE --> JAPOST
  GATE --> ACCOUNT
  PAID -->|first paid + matching PDF receipt| DEMO
~~~

同じsubscriberに複数のStripe subscriptionを持てるようにし、古いeventの到着順でaccess stateを戻さない。

~~~mermaid
sequenceDiagram
  autonumber
  participant Stripe
  participant Hook as Netlify webhook
  participant DB as Supabase
  Stripe->>Hook: signed Checkout/subscription event
  Hook->>DB: reserve subscription readback generation
  DB-->>Hook: subscriber id + generation
  Hook->>Stripe: GET current subscription
  Stripe-->>Hook: status + immutable Subscription.created
  Hook->>DB: apply only when generation is still current
  alt generation is current
    DB->>DB: aggregate access across mapped subscriptions
    DB->>DB: choose newest created subscription pointer
    DB-->>Hook: applied; record payment/delivery state
  else newer readback has started
    DB-->>Hook: stale
    Hook->>DB: keep Checkout receipt retryable
  end
~~~

## 受入契約

1. /go/<token>のclick receipt、checkout metadata、buyer/subscriber receiptが同じproduct・locale・campaign tokenを持つ。click・view・renderはsaleではない。
2. one-time paymentの署名済みCheckoutだけでbuyer/PDF fulfillmentを行い、同じStripe sessionのretryで購入receiptやemailを重複作成しない。
3. ResendにはverifiedのRESEND_FROM_EMAILだけを渡す。設定不足やDB失敗は成功にせず、durable retry/fenceを残す。
4. Letter/TegamiのsubscriptionはDB generationをStripe GET前に予約し、最新generationだけを適用する。trial/accessはpaid MRRと区別する。MRRは初回invoice.paidとactive paid stateを確認して数える。
5. subscribersのemail一意性をproduction schemaで確認する。unique constraintが無ければ、lead-magnetとStripe webhookの全subscriber writerを同じDB-owned normalized-email upsert/lockへ寄せてからtrafficを拡大する。
6. lead-magnetのDay-0 senderもverified production senderを使い、subscriber writeの失敗を見てから送信する。無料signupをpaid subscriber/MRRとして数えない。
7. eBook distributionは既存のMarketing Video Publication Adapterを使い、one render receiptをproduct/slotで共有する。JAはWatercolor Monk Factoryの11 scene assetsをLife Manager asset rootでSHA-256検証して使う。ENはrender前後wallet readbackをreceiptに結び、cost unknown時は次のrenderを止める。account別publisher ownerは1 occurrenceにつき1 provider effectとし、effect_unknownはreadbackなしに再送しない。system-generated baseline copyのみstanding policy内で配信し、Daisが直接編集したcopyは確認なしに使わない。
8. 既存の本人所有accountと公開statusを照合する。challenge_requiredの場合はchallenge typeを実画面で確認し、既存の認証済みchallenge pathだけを使って、解決後に期待accountとprovider stateまでreadbackする。identity/appeal/suspensionはCAPTCHA solverで回避しない。
9. Capafy marketingは公開中listingと実際の入出力に基づくoriginal Reelを使う。product/listing/account lifecycle codeは別担当の所有に残す。
10. Capafyのct click、売上、refund、fee、実費、payout、bank receiptを分ける。providerがpost単位注文を返さない場合はcampaign-level correlationと明記し、銀行着金なしにnet contributionを確定しない。

## 数値の意味

- $9.99/monthで$10,000 gross MRRに必要な有料active subscriptionは1,002件。fees・refunds・cost前の算数であり、実測や予測ではない。
- $10.99のebook saleは一回売上で、subscription MRRではない。
- Capafyの$10,000は既存CFO定義の同一30日窓banked net contributionと、portfolio計画のchannel allocationを整合させてから測る。seller balanceやviewsを銀行着金とみなさない。

## 正本

- checkout/webhook/PDF implementation: anicca-products PR #419/#420
- eBook/Capafy marketing execution order and cursor: docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md
- eBook implementation tasks: docs/superpowers/plans/2026-10-05-ebook-revenue-loop.md
- Capafy Instagram D5 marketing tasks: docs/superpowers/plans/2026-10-04-capafy-10k-mrr-recipe.md
- Capafy product development cursor: the separate owner's canonical project plan
