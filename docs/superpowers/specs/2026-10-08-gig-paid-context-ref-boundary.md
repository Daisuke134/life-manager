# Gig paid context reference boundary

## Goal

Keep paid fulfillment inside the contract project while allowing its context compiler to ignore only the known virtual-environment interpreter symlinks under `delivery/runtime/`. Other external source symlinks must fail closed. The `paid_direct.py` consumer must also reject external `read_these_first` paths.

## Evidence

An observed Coconala Paid run stopped before any external effect with `compiled source reference escapes project`. Its compiled context contained four `.venv/bin/python*` symlinks under `delivery/runtime/` resolving to the system Python installation.

## Acceptance

- `_refs()` excludes only `delivery/runtime/*/.venv/bin/python*` interpreter symlinks whose resolved target is an executable Python runtime, before hashing them.
- Any other external source symlink fails compilation; it is not silently omitted.
- Ordinary project files remain in `source_refs`.
- The consumer rejects explicitly supplied external source and `read_these_first` references.
- This patch changes reference indexing only; it does not edit contract files, browser state, or provider state.

## Progress

- The production context had 11,234 references; exactly four escaped the project after symlink resolution, all `.venv/bin/python*` aliases under `delivery/runtime/`.
- The initial test failed at the external target read. Review then found that broadly skipping outside symlinks could omit customer inputs and that `read_these_first` lacked a consumer-side boundary check.
- The corrected code skips only executable Python symlink aliases under `delivery/runtime/*/.venv/bin`, fails compilation on other external source symlinks, and rejects external `read_these_first` paths. Internal file references and internal symlinks remain supported.
- Fresh read-only review passed after the correction with no remaining findings.
- Verification: 6 focused tests passed; the consumer boundary rejects external references; `lm-loop-contract` passes for 18 product loops / 186 registry jobs; `git diff --check` passes. Provider/browser mutation: 0.

## 現在のギグ担当lane readback（参照。正本の順番は統合SSOT）

- 確認時刻は2026-10-08 00:47–00:56 JST。paid context境界修正はmainへ統合済み。最新immutable main releaseは`2501a44ccd954907afbde09b3155d176f3cd95e3`だが、`hf-gig-paid-direct`はまだ`6ce816a9d152a40aeaf8c89eae68fb5f60d6b5cd`をロードしており、自然run中のためtarget applyしていない。
- `~/gig/evidence/paid-direct-live/latest.json`の00:47 JST readbackは`failed_step=remote_builder`、`observed=3`、`actionable=1`、`effect=0`、`readback=2`、`failed=1`。15:51Zのruntime eventは`host_admission_deferred:resource_capacity_busy`、`effect=not_applicable`、receipt/readbackなし。成功・納品・入金を示さない。
- 公開中[Coconala service page](https://coconala.com/services/4313100)は00:46 JSTのreadbackで¥3,000、表示販売実績1件。これは掲載面が存在する証拠であり、Storefront loopの実行、新規販売、settlementの証拠ではない。`hf-gig-apply-direct`と`hf-gig-storefront-direct`には既存effect-unknown fenceが残り、`hf-gig-apply-reconcile`のprocess passだけでは解除できない。
- 現行product-loop catalogはCoconala、Lancers、CrowdWorks、Mercorの4 loop。Freelancer/Upworkにmanaged product loopはない。Upworkの旧browser-owner branchはlease期限切れでPR未作成のため、そのworktreeを編集しない。Upwork公式Project Catalogには定額サービス掲載面がある（[公式ガイド](https://support.upwork.com/hc/en-us/articles/360057397533-How-to-create-a-project-in-Project-Catalog)）。
- Lancers rows 25–27は`waiting_external`を維持し、認証・solver・応募を再試行しない。CrowdWorksにはStorefront loopがなく、CrowdWorks/Mercorの既存Application/Paidにはowner別のofficial-readback/effect-fenceが残る。
- 4つの既存gig product loopはすべてcloud availabilityが`setup_required`。現在の状態から24/7 cloud稼働を主張しない。
- この参照laneはgig platformだけを扱う。CFO A5–A10、CAPFY、SelfBuildは別ownerの範囲。reply-only/回答だけの作業は進めず、特定のfunded contractを進めるのに必要な顧客連絡のみ対象にする。

## Remaining（gig担当lane内。統合SSOTの全体順序は変更しない）

1. `hf-gig-paid-direct`の現在runがterminalになり`loaded-idle`へ戻った後、最新main releaseをこのownerだけへ`--loaded-idle-only`で適用し、loaded SHAを確認する。その次の自然runで、修正済みcontext compilerを通過したか、`remote_builder`の理由とeffect/readbackを確認する。provider容量が再現する場合は既存fallback policyをreadbackしてから判断し、手動wakeしない。
2. Coconala Applyの既存fenceについて、同一occurrenceのdurable run→pass linkageと公式応募履歴を結合する。結び付きを証明できなければfenceを保持し、再応募しない。
3. 2が安全に閉じた後、既存Coconala Storefront ownerの自然runと公式listing readbackを確認する。公開中listingを重複作成しない。
4. Lancers rows 25–27は`waiting_external`のまま飛ばし、active ownerのWAF worktreeへ介入しない。CAPTCHAが続く場合も再試行しない。
5. CrowdWorks/Mercorは既存ownerのleaseと最新公式readbackを引き継ぎ、funded contractに結び付くApplication→必要なNegotiate→Paid/deliveryだけを閉じる。effect-unknownは公式証拠なしに再送しない。
6. Freelancer/Upworkは既存adapter・retired labels・Upwork browser-owner差分を読み、他ownerのlease解放後にfresh-main worktreeで不足するmanaged ownerだけを実装する。account-bound inventory、funded contract、公式receiptが揃うまでprovider mutationしない。
7. Storefrontが使える各platformの掲載・公開readbackを整え、既存host/setup契約でcloud availabilityを有効化する。自然runとprovider readbackが揃うまで24/7とは数えない。
8. 各platformでbuyer-visible納品、settlement、fee/actual cost、重複0を同一contract/occurrenceに結び、残る`unknown`を実データで解消する。その後に限り後段のSelfBuild cursorへ進む。

統合SSOT writerのleaseが有効なため、この変更ではcanonical SSOTを編集しない。lease解放後、上記のギグ証拠だけをSSOT writerへ渡し、正本へ反映する。

TODO ordering remains owned by `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`.
