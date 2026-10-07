# ギグ契約・Storefront lane readback

> 参照用の状態証拠です。全体TODOと実行順の唯一の正本は
> [`2026-09-25-life-manager-unified-ssot.md`](2026-09-25-life-manager-unified-ssot.md) です。
> この文書は別のTODO・順序を作りません。

## 担当範囲と完了条件

Coconala、Lancers、CrowdWorks、Mercorの既存gig ownerと、将来のUpwork・Freelancer接続を扱います。CFO A5–A10、CAPFY、SelfBuild、他ownerのブラウザ・state・loopは担当外です。Lancers rows 25–27は`waiting_external`を維持し、認証・solver・応募を再試行しません。回答だけの作業も対象外です。

gig ownerの契約完了は、同一のfunded contract/occurrenceに結びついた要件・納品物hash・provider正式納品receipt・買い手検収・platform settlement/fee readback・replay-zeroが揃った時だけです。会社横断CFO joinはCFO ownerの担当です。Storefrontは公式の掲載状態と購入readbackを別々に扱い、掲載中だけで販売・入金とは判定しません。24/7はboundedな自然wakeとdurable stateで進捗する運用を指し、loop登録・loaded表示だけでは稼働完了としません。

## 前段のsource変更

- PR #6936のPaid context reference境界修正とPR #6945のUpwork CDP endpoint修正はmainへ統合済みです。PR #6945は`scout.py`が`CLOAK_CDP_BASE_URL`を使う修正で、focused testは2/2でした。
- 03:12 JSTの再readbackでは`origin/main=541d8466`、current symlinkは`20261008T024154-64c078b3`です。owner promotionは未収束で、Coconala Paid/Apply/Storefrontはrelease `64c078b3`上のprocess/host fencesが残ります。全体healthは186 jobs中healthy 22 / running 25 / failed 54 / safely_fenced 73 / effect_unknown 9 / telemetry_gap 3でした。強制apply/restartせず、各ownerのnatural terminal後に既存reconcilerの収束をreadbackします。

## 2026-10-08 02:41 JSTのreadback

- `lm-loop health --json`（02:37 JST）: 186 jobs中、healthy 41 / running 25 / failed 34 / safely_fenced 74 / effect_unknown 9 / telemetry_gap 3。02:41 JSTの`df -Pk /`は空き2.51 GiB。状態は自然wakeで変わるため、owner別の次の操作前に再readbackします。
- product-loop catalogに管理登録されるgig loopはCoconala 7、Lancers 7、CrowdWorks 5、Mercor 3です。FreelancerとUpworkのmanaged product loopはありません。現行4 loopのcloud availabilityはすべて`setup_required`です。
- Coconala Paid ownerのoccurrence `798461c1a4ebdc8d0db12669`は02:30 JSTに`phase=report`, `status=pass`, `effect=not_applicable`で、provider receipt/readbackなしでした。02:32 JSTの公式talkroom readbackでは1件が¥9,000・「取引中／進行中」。parserは既存artifactの買い手可視化とその後の買い手返信を観測し、feedbackを`revision`に分類しました。正式納品receiptはなく、`formal_delivery_confirmed=false`です。よって契約は未納品で、settled revenueではありません。対象projectの`.paid-effect-owner.lock`を`paid_direct.py` processが保持中のため、既存ownerのstateや納品物は編集しません。受注一覧snapshotは3件を観測していますが、一覧上の各`status`は`unknown`です。
- 公開中[Coconala service page](https://coconala.com/services/4313100)はreadback時に販売実績1件を表示しました。これは掲載・表示実績であり、このturnの新規購入、検収、settlementのreceiptではありません。
- `lm-loop pre-effect-reconcile hf-gig-storefront-direct --dry-run`はoccurrence `hf-gig-storefront-direct:18d8d288748508e8-23902`を`no_pre_effect_terminal`で未証明と返しました。dry-runでfence変更はありません。公開listingの存在だけではこのeffectとの同一性を証明できず、provider receiptか同一occurrenceの完全なpre-effect evidenceが得られるまで再作成・再編集しません。
- 最新owner statusでは、Coconala Apply/Storefrontはrelease `6c9a34c1`で`resource_effect_unknown`、Paid/Browserは旧releaseでloaded-running。Lancers Application/Negotiateは新releaseでも`disk_headroom_low`、Paidは`entrypoint_exit_1`かつ`effect_unknown`、Storefrontも`effect_unknown`。CrowdWorks Paid/Replyは新releaseで`entrypoint_exit_75` / `official_readback_required`、Applicationは旧releaseで`effect_status=unknown`。Mercor Applicationは新releaseのまま`unloaded`かつ`resource_effect_unknown`、Paidは`resource_effect_unknown`、Replyは旧releaseです。provider receipt/readbackは未結合です。新しいpre-effect holdで古いeffect fenceが自動解除されたとは扱わず、無差別restart・再送もしません。
- LancersのWAF worktreeは`lm-cfo-observability-1002`のactive leaseです。担当外として維持します。AGMSG inboxに新着はありません。open PR #6485/#6338/#4813などは以前のsource課題であり、現在のproduction receiptの代用ではありません。
- Upwork公式[Project Catalog作成ガイド](https://support.upwork.com/hc/en-us/articles/360057397533-How-to-create-a-project-in-Project-Catalog)とFreelancer公式[Services FAQ](https://www.freelancer.com/faq/topic.php?id=52)は定額サービス掲載面の存在を示します。Upwork `Project Dashboard`は02:35 JSTにログイン・verification誘導なしで読め、「Drafts (0)」とProject Catalog UIは表示されましたが、公開listing件数は見えず`unknown`です。Freelancerのaccount-bound auth/listing inventoryも未確認です。公式機能の存在を自アカウントの出品状態と混同しません。

## 2026-10-08 02:55–03:20 JST Coconala storefront再確認

- `listing_inventory.py collect`の公式seller-list readbackは20件すべて`公開中`。service `4313100`は¥3,000、seller inventoryの`sales_count=0`でした。以前のpublic service-page readbackは販売実績1件を表示しました。2つのreadbackが不一致なので、この数値を販売・settlementとして採用せず`unknown`を維持します。
- `18d8d288748508e8-23902`のruntime reportはoccurrence `18d8d2334ab70e80-9111`をclaimし、次run `18d8d2b3f46565c8-28218`のreportはoccurrence `18d8d288748508e8-23902`をclaimします。過去stdout receiptにrun ID/claimed-occurrence IDが無いため、時刻だけではどちらのoccurrenceにも結び付けません。local helper dry-runはこの2件とも`HELD`です。production fenceは変更していません。
- 今後のpre-effect proofは、requested occurrenceに一致する唯一のruntime report、そのreportのexact `lm-occurrence://.../claim`、同じ`runtime_run_id`と`runtime_occurrence_id`を含むStorefront stdout receipt、host admissionのowner/stateを揃えます。同一occurrenceに複数のreportがあればholdし、旧receiptにidentity fieldsが無い場合もholdします。`official_inventory_empty_or_invalid`は`pending/pass`、`official_service_contract_invalid`は`failed/fail`に厳密対応し、両方ともeffect/actionable/readbackが0であることを要求します。

## 証拠境界

- `loaded` / `running` / process `pass`は契約応募・返信・納品・支払いを証明しません。
- `effect_unknown`は同じ外部effectを再実行する許可ではありません。receiptまたはno-effectの公式証拠が同一occurrenceに結びつくまでfenceを保持します。
- 掲載、応募receipt、買い手向け納品receipt、検収、売上settlementは別の証拠です。gross、残高通知、画面の販売表示をsettled netとして扱いません。
- 他ownerのlease/profile、共有checkout、顧客project stateは切替・編集・再起動しません。

## 2026-10-08 03:18 JSTのCoconala readbackとproof契約

- 現在の`origin/main`は`541d8466`、immutable current releaseは`20261008T024154-64c078b3`で、owner適用は未収束です。`lm-loop health --json`は186 jobs中、healthy 22 / running 25 / failed 54 / safely_fenced 73 / effect_unknown 9 / telemetry_gap 3。Coconala Paidは`apply_lock_busy`、Storefrontは`resource_effect_unknown`でprovider receiptなしです。
- `listing_inventory.py collect`の02:55 JST公式seller-list readbackは20件すべて`公開中`。service `4313100`は¥3,000でseller inventoryの`sales_count=0`。既出public service pageの販売表示1件と不一致なので、販売・settlementは`unknown`のままです。
- 旧runtime run `18d8d288748508e8-23902`のreportは別occurrence `hf-gig-storefront-direct:18d8d2334ab70e80-9111`をclaimし、次run `18d8d2b3f46565c8-28218`のreportは`hf-gig-storefront-direct:18d8d288748508e8-23902`をclaimします。旧stdout pass lineにはruntime run/claimed-occurrence IDがありません。時間窓だけで別runの`pending/effect=0`行を選ぶ解除はしません。
- pre-effect proofは同一のrequested occurrenceについて、runtime reportの`owner_id`/`loop_id`/`occurrence_id`、正確な`lm-occurrence://.../claim`、storefront stdoutの`runtime_run_id`と`runtime_occurrence_id`、host admissionのowner/state/effect_unknownを全て一致させます。`official_inventory_empty_or_invalid`は`pending/pass`、`official_service_contract_invalid`は`failed/fail`との対応と`effect=0/actionable=0/readback=0`を要求し、旧receiptにidentity fieldsが無ければ`HELD`を維持します。
- `latest.json`は02:47:59 JSTの`pending/observed=3/actionable=1/effect=0/readback=2`から更新されていません。03:14 JSTのPaid runtime eventは`pass/effect=not_applicable`でもprovider receipt/readbackがなく、対象project lockも保持中です。納品・検収・settlementは未完です。
- 旧run `18d8d288748508e8-23902`の時間窓にはbusiness wake `pending/effect=0/readback=0/official_inventory_empty_or_invalid`、後続run `18d8d2b3f46565c8-28218`の時間窓には`failed/effect=0/readback=0/official_service_contract_invalid`が記録されています。runtime reportは順に異なるoccurrenceをclaimしますが、両stdout行にruntime identityがありません。時間窓だけでこの行を各occurrenceへ割り当てず、strict helper previewは両方`HELD/stdout_runtime_binding_invalid`です。
- exact run/occurrence bindingのsource修正はbranch `fix/gig-storefront-inventory-pre-effect-proof-20261008`でlocal tests 17+56 PASS、PII scan/diff check PASS、fresh read-only review SHIPです。旧2 occurrenceは新helperのlocal dry-runでも`HELD`のままです。PR #6958はCI実行中で、main merge/release/production resolutionは未実施です。

## 2026-10-08 03:28 JST control-plane / owner readback

- `origin/main=e0a92daa9bf213e6ea1d9758c1b252be978c8636`、current releaseは`/Users/anicca/loops/releases/20261008T024154-64c078b3`（SHA `64c078b34bab37d026926ef441a9322edecc45d0`）。`lm-loop health --json`の`generated_at=2026-10-07T18:28:05Z`は186 jobs中、healthy 32 / running 25 / failed 43 / safely_fenced 74 / effect_unknown 9 / telemetry_gap 3。件数はwakeごとに変わるため、この値を恒久状態とは扱わない。
- 同readbackでCoconala Applyは`disk_headroom_low`、Paidはprocess health `healthy`でもprovider receiptなし、Storefrontは`effect_unknown/resource_effect_unknown`、Replyは`disk_headroom_low`。CrowdWorks Apply/Replyは`entrypoint_exit_75/official_readback_required`、Paidは`resource_capacity_busy`。Mercor Apply/Replyは`disk_headroom_low`、Paidは`effect_unknown/resource_effect_unknown`。LancersはApplication/Storefront/Report/Negotiate/Paid/Work-syncにcapacity・effect fence・entrypoint failureが残るが、rows 25–27を今回再試行しない。いずれもprocess stateだけで応募・納品・収益を完了扱いしない。
- product-loop catalogにはCoconala/Lancers/CrowdWorks/Mercorの4行があり、4行すべてcloud `setup_required`。Freelancer/Upworkには共有PaidHandoff adapter境界があるが、gig product-loop登録、account-bound funded work、settlement readbackはまだ確認できない。既存コードやbrowser provisionerの存在だけで24/7収益loopとは判定しない。
- PR #6958のhead `b92aab7bf9aabb51af15f2bee9291c2e022a544d`ではSecurity/contract/test checksが全PASS。branchはこのreadback時点で最新`origin/main`より1 commit遅れているため、mainへ載せ直したheadのchecks完了まではmerge・release・production fence解決を未完とする。
- AGMSG `team lm --json`では`lm-gig-contract-owner-1007`と各CFO/CrowdWorks担当が登録されているが、該当席はplacement/activity `unknown`・reach `cannot`で、現在作業中とは確認できない。Worktree leaseでは別のCFO所有Lancers WAF taskがactiveのため、その範囲は変更しない。

## 2026-10-08 03:47 JST post-merge / production readback

- PR #6958はmerge commit `8dc0654954964071e83cf9c68a67846c6422e1a9`でmainに統合済み。rebase後headのfocused testsは17/17と56/56 PASS、GitHubのSecurity/contract/test checksも全PASS。自動cutは`/Users/anicca/loops/releases/20261008T034242-8dc06549`を生成し、`~/loops/current`と`RELEASE.json.sha`はmain SHA `8dc0654954964071e83cf9c68a67846c6422e1a9`へ一致、provenanceは`ancestor-of-origin-main`。
- `lm-loop health --json`の`generated_at=2026-10-07T18:47:28Z`は186 jobs中、healthy 25 / running 25 / failed 52 / safely_fenced 74 / effect_unknown 7 / telemetry_gap 3。Gigの選択readbackではCoconala Apply/Storefront、CrowdWorks Application/Paid、Mercor Paidが`disk_headroom_low`。Coconala Paidはprocess `healthy`でもreceipt/readbackなし。対象Gig ownersのinstalled/event SHAはまだ`64c078b3`で、8dc releaseをloadedしたreadbackは未取得。
- production `lm-loop pre-effect-reconcile hf-gig-storefront-direct --dry-run`は旧occurrence `hf-gig-storefront-direct:18d8d288748508e8-23902`を`resolved=[]` / `no_pre_effect_terminal`として保持。effect fenceは変更せず、Storefrontのprovider effectも再試行していない。
- disk-cleanupの18:44:31Z receiptは1,687,307,576 bytes reclaimedと記録する一方、free spaceは225,513,472→263,024,640 bytes、recovery floor 2,147,483,648 bytesは`unmet`、`inventory_gaps=23`。続く`life-manager-disk-cleanup` occurrence `18dc53946d13a908-99994`は`entrypoint_exit_1`。18:47Zのfree spaceは約251 MiBで、Gigのeffectful ownersは安全に動作できる容量を得ていない。
- release reconcilerの最新readbackはoccurrence `18dc537f702ae878-30650` / `entrypoint_exit_143`。新releaseのcurrent化は済んだが、Gig ownerへの適用・自然terminal・provider receipt/readback・replay-zeroは未確認である。Lancers rows 25–27は引き続き`waiting_external`とし、認証・solver・応募の再試行はしない。
- 03:50 JST前のread-only `listing_inventory.py collect --out -`はCoconala service 20件を取得し、20件すべて`公開中`、各public pageの`sales_count=0`。同じreadbackのlocal ledgerはpublished 10件、live ID未記録12件、ledger上のみ2件。BrowserGuard leaseはcollector終了後`holder=""` / collisions 0へ戻った。これは出品と台帳の不一致を示す観測であり、受注・settlement・収益の証拠ではない。
