# Life Manager 初週配布プラン

> Historical snapshot from 2026-10-21. Its dated counts, URLs, and statuses are not the current readback. Current status and cursor: [integrated SSOT](../../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md); current evidence: [2026-10-24 readback](../../../evidence/maritime/live-readback-20261024-1110Z.json).


**最終readback:** 2026-10-21 10:49 UTC。Article source/packageはLife Manager mainへPR #8492でmerge済み。Anicca Products PR #537はdraftでLanding CI/CodeRabbit PASSだが、candidate URLは404。GSC settled through 2026-10-18は0 clicks / 7 impressions。Postiz connectorはgroups=0 / integrations=0。RailwayはDashboard/APIとbuildが停止中で、production life-call/workerは06:23Zのdeploymentのまま。公開EN/JA pilot pageはHTTP 200だが旧daily-email claim。T26.5bのlive readback前はarticleやDMを公開しない。Life Manager X投稿・verified signup・attributed revenueは未確認。新規Instagram/X accountは作らない。

## 成功事例から移す仕組み

参照URL・出典のreported metric・適用範囲は docs/research/maritime/2026-10-20-source-map.md が正本。

- Todoist: 具体的な生産性の悩みを解く記事、実ユーザー例、一つのproduct CTAを同じcontent hubへ置く。公式ページの170K超はnewsletter readerの表示で、Life ManagerのSEO効果とは言わない。
- Ahrefs: 検索意図別のguide/how-toと独自調査を積み上げる。公式traffic表示をLife Managerの予測へ転用しない。
- Levels: 実際のbuild decision/result/constraintを記事と短いX投稿に分ける。Xが獲得原因とは断定しない。
- 同じ自律Life Managerが同じ媒体で1,000 usersへ到達した因果事例は未確認。まず記事1本と計測可能なCTAで試す。

## SEO記事

- canonical source: docs/research/manager/articles/2026-10-21-ai-assistant-vs-agent-next-task-en.md
- brief/公開条件: docs/distribution/maritime/week1/seo-article-draft-en.md
- existing destination: https://aniccaai.com/blog/manager
- candidate canonical URL: https://aniccaai.com/blog/manager-ai-assistant-vs-agent-next-task-en
- 2026-10-21 10:49 UTC readback: candidate URL HTTP 404。source/package are merged to Life Manager main by PR #8492 (app-code SHA b5ecef6e624203811d0e1103003c3cdbaf88c4cd); current main includes docs-only PR #8496. Anicca Products PR #537 remains draft. Deploy/readback remain.
- Early-pilot CTA may publish before the complete hosted cycle only after the page and article both say: full hosted work/report cycle is unverified; pilot sends necessary work data to Maritime; its AI-credit calls may be retained indefinitely after account deletion; revenue/profit is not guaranteed. Do not claim completed work or user earnings without provider receipts.
- UTM: utm_source=aniccaai&utm_medium=organic_search&utm_campaign=maritime-week1.

### Publication atoms

1. [x] Add the canonical article byte-for-byte at docs/research/manager/publication/2026-10-19/en/manager-ai-assistant-vs-agent-next-task-en.md; source/package are merged via PR #8492.
2. [x] Append title, description, slug, word_count, series_order=56, source/package SHA-256 and markdown to manifest.json; 56 entries and matching hash are in main.
3. [ ] Current bridge PR #537 is draft with Landing CI/CodeRabbit PASS; wait for T26.5b and a fresh exact-head review before marking ready/merging, then verify the production build.
4. [ ] Current state: canonical URL is HTTP 404 at 10:49Z. After deploy, crawl the canonical URL; require HTTP 200 and title/canonical/body matching the source package before treating the article as published.

## X

- Current Postiz connector readback at 10:49 UTC: groups=0, integrations=0.
- An earlier same-day receipt for @selawmqt is about AI-monk research and is not Life Manager promotion. It does not prove the current connector has that account.
- Do not publish until the existing broad X account identity and Postiz integration are visible in a fresh readback. Current integration count is zero. Then post one unique build-in-public update with utm_source=x&utm_medium=social&utm_campaign=maritime-week1. No new account, no Instagram, no duplicate post, no automated DM.
- Ready draft: “Life ManagerをMaritime向けにCloud接続中。pilot pageは公開していますが、hosted版が仕事を完了して日次メールまで送る一連の流れはまだ未検証です。目標・予算入力やTelegramを必須にしないManagerを作っています。売上・利益は保証しません。登録前にMaritimeへのデータ送信と保持条件を確認してください。”

## Daisが家族・友人へ送るDM案

“Life Managerのearly pilotページを公開しています。毎回の目標・予算入力なしでManagerが仕事を選び進める製品を作っていますが、hosted版の仕事完了〜日次報告はまだ未検証です。登録で必要なwork dataをMaritimeへ送り、AI-credit callはMaritime Privacy Policy上アカウント削除後も無期限保持されると説明されています。収益/利益は保証されません。内容を確認してから試すか判断してください: https://life-call-production.up.railway.app/maritime?lang=ja&source=referral&utm_source=friends&utm_medium=dm&utm_campaign=maritime-week1”

このcopyは配布素材であり、送信・既読・signup・競技user countの証拠ではない。現在のlive landingにはdaily-emailの未修正claimが残るため、T26.5b後に説明が一致したことを確認してから送信する。送信はDaisが担当する。

## 金銭計測

- Product-user revenue: external provider receipt → platform sale → cash settlement → refund/fee/cost → net.
- Life Manager company revenue: existing Stripe Life Manager price subscriptions and attributed paid invoices.
- Distribution revenue: article/X UTM source → verified lead → completed work → attributed paid receipt/settled amount.
- Pageview、impression、signup、listing、投稿だけを収益・competition real userへ換算しない。