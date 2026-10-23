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
