# Life Managerの順序付きpatch実行計画

> 実装時はsuperpowers:executing-plans。今回は文書のみ。順序/status/cursorは統合specだけへ記録する。

**Goal:** whole-life/proactiveという製品哲学を保ち、ChatGPT契約一つの新利用者が選択agentを起動し、account→仕事/商品→正式結果→実収入まで進む経路と、成功の再利用・利益改善を成立させる。
**Architecture:** 既存bootstrap/Codex transport/catalog/marketplace-core/provider adapter/CFO/recovery/evalを使う。業務判断はagent、identity/金額/hash/receipt/重複/資源は既存contract。新harness/scheduler/会計ledgerを作らない。
**Tech Stack:** 既存Bash/Python/Node、stdlib、既存focused tests。追加のmodel契約/API-key transportを必須にしない。
**Spec:** ../specs/2026-09-25-life-manager-unified-ssot.mdの「whole-life哲学と実装順」。source基準13f59bca114e48e284b3b55fee1c1f450c66b2c0。実装前に最新mainの同functionを比較し、既済修正を再実装しない。

## Global Constraints

- 現在のF2→F5、各laneのowner/lease/cursorを保持する。今回provider/auth/install/release/applyは0。
- effect unknownは公式結果を取るcursor。証拠前の解除/再送は0。
- public profileだけを変更し、private production routingとUIのmodel選択を一括変更しない。
- credential/session/customer assetはGitへ置かず、新userへDaisのものを移植しない。
- ChatGPTは推論の必要契約。本人/税/payout/市場の実費条件を追加model契約と混同しない。

## Review Focus

一accountのquota失敗（S03）、未選択/他userの起動（S04/S05）、保存失敗後のunknown保持（S01）、正式納品とanswerの混同（S07）、private顧客情報/自分のgrader変更（S10/S11）。各caseのREDまたは既存回帰を下の担当patchへ結ぶ。

## 実装開始の分類

SOURCE_ACCEPTANCE=source済み、自然採用/公式結果待ち。PATCH_READY=対象差分とREDを決めた設計。EVIDENCE_FIRST=次probeは決まったが原因未確定のsource変更は始めない。この分類を曖昧な「全部直す」へ置換しない。

### S00 — 製品の意味を戻す（文書）

**Files:** README日英proposal、適用時README.md/README.ja.md。
- [ ] whole life、proactive、身体/心/お金、時間/心の余裕/収入、missionを冒頭へ戻す。workflow/stateを価値提案にしない。proposal修正は今回実施。
- [ ] 日英の意味・全18name・command・North Starを確認。本文適用はsourceに一致するstartup範囲と同じ差分で行う。

### S01 — F2の既存修正を閉じる（SOURCE_ACCEPTANCE）

**Files:** 読取runtime/loop/fence_reconcile.py::_lost_terminal_unknown_occurrences/_closure_proof/reconcile、central_cleanup.py::scratch_gc。既存test_fence_reconcile.py。
**Interface:** 同owner/run/occurrence/releaseのevent＋official proof→verified closure。proof欠落はhold。
- [ ] 最新specのsource/loaded SHA/自然runを読取。同修正のcodeを再び書かない。
- [ ] registered adapterで同occurrenceの公式結果を結び、closure後だけ終了済み・参照なしscratchを既存sweepへ渡す。
- [ ] 既存lost-terminal/unknown回帰と自然closure/正式receipt保持を確認。足りないbinding/provider IDを記録し、DB手修正/再送0。

### S02 — F5のwriter往復（EVIDENCE_FIRST）

**Files:** runtime/loop/central_cleanup.py::scratch_gc、lm_loop_run.py、実測で特定したproducer entrypoint。runtime/loop/tests/test_loop_cleanup.py / test_loop_scratch.pyの関連case。
- [ ] 三自然cycleでowner+PID+run+path+bytes→parent/child終了→次sweep→商品/receipt保持を結ぶ。
- [ ] 閉じた参照なのにGC拒否ならscratch_gc、child残存ならそのproducer teardownへ一つのREDを置く。先にproducer名を推測しない。
- [ ] 最初の不成立functionだけ最小修正し、同fixtureと三cycleでlost/duplicate/manual cleanup0。容量bytesだけでDoneにしない。

### S03 — public ChatGPT-only設定と実読込（PATCH_READY、auth/model継承probeを先行条件）

**Files:** Create runtime/agent-runner/oss_config.py。Modify apps/job-search-loop/job_search_loop/local_setup.py::install/provider_authenticated、scripts/runtime-paths.sh、install-oss.sh。Gigはcoconala_onboarding.configure、gig_release.plist_for、launchd-jobs.jsonの既存override。runnerはresolve_provider_profiles/provider_process_env/command_for/runを再利用。
**Interface:** build_public_config(base_config:dict, *, auth_file:str, automation_home:str, model:str|None=None, effort:str|None=None)->dict。profile_alias=owner一件、Codexだけ、account_fallback_next=false、authはuser-owned参照。既存configはprivate runtimeへ残す。
- [ ] S03.P0を最初に閉じる: ChatGPT/API認証の安定識別と、user config/modelの読込契約を確認する。識別できない時はAUTH_MODEL_CONTRACT_REQUIREDを保持し、判定field/継承方式を推測してpatchを始めない。
- [ ] 生成器の差分: baseをdeep copyし、providersはcodexだけ、profilesはownerだけ、account_profile_order=[owner]へ置換。deterministic classの空候補は保持。他classは先頭Codex候補を一つ選びprofile_alias=ownerへ、他account/provider候補を除く。Codex候補のないclassはcodex_candidate_required:<class>で明示拒否。baseの固定model/effort/auth/proxy参照を公開設定へ持ち込まず、model/effortは利用者が明示した値だけ設定する。元baseを変更しない。
- [ ] 公開生成器はsource13fでは未実装。古いJob専用configを参照するだけではprofile_alias不足で失敗するので、現resolver形式へ生成する。
- [ ] provider_process_env/command_forに新transportを作らない。生成pathをAGENT_RUNNER_CONFIGと各実child引数へ同じ値で渡す。共有configのacct1/acct2/他社候補をpublicに使わない。
- [ ] auth判定はlogin statusのexit0だけでChatGPT/APIを同一視しない。vendorの安定metadata契約をsource/公式仕様で確認してからprobeを実装。秘密を出力せず、API認証はchatgpt_auth_required、未認証は公式login待ち。
- [ ] public候補のmodel未指定をruntime既定へ任せ、既存明示modelは保つ。--ignore-user-configと保存されたUI選択の継承を先に隔離probeで確定し、UI/global設定を上書きしない。
- [ ] RED名: test_public_config_has_one_owner_profile_and_only_codex_candidates、test_public_single_profile_quota_failure_never_launches_claude、test_public_runtime_paths_use_generated_config、test_api_key_auth_is_not_chatgpt_ready、test_public_candidate_without_model_does_not_add_model_override。
- [ ] Assert: 一profile、別account/provider呼出し0、生成/読込path一致、未認証/不適合はtyped wait、未指定model強制0。GREENはtest_codex_account_failover.py、Job test_local_setup.py、Gig test_money_loop_onboarding.py。実login/inferenceは別受入。

### S04 — 一command選択/dispatch（PATCH_READY）

**Files:** scripts/bootstrap.sh、install.sh、既存product-onboarding-plan.jsとproduct-onboarding.js::planProductOnboarding。Test product-onboarding.test.js/install-coconala-dispatch.test.mjs。
**Interface:** {host:local,selected_loop_ids:[id],verified_requirements:[]}→既存product.onboarding.v1。syntax不正はnetwork前、未知IDはcatalog取得後もprovider/setup/owner開始前に拒否。
- [ ] --loop <catalog-id>/--plan-onlyをparseし、未指定GUIを保つ。--allを追加しない。canonical IDを既存legacy installerへ結ぶ。
- [ ] pure plannerはreadonly。plan-onlyはinstaller0、未完成packageは具体的stageをsetup_requiredへ。
- [ ] RED: test_selected_loop_dispatches_once、test_unknown_loop_starts_nothing、test_plan_only_never_calls_installer。mock deps/provider/owner呼出し数とstateをassert。syntax/helpと同focused testでGREEN。

### S05 — 新端末account/identity/persistent owner（PATCH_READY）

**Files:** integration-onboarding.py::load_manifests/graph、life-manager-onboarding-server.py::_graph/_connect、integrations/*.json、Connector/Fundraiser installers、Job catalog requirements。Test install-connector-dispatchと既存onboarding。
- [ ] Coconala一manifestのgraphを同catalogへ結ぶ。未選択はmetadataだけ、選択loopだけpreflight/readiness/activation。
- [ ] 既存deps/browser provisionを使いuser identityを準備。interactive:daisを必須にしない。GUI読取はlaunchctl-safe、非Macをloaded=len(owners)でreadyにしない。
- [ ] RED: test_new_user_never_uses_dais_identity、test_unselected_loop_never_runs_preflight、test_gui_unavailable_does_not_probe_domain、test_non_macos_is_not_fake_loaded。own setup proofなしはready0。
- [ ] JobのTelegram任意/必須を実transport契約で統一。新supported deviceで同command→公式account setup→selected owner→自然仕事/公式結果→停止/再開を確認。追加model API keyを必須にしない。

### S06 — 未照合・account/inventory（EVIDENCE_FIRST）

**Files:** application_parent.py::_runtime_occurrence_binding、application_occurrence_reconcile.py::build_provider_proof/reconcile_occurrence、storefront_pre_effect_reconcile.py、coconala_reply_effect_reconcile.py。Lancers work_sync.py::read_paid_inventory/run_tick、paid_adapter.py::_inventory。CrowdWorks application owner/paid adapter。Freelancerはskills/earn/gig/scripts/freelancer_readiness.py、freelancer_bid_watch.py、providers/freelancer_transport.py / freelancer_paid_adapter.py。
- [ ] Apply occurrence→request intent、Storefront stdout/runtime→listing、Reply body hash→message IDを公式に結ぶ。既存関数で足りればproof取得を進め、比較を緩めない。
- [ ] account/inventory失敗は同runの最初に不成立なresponse/identityを特定して、そのadapterだけにREDを置く。古い一覧/solver pendingをlive認証へ置換しない。
- [ ] Freelancerはregistered/readiness、正式bid receipt、message/negotiation、funded work、正式納品の各境界を同じ表へ記録。未登録agentはcatalog追加条件を満たしたreceiptから登録し、READMEへ手で第二の一覧を作らない。
- [ ] 反例がない時はcode差分を作らず、次readbackと必要ID/fieldまで記録する。解除/再送0。

### S07 — 共通Paidで正式納品まで（EVIDENCE_FIRST）

**Files:** marketplace-core/scripts/paid_handoff.py::build_paid_handoff、paid_kernel.py、各paid_adapter.py::_inventory/mutate。既存contracts/paid tests。
- [ ] funded価格/期限/成果物/品質をhandoffへ結び、制作→正式納品→受領→精算を別receiptで閉じる。
- [ ] RED: test_paid_handoff_requires_exact_funded_terms、test_formal_delivery_is_not_answer_receipt。answer/PASS/5pending/0 open ordersをincomeへしない。
- [ ] Mercor human submission gateを削る前に、agent作業/提出の許可と実surfaceを取る。本人になるinterview/identityと成果物の受託を分ける。自然receipt/受領/精算/replay-zeroがDone。

### S08 — Storefrontの共通offerを積む（proof後PATCH_READY）

**Files:** skills/gig-work/profile/listings/catalog.json、storefront_direct.py::run_once、test_storefront_catalog_grounding.py、既存contracts/application/reply/paid kernel。
**Interface:** 実証済みscope+価格/期限+原価/品質→canonical offer→薄いprovider listing projection。
- [ ] 最初の正利益/納品能力を確認した一offerをnative listingへ。S06のproof後だけmutation。未完成Web/App factoryを売らない。
- [ ] RED: test_offer_projection_keeps_scope_and_deliverable_hash、test_unverified_factory_cannot_be_listed_as_complete。同scope/品質versionを投影でも保持。
- [ ] 新市場ではadapterだけ追加し、応募/返信/納品/receipt/会計をコピーしない。FROZEN sellersは保持する。

### S09 — Capafy/CFOの利益結合（EVIDENCE_FIRST）

**Files:** capafy_hourly_reconcile.py::_inventory/_window_totals/_fetch_agent_stats_windows、inventory_status.py::normalize_agents、既存distributor/event adapters、skills/cfo/adapters/marketplace.pyとfinancial/scorer tests。
- [ ] 既済goal/funnel/slot修正とloaded版を比較。EX_CONFIGはexact config path/profile/errorを取得後に差分化し、既済修正を重ねない。
- [ ] RED: 同入力slot定義一致、FROZEN sellerが60件枠外に落ちない、売上日と取得日が別、欠測fee/costでpositive netにならない。
- [ ] S09.P0 / HOSTED_INFERENCE_CONTRACT_REQUIRED: skills/capafy-autopublish/scripts/drive_checkpoint2.pyはBASE_URL=OpenRouterとCAPAFY_HOST_OPENROUTER_KEYを要求し、build_config.pyもprovider=openrouter.aiを生成する。LMのCodex認証と、売った商品のhosted実行を別依存として記録する。sourceにはChatGPT-only hosted対応を確認できない。Capafyが正式に支持する実行方式/課金/所有者を確認してから、その実方式だけへadapterを変更する。未確認のCodex proxyや無料化を発明しない。純ChatGPT契約の新利用者でこの経路を閉じる証拠がなければ、Capafyをsubscription-only readyと表示しない。
- [ ] RED: test_hosted_api_key_dependency_is_not_chatgpt_only_ready。公開catalog/plannerへこの欠落を既存setup_requiredとして渡し、無関係なGigの起動を止めない。
- [ ] publication→slot/CT→paid→refund/actual fee/payout→全実費を同期間/通貨/IDでjoin。20%仮定/別期間cost/pendingを確定利益へしない。provider実費/支払元/capを記録し追加model契約を必須にしない。

### S10 — 成功/失敗を共通skillへ戻す（観測後PATCH_READY）

**Files:** buyer_outcome_ledger.py::scan、既存CFO/event records、skills/gig-workのcanonical offer/品質/納品skill、既存Writer/DD eval。
**Interface:** official outcome+scope/工数/品質/費用→匿名lesson {symptom,wrong_instinct,correct_step,general_law,evidence_refs}。private本文/asset/credentialは対象外。
- [ ] 第二のvictory ledgerを作らず既存recordを読む。一般化できるlessonだけagentが候補化。
- [ ] RED: test_shared_lesson_excludes_customer_payload、test_missing_net_cannot_be_success_pattern、test_offer_and_quality_use_same_lesson_version。evidence不足はunknown。
- [ ] 一候補をbaseline/candidateで比較し、品質/費用/実利益を別評価。件数を成功学習のproxyにしない。

### S11 — metaの一周（EVIDENCE_FIRST）

**Files:** recovery-intent.mjs/recovery-apply-plan.mjs、recovery-self-build-bridge.js、既存dev/merge guard、platform_enrollment.py::evaluate_platform_candidate、economic-autonomy runner/scorer。
- [ ] H: 同自然障害を検知→LM内部修復→PR/main/immutable→次自然成功。I: frozen基準/同条件/actual cost→一候補→限定canary→source rollbackまたは採用、外部effectは保持。
- [ ] N/Meta: 一候補のdurable discovery→policy/adapter→適格work→official canary→owner provisioning→settlement→quality/net feedback。pure gate PASSを一周へ代用しない。
- [ ] 既存回帰へcandidate_edits_grader_is_rejected、promotion_needs_official_net、unknown_effect_never_replayedを対応付ける。全18完成待ちではなく対象証拠後。OpenEvolve quarantineを先に外さない。

### S12 — 残capability/OSS/general agent/規模

- [ ] 残るWriter/Affiliate/Mobile/eBook/LINE/Investment/Agent Economy/Job Hunter/Fundraiser/Connector/SelfBuildを同contractと既存ownerから受け入れる。factory/marketing/readback/financeを縮めない。
- [ ] 受入済み能力からpublic packageを増やし、両README/catalog/CLIを同期。19番目以降も同じaccount/品質/会計を使う。
- [ ] positive unit net/継続購入を保ってUS$10M/月以上へ。生活/身体/心/未知taskへの適応・外部再現は別評価。登録数/合成scoreをAGIにしない。


## 省略名の正確なpathと最小検証

下のpathを上のFilesへ対応付ける。既存testを使い、新RED名は列挙した既存testへ追加する。EVIDENCE_FIRSTはprobe後にその最初の不成立箇所のtestだけ追加する。

|task|変更/観測するpath|既存の最小検証path|
|---|---|---|
|S01/S02|runtime/loop/fence_reconcile.py、runtime/loop/central_cleanup.py、runtime/loop/lm_loop_run.py|runtime/loop/tests/test_fence_reconcile.py、test_loop_cleanup.py、test_loop_scratch.py、test_lm_loop_run_bounds.py|
|S03 runner|runtime/agent-runner/oss_config.py（新規）、runtime/agent-runner/agent_runner.py|runtime/agent-runner/tests/test_codex_account_failover.py（既存）、test_oss_config.py（公開設定の必要最小RED用、新規）|
|S03 Job|apps/job-search-loop/job_search_loop/local_setup.py、apps/job-search-loop/scripts/runtime-paths.sh、apps/job-search-loop/scripts/install-oss.sh|apps/job-search-loop/tests/test_local_setup.py|
|S03 Gig|skills/earn/gig/scripts/coconala_onboarding.py、skills/earn/gig/scripts/gig_release.py、skills/earn/gig/config/launchd-jobs.json|skills/earn/gig/tests/test_money_loop_onboarding.pyと既存release/manifest test|
|S04|scripts/bootstrap.sh、install.sh、apps/life-manager/scripts/product-onboarding-plan.js、apps/life-manager/lib/product-onboarding.js|apps/life-manager/lib/product-onboarding.test.js、test/install-coconala-dispatch.test.mjs|
|S05|scripts/integration-onboarding.py、scripts/life-manager-onboarding-server.py、integrations/coconala.json、integrations/onboarding.schema.json、apps/life-manager/config/product-loop-catalog.json、skills/connector/install.sh、skills/fundraiser-agent/runtime/install.sh|test/install-connector-dispatch.test.mjs、skills/connector/test/portable-install-contract.test.js|
|S06 Coconala|skills/earn/gig/scripts/application_parent.py、application_occurrence_reconcile.py、storefront_pre_effect_reconcile.py、coconala_reply_effect_reconcile.py|skills/earn/gig/tests内の同adapter回帰|
|S06/07 Lancers/CrowdWorks|skills/earn/lancers/scripts/work_sync.py、paid_adapter.py、skills/earn/crowdworks/scripts/paid_adapter.py|skills/earn/lancers/tests/test_work_sync_browser_attach_exit.py、test_paid_acceptance.py|
|S06/07 Freelancer/Mercor|skills/earn/gig/scripts/freelancer_readiness.py、freelancer_bid_watch.py、providers/freelancer_transport.py、providers/freelancer_paid_adapter.py、skills/earn/mercor/scripts/paid_adapter.py|skills/earn/gig/tests/test_freelancer_readiness.py、test_freelancer_transport.py、test_freelancer_paid_adapter.py|
|S07 shared|skills/_shared/marketplace-core/scripts/paid_handoff.py、paid_kernel.py、skills/earn/gig/scripts/coconala_paid_adapter.py|skills/earn/gig/tests/test_coconala_paid_adapter.pyと既存shared paid test|
|S08|skills/gig-work/profile/listings/catalog.json、skills/earn/gig/scripts/storefront_direct.py|skills/earn/gig/tests/test_storefront_catalog_grounding.py|
|S09|skills/earn/capafy-marketing/scripts/capafy_hourly_reconcile.py、skills/capafy-autopublish/scripts/inventory_status.py、build_config.py、drive_checkpoint2.py、skills/cfo/adapters/marketplace.py|apps/life-manager/lib/financial-record-capafy.test.jsと既存Capafy collector/slot test|
|S10|skills/earn/gig/scripts/buyer_outcome_ledger.py、既存canonical skill/Writer/DD evaluator|既存buyer outcome/各evaluator回帰|
|S11|runtime/loop/recovery-intent.mjs、recovery-apply-plan.mjs、apps/life-manager/lib/recovery-self-build-bridge.js、skills/_shared/marketplace-core/scripts/platform_enrollment.py|runtime/loop/__tests__/recovery-intent.test.mjs、recovery-apply-plan.test.mjs、apps/life-manager/lib/recovery-self-build-bridge.test.js|

再現可能なfocused command例（実装時だけ実行、今回未実行）:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s runtime/loop/tests -p test_fence_reconcile.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s runtime/loop/tests -p test_loop_cleanup.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s runtime/agent-runner/tests -p test_codex_account_failover.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s apps/job-search-loop/tests -p test_local_setup.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest skills/earn/gig/tests/test_money_loop_onboarding.py
node --test apps/life-manager/lib/product-onboarding.test.js test/install-coconala-dispatch.test.mjs
bash -n scripts/bootstrap.sh install.sh apps/job-search-loop/scripts/install-oss.sh
```

各patchはworktree/ownerを指定し、変更前の最小REDを確認してから実装する。固定済みcontractの証拠取得とsource patchを混同しない。時点が異なるloaded SHA/売上を最新状態へ読み替えない。

## 各patchのDone

RED→最小差分→focused GREEN→review/CI/main→immutable→対象自然run/official readback。金銭/effect成果はlocal testで代用しない。現在の先頭はS01/F2→S02/F5。S03–05とS06–09は依存が閉じた対象から同sourceを使い、shared file/ownerの書込を直列にする。S10/11の評価準備は並行可能、full採用は対象証拠後。順序/statusはspecだけへ。
