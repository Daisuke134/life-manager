# 公開human reference artifactの用途別監査

2026-10-23。SafetyBench / ELEPHANT / PersuSafety / MindEval / XSTest / WildGuard / StrongREJECTの7候補について、既存の私有一次資料監査と取得receipt（XSTestの狭い追加確認を含む）から、公開可能なmetadata・方法・集計事実だけを整理した。本文の整理自体では新しい検索・推論・人手評価を行っていない。XSTestの追加確認では別途4 GETを実施し、以下へ反映した。対象候補の限定監査であり、世界の全データを調べたとの主張ではない。

目的は、行動変容を通じて苦しみを終わらせることを目指すManagerのoffline評価に、既存研究をどこまで再利用できるかを具体化すること。宗教の受容を採点条件にしない。本書は研究memoであり、権利台帳・spec・タスク状態を変更しない。V001/V002の完了、INTIMA生成物の人手採点、臨床効果、人の便益を示すものではない。

## 用途別の結論

**SafetyBenchには、配布者がdataset側にもMITを明示する人手検査済みMCQ正解がある。XSTestとStrongREJECTには、元model responseへ付いた実人手ラベルがある。XSTestのMistral分は下記の条件付き非公開評価へ進めるとrootが判断したが、annotation列の明示scopeには解釈が残る。StrongREJECTの商用data採用はremote許諾が未確認。** 一方、既存論文の方法・公開集計値から学ぶことは、raw dataをManagerの商用benchmarkへ採用する判断と分けて進められる。

| 候補 | 確認した人手参照の意味 | 進められる用途 | 商用offline評価採用に残る限定事項 |
|---|---|---|---|
| SafetyBench | 人手で検査・修正したMCQの正解。自由文responseへのharm採点ではない | 配布者MITの条件下でsafety knowledge評価の候補。正解・ID・scorerは取得済み | 元試験問題/他datasetの権利連鎖は全件未監査。自由文の圧力・依存・自律性へ読み替えない |
| ELEPHANT | 450例のexpert評価は論文に報告。取得した小datasetでは、そのgold/votesを識別できず | 公開論文・rubric・取得済みschemaの研究。human-written回答baselineとexpert採点を区別 | OSF expert artifactのlocator・原response対応・license scope。大results ZIP内部はUNKNOWN |
| PersuSafety | 論文に人手検査報告。取得CSVは人手訂正後goldと識別できない | 圧力・依存等の15strategy定義と、0/1/2採点契約の研究 | raw response/human correctionの対応とdata別許諾。`human_eval`という名前だけで採用しない |
| MindEval | human annotation fileの存在をlegacy treeで確認、本文/schemaは未取得 | 公開方法・code/data権利分離の研究 | code Apacheをdataへ適用できない。dataは最新READMEにNC条件、旧human artifactの別商用grantは未確認 |
| XSTest | 元responseに2名の注釈と協議後final label。主にrefusal/compliance | 固定Mistral450応答と配布string判定の条件付き非公開比較。新生成不要 | prompt CC-BY-4.0とoutput原条件を分離。Mistral公式Apache宣言確認済み、annotation列の明示scopeは未確認。raw再配布/学習/製品使用へ拡張しない |
| WildGuardTest | 論文にprompt harm / response harm / refusalの3名独立注釈とmajority gold | 方法・test/train来歴の研究。正規取得後の直接的harm/refusal校正候補 | HF取得gate未通過。ODC-BY表示だけで追加条件・実schema・data権利を確定しない |
| StrongREJECT | 1,361元responseへの実人手ordinal評価を取得。論文にjudgeとの比較値 | 公開研究の記載値・scale・欠測・source keyの監査 | OSF node license未設定、元素材の権利が混在。配布自動score未取得で再計算も未実施 |

「knowledge MCQの正解」「人間が書いた回答」「model responseへの人手gold」「LLMによる自動採点」は別である。人手との一致やbenchmark改善があっても、人への実行動・苦しみ・害の因果効果を測ったことにはならない。

## 1. SafetyBench: 正解を使える限定的knowledge評価

一次資料: [paper v2](https://arxiv.org/html/2309.07045v2)、[公式repo固定版](https://github.com/thu-coai/SafetyBench/tree/960833692a1ec82b191ff3e902daca7993c35cc1)、[LICENSE全文](https://github.com/thu-coai/SafetyBench/blob/960833692a1ec82b191ff3e902daca7993c35cc1/LICENSE)、[dataset card固定版](https://huggingface.co/datasets/thu-coai/SafetyBench/blob/70538631943dc1517ae9bb0733251809f4445d0e/README.md)。

- Git tree/source revision: `960833692a1ec82b191ff3e902daca7993c35cc1`。HF revision: `70538631943dc1517ae9bb0733251809f4445d0e`。
- `opensource_data/test_en.json`: **11,435件 / 5,110,687bytes**、SHA256 `517648d44a68c79e5d46a284837d673c578fa53a45785c83407cd8358602c547`。
- `opensource_data/test_answers_en.json`: **11,435正解 / 729,736bytes**、SHA256 `a26ec13deeb551d68f71d61dd269d05dd43c24e6b22d8be3b93788ee10cf8615`。
- ID集合一致、一意ID 11,435、選択肢範囲外の正解0、category不一致0。Mental Healthは**1,566件**。2/3/4択が混在する。

dataset cardが`license: mit`と明示し、repo LICENSE全文もMITであることを確認した。codeのMIT表示だけに依拠した判断ではない。notice保持等を条件とする配布者許諾のある評価候補だが、第三者試験問題・既存dataset由来部分の原権利まで全件検証したわけではない。学習・raw再配布・製品投入の判断を自動的に加えない。

paper §3.2–3.3は、既存human annotation、試験問題の解答、LLM生成問題の人手検査/修正を説明する。rowごとのrater votesや出所列はない。HF cardには「test正解未公開」という旧説明が残るが、GitHub READMEは2025-07-28公開を記載し、上記正解fileも実在する。

upstream `eva.py`は選択肢indexの一致を全gold分母で集計し、LLM judgeは不要。次の狭い作業は、既存Source/hash/reproduction manifestとprediction scorerへこのMCQ contractを対応付けること。拒否・parse failure・未測定を別に保持する。Mental Health正解率を自由文助言の安全性や臨床的妥当性に置き換えない。

## 2. ELEPHANT: 小datasetのschema確認後もexpert goldは未特定

一次資料: [paper v2](https://arxiv.org/html/2505.13995v2)、[公式repo固定版](https://github.com/myracheng/elephant/tree/61f7044fc0e11defc971dfaa9bc84d7340fa88eb)、[CC0 LICENSE全文](https://github.com/myracheng/elephant/blob/61f7044fc0e11defc971dfaa9bc84d7340fa88eb/LICENSE)、[著者README](https://github.com/myracheng/elephant/blob/61f7044fc0e11defc971dfaa9bc84d7340fa88eb/README.md)、[OSF project](https://osf.io/r3dmj/)。OSFの閲覧は著者READMEが公開案内する共有先を使用した。共有tokenは本書へ転載しない。

Git tree/source revisionは`61f7044fc0e11defc971dfaa9bc84d7340fa88eb`。paper §3.2/Appendix Cには**3 expert annotators・450例、3metric各150例**の独立注釈とmajority対GPT-4o一致の報告がある。

OSF visible rootは2 ZIP、child nodes/wikiは0。両ZIP末尾のHTTP 206 Rangeでdirectory全件を確認し、小さいdataset ZIPだけを追加取得した。

| artifact | 取得範囲・版 | bytes・SHA256 |
|---|---|---|
| `datasets.zip` / OSF GUID `4chzv` | version 1、全bytes/hashと全5CSV schemaを検査 | 6,651,747 / `859dc4f5f3a8486c09184918e67728d6a233ed55e7e5a0bede383bacc87c8122` |
| `elephant_full_results.zip` / GUID `cjwfe` | version 1、105 entryのdirectoryのみ。本文未取得 | OSF宣言230,468,789bytes。宣言hash `60d1871420a6740768da7cb91a1d2cb3ab46a7d1007f41f1021aba98894e25e2`はfull bytes未照合 |

5CSVの実件数はOEQ **3,027**、AITA-NTA-OG **1,591**、AITA-NTA-FLIP **1,591**、SS **3,777**、AITA-YTA **2,000**。malformed row0、OG/FLIPのIDは各1,591一意・欠測0。full OGは`id,original_post`を持ち、GitHub sampleと同一schemaではない。

OEQ/AITA-YTAの`human`/`top_comment`は人間が書いた回答。`validation_human,indirectness_human,framing_human`はREADME上その回答をLLM scorerへ通した値であり、専門家がmodel responseへ付けたgoldとは区別する。全5CSVには専門家450例のsubset、原model response、独立rater票、majority goldを識別できる列がなかった。results directoryにもexpert/gold/annotationと識別できる個別file名はなかったが、**大ZIP内CSVに対応列が含まれるかはUNKNOWN**。

GitHubのCC0全文は確認済み。OSF匿名metadataにはlicense属性/relationshipが返らず、ZIP directoryにもLICENSE entryはない。OSF data・expert annotationへのCC0 scopeと、Reddit/既存研究/助言column等の原権利は未確認。次は450例の正確なmember/columns locator、response-ID/hash対応、data grantを特定する。一般datasetのLLM採点をexpert goldへ読み替えてgapを埋めない。

## 3. PersuSafety: human検査の論文報告とCSVのgold来歴を分ける

一次資料: [paper v1](https://arxiv.org/html/2504.10430v1)、[公式repo固定版](https://github.com/PLUM-Lab/PersuSafety/tree/892bf057f2974c1d1624f37d1110dcb4924e4fd6)、[MIT LICENSE全文](https://github.com/PLUM-Lab/PersuSafety/blob/892bf057f2974c1d1624f37d1110dcb4924e4fd6/LICENSE)、[対象CSV](https://github.com/PLUM-Lab/PersuSafety/blob/892bf057f2974c1d1624f37d1110dcb4924e4fd6/results/selfchat_conv/scores/gpt-4o_human_eval.csv)。

source revision `892bf057f2974c1d1624f37d1110dcb4924e4fd6`。CSVは**15対話 / 51,723bytes**、SHA256 `de6aa3fda0cfedbc384831f635b8f0425c900bfb50767df905677eb5f666a141`。列はtask/context/fact/conversationと`eval_scores`で、独立rater列・訂正前後・final majority列はない。

paper Appendix B.1はNLP/HCIのCS PhD学生2名による独立検査、不同意時の訂正、92.6%一致を報告する。しかし配布CSVのどの値が人手確認/訂正後かは識別できない。ファイル名の`human_eval`や`gpt-4o`だけからgold来歴や生成modelを確定しない。

`strategy_eval.py`はPressure and Coercion / Creating Dependency等15strategyを0=absent、1=ambiguous、2=clearで採点する。codeには`claude-3-5-sonnet-20241022`、temperature=0、`ast.literal_eval`があるが、top-level API呼出しを持つためoffline処理として無条件importしない。MIT codeと、paperの「for research purposes」というdata案内から、remote response/human correctionの商用grantを推測しない。

次は既存rubricを害の検出契約として照合し、対象15対話と人手訂正goldの対応・data別許諾を特定する。説得成功を人への便益や有害手段の報酬にしない。

## 4. MindEval: code Apacheとdata NCを分離

一次資料: [master README固定版](https://github.com/SWORDHealth/mind-eval/blob/f870ac90ccbba911942c097c502c12c90d808627/README.md)、[Apache LICENSE](https://github.com/SWORDHealth/mind-eval/blob/f870ac90ccbba911942c097c502c12c90d808627/LICENSE)、[legacy tree](https://github.com/SWORDHealth/mind-eval/tree/1c17f9e66c092d9480c4bda5a2bebc80b7f84961)。

master revision `f870ac90ccbba911942c097c502c12c90d808627`はMindEval2。READMEは**code Apache-2.0、models/data CC-BY-NC-SA-4.0、MQM judge promptもNC対象**と明記し、MindEval1とscore非互換とする。

legacy tree `1c17f9e66c092d9480c4bda5a2bebc80b7f84961`で`human_annotations.jsonl` **2,152,477bytes**と`human_user_turns.jsonl` **2,751,505bytes**の存在を確認した。これらの本文は未取得で、実schema・human gold件数・file SHA256はUNKNOWN。legacy treeにLICENSEを確認できず、旧human artifactの別商用grantも未確認。最新条件が過去の許諾を取り消したとは推測しないが、最新code Apacheをそのdataへ適用しない。

次は旧human artifactに適用する明示grantの既存証拠を確認する。NC data/promptをcopyして商用評価adapterへ取り込まず、公開方法・codeの研究と分ける。

## 5. XSTest: 実人手refusal gold、条件付きの非公開評価

一次資料: [NAACL paper](https://aclanthology.org/2024.naacl-long.301/)、[公式repo固定版](https://github.com/paul-rottger/xstest/tree/d7bb5bd738c1fcbc36edd83d5e7d1b71a3e2d84d)、[LICENSE全文](https://github.com/paul-rottger/xstest/blob/d7bb5bd738c1fcbc36edd83d5e7d1b71a3e2d84d/LICENSE)、[READMEの権利区別](https://github.com/paul-rottger/xstest/blob/d7bb5bd738c1fcbc36edd83d5e7d1b71a3e2d84d/readme.md)。

revision `d7bb5bd738c1fcbc36edd83d5e7d1b71a3e2d84d`。promptは**450件（safe250/unsafe200）**、model response CSVは5系統各450件。paper §4.2は著者3名のうち2名が注釈し、不同意を3名で協議してfinal labelを決めると記載する。

監査したMistral-instruct CSVは**450行 / 371,935bytes**、SHA256 `6a146b65a5b96ec8249729bc2db459697175125998d7cbbcc88f7688ecf31dad`。2名annotation/final labelの欠測0。final labelの集計はcompliance374、full refusal49、partial refusal27。これは実際の原responseへの人手注釈である。ただしcomplianceは回答を試みたという意味で、正確性・害のなさを保証するlabelではない。

READMEは**prompt CC-BY-4.0 / model completionsはMeta・Mistral・OpenAIの原license**と区別する。paperの生成modelはMistral-7B-Instruct-v0.1。狭い追加4 GETでは、[公式model card](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.1/blob/ec5deb64f2c6e6fa90c1abf74a91d5c93a9669ca/README.md)とAPIのApache-2.0宣言、[Apache標準全文](https://www.apache.org/licenses/LICENSE-2.0.txt)を確認した。固定revisionは`ec5deb64f2c6e6fa90c1abf74a91d5c93a9669ca`。そのmodel repoには独立LICENSE/NOTICE fileがなく、「model固有LICENSE実読取済み」とは記さない。今回のcard/標準本文にNCやoutput専用の商用禁止は確認されなかった。元研究のweight commit/hashはUNKNOWN。4 GETは200成功3・301応答1で、redirect再取得0。検索0。

rootのCC-BY全文とcompletionだけを原licenseへ分けるREADMEは、作者由来のannotationを同repo許諾下で扱う合理的な根拠になる。ただし積極的なCC-BY文言はpromptを名指しし、annotation列への個別grantは明記しない。Apacheが第三者生成文や人のannotationまで一括許諾するという意味にはしない。

rootは、この範囲と不確実性を記録した**CONDITIONAL_PRIVATE_EVALUATION_ONLY**として、Mistral450元responseの人手final labelと配布済みstring判定の記述的比較を進めると判断した。出典・版・hash・attributionを保持し、raw本文/個別annotationを再配布せず、train/SFT/DPO/few-shot/retrieval/製品データへ転用しない。Meta/OpenAI completionやGPT judge labelの条件を確認したとはせず、最初の比較から除く。これは用途を絞った運用判断で、全面的な権利保証・権利台帳の採用ではない。

同じ原response/ID/hashを全450件で照合してから比較でき、新しいmodel生成・GPUを必須にしない。refusal/complianceは回答の試行/拒否の分類であり、正確性・response harm・圧力/依存・便益を測らない。配布string判定の再集計と、上流判定algorithmの再実行も別に記録する。

**その後の限定再集計:** [Mistral450応答の配布string判定を元human goldと比較](../verification/XSTEST_RELEASED_REFUSAL_CALIBRATION_20261023.md)した。全体383/450一致でも、full-refusal recall12/49・partial-refusal recall0/27で見落としが大きい。別prompt版との対応未成立によりsafe/unsafe別集計はNOT_RUN。v1失敗・v2未実行・指標前v3改訂と、初回要約誤記の訂正を保持する。上流algorithm再実行や新model judgeの検証ではない。

## 6. WildGuardTest: 直接的なharm/refusal候補、取得gate未通過

一次資料: [paper v1](https://arxiv.org/html/2406.18495v1)、[公式repo固定版](https://github.com/allenai/wildguard/tree/495b9dc837be594c6c5665b0f7f56169baf0d5be)、[code LICENSE](https://github.com/allenai/wildguard/blob/495b9dc837be594c6c5665b0f7f56169baf0d5be/LICENSE.md)、[dataset API](https://huggingface.co/api/datasets/allenai/wildguardmix)、[固定dataset](https://huggingface.co/datasets/allenai/wildguardmix/tree/d29c47f41c8b51348b5c8e8c81c039b3132b66d1)。

code revision `495b9dc837be594c6c5665b0f7f56169baf0d5be`、dataset revision `d29c47f41c8b51348b5c8e8c81c039b3132b66d1`。APIはtest config `wildguardtest`、file `test/wildguard_test.parquet`、data license表示`odc-by`を返す。codeはApache noticeであり、dataへ適用しない。

paper §3.2は**1,725 prompt-response pairsを起点**に3名がprompt harm / response refusal / response harmを独立注釈し、2名以上一致でgoldを作り、不一致項目を除くと説明する。κは順に.55/.72/.50。1,725を3label非欠測の最終配布行数とは断言しない。trainのGPT-4 label＋部分human auditを、testのhuman goldと混同しない。

HFはauto-gated。Responsible Use Guidelinesへの同意、所属/連絡先/目的等の入力を要求し、匿名README raw GETは401だった。**正規取得gateは未通過**。実parquetのbytes/hash/schema/最終件数、ODC-BY全文と追加条件の適用は未確認。classifierのoutput keysをparquetの実schemaと見なさない。

次は既存の正規取得artifact/利用条件があれば確認し、条件成立後にtest fileだけを固定する。training set・weights・GPUを開始条件にしない。pressure/dependency/autonomy専用の人手goldがあるとの根拠もないため、この候補で全保護を測れるとはしない。

## 7. StrongREJECT: 公開人手artifact実在、published metricsは未再現

一次資料: [paper v2](https://arxiv.org/html/2402.10260v2)、[公式repo固定版](https://github.com/dsbowen/strong_reject/tree/7a551d5b440ec7b75d4f6f5bb7c1719965b76b47)、[MIT LICENSE全文](https://github.com/dsbowen/strong_reject/blob/7a551d5b440ec7b75d4f6f5bb7c1719965b76b47/LICENSE)、[公式download案内](https://github.com/dsbowen/strong_reject/blob/7a551d5b440ec7b75d4f6f5bb7c1719965b76b47/Makefile)、[OSF file API](https://api.osf.io/v2/files/jwmqe/)、[OSF node license metadata](https://api.osf.io/v2/nodes/j69tc/?include=license)。

Git tree/source revision `7a551d5b440ec7b75d4f6f5bb7c1719965b76b47`。取得したOSF `labelbox.csv`は**version1 / 1,361行 / 1,770,466bytes**、SHA256 `7a5928a4f09b4cbfce274001873ccf095510d5a990f8be52e4323d4c069fbad2`。実bytes hashはOSF宣言と一致する。

paper §3.1はLabelBox labelersが4modelの原responseを1〜5で評価したと報告する。CSVの`label_0..4`は公式cleanerの`(score-1)/4`で0〜1へ写した値で、`label_median`はnonmissing中央値。今回の中央値再計算は不一致0。人手labelであり、LLM scoreだけのdataではない。

- nonmissing raters: 5名1,084行、4名60行、3名14行、2名26行、1名177行。全行を独立5名goldと呼ばない。
- unique prompt **39**（paperの60-prompt subsetとは不一致、理由未確認）、unique prompt-response pair **1,331**、jailbreak methods **17**。
- `(forbidden_prompt,jailbreak,model)`は全1,361行で一意。human median=0は1,035行、>0は326行。別個のhuman refusal/harm/dependency/autonomy列はない。

code LICENSEはMITだが、remote OSF nodeは **`node_license: null`**。READMEは元promptにMITとno-license素材の混在を明記し、clean CSVには元source/license列がない。remote response・annotationの商用grantと元権利の対応は未確認。**学術的な方法・公開数値の読解と、Manager商用benchmarkへのdata採用を区別し、後者はHOLDを維持する。**

paper Table 1はStrongREJECT rubricの**bias .012 / MAE .077 / human>0 MAE .196 / Spearman .846**を報告する。これは**論文記載値で、今回の独立再計算値ではない**。公開された`labelbox_evals.csv`は未取得で、computed MAE/bias/correlation/score coverageはUNKNOWN。公開研究にhuman calibration報告があることと、Manager judgeを検証済みにすることは別である。

固定公式codeのSpearmanはGPT-3.5-Turbo-0613だけを対象に、jailbreak別平均同士を相関する。単純な全response間相関ではない。生成scriptはscore保存前にresponse列を削除し、入力artifact hashを埋め込まない。次は既存の配布score artifactとその入力版bindingを確認し、一意source key・原response hash・scaleの対応が成立した場合だけ一度結合する。今回join0、新AI呼出し0。元response同一性を確立せずに論文metricsを再現したとは言わない。

## 次に進める順序と評価の限界

1. **safety knowledgeを測る限定作業**はSafetyBenchの固定正解・既存scorerを候補にする。全gold分母、拒否、parse failure、未測定を分け、SSOTの採用条件へ照合する。自由文の害評価を終えたことにしない。
2. **既存研究のjudge方法を理解する作業**は、StrongREJECTの公開Table 1・公式scale/欠測/分母の監査を使える。商用data採用や新推論を先に要求しない。
3. **response harmとrefusalの直接校正**は、WildGuardTestの正規取得条件とtest artifact固定、又はXSTest Mistralの上記条件付き非公開refusal比較を進める。一括の「全候補blocked」で終わらせない。
4. **社会的迎合・圧力・依存・自律性**は、ELEPHANT expert artifact locatorとPersuSafety human correction対応が残る。INTIMAの生成物へ他研究のhuman goldを付け替えない。公開rubricを使う場合も独自judge protocolを別versionにし、原benchmarkの完全再現とは呼ばない。
5. 採用するtestはtrain/SFT/DPO/few-shot/retrievalから隔離する。公開benchmarkでは人物/研究/時間holdout全体や臨床効果は成立しない。未確認はUNKNOWNとして残し、新介入・運用昇格・V001/V002完了へ進めない。

本書に元prompt/response、個別label行、私有保存場所、共有tokenは含めていない。記載したhash・版・件数・license条件は既存取得物の監査結果であり、本書作成時に新しい外部readbackや採用判断を行ったものではない。
