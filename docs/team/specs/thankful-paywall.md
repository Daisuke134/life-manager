# Thankful 課金改修スペック（勝ち組コピー）
2026-10-23 19:55 JST / 作成: Grok Bot（毎時の収益パス、自社プロダクト担当）

## 数字（RevenueCat proj7aaf9429、過去28日、2026-10-23時点）
| 指標 | 値 |
|---|---|
| MRR | $0 |
| 売上(28日) | $0 |
| 新規顧客 | 3 |
| アクティブユーザー | 3 |
| アクティブトライアル | 0 |
| アクティブ課金 | 0 |
| 転換率 | 0/3 = 0% |

Offering `default`（current、RCペイウォールなし: paywall_id=null）
- `$rc_monthly` = `thankful_monthly` $4.99/月（iOS版にトライアルなし）
- `$rc_annual` = `thankful_annual` $29.99/年（iOS版に**P1W＝7日間無料トライアル**）
- Android版は Play のサービスアカウント未設定（play_service_account_credentials_configured=false）

## 原因（コードで確認済み）
ソース: `~/Projects/anicca-products/mobile-apps/rork-thankful-gratitude-app/ThankfulGratitudeApp/`
課金画面: `Views/PaywallView.swift`（表示箇所: `ContentView.swift`（オンボーディング後）、`Views/SettingsView.swift`）

1. **何もロックされていない。** `viewModel.isPro` を読んでいるのは Settings の表示だけ（`grep isPro`）。Home/History/アファメーションは全部無料なので、課金する理由がない。ペイウォールの約束（「無制限の記録」「200以上のアファメーション」「インサイト」）は無料版で全部手に入る。→ 転換0の主因。
2. **課金画面は1回だけ出て、×ですぐ閉じられる。** オンボーディング直後に1回出るだけ（`paywall_skip`）。その後は設定タブの奥にしかない。
3. **無料でProになるバグ。** `purchase()` の中で `offerings?.current` が nil、またはパッケージが無いと `onPurchaseSuccess()` が呼ばれ、お金を払わずに `isPro=true` になる。オファリングの読み込みに失敗すると、`fetchOfferings` がエラーを握りつぶしてこの状態になる。
4. **価格がハードコード。** `Strings.swift` に「$29.99/年」「¥4,500/年」「¥800/月」と直書き。ストア価格（`package.localizedPriceString`）もトライアルの対象かどうかも使っていない。月額を選んでも、注意書きは「トライアル中いつでもキャンセル」のまま。
5. 流入も小さい（28日で3人）。課金を直したら次は流入（apps.md「集客なし」）。

## 勝ち組の型（2026-10調査）
| アプリ | 無料範囲 | 有料で解放 | 価格/トライアル |
|---|---|---|---|
| 5 Minute Journal（推定月$40k） | 朝夕のガイド記録・リマインダー・ストリーク・引用 | 写真/動画、カスタム質問、ムード、On this Day、ウィジェット | 年$39.99（3日トライアル）/ 月$9.99 / 生涯$99.99 |
| Gratitude: Self-Care Journal（4.9★ 45k） | 記録の基本機能 | Pro: アファメーション全部、ビジョンボード、写真/音声、プロンプト全部 | 年$29.99–39.99（7日 or 1ヶ月トライアル）/ 月$4.99–6.99 / 3ヶ月$9.99 |
| Presently（Android、41.7k件レビュー） | 全部無料（課金なし） | - | 参考外（課金モデルではない） |
共通点: **毎日の記録は無料（習慣づけ）＋「おまけの深さ」（全アファメーション、写真、インサイト、ウィジェット、テーマ）をPro化**。年額＋無料トライアルをデフォルトで選択、オンボーディング直後とロック機能タップ時にペイウォールを出す。

## 改修内容（コピーするだけ、独自案なし）
1. **ゲートを入れる（Gratitude/5MJ型）。** 無料: 1日1件の感謝記録、今日のアファメーション1件、7日分の履歴。Pro: 1日の記録無制限、アファメーション200以上全部、全履歴＋インサイト/ストリーク統計、写真添付・ウィジェット・テーマ（既存機能があれば）。ロック行をタップしたら `showPaywall = true`。
2. **無料Proバグを直す。** offerings/package が nil のときは `onPurchaseSuccess()` を呼ばず、エラー表示と再取得にする。Proは `customerInfo.entitlements["pro"]` が有効なときだけ付ける。
3. **ストア価格を表示する。** `package.storeProduct.localizedPriceString` と `introductoryDiscount` を使い、トライアル表記はトライアル対象のときだけ出す。年額の「月あたり◯円」とお得率（例: 月額比 −50%）を表示する（5MJの「年額は約67%お得」と同じ）。
4. **ペイウォールを出すタイミング。** オンボーディング直後（今のまま）＋ロック機能タップ時＋3日連続記録の達成時（ストリーク達成時のソフトペイウォール）。×ボタンは2〜3秒遅れて表示する（業界標準）。
5. **価格（RCとASCの設定変更は別途承認。今回は変更していない）。** 今の $4.99/月・$29.99/年（7日トライアル）は Gratitude の主力価格帯と同じなので、**価格は据え置き**。追加候補は 5MJ 型の生涯 $59.99–99.99 だけ（あとでA/B）。
6. **計測。** RCの新規→トライアル開始率を週次で追う。目標: トライアル開始 ≥10%（業界中央値）、トライアル→課金 ≥35%。

## 担当と次の一手
- 実装: Local Life Manager（Mac mini、Xcode）。対象ファイル: `PaywallView.swift`、`ContentView.swift`、`HomeView.swift`、`HistoryView.swift`、`Models/Strings.swift`。ビルド → TestFlight → 審査提出。
- 並行: 流入施策（IG anicca.en のクオートカード型で、感謝プロンプトを毎日1枚、UTM付きのApp Storeリンク）。
