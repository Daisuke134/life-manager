# V002: 小型 refusal judge 再利用候補の根拠 metadata

調査日: 2026-10-23 UTC。V002の研究設計で既存judgeを選ぶための公開資料メモ。
既存の汎用 Qwen3-0.6B / XSTest450 実験に対する条件変更は **0**。
このメモを根拠にモデル、prompt、gold、分類規則、実行条件を変更していない。

## 判断

次の独立実験の第一候補は **Qwen/Qwen3Guard-Gen-0.6B**。
公式cardで、prompt + responseから `Refusal: Yes|No` を出す専用機能を確認した。
ただし拒否のbinary判定であり、XSTestの full / partial / no refusal の3class置換は **HOLD**。
確認した範囲では、partial refusalを独立クラスとして直接出す候補は見つかっていない。

`Safe / Controversial / Unsafe` は安全性の危険度3分類で、拒否3分類とは異なる。
`Controversial` をpartial refusalへ、`Safe` をrefusalへ写像する根拠はない。
無害な回答もSafeになり得るため、harm判定とrefusal判定を混ぜない。

## 候補ごとの用途と制約

| 系列・正式ID | 確認した規模・入出力 | V002での取扱い |
|---|---|---|
| `Qwen/Qwen3Guard-Gen-0.6B` | 公称0.6B。baseはQwen3-0.6B。prompt + responseからSafety、Categories、Refusal Yes/Noを生成 | 次のbinary refusal実験候補。partial独立ラベルがないため現3class置換はHOLD |
| `Qwen/Qwen3Guard-Stream-0.6B` | 公称0.6B。token単位のrisk levelとcategory。cardの出力にRefusal欄は確認できない | riskの3classを拒否3classと扱わない。今回の拒否採点用途はHOLD |
| `ibm-granite/granite-guardian-3.1-2b` | 公称2B。harm、bias、jailbreak、RAG等のriskをYes/Noと確率で評価 | 標準refusalラベルは確認できない。custom riskは要検証。refusal用途はHOLD |
| `ibm-granite/granite-guardian-hap-38m` | 38M、4層、hidden576。英語toxicity binary、label1=toxicity | HAPはhate/abuse/profanity用途。軽さだけでrefusal judgeに採用しない |
| `LibrAI/longformer-action-ro` | 実configは12層、hidden768、6 labels、LongformerForSequenceClassification、F32 | 6 actionの意味・partialとの対応・権利が未確定。HOLD |

Qwen GenはTransformers >=4.51.0を要求する。
Streamは >=4.55.0と `trust_remote_code=True` を要求し、独自codeの静的監査が別途必要。
StreamはQwen3のtoken IDを使うため、異なるtokenizerの生成モデルでは再tokenizeと逐次入力が必要。
Granite 3.1-2Bは英語のみ訓練・評価され、所定templateによるyes/no scoring modeを指定する。
custom risk対応から、未検証のrefusal3class性能を推測しない。

HAP-125Mの存在はIBM公式検索結果と38M cardのリンクで確認したが、125M card本文は未取得。
LibrAI cardは用途・データの説明が不足し、訓練データは `None dataset` と記載されている。
WildGuard論文の一次検索抜粋ではLibrAIはresponse-onlyの6 action分類で、
比較時に0..4をrefusal、5をcomplianceへ二値化している。これはXSTest3classの定義ではない。

## 規模と8GiB CPUの未確定点

CPU推論、RSS、ロード時ピーク、レイテンシ、全件所要時間は **未実測**。
下記はweightsのみの概算で、KV cache、activations、runtime、OS、一時コピーを含まない。

- Qwen Genはcardの公称0.6Bに対し、HFの一次検索結果表示が **0.8B params**、
  tree表示のweightsが約1.5GBだった。API metadata取得は失敗し、正確なcountは未確定。
  公称値だけならBF16約1.12GiBだが、1.5GB weightsなら約1.40GiBが下限相当。
  表示差の理由を推測せず、revisionと実weights metadataを次に確認する。
- StreamのRAMはGenから流用しない。独自headとstream stateの費用は未確認。
- Granite公称2BはBF16約3.73GiB、F32約7.45GiB。F32では8GiBの余裕が乏しい。
- HAP38MはF32約0.142GiB。CPU対応は公式cardの記載であり、この環境の計測結果ではない。
- LibrAIは実configから通常構造で約149M、F32約0.55GiBの静的見積。
  実weightsの確定countではない。dataset側の「600M evaluator」をこのcheckpointのsizeと断定しない。

将来ローカルweightsを揃えればAPI/GPUなしの構成を検討できるが、導入済み・実行可能とは未確認。
本調査ではweights/tokenizer追加DL、モデル実行、依存installを行っていない。

## 権利確認の粒度

model、base、code、data、prompt、outputの条件を分け、cardタグを実LICENSE本文と区別する。

| 対象 | 確認済み | 未確認・保留 |
|---|---|---|
| Qwen Gen model repo | 実LICENSE本文のApache-2.0を取得 | baseの実LICENSE、code repo LICENSE、data全体の条件 |
| Qwen Stream | cardのApache-2.0表記とLICENSEリンク | Stream実LICENSE本文、base、remote code、data条件 |
| Granite 3.1-2B / HAP38M | cardのApache-2.0表記 | model実LICENSE本文、base・code・data各条件。2BのLICENSE取得は失敗 |
| LibrAI | model cardのApache-2.0タグ。do-not-answer **code repo** の実LICENSE Apache-2.0本文 | model weightsとbaseの実LICENSE、6 actionの公式code定義、checkpointと訓練dataの対応 |

LibrAIのdataset一次検索抜粋は、本文でdataをCC BY-NC-SA-4.0、source filesをApache-2.0と記載する一方、
frontmatterにはApache表記があり、条件の通し確認は未了。codeの許諾をdata/weightsへ転用しない。
各cardのprompt/templateに別条件は確認していない。repoのApache表記を生成outputの権利保証とは扱わない。
dataの再利用や再訓練を行う場合は、data自体の条件とモデルとの対応を先に確認する。

## 調査範囲と次の確認

Exa Search skillを読み、Exaで **4検索、12一次fetch試行、8成功・4失敗**。
対象はQwen3Guard、Granite Guardian、LibrAIの3系列。FirecrawlとAlphaXivは未使用。
網羅性は主張しない。今回の圧縮作業で追加検索・fetchは行っていない。
失敗はQwen code LICENSEとGranite2B LICENSEの `CRAWL_NOT_FOUND`、
Qwen GenとLibrAIのHF API metadataの `CRAWL_UNEXPECTED_CONTENT_TYPE`。
取得失敗を不存在と解釈しない。検索抜粋と本文取得済み資料を分けている。

Qwen論文の拒否性能は一次検索抜粋でのみ確認したpublished result。
binary定義・partial集約・評価集合は照合しておらず、現在の3class実験との性能比較には使わない。

1. 既存固定実験を変更せず完了する。Qwen Genは別のbinary実験候補として扱う。
2. 実装前にrevision、正確なweights、base/code license、template、CPU dtype、parse failure処理を固定する。
   cardのresponse例には別モデル名が混在するため、正式0.6B IDと一致させる確認も必要。
3. full/partial/noを維持する場合は置換HOLD。binaryへ集約するならpartialの扱いを新条件として事前定義する。
   LibrAIは6 actionと権利確認が揃うまでHOLD、HAPはrefusal候補から外す。

## 一次資料

- [Qwen Gen card](https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B) / [実LICENSE](https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B/raw/main/LICENSE)
- [Qwen Gen tree: size表示は検索抜粋](https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B/tree/main)
- [Qwen Stream card](https://huggingface.co/Qwen/Qwen3Guard-Stream-0.6B)
- [Qwen technical report: 検索抜粋](https://arxiv.org/html/2510.14276)
- [Granite 3.1-2B card](https://huggingface.co/ibm-granite/granite-guardian-3.1-2b)
- [Granite HAP38M card](https://huggingface.co/ibm-granite/granite-guardian-hap-38m)
- [LibrAI card](https://huggingface.co/LibrAI/longformer-action-ro) / [実config](https://huggingface.co/LibrAI/longformer-action-ro/raw/main/config.json)
- [LibrAI code実LICENSE](https://github.com/Libr-AI/do-not-answer/blob/main/LICENSE)
- [WildGuard paper: LibrAI説明は検索抜粋](https://arxiv.org/html/2406.18495v3)
- [Do-Not-Answer dataset: 条件は検索抜粋](https://huggingface.co/datasets/LibrAI/do-not-answer)
