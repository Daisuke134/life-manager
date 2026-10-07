# ギグ契約・Storefront lane readback

> 参照用の状態証拠です。全体TODOと実行順の唯一の正本は
> [`2026-09-25-life-manager-unified-ssot.md`](2026-09-25-life-manager-unified-ssot.md) です。
> この文書は別のTODO・順序を作りません。

## 担当範囲と完了条件

Coconala、Lancers、CrowdWorks、Mercorの既存gig ownerと、将来のUpwork・Freelancer接続を扱います。CFO A5–A10、CAPFY、SelfBuild、他ownerのブラウザ・state・loopは担当外です。Lancers rows 25–27は`waiting_external`を維持し、認証・solver・応募を再試行しません。回答だけの作業も対象外です。

gig ownerの契約完了は、同一のfunded contract/occurrenceに結びついた要件・納品物hash・provider正式納品receipt・買い手検収・platform settlement/fee readback・replay-zeroが揃った時だけです。会社横断CFO joinはCFO ownerの担当です。Storefrontは公式の掲載状態と購入readbackを別々に扱い、掲載中だけで販売・入金とは判定しません。24/7はboundedな自然wakeとdurable stateで進捗する運用を指し、loop登録・loaded表示だけでは稼働完了としません。

## 前段のsource変更

- PR #6936のPaid context reference境界修正とPR #6945のUpwork CDP endpoint修正はmainへ統合済みです。PR #6945は`scout.py`が`CLOAK_CDP_BASE_URL`を使う修正で、focused testは2/2でした。
- 現在の`origin/main`は`6c9a34c163`。immutable current releaseは`20261008T015349-c5c4d791`で、mainと同じSHAではありません。source mergeはproduction loadや自然runの証拠ではありません。

## 2026-10-08 02:37 JSTのreadback

- `lm-loop health --json`: 186 jobs中、healthy 41 / running 25 / failed 34 / safely_fenced 74 / effect_unknown 9 / telemetry_gap 3。状態は自然wakeで変わるため、owner別の次の操作前に再readbackします。
- product-loop catalogに管理登録されるgig loopはCoconala 7、Lancers 7、CrowdWorks 5、Mercor 3です。FreelancerとUpworkのmanaged product loopはありません。現行4 loopのcloud availabilityはすべて`setup_required`です。
- Coconala Paid ownerのoccurrence `798461c1a4ebdc8d0db12669`は02:30 JSTに`phase=report`, `status=pass`, `effect=not_applicable`で、provider receipt/readbackなしでした。02:32 JSTの公式talkroom readbackでは1件が¥9,000・「取引中／進行中」。parserは既存artifactの買い手可視化とその後の買い手返信を観測し、feedbackを`revision`に分類しました。正式納品receiptはなく、`formal_delivery_confirmed=false`です。よって契約は未納品で、settled revenueではありません。対象projectの`.paid-effect-owner.lock`を`paid_direct.py` processが保持中のため、既存ownerのstateや納品物は編集しません。受注一覧snapshotは3件を観測していますが、一覧上の各`status`は`unknown`です。
- 公開中[Coconala service page](https://coconala.com/services/4313100)はreadback時に販売実績1件を表示しました。これは掲載・表示実績であり、このturnの新規購入、検収、settlementのreceiptではありません。
- 最新owner statusでは、Coconala Applyは02:35 JSTに`resource_effect_unknown`、Storefrontは02:37 JSTに`disk_headroom_low`でeffect前hold。Lancers Storefrontは`resource_effect_unknown`。CrowdWorks Applicationはprocess passだが`effect_status=unknown`、Paidは`entrypoint_exit_75` / `official_readback_required`。Mercor Applicationは`resource_effect_unknown`。provider receipt/readbackは未結合です。新しいpre-effect holdで古いeffect fenceが自動解除されたとは扱わず、無差別restart・再送もしません。
- LancersのWAF worktreeは`lm-cfo-observability-1002`のactive leaseです。担当外として維持します。AGMSG inboxに新着はありません。open PR #6485/#6338/#4813などは以前のsource課題であり、現在のproduction receiptの代用ではありません。
- Upwork公式[Project Catalog作成ガイド](https://support.upwork.com/hc/en-us/articles/360057397533-How-to-create-a-project-in-Project-Catalog)とFreelancer公式[Services FAQ](https://www.freelancer.com/faq/topic.php?id=52)は定額サービス掲載面の存在を示します。Upwork `Project Dashboard`は02:35 JSTにログイン・verification誘導なしで読め、「Drafts (0)」とProject Catalog UIは表示されましたが、公開listing件数は見えず`unknown`です。Freelancerのaccount-bound auth/listing inventoryも未確認です。公式機能の存在を自アカウントの出品状態と混同しません。

## 証拠境界

- `loaded` / `running` / process `pass`は契約応募・返信・納品・支払いを証明しません。
- `effect_unknown`は同じ外部effectを再実行する許可ではありません。receiptまたはno-effectの公式証拠が同一occurrenceに結びつくまでfenceを保持します。
- 掲載、応募receipt、買い手向け納品receipt、検収、売上settlementは別の証拠です。gross、残高通知、画面の販売表示をsettled netとして扱いません。
- 他ownerのlease/profile、共有checkout、顧客project stateは切替・編集・再起動しません。
