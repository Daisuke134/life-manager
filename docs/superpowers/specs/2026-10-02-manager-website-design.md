# Aniccaai.com — Managerへの全面更新仕様

2026-10-02 UTC。状態: **レビュー用。公開サイトはまだ更新していない。**

本体の [Manager設計](2026-10-02-manager-design.md) と合わせて読む。作業順・状態は [統合SSOT](2026-09-25-life-manager-unified-ssot.md#manager-20261002) だけで管理する。

## 1. 誰が、何を理解するサイトか

訪問者は、Managerに関心を持つ人、研究者、施設・インフラ運営者、投資家。最初の画面で「何をする存在か」「なぜ自分がアプリを使う必要がないのか」「どこまで実証されているか」を理解できる。

名称はManager。Aniccaは既存ドメインと発行主体の表記として残す。法律上の会社名変更やドメイン名変更を今回のブランド更新と混同しない。

サイトは説明・研究・評価の公開場所。signup、login、個人プロフィール、Calendar接続、メール登録、Telegram、waitlist、個人用dashboardを新しいManager導線に置かない。

## 2. 公開ページとルート

| URL | 新しい役割 |
|---|---|
| `/` | 現在と同様に`/en`へ。Managerのmetadataへ統一 |
| `/en` | Managerの英語トップ。概念・ループ・研究状態・証拠へのリンク |
| `/ja` | 同じ内容の日本語トップ。日本語を英語の短縮版にしない |
| `/lm` | Managerの旧名URLとして`/en`へredirect。旧オンボーディング実装は別のlegacy URLへ退避して既存利用者の継続動作を確認 |
| `/manager/benchmarks` | 公開評価。英日切替でprotocol・実行状態・artifactを読む |
| `/manager/research` | 出典付き研究整理。英日切替。企業・研究者・OSSの区別と限界 |

既存`/research`には別の研究コンテンツがあるため、上書きせず新しいnamespaceを使う。旧商品、決済、プライバシー、規約、support、既存backend endpointsは別の運用契約を持つ。今回のManager新規導線の変更を理由にそれらを削除しない。

`/lm`のredirectはlegacy onboardingの新URLと既存callbackの動作を検証してから行う。実装段階で既存checkoutや既存ユーザーリンクが`/lm`を必要とする場合、最初のreleaseでは`/lm`にManager説明と既存利用者向け継続リンクを置き、backend依存解消後にredirectへ進む。**Managerの新規consumer signupは表示しない。**この互換性判断はrelease前の実際の依存検査で決め、検査結果をSSOTへ記録する。

## 3. 英語トップ — 掲載原稿

### 最初の画面

**Manager**

**One entity, blessing for all.**

Manager builds a model of the world, discovers the highest-leverage changes to its environment, acts on them, and learns from the resulting reality.

Its aim is to improve the conditions of life without requiring people to use an app, create an account, or hand over personal credentials.

**Research and development. Environmental impact has not yet been demonstrated.**

読むためのリンク: **Read the benchmark protocol** / **Explore the research**。

### 環境を変える

**Better conditions. Better lives.**

The environment shapes what is easy, costly, available, and possible. Manager is being designed to improve those conditions: the systems around people, animals, and other living beings.

The long-term aim is healthier lives, greater material security, and more room to thrive. Each claim will need its own evidence.

### 継続するループ

**Observe → Model → Compare → Act → Measure → Learn**

- **Observe:** Gather permitted observations and record their source and freshness.
- **Model:** Estimate the state of an environment, including what remains uncertain.
- **Compare:** Test possible changes against a baseline, constraints, and costs.
- **Act:** Apply a change within the authority granted for that environment.
- **Measure:** Check what changed in reality and who or what was affected.
- **Learn:** Update the model and policy from measured outcomes.

A model is a partial picture of the world. Predictions and simulated outcomes are kept separate from real observations.

### 変える環境と評価

**Change the conditions of everyday life.**

Manager explores changes to supply, prices, access, shared resources, and the systems that shape income, health, time, and opportunity. People benefit through the environment around them, without signing up or operating an app.

We will compare structural changes in simulations and then in real systems where changes can be authorized and outcomes measured. The first real-world domain has not been selected. No measured improvement in income or health is claimed today.

### 何を信頼すればよいか

**Evidence for every claim.**

We will publish the method, comparison baseline, constraints, costs, results, and failures. Simulation results will be labeled as simulation results. A proposed action, an applied action, and a measured improvement are different things.

### 研究の位置づけ

**Learning from work on environments, simulation, and collective intelligence.**

Our research draws on Aaru, Simile, Concordia, AgentSociety, MiroFish, Woven City, and work by B. F. Skinner, Michael Levin, Joon Sung Park, and David Krakauer.

These references inform the design. They do not imply partnership, endorsement, or proof that Manager can improve every environment.

### 最後の一文

**Manager continuously redesigns the world so living beings can thrive without anyone having to use it.**

This is the vision. The benchmark is how we begin testing it.

Footer: **Manager by Anicca** / Research / Benchmarks / Source / Privacy / Terms / existing support。メールフォームや購読導線は追加しない。

## 4. 日本語トップ — 掲載原稿

### 最初の画面

**Manager**

**ひとつの存在、すべてに恩恵を。**

Managerは世界のモデルを構築し、環境に対する最も効果の大きい変更を見つけ、実行し、その結果として起きた現実から学ぶ。

人がアプリを使ったり、アカウントを作ったり、個人の認証情報を渡したりしなくても、暮らしの条件をよくすることを目指しています。

**研究・開発段階です。環境改善の効果は、まだ実証していません。**

読むためのリンク: **評価方法を読む** / **研究と出典を見る**。

### 環境を変える

**よい環境が、よい暮らしを支える。**

何が簡単で、何に費用がかかり、何が手に入り、何が可能か。環境は、その条件をつくっています。Managerは、人・動物・その他の生命を取り巻く仕組みを改善するために設計しています。

より健康で、暮らしに余裕があり、生命が豊かに生きられる世界へ。それぞれの改善は、個別に測定し、確かめます。

### 継続するループ

**観測 → モデル化 → 比較 → 実行 → 測定 → 学習**

- **観測:** 許可された情報を集め、出典と鮮度を記録する。
- **モデル化:** 環境の状態を推定し、わからないことも残す。
- **比較:** 変更候補を、今の方法・制約・費用と比較する。
- **実行:** その環境で認められた範囲の変更を行う。
- **測定:** 現実に何が変わり、誰や何に影響したかを確かめる。
- **学習:** 測定した結果から、モデルと行動方針を更新する。

モデルは世界の一部を表すものです。予測やシミュレーションの結果を、現実の観測と区別して扱います。

### 変える環境と評価

**日々の暮らしを決める条件を変える。**

供給、価格、利用のしやすさ、共有資源、所得・健康・時間・機会を左右する仕組みを改善します。人々は登録したりアプリを操作したりすることなく、周囲の環境を通じて恩恵を受けます。

構造的な変更をシミュレーションで比較し、変更する権限と結果を測る方法がある実環境で検証します。最初の実環境は未確定です。現時点で所得や健康の改善を実証したという主張はしていません。

### 何を信頼すればよいか

**主張には、証拠を。**

評価方法、比較対象、制約、費用、結果、失敗を公開します。シミュレーションの結果には、そのことを明記します。変更を提案したこと、変更が適用されたこと、改善を実測したことは、それぞれ違います。

### 研究の位置づけ

**環境、シミュレーション、集団の知性を研究する。**

Aaru、Simile、Concordia、AgentSociety、MiroFish、Woven City、そしてB. F. Skinner、Michael Levin、Joon Sung Park、David Krakauerらの研究を参考にしています。

これらは設計の参考資料です。提携や推薦、Managerがあらゆる環境を改善できるという証明を意味しません。

### 最後の一文

**Managerは、人が使わなくてもあらゆる生命が豊かに生きられるよう、世界の環境を継続的に設計し直すことを目指す。**

これはビジョンです。その実証を始める方法が、ベンチマークです。

Footer: **Manager by Anicca** / 研究 / 評価 / ソース / プライバシー / 利用規約 / 既存support。

## 5. ベンチマークページの表示契約

初期表示は **Not run / 未実行**。protocol、比較対象、合格基準を読めるが、スコア・改善率・実施施設・受益者数は表示しない。

公開artifactは次を持つ: `benchmark_id`, `protocol_version`, `source_sha`, `mode`, `status`, `generated_at`, `case`, `scenario`, `baseline`, `metrics`, `cost`, `failures`, `artifact_hash`, `reproduction_url`。

- `planned`: 未実行。数値なし。
- `simulation_completed`: シミュレーション結果。simulator版と条件を必須表示。
- `field_completed`: 許可された現場試験。比較方法と測定範囲を必須表示。
- `failed` / `incomplete`: 失敗や欠損をそのまま表示。

JSON欠損・parse failure・artifact不在時は「結果を取得できません」と表示する。ゼロ、成功、liveへ変換しない。古いartifactは日付を表示し、新しい測定のように見せない。研究を読むだけの人にアカウントを要求しない。

proof未取得の「24/7 world awareness」「AGI achieved」「makes everyone rich」「self-funded」「全世界の状態を把握」を掲載しない。第三者の精度や旧loopの売上をManager benchmarkのスコアに転用しない。

## 6. 研究ページの表示契約

企業、研究者、OSSを区別し、一次URL・発表日または版・何を検証したか・限界を記載する。AaruとSimileの比較値は評価セットが違うことを明記する。Parkの1,000人研究は今回確認した2026改訂v3と初期版の値を混ぜない。

READMEだけを読んだ項目、原論文を読んだ項目、アクセスできなかった項目を分ける。Generative Agentsの原repoは今回404であり、現在のライセンスやSHAを作らない。外部研究者への連絡実績や返答を、存在しない状態で載せない。

## 7. 見た目と読みやすさ

- 視覚方針: 静かで明快な研究組織のサイト。一つのManagerから環境への作用とfeedbackがつながる簡潔な図を使う。
- 色: deep navy、白、cobaltのアクセント。成功を偽装する点滅や緑のlive indicatorは使わない。
- 最初の画面: 名称、motto、仕組みの一文、研究段階、評価へのリンク。文字を巨大化して説明が画面外へ追い出されないようにする。
- 本文16px以上、line-height 1.6以上を目安。日本語は折り返しと行間を別途確認する。
- 360 / 390 / 768 / 1440px、200%文字拡大、keyboard navigationで読む。
- animationは補助。`prefers-reduced-motion`に従い、文章はJavaScriptやanimation完了なしでも読める。
- 既存faviconとsocial preview画像は保持。新しいsocial cardや追跡pixelは今回追加しない。
- 参照リンクのラベルで遷移先がわかるようにする。外部リンクは適切なrel属性を持つ。

## 8. metadata・公開コピーの一貫性

root、英日layout、英日page、JSON-LD、OG/Xのtitle / description、sitemapを更新する。既存social画像がある場合は画像を保持し、タイトルだけ旧Life Managerのままにしない。

英語title: **Manager — One Entity, Blessing for All**。
日本語title: **Manager — ひとつの存在、すべてに恩恵を。**

descriptionは冒頭の仕組みと研究段階に整合する。Organizationのlegal identityをManagerへ偽装しない。WebSite / WebPageの名前にManagerを使い、発行主体はAniccaの既存表記を維持する。localeのcanonicalとhreflangを揃える。

## 9. ソースと公開経路

現在、接続Sitesに該当サイトはない。既存ソースはNext.js / Netlifyのサイトであり、Sitesへの移行や別ドメインの新規公開を前提にしない。既存Netlifyを維持する。

正本repoのAGENTS.mdは、Life Manager関連ソースを`Daisuke134/life-manager`に置くよう指定。旧`anicca-products/apps/landing`の全サイトには他商品のルートもある。次の境界で移す。

1. 読取専用で旧サイトの公開元SHA、Netlify siteとdomainの対応、build base、build command、deploy contextを確認する。
2. Managerに必要なtop /en /ja、関連component、metadata、package/build設定を正本の`apps/landing`へ移す。既存`/lm`と関数を維持し、別実装を増やさない。
3. 共有サイトの移行中は、旧サイトの固定SHAを**変更しないbuild入力**として使い、正本のManagerファイルを明示的allowlistで重ねて既存のNetlify deploy packageを作る。この一時方式には固定baseline、overlay manifest、artifact hashを記録する。旧repoに修正を入れない。
4. overlayではManager所有ルート・componentsだけを置換。無関係のpaid content、functions、private data、外部認証値は移さない。取得不能なprivate資産がある場合は削除せず、そのreleaseを止める。
5. 既存サイト側の別担当変更があればbaselineを再取得し、差分をレビューしてからpackageを作る。古い固定snapshotで新しい既存商品変更を巻き戻さない。
6. 完全な正本移行は別工程。overlayを新しい恒久的ソース正本と呼ばず、終了条件と所有者をSSOTへ記録する。

このsessionのcloud runtimeにはNetlifyの認証・外部identityが設定されていない。現在は公開サイトのHTTP確認とGitHubのreadができる状態。管理APIでのdeploy source確認・本番公開が可能とはまだ言えない。資格情報の中身を出力せず、既存の許可された接続を使用する。新しいログインや秘密の共有を無条件に要求しない。

## 10. 検証と公開の受入条件

- 英日ページが上記の内容を伝え、研究段階が読める。
- Manager所有の公開導線にsignup / login / Calendar / Telegram / メール登録 / $29 subscription CTAがない。
- URL・metadata・JSON-LDで名称と説明が一致する。
- benchmarkが未実行の間は、実績値・beneficiary count・live stateを表示しない。
- artifactの欠損、失敗、古さ、simulationとfieldの区別を確認する。
- 既存のprivacy / terms / support、旧有料商品と必要なcallbackが壊れていない。
- build成功、関連contract tests、legacy route smoke check、responsive / keyboard / reduced-motion確認。
- 本番公開後、`/`, `/en`, `/ja`, `/lm`, `/manager/benchmarks`, `/manager/research`の実際の内容・status・metadata・リンクをreadbackする。deploy成功だけで完了にしない。
- 直前のdeployへのrollbackを可能にする。変更したsource SHAと公開されたartifactの対応を記録する。

詳細なmigration順は統合SSOTのW0–W2へ記載した。公開元sourceの固定後に、実在するsite pathとbuild commandを確定する。サイト説明の更新は、Managerの環境改善実装の完了とは別に評価する。
