# Life Manager CFO handover — 2026-10-05 04:25 JST

## 正本と作業位置

- Repo: `/Users/anicca/Projects/life-manager-main`
- Worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002`
- Branch / upstream / push target: `docs/lm-cfo-cost-observability-spec-20261002` / `origin/docs/lm-cfo-cost-observability-spec-20261002` / same remote branch.
- Spec/TODO SSOT: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`, §87-J items 5→6→7→8. Evidence: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002/docs/evidence/cfo/2026-10-05-cfo-live-observability-readback.md`.
- Code/spec baseline commit verified on origin before this handover: `82ed8422fb88f50efdc05c4119532a1b5df155da`. This handover is the only new file after that commit; fetch and verify the final branch tip, upstream, and dirty state before resuming.
- Main/installed release: `82d31995e68a5220b7a288318a893866a24c7ea6`. The task branch history includes unrelated marketing commit `cab8cce811`; do not merge the branch wholesale. The shared checkout `/Users/anicca/Projects/life-manager-main` is outside this task. Do not edit the separate mobile worktree while its lease/HEAD mismatch remains unresolved.

## 最新確認

- B7 candidate projection at 2026-10-05 03:42 JST: historical/trailing gaps 135/135, 14/14 loops unknown, MRR/runway unknown; causes 126 `missing_category`, 1 `missing_coverage`, 6 `source_unconnected`, 2 `stale_readback`, 0 `read_failed`. Candidate source-status fix passed 45 focused and 267 CFO tests plus independent review, but is not production-loaded.
- Moneytree exposes no freshness timestamp or refresh action; 12-month summary ends 2026-08 and the 2026-09-01..10-05 transaction query returned no rows. This is unknown coverage, not zero spending or a verified current bank balance.
- Capafy seller-order detail is not available from the inspected official seller endpoints; statement rows had no CSV. Installed report's USD 34.50 cost / USD 31.72 profit used unfiltered account-wide OpenRouter activity and is invalid for Capafy. Scoped USD 25.08 has a different date window. Payout balances are not bank cash or settled revenue. One correction notice was sent; do not resend.
- Google September invoice total is JPY 27,889 (invoice evidence, not payment proof). October invoice/cost is unverified; the candidate parser still omits a small cross-month line. No free replacement has passed production UX/cost measurement.
- Runtime status read at 04:18 JST: installed release remains main SHA. Local CFO at 04:02 exited 0 but `effect=unknown`, no receipt/readback; Capafy at 04:07 and cloud report owner at 04:16 deferred pre-effect (`resource_fifo_wait`, exit 75), no receipts. No retry/restart/send was done. Latest independent review found one stale Capafy reason label; it was corrected to `resource_fifo_wait` and matches the status evidence.

## 残作業と最初の安全な一手

1. §87-J item 5（現在cursor）— 公式sourceのfreshness・全transaction/分類、全14 loopのsettled revenue/refund/fee/owner mapping・actual subscription/tool/cloud costを同じperiodで照合。Capafy seller receipt、Stripe product/owner/payout-to-bank join、mobile ASC/RevenueCat attribution、Moneytreeのfresh readを完了し、unknownを0にせずB7を再計算する。
2. item 6 — Google Cost Table全行をbilling month/project/tenant/loopへ照合し、parser回帰修正。Google API残存call・cache/fallback・OpenPOI候補のUX品質・実費を同期間で比較する。
3. item 7 — 正規main→immutable release→自然daily runの経路を解消。receipt/source coverage/replay-zero確認後だけ重複cloud senderをretireする。`effect_unknown`は再送しない。
4. item 8 — 7連続日のreport receipt、freshness/coverage、provider cost、fallback、replay-zeroを同一periodで観測する。

最初は最新状態を再確認し、Moneytree/Capafyの既存公式read pathでfreshness・seller order detailをもう一度だけ安全に探索する。使えるrefresh/order receiptが無ければ具体的gapを記録し、item 5の次のsource joinへ進む。新CLI/worktreeは作らない。今回のspec/evidence変更は`git diff --check`とread-only reviewで確認し、modelはplanning/review `gpt-6.1-sol` medium、implementation `gpt-6-luna` maxを使う（5.6禁止）。

## User-sendable `/goal`（未activate）

新しいCodex sessionにworkerを起動させる場合、ユーザーが次の行を送る。現sessionには既存Goalがactiveで、このhandover行自体はそれをactivateしない。長さvalidatorはPASS（1,556文字）。

```text
/goal Life Manager CFOを、Daisへ毎日、鮮度を検証したMUFG残高・全収益・全費用・settled netを届け、Google費用と代替UXの同期間コストを比較できる運用にする。Done: Moneytree freshness/transaction coverageと分類を公式sourceで照合し、14 loop全てのsettled revenue/refund/fee、owner mapping、subscription/tool/cloud actual costを同一periodでjoinする。Google Cost Table全明細・project/tenant/loop配賦・残存Google call/caching/fallback/UX・実費を同期間で照合し、OpenPOI等はcandidateでなく実利用pathの同等検索品質を実測する。正規main→immutable releaseの経路で自然daily reportのreceipt/source freshness/coverage/provider cost/replay-zeroを確認し、その後に限り重複cloud senderをretire、最後に7連続日の証拠を照合する。未検証/estimate/stale/unsettled/unknownを分け、unknownを0にしない。正本は /Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md §87-J items 5→6→7→8。repo /Users/anicca/Projects/life-manager-main、worktree /Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002、branch/upstream/push target docs/lm-cfo-cost-observability-spec-20261002 / origin/docs/lm-cfo-cost-observability-spec-20261002、verified source commit 82ed8422fb88f50efdc05c4119532a1b5df155da。再開時は最新fetch後にHEAD/upstream/dirtyを照合する。dirtyな共有checkout、lease/HEAD不一致のmobile worktree、branch内の無関係なmarketing commitは触らず、branch全体をmainへmergeしない。新CLI/worktreeやpromotion迂回を作らない。item 5→6→7→8を1 atomずつ進め、mainがTODO順と統合を所有する。必要時だけspawn_agentを一人ずつ使い、read-only reviewerとwriterの範囲を重ねない。planning/reviewはgpt-6.1-sol medium、implementationはgpt-6-luna max、5.6は禁止。effect_unknownを再送/restartせずreadbackを診断する。安全な手段が残る間は続行し、公式source/permissionが無く安全な次手がなくなった時だけ正確なgapと最小の人手を記録する。
```

メールは送らない（ユーザーはチャットでのhandoverを希望）。
