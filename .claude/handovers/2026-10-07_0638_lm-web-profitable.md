# Life Manager Web-first 作業引き継ぎ

## 正本と現在cursor

- 主repo: /Users/anicca/Projects/life-manager-main、originはhttps://github.com/Daisuke134/life-manager.git。
- 前回のhandover作成branch/worktree: codex/lm-web-handover-20261007、/Users/anicca/Projects/life-manager-main/.worktrees/lm-web-handover-20261007。
- 前回handoverのcommit 1f814f451f15be8bae6850bd30f86af72ff35299はPR #6792でmainへmerge済み。merge commitは9ca3803060938343a8d8a64063f738a52bec573c。branchと作業worktreeはcleanup済み。
- 唯一のTODO正本: /Users/anicca/Projects/life-manager-main/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md の「Dais指定のWeb-first Life Manager Travel Product — 現在の最優先cursor」内「Web-first進行状態と原子TODO」。
- 現在cursor: WB-01 / W3-P0。最初の次手は資格情報の値を出さずにcredential/provider状態を再確認し、同一Supabase projectのowner経路を確保すること。曖昧なGitHub recovery POSTは再送しない。
- Webの振る舞い・画面の参照spec（TODO正本ではない）: /Users/anicca/Projects/life-manager-main/docs/superpowers/specs/2026-10-06-life-manager-web-first-travel-design.md。

## 確認済み状態と阻害原因

- 2026-10-06のproduction GETでは/lmがHTTP 200、/auth/googleがHTTP 503。直接原因はRailway productionのlife-callにSUPABASE_ANON_KEYが無いこと。sourceはこのkeyを必須とし、service-role keyによる代替を拒否する。
- 既知のauthorized配布先から同一projectのpublic keyとDB/Management accessは見つからなかった。Web control columnsはremote schemaに無く、既存Web migrations 5件が未適用。正本に正確なファイル名と適用順・readbackがある。
- GitHub loginのSSOT passwordは拒否された。replacement reset linkは2026-10-06 13:05:53Zに受信し、最後のreadbackではcredential SSOT内に未使用で保存されていた。今の有効性とprovider statusを先にreadbackし、URLを表示・複製しない。以前の/sessions/recovery/without_password POSTはHTTP 200の空bodyでeffect/statusが不明なままなので、公式providerのstatus/no-effect証拠前に再送しない。最初のreset URLがprovider側で無効化された証拠もない。GitHubを待たずSupabase owner accessが得られればWeb作業を進める。
- Stripeのlive read-only pre-readではLife Managerのactive Payment Linkは$29/month、同商品のactive $20/month priceもあり、各priceのsubscription readbackは0件。Stripe trial_period_daysはnullだがappは3日entitlementを開始するため、広告やterms変更前に整合を取る。
- 30日service-wide cost estimateはUSD 69.278553。実請求額でもWeb別配賦額でもない。Webのrefund/fee/settlement、Composio/hosting、attributed marketing spendは未照合。
- 2026-10-06最後の公開readbackではaniccaai.com/lmはTelegram CTA、$29/month、phone-call copyを表示。競合調査、未計測の50キーワード、SEO outline 2本、X/Reel案はWeb design specにあり、未公開。今回の作業でCTA、price、marketing公開は変更していない。
- 今sessionのagent censusでは稼働workerなし。旧handover goalはruntime上blockedのまま。この文書と貼り付け用goalはまだ新sessionで有効化していない。
- 旧共有Life Manager checkout /Users/anicca/Projects/life-manager-mainはCapafy branch、origin/mainより470 commit遅れ、無関係のuntracked pathあり。触らず、switch/cleanupもしない。

## marketing repoの経路

- 公開landingの正本は別repo /Users/anicca/Projects/anicca-products、originはhttps://github.com/Daisuke134/anicca-products.git。
- 前回read-only確認では共有main checkoutはclean、local HEAD 1a8f5a30d27135f0c4d28f61adde0be9b3b469d8、origin/mainより3 commit遅れ。そこは編集しない。
- WB-14に着手できる条件が揃ったら、fresh fetch後に専用worktree /Users/anicca/Projects/anicca-products/.worktrees/lm-web-marketing-next とbranch codex/lm-web-marketing-next-20261007を作り、origin/codex/lm-web-marketing-next-20261007へpushする。production sourceとしてLife Manager repo内のdiverged apps/landingを使わない。

## 新sessionで送信する完全な/goal

    /goal goal-setterとhandoverのskillを使い、まずhandover /Users/anicca/Projects/life-manager-main/.claude/handovers/2026-10-07_0638_lm-web-profitable.mdとSSOT /Users/anicca/Projects/life-manager-main/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.mdを読み、fresh git/provider stateと照合したうえで、統一SSOTに残るTODOを最初から最後まで完了する。開発はsuperpowers:using-superpowersを最初に読み、該当するskillの手順に従う。最優先のWeb-first cursorから、Life Manager CloudをTelegramなしで使えるproduction Web商品にする。新規Google signup、同じuidのCalendar ACTIVE readback、home設定、正しいtravel/departure block、厳密なCalendar readback、replay-zeroまでを実証する。次にStripe checkoutとtrialを整合し、Web別settled revenueと同期間のrefund・fees・route/provider・hosting・marketing costを実データで照合してofferを決め、source attribution付きWeb CTAと準備済みX/Instagram/SEOを配信し、有料Web顧客10人以上でcontributionが3か月連続positiveになるまで獲得と改善を続ける。このgate後にだけ既存mobile app factoryとreviewed Self-Build boundaryを再利用したWeb App Factoryを最小実装し、計測可能な1 iterationで動作を実証してから、統一SSOT次cursor（現在§84-A P5c）へ戻る。Doneは既存SSOT acceptance criteriaごとのauthoritative evidenceで判断し、同じ正本を証拠に合わせて更新してopen TODOを最後まで続ける。既存Telegram利用者、auth guard、provider effect fence、正確な売上/原価帰属を維持し、secretを表示せず、曖昧なGitHub recovery actionをofficial status/no-effect readback前に再送しない。Supabase owner-only accessだけがblockerなら独立調査・準備を続け、不足するprovider actionを正確に記録し、credentialを捏造したりservice-role keyで代用したりしない。作業routing: Life Manager repoは/Users/anicca/Projects/life-manager-main、書込worktreeは/Users/anicca/Projects/life-manager-main/.worktrees/lm-web-profit-next、branch codex/lm-web-profit-next-20261007、push先origin/codex/lm-web-profit-next-20261007。handover merge後に確認したorigin/mainは9ca3803060938343a8d8a64063f738a52bec573cだが、開始時に必ずfresh fetchして最新を使う。WB-14用anicca-products worktreeは/Users/anicca/Projects/anicca-products/.worktrees/lm-web-marketing-next、branch codex/lm-web-marketing-next-20261007、push先origin/codex/lm-web-marketing-next-20261007。開始前に両repoでhandoverとSSOTを読み、HEAD/upstream/dirtyをreadbackしてから専用worktreeを作る。共有checkout /Users/anicca/Projects/life-manager-main と /Users/anicca/Projects/anicca-products は書き換えない。reviewが必要なら対象commitのdetached snapshotに対するread-only reviewとする。

## メール

- Daisの指示どおりhandoverはチャットのみ。メール本文の作成・送信・mailbox readbackはしていない。
