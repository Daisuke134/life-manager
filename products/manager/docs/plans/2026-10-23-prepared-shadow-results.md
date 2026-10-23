# Prepared Catalog Shadow Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 選定済みの同じ公開入力からP0比較を行い、同じprivate checkpointへ保存・ACK後提示し、fresh restoreで原比較を要求追加0で再提示できるsource境界を作る。
**Architecture:** 既存shadow callerを同入力の比較関数へ抽出し、旧wrapperを保持する。同じSQLiteへoptionalな結果1表を追加し、既存provider intent/budgetと参照照合する。公開projectionは固定allowlistとし、host/CLI/workflowには接続しない。
**Tech Stack:** 既存Python stdlib/SQLite/unittest、既存PrivateCheckpoint/CheckpointedProvider。新しい依存・frameworkなし。
**Spec:** 同directoryの `2026-10-23-prepared-shadow-results-design.md` と研究仕様§1.3.2の順2のみ。U003の実consumerは `products/manager/docs/product/FIRST_WEDGE.md:93` 以降。SDKはmain `f29c10074d7ac31327b5d6247d0f656f20d4c4db`への通常統合・研究同期後を実装前提とする。

## Global Constraints

- 「P0比較を同じprivate `cycle.sqlite`へ保存しcheckpoint ACK後に提示する」「保存結果の再読で新しいcreateをしない」「intentだけ残る場合はUNKNOWN／要照合のまま」。
- 「旧checkpointとの互換も検証する」「raw応答・provider ID・秘密を出さない」。推論は既定OFF、同入力化/保存から実有用性・人の便益・実行権限を推定しない。
- source受入と公開projectionの準備のみ。host/CLI/workflow/production/credentials/予算設定/モデル要求/新ID/台帳件数は変更しない。source guard既知FAILを緩和しない。
- root採用済み: 同じoperation IDでも実prompt/body hashが変われば `UNKNOWN / INPUT_BINDING_MISMATCH`、create0。保存対象は `COMPARED_P0` のみ（invalid model outputも含む）。UNKNOWNを新terminal cacheにしない。
- 参照sourceはSDK branch `be055dffd922ba887345183c4e4c192f86a3cef9`（統合済みmainと対象bytes同一）。実装はrootが確定した専用worktree/branchで行い、以下は全てrepo相対path。

## Review Focus

1. cache/off/不適合で隠れた初期化: planner・client factory・BudgetLedger constructor・provider要求が不要に走らない（Task1/2の0-call検査）。
2. 同operation IDの入力変化: retrieved_at/goal等でprompt hashが異なる旧結果を、新しい比較として表示しない（Task2 `test_changed_prompt_same_operation_is_unknown_without_create`）。
3. 中断とACK損失: intentだけ・BOUNDだけを成功にせず、結果保存ACK不明は永久fence、再読で再送しない（Task2のintent/ACK検査）。
4. 不正snapshot: 結果表のschema/JSON/PK/FK/intent/budget参照不一致を新しい空stateへ修復しない（Task2のrestore拒否検査）。
5. 情報漏洩と権限化: model reason/provider ID/任意keyが公開に混入せず、期限切れscopeやcached PROPOSEも実行権限・新しい成果にならない（Task1のprojection/期限検査、Task2の原run/time保存検査）。

---

### Task 1: 同じprepared入力のP0比較と公開projection

**Files:** Modify `products/manager/manager_core/{ampersand_api.py,owned_provider_shadow.py}`; Test `products/manager/tests/test_owned_provider_shadow.py`。既存ファイル以外のproduction moduleは作らない。

**Interfaces:**
- Consumes: `OwnedChangeContext`, `TechnicalAssessment`, `OwnedDigitalScope`; `prepare_owned_change(context, assessment, scope, now, schema="manager.digital-handoff.v2")`; `render_prompt(context.planner, fictional=False)`; 既存 `_canonical_operation`/`_base_fields`/`CheckpointedProvider.initial`。`OwnedDigitalScope` は `authority.py`、`Callable`/`Any` はstdlib `typing`から参照する。
- Produces in `ampersand_api.py`: `initial_request_body_hash(prompt: str, instructions: str = DEFAULT_INSTRUCTIONS) -> str`。既存 `read_initial_turn` のcanonical JSON `{model: MODEL, instructions: instructions, input: prompt, environment: {type: "none"}}`（ensure_ascii=False, sort_keys=True, separators=(",", ":")）のUTF-8 SHA256をそのまま抽出。hash protocolを変更しない。
- Produces in `owned_provider_shadow.py`: `compare_prepared_catalog_shadow(checkpoint: PrivateCheckpoint, prepared: tuple[OwnedChangeContext, TechnicalAssessment, OwnedDigitalScope] | None, *, now: datetime, run_id: str, enabled: bool = False, client_factory: Callable[[], Any] | None = None, cap_usd: Decimal | None = None, upper_usd: Decimal | None = None, deadline_monotonic: float) -> dict`。
- Old `run_catalog_shadow(checkpoint, client, checkout, workspace, source_commit, *, run_id, enabled=False, cap_usd, upper_usd, deadline_monotonic) -> dict` はsignature・既存preflight順序を保持し、plannerを一度だけ呼び、上記へ `client_factory=lambda: client` で委譲する互換wrapper。
- Produces `public_catalog_shadow_summary(result: dict) -> dict`。private辞書を展開せず、下記固定keys/enumから新辞書を作る。

- [x] **Step 1: 失敗テストを書く。** 既存 `make_catalog_fixture`/`client_for`/`OwnedProviderShadowTests.owner` で一度だけ実planner fixtureのtupleを作り、次を同classへ追加する。
  - `test_prepared_shadow_never_replans`: 準備後plannerをAssertionErrorにpatchして比較し、`self.assertEqual(result["status"], "COMPARED_P0")`、`self.assertEqual(sessions.create_count, 1)`、baseline/candidate bytes不変をassert。
  - `test_initial_request_hash_preserves_existing_journal_identity`: helper値を既存fake initial要求後の `amp_sessions.body_hash` と照合し、既存canonical要求の式が変わらないことをassert。
  - `test_prepared_disabled_invalid_scope_deadline_and_unsupported_do_not_initialize_provider`: enabled=Falseは他引数不備でもSKIPPED/DISABLED、enabled=1はValueError。None候補/current-page criteria/expired scope/deadlineは既存静的理由でSKIPPED、factory/create0。invalid finite/type configurationもfactory0。
  - `test_public_projection_is_fixed_and_never_echoes_private_fields`: private model reason/未知key/provider IDへ識別markerを入れ、公開keysが下記集合と完全一致しmarkerなし、INVALID_MODEL_OUTPUTをPASSに変換しないことをassert。未知top-level reason/不正flagは静的ValueErrorのみ。
- [x] **Step 2: REDを実行する。** `cd products/manager && env PYTHONPATH=.:tests python -m unittest test_owned_provider_shadow -v`。新API不在の失敗を確認し、実exit非0をprivate logへ残す。
- [x] **Step 3: 上記Interfacesを最小実装する。** standalone helperは型・exact bool・positive decimal run ID・aware now・finite deadline・active checkpointを検査し、同tupleの `prepare_owned_change` とpublic promptを再検証する。既存action2種だけ、source/bytes/scope検証は緩めない。DISABLED判定は他の処理より先。
  - client factoryとcap/upperは新送信にだけ必要。新送信時はfinite Decimalを既存 `provider_budget._money` の範囲/精度で検査し、設定済みの不正値は固定ValueError・factory0、未設定なら `SKIPPED / PROVIDER_NOT_CONFIGURED`。既存provider境界で予算・intent ACK→送信を守り、factoryエラーもraw例外を返さない。
  - 成功辞書は既存P0 fieldsを保持し、host UTCの `compared_at: str` を成功時一度だけ付加する。model parser/invalid状態・NO_ACTION/rules比較・action_writes0は既存処理を使う。private model reasonは既存bounded parsed値だけでraw応答は保存しない。
  - result schemaは既存 `manager.catalog-shadow.v1`、statusは `SKIPPED|UNKNOWN|COMPARED_P0`。reasonは現sourceの既存値と、新規 `INPUT_BINDING_MISMATCH|PROVIDER_NOT_CONFIGURED` の固定文字列のみ（下記列挙を正本とする）。
  - reason集合: `DISABLED, DEADLINE_EXPIRED, PLANNER_UNCERTAIN, NO_CANDIDATE, UNSUPPORTED_CONTEXT, UNSUPPORTED_ACTION, CONTEXT_REVALIDATION_FAILED, PRIOR_INTENT_RECONCILIATION_REQUIRED, BUDGET_EXCEEDED, PROVIDER_TRANSPORT_UNKNOWN, MODEL_RESPONSE_PARSED, INPUT_BINDING_MISMATCH, PROVIDER_NOT_CONFIGURED`。
  - 公開keys: `schema,status,reason,run_id,compared_at,operation_id,context_sha256,baseline_digest,candidate_digest,baseline_decisions,model_status,model_decision,model_comparison,proof_level,authorized_execution,causal_support,human_outcome,action_writes,settled_cost_usd`。未存在の比較値はNone、baseline_decisionsは `{no_action,rules}`、model_comparisonは `{no_action_same_decision,rules_same_decision}`（各bool/None）を固定。decisionはPASS/ASK/PROPOSE、model_statusはMODEL_ADVICE_P0/INVALID_MODEL_OUTPUT/Noneのみ。scope/packet/URL/自由reason/provider IDを公開しない。
  - 公開flagは常にP0/False/False/NOT_MEASURED/int0/None。選択する値の型・hash・run/time・enumを検査し、不正値は内容を含まない `ValueError("invalid catalog shadow record")`。未知keyはコピーしない。
- [x] **Step 4: GREENを実行する。** 同unittestと `python scripts/check_boundaries.py` が成功、既存shadow regressionにskip追加なし、git diff --check成功を確認する。
- [x] **Step 5: 独立レビュー・commit。** このtaskのsource/API・境界だけをreviewし、指摘対応後に明示pathだけstageしてcommit。host/CLI/workflowの差分0を確認する。

### Task 2: 同じcheckpointへの保存・検証・要求0の再読

**Files:** Modify `products/manager/manager_core/{owned_provider_shadow.py,owned_checkpoint.py}` and `products/manager/tests/test_owned_provider_shadow.py`; Create `products/manager/tests/test_owned_catalog_shadow_results.py`。

**Interfaces:**
- Consumes: Task1のAPI/結果形・hash helper、`PrivateCheckpoint.save()`、既存 `validate_provider_tables`、既存provider4表と `CheckpointedProvider._operation_id("initial_", operation_id)`。
- Produces in `owned_provider_shadow.py`: `validate_catalog_shadow_results(db: sqlite3.Connection, tables: set[str]) -> None`; `_read_saved_comparison(checkpoint: PrivateCheckpoint, *, operation_id: str, body_hash: str, expected_fields: dict) -> dict | None`; `_save_compared_result(checkpoint: PrivateCheckpoint, *, body_hash: str, result: dict) -> dict`。
- `expected_fields` はTask1が同入力から作った `_base_fields` の全6keys（operation_id/context_sha256/baseline_digest/candidate_digest/candidate/sources）。lookupのNoneは保存行なし、dictは原比較または静的UNKNOWN。corrupt保存はCheckpointUnavailable＋fenceであり、cache missへ落とさない。

**Schema / serialization（このtaskの固定契約）:**
- Optional groupは結果1表 `catalog_shadow_results(operation_id TEXT PRIMARY KEY NOT NULL, body_hash TEXT NOT NULL, result_json TEXT NOT NULL, FOREIGN KEY(operation_id) REFERENCES amp_sessions(request_id))`。旧checkpointで表なしは受容。表があれば空でも既存provider4表が全て必要。部分schema/PK/FK不正・重複・参照不一致は拒否。既存4表のgroup規則を変更しない。
- 結果行はCOMPARED_P0だけ。JSONは32,768 UTF-8 bytes以下、sort_keys=True/separators=(",", ":")/ensure_ascii=False/allow_nan=False。既存 `collaboration._strict_pairs` / `_no_nonfinite_constant` を再利用し、duplicate key/未知keyを拒否する。raw prompt/応答・新しい秘密は保存しない。
- JSON共通keysは `schema,status,reason,run_id,compared_at,proof_level,authorized_execution,causal_support,human_outcome,action_writes,settled_cost_usd,operation_id,context_sha256,baseline_digest,candidate_digest,candidate,sources,baseline,provider,model_comparison,model_status`。MODEL_ADVICE_P0時のみ `model_advice` を追加、INVALID_MODEL_OUTPUT時は追加せずmodel_comparison=None。
- 固定値はCOMPARED_P0/MODEL_RESPONSE_PARSED、既存schema/P0 flags。原run IDとUTC aware ISOのcompared_atを保存し、再読で書換えない。hashはlowercase64桁、operation IDは `catalog_shadow_`+64桁。candidateはaction/targetだけ、actionは既存2種、targetは既存PUBLISH_PREFIX+PAGES。sourcesは既存 `_source_records` の正確な3keys、source ID重複なし、既存 `digital_environment._url` とSHA検査を使う。
- baselineはno_action/rulesだけで既存advisory_receiptの形。model_adviceも同形、既存parse_advice/allowed source IDsで検査し、P0 flagsを固定。model_comparisonの2boolは保存したdecision間の等値と一致させる。providerは既存5keys(session_id/turn_id/status/input_tokens/output_tokens)、status=completed、IDは既存prefix/長さ、tokensはNoneまたは0..10**10のint（bool不可）。
- 行operation_id=JSON operation_id=amp_sessions.request_id、行body_hash=amp_sessions.body_hash、intent.status=BOUND、JSON provider.session_id=同intent.session_id。派生budget IDのreservationが必須、成功行にRESERVEDは不可（UNKNOWN_USAGEまたはTOKENS_OBSERVED_COST_UNSETTLED）。usage有りならJSON token2値も一致、settled_units/settled_costはNULL/Noneのまま。usage不明を0にせず、既存Usage/予算validatorの範囲を再利用する。
- `owned_checkpoint._validate_database` は既存provider validatorの後にlocal importで新validatorを呼ぶ。module-topでshadowをimportしない。新validatorはDDL/constructor/save/plannerを呼ばないため、shadow→checkpointの既存importと循環実行しない。

- [x] **Step 1: REDテストを書く。** 新test fileでは既存shadow fixtureと `test_owned_checkpoint` のMemoryGateway/snapshotを再利用し、以下の境界を一つずつ検査する。
  - `test_completed_result_is_remote_acked_before_return`: 成功結果を返す時点でremote snapshotにvalid結果行があり、provider意図/予算ACKも先行する。結果保存にだけ失敗するtransportを使う対になる検査も用意する。
  - `test_fresh_restore_replays_original_comparison_without_initialization`: fresh cpへ復元、同prepared入力、factory/BudgetLedger constructor/plannerをAssertionErrorにpatch、cap/upper=Noneで `self.assertEqual(replayed, first)`、原run/time一致、create0・追加reservation0・結果行1件をassert。
  - `test_changed_prompt_same_operation_is_unknown_without_create`: retrieved_atだけを更新した同content入力でop ID一致/body hash不一致を確認し、`self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "INPUT_BINDING_MISMATCH"))`、factory/create0、保存行/原run/time不変。
  - `test_intent_without_result_is_unknown_for_reserved_unknown_and_bound`: 3状態全てでUNKNOWN/PRIOR_INTENT_RECONCILIATION_REQUIRED、body不一致ならINPUT_BINDING_MISMATCH、create0。BOUNDを完了と推定しない。既存shadowのprior-intent期待値をSKIPPEDからUNKNOWNへ更新。
  - `test_result_ack_loss_permanently_fences_without_success_or_retry`: local commit後のACK喪失は `with self.assertRaises(CheckpointUnavailable)` と `self.assertTrue(cp.broken)`、同cp再使用/解放不可。remote適用前ならfresh restoreはintent-only UNKNOWN、適用済みなら同保存比較の再読のみ、双方create0。
  - `test_old_snapshot_and_complete_optional_result_schema`: 結果表なしの旧snapshot受容、現行valid snapshotのfresh restore受容。import checkpoint→shadow／shadow→checkpoint両順をoffline subprocessで確認しSDK import/provider0。
  - `test_corrupt_result_restore_fences_before_any_factory`: missing column/PK/FK、provider4表欠落、duplicate JSON/NaN/未知key、operation/body/session参照差替え、budget欠落/RESERVED、不整合token/decision/flagsをsubTestで改変し、acquire拒否・cp.broken・factory/create0。壊れた結果を空表へ修復しない。
  - `test_expired_scope_or_deadline_cannot_turn_cached_propose_into_authority`: cached PROPOSEでも古いscope/期限は既存SKIPPED、factory/create0、packet/実行権限なし。正当な再読もaction_writes0・P0のまま、新比較件数を増やさない。
- [x] **Step 2: RED実行。** `cd products/manager && env PYTHONPATH=.:tests python -m unittest test_owned_catalog_shadow_results -v`。保存/API不在の実exit非0を残す。
- [x] **Step 3: Interfaces/schemaを実装する。** 新tableを新比較成功後の同一SQL transactionでCREATE+INSERT（OR REPLACE禁止）しcommit/close→checkpoint.save→ACK後return。ACK/検証不明を成功へcatchしない。
  - helperは既存preflight/同tuple再検証→現在のprompt/context/request hash計算→保存結果読取→既存intent確認→新送信config/予算/client生成、の順。cache hitは原辞書を返し、run/timeを現runへ置換しない。current expected_fieldsまたはbody hashが異なれば静的UNKNOWN/create0。intent-onlyもUNKNOWN/create0。
  - 保存を読む際は同じDB validationを行い、corruptならcpをfenceする。比較表がないだけならDDLなしでmiss。valid cache readではcap/upper/client_factoryが不要で、BudgetLedger初期化によるcap変更やcheckpoint追加も起こさない。
- [x] **Step 4: GREEN実行。** 新testと `env PYTHONPATH=.:tests python -m unittest test_owned_provider_shadow test_owned_provider test_owned_checkpoint -v`、境界検査、diff検査を実行。保存field以外の旧wrapper契約を維持し、skip/xfailやguard緩和を追加しない。
- [x] **Step 5: 独立レビュー・commit。** 5 Review Focusを新diffと実RED/GREEN証拠で確認し、明示pathだけcommit。rootが最終integrated headの必要なsuite/CIを確認して通常main統合する。host接続/activationは別段のまま。

## 判断済み事項・限界・self-review

- hash-only方針を保持する。DB単独でcontext SHAからrequest SHAの逆算、元promptの再構成、remote completed turnの再証明はできない。validatorはintent/budget参照整合、current prepared inputは両hashと全base fieldsを照合する。BOUNDだけを成功認定しない。
- 日時だけ変わる再planningも厳密には新入力なので再読失敗となる。元のsame-input比較を取り出す機能であり、新しい観測に旧モデル判定を転用する機能ではない。新しい有用性・成果・課金確定を認定しない。
- Spec coverage: 同入力/保存/ACK/replay/UNKNOWN/公開/旧snapshotを2taskへ割付済み。Interfaces名・kwargs・keysを統一。5 Review Focusは全て明示negative testあり。sourceは3ファイル、追加production module0。host/CLI/workflowと実model比較は意図した範囲外。
- Task1/2のsource実装と個別reviewは完了。最終focused70/full430 tests成功、skip0、各reviewは仕様・品質PASS／指摘0。rootのブランチ全体review・公式CI・通常main統合は未完了。元113件の台帳は変更していない。host接続・推論ON・有用性の認定は含めない。
