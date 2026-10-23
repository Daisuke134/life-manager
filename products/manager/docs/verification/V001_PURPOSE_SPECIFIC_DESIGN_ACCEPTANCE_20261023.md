# V001 用途別の有限記述設計 — root受入receipt

**FINITE_DESCRIPTIVE_DESIGN_ACCEPTED。** 独立review・実source適用と同一payload照合後、rootは既存4有限診断役割の設計だけを受入した。V001 done、113件＝81 done / 22 todo / 10 skipped。旧literal UNMET/HOLD、一般化・訓練・便益・実運用の未受入は変わらない。

## 受入判断と変更理由

rootは[用途別追補](../specs/2026-10-23-v001-purpose-specific-acceptance-amendment.md)の有限constructed-benchmark取込/開発記述scopeを明示採択し、既存4診断役割の対象・単位・参照/権利binding・採点/未採点・分母/null・隔離設計だけをV001設計gateとして受入する。有限集合を記述する対象に実人物/研究/時間holdoutを一律要求していた旧scopeを用途別に改訂するためであり、モデル成績の良否を理由にしない。遡及mappingを新規preregistrationや独立final testへ変更しない。

旧change/verify/scope原文は[直前V001全行](V001_PURPOSE_SCOPE_PREVIOUS_ROW_20261023.json)と[以前のscope archive](BEHAVIOR_SCOPE_PREVIOUS_ROWS_20261023.json)、追補の引用へ保存する。元の3adapter fixture受入、旧80 done、S003の別研究holdoutは、この新しい設計受入の代用にしない。[不変旧contract](../../experiments/behavior-model/v001-evaluation-contract-v1.json)の`/authority/acceptance/v001_full=HOLD`と原hold_reason “Person/study/time holdouts are unavailable; intake, selected dev and observed coverage are not independent heldout evaluation.” を保存し、旧literal条件は**UNMET/HOLD**のままである。

## 今回の正確な対象と非該当の意味

[用途metadata](../../experiments/behavior-model/v001-purpose-applicability-v1.json)の4役割だけを対象にする。各役割のperson/study/time計12軸は、明示した有限記述targetに限ってNOT_APPLICABLEと判断する。availabilityはUNAVAILABLEのまま、未知版・汚染・意味familyの未確立はUNKNOWN/UNAVAILABLEのままにする。field欠落だけでN/Aにせず、N/Aを成功holdoutに数えない。未知人物、別研究、未来、新generator/新応答への主張は今回の対象外HOLD。

| 役割 | 対象・単位・契約上の限界 |
|---|---|
| INTIMA取込/未採点生成 | 固定synthetic promptと32×3条件=96 assigned response rowsの生成可能性。prompt-generatorは応答generator/judgeと別役割。NOT_SCORED、圧力/依存/害/行動変化/便益はnull/未測定。未知上流judge版の再現を主張しない |
| HelpSteer2固定dev8 NLL | 正確な元prompt/candidate対、8 groups/16 forwards、token NLLと元preferenceの有限一致だけ。NO_ACTION棄権とaccuracy=nullを区別。新応答のgoldでない。final16 PROPOSED/NOT_RUN、original32から除外後train27/32 NOT_READY、training rights HOLD |
| XSTest元応答3class | 全450の開発割当と元Mistral応答へのexact joinだけ。released-rule/local judgeと元goldのlabel agreement/errors。既往partial coverage・UNKNOWN/NOT_RUN・local設定DECLINED・no-resumeを保存 |
| XSTest native-binary別protocol | [不変native protocol](../../experiments/behavior-model/xstest-qwen3guard-binary-protocol-v1.json)の全450 assigned、primary423 extremes、partial27は無採点分布のみ。独立native-binary goldなし、policy mismatch維持。旧3classを上書きせず、異なる分母/classのaccuracy比較をしない |

dataset・prompt生成model・元応答generator・現在の採点model・upstream/current judge・baselineを混同しない。正確な版/package/template/parser/順序/membership/label/資源/停止/分母は旧contractと別native protocolから参照し、未知版を既知へ変えない。Source.verify_contentとOutcomeBench reproduction_manifestへの既存bindingはP0で、can_execute=false。source取得時刻は観測時刻でなく、exact hash/joinは元応答bindingであって意味familyの非重複・汚染なし・未見性の証明ではない。scalesや母数を単純合算せず、assigned/valid/failed/UNKNOWN/NOT_RUN/ABSTAIN、zero-denominator=null、未測定nullを保持する。

FINAL用に予約したdataは**公開/非公開とも学習・few-shot・retrieval・モデル選別から隔離**する。公開benchmarkの明示development/calibrationは露出・選別履歴を保存し、後から独立finalへ昇格しない。既存evaluation-only・選別禁止・許諾制限は緩めない。今回の対象は既存有限development membershipの設計であり、将来train/dev/test split・独立評価manifestを受入していない。

## 限定source auditの証拠

設計/先行source基準headは`42e3281a14d6f98360b6d9ff34587c22afc032e2`。本統合提案のworking baselineはnative8文書受入後の`420b24626d325c8d32f969e6ea1c08c56fdb1f6b`。これは最終統合source commitではない。旧contract SHA256は`f0b0644e52a92516a05273cf7cb663a5ef056f0646ecb0ec28e61f97b870a8a8`、別native protocolは`58c15f812202236e92b27bd704ea37f3803288749f03c1fcb4039f58600cec7f`。native予測/結果はscope設計・独立設計review時に未読であり、その後に完了したnative診断の品質もこの設計受入の根拠には用いない。既存native receiptを含む旧結果文書は各履歴の所有者として保存する。

13refsは現source bytes、旧基準head bytes、各commit:pathのimmutable bytesとSHA256がすべて一致することを限定確認した。pathは`products/manager/`相対。raw dataset/予測/個票の再検証、生成来歴・独立性・合法性の認定ではない。

| ref | immutable commit | path | SHA256 |
|---|---|---|---|
| rights | `96d67e6f13f61f4812361d6d6568e05bcc4219dd` | `docs/research/source-rights.json` | `9e138472f4b6ee0e8873bd9a41e99c097d43fe8be976978faf76f10ef6bc45ad` |
| source | `a65d2f8be024be43b6ae29b172d3f5417384cceb` | `manager_core/models/source.py` | `ae2b673c970f0e7d4e25c0c44323e0f9128bd7d2513485c44af826ce616d7cf8` |
| outcome_bench | `a65d2f8be024be43b6ae29b172d3f5417384cceb` | `manager_core/outcome_bench.py` | `7a7621d20d25463d24bda62fecc49b1c5c235a117a23ca38075e8fec0e6c336f` |
| intima_adapter | `a65d2f8be024be43b6ae29b172d3f5417384cceb` | `manager_core/intima_benchmark.py` | `8b7c6ff3f6a6cab039bf590bfa7b2af7840c3920909f7b211de725e3d35f7282` |
| helpsteer2_adapter | `9d05252e2c062a44c9553a2352d6b557f9602cb4` | `manager_core/helpsteer2_candidate_eval.py` | `2498f00de9d1be4c99b1850c37d733b7361d9809c76f36824e5e7573dd943d1e` |
| xstest_adapter | `088acd6c13525c9b279a0e9bb58d5d0a1479b820` | `manager_core/xstest_refusal_eval.py` | `38ca145f43ef018d3ef70791103ad38d89c60801ddd1d75a5da1cabc09e131ef` |
| helpsteer2_protocol | `a344e55e5a6e4eb098d8eeee188b73f048106db3` | `experiments/behavior-model/helpsteer2-dev-protocol-v1.json` | `586d8701a26305ea56ffab0d095db72d4fb64974977528d7581511ff7c8ef529` |
| xstest_protocol | `3fb1754f8e0ab2998574b66bc7348a57ad4b8af9` | `experiments/behavior-model/xstest-local-refusal-judge-protocol-v1.json` | `8d5a20a4172d790ee8b0265ae44655ca35e289fed40207ac8baf6eee012cf010` |
| intima_receipt | `96d67e6f13f61f4812361d6d6568e05bcc4219dd` | `docs/verification/INTIMA_CPU_DIAGNOSTIC_20261023.md` | `e444e5d116a565de168836eddfbb251551a202774365170a97c3376c4c4e0e49` |
| helpsteer2_receipt | `96d67e6f13f61f4812361d6d6568e05bcc4219dd` | `docs/verification/HELPSTEER2_DEV_CPU_EVALUATION_20261023.md` | `7c5ea0f14e59a1d9408e752dad6586bd1d55ab367b45b1354376b1dfe1c1198e` |
| xstest_released_receipt | `96d67e6f13f61f4812361d6d6568e05bcc4219dd` | `docs/verification/XSTEST_RELEASED_REFUSAL_CALIBRATION_20261023.md` | `204c5362e720302920d4e6c33158355fce9944cf0dc8a45f41e01be008e223ee` |
| xstest_local_receipt | `96d67e6f13f61f4812361d6d6568e05bcc4219dd` | `docs/verification/XSTEST_LOCAL_JUDGE_CPU_20261023.md` | `075c1182a51349c7f5b74dd2e66ad1799d9243b786865564b6a1191a5d1d33d7` |
| cpu_model_receipt | `96d67e6f13f61f4812361d6d6568e05bcc4219dd` | `docs/verification/LOCAL_CPU_MODEL_ACCEPTANCE_20261023.md` | `cf9694a2c075b45d16829569589b4e2e7e714032b89c30f66165af8282ca7a3b` |

既存3rights recordはrecord_idで解決し、完全recordをUTF-8 JSON・sort_keys=true・ensure_ascii=false・separators=(comma,colon)でcanonical化したSHA256とartifact pointerを確認した。別nativeも同じXSTest rights ID/hashを参照する。既存の条件付き評価・出典表示・非公開raw境界を保存し、training/product/raw redistribution HOLDを追加授権に変えない。

| record_id | canonical SHA256 | artifact pointer |
|---|---|---|
| `intima-prompts` | `224655bd770231efbdc4ee381c2f3d94d93c07bef54ceaf78f12ce6338ad4386` | `/artifact` |
| `helpsteer2-candidates` | `0b76b970e877dc17a6fc21c18979c9c7efaf4e1e6053c01a9c13577ee2920a41` | `/artifact` |
| `xstest-mistral-refusal-private` | `e3f0f0d53269eb52d54ebd8b2feccf8654cf433dce0fbc746a875fbbdabf434d` | `/artifact` |

先行の独立科学/設計reviewと5-file source仕様/品質reviewはPASS、各0 findings / 0 blocking。監査識別用の証拠名と読取bytesのhashは以下。私有review本文やrawはsourceへ同梱しない。これらのreviewは本root統合差分の最終reviewを代替しない。

- v001-amendment-draft/design-review.md — SHA256 `1932ae2f8d8e5057c84c598386c0401d37fad15577e7644d2549b3835428e688`。
- v001-purpose-source-sdd/task-1-review.md — SHA256 `7da09f188d6760b1fd43443a8e8d6c057971e3ec216d0885bc8e9779272b7718`。
- v001-purpose-source-sdd/source-adoption.patch — SHA256 `8a456f35665bcc55ccc329f3b635c9da9f0f04321d0e0bcd3d0c8c57340fb445`。

依存K014/R006/S003は既存tasks.jsonでいずれも実際にdoneで、行を変更していない。K014はfixtureでの共通kernel契約、R006はartifact権利register、S003は別sourceのstudy-ID漏洩guardという元の受入意味を維持する。S003の170/40 study splitを本4役割のholdoutへ流用しない。新しいtest/CIや全suiteを実施したとは主張しない。

今回のbounded stdlib静的確認は、JSON parse、113 unique IDs/依存順、他112行object一致、全original_*と旧archive、直前V001行の42基準object一致、13refs/3rights、4役割12軸・null・partial27無採点・FINAL隔離、内部JSON pointer/新相対リンク、README履歴/SSOT他lane suffixのbyte保持、22残件ID/81・22・10の算術を対象にする。既存make_roadmap.pyを私有stagingへそのまま複製し、実出力ATOMIC_BACKLOG.mdだけを新tasksから生成する。不存在のimplementation mapや新view engineは追加しない。sourceへ適用せずgit apply --check --whitespace=errorでworking baselineとの適用可能性を確認する。個々の実行結果・patch/payload hashは私有integration reportに残す。

## 解除しないgate

- V002はtodo。同じ入力/権利/分母/予算/coverage、NO_ACTION/ルール/既存model、独立評価・上流scorerと人手照合の全受入が別に必要。拒否判定だけで害/圧力/依存/便益を認定しない。
- V003はtodo。V002受入、具体的なtrainable deficit、適法なbase/data、最終train/dev/test membership・露出履歴、実compute/予算、別実行判断が必要。original32を成立扱いにせずtrain27/32 NOT_READY・rights HOLDを保持。現人物/文脈/言語/時間holdout/OODを満たせない研究を始めるには、V003自体の別scope改訂/reviewが先。実未使用test/baseline比較と一般化・採用はさらに別gate。
- V004/D016とV005/V006はtodo。真正な実結果と保護、未見評価、既定OFF、予算/権限、STOP/復元と独立readback、第三者再現・持続・異集団の元gateを維持する。
- 全Gはtodo。G001/G002の憲章・責任・設計だけrootのV001実受入後に進められる。live作用・権限変更・一般化受入を与えず、G003以後の依存を短絡しない。他112task rowは厳密object一致。

新holdout、judge calibration/adoption、訓練、優位/同等性/一般化、人の便益、安全性、live authorityの受入は0。原32件や将来splitも未受入である。

## root実イベント

- 実受入記録UTC: `2026-10-23T19:25:39.926533+00:00`。actorは所有者の継続指示に基づくCodex rootのAI技術/設計review。人間の法律/倫理/研究承認や新しい人手評価ではない。
- 最終統合独立review: 0 findings / 0 blocking、SPEC/QUALITY/INTEGRATION PASS。report SHA256 `ed2c4b45fd78f6e56b5d0ee758539bf4bec86c4c211d347f49b9b0a47da18598`。
- 適用直前source: `3bada454efaff896c4a425c8e3f362708e13e77b`。review済み12-file patch SHA256 `2a06fe551c838fa94d6df915fc192834ebee0a9f12d14ff543251750661eafa0`を実適用し、全12payload bytes一致を確認後、この実イベントと現在表示だけを更新した。
- 私有の実適用proof SHA256 `60d54ed9269f4ac3bffa8a4220f136bb2f16aac99cea554182d30ebc66fd4d79`。13 refsのcurrent/immutable commit:path hash、3 canonical rights、K014/R006/S003 done、他112行不変、81/22/10をrootが実照合した。旧literalはUNMET/HOLD。
- source guardの実FAIL/exit2（canonical host path不在）と、既存の明示cloud作業許可を区別して保存し、偽PASSにしていない。
- 判断: 対象/推定量に適合した有限記述設計を明示採択・受入する。独立未見評価、学習、採用、作用権限、人の便益の受入は0。新しいsourceや用途は別評価する。
- このreceiptは自身を含む最終commit hashを先取りしない。commit/pushとGitHub refの実readbackはrootの別統合記録で確定する。main統合やproduction昇格ではない。
