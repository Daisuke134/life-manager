# 世帯人口v0（8B）

## 何ができたか

Rhode Islandの2020–2024 ACS 5-year PUMSから通常居住世帯の見本を読み、所属する個人を結んで、世帯単位で複製する。出力は世帯一覧と個人一覧のCSV。8Aの集計表に加え、各個人がどの仮想世帯に属するかを持つ。

2026年10月18日の実行では、20,182世帯・45,755人の見本から、調整後の441,570世帯・1,042,763人を生成した。これは見本を重みに応じて複製した仮想人口で、実在の住民名簿や住所を復元したものではない。既存MITの公開ソースで、有料モデル呼び出しは0。BN、VAE、GAN、拡散モデル、LLMは今回実行していない。

## 再実行

リポジトリのルートで実行する。Python3.12と、[README](../README.md)のhash固定依存を利用する。ソースcheckout向けで、raw/runはGit外へ保存する。

```bash
export PYTHONPATH="$PWD/apps/manager/src"
export HOUSEHOLD_RUN=/tmp/manager-household-example
python -m manager fetch-households --out "$HOUSEHOLD_RUN/input"
python -m manager prepare-households --input "$HOUSEHOLD_RUN/input" --out "$HOUSEHOLD_RUN/prepared"
python -m manager synthesize-households --prepared "$HOUSEHOLD_RUN/prepared" --method baseline --out "$HOUSEHOLD_RUN/baseline"
python -m manager synthesize-households --prepared "$HOUSEHOLD_RUN/prepared" --method calibrated --out "$HOUSEHOLD_RUN/calibrated"
python -m manager score-households --prepared "$HOUSEHOLD_RUN/prepared" --run "$HOUSEHOLD_RUN/baseline" --run "$HOUSEHOLD_RUN/calibrated" --out "$HOUSEHOLD_RUN/report"
python -m unittest discover -s apps/manager/tests -v
```

取得以後はオフラインで動く。同じ入力とseedならweights.jsonと両CSVが一致する。経過時間などrun metadataは毎回変わるため、新しい出力先で実行する。JSONは既存のSHA256付きenvelope形式、CSVは通常のUTF-8。source/config/code/input/outputの識別を保存し、異なる既存ファイルを上書きしない。manifestが最後に保存されるまで実行完了としない。

## データと所属

公式のcsv_hri.zipとcsv_pri.zipから、SERIALNOで住宅と個人を結ぶ。2024配布CSVの州列はSTATEで、古いST列を前提にしない。NPが人数、HHTが世帯種別、SPORDERが世帯内の個人番号、RELSHIPPが続柄。通常世帯はTYPEHUGQ=1かつNP>0とし、1,503空き家と4,070のGQ placeholderおよび対応するGQ個人を分けた。GQは寮や施設などの集団居住を指し、この世帯人口に混ぜていない。

元ファイルは住宅25,755行、個人49,825行。対象20,182世帯では、NPと所属個人数がすべて一致した。出力には新しいhousehold_id/person_idを付ける。元の世帯を2組選ぶ場合は構成員全員を2組作る。人数、続柄、年齢などの元属性と所属を出力後に再読して検査する。出力の地理は州44であり、実住所やPUMAへの精密な配置は行っていない。

PUMSは公開用に秘匿処理された標本で、Census公式ReadMeは住宅集計にWGTP、個人集計にPWGTPを使うよう説明している。今回の複製回数は世帯のWGTPを基準にする。一つの世帯に属する全員を同じ回数複製するため、個々のPWGTPを使って別々に人数を合わせる処理とは異なる。

## 調整と整数化

比較するbaselineはWGTPの比例スケール。calibratedは家族/非家族×1人/2人/3人以上の重み集計を、公式B11016の世帯種別別合計と人数構成別合計へIPFで合わせる。非家族世帯には同居人など複数人の世帯もある。家族世帯の1人は定義上あり得ない0として保つ。資料のない世帯タイプへ微小値を足して発明しない。

調整には既存ipfn1.4.4を使い、周辺集計の最大絶対残差/世帯総数が1e-10以下、1000反復以内を別途検査する。調整後のセル値と元セル値の比を、各世帯の重みに掛ける。セル内の世帯の相対重みは保つ。

重みが12.4なら、整数部分の12世帯を採用する。全世帯の整数部分を採った後、目標までの残りを各重みの端数に比例して抽選する。これがTRS（truncate–replicate–sample）。seedは20261018、入力はSERIALNO順で固定し、追加で10seedの変動幅を記録する。世帯総数は一致するが、世帯種別や世帯人数の内訳、総人数まで同時に厳密一致するとは限らない。

## 実測

|方式と段階|6区分TVD|周辺集計の最大差|世帯数|人数|
|---|---:|---:|---:|---:|
|調整前・重み|0.00233938|1,021世帯|441,570|1,041,476|
|調整後・重み|0.00051085|約0.000014世帯|441,570|約1,042,732.63|
|調整後・整数|0.00054352|17世帯|441,570|1,042,763|

調整前の元WGTPは、この資料では総数が目標と等しく、すでに整数だったため、整数化しても同じ結果になった。調整後の整数人口ではTVDが約76.8%小さくなった。これは一つの州の、この6区分の比較であり、あらゆる属性や地域での改善率ではない。8Aの年齢×貧困TVDとは対象も区分も違い、値の大小から優劣を比較できない。

TVDは6区分の構成比の絶対差を足して半分にした値で、0が一致する。採点用のB11016交差セルはsynthesizeに渡さず、scoreだけが読む。調整に使った周辺集計と採点用交差集計は同じ表由来で、PUMSも元のACS調査と重なる。完全に独立した調査や将来予測による検証ではない。

調整後の整数化を10seedで繰り返したTVDは0.00045519〜0.00058201だった。これは整数化の乱数による幅で、ACS調査の不確実性を表す信頼区間ではない。調整後の個人年齢割合は、元PUMSをPWGTPで集計した参考値と最大約0.70ppの差が残った。生成人数1,042,763人も、PWGTPで数えた対象個人1,057,168人とは一致しない。個人用の制約を調整に入れていないため、この差は成功として隠さず報告する。

## 既存実装から採った考え方

PopulationSimの固定commitにあるexpand_households.pyとwrite_synthetic_population.pyを読解し、整数の世帯重みから展開し、新世帯IDと元世帯の属性を結ぶ形を参考にした。PopulationSim本体のlist balancingや整数最適化を再現・統合した実装ではない。コードはコピーせず、最小のCSV実装を作った。TRSの概念はLovelace/Ballasの既存手法に基づく。複数レベルの制約を同時に厳密に満たすソルバーや、個人・世帯の階層モデルは後続の比較候補である。

## 限界と次の接続

実測しているのは人口の構成とデータ整合である。見本にない家族構成を発見した、地域転移を実証した、行動を当てた、苦しみを減らした、とはしない。年齢や性別の公開コードを使うが、現実の全属性や経験を表現できるわけでもない。ACSのreplicate weightsによる推計誤差の伝播は未実装。見本の所属を保つことは、あらゆる現実上の妥当性の保証ではない。

次の行動モデルは、この仮想の個人や世帯に状況を与えて選択を予測する部品になる。移動・生活時間など用途に合う別の実観測で学習・評価し、人口の精度と行動の精度を分けて測る。

[図付き記事](../../../docs/research/manager/articles/2026-10-18-household-v0-results-ja.md)、[公開集計記録](../../../docs/research/manager/evidence/2026-10-18/household-v0-summary.json)。図や記事はGitHubの素材で、ブログやSNSへの投稿は今回実行していない。

## 一次資料

- [住宅ZIP](https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year/csv_hri.zip)
- [個人ZIP](https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year/csv_pri.zip)
- [2024 PUMS辞書](https://www2.census.gov/programs-surveys/acs/tech_docs/pums/data_dict/PUMS_Data_Dictionary_2024.pdf)
- [B11016定義](https://api.census.gov/data/2024/acs/acs5/groups/B11016.json)
- [B11016公式Summary File](https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b11016.dat)
- [PopulationSim固定参照](https://github.com/ActivitySim/populationsim/tree/21881f0094680afbe11e2839124dfca10e61a2d2)
- [TRSを含む整数化の原論文](https://arxiv.org/abs/1303.5228)
