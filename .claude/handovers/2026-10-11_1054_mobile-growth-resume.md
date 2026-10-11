# Mobile growth 継続用handover

最終確認: 2026-10-11 10:54 JST。メール送信はしていない。

## 正本とルーティング

- repo: `/Users/anicca/Projects/life-manager-main`
- 作業worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/mobile-growth-release-gc-20261011`
- branch / push target: `docs/mobile-growth-postmerge-20261011` / `origin/docs/mobile-growth-postmerge-20261011`
- この記録作成前の確認済みHEAD: `f76c39b3b65cc688f8c30ecf80380b7707527514`。このhandoverとspec更新はその上にcommit/pushする。再開時は必ずfetchしてbranch HEAD/upstream/dirty状態を読み直す。
- current main at readback: `899ddafe2191e6e0558b73b8803f0a0992eeb346`; PR #7588 `https://github.com/Daisuke134/life-manager/pull/7588` はOPEN。
- canonical TODO/order SSOT: `/Users/anicca/Projects/life-manager-main/.worktrees/mobile-growth-release-gc-20261011/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`。最新cursorは末尾の`2026-10-11 10:54 JST`節。
- 共有checkout `/Users/anicca/Projects/life-manager-main` はdirtyな`capafy/annual-report-risk-change-brief-20261009` / `e2010e5b81cd4139fb097a89a4a9a60d5ccf464f`。切替・編集しない。
- このworktreeのleaseはowner `codex-mobile-growth`、task `Diagnose and safely unblock mobile release retention while preserving memory and state`、readback時点でactive。作業後のHEADは通常のlease heartbeatで記録する。

## 現在の状態と最初の一手

PR #7588のsourceはmetrics ownerの新occurrenceを古いeffect_unknownから分離する変更だが、まだmain/production未反映。exact-head `Loop control contracts`は862件中1件failし、`runtime/loop/tests/fixtures/macos-loop-jobs.json`がrendererの新`admission_effect_scope`出力に追いついていない。最初にfixtureを直し、失敗test→loop test suite→PR checksを通す。独立review/subagentはユーザー指示で起動しない。

Production currentはimmutable `20261011T101349-98f93e27` / SHA `98f93e272489db9a17f6e0d9df897bb5e2beb853`。18 publisher lane中17が98f、`life-manager-anicca-en-widget-instagram`だけ49af。`life-manager-anicca-ja-widget-instagram`と`life-manager-anicca-main-instagram`は直近`entrypoint_exit_1` / unknown / `official_readback_required`。Instagram metrics ownerは9a76、TikTok metrics ownerは98fで両方effect_unknown admission blocked。release/ownerを手動restartせず、公式readbackで状態を分ける。

最後のPostiz official GETは10:37 JSTで28/54 `PUBLISHED`、18 first slots中17成功、当日per-post metrics durable snapshot joinは0。最後のASC/RevenueCat/Mixpanel snapshotは10/11 02:27 JSTで古い。RevenueCat Anicca USD 20.34はsubscription MRRでsettled netではなく、USD 10,000 net MRRは未達・未確認。paywall plan-loadとnotification→same-quoteも未解決。細部と順序はSSOT最新節を正とする。

実装中は次slotの時刻を待たず進める。Postizの既存assetを再利用し、投稿ごとのGemini/image generationや新analytics vendorは加えない。古いeffect_unknownをno-effect扱いして解除・再送しない。

## 再開用goal

```goal
/goal Anicca iOSを先頭に既存6モバイルappのdistributionとconversionを伸ばし、AniccaのUSD 10,000 verified net recurring MRRを達成してからmobile factoryへ広げる。Doneは、18 Postiz publisher laneが各JST日3つの異なるconfigured slotを`PUBLISHED` receipt＋permalinkで満たし、per-post metricsがdurable snapshotとTelegram `message_id`まで結び付き、同一occurrence/snapshotの再送が0件であること、これを7 JST日連続で確認すること。slot時刻を待って実装・分析を止めず、自然発生証拠を積む。まずhandoverとSSOT最新節を読み、下記専用worktreeでPR #7588のfixture CI failureから再開し、git/runtime/provider stateをfresh readbackしてSSOTを更新する。ASC first-time downloads、RevenueCat subscription MRR、Mixpanel onboardingをsource/cohortごとに分け、Anicca 100 first-time downloads/day（trailing 7-day average）を目指してからASO・onboarding/paywallを一変数ずつ改善する。Apple settlement/refunds/feesとactual costsを同期間で照合し、10K net MRRを未達のまま達成扱いしない。保存済みcreative assetsを使い、投稿ごとの画像生成や新analytics vendorを追加しない。古いeffect_unknownを解除・再送せず、公式readbackが無い時はunknownを保持する。独立review/subagentは起動しない。worktree=`/Users/anicca/Projects/life-manager-main/.worktrees/mobile-growth-release-gc-20261011`、branch/upstream=`docs/mobile-growth-postmerge-20261011` / `origin/docs/mobile-growth-postmerge-20261011`、確認済み開始commit=`f76c39b3b65cc688f8c30ecf80380b7707527514`。編集前にremote HEAD/upstream/dirty stateとowner leaseを確認し、共有checkout `/Users/anicca/Projects/life-manager-main` は触らない。source acceptanceとCIがPASSするまでmergeせず、本番はmain由来immutable releaseと通常owner admissionだけを使う。
```
