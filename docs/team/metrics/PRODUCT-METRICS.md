# プロダクト計測の正本

## ファネル

アプリ内の標準ファネルは次の順です。

1. onboarding_completed
2. paywall_shown
3. trial_started
4. purchase_completed

アプリ内イベントの既存送信先はMixpanelです。現在のソースではPostHogはA/Bテスト関連のイベント層で使われ、プロダクトファネルのイベント読み戻しは確認できていません。新しい分析ベンダーやイベント名は追加しません。

- onboarding_completed: オンボーディング完了イベント。
- paywall_shown: プラン選択ペイウォール表示イベント。
- trial_started: RevenueCatのCustomerInfoで有効なトライアル中のentitlementを確認した後に送信します。
- purchase_completed: クライアントの購入完了テレメトリです。単独では決済の証明にしません。

このイベント列だけから利用者単位の遷移率や売上を推定しません。支払いはRevenueCatとAppleの取引・精算記録で照合し、Mixpanel上の購入イベントを実売上へ加算しません。

## キャンペーン属性とクリック領収

Webリンクでは utm_source、utm_medium、utm_campaign を獲得元・媒体・キャンペーンとして保持します。App Storeの ct はキャンペーン識別子です。

- /.netlify/functions/hit はcookie、IP、user IDを保存しないfirst-party集計です。ページビューはパスとsource/medium/campaign/refで集計し、イベントはイベント名とsource/medium/campaign/ctの組み合わせで集計します。
- /.netlify/functions/stats はこの集計を返します。設定で STATS_KEY が要求される環境では、キーなしの読み戻しはできません。
- /go/:token はリダイレクト前に marketing_click_receipts へ schema_version、receipt_id、campaign_token、product_id、clicked_at を保存します。App Storeリンクは ct、Webリンクはsource/medium/campaignを渡します。クリック領収はクリック記録であり、インストールや購入の証拠ではありません。
- 現在、Webのクリック・サイトイベントとアプリ内Mixpanel利用者の間に、検証済みの利用者単位の結合はありません。キャンペーンクリックからRevenueCat entitlementまでの帰属を断定しません。

## テストイベントの扱い

計測経路の確認に送る合成イベントは paywall_shown、ct=test_codex_1027、utm_source=codex_test、utm_medium=qa、utm_campaign=test_codex_1027 とします。stagingまたはproductionの既存集計に現れたことを読み戻して確認し、テストとして除外します。イベント数を実利用者、トライアル、購入、売上として扱いません。

## 根拠

- Google Analytics Help, [URL builder: Collect campaign data with custom URLs](https://support.google.com/analytics/answer/10917952?hl=ja): UTMのsource、medium、campaignの役割。
- Apple, [Campaign links](https://developer.apple.com/help/app-store-connect-analytics/acquisition/campaign-links/): App Storeキャンペーンのct。
- 実装: apps/mobile/anicca-ios/aniccaios/Services/AnalyticsManager.swift、apps/landing/lib/site-hit.ts、apps/landing/netlify/functions/_lib/site-hit-store.js、apps/landing/netlify/functions/_lib/marketing-go.js。
