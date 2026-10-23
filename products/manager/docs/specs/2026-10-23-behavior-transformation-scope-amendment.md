# Manager — 行動変容へのscope改訂と、独自モデルへの道筋

2026-10-23 UTC。所有者の明示した方向転換を記録する。これは設計・受入条件の改訂であり、実装や人への便益の達成記録ではない。状態・依存は既存`../roadmap/tasks.json`、全体の入口はrepository統合SSOTに置く。

## 1. 使命と呼称

**行動変容を通じて、苦しみを終わらせることを目指す。** 組織の位置づけは **Behavior Transformation Company — Simulation / Persuasion / Intervention / Evaluation**。Managerは、その使命を継続する一つのAIエンティティ。『心の苦しみ』へ目的を限定したり、『心と行動の変容』を並列の別目的として定義したりしない。臨床mental-health研究は学ぶ根拠群の一つであり、使命全体の定義ではない。

Digital Buddha／Transparent Godは所有者の長期構想・呼称として保持できるが、仏教や特定の宗教・教義の受容を利用条件・成功指標にしない。覚り・意識・全知・AGI・全存在の苦の終結を現在証明したとは表示しない。観測するのは、本人が選んだ行動、その結果として報告される苦しみ・生活機能・持続・害・負担である。

上座部の原典を学ぶ場合、[SN56.11](https://www.accesstoinsight.org/tipitaka/sn/sn56/sn56.011.harv.html)の苦・渇愛・滅・道、[SN36.6](https://www.dhammatalks.org/suttas/SN/SN36_6.html)の痛みとそれへの反応を区別する説明を出典として扱う。これを『物理的な痛み・疾患・生活条件は無意味』という科学的結論や、動物の覚りの証明へ変換しない。宗教的説明と実験上のconstruct・測定を明記し、宗教に依存しない方法も同じ基準で学ぶ。

## 2. 今回の必須経路から外すもの

**D004、D005–D009、D012の7件をtodo→skippedへ変更する。** 金融支援の追試、室内外センサー・校正・施設比較・環境制御・電力/騒音・曝露/健康の追試、収入純増の研究を、今回の完成条件から外す。未達成でありdoneへ進めない。元の行は[改訂前archive](../verification/BEHAVIOR_SCOPE_PREVIOUS_ROWS_20261023.json)とsource commit `fb37dd25bc26dc03eac9facc9ad442a447127132`へ結ぶ。

113 IDsは保持し、**80 done / 23 todo / 10 skipped**。既存80件のdone、E01–E16/FのP2限定receipt、H005/F004/F007のwaiverを改変しない。過去のfinance/environment code・研究・公開receiptを削除しない。それらを新使命の実証へ読み替えない。費用・害・生活上の影響を測る責任は残るが、センサーや施設は現在の開発依存にしない。

**依存の改訂:** D016=`[D015,U007]`、V001=`[K014,R006,S003]`、V004=`[V003,D016]`。他の変更は台帳のscope revisionとarchiveで追跡する。V001–V003のoffline評価・独自重み研究を実パイロット全体の完了から切り離し、V004の実運用昇格では実結果と保護を要求する。

## 3. 既存の介入研究から借りるもの

以下は原著を確認した7研究で、全人類史の網羅でも、Managerの実証でもない。介入package・対象・比較・実施条件を保持する。宗教・対話app・専門家の役割を外した場合の同等性は未検証。

| 一次資料 | 実結果と限界 | 借りる部分 |
|---|---|---|
| [Heinzら、Therabot／NEJM AI 2025](https://ai.nejm.org/doi/full/10.1056/AIoa2400802) | 210人、4週介入・8週評価、待機群との比較で症状改善。全対話の品質・安全を人が監督し、専門家の迅速介入が可能だった。人間治療との直接比較や無監督運用の検証ではない | 専門的な追加学習、事前定義outcome、脱落、危機対応、一般モデルとの別比較。code/weights/dataの自由利用は未確認 |
| [Cuijpersら、WHO Step-by-Step／PLOS Medicine 2022](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004025) | 569人のRCT、behavioral activationとe-helper付き。症状と生活機能を測定し、3か月追跡。大きな脱落があり、無支援LLMへ外挿しない | 本人が選ぶ小さな行動、物語、日常での実践、文化適合、生活機能。教材・データの権利を個別確認 |
| [Tolら、WHO SH+／Lancet Global Health 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC9899129/) | 女性難民694人・14村のcluster RCT。ACT系の5回course＋facilitator。3か月K6効果d≈−.26。book単独や各成分の効果ではない | 価値に沿う行動、経験との関わり方、負担・対照・追跡。WHO manualはCC BY-NC-SA 3.0 IGO、商用転載/改変は別条件 |
| [Kuykenら、PREVENT／Lancet 2015](https://doi.org/10.1016/S0140-6736(14)62222-4) | 424人、24か月。MBCT＋薬の減量支援は維持薬に対し優越を示さず（HR .89［.67,1.18］）。同等性の証明とも言わない | 能動対照、再発・長期追跡、実施者の技能。服薬変更は研究から一般推奨しない |
| [Galanteら、Mindful Student Study／Lancet Public Health 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC5813792/) | 616人、世俗的な指導者付きcourse。試験期のCORE-OMで改善。主要結果取得74%、通常支援対照で、接触/期待の効果を分離できない | 日常の負荷がある時点でのtransfer、選べる短い実践、離脱・支援経路 |
| [Brittonら、meditation adverse effects／2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8845498/) | side effect83%を『83%が害を受けた』と書かない。負の生活機能影響は別分母。非瞑想対照がなく、一般的な因果リスク率ではない | 不調の具体的な質問、持続、機能悪化、停止。悪化を覚りへの進歩と決め付けない |
| [Tagalidouら、humor training／BMC Psychiatry 2019](https://bmcpsychiatry.biomedcentral.com/articles/10.1186/s12888-019-2075-x) | 37人の小規模RCT。主要/副次outcomeの群×時点効果はいずれも有意でない。後付けの群内改善でRCTのnullを補わない | comedyは本人の希望する探索的な表現手段。苦しみを軽視する笑いや確立治療の主張にしない |


**Mindful Student Studyのsource内不一致に関する追記案（限定訂正）:** 原著abstractに依拠した従前の試験期CORE-OM引用「−.14［−.22,−.06］」を履歴として残す。[公開原著XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC5813792/fullTextXML)、版 `PMC5813792.2`（取得UTC `2026-10-23T19:53:09.738365+00:00`、SHA-256 `6ee6aa4fc5a76a4bdadecb9186debe9f470cc541e10d28e8f81c4155fafb0506`）の本文/Table3では、−.14［−.22,−.06］は**post-intervention**、主要な**examination periodは−.25［−.34,−.16］**である。abstractと本文/Table3のtimepoint/estimate対応の内部不一致を保持し、今後primary試験期を引用する場合はTable3へ結ぶ。standardized β−.44［−.60,−.29］とも別の量で、こちらを独自の再解析値やManager効果としない。この追記案だけで他研究・scope・task状態は変更しない。

説得研究、COM-B/BCT/BCIO、HeartSteps/MRT等は[主仕様§1.2.1–1.2.3](../MANAGER_PRODUCT_SPEC.md)から再利用する。説得は理解・選択・実行を支える手段で、従順さ・宗教的同意・会話時間・依存を最大化しない。欺瞞、圧力、秘密の心理profiling、個別の政治判断を狙う最適化、他者にさせることによる権限迂回は採用しない。no UIは無告知・無同意の意味ではない。

## 4. モデルはいつ作るか

**柔軟性:** 使命と根拠の基準を保ちながら、モデル・規模・量子化・runtime・学習方法を比較で変更する。4B/GPUは必須条件ではない。[既存CPUでの実推論と複数系統の比較](../verification/LOCAL_CPU_MODEL_ACCEPTANCE_20261023.md)を追補した。GGUF推論の成功と追加学習可能性は別に測る。

**最終的に、独自に評価・追加学習・版管理できる重みを持つモデルを主体の中心へ育てる。** 最初の自前モデルは既存open-weight baseへのLoRA/SFT等を優先する。ゼロから汎用基盤モデルを学習することを初期条件にしない。重みは重要だが、実際の観測・文脈・記憶・道具・権限・結果測定も主体の振舞いを変える。既存の実行基盤を捨てることを目標にしない。

| 段階 | 進む条件／採用判断 |
|---|---|
| V001: 評価・権利・split | 利用するartifact・用途ごとにsource/版/license/対象/推定量と評価契約を確認し、適用する独立単位・splitを固定する。人物/研究/時間等の各軸を用途に照らして適用/非該当/利用不能/不明と判定し、必須軸が未成立の用途はHOLD。最終評価用に予約したdataは公開/非公開を問わず学習・few-shot・retrieval・モデル選別から隔離する。開発/校正に明示利用する公開benchmarkは露出・選別履歴を残し、後から独立した最終testと呼ばない。既存の凍結protocolの用途制限と権利条件は変更しない。設計/既存診断の受入と実未見一般化の受入を分ける。 |
| V002: 既存モデル比較 | NO_ACTION/ルール/既存API/open-weightを同条件で比較し、対象能力の不足・採点誤差・費用を記録。一般APIだけで足りる部分を再実装しない |
| V003: 最小の独自adapter | 権利確認済みbase/data、固定評価、追加学習で解く具体的な不足、利用可能な実compute/予算が揃えばoffline SFT/LoRAを開始。人対象研究全体の完了を待たない。優位がなければ採用しない |
| V003以降: SFT拡張/DPO/蒸留 | 専門的に評価したsupervision/preferenceが必要。既存judgeの同意を量産しない。蒸留はproviderの出力利用条件を満たす場合だけ。自動的なRL段階を設定しない |
| V004: 人に届く限定運用 | V003の未見評価とD016の真正な結果・保護を満たして、隔離→shadow→限定昇格。source受入・重み生成・benchmark改善と、実運用/便益の受入を分ける |
| V005/V006/G: 再現・継続 | code/recipe/版/権利に沿うadapter公開、独立再現、持続・異なる集団・失敗を検証 |
| scratch pretraining | 既存base/追加学習で解けない不足、適法な大規模corpus、実測compute/運用費、比較優位、実行体制が揃ったときの別設計。必ずscratchへ進むと約束しない |

V001の現行設計scopeは[用途別追補](2026-10-23-v001-purpose-specific-acceptance-amendment.md)を参照する。[別の限定設計受入receipt](../verification/V001_PURPOSE_SPECIFIC_DESIGN_ACCEPTANCE_20261023.md)にrootの実判断を記録した場合に限り、既存4有限役割の設計を受入する。私有統合提案の作成時点では実受入ではない。旧literalの人物・研究・時間holdout条件はUNMET/HOLDのまま保存し、既存の後続gateと本書の過去の件数は変更しない。

候補baseの[Qwen3-4B-Base](https://huggingface.co/Qwen/Qwen3-4B-Base)は公式cardと実LICENSEのApache 2.0を確認した。最初の比較候補であり、実験開始時には正確なrevision・tokenizer・recipeを固定する。学習は[PEFT](https://huggingface.co/docs/peft/index)・[TRL SFTTrainer](https://huggingface.co/docs/trl/sft_trainer)等を再利用し、新trainerを作らない。データは商用利用・追加学習の権利を確認したもの、または利用権を持つ専門家作成supervisionから始める。費用/資源未確認を0や利用可能なGPUとしない。

## 5. 特化した既存benchmarkと企業

| 一次資料 | 再利用と制約 |
|---|---|
| [CounselBench](https://github.com/llm-eval-mental-health/counselbench)・[Eval](https://huggingface.co/datasets/izi-ano/CounselBench-Eval)・[Adv](https://huggingface.co/datasets/izi-ano/CounselBench-Adv) | 専門家評価2,000件、adversarial prompts120件。相談技能・誤った前提等を評価。dataはCC BY-NC-ND 4.0で商用利用/改変/学習へ無条件投入しない |
| [INTIMA](https://huggingface.co/datasets/AI-companionship/INTIMA) | cardは368 promptsと記載するが、固定revision `48537e5d3905152751964b48d0a2ef681ace74dc` の実JSONLは380行/376 unique prompts/32 codes（4完全重複）。cardのCC BY 4.0宣言を確認。迎合・孤立・関係代替・境界を調べる英語single-turn診断で、実際の依存率や便益の試験ではない。上流judgeの完全prompt/parser/正確な版は未確認。[固定input受入計画](../plans/2026-10-23-intima-intake.md) |
| [AHaBench/AHaPairs](https://aclanthology.org/2026.findings-eacl.4/)・[data](https://huggingface.co/datasets/anonymous9268/AHaBench) | 500 prompts/5K preference pairs。過度な依存や関係上の誤認。data/codeはCC BY-NC 4.0。商用学習の無条件な選択肢としない |
| [MentalHealthBench公式発表](https://openai.com/index/introducing-mentalhealthbench/) | 最新の比較候補。今回artifact版・正確なlicenseは未確認で、導入済みとはしない。全benchmarkを初期必須化しない |

企業からは、[humans& Ampersand model card](https://ampersand.humansand.ai/blog/model-card.html)の既存baseからの長期協働学習、[Persimmon](https://persimmon.humansand.ai/blog/)のuser simulationとの分離、[Slingshot/Ash](https://www.talktoash.com/blog/building-ash)の専門モデルへの追加学習、[Limbicの公開研究code](https://github.com/LimbicAI/study-2025-cognitive-layer)のモデルと付加contextの比較、[SoulChat2.0](https://github.com/scutcyr/SoulChat2.0)の公開recipeを学ぶ。商用の主張、公開研究code、API、実weights、training corpusの権利を区別する。humans&/Ash/Limbicの自前weightsを自由に使えるとは確認していない。SoulChatもbase/data/版ごとの権利が別。Bobaはappで、Managerのno UIの先例ではない。

## 6. ストーリーと最初の対象

ストーリーは、**行動変容appへの問い → neurofeedbackへの問い → AI・simulation・評価 → 結果から学ぶ独自モデル**。A10 LabでのMarketing Intern歴は既存の公開プロフィール読戻し、当時の関心と現在へのつながりは所有者本人の今回の説明を根拠にする。アプリ開発への技術貢献や、過去研究で行動変容を実証した成果は創作しない。

初期の実対象は、非臨床の成人が自ら選ぶ一つの行動について、任意の実践・説明・振り返りが結果にどう関わるかを調べる候補とする。需要・最適対象・効果は未検証。旧U002/U003/U005の支援アクセス研究/技術proofを新対象の需要や効果へ置換しない。[新protocol草案](../../pilot/BEHAVIOR_TRANSFORMATION_STUDY_V2.md)は参加者0・NOT_REGISTEREDで、既存の120世帯/58日計画とhashを改変しない。

site sourceは既存`apps/landing/marketing/pages/en.html`と`ja.html`のhero/story/research、および3参照の`route-manifest.json`。bio/使命の訂正と新記事制作を区別する。実source更新は現mainからの専用PR、公開は既存full-site releaseと独立readbackを要する。この仕様更新自体でlive siteが変わったとは表示しない。

## 7. 今回確認した範囲

Exaのroot2検索=12結果枠、介入研究11検索=55枠、モデル研究17検索=85枠、計152検索結果枠を3観点で探索した。これは152独立原著を精読した数ではない。保持した原著・artifactは上のURLへ結び、DOI/PMC/企業pageの重複を別研究へ数えない。原典2本文も取得した。公開研究・実践・企業の全史や全言語を網羅したとは主張しない。新モデル学習・provider推論・新規課金・参加者介入・記事公開・本番変更は今回行っていない。
