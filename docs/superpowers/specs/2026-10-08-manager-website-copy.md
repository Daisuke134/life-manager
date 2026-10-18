# Aniccaai.com — Manager for the universe

2026年10月12日の原稿。[現行の構想](2026-10-12-manager-universe-design.md)に従い、宇宙とすべての生命を最上段で紹介する。過去原稿は変更履歴に保存する。会社はアニッチャ、製品はマネージャー。公式サイトには未反映。

## English

**Manager**

**A Manager for the universe.**

**One entity, blessing for all.**

We are building Manager: one AI entity with the ambition to improve the conditions of life for all living beings, across the universe.

The universe deserves a better manager. Our ambition is to build an entity that understands the world, discovers changes to its environment, acts on them, and learns from the reality that follows. The horizon is every living being—not a single user, species, or planet.

We begin by building the capabilities that this ambition requires: models grounded in evidence, decisions that account for different populations, and actions whose consequences can be measured.

## 日本語

**マネージャー**

**宇宙のためのマネージャー。**

**ひとつの存在、すべてに恩恵を。**

宇宙全体のすべての生命が豊かに生きられるように、環境を改善し続ける一つの人工知能「マネージャー」を開発しています。

宇宙には、もっとよいマネージャーが必要だ。世界を理解し、環境への変更を見つけ、実行し、その後に起きた現実から学ぶ存在をつくる。私たちの構想は、一人の利用者、一つの種、一つの惑星にとどまりません。

その構想へ進むために、証拠に基づくモデル、集団ごとの影響を考える判断、結果を測定できる行動の仕組みを、一つずつ作っています。

## ページの構成

ビジョン、観測・モデル化・比較・実行・学習の循環、成果の検証、各社と分野全体の解説、標語の順に構成する。資料確認、実装計画、設計、未測定という現在の状態を明示する。受益者の登録やログインは設けない。最初の人口評価と製品全体の構想を区別し、他社の精度や売上を自社の実績として書かない。

設計ファイル：[英語](../../design/manager-universe-preview/en.html) / [日本語](../../design/manager-universe-preview/ja.html)。配布版は装飾と図を内蔵し、研究記事とともに圧縮ファイルで提供する。

## 本番で更新するファイル

公開HTTPの/enと/jaは2026-10-08時点でも旧Life Manager copy。旧sourceを読み取り、baseline `Daisuke134/anicca-products@da2e99002a6494c6589db33adbed95f0521de0c8` を確認した。これはGitHub source SHAであり、Netlify公開SHAとの対応は未確認。

実在path: `apps/landing/app/page.tsx` は/enへredirect。`app/en/page.tsx` と `app/ja/page.tsx` はNavbar/Hero/Fellows/ManifestoStrip/Footer/SelfImproveLoop/DemoVideo/VisionBandをimport。root/en/ja layoutにも旧metadataがある。heroのみの置換では古い説明が残る。

新copyはcanonical `life-manager` repo内で実装。en/ja page、root/en/ja metadata、専用 `components/manager/` を所有し、既存Navbar/Footer等への影響を確認する。現在canonicalにはfull build sourceがないため、旧固定baselineをread-only入力とする限定overlay又は正本移行を先に確定する。無関係routeと旧paid callbacksを保存する。

旧packageのbuildは `npm run build`、prebuildはfont import確認とdashboard snapshot生成。Next設定はstatic exportだがtype/lint errorsを無視する設定があるため、buildだけで型の検証完了としない。固定baselineのtsconfig/dependenciesでfocused typecheckとroute checksも行う。新dependency追加は必要性確認後。

Netlify management identityは現在のcloudには未設定。公開元site/domain/SHA/build設定の公式readbackが未実施。本番公開したという主張はしない。既存hostingを保持し、previewの別domainで更新完了にしない。

metadata英語: `Manager — One entity, blessing for all.`。日本語: `マネージャー｜ひとつの存在、すべてに恩恵を。`。Aniccaは発行主体として残し、legal identityをManagerへ書き換えない。英日canonical/hreflang、OG、JSON-LD、sitemapも同じ説明へ。


## 2026-10-18 創業者の問いを伝える追加セクション案

製品の紹介に続き、「なぜつくるのか」で背景を説明する草稿。最新の使命は苦しみの終焉であり、一般的な生活改善だけへ縮小しない。全生命・宇宙の構想を維持する。以下は本文案で、本番反映は未実施。

### 日本語

問いは、ずっと同じです。

自分の苦しみをどうすれば終わらせられるか。16歳の頃に出会ったヴィパッサナーが、出発点でした。大学院では、脳活動や瞳孔のデータを使う個人向けのデコーダと神経フィードバックのアプローチを研究しました。今は、人口と社会をモデル化し、人々が生きる環境へ働きかけるマネージャーを開発しています。

手段は変わってきました。テクノロジーで、この世界の苦しみをどうすれば終わらせられるか。その問いを、すべての生命を視野に追い続けます。

### English

The question has stayed the same.

How can I end my suffering? Vipassana, which I encountered at around sixteen, was my starting point. In graduate school, I worked on personalized decoding using brain and pupil data and explored neurofeedback. Today, I am building Manager to model populations and society and act on the environments in which people live.

The approach has changed. The question remains: how can technology end suffering in the world? We pursue it with every living being in view.

詳しい物語と実証上の区別：`../../research/manager/2026-10-18-founder-story-and-mission.md`。会社名と製品名の区別は従来どおり。
