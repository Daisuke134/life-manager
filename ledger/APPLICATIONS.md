# APPLICATIONS ledger (全エージェント共通・唯一の応募台帳)

対象: 就職応募 / VC・資金調達 / 助成金 / アクセラ / 案件提案(Upwork, Fiverr, Coconala, CrowdWorks, Lancers 等) / ディレクトリ・掲載依頼。
書く人: 参謀(Grok Bot), Fucker, Anicca Marketer, Side Hustle CEO, Local Life Manager (Mac mini Claude Code), Codex, Dots, Muse, 今後の全エージェント。

## ルール (必ず守る)
1. 応募前に `scripts/ledger-check.sh <key>` (または `git pull && grep -i <key> ledger/APPLICATIONS.md`)。ヒットしたら応募しない。
2. 無ければまず `claimed` 行を追加 → commit+push (main)。その後に応募。
3. 応募後に status を更新 (claimed → applied → replied → interview → won/lost) して push。
4. key = 正規化した一意キー: 会社/VCはドメイン (例 `a16z.com`)、案件は platform:ID (例 `coconala:5339402`)、メールは宛先アドレス。小文字、https:// と末尾/ は外す。
5. YC / a16z の既存応募には触れない (記録のみ)。秘密情報は書かない。日時はJST。

| date (JST) | type | target | key | agent | status | link | next action |
|---|---|---|---|---|---|---|---|
| 2026-10-?? | vc | Y Combinator (既存応募) | ycombinator.com | 成田さん | applied | - | 触らない |
| 2026-10-?? | vc | a16z speedrun (既存応募) | a16z.com | 成田さん | applied | - | 触らない |
| 2026-10-22 | gig | Upwork: AI-Powered Property Website Article Generation System ($60) | upwork:ai-powered-property-website-article-generation-system | 参謀 | applied | https://www.upwork.com/freelancers/~01f5fe272d6df34084 | 返信待ち。Connects 4残、購入しない |
| 2026-10-22 | gig | Upwork Project Catalog: AI agent $450 | upwork:catalog:ai-agent | 参謀 | applied | https://www.upwork.com/freelancers/~01f5fe272d6df34084 | 承認済み・受注待ち |
| 2026-10-22 | gig | Upwork Project Catalog: automation $350 | upwork:catalog:automation | 参謀 | applied | https://www.upwork.com/freelancers/~01f5fe272d6df34084 | 承認済み・受注待ち |
| 2026-10-22 | gig | Upwork Project Catalog: PDF extraction $300 | upwork:catalog:pdf-extraction | 参謀 | applied | https://www.upwork.com/freelancers/~01f5fe272d6df34084 | 承認済み・受注待ち |
| 2026-10-2? | gig | Fiverr gig (Fucker) | fiverr:fucker-gig | Fucker | claimed | - | 成田さんのID・税フォーム認証待ち |
| 2026-10-23 | gig | Coconala: AI活用SNS動画/note効率化 ¥30,000 | coconala:5339402 | 参謀 | applied | https://coconala.com/requests/5339402 | 返信待ち |
| 2026-10-23 | gig | Coconala: 外国人向け日本語学習Webアプリ ¥180,000 | coconala:5340997 | 参謀 | applied | https://coconala.com/requests/5340997 | 返信待ち |
| 2026-10-23 | directory | mybeing.app best affirmation app (Anicca) | hello@enthu.ai | 参謀 | applied | https://mybeing.app/blog/best-affirmation-app | 返信待ち |
| 2026-10-23 | directory | loa-lawofattraction.co best affirmation apps (Anicca) | hello@loa-lawofattraction.co | 参謀 | applied | https://loa-lawofattraction.co/blog/best-affirmation-apps | 返信待ち |
| 2026-10-23 | directory | sayafterme.app affirmation apps compared (Anicca) | hello@igwestudios.com | 参謀 | applied | https://sayafterme.app/blog/affirmation-apps-compared-2026 | 返信待ち |
| 2026-10-23 | directory | mylifenote.ai best gratitude journal apps (Thankful) | daniel@mylifenote.ai | 参謀 | applied | https://blog.mylifenote.ai/best-gratitude-journal-apps | 返信待ち |
| 2026-10-23 | directory | habitbox.app best gratitude journal app (Thankful) | support@habitbox.app | 参謀 | applied | https://habitbox.app/blog/best-gratitude-journal-app | 返信待ち |
| 2026-10-23 | directory | kickstherapy.com best journaling apps (Thankful) | annabel@kickstherapy.com | 参謀 | applied | https://kickstherapy.com/blog/best-journaling-apps-mental-wellness | 返信待ち |
| 2026-10-23 | directory | sleepingontheedge.com best sleep apps (For Better Sleep) | hello@sleepingontheedge.com | 参謀 | applied | https://sleepingontheedge.com/best/best-sleep-apps | 返信待ち |
| 2026-10-23 | directory | appstoretracker.com sleep tracker apps (For Better Sleep) | info@appstoretracker.com | 参謀 | applied | https://appstoretracker.com/best/sleep-tracker-apps | 返信待ち |
| 2026-10-23 | directory | snorecam.app best sleep apps 2026 (For Better Sleep) | privacy@snorecam.app | 参謀 | applied | https://snorecam.app/learn/best-sleep-apps-2026 | 返信待ち |
| 2026-10-23 | directory | mindfulsuite.com best affirmations apps (Anicca) | mindfulsuite.com | 参謀 | claimed | https://mindfulsuite.com/reviews/best-affirmations-apps | メール無し→問い合わせフォーム |
