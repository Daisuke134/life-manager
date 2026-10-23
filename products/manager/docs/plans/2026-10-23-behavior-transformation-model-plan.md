# Behavior Transformation and Owned Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 行動変容を通じて苦しみの終結を目指す主体を、既存研究・評価・モデルから育て、独自重みと検証された実結果へ接続する。

**Architecture:** 既存kernel/owner・OutcomeBench・scorer・model APIを再利用。権利とholdoutを固定した既存モデル比較から、PEFT/TRLによる最小の独自adapter研究へ進む。人対象の実施・昇格・便益の受入はoffline研究と別gateにする。

**Tech Stack:** 既存Python/unittest、SQLite/checkpoint、既存Actions owner、既存model adapter、権利確認済みopen weights、必要になった段階のPEFT/TRL。新しいagent OS/trainer/simulatorを作らない。

**Spec:** `docs/specs/2026-10-23-behavior-transformation-scope-amendment.md`、`docs/MANAGER_PRODUCT_SPEC.md`。唯一の状態・依存は`docs/roadmap/tasks.json`。

## Global Constraints

- 使命は「行動変容を通じて、苦しみを終わらせることを目指す」。宗教は必須条件/採点基準ではない。
- 113 IDs、改訂時点の状態は80 done / 23 todo / 10 skipped。退役7件は未達成。旧done/receipt/protocol hashは保存。
- 目的と評価基準を保ち、モデル系列/規模/量子化/runtime/学習方法は実測で更新する。GPU/特定4B候補を全体の開始条件にしない。既存CPUで公開モデル推論を進め、訓練と推論の必要資源を分ける。
- 独自modelは将来像へ含める。最初のLoRA/SFT研究はoffline評価条件成立後に開始でき、実研究全体の完了を待たない。
- 新規費用・GPU・データ利用権・live推論は仮定しない。既存予算・契約・資源を確認してから実行する。
- 既定OFF、単一owner、ACK/UNKNOWN/STOP/復元/独立readbackを保持。説得は権限・同意の迂回路ではない。

## Review Focus

1. 同じ人物・研究・時間・test promptの学習への漏洩。分割manifestと交差検査を持つ。
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

**限定sliceの実績（全受入ではない）:** INTIMAの固定input受入と未採点32組診断に続き、[HelpSteer2 dev subplan](2026-10-23-helpsteer2-dev-likelihood.md)を実装・実行した。[実結果](../verification/HELPSTEER2_DEV_CPU_EVALUATION_20261023.md)は16/16完了、model4/8・短い候補ルール4/8、NO_ACTION8棄権。generic preferenceへの一致だけでモデル優位や人の便益は示されない。[追加の人参照artifact監査](../research/2026-10-23-human-reference-artifact-audit.md)から用途・利用条件を照合し、元回答に対する採点者の校正、圧力/依存等の評価、未見比較を埋める。[既存XSTest string判定の人参照450件照合](../verification/XSTEST_RELEASED_REFUSAL_CALIBRATION_20261023.md)はfull-refusal recall12/49・partial0/27で不足を示したが、新しいManager judgeの校正ではない。V001/V002全体とV003はtodo。

## Task 3: 独自重みの最小研究 — V003

**Proposed files:** `experiments/behavior-model/dataset-card.json`、`split-manifest.json`、`sft-config.yaml`、`training-receipt.json`。未作成の実験成果物で、本番moduleではない。

**Interface:** 権利・split・baseline不足を入力として、base/adapter/tokenizer revision/hash、recipe、seed、実compute/費用、未見評価を出す。dataset/model-cardの利用権が合う場合に限りQwen3-4B-Base等を比較候補にする。

- [ ] 合法なsupervisionと実compute/予算、追加学習で解く不足を確認する。例数やGPUを推測で埋めない。
- [ ] splitの交差・評価test混入・利用権欠落・baseline/source版欠落を拒否する検査を先に作る。
- [ ] 既存PEFT/TRLで最小SFT/LoRAを実行し、実artifactと失敗・費用を保存する。
- [ ] 固定した未見testで既存baselineと再比較。heldoutを見てから学習/閾値を調整しない。採用しない結果も記録する。
- [ ] 必要な不足が残るときだけ、権利のあるpreferenceでDPO等や合法な蒸留を別比較する。scratch pretrainingは別設計の条件付き段階。

## Task 4: 実研究条件と本人の選ぶ価値 — D014/D015/U004

**Files:** `pilot/BEHAVIOR_TRANSFORMATION_STUDY_V2.md`、新v2 manifest、既存source/rights/protection文書。

**Interface:** 現対象の一次的な課題確認、適用判断・必要な同意/役割、主要結果・比較・検出力・追跡・害/停止を固定した研究versionを出す。旧120世帯/58日のhashは変えない。

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
- [ ] V005の第三者再現、V006の実案件、G001/G002の憲章/監査、G003以降の異集団/接続責任/原価/未測定領域へ進む。

## Task 7: siteの経歴・使命の訂正、その後の発信

**Files:** `apps/landing/marketing/pages/en.html`、`ja.html`、`route-manifest.json`（repository root相対）。

- [ ] 現mainからの専用PRでhero/story/researchを更新。A10 LabはMarketing Internと関心の出発点として書き、アプリ開発への貢献を作らない。
- [ ] EN/JAのbytesと3manifest hash、HTML/locale/canonical、desktop/mobile、他routeの不変を確認する。
- [ ] 既存full-site releaseと独立GETを確認して初めてlive更新とする。研究branchの本仕様更新では公開済みにしない。
- [ ] C002/Y008の新記事・書籍等は本体優先の後段。Y003/Y005は期限と実際の提出/応答を別に扱い、採択/採用を約束しない。

## 今回の計画のself-review

scope・23残件・独自重み・公開研究再利用・no UI・実結果・siteの各要求をTask1–7へ対応付けた。未確定の研究条件はprotocol草案へ明記し、実行時に埋める方法と受入を指定した。本計画のcheckboxは未来の実施手順で、第二の状態台帳や達成件数にはしない。
