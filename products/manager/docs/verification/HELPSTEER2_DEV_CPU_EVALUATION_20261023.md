# HelpSteer2 dev — 既存CPUモデルの実比較

2026-10-23 UTC。公開された回答候補に対する人の選好と、小型既存モデルによる候補順位を比較した、固定dev8組の限定受入。独自学習・新しい応答の評価・人の行動変容や便益の実証ではない。

## 結論

| 方策 | 元の人の選好との一致 | coverage | 評価したこと |
|---|---|---|---|
| BASE_QWEN | 4/8（50%） | 8/8 | 候補ごとの平均token NLLが小さい方を選ぶ |
| SHORTER_CANDIDATE_RULE | 4/8（50%） | 8/8 | completion token数が少ない方を選ぶ |
| NO_ACTION | conditional accuracy=null | 0/8、8組すべて棄権 | 候補選択をしない基準 |

この小さく選択されたdev batchでは、モデルが単純なルールを上回る証拠は得られなかった。両方策の選択は4/8で一致し、両方正解2・モデルのみ正解2・ルールのみ正解2・両方不正解2。同じ正答率から統計的同等性、普遍的な性能、未見testへの転移を結論しない。結果を見て候補・閾値・hyperparameterを変えたり、再実行したりしていない。

16候補を割当て、16 attempted / 16 completed、failed・unknown・unattemptedは各0。rule/no-actionのNLLはnull。人のラベルは元の完全一致候補に対する過去の評価であり、新たな生成文への人の評価ではない。害、圧力、依存、clinical competence、実行動、持続、苦しみの減少は未測定。

## 固定したsourceとデータ

- 実装commit: `9d05252e2c062a44c9553a2352d6b557f9602cb4`。専用の[研究CLI](../../scripts/evaluate_helpsteer2_dev.py)と[candidate evaluator](../../manager_core/helpsteer2_candidate_eval.py)を使用。通常kernel/owner/workflowは変更しない。
- [事前固定protocol](../../experiments/behavior-model/helpsteer2-dev-protocol-v1.json)はcommit `a344e55e5a6e4eb098d8eeee188b73f048106db3`で採点前に固定・push。SHA256 `586d8701a26305ea56ffab0d095db72d4fb64974977528d7581511ff7c8ef529`。
- Dataset: [NVIDIA HelpSteer2](https://huggingface.co/datasets/nvidia/HelpSteer2/tree/990b2711a36180dd19d9c94b8627844866f8982a)、revision `990b2711a36180dd19d9c94b8627844866f8982a`。元qualityは20324 train / 1038 validation、preferenceは9125行（raw train8677 / val448）。val→validationのsplit名だけ正規化する。
- 事前固定した8組のraw train行を元gzipから再構成し、16候補のprompt/response hash、唯一のquality join、preferenceの符号を確認。新しいjudgeやcallerの任意goldを使わない。元本文と行別ラベルはGitへ含めない。
- 公式cardのCC BY4.0とlegalcodeを確認し、出典・版・変更を保持。独立したdataset LICENSEは見つかっていない。第三者promptの権利やprivacyの普遍的な保証ではない。採用した権利recordは商用評価を条件付きとし、この運用目的の学習・製品使用・raw再配布はHOLD。
- 56組のdata-only候補固定後のAI支援内容レビューは51 retain / 5 exclude。dev8とfinal-test16は全件retain、train案は27/32でNOT_READY。これは人のannotation・承認やPII非含有の保証ではない。除外を補充せず、train・final-testモデル採点は未実施。
- Model: [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B/tree/c1899de289a04d12100db370d81485cdf75e47ca)、revision `c1899de289a04d12100db370d81485cdf75e47ca`。Native safetensors、Apache2.0。weight1,503,300,328 bytes、SHA256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`。GGUF推論artifactと混同しない。

全文は256 token以下、prompt prefix一致、assistant EOS151645を1個含める。prefixとEOS後はlabels=−100、assistant EOSまでをnative Transformers causal-LM lossで採点した。自己実装のtrainerや新しいagent harnessは作らない。exact tieはresponse hashで解決する。

## 実CPU実行と停止確認

既存8GiB cloud CPU、BF16、2 threads、seed42、local_files_only、trust_remote_code=False。torch2.8.0+cpu / transformers4.56.2 / peft0.17.1 / trl0.23.1 / datasets4.1.1 / accelerate1.10.1を固定。今回PEFT/TRLの学習処理は呼ばない。

- 実行開始 `2026-10-23T16:09:51.227983Z`、終了 `16:10:19.083956Z`、wall27.856秒、exit0。
- sampled process-group peak RSS: 1,909,272,576 bytes（約1.78GiB）。モデル読み込み前から累積900秒・RSS6GiBのwatchdogで自分の子process groupだけを監視。6GiBはscan/poll遅延のある監視閾値で、kernel hard capではない。環境のmemory.maxは8GiB。
- retry0、TERM/KILLなし。自分の子PID734336をreapし、不在・process group残存0を独立照合。共有hostのcache削除や他processの停止は行っていない。
- 新規有料API・有料resourceの追加0。基盤費用は独立したbilling観測がなくUNKNOWN。packet captureによる通信非発生の証明は主張しない。
- モデル生成、backward、optimizer、adapter学習、final-test採点、production activation、人対象作用はNOT_RUN。推論のRAM適合を確認したが、訓練のRAM適合を確認した意味ではない。

## 検証範囲

新規22 tests、既存rights/Source/OutcomeBench/INTIMA46 tests、local full1047 tests / skip5 / failure0。fresh task reviewと実結果の独立照合は各0 findings、限定SPEC/QUALITY PASS。 実装とprotocol・全metadata差分を含むfresh whole-branch reviewもHEAD `797012f9418907082417d10523c59f5d816cbbd0`で0 findings、限定SPEC/QUALITY PASS。

同じ実装commitの[公式CI39984363992](https://github.com/Daisuke134/life-manager/actions/runs/39984363992)はfull1021 / skip6 / failure0、別focused suites6・21、1 job10 stepsすべて成功。local/officialの件数差の原因は未確定。GitHub server created16:09:08Zはcompute開始前、CI完了16:09:57Zはcompute開始後。local testsとfresh source reviewはcompute前に完了していたが、公式CIも開始前に完了していたとは記さない。

独立照合では元gzipの全行count、8組の元ラベル・16 joins・hash・NLL集計・選択・分母・出力非漏洩・cleanupを確認。モデル再実行、独立再tokenize、数値NLL再現、weight1.5GBの再hashはその照合で行っていない。実行前全weight hashを要求するsource・固定download receipt・現在sizeとの結合で確認した。保存されたmetadataの整合性を受け入れる範囲である。

cloudのsource-boundary guardはcanonical host path不在による実FAIL/exit2を保持し、PASSへ書き換えていない。ownerの既存の明示的cloud source作業指示の範囲で、canonical origin/common Gitと専用research worktreeを確認して進めた。main統合や運用昇格の証明へ置き換えない。

| 私有証拠のSHA256 | 値 |
|---|---|
| result.json（25624 bytes） | `c521249f02b1772e99fc5670a2815727bc2d9d396aed27dd6b81ceb355ab83c0` |
| stdout（resultに改行1個を付加） | `7ae8e1e3f483a83312dac81d8d3eea8ff68ef979718eb460519058b33ef058c7` |
| execution receipt | `995301433983c12e0e31dca7b3ca5686f01e45a2a4c08d382b20285d70613e4b` |
| official CI log（31510 bytes） | `061a2270b077e9b085111ddde26852ada822d758f3601947ebe4745ef1fe3e8e` |
| 独立照合JSON | `e8d5c4fa3a0fccbaef6fb3f75b4bceb32a82b791b24f8fa78ce2a4bdcafe40ea` |

## 次の受入

[実装・実行plan](../plans/2026-10-23-helpsteer2-dev-likelihood.md)の限定sliceを受け入れる。P0 / NOT_MEASURED / can_execute=Falseを保持し、原113件の状態は80 done / 23 todo / 10 skipped、V001/V002/V003はtodoのまま。

次は[人の参照ラベルを持つ既存artifactの監査](../research/2026-10-23-human-reference-artifact-audit.md)に基づき、利用権と元回答の対応が成立する範囲で採点者の照合と限界を埋める。安全知識MCQ、元回答の拒否分類、generic preference、実行動・便益は別の評価として扱う。追加学習で解く具体的な不足とV002の受入が成立してからV003へ進む。今回の4/8を理由に直ちに学習・昇格したり、INTIMAの未採点96行を採点済みにしたりしない。
