# map: heartsteps-r004

問い: HeartStepsの方法・結果・限界を、実装前に原典へ固定する。
最初の検索語: "HeartSteps" "kay067" methods analysis availability 2019

## 要る主張
- [x] 知見の場と一次資料はどこか: PMC原著、付属資料、著者GitHub。provenance.json参照。
- [x] 何人・どの時点が実際に解析されたか: sources/sample.md（原著Sample/Decision Points）。
- [x] 何を無作為化して何を測定したか: sources/methods.md（原著Methods、補足I–III、解析コード）。
- [x] どの効果にどれだけの不確実性があるか: sources/results.md（主要解析と二次解析を分離）。
- [x] 「何が本当に実証されたのか」、苦しみ軽減まで言えるか: sources/limitations.md（Discussion/Limitations）。

## 用語
MRT、availability、decision point、proximal outcome、centered and weighted least squares、secondary analysis。

## 人
Klasnja、Smith、Seewald、Lee、Hall、Luers、Hekler、Murphy（対象論文著者）。Boruvkaら（原著参考文献23）。現在の所属を推測していない。

## 場
Annals of Behavioral Medicine / PMC / 著者のHeartStepsV1データ案内 / StatisticalReinforcementLearningLab解析コード。

## 原文（sources/）
ここには全文を置かず、短い抜き書きと位置を保存する。日本語メモは引用ではない。

| 資料 | 保存ファイル | URL | 来歴 |
|---|---|---|---|
| 〔論文・測定あり〕対象と除外 | sources/sample.md | https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ | 0周目: DOI・題名検索 |
| 〔論文・測定あり〕方法 | sources/methods.md | https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ | 1周目: 補足・参考文献・著者コードを追跡 |
| 〔論文・測定あり〕結果 | sources/results.md | https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ | 1周目: 主要/二次/感度分析を区別 |
| 〔論文・測定あり〕限界 | sources/limitations.md | https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ | 反証ルートとDiscussion/Limitations照合 |
| 〔著者補足〕統計詳細 | provenance.json, OPEN_REPRODUCTION_QUESTIONS.md | https://pmc.ncbi.nlm.nih.gov/articles/instance/6499406/bin/kay067_suppl_supplementary_materials.docx | 本文のSupplementary Materialから追跡 |
| 〔著者コード〕主効果の解析 | provenance.json, OPEN_REPRODUCTION_QUESTIONS.md | https://github.com/StatisticalReinforcementLearningLab/HeartstepsV1Code/blob/c077c86d20b5d9cfa937f7ed1720172d726ba9a0/Main%20Effects%20Analysis.R | データREADMEから解析リポジトリへ追跡 |

## 次の手がかり
R005は別タスク。再現時の未確定点はOPEN_REPRODUCTION_QUESTIONS.mdを参照。資料の不一致を都合よく修正しない。
