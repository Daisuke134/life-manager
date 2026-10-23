# Honne (本音翻訳AI) launch kit

- App Store: `https://apps.apple.com/jp/app/id6759667221` → post with `<APP_STORE_URL>` (campaign link, `ct=honne-launch-x-<n>`)
- Version in review: 1.0.5 (build 202610240347), submitted 2026-10-24 04:40 JST.
- Approved claims only: analyzes pasted conversation text; suggests possible emotional context and a reply. Do not say it "reads minds", "reveals the truth" or is accurate.
- Price: weekly and annual subscription; the app requires a subscription after onboarding (hard paywall since 1.0.5). RevenueCat 2026-10-23 lists ¥1,300/week and ¥1,810/year; confirm in App Store Connect before quoting.
- Images (attach 1–4, photo beats video in the study): ① a pasted message → result screen (本音 / 心理状態 / 返信案), ② the relationship picker, ③ the plan screen only if the post states the price.

## EN 1 — story opener

```
I kept rereading one text from a friend for an hour.

"It's fine, do whatever you want."

So I built an iPhone app for that moment.

Paste the conversation, pick who it's from, and it suggests what they might be feeling and a reply you could send.

What message would you paste first?
```

## EN 2 — one difference

```
Most AI chat apps answer you.

This one looks at the message someone sent you.

Paste the text, choose the relationship (partner, boss, parent, friend), and get a possible emotional read plus a reply draft.

Honne is on the App Store. Link below.

Which relationship is hardest to read for you?
```

## EN 3 — result / build-in-public

```
Shipped a new version of my iPhone app today.

It reads a pasted conversation and suggests the emotion behind it and a reply.

This week I rebuilt the plan screen so prices come straight from the App Store, and moved the AI to my own server.

Link in the reply. What would make you trust a tool like this?
```

## JP — yokoichi777 shape

```
「別にいいよ、好きにすれば」

この一言の裏にある気持ち、気になったことはありませんか。

『本音翻訳AI』を作りました。
会話を貼って相手との関係を選ぶと、考えられる気持ちと返信の案を出してくれるiPhoneアプリです。

<BUILD_MONTHS>ヶ月かけて作りました（不明なら行ごと削除）

祝個人開発
詳細はツリーに
```

## First reply (all posts)

```
App Store: <APP_STORE_URL>
```
JP: `App Storeはこちら → <APP_STORE_URL>`

## ASO keyword candidates

Current (ja): `本音,翻訳,AI,LINE,人間関係,感情,心理,コミュニケーション,恋愛,分析`
Current (en): `ai,translate,true intent,relationship,line,chat,psychology,emotion,communicate,hidden`

Observed in the JP App Store for 「本音」 (iTunes Search API, 2026-10-24): the top results are anonymous-SNS apps (愚痴バブル 11,572 ratings, GRAVITY 72,440, ilka 3,567, 焚き火チャット 16,117). The word 本音 alone pulls a different intent.

Candidates to test (verify search popularity in App Store Connect before changing; do not touch a version in review):
- ja: `返信,既読,脈あり,LINE返信,気持ち,彼氏,彼女,上司,恋愛相談,メッセージ分析` (situational words a reader of "what did they mean" types)
- en: `reply,text,message,meaning,decode,boyfriend,girlfriend,dating,advice,read` (drop `true intent` and `hidden`; they overpromise against the approved claims)
