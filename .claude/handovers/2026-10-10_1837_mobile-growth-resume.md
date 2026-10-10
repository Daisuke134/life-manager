# モバイル配信・計測の引き継ぎ

作成時刻: 2026-10-10 18:37 JST。ここにあるPostiz/runtime値は時点値なので、再開時に必ず取り直す。

## 正本と作業場所

- Repo: `/Users/anicca/Projects/life-manager-main`
- 実装worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/mobile-distribution-e2e-20261010`
- Branch: `fix/mobile-distribution-e2e-20261010`
- Upstream/push target: `origin/fix/mobile-distribution-e2e-20261010`
- handover作成前のHEAD: `084e07a8777115f4dc17ae12800efaa4f9ac31ab`
- `origin/main`: `c182cec05a585505e55987cdf821a3b542029ac0`。実装branchはこのmainを含む。mainとのmerge commitは `e7aca2a1a4c35ea9da2ebbe8f00bef981c540728`。
- handover作成前のremote feature ref: `269378efe45d2b8a4279d13a25c02590c80c0d28`。PRはこのbranch headで未発見。handover/spec commitをpushした後のremote headは再確認する。
- Canonical SSOT/TODO: `/Users/anicca/Projects/life-manager-main/.worktrees/mobile-distribution-e2e-20261010/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` の `2026-10-10 18:36 JST — Main sync complete; current handover cursor` と、その直下の `Current atomic cursor`。
- 実装worktreeには `codex-root` のmanaged leaseがあり、記録された期限は `2026-10-11T09:25:32Z`。再開時にleaseとworktreeの状態を確認し、共有checkoutや他のleaseを触らない。

## 未commitの実装差分

handover作成前のHEADでは、以下9ファイルがローカルで変更済み。これらはremote feature refには含まれていない。内容を確認してから作業し、破棄・置換・別worktreeへの盲目的な切替をしない。

- `apps/life-manager/lib/honne-ja-shadow-schedule.js`
- `apps/life-manager/lib/honne-ja-shadow-schedule.test.js`
- `apps/life-manager/scripts/generate-larry-slide-pack.js`
- `apps/life-manager/scripts/generate-larry-slide-pack.test.js`
- `apps/life-manager/scripts/anicca-larry-ja-canary.js`
- `apps/life-manager/scripts/anicca-larry-ja-canary.test.js`
- `apps/life-manager/scripts/anicca-larry-ja-rotating.js`
- `apps/life-manager/scripts/anicca-larry-ja-rotating.test.js`
- `runtime/loop/tests/test_lm_loop_run_bounds.py`

slot catch-upの4 focused test filesはmain同期前に55/55。read-only dry-runは既存8-pack poolから未投稿の当日slotを選び、generatorを呼ばなかった。`test_lm_loop_run_bounds.py`はnumeric disk floorの4ケースを修正し、operator stopのケースを追加したが、まだ実行していない。`runtime/loop/lm_loop_run.py`自体は未変更。disk-gate修正後のtest結果はまだない。今回のturnでは実装テストを実行していない。

## 最新の配信・runtime evidence

- 2026-10-10 18:35 JSTの公式Postiz GET: 18/18 integrations present、対象アカウント24/54 `PUBLISHED`、0 queued/scheduled。2/3は `@ani.cca1234`, `@anicca.affirmation`, `@anicca.he`, `@anicca.jp`, `@anicca.jpx`, `@anicca_buddha`, `@anicca_slideshow`, `@aniccaaffirmation`。1/3は `@anicca-affirmation-video`, `@anicca-ai`, `@anicca.en`, `@anicca.encards`, `@anicca.jp1`, `@anicca.jp.videos`, `@anicca.jp4`, `@honnevideo`。0/3は `@aniccaen2`, `@honne_reveal`。18 profile全て3/3ではない。
- `life-manager-anicca-main-tiktok`の18:35 occurrence `life-manager-anicca-main-tiktok:18dccc6cb078ecc0-77315`は既存Postiz receipt `cmv25mjy80v1omq0yq5w7y079`を再照合しただけで、新規postではない。ownerはSHA `d3eedfb78ec65006d98d75da511748fdde0632b5`、`~/loops/current`はrelease `20261010T175612-ef35fa3b` (`ef35fa3bb890619418650c2fb2d07c7988338670`)で不一致。20件の過去 `admission_effect_unknown` fenceは維持する。
- 18:31のdisk-deferred occurrenceは18:36にadmission DBをread-only検索した時点で行がなく、provider未接触として記録されている。現在のqueued itemと決めつけて再送しない。
- 18:35 statusではdisk-cleanup ownerがloaded-idle / exit 75 / `effect_status=not_applicable`。release-reconciler statusはexit 1だったが、18:36のprocess readではPID 88394がrelease `ef35fa3`から実行中。直近process readでは`lm-loop apply`は見えなかった。18:35の空き容量は2,182,380 KiB。再開時にruntime、process、lock、空き容量をfresh readbackし、active ownerと競合しない。
- 前回のRevenueCat Anicca USD 20.34はsubscription MRR観測で、settled netではない。今回ASCとin-app eventは再取得していない。USD 10K verified net MRRとASC first-time download 100件/日/アプリは未達。

## 最初の安全な再開手順

1. このhandoverとSSOTの指定sectionを読み、`git fetch`後にHEAD/upstream/dirty diff/leaseを確認する。最新mainを含むbranchと、handover/spec commitを含むremote headを確認する。
2. まずslot catch-upの4 focused test filesを再実行し、main同期後もgreenであることを確認する。通ったらcatch-upの8 source/test filesだけをcheckpoint commit/pushする。
3. 次に`test_lm_loop_run_bounds.py`の変更済みケースを実行してREDを確認する。その後の実装は2 GiBのnumeric producer admissionだけを外し、explicit operator stop flag、実際のstorage/write failure、admission receipt、effect fenceを保持する。
4. 独立した作業は次slot時刻を待たず続ける。production apply/postはrelease reconciler、cleanup、apply lockをfresh確認するまでしない。old unknown fenceを解放・再送しない。
5. 検証・exact-head CI・source PR/main merge後に、main由来immutable releaseを用意し、対象ownerだけを適用する。公式Postizの新しいdistinct `PUBLISHED` receiptとpermalink、同じslotのreplay-zeroを確認し、残る全target、metrics、ASC/RevenueCat/Mixpanel、onboarding、USD 10K net MRRの順はSSOTに従う。

この引き継ぎでは投稿、release apply、テスト、レビューagent起動、Telegram/email送信をしていない。handoverとspecをcommit/pushした後のremote object/HEADは、利用前に確認する。
