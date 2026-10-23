# Step-by-Step published-effect audit v1 — protocol proposal

2026-10-23 UTC。**Protocol ID: `MGR-D014-STEP-PUBLISHED-EFFECT-AUDIT-V1`。PRIVATE_FINAL_PROPOSAL / ROOT_CONDITIONAL_PURPOSE_ACTUAL / FRESH_AI_TECHNICAL_REVIEW_R1_R2_ACTUAL / SOURCE_ADOPTION_AND_D014_D015_ACCEPTANCE_PENDING。**

## 1. 有限scopeと凍結済みprotocolとの接続

本案は既に公表された非個人のRCT集計効果・欠測仮定をretrospectiveに検証するsource-specific protocolである。人への新たな曝露・接触・尺度実施・個人連結は含めない。公表結果を読んだ後に作った案であり、前向き登録・盲検分析・独立したraw RCT再現とはしない。Managerの使命は「行動変容を通じて、苦しみを終わらせることを目指す」。この検証を行動変容の実効果、臨床的承認、覚り・AGI・苦の終結の証明としない。

凍結済み[公開集計Route A/B protocol](PUBLIC_AGGREGATE_COLLABORATION_PROTOCOL.md)と[人対象の安全protocol](MENTAL_OUTCOME_SAFETY_AND_INDEPENDENT_REVIEW.md)に接続する別文書であり、両文書、旧5項目の[manifest](RESEARCH_PROTOCOLS_20261022.sha256)、旧hash/受入を全文bytesで保持する。本案の既公表intervention研究効果は、全国surveyのcontext統計とも、Route Bの新たに作る人研究集計とも区別する。公開licenseは実協働/endorsementを成立させない一方、全offline再利用へ企業提携・NDA・新規参加者・署名役割を一律追加しない。

[新規U004草案](BEHAVIOR_TRANSFORMATION_STUDY_V2.md)はDRAFT / NOT_REGISTERED / participants=0 / intervention_runs=0、D014/D015のsource採用/task受入はPENDING。この新文書自体の将来hash/commitやrootのsource採用/task受入を本案内で先取りしない。実source採用時のversion/hashは、rootの後続adoption receiptで外部から固定する案とし、別のhash manifest・registry・解析frameworkを追加しない。

## 2. Sourceと用途・利用権


対象はCuijpersら、[PLOS Medicine 2022原著](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004025)、DOI `10.1371/journal.pmed.1004025` の**既公表Table3集計効果と欠測仮定の検証**に限る。[原著XML](https://journals.plos.org/plosmedicine/article/file?id=10.1371/journal.pmed.1004025&type=manuscript) はPLOS corpus `/1/pmed.1004025.xml`、取得UTC `2026-10-23T19:53:09.737066+00:00`、SHA-256 `dcb633928041f081770bb18158fa3dde1af1bfda9095d122baf1c1754ffa574c`、Table DOI `10.1371/journal.pmed.1004025.t003`。原著XMLは[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)を表示する。著者・原著・DOI・license・抽出/正規化した点を帰属表示する。これは原著の許諾であり、教材・尺度の実施/配布・audio・code・dataset・モデル学習へ自動継承しない。

[DANS公式dataset metadata](https://ssh.datastations.nl/api/datasets/:persistentId/?persistentId=doi:10.17026/dans-zey-hjpk) はDOI `10.17026/dans-zey-hjpk`、v1.0、RELEASED `2022-05-16T22:00:00Z`、取得UTC `2026-10-23T19:53:34.684583+00:00`、metadata SHA-256 `0df93c326c84f7de3c2ec69fbe9ef97a818fd0a8a249705cace82422142cbf8e`。利用条件は別のDANS Licenceで、`SbS_Syrian_Anonymized_Final.tab` は **restricted=true / fileAccessRequest=true**。個票もpublic migration archiveも未取得。原著の「匿名データavailable」を無条件の公開accessとせず、本案では個票を取得しない。raw独立再解析は **UNAVAILABLE_WITHOUT_ACCESS_REQUEST / NOT_PERFORMED**。

[権利registry](../docs/research/source-rights.json)への単独追加案は `who-step-by-step-published-effects-v1`、実article licenseは **CC-BY-4.0**。rootは下記実receiptでこの限定用途を条件付承認した。study_read/local_researchは**正確な最終review済みsource統合後に限るallowed_with_conditions**、raw redistribution/product use、学習、人への介入、live/publicationはこのpurpose外のHOLD。これらHOLDはCC BYが許す一般的用途を否定する法的主張ではなく、本root用途の範囲を示す。現在はPRIVATE案でsource未追記/未採用、最終delta R2は実完了済みだが、source統合/受入はPENDINGである。

## 3. 原著の設計と4行の公表結果


原試験はLebanonのdisplaced Syrians、guided Step-by-Step対enhanced care as usual。個人1:1、長さ2–8の可変permuted block割付、assigned **283 / 286 = 569**。PHQ-9とWHODAS-12 2.0は別endpoint、posttestと3か月follow-upは同じ試験の反復時点で、4独立研究へ数えない。この569人はManagerの参加者ではない。

以下の推定量は**AUTHOR_REPORTED_NOT_INDEPENDENTLY_REPRODUCED**。公表された4行×9値=36値の独立転記照合は実施済み36/36一致だが、個票/seed/codeからのITT/MI/RFLB統計再現はNOT_PERFORMED。B/SEは各原尺度のscore points、gは著者報告Hedges g、CIはgの95% CI。負のBは低い症状/機能障害、正のgは改善方向の符号化を示す。RFLBの下限/上限と各SEは、通常のCIへ置換しない。

| endpoint | 時点 | MI B (SE) | Hedges g [95% CI] | RFLB B下限 (SE) | RFLB B上限 (SE) | 時点observed/missing n |
|---|---|---|---|---|---|---|
| PHQ-9 | posttest | −2.81 (0.66) | 0.48 [0.26, 0.70] | −4.78 (0.84) | −0.89 (0.83) | UNKNOWN / UNKNOWN |
| WHODAS-12 2.0 | posttest | −3.27 (0.98) | 0.35 [0.14, 0.56] | −6.63 (1.37) | 0.11 (1.35) | UNKNOWN / UNKNOWN |
| PHQ-9 | 3か月follow-up | −3.63 (0.72) | 0.61 [0.37, 0.85] | −5.85 (0.99) | −1.27 (0.94) | UNKNOWN / UNKNOWN |
| WHODAS-12 2.0 | 3か月follow-up | −4.28 (1.13) | 0.45 [0.22, 0.68] | −8.00 (1.54) | −0.20 (1.41) | UNKNOWN / UNKNOWN |

原著Model1は **150 multiple imputations / MAR**、群別multivariate normal regressionとiterative MCMC、gはRubin rulesで統合。Model2は **Random Forest Lee Bounds / MNAR for differential attrition**。prescore/background controlsの説明は原著methods/Table3 footnoteを保持し、個票なしにdesign matrixや同じ推定量の実行を再構成しない。posttest WHODASのRFLB上限+0.11を隠さない。

原著のlost-to-follow-upは **167/283、133/286**、定義は「posttest又はfollow-upでoutcome measuresを回答しなかった参加者」。この定義を特定時点のmissing nへ置換せず、assignedから差し引いて時点observedを作らない。本4行の時点別observed/missing nは**未抽出/UNKNOWN**であり、元試験全体に情報が存在しないという主張ではない。費用は **UNKNOWN**。原著はserious adverse event 1件を報告し関連なしと評価したが、これは著者のassessmentであり、独立した安全再解析やゼロリスクを意味しない。

## 4. 実役割・適用判断・受入境界


公開source取得と私有engineering案の作成は実AI agent `/root/public_behavior_reuse_applicability` が行った。別contextのfresh AI technical reviewer `/root/public_behavior_protocol_task_review` によるR1は**実施済み、1 Nit / 0 blocking**。私有receipt `task-1-review.md`、SHA-256 `2cbaf08fcc2fcb4c544eafc8be69c7b204eb0b63e244fad0558d92982d592732`。これはsource/数値/権利/scopeの技術照合であり、別法人/人間/臨床の独立性、臨床資格、独自runtime model attestationは主張しない。唯一のNitは歴史的abstract引用の参照語として修正済み。実R2は同じ別context AI reviewerによるdelta-only read-only review、**0 findings / 0 blocking、Nit FIXED/CLOSED**。私有receipt `task-1-review-r2.md`、SHA-256 `79710ab80c7f3bae0a6614b9b2628215a01627a3c6e422435fd553df1aa786fc`。R2は新たなGET/統計再現/人間や臨床の独立審査を含まない。

| fresh R1で実再取得したsource | request開始UTC | raw SHA-256 |
|---|---|---|
| PLOS XML | 2026-10-23T20:05:26.668211+00:00 | `dcb633928041f081770bb18158fa3dde1af1bfda9095d122baf1c1754ffa574c` |
| DANS metadata | 2026-10-23T20:05:27.526758+00:00 | `0df93c326c84f7de3c2ec69fbe9ef97a818fd0a8a249705cace82422142cbf8e` |
| Mindful XML | 2026-10-23T20:05:28.903697+00:00 | `6ee6aa4fc5a76a4bdadecb9186debe9f470cc541e10d28e8f81c4155fafb0506` |

3 GETは各raw bytes hashが宣言pinと一致し、PLOS Table3全36値が一致した。fresh R1はCC BY法文を新たにGETしたものではなく、原著XML license表示と既存pinを確認した。公表数値の独立照合をraw統計再現や元RCTの独立実施へ昇格させない。

root AI engineering/research reviewer `/root` は **2026-10-23T20:11:35.036894+00:00** に、既公表非個人集計のattributed retrospective audit、source/claim停止・訂正という技術適用範囲を、正確な最終source統合とNit修正を条件に受入した。私有decision basename `root-purpose-and-technical-applicability-decision.md`、SHA-256 `1d79b26cd6e3423d9b49ca4621f59d9b110917a9b9b6aeed1672325c8d4af31a`。この実用途/技術適用判断は、source採用・D014/D015 task status受入とは別eventであり、後者は現在PENDING。

このoffline活動は公表済み非個人集計の読取・検証だけで、新規接触・介入・尺度実施・個人連結を含まない。原参加者への再同意、提携/NDA、臨床staff、正式IRBを普遍的な必須条件にはしない。所属機関/管轄等への制度適用は **UNKNOWN**、正式承認/免除は **NOT_OBTAINED**。本案は臨床・法的・IRB判断を発行せず、AI技術reviewもその代行ではない。将来新規人研究へ進む時だけ、その実活動に必要な同意・実在する実施/安全役割・適用判断を別に成立させる。

本案は既公表結果を見て選んだretrospective published-effect audit。将来のversion/hash固定を前向き登録・元RCTの独立raw再現と呼ばない。D014/D015のsource採用/task受入は **ACCEPTANCE_PENDING**、新規U004はDRAFT/NOT_REGISTERED/参加者0のまま。rootの条件付用途/技術適用判断とfresh R1の実source再照合は上記receiptの範囲で成立済み。最終差分のfresh R2は上記実receiptの範囲で完了した。正確なsource統合・rootによるsource/task受入と新version/hashの外部固定はまだ行っていない。

許される将来の成果はsourceと公表数値/仮定を検証する能力の評価に限る。Managerへの実曝露、本人の行動、苦しみ/生活機能、持続、害、臨床治療効果、覚り・AGI・苦の終結を実証したとはしない。人への昇格は既存D016/V004等の別gateを維持する。[本protocolのoffline停止/復旧](#5-offline停止復旧)を適用候補とする。

## 5. Offline停止/復旧

以下は本protocolの非個人公表集計の取得/抽出/claimに限る停止・訂正案であり、凍結済み安全protocolの人研究条件や数値triggerを改変しない。participant-facing活動がないこのscopeでは、人への危機monitoring・臨床staff・24h対応は **NOT_APPLICABLE_TO_THIS_OFFLINE_ACTIVITY**。臨床安全性の承認という意味ではない。人研究へ拡張する場合は、その実活動について同意・撤回・必要な実在する安全/研究役割・連絡/支援経路を別に確認する。

| offline signal | 停止/保護 | 復旧条件 |
|---|---|---|
| source hash、版、権利条件が記録と一致しない／未確認 | ingestion・抽出・関連claimをHOLD。別bytesを同一版として上書きしない | 原sourceの版/rightsを再確認し、差分と採用判断を記録。実fresh技術照合が終わるまで再開しない |
| 個票・private回答・linkableな情報に遭遇 | 追加取得/表示/転記を止める。匿名化目的で先にdownloadしない。偶発素材をsource・issue・model promptへ複製しない | 個票を含まない承認済み公表素材だけへ戻し、適用するprivacy対応とsource確認を記録 |
| source訂正/撤回、endpoint/timepoint/分母の不整合 | 問題のあるclaimと抽出結果を停止/限定。以前の版と問題を残し、不明はnull/UNKNOWN | 訂正根拠と影響範囲を記録し、fresh技術reviewがsourceと訂正値を照合。時間経過で自動解除しない |
| 公表効果をManager効果、raw独立再現、前向き登録、ゼロリスクや臨床承認へ誤昇格 | そのclaimを取り下げ/訂正し、採用/作用への接続をHOLD | AUTHOR_REPORTED_NOT_INDEPENDENTLY_REPRODUCED、source母集団、未測定のManager結果、未取得の承認を正しく記録し、fresh照合とroot用途判断を実記録 |

現scopeのroot条件付用途判断とfresh R1のactor/実GET時刻は§4の実receiptに記録した。将来のsource変更・訂正からの再開は、その変更に対するfresh再照合と必要なroot判断を改めて実記録する。現在のsource統合/受入はPENDINGであり、実R1/R2を未来の復旧やsource採用の受入へ流用しない。このauthor自身による転記確認はfresh reviewの代替ではない。原著serious eventの「関連なし」は著者assessment、費用UNKNOWNはUNKNOWNのままとし、原著平均の改善で個人の害やrare eventを排除しない。

このprotocolはoffline ingestion/claimの停止と訂正を定義する案である。新規研究の発動、clinical/legal/IRB clearance、D014/D015の完了を記録しない。旧5項目manifestと凍結文書はそのまま保持し、本案の未来のbytes/受入へ遡及適用しない。


### 作成時点snapshotと後続source採用の区別

本v1のPRIVATE_PROPOSAL/PENDING表記や、固定したrights recordの`final_delta_review_status=PENDING`は各案を作った時点のsnapshotで、後続の実R2/採用を永久的に拒否する条件ではない。実R2受領は上記receipt（`79710ab80c7f3bae0a6614b9b2628215a01627a3c6e422435fd553df1aa786fc`）により記録済みで、rights recordのreview済みcanonical bytesは履歴のまま保持する。**このsource統合案の段階ではroot SOURCE_ADOPTION / D014_D015_STATUS_ACCEPTANCEは依然PENDING**。将来、rootが実採用した時だけ、その実eventと本protocolの最終version/hashを[既存D014/D015 receipt](../docs/verification/D014_D015_PROTOCOL_ACCEPTANCE_20261023.md)等の外部採用記録から一方向に固定する。本科学定義へ未来の自己hash/commit/採用時刻を書き込まず、rightsへprotocol未来digestを逆pinしない。新規U004/人への実効果の受入とは引き続き別である。
