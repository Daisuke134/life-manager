# For Better Sleep（Sleep Reset）課金改修スペック（勝ち組コピー）
2026-10-23 23:00 JST / 作成: Grok Bot（毎時の収益パス、自社iOSアプリのローテーション）

## 数字（RevenueCat proj77301666「sleep」、過去28日、2026-10-23 22:53 JST 取得、読み取りのみ）
| 指標 | 値 |
|---|---|
| MRR | $0 |
| 売上(28日) | $0 |
| 新規顧客 | 1 |
| アクティブユーザー | 1 |
| アクティブトライアル | 0 |
| アクティブ課金 | 0 |

- App Store: 「For Better Sleep - Sleep Reset」id 6762143790 / bundle `app.rork.vcinrjbl3ke00f07gtlzf` / v1.0.1（2026-05-04 公開）/ 評価0件（iTunes lookup API）
- Offering `default`（current、RCペイウォールなし: paywall_id=null、RC paywall 0件）
  - `$rc_weekly` (`weekly`) = `sleepreset_weekly` US $7.99/週・JP ¥1,300（ASC: 3日間無料トライアル、全地域）
  - `$rc_annual` (`annual`) = `sleepreset_yearly` US $39.99/年・JP ¥6,000（ASC: 3日間無料トライアル、全地域）
  - 出典: RC `get-product-store-state`（store_fetched_at 2026-10-23 22:53 JST）。両方 APPROVED、グループ「Sleep Reset Premium Plan」
- Entitlement `premium` に iOS/Test Store の4商品すべて紐付け済み（コードの `entitlements["premium"]` と一致）
- 注: RC 側の iOS 年額商品 `prod30984f886f` は duration/trial が null 表示（メタデータ未同期。ストア側は P1Y＋P3D で正常。購入には影響なし）

## 原因（コードで確認済み）
ソース: GitHub `Daisuke134/rork-lazy-app-profit-blueprint` の `ios/SleepReset/`（Rork製、最終コミット fb0bc77 2026-05-01）
- `Views/SleepResetFlowView.swift`（`SleepPaywallView`）、`ViewModels/SleepResetViewModel.swift`、`Models/SleepResetModels.swift`

**すでにハードペイウォール＋トライアルあり。** 14問のオンボーディング → 分析 → スコア → レビュー依頼 → ペイウォール。×ボタンも戻るボタンもなし（`toolbar(.hidden)`・`navigationBarBackButtonHidden`）、`hasUnlockedPlan`（entitlement `premium`）が無いとダッシュボードに入れない。年額がデフォルト選択、CTAは「Start for free」。Thankful/ダンマのような「何もロックされていない」「無料Proバグ」は無い。

なので転換0の主因は **流入（28日で1人）**。1人では転換率を語れない。そのうえで課金画面に勝ち組との差が4つある:
1. **年額の見せ方が弱い。** 週額 $7.99 が先頭、年額 $39.99 は総額だけ。BetterSleep は「年額 $4.99/月相当、Save 30%、best value、7 days free」で月額換算を大きく出す。年額 $39.99 は週 $0.77 なのに伝わっていない。
2. **ハードコードの価格が間違い。** `displayPrice` が `$12.99/week`・`$49.99/year`（実際は $7.99/$39.99）。オファリング読み込み失敗時にこれが出る。トライアル文言「Both plans include 3 days free」も固定で、トライアル使用済みユーザーにも表示される（審査リスク）。
3. **社会的証明が無い。** BetterSleep はペイウォール直前（19画面中17番目）に社会的証明、18番目にペイウォール。こちらはレビュー依頼（評価0件のアプリでいきなり星を求める）だけ。
4. **計測ゼロ。** `AnalyticsService.track` は `print` だけ。paywall表示→購入開始→購入の数が取れていない。
5. 細かい点: プライバシーポリシーURLが `paste.rs`（ストア商品の review_information）。信頼感と審査で不利。

## 勝ち組の型（2026-10調査）
| アプリ | ペイウォール位置 | 価格/トライアル |
|---|---|---|
| BetterSleep（月$600k、H&F #47） | 19画面中18番目（直前に社会的証明）、2025年にフリーミアム→完全有料化 | 年$59.99（7日無料、「$4.99/月」表示、best value）/ 月$14.99 / 生涯$249.99 |
| Calm | 初回起動でトライアル | 年$79.99（14日無料、Web） |
| Sleep Cycle | トライアル先行 | 30日無料、年〜$57.99 |
出典: appsroo.com/apps/314498713、bettersleep.com/transform-your-sleep-d、support.calm.com、sleepcycle.com

## 改修内容（コピーのみ、価格は据え置き）
1. **年額を先頭・最大に。** 年額カードを上に、「BEST VALUE」「3日間無料」バッジ、価格は `storeProduct.localizedPricePerWeek`（または PerMonth）を大きく、総額 `localizedPriceString`/年を小さく。週額は下に小さく（BetterSleep型）。
2. **価格とトライアル表示をストアから。** ハードコードの `displayPrice` フォールバックを削除し、読み込み中はスケルトン＋再試行。トライアル文言は `Purchases.shared.checkTrialOrIntroDiscountEligibility` の結果と `storeProduct.introductoryDiscount` から生成し、対象外なら「3日間無料」を出さない。
3. **社会的証明をペイウォール直前に。** レビュー依頼画面を「あなたと同じ悩みの人向けのプラン」系の画面に置き換え（数字は実績が出るまで出さない、誇張しない）。レビュー依頼は購入後のダッシュボード初回に移す。
4. **計測を入れる。** paywall_viewed / checkout_started / trial_started / purchase を RevenueCat の customer attributes か既存の無料計測に送る（有料SaaSは使わない）。
5. **プライバシーポリシーを aniccaai.com 配下へ**（ASCのURL変更は人手またはASC API、RCの商品設定は触らない）。
6. 価格（$7.99/週、$39.99/年）とトライアル（3日）は変更しない。7日トライアル化は、流入が週20人以上になり数字で比較できてから検討。

## 受け入れ基準
- 年額がデフォルト選択かつ一番上、週あたり換算が表示される（US で「$0.77/week」相当、JP で円表示）
- コード内に `$12.99` `$49.99` が残っていない。オファリング取得失敗時に価格を出さず再試行ボタンが出る
- トライアル使用済みの Sandbox アカウントでは「3日間無料」が表示されない
- ペイウォールは引き続き閉じられない（×・戻るなし）、未購入でダッシュボードに入れない
- 4つの計測イベントが1回の Sandbox 購入で記録される
- TestFlight で購入〜復元が通る

## 触らないもの
- RevenueCat の本番設定（offering、package、商品、価格、entitlement、paywall）は一切変更しない。今回は読み取りのみ。
- 最優先は流入。課金画面の改修と並行して、配信ループで aniccaai.com/sleepreset と App Store リンクを流す（apps.md「集客なし」）。
