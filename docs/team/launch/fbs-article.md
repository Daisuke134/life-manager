# 4アプリ課金画面の作り直し記録: note(JA) / Substack(EN) クロスポスト原稿 + X引用ポスト案 2026-10-24

下書きのみ。公開はしていない。

- 元記事（正本）: https://aniccaai.com/blog/build-in-public-paywall-4apps-2026-10-24 （claude-7、anicca-products #658）
- note: claude-7 の下書き `nd42c30868e7c` が既にある。新しい下書きは作らない。note と Substack の公開は Dais 2026-07-12 の決定（`skills/writer-agent/scripts/publish-substack.sh` の DRAFT-ONLY 注記、BOARD 2026-10-24 13:0x claude-7 行）により、Dais がダッシュボードで判断する。公開時は下の JA 版の「今回のアプリ」節で note 下書きの末尾を差し替える。
- Substack: EN 版を既存 `publish-substack.sh`（draft-only）で下書き作成。draft id は BOARD のログ行に記録。
- 数字の出典は元記事と同じ（`docs/team/specs/{thankful,for-better-sleep,honne,daily-dhamma}-paywall.md` の RevenueCat 28日 2026-10-23、Apple 審査完了メール、ASC 1.0.2 READY_FOR_SALE）。新しい数字は足していない。
- 導線: aniccaai.com は `utm_source=note|substack&utm_medium=article&utm_campaign=fbs-102|thankful-102`。App Store は utm を無視するため `docs/team/launch/README.md` の規約どおり `ct=<source>_<campaign>`（例 `ct=note_fbs-102`）で計測する。

---

## JA（note 用）

タイトル: 4つのアプリの課金画面を一晩で作り直した記録：28日売上$0から、2本が審査を通るまで（数字をぜんぶ公開）

2026年10月23日の夜から24日の朝にかけて、私たちのチーム（人間1人とAIエージェント数体）は、自社iOSアプリ4本の課金画面を作り直しました。結果、Thankful 1.0.2 が06:29、For Better Sleep 1.0.2 が08:21に審査を通過し、App Storeで公開されました。

先に正直に書きます。改修後の売上は、この記事を書いている時点でまだ1件も確認できていません。これは成功談ではなく、売上ゼロのアプリを「売れているアプリの型」に合わせて直した、最初の一晩の記録です。

### 1. 出発点：4本とも、ほぼ売れていなかった

RevenueCat（課金管理サービス）で過去28日の数字を見たところから始めました（2026-10-23取得）。

| アプリ | 28日の新規ユーザー | 28日の売上 | 状態 |
|---|---|---|---|
| Thankful（感謝日記） | 3人 | $0 | 3人中0人が課金 |
| For Better Sleep（睡眠） | 1人 | $0 | 流入がほぼない |
| 本音翻訳AI | 24人 | $38（既存の更新のみ） | 7月以降の新規41人中、7日以内の課金0人 |
| デイリー・ダンマ（仏教の言葉） | 16人 | $0 | 1月以来の新規139人中、7日以内の課金0人 |

ユーザーは少しいるのに、新しく払う人がいない。原因を探すため、課金画面のコードを1行ずつ読みました。

### 2. 見つかった原因：「払う理由」と「払う場面」がなかった

- Thankful：何もロックされていなかった。有料版の約束（無制限の記録、200以上のアファメーション）が、無料版で全部使えました。課金の読み込みに失敗すると、お金を払わずに有料版になる不具合もありました。
- デイリー・ダンマ：「今すぐ¥3,000払う」以外の選択肢がなかった。まだ1句も読んでいない人に、無料体験なしで年額か月額の支払いを求め、閉じるボタンが2つありました。
- 本音翻訳AI：閉じられる課金画面と、毎日3回の無料枠。軽く使う人は払う必要がありませんでした。
- For Better Sleep：課金画面はすでに勝ち組型。問題は見せ方と流入です。年額$39.99は週あたり約$0.77なのに総額だけが出ていて、通信に失敗すると実際と違う価格（$12.99/週）が表示される作りでした。

### 3. やったこと：自分で考えず、売れているアプリの型を写した

- Thankful → Gratitude / 5 Minute Journal 型。毎日の記録（1日1件、今日のアファメーション、7日分の履歴）は無料のまま、深い機能を有料に。ロックした機能を押したときと3日連続記録の達成時に課金画面を出し、閉じるボタンは3秒後に表示。無料で有料版になる不具合を修正。
- For Better Sleep → BetterSleep 型。年額を先頭に置き、週あたりの金額を大きく表示。直書きの価格を削除してストアの価格だけを表示。
- 本音翻訳AI → ハードペイウォール型。購入か復元をしないと本編に入れない課金画面に変更。
- デイリー・ダンマ → Motivation（評価110万件）型。年額に3日間の無料体験を付けた。$19.99/年は Motivation と同じなので据え置き。

価格はどのアプリも上げていません。変えたのは、見せ方と、課金画面を出す場面です。

### 4. タイムライン（JST）

| 時刻 | 出来事 |
|---|---|
| 10/23 21:15 | Thankful の課金改修PRとTestFlightへのアップロード |
| 10/24 02:45 | Thankful 1.0.2 を審査に提出 |
| 10/24 04:3x | For Better Sleep 1.0.2 を審査に提出 |
| 10/24 04:40 | 本音翻訳AI 1.0.5 を審査に提出（審査待ち） |
| 10/24 06:29 | Thankful 1.0.2 審査通過 |
| 10/24 08:21 | For Better Sleep 1.0.2 審査通過 |
| 10/24 09:00 | デイリー・ダンマ 1.1.1 が TestFlight で利用可能に（提出準備中） |

提出から通過まで、Thankful が約3時間45分、For Better Sleep が約4時間でした。

### 5. 全数字まとめ（10/24 昼時点）

| 項目 | 値 |
|---|---|
| 課金画面を作り直したアプリ | 4本 |
| 審査を通過して公開 | 2本（Thankful、For Better Sleep） |
| 審査待ち | 1本（本音翻訳AI） |
| 提出準備中 | 1本（デイリー・ダンマ） |
| 価格を上げたアプリ | 0本 |
| 改修後に確認できた売上 | まだ0件 |

### 6. うまくいっていないこと

- 流入が小さすぎる。For Better Sleep は28日で新規1人です。課金画面を直しても、見る人がいなければ売上は増えません。
- 効果はまだ測れていない。課金画面の表示回数・無料体験の開始数・課金数を、ここから計測します。
- 実機での購入テストは一部未実施。For Better Sleep のサンドボックス購入から復元までの確認が残っています。

### 7. ここから何をするか

1. 計測。新規ユーザー→無料体験の開始率を週ごとに追います。目標は業界中央値の10%以上。
2. 流入。X・TikTok・Instagram・無料記事で毎日アプリを紹介します。広告費はかけません。
3. 残り2本の公開。本音翻訳AIの審査結果を待ち、デイリー・ダンマを提出します。

結果は、売れても売れなくても、また数字で公開します。

### 今回のアプリ

- For Better Sleep（睡眠リセット）: https://aniccaai.com/sleepreset?utm_source=note&utm_medium=article&utm_campaign=fbs-102
- For Better Sleep（App Store）: https://apps.apple.com/jp/app/id6762143790?pt=93486075&ct=note_fbs-102&mt=8
- Thankful（App Store）: https://apps.apple.com/jp/app/id6759514159?pt=93486075&ct=note_thankful-102&mt=8

全文と更新は元記事に置いています: https://aniccaai.com/blog/build-in-public-paywall-4apps-2026-10-24?utm_source=note&utm_medium=article&utm_campaign=fbs-102

---

## EN (Substack)

Title: We rebuilt the paywalls of 4 apps in one night: from $0 in 28 days to 2 approvals (every number)
Subtitle: No price increases. We copied the paywalls of apps that already sell. Post-change revenue so far: zero.

Between the night of October 23 and the morning of October 24, 2026, our team (one human and a few AI agents) rebuilt the paywalls of four of our own iOS apps. Thankful 1.0.2 passed App Review at 06:29 JST and For Better Sleep 1.0.2 at 08:21 JST. Both are live on the App Store.

To be upfront: as of writing, we have not confirmed a single sale since the change. This is not a success story. It is the record of one night spent fitting zero-revenue apps to the shape of apps that sell.

### 1. Starting point: none of the four was selling

We started from the last 28 days in RevenueCat (pulled 2026-10-23).

| App | New users (28d) | Revenue (28d) | Status |
|---|---|---|---|
| Thankful (gratitude journal) | 3 | $0 | 0 of 3 paid |
| For Better Sleep | 1 | $0 | almost no traffic |
| Honne Translator AI | 24 | $38 (renewals only) | 0 of 41 new users since July paid within 7 days |
| Daily Dhamma (Buddhist quotes) | 16 | $0 | 0 of 139 new users since January paid within 7 days |

A few people used the apps, but nobody new paid. We read the paywall code line by line to find out why.

### 2. What we found: no reason to pay, and no moment to pay

- Thankful: nothing was locked. Everything the paid tier promised (unlimited entries, 200+ affirmations) was available for free. If billing failed to load, the app also unlocked the paid tier without payment.
- Daily Dhamma: the only option was "pay ¥3,000 now". People who had not read a single verse were asked for an annual or monthly payment with no free trial, and the screen had two close buttons.
- Honne Translator AI: a dismissible paywall and three free uses per day. Light users never needed to pay.
- For Better Sleep: the paywall already followed the winning shape. The problems were presentation and traffic. $39.99/year is about $0.77/week, but only the total was shown, and a network failure displayed a wrong price ($12.99/week).

### 3. What we did: copied the paywalls of apps that already sell

- Thankful → Gratitude / 5 Minute Journal. The daily habit (one entry a day, today's affirmation, 7 days of history) stays free; deeper features are paid. The paywall appears when a locked feature is tapped and after a 3-day streak; the close button appears after 3 seconds. Fixed the free-unlock bug.
- For Better Sleep → BetterSleep. Annual plan first, with the per-week price shown large. Removed hard-coded prices so only store prices appear.
- Honne Translator AI → hard paywall. The app cannot be entered without purchasing or restoring.
- Daily Dhamma → Motivation (1.1M ratings). Added a 3-day free trial to the annual plan. $19.99/year matches Motivation, so the price stays.

We did not raise any price. We changed how the offer is shown and when the paywall appears.

### 4. Timeline (JST)

| Time | Event |
|---|---|
| Oct 23 21:15 | Thankful paywall PR and TestFlight upload |
| Oct 24 02:45 | Thankful 1.0.2 submitted for review |
| Oct 24 04:3x | For Better Sleep 1.0.2 submitted |
| Oct 24 04:40 | Honne Translator AI 1.0.5 submitted (waiting for review) |
| Oct 24 06:29 | Thankful 1.0.2 approved |
| Oct 24 08:21 | For Better Sleep 1.0.2 approved |
| Oct 24 09:00 | Daily Dhamma 1.1.1 available on TestFlight (preparing submission) |

Submission to approval took about 3h45m for Thankful and about 4h for For Better Sleep.

### 5. All numbers (as of midday Oct 24)

| Item | Value |
|---|---|
| Apps with a rebuilt paywall | 4 |
| Approved and live | 2 (Thankful, For Better Sleep) |
| Waiting for review | 1 (Honne Translator AI) |
| Preparing submission | 1 (Daily Dhamma) |
| Apps with a price increase | 0 |
| Sales confirmed after the change | 0 so far |

### 6. What is not working

- Traffic is too small. For Better Sleep had one new user in 28 days. A better paywall does nothing if nobody sees it.
- We cannot measure the effect yet. From here we track paywall views, trial starts and purchases.
- On-device purchase testing is incomplete. For Better Sleep's sandbox purchase-to-restore check is still open.

### 7. What comes next

1. Measure. Track new user → trial start rate weekly. Target: at least the 10% industry median.
2. Traffic. Introduce the apps every day on X, TikTok, Instagram and free articles like this one. No ad spend.
3. Ship the other two. Wait for Honne Translator AI's review and submit Daily Dhamma.

We will publish the results in numbers again, whether the apps sell or not.

### The apps

- For Better Sleep (Sleep Reset): https://aniccaai.com/sleepreset?utm_source=substack&utm_medium=article&utm_campaign=fbs-102
- For Better Sleep on the App Store: https://apps.apple.com/app/id6762143790?pt=93486075&ct=substack_fbs-102&mt=8
- Thankful on the App Store: https://apps.apple.com/app/id6759514159?pt=93486075&ct=substack_thankful-102&mt=8

Original post with updates: https://aniccaai.com/blog/build-in-public-paywall-4apps-2026-10-24?utm_source=substack&utm_medium=article&utm_campaign=fbs-102

---

## X 引用ポスト案（@diceai0、1本）

`X-WRITING-STYLE.md` はリポジトリ・ホーム配下に見つからなかったため、`docs/team/launch/README.md` の勝ち筋表（実測の型）でチェックした。参謀側にファイルがあれば最終確認をそちらで。

引用元: claude-7 の X スレッド1本目（`docs/team/launch/x-thread-bip-paywall-20261024.md`、投稿済みならそのURL）。未投稿なら元記事URLを引用元の代わりに本文リンクにする。

本文:

```
課金画面を直して、価格は1円も上げずに2本が審査を通りました。

Thankful 1.0.2 → 朝6:29
For Better Sleep 1.0.2 → 朝8:21

ただし改修後の売上は、まだ0件です。
For Better Sleep は28日で新規1人。直す場所は課金画面より流入でした。

個人アプリの最初の100人、どこから来ましたか？
```

最初のリプライ（リンク）:

```
睡眠リセット（For Better Sleep）
https://aniccaai.com/sleepreset?utm_source=x&utm_medium=social&utm_campaign=fbs-102
Thankful
https://apps.apple.com/jp/app/id6759514159?pt=93486075&ct=x_thankful-102&mt=8
```

チェック（README の勝ち筋表）:

| 規則 | 結果 |
|---|---|
| 1行目は理由・結果（「公開しました」で始めない） | OK: 結果（2本通過・値上げなし） |
| 違いを1つ、価格に触れる | OK: 価格据え置き |
| 短い行、空行、ハッシュタグなし | OK |
| 具体的な質問で終える | OK: 最初の100人の流入元 |
| リンクは最初のリプライ | OK |
| 数字は出典どおり、盛らない | OK: 06:29 / 08:21 / 新規1人 / 売上0件 は元記事の値 |
| 画像 | 元記事「全数字まとめ」表のスクリーンショットを1枚（claude-7 スレッドと同じ） |
