# デイリー・ダンマ (Daily Dhamma) 課金改修スペック #1：年額3日無料トライアル＋閉じにくい課金画面（勝ち組のコピー）

現在の進捗・残TODO正本 → [統合SSOT「Dhammaの無料体験資格と再提出契約」](../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md#anicca旗艦公開6アプリの配信と継続課金)。実装契約 → [publisherのペイウォール仕様](https://github.com/Daisuke134/anicca-products/blob/main/web-apps/daily-dhamma-app/docs/onboarding-paywall-implementation-spec.md)。
2026-10-23 22:0x JST / 作成: 参謀（チーム収益ループ、自社プロダクト担当）
前回メモ: docs/team/specs/dhamma.md（17:57、ハードペイウォール＋週額案）。今回は勝ち組の調査結果を反映して、優先順位を入れ替えた。

## IDs
- RevenueCat project: proj86624956 (dhamma) / iOS app appbe1e2ee955 (bundle com.dailydhamma.app) / Test Store app9fb064ef44
- Offering: `default` (ofrng18fe5c8f69, is_current)。RCペイウォールなし（paywall_id=null、list-paywalls=0件）。アプリ側の自作 `app/paywall.tsx` を使用
  - `monthly` → com.dailydhamma.app.premium.monthly ¥800 / $4.99（トライアルなし）
  - `annual`  → com.dailydhamma.app.premium.yearly ¥3,000 / $19.99（無料体験はストア設定と顧客資格の両方で判定）
  - Entitlement: `premium`
- ソース: Mac mini `~/Projects/anicca-products/web-apps/daily-dhamma-app/`（Expo/React Native, react-native-purchases ^9.6）
  - `app/paywall.tsx`、`app/onboarding.tsx:71`（オンボーディング後に1回だけ遷移）、`app/index.tsx:37,48`（無料は10句・ブックマークでpaywall）、`providers/AppProvider.tsx`（無料は通知1日3回まで）

## 数字（RevenueCat、2026-10-23 21:5x JST取得）
| 指標 | 値 |
|---|---|
| MRR（28日） | $0 |
| 売上（28日） | $0 |
| 新規顧客（28日） | 16 |
| アクティブユーザー（28日） | 21 |
| アクティブトライアル | 0 |
| アクティブ課金 | 0 |
| 7日以内の転換（2026-01-13〜10-23） | **0 / 139人 = 0%**（リリース以来一度も課金なし） |
| Paywall Encounter（1日以内、7月〜） | 0 / 41（自作ペイウォールの表示がRCに記録されていない＝計測不能） |
新規の推移（四半期）: 1Q 68 → 2Q 30 → 3Q 31 → 4Q(途中) 10。

## 一番大きな転換ブロッカー（1つだけ）
**「今すぐ¥3,000払う」以外の選択肢がない、1回きりで閉じられる課金画面。**
- 年額にも月額にも無料トライアルがない。初回起動の直後に、まだ1句も読んでいない人へ「¥3,000/年 か ¥800/月を今払う」を出している。
- しかも右上の ✕ と「無料で続ける」(`paywall_skip`) の2つの逃げ道がある。オンボーディング後に1回出たら、その後はブックマークを押したときと設定画面の奥にしか出ない。
- 無料枠（10句・通知3回/日）は「1日1句を読む」アプリとしては十分なので、閉じた人が払う理由がない。
→ 139人中0人。無料体験の入口不足を改善仮説とする。0/139だけでは価格や入口の因果関係を確定できず、提出後の実trial・課金で評価する。

## 勝ち組の型（2026-10 調査、App Store / appslupa / apppricer）
| アプリ | 規模 | 無料範囲 | 有料で解放 | 価格・トライアル |
|---|---|---|---|---|
| Motivation - Daily quotes（Monkey Taps） | 110万件の評価 4.8★、Health & Fitness #20 | 基本の名言＋広告 | 全テーマ/カテゴリ、無制限リマインダー、背景写真、検索、広告なし | **年額 $19.99 に3日無料トライアル**（メイン）、週 $3.99、月 $4.99〜、生涯あり |
| I am - Daily Affirmations（Monkey Taps） | 同社の主力 | 基本のアファメーション | 全カテゴリ、ウィジェット、無制限リマインダー | **年額 $47.99〜59.99 に3日無料トライアル**、月 $9.99、生涯 $149.99 |
| Thankful / 本音翻訳（自社スペック） | — | — | — | 同じ型（年額＋トライアル、デフォルト選択）を採用済み |
共通点: **オンボーディング直後に全画面ペイウォール → 年額＋3日無料トライアルがデフォルト選択 → CTAは「3日間無料で始める」→ ✕は小さく遅れて出る**。毎日の基本（今日の1句）は無料、深さ（全句・全テーマ・無制限リマインダー・ウィジェット）を有料にする。Daily Dhamma の価格（$19.99/年）は Motivation のトライアル付き年額とまったく同じなので、**価格は変えずにトライアルだけ足せばよい**。

## 改修内容（コピーするだけ、独自案なし）
1. **年額に3日間無料トライアルを付ける（最優先・ストア設定）**
   - ASC: com.dailydhamma.app.premium.yearly に導入オファー「無料・3日」を作成（全地域）。価格 ¥3,000 / $19.99 は据え置き。月額にはトライアルを付けない（Monkey Taps と同じ）。
   - RevenueCat の offering / package は変更不要（annual パッケージのまま、SDK が intro offer を自動で返す）。
2. **ペイウォールをトライアル前提に書き換える（`app/paywall.tsx`）**
   - 年額をデフォルト選択（今も 'yearly'）にして、年額カードの上に「3日間無料」「BEST VALUE」バッジ、月換算「¥250/月」と「月額より69%お得」を表示する。
   - 無料体験のバッジ・CTA・trial後の請求時期は、無料の `pkg.product.introPrice` と現在の顧客の `INTRO_ELIGIBILITY_STATUS_ELIGIBLE` が両方確認できる場合だけ表示する。確認中・不明・対象外・欠測・API失敗では通常価格と通常CTAにし、顧客/商品変更や画面再表示時に以前の資格を使わない。期間・請求価格は取得した商品値を使う。
   - 月額を選んだときは CTA を「今すぐ始める」に切り替え、トライアル文言を出さない。
3. **閉じにくくする（Monkey Taps 型）**
   - 「無料で続ける」(`paywall_skip`) ボタンを削除する。
   - 右上の ✕ は 3秒遅れて小さく表示（審査対策として完全に消さない）。
4. **出すタイミングを増やす**
   - オンボーディング後（今のまま）に加えて、11句目にスワイプしたとき（ロック画面＋paywall）、通知回数を4回以上にしようとしたとき、3日連続で開いたとき。
5. **計測を入れる**
   - 自作ペイウォールの表示を RevenueCat に記録する（または RevenueCat Paywalls（無料）に移行する）。これで Paywall Encounter / Paywall Conversion が見えるようになる。
6. **価格（今回は変更しない）**: ライブの RevenueCat 設定と価格は一切変更していない。週額（¥500 / $2.99）の追加は 17:57 の dhamma.md の案として残し、トライアルの結果を見てからA/Bで検討する。

## 成功指標（提出後14日）
- トライアル開始率（新規→トライアル）≥ 10%、トライアル→課金 ≥ 35%、7日内の転換 0% → 3%以上
- 新規 16人/28日のままでも、MRR $0 → 約$10〜15（その後は流入：IG/TikTok の AI僧侶動画から UTM付きで送客）

## 担当と次の一手
- ASC の導入オファー作成: ASC API（/workspace/.secrets/asc.env）で可能。審査は新バージョンと一緒に提出する。
- アプリ改修: Local Life Manager / Codex（Mac mini、Expo）。対象 `app/paywall.tsx`、`app/index.tsx`、`app/settings.tsx`、`utils/paywallUtils.ts`、i18n の文言。EAS build → TestFlight → 1.1.1（ASC で PREPARE_FOR_SUBMISSION のまま放置中）として審査提出。source受入れ・独立検証を完了し、確定mainから作るbuildを照合して提出する。
- 注意: リポジトリの `package.json` / `app.json` は version 1.0.0 だが、ASC は 1.1.0 が販売中。ビルド前に、販売中の 1.1.0 と同じソースかどうかを確認すること。
