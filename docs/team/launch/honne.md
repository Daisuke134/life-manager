# Honne (本音翻訳AI) launch kit (1.0.5)

型は `docs/team/launch/thankful.md`（1.0.2）と同じ。共通ルールと勝ち組の根拠は `docs/team/launch/README.md`、文体は `~/team/head-of-content/X-WRITING-STYLE.md`（短く、一人称、具体的な数字、1投稿1つ、ダッシュ・ハッシュタグ・教訓の締めは使わない）。

- Status: 1.0.5（build 202610240347）は審査待ち。ASC `appStoreVersions` 1.0.5 = `WAITING_FOR_REVIEW`（2026-10-24 12:30 JST に確認）。Ready for Distribution になるまで予約しない。
- App Store (id 6759667221): 下の「リンク」を使う。`ct` は App Store Connect のキャンペーン計測用、`utm_*` は共通キー（Apple は `utm_*` を集計しないので、DL の帰属は `ct` で読む）。
- Approved claims only (`skills/earn/marketing-engine/registry/products/honne-ai.json`): analyzes pasted conversation text; suggests possible emotional context and a reply. 「本音が分かる」「心が読める」「当たる」とは書かない。
- 1.0.5 で変わったこと（事実）:
  - オンボーディングの後に課金画面を出し、閉じられなくした（購入か復元で先に進む）。年額を最初から選択（life-manager #8711）。
  - AI 分析の中継先を自分のサイトに移した。Rork の公開 toolkit は鍵なしで `POST /llm/object` が 403。aniccaai.com の Netlify 関数 `/api/honne/llm/object` を書き、OpenRouter の DeepSeek V4.1 Flash を呼ぶ。実測は1回あたり $0.00005〜$0.0002、推論トークンを切って 100〜150 トークン（anicca-products #623/#625）。最初は推論トークンが 800 中 461 を使って JSON が途中で切れていた。
  - 利用規約リンクを Apple 標準 EULA に直した（以前は相対 URL で何も開かなかった）（#8764）。
- Price (ASC subscription prices, read 2026-10-24): weekly ¥1,300 / $7.99, monthly ¥660 / $4.99, yearly ¥1,810 / $39.99。無料体験はない（導入オファーなし）。課金画面の初期選択は年額。
- Numbers (RevenueCat projcfa60dd8, 2026-10-23, `docs/team/specs/honne-paywall.md`): 28日 MRR $4・売上 $38・新規 24・トライアル 0。7月以降の新規 41 人のうち、7日以内の課金は 0 人。
- Images: ① 会話を貼った後の結果画面（本音／心理状態／返信案）、② 相手との関係を選ぶ画面、③ 価格を書く投稿だけ課金画面。
- Post time: 夜 JST。

## リンク

`<cc>` = `jp`（日本語投稿）/ `us`（英語投稿）。`<channel>` = `x`, `bluesky`, `mastodon` など。

```
https://apps.apple.com/<cc>/app/id6759667221?pt=93486075&ct=<channel>-honne-105&mt=8&utm_source=<channel>&utm_campaign=honne-105
```

## JA 1 — 実話（中継を作った）

```
本音翻訳AIの更新を作っていたら、使っていたAIの中継が鍵なしで403を返すようになっていた。

自分のサイトに中継を1本書いた。
1回の分析で約0.0001ドル。

最初は推論に800トークン中461を使われて、返事が途中で切れていた。推論を切ったら直った。
```

## JA 2 — 課金画面（数字）

```
本音翻訳AI、7月から新しく入った41人のうち、7日以内に課金したのは0人だった。

課金画面が×で閉じられたから。

1.0.5から、最初の説明の後に出す課金画面は閉じられない。
週1,300円か年1,810円。
```

## JA 3 — yokoichi777 shape

```
「別にいいよ、好きにすれば」

この一言、どう返すか迷ったことありますか。

『本音翻訳AI』は、会話を貼って相手との関係を選ぶと、考えられる気持ちと返信の案を出すiPhoneアプリです。

祝個人開発
詳細はツリーに
```

## EN 1 — real event

```
Shipping an update to my Japanese iPhone app. The AI relay it used started returning 403 without a key.

Wrote my own relay on my site instead.
About $0.0001 per analysis.

First version cut its JSON in half. Reasoning was eating 461 of 800 tokens. Turned reasoning off, fixed.
```

## EN 2 — paywall numbers

```
41 new users since July. 0 paid within 7 days.

The paywall had a close button.

1.0.5 shows it after onboarding and you can't skip it. $7.99 a week or $39.99 a year.
```

## 2件目（すべての投稿）

```
App Store: <上の「リンク」で cc と channel を埋めたURL>
```

## Schedule (Postiz)

Ready for Distribution の後に入れる。Thankful 1.0.2 と同じく Postiz public API `POST /public/v1/posts`（`type: schedule`）、integration `cmm6d7m5703rwpr0yr5vtme3w`（X @aniccaxxx）、各投稿は2件のスレッド（1件目が本文＋画像、2件目がリンク）。Bluesky / Mastodon は Postiz に連携がないので、Thankful と同じく今回は予約しない。

| postId | 予約 (JST) | 本文 | readback |
|---|---|---|---|
| （未予約） | | | |

## ASO keyword candidates

Current (ja): `本音,翻訳,AI,LINE,人間関係,感情,心理,コミュニケーション,恋愛,分析`
Current (en): `ai,translate,true intent,relationship,line,chat,psychology,emotion,communicate,hidden`

Observed in the JP App Store for 「本音」 (iTunes Search API, 2026-10-24): the top results are anonymous-SNS apps (愚痴バブル 11,572 ratings, GRAVITY 72,440, ilka 3,567, 焚き火チャット 16,117). The word 本音 alone pulls a different intent.

Candidates to test (verify search popularity in App Store Connect before changing; do not touch a version in review):
- ja: `返信,既読,脈あり,LINE返信,気持ち,彼氏,彼女,上司,恋愛相談,メッセージ分析` (situational words a reader of "what did they mean" types)
- en: `reply,text,message,meaning,decode,boyfriend,girlfriend,dating,advice,read` (drop `true intent` and `hidden`; they overpromise against the approved claims)
