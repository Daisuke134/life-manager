# Thankful – Gratitude Journal launch kit (1.0.2)

型は `docs/team/launch/for-better-sleep.md` と同じ。共通ルールと勝ち組の根拠は `docs/team/launch/README.md`。

- Status: 1.0.2（新しい課金画面）が App Store で公開中。Apple「Ready for Distribution」メール 2026-10-24 06:32 JST、ASC `appStoreVersions` 1.0.2 = `READY_FOR_SALE`。
- App Store (id 6759514159): 下の「リンク」を使う。`ct` は App Store Connect のキャンペーン計測用、`utm_*` は参謀指定の共通キー（Apple は `utm_*` を集計しないので、DL の帰属は `ct` で読む）。
- Approved claims only (`skills/earn/marketing-engine/registry/products/thankful.json`): write three gratitude entries, read daily affirmations, track a journaling streak. Do not claim mental-health outcomes.
- Free vs Pro (1.0.2, `docs/team/specs/thankful-paywall.md`): free = one entry a day, today's affirmation, last 7 days of history. Pro = unlimited entries, all affirmations, full history.
- Price (ASC subscription prices, read 2026-10-24): monthly $4.99 / ¥800, annual $29.99 / ¥5,000. ASC に1週間無料の導入オファーが登録済み。ただしアプリが表示するのは対象者だけなので、投稿では無料体験を約束しない。
- Numbers (RevenueCat proj7aaf9429, 28 days, 参謀 2026-10-24 12:5x): new 8, trials 0, paid 0, MRR $0. Main gap is traffic.
- Images: App Store screenshots (iTunes lookup `screenshotUrls`): ① home with three lines and streak, ② history, ③ affirmation card.
- Post time: evening JST (yokoichi777's health app peaked 20:00–21:00 JST) / late evening US.

## リンク

`<cc>` = `jp`（日本語投稿）/ `us`（英語投稿）。`<channel>` = `x`, `bluesky`, `mastodon` など。

```
https://apps.apple.com/<cc>/app/id6759514159?pt=93486075&ct=<channel>-thankful-102&mt=8&utm_source=<channel>&utm_campaign=thankful-102
```

## EN 1 — story opener

```
I tried gratitude journaling three times and quit every time.

Too many prompts. Too much to write.

So I made the smallest version I would actually keep: three lines a day, a daily affirmation, and a streak.

What's the one thing that makes you quit a habit app?
```

## EN 2 — one difference + price

```
Most journaling apps want a paragraph.

Thankful asks for three short lines.

Write what you're grateful for, read today's affirmation, keep your streak.

Free for one entry a day. Pro is $4.99/month or $29.99/year for unlimited entries and your full history.

What would you write today?
```

## JA 1 — yokoichi777 shape

```
1日3行だけの感謝日記アプリ『Thankful』を作りました。

ありがとうを3つ書いて、今日のアファメーションを読んで、連続記録を伸ばすだけ。

続かなかった日記の「いちばん小さい版」です。

祝個人開発
詳細はツリーに
```

## JA 2 — one difference + price

```
日記アプリは、だいたい長い文章を求めてきます。

Thankful が求めるのは、短い3行だけ。

感謝を書く、今日のアファメーションを読む、連続記録を伸ばす。

無料でも1日1件書けます。
Pro（月¥800／年¥5,000）で、何件でも書けて、全部の履歴を見返せます。

今日、何を書きますか？
```

## First reply

```
App Store: <上の「リンク」で cc と channel を埋めたURL>
```

## ASO keyword candidates

Current (en): `gratitude,journal,mindfulness,affirmation,diary,thankful,mood,wellness,habit`
Current (ja): `感謝,日記,習慣,マインドフルネス,朝活,振り返り,ジャーナル,メンタル,gratitude,journal`

Observed titles (iTunes Search API, 2026-10-24): US "gratitude journal" → Gratitude: Self-Care Journal (44,975 ratings), Gratitude Plus – Journal (20,501), 5 Minute Journal・Daily Diary (17,608), 365 Gratitude Journal & Diary (4,541). JP 「感謝日記」 → My感謝日記 -毎日のありがとうを習慣化するSNSアプリ (1,915), muute｜AIジャーナリング (21,037), 神棚アプリ - 感謝日記・引き寄せ… (7,023).

Pattern in winners: the title carries "Journal / Diary" plus a second use word; JP titles put the benefit after a hyphen (毎日のありがとうを習慣化).

Candidates (verify popularity before changing; keyword field is 100 characters, no spaces after commas):
- en: `gratitude,journal,diary,affirmations,self care,daily,prompts,streak,positive,reflection,habit` (drop `mood`, `wellness`, `mindfulness` if popularity is low; `daily` and `self care` appear in the top titles)
- ja: `感謝,ありがとう,日記,3行日記,習慣化,アファメーション,引き寄せ,自己肯定感,振り返り,ジャーナリング`
- Subtitle idea (ja), copying the hyphen-benefit shape: `毎日3行のありがとうを習慣に`

## Schedule (Postiz)

Postiz public API `POST /public/v1/posts`（`type: schedule`）、integration `cmm6d7m5703rwpr0yr5vtme3w`（X「アニッチャ」@aniccaxxx）。各投稿は2件のスレッドで、1件目が本文＋App Store スクリーンショット、2件目が App Store リンク（`ct=x-thankful-102`、`utm_source=x&utm_campaign=thankful-102`）。

| postId | group | 予約 (JST) | 本文 | 画像 | readback |
|---|---|---|---|---|---|
| `cmvlv50ix162equ1cwhpy6ldt` | `7ccf71d6` | 2026-10-24 21:00 | JA 1 | スクショ3枚 | `GET /public/v1/posts` state=QUEUE |
| `cmvlv514308boln1ckjykvnp6` | `1256c7aa` | 2026-10-25 21:00 | JA 2 | スクショ1枚 | `GET /public/v1/posts` state=QUEUE |

同じアカウントの For Better Sleep 投稿 `cmvlmk64m02x7ln1c7aop018l` が 2026-10-24 22:10 JST に予約されているので、その70分前に置いた。

Known gaps:
- Bluesky と Mastodon は Postiz に連携がなく（`GET /public/v1/integrations` に該当なし）、`~/.local/share/anicca/credentials.json` にもアカウントがない。新しいアカウントからすぐリンク付きで投稿すると spam 判定されやすい（TikTok での実例）ため、今回は予約していない。
- `skills/earn/capafy-marketing/scripts/capafy_x_link_reply.py` に「Postiz は X 投稿からリンクを除去する（2026-10-11）」という記録がある。2件目のリンクが公開後に残っているか確認が必要。消えていた場合は、ブラウザからの自己リプライで足す（前例は `x:anicca` の @selawmqt）。ただし `browsers.toml` に @aniccaxxx 用の identity はまだない。
- 公開後の `releaseURL` とリプライの有無は未確認（予約時点）。
