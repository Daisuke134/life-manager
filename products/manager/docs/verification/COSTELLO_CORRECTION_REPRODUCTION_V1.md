# Costello correction — actual finite reproduction

2026-10-24 UTC。A01–A04の有限offline研究の実結果。Managerの新規介入、独自model優位、苦しみ低減、全V002/V003完了のreceiptではない。

Source: Costello/Pennycook/Randの[Science原著](https://www.science.org/doi/10.1126/science.adq1814)、[Dryad version8](https://doi.org/10.5061/dryad.v6wwpzh4h)、[Zenodo record22754984 version1.0](https://doi.org/10.5281/zenodo.22754984)。[来歴と用途](../research/2026-10-24-costello-correction-reuse.md)・[artifact manifest](../../experiments/behavior-model/costello-correction-artifacts-v1.json)を参照。

## 実行

上流の`scripts/build_results.R`と`scripts/validate_analysis.R`を変更せず、入力原本/配布precomputedとは別の作業copyで実行した。R4.5.3、broom1.0.13、dplyr1.2.1、readr2.2.0、tidyr1.3.2、lme4 2.0.6、ggeffects2.3.2、emmeans2.0.4、pbkrtest0.5.5、lmerTest3.2.1。上流lockはR4.5.0等の別versionで、環境のexact再現ではない。

```sh
Rscript --vanilla scripts/build_results.R
Rscript --vanilla scripts/validate_analysis.R
```

buildは2026-10-24T11:59:07.300242Z開始、11:59:08.467118Z終了、exit0、1.166897秒。初回validationはemmeans不足で停止。追加後はpbkrtest/lmerTest不足による追跡区間/pの4不一致を記録した。必要な依存を導入し、元の式/期待値/許容差を変更せず最終validationは12:02:20.799090Zにexit0、2.772375秒で終了した。失敗した2回のreceiptは保全した。

最終上流validatorの7部すべてPASS: ordinary-lm headline、correction record、S7/S8全cell、participant flow、released persistence models、Study2b protest models、frozen forest summary。forestは保存集計の確認で再学習していない。political behaviorを誘導するmodel/policyの実装・配信は行っていない。

## 数値結果

| 対象 | screened N | OLS model N | treatment係数 | classical95%CI |
|---|---:|---:|---:|---|
| Study1 | 748 | 738 | −16.5549703072 | [−19.5150102063, −13.5949304080] |
| Study2 pooled | 1346 | 1306 | −12.8358244919 | [−15.3539826650, −10.3176663188] |

単位は0–100の本人報告confidence slider point。screened cohort平均の事前値における、割付条件と事前値の交互作用を含むOLSのtreatment係数。全個人への同じ効果や、苦しみ/真偽の改善量ではない。

correction_results13行、headline_records6行、headline_comparison_ledger3行、participant_flow_assertions15行、S7/S8各4行の計6表45行を上流配布表と全cell照合した。numeric許容差1e−10内で一致、最大差7.389644451905042e−13。文字fieldも一致。履歴値やd等の一部は上流script内の定数であり、45行すべてを独立に推定したとはしない。浮動小数点の表記差により、数値一致とfile bytes一致は異なる。

追跡validatorは10日630人/1883observations、2か月489人/1951observationsの元条件を使う混合モデルを再fitし、指定contrast/CI/pの許容差1e−6でPASS。非有意な直後対追跡差を同等性の証明とせず、追跡者への条件付け/脱落があることを明記する。survey reconstruction/全figure/PDF/補足文書/全archive validatorを再実行したわけではない。

## 次の研究に使える範囲

公開primaryは2094行でpost欠測50。公開participant bridgeを確認した範囲でwave横断重複0。次の[数値forecast設計](../plans/2026-10-24-costello-numeric-forecast.md)はtrain128/dev584/evaluation762の別研究で、今回の原著効果再現と分ける。devのbaselineだけを実測し、evaluationのbaseline/model採点は未実施。公開/QC曝露をpristine holdoutへ変換しない。

新LLM推論/学習/API呼出し0、新規Manager参加者0、介入0。費用はUNKNOWN、新たな有料provider/計算契約は追加していない。source-boundaryは既存cloud例外下の実FAIL2で、guard変更や偽PASSはない。通常GitHub source統合/CIの結果は別の実readbackで扱う。
