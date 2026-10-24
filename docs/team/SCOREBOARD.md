# Anicca Company スコアボード（数字の正本）

数字はこのファイルが正本。出典のある数字だけ書く。推測・未確認は書かない（不明は「未計測」）。
更新したら該当行の「更新(JST)」と「出典」を書き換え、BOARD.md のログに1行追記する。

## 最新（毎時更新） 2026-10-24 12:10 JST

| 項目 | 値 | 出典 |
|---|---|---|
| 共有応募台帳 行数 | 197（status別: historical_recorded_pending_not_reverified 52 / rejected 32 / applied 22 / acknowledged 14 / historical_submission_assertion_primary_receipt_not_reverified 14 / claimed 12 / submission_uncertain 11 / application_receipt_verified_in_review 7 / submitted_official_confirmation_recorded 6 / interview_or_scheduling_pending 6 / application_email_sent 4 / withdrawn 4 / outcome_mapping_pending 3 / listed 2 / needs-owner 2 / acknowledged_unmapped_group 1 / assessment_pending 1 / email_bounced 1 / published 1 / blocked 1 / parked 1）（type別: job 165 / directory 11 / gig 7 / listing 4 / grant 3 / vc 2 / promo 2 / promotion 1 / content 1 / accelerator 1） | `ledger/APPLICATIONS.md` @ origin/main e18dd46266（ファイル最終変更 b34707a27d）、表のヘッダ・区切り以外の行を status/type 列で awk 集計 |
| Capafy 初の有料販売（エージェント単位） | 「TikTok Series Continuity Planner」(9425449917) $9.99/週・トライアルなし 1件、流入元 direct | Capafy 通知メール「Your Agent "TikTok Series Continuity Planner" just made its first sale」2026-10-23 13:17 JST（Gmail id 1a166faac1614e9b）＋ `capafy-hourly-reconcile.json` `traffic_sources.by_agent.9425449917.last_30d`（paid_orders 1, sales_usd 9.99） |
| Capafy 累計 gross / 非トライアル / トライアル | $112.74 / 33件 / 75件（creator earnings $83.78、pending $59.00、paid out $0.00） | `~/.local/state/life-manager/state/capafy-hourly-reconcile.json` `money.*`、observed_at 2026-10-23T17:28:09Z |
| Capafy 流入（全エージェント） 7日 / 30日 | views 1,929（有料1・トライアル2）/ 5,476（有料9・トライアル6）。7日の内訳 search 1,125 / direct 422 / other 151 / ai_overview 91 / google 49 / 自社 ct 計55（hooklab_free 48・tiktok_x 4・hooklab_x 2・youtube_x 1） | 同ファイル `traffic_sources.last_7d.by_source`・`last_30d.by_source`、observed_at 2026-10-23T17:28:09Z |
| 配信リーチ（X・IG・TikTok 表示回数） | 未計測（本更新では各プラットフォームの公式値を取得していない。自社 ct 経由の Capafy 流入は上の行） | — |
| PromptBase 売上 | 0件 / $0.00 | `~/.local/state/life-manager/state/promptbase-sales.json` observed_at 2026-10-23T13:24:33Z |
| Coconala 応募（今日JST） | 7件 | `~/gig/applied.jsonl` status==applied, ts>=2026-10-24 0時JST（12:05 JST 集計） |
| Writer 有料記事 公開（今日JST） | 0本（今日の台帳行 0） | `~/.local/state/life-manager/writer/articles.jsonl` |
| RevenueCat Anicca 28日 MRR / 売上 / 有効購読 / 新規顧客 | $20 / $0 / 5 / 45（active users 67） | RevenueCat v2 `GET /projects/projbb7b9d1b/metrics/overview?currency=USD` 2026-10-24 12:08 JST。APIキーは Anicca プロジェクトのみ参照可のため、他アプリは下の「売上 / MRR」表（10/23 17:40 スナップショット）が最新 |
| App Store 新規DL 10/17〜10/22（6日計） | Honne 8 / Daily Affirmations - Anicca 4（＋再DL 1）/ Daily Dhamma 5 / STUDIO CHERIE 1（＋再DL 1）/ For Better Sleep 1 / Thankful 0。日別: 10/17 Honne1・10/18 Anicca1(+再1) Honne4 Dhamma1・10/19 Anicca2 CHERIE1 FBS1・10/20 Dhamma1 Honne1・10/21 Anicca1 Honne2(CHERIE再1)・10/22 Dhamma3 | ASC Sales Report API（DAILY SALES SUMMARY、全アプリ、Product Type 1/1F=新規・3/3F=再DL）を `business_outcomes.read_asc_sales_report` で 2026-10-24 12:06 JST に読取。10/23 は Apple『Report is not available yet』 |
| App Store レビュー件数 | Daily Affirmations - Anicca 3件（平均 3.67）/ STUDIO CHERIE 1件（5.0）/ 他22アプリ 0件 | ASC API `GET /v1/apps/{id}/customerReviews`（全24アプリ）2026-10-24 12:09 JST |
| GitHub stars（Daisuke134/life-manager） | 8 / 目標 10,000 | `gh api repos/Daisuke134/life-manager --jq .stargazers_count` 2026-10-24 12:05 JST |

## 2026-10-23 夜（参謀依頼）

| 項目 | 値 | 時刻 | 出典 |
|---|---|---|---|
| Grok for Startups 提出 | 提出済み | 22:32 JST | 参謀(daisuke/cursor) の Reason 報告 2026-10-23。`ledger/APPLICATIONS.md` には未記載（照合未了） |
| Coconala 提案 5338722 | applied ¥10,000 | 22:02 JST | `~/gig/applied.jsonl` requestId=5338722 status=applied |
| Coconala 提案 5338965 | applied ¥30,000 | 22:02 JST | `~/gig/applied.jsonl` requestId=5338965 status=applied |
| Coconala 提案 5341300 | applied ¥80,000 | 22:02 JST | `~/gig/applied.jsonl` requestId=5341300 status=applied |
| 今夜の売上 | ¥0 | 23:00 JST 時点 | 参謀の Reason 報告。ローカルの Coconala 売上台帳（`~/gig/earnings.jsonl`）は 9/27 で停止のため未照合 |

## 売上 / MRR

| 項目 | 値 | 更新(JST) | 出典 |
|---|---|---|---|
| 全21プロジェクト合計 28日MRR / 28日売上 | $24 / $38 | 2026-10-23 17:40 | RevenueCat get-overview-metrics → `docs/team/specs/revenuecat-snapshot-20261023.md` |
| 本音翻訳AI（honne-honyaku）28日MRR / 28日売上 | $4 / $38 | 2026-10-23 17:40 | 同上 |
| デイリー・ダンマ（dhamma）28日MRR / 28日売上 | $0 / $0 | 2026-10-23 17:40 | 同上 |
| Anicca 28日MRR / 28日売上 | $20 / $0 | 2026-10-23 17:40 | 同上 |
| LINEスタンプ 売上（工場セット、分配速報値） | ¥0 | 2026-10-14 06:06 | Creators Market 公式 `/stats/sticker`・`/payment_request/` → 統合SSOT `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`（LINE sticker As-Is） |

## 受託（応募・提案）

| 項目 | 値 | 更新(JST) | 出典 |
|---|---|---|---|
| ココナラ 応募 | 2件（5339402 ¥30,000 / 5340997 ¥180,000） | 2026-10-23 18:55 | BOARD.md ログ 参謀 18:55 |
| ランサーズ 提案 | 5件（17:25 に3件 + 17:57 に2件） | 2026-10-23 17:57 | BOARD.md ログ 参謀 17:25・17:57 |
| 提案数 合計（10/23） | 7件 | 2026-10-23 18:55 | 上2行の合計 |
| 成約 | 0件 | 2026-10-23 18:55 | BOARD.md ログ 参謀 18:55（受信は不採用連絡・スパムのみ） |

## インストール / App Store Connect

| 項目 | 値 | 更新(JST) | 出典 |
|---|---|---|---|
| Anicca 新規ダウンロード 日別 10/18・10/19・10/20・10/21・10/22 | 1・2・0・1・0（他に再ダウンロード 10/18 に1） | 2026-10-23 20:45 | ASC Sales Report API（DAILY SALES SUMMARY、Apple ID 6755129214、Product Type 1=新規・3=再DL）を `business_outcomes.read_asc_sales_report` で読取。10/22 は Apple『There were no sales for the date specified.』 |
| Anicca App Units 週次（10/12〜10/18） | 2（前週比 -71%） | 2026-10-23 04:44 | Apple App Analytics Weekly Summary メール → 統合SSOT「今回の一次証拠」 |

## 資金調達パイプライン

| 候補 | 種別 | 状態 | 次の一手 | 更新(JST) | 出典 |
|---|---|---|---|---|---|
| （空） | | | | 2026-10-23 20:06 | 未着手（担当: claude-3 資金調達・機会パイプライン） |

## OSS

| 項目 | 値 | 更新(JST) | 出典 |
|---|---|---|---|
| Daisuke134/life-manager stars / 目標 | 8 / 10,000 | 2026-10-23 20:06 | `gh api repos/Daisuke134/life-manager --jq .stargazers_count` |

## 2026-10-23（JST）ローカル readback 計測

Mac mini 上の実ファイルを read-only で集計（20:35 JST 時点）。推測なし。取れないものは「未取得」と理由。

| 項目 | 値 | 更新(JST) | 出典 |
|---|---|---|---|
| 応募台帳 行数（type別） | 合計26 = directory 10 / gig 7 / listing 4 / job 3 / vc 2 | 2026-10-23 20:35 | `ledger/APPLICATIONS.md`（main 98241d81f1、ファイル最終変更 3bc09b272a）表の `\| 20` 始まり行を awk 集計 |
| 応募台帳 行数（status別） | applied 20 / claimed 4 / listed 2 | 2026-10-23 20:35 | 同上 |
| ココナラ 応募（`~/gig/applied.jsonl`） | 直近24h 26件 / 今日JST 26件（最終 20:27） | 2026-10-23 20:35 | `~/gig/applied.jsonl` の `status=="applied"` 行を `ts`（epoch秒）で JST 集計。上の「受託」表の2件（BOARD ログ由来）とは出典が異なる |
| Anicca App Units（ASC, business-outcomes.jsonl 経路） | この経路では未取得（最新 business_date 2026-10-21 の downloads は `report_pending`。最後の available は 10/15 の first_time_downloads=1）。日別実測は上の「インストール」表の ASC Sales Report API 行を参照 | 2026-10-22 06:07 | `~/.local/state/life-manager/marketing-metrics-daily/state/business-outcomes.jsonl` product_id=`anicca-ios`、observed_at 2026-10-21T21:07:53Z、`sources.app_store_connect.data.reports.downloads.status` |
| 無料記事公開（aniccaai.com self-owned landing） | 20本（ユニーク slug） | 2026-10-23 20:35 | `~/.local/state/life-manager/writer/checkouts/self-owned-landing` の reflog（`.git/logs/HEAD`）で今日JSTの `publish free article <slug>` をユニーク集計（rebase pick 重複を除外、生の行数は33） |
| Postiz 投稿（Anicca 連携） | PUBLISHED 10 / ERROR 3（09:00〜16:48 JST の範囲） | 2026-10-23 16:48 | `~/.local/state/life-manager/evidence/mobile-flagship/20261023/postiz-final-official-readback-20261023T074813Z.json`（`GET /public/v1/posts`、`anicca_post_readbacks[].state`）。16:48 以降は未取得 |
| Writer 有料記事 公開 | 0本（今日の行3件はすべて `pending: required fail-closed proofs unavailable`、`published=false`） | 2026-10-23 14:49 | `~/.local/state/life-manager/writer/articles.jsonl` の ts 今日JST行。`live_url` 列は存在しない |
| Capafy 累計 gross / 非トライアル件数 | $112.74 / 33件 | 2026-10-23 20:07 | `~/.local/state/life-manager/state/capafy-hourly-reconcile.json` `money.gross_usd`・`money.non_trial_units`、observed_at 2026-10-23T11:07:54Z |
| Capafy 増加分の出所（+$9.99） | agent 9425449917「TikTok Series Continuity Planner」有料1件（$9.99/週・trialなし）、流入元 direct、7日views 4 | 2026-10-23 21:45 | `~/.local/state/life-manager/state/capafy-hourly-reconcile.json` `traffic_sources.by_agent.9425449917.last_7d`（paid_orders 1, sales_usd 9.99）、初観測 reconcile 2026-10-23T04:14Z（PR #8622 で FROZEN 化） |
| PromptBase 売上件数 / net | 0件 / $0.00 | 2026-10-23 17:52 | `~/.local/state/life-manager/state/promptbase-sales.json` `sales_count`・`net_usd`、observed_at 2026-10-23T08:52:15Z（source: PromptBase Sales tab） |
