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

- 確認時刻は2026-10-08 01:46 JST。最新immutable main releaseは`c5c4d791`。`hf-gig-paid-direct`は`0de29b35`をロード済みだが、自然runは`host_admission_deferred:disk_headroom_low`、`effect=not_applicable`、receipt/readbackなし。`df -Pk /`の空きは約1.26 GiB。別ownerのdisk-cleanup loopも`entrypoint_exit_1`で、別worktree leaseが有効なため、ここからhost stateやそのworktreeを変更しない。
- `~/gig/evidence/paid-direct-live/latest.json`の01:37 JST readbackは`status=pending`、`observed=3`、`actionable=1`、`effect=0`、`readback=2`、`failed=0`。00:47 JST reportの`failed_step=remote_builder`と00:57 JSTのread-only DM preflight timeout（`dm_collection_unavailable`, returncode 124）は、その後のreportでまだ更新されていない。納品・入金は確認されていない。
- 公開中[Coconala service page](https://coconala.com/services/4313100)は¥3,000、表示販売実績1件。これは掲載面が存在する証拠であり、Storefront loopの実行、新規販売、settlementの証拠ではない。`hf-gig-apply-direct`と`hf-gig-storefront-direct`には既存effect-unknown fenceが残り、`hf-gig-apply-reconcile`のprocess passだけでは解除できない。
- 現行mainのproduct-loop catalogはCoconala、Lancers、CrowdWorks、Mercorの4 loop。Freelancer/Upworkにmanaged product loopはない。Upwork公式Project CatalogとFreelancer公式Freelancer Servicesは定額サービス掲載面を持つ（[Upwork公式ガイド](https://support.upwork.com/hc/en-us/articles/360057397533-How-to-create-a-project-in-Project-Catalog)、[Freelancer公式FAQ](https://www.freelancer.com/faq/topic.php?id=52)）。これはstorefront機能の証拠で、当アカウントの掲載・購入・入金を示すreadbackではない。
- Upworkの既存9233 Chromiumは`ai.anicca.provision-browser.upwork.dais` labelとowner receiptで稼働中。current mainには別の`upwork-revenue-browser` jobはなく、重複ownerを追加しない。`upwork:dais` identity lease経由でProject Dashboardを読んだ結果、login/verification redirectなしでProject Catalog UIを確認したがlisting card/countは取得できず、掲載状態はunknown。掲載・応募・返信・決済effectは0。
- PR #6945は`scout.py`がregistered identityの`CLOAK_CDP_BASE_URL`を使う修正だけへ絞る。9233 listenerを新規起動せず、Upwork catalogのaccount readbackを続けるためのendpoint修正である。
- Lancers rows 25–27は`waiting_external`を維持し、認証・solver・応募を再試行しない。CrowdWorksにはStorefront loopがなく、CrowdWorks/Mercorの既存Application/Paidにはowner別のofficial-readback/effect-fenceが残る。
- 4つの既存gig product loopはすべてcloud availabilityが`setup_required`。現在の状態から24/7 cloud稼働を主張しない。
- この参照laneはgig platformだけを扱う。CFO A5–A10、CAPFY、SelfBuildは別ownerの範囲。reply-only/回答だけの作業は進めず、特定のfunded contractを進めるのに必要な顧客連絡のみ対象にする。

## Remaining（gig担当lane内。統合SSOTの全体順序は変更しない）

1. disk-cleanup ownerがheadroomを回復した後、Coconala Paidの次の自然runでcontext compileとbuyer-visible delivery gateを確認する。手動wake、browser restart、任意削除、別ownerのworktree編集をしない。
2. Coconala Applyの既存fenceについて、同一occurrenceのdurable run→pass linkageと公式応募履歴を結合する。結び付きを証明できなければfenceを保持し、再応募しない。
3. 2が安全に閉じた後、既存Coconala Storefront ownerの自然runと公式listing readbackを確認する。公開中listingを重複作成しない。
4. PR #6945のrequired checksを通し、`scout.py`のregistered endpoint修正をmainへ統合する。Upwork 9233は既存`provision-browser` ownerとreceiptを再読し、二重起動しない。Project Dashboardのlisting status/countは未確定。
5. Freelancer Servicesのaccount-bound listing/inventoryを確認し、既存adapterとmanaged ownerが不足する部分だけを実装する。listing copy/pricingは既存成果物と市場readbackから作り、settlement evidenceなしに売上扱いしない。
6. Lancers rows 25–27は`waiting_external`のまま飛ばし、active ownerのWAF worktreeへ介入しない。CAPTCHAが続く場合も再試行しない。
7. CrowdWorks/Mercorは既存ownerのleaseと最新公式readbackを引き継ぎ、funded contractに結び付くApplication→必要なNegotiate→Paid/deliveryだけを閉じる。effect-unknownは公式証拠なしに再送しない。
8. Storefrontが使える各platformの掲載・公開readbackを整え、既存host/setup契約でcloud availabilityを有効化する。自然runとprovider readbackが揃うまで24/7とは数えない。
9. 各platformでbuyer-visible納品、settlement、fee/actual cost、重複0を同一contract/occurrenceに結び、残る`unknown`を実データで解消する。その後に限り後段のSelfBuild cursorへ進む。

統合SSOT writerのleaseが有効なため、この変更ではcanonical SSOTを編集しない。lease解放後、上記のギグ証拠だけをSSOT writerへ渡し、正本へ反映する。

TODO ordering remains owned by `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`.
