# Phase 11｜全33枚・日本語発表ノート

## Slide 01｜Phase 11｜研究講義

Phase 11｜研究講義

P11-1からP11-5まで。学習成果は論文と合成実装で保存。これは製品の実ユーザー有効性や独自行動FM完成の主張ではない。

出典・参考：P11講義原稿および完全合成実験
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 02｜Phase 11の全5講義

Phase 11の全5講義

全講義はモデルと実行の境界を跨ぐが、共通の規則は『予測≠介入効果≠独立検証された価値』。

出典・参考：P11講義原稿および完全合成実験
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 03｜予測と方策価値は違う

予測と方策価値は違う

説明：P(Y|X,A)は観測の予測。／P(Y|do(A))には介入の識別仮定が必要。／NO_ACTIONも有効な候補として扱う。。
数式・概念：Predict ≠ Causal Effect。
限界：研究主張と合成例を混同しない

出典・参考：Jiang & Li 2016 / CQL 2020 / MOPO 2020
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 04｜MDPとBellman方程式

MDPとBellman方程式

説明：状態S、行動A、遷移P、報酬R、割引γ。／即時のクリックが長期の福祉改善とは限らない。／将来の負担や離脱も状態・評価対象に含める。。
数式・概念：Q = E[R + γV(next)]。
限界：研究主張と合成例を混同しない

出典・参考：Jiang & Li 2016 / CQL 2020 / MOPO 2020
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 05｜Offline RLで何が難しい？

Offline RLで何が難しい？

説明：固定ログには選ばれなかった行動の結果がない。／Qの外挿がデータ外の行動を過大評価し得る。／CQL/MOPOは保守性・モデル不確実性を扱う。。
数式・概念：No Support → No Claim。
限界：研究主張と合成例を混同しない

出典・参考：Jiang & Li 2016 / CQL 2020 / MOPO 2020
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 06｜OPEはログに存在する確率で評価

OPEはログに存在する確率で評価

説明：IPS: πe(a|x)/πb(a|x) の重み。／DR: outcome model と残差補正。／ESSが小さい場合やsupport欠落なら棄権。。
数式・概念：IPS / SNIPS / DR。
限界：研究主張と合成例を混同しない

出典・参考：Jiang & Li 2016 / CQL 2020 / MOPO 2020
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 07｜固定乱数の架空20,000件

固定乱数の架空20,000件

図は自作であり論文図の転載ではない。
真の合成policy価値 0.435。
IPS 0.43551 / DR 0.43539。
全ての合成数値は架空である。

出典・参考：Jiang & Li 2016 / CQL 2020 / MOPO 2020
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 08｜本当の研究の受入条件

本当の研究の受入条件

説明：割付と実配信を区別し、propensityを保存。／人単位の分割・欠測・事前停止を検査。／新しい方策は同意・独立比較を経てから評価。。
数式・概念：Experiment ≠ Product。
限界：研究主張と合成例を混同しない

出典・参考：Jiang & Li 2016 / CQL 2020 / MOPO 2020
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 09｜個人は孤立していない

個人は孤立していない

説明：友人・家族・推薦・制度が行動に影響。／ネットワークG=(V,E)上の相互作用を記述。／社会的影響の因果と観測相関を区別。。
数式・概念：Individual ≠ Society。
限界：研究主張と合成例を混同しない

出典・参考：Park 2023 / OASIS 2024 / AgentSociety 2025
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 10｜ABMとGenerative Agents

ABMとGenerative Agents

説明：個体の記憶・規則・環境から集団を模擬。／Parkら2023の町では25体が相互作用。／自然な会話は未知集団での予測証拠ではない。。
数式・概念：Believable ≠ Predictive。
限界：研究主張と合成例を混同しない

出典・参考：Park 2023 / OASIS 2024 / AgentSociety 2025
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 11｜OASIS / AgentSociety

OASIS / AgentSociety

説明：SNSの投稿・推薦・つながりをモデル化。／1万〜100万規模の設計・模擬研究が公開。／分布・時間・文化・少数集団を外部検証する。。
数式・概念：Scale ≠ Validity。
限界：研究主張と合成例を混同しない

出典・参考：Park 2023 / OASIS 2024 / AgentSociety 2025
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 12｜HomophilyとContagion

HomophilyとContagion

説明：同類選好・共通曝露・因果的伝播は別。／見かけの友人間一致が100%でも因果影響0もあり得る。／ネットワークがあるとSUTVAが破れ得る。。
数式・概念：Correlation ≠ Influence。
限界：研究主張と合成例を混同しない

出典・参考：Park 2023 / OASIS 2024 / AgentSociety 2025
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 13｜4ノードの合成構造方程式

4ノードの合成構造方程式

図は自作であり論文図の転載ではない。
近隣曝露率 e_i = treated neighbors / neighbors。
架空のaの期待値は0.20+0.30=0.50。
全ての合成数値は架空である。

出典・参考：Park 2023 / OASIS 2024 / AgentSociety 2025
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 14｜評価の多層性

評価の多層性

説明：個人NLL・集団TVD・ネットワーク統計。／拡散曲線・干渉・長期変化の別評価。／現実の因果実験を模擬出力に置き換えない。。
数式・概念：Multi-Level Validation。
限界：研究主張と合成例を混同しない

出典・参考：Park 2023 / OASIS 2024 / AgentSociety 2025
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 15｜Distributed Cognition

Distributed Cognition

説明：認知は人・道具・記録・手順に分散。／Hutchins 1995の航海作業研究が理論の基礎。／AI同士の会話も「全体システム」で評価。。
数式・概念：System > Individuals。
限界：研究主張と合成例を混同しない

出典・参考：Hutchins 1995 / Anthropic 2025 / Google 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 16｜協調の4つの構造

協調の4つの構造

説明：Single / Central / Decentralized / Hierarchical。／通信経路は完全グラフn(n−1)/2。／10体で45ペア、スターでは9本。。
数式・概念：Topology Matters。
限界：研究主張と合成例を混同しない

出典・参考：Hutchins 1995 / Anthropic 2025 / Google 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 17｜AnthropicとGoogleの実測

AnthropicとGoogleの実測

説明：並列化可能な研究はsubagentsで分担可能。／Anthropicはトークン増大を報告。／Googleは180構成で逐次タスクの悪化を報告。。
数式・概念：More ≠ Better。
限界：研究主張と合成例を混同しない

出典・参考：Hutchins 1995 / Anthropic 2025 / Google 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 18｜Amdahlと通信オーバーヘッド

Amdahlと通信オーバーヘッド

説明：並列率pと調整費が処理時間を決定。／12架空タスク、単体120。／2 worker: 並列90%=74、並列10%=122。。
数式・概念：SYNTHETIC TIME。
限界：研究主張と合成例を混同しない

出典・参考：Hutchins 1995 / Anthropic 2025 / Google 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 19｜共通エラーと独立監査

共通エラーと独立監査

図は自作であり論文図の転載ではない。
二体の誤りが独立ならp²。
完全相関なら同時誤りはpのまま。
全ての合成数値は架空である。

出典・参考：Hutchins 1995 / Anthropic 2025 / Google 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 20｜Managerで役割をどう分ける？

Managerで役割をどう分ける？

説明：Research / Analysis / Builder / Verifier。／権限はLLMの自己申告から付与しない。／成功率だけでなく総費用と誤りを評価。。
数式・概念：Measure Per Work。
限界：研究主張と合成例を混同しない

出典・参考：Hutchins 1995 / Anthropic 2025 / Google 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 21｜基盤モデルの定義

基盤モデルの定義

説明：複数領域の人間の選択確率を学習。／人・研究・時間・文化の未知データで評価。／行動予測と介入の因果効果を分離。。
数式・概念：Predictive Foundation。
限界：研究主張と合成例を混同しない

出典・参考：Binz et al. Nature 2025 / BehaviorBench 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 22｜Nature Centaurを元論文から

Nature Centaurを元論文から

説明：Psych-101：160実験・60,092人・1,068万選択。／Llama3.1 70BにQLoRA rank8。／回答tokenだけにloss。A100 80GBで約5日。。
数式・概念：Real Paper Facts。
限界：研究主張と合成例を混同しない

出典・参考：Binz et al. Nature 2025 / BehaviorBench 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 23｜BehaviorBenchの設計

BehaviorBenchの設計

説明：行動予測/戦略/特徴/知識の4能力。／個人精度と集団分布の一致を分離。／公開比較は実測条件と権利を明記。。
数式・概念：Individual + Distribution。
限界：研究主張と合成例を混同しない

出典・参考：Binz et al. Nature 2025 / BehaviorBench 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 24｜LoRAと負の転移

LoRAと負の転移

説明：W' = W + (α/r)BA。／複数タスクの勾配が競合する場合がある。／PCGrad/EWC等の効果は外部実験で検証。。
数式・概念：Shared ≠ Superior。
限界：研究主張と合成例を混同しない

出典・参考：Binz et al. Nature 2025 / BehaviorBench 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 25｜相反する2領域の合成結果

相反する2領域の合成結果

図は自作であり論文図の転載ではない。
Shared logloss: A .677 / B .717。
Specialist: A .395 / B .433。
全ての合成数値は架空である。

出典・参考：Binz et al. Nature 2025 / BehaviorBench 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 26｜BFMの正しい受入条件

BFMの正しい受入条件

説明：人物/研究/時期/文化/領域Holdout。／校正・OOD・棄権・負の転移を検査。／ライセンスと再配布権も別Gate。。
数式・概念：Evidence & Rights。
限界：研究主張と合成例を混同しない

出典・参考：Binz et al. Nature 2025 / BehaviorBench 2026
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 27｜Domain Shiftを分類

Domain Shiftを分類

説明：Covariate / Label / Concept / Temporal。／特徴の割合だけ変わるのか、規則自体が変わるのか。／領域移植に万能な補正はない。。
数式・概念：P_train ≠ P_target。
限界：研究主張と合成例を混同しない

出典・参考：Arjovsky et al. 2019 / Bailey et al. 2015
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 28｜Transportabilityの仮定

Transportabilityの仮定

説明：効果修飾因子を十分に観測する。／対象集団に重なりがある。／ATE_T = Σ CATE_S(z) P_T(z)。。
数式・概念：Assumptions First。
限界：研究主張と合成例を混同しない

出典・参考：Arjovsky et al. 2019 / Bailey et al. 2015
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 29｜架空の効果移植計算

架空の効果移植計算

説明：元研究：A/B半数、効果 .30/.10→平均.20。／対象：A20%/B80%なら .14。／条件付き効果の移植可能性が必要。。
数式・概念：SYNTHETIC .14。
限界：研究主張と合成例を混同しない

出典・参考：Arjovsky et al. 2019 / Bailey et al. 2015
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 30｜金融でのBacktest Overfitting

金融でのBacktest Overfitting

説明：大量の候補を試すと偶然の勝者が出る。／過去と未来を分けるだけでなく試行数も記録。／手数料・流動性・リスクを含む必要。。
数式・概念：Best Past ≠ Future。
限界：研究主張と合成例を混同しない

出典・参考：Arjovsky et al. 2019 / Bailey et al. 2015
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 31｜150の架空ゼロ技能戦略

150の架空ゼロ技能戦略

図は自作であり論文図の転載ではない。
過去最良+0.537、同戦略の未来−0.0365。
架空取引費後−0.0665。
全ての合成数値は架空である。

出典・参考：Arjovsky et al. 2019 / Bailey et al. 2015
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 32｜他領域へ広げるGate

他領域へ広げるGate

説明：独立の未来期間・別母集団で評価。／選択したベンチマークをtestへ混ぜない。／規制・権限・資本リスクは別審査。。
数式・概念：No Automatic Transfer。
限界：研究主張と合成例を混同しない

出典・参考：Arjovsky et al. 2019 / Bailey et al. 2015
このスライドでの推論と実際の人間への因果効果を区別する。

## Slide 33｜Phase 11まとめ / 次はP12-1

Phase 11まとめ / 次はP12-1

P11-1〜5の5つの区別を確認。教材/38 tests/公開記事は証拠の種類を分けて報告する。次の正式学習はP12-1（第三者再現）。

出典・参考：P11講義原稿および完全合成実験
このスライドでの推論と実際の人間への因果効果を区別する。
