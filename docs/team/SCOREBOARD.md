# Anicca Company スコアボード（数字の正本）

数字はこのファイルが正本。出典のある数字だけ書く。推測・未確認は書かない（不明は「未計測」）。
更新したら該当行の「更新(JST)」と「出典」を書き換え、BOARD.md のログに1行追記する。

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
| Anicca App Units（ASC） | 未取得（最新 business_date 2026-10-21 の downloads は `report_pending`。最後の available は 10/15 の first_time_downloads=1） | 2026-10-22 06:07 | `~/.local/state/life-manager/marketing-metrics-daily/state/business-outcomes.jsonl` product_id=`anicca-ios`、observed_at 2026-10-21T21:07:53Z、`sources.app_store_connect.data.reports.downloads.status` |
| 無料記事公開（aniccaai.com self-owned landing） | 20本（ユニーク slug） | 2026-10-23 20:35 | `~/.local/state/life-manager/writer/checkouts/self-owned-landing` の reflog（`.git/logs/HEAD`）で今日JSTの `publish free article <slug>` をユニーク集計（rebase pick 重複を除外、生の行数は33） |
| Postiz 投稿（Anicca 連携） | PUBLISHED 10 / ERROR 3（09:00〜16:48 JST の範囲） | 2026-10-23 16:48 | `~/.local/state/life-manager/evidence/mobile-flagship/20261023/postiz-final-official-readback-20261023T074813Z.json`（`GET /public/v1/posts`、`anicca_post_readbacks[].state`）。16:48 以降は未取得 |
| Writer 有料記事 公開 | 0本（今日の行3件はすべて `pending: required fail-closed proofs unavailable`、`published=false`） | 2026-10-23 14:49 | `~/.local/state/life-manager/writer/articles.jsonl` の ts 今日JST行。`live_url` 列は存在しない |
| Capafy 累計 gross / 非トライアル件数 | $112.74 / 33件 | 2026-10-23 20:07 | `~/.local/state/life-manager/state/capafy-hourly-reconcile.json` `money.gross_usd`・`money.non_trial_units`、observed_at 2026-10-23T11:07:54Z |
| PromptBase 売上件数 / net | 0件 / $0.00 | 2026-10-23 17:52 | `~/.local/state/life-manager/state/promptbase-sales.json` `sales_count`・`net_usd`、observed_at 2026-10-23T08:52:15Z（source: PromptBase Sales tab） |
