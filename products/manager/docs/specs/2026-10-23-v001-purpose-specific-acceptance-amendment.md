# V001 用途別の有限記述設計scopeへの追補 — 有限記述設計の受入範囲

2026-10-23の用途別設計scope改訂。rootが[限定設計受入receipt](../verification/V001_PURPOSE_SPECIFIC_DESIGN_ACCEPTANCE_20261023.md)に実際のreview・適用・受入を記録した時に限り、既存4役割の有限集合の取込/開発診断設計を採択し、V001をFINITE_DESCRIPTIVE_DESIGN_ACCEPTED / doneとする。私有提案を独立review後に実適用し、rootの限定設計受入をreceiptへ記録した。旧literal条件のUNMET/HOLD、既存contract/protocol、権利、実行許可は変更しない。独立科学・設計reviewと先行5-file source reviewはPASS、最終統合reviewとroot受入はreceiptの実イベントで確定する。架空の実効UTC・人署名・最終source commitは作らない。native予測/結果はscope設計・独立設計review時に未読であり、その後の実験成績も設計受入の根拠にしない。

## 変更理由と効力

改訂前のV001は有限のconstructed benchmarkの取込・開発診断にも人物/研究/時間の実holdoutを一律要求する。これらの有限集合を記述する推定対象には、その全軸が必ずしも存在しない。一方、未見人物・別研究・未来時点等への一般化には、それぞれの主張を識別できる独立した評価が必要である。1つのsplitで全軸を同時に達成したと仮定しない。別々に測った軸の成績から、その交差targetの一般化も自動認定しない。

この追補は、観測済みの診断を未見testへ変更せず、有限集合の用途を明示した設計受入と、実未見評価・採用を分ける設計である。既存mappingは遡及対応付けであり、新しいpreregistrationではない。statusを通すための暗黙の解釈変更を避けるため、旧条件の未達、後日の対象限定、改訂理由・発効範囲を併記する。

## 保存する旧本文と旧判定

`products/manager/docs/roadmap/tasks.json` V001の改訂前change:

> 行動変容の公開benchmark/data/modelの版・権利・対象・split・採点契約を既存OutcomeBenchへ対応付ける

改訂前verify:

> 人対象研究を待たずoffline評価を開始できる。source/model/judge版、人物/研究単位と時間holdout、未評価null、拒否/失敗/分母を固定し、人の便益を主張しない

scope amendmentの改訂前V001行:

> 利用するartifactごとにsource/版/license/対象を確認。人物・研究・時間のholdoutを固定し、公開testを学習に混ぜない

現契約 `experiments/behavior-model/v001-evaluation-contract-v1.json` は変更せず保存する。`/authority/acceptance/v001_full` の **HOLD**、`/authority/hold_reason` の原文 **“Person/study/time holdouts are unavailable; intake, selected dev and observed coverage are not independent heldout evaluation.”**、各sliceのUNAVAILABLEとrequired_use=HOLDをそのまま残す。旧literal条件は現在も未達であり、本追補は達成証明ではない。旧protocol/receipt/result、停止・UNKNOWN・null・母数も書き換えない。以前のfixture受入や80 doneを新V001の受入へ流用しない。

## source適用で採択する正確な置換本文

V001 `change` の正確な本文:

> 行動変容に関する採用artifactと用途ごとに、版・権利・対象/推定量・評価単位・split設計・採点契約を既存OutcomeBenchへ対応付ける。取込、開発診断、独立未見評価を区別する。

V001 `verify` の正確な本文:

> 人対象研究全体の完了を待たず、用途別のoffline評価設計を受入できる。採用artifactごとにsource/dataset/model/judge版、利用権、対象集団/推定量、独立単位、最終評価用に予約したdataの隔離、採点/未評価null、拒否/失敗/UNKNOWN/分母を固定する。人物・研究・時間および対象に必要な内容family等の各軸について、適用の有無、理由、利用可能field、分割状態と証拠を記録する。最終評価用に予約したdataは公開/非公開を問わず学習・few-shot・retrieval・モデル選別から隔離する。開発/校正に明示利用する公開benchmarkは露出・選別履歴を残し、後から独立した最終testと呼ばない。既存の凍結protocolの用途制限と権利条件は変更しない。適用する未見評価は実key・membership・非重複・時間順序/境界・許容用途を実行前に固定する。利用不能/不明/未分割の必須軸はその用途の評価受入・一般化主張をHOLDし、NOT_APPLICABLEを達成済みholdoutに数えない。固定診断/設計の受入は、訓練受入、独立一般化、優位、人の便益、実行権限を与えない。

scope amendment §4のV001行の正確な本文:

> 利用するartifact・用途ごとにsource/版/license/対象/推定量と評価契約を確認し、適用する独立単位・splitを固定する。人物/研究/時間等の各軸を用途に照らして適用/非該当/利用不能/不明と判定し、必須軸が未成立の用途はHOLD。最終評価用に予約したdataは公開/非公開を問わず学習・few-shot・retrieval・モデル選別から隔離する。開発/校正に明示利用する公開benchmarkは露出・選別履歴を残し、後から独立した最終testと呼ばない。既存の凍結protocolの用途制限と権利条件は変更しない。設計/既存診断の受入と実未見一般化の受入を分ける。

このscope変更の意味:

> この改訂は、旧V001が要求した全artifactの人物・研究・時間holdoutを達成した記録ではない。有限benchmarkの取込/開発診断にも全軸の実holdoutを要求していた範囲を、対象/推定量に適合する設計受入へ改訂する。過去のprotocol、結果、HOLD判定は保存し、既存結果を新規事前登録・独立testに変更しない。人物・研究・時点等を越える一般化の科学的要求は、その主張を行う評価・採用段階に残る。

この隔離条件は将来の用途別設計に適用する。公開benchmarkを明示した開発/校正に使い、現judgeを棄却した既往はその履歴として保持する。予約した最終評価集合と開発集合を混同せず、観測済み結果を独立finalへ昇格しない。既存contract/protocolの原文、evaluation-only資料の学習/few-shot/retrieval等への禁止、既存の選別制限は緩めず、新たな利用権を与えない。

主仕様 §1.2–1.3.3はV001設計gate、V002比較gate、V003開始/評価/採用gate、V004実運用gateを区別して参照する。既存依存、original_*、旧archive、113 IDsと他112行は保存する。先行scope-only差分はtodo / 80 done・23 todo・10 skippedを保ったが、本最終統合提案では別receiptによる限定V001設計受入だけをdoneへ反映し、受入成立後の算術は81 done・22 todo・10 skippedとなる。私有提案作成時点ではsource適用と受入は未了で、その後の実状態は別receiptへ記録する。

## 小さな用途metadataの意味

[用途metadata](../../experiments/behavior-model/v001-purpose-applicability-v1.json) は既存contractを1参照し、既存13 refsと3つの権利record選択を再利用する追補である。権利の第二定義・license grant・engine・validator・scorer・trainer・runtime consumerを作らない。native-binaryはその別protocolへの追加参照だけであり、旧3classのprotocolを置換しない。hashは読んだmetadata bytesの整合bindingだけで、真正性・法的認定・未見性の証明ではない。

`availability`はfield/holdoutを実装・立証できるかを表し、現3sliceおよびnative-binaryの人物/研究/時間はUNAVAILABLEのままである。UNKNOWNも未確認の意味を保つ。実keyが存在しても分割していなければAVAILABLE_NOT_SPLIT相当であり、VALIDATEDではない。

`applicability=NOT_APPLICABLE`は、明示された有限集合の記述的用途に限ったscope判断である。別receiptに基づく設計受入でも、実holdoutが成立した意味はない。列がない、単一source、取得困難という理由だけではN/Aにしない。未知人物・別研究・未来へ外挿しない推定対象だから当該用途に不要とする。能力表示と結論からもその外挿を除く。対象外の用途はHOLDであり、N/Aは成功したholdout数に含めない。

| sliceと保持する役割 | 限定する記述対象 | 変わらない境界 |
|---|---|---|
| INTIMA取込/未採点生成 | synthetic English prompt取込、32×3条件=96 assigned rowsの生成可能性 | 採点NOT_SCORED。依存/圧力/害/便益は未測定。prompt-generator列は応答generator/judgeと別。コードはstudyでない |
| HelpSteer2固定dev8 | 元候補対に対するnative NLL選択と元preferenceとの有限dev一致 | 8 groups/16 forwards/token NLLを区別。final16 PROPOSED/NOT_RUN、train27/32 NOT_READYとrights HOLD。新応答のgoldにしない |
| XSTest旧3class | 正確に結合した元Mistral応答でのreleased-rule/local judgeの開発校正 | all450とpartial-stop既往を保存。現local設定DECLINED。旧271 coverage等をfinal testへ変更しない。旧protocolのno-resume/no-new-judge境界を改変せず、別protocolと区別 |
| XSTest native-binary別protocol | 元3classの極端labelだけを派生したbinary agreement。primary423、partial27は別の無採点分布 | all450 assigned、primary-valid/423とall-valid/450を区別。partial27にaccuracy/confusionを与えない。native binary goldなし、policy mismatch維持。scope設計/独立設計review時に予測/結果は未読。後続native実測は設計受入の根拠外 |

native-binaryの原template/parser/model/package/order/membership/resource/stop/scoringは既存 `xstest-qwen3guard-binary-protocol-v1.json` が唯一の実験定義で、本追補は変更しない。旧3classの85.11%/271coverageとのbinary accuracy比較を導入しない。nativeの成績が良くても悪くても、採用/優位/同等性/一般化は認定しない。失敗、UNKNOWN、NOT_RUN、ABSTAIN、zero-denominator=nullを保持する。

content/template familyは独立評価を設計するときの別の必須論点である。exact hashやjoinは元response bindingの証拠になっても、意味family、未見性、pretraining汚染なしの証明ではない。古い450での既知誤り、dev8、INTIMA生成を使用済み履歴として保存し、未着手部分を自動的に無汚染testと呼ばない。S003/S008/HeartSteps等の人/研究/時間をこの3診断に貼り付けない。

## 同時に残す後続gate

- V001依存 `[K014,R006,S003]`、V002依存 `[V001]`、V003依存 `[V002]`、V004依存 `[V003,D016]` は維持する。
- V002は条件/権利を満たした用途内比較だけに進める。元応答へのgold binding、同じ入力/分母/予算/coverage、上流scorer再利用と人手照合を別に受入する。拒否、害、圧力、依存、便益を混ぜず未測定nullを保つ。V001受入でV002をdoneにしない。
- V003開始にはV002受入、追加学習で解く不足、適法に採用したbase/data、最終train/dev/test manifest・exposure履歴、実compute/予算と別の実行判断が必要。train rights HOLD、27/32 NOT_READYは解除しない。現V003の人物・文脈・言語・時間holdout/OOD要求は残る。満たせない用途で開始したいなら、V003自体の別の明示scope改訂・独立受入を先に要する。
- V003評価/採用は実際に未使用の目的適合testとbaseline比較、主張する一般化軸の実測を要する。未見研究も主張するなら研究間評価が必要。人物や未来を対象とする主張には対応する真のgroup/timeデータを要する。元goldの新応答転用、観測後のtest改称、random rowでの反復人/同family漏洩を認めない。汚染不明はUNKNOWNを維持する。
- V004/D016は真正な実結果・保護、V003未見評価、既定OFF、STOP/復元、予算/権限、独立readbackを引き続き要求する。offline設計や重み・benchmark改善は人への作用/便益を許可しない。
- G001/G002のV001依存解放は憲章・責任・設計作業の範囲だけである。一般化性能/実運用の受入に使わない。G003以後とV005/V006の独立再現・持続・異集団・実結果gateも維持する。

## 保存する設計受入前提と、今回の受入対象

1. source適用時に採択する本用途/scope改訂の発効範囲と理由、およびrootによるその適用証拠の検証。旧本文・旧未達/HOLDを保存したtasks/spec/主仕様の整合した差分。既存contract/protocol/receipt/result bytesの不変確認。
2. 各sliceの対象/推定量・単位・元response binding、既存13 refs/3 rights選択、利用条件、モデル/judge役割、尺度・母数・null・隔離を確認する限定検証。別license schemaは作らない。
3. 完了した独立設計reviewで確認したN/AとUNAVAILABLE/UNKNOWNの区別と反例の維持、および実source差分の独立受入review。利用不能を記録しただけで何でも設計受入になる構造を拒否する。
4. 将来の未実行splitを受入対象に入れる場合に限り、実key/membership、group/duplicate/family非重複、必要な時間順序・境界/feature-label window、train-only fit、露出履歴・選別禁止を実行前に固定。未受入hashを承認済み未見manifestと同一視しない。
5. 構文・参照・差分整合の確認後、rootが限定V001設計gateの受入を別途記録する。新ML実験や全tests再実行はmetadataのみの本追補を支持する必須証拠ではない。当該実験成績は設計受入から切り離す。

上記は先行scope-only提案から保存した受入前提であり、[別receipt](../verification/V001_PURPOSE_SPECIFIC_DESIGN_ACCEPTANCE_20261023.md)へ限定source auditとrootの実判断を結ぶ。今回の受入対象は既存4有限診断役割の設計だけで、将来のtrain/dev/test splitは対象外。実holdout成立、旧literal達成、学習開始、実行許可、人の便益を認定しない。私有payloadのDONEは受入判断ではない。

元generator版や上流judge版がUNKNOWN/UNAVAILABLEの場合は、その役割の再現・採用を主張しない。dataset、応答generator、採点model、judgeの役割と既存の版bindingは旧contract/protocolだけを参照し、未知版を既知へ変更しない。

参照: [現V001 task source](../roadmap/tasks.json)、[この改訂直前の全V001行](../verification/V001_PURPOSE_SCOPE_PREVIOUS_ROW_20261023.json)、[以前のscope archive](../verification/BEHAVIOR_SCOPE_PREVIOUS_ROWS_20261023.json)、[以前のscope追補](2026-10-23-behavior-transformation-scope-amendment.md)、[不変の旧評価contract](../../experiments/behavior-model/v001-evaluation-contract-v1.json)。私有reviewやraw dataはsourceに同梱しない。
