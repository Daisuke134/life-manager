# HelpSteer2 train27 PRIVATE SFT implementation plan

2026-10-23 / finite source scope adopted。Status: SOURCE_SCOPE_ACCEPTED_FINITE_TRAIN27_ONLY at 2026-10-23T19:59:07.182754+00:00; final integration R2 PASS (0 findings); G6/G7 NOT_ACCEPTED; training/evaluation NOT_AUTHORIZED。科学protocolと先行metadataのPENDING/HOLDは準備/freeze時snapshotで、現在の有限source受入は下記実イベント、実行authorityは独立root所有0400 execution config/receiptの実受入記録で判断する。この計画の納品/metadata準備は実装・権利受入・学習開始ではない。[有限研究scope](../specs/2026-10-23-finite-private-sft-research-start.md)を規範とし、正規task台帳は既存のまま使う。rootがscope/right/source/runtimeの採否と統合を所有する。

## Actual G0 source event

実受入UTC: `2026-10-23T19:59:07.182754+00:00`。Actor: Codex root AI engineering/research reviewer within standing owner development authorization。これは人の法律/倫理/IRB/運営署名ではない。rootはexact27 PRIVATE completion-only SFTの有限source scopeを `SOURCE_SCOPE_ACCEPTED_FINITE_TRAIN27_ONLY` として実採択した。全V002/全V003の受入・一般化・安全性・live/人便益は別のtodo/HOLD/NOT_MEASUREDで、113 IDs=83 done / 20 todo / 10 skippedと元依存は変えない。

実判断receipt `root-actual-g0-scope-and-eval-science-acceptance.json` SHA256 `b7e61946f0164cdf517b8445698952a16b6d0012c4ded0496b0ec2e0d53573fb`、8source payload適用照合のproof `root-g0-eval-actual-application-proof.json` SHA256 `948daeddf8ece138f54bed4d99c4ccdb9459107af335b08489bbdcb0d7e99c26` を私有保存する。先行独立scope design R2 clean、scientific source Task1 clean、training code Task2 writer-fix R2 clean、評価metadata Task1 cleanを根拠とし、whole R1唯一の段階順序findingの修正をrootが読み受け入れた。**最終統合R2は0 findings / 0 blocking、SPEC/QUALITY/INTEGRATION PASS。** 実報告SHA256 `ca1fbe23a8bf2adeab244edc108959db7b6d573a8a060fee6ca6c99e47a0a0a9` を記録する。実G6/G7開始は受け入れていない。

条件付き評価用途判断を反映したprospective固定評価科学定義 `cb7d6cebf90549e8fa17b8cb393efaa00cdcd4783d9cb4edaf3da343533ac2f9` と別rights record canonical `088f6cc5a17f8ff3c83dfc10b44bca70dbd0855d3dd0c8b1063727ff2271225d` は、未学習・adapter未作成・未採点の時点でsource採択しprospectively freeze済み。実adapterの存在やG7実行受入をこの事前科学freezeの前提にしない。training science `eb2e585321d954d507af52b1bf71db9eb3b7ae3150273484909b6aeeae48a53d`、manifest、旧dev/training rights、旧receiptは不変。科学protocol/先行metadata内PENDING/HOLDはfreeze時snapshotであり、現在source受入や実行authorityそのものではない。

**G6_start=NOT_ACCEPTED / G7_execution=NOT_ACCEPTED。** 学習/backward/optimizer/adapter/HelpSteer2 final採点はNOT_RUN。最終exact-source公式CI、実resource/watchdog、外部root所有0400のevidence/bindingsとG6一attempt実判断が依然必要。G7は実学習/通常save後、正常終了と全save/fsync/inventory/hash・単一adapter固定、評価code/CI/resource/外部0400/別root実判断を採点前に受け入れる。今回の有限source/評価science採択は実開始権限を生まない。

## 全体制約とreview focus

- Sourceはcanonical Life Managerのみ。旧strict8 dev evaluator/protocol/rightsとreceipt、旧32 NOT_READY・除外5、QC曝露済みfinal16を保存する。別V001受入の現在status/算術は正規台帳へ従い、過去snapshotへ巻き戻さない。本SFTだけで全V002/V003やV004/D016をdoneにしない。
- exact27 chosen元候補だけのcompletion-only SFT。no refill/split移動/justification/非選好target/dev-final training/few-shot/retrieval/new generation。raw/processed/tensor/adapterはGit/stdout/publicへ出さない。0700/0600/umask077、metadata-only durable receipts。
- 標準Qwen3/PEFT/TRL/SFTTrainer、既存Source/strict JSON/hash/mask/choice/summary/atomic-writer/own-process watchdogを再利用する。新trainer、optimizer loop、framework、source registry、resume system、production routeを作らない。
- 一CPU2/BF16 recipe/初期adapter/attempt、累積900s/6GiB RSS polling、retry/resume/延長/new paid resource/networkなし、他MLと非並行。実fit/time/peak/infra costは測定までUNKNOWN。実disk余裕とACL/保存失敗を検査し、disk quotaは追加必須にしない。
- Review重点はsource/gold/chosen結合、旧rights全object不変、hash循環なし、mask/native collator一致、stage-specific UNKNOWN、optimizer集合/finite gradient時期、global_stepと数値変化/保存の分離、final曝露/隔離、失敗・無変化の正直な記録。

## Task1: metadataと独立したsource adoption

このTask1のowned範囲と1–5は先行metadata準備時の手順として保存する。現在の有限source/評価science受入は上記Actual G0 source eventに従い、最終統合R2は上記実報告でPASSだが、残る実行条件を受入済みとはしない。

Owned source: 本plan、scope、新[train27 manifest](../../experiments/behavior-model/helpsteer2-train27-manifest-v1.json)、新[private SFT protocol](../../experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json)、[source-rights](../research/source-rights.json)への一record appendのみ。Private準備はsourceへapplyしない。

1. Reviewed R2の用途限定routeを現在source SPEC/scope/parent planと整合させてrootが採択・独立reviewを記録する。限定V001設計受入は別イベント。旧literal未達/history/dependenciesは保存する。
2. 原root compact proposal/numeric intakeから27 retained/8 dev/16 final・除外5、exact/canonical prompt/両response hash、54 train quality joins、27 choice符号/hash、token/mask長を固定する。旧proposalを上書きしない。final chosen labels/raw textを追加しない。
3. native source-rights.v1へ目的限定recordを一つappendし、旧recordsのbyte/canonical/object意味を保つ。実root AI工学reviewerの限定用途判断と既存AI QC採用による以前のpending解決、actor/UTC/risk/private receipt basename+SHAを反映し、study_read/local_research/private_exploratory_sftを条件付きとした。human/raw manual reviewや全第三者clearanceは主張しない。有限G0 sourceと別評価科学定義/用途のsource採択は上記実イベントに記録済み。これはprotocol/code/CI/resourceの全実行受入やG6/G7実開始判断ではなく、最終統合R2は0 findings/PASS。exact-source公式CI・実resource/外部0400と実G6/G7が依然必要。
4. Manifest → rights record(manifestをpin) → 静的科学protocol(manifest/rights canonical SHA、recipe/data/native-helper/package/期待stage述語をpin) → consumer built-in expected protocol SHAと独立root所有0400 execution config/receiptの順に結合する。実rights判断とmanifestをprotocol freeze前にfinalizeできる。後から生じる新core/script/watchdog hashes、final source commit、CI、G0–G6/start/resource実受入は外部config/receiptだけがprotocol SHAへ一方向にpinし、protocol自身やrightsへ逆pinしない。protocol内PENDING/HOLDはfreeze時snapshotでcurrent authorityでも永久拒否literalでもない。preimportは外部実root受入/pinsの存在・一致とconsumer built-in scientific protocol SHAを両方要求し、caller-only hash/再承認で科学bytesを差替えない。本準備では外部configを作らない。
5. Bounded stdlib metadata静的照合と5path patch apply-check、旧record不変/隔離/リンク/hashcycle/schema/stages確認。これはML/学習/test実行ではない。rootがsource監査/統合を所有する。

## Task2: test-first native training entry

New paths relative products/manager/: `manager_core/helpsteer2_candidate_sft.py`, `scripts/train_helpsteer2_candidate_sft.py`, `tests/test_helpsteer2_candidate_sft.py`。必要時だけ既存`manager_core/helpsteer2_candidate_eval.py`のrun_local内native encode closureを小さいshared rendering helperへ抽出し、dev regressionを保つ。len8/dev-only validatorを汎用化して学習へ流用しない。

まずsynthetic stdlib RED/GREENで、gate/rights/protocol/built-in expected hash/source/membership/choice/duplicate/split/privacy不正がoptional importより前に拒否されることを検証する。fictional27 source rowsでnegative strength→candidate1、positive→candidate2を復元し、人labelをcaller指定で差し替えない。fictional tokenでprefix mismatch/EOS数/full>256/prompt/EOS後/pad/shift境界を意味のある失敗例として検証する。fake lifecycle/writer故障でpartial backward/step skip/global_step/未到達/save例外/killをfalse COMPLETEDへしない。

既存installed APIはTRL0.23.1 `SFTTrainer(...,processing_class=tokenizer,peft_config=LoraConfig(...))` と `SFTConfig(max_length=256,dataset_kwargs={"skip_prepare_dataset":True},completion_only_loss=True,assistant_only_loss=False,packing=False,padding_free=False,loss_type="nll")`。未wrapのlocal native modelを一回渡し、別get_peft_modelで二重wrapしない。既存native renderingのprefix/fullを使い、検証したCompletionMaskから`input_ids`と0/1 `completion_mask`を作る。skip_prepare_dataset時の長さ上限はentryがfail-closedで検査する。standard collatorのright pad/labels/attention一致は合成textのみで、optional importが許されるsource検証段階に確認し、real-data backwardをpreflightと偽装しない。

固定recipeはprotocolのexact base/tokenizer8 assets・source4 artifacts・installed6 packages、CPU2 BF16 eager/use_cacheFalse、q_proj/v_proj r8 alpha8 dropout0/biasNone/標準init、標準PEFT FP32 adapter昇格、AdamW2e-4 constant/wd0/warmup0/clip1、seed/data_seed42、batch1/accum4/oneepoch27/max_steps=-1/no checkpoint。標準objectiveはaccumulation window内valid-token平均で、per-candidate均等meanの直接最適化ではない。標準seeded samplerを使い、actual row順は未観測ならNOT_OBSERVED。

G6内runtime順序:

1. PREIMPORTでconsumer built-in scientific protocol SHAを照合し、独立root0400 execution config/receiptにある実G0–G6/rights/code/CI/source commit/resource受入・具体的pinsの存在と一致を要求する。科学protocolのmodel/tokenizer/package/manifest/recipe/privacy/期待述語も照合し、protocol内snapshot pendingをcurrent authorityや永久拒否literalとして扱わない。
2. 許可されたnative load/tokenization、単一standard trainer+PEFT/optimizer構築後、初backward前に27 masks、adapter-only実names/count/dtypes・初期finite tensor・optimizer集合一致を記録し、初期trainable cloneを私有保存する。gradient実測はここで要求しない。
3. standard Trainer.train一epoch。`on_pre_optimizer_step`はbackward/clip後・optimizer前なのでここで全trainable gradientの存在/finiteを検査し、None/nonfiniteはそのstepを止める。これは実学習である。
4. on_substep_end/on_optimizer_step/on_step_endから実観測下限、step return/公開step_was_skipped(なければUNKNOWN)、global_step、正常train return/7予定機会(4×6+3)を別記録する。callbackはrow ID/各raw loss/完全な消費順を提供しない。global_stepは成功update証明ではない。
5. 正常train return/予定機会検証後に標準`Trainer.save_model(private_dir)`一回。save_strategy=no。on_train_endは保存証明でなく、direct save_modelはon_saveを発火しない。tokenizer・training_args.binを含む全実inventory/size/hash/ACL/fsyncを記録し、pickle loadなし。final有限tensorと初期/最終数値比較、artifact manifest/hashを別にfreezeする。不完全保存をCOMPLETEDへせず、数値無変化は測定陰性として保存する。

CLIは既存dev薄CLIのexplicit required paths/固定redacted error/atomic0600 metadata形状を再利用する。receiptはtemporary flush/fsync→replace→directory fsync。watchdogは外側でown process-group累積wall/RSSとTERM/KILL/reap/exit/signal/cleanupを保存する。中断時の最後のdurable eventを実到達下限として扱い、未到達/nullを0へしない。新trainer/独自optimizerは不要。

## Task3: separately frozen fixed-adapter comparison

条件付き評価用途判断を反映した[prospective dev8/final16評価科学定義](2026-10-23-helpsteer2-fixed-adapter-eval.md)は独立reviewを経て、G6実学習・adapter選別・モデル採点より前の2026-10-23T19:59:07.182754+00:00にrootがsource採択・freeze済み。この事前固定には実adapterの存在もG7実行受入も要求しない。trainingと分離した薄いoriginal-candidate evaluation extension/CLIの実装と実artifact受入は別段階で扱う。既存dev-only entryは保つ。meaningful synthetic lifecycle/pair/null/privacy tests、標準PeftModel eval/disable_adapter contextのnative source確認を行い、generation/optimizer/post-final tuningは入れない。

事前のmethodは既存mean completion-token NLL/EOS-inclusive mask/hash tie-breakを再利用し、base/固定adapter/短候補rule/NO_ACTIONをdev8とfinal16別々に比較する。base48+adapter48=96 candidate forwards。同じ元ID、assigned/valid/failure/missing/abstain分母とpaired差を報告する。rule/NO_ACTIONはmodelなしNLL=null、NO_ACTION accuracy=null。害/圧力/依存/行動変容はnull、人便益NOT_MEASURED、P0に限る。

上記の評価科学定義/用途の事前固定後、G6実学習/通常saveが正常に戻ったことと完全save/fsync/inventory/hashを検証して単一adapterを固定する。モデル採点より前に、別の評価code独立review/必要検証/公式CI・実resource・外部root所有0400 bindings・final未モデル採点/未学習とQC曝露履歴再確認を受け入れ、rootが実G7開始を別判断する（現在pending）。実adapter/final code/CI/resource/G7の後続hashは外部receiptから凍結評価科学protocolへ一方向に結び、科学定義へ逆pinしない。候補900s/6GiB評価budgetは別にprospective確定し、実resource受入と区別してtraining budget延長にしない。final結果による設定/候補/閾値/adapter選別はせず、変更は別versionと別holdout。training rights/G6はfinal評価権限を生まない。

## Task4: root verification, execution and integration

Rootはfresh combined source review、適切なfocused/full configured tests、secret scan、source-boundaryのtruthful disposition、named nonforcepush/PR、exact-head official CIを受け入れ、immutable code/versionとprivate runtime config/watchdog/actual resource receiptをfreezeする。これらはmetadata準備の完了と別で、実training前に必要である。

Root G6が固定述語を含む一attemptを許可した後、その観測/通常saveのための二度目のユーザー承認は不要。実行失敗もreceiptを保ち、report修復のため再実行しない。実training/artifactの独立検証、G7の別評価実行・失敗/算術/source検証、fresh broad reviewの後でのみpublic aggregate/spec/plan/正規台帳を必要範囲で更新し、authoritative remote readbackで確認する。単にadapterを作れたこと、小Nの一致率や陰性結果を、全V003・live・行動変容・便益の受入へ変換しない。
