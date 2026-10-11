# Aniccaai.com — Managerのgreenfield rebrand

2026-10-08。掲載原稿とsource差分の設計。サイト実装・公開は未実施。旧body/mind/money agentの紹介を、Managerのmission・仕組み・証拠へ置き換える。順序と状態は [統合SSOT](2026-09-25-life-manager-unified-ssot.md#manager-20261011)。

## 英語の掲載原稿

**Manager**

**One entity, blessing for all.**

### AI for world engineering.

We are building an ambient AI entity that models the world, discovers high-leverage changes to its environment, acts on them, and learns from what happens next.

The goal: improve the conditions of life—physical health, mental wellbeing, and financial security—so people and other living beings can thrive without having to use an app.

Links: **Read the architecture** / **See the evaluation plan** / **Explore the research**

Status: **Early development. Real-world outcomes have not yet been demonstrated.**

### Change the systems that shape everyday life.

Supply, prices, access, shared resources, and the networks around us affect health, income, time, and opportunity. Manager is being designed to improve those conditions directly. Beneficiaries do not need an account, login, or personal credentials.

### Model. Compare. Act. Measure. Learn.

Build a partial model from evidence. Compare structural changes against a baseline. Apply a change through an authorized connection to the environment. Verify what changed. Measure outcomes and update the model.

### Transparent action. Measurable outcomes.

Every claimed improvement should be traceable: what Manager predicted, what it changed, what was measured, and who benefited or was harmed. We will publish reproducible simulations, assumptions, costs, failures, and measured outcomes as they become available. Predicted effects, applied changes, and verified improvements will be reported separately.

### Research foundations.

Our research spans behavioral simulation, agent-based modeling, causal evaluation, collective intelligence, and real-world experimentation. We are studying work from Aaru, Simile, Concordia, AgentSociety, AI Economist, MiroFish, and Woven City. These references do not imply affiliation or endorsement.

Footer: **Manager by Anicca** / Architecture / Research / Benchmarks / Contact / Privacy / Terms.

## 日本語の掲載原稿

**Manager**

**ひとつの存在、すべてに恩恵を。**

### AIで、世界の環境を設計し直す。

世界のモデルを作り、環境への効果の大きい変更を見つけ、実行し、結果として起きた現実から学ぶ。そんな一つのAI主体を、私たちは開発しています。

目指すのは、身体・精神・経済の健康を支え、人々や他の生命が、アプリを使わなくても豊かに生きられる環境です。

リンク: **仕組みを読む** / **評価計画を見る** / **研究を読む**

状態: **開発初期。現実の生活改善は、まだ実証していません。**

### 暮らしを決める仕組みを変える。

供給、価格、アクセス、共有資源、周囲のネットワークは、健康・所得・時間・機会を左右します。Managerは、こうした条件を直接改善する存在として設計しています。受益者のアカウント、ログイン、個人の認証情報を必要としません。

### モデル化。比較。実行。測定。学習。

証拠から世界の部分モデルを作る。構造的な変更を現状と比較する。変更する権限がある環境へ接続し、実行する。何が変わったかを確かめ、生活の結果を測り、モデルを更新する。

### 成果は、証拠とともに。

再現可能なsimulation、仮定、費用、失敗、実測結果を、得られた段階で公開します。予測した効果、適用された変更、確認できた改善を区別して報告します。

## デモ・benchmarkページ

`/manager/demo` は開発状況と研究用demo artifactを公開。閲覧者の操作が現実の作用を発生させない。受益者向け操作UIではない。

`/manager/benchmarks` は `not_run / simulation / calibrated / shadow / field` のmode、source/model版、manifest、比較対象、全費用、失敗、不確実性、集団別結果を表示。初期はnot_run。結果が無いときゼロ・成功に補完しない。

`/manager/research` は会社・論文・repo・原SHA・学んだもの・限界を表示。第三者の精度をManagerの精度にしない。

## 実際に更新するsource

公開HTTPの/enと/jaは2026-10-08時点でも旧Life Manager copy。旧sourceを読み取り、baseline `Daisuke134/anicca-products@da2e99002a6494c6589db33adbed95f0521de0c8` を確認した。これはGitHub source SHAであり、Netlify公開SHAとの対応は未確認。

実在path: `apps/landing/app/page.tsx` は/enへredirect。`app/en/page.tsx` と `app/ja/page.tsx` はNavbar/Hero/Fellows/ManifestoStrip/Footer/SelfImproveLoop/DemoVideo/VisionBandをimport。root/en/ja layoutにも旧metadataがある。heroのみの置換では古い説明が残る。

新copyはcanonical `life-manager` repo内で実装。en/ja page、root/en/ja metadata、専用 `components/manager/` を所有し、既存Navbar/Footer等への影響を確認する。現在canonicalにはfull build sourceがないため、旧固定baselineをread-only入力とする限定overlay又は正本移行を先に確定する。無関係routeと旧paid callbacksを保存する。

旧packageのbuildは `npm run build`、prebuildはfont import確認とdashboard snapshot生成。Next設定はstatic exportだがtype/lint errorsを無視する設定があるため、buildだけで型の検証完了としない。固定baselineのtsconfig/dependenciesでfocused typecheckとroute checksも行う。新dependency追加は必要性確認後。

Netlify management identityは現在のcloudには未設定。公開元site/domain/SHA/build設定の公式readbackが未実施。本番公開したという主張はしない。既存hostingを保持し、previewの別domainで更新完了にしない。

metadata英語: `Manager — One entity, blessing for all.`。日本語: `Manager — ひとつの存在、すべてに恩恵を。`。Aniccaは発行主体として残し、legal identityをManagerへ書き換えない。英日canonical/hreflang、OG、JSON-LD、sitemapも同じ説明へ。

## 2026-10-10の公開構成更新

ブランドはManager、説明はAI for world engineering。Godは創業者の比喩にとどめ、heroで全知・万能を性能として宣伝しない。ページはmission→構造変更の例→閉ループarchitecture→4評価track→evidence→研究記事とfounder背景の順。受益者signup導線は設けない。研究/企業contactと公開evidenceは残す。

/benchmarksではprediction/policy/execution/outcomeの別カード、not_run状態、protocol、manifest、baseline、uncertainty、費用、群別影響を掲載。/researchでは研究記事の出典と実装stage。/aboutでは確認できた研究/実務経歴だけを掲載し、ICLR参加をaccepted paperと書かない。新Managerの顧客・売上・健康改善を創作しない。Life Manager収益は確認できた場合に別scopeで説明する。

この更新は原稿・構成の変更。本番Aniccaai.comの更新ではない。source/build/deploymentの残作業は統合SSOT D6。

## 2026-10-11の研究と会社ストーリー

研究sectionは三者を同じLLM人格simulationと扱わず、Aaruのjoint population/非LLM中核、Simileのhuman-grounded trained behavior/confidence、AI Economistの制度plannerと住民適応を説明する。記事6原稿とtalkの公開先はD6/N3で決め、未公開routeをliveリンクにしない。

会社の説明案: **Life Manager builds and operates businesses to create wealth. Manager extends this work to the shared conditions of life: modeling behavior, redesigning environments, and measuring outcomes for people who never use an app.** これは方向性の説明。現在の売上は確認された期間/主体/数値、Manager benchmarkは実run後の範囲だけ載せる。受益者にログイン不要、作用と根拠は公開できる形にする。
