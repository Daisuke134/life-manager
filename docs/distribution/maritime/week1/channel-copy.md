# Life Manager 初週の配布文案

状態: 未配布。Daisが家族・友人へDMする。公開投稿は稼働URLと実際の対応範囲を確認してから実行する。初期の獲得レーンは既存ブログのSEO記事と、既存Postiz接続済みXアカウント。Instagramは使わず、新規アカウントも作らない。無料pilotは既存のpaid Calendar trialとは別。全員の利益・将来の無料継続を保証しない。

## 配布の仕組み

参照: `docs/research/maritime/2026-10-20-source-map.md`。Todoistの有用な生産性記事＋実ユーザー事例＋一つの製品CTA、Ahrefsの検索意図別ガイド/調査、Levelsの公開build記事と短いX投稿を形式の参考にする。いずれもLife Managerの利用者獲得を証明するものではないので、まず一記事・一投稿で計測する。数値・顧客の言葉・保護されたコピーは転用しない。

## SEO記事（未作成）

- 配置先は既存`https://aniccaai.com/blog/manager`。本文と公開は既存Writer workflowを調べて再利用し、新CMSや別publisherを作らない。
- 読者の具体的な検索意図は既存の無料keyword/SERP資料で一つ選ぶ。根拠が足りなければ検索語は仮説と明記し、検索量を捏造しない。
- 記事の骨格: 具体的な問題 → AI assistantとManagerの違い → 現在ライブで動く実画面/receipt → 未対応・必要なprovider接続 → 無料pilotの一つのCTA。
- Product URL、実行証拠、メール登録から初回完了までの公開経路が揃うまで公開しない。売上・利益が出たという未検証の主張は書かない。
- 計測UTMは`utm_source=aniccaai&utm_medium=organic_search&utm_campaign=maritime-week1`。公開後はSearch Console等の既存readbackでimpressions/clicksを見て、funnelでverified signup/activation/completed work/returnにつなぐ。

## 公開前にDaisが送れる家族・友人向けDM

> 自分で仕事を見つけて進めて、何をしたか毎日メールで報告する「Life Manager」を作ってる。今、自分のPCで動く収益業務をCloudにつないでいて、Maritimeのコンペにも参加中。無料pilotを出すから、動く版が出たらリンク送るね。最初からお金が増える保証はないけど、実際に何を進めたかが分かる形にしてる。

これは事前案内。利用者数・売上・公開済みの証拠には数えない。

## 公開後の家族・友人向けDM

> Life Managerの無料pilotを出したよ。毎回指示しなくても、自分で仕事を選んで進めて、結果を毎日メールで知らせるManager。目標や予算を入力してから始める必要はなく、Telegramも不要。まずはメールで登録して試せるよ。
>
> 売上は保証していないし、販売先のアカウント接続が必要な部分はある。何を実行できて、何がまだ未接続かも報告する。
>
> 入口: 実URLを下記「URL確定」手順で差し込む。

公開前にこの版を送らない。Capafy未接続時に何が動くかは公開版の実装に合わせて一文追記する。

## X 日本語・公開前

> 自分で仕事を選び、進め、結果を毎日メールで報告するLife Managerを作っています。
>
> 自分のPCで動かしてきた収益業務を、今はCloudへ。目標・予算の入力を始める条件にせず、Telegramも必須にしません。
>
> Maritimeの競技に参加中。動く画面と、できたこと・未完の部分を公開していきます。

## X 日本語・公開後

> Life Managerの無料pilotを公開しました。
> メール登録→Managerが仕事を選ぶ→実行→日次メール。
> 目標・予算入力やTelegramは必須にしません。
> まずは商品づくりから。売上・利益は保証しません。
> 実画面demoと登録リンク👇

最終URLを添付する。「商品づくり」は実行確認した範囲に限定し、公開実績がなければ販売完了を示す画面を使わない。長い補足は返信へ分け、accountの長文投稿権限を前提にしない。

## X build-in-public（初期の一投稿案）

> Life ManagerのCloud版をMaritime向けに接続中。今週はメール登録から「仕事を選ぶ→実行→結果を確認→日次レポート」までを一つずつ通しています。
>
> 今日確認できたこと: [公開可能な実際の画面またはreceiptを一つ記載]
> まだできないこと: [未対応を一つ記載]
>
> 動くpilot: [稼働URL]

これはdraftで未投稿。確認できた一件だけを埋め、同じ文面を複数アカウントへ重複投稿しない。既存X accountをPostiz経由で使い、URLは`utm_source=x&utm_medium=social&utm_campaign=maritime-week1`を付ける。自動DMや新規アカウントは作らない。

## X English・公開後

> Life Manager chooses work, executes it, and emails daily results. No required goal/budget setup. Telegram is optional. Starting with product creation. Free pilot; revenue isn't guaranteed. Real demo + signup link below.

最終URLを添付する。利用可能な文字数へ収まることを投稿前に確認し、補足は返信へ分ける。

## URL確定

- 公開先はT22でreadbackしたRailway/既存domain originを使う。例のhostnameを公開しない。
- Daisの紹介: `${PUBLIC_ORIGIN}/maritime?source=referral&utm_source=friends&utm_medium=dm&utm_campaign=maritime-week1`
- X: `${PUBLIC_ORIGIN}/maritime?source=x&utm_source=x&utm_medium=social&utm_campaign=maritime-week1`
- Blog: `${PUBLIC_ORIGIN}/maritime?source=aniccaai&utm_source=aniccaai&utm_medium=organic_search&utm_campaign=maritime-week1`
- Community: `${PUBLIC_ORIGIN}/maritime?source=community&utm_source=community&utm_medium=community&utm_campaign=maritime-week1`
- `PUBLIC_ORIGIN`差込後にGETとCTAを確認し、完成版には変数・例示URL・未検証リンクを残さない。
- 氏名・email・紹介先の個人識別子をURLへ入れない。UTMの媒体名だけを残す。

## 短い返信テンプレ

- 「何もしなくていい？」→「毎日の指示や目標・予算入力は必須にしない設計。販売先の本人確認やアカウント接続は、そのサービスの条件次第で必要です。」
- 「稼げる？」→「作業結果と、公式に確認できた売上を分けて報告します。将来の売上や利益は保証しません。」
- 「Telegram必要？」→「不要。メールが基本で、Telegramは任意です。」
- 「無料？」→「このpilotの対象範囲は無料。外部サービスの費用や今後の料金は、利用前の表示を確認してください。勝手にpaid Calendar trialへ入れるものではありません。」
- 「やめたい」→「登録したアカウントの停止入口から停止できます。今後の実行と配信を止めるもので、外部サービスへ既に送信済みの情報が全て消える意味ではありません。」

## 計測

blog canonical URL / search query / X permalink → organic impressions or post clicks → visit → email verified → activated → work completed → return。Blog reader数、X impression/like、API signup、知人への送信だけを競技実利用にしない。source別に初回完了・再利用・利用者あたり費用を比較して、成果が確認できた配布だけを増やす。
