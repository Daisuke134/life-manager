# RSI-Anything / MASSから学ぶ自己改善

2026-10-12、静的調査。両repoをscratchへcloneし、論文PDFの方法・評価節、公式README/blog、主要コードと再現上の説明を確認。モデル/GPU学習、外部API、研究benchmarkの実行はしていない。Managerへの統合も未実施。

## 調査した固定source

- [RSI-Anything](https://github.com/Gen-Verse/RSI-Anything): `99dbf000a424b9033651b1096c5da2b6d5fa3865`。Apache-2.0はproject-owned code。第三者モデル/データ等は別条件。[論文](https://arxiv.org/abs/2610.13912)。
- [MASS](https://github.com/SakanaAI/mass): `fb403581bed2c974b3f99e7236224169da643079`。[公式説明](https://pub.sakana.ai/mass/)、[論文](https://arxiv.org/abs/2610.12176)。`NOTICE.md`に独自コードへpublic open-source license未付与と明記。方法の理解と製品へのコード再利用を区別し、後者は許諾確認が必要。

## RSI-Anything

候補生成→結果予測→選択→外部feedback→更新→採用、という方式。world modelは、見えた状態と変更候補から結果を予測する。JEPA系の表現予測にtask-specific readoutを加える。code-repairの `world.py` ではLoRA encoder、256次元表現、4因子、EMA target、実行状態class/時間readout、表現予測・分類・資源・順位lossを確認した。これは特定実装であり人口モデルの完成品ではない。

`evaluation.py`は4修正候補と現状維持を比較する。最大の修正utilityが現状より高い場合だけ修正を選ぶ。同じcoding modelのままでも選択/予測が良くなるかを調べられる。論文のcode-repair成功率26.3→29.2→31.2%は予測選択とworld adaptationの著者報告で、31.2ppの改善ではない。

policyを改善すると、world modelが見る候補/状況の分布も変わる。予測単独とpolicy単独が良くても、組み合わせたシステムが良くなるとは限らない。論文はcomponent/pair checks、update budget、固定した評価条件、必要時の予測モデル更新を扱う。実測と想像内の結果を別provenanceにする。

`src/rsi_anything/workflow/runner.py`ではstage記録、出力hash、source/config identity、排他lock、resume時の整合確認を読んだ。再現/再開できる実験の管理として参考になる。runnerがあることと科学的結果を再現済みであることは別。

Managerでは環境変更の候補と応答/状態モデルの更新ペアへ応用できる。Life Managerではコード修正/業務手順の選択と失敗率・費用・実売上のreadbackへ応用候補。市場の実売上を予測利益に置き換えない。

## MASS

同じモデルをexecutor、workflow optimizer、in-loop evaluatorへ使うhomogeneous RSI。内側では重みを固定し、役割・指示・出力契約・呼び出し順を探索する。外側では選ばれた手順の実行trajectoryを集めてLoRA SFTし、次世代モデルで繰り返す。自己評価だけで社会の改善が確定する仕組みではない。

公開方法では18rollouts/taskを生成、自己比較をBradley–Terryで順位化し、最大15train+1validationを選ぶ。オーケストレーターの初期workflow文を学習promptから除き、調整/実行の能力を学ぶ。`mass/ranking.py`、`mass/judging.py`、`training/prepare_sft_data.py`、`training/train_sft_lora.py`と `docs/paper_to_code.md`を読んだ。assistant出力を学習targetにし、tool結果等をcontextとしてmaskする。

研究はQwen3.6-27Bで2cycle。12synthetic tasks、9designated trainから8がSFTへ寄与、3test。testはSFT/validation/checkpoint選択に含めないがworkflow searchの評価にも使われる。4研究benchmarkのscore/output-tokenの改善は1.2–1.6倍という著者報告。全学習/探索費用を含む1.6倍効率ではない。Terminal-Bench/SWE-benchへのtransferは低下もある。永久に単調改善する証明ではない。

`docs/reproduction.md`では現在のfixed bare-reference＋champion arbitrationが論文の直接retained-best比較と異なること、2cycle目budget/比較tournamentなど再構成上の選択があること、歴史run ledgerの不在を確認。`docs/experiment_coverage.md`ではMLR107task設定や複数benchmark adapter未同梱などを確認。cloneだけで全報告値を再現できない。

## Managerへ取り込む設計案

三段階を分ける。第一はデータ/予測の更新、第二はworkflow/変更選択の更新、第三はモデル重みの更新。記憶やpromptに過去結果を足すだけをweight learningと書かない。

まずfixed-model workflow改善を比較する。人口/制度が未知のheldoutで、同じ全費用と試行数、生活上の目的、集団別の悪化、制約違反を測る。改善案は実行系のsandboxで試し、現行との比較に通ったpolicy/modelペアだけを採用する。実地への適用は権限と実地評価を別に必要とする。

改善trajectoryが十分で学習の追加価値がある場合にだけSFTへ進む。モデルが提案・内部評価を担当できても、最終の実観測結果と固定heldoutを勝手に書き換えさせない。objective/metric version、model/policy pair、dataset/split、費用、失敗、rollback先をrelease記録へ含める。accepted versionを次cycleへ残すことで改善を持続させる。

多agent数や「自己改善」という名前ではなく、same-budgetの性能、保持された改善、未知条件へのtransfer、悪化の検出/復旧を成果として扱う。Managerの使命は固定の一指標で完全に表せないため、指標更新は独立したレビューとversioningで扱い、過去との比較可能性を保存する。
