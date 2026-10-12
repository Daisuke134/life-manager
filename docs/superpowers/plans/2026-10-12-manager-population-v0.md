# Manager Population v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execution status remains solely in the unified SSOT; these boxes describe the procedure and are not a second task-state ledger.

**Goal:** 全生命・宇宙全体を対象とするManagerの最初のPopulation/Evidence/Evaluator部品として、公開の集団統計から人口を再構築し、入力から分離した実観測交差表への誤差を、再現可能な比較として出力する。

**Architecture:** 証拠の取得、集計とsplit、人口再構築、独立採点、reportを分離する。開発地域だけでseedを作り、対象地域のmarginalsからindependent/IPFを比較。ManagerのPopulation/Evidence/Evaluationの最初の部分として後のWorld/Policyへつなぐ。

**Tech Stack:** Python >=3.12、stdlib、ipfn1.4.4/NumPy2.4.4/pandas2.3.3、frozen dataclasses、JSON/JSONL、unittest。paid APIなし。

**Spec:** [人口と評価v0設計](../specs/2026-10-12-manager-population-v0-design.md)、[上位のaggregate-first設計](../specs/2026-10-12-manager-aggregate-first-design.md)。

## Global Constraints

- Python >=3.12、stdlibと固定ipfn/NumPy/pandas CPU依存。既存Life Manager runtime/credentials/schedulerを変更しない。
- ACS2024 5-year B17001、50州+DC51地域、対象はpoverty status判定可能人口。
- セル順、変数mapping、FIPS/splitはspecの固定値をそのまま使う。
- 開発6地域のjointだけでseedを作る。validation/testのjointは採点側にのみ渡す。
- IPF: normalized residual <=1e-10、max_iterations=1000、positive seed、非収束/欠測を成功値へ補完しない。
- report stage=empirical_reconstruction。behavior_prediction/policy/execution/fieldはnot_run。
- raw/run artifactsはGit外。各Taskの完了状態は統合SSOTへ記録する。

## Review Focus

- APIのHTML/redirect、別表B17001E、欠落headerを有効データにしない（Task1）。
- 負のsentinel、重複/不足地域、誤ったセル集計を補完しない（Task1/2）。
- 行順/入力によりsplitが変わったり、評価jointがseedへ混ざらない（Task2/5）。
- zero support、ゼロtarget marginal、収束しないIPFを成功populationにしない（Task3）。
- referenceやhash不一致、欠測の採点、模型/生活改善への誤った成果表示を拒否する（Task4/5）。

## File Structure

Create `apps/manager/pyproject.toml`, `README.md`, `src/manager/__init__.py`, `src/manager/__main__.py`。

Create `src/manager/population/{__init__,contracts,acs,prepare,fit}.py`、`src/manager/benchmarks/{__init__,population}.py`、`src/manager/{artifacts,cli}.py`。

Create `config/population-v0.json`、`tests/{test_acs,test_population_prepare,test_population_fit,test_population_score,test_population_cli}.py`、`tests/fixtures/population/*.dat`、`docs/population-v0.md`。package内の空initとconfigurationは、それを必要とするTaskへ含める。

Task間の型はspecのdataclassesで固定。各テストはunittest。以下のcommandはrepo rootで実行する。

---

### Task 1: 来歴付きの公式集計入力

**Files:** package metadata/init、`population/contracts.py`, `population/acs.py`, `tests/test_acs.py`, public miniature DAT fixtures。

**Interfaces:**
- `read_acs_extract(path: Path) -> tuple[SourceRef, tuple[dict[str,str],...]]`。取得manifest/hashは隣接manifest `source.json` から読む。入力は同じdirectoryの `source.dat`。
- `fetch_acs_extract(destination: Path, *, timeout_seconds: int=30, max_bytes: int=8388608) -> SourceRef`。
- Produces: specのSourceRef/JointTable/Marginals/FitResult/PopulationScore、`PopulationDataError(ValueError)`。

- [ ] **Step 1: Write failing tests.** `test_rejects_html_and_wrong_table`はHTML、B17001E header、必要header欠落をPopulationDataErrorとする。`test_rejects_duplicate_missing_and_negative_estimates`は重複・不足地域と負の必要estimateで例外。`test_extract_manifest_hash_matches_bytes`は保存したextract bytesへのSHA256一致、tamper後の拒否をassertする。networkはmockし、試験内に外部通信をしない。
- [ ] **Step 2: Run red.** `PYTHONPATH=apps/manager/src python3 -m unittest discover -s apps/manager/tests -p test_acs.py -v`。新package/import欠如でFAILを確認する。
- [ ] **Step 3: Implement.** metadata/packageと型validationを作り、公式DATをpipe区切りで読む。fetchはHTTP statusだけで成功にせずheaderを検証、exact52 state rowsの完了まで読み、specのサイズ/EOF条件を適用。state extract hashでありfull source hashではないとmanifestに記す。offline入力とfetchの検証を共用する。
- [ ] **Step 4: Run green.** 同じcommandで全ケースPASS。取得中断/上限のfixtureも失敗として返し、completed manifestを残さない。
- [ ] **Step 5: Commit.** `git add --sparse apps/manager`、`git commit -m "feat: add provenance-checked ACS aggregate input"`。

### Task 2: 年齢×貧困の集計と、評価入力の分離

**Files:** `population/prepare.py`, `config/population-v0.json`, `tests/test_population_prepare.py`。

**Interfaces:**
- Consumes: Task1 records。
- `aggregate_b17001(row: dict[str,str], source: SourceRef) -> JointTable`。
- `marginalize(table: JointTable) -> Marginals`。
- `partition_tables(tables: tuple[JointTable,...]) -> dict[str,tuple[JointTable,...]]`。keysはdevelopment/validation/test。
- `build_seed(development: tuple[JointTable,...]) -> tuple[float,float,float,float,float,float]`。

- [ ] **Step 1: Write failing tests.** `test_leaf_mapping_and_total`はspecの各leafに値を入れ六群とE001/E002/E031の一致をassert。`test_split_is_fixed_and_order_independent`は51件を並べ替えても6/4/41と同一FIPS集合。`test_test_joint_cannot_change_seed`はtest jointの値だけを変えてseedが同一。`test_marginals_carry_no_joint_fields`はMarginalsのdataclass fieldsがgeo_id/source/poverty/age/totalだけであることをassert。
- [ ] **Step 2: Run red.** `PYTHONPATH=apps/manager/src python3 -m unittest discover -s apps/manager/tests -p test_population_prepare.py -v`。
- [ ] **Step 3: Implement.** specのmappingを定数とし、親totalを二重加算しない。seedはdevelopmentのみ合計。configにFIPS、split、方法と評価versionを固定する。
- [ ] **Step 4: Run green.** 同じcommandでPASS。unknown/PR/exact non-state geographyを区別し、必要51の不足を成功splitにしない。
- [ ] **Step 5: Commit.** `git add --sparse apps/manager`、`git commit -m "feat: isolate population marginals and held-out references"`。

### Task 3: independentとIPFの人口再構築

**Files:** `population/fit.py`, `tests/test_population_fit.py`。

**Interfaces:**
- `independent_population(target: Marginals) -> FitResult`。
- `fit_population(seed: tuple[float,float,float,float,float,float], target: Marginals, *, tolerance: float=1e-10, max_iterations: int=1000) -> FitResult`。
- Both consume Marginals only; neither receives a target JointTable or file path。

- [ ] **Step 1: Write failing tests.** `test_independent_exact_product`はtotal100、poverty(30,70)、age(20,60,20)からcounts(6,18,6,14,42,14)。`test_ipf_matches_marginals_without_erasing_seed_relation`はpositive non-independent seedに別marginalsを与え、normalized residual<=1e-10と同じ2×2 cross-product ratioの保持をassert。`test_zero_target_is_zero_without_nan`はpoverty0のrowが全0。`test_zero_seed_and_nonconvergence_fail`はseed0とmax_iterations=1の未収束例をPopulationDataErrorとする。
- [ ] **Step 2: Run red.** `PYTHONPATH=apps/manager/src python3 -m unittest discover -s apps/manager/tests -p test_population_fit.py -v`。
- [ ] **Step 3: Implement.** 固定ipfn NumPy backendを薄いadapterから呼ぶ。target0の軸を除いてsolverへ渡し戻りを元shapeへ復元、残差とiteration上限を独立に確認。seed0をepsilonへ置き換えない。数値/total/marginal一致、nonfiniteを検証し、seed hash、target_source_sha256、iterationsを返す。
- [ ] **Step 4: Run green.** 同じcommandでPASS。uniform seedのIPFがindependentと一致することを追加確認し、IPFが未知の相関を発見するという説明を書かない。
- [ ] **Step 5: Commit.** `git add --sparse apps/manager`、`git commit -m "feat: reconstruct weighted cohorts with transparent baselines"`。

### Task 4: 独立した人口精度の採点

**Files:** `benchmarks/population.py`, `tests/test_population_score.py`。

**Interfaces:**
- `score_population(prediction: FitResult, reference: JointTable) -> PopulationScore`。
- `summarize_population(scores: tuple[PopulationScore,...], references: tuple[JointTable,...]) -> dict[str,object]`。
- Consumes predictions and separate reference; neither prepares seed nor fits a model。

- [ ] **Step 1: Write failing tests.** `test_same_marginals_can_have_wrong_joint`はref(15,10,5,5,50,15)、independent(6,18,6,14,42,14)でTVD=0.18、max_cell_error_pp=9。`test_zero_age_rate_is_unknown`は該当rate None。`test_mismatched_scope_or_total_is_rejected`は別geo/total/source hashで例外。`test_weighted_and_unweighted_scores_are_distinct`は異なる人口のfixtureで両平均を検証。`test_stage_never_claims_field_improvement`はstage/5track表示を固定する。
- [ ] **Step 2: Run red.** `PYTHONPATH=apps/manager/src python3 -m unittest discover -s apps/manager/tests -p test_population_score.py -v`。
- [ ] **Step 3: Implement.** TVD=0.5*sum(abs(normalized cell differences))。率/pp単位とpoint-estimate referenceを明記。全体meanだけでなく各地域と各年齢群を出す。ACS MOEを独立と仮定した正確なCIやreal-life outcomeへ転用しない。
- [ ] **Step 4: Run green.** 同じcommandでPASS。missing predictionを0点/完全一致へ補完せずcoverage不足として拒否する。
- [ ] **Step 5: Commit.** `git add --sparse apps/manager`、`git commit -m "feat: evaluate joint population fidelity independently"`。

### Task 5: 再現runnerとCLI、証拠report

**Files:** `artifacts.py`, `cli.py`, `__main__.py`, `tests/test_population_cli.py`。

**Interfaces:**
- `write_artifact(path: Path, payload: object) -> str`、canonical JSON/hashとatomic write。異なる既存結果を上書きしない。
- `main(argv: list[str]|None=None) -> int`。
- `fetch-acs --out DIR` → `source.dat` / `source.json`。
- `prepare-population --input EXTRACT --out DIR` → `seed.json`, `marginals.jsonl`, `split.json`, `manifest.json`, `reference/all.jsonl`。referenceはscoreだけが読む。
- `reconstruct --seed SEED --marginals MARGINALS --method independent|ipf --out FILE` → predictions。reference引数なし。
- `score-population --predictions FILE --predictions OTHER_FILE --reference REFERENCE --manifest MANIFEST --out DIR` → `report.json` / `report.md`。--predictionsはrepeatable、split別に集計し、developmentをtest成績へ混ぜない。

- [ ] **Step 1: Write failing tests.** `test_offline_cli_is_reproducible`は同fixtureを別run directoryへ実行し数値結果/hash一致。`test_reconstruct_never_opens_reference`はreference読み取りをfailするmockでもreconstructが成功。`test_hash_mismatch_and_existing_different_output_fail`は改変input/異なる出力の上書きを拒否。`test_complete_report_has_all_methods_regions_and_cost_scope`は2method/51region、split/source、paid_model_calls0、field not_runをassert。
- [ ] **Step 2: Run red.** `PYTHONPATH=apps/manager/src python3 -m unittest discover -s apps/manager/tests -p test_population_cli.py -v`。
- [ ] **Step 3: Implement.** Task1–4のinterfaceを接続する。reference/all.jsonlをscoreだけに渡し、split.jsonで各partitionを別採点する。reconstructionはmarginals/seedのみ。config/source/extract/code identity、method数値設定、wall timeと欠測/失敗をmanifestへ。最低入力coverageを満たさない比較はnonzero exit。
- [ ] **Step 4: Run green.** `PYTHONPATH=apps/manager/src python3 -m unittest discover -s apps/manager/tests -v`。全offline tests PASS。network/model callsなしを確認。
- [ ] **Step 5: Commit.** `git add --sparse apps/manager`、`git commit -m "feat: add reproducible population benchmark commands"`。

### Task 6: 実資料での比較と説明の完成

**Files:** `apps/manager/README.md`, `docs/population-v0.md`。実raw/run/reportはGit外へ、実験receiptをSSOTへ。

**Interfaces:** Task5 CLI。使うstate extractはpreflight receiptのhashを照合し、正規source manifestをTask1形式で作る。hash不一致なら別snapshotへ。

- [ ] **Step 1: Run offline gate.** `PYTHONPATH=apps/manager/src python3 -m unittest discover -s apps/manager/tests -v`。PASSを確認。
- [ ] **Step 2: Run real integration.** `PYTHONPATH=apps/manager/src python3 -m manager fetch-acs --out /workspace/artifacts/manager-population/input`。続けて以下を実行する。合成fixtureをreal integrationへ転用しない。

```bash
PYTHONPATH=apps/manager/src python3 -m manager prepare-population --input /workspace/artifacts/manager-population/input/source.dat --out /workspace/artifacts/manager-population/prepared
PYTHONPATH=apps/manager/src python3 -m manager reconstruct --seed /workspace/artifacts/manager-population/prepared/seed.json --marginals /workspace/artifacts/manager-population/prepared/marginals.jsonl --method independent --out /workspace/artifacts/manager-population/independent.jsonl
PYTHONPATH=apps/manager/src python3 -m manager reconstruct --seed /workspace/artifacts/manager-population/prepared/seed.json --marginals /workspace/artifacts/manager-population/prepared/marginals.jsonl --method ipf --out /workspace/artifacts/manager-population/ipf.jsonl
PYTHONPATH=apps/manager/src python3 -m manager score-population --predictions /workspace/artifacts/manager-population/independent.jsonl --predictions /workspace/artifacts/manager-population/ipf.jsonl --reference /workspace/artifacts/manager-population/prepared/reference/all.jsonl --manifest /workspace/artifacts/manager-population/prepared/manifest.json --out /workspace/artifacts/manager-population/report
```

- [ ] **Step 3: Inspect report.** 対象51、split6/4/41、対象定義、セルmapping、別表拒否、whole-sourceではないhash、group error、全費用/失敗、他track not_runを確認。IPFが負けても値を残す。Validation/testを見て設定を変更した場合はexploratoryと記録し、同setでconfirmatory claimへ戻さない。
- [ ] **Step 4: Document actual evidence.** READMEに実際のcommandと結果、ACSの推計誤差、地域転移の限界、未来予測/因果/生活改善を測っていない範囲を書く。3repo研究方法との差を説明し、Aaru/Simile内部モデルを再現したとは書かない。
- [ ] **Step 5: Commit and review.** `git diff --check`とsource-boundary、offline suiteを確認してdocsをcommit。whole-branch reviewでspec/plan/report一致を確認し、通常のPR/merge経路へ。source branch pushを本番deploymentと扱わない。

## Scope Coverage and Handoff

このplanはPopulation/Evidence/Evaluationの基礎のみ。Response/World/Policy/Executorの実装とfieldは後続の独立planへ。記事、連絡、イベント、website、履歴書/YCは統合SSOTの活動順で並行し、このplanのコードtaskへ混ぜない。

計画review後の推奨executionはNative: 私が一つずつ実装し、focused testで確かめる。完成後に独立whole-branch reviewを行う。現時点では計画作成と公開資料preflightまで。Task1–6は未実装。

## Patch-level decomposition

6Taskを[原子パッチと取得元](2026-10-12-manager-atomic-patches.md)に分解した。ここは比較の受入仕様、補足は取得/変更の具体的手順。status正本はSSOTのみ。
