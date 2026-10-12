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

このrunの`quality-self-heal.json`は不正JSONです。

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

W-01のquality self-heal artifactがJSONとして読めず、品質判定の再現に使えません。

**次手:** receipt parseabilityをcodeで別評価し、parse failureをagent quality FAILやPASSへ置換しません。

## 境界

このinventoryはeval frameworkの性能結果、model順位、収益効果、lab採用、AGI能力を示しません。

公開前quality PASSは外部impactや収益成果ではありません。

E01のmain由来release adoption/natural evaluationは未完であり、実行cursorは統一SSOTから動かしません。
