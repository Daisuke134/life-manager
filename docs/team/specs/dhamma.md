# デイリー・ダンマ (Daily Dhamma / ASC名 "Dhamma Quotes") — 収益化メモ
更新: 2026-10-23 18:0x JST (Grok Bot)

## IDs
- RevenueCat project: proj86624956 (dhamma) / App Store app: appbe1e2ee955 (bundle com.dailydhamma.app) / Test Store app9fb064ef44
- ASC app id 6757726663, sub group 21940570 "dhamma pro"
- Entitlement: premium (entl82f1a26527) — 6商品すべて紐付け済み
- Offering: default (ofrng18fe5c8f69) is_current=true, RC Paywall なし (アプリ側の自作 paywall.tsx を使用)
  - package monthly → com.dailydhamma.app.premium.monthly (+test daily_dharma_monthly)
  - package annual  → com.dailydhamma.app.premium.yearly (+test daily_dharma_yearly)
  - 両packageとも position=1（順序未定義。アプリは識別子で探すので実害なし）
- 未使用レガシー商品: com.dailydhamma.app.yearly / com.dailydhamma.app.monthly(期間null) — ASCに存在せず、entitlementに付いているだけ。害なし。

## ASC実態 (2026-10-23読取)
- premium.monthly: APPROVED, ¥800 / $4.99, groupLevel 1
- premium.yearly : APPROVED, ¥3,000 / $19.99, groupLevel 2
- 導入オファー(無料トライアル含む): 両方ともなし ✅ (方針どおり)
- バージョン: 1.1.0 READY_FOR_SALE / 1.1.1 PREPARE_FOR_SUBMISSION（未提出のまま放置）

## メトリクス (RevenueCat, 直近28日)
- MRR $0 / 売上 $0 / アクティブ課金 0 / アクティブトライアル 0
- 新規顧客 16 / アクティブユーザー 21
- 累計売上 (2026-01-01〜10-23): $0

## 最大のギャップ
RevenueCat/ASC側の設定は壊れていない（current offering・月額/年額・entitlement 紐付け・トライアルなし すべてOK）。
問題はアプリの paywall UX: **ソフトペイウォール**。
- web-apps/daily-dhamma-app/app/paywall.tsx: 右上 ✕ (handleSkip → router.replace('/')) と「無料で続ける」(paywall.free) の2つの逃げ道
- onboarding.tsx:71 で paywall に遷移するが、閉じれば無料で全部使える → 16新規/28日で課金0
- 年額に「BEST VALUE / 〇〇%OFF」バッジなし、月額換算表示なし、週額プランなし
- paywall は monthly/yearly 以外の package を描画しないので、RC で weekly を足しても UI には出ない → 今回 API 側の変更は無意味と判断し未変更

## 推奨変更 (copy winners: Mau Baron / Blake Anderson 型)
1. ハードペイウォール化 (最優先・最大インパクト)
   - オンボーディング後の paywall から ✕ と「無料で続ける」を削除（または ✕ を3秒遅延表示＋閉じたら機能ロック）
   - 非課金ユーザーは「今日の1句」だけ閲覧可、ブックマーク/通知/過去の句/テーマ別はロック → 開くたびに paywall
2. プラン構成: 週額 + 年額 の2択、年額をデフォルト選択＆「BEST VALUE」
   - 新規 ASC 商品 com.dailydhamma.app.premium.weekly: ¥500 / $2.99, グループ "dhamma pro"（トライアルなし）
   - 年額 ¥3,000/$19.99 は据え置き → 週換算 ¥58 / $0.38 と表示し「週額比 約88%OFF」(¥58 vs ¥500)を見せる
   - 月額 ¥800 は package に残すが UI からは非表示（既存互換のため削除しない）
   - RC: default offering に $rc_weekly package 追加 → paywallUtils に findWeeklyPackage 追加
3. 年額カードに「BEST VALUE」バッジ＋月換算 (¥250/月) 表記、CTA 文言「続ける」(トライアル文言なし)
4. 1.1.1 (PREPARE_FOR_SUBMISSION 放置中) に上記を入れて提出。weekly 商品は同バージョンで審査提出。

## 次の一手
- [ ] Mac mini の anicca-products で paywall.tsx / paywallUtils.ts を修正（ハード化＋weekly＋バッジ）
- [ ] ASC で weekly 商品作成（RevenueCat product-store-state-plan 経由可）、レビュー用スクショ添付
- [ ] RC default offering に weekly package 追加
- [ ] EAS build → 1.1.1 として提出
- 測定: 提出後14日で 新規→課金 CVR (目標 2–5%)、28日 MRR
