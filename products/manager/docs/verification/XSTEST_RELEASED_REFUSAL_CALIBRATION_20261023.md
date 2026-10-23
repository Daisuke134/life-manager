# XSTest — 配布済み拒否判定の人手参照との一致

2026-10-23 UTC。Mistral-Instructの元450応答に対する、配布済みstring-match判定と元の人手final labelの記述的比較。新しいmodel/judge生成、上流判定algorithmの再実行、Manager/INTIMA応答への採点ではない。

## 結果と判断

全450件に有効な比較pairがあり、coverage450/450、accuracy383/450（85.11%）。欠測・不正・重複・失敗・未実行・silent dropは各0。行が元の人手gold、列が配布済み判定。

| gold / 配布判定 | full compliance | full refusal | partial refusal | gold件数 |
|---|---:|---:|---:|---:|
| full compliance | 371 | 3 | 0 | 374 |
| full refusal | 37 | 12 | 0 | 49 |
| partial refusal | 23 | 4 | 0 | 27 |

| label | precision | recall | F1 |
|---|---|---|---|
| full compliance | 371/431（86.08%） | 371/374（99.20%） | 742/805（92.17%） |
| full refusal | 12/19（63.16%） | 12/49（24.49%） | 24/68（35.29%） |
| partial refusal | null（0/0） | 0/27 | 0/27 |

元goldの374/450がfull complianceであり、全体accuracyだけでは拒否の検出を説明できない。完全拒否の37/49件がcomplianceとされ、部分拒否を正しく検出した例は0/27。**この配布済みstring判定を、拒否を十分に捉える唯一の採点者として採用する根拠は得られない。** この結果から全モデル・全課題の判定器の性能を推定しない。refusal/complianceは回答を試みたかどうかで、正確性・害・圧力・依存・臨床安全や人の便益を意味しない。

precision/recallはそれぞれの分母0をnull、F1は2TP/(2TP+FP+FN)で計算する。partial refusalのprecisionはnullだがF1の分母は27で0となる。新しい閾値・filter・candidate選別を結果に合わせて導入していない。

## 原artifactと対応

[Paul RöttgerらのXSTest原著](https://aclanthology.org/2024.naacl-long.301/)と[公式固定repo](https://github.com/paul-rottger/xstest/tree/d7bb5bd738c1fcbc36edd83d5e7d1b71a3e2d84d)を参照。paperは著者2名の注釈と不同意時の3名協議によるfinal labelを記す。人のgoldは元の完全一致応答にだけ適用する。

| 固定source（revision d7bb5bd738c1fcbc36edd83d5e7d1b71a3e2d84d） | bytes | SHA256 |
|---|---:|---|
| `model_completions/xstest_v2_completions_mistralinstruct.csv` | 371935 | `6a146b65a5b96ec8249729bc2db459697175125998d7cbbcc88f7688ecf31dad` |
| `evaluation/automated_evaluation_labels/xstest_v2_completions_mistralinstruct_streval.csv` | 379544 | `a1ad24b837a13380a88f9748b39663add74cd992d5841db782271490dcbb41d3` |

両CSV各450行・一意ID450・同一ID集合。id/type/prompt/completion/annotation_1/annotation_2/final_labelをper-IDで全文完全一致確認してから集計した。agreement列だけ、事前のv3規則でTRUE/True→true、FALSE/False→falseと厳密parseし一致確認。元ファイル・本文・goldは変更していない。出力は公開可能な集計とhashだけで、元本文・個票をGitへ含めない。

## 失敗を残したprotocol改訂

最初のv1ではagreementの文字列完全一致と別prompt CSVの同一IDを要求し、FAIL_CLOSED/metrics=nullで停止した。agreementはTRUE/FALSE対True/Falseという表記差。一方、別prompt CSVと応答CSVは版付きIDと数値IDで交差集合0であり、row順でもprompt/typeの完全一致は449/450だった。別版からsafe/unsafe goldを借りたり、ID/本文を変換して対応を補ったりしない。

担当の初回要約には3 CSVのID集合が一致するという誤りがあり、rootもその要約を基にv2を固定した。元resultは不一致を正しく保存しており、最終readbackで誤記を発見。v2は未実行/metrics=nullのまま保存し、元v1 report/result/script/protocolを保持して別の訂正文を加えた。交差集合が空の比較で「列別差分0」を対応成立と読まない。

指標を一度も観測する前にv3を改めて固定した。主要2 CSV・全450応答・gold・主要accuracy/confusion/per-label指標は不変とし、agreementの真偽値parseを明示。対応未成立の別prompt CSVを入力から外し、optional safe/unsafe別集計をNOT_RUNとした。初回v1のまま成功した実験や事前固定の変更がなかった研究として報告しない。

## 用途・権利・照合の限界

[用途別一次監査](../research/2026-10-23-human-reference-artifact-audit.md)に従い、rootはCONDITIONAL_PRIVATE_EVALUATION_ONLYとして実施した。XSTestのroot CC-BY-4.0とcompletionを原licenseへ分けるREADME、[Mistral-7B-Instruct-v0.1公式Apache-2.0宣言](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.1/blob/ec5deb64f2c6e6fa90c1abf74a91d5c93a9669ca/README.md)を確認。annotation列への個別明示grantと元研究のweight commit/hashは未確認。元本文/annotationのraw再配布・学習・few-shot/retrieval・製品データには使用しない。Meta/OpenAI completionとGPT judge labelを採用していない。全面的な権利保証や商用benchmark全体への採用ではない。

workerは固定v3の一度の集計を行い、rootは元2 CSVのhash、450行全source対応、confusion、各precision/recall/F1の分子分母・nullを別実装で独立再計算して一致を確認した。一次取得時と終了時のsource bytesは不変。API・model/judge・network・依存追加は0。上流string algorithmの再実行、現在のモデルへの性能外挿、未見holdout、害・行動変容・便益は未検証。safe/unsafe別集計もNOT_RUN。

| 私有証拠 | SHA256 |
|---|---|
| v3事前protocol | `2f2fbd93e4d820d8a34d57cb4993dfe69c3d1be99643a7dde790b76ed3f619a8` |
| v3集計script | `8cef02490963e15f54dac564eba4b2e5adbdc90078c0f317456a8d5c403c8314` |
| v3 result | `e31a8e16213a9e2e758656b386da38c8db0a34d683ecf5d1505f25a9c7a18070` |
| v1訂正文 | `0c639eaa1d6cad5fa355bbd15574fe39c581b9f50dc5fdf8bd4958fdcae8bf30` |
| root独立照合JSON | `aa8dea1cde8d2d2e1275b3cc7d93d0018bfc64dd49eb53bc3e44ab57628fa7fc` |

これはV002の一部に必要な、既存の人参照と自動採点の限界を示す限定証拠。V001/V002/V003はtodo、原113件は80 done / 23 todo / 10 skippedを維持する。INTIMAの未採点生成やHelpSteer2の選好一致率にこの人手goldを転用しない。
