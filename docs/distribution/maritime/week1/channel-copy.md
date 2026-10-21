# Life Manager 初週の配布文案

状態: 未配布。Daisが家族・友人へDMする。初期の獲得レーンは既存ブログのSEO記事と、本人・接続先を確認した既存の広いXアカウント。2026-10-21 06:02ZのPostiz readbackはgroups=0 / integrations=0、postsは05:20Z時点で0のため、このconnectorではX連携先を確認できていない。Instagramは使わず、新規アカウントも作らない。無料pilotは既存のpaid Calendar trialとは別。全員の利益・将来の無料継続を保証しない。

## 配布の仕組み

参照: `docs/research/maritime/2026-10-20-source-map.md`。Todoistの有用な生産性記事＋実ユーザー事例＋一つの製品CTA、Ahrefsの検索意図別ガイド/調査、Levelsの公開build記事と短いX投稿を形式の参考にする。いずれもLife Managerの利用者獲得を証明するものではないので、まず一記事・一投稿で計測する。数値・顧客の言葉・保護されたコピーは転用しない。

## SEO記事（内部草稿あり・未公開）

- 配置先は既存`https://aniccaai.com/blog/manager`。canonical sourceはLife Manager repo、公開は`Daisuke134/anicca-products`の既存Manager article bridge。新CMSや別publisherは作らず、Writerの複数destination publish matrixも起動しない。
- 記事テーマは **“AI Assistant vs AI Agent: Who Chooses the Next Task?”**。比較意図のSERPを見た編集仮説で、検索量は未測定。2026-10-18までの28日間のサイト全体GSCは0 clicks / 7 impressionsであり、この記事の需要や性能を示す数字ではない。基準値と欠測条件は`docs/evidence/maritime/seo-baseline-20261021.json`。
- 内部草稿: `docs/distribution/maritime/week1/seo-article-draft-en.md`。AI assistant / agent の定義差を説明し、Life Managerの「次の仕事を選び、実行し、結果を確かめて報告するmanager」は当社の製品設計上の表現だと明記する。
- 公開CTAは保留。実際のメール確認→明示consent→仕事完了→成果/receipt→日報→停止の一連readbackを終えるまで、登録を「今すぐ試せる完成品」と表現しない。現在の製品範囲、未対応・必要なprovider接続を記事と一致させ、売上・利益の未検証claimは書かない。
- Todoistの役立つ記事と一つのCTA、Ahrefsの検索意図別ガイド、Levelsのbuild decisionを記事へ展開する仕組みを参考にする。成果数字は転用しない。詳細と適用限界は`docs/research/maritime/2026-10-20-source-map.md`。
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

## X build-in-public（確認済み状況を反映した未投稿draft）

> Life ManagerのCloud版をMaritime向けに接続中。今週はメール登録から「仕事を選ぶ→実行→結果を確認→日次レポート」までを一つずつ通しています。
>
> 今日確認できたこと: pilot登録ページがHTTP 200で表示され、workerにMaritimeのprovision / cycle / report capabilityが読み込まれている。
> まだ確認できていないこと: メール確認から実業務、外部結果、日次メール、停止までの一連の利用。
>
> 完了した利用者サイクルはまだ確認できていないので、登録リンクはまだ案内しません。

これはdraftで未投稿。Postiz readbackはgroups=0 / integrations=0のため、投稿前に既存X accountの所有者・接続先を確認する。同じ文面を複数アカウントへ重複投稿しない。投稿開始後は`utm_source=x&utm_medium=social&utm_campaign=maritime-week1`を使う。自動DMや新規アカウントは作らない。

## X build-in-public English (draft, unpublished)

> The Life Manager pilot signup page is live. Its full path from email verification through completed work, an external result, a daily report, and stop is still unverified. I’m holding the acquisition link until that cycle works end to end.

This draft is not published. The current Postiz connector exposes no groups or integrations, so verify the existing profile before scheduling it. Do not imply that the product has already earned money for users.

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
