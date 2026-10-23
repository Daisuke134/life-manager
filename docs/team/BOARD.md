# Anicca Company チームボード（全エージェント共有）
目標: One Phone One Million。売上最大化＋成田さんの生活管理。
メンバー: 参謀(Grok Bot, 司令塔・X担当) / Local Life Manager(Mac mini) / Dots / Muse(Instagram担当)
ルール:
- 正本は GitHub Daisuke134/life-manager の docs/team/BOARD.md。各ループ開始時にこのファイルを読み、終了時に「## ログ」へ1行追記（日時JST・担当・やったこと・数字・次）。
- タスクは「## タスク」で担当を名乗ってから着手。重複禁止。
- 認証情報は /workspace/.secrets、ノウハウは /workspace/knowhow/INDEX.md。
- 成田さんへの報告は日本語。承認は不要（全部承認済み）。
## タスク
- [Codex AI Monk] Factory AM-15c source受入とPII CI注記1件修復 → docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md S11。outreach送信/宛先は変更しない。
- [Codex] READMEの外部向け整理・Mac初回導入修復（PR #8666、CI確認中）
- [参謀] ランサーズ/ココナラ応募・返信、X読み取り＋数字分析
- [Muse] Instagram配信
- [Local LM] Mac mini上のジョブ
- [Dots] 未割当
## ログ
- 2026-10-23 18:39 Codex AI Monk: PR8668のFactory利用者publisher接続を独立review後に修復し、未解決0件。旧head独立210件とtimezone修復後38件がPASS。mainのlisticle-outreach.mdの使用禁止個人Gmail注記1件だけをprivate SSOT参照へ置換し、PII scan clean。送信元/宛先/配信状態・scanner/allowlistは保持、outreach送信0。次: exact CI/main/固定版、運用順はS11。
- Codex: READMEを英日各52行へ整理し、Codex認証確認漏れとbrowser依存不足を修復。空Python環境・installer28件・Web CTA122件がPASS。並行main文書の個人senderをprivate参照へ置換し、PII検査はclean。次は最新CI・main統合・公開readback。
- 2026-10-23 17:25 参謀: ボード作成。ランサーズ3件提案済み。
- 2026-10-23 17:55 参謀(チーム収益ループ初回): 受託=ランサーズ受信確認＋新規2件提案を実行中／自社=デイリー・ダンマのRevenueCat転換チェック実行中。結果は次パスで追記。
- 2026-10-23 17:57 参謀: 受託=ランサーズ新規2件提案（Shopify移行5618921 ¥35万／Beds24空調自動化5619037 ¥35万、補足メッセ送信）、受信3件は運営削除のスパムで返信なし、残り提案枠11→9。自社=デイリー・ダンマ28日MRR$0・新規16/課金0、原因は閉じられる課金画面。推奨案 team/inhouse/dhamma.md（ハードペイウォール＋週額¥500/年額BEST VALUE、トライアルなし）。次: paywall.tsx改修→週額商品作成→1.1.1提出。
- 2026-10-23 18:55 参謀(SEO/AIO/Reddit真似プラン): aniccaai.comに比較記事2本公開(/best-affirmation-apps, /ja/best-affirmation-apps, sitemap追加, IndexNowキー追加, anicca-products d1d8b4a2a)。GSCは所有確認済み(10/18, keiodaisuke)だがサイトマップ送信はAPI権限なし→成田さんのブラウザで1クリック要。リスティクル10件の連絡先と依頼文=docs/team/specs/listicle-outreach.md(未送信)。Reddit=docs/team/specs/reddit.md(下書き5件・未作成アカウント)。次: Bing IndexNow送信、Redditアカウント作成(ブラウザ要)。
- 2026-10-23 18:32 参謀: リスティクル掲載依頼メール送信(lifemanager.jp@agentmail.to)=5件: MyBeing hello@enthu.ai / LoA hello@loa-lawofattraction.co / Say After Me hello@igwestudios.com / Life Note daniel@mylifenote.ai / HabitBox support@habitbox.app。残り4件(Kicks Therapy, SleepingOnTheEdge, App Store Tracker, SnoreCam)はAgentMail送信上限(初回1時間5宛先)で未送信、19:30 JST以降に再送。mindfulsuiteはフォームがブラウザ必須(Cloudflare)でスキップ。
