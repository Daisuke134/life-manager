# マネージャーの人口部品

公開集計から年齢×貧困状態の6区分を復元し、入力に渡していない交差集計と比較するPython実装。行動予測や介入効果のモデルはまだ含まない。

## 実行環境

Python 3.12、Linux x86_64で検証。依存は `requirements-population.lock` のwheel SHA256で固定した。別OSでは利用できるwheelが異なるため、このlockがそのまま使えるとは限らない。ソースcheckoutから実行する。

```bash
python3.12 -m venv /tmp/manager-population-venv
/tmp/manager-population-venv/bin/python -m pip install --require-hashes -r apps/manager/requirements-population.lock
export PATH="/tmp/manager-population-venv/bin:$PATH"
export PYTHONPATH="$PWD/apps/manager/src"
/tmp/manager-population-venv/bin/python -m unittest discover -s apps/manager/tests -v
```

## 実データで動かす

以下のコマンドはリポジトリのルートで実行する。`python` は上で依存を導入したvenvのPythonを使う。成果物はGit外へ保存する。取得にはネットワークが必要だが、以後の3工程はオフラインで動く。Census APIキーやモデルAPIは使わない。

```bash
export POPULATION_RUN=/tmp/manager-population-example
python -m manager fetch-acs --out "$POPULATION_RUN/input"
python -m manager prepare-population --input "$POPULATION_RUN/input/source.dat" --out "$POPULATION_RUN/prepared"
python -m manager reconstruct --seed "$POPULATION_RUN/prepared/seed.json" --marginals "$POPULATION_RUN/prepared/marginals.jsonl" --method independent --out "$POPULATION_RUN/independent.jsonl"
python -m manager reconstruct --seed "$POPULATION_RUN/prepared/seed.json" --marginals "$POPULATION_RUN/prepared/marginals.jsonl" --method ipf --out "$POPULATION_RUN/ipf.jsonl"
python -m manager score-population --predictions "$POPULATION_RUN/independent.jsonl" --predictions "$POPULATION_RUN/ipf.jsonl" --reference "$POPULATION_RUN/prepared/reference/all.jsonl" --manifest "$POPULATION_RUN/prepared/manifest.json" --out "$POPULATION_RUN/report"
```

同じ出力先へ異なる内容は上書きしない。再実行には新しいディレクトリを使う。数値予測は同じ入力から同じbytesになるが、run metadataの実行時間は毎回変わる。JSON/JSONLは `payload` とSHA256のenvelope形式で、`manager.artifacts.read_artifact` で検証して取り出す。ハッシュは破損検出用で、電子署名ではない。

## 2026年10月18日の実測

ACS 2020–2024 B17001、50州+DC。開発6州、検証4州、最終評価41地域を事前固定した。TVDは6区分の構成の差で、0が一致、1が最大。

|分割|単純独立法の平均TVD|IPFの平均TVD|
|---|---:|---:|
|開発6州|0.015544|0.003100|
|検証4州|0.017104|0.005243|
|最終評価41地域|0.014348|0.008881|

最終評価の地域平均では約38.1%低下した。41地域のうち29で改善、12で悪化。最大TVDは単純法0.033504、IPF0.015971。人口加重平均は0.015560と0.007666であり、地域平均と区別する。成績が悪い地域も除外していない。

ACSは調査に基づく推計値で、今回その不確実性を誤差へ伝播していない。対象は貧困状態を判定できる人口で、全住民や苦しみそのものではない。同じ資料の周辺集計から交差集計を復元した結果であり、独立の実地検証、将来予測、生活改善の実証ではない。

[処理と解釈の詳細](docs/population-v0.md)、[図付きの結果解説](../../docs/research/manager/articles/2026-10-18-population-v0-results-ja.md)。最新の進捗と作業順は[統合SSOT](../../docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md)のみで管理する。
