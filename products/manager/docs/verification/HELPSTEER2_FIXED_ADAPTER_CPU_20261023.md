# HelpSteer2 fixed-adapter dev8/final16 — 実CPU比較結果

2026-10-23 UTC。**ONE_FIXED_ADAPTER_COMPARISON_COMPLETED / EVALUATION_RETURNED**。学習前に凍結した科学定義と、採点前に一つだけ固定した保存adapterを用い、別の実G7受入後に元候補のbase/adapter比較を1回完了した。96/96 candidate forwardsが有効完了した。この有限元候補比較で**baseに対する改善は観測されなかった。モデル採用は点推定にかかわらずHOLD**。全V002/V003・live/人便益は未完である。

[親SFTの実結果](HELPSTEER2_PRIVATE_SFT_CPU_20261023.md)は訓練・保存段階のimmutableな履歴として保存する。同receiptのG7 NOT_RUN/NOT_ACCEPTEDはその時点のsnapshotで、現在の実評価結果は本書へ結ぶ。[固定評価plan](../plans/2026-10-23-helpsteer2-fixed-adapter-eval.md)、[親model計画](../plans/2026-10-23-behavior-transformation-model-plan.md)、[SFT subplan](../plans/2026-10-23-helpsteer2-private-sft.md)、[凍結評価science](../../experiments/behavior-model/helpsteer2-fixed-adapter-eval-protocol-v1.json)を参照。使命は「行動変容を通じて、苦しみを終わらせることを目指す。」。意識・覚り・AGI・苦しみの終結の実証を意味しない。

## 実段階と受入の順序

| 実段階 | UTC / 証拠 |
|---|---|
| 評価科学source採択/freeze | 19:59:07.182754Z。親学習・adapter選別・新規target-model採点より前 |
| 親SFT | 20:09:45.449559Z→20:11:07.426371Z、正常train/save、独立実結果検証58checks一致 |
| 単一保存adapter固定 | 20:16:39.598466Z。新規target-model採点前、run/checkpoint/成績による選別なし |
| exact-source公式CI | source `3694f80c39e6cd164a1a9a299e922d85bc75897c`、[run40019570960](https://github.com/Daisuke134/life-manager/actions/runs/40019570960)/[job120640311552](https://github.com/Daisuke134/life-manager/actions/runs/40019570960/job/120640311552)、completed/success、run更新20:30:02Z |
| 実G7別受入 | 20:32:19.192976Z。一つのoffline fixed-adapter comparison attemptに限る |
| 外部0400実設定 | SHA `98e2eeb2dc114cd2758a0466a43c7c9a4f45d2a318f8deca84a9f5a2f093ab44`。science・parent・単一inventory・code/CI/review/resource/exposureを一方向にpin |
| 内monitor実行 | 20:32:40.168148Z→20:34:18.875530Z、98.707秒、EXITED_SUCCESS/return0 |
| 終了直後のsource/terminal proof | 20:34:40.456780Z。full source clean、HEAD3694、source19全hash一致 |
| 独立実結果検証 | 実報告を読み、464照合全一致・0 findings (0 blocking)、SPEC/QUALITY PASS（有限実結果検証/元候補一致の記述に限る）。結果の算術/提供runtime証跡と独立検算の区別は下記証拠に従う |

研究branchは `research/manager-e06-cloud-execution-20261022`、canonical originは `https://github.com/Daisuke134/life-manager.git`。source guardはactual **FAIL exit2 / canonical host不在**。既存明示owner cloud許可の処置を保持し、PASSに置換しない。source全体の凍結受入と終了後clean/hash実証跡を接続し、全期間の連続source監視を独立再構成したとはしない。

公式full suiteは1119tests/skip6・37.039秒、既存localは1145tests/skip5・30.498秒。件数差26の原因はUNKNOWN、既存argparse診断・Node deprecation警告を保持する。本書作成はtests/CIを再実行せず、保存された実受入証拠を参照した。CI成功やJSONのCOMPLETEDだけをnative採点成功/cleanupの証明にはしない。

## 元人preferenceとの一致と分母

元のexact候補1/2を既存native mean completion-token NLLで比較した。EOS-inclusive completion mask/hash tie-breakを使い、新しい応答生成はしない。dev8とfinal16を別に報告し、pooled24のprimary scoreを作らない。candidate forwardsはbase48+adapter48=96、assigned/attempted/completed=96、failed/unknown/not_run=0。

| slice / policy | assigned | valid completed | abstained | correct | conditional accuracy |
|---|---:|---:|---:|---:|---:|
| dev8 / native base | 8 | 8 | 0 | 4 | 4/8 = 50% |
| dev8 / fixed adapter | 8 | 8 | 0 | 4 | 4/8 = 50% |
| dev8 / shorter-candidate rule | 8 | 8 | 0 | 4 | 4/8 = 50% |
| dev8 / NO_ACTION | 8 | 0 | 8 | 0 | null |
| final16 / native base | 16 | 16 | 0 | 12 | 12/16 = 75% |
| final16 / fixed adapter | 16 | 16 | 0 | 11 | 11/16 = 68.75% |
| final16 / shorter-candidate rule | 16 | 16 | 0 | 3 | 3/16 = 18.75% |
| final16 / NO_ACTION | 16 | 0 | 16 | 0 | null |

独立検証者は権限のある元preference24行/quality48行のgold/元候補hash/quality joinを再構成し、保存ラベルや速報値に依存せず全policy/sliceの集計を検算した。本書作成自体はraw再開封を行っていない。

全policyのattemptedはassignedに一致し、failed/unknown/not_run/ties=0。base/adapter/ruleのcoverageは1、NO_ACTIONは0。rule/NO_ACTIONのNLLはnullで、model forwardを消費しない。NO_ACTIONのcorrect=0はreceiptの非選択countであり、accuracy0として扱わずnullを保持する。candidate loss・個別ID/gold/choiceとその対応はPRIVATEに保存し、本書に出さない。

| slice | common valid pairs | 両者正答 | baseのみ正答 | adapterのみ正答 | 両者不正答 | adapter−base |
|---|---:|---:|---:|---:|---:|---:|
| dev8 | 8/8 | 4 | 0 | 0 | 4 | 0/8 = 0 percentage points |
| final16 | 16/16 | 11 | 1 | 0 | 4 | −1/16 = −6.25 percentage points |

base/adapterのpaired coverageは両slice1、missing/failed pairs=0。adapter−rule差はdev0、final8/16=50 percentage points（paired valid8/16、coverage1、missing/failed0）。これは同一元候補の観測差であり、同等性・統計的劣位/優位の検定や一般化を認定しない。

## 実native経路と終了・資源

凍結sourceは、別実G7/0400 evidence・全11保存inventory・science/rights/source/base/package pinsをoptional import前に検証し、標準PeftModel.from_pretrained(is_trainable=False)とdisable_adapter contextで同じbaseを比較する。標準torch.inference_mode、CPU2/BF16 base・FP32保存LoRA、全48候補のnative mask一致、期待112adapter tensorsのnames/shapes/finite/保存値一致、非merged・eval・regular enable/disable/restoreを要求する。実正常終了と96有限lossはこの経路に整合する提供runtime証拠で、独立検証者がnative inferenceを再実行した観測ではない。base_numeric_in_memory_unchangedは **NOT_MEASURED** のまま保持する。

内model childはreturn0、wait/reaped/absent=true、残group空。TERM=false/KILL=false/retry0。外側monitorもactual parent wait return0/reaped/absent=true、98.775秒。内外差0.068秒は測定境界の差で、training budget延長ではない。inner stdout3048B/outer stdout769Bはredacted aggregate、stderrはいずれも0B。durable receiptのflush/fsync/replace/dir-fsync経路と外部正常終了を合わせて確認し、過去の全fsync syscall再観測や電源断耐久試験とはしない。

sampled own-group peak RSS=2,103,181,312B（約1.959GiB）、900秒累積wall/6GiB RSS polling threshold内。0.05秒sleepにproc scan時間が加わり、共有mappingの二重計数もあり得る。全poll系列は保存されておらず、連続peak・瞬間的な全child・kernel hardcapを認定しない。外側軽量metadata照合と、child内全data/model/adapter body hash/load/96 forwardsの境界を区別する。retry/resume/延長/追加学習/新adapter/merge/生成/network/新有料resource/並行MLなしは設定・source・正常終了証跡の範囲で整合し、全host履歴の独立不在証明とはしない。実インフラ$費用はUNKNOWNで$0にしない。

## 不変bindingとPRIVATE証拠

training science `eb2e585321d954d507af52b1bf71db9eb3b7ae3150273484909b6aeeae48a53d`、評価science `cb7d6cebf90549e8fa17b8cb393efaa00cdcd4783d9cb4edaf3da343533ac2f9`、manifest `7547ff63f7c06f8196689b3890288417154012d71e9609d0a3db232eeb0f182e`は不変。用途rights canonicalは旧dev-only `0b76b970e877dc17a6fc21c18979c9c7efaf4e1e6053c01a9c13577ee2920a41`、training `f41063b9ae281bc5bc1677655cb5a5997b1c9b5de8857ac180480176d71a1be5`、fixed evaluation `088f6cc5a17f8ff3c83dfc10b44bca70dbd0855d3dd0c8b1063727ff2271225d`。全11file inventory canonical SHA `9ed8f7e04d9bd601a77e6bad78694d4ed5cfaab3e2b03dd3efad7b890bdc3b7b`、adapter weights SHA `84481574261138b6bf5ac7f683a96b0342e3e02b564c577bbc8694903cd1c81c`を保持する。

| PRIVATE証拠basename | SHA256 |
|---|---|
| root-single-adapter-freeze-v1.json | `93f63b8de8cfc0675b388a77425d4159cb00d0259917d849b1ecc6ff99015020` |
| whole-preexecution-review.md | `2e0d60d7f41f5d827a27e1e7aaaeda3f80236bc327a9ea4ad5d41218a283842c` |
| official-ci-accepted.json | `99a466a357c8610ac87e93921104209b44efe911b26dbaeed1b98f3037a4f9f1` |
| root-preexecution-G7-accepted.json | `a2bcfca7e08bd21562d5f84d70148cae7679432789eea1fb3c287d27f86eba02` |
| execution-config-v1.json | `98e2eeb2dc114cd2758a0466a43c7c9a4f45d2a318f8deca84a9f5a2f093ab44` |
| root-actual-launch-v1.json | `94df78c681467d229deb4deb475e22b84723cc75cd941a889f4c0f4f44b4df4e` |
| root-outer-monitor-terminal-proof.json | `d6e6ffce5450b584e68e60a1930b0b3fc67ee732e4477e84f9957edb75a0f862` |
| execution-receipt.json | `cb4ce45abb0853c9ec096bf0dfafc43f261cf4db50608e970d45a63f5688c253` |
| result.json | `21aca1608c815a4989b2f8cbedcee21fef4b1b2ea1646e95b926bc3e55f3cc71` |
| root-postevaluation-source-and-terminal-proof.json | `1973944b19823df6a94b198cf996cdb8943e7e815798610a63498638c9a5bc2f` |
| actual-result-verification.md | `fbbb6d51c4f9a0bc00086113f539e9aa5a6618a365cb48a5009391bec3e293f5` |
| actual-result-verification.json | `9171d8e960c22db17fa2e65c33ff478f3c4dd8259bd14113d16aba6ea94de5e9` |

raw data/model/adapter/config/runtime実path・ID/gold・候補本文はPRIVATEだけに保持する。本書はbasename/hash/集計metadataの接続で、ML/native import/model/tensor/pickleの再load・raw再開封を行わない。

## 採点後の制約と次の作業

final16はAI内容QC曝露済み・NOT_PRISTINEで、今回target-model採点済みになった。訓練・few-shot・retrieval・設定/recipe/閾値/adapter選択には未使用という記録を保持するが、以後の新研究に対する未見holdoutとは呼ばない。凍結manifest/scienceのUNSCORED/NOT_RUNはfreeze時snapshotとして変更しない。旧train32=27retain/5exclude NOT_READY、補充/除外復帰/split移動なし、旧dev4/8とXSTest不採用の結果、person/study/time UNAVAILABLE・language/family/OOD/汚染UNKNOWNを保存する。

小N・元候補への一致のみで、行動変容・苦しみ低減・人の便益/安全性・一般化・同等性/統計的劣位・臨床効果を示さない。behavior_change/harms/pressure/dependency=null、suffering_reduction/human_benefit=NOT_MEASURED。用途rightsはPRIVATE条件付きAI engineering/research判断で、新しい人のlegal/IRB/同意署名や全第三者clearanceを主張しない。

次はこの有限結果と限界を報告し、全V002のAPI/費用・圧力/依存/害・人参照照合、全V003の用途に適合した未見/一般化/安全性の評価設計、D014/D015/U004の実研究条件/保護を進める。新しい実験は別version・用途に適合したholdoutと別実受入を要し、現finalやこの結果を使ったretune/選別/再採点を許可しない。[正規task台帳](../roadmap/tasks.json)は113 IDs=83done/20todo/10skipped、V003 status=todo / implementation_status=SCOPE_REVISED_ACCEPTANCE_NOT_COMPLETEDのまま、本receiptだけをimplementation_evidenceに追記する。V004=[V003,D016]・元依存・原要件/旧研究hash、旧V001/G001/G002有限設計done、運営UNADOPTED/実外部監査NOT_PERFORMED、実参加者0/募集なし・臨床未実施は不変。

**実結果sourceの実採択:** fresh whole actual-result review R1は0 findings / 0 blocking、SPEC・QUALITY・INTEGRATION PASS。私有report `whole-actual-result-review.md` SHA256 `a572e39357e54707a931ae67fca7cf8ca420beb64710e0d77b20a47108066294`。rootは2026-10-23T20:44:38.742565+00:00に陰性の有限比較結果を採択し、review済み11文書を実適用した。私有receipt `root-actual-finite-eval-result-source-adoption.json` SHA256 `3a9c34098cf3dcdf270352602047fbf2f01d6916f5903587d13cf43ee4fdab6a`。モデル採用・全V003・live/人便益の受入ではない。

sourceのcommit/push/authoritative remote readbackはrootの後続作業。本書で将来commit/refを先書きしない。新記事/site/outreachは後段で、public weight配布・production採用は実施していない。
