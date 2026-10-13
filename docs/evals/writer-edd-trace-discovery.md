# Writer EDD trace discovery

## 範囲

この記録は Writer の英語記事を公開前に評価する Pilot A の trace discovery です。

記事本文、CTA URL、provider receipt、raw prompt、顧客データはGitへ複製しません。

自然runと子agent呼び出しを別の分母として扱い、ここに記す件数から失敗率やbenchmark scoreを算出しません。

## 記事単位の自然run

観測時刻は 2026-10-12T15:14:46Z です。

8件すべてのrun directoryを既存の`article-daily.log`へ照合しました。

| 観測されたstage | 件数 | 解釈 |
|---|---:|---|
| English draftなし | 3 | identity/CTAの評価結果なし |
| English draftあり、English quality gate receiptなし | 1 | 最終quality判定なし |
| English quality gate receiptあり | 4 | task-level case discoveryに使える |

4件のうち3件は`identity=PASS`、`CTA=PASS`、`editorial/reader=ADVISORY`、`safety=ALLOW`でした。

残る1件は`identity=FAIL` category `C`、`CTA=PASS`、`blocked-before-publication`、`tracked_source_unchanged=true`です。

W-01の`quality-self-heal.json`は存在しますが0 bytesです。SHA-256は`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`で、JSON parseは`JSONDecodeError`になります。

8件すべての`harness_git_hash`は`UNKNOWN`であり、各結果を現在のsource commitへ結び付けられません。

Identity/CTAの不一致は自然case候補ですが、意味判定はunknownです。no-human A8aのsynthetic referenceへ混ぜません。

記事全体と読者文脈の根拠が不足するため、製品CTAが内部context leakかjudgeの誤検知かはunknownです。false positive/true positiveへ数えません。

## 子agent呼び出しtrace

観測時刻は 2026-10-12T15:22:08Z です。

`agent-runner-evidence`には1,498 directory、うち1,469の`summary.json`があり、29 directoryはsummaryを持ちません。

`loop=article-daily`は276 summaryで、`writer-judge`が251件、`writer-agent`が25件です。

子呼び出しsummaryの`status`はsuccess 252件、failed 24件ですが、これは記事単位のtask成功・品質・売上の内訳ではありません。

276件すべてに`runtime_event_id`と`started_at`がありますが、summary自身に`run_id`、`owner_id`、`occurrence_id`、`release_sha`はありません。

現在保持される`writer/events.jsonl`へ結合できるのは25/276件です。

結合できるeventには子呼び出しのowner/run/occurrence/releaseが記録されていますが、8件の記事runとの親子bindingは確認できません。

したがって276 child callsを276件の独立記事taskとして採点せず、残る251件についてsource別の結果を主張しません。

## Candidate W-01

**Task:** English draftのidentity判定と必須CTA判定が食い違った自然runを、読者向けpublic referenceと内部context leakのルールで判定します。

**観測されたinitial state:** English draftあり、identity judgeはcategory `C`でFAIL、CTA gateはPASS、publication前にblocked、quality self-heal receiptは不正JSONです。

**Provenance:** natural run。原本はWriter private storeにありますが、source commitは`UNKNOWN`です。

**Expected outcome:** natural W-01のidentity/CTA semantic resultはunknownのままです。synthetic referenceはW-01へ流用せず、human label gateも設けません。

**Judge境界:** JSON/schema、CTA receipt、publication stage、receiptの有無はcodeで判定し、public性とinternal contextの意味判定だけをLLM judgeに残します。

**Human validation:** not performed. W-01は自然caseですが意味判定はunknownで、synthetic fixtureのmetricsには入りません。

**未計測:** judgeのTPR/TNR、記事task全体の失敗率、費用控除後net、記事のreadership、売上uplift、source-specific before/after、複数trialのばらつきです。

## A4 failure taxonomy (development-only)

以下は重複しうるfailure/stage分類です。件数はcase discovery用であり、率や性能scoreの分母にはしません。

| Class | 自然traceでの観測 | 評価上の扱い |
|---|---|---|
| `english_draft_absent` | 8件中3件 | quality gate未到達。quality failとは判定しない。 |
| `quality_receipt_absent` | English draftありの1件 | quality outcomeは`unknown`。 |
| `quality_gate_advisory` | gate receiptがある4件中3件 | advisoryはquality failともquality passとも数えない。 |
| `identity_cta_disagreement` | W-01の1件 | 意味判定はunknown。synthetic referenceへ混ぜず、false positive/true positiveへ数えない。 |
| `quality_self_heal_record_unparseable` | W-01の1件、0-byte JSON artifact | deterministicなevidence-integrity failure。内容品質とrecovery結果は`unknown`のままにする。 |
| `source_lineage_missing` | 8件中8件 | provenance failure。agent task failureとして数えない。 |

**A4で選ぶ最初のfailure class:** `quality_self_heal_record_unparseable`。存在・byte length・JSON/schemaはcodeで採点でき、identity/CTAの自然semantic判定とは独立して評価境界を作れます。W-01のartifact SHA-256は上記の値ですが、`harness_git_hash=UNKNOWN`なのでsource-level reproductionは未達です。これはcase discoveryの選定であり、A5 case cardや回帰試験の完了ではありません。E01 cursorも進めません。

## A5 case card — W-01 empty self-heal record

- **case_id:** `writer-quality-self-heal-empty-w01`
- **task:** W-01のquality self-heal artifactがparse可能かを判定する。内容品質やidentity/CTAの意味labelは採点しない。
- **initial_state:** natural run `20261011-210544`、English draftあり、identity `C: FAIL` / CTA `PASS`、publication前にblock。`gates/quality-self-heal.json`は0 bytes、SHA-256=`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- **allowed_tools:** この1 artifactのread-only readと標準JSON parserのみ。
- **budget/constraints:** input上限1,000,000 bytes（read-only review endpointの既存上限）、model calls 0、network requests 0、provider/browser actions 0、external effects 0。
- **expected_outcome:** evaluatorは`receipt_unparseable` / `artifact_integrity=FAIL`を返す。writerのdraft-stageは`PASS`、pre-publication qualityとrecovery outcomeは`UNKNOWN`、publicationは`blocked-before-publication`、settled netは`UNKNOWN`。identity/CTAの意味判定はunknownのまま保持し、synthetic referenceで補完しない。
- **outcome_dimensions:** `task_completion=UNKNOWN`（draftはあるがquality stageがterminalにならない）、`quality=UNKNOWN`、`safety_gate=ALLOW`（gate値だけ）、`effect_integrity=UNKNOWN`（公式readbackなし；publication stageは`blocked-before-publication`）、`settled_net=UNKNOWN`、`cost_coverage=UNKNOWN`、`latency=UNKNOWN`、`human_intervention=UNKNOWN`（自然run内の介入記録なし）、identity/CTA semantic resultも別軸でunknown。
- **provenance/split:** `natural_observation` / `development`; `harness_git_hash=UNKNOWN`。source-level replayはlineageが回復するまで不可。held-outではない。
- **evidence_refs:** private Writer trace `run_id=20261011-210544`, artifact `gates/quality-self-heal.json`; sanitized summary in this document under Candidate W-01.

このcardはcase定義であり、grader実装、source再現、agent performance測定の完了ではありません。外部receiptや費用がない状態を売上0へ変換しません。Case-level dimensionsを揃えても、canonical E02のCFO receipt/cost join完了とは扱いません。

## A7 code grader — W-01 receipt parseability

`apps/life-manager/eval/writer/receipt-grader.js`は匿名化したcase入力をstdinから受け、artifact SHA-256、UTF-8/JSON parseability、既存v2 receipt schema、self-hash、receipt chain/重複、publication stageをcodeで判定します。入力・artifactのサイズを制限し、path/network/providerアクセスを行いません。

W-01の0-byte artifactに対するgradeは、artifact hash `pass`、receipt parseability `fail`、publication status `pass`（`blocked-before-publication`）、reason `quality_self_heal_record_unparseable`です。receipt schema/id/duplicateは解析可能なreceiptがないため`unknown`。task completion、content quality、effect integrityも`unknown`、settled netは`null`です。

`npm run test:writer-eval`で9件のgrader testsとW-01 CLI出力を検証します。別のsynthetic valid v2 fixtureはschema/receipt hashのcontrol testだけに使い、natural case数、writer performance、qualityやrevenue scoreへ数えません。grader出力は一つのcode-checkable evidence dimensionであり、A8のsemantic judge calibration、自然source reproduction、E02の公式receipt/cost joinは未完です。

## A3c child-to-parent trace binding — current Writer cursor

Current private inventory has 251 `writer-judge` child summaries under `article-daily`. They contain `runtime_event_id` and model-generated results, but omit child owner/run/occurrence/release fields and parent Writer article/lifecycle IDs. `shared-model-runner.py` inherits `ARTICLE_RUN_ID`; loop launchd provides `LIFE_MANAGER_RUN_ID`, `LIFE_MANAGER_OCCURRENCE_ID`, and `LIFE_MANAGER_RELEASE_SHA`. The generic agent-runner writes the child runtime event but only copies `event_id` into summary.json.

A3c child-to-parent binding is merged in PR #7881 (`e2463ba9`) and CI passes. It does not copy article body or convert model verdicts to human labels. Historical child summaries remain unbound; they are not retroactively rewritten. The no-human A8 route uses synthetic references only; 8 historical article runs (7 retained run dirs) / 4 identity receipts remain separate natural-case candidates and stay unscored.

## A3b source provenance — current Writer atom

自然trace inventoryでは8 runすべて`harness_git_hash=UNKNOWN`です。実run `20261011-210544`のprivate `git-hash.txt`も同じです。最新mainの`article-daily.sh`はGit履歴からSHAを取りますが、現行immutable release `3e19c8463a1751b8c3c5a7c3a273330d4280b2f2`には`.git`がありません。loop applyはそのrelease SHAを`LIFE_MANAGER_RELEASE_SHA`として渡し、`writer-runtime-env.sh`も保持する一方、capture経路が使っていません。

A3bではvalidな40-hex env SHAを優先し、local checkoutではGit fallbackを残すfocused regressionを追加します。過去runのSHAは推定しません。W-01 0-byte receiptの過去原因、quality、netは引き続きunknownです。既存publish occurrenceの`effect_unknown` fenceは変更しません。
## 優先findings

### 1. Source lineageが不足

8件の記事runでsource SHAが不明で、子call summaryもrelease SHAを直接保持しません。

event IDだけに依存する結合は現行保持範囲で25/276件です。

**次手:** case/fixの前に親`run_id`・`occurrence_id`・`release_sha`を子agent evidenceへ直接結び付け、event retention後も再現可能にします。

### 2. Identity judgeの自然性能は未確認

人手label、TPR/TNR、自然記事のfalse-pass/false-fail集計はありません。A8a synthetic referenceは回帰用conformance fixtureで、人間との一致や自然性能を示しません。

**次手:** A9でtarget model/runtimeとsplitを固定し、A8bではsynthetic reference agreementのみを計測します。自然性能・readership・購入効果は公式outcome evidenceが揃うまでunknownに保ちます。

### 3. 小標本を性能と誤認しやすい

8件はfailure discoveryの初期sampleで、error-auditの粗い目安である約100件のsaturation確認や、50 Pass/50 Failに近いjudge validationには足りません。

これらは固定gateではなく、より広い代表sampleとuncertaintyを必要とすることを示す目安です。

276件の子呼び出しは独立記事taskではないため、sample数を水増しする根拠にしません。

**次手:** 正確な親子trace bindingが回復してからtask-level と child-judge sampleを分けて増やします。

### 4. Judge artifactのschema failureも計測対象

W-01のquality self-heal artifactは0 bytesでJSONとして読めず、品質判定の再現に使えません。

**次手:** receipt parseabilityをcodeで別評価し、parse failureをagent quality FAILやPASSへ置換しません。A4でこの分類を最初のeval対象に選び、case schemaと既存test対応はA5で確定します。

## 境界

このinventoryはeval frameworkの性能結果、model順位、収益効果、lab採用、AGI能力を示しません。

公開前quality PASSは外部impactや収益成果ではありません。

E01のmain由来release adoption/natural evaluationは未完であり、実行cursorは統一SSOTから動かしません。

## A8 Category C synthetic reference set

The versioned `apps/life-manager/eval/writer/fixtures/a8-category-c-reference-v1.jsonl` binds 40 synthetic Category C excerpts (dataset v3 SHA-256 `355729f17728c1ef8638cde71f8deca44a37619854f1be6995efdd11df3c1f39`) to 20 PASS and 20 FAIL expected labels. `reference_source=synthetic_policy_reference_v1`; these are explicit scenario references, not human labels, not natural Writer traces, and not evidence of human agreement or revenue. Reference rationales are excluded from prompts and metric rows.

The standard runner accepts only the versioned synthetic reference schema and rejects the optional offline review export. The review page is a local, non-gating audit aid; it does not upload or run the judge. Before any provider starts, `run-identity-cases.js` requires `--freeze-manifest` and checks dataset/reference/evaluator/runtime/split hashes, the Codex/Python/Node versions, and a single-candidate `composition-agent` config. Missing or mismatched freeze data, provider fallback, and runtime drift emit a preflight `effect=none`; the freeze ID/hash stay joined to predictions and metrics. A8b reports synthetic-reference agreement only. Natural W-01 remains separate with identity/CTA semantics unknown; the A8 fixture does not fill that gap. No real judge call is made before A9 creates the canonical freeze manifest and split.

**A8 metric contract:** `reference_label=PASS` is the positive fixture class. `reference_false_pass` counts reference FAIL / judge PASS; `reference_false_fail` counts reference PASS / judge FAIL. `reference_unknown` and judge `UNKNOWN` are counted separately and never converted to either class. Rates remain null until at least 20 synthetic references in each class exist and predictions are complete. Output scope is `synthetic_reference_agreement`, `human_validation=not_performed`; arithmetic availability is not judge acceptance or natural performance. `apps/life-manager/eval/writer/join-labels.js` validates canonical dataset version/SHA, reference-set version/SHA/source, freeze ID/hash, and case IDs, preserves missing predictions as UNKNOWN, omits rationale, and rejects human-export or mixed-freeze inputs without echoing them. `judge-metrics.js` rejects any non-UNKNOWN verdict without freeze provenance; all-UNKNOWN/no-freeze rows remain incomplete with null rates. `apps/life-manager/eval/writer/run-identity-cases.js --reference-labels <path> --freeze-manifest <path>` runs only the fixed case excerpts through the isolated identity gate; references/rationales never enter prompts. Fake-runner tests cover missing/stale freeze, provider fallback/version drift, the 20/20 gate, broker/nested rejection, per-case usage-ledger isolation, no label leakage, and the runner→joiner→metrics path. The label set is public and partitioned dev 20 / held-out 10 / challenge 10. The first A8b 40-case attempt returned UNKNOWN for every case (`malformed_judge_output`), so its metrics are incomplete and no baseline score is claimed. Diagnostic probe 1 returned no provider receipt or model-runner log and did not retain the usage error values. Probe 2 (`202d37501ba26ec82da5273240f4f7a1745c531c7ac89099d1efacfe9e48d06f`) returned generic `validation_or_task_failure` with no token/cost receipt. Probe 3 confirmed the sparse worktree omitted `skills/earn/marketing-engine/intel`, which agent-runner requires before provider start; no provider tokens or receipt were produced. The subtree is now present; Writer suite passes 33/33 and the frozen preflight is effect=none. Run2 produced 38 determinate and 2 UNKNOWN with incomplete metrics; context `writer-edd-a8b-baseline-run2-context-v1.json` SHA-256=`d81a6e2f1a22c65fc8cf2722c339bb19117cb3b607e65982443bcca3dbeb7e46` pins source HEAD and Treg tree. These public cases are not blind examples; do not use held-out/challenge case-level rows for tuning, and use new private/natural cases for blind benchmark claims. The optional review UI remains non-gating; the first model-runner attempts have no provider receipt, so provider completion is unverified, and human calibration remains not performed.


## A8b run2 diagnosis and run3 result

Run2's two UNKNOWN rows remain historical and incomplete; no score is claimed for that run. The separate diagnostic-only W-C-026 artifact `writer-edd-a8b-case-diagnostic-v1.json` has SHA-256 `db7b9888b531b0ca93e27c97aabf72c453d94083dbc71a4617ff1a2e8b1e79a8`; it records `codex_home_busy`, `provider_started=false`, rc 75, `prelaunch_provider_home_busy`, and no provider receipt. The A9 fixture pins `fail_fast_provider_lease=true`. This later probe supports the lock-contention failure mode but does not prove that the original run2 W-C-026 occurrence had the same cause.

The diagnostic exposed an evaluator observability bug: `agent_runner` writes the structured attempt error under the case's shared-runner evidence directory, but `identity-gate.sh` suppresses model-runner stderr and exits 3 when no verdict JSON exists. `run-identity-cases.js` now reads the case's structured attempt evidence before its temporary directory is removed and records `error_class`, `provider_started`, and usage measurement; it sets `effect=none` only when evidence proves the provider did not start. The judge verdict remains UNKNOWN and is never repaired into PASS or FAIL.

Run3 (`writer-a8-947781cf-d83b-4f27-80f9-57d25716c270`) used immutable A9 freeze v2 (`writer-edd-a9-codex-terra-medium-20261014-v2`, SHA-256 `5f40c682b01420ca7c7efa255c001f2b2a3a52828d267973fad3516ebd81c170`) and completed 40/40 predictions with zero runner error events. The metrics artifact reports `synthetic_reference_metrics_available`: 39/40 matched the public synthetic references, with 1 false-pass, 0 false-fails, TPR 1.00, TNR 0.95, and 0 UNKNOWN. Context `writer-edd-a8b-baseline-run3-context-v1.json` SHA-256 is `3058acab8eee6892aa60fda66ca7ed91cc08dd5f2fdb04304633c672ce8a287e`. Provider receipt count is 0, usage/cost was not retained, and `human_validation=not_performed`; this is not human agreement, natural article quality, revenue impact, blind performance, or evidence of lab adoption. The references are public development fixtures. Do not use challenge case-level results, including W-C-023, for tuning.

**Verification:** the new integration regression failed first with `malformed_judge_output`, then passed with the evidence-preserving classifier. `npm run test:writer-eval` passes 34/34; W-01 remains a code-grade fixture, not article quality or revenue evidence. The A9 v2 preflight event `writer-a9-preflight-6812a670-10ee-4b55-8b7b-568f9f7b9a67` records `phase=preflight`, `effect=none`, and no error; no provider started.

**Current cursor:** A8b run3 is integrated by PR #7948 (`837ba59af90ac004dc7e524b1115745358ab5935`); Security Scan run `38440330127` passed 11/11 jobs and issue #7943 is closed. The next canonical atom is DD01, followed by DD02–DD12 before A10. The broader EDD objective remains open: human calibration, natural-trace evaluation, and E01 main-derived release adoption are unverified, so keep them in their canonical SSOT order.
