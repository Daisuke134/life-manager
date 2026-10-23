# XSTest local refusal judge — 固定予算の実CPU診断

2026-10-23 UTC。元の人手goldがある同じ450回答に、既存Qwen3-0.6Bをローカルjudgeとして適用した限定診断。上流GPT judgeの再現、Manager応答への人の採点、実介入や便益の評価ではない。

## 結果と採否

実行は固定900秒の時間上限で停止した。**全450件を完了していない。** 有効271件はすべて`1_full_compliance`と判定され、元goldの完全拒否27件・部分拒否20件は検出できなかった。**今回の設定は拒否判定に採用しない。** 汎用Qwen系列全体の性能や、別設定・専用モデルの結果を否定する意味ではない。

| 方策・集計対象 | 正答 / 有効採点 | coverage | 解釈 |
|---|---|---|---|
| BASE_QWEN_JUDGE / 元割当450 | 224/271（82.66%） | 271/450（60.22%） | 有効集合内の条件付き値。全出力がcompliance |
| RELEASED_STRING_RULE / modelと同じ有効271 | 230/271（84.87%） | 271/271、元450の60.22% | 同じ観測集合内の比較。独立testではない |
| RELEASED_STRING_RULE / 元全450 | 383/450（85.11%） | 450/450 | 配布済み判定。上流string algorithmの再実行ではない |
| NO_ACTION / 元全450 | conditional accuracy=null | 0/450、450棄権 | 分類しない基準 |

モデルはassigned450 / attempted272 / generation_completed271 / valid271 / UNKNOWN1 / NOT_RUN178。invalid_label・length_limit・context_overflow・failed各0。UNKNOWN1は停止時の処理中であり、failed0から全要求の正常終了を推論しない。既知の正答数の下限は224/450（49.78%）。有効集合のgoldは224 compliance /27 full refusal /20 partial refusalで、82.66%はそのcompliance比率と一致する。

| gold / model判定 | compliance | full refusal | partial refusal |
|---|---:|---:|---:|
| compliance | 224 | 0 | 0 |
| full refusal | 27 | 0 | 0 |
| partial refusal | 20 | 0 | 0 |

完全拒否recall0/27・部分拒否recall0/20、それぞれprecision=null（予測0）、F1=0。同じ有効集合でモデルは配布ruleを上回らなかった。未完了による選択偏りがあり、450件全体のモデルaccuracy、普遍的な優劣、統計的同等性は結論しない。

未完了を誤答・正常終了・ゼロへ変換しない。conditional accuracyは有効採点集合内だけの値。observed correct/assignedは既知の正答数の下限で、未知分を誤答と補完したaccuracyではない。配布済みstring判定の全450と、model有効集合に限定した同じruleの集計を分ける。NO_ACTIONのaccuracyはnull。

refusal/complianceは回答を試みたかどうかの分類で、正確性・害・圧力・依存・行動変容・苦しみの減少とは別。限定集計を人の便益や一般化の証拠へ昇格しない。

## 事前に固定した接続

- 実装 `088acd6c13525c9b279a0e9bb58d5d0a1479b820`。[研究CLI](../../scripts/evaluate_xstest_refusal.py) / [evaluator](../../manager_core/xstest_refusal_eval.py)。通常kernel、owner、production workflowの変更なし。
- [protocol](../../experiments/behavior-model/xstest-local-refusal-judge-protocol-v1.json) は生成前の `3fb1754f8e0ab2998574b66bc7348a57ad4b8af9` で固定。SHA256 `8d5a20a4172d790ee8b0265ae44655ca35e289fed40207ac8baf6eee012cf010`。個票・prompt・hyperparameter・時間上限の事後変更、retry、resumeは0。
- [XSTest公式repo](https://github.com/paul-rottger/xstest/tree/d7bb5bd738c1fcbc36edd83d5e7d1b71a3e2d84d)、revision `d7bb5bd738c1fcbc36edd83d5e7d1b71a3e2d84d`。元Mistral応答CSV 371935 bytes / SHA256 `6a146b65a5b96ec8249729bc2db459697175125998d7cbbcc88f7688ecf31dad` と配布済みstring判定CSV 379544 bytes / SHA256 `a1ad24b837a13380a88f9748b39663add74cd992d5841db782271490dcbb41d3`。450一意IDを全文・注釈・gold完全一致で結合。agreementだけTRUE/TrueとFALSE/Falseの厳密bool対応を使う。別版のunbound prompt CSVやGPT/Meta/OpenAIラベルは使わない。
- 全450を生成前にhash順へ固定し、除外/補充しない。membership SHA256 `2978c8c38183ec86bb810afe00c88388f34273a3f7332711ef8835f07ad86cc0`。人物/研究/時間軸はUNAVAILABLE、pretraining contaminationはUNKNOWN。公開benchmarkの開発診断であり、未見holdoutではない。
- Model [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B/tree/c1899de289a04d12100db370d81485cdf75e47ca)、revision `c1899de289a04d12100db370d81485cdf75e47ca`、native safetensors。weight 1,503,300,328 bytes / SHA256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`。生成前に8 assets全byte hashをrootが確認し、guarded loaderも照合する。
- CPU/BF16/2 threads/seed42、thinking OFF、greedy、max16 new tokens。native template全文+16 reserveが2048を超えたら未attemptedのCONTEXT_OVERFLOW、truncationなし。model入力はJSON引用した元QUESTION/RESPONSEと固定rubricだけ。gold/annotation/released labelは入力しない。
- parserはterminal EOS151645/151643を要求し、`decode(skip_special_tokens=True)`後にstripした全文がexact3labelsである場合だけ有効。追加のraw special tokenが一切ないことを保証するparserではない。prose/数字/引用の補正や再生成はしない。
- torch2.8.0+cpu、transformers4.56.2、peft0.17.1、trl0.23.1、datasets4.1.1、accelerate1.10.1。offline/local_files_only、trust_remote_code=False、学習処理なし。

## 実行と停止

- 開始 `2026-10-23T17:02:13.900554Z`、終了 `17:17:15.419447Z`、wall901.519秒。
- watchdog終端は`RESOURCE_LIMIT / WALL`、子returncode−15、wrapper exit2。SIGTERMを自分のprocess groupへ送り、KILLなし、retry0。固定900秒にscan/poll/終了処理の遅延を含む。
- checkpoint内の`lane_status=RUNNING`は書き換えず、外側の終了receiptと組み合わせて中断と解釈する。`COMPLETED`やexit0の実験とは記さない。
- sampled own-process-group peak RSS 1,927,737,344 bytes（約1.80GiB）。監視閾値6GiBはkernel hard capではなく、共有mappingを重複計数し得る。環境memory.maxは8GiB。今回RSS上限には達していない。
- own PID/PGID741685をreapし、不在・残存process0をrootと独立verifierが`/proc`から確認。共有cache削除や他process停止はなし。
- stdout/stderrは各0 bytes。元のcheckpoint・実行receipt・各hashを保存し、未着手178件を自動再開しない。

実行前に全450行のcheckpointとrule/no-actionを保存し、推論前に当該行をUNKNOWNへ更新した。private outputは0600 atomic replace/fsync。third-party stdout/stderrを抑止し、元本文・生成文・gold個票をGitへ含めない。新規有料API/有料resource追加0、基盤原価はbilling未観測のUNKNOWN。packet captureによる通信非発生の証明は主張しない。

## 権利と検証範囲

[元artifactの監査](../research/2026-10-23-human-reference-artifact-audit.md)と[配布判定の照合](XSTEST_RELEASED_REFUSAL_CALIBRATION_20261023.md)から、rootは条件付きprivate評価を今回のlocal judge校正へ限定拡張した。XSTest root CC-BY-4.0、READMEのcompletion例外、Mistral公式Apache2宣言を照合したが、annotation列への個別grantは明示的ではない。source-rightsのcanonical record SHA256 `e3f0f0d53269eb52d54ebd8b2feccf8654cf433dce0fbc746a875fbbdabf434d`。raw再配布、学習/fewshot/retrieval/製品データへの利用はしない。全面的な権利保証やPII非含有保証ではない。

Sourceは17 focused / full1064(skip5) pass、fresh task review0 findings / SPEC PASS / QUALITY Approved。[exact-head公式CI39991619944](https://github.com/Daisuke134/life-manager/actions/runs/39991619944) はfull1038(skip6)、別focused6/21、1 job10 stepsすべて成功。local/official件数差の原因はUNKNOWN。CI完了17:02:07Zは実CPU開始前。既存のcheckout/setup-pythonにNode20 deprecation warningがあり、warning0とは主張しない。

fresh独立verifierは元2 CSVの全450 join、全text/gold hash、順序/membership、全policyとmatched ruleの分母/confusion/precision/recall/F1/null、未完了/cleanupを別stdlib実装で再計算し52/52確認PASS、0 findings / SPEC PASS / QUALITY Approved。rootも最終count/confusion/source/protocol/hash/PID/PGIDを再確認した。source/metadata全8pathsのfresh Astra R1はHEAD `cd27bed72283308c4c12061c8dbdde3518b07b27`で0 findings / SPEC PASS / QUALITY Approved。最終実結果と新metadataは後続R2の対象。

verifierはML/tokenizer、生成、全suiteを再実行せず、weight1.5GBの再hashもしていない。raw生成token/textは保存しない設計のため、実生成のparser適合を独立再演した証拠ではない。実行code versionは088のまま、docs-only子孫HEADは別に記録し、ancestor・許可metadata差分・実source hashで同一性を確認した。初期のHEAD==088という検証仮定は結果を観測する前に修正し、その履歴を私有reportへ残した。

cloud source guardはcanonical host path不在の実FAIL/exit2を保持。既存の明示的cloud source作業指示、canonical origin/common Git、専用worktreeを確認して継続し、guardをPASSへ変更していない。研究branchの受入であり、main統合/production昇格ではない。

| 私有証拠 | SHA256 |
|---|---|
| result.json | `a1cb86bacbf5208d006a776f48e9ee9caee2e3951ba17560956e319a379d79d6` |
| execution receipt | `0e1930171855964b2e04da50211e74ad41808bbbeb1b81cde66fe2dd2e459dce` |
| execution config | `141284ba53b770d85e3180823f10843c967d90ee9168d16d08e32fa790cfe5ec` |
| official CI log | `ab3fda22b8617d1d7e1c814112246fea8045d075cc82f0db03aabd81b10d4f85` |
| 独立照合JSON | `e15098eeebd9cd40d215e6216f70b72830729b472e3b1fe2593584d1e237d297` |
| root最終照合 | `a114419626d3c42045f5f57e574d6338fff79f60973f7b6c907b27272bacf793` |

## 次の判断

[実装・実行plan](../plans/2026-10-23-xstest-local-refusal-judge.md)の限定診断として記録する。P0 / NOT_MEASURED / can_execute=False、原113件=80 done /23 todo /10 skipped、V001/V002/V003 todoを維持。training/optimizer、HelpSteer2 final-test、production activation、人対象作用はNOT_RUN。

[専用judgeの追加一次資料](../research/2026-10-23-small-refusal-judge-reuse.md)ではQwen3Guard-Gen-0.6Bのbinary Refusal Yes/Noを確認した。次の独立比較候補で、今回の3classを途中で置き換えない。risk/toxicityと拒否を区別し、partialの扱い、revision、実LICENSE、template、CPU予算を別protocolで先に固定する。圧力/依存/害の人参照、利用可能な未見評価、実行動と結果の検証は残る。
