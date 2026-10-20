# Life Manager 初週の配布文案

状態: 文案。未送信・未投稿。Daisが家族・友人へDMする。公開投稿は稼働URLと実際の対応範囲を確認してから実行する。無料pilotは既存のpaid Calendar trialとは別。全員の利益・将来の無料継続を保証しない。

## 配布の仕組み

参照: `docs/research/maritime/2026-10-20-source-map.md`。Arc/Pandaの「具体的な仕事→実際の成果→普段の連絡先で短く見せる」、Pokeの「一つの業務と一つの共有URL」を模倣する。成果数値や保護された文言をコピーしない。

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
>
> メール登録 → Managerが仕事を選ぶ → 実行 → 日次メール。
>
> 最初は商品づくりと販売業務から。できた作業、確認できた売上、まだ未接続の部分を分けて報告します。収益保証はありません。
>
> 実画面の短いdemoと、試せるリンクを添付します。

「商品づくりと販売業務」は実行確認した範囲に限定する。公開実績がなければ販売完了を示す画面を使わない。

## X English・公開後

> Life Manager is a proactive manager that chooses work, executes it, and emails you a daily report.
>
> No required goal or budget setup. No Telegram requirement.
>
> We're starting with product creation and earning workflows. Completed work, recorded revenue, and missing connections are reported separately. Free pilot; earnings aren't guaranteed.
>
> Real demo + signup link below.

## Instagram DM・公開後

> 作っていたLife Managerの無料pilotを公開したよ。自分で仕事を進めて、毎日メールで結果が届く仕組み。最初から利益が出る保証はないけど、実行したことと未接続の部分が分かるようにしてる。メールで試せるリンクを送るね。

## Instagram Story/Reel caption・公開後

> 毎日の指示なしで、仕事を進めるManager。
> メール登録 → 自律実行 → 日次レポート。
> 無料pilot公開中。できたことも、未完も、そのまま報告。
> 実際の対応範囲は登録ページへ。収益保証なし。

## URL確定

- 公開先はT22でreadbackしたRailway/既存domain originを使う。例のhostnameを公開しない。
- Daisの紹介: `${PUBLIC_ORIGIN}/maritime?source=referral&utm_source=friends&utm_medium=dm&utm_campaign=maritime-week1`
- X: `${PUBLIC_ORIGIN}/maritime?source=x&utm_source=x&utm_medium=social&utm_campaign=maritime-week1`
- IG: `${PUBLIC_ORIGIN}/maritime?source=other&utm_source=instagram&utm_medium=dm&utm_campaign=maritime-week1`
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

copy variant/source/permalink → visit → email verified → activated → work completed → return。APIのsignup成功や知人への送信だけを競技実利用にしない。投稿量より、完了した人数と費用を改善する。
