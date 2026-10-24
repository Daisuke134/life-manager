# Behavior Transformation and Owned Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 行動変容を通じて苦しみの終結を目指す主体を、既存研究・評価・モデルから育て、独自重みと検証された実結果へ接続する。

**Architecture:** 既存kernel/owner・OutcomeBench・scorer・model APIを再利用。権利とholdoutを固定した既存モデル比較から、PEFT/TRLによる最小の独自adapter研究へ進む。人対象の実施・昇格・便益の受入はoffline研究と別gateにする。

**Tech Stack:** 既存Python/unittest、SQLite/checkpoint、既存Actions owner、既存model adapter、権利確認済みopen weights、必要になった段階のPEFT/TRL。新しいagent OS/trainer/simulatorを作らない。

**Spec:** `docs/specs/2026-10-23-behavior-transformation-scope-amendment.md`、`docs/MANAGER_PRODUCT_SPEC.md`。唯一の状態・依存は`docs/roadmap/tasks.json`。

## Global Constraints

- 使命は「行動変容を通じて、苦しみを終わらせることを目指す」。宗教は必須条件/採点基準ではない。
- 113 IDs、先行scope改訂時点のsnapshotは80 done / 23 todo / 10 skipped。rootが[限定V001設計receipt](../verification/V001_PURPOSE_SPECIFIC_DESIGN_ACCEPTANCE_20261023.md)で実受入した時点は81 done / 22 todo / 10 skipped。その後[G001/G002有限source設計receipt](../verification/G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md)のroot実受入を反映した時点は83 done / 20 todo / 10 skipped。その後D014の実台帳記録時点は84 done / 19 todo / 10 skipped。D015有限定義task実受入を反映する現在viewは85 done / 18 todo / 10 skipped。退役7件は未達成。旧done/receipt/protocol hashを保存し、有限SFT開始scope/結果だけではstatus/件数/全体依存を変えない。
- 目的と評価基準を保ち、モデル系列/規模/量子化/runtime/学習方法は実測で更新する。GPU/特定4B候補を全体の開始条件にしない。既存CPUで公開モデル推論を進め、訓練と推論の必要資源を分ける。
- 独自modelは将来像へ含める。有限train27 PRIVATE SFTは[別scope](../specs/2026-10-23-finite-private-sft-research-start.md)のG0有限sourceを実採択済み（SOURCE_SCOPE_ACCEPTED_FINITE_TRAIN27_ONLY）。用途別の実G0–G6/CI/resource/0400受入後に一attempt学習/単一adapter保存を完了・独立検証した（[実結果](../verification/HELPSTEER2_PRIVATE_SFT_CPU_20261023.md)）。[固定比較](../verification/HELPSTEER2_FIXED_ADAPTER_CPU_20261023.md)も実G7別受入後96/96完了、baseへの改善未観測・採用HOLDで、全V002完了や人対象実研究全体の完了を一律前提としない。全V002/V003の一般採用要件・todoとV004=[V003,D016]は維持する。
- 新規費用・GPU・データ利用権・live推論は仮定しない。既存予算・契約・資源を確認してから実行する。
- 既定OFF、単一owner、ACK/UNKNOWN/STOP/復元/独立readbackを保持。説得は権限・同意の迂回路ではない。

## Review Focus

1. 用途に適合する分割と漏洩。有限train27は元prompt/responseのexact/canonical交差検査とfinal隔離/曝露台帳を必須とし、person/study/time UNAVAILABLE、language/family/OOD UNKNOWNの一般化はHOLD。全V003の未見/外挿受入に必要な軸をこのN/Aで満たしたとしない。
2. code MITとNC/ND教材・data・base/出力利用権の混同。artifact別の採用/HOLDを記録する。
3. LLM judge・同意率・利用時間の改善が人の便益へ昇格。P0と実outcomeを別欄にする。
4. 独自adapterの生成/benchmark向上だけでlive作用を発火。既定OFF・stop・再送0を回帰確認する。
5. 退役を成功として件数へ加算、または旧人間研究を事後改変。原行archiveと旧hashを検査する。

## Task 1: 既存sourceとresearch branchを揃える

**Files:** `manager_core/ampersand_api.py`、`manager_core/owned_checkpoint.py`、`manager_core/owned_provider_shadow.py`、対応する既存tests、受入receipt。

**Interface:** main PR8710/8715の受入sourceを同じbytesで研究branchへ同期し、既存のprepared比較／保存／再読契約を使う。研究source dc56ba984ee9と公式CI39972208021で受入済み。host接続は別Task6。

- [x] 差分の個別編集とsource由来を確認し、受入済みの必要fileだけを同期する。
- [x] focused testsと全Manager suite、公式研究CIで同じsource headを検証する。
- [x] 実結果・main/research SHA・skip理由をreceiptへ固定する。

## Task 2: 既存評価の最小接続 — V001/V002

**Files:** `docs/research/source-rights.json`、`manager_core/evaluation.py`、`manager_core/outcome_bench.py`、`tests/test_r006_rights.py`、`tests/test_evaluation.py`、`tests/test_outcome_bench.py`。 最初の固定input受入は[INTIMA subplan](2026-10-23-intima-intake.md)のdataset専用adapter/inspector/testで実装し、既存数学scorerを変更しない。

**Interface:** 既存のprediction/evidence契約へ、source/dataset/adapter/model/judge版、人物/研究/時間split、分母・失敗・拒否・未評価nullを対応付ける。新しい実行権限を返さない。

- [ ] 9法比較の公開集計、APE/PersuSafety、INTIMA等から最小の利用可能な評価を選び、artifact別権利を固定する。
- [ ] 人の便益へ昇格しない・NC資料を採用しない・分母0をUNKNOWNに保つ境界のREDを作る。
- [ ] 上流scorer/既存関数を薄く接続し、同じ境界のGREENを確認する。
- [ ] NO_ACTION/ルール/既存modelを同じ入力・予算・failure denominatorで比較し、judgeの人手照合と限界を報告する。

**限定sliceの実績（全受入ではない）:** INTIMAの固定input受入と未採点32組診断に続き、[HelpSteer2 dev subplan](2026-10-23-helpsteer2-dev-likelihood.md)を実装・実行した。[実結果](../verification/HELPSTEER2_DEV_CPU_EVALUATION_20261023.md)は16/16完了、model4/8・短い候補ルール4/8、NO_ACTION8棄権。generic preferenceへの一致だけでモデル優位や人の便益は示されない。[追加の人参照artifact監査](../research/2026-10-23-human-reference-artifact-audit.md)から用途・利用条件を照合し、元回答に対する採点者の校正、圧力/依存等の評価、未見比較を埋める。[既存XSTest string判定の人参照450件照合](../verification/XSTEST_RELEASED_REFUSAL_CALIBRATION_20261023.md)はfull-refusal recall12/49・partial0/27で不足を示したが、新しいManager judgeの校正ではない。さらに[local judge subplan](2026-10-23-xstest-local-refusal-judge.md)を実装・実行し、[900秒診断](../verification/XSTEST_LOCAL_JUDGE_CPU_20261023.md)で271/450有効、UNKNOWN1/未着手178。全271をcomplianceと判定して拒否recallは0/27・0/20、この設定は不採用。同じ有効集合でmodel224/271・配布rule230/271。専用binary judgeは別の事前固定候補とし、3class・害・圧力評価の代わりにしない。当時V001/V002全体とV003はtodoだった。今回のV001設計のみの提案受入は下記別receiptに結び、V002/V003はtodoのまま。

[専用native binary subplan](2026-10-23-qwen3guard-binary-diagnostic.md)も一度実行し、[実結果](../verification/QWEN3GUARD_BINARY_CPU_20261023.md)は450/450規定形式、primary377/423対rule383/423、拒否recall20/49・誤検出17。partial27は無採点。監視再接続の空白と未reapを保存し、全資源protocol準拠や自動採用を認定しない。旧3classと直接accuracy比較せず、Task2全体/V002は未完。

[V001 mapping subplan](2026-10-23-v001-evaluation-contract.md)と[metadata受入](../verification/V001_EVALUATION_CONTRACT_MAPPING_20261023.md)により、既存3診断のscope/役割/scoring/refusal/null/split availabilityの対応を固定した。person/study/time holdoutの実情報は増えておらず、当時Task2全体とV001/V002は未完だった。新規推論・追加学習・評価engineは導入していない。

**V001設計とTask2全体の区別:** [用途別scope](../specs/2026-10-23-v001-purpose-specific-acceptance-amendment.md)と[限定設計受入receipt](../verification/V001_PURPOSE_SPECIFIC_DESIGN_ACCEPTANCE_20261023.md)にrootの実review/適用/受入を記録済みで、既存4有限診断役割の設計だけをV001 doneとした。旧literal UNMET/HOLD、12軸のavailability UNAVAILABLE、FINALの公開/非公開隔離と公開development露出履歴は保存。将来splitは未受入。上記Task2の4 checkboxはV002の全比較/人手照合を含むため、このV001受入だけでは完了にしない。全V002/V003の一般採用条件と依存は維持する。Task3の有限train27開始だけは下記別scopeのG0有限source実採択へ接続し、全V002完了を一律前提としない。G0単独で用途rights/protocolの全実行条件を受け入れたとせず、最終統合R2は0 findings/PASS。V001/G0単独では開始せず、その後の公式CI・実資源/外部0400とG0–G6実判断を別に受け入れて、下記Task3の一attemptだけを完了した。

**追加の公開評価codeから学ぶ候補:** [DarkBenchの一次資料・契約差](../research/2026-10-23-darkbench-reuse.md)を確認した。rubric/MIT scorer/著者集計は部分参考になるが、exact原responseと公開human票のbindingは未確認。上流の空category0・invalid/parse失敗・3attempts/JSON修復・現default judgeと原著3judgeの差を保持し、既存Managerのnull/全assigned/失敗区別へ無条件に直結しない。新engine/data/scorer実行を導入せず、用途に適合する実参照が成立した箇所から既存評価契約へ接続する。V002/V003 todo・現final16の採点済み状態・モデル採用HOLDは変えない。

[SafetyBench MCQ contract subplan](2026-10-23-safetybench-mcq-contract.md)と[実固定control receipt](../verification/SAFETYBENCH_MCQ_CONTRACT_20261023.md)で、固定source/key、recorded status、NO_ACTION、事前固定FIRST_OPTION_RULEと全gold分母のlocal adapterを接続・有限実行した。rootの実用途受入は2026-10-23T22:35:25.697772+00:00のprivate offline MCQ scopeのみ、最終rights bytesの実受入は22:47:20.060532+00:00。immutable code `31e746640794068e714baeaf3636570abc2d4386`で44 focused testsとrootの全1160 tests PASS（skip5）を区別して記録し、22:49:13.236290+00:00–22:49:14.343993+00:00の実CLI一度で11435件全assigned/ID/categoryを確認した。recorded NOT_RUN11435、NO_ACTION ABSTAIN11435/refusal0/valid0/conditional null、FIRST_OPTION_RULE VALID11435/coverage1、4098/11435=`35.83734149540883%`。各control一度のexact上流eva_resは8割合すべて一致、authored valid/wrong/sparse SYNTHETIC_CONTRACT_PARITYも一致した。model実行NOT_RUN/predictions null、public/exposed・P0/NOT_MEASURED・can_execute=False/HOLDであり、model比較・人便益・未見finalの証拠へ昇格しない。全体独立review・公式exact-source CI・source adoption/integrationはroot所有の後続事項。Task2/V002の4 checkbox、85 done/18 todo/10 skipped、既存negative結果、final16 SCORED/NOT_PRISTINE、model HOLDとparent ACTIVEは維持する。

**SafetyBench local Qwen3 CLPの後続実行:** [実結果](../verification/SAFETYBENCH_LOCAL_QWEN3_CLP_CPU_20261023.md)と[recovery amendment](../specs/2026-10-24-safetybench-journal-replay-recovery.md)に、元native attemptと別accepted recorded replayを分けて記録した。元attemptは固定10,800秒wall limitで`RESOURCE_LIMIT`となり、native childはreapedだがouter wait/reap proofがなく、元finalizationは`UNFINALIZED_MISSING_OUTER_REAP`。通常finalizerは実行しておらず、Task2 step完了にしない。事前にrootが受け入れた一度の決定的replayはmodel call/retry/resume/extensionなしで既存scorerを1回実行し、11,435 assigned中6,425 VALID、1 UNKNOWN、5,009 NOT_RUN、`PARTIAL_OR_FAILED_REPLAY_ONLY`を返した。42.5214%は有効な観測prefixだけのconditional key agreement、全gold denominatorでは2,732/11,435=23.8916%、coverageは56.1871%。source-order censoringと分母差によりcontrolとの優位比較はできない。Qwen3-0.6BのCLP/MCQ key agreementはfree-response safety/refusal、未見一般化、pressure/dependency/response harm、臨床妥当性、行動変容、人の便益を示さない。producer provenanceは`DECLARED_NOT_AUTHENTICATED`、採用`HOLD`、`can_execute=false`を維持。execution source Hのprimary rights registryは5 records、別research registryは18 recordsのまま不変で19件目は追加していない。元v1未完了とreplayの明示的な二重状態はrecovery amendmentを参照する。Task2/V002の4 checkbox、85 done/18 todo/10 skipped、既存negative結果、final16 SCORED/NOT_PRISTINE、U004 draft・参加者0/介入0、parent ACTIVEは維持する。prospective replay reviewとactual receipt/arithmetic reviewはいずれも0 findings（prospective reviewのauthored 9 tests PASS）。whole-source reviewと標準PR/CI/integration/official-readbackはrootが別途追跡し、本receiptは完了を主張しない。

## Task 3: 独自重みの最小研究 — V003

**実在するsource:** [有限研究scope](../specs/2026-10-23-finite-private-sft-research-start.md)、[train27 manifest](../../experiments/behavior-model/helpsteer2-train27-manifest-v1.json)、[静的科学protocol](../../experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json)、[source-rights](../research/source-rights.json)、[実装subplan](2026-10-23-helpsteer2-private-sft.md)、[core](../../manager_core/helpsteer2_candidate_sft.py)、[薄いCLI](../../scripts/train_helpsteer2_candidate_sft.py)、[focused tests](../../tests/test_helpsteer2_candidate_sft.py)。runtime receipt/adapterは既存のprivate Git外保存・metadata receipt契約へ結ぶ。

**Interfaceと現在地:** G0は**SOURCE_SCOPE_ACCEPTED_FINITE_TRAIN27_ONLY**。2026-10-23T19:59:07.182754+00:00にrootが有限source scopeを実採択した（[実イベント](2026-10-23-helpsteer2-private-sft.md#actual-g0-source-event)）。最終統合R2は0 findings/PASS。exact-source公式CI・実resource/外部0400・G0–G6実判断を別に受け入れ、[一attemptの学習/完全保存](../verification/HELPSTEER2_PRIVATE_SFT_CPU_20261023.md)を完了・独立検証済み。[固定比較](../verification/HELPSTEER2_FIXED_ADAPTER_CPU_20261023.md)も実G7別受入後96/96完了。dev base4/8・adapter4/8、final base12/16・adapter11/16、採用HOLD。exact retained train27の元preferenceが選んだ元候補1本だけを、既存native Qwen3-0.6Bへ標準PEFT/TRL/SFTTrainerでcompletion-only SFTする一recipe/初期adapter/attempt。目的は固定元候補mean completion-token NLL選択の元人preference一致の変化（P0）で、pairwise rankingの直接最適化ではなく改善も保証しない。同じbaseへの有限差を問うためAPIは必須にしない。既知dev4/8対rule4/8は探索動機に限る。全V002のAPI比較・圧力/依存/害/人参照照合、全V003の人物/文脈/言語/時間holdout・OODと一般化/安全性はtodo/HOLDのまま。全体V001→V002→V003、V004=[V003,D016]、D014/D015の有限受入を反映する現在件数は113 IDs・85/18/10。SFT/G7だけではstatus/元依存を進めない。

**権利/履歴/曝露:** 新record `helpsteer2-private-exploratory-sft-train27-v1`（canonical SHA `f41063b9ae281bc5bc1677655cb5a5997b1c9b5de8857ac180480176d71a1be5`）は2026-10-23のroot AI engineering/research判断でexact27 PRIVATE前処理/SFT/adapter保管用途を条件付き受入とした。既存AI QCとmetadata/source-binding reviewを採用した用途限定のpending解決で、新しい人手raw reviewや全第三者/privacy clearanceではない。旧strict8 protocol/権利、native/Qwen3Guard陰性結果、旧train32の27 retain/5 exclude NOT_READYを保存し、補充/除外復帰/split移動をしない。final16はAI適格性QCで内容曝露済み・未学習/設定選択未使用、今回の固定比較でtarget-model採点済み。pristineでも以後の新規未見holdoutでもない。person/study/time UNAVAILABLE、language/family/OOD・paraphrase/pretraining汚染UNKNOWNを成功holdoutへ変えない。

- [x] 有限scopeのG0正規source整合・先行独立reviewに基づくroot実採択を2026-10-23T19:59:07.182754+00:00に記録済み。最終統合R2は0 findings/PASS。G0単独をG1–G6実受入としない。
- [x] manifest/protocol/source/gold/choice/hash/隔離と条件付き用途rightsのexact統合、最終code独立review・必要検証/公式CI、実host/memory/disk/private ACL・own-process watchdog/TERM/KILL/reapを受け入れる。
- [x] 独立root所有0400 execution config/receiptから凍結科学protocol SHAへ一方向に、immutable core/CLI/watchdog/final source・CI/review・resourceとG0–G5/G6実判断を結ぶ。future自身commit/hashをprotocolへ逆pinせず、caller-only hashで科学bytesを差し替えない。
- [x] 条件付き評価用途判断を反映した[prospective dev8/final16評価科学定義](2026-10-23-helpsteer2-fixed-adapter-eval.md)は独立reviewを経て、G6実学習・adapter選別・モデル採点より前の2026-10-23T19:59:07.182754+00:00にrootがsource採択・freeze済み。この事前固定に実adapterやG7実行受入を要求しない。
- [x] G6実判断後、CPU2/BF16・累積900秒/6GiB RSS pollingの一attemptを実行。retry/resume/延長/network/新有料resourceなし。COMPLETED / ARTIFACT_FROZEN、27 backward-microbatch下限、7 optimizer機会/7 return/global_step7、112 FP32 trainable tensors・1,146,880要素。runtime初期in-memory clone比では112tensor変化、独立保存検査は全112finiteと標準zero-B初期化比の変化下限56tensorを確認した。全112の独立初期差分復元ではない。正常train/save return、全11保存物・inventory/hash/ACL/fsync経路と外部正常終了/reapを58checks一致の独立実結果検証で確認した（[実結果](../verification/HELPSTEER2_PRIVATE_SFT_CPU_20261023.md)）。81.977秒/sample peak約2.828GiB、$費用UNKNOWN。global_stepを7数値更新の証明にしない。この学習完了段階では新規target-model dev/final採点はNOT_RUNだった。その後の実G7比較は次checkbox/別receiptへ結ぶ。
- [x] 正常終了と完全save/fsync/inventory/hashの独立検証後、rootが20:16:39.598466Zに単一adapterを新規target-model採点前・成績選別なしで固定した。
- [x] 別の評価code独立review/公式CI・実resource・外部root所有0400 bindingsと実G7判断を採点前に受け入れ、固定比較を96/96完了した（[実結果](../verification/HELPSTEER2_FIXED_ADAPTER_CPU_20261023.md)）。実G7を20:32:19.192976Zに別受入し、exact-source3694f80c39e6cd164a1a9a299e922d85bc75897c・公式CI40019570960/job120640311552・外部0400設定でdev8/final16固定比較を1回完了した。96/96 candidate forwardsが正常完了、failed/unknown/not_runは0。dev8はbase4/8・adapter4/8・短候補rule4/8、final16はbase12/16・adapter11/16・rule3/16、NO_ACTIONは8/16棄権でaccuracy=null。この有限元候補比較でbaseに対する改善は観測されず、モデル採用は点推定にかかわらずHOLD。final16は内容QC曝露済み・NOT_PRISTINEで、今回はtarget-model採点済み。未学習は維持するが、以後新しい未見holdoutとして使わない。小Nの点差から同等性・統計的劣位・一般化/安全性・行動変容/苦しみ低減・人便益を結論しない。新しい研究は別version・用途に適合したholdoutと別の受入を要し、再学習/retune/adapter選別/再採点を今回の結果から自動許可しない。同じ元候補/分母で比較し、rule/NO_ACTION NLL=null、NO_ACTION accuracy=nullを保持。
- [ ] 有限P0の成功/無改善/悪化を一般採用・全V003 done・V004/live・人の便益へ変換しない。DPO/蒸留/scratch pretrainingは不足と適法data/computeを要する別比較/設計とする。

## Task 4: 実研究条件と本人の選ぶ価値 — D014/D015/U004

**Files:** `pilot/BEHAVIOR_TRANSFORMATION_STUDY_V2.md`、新v2 manifest、既存source/rights/protection文書。

**D014/D015有限protocol/定義受入:** D014は現scopeの公表非個人published-effect protocol taskに限り実受入・台帳記録済み。D015の9つの非診断signal→該当作用の停止/通常支援保持→適した実独立判断と自由な再選択/版固定による復旧の有限定義は、別contextの実適用YES reviewを受け、rootが2026-10-23T21:16:58.283242Zにsource採用し、同21:16:58.283436Zに定義taskを別受入した。D015もこの有限定義scopeに限るdone。U004はDRAFT/NOT_REGISTERED/参加者0/介入0のtodo。[実receipt](../verification/D014_D015_PROTOCOL_ACCEPTANCE_20261023.md#d015-actual-task-acceptance)。旧original_*の実団体協力UNMET、正式制度適用UNKNOWN・承認/免除NOT_OBTAINED・臨床承認NOT_GRANTEDを保持する。新規人介入・実協働・臨床・人便益・モデル採用の受入ではなく、モデル採用HOLD/親目標ACTIVEを維持する。D014の原要件/依存/original_*は変更しない。

- [x] D014の実root task判断を現scopeの公表非個人protocolに限る受入として記録した。D014台帳はrootの21:16:35.340175Z実適用/readbackでdone記録済み。D014 R1のreceipt表記Nitは修正済み。Sol delta R2は0 findings/0 blocking・Nit FIXED/CLOSEDで完了し、D014/D015の台帳記録はcommit `ddcbf91dcd9be0337ede3075a28490e6c3c27f49` でpush・公式readback一致を確認済み。
- [x] D015の依存signal・停止/本人選択の通常支援/復旧定義と現scopeへの有限独立適用判断を、新Safety定義と21:12:45.444261Z別context実review YESで満たした。rootはsource採用21:16:58.283242Zと別task判断21:16:58.283436Zを実記録した（[実receipt](../verification/D014_D015_PROTOCOL_ACCEPTANCE_20261023.md#d015-actual-task-acceptance)）。台帳反映はcommit `ddcbf91dcd9be0337ede3075a28490e6c3c27f49` で実施し、push・公式readback一致を確認済み。人研究/個人安全/clinical承認は未発動。

**Interface:** 以下の新規人研究の条件は別に未完。現対象の一次的な課題確認、適用判断・必要な同意/役割、主要結果・比較・検出力・追跡・害/停止を固定した研究versionを出す。旧120世帯/58日のhashは変えない。

- [ ] 対象行動/需要と媒体の適合を実確認し、旧UK支援面談を新対象の検証に流用しない。
- [ ] 草案の未確定欄を実条件・測定権利・検出力根拠で埋め、独立した適用判断と停止経路を成立させる。
- [ ] 開始前のversion/hashと適用する登録を固定する。ここまで成立するまでU004はtodo。

## Task 5: 実介入と価値の比較 — U006/U007/U008/D016

**Files:** 既存`manager_core/outcome_windows.py`、`manager_core/outcome_bench.py`、`manager_core/causal_analysis.py`、新研究のprivate実記録と公開可能な集計receipt。

- [ ] protocol内の実施・曝露・撤回・欠配・行動・生活機能・苦しみ・追跡・害を記録する。
- [ ] 割付分母・欠測/離脱・悪化・比較効果と不確実性を含めて分析する。既存adapterの統計仮定を満たさない反復/clusterへ無条件流用しない。
- [ ] 実際の継続意思/支援と費用を別観測し、D016で真正な結果と保護を統合する。

## Task 6: 主体への接続と運用昇格 — V004/V005/V006/G

**Files:** `manager_core/owned_platform_host.py`、`scripts/run_owned_digital_cycle.py`、repository rootの`.github/workflows/manager-phase06-service.yml`、`manager_core/governance.py`、既存監査文書。

- [x] STOP/recovery/cadence後の同じ候補を使う既定OFFのshadow接続を実装し、control/無効設定/再読のprovider呼出し境界を回帰確認する。[PR8741と研究source5018の受入](../verification/HOST_SHADOW_CONNECTION_ACCEPTANCE_20261023.md)。実推論運用やV004全体の完了ではない。
- [ ] 新しい行動変容channelの実範囲と観測をreviewし、既存7パスpublisherの権限を流用しない。
- [ ] V003とD016を満たして初めて限定昇格し、停止・復元・独立readback・再送0を確認する。
- [x] G001/G002の有限source憲章/監査設計は[限定receipt](../verification/G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md)に記録済みのroot実受入によるdone（実依存K007/V001→G001→G002を確認済み）。運営採択UNADOPTED・実外部監査NOT_PERFORMED、実役割/窓口/独立母集団と運用は未成立。V005第三者再現、V006実案件、G003以降の異集団/接続責任/原価/未測定領域は別受入。

## Task 7: siteの経歴・使命の訂正、その後の発信

**Files:** `apps/landing/marketing/pages/en.html`、`ja.html`、`route-manifest.json`（repository root相対）。

- [ ] 現mainからの専用PRでhero/story/researchを更新。A10 LabはMarketing Internと関心の出発点として書き、アプリ開発への貢献を作らない。
- [ ] EN/JAのbytesと3manifest hash、HTML/locale/canonical、desktop/mobile、他routeの不変を確認する。
- [ ] 既存full-site releaseと独立GETを確認して初めてlive更新とする。研究branchの本仕様更新では公開済みにしない。
- [ ] C002/Y008の新記事・書籍等は本体優先の後段。Y003/Y005は期限と実際の提出/応答を別に扱い、採択/採用を約束しない。

## 今回の計画のself-review

scope・元snapshotの23残件から限定V001/G001/G002とD014/D015有限受入後の現18残件・独自重み・公開研究再利用・no UI・実結果・siteの各要求をTask1–7へ対応付けた。有限train27開始routeのG0 sourceを実採択し、評価科学定義の用途判断・独立reviewに基づくsource採択/freezeをG6実学習より前に記録済み。実G0–G6・CI/config受入、一attempt学習/完全保存と独立実結果検証・単一artifact固定を[実結果](../verification/HELPSTEER2_PRIVATE_SFT_CPU_20261023.md)へ結んだ。別G7/code/CI/resource/0400受入後の固定比較96/96完了と[独立実結果検証](../verification/HELPSTEER2_FIXED_ADAPTER_CPU_20261023.md)を接続した。baseへの改善未観測・採用HOLDと全体未達を保持し、新しい研究は別version/用途適合holdoutを要する。未確定の研究条件はprotocol草案へ明記し、実行時に埋める方法と受入を指定した。本計画のcheckboxは実イベントと今後の手順を区別し、第二の状態台帳や達成件数にはしない。
