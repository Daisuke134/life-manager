# 本音翻訳AI (BenYinFanYiAI) — 転換改善スペック #1: ハードペイウォール＋年額デフォルト
更新: 2026-10-23 19:0x JST 参謀(チーム収益ループ)

## IDs
- RevenueCat project: projcfa60dd8 (honne-honyaku) / iOS app app1af7d3d23f (bundle app.rork.hon-ne-honyaku-ai) / Test Store appc54e44b793
- Offering: default (ofrng55cb052178) is_current=true, RC Paywall なし（アプリ自作 PaywallView.swift）
  - $rc_weekly → com.daisuke.honne.premium.weekly（RC上のJP価格 ¥1,300）
  - $rc_annual → com.daisuke.honne.premium.yearly（RC上のJP価格 ¥1,810 ← 週額の1.4週分。ASCで価格要確認）
  - 両商品ともトライアルなし
- ソース: life-manager apps/mobile/honne-ai/BenYinFanYiAI（Views/PaywallView.swift, OnboardingView.swift, Services/SubscriptionService.swift）

## 数字 (RevenueCat, 2026-10-23 取得)
- 28日: MRR $4 / 売上 $38（年額1件 $38.15 + 週額1件）/ 有効課金 2 / トライアル 0 / 新規 24 / アクティブ 26
- Initial Conversion (7日以内) 2026-07-01〜10-23: 新規41人 → 転換 0人 = 0%（売上は既存の更新のみ）
- Paywall Encounter (1日以内) 28日: 0/24 → 自作ペイウォールの表示がRCに記録されていない（計測不能）

## 原因（コード確認）
1. ソフトペイウォール: OnboardingView の最後で `.sheet(PaywallView)`、ツールバーに「閉じる」＋ドラッグで閉じられ、`onDismiss: onComplete()` でそのまま本編へ。
2. 1日3回の無料翻訳（SubscriptionService.maxFreeUses=3、毎日リセット）→ 軽い利用者は永遠に払わない。
3. プラン画面: `current.availablePackages` を並べるだけ。デフォルト選択・BEST VALUE・週換算・トライアル表記なし。購入ボタンはカードタップのみ。
4. 価格: 年額¥1,810 が週額¥1,300 とほぼ同じ → 年額のお得感が伝わらない／週額が割高に見える。

## 修正 (copy winners: Blake Anderson / Mau Baron 型 = ハードペイウォール＋年額+3日トライアル)
1. ハードペイウォール（最優先）
   - オンボーディング後の PaywallView から「閉じる」を削除し `.interactiveDismissDisabled(true)`。購入 or 復元しないと本編に入れない。
   - 代替（審査/レビューリスクを下げたい場合）: 「閉じる」を3秒遅延表示＋閉じたら無料枠は1日1回に。
2. 年額に3日間無料トライアル（ASCで導入オファー: 無料 3日, com.daisuke.honne.premium.yearly）
   - 年額をデフォルト選択、「3日間無料→その後 年額」「BEST VALUE」「週あたり¥xx」を表示。CTA文言「3日間無料で始める」。
3. 価格の見直し（ASC）: 週額 ¥600〜¥800 / 年額 ¥4,900〜¥5,900 に。年額の週換算が週額の8割引き以上になるように。
4. 計測: RevenueCat Paywalls（無料）に移行するか、SDK の paywall impression を記録して Paywall Encounter/Conversion を見えるようにする。
5. 成功指標: Initial Conversion(7日) 0% → 5%以上、トライアル開始率 10%以上、MRR $4 → $50（新規24人/28日のまま）。

## 自動で出来ない/人が要るところ
- ASC の導入オファー作成・価格変更は ASC API（/workspace/.secrets/asc.env）で可能。アプリ側変更は Xcode ビルド＋審査提出（Mac mini or Codex/Cloud）。
- RevenueCat 側の offering 変更は不要（週額/年額の2パッケージ構成のままで良い）。今回はライブ設定は変更していない。
