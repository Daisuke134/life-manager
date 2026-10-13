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

Identity/CTAの不一致は人手ラベル待ちのcandidateです。

公開中の製品CTAが内部context leakか、judgeの誤検知かは、記事全体と読者文脈を見たdomain expertが決めるまで未確定です。

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

**Expected outcome:** domain expertの人手ラベル後に固定します。ラベル前にfalse positive/true positiveを決めません。

**Judge境界:** JSON/schema、CTA receipt、publication stage、receiptの有無はcodeで判定し、public性とinternal contextの意味判定だけをLLM judgeに残します。

**Human label:** domain expertのreviewを依頼中です。ラベルはheld-outではなくdevelopment dataとして扱います。

**未計測:** judgeのTPR/TNR、記事task全体の失敗率、費用控除後net、記事のreadership、売上uplift、source-specific before/after、複数trialのばらつきです。

## A4 failure taxonomy (development-only)

以下は重複しうるfailure/stage分類です。件数はcase discovery用であり、率や性能scoreの分母にはしません。

| Class | 自然traceでの観測 | 評価上の扱い |
|---|---|---|
| `english_draft_absent` | 8件中3件 | quality gate未到達。quality failとは判定しない。 |
| `quality_receipt_absent` | English draftありの1件 | quality outcomeは`unknown`。 |
| `quality_gate_advisory` | gate receiptがある4件中3件 | advisoryはquality failともquality passとも数えない。 |
| `identity_cta_disagreement` | W-01の1件 | identityの意味判定はhuman label pending。false positive/true positiveを決めない。 |
| `quality_self_heal_record_unparseable` | W-01の1件、0-byte JSON artifact | deterministicなevidence-integrity failure。内容品質とrecovery結果は`unknown`のままにする。 |
| `source_lineage_missing` | 8件中8件 | provenance failure。agent task failureとして数えない。 |

**A4で選ぶ最初のfailure class:** `quality_self_heal_record_unparseable`。存在・byte length・JSON/schemaはcodeで採点でき、identity/CTAの人手判定を待たずに評価境界を作れます。W-01のartifact SHA-256は上記の値ですが、`harness_git_hash=UNKNOWN`なのでsource-level reproductionは未達です。これはcase discoveryの選定であり、A5 case cardや回帰試験の完了ではありません。E01 cursorも進めません。

## A5 case card — W-01 empty self-heal record

- **case_id:** `writer-quality-self-heal-empty-w01`
- **task:** W-01のquality self-heal artifactがparse可能かを判定する。内容品質やidentity/CTAの意味labelは採点しない。
- **initial_state:** natural run `20261011-210544`、English draftあり、identity `C: FAIL` / CTA `PASS`、publication前にblock。`gates/quality-self-heal.json`は0 bytes、SHA-256=`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- **allowed_tools:** この1 artifactのread-only readと標準JSON parserのみ。
- **budget/constraints:** input上限1,000,000 bytes（read-only review endpointの既存上限）、model calls 0、network requests 0、provider/browser actions 0、external effects 0。
- **expected_outcome:** evaluatorは`receipt_unparseable` / `artifact_integrity=FAIL`を返す。writerのdraft-stageは`PASS`、pre-publication qualityとrecovery outcomeは`UNKNOWN`、publicationは`blocked-before-publication`、settled netは`UNKNOWN`。identity/CTAのhuman labelはpendingのまま保持する。
- **outcome_dimensions:** `task_completion=UNKNOWN`（draftはあるがquality stageがterminalにならない）、`quality=UNKNOWN`、`safety_gate=ALLOW`（gate値だけ）、`effect_integrity=UNKNOWN`（公式readbackなし；publication stageは`blocked-before-publication`）、`settled_net=UNKNOWN`、`cost_coverage=UNKNOWN`、`latency=UNKNOWN`、`human_intervention=UNKNOWN`（自然run内の介入記録なし、semantic labelは別途pending）。
- **provenance/split:** `natural_observation` / `development`; `harness_git_hash=UNKNOWN`。source-level replayはlineageが回復するまで不可。held-outではない。
- **evidence_refs:** private Writer trace `run_id=20261011-210544`, artifact `gates/quality-self-heal.json`; sanitized summary in this document under Candidate W-01.

このcardはcase定義であり、grader実装、source再現、agent performance測定の完了ではありません。外部receiptや費用がない状態を売上0へ変換しません。Case-level dimensionsを揃えても、canonical E02のCFO receipt/cost join完了とは扱いません。

## A7 code grader — W-01 receipt parseability

`apps/life-manager/eval/writer/receipt-grader.js`は匿名化したcase入力をstdinから受け、artifact SHA-256、UTF-8/JSON parseability、既存v2 receipt schema、self-hash、receipt chain/重複、publication stageをcodeで判定します。入力・artifactのサイズを制限し、path/network/providerアクセスを行いません。

W-01の0-byte artifactに対するgradeは、artifact hash `pass`、receipt parseability `fail`、publication status `pass`（`blocked-before-publication`）、reason `quality_self_heal_record_unparseable`です。receipt schema/id/duplicateは解析可能なreceiptがないため`unknown`。task completion、content quality、effect integrityも`unknown`、settled netは`null`です。

`npm run test:writer-eval`で9件のgrader testsとW-01 CLI出力を検証します。別のsynthetic valid v2 fixtureはschema/receipt hashのcontrol testだけに使い、natural case数、writer performance、qualityやrevenue scoreへ数えません。grader出力は一つのcode-checkable evidence dimensionであり、A8のsemantic judge calibration、自然source reproduction、E02の公式receipt/cost joinは未完です。

## A3b source provenance — current Writer atom

自然trace inventoryでは8 runすべて`harness_git_hash=UNKNOWN`です。実run `20261011-210544`のprivate `git-hash.txt`も同じです。最新mainの`article-daily.sh`はGit履歴からSHAを取りますが、現行immutable release `3e19c8463a1751b8c3c5a7c3a273330d4280b2f2`には`.git`がありません。loop applyはそのrelease SHAを`LIFE_MANAGER_RELEASE_SHA`として渡し、`writer-runtime-env.sh`も保持する一方、capture経路が使っていません。

A3bではvalidな40-hex env SHAを優先し、local checkoutではGit fallbackを残すfocused regressionを追加します。過去runのSHAは推定しません。W-01 0-byte receiptの過去原因、quality、netは引き続きunknownです。既存publish occurrenceの`effect_unknown` fenceは変更しません。
## 優先findings

### 1. Source lineageが不足

8件の記事runでsource SHAが不明で、子call summaryもrelease SHAを直接保持しません。

event IDだけに依存する結合は現行保持範囲で25/276件です。

**次手:** case/fixの前に親`run_id`・`occurrence_id`・`release_sha`を子agent evidenceへ直接結び付け、event retention後も再現可能にします。

### 2. Identity judgeが人手較正されていない

現物には人手label、TPR/TNR、false-pass、false-failの集計がありません。

**次手:** W-01のhuman labelを保存し、別caseを集めてからlabelをtuning用とheld-out用に分けます。

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
