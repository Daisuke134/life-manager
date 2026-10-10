# Mobile distribution handover

## 正本と再開場所

- Repo: `/Users/anicca/Projects/life-manager-main`
- 正本spec/TODO: `/Users/anicca/Projects/life-manager-main/.worktrees/mobile-distribution-e2e-20261010/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`、§S09と末尾の`2026-10-10 20:10 JST`節。
- 今回のdocs worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/mobile-distribution-e2e-20261010`
- Branch/upstream/push: `docs/mobile-growth-postmerge-20261010` / `origin/docs/mobile-growth-postmerge-20261010`
- handover本文作成前の確認済みcommit: `c405732a13fdc40f8880cd7710d9d756b311ffd7`（latest main同期とspec更新を含む。handoverは後続commitとしてpushする）。
- Source PR #7485は`0615b8ff4668c73cd6d4f5fda8563a1ac2f76a95`でmainに統合済み。PR #7493はdocs-only更新用でopen。handover commit後にhead/base/mergeability/required checksをfresh確認する。
- 実装worktreeは未作成。必要になった場合だけ`/Users/anicca/Projects/life-manager-main/.worktrees/mobile-postiz-3perday-20261010`を`origin/main`最新から作り、branch/upstream `fix/mobile-postiz-3perday-20261010` / `origin/fix/mobile-postiz-3perday-20261010`を使う。作成前にfetch、worktree/lease/branchを確認する。共有checkout `/Users/anicca/Projects/life-manager-main`には触れない。

## 最新証拠

- 20:09:56 JSTのPostiz公式GET: 設定21 integration（18 mobile: Anicca 16 + Honne 2、別laneのeBook 3）、全21 IDが見つかり有効。18 mobile targetの本日実績は25/54 `PUBLISHED`: 9口座が2/3、7口座が1/3、2口座が0/3。残り29件。全profile内訳は正本specの20:06/20:10節にある。最新GETでも同じ件数。予約/queueは公開数に数えない。
- 20:09 JSTのruntime readback: `~/loops/current`=`20261010T195449-2bacf1f4`、main=`95da8dd1cb43fca97d29b6dcee0d016341077d2b`。`life-manager-release-reconciler` PID `33289`が稼働中。Anicca main TikTok ownerは旧SHA `d3eedfb78ec65006d98d75da511748fdde0632b5`のloaded-idle。occurrence `18dd268420a83ea8-50482`はprovider前のdisk defer、effect `not_applicable`、receiptなし。過去のunknown occurrenceは解決・再送しない。reconciler/apply lock中にtarget applyやrestartをしない。
- RevenueCat/ASC/Mixpanelを今回fresh-readしていない。古いRevenueCat USD 20.34はcurrent/settled net MRRではない。USD 10K net MRRは未達証明。
- 既存source pathのapproved pack/cached backgroundsを再利用する。投稿毎にGemini/GPT Image等を呼ばない。Postiz公式`PUBLISHED` receipt/permalinkと同一slot replay-zeroを投稿証拠にする。views/likes/comments/reachはまだ全postにjoin済みではない。

## 最初の安全な再開

1. handoverと正本specを読み、`git fetch origin`後にworktree/branch/HEAD/upstream/dirty-state/lease、PR #7493の最新head/base/checksを確認する。docs branchにはhandover commitをpushし、remote objectを読む。
2. PR #7493のexact-head checksを確認し、競合があれば該当spec差分のみ解消する。required checksがpassしたらdocs PRをmainへ統合する。
3. 現在稼働中のrelease reconcilerが自然終了したか確認する。終了後、release pointer・locks・18 owner loaded SHA/fence・最新Postiz day countsをfresh readする。slot時刻は待たない。missed slotは既存catch-up pathを使い、独立してできるmetrics作業は続ける。

## User-sendable /goal

/goal Life ManagerのAnicca iOS中心の配信を計測可能にし、設定済み18 mobile accountすべてで1日3件のdistinct postを公開し、per-post views/engagementとpermalinkを結び、ASC first-time downloads 100件/日/app（trailing 7-day average）とAniccaの公式settled net MRR USD 10,000を達成してから他の承認済みappへ再現する。最初にこのhandoverと正本specを読み、fetch後のGit/PR/lease/runtime/providerを検証し、specを証拠に合わせて更新しながら完了まで進める。確認証拠はPostizの3 distinct `PUBLISHED` receipts/permalinks per mobile account/day、重複effectなし、全postの公式views/engagement、ASC acquisition、RevenueCat subscription/refund/fee/settlement、Mixpanel onboarding/paywall funnelとする。画像は保存済みapproved pack/cached backgroundsを再利用し、投稿毎に生成APIを呼ばない。旧unknown fenceを解除/再送せず、Postiz direct bypassを使わない。missed slotはreconciler/owner lock解放後に既存catch-up pathで処理し、後のslot時刻を待たず独立した作業を続ける。配信を先に安定させ、次にASC/RevenueCatとin-app計測、続いてASO/store page、onboarding/paywall/UXを一度に一実験ずつ進める。100 downloads/dayや$10K net MRRは公式証拠が揃うまで達成扱いしない。Geminiやper-post paid image generationは使わない。review/subagentはユーザー指示どおり追加しない。Docs worktreeは`/Users/anicca/Projects/life-manager-main/.worktrees/mobile-distribution-e2e-20261010`、branch/upstream `docs/mobile-growth-postmerge-20261010` / `origin/docs/mobile-growth-postmerge-20261010`、確認済み基準commit `c405732a13fdc40f8880cd7710d9d756b311ffd7`。実装が必要なら専用worktree `/Users/anicca/Projects/life-manager-main/.worktrees/mobile-postiz-3perday-20261010`、branch/push `fix/mobile-postiz-3perday-20261010` / `origin/fix/mobile-postiz-3perday-20261010`を最新`origin/main`から作成し、lease確認後に使う。共有checkoutには触らない。
